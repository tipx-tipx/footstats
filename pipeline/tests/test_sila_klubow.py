# -*- coding: utf-8 -*-
"""SIŁA KLUBU (Elo z poziomem ligi) jako cecha modelu drużynowego (2026-10-15).

Pilnuje rzeczy, które psują wynik po cichu:
  1. siła wiersza treningowego jest sprzed meczu (bez przecieku z wyniku),
  2. poziom ligi rusza się wyłącznie meczami międzyligowymi,
  3. wagi wytrenowane PRZED zmianą liczą identycznie (inaczej pierwszy cykl
     po wdrożeniu dostałby rozjazd schematu i model by zamilkł),
  4. poza zakresem treningu nie ekstrapolujemy (obcięcie ±1),
  5. opis na karcie mówi to, co liczy model.
"""
import pytest

from footstats.model import opis_uczony as O
from footstats.model import sila_klubow as S
from footstats.model import uczony as U


def _m(t, opp, dom, g, gp, liga=17, e=None):
    return {"t": t, "e": e or t, "o": opp, "h": dom, "l": liga, "g": g, "gp": gp,
            "s": {"cor": 6, "sh": 12}, "sp": {"cor": 4, "sh": 9}}


def _serie_dwie_ligi():
    """A, B grają w lidze 17; C, D w lidze 500; A–C to mecz międzyligowy."""
    return {
        "A": [_m(100, "B", 1, 3, 0, e=1), _m(110, "B", 0, 2, 0, e=2), _m(120, "C", 1, 4, 0, liga=7, e=3)],
        "B": [_m(100, "A", 0, 0, 3, e=1), _m(110, "A", 1, 0, 2, e=2)],
        "C": [_m(105, "D", 1, 1, 1, liga=500, e=4), _m(120, "A", 0, 0, 4, liga=7, e=3)],
        "D": [_m(105, "C", 0, 1, 1, liga=500, e=4)],
    }


def test_sila_przed_meczem_i_ruch_po_wyniku():
    st = S.licz(_serie_dwie_ligi())
    assert st["przed"][1][2:] == (0.0, 0.0), "pierwszy mecz: obie drużyny od zera"
    # A wygrała dwa razy z B w tej samej lidze → A silniejsza przed meczem 3
    _, _, r_a, r_c = st["przed"][3]
    assert r_a > 0 > st["R"]["B"]
    assert st["R"]["A"] > r_a, "wygrana z C podnosi A po meczu, nie przed"


def test_poziom_ligi_rusza_tylko_mecz_miedzyligowy():
    serie = _serie_dwie_ligi()
    bez = {k: [m for m in v if m["e"] != 3] for k, v in serie.items()}
    st0 = S.licz(bez)
    st = S.licz(serie)
    # po wygranej A z C poziom ligi 500 spada — D traci, choć nie grała,
    # a B (liga A) zyskuje, choć też nie grała
    assert st["R"]["D"] < st0["R"]["D"]
    assert st["R"]["B"] > st0["R"]["B"]


def test_sila_na_chwile_bez_przecieku():
    st = S.licz(_serie_dwie_ligi())
    assert S.sila_na(st, "A", 105) == pytest.approx(st["hist"]["A"][1][0])
    assert S.sila_na(st, "A", 50) == 0.0, "przed pierwszym meczem – zero"
    assert S.sila_na(st, "A", 10 ** 10) == st["R"]["A"], "nadchodzący mecz – siła bieżąca"
    assert S.sila_na(st, "NIEZNANA", 10 ** 10) is None


def test_roznica_z_domem_i_obcieciem():
    assert S.roznica(0.0, 0.0, True) == pytest.approx(S.PRZEWAGA_DOMU / S.SKALA)
    assert S.roznica(0.0, 0.0, False) == pytest.approx(-S.PRZEWAGA_DOMU / S.SKALA)
    assert S.roznica(2000.0, 0.0, True) == S.MAX_ROZNICY
    assert S.roznica(None, 0.0, True) is None


def _magazyn_silny_slaby(n=40):
    """Drużyna 10 (liga 17) wygrywa wysoko i ma więcej rożnych; 20 odwrotnie."""
    mag = {"10": {"m": []}, "20": {"m": []}}
    for i in range(n):
        dom = i % 2
        mag["10"]["m"].append({"t": 1000 + i, "e": 5000 + i, "o": 20, "h": dom, "l": 17,
                               "g": 3, "gp": 0, "s": {"cor": 7 + i % 3}, "sp": {"cor": 3}})
        mag["20"]["m"].append({"t": 1000 + i, "e": 5000 + i, "o": 10, "h": 1 - dom, "l": 17,
                               "g": 0, "gp": 3, "s": {"cor": 3 - i % 2}, "sp": {"cor": 7}})
    return mag


def test_wiersze_treningowe_maja_sile_sprzed_meczu():
    w = [x for x in U.wiersze_treningowe(_magazyn_silny_slaby())["team_corners"]
         if x["team"] == "10"]
    assert all(x["sila"] is not None for x in w)
    # silniejsza drużyna rośnie z każdym meczem – siła wiersza rośnie z czasem
    assert w[-1]["sila"] > w[0]["sila"] > -1


def test_stare_wagi_bez_lin_licza_jak_przed_zmiana():
    """Wagi z produkcji sprzed 15.10 nie znają `sila` ani `lin`."""
    wiersze = U.wiersze_treningowe(_magazyn_silny_slaby())["team_corners"] * 30
    U_LIN = list(U.CECHY_LIN)
    try:
        U.CECHY_LIN = list(U.CECHY_LIN_DAWNE)
        stare = U.trenuj_rynek(wiersze)
    finally:
        U.CECHY_LIN = U_LIN
    stare.pop("lin")                       # tak wyglądają wagi sprzed zmiany
    c = dict(wiersze[-1])
    assert U.lam(stare, c) == pytest.approx(U.lam(stare, {**c, "sila": 0.9}))
    nowe = U.trenuj_rynek(wiersze)
    assert nowe["lin"] == U.CECHY_LIN and "sila" in nowe["cechy"]
    assert U.lam(nowe, c) is not None


def test_cykl_i_trening_licza_sile_ta_sama_droga():
    mag = _magazyn_silny_slaby()
    ctx = U.przygotuj(mag)
    c = U.cechy_z_kontekstu(ctx, "10", "team_corners", "20", 1, 17)
    oczek = S.roznica(ctx["sila"]["R"]["10"], ctx["sila"]["R"]["20"], 1)
    assert c["sila"] == pytest.approx(oczek) and c["sila"] > 0
    # rywal spoza rankingu – cecha pusta (kolumna dostaje 0), nie zgadujemy
    assert U.cechy_z_kontekstu(ctx, "10", "team_corners", "999", 1, 17)["sila"] is None


def _typ(sila, dom, mn_sila, strona="powyzej"):
    return {"strona": strona, "linia": 4.5, "przeciwnik": "Brugge", "podmiot_typ": "druzyna",
            "p_uczony": {"p": 0.6, "lam": 5.0,
                         "skl": {"mn": {"sila": mn_sila}, "x": {"sila": sila, "dom": dom}, "ref": {}}}}


def test_opis_sily_na_karcie():
    cz = O.czynniki(_typ(0.6, 1, 1.25))
    sil = [c for c in cz if c["nazwa"] == "Siła drużyn"]
    assert sil and sil[0]["opis"].startswith("Według wyników ostatnich meczów drużyna ")
    assert sil[0]["opis"].endswith(" jest wyraźnie silniejsza od drużyny Brugge")
    assert sil[0]["mnoznik"] == 1.25
    # „poniżej” – ten sam czynnik działa przeciw typowi
    assert [c for c in O.czynniki(_typ(0.6, 1, 1.25, "ponizej"))
            if c["nazwa"] == "Siła drużyn"][0]["mnoznik"] == pytest.approx(0.8)


def test_opis_bez_zdania_gdy_roznica_to_tylko_dom():
    """Gospodarz o równej sile: różnica 0,15 to sama przewaga domu – ta ma
    własny wiersz „Gdzie gra”, więc „Siła drużyn” się nie pokazuje."""
    assert not [c for c in O.czynniki(_typ(0.15, 1, 1.06)) if c["nazwa"] == "Siła drużyn"]
    # gospodarz słabszy o 0,12, ale z domem wychodzi +0,03: czynnik działa
    # jak dla silniejszego, więc zdanie „słabsza” byłoby sprzeczne – nie ma go
    assert not [c for c in O.czynniki(_typ(0.03, 1, 1.05)) if c["nazwa"] == "Siła drużyn"]
