"""Cecha `rywal` modelu zawodniczego: koncesja rywala PER MECZ, bez przecieku.

Do 14.09 cecha `opp` była jedną liczbą na całą serię (nadchodzący rywal ze
statshuba) przyklejaną w treningu do każdego historycznego meczu — model
uczył się jej ze szumu (wagi ≈ 0). Teraz trening dostaje rywala KAŻDEGO meczu
z `game_opponent_ids`, a produkcja nadchodzącego z `opponent_id`, tą samą
funkcją `cechy_zawodnika`.
"""
import math

from footstats.model import uczony as U

DZIEN = 86_400
T0 = 1_700_000_000


def _seria(pid, rywale, counts, poz="ST", mk="fouls_won", start=T0, minuty=90.0):
    n = len(counts)
    return {
        "player_id": pid, "market_code": mk, "position": poz[0],
        "counts": [float(c) for c in counts], "minutes": [minuty] * n,
        "timestamps": [start + 7 * DZIEN * i for i in range(n)],
        "started": [True] * n, "game_positions": [poz] * n,
        "game_opponent_ids": list(rywale),
        "league_average": None, "opponent_average": None, "is_home": True,
    }


def _bank():
    """Rywal 500 dopuszcza napastnikom 3 faule/mecz, rywal 600 — 1 faul/mecz,
    reszta ligi — 2. Sześciu zawodników, po 12 meczów, rywale na zmianę."""
    lib = {}
    for pid in range(1, 7):
        ryw = [500 if i % 3 == 0 else 600 if i % 3 == 1 else 700 for i in range(12)]
        cnt = [3.0 if r == 500 else 1.0 if r == 600 else 2.0 for r in ryw]
        lib[f"{pid}:fouls_won"] = _seria(pid, ryw, cnt)
    return lib


def test_tabela_i_koncesja_wzgledem_normy():
    tab = U.tabela_rywali(_bank())
    t_po = T0 + 7 * DZIEN * 12          # po wszystkich meczach
    k500 = U.koncesja_rywala(tab, 500, "fouls_won", "FWD", t_po)
    k600 = U.koncesja_rywala(tab, 600, "fouls_won", "FWD", t_po)
    assert k500 is not None and k600 is not None
    assert k500 > 1.3 and k600 < 0.7 and abs(k500 / k600 - 3.0) < 0.05
    # inna grupa pozycji / rynek / nieznany rywal → brak profilu, nie zero
    assert U.koncesja_rywala(tab, 500, "fouls_won", "DEF", t_po) is None
    assert U.koncesja_rywala(tab, 500, "shots", "FWD", t_po) is None
    assert U.koncesja_rywala(tab, 999, "fouls_won", "FWD", t_po) is None
    assert U.koncesja_rywala(None, 500, "fouls_won", "FWD", t_po) is None


def test_koncesja_nie_zaglada_w_przyszlosc_i_wymaga_proby():
    tab = U.tabela_rywali(_bank())
    # przed czwartym meczem rywala 500 (mecze 0, 3, 6, 9 → czwarty to i=9)
    t_przed = T0 + 7 * DZIEN * 9
    assert U.koncesja_rywala(tab, 500, "fouls_won", "FWD", t_przed) is None
    t_po4 = T0 + 7 * DZIEN * 9 + 5 * 3600     # 5 h po gwizdku czwartego
    assert U.koncesja_rywala(tab, 500, "fouls_won", "FWD", t_po4) is not None
    # dokładnie w godzinie meczu (tolerancja 4 h) — ten mecz NIE wchodzi
    assert U.koncesja_rywala(tab, 500, "fouls_won", "FWD", T0 + 7 * DZIEN * 9 + 3600) is None


def test_okno_liczy_ostatnie_mecze_rywala():
    """Rywal zmienił styl: 8 meczów po 1 faulu, potem 10 po 3 — okno 10 widzi
    głównie nowe; okno 100 miesza."""
    lib = {}
    for pid in range(1, 4):
        cnt = [1.0] * 8 + [3.0] * 10
        lib[f"{pid}:fouls_won"] = _seria(pid, [500] * 18, cnt)
        lib[f"{pid + 10}:fouls_won"] = _seria(pid + 10, [700] * 18, [2.0] * 18)
    tab = U.tabela_rywali(lib)
    t = T0 + 7 * DZIEN * 18
    assert U.koncesja_rywala(tab, 500, "fouls_won", "FWD", t, okno=10) > \
        U.koncesja_rywala(tab, 500, "fouls_won", "FWD", t, okno=100)


def test_trening_uczy_sie_rywala_meczu_a_nie_serii():
    """Bank, w którym jedyne, co różni mecze, to rywal: waga `log_rywal` musi
    być wyraźnie dodatnia. Ze starą cechą (jedna liczba na serię) byłaby ≈ 0."""
    lib = {}
    for pid in range(1, 80):
        ryw = [500 if (i + pid) % 3 == 0 else 600 if (i + pid) % 3 == 1 else 700 for i in range(16)]
        cnt = [3.0 if r == 500 else 1.0 if r == 600 else 2.0 for r in ryw]
        lib[f"{pid}:fouls_won"] = _seria(pid, ryw, cnt)
    U_MIN = U.MIN_WIERSZY_RYNKU
    try:
        U.MIN_WIERSZY_RYNKU = 100
        wagi = U.trenuj_zawodnikow(lib)
    finally:
        U.MIN_WIERSZY_RYNKU = U_MIN
    w = wagi["fouls_won"]
    assert "rywal" in w["log"] and "opp" not in w["log"]
    beta = dict(zip(w["cechy"], w["beta"]))
    assert beta["log_rywal"] > 0.5, beta
    wiersze = U.wiersze_zawodnicze(lib)["fouls_won"]
    assert sum(1 for r in wiersze if r.get("rywal") is not None) > 0.8 * len(wiersze)


def test_prognoza_stempluje_rywala_i_p_bez_rywala():
    lib = {}
    for pid in range(1, 80):
        ryw = [500 if (i + pid) % 3 == 0 else 600 if (i + pid) % 3 == 1 else 700 for i in range(16)]
        cnt = [3.0 if r == 500 else 1.0 if r == 600 else 2.0 for r in ryw]
        lib[f"{pid}:fouls_won"] = _seria(pid, ryw, cnt)
    U_MIN = U.MIN_WIERSZY_RYNKU
    try:
        U.MIN_WIERSZY_RYNKU = 100
        wagi = {"rynki_zaw": U.trenuj_zawodnikow(lib)}
    finally:
        U.MIN_WIERSZY_RYNKU = U_MIN
    tab = U.tabela_rywali(lib)
    seria = {**lib["1:fouls_won"], "opponent_id": 500}
    t = T0 + 7 * DZIEN * 20
    z = U.prognoza_zawodnika(wagi, seria, "fouls_won", 1.5, "powyzej",
                             oczekiwane_minuty=90.0, do_ts=t, tabela_rywali=tab)
    assert z["rywal"] > 1.2 and z["p"] > z["p_bez_rywala"]
    seria["opponent_id"] = 600
    n = U.prognoza_zawodnika(wagi, seria, "fouls_won", 1.5, "powyzej",
                             oczekiwane_minuty=90.0, do_ts=t, tabela_rywali=tab)
    assert n["rywal"] < 0.8 and n["p"] < n["p_bez_rywala"]
    # bez tabeli: brak stempla, cecha neutralna (mediana)
    b = U.prognoza_zawodnika(wagi, seria, "fouls_won", 1.5, "powyzej",
                             oczekiwane_minuty=90.0, do_ts=t)
    assert "rywal" not in b and "p_bez_rywala" not in b
    assert abs(b["p"] - z["p_bez_rywala"]) < 1e-6


def test_stare_wagi_z_cecha_opp_dalej_licza():
    """Wagi sprzed zmiany (schemat z `opp`) muszą działać do nocnego treningu:
    brakująca cecha idzie w medianę, macierz ma tyle kolumn, ile wag."""
    wr = {"beta": [0.1, 0.0, 0.0, 0.5, -0.1, 0.05, 0.02, 0.0, 0.0, 0.2, 0.3],
          "cechy": ["const", "log_t3", "log_t6", "log_t12", "log_min6", "log_liga",
                    "log_opp", "dom", "udzial_startow", "poz_MID", "poz_FWD"],
          "log": ["t3", "t6", "t12", "min6", "liga", "opp"],
          "med": {"t3": 1.0, "t6": 1.0, "t12": 1.0, "min6": 80.0, "liga": 11.0, "opp": 11.0},
          "r_nb": None}
    seria = _seria(1, [500] * 12, [2.0] * 12)
    out = U.prognoza_zawodnika({"rynki_zaw": {"fouls_won": wr}}, seria, "fouls_won",
                               1.5, "powyzej", oczekiwane_minuty=90.0,
                               do_ts=T0 + 7 * DZIEN * 20)
    assert out and out["p"] is not None and "rywal" not in out
