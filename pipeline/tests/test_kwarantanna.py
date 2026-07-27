"""Brama publikacji: kwarantanna rynków + flaga poza_publikacja w logu."""

from footstats.jobs import rozliczanie


def _rec(mk: str, p: float, wynik: str, ts: int = 0, kurs: float = 1.5,
         **kw) -> dict:
    return {
        "rynek_kod": mk, "rynek": mk, "p_model": p, "wynik": wynik,
        "kickoff_ts": ts, "sugestia": False, "kurs": kurs, **kw,
    }


def _log(recs: list[dict]) -> dict:
    return {f"k{i}": r for i, r in enumerate(recs)}


def _seria(mk: str, n: int, wygrane: int, kurs: float, **kw) -> list[dict]:
    """n rozliczeń rynku, z tego `wygrane` trafionych, kurs stały."""
    return [
        _rec(mk, 0.72, "wygrany" if i < wygrane else "przegrany", ts=i,
             kurs=kurs, **kw)
        for i in range(n)
    ]


def test_kwarantanna_lapie_rynek_ktory_traci():
    # 20 typów po kursie 1,4, weszło 8 -> ROI = (8*0,4 − 12)/20 = −44%
    kw = rozliczanie.rynki_kwarantanna(_log(_seria("fouls_committed", 20, 8, 1.4)))
    assert "fouls_committed" in kw
    assert kw["fouls_committed"]["n"] == 20
    assert kw["fouls_committed"]["roi"] < rozliczanie.KWARANTANNA_ROI_WEJSCIE


def test_zdrowy_rynek_zostaje_w_publikacji():
    # 20 typów po kursie 1,6, weszło 15 -> ROI = (15*0,6 − 5)/20 = +20%
    assert rozliczanie.rynki_kwarantanna(_log(_seria("shots", 20, 15, 1.6))) == {}


def test_rynek_zle_skalibrowany_ale_dochodowy_zostaje():
    """Sedno bramy ROI: karą jest zdjęcie z publikacji, więc mierzymy
    pieniądze, nie zgodność z deklaracją.

    20 typów zapowiadanych na 72%, weszło 11 (55%) — dawna brama biasowa
    (0,79 < 0,80) wstrzymałaby rynek. Przy kursie 2,2 ROI to +21%.
    """
    kw = rozliczanie.rynki_kwarantanna(_log(_seria("sot", 20, 11, 2.2)))
    assert kw == {}


def test_za_mala_proba_nie_jest_oceniana():
    recs = [_rec("sot", 0.8, "przegrany", ts=i)
            for i in range(rozliczanie.KWARANTANNA_MIN_N - 1)]
    assert rozliczanie.rynki_kwarantanna(_log(recs)) == {}


def test_bez_kursu_rynek_jest_niemierzalny():
    # ROI bez kursu nie istnieje — same pudła, a mimo to brak werdyktu
    recs = [{**_rec("shots", 0.7, "przegrany", ts=i), "kurs": None}
            for i in range(40)]
    assert rozliczanie.rynki_kwarantanna(_log(recs)) == {}


def test_okno_kroczace_pozwala_wrocic():
    # stare 40 przegranych, świeże 40 wygranych — okno widzi tylko świeże
    stare = _seria("tackles", 40, 0, 1.5)
    swieze = [{**r, "kickoff_ts": 100 + i}
              for i, r in enumerate(_seria("tackles", 40, 40, 1.5))]
    assert rozliczanie.rynki_kwarantanna(_log(stare + swieze)) == {}
    # i w drugą stronę: świeża zapaść wchodzi do kwarantanny mimo dobrej historii
    zapasc = [{**r, "kickoff_ts": 100 + i}
              for i, r in enumerate(_seria("tackles", 40, 0, 1.5))]
    assert "tackles" in rozliczanie.rynki_kwarantanna(
        _log(_seria("tackles", 40, 40, 1.5) + zapasc)
    )


def test_histereza_trzyma_stan_w_szarej_strefie():
    """ROI między progami (−2,5%) nie rusza rynku w żadną stronę — decyduje
    to, czy rynek stał w kwarantannie w poprzednim cyklu."""
    # 20 typów po kursie 1,5, weszło 13 -> ROI = (13*0,5 − 7)/20 = −2,5%
    wolny = _seria("shots", 20, 13, 1.5)
    assert rozliczanie.rynki_kwarantanna(_log(wolny)) == {}
    wstrzymany = _seria("shots", 20, 13, 1.5,
                        poza_publikacja="kwarantanna_rynku")
    assert "shots" in rozliczanie.rynki_kwarantanna(_log(wstrzymany))


def test_wyjscie_dopiero_po_odbudowie_roi():
    # ten sam rynek w kwarantannie: ROI +5% (14/20 po 1,5) przekracza próg
    # wyjścia (−2%), więc wraca do publikacji mimo flagi z poprzedniego cyklu
    recs = _seria("shots", 20, 14, 1.5, poza_publikacja="kwarantanna_rynku")
    assert rozliczanie.rynki_kwarantanna(_log(recs)) == {}


def test_typy_poza_publikacja_ucza_kwarantanne():
    # typy z flagą poza_publikacja LICZĄ SIĘ do oceny rynku (inaczej rynek
    # w kwarantannie nie miałby czym udowodnić powrotu)
    recs = _seria("shots", 20, 20, 1.5, poza_publikacja="kwarantanna_rynku")
    assert rozliczanie.rynki_kwarantanna(_log(recs)) == {}  # zdrowe wyniki
    recs_zle = _seria("shots", 20, 0, 1.5, poza_publikacja="limit_meczu")
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


# --- KWARANTANNA KATEGORII: brama po POWODZIE wejścia typu, nie po rynku ---


def test_kategoria_ktora_traci_wypada_z_publikacji():
    """Pomiar 2026-07-27: „ambitniejsza linia" trafiała 47% przy progu
    opłacalności 63%. Bez tej bramy wystarczyło przekleić stratny typ na
    inny rynek, żeby przeszedł."""
    # 20 typów po kursie 1,7 na dwóch RÓŻNYCH rynkach, weszło 7
    recs = (_seria("shots", 10, 3, 1.7, wyzsza_linia=True)
            + _seria("sot", 10, 4, 1.7, wyzsza_linia=True))
    kw = rozliczanie.kategorie_kwarantanna(_log(recs))
    assert "wyzsza_linia" in kw
    assert kw["wyzsza_linia"]["n"] == 20
    assert kw["wyzsza_linia"]["nazwa"] == "Ambitniejsza linia"


def test_kategoria_dochodowa_zostaje():
    recs = _seria("shots", 20, 15, 1.6, matchup=True)
    assert rozliczanie.kategorie_kwarantanna(_log(recs)) == {}


def test_kategoria_na_krotkiej_probie_nie_jest_oceniana():
    recs = _seria("shots", rozliczanie.KATEGORIA_MIN_N - 1, 0, 1.7,
                  miekka_linia=True)
    assert rozliczanie.kategorie_kwarantanna(_log(recs)) == {}


def test_typy_bez_flag_nie_wpadaja_do_zadnej_kategorii():
    """„Zwykłe" typy to te, które zarabiają — nie wolno ich objąć bramą."""
    recs = _seria("shots", 30, 5, 1.5)
    assert rozliczanie.kategorie_kwarantanna(_log(recs)) == {}
