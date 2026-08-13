# -*- coding: utf-8 -*-
"""DRUGI SZCZEBEL DRABINKI JAKO OSOBNE ROZLICZENIE (2026-08-13).

Karta pokazuje drabinkę: szczebel z nagłówka (`hero`) i drugi szczebel, który
user ma „upolować". Do dziś księga zapisywała WYŁĄCZNIE hero, więc zdanie,
na którym stoi cała zakładka, nie miało ani jednego rozliczenia — przy ROI
strumienia −25% to była najdroższa biała plama produktu.

Te testy pilnują trzech rzeczy naraz:
  1. drugi szczebel dojeżdża do księgi z własnym kluczem i stemplem,
  2. jest POMIAREM — nie rusza Skuteczności, kalibracji ani korekty strumienia,
  3. `pomiar_szczebli_drabinek` zestawia oba poziomy i mierzy korektę
     strumienia nałożoną na drugi szczebel (pozycja z kolejki po audycie).
"""
from footstats.jobs import rozliczanie


def _szczebel(i, *, poziom, p, wynik, linia, kurs, p_raw=None):
    rec = {
        "mecz_id": i, "mecz": "Alfa – Beta", "kickoff_ts": 1_786_000_000 + i,
        "podmiot_id": i, "podmiot": f"Zawodnik {i}",
        "rynek_kod": "shots", "rynek": "Strzały", "linia": linia,
        "strona": "powyzej", "kurs": kurs, "p_model": p, "wynik": wynik,
        "zrodlo": rozliczanie.ZRODLO_DRABINKA, "szczebel": poziom,
    }
    if p_raw is not None:
        rec["rachunek"] = {"p_over_raw": p_raw, "p_over_final": p}
    if poziom == 2:
        rec["odrzucony"] = True
        rec["odrzucenie_powod"] = rozliczanie.POWOD_POMIARU_DRUGIEGO
    return rec


def _para(i, *, hero_wynik, drugi_wynik, p_drugi=0.35, p_raw=None):
    return (
        _szczebel(i, poziom=1, p=0.62, wynik=hero_wynik, linia=1.5, kurs=1.6),
        _szczebel(i, poziom=2, p=p_drugi, wynik=drugi_wynik, linia=2.5,
                  kurs=3.2, p_raw=p_raw),
    )


def test_drugi_szczebel_ma_wlasny_klucz_w_ksiedze():
    """Ten sam zawodnik i rynek, INNA linia — dwa rekordy, nie jeden.

    Gdyby klucz nie rozróżniał linii, drugi szczebel nadpisałby hero i pomiar
    kosztowałby nas rozliczenie zamiast je dołożyć."""
    hero, drugi = _para(1, hero_wynik=None, drugi_wynik=None)
    log = {}
    rozliczanie._dopisz_nowe(log, [hero, drugi])
    assert len(log) == 2
    poziomy = sorted(r["szczebel"] for r in log.values())
    assert poziomy == [1, 2]


def test_stempel_szczebla_przechodzi_biala_liste():
    """`_dopisz_nowe` przepisuje tylko pola z własnej listy — nowe pole bez
    wpisu tam ginie po cichu (udokumentowana pułapka repo)."""
    log = {}
    rozliczanie._dopisz_nowe(log, [_szczebel(
        7, poziom=2, p=0.31, wynik=None, linia=2.5, kurs=3.4, p_raw=0.44
    )])
    rec = next(iter(log.values()))
    assert rec["szczebel"] == 2
    assert rec["odrzucenie_powod"] == rozliczanie.POWOD_POMIARU_DRUGIEGO
    assert rec["rachunek"]["p_over_raw"] == 0.44


def test_drugi_szczebel_nie_uczy_korekty_strumienia():
    """Pomiar ma dokładać wiedzę, nie przesuwać szans publikowanych kart."""
    log = {}
    for i in range(rozliczanie.KOREKTA_DRABINEK_MIN_N + 5):
        log[f"d{i}"] = _szczebel(
            i, poziom=2, p=0.55, wynik="przegrany", linia=2.5, kurs=3.0
        )
    assert rozliczanie.korekta_strumienia(log) == {}


def test_drugi_szczebel_poza_pomiarem_progu_pokrycia():
    """Dwa pomiary, dwie grupy — drugi szczebel nie ma prawa wejść do żadnej
    z grup pomiaru progu, bo mierzy zupełnie co innego."""
    log = {}
    for i in range(6):
        log[f"h{i}"] = _szczebel(
            i, poziom=1, p=0.6, wynik="wygrany", linia=1.5, kurs=1.7
        )
        log[f"d{i}"] = _szczebel(
            i, poziom=2, p=0.3, wynik="przegrany", linia=2.5, kurs=3.5
        )
    p = rozliczanie.pomiar_progu_drabinek(log)
    assert p["opublikowane"]["n"] == 6
    assert p["pod_progiem"]["n"] == 0


def test_pomiar_szczebli_zestawia_oba_poziomy():
    log = {}
    # cztery karty: w dwóch wszedł też drugi szczebel, w dwóch tylko pierwszy
    for i, (h, d) in enumerate([
        _para(1, hero_wynik="wygrany", drugi_wynik="wygrany"),
        _para(2, hero_wynik="wygrany", drugi_wynik="wygrany"),
        _para(3, hero_wynik="wygrany", drugi_wynik="przegrany"),
        _para(4, hero_wynik="przegrany", drugi_wynik="przegrany"),
    ]):
        log[f"h{i}"], log[f"d{i}"] = h, d
    p = rozliczanie.pomiar_szczebli_drabinek(log)
    assert p["hero"]["n"] == 4 and p["hero"]["trafione"] == 3
    assert p["drugi"]["n"] == 4 and p["drugi"]["trafione"] == 2
    assert p["pary"]["n"] == 4
    assert p["pary"]["oba"] == 2 and p["pary"]["tylko_hero"] == 1
    assert p["pary"]["udzial_oba"] == 0.5
    # ROI drugiego szczebla liczy się z JEGO ceny (3,2), nie z ceny hero
    assert p["drugi"]["roi"] == round((2 * 2.2 - 2) / 4, 3)


def test_pomiar_szczebli_widzi_niespojne_rozliczenie():
    """Wyższy szczebel wszedł, niższy nie — arytmetycznie niemożliwe.
    To alarm o rozliczaniu, nie ciekawostka o modelu."""
    log = {}
    h, d = _para(9, hero_wynik="przegrany", drugi_wynik="wygrany")
    log["h"], log["d"] = h, d
    p = rozliczanie.pomiar_szczebli_drabinek(log)
    assert p["pary"]["niespojne"] == 1


def test_pomiar_szczebli_porownuje_deklaracje_przed_i_po_korekcie():
    """Kolejka pyta, czy korektę zmierzoną na hero wolno nakładać na drugi
    szczebel. Odpowiedź wymaga OBU deklaracji przy tej samej prawdzie."""
    log = {}
    for i in range(4):
        log[f"d{i}"] = _szczebel(
            i, poziom=2, p=0.30, wynik="wygrany" if i < 2 else "przegrany",
            linia=2.5, kurs=3.2, p_raw=0.42,
        )
    p = rozliczanie.pomiar_szczebli_drabinek(log)
    k = p["korekta_strumienia"]
    assert k["n"] == 4
    assert k["deklaracja_przed"] == 0.42     # przed ścięciem
    assert k["deklaracja_po"] == 0.30        # to, co pokazała karta
    assert k["faktycznie"] == 0.5            # 2 z 4 weszły
    # przy takiej próbie to ścięcie było w złą stronę — ale wnioski dopiero
    # od progu, więc pomiar niesie go ze sobą
    assert p["min_n"] == rozliczanie.KOREKTA_DRABINEK_MIN_N


def test_hero_bez_stempla_liczy_sie_jak_pierwszy_szczebel():
    """Rekordy sprzed 13.08 nie mają pola `szczebel` i NIE są przepisywane
    wstecz — mają się liczyć jako hero, bo tylko takie wtedy powstawały."""
    log = {"stary": {
        "mecz_id": 5, "mecz": "Alfa – Beta", "kickoff_ts": 1_786_000_005,
        "podmiot_id": 5, "podmiot": "Zawodnik 5", "rynek_kod": "shots",
        "rynek": "Strzały", "linia": 1.5, "strona": "powyzej", "kurs": 1.8,
        "p_model": 0.6, "wynik": "wygrany",
        "zrodlo": rozliczanie.ZRODLO_DRABINKA,
    }}
    p = rozliczanie.pomiar_szczebli_drabinek(log)
    assert p["hero"]["n"] == 1 and p["drugi"]["n"] == 0
