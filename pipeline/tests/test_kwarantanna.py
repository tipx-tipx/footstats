"""Brama publikacji: kwarantanna rynków + flaga poza_publikacja w logu."""

from footstats.jobs import rozliczanie


def _rec(mk: str, p: float, wynik: str, ts: int = 0, **kw) -> dict:
    return {
        "rynek_kod": mk, "rynek": mk, "p_model": p, "wynik": wynik,
        "kickoff_ts": ts, "sugestia": False, **kw,
    }


def _log(recs: list[dict]) -> dict:
    return {f"k{i}": r for i, r in enumerate(recs)}


def test_kwarantanna_lapie_rynek_ponizej_deklaracji():
    # 20 typów po 72%, weszło 8 (40%) -> bias ~0.61 < 0.80
    recs = [
        _rec("fouls_committed", 0.72, "wygrany" if i < 8 else "przegrany", ts=i)
        for i in range(20)
    ]
    kw = rozliczanie.rynki_kwarantanna(_log(recs))
    assert "fouls_committed" in kw
    assert kw["fouls_committed"]["n"] == 20
    assert kw["fouls_committed"]["bias"] < rozliczanie.KWARANTANNA_PROG_BIAS


def test_zdrowy_rynek_zostaje_w_publikacji():
    # 20 typów po 72%, weszło 15 (75%) -> bias > 1
    recs = [
        _rec("shots", 0.72, "wygrany" if i < 15 else "przegrany", ts=i)
        for i in range(20)
    ]
    assert rozliczanie.rynki_kwarantanna(_log(recs)) == {}


def test_za_mala_proba_nie_jest_oceniana():
    recs = [_rec("sot", 0.8, "przegrany", ts=i)
            for i in range(rozliczanie.KWARANTANNA_MIN_N - 1)]
    assert rozliczanie.rynki_kwarantanna(_log(recs)) == {}


def test_okno_kroczace_pozwala_wrocic():
    # stare 40 przegranych, świeże 40 wygranych — okno widzi tylko świeże
    stare = [_rec("tackles", 0.7, "przegrany", ts=i) for i in range(40)]
    swieze = [_rec("tackles", 0.7, "wygrany", ts=100 + i) for i in range(40)]
    assert rozliczanie.rynki_kwarantanna(_log(stare + swieze)) == {}
    # i w drugą stronę: świeża zapaść wchodzi do kwarantanny mimo dobrej historii
    assert "tackles" in rozliczanie.rynki_kwarantanna(
        _log([_rec("tackles", 0.7, "wygrany", ts=i) for i in range(40)]
             + [_rec("tackles", 0.7, "przegrany", ts=100 + i) for i in range(40)])
    )


def test_typy_poza_publikacja_ucza_kwarantanne():
    # typy z flagą poza_publikacja LICZĄ SIĘ do oceny rynku (inaczej rynek
    # w kwarantannie nie miałby czym udowodnić powrotu)
    recs = [
        _rec("shots", 0.72, "wygrany", ts=i, poza_publikacja="kwarantanna_rynku")
        for i in range(20)
    ]
    assert rozliczanie.rynki_kwarantanna(_log(recs)) == {}  # zdrowe wyniki
    recs_zle = [
        _rec("shots", 0.72, "przegrany", ts=i, poza_publikacja="limit_meczu")
        for i in range(20)
    ]
    assert "shots" in rozliczanie.rynki_kwarantanna(_log(recs_zle))


def test_dopisz_nowe_niesie_i_awansuje_flage():
    log: dict = {}
    b = {
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 123,
        "podmiot_id": 7, "podmiot": "Jan Testowy",
        "rynek_kod": "shots", "rynek": "Strzały",
        "linia": 0.5, "strona": "powyzej", "p_model": 0.8,
        "poza_publikacja": "kwarantanna_rynku",
    }
    rozliczanie._dopisz_nowe(log, [b])
    rec = next(iter(log.values()))
    assert rec["poza_publikacja"] == "kwarantanna_rynku"
    # ten sam typ opublikowany w kolejnym cyklu (bez flagi) — awansuje
    rozliczanie._dopisz_nowe(log, [{**b, "poza_publikacja": None}])
    assert not rec.get("poza_publikacja")


def test_kalibracja_uczy_sie_na_typach_poza_publikacja():
    # 30 rozliczonych typów poza publikacją: przeszacowany rynek musi
    # dostać ujemną deltę logitową mimo braku publikacji
    recs = [
        _rec("shots", 0.85, "wygrany" if i < 12 else "przegrany", ts=i,
             poza_publikacja="kwarantanna_rynku")
        for i in range(30)
    ]
    bias = rozliczanie.compute_bias_full(_log(recs))
    assert "shots" in bias
    assert bias["shots"]["global"] < 0


def test_cap_logit_poszerzony_w_dol():
    lo, hi = rozliczanie.BIAS_CAP_LOGIT
    assert lo <= -0.75  # zmierzone błędy wymagały delty ~-0.6
    assert hi == 0.40


def test_skutecznosc_pokazuje_poza_publikacja_bez_liczenia():
    dzien = 86400
    publ = [
        {**_rec("shots", 0.7, "wygrany", ts=10 * dzien), "kurs": 1.5,
         "podmiot": "A", "faktyczna": 2},
        {**_rec("shots", 0.7, "przegrany", ts=10 * dzien), "kurs": 1.5,
         "podmiot": "B", "faktyczna": 0},
    ]
    poza = [
        {**_rec("fouls_committed", 0.7, "wygrany", ts=10 * dzien),
         "kurs": 1.4, "podmiot": "C", "faktyczna": 3,
         "poza_publikacja": "kwarantanna_rynku"},
    ]
    dni = rozliczanie.skutecznosc_per_dzien(publ, poza=poza)
    assert len(dni) == 1
    d = dni[0]
    # liczniki tylko z publikowanych, typ w tle w osobnych polach i liście
    assert d["rozliczone"] == 2 and d["trafione"] == 1 and d["okazje"] == 2
    assert d["poza_n"] == 1 and d["poza_trafione"] == 1
    assert len(d["typy"]) == 3
    # typ poza publikacją na końcu listy, z flagą
    assert d["typy"][-1]["poza_publikacja"] == "kwarantanna_rynku"
    assert all(not t.get("poza_publikacja") for t in d["typy"][:-1])


def test_kalibracja_wazy_swieze_rozliczenia_mocniej():
    # ta sama liczba trafień/pudeł, ale pudła ŚWIEŻE (duże ts), trafienia
    # stare — ważona kalibracja musi być bardziej ujemna niż nieważona
    dzien = 86400
    stare_traf = [_rec("shots", 0.75, "wygrany", ts=i * dzien) for i in range(20)]
    swieze_pudla = [
        _rec("shots", 0.75, "przegrany", ts=(40 + i) * dzien) for i in range(20)
    ]
    log = _log(stare_traf + swieze_pudla)
    # bez capa, żeby porównać czyste delty (cap przycinałby oba wyniki)
    bez_capa = (-3.0, 3.0)
    wazona = rozliczanie.compute_bias_full(log, cap=bez_capa)["shots"]["global"]
    # kontrola: te same rekordy z jednym ts (wagi równe)
    log_plaski = _log([{**r, "kickoff_ts": 0} for r in stare_traf + swieze_pudla])
    plaska = rozliczanie.compute_bias_full(
        log_plaski, cap=bez_capa,
    )["shots"]["global"]
    assert wazona < plaska
