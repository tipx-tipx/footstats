"""Brama publikacji: kwarantanna rynków + flaga poza_publikacja w logu."""

import pytest

from footstats.jobs import rozliczanie
from footstats.model import betting


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


def _dni(recs, od_dnia: int):
    """Rozłóż rozliczenia na kolejne DNI meczowe.

    Od 2026-08-03 okno kwarantanny musi objąć kilka dni, a nie tylko N rekordów
    (patrz `okno_kroczace`) — dane testowe upchnięte w jednej dobie mierzyłyby
    już co innego niż reguła w produkcji.
    """
    DOBA = 86400
    return [{**r, "kickoff_ts": (od_dnia + i % 8) * DOBA + i}
            for i, r in enumerate(recs)]


def test_okno_kroczace_pozwala_wrocic():
    # stare 40 przegranych, świeże 40 wygranych — okno widzi tylko świeże
    stare = _dni(_seria("tackles", 40, 0, 1.5), 100)
    swieze = _dni(_seria("tackles", 40, 40, 1.5), 200)
    assert rozliczanie.rynki_kwarantanna(_log(stare + swieze)) == {}
    # i w drugą stronę: świeża zapaść wchodzi do kwarantanny mimo dobrej historii
    assert "tackles" in rozliczanie.rynki_kwarantanna(_log(
        _dni(_seria("tackles", 40, 40, 1.5), 100)
        + _dni(_seria("tackles", 40, 0, 1.5), 200)
    ))


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


# --- KOREKTA STRUMIENIA (2026-07-27) ---------------------------------------

def _typ(i, p, wynik, strumien="pewniaki", kal=None):
    rec = {
        "mecz_id": i, "mecz": "A – B", "kickoff_ts": 1_700_000_000 + i,
        "podmiot_id": i, "podmiot": f"G{i}",
        "rynek_kod": "team_goals" if strumien == "druzyny" else "shots",
        "rynek": "R", "linia": 1.5, "strona": "powyzej",
        "kurs": 1.9, "p_model": p, "wynik": wynik, "zagral": True,
    }
    if kal is not None:
        rec["kal_strumien"] = kal
    return rec


def test_korekta_strumienia_sciaga_przeszacowanie():
    """Deklaracja 70%, trafienia 50% -> korekta ujemna, ale STŁUMIONA.

    Pierwszy cykl dokłada połowę potrzebnej korekty (patrz
    KOREKTA_STRUMIENIA_TLUMIENIE) — pełna wartość od razu wyzerowałaby listę.
    """
    log = {}
    for i in range(60):
        log[str(i)] = _typ(i, 0.70, "wygrany" if i % 2 == 0 else "przegrany")
    k = rozliczanie.korekta_strumienia(log)
    # od 2026-07-31 korekta bywa binowana po `p_over`; `delta_globalna`
    # czyta jej część wspólną, czyli dokładnie to, czym była wcześniej
    assert -0.6 < betting.delta_globalna(k["pewniaki"]) < -0.25
    # strumień drużynowy bez próby nie dostaje nic
    assert "druzyny" not in k


def test_korekta_ma_osobne_delty_per_przedzial_szansy():
    """Błąd modelu ZMIENIA ZNAK, więc jedna liczba na strumień go nie opisze.

    Pomiar 2026-07-31: na „powyżej" model przeszacowuje, a na „poniżej" przy
    wysokich kursach niedoszacowuje o 16,7 pp. Uśrednienie psuje oba naraz.

    Tu: typy o p_over ~0,80 mocno przeszacowane (weszło 40%), a typy
    o p_over ~0,45 trafiające zgodnie z deklaracją. Delta dla wysokiego
    przedziału musi być WYRAŹNIE ostrzejsza niż dla niskiego.
    """
    log = {}
    for i in range(40):                        # p_over 0,80 -> weszło 40%
        log[f"a{i}"] = _typ(i, 0.80, "wygrany" if i % 10 < 4 else "przegrany")
    for i in range(40):                        # p_over 0,45 -> weszło 45%
        log[f"b{i}"] = _typ(100 + i, 0.45,
                            "wygrany" if i % 20 < 9 else "przegrany")
    k = rozliczanie.korekta_strumienia(log)["pewniaki"]
    assert isinstance(k, dict), "przy takiej próbie muszą powstać przedziały"
    d_niski = betting.delta_dla_p(k, 0.45)
    d_wysoki = betting.delta_dla_p(k, 0.80)
    assert d_wysoki < d_niski - 0.15, (
        f"przedziały się nie rozjechały: {d_niski:+.3f} vs {d_wysoki:+.3f}"
    )


def test_korekta_binowana_po_p_over_a_nie_po_p_typu():
    """Typ „poniżej" ma `p` będące LUSTREM `p_over`, a przedziały są
    wyszukiwane po `p_over` (engine._select_bias). Mierzone muszą być tak samo,
    inaczej rekord ląduje w binie po przeciwnej stronie skali.

    Błąd realny do 2026-07-31 — niewidoczny na propsach (100% „powyżej"),
    wychodził na rynkach drużynowych, gdzie 76% typów to „poniżej".
    """
    r = {"p_model": 0.30, "strona": "ponizej"}
    assert abs(rozliczanie._p_over_rekordu(r) - 0.70) < 1e-9
    r2 = {"p_model": 0.30, "strona": "powyzej"}
    assert abs(rozliczanie._p_over_rekordu(r2) - 0.30) < 1e-9


def test_korekta_strumienia_cisza_gdy_model_trafia():
    log = {}
    for i in range(60):
        log[str(i)] = _typ(i, 0.60, "wygrany" if i % 10 < 6 else "przegrany")
    assert rozliczanie.korekta_strumienia(log) == {}


def test_korekta_strumienia_nie_oscyluje():
    """Regulator liczy na SUROWYM p — inaczej po jednym cyklu wyzerowałby się.

    Typy z drugiego cyklu mają p JUŻ ściągnięte korektą (0,70 -> 0,52) i
    stempel `kal_strumien`. Gdyby pomiar szedł po p_model, luka wyglądałaby
    na zamkniętą i korekta wróciłaby do zera — a przeszacowanie wróciłoby
    razem z nią.
    """
    log = {}
    for i in range(60):
        log[str(i)] = _typ(i, 0.52, "wygrany" if i % 2 == 0 else "przegrany",
                           kal=-0.80)
    k = rozliczanie.korekta_strumienia(log)
    assert betting.delta_globalna(k["pewniaki"]) < -0.5, (
        "korekta zniknęła — regulator oscyluje"
    )


def test_korekta_strumienia_wymaga_proby():
    log = {str(i): _typ(i, 0.70, "przegrany") for i in range(20)}
    assert rozliczanie.korekta_strumienia(log) == {}


# --- STEMPEL KOREKTY MUSI BYĆ LICZBĄ (regresja 2026-08-01) -----------------
#
# Co się stało na produkcji: od wprowadzenia przedziałów (31.07) korekta bywa
# słownikiem i CAŁY ten słownik trafiał do księgi jako `kal_strumien`. Każde
# `float(stempel)` wywalało TypeError, a że `korekta_strumienia` i
# `szansa_pokazywana` stoją w cyklu w try/except, DRUGA WARSTWA UCZENIA CICHO
# SIĘ WYŁĄCZYŁA na półtorej doby. Model szedł na bramę zgody z rynkiem
# nieskorygowany (mediana odrzuceń: +17,5 pp nad kursem), a korekta pokazywana
# nie miała czego odjąć, więc działała z podwójną siłą.

BINOWANA = {"logit": True, "global": -0.30,
            "bins": [[0.0, 0.55, -0.10], [0.55, 1.01, -0.50]]}


def test_stempel_korekty_zapisuje_liczbe_nie_caly_rozklad():
    rozliczanie.ustaw_korekte_strumienia({"pewniaki": BINOWANA})
    try:
        log = {}
        rozliczanie._dopisz_nowe(log, [{
            "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 1_700_000_000,
            "podmiot_id": 1, "podmiot": "G", "rynek_kod": "shots",
            "rynek": "R", "linia": 1.5, "strona": "powyzej",
            "kurs": 1.9, "p_model": 0.80,
        }])
        stempel = next(iter(log.values()))["kal_strumien"]
        assert isinstance(stempel, float), f"stempel to {type(stempel).__name__}"
        assert stempel == -0.50, "bin czytany po p_over typu"
    finally:
        rozliczanie.ustaw_korekte_strumienia({})


def test_uczenie_przezywa_stary_stempel_slownikowy():
    """87 rekordów w produkcyjnej księdze ma stary kształt — na zawsze."""
    log = {}
    for i in range(60):
        log[str(i)] = _typ(i, 0.52, "wygrany" if i % 2 == 0 else "przegrany")
        log[str(i)]["kal_strumien"] = BINOWANA      # stary, zły kształt
    k = rozliczanie.korekta_strumienia(log)         # nie może rzucić
    assert betting.delta_globalna(k["pewniaki"]) < 0.0
    assert isinstance(rozliczanie.szansa_pokazywana(log), dict)


# --- CZY BIJEMY CENĘ BUKMACHERA (2026-08-01) -------------------------------

def _typ_z_kursem(i, p, kurs, wynik, rynek="team_goals", strona="ponizej"):
    return {
        "mecz_id": i, "mecz": "A – B", "kickoff_ts": 1_700_000_000 + i,
        "podmiot_id": i, "podmiot": f"G{i}", "rynek_kod": rynek, "rynek": "R",
        "linia": 1.5, "strona": strona, "kurs": kurs, "p_model": p,
        "wynik": wynik,
    }


def test_przewaga_dodatnia_gdy_model_bije_cene():
    """Kurs 2,0 mówi ~53%, my mówimy 80% i trafiamy 80% — bijemy cenę."""
    log = {}
    for i in range(40):
        log[str(i)] = _typ_z_kursem(
            i, 0.80, 2.0, "wygrany" if i % 10 < 8 else "przegrany")
    w = rozliczanie.przewaga_rynkow(log)["team_goals|ponizej"]
    assert w["n"] == 40
    assert w["przewaga"] > 0, "model trafia zgodnie z deklaracją, cena nie"
    assert w["brier_model"] < w["brier_kurs"]


def test_przewaga_ujemna_gdy_model_gada():
    """Deklarujemy 85%, trafiamy 40%, a kurs 2,0 był bliżej prawdy."""
    log = {}
    for i in range(40):
        log[str(i)] = _typ_z_kursem(
            i, 0.85, 2.0, "wygrany" if i % 10 < 4 else "przegrany")
    w = rozliczanie.przewaga_rynkow(log)["team_goals|ponizej"]
    assert w["przewaga"] < 0


def test_przewaga_milczy_na_malej_probie():
    """Brak danych to nie wina rynku — po prostu go nie oceniamy."""
    log = {str(i): _typ_z_kursem(i, 0.80, 2.0, "wygrany") for i in range(10)}
    assert rozliczanie.przewaga_rynkow(log) == {}


def test_przewaga_tlumiona_wielkoscia_proby():
    """Ten sam wynik na większej próbie znaczy więcej — inaczej rynek z 26
    rozliczeniami przeskakiwałby rynek ze 130 po jednym dobrym tygodniu."""
    def zbuduj(ile):
        return {str(i): _typ_z_kursem(
            i, 0.80, 2.0, "wygrany" if i % 10 < 8 else "przegrany")
            for i in range(ile)}
    mala = rozliczanie.przewaga_rynkow(zbuduj(30))["team_goals|ponizej"]
    duza = rozliczanie.przewaga_rynkow(zbuduj(200))["team_goals|ponizej"]
    assert duza["przewaga"] > mala["przewaga"]


def test_przewaga_rozdziela_strony_tego_samego_rynku():
    """„Powyżej" i „poniżej" to osobne byty — pomiar 01.08 pokazał, że jeden
    potrafi bić cenę, gdy drugi ją przegrywa."""
    log = {}
    for i in range(30):
        log[f"p{i}"] = _typ_z_kursem(
            i, 0.80, 2.0, "wygrany" if i % 10 < 8 else "przegrany")
        log[f"n{i}"] = _typ_z_kursem(
            100 + i, 0.85, 2.0, "wygrany" if i % 10 < 4 else "przegrany",
            strona="powyzej")
    w = rozliczanie.przewaga_rynkow(log)
    assert w["team_goals|ponizej"]["przewaga"] > 0
    assert w["team_goals|powyzej"]["przewaga"] < 0


def test_przewaga_pasm_znajduje_przedzial_z_przewaga():
    """Zgłoszenie usera: „model ma znajdować pewne typy przy różnych kursach".

    Odpowiedź jest pomiarowa: pasmo wchodzi, gdy w NIM bijemy cenę. Tu tanie
    kursy są wycenione idealnie przez bukmachera, a przy 3,0+ trafiamy dużo
    częściej, niż cena sugeruje — dokładnie jak na produkcji.
    """
    log = {}
    for i in range(40):          # tanio: cena mowi ~83%, wchodzi ~83%
        log[f"t{i}"] = _typ_z_kursem(
            i, 0.95, 1.2, "wygrany" if i % 6 < 5 else "przegrany")
    for i in range(40):          # drogo: cena mowi ~28%, wchodzi 50%
        log[f"d{i}"] = _typ_z_kursem(
            100 + i, 0.50, 3.2, "wygrany" if i % 2 == 0 else "przegrany")
    p = rozliczanie.przewaga_pasm(log)
    assert p["3.0-6.01"]["przewaga"] > 0, "przy 3,0+ bijemy cene"
    assert p["1.19-1.35"]["przewaga"] < p["3.0-6.01"]["przewaga"]


def test_przewaga_pasma_dla_wybiera_wlasciwy_przedzial():
    pasma = {"1.9-2.3": {"od": 1.9, "do": 2.3, "przewaga": 0.05},
             "3.0-6.01": {"od": 3.0, "do": 6.01, "przewaga": 0.02}}
    assert rozliczanie.przewaga_pasma_dla(2.0, pasma) == 0.05
    assert rozliczanie.przewaga_pasma_dla(3.5, pasma) == 0.02
    assert rozliczanie.przewaga_pasma_dla(1.5, pasma) == 0.0   # brak pomiaru
    assert rozliczanie.przewaga_pasma_dla(None, pasma) == 0.0
    assert rozliczanie.przewaga_pasma_dla(2.0, None) == 0.0


# --- HISTORIA POMIARU (2026-08-01): bez niej etap 3 jest zgadywanka ---------

def _pomiar(przewaga, n=40):
    return {"team_goals|ponizej": {"n": n, "przewaga": przewaga,
                                   "brier_model": 0.20, "brier_kurs": 0.22}}


def test_stempel_jest_dzienny_a_nie_na_cykl(monkeypatch):
    """Cykl chodzi kilkanaście razy dziennie — historia ma rosnąć raz na dobę."""
    zapisane = {}
    monkeypatch.setattr(rozliczanie, "get_key_ok_przewagi",
                        lambda: (zapisane.get("h"), True))
    monkeypatch.setattr(rozliczanie.supa, "put_key",
                        lambda k, v: zapisane.__setitem__("h", v) or True)
    rozliczanie.zapisz_przewage(_pomiar(0.01), {}, dzien="2026-08-01")
    rozliczanie.zapisz_przewage(_pomiar(0.02), {}, dzien="2026-08-01")
    assert list(zapisane["h"]) == ["2026-08-01"]
    # ostatni pomiar dnia wygrywa
    assert zapisane["h"]["2026-08-01"]["rynki"]["team_goals|ponizej"]["przewaga"] == 0.02
    rozliczanie.zapisz_przewage(_pomiar(0.03), {}, dzien="2026-08-02")
    assert sorted(zapisane["h"]) == ["2026-08-01", "2026-08-02"]


def test_nieudany_odczyt_nie_kasuje_historii(monkeypatch):
    """Jeden timeout nie może zastąpić miesiąca pomiarów jednym wpisem."""
    monkeypatch.setattr(rozliczanie, "get_key_ok_przewagi", lambda: (None, False))
    monkeypatch.setattr(rozliczanie.supa, "put_key",
                        lambda k, v: pytest.fail("zapis mimo padnietego odczytu"))
    assert rozliczanie.zapisz_przewage(_pomiar(0.01), {}) is False


def test_trend_pokazuje_kierunek():
    hist = {
        "2026-07-20": {"rynki": {"team_goals|ponizej":
                                 {"n": 30, "przewaga": -0.010}}, "pasma": {}},
        "2026-08-01": {"rynki": {"team_goals|ponizej":
                                 {"n": 90, "przewaga": +0.015}}, "pasma": {}},
    }
    t = rozliczanie.trend_przewagi(7, hist)["team_goals|ponizej"]
    assert t["bylo"] == -0.010 and t["teraz"] == 0.015
    assert t["zmiana"] == 0.025          # model sie nauczyl
    assert t["n_bylo"] == 30 and t["n_teraz"] == 90


def test_trend_milczy_gdy_jest_jeden_pomiar():
    hist = {"2026-08-01": {"rynki": _pomiar(0.01), "pasma": {}}}
    assert rozliczanie.trend_przewagi(7, hist) == {}


def test_historia_przycinana_do_okna():
    dni = {f"2026-{m:02d}-{d:02d}": {"rynki": {}, "pasma": {}}
           for m in (1, 2, 3, 4, 5, 6, 7) for d in range(1, 29)}
    assert len(dni) > rozliczanie.PRZEWAGA_HISTORIA_DNI
    zapisane = {}
    import footstats.jobs.rozliczanie as R
    stary_get, stary_put = R.get_key_ok_przewagi, R.supa.put_key
    R.get_key_ok_przewagi = lambda: (dni, True)
    R.supa.put_key = lambda k, v: zapisane.__setitem__("h", v) or True
    try:
        R.zapisz_przewage(_pomiar(0.01), {}, dzien="2026-08-01")
    finally:
        R.get_key_ok_przewagi, R.supa.put_key = stary_get, stary_put
    assert len(zapisane["h"]) == rozliczanie.PRZEWAGA_HISTORIA_DNI
    assert "2026-08-01" in zapisane["h"]     # najnowszy zawsze zostaje


# --- KIEDY RYNEK ZNIKA ZE STRONY (2026-08-01) ------------------------------
#
# User: „jak coś tragicznie nie wchodzi to ma być ukryte do czasu dopracowania,
# ale jak coś raz na jakiś czas nie wejdzie to ma się pokazywać".

# `roznica` (o ile Briera jesteśmy gorsi od kursu) to od 2026-08-03 DRUGI
# warunek ukrycia — patrz rozliczanie.UKRYCIE_MIN_ROZNICA i
# tests/test_ukrywanie_rynkow.py. Tutejsze przypadki badają wymiar ISTOTNOŚCI,
# więc domyślnie opisują rynek naprawdę tragiczny (−0,09), żeby to `se`
# rozstrzygało o wyniku.
def _dzien(se, n=120, klucz="shots|powyzej", roznica=-0.09):
    return {"rynki": {klucz: {"n": n, "se": se, "przewaga": -0.03,
                              "roznica": roznica,
                              "brier_model": 0.31, "brier_kurs": 0.22}},
            "pasma": {}, "ukryte": []}


def _teraz(se, n=120, klucz="shots|powyzej", roznica=-0.09):
    return {klucz: {"rynek_kod": "shots", "strona": "powyzej", "n": n,
                    "se": se, "przewaga": -0.03, "roznica": roznica,
                    "brier_model": 0.31, "brier_kurs": 0.22}}


HIST_ZLA = {"2026-07-30": _dzien(-3.0), "2026-07-31": _dzien(-2.9),
            "2026-08-01": _dzien(-3.2)}


def test_rynek_tragiczny_znika():
    assert rozliczanie.rynki_do_ukrycia(_teraz(-3.2), HIST_ZLA) == {"shots|powyzej"}


def test_zla_seria_to_za_malo():
    """„Raz na jakiś czas nie wejdzie" ma zostać na stronie."""
    assert rozliczanie.rynki_do_ukrycia(_teraz(-2.0), HIST_ZLA) == set()


def test_jeden_zly_dzien_nie_wystarcza():
    hist = {"2026-07-30": _dzien(-0.5), "2026-07-31": _dzien(-0.4),
            "2026-08-01": _dzien(-3.2)}
    assert rozliczanie.rynki_do_ukrycia(_teraz(-3.2), hist) == set()


def test_mala_proba_nie_moze_ukryc_rynku():
    """Przy 30 rozliczeniach sam błąd standardowy jest niestabilny."""
    assert rozliczanie.rynki_do_ukrycia(_teraz(-3.2, n=30), HIST_ZLA) == set()


def test_bez_historii_nie_ukrywamy_w_ciemno():
    assert rozliczanie.rynki_do_ukrycia(_teraz(-3.2), {}) == set()


def test_histereza_wyjscie_trudniejsze_niz_powrot():
    ukryty = {"shots|powyzej"}
    # lekka poprawa nie wystarcza, zeby wrocic
    assert rozliczanie.rynki_do_ukrycia(
        _teraz(-1.5), HIST_ZLA, ukryty) == {"shots|powyzej"}
    # ...ale realna juz tak, i to BEZ udowadniania przewagi
    assert rozliczanie.rynki_do_ukrycia(_teraz(-0.5), HIST_ZLA, ukryty) == set()


def test_przewaga_rynkow_liczy_istotnosc():
    """Ta sama różnica na małej i dużej próbie znaczy co innego."""
    def log(ile):
        return {str(i): _typ_z_kursem(
            i, 0.85, 2.0, "wygrany" if i % 10 < 4 else "przegrany")
            for i in range(ile)}
    mala = rozliczanie.przewaga_rynkow(log(30))["team_goals|ponizej"]
    duza = rozliczanie.przewaga_rynkow(log(300))["team_goals|ponizej"]
    assert duza["blad_std"] < mala["blad_std"]
    assert duza["se"] < mala["se"]          # bardziej ujemne = pewniejsze


def test_delta_zapisana_toleruje_smieci():
    assert rozliczanie._delta_zapisana({}) == 0.0
    assert rozliczanie._delta_zapisana({"kal_strumien": -0.4}) == -0.4
    assert rozliczanie._delta_zapisana({"kal_strumien": "nonsens"}) == 0.0
    assert rozliczanie._delta_zapisana(
        {"kal_strumien": BINOWANA, "p_model": 0.80, "strona": "powyzej"}
    ) == -0.50

# --- WŁASNE UCZENIE DRABINEK (2026-07-29) ----------------------------------


def _drabinka(i, p, wynik, odrzucony=False, kurs=2.2):
    """Rekord księgi ze strumienia drabinek (p z pokrycia, nie z silnika)."""
    rec = {
        "mecz_id": i, "mecz": "A – B", "kickoff_ts": 1_700_000_000 + i,
        "podmiot_id": i, "podmiot": f"G{i}",
        "rynek_kod": "shots", "rynek": "Strzały", "linia": 1.5,
        "strona": "powyzej", "kurs": kurs, "p_model": p, "wynik": wynik,
        "zrodlo": rozliczanie.ZRODLO_DRABINKA,
    }
    if odrzucony:
        rec["odrzucony"] = True
        rec["odrzucenie_powod"] = rozliczanie.POWOD_POMIARU_POKRYCIA
    return rec


def test_drabinki_dostaja_wlasna_korekte():
    """Do 2026-07-29 strumień z ROI −68% nie miał ŻADNEGO sprzężenia
    zwrotnego: kalibracja i kwarantanna pomijają wszystko, co ma `zrodlo`."""
    log = {
        str(i): _drabinka(i, 0.55, "wygrany" if i % 5 == 0 else "przegrany")
        for i in range(rozliczanie.KOREKTA_DRABINEK_MIN_N + 5)
    }
    k = rozliczanie.korekta_strumienia(log)
    assert k["drabinki"] < -0.1
    # ...ale nie głębiej niż pozwala ich węższy cap (przy n=30 zerowanie
    # zakładki byłoby wnioskiem mocniejszym niż dane)
    assert k["drabinki"] >= rozliczanie.KOREKTA_DRABINEK_CAP[0]
    # i nie wolno im zatruć strumienia typów modelu
    assert "pewniaki" not in k


def test_drabinki_na_krotkiej_probie_bez_korekty():
    log = {
        str(i): _drabinka(i, 0.55, "przegrany")
        for i in range(rozliczanie.KOREKTA_DRABINEK_MIN_N - 1)
    }
    assert rozliczanie.korekta_strumienia(log) == {}


def test_typy_pomiarowe_drabinek_nie_ucza_korekty():
    """Szczebel spod progu nigdy nie był opublikowany — nie ma prawa
    przesuwać szans kart, które publikujemy."""
    log = {
        str(i): _drabinka(i, 0.55, "przegrany", odrzucony=True)
        for i in range(rozliczanie.KOREKTA_DRABINEK_MIN_N + 5)
    }
    assert rozliczanie.korekta_strumienia(log) == {}


def test_pomiar_progu_drabinek_zestawia_obie_grupy():
    log = {}
    for i in range(10):
        log[f"pub{i}"] = _drabinka(i, 0.55, "wygrany" if i < 6 else "przegrany")
    for i in range(8):
        log[f"pom{i}"] = _drabinka(
            100 + i, 0.45, "wygrany" if i < 2 else "przegrany", odrzucony=True
        )
    p = rozliczanie.pomiar_progu_drabinek(log)
    assert p["opublikowane"]["n"] == 10 and p["opublikowane"]["hit"] == 0.6
    assert p["pod_progiem"]["n"] == 8 and p["pod_progiem"]["hit"] == 0.25
    # ROI liczone z kursu, nie z samych trafień
    assert p["opublikowane"]["roi"] > p["pod_progiem"]["roi"]


# --- SZANSA POKAZYWANA NA STRONIE (2026-07-29) -----------------------------


def test_szansa_pokazywana_odejmuje_korekte_sprzed_bramy():
    """Najważniejszy warunek: nie liczyć jednej rzeczy dwa razy.

    Typy w oknie deklarowały 70% i trafiały 50% (rozjazd ~-0,8 logita).
    Skoro korekta strumienia ściąga już -0,5 PRZED bramą, do pokazania
    zostaje reszta, a nie całość.
    """
    log = {
        str(i): _typ(i, 0.70, "wygrany" if i % 2 == 0 else "przegrany")
        for i in range(60)
    }
    calosc = rozliczanie.szansa_pokazywana(log, {})["pewniaki"]
    reszta = rozliczanie.szansa_pokazywana(log, {"pewniaki": -0.5})["pewniaki"]
    assert calosc < -0.5
    assert reszta == pytest.approx(calosc + 0.5, abs=1e-3)


def test_szansa_pokazywana_mierzy_na_surowym_p():
    """Typy wystawione z korektą mają p JUŻ ściągnięte i stempel — pomiar
    idzie po surowym, inaczej korekta zjadałaby własny ogon."""
    log = {
        str(i): _typ(i, 0.52, "wygrany" if i % 2 == 0 else "przegrany",
                     kal=-0.80)
        for i in range(60)
    }
    d = rozliczanie.szansa_pokazywana(log, {"pewniaki": -0.80})["pewniaki"]
    # surowe p to ~0,70, trafienia 50% -> rozjazd ~-0,8; korekta przed bramą
    # zdejmuje dokładnie tyle, więc do pokazania zostaje prawie nic
    assert abs(d) < 0.15


def test_szansa_pokazywana_cisza_gdy_deklaracja_sie_broni():
    log = {
        str(i): _typ(i, 0.60, "wygrany" if i % 10 < 6 else "przegrany")
        for i in range(60)
    }
    assert rozliczanie.szansa_pokazywana(log, {}) == {}


def test_szansa_pokazywana_pomija_typy_spoza_publikacji():
    """Mierzymy to, co user WIDZIAŁ — typy z kwarantanny nie były na stronie."""
    log = {}
    for i in range(50):
        log[f"ok{i}"] = _typ(i, 0.60, "wygrany" if i % 10 < 6 else "przegrany")
    for i in range(50, 110):
        log[f"x{i}"] = {**_typ(i, 0.60, "przegrany"),
                        "poza_publikacja": "kwarantanna_rynku"}
    assert rozliczanie.szansa_pokazywana(log, {}) == {}


def test_urealnij_p_zachowuje_kolejnosc_i_zakres():
    d = -0.33
    assert 0 < rozliczanie.urealnij_p(0.01, d) < rozliczanie.urealnij_p(0.5, d)
    assert rozliczanie.urealnij_p(0.5, d) < rozliczanie.urealnij_p(0.99, d) < 1
    assert rozliczanie.urealnij_p(0.7, 0.0) == 0.7


def test_flaga_pewniak_jest_objeta_kwarantanna_kategorii():
    """Dziura załatana 2026-07-29: `pewniak` to ponad połowa typów
    zawodniczych (136 z 259 rozliczonych, ROI −22% na opublikowanych),
    a stała POZA bramą, która pilnuje dokładnie takich ścieżek — wpuszcza
    typ na listę bez wymogu wartości, na samej wysokiej szansie."""
    assert "pewniak" in rozliczanie.KATEGORIE_KWARANTANNY
    recs = _seria("shots", 30, 5, 1.7, pewniak=True)
    kw = rozliczanie.kategorie_kwarantanna(_log(recs))
    assert "pewniak" in kw
    assert kw["pewniak"]["nazwa"] == "Najwyższa szansa w meczu"


def test_pewniak_ktory_zarabia_nie_jest_wstrzymywany():
    """Brama patrzy na ROI z okna, nie na samą flagę — dochodowa kategoria
    zostaje (na 29.07 `pewniak` miał w oknie +10% i przechodził)."""
    recs = _seria("shots", 30, 25, 1.7, pewniak=True)
    assert "pewniak" not in rozliczanie.kategorie_kwarantanna(_log(recs))


# --- KWARANTANNA STRONY LINII (2026-07-30) ---------------------------------


def test_strona_linii_ma_wlasna_kwarantanne():
    """Pomiar 30.07 na 108 typach drużynowych: „powyżej" ROI −15%,
    „poniżej" +8% na tych samych rynkach. Kwarantanna rynkowa widziała
    tylko średnią, więc rynek wypadał cały albo zostawał cały."""
    recs = (_seria("team_goals", 30, 5, 1.7, strona="powyzej")   # tonie
            + _seria("team_goals", 30, 25, 1.5, strona="ponizej"))
    kw = rozliczanie.strony_kwarantanna(_log(recs))
    assert "team_goals:powyzej" in kw
    assert "team_goals:ponizej" not in kw
    assert kw["team_goals:powyzej"]["strona"] == "powyzej"


def test_strona_na_krotkiej_probie_nie_jest_oceniana():
    recs = _seria("shots", rozliczanie.STRONA_MIN_N - 1, 0, 1.7,
                  strona="powyzej")
    assert rozliczanie.strony_kwarantanna(_log(recs)) == {}


def test_dochodowa_strona_zostaje():
    recs = _seria("team_corners", 30, 24, 1.5, strona="ponizej")
    assert rozliczanie.strony_kwarantanna(_log(recs)) == {}


def test_cap_korekty_siega_zmierzonej_potrzeby():
    """Pomiar 2026-07-30: pełna potrzebna korekta pewniaków to −0,955, więc
    stary cap −0,80 BYŁ WIĄŻĄCY — bezpiecznik nie pozwalał korekcie dojść
    tam, gdzie wskazują dane. Rolę „nie wyzeruj listy" przejęły osobna
    szansa pokazywana i brama „ujemna po korekcie"."""
    lo, _hi = rozliczanie.KOREKTA_STRUMIENIA_CAP
    assert lo <= -0.95


def test_korekta_dochodzi_do_zmierzonej_wartosci_przez_cykle():
    """Tłumienie ma spowalniać, nie zatrzymywać: po kilku cyklach korekta
    ma sięgnąć poziomu, który mówi pomiar."""
    log = {}
    for i in range(60):
        log[str(i)] = _typ(i, 0.70, "wygrany" if i % 10 < 4 else "przegrany")
    d1 = betting.delta_globalna(rozliczanie.korekta_strumienia(log)["pewniaki"])
    # drugi cykl: te same wyniki, ale typy wystawione JUŻ z korektą d1
    log2 = {}
    for i in range(60):
        p2 = rozliczanie.urealnij_p(0.70, d1)
        log2[str(i)] = _typ(i, round(p2, 4),
                            "wygrany" if i % 10 < 4 else "przegrany", kal=d1)
    d2 = betting.delta_globalna(rozliczanie.korekta_strumienia(log2)["pewniaki"])
    assert d2 < d1, "korekta musi pogłębiać się między cyklami, nie cofać"


def test_strona_z_wlasna_proba_ma_wlasny_werdykt():
    """Strona, którą da się ocenić osobno, nie podlega bramie rynkowej.

    Pomiar 2026-08-04: `team_corners` stał w kwarantannie CAŁY (ROI −16,5%
    z obu stron razem), choć jego strona „powyżej" zarabiała +9,4% na 34
    rozliczeniach i biła cenę bukmachera. Licznik rynku to średnia dwóch
    kolumn o przeciwnym znaku — nie ma prawa orzekać o stronie, która ma
    własną próbę.
    """
    recs = (_seria("team_corners", 30, 8, 1.5, strona="ponizej")   # tonie
            + _seria("team_corners", 20, 16, 1.6, strona="powyzej"))  # zarabia
    log = _log(recs)
    # rynek jako całość wpada do kwarantanny...
    assert "team_corners" in rozliczanie.rynki_kwarantanna(log)
    # ...ale obie strony mają dość rozliczeń, żeby odpowiadać za siebie
    ocenione = rozliczanie.strony_ocenione(log)
    assert "team_corners:powyzej" in ocenione
    assert "team_corners:ponizej" in ocenione
    # i tylko tracąca jest wstrzymana
    kw = rozliczanie.strony_kwarantanna(log)
    assert "team_corners:ponizej" in kw
    assert "team_corners:powyzej" not in kw


def test_strona_bez_wlasnej_proby_dalej_podlega_rynkowi():
    """Brak danych nie jest ułaskawieniem — inaczej nowa strona wchodziłaby
    na rynek, który udowodnił, że traci, i to bez żadnego zabezpieczenia."""
    recs = (_seria("team_corners", 30, 8, 1.5, strona="ponizej")
            + _seria("team_corners", rozliczanie.STRONA_MIN_N - 1, 9, 1.6,
                     strona="powyzej"))
    ocenione = rozliczanie.strony_ocenione(_log(recs))
    assert "team_corners:powyzej" not in ocenione


def test_brama_kwarantanny_jedna_regula_dla_wszystkich_sciezek():
    """Sumy meczowe i „kto wiecej" dopisuja sie do listy Z POMINIECIEM glownej
    petli publikacji — wiec regula musi byc JEDNA funkcja, ktora kazda sciezka
    wola, a nie warunkiem przepisanym w kilku miejscach.

    Zmierzone 2026-08-04: dopoki okno zgody stalo na +12 pp, dziura byla
    niewidoczna (te typy odpadaly wczesniej). Po rozszerzeniu okna na +16 pp
    weszly na liste trzy SWIEZE „rozne w meczu ponizej" z rynku w kwarantannie.
    """
    brama = rozliczanie.brama_kwarantanny(
        rynki={"team_corners": {}},
        strony={"match_corners:ponizej": {}},
        ocenione={"team_corners:powyzej", "team_corners:ponizej"},
    )
    # rynek w kwarantannie, ale strona ma wlasny werdykt -> przechodzi
    assert brama({"rynek_kod": "team_corners", "strona": "powyzej"}) is None
    # strona wstrzymana wlasnym wynikiem -> zdjeta, i to z wlasnym powodem
    assert brama({"rynek_kod": "match_corners", "strona": "ponizej"}) == (
        "kwarantanna_strony")
    # strona bez wlasnej proby na rynku w kwarantannie -> zdejmuje ja rynek
    assert brama({"rynek_kod": "team_corners", "strona": "gospodarz"}) == (
        "kwarantanna_rynku")
    # rynek zdrowy -> nic nie stoi na przeszkodzie
    assert brama({"rynek_kod": "team_goals", "strona": "ponizej"}) is None


def test_obie_bramy_licza_z_tej_samej_proby():
    """`strony_ocenione` i `strony_kwarantanna` muszą widzieć ten sam zbiór.

    Gdyby liczyły z osobnych prób, strona mogłaby jednocześnie „mieć własny
    werdykt" (więc rynek jej nie dotyczy) i nie mieć go (więc nikt jej nie
    ocenia) — czyli wejść na listę bez żadnej bramy.
    """
    recs = (_seria("team_goals", 30, 5, 1.7, strona="powyzej")
            + _seria("team_goals", 30, 25, 1.5, strona="ponizej"))
    log = _log(recs)
    assert set(rozliczanie.strony_kwarantanna(log)) <= rozliczanie.strony_ocenione(log)


def test_kwarantanna_zna_strony_rynku_kto_wiecej():
    """Nowy rynek ma kierunki „gospodarz"/„gosc", nie „powyzej"/„ponizej".
    Bez tego wchodziłby BEZ zabezpieczenia, które 30.07 okazało się
    najskuteczniejsze — to ono pokazało, że wszystkie tracące strony to
    „powyżej"."""
    recs = _seria("wiecej_shots", 30, 5, 1.9, strona="gospodarz")
    kw = rozliczanie.strony_kwarantanna(_log(recs))
    assert "wiecej_shots:gospodarz" in kw


# --- CIEN WYCENY: ile daja potwierdzone skalady (2026-08-01) ---------------

def test_cien_zapisuje_sie_obok_zamrozonej_liczby():
    """Karta i rozliczenie jada po cenie z chwili publikacji — cien tylko obok."""
    b = _typ_z_kursem(1, 0.70, 2.0, None)
    log = {}
    rozliczanie._dopisz_nowe(log, [b])
    klucz = next(iter(log))
    rozliczanie.ustaw_cienie_skladow({klucz: 0.55})
    try:
        rozliczanie._dopisz_nowe(log, [b])          # kolejny cykl, skladzy znane
    finally:
        rozliczanie.ustaw_cienie_skladow({})
    rec = log[klucz]
    assert rec["p_model"] == 0.70, "zamrozona szansa nie moze sie ruszyc"
    assert rec["p_cien"] == 0.55
    assert rec["p_cien_ts"] > 0


def test_cien_nie_dotyka_rozliczonych():
    b = _typ_z_kursem(1, 0.70, 2.0, "wygrany")
    log = {}
    rozliczanie._dopisz_nowe(log, [b])
    klucz = next(iter(log))
    log[klucz]["wynik"] = "wygrany"
    rozliczanie.ustaw_cienie_skladow({klucz: 0.55})
    try:
        rozliczanie._dopisz_nowe(log, [b])
    finally:
        rozliczanie.ustaw_cienie_skladow({})
    assert "p_cien" not in log[klucz], "rozliczony rekord jest zamrozony"


def test_raport_cieni_wykrywa_poprawe():
    """Typy weszly; cien mowil 0,8, zamrozone 0,5 -> sklad poprawia prognoze."""
    log = {}
    for i in range(120):
        log[str(i)] = {**_typ_z_kursem(i, 0.50, 2.0, "wygrany"),
                       "p_cien": 0.80}
    r = rozliczanie.raport_cieni(log)
    assert r["n"] == 120 and r["gotowy"] is True
    assert r["lepszy_cien"] > 0
    assert r["brier_ze_skladem"] < r["brier_zamrozone"]


def test_raport_cieni_milczy_bez_par():
    assert rozliczanie.raport_cieni({})["n"] == 0
    assert rozliczanie.raport_cieni({})["gotowy"] is False
