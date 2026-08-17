# -*- coding: utf-8 -*-
"""MODEL UCZONY NA DANYCH — regresja Poissona zamiast formuły z ręcznymi mnożnikami.

Zmierzone 17.08 na 4398 typach, które poszły na stronę (pełne liczby
w `docs/model-uczony-pomiar.md`): luka deklaracji −14,4 pp → −0,7 pp,
Brier 0,2434 → 0,2291.

Te testy pilnują rzeczy, które przy modelu uczonym najłatwiej złamać, a każda
z nich psuje wynik po cichu:
  1. cechy liczone TYLKO z przeszłości (wyciek z przyszłości daje świetny
     pomiar i bezużyteczny model),
  2. jedna funkcja cech dla treningu i produkcji,
  3. schemat cech ustalony na treningu i narzucony predykcji,
  4. brak danych nie udaje prognozy.
"""
import math

import numpy as np

from footstats.model import uczony as U


def _mecz(ts, cor=6, cor_opp=4, dom=1, opp=99, liga=1, gole=2):
    return {"t": ts, "e": ts, "o": opp, "h": dom, "l": liga, "g": gole, "gp": 1,
            "s": {"cor": cor, "pos": 55, "crs": 8, "f3": 100},
            "sp": {"cor": cor_opp, "pos": 45, "crs": 5, "f3": 80}}


def _magazyn(n=40, tid="10", opp="99"):
    """Prosty magazyn: drużyna 10 notuje ~6 rożnych, rywal 99 dopuszcza ~4."""
    mag = {
        tid: {"m": [_mecz(1000 + i, cor=6, dom=i % 2, opp=int(opp))
                    for i in range(n)]},
        opp: {"m": [_mecz(1000 + i, cor=4, cor_opp=6, dom=(i + 1) % 2, opp=int(tid))
                    for i in range(n)]},
    }
    return mag


# --- 1. żadnego zaglądania w przyszłość ------------------------------------

def _nasze(mag, rynek="team_corners", tid="10"):
    """Wiersze JEDNEJ drużyny — `wiersze_treningowe` zwraca wszystkie naraz."""
    return [w for w in U.wiersze_treningowe(mag)[rynek] if w["team"] == tid]


def test_cechy_licza_sie_tylko_z_przeszlosci():
    """Wiersz meczu i nie może znać tego meczu ani żadnego późniejszego.

    Wyciek z przyszłości to najgorszy możliwy błąd w takim zbiorze: daje
    świetny pomiar i bezużyteczny model, a w danych nie zostawia śladu.
    """
    mag = _magazyn(n=20)
    przed = _nasze(mag)
    # skrajna wartość w OSTATNIM meczu — cechy wcześniejszych wierszy nie mogą
    # o niej wiedzieć
    mag["10"]["m"][-1]["s"]["cor"] = 99
    po = _nasze(mag)
    assert len(przed) == len(po)
    for a, b in zip(przed[:-1], po[:-1]):
        assert a["w6"] == b["w6"] and a["w12"] == b["w12"]
        assert a["y"] == b["y"], "zmienił się cel wcześniejszego meczu"
    assert po[-1]["y"] == 99.0, "cel OSTATNIEGO wiersza ma się zmienić"
    assert po[-1]["w6"] == przed[-1]["w6"], "…ale jego cechy już nie"


def test_wiersz_wymaga_minimum_historii():
    mag = _magazyn(n=U.MIN_HISTORII)
    assert not U.wiersze_treningowe(mag).get("team_corners")


def test_koncesje_rywala_ida_z_jego_meczow():
    """`opp12` to ile RYWAL DOPUSZCZA, nie ile sam notuje."""
    mag = _magazyn(n=20)
    w = _nasze(mag)[-1]
    assert w["w6"] == 6.0, "nasza drużyna notuje 6 rożnych"
    assert w["opp12"] == 6.0, "rywal w swoich meczach dopuszczał 6 (pole `sp`)"
    # kontrola z drugiej strony: dla rywala te liczby są odwrotne
    ich = _nasze(mag, tid="99")[-1]
    assert ich["w6"] == 4.0 and ich["opp12"] == 4.0


# --- 2 i 3. jedna droga cech, schemat z treningu ---------------------------

def test_cechy_produkcyjne_to_te_same_cechy():
    """Predykcja dla nadchodzącego meczu liczy się tą samą funkcją co trening."""
    mag = _magazyn(n=20)
    c = U.cechy_na_mecz(mag, 10, "team_corners", opp_id=99, dom=1, liga=1,
                        do_ts=99999)
    assert c is not None
    # wiersz treningowy z tą samą historią: ostatni mecz drużyny 10 u siebie
    tren = [w for w in _nasze(mag) if w["dom"] == 1][-1]
    for pole in ("w6", "w12", "opp12", "liga", "trend", "brak_rywala"):
        assert c[pole] == tren[pole], f"{pole} liczone inaczej w produkcji"


def test_schemat_z_treningu_narzucony_predykcji():
    """Inna liczba kolumn = inny model. Wagi i cechy muszą się zgadzać."""
    mag = _magazyn(n=40)
    wiersze = U.wiersze_treningowe(mag)["team_corners"]
    sch = U.schemat(wiersze)
    X = U.macierz(wiersze, sch)
    assert X.shape[1] == len(U.nazwy_cech(sch))
    # wiersz z BRAKAMI dostaje tyle samo kolumn
    ubogi = {"w6": 5.0, "dom": 1}
    assert U.macierz([ubogi], sch).shape[1] == X.shape[1]


def test_rozjazd_wag_i_cech_daje_cisze_nie_zgadywanie():
    mag = _magazyn(n=40)
    wagi = U.trenuj_rynek(U.wiersze_treningowe(mag)["team_corners"] * 30)
    assert wagi is not None
    wagi_zle = {**wagi, "beta": wagi["beta"][:-1]}
    c = U.cechy_na_mecz(mag, 10, "team_corners", 99, 1, 1, do_ts=99999)
    assert U.lam(wagi_zle, c) is None, "niepełny zestaw cech musi MILCZEĆ"


# --- 4. brak danych nie udaje prognozy ------------------------------------

def test_druzyna_bez_historii_nie_dostaje_prognozy():
    assert U.cechy_na_mecz({}, 10, "team_corners", 99, 1, 1) is None


def test_nieznany_rynek_milczy():
    mag = _magazyn(n=20)
    assert U.cechy_na_mecz(mag, 10, "wiecej_shots", 99, 1, 1) is None


def test_maly_rynek_nie_dostaje_wag():
    assert U.trenuj_rynek([{"w6": 5.0, "dom": 1, "y": 5.0, "t": 1}]) is None


# --- rachunek: czy w ogóle liczy sensownie --------------------------------

def test_model_uczy_sie_poziomu_druzyny():
    """Drużyna notująca 9 dostaje wyższą λ niż notująca 3."""
    duzo = {"10": {"m": [_mecz(1000 + i, cor=9, dom=i % 2) for i in range(40)]},
            "99": {"m": [_mecz(1000 + i, cor=4, cor_opp=9, dom=(i + 1) % 2)
                         for i in range(40)]}}
    malo = {"10": {"m": [_mecz(1000 + i, cor=3, dom=i % 2) for i in range(40)]},
            "99": {"m": [_mecz(1000 + i, cor=4, cor_opp=3, dom=(i + 1) % 2)
                         for i in range(40)]}}
    # trenujemy na obu naraz, żeby model miał rozpiętość
    razem = U.wiersze_treningowe(duzo)["team_corners"] * 15 + \
        U.wiersze_treningowe(malo)["team_corners"] * 15
    wagi = U.trenuj_rynek(razem)
    assert wagi is not None
    lam_duzo = U.lam(wagi, U.cechy_na_mecz(duzo, 10, "team_corners", 99, 1, 1,
                                           do_ts=99999))
    lam_malo = U.lam(wagi, U.cechy_na_mecz(malo, 10, "team_corners", 99, 1, 1,
                                           do_ts=99999))
    assert lam_duzo > lam_malo, "model nie odróżnia drużyny notującej 9 od 3"


def test_p_powyzej_zgadza_sie_z_rozkladem():
    """Ogon Poissona liczony ręcznie — musi zgadzać się ze scipy."""
    from scipy.stats import poisson
    for lam_ in (0.8, 2.5, 6.0, 12.0):
        for linia in (0.5, 1.5, 4.5, 12.5):
            nasze = U.p_powyzej(lam_, linia)
            wzor = 1.0 - poisson.cdf(math.floor(linia), lam_)
            assert abs(nasze - wzor) < 1e-6, (lam_, linia)


def test_strony_sumuja_sie_do_jedynki():
    """Jedna λ, dwie strony — bez tego wracamy do niespójnych szans."""
    for lam_ in (1.2, 5.5, 11.0):
        p_over = U.p_strony(lam_, 4.5, "powyzej")
        p_under = U.p_strony(lam_, 4.5, "ponizej")
        assert abs(p_over + p_under - 1.0) < 1e-9


def test_brak_lambdy_nie_daje_szansy():
    assert U.p_powyzej(None, 4.5) is None
    assert U.p_strony(None, 4.5, "powyzej") is None


def test_naddyspersja_rozpoznaje_rozklad():
    """1,0 = dokładnie Poisson; wyżej = rozkład szerszy niż zakładamy."""
    rng = np.random.default_rng(7)
    mu = np.full(4000, 5.0)
    y_poisson = rng.poisson(5.0, 4000).astype(float)
    assert abs(U.naddyspersja(y_poisson, mu) - 1.0) < 0.12
    y_szerokie = rng.negative_binomial(5, 0.5, 4000).astype(float)
    assert U.naddyspersja(y_szerokie, np.full(4000, y_szerokie.mean())) > 1.3


def test_stan_bez_wag_krzyczy():
    assert "BRAK WAG" in U.zdanie_stanu(None)
    assert "BRAK WAG" in U.zdanie_stanu({"rynki": {}})


# --- rozkład: Poisson jest za wąski dla części rynków ---------------------

def test_ksztalt_nb_rozpoznaje_rozrzut():
    """Zmierzone 17.08: naddyspersja 1,56 na rożnych i 1,90 na strzałach."""
    rng = np.random.default_rng(11)
    mu = np.full(5000, 5.0)
    # dane dokładnie poissonowskie — NB niepotrzebny
    assert U.kształt_nb(rng.poisson(5.0, 5000).astype(float), mu) is None
    # dane rozleglejsze — r skończone i dodatnie
    y = rng.negative_binomial(5, 0.5, 5000).astype(float)
    r = U.kształt_nb(y, np.full(5000, y.mean()))
    assert r is not None and r > 0


def test_nb_daje_grubsze_ogony_niz_poisson():
    """Sedno poprawki: przy tej samej λ skrajna linia ma WIĘKSZĄ szansę.

    Poisson zaniżał „powyżej" na wysokich liniach, czyli tam, gdzie zakład
    jest ciekawy — a to jest liczba, którą sprzedajemy.
    """
    lam_ = 5.0
    for linia in (8.5, 9.5, 11.5):
        p_poisson = U.p_powyzej(lam_, linia)
        p_nb = U.p_powyzej(lam_, linia, r_nb=8.0)
        assert p_nb > p_poisson, linia
    # ...a blisko środka rozkładu różnica jest niewielka
    assert abs(U.p_powyzej(lam_, 4.5, r_nb=8.0) - U.p_powyzej(lam_, 4.5)) < 0.06


def test_nb_strony_nadal_sumuja_sie_do_jedynki():
    for lam_ in (1.2, 5.5, 11.0):
        p_o = U.p_strony(lam_, 4.5, "powyzej", r_nb=6.0)
        p_u = U.p_strony(lam_, 4.5, "ponizej", r_nb=6.0)
        assert abs(p_o + p_u - 1.0) < 1e-9


def test_nb_zgadza_sie_z_rozkladem_wzorcowym():
    from scipy.stats import nbinom
    for lam_ in (2.0, 5.0, 12.0):
        for r in (3.0, 8.0, 40.0):
            for linia in (1.5, 4.5, 10.5):
                p0 = r / (r + lam_)
                wzor = 1.0 - nbinom.cdf(math.floor(linia), r, p0)
                nasze = U.p_powyzej(lam_, linia, r_nb=r)
                assert abs(nasze - wzor) < 1e-6, (lam_, r, linia)


def test_trend_jest_osobna_informacja():
    """„Ostatnio więcej niż zwykle" to nie to samo co poziom drużyny."""
    rosnie = {"10": {"m": [_mecz(1000 + i, cor=3 if i < 30 else 9, dom=i % 2)
                           for i in range(40)]},
              "99": {"m": [_mecz(1000 + i, cor=4, cor_opp=5, dom=(i + 1) % 2)
                           for i in range(40)]}}
    c = U.cechy_na_mecz(rosnie, 10, "team_corners", 99, 1, 1, do_ts=99999)
    # w3 = 9, w12 = (2×3 + 10×9)/12 = 8,0  ->  log(9,5/8,5) ≈ 0,11
    assert c["trend"] > 0.1, "trzy ostatnie mecze powyżej dłuższego okna"
    # skok ostry: ostatnie 4 mecze po 12 przy 36 meczach po 2
    ostro = {"10": {"m": [_mecz(1000 + i, cor=2 if i < 36 else 12, dom=i % 2)
                          for i in range(40)]},
             "99": {"m": [_mecz(1000 + i, cor=4, cor_opp=5, dom=(i + 1) % 2)
                          for i in range(40)]}}
    c_ostro = U.cechy_na_mecz(ostro, 10, "team_corners", 99, 1, 1, do_ts=99999)
    # w3 = 12, w12 = (8×2 + 4×12)/12 = 5,33  ->  log(12,5/5,83) ≈ 0,76
    assert c_ostro["trend"] > 0.7, "skok z 2 na 12 musi być wyraźnym trendem"
    assert c_ostro["trend"] > c["trend"], "ostrzejszy skok = mocniejszy trend"
    stabilne = _magazyn(n=40)
    c2 = U.cechy_na_mecz(stabilne, 10, "team_corners", 99, 1, 1, do_ts=99999)
    assert abs(c2["trend"]) < 1e-9, "stała forma = brak trendu"


def test_brak_rywala_to_jedna_flaga():
    """Dwie skorelowane flagi kompensowały się nawzajem (+0,49 i −0,45)."""
    mag = _magazyn(n=20)
    c = U.cechy_na_mecz(mag, 10, "team_corners", opp_id=12345, dom=1, liga=1,
                        do_ts=99999)
    assert c["brak_rywala"] == 1.0 and c["opp12"] is None
    c2 = U.cechy_na_mecz(mag, 10, "team_corners", opp_id=99, dom=1, liga=1,
                         do_ts=99999)
    assert c2["brak_rywala"] == 0.0
