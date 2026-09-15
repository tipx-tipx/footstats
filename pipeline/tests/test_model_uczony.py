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


# ⚑ liga=17 to Premier League — MUSI być rozgrywką z zakresu drużynowego
# (`rozgrywki.PROFILE`), bo od 18.08 trening bierze WYŁĄCZNIE mecze
# z zakresu ([[magazyn-gubil-top-ligi]]). Fixture z ligą spoza zakresu
# dawałby zero wierszy i testy mierzyłyby pustkę zamiast modelu.
def _mecz(ts, cor=6, cor_opp=4, dom=1, opp=99, liga=17, gole=2):
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
    # liga MUSI być ta sama co w magazynie (17), inaczej średnia ligowa
    # wychodzi None i test porównuje dwie różne rozgrywki
    c = U.cechy_na_mecz(mag, 10, "team_corners", opp_id=99, dom=1, liga=17,
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


# --- zasięg modelu i widełki półek ----------------------------------------
#
# Zmierzone 17.08 na 4470 typach: luka deklaracji wobec odległości linii od λ
# wynosi −0,3 pp przy 0–1, ale −15,5 pp przy 4+. Trzy procent typów niesie całą
# lukę na górze rozkładu. Kalibracja tego NIE naprawia (krzywa Platta wyszła
# b ≈ 1,00, Brier nawet gorszy) — problem jest lokalny, w ogonie.

def test_zasieg_odcina_skrajny_ogon():
    """Linia daleka od λ to obszar, w którym model zgaduje."""
    assert U.w_zasiegu(5.0, 4.5) and U.w_zasiegu(5.0, 6.5)
    assert U.w_zasiegu(5.0, 7.5), "dokładnie 2,5 jeszcze wchodzi"
    assert not U.w_zasiegu(5.0, 8.5), "3,5 od λ to już ogon"
    assert not U.w_zasiegu(4.0, 8.5)
    assert not U.w_zasiegu(None, 4.5), "brak λ to nie „w zasięgu”"


def test_polki_dziela_typy_po_kursie():
    assert U.polka_dla(1.45) == "wysoka_szansa"
    assert U.polka_dla(1.79) == "wysoka_szansa"
    assert U.polka_dla(1.80) == "wyzsze_kursy"
    assert U.polka_dla(2.19) == "wyzsze_kursy"
    assert U.polka_dla(2.25) is None, "powyżej 2,20 model jest anty-sygnałem"
    assert U.polka_dla(1.10) is None
    assert U.polka_dla(None) is None


def test_regula_zasiegu_tylko_na_polce_pewniakow():
    """⚑ Na wyższych kursach zasięg POGARSZA wynik (53,4% → 48,9%).

    Wysoki kurs to z definicji zdarzenie rzadkie, czyli linia daleka od λ —
    odcinanie takich typów wycięłoby z tej półki właśnie to, po co istnieje.
    """
    # pewniak z linią daleko od λ — odpada
    ok, powod = U.dopuszczony(1.45, lambda_=4.0, linia=8.5)
    assert not ok and powod == "linia_poza_zasiegiem_modelu"
    # ten sam układ na półce wyższych kursów — wchodzi
    ok2, powod2 = U.dopuszczony(1.95, lambda_=4.0, linia=8.5)
    assert ok2 and powod2 is None
    # pewniak z linią blisko λ — wchodzi
    ok3, _ = U.dopuszczony(1.45, lambda_=4.0, linia=5.5)
    assert ok3


def test_kurs_poza_polkami_ma_powod():
    ok, powod = U.dopuszczony(3.20, lambda_=4.0, linia=4.5)
    assert not ok and powod == "kurs_poza_polkami"


def test_polki_maja_limity_i_granice():
    """Cztery liczby całych widełek — bez progów wartości i EV."""
    assert set(U.POLKI) == {"wysoka_szansa", "wyzsze_kursy"}
    # 2026-09-15, decyzja właściciela: 15 + 5 na dobę (było 18 + 3);
    # pewniaki drużynowe do 1,45.
    assert U.POLKI["wysoka_szansa"]["limit_dobowy"] == 15
    assert U.POLKI["wyzsze_kursy"]["limit_dobowy"] == 5
    assert U.KURS_MAX_PEWNIAKA == {"druzyna": 1.45}
    assert U.polka_dla(1.60, "druzyna") is None
    assert U.polka_dla(1.60, "zawodnik") == "wysoka_szansa"
    assert U.polka_dla(1.40, "druzyna") == "wysoka_szansa"
    assert U.POLKI["wyzsze_kursy"]["kurs_max"] == 2.20, (
        "granica 2,20 ma pokrycie w pomiarze: wyżej górna tercja szansy "
        "trafia 30,8%, a dolna 46,7%"
    )
    assert U.POLKI["wyzsze_kursy"]["zasieg"] is None


# --- druga liczba w cyklu: model liczy OBOK starego rachunku --------------

def test_kontekst_liczy_te_same_cechy_co_pojedyncze_wywolanie():
    """Kontekst istnieje dla szybkości, nie może zmieniać liczb."""
    mag = _magazyn(n=30)
    ctx = U.przygotuj(mag)
    a = U.cechy_z_kontekstu(ctx, 10, "team_corners", 99, 1, 1, do_ts=99999)
    b = U.cechy_na_mecz(mag, 10, "team_corners", 99, 1, 1, do_ts=99999)
    assert a == b


def test_prognoza_daje_komplet_albo_nic():
    mag = _magazyn(n=40)
    wagi = {"rynki": {"team_corners": U.trenuj_rynek(
        U.wiersze_treningowe(mag)["team_corners"] * 30)}}
    ctx = U.przygotuj(mag)
    out = U.prognoza(wagi, ctx, 10, "team_corners", 99, 1, 1,
                     linia=5.5, strona="powyzej", do_ts=99999)
    # ⚑ POLA POKRYCIA SĄ OPCJONALNE, RESZTA OBOWIĄZKOWA (2026-08-24). Pokrycie
    # liczy się tylko wtedy, gdy historii starczy — brak pola znaczy „nie
    # wiemy", nie „zero". Kontrakt pilnuje więc obu stron: komplet obowiązkowy
    # ma być zawsze, a niczego spoza listy nie wolno dorzucić po cichu.
    obowiazkowe = {"p", "lam", "r_nb", "odl", "sciag"}
    dozwolone = obowiazkowe | {"pkw", "pkr", "pkn", "pkrn", "pokr",
                               "p_bez_pokrycia"}
    assert obowiazkowe <= set(out) <= dozwolone
    assert 0.0 < out["p"] < 1.0 and out["lam"] > 0
    assert out["odl"] == round(abs(5.5 - out["lam"]), 2)
    # strony sumują się do jedynki także po drodze przez `prognoza`
    pod = U.prognoza(wagi, ctx, 10, "team_corners", 99, 1, 1,
                     linia=5.5, strona="ponizej", do_ts=99999)
    assert abs(out["p"] + pod["p"] - 1.0) < 2e-4


def test_prognoza_milczy_bez_wag_i_bez_historii():
    mag = _magazyn(n=40)
    ctx = U.przygotuj(mag)
    assert U.prognoza(None, ctx, 10, "team_corners", 99, 1, 1, 5.5,
                      "powyzej") is None
    assert U.prognoza({"rynki": {}}, ctx, 10, "team_corners", 99, 1, 1, 5.5,
                      "powyzej") is None
    wagi = {"rynki": {"team_corners": U.trenuj_rynek(
        U.wiersze_treningowe(mag)["team_corners"] * 30)}}
    # drużyna, której magazyn nie zna
    assert U.prognoza(wagi, ctx, 777777, "team_corners", 99, 1, 1, 5.5,
                      "powyzej") is None


def test_stempel_drugiej_liczby_jedzie_wszystkimi_drogami():
    """`p_uczony` musi przejść przez każdą białą listę pól po drodze.

    To ta sama pułapka, która 16–17.08 zatrzymała stempel `kal_strony`
    na czterech listach naraz.
    """
    import inspect

    from footstats.jobs import build_wc_fast as B
    from footstats.jobs import rozliczanie as R

    assert "p_uczony" in B._STEMPLE_PUBLIKACJI, "wznowiony typ gubiłby drugą liczbę"

    zrodlo = inspect.getsource(B)
    i = zrodlo.index('"rank_score": round(_atrakcyjnosc(b), 4)')
    assert '"p_uczony"' in zrodlo[i:i + 2500], "biała lista `rec_pewniaka`"

    rec = R._kupon_leg_do_logu({
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 1, "podmiot": "A",
        "rynek": "Rożne", "rynek_kod": "team_corners", "linia": 4.5,
        "strona": "ponizej", "kurs": 1.85, "p_model": 0.55,
        "p_uczony": {"p": 0.51, "lam": 4.2, "r_nb": 9.4, "odl": 0.3},
    })
    assert rec.get("p_uczony", {}).get("p") == 0.51

    log: dict = {}
    R._dopisz_nowe(log, [{
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 2,
        "podmiot_id": 5, "podmiot": "A", "podmiot_typ": "druzyna",
        "rynek_kod": "team_corners", "rynek": "Rożne", "linia": 4.5,
        "strona": "ponizej", "kurs": 1.85, "p_model": 0.55,
        "pewnosc": "wysoka",
        "p_uczony": {"p": 0.49, "lam": 4.4, "r_nb": 9.4, "odl": 0.1},
    }])
    assert next(iter(log.values())).get("p_uczony", {}).get("p") == 0.49


def test_druga_liczba_nie_wchodzi_do_zadnej_bramy():
    """Model liczy OBOK — jedno przeoczenie i nowy rachunek zmienia produkt
    przed pomiarem, czyli dokładnie to, czego mamy nie robić."""
    import inspect

    from footstats.jobs import build_wc_fast as B

    zrodlo = inspect.getsource(B)
    # `p_uczony` może być wyłącznie ZAPISYWANE, nigdy czytane do decyzji
    for wzor in ('if _pu["p"', 'p_uczony"]["p"] >', 'p_uczony")["p"] >',
                 '_pu["p"] >', '_pu["p"] <'):
        assert wzor not in zrodlo, (
            f"druga liczba wchodzi do decyzji przez `{wzor}` — najpierw pomiar"
        )


# --- ZAWODNICY: ten sam model, offset minut -------------------------------
#
# Zmierzone 17.08 na 260 rozliczonych typach zawodniczych: luka −12,5 pp
# (produkcja) wobec −6,7 pp (model), Brier 0,2305 wobec 0,2263.

def _seria_zaw(n=20, tempo=2.0, minuty=90.0, poz="ST", malejaco=True):
    """Seria jak w banku: tempo `tempo` zdarzeń na 90 minut."""
    czasy = [1000 + i for i in range(n)]
    counts = [tempo * minuty / 90.0 for _ in range(n)]
    seria = {
        "counts": counts, "minutes": [minuty] * n, "timestamps": czasy,
        "started": [True] * n, "game_positions": [poz] * n,
        "league_average": 1.5, "opponent_average": 1.6, "is_home": True,
        "market_code": "shots", "player_id": 7,
    }
    if malejaco:            # bank trzyma serie od najnowszej
        for k in ("counts", "minutes", "timestamps", "started", "game_positions"):
            seria[k] = list(reversed(seria[k]))
    return seria


def test_bank_trzyma_serie_malejaco_i_model_to_wie():
    """⚑ Odwrotna kolejność = model uczyłby się na przyszłości."""
    rosnaco = _seria_zaw(n=10, malejaco=False)
    malejaco = _seria_zaw(n=10, malejaco=True)
    a = U.cechy_zawodnika(rosnaco, do_ts=99999)
    b = U.cechy_zawodnika(malejaco, do_ts=99999)
    assert a is not None and b is not None
    assert abs(a["t6"] - b["t6"]) < 1e-9, "kolejność serii nie może zmieniać cech"


def test_cechy_zawodnika_licza_tempo_na_90_minut():
    """Zawodnik grający 45 minut z jednym strzałem ma tempo 2, nie 1."""
    pol = _seria_zaw(n=12, tempo=2.0, minuty=45.0)
    pelne = _seria_zaw(n=12, tempo=2.0, minuty=90.0)
    c1 = U.cechy_zawodnika(pol, do_ts=99999)
    c2 = U.cechy_zawodnika(pelne, do_ts=99999)
    assert abs(c1["t6"] - 2.0) < 1e-6 and abs(c2["t6"] - 2.0) < 1e-6
    assert c1["min6"] == 45.0 and c2["min6"] == 90.0


def test_krotkie_wejscia_nie_licza_sie_do_tempa():
    """5 minut z jednym strzałem dałoby tempo 18 na 90 minut."""
    seria = _seria_zaw(n=12, tempo=2.0, minuty=5.0)
    assert U.cechy_zawodnika(seria, do_ts=99999) is None


def test_cechy_zawodnika_widza_tylko_przeszlosc():
    seria = _seria_zaw(n=20, malejaco=True)
    wczesniej = U.cechy_zawodnika(seria, do_ts=1005)
    pozniej = U.cechy_zawodnika(seria, do_ts=99999)
    assert wczesniej["n_hist"] < pozniej["n_hist"]


def test_pozycja_wchodzi_jako_grupa():
    assert U.grupa_pozycji("ST") == "FWD"
    assert U.grupa_pozycji("RCB") == "DEF"
    assert U.grupa_pozycji("LCM") == "MID"
    assert U.grupa_pozycji("G") == "GK"
    assert U.grupa_pozycji(None) == "NIE"


def test_offset_minut_skaluje_lambde():
    """λ ma być proporcjonalna do minut — na tym stoi cały model zawodniczy."""
    lib = {f"{i}:shots": _seria_zaw(n=20, tempo=2.0 + (i % 3))
           for i in range(120)}
    for k, v in lib.items():
        v["player_id"] = k.split(":")[0]
    wiersze = U.wiersze_zawodnicze(lib)["shots"]
    wagi = U.trenuj_rynek_zaw(wiersze)
    assert wagi is not None
    cechy = U.cechy_zawodnika(_seria_zaw(n=20, tempo=2.0), do_ts=99999)
    lam90 = U.lam_zaw(wagi, cechy, oczekiwane_minuty=90.0)
    lam45 = U.lam_zaw(wagi, cechy, oczekiwane_minuty=45.0)
    assert abs(lam45 / lam90 - 0.5) < 1e-6, "połowa minut = połowa zdarzeń"


def test_prognoza_zawodnika_daje_komplet_albo_nic():
    lib = {f"{i}:shots": _seria_zaw(n=20, tempo=1.5 + (i % 4) * 0.5)
           for i in range(120)}
    for k, v in lib.items():
        v["player_id"] = k.split(":")[0]
    wagi = {"rynki_zaw": U.trenuj_zawodnikow(lib)}
    assert "shots" in wagi["rynki_zaw"]
    seria = _seria_zaw(n=20, tempo=2.0)
    out = U.prognoza_zawodnika(wagi, seria, "shots", 1.5, "powyzej",
                               oczekiwane_minuty=80.0, do_ts=99999)
    # ⚑ POKRYCIE JEST STEMPLOWANE NAWET GDY WYŁĄCZONE (2026-08-24). `pkw`/`pkn`
    # dochodzą zawsze, `pokr`/`p_bez_pokrycia` dopiero gdy waga > 0 — dzięki
    # temu księga zbiera próbę do pomiaru, ZANIM cokolwiek włączymy.
    obowiazkowe = {"p", "lam", "r_nb", "odl", "min", "sciag"}
    # `p_sciag` — liczba przy dawnym ściąganiu λ (pomiar, 2026-09-15)
    dozwolone = obowiazkowe | {"pkw", "pkn", "pokr", "p_bez_pokrycia", "p_sciag"}
    assert obowiazkowe <= set(out) <= dozwolone
    assert "pokr" not in out, "waga zawodnicza jest zerowa — nie wolno mieszać"
    assert out["min"] == 80.0
    # rynek, którego wagi nie znają
    assert U.prognoza_zawodnika(wagi, seria, "tackles", 1.5, "powyzej") is None
    # seria bez historii
    assert U.prognoza_zawodnika(wagi, _seria_zaw(n=2), "shots", 1.5,
                                "powyzej") is None


def test_trening_obejmuje_oba_strumienie():
    """Jedna wersja modelu dla drużyn i zawodników — nie dwa światy."""
    mag = _magazyn(n=40)
    lib = {f"{i}:shots": _seria_zaw(n=20, tempo=1.5 + (i % 4) * 0.5)
           for i in range(120)}
    for k, v in lib.items():
        v["player_id"] = k.split(":")[0]
    wagi = U.trenuj(mag, lib=lib)
    assert wagi["wersja"] == U.WERSJA_MODELU_UCZONEGO
    assert "shots" in (wagi.get("rynki_zaw") or {})
    assert "zawodnicz" in U.zdanie_stanu(wagi)


# --- DRABINKI: druga liczba na obu szczeblach -----------------------------
#
# Drabinki mają WŁASNY rachunek (pokrycie Wilsona × mnożniki kontekstu), inny
# niż silnik zawodniczy i inny niż drużynowy. To dokładnie ta klasa różnic,
# która kosztowała najwięcej — więc i one dostają drugą liczbę do porównania.

def test_szczebel_drabinki_niesie_druga_liczbe():
    """Stempel musi przejść: szczebel → hero → rekord księgi."""
    import inspect

    from footstats.jobs import build_wc_fast as B
    from footstats.jobs import radar

    zr = inspect.getsource(radar)
    # 1. szczebel dostaje prognozę
    i = zr.index('szczebel = {')
    assert "prognoza_zawodnika" in zr[i:i + 2500], (
        "szczeble drabinki nie pytają modelu uczonego"
    )
    # 2. hero kopiuje ją ze szczebla i niesie następnik osobno
    j = zr.index('"p_final": p_final,')
    assert '"p_uczony"' in zr[j:j + 900], "hero gubi drugą liczbę szczebla"
    assert '"drugi_p_uczony"' in zr, "następnik bez drugiej liczby"

    # 3. oba rekordy księgi ją przenoszą
    zb = inspect.getsource(B)
    k = zb.index('"p_model": h.get("p_final") or 0.0,')
    assert '"p_uczony"' in zb[k:k + 700], "rekord hero gubi drugą liczbę"
    m = zb.index('"p_model": h["drugi_p"],')
    assert 'drugi_p_uczony' in zb[m:m + 700], (
        "rekord drugiego szczebla gubi drugą liczbę"
    )


def test_druga_liczba_drabinki_nie_wchodzi_do_oceny_karty():
    """Kolejność kart stoi na przewadze drabinki — model liczy OBOK."""
    import inspect

    from footstats.jobs import radar

    zr = inspect.getsource(radar)
    # sam rachunek oceny: od porównania szczebli do premii za okno ceny
    i = zr.index("if nast is not None and p_nast is not None:")
    j = zr.index("ocena += BONUS_OKNA_CENY")
    rachunek = zr[i:j]
    assert "p_uczony" not in rachunek, (
        "druga liczba weszła do oceny karty — najpierw pomiar, potem decyzje"
    )
    # ...i do progów wyboru szczebla
    assert "p_uczony" not in zr[zr.index("MIN_P_SZCZEBLA"):
                                zr.index("MIN_P_SZCZEBLA") + 400]


# --- SUMY MECZOWE: cel liczony wprost, nie splotem ------------------------
#
# Zmierzone 17.08 na 900 typach `match_*`: luka −10,2 pp → +1,5 pp,
# Brier 0,2232 → 0,2173. ⚑ ALE NIE NA KAŻDYM RYNKU — kartki i celne meczowe
# wychodzą GORZEJ (model tam zaniża), więc przełączanie musi patrzeć per rynek.

def _mecz_sum(ts, cor=6, cor_opp=4, dom=1, opp=99, ev=None):
    return {"t": ts, "e": ev if ev is not None else ts, "o": opp, "h": dom,
            "l": 17, "g": 2, "gp": 1,
            "s": {"cor": cor, "pos": 55}, "sp": {"cor": cor_opp, "pos": 45}}


def _mag_sum(n=30):
    """Gospodarz 10 (6 rożnych), gość 99 (4) — suma w meczu 10."""
    return {
        "10": {"m": [_mecz_sum(1000 + i, cor=6, cor_opp=4, dom=1, opp=99,
                               ev=5000 + i) for i in range(n)]},
        "99": {"m": [_mecz_sum(1000 + i, cor=4, cor_opp=6, dom=0, opp=10,
                               ev=5000 + i) for i in range(n)]},
    }


def test_suma_liczy_sie_z_obu_stron_meczu():
    mag = _mag_sum(n=20)
    wiersze = U.wiersze_sum(mag)["match_corners"]
    assert wiersze, "brak wierszy sumy"
    assert wiersze[-1]["y"] == 10.0, "6 + 4 = 10 rożnych w meczu"
    assert wiersze[-1]["gosp6"] == 6.0 and wiersze[-1]["gosc6"] == 4.0
    assert wiersze[-1]["suma6"] == 10.0


def test_mecz_liczony_RAZ_a_nie_dwa_razy():
    """⚑ Każdy mecz jest w magazynie z perspektywy OBU drużyn."""
    mag = _mag_sum(n=20)
    wiersze = U.wiersze_sum(mag)["match_corners"]
    ile_gospodarza = len([m for m in mag["10"]["m"]
                          if int(m.get("h") or 0) == 1])
    assert len(wiersze) <= ile_gospodarza, (
        "ta sama suma weszła do treningu podwójnie"
    )
    # kontrola: identyfikatory meczów bez powtórzeń
    assert len({w["t"] for w in wiersze}) == len(wiersze)


def test_suma_wymaga_historii_obu_druzyn():
    mag = _mag_sum(n=20)
    mag["99"]["m"] = mag["99"]["m"][:2]        # gość prawie bez historii
    assert not U.wiersze_sum(mag).get("match_corners")


def test_prognoza_sumy_bierze_lige_z_historii():
    """Średnia ligowa to najmocniejsza cecha tego modelu — nie wolno jej zgubić."""
    mag = _mag_sum(n=40)
    wagi = {"rynki_sum": {"match_corners": U.trenuj_rynek_sum(
        U.wiersze_sum(mag)["match_corners"] * 30)}}
    ctx = U.przygotuj_sumy(mag)
    assert ctx.get("liga_sr_sum"), "kontekst sum bez średnich ligowych"
    z_liga = U.prognoza_sumy(wagi, ctx, 10, 99, 1, "match_corners", 9.5,
                             "powyzej", do_ts=99999)
    bez_ligi = U.prognoza_sumy(wagi, ctx, 10, 99, None, "match_corners", 9.5,
                               "powyzej", do_ts=99999)
    assert z_liga is not None and bez_ligi is not None
    assert abs(z_liga["p"] - bez_ligi["p"]) < 1e-9, (
        "brak ligi ma być uzupełniony z historii gospodarza, nie medianą"
    )


def test_prognoza_sumy_milczy_bez_druzyny():
    mag = _mag_sum(n=40)
    wagi = {"rynki_sum": {"match_corners": U.trenuj_rynek_sum(
        U.wiersze_sum(mag)["match_corners"] * 30)}}
    ctx = U.przygotuj_sumy(mag)
    assert U.prognoza_sumy(wagi, ctx, 10, 777777, 1, "match_corners", 9.5,
                           "powyzej", do_ts=99999) is None
    assert U.prognoza_sumy({}, ctx, 10, 99, 1, "match_corners", 9.5,
                           "powyzej") is None


def test_trening_obejmuje_trzy_grupy_rynkow():
    """`trenuj` zawsze zwraca klucz sum, a stan raportuje trzy grupy osobno."""
    mag = _mag_sum(n=40)
    wagi = U.trenuj(mag)
    assert "rynki_sum" in wagi, "brak grupy sum w wyniku treningu"
    # ta próba jest za mała na wagi ŻADNEJ grupy (36 wierszy przy progu 500),
    # więc stan mówi wprost „BRAK WAG" — cisza znaczy „nie wiemy"
    assert "BRAK WAG" in U.zdanie_stanu(wagi)

    # gdy jedna grupa jest, a sum brak — musi to być widoczne osobno
    assert "ZERO sum meczowych" in U.zdanie_stanu({
        "wersja": "test", "trenowano_ts": 1,
        "rynki": {"team_corners": {"n": 900}},
    })

    # ...a przy wagach obu grup stan wymienia je osobno
    stan = U.zdanie_stanu({
        "wersja": "test", "trenowano_ts": 1,
        "rynki": {"team_corners": {"n": 900}},
        "rynki_sum": {"match_corners": {"n": 600}},
        "rynki_zaw": {"shots": {"n": 5000}},
    })
    assert "1 sum meczowych" in stan
    assert "1 drużynowych" in stan and "1 zawodniczych" in stan
    assert "ZERO" not in stan


# --- TRENING TYLKO NA ROZGRYWKACH, KTÓRE WYCENIAMY (2026-08-18) -------------

def test_trening_pomija_mecze_spoza_zakresu_druzynowego():
    """Magazyn trzyma 177 lig (backfill pyta o kluby z całego terminarza),
    a rynki drużynowe liczymy dla 21. Trening na obcym rozkładzie POGARSZA
    model — zmierzone na tym samym zbiorze testowym:

        cały magazyn (221 765 wierszy)  Brier 0,2287  margines −2,0 pp
        tylko zakres  (57 256 wierszy)  Brier 0,2279  margines −0,7 pp

    Mniejsza próba wygrywa na każdej mierze. Kto zdejmie ten filtr, musi
    najpierw powtórzyć ten pomiar.
    """
    from footstats import rozgrywki
    assert 17 in rozgrywki.PROFILE, "17 = Premier League, kotwica tego testu"
    OBCA = max(rozgrywki.PROFILE) + 10_000
    assert OBCA not in rozgrywki.PROFILE

    mag = _magazyn(n=20)                       # liga 17 — w zakresie
    assert U.wiersze_treningowe(mag)["team_corners"], "zakres ma dawać wiersze"

    # ta sama historia, ale rozgrywki spoza zakresu -> zero wierszy
    obcy = {tid: {"m": [{**m, "l": OBCA} for m in rec["m"]]}
            for tid, rec in mag.items()}
    assert not U.wiersze_treningowe(obcy).get("team_corners")

    # ...chyba że ktoś ŚWIADOMIE wyłączy filtr (do pomiarów, nie do produkcji)
    assert U.wiersze_treningowe(obcy, tylko_zakres=False)["team_corners"]


# --- ściąganie λ do linii: model za mocno ufa własnym odchyleniom ----------
#
# Zmierzone 23.08 na 3003 rozliczeniach: λ zawyżona o 13% tam, gdzie gramy
# „powyżej", zaniżona o 5% przy „poniżej" — w TYM SAMYM rynku i paśmie λ,
# 9 z 9 przypadków. Pełne liczby i odrzucone warianty: nota przy
# `SCIAGANIE_LAMBDY_DO_LINII`.

def test_sciaganie_przy_sile_jeden_nie_rusza_lambdy():
    """Przełącznik powrotu: 1,0 ma oddawać λ co do bitu, bez żadnej ścieżki.

    To jest warunek postawiony przy zatwierdzaniu — cofnięcie ma być zmianą
    jednej wartości, a nie rewertowaniem commita.
    """
    for lam_ in (0.4, 1.0, 5.5, 13.2):
        for linia in (0.5, 4.5, 12.5):
            assert U.lambda_do_wyceny(lam_, linia, sila=1.0) == lam_


def test_sciaganie_zbliza_lambde_do_linii_z_obu_stron():
    """Ściągamy odchylenie, nie kierunek — λ nie może przeskoczyć linii."""
    # λ powyżej linii — ma zejść, ale zostać powyżej
    assert 4.5 < U.lambda_do_wyceny(6.5, 4.5, sila=0.8) < 6.5
    # λ poniżej linii — ma podejść, ale zostać poniżej
    assert 2.0 < U.lambda_do_wyceny(2.0, 4.5, sila=0.8) < 4.5
    # dokładna arytmetyka: linia + w·(λ − linia)
    assert abs(U.lambda_do_wyceny(6.5, 4.5, sila=0.5) - 5.5) < 1e-9
    # λ nigdy nie schodzi do zera ani poniżej
    assert U.lambda_do_wyceny(0.01, 0.5, sila=0.0) > 0.0


def test_sciaganie_ciagnie_szanse_w_strone_ceny_symetrycznie():
    """Skutek na `p`: obie strony schodzą ku 50%, bo λ zbliża się do linii."""
    surowe_o = U.p_strony(7.0, 4.5, "powyzej")
    po_o = U.wycena(7.0, 4.5, "powyzej")["p"]
    assert po_o < surowe_o, 'powyzej przy wysokiej lambdzie ma zejsc'
    surowe_u = U.p_strony(2.0, 4.5, "ponizej")
    po_u = U.wycena(2.0, 4.5, "ponizej")["p"]
    assert po_u < surowe_u, 'ponizej przy niskiej lambdzie tez ma zejsc'


def test_wycena_stempluje_sile_i_zachowuje_surowa_lambde():
    """Bez stempla za dwa tygodnie nie da się odpowiedzieć „czy zadziałało".

    ⚑ `lam` i `odl` MUSZĄ zostać na surowej λ — `odl` niesie regułę zasięgu,
    a liczona po ściągnięciu zmalałaby o jedną piątą i po cichu rozluźniła
    bramę, czyli zmieniła podaż przy okazji zmiany kalibracji.
    """
    w = U.wycena(7.0, 4.5, "powyzej")
    assert w["sciag"] == U.SCIAGANIE_LAMBDY_DO_LINII
    assert w["lam"] == 7.0, "stempel ma nieść λ SUROWĄ, nie ściągniętą"
    assert w["odl"] == 2.5, "odległość liczona od surowej λ — brama zasięgu"
    assert U.w_zasiegu(w["lam"], 4.5), "ta sama λ, ta sama decyzja bramy"


def test_wycena_bez_lambdy_nie_zgaduje():
    assert U.wycena(None, 4.5, "powyzej") is None


def test_strony_sumuja_sie_do_jedynki_takze_po_sciagnieciu():
    """Jedna λ, dwie strony — ściąganie nie może tego złamać."""
    for lam_ in (1.2, 5.5, 11.0):
        for r in (None, 6.0):
            o = U.wycena(lam_, 4.5, "powyzej", r_nb=r)["p"]
            u = U.wycena(lam_, 4.5, "ponizej", r_nb=r)["p"]
            assert abs(o + u - 1.0) < 1e-3


def test_wycena_jest_jedyna_droga_do_szansy():
    """STRAŻNIK: nowa ścieżka wyceny ma iść przez `wycena`, albo nie istnieć.

    Drużyny, zawodnicy i sumy liczyły to samo w trzech miejscach oddalonych
    o setki linii. Ten układ kosztował nas już dwa ciche rozjazdy
    (`ujemna_po_korekcie` z dwoma wejściami, `kal_strony` bez stempla), więc
    tu jest zamknięty na klucz: `p_strony` wolno wołać wyłącznie z wnętrza
    `wycena`, gdzie λ jest ściągana.
    """
    import inspect
    zrodlo = inspect.getsource(U)
    wolania = [l.strip() for l in zrodlo.splitlines()
               if "p_strony(" in l and not l.strip().startswith(("#", "*", '"'))
               and "def p_strony" not in l]
    assert len(wolania) == 1, (
        "p_strony wołane poza `wycena` — ta ścieżka ominie ściąganie λ "
        f"i stempel `sciag`: {wolania}")
    assert "lambda_do_wyceny" in wolania[0], wolania[0]


def test_wszystkie_trzy_strumienie_stempluja_sciagniecie():
    """Drużyny, zawodnicy i sumy — komplet, bo brak stempla to cichy fałsz.

    Nie sprawdzam tu liczb, tylko że KAŻDA ścieżka przechodzi przez wspólną
    wycenę. Dopisanie czwartego strumienia bez stempla ma ten test wywalić.
    """
    import inspect
    for nazwa in ("prognoza", "prognoza_zawodnika", "prognoza_sumy"):
        src = inspect.getsource(getattr(U, nazwa))
        assert "wycena(" in src, f"{nazwa} nie idzie przez wspólną wycenę"


def test_prognoza_sumy_daje_komplet_albo_nic():
    """SUMY MECZOWE — KONTRAKT PÓL, którego pozostałe testy sum nie sprawdzają.

    Sumy mają już testy (liga z historii, brak drużyny, brak wag), ale żaden
    nie pilnuje ZESTAWU zwracanych pól — a to on gwarantuje, że stempel
    dojedzie do księgi. Drużyny i zawodnicy taki test mają; ta ścieżka go nie
    miała i przy wdrażaniu ściągania λ (23.08) trzeba było weryfikować ją
    ręcznie na produkcyjnych wagach.
    """
    mag = _mag_sum(n=40)
    # wierszy z jednego fixture jest za mało na regresję — ten sam zabieg
    # co w `test_prognoza_sumy_bierze_lige_z_historii`
    wagi = {"rynki_sum": {"match_corners": U.trenuj_rynek_sum(
        U.wiersze_sum(mag)["match_corners"] * 30)}}
    rynek = "match_corners"
    ctx = U.przygotuj_sumy(mag)

    out = U.prognoza_sumy(wagi, ctx, 10, 99, None, rynek, 9.5, "powyzej",
                          do_ts=99999)
    assert set(out) == {"p", "lam", "r_nb", "odl", "sciag"}
    assert out["sciag"] == U.SCIAGANIE_LAMBDY_DO_LINII

    # obie strony jednej λ nadal sumują się do jedynki
    pod = U.prognoza_sumy(wagi, ctx, 10, 99, None, rynek, 9.5, "ponizej",
                          do_ts=99999)
    assert abs(out["p"] + pod["p"] - 1.0) < 1e-3

    # brak wag / nieznany rynek / brak kontekstu = cisza, nie zgadywanie
    assert U.prognoza_sumy(None, ctx, 10, 99, None, rynek, 9.5, "powyzej") is None
    assert U.prognoza_sumy(wagi, ctx, 10, 99, None, "nie_ma_takiego", 9.5,
                           "powyzej") is None
    assert U.prognoza_sumy(wagi, {}, 10, 99, None, rynek, 9.5, "powyzej") is None


# --- POKRYCIE LINII (2026-08-24) -------------------------------------------
#
# Wskazanie właściciela: model liczy ŚREDNIE, a miarą pewności jest to, ile
# razy drużyna faktycznie przekroczyła TĘ linię — i ile jej rywal DOPUSZCZA.
# Zmierzone przed wpięciem: pokrycie rywala bije model (AUC 0,517 vs 0,515),
# Brier mieszanki −2,09% out-of-sample. Szczegóły przy `WAGA_POKRYCIA`.

def test_pokrycie_liczy_czestosc_przekroczen():
    hist = [{"t": i, "s": {"cor": v}} for i, v in enumerate([6, 3, 7, 5, 2])]
    assert U.pokrycie_linii(hist, "cor", 4.5) == 0.6      # 6, 7, 5 > 4,5
    assert U.pokrycie_linii(hist, "cor", 9.5) == 0.0


def test_pokrycie_rywala_czyta_koncesje():
    """`wlasne=False` bierze stronę RYWALA tamtych meczów — ile DOPUSZCZAŁ."""
    hist = [{"t": i, "s": {"cor": 0}, "sp": {"cor": v}}
            for i, v in enumerate([8, 6, 9, 5, 7])]
    assert U.pokrycie_linii(hist, "cor", 4.5, wlasne=False) == 1.0
    assert U.pokrycie_linii(hist, "cor", 4.5, wlasne=True) == 0.0


def test_pokrycie_milczy_gdy_za_malo_historii():
    """Cisza znaczy „nie wiemy", nie „zero" — inaczej model dostałby po cichu
    wartość zastępczą i nikt by tego nie zauważył."""
    hist = [{"t": i, "s": {"cor": 6}} for i in range(3)]
    assert U.pokrycie_linii(hist, "cor", 4.5) is None
    assert U.pokrycie_linii([], "cor", 4.5) is None


def test_mieszanka_zachowuje_sume_stron():
    """p(powyżej) + p(poniżej) = 1 także po zmieszaniu z pokryciem.

    Gdyby mieszanka psuła tę sumę, obie strony tej samej linii deklarowałyby
    szanse, które się nie domykają — a na tym stoi cała wycena."""
    for p, pw, pr in ((0.60, 0.60, 1.00), (0.35, 0.20, 0.40), (0.80, 0.90, 0.70)):
        gora, _ = U.zmieszaj_z_pokryciem(p, pw, pr, "powyzej")
        dol, _ = U.zmieszaj_z_pokryciem(1 - p, pw, pr, "ponizej")
        assert abs(gora + dol - 1.0) < 1e-9


def test_waga_zero_wylacza_mieszanke():
    """Powrót jedną wartością — warunek postawiony przy wpinaniu."""
    assert U.zmieszaj_z_pokryciem(0.6, 0.9, 0.9, "powyzej", waga=0.0) == (0.6, None)


def test_brak_pokrycia_nie_rusza_szansy():
    assert U.zmieszaj_z_pokryciem(0.6, None, None, "powyzej") == (0.6, None)


def test_jedno_pokrycie_wystarczy():
    """Gdy rywal jest nieznany, własne pokrycie i tak wchodzi — połowa sygnału
    jest lepsza niż żadna."""
    p, pokr = U.zmieszaj_z_pokryciem(0.5, 1.0, None, "powyzej")
    assert pokr == 1.0 and p > 0.5


def test_mianownik_pokrycia_liczy_tylko_mecze_z_danymi():
    """⚑ Karta pokazuje „w 8 z 10 ostatnich". Gdy źródło nie podało statystyki
    w części meczów, mianownik MUSI zmaleć — inaczej pokazalibyśmy klientowi
    zdanie nieprawdziwe."""
    hist = [{"t": 1, "s": {"cor": 6}}, {"t": 2, "s": {}},
            {"t": 3, "s": {"cor": 7}}, {"t": 4, "s": {"cor": 2}},
            {"t": 5, "s": {"cor": 5}}, {"t": 6, "s": {"cor": 1}}]
    assert U.meczow_w_pokryciu(hist, "cor") == 5          # mecz nr 2 bez danych
    assert U.pokrycie_linii(hist, "cor", 4.5) == 3 / 5    # 6, 7, 5


def test_mianownik_i_pokrycie_licza_z_tego_samego_okna():
    """Licznik i mianownik nie mogą się rozjechać — jedno źródło wartości."""
    hist = [{"t": i, "s": {"cor": i}} for i in range(1, 21)]
    assert U.meczow_w_pokryciu(hist, "cor") == U.OKNO_POKRYCIA
    assert U.pokrycie_linii(hist, "cor", 15.5) == 5 / 10   # 16..20 z ostatnich 10


# --- POKRYCIE U ZAWODNIKÓW (2026-08-24, wpięte ale WYŁĄCZONE) --------------
#
# ⚑ Helper nazwany `_seria_pokrycia`, NIE `_seria_zaw` — ta druga już istnieje
# w tym pliku i ma inną sygnaturę. Kolizja nazw wywróciła pięć cudzych testów
# przy pierwszym podejściu.

def _seria_pokrycia(counts, minuty=None, czasy=None):
    n = len(counts)
    return {"counts": list(counts),
            "minutes": list(minuty or [90.0] * n),
            "timestamps": list(czasy or [1000 + i for i in range(n)])}


def test_pokrycie_zawodnika_liczy_przekroczenia():
    s = _seria_pokrycia([3, 1, 4, 2, 5, 0])
    assert U.pokrycie_zawodnika(s, 2.5, do_ts=99999) == 3 / 6      # 3, 4, 5


def test_pokrycie_zawodnika_pomija_mecze_bez_gry():
    """⚑ Dwadzieścia minut na boisku to inny zakład niż pełne 90. Mecz poniżej
    progu minut nie może zaniżać pokrycia, bo myliliśmy by „słaby zawodnik"
    z „mało grał"."""
    s = _seria_pokrycia([3, 0, 4, 0, 5, 4, 6],
                        minuty=[90, 5, 90, 8, 90, 90, 90])
    assert U.meczow_w_pokryciu_zaw(s, do_ts=99999) == 5            # dwa odpadają
    assert U.pokrycie_zawodnika(s, 2.5, do_ts=99999) == 1.0        # 3, 4, 5, 4, 6


def test_pokrycie_zawodnika_nie_zaglada_w_przyszlosc():
    """Mecz późniejszy niż `do_ts` nie może wpłynąć na pokrycie — wyciek
    z przyszłości daje świetny pomiar i bezużyteczny model."""
    s = _seria_pokrycia([1, 1, 1, 1, 1, 9],
                        czasy=[10, 20, 30, 40, 50, 60])
    assert U.pokrycie_zawodnika(s, 4.5, do_ts=55) == 0.0           # dziewiątki nie widać
    assert U.pokrycie_zawodnika(s, 4.5, do_ts=99) == 1 / 6         # teraz widać


def test_pokrycie_zawodnika_milczy_przy_krotkiej_historii():
    assert U.pokrycie_zawodnika(_seria_pokrycia([3, 4]), 2.5, do_ts=99999) is None
    assert U.pokrycie_zawodnika(None, 2.5) is None


def test_pokrycie_zawodnicze_jest_WYLACZONE_do_czasu_pomiaru():
    """⚑ U drużyn pokrycie WŁASNE nie porządkowało nic (AUC 0,499) — cały
    sygnał niósł rywal, którego zawodnicy nie mają. Waga zostaje na zerze,
    dopóki pomiar nie pokaże >= 2% poprawy out-of-sample."""
    assert U.WAGA_POKRYCIA_ZAW == 0.0
    assert U.zmieszaj_z_pokryciem(0.6, 0.9, None, "powyzej",
                                  waga=U.WAGA_POKRYCIA_ZAW) == (0.6, None)


# --- 5. DLACZEGO model nie policzył (2026-09-11) ---------------------------
#
# Na produkcji 27 z 61 typów stojących na stronie wracało na stary rachunek ze
# stemplem `stary_bez_pokrycia`, a te same typy policzone lokalnie na kopii
# magazynu wychodziły bez problemu (Werder `team_corners` p=0,73). Licznik
# mówił TYLKO „bez pokrycia", a to może znaczyć cztery różne rzeczy i cztery
# różne naprawy. Stąd `powod_braku`: jedno słowo do rentgenu, liczone dopiero
# wtedy, gdy prognozy nie ma.

def _wagi_dla(mag, rynek="team_corners"):
    # ×30, bo `trenuj_rynek` nie tyka rynku poniżej MIN_WIERSZY_RYNKU — tak
    # samo robią testy prognozy wyżej
    return {"rynki": {rynek: U.trenuj_rynek(
        U.wiersze_treningowe(mag)[rynek] * 30)}}


def test_powod_braku_rozpoznaje_pusty_magazyn():
    mag = _magazyn(n=20)
    ctx = U.przygotuj_sumy(mag)
    # drużyny 777 nie ma w magazynie w ogóle
    assert U.powod_braku(_wagi_dla(mag), ctx, 777, "team_corners",
                         99, 1, 17) == "druzyny_nie_ma_w_magazynie"


def test_powod_braku_rozpoznaje_krotka_historie():
    mag = _magazyn(n=2)
    ctx = U.przygotuj_sumy(mag)
    powod = U.powod_braku({"rynki": {"team_corners": {"w": {}, "log": []}}},
                          ctx, 10, "team_corners", 99, 1, 17)
    assert powod.startswith("historia_"), powod
    assert powod.endswith(f"_z_{U.MIN_HISTORII}")


def test_powod_braku_rozpoznaje_nietrenowany_rynek():
    mag = _magazyn(n=20)
    ctx = U.przygotuj_sumy(mag)
    assert U.powod_braku({"rynki": {}}, ctx, 10, "team_corners",
                         99, 1, 17) == "rynek_nietrenowany"
    assert U.powod_braku(None, ctx, 10, "team_corners") == "brak_wag"
    assert U.powod_braku({"rynki": {"team_corners": {}}}, {}, 10,
                         "team_corners") == "brak_kontekstu"


def test_powod_braku_rozpoznaje_brak_samej_statystyki():
    """Historia JEST, ale źródło nie podało tej statystyki — inna naprawa."""
    mag = _magazyn(n=20)
    for m in mag["10"]["m"]:
        m["s"].pop("cor", None)
    ctx = U.przygotuj_sumy(mag)
    powod = U.powod_braku({"rynki": {"team_corners": {"w": {}, "log": []}}},
                          ctx, 10, "team_corners", 99, 1, 17)
    assert powod == "brak_statystyki_cor", powod


def test_powod_braku_milczy_gdy_prognoza_jest_mozliwa():
    """Gdy wszystko jest na miejscu, powód to „inne" — a nie fałszywy alarm."""
    mag = _magazyn(n=40)
    ctx = U.przygotuj(mag)
    wagi = _wagi_dla(mag)
    assert U.prognoza(wagi, ctx, 10, "team_corners", 99, 1, 1, 5.5,
                      "powyzej") is not None
    assert U.powod_braku(wagi, ctx, 10, "team_corners", 99, 1, 1) == "inne"


def test_powod_braku_sumy_wskazuje_ktora_druzyne():
    mag = _magazyn(n=20)
    ctx = U.przygotuj_sumy(mag)
    wagi = {"rynki_sum": {"match_corners": {"w": {}, "log": []}}}
    powod = U.powod_braku_sumy(wagi, ctx, 10, 777, "match_corners")
    assert powod == "nie_ma_w_magazynie_gosc", powod
    powod = U.powod_braku_sumy(wagi, ctx, 888, 777, "match_corners")
    assert powod == "nie_ma_w_magazynie_gospodarz_gosc", powod
