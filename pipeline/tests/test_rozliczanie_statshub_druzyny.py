# -*- coding: utf-8 -*-
"""Zapasowe rozliczanie drużyn, sum i „kto więcej" ze statshub (2026-10-05).

Gdy 365 nie miało meczu, rynki drużynowe (poza golami), sumy meczowe i „kto
więcej" po 7 dniach szły na zwrot „brak danych" — 19–20.09 42 typy na meczach,
dla których statshub miał komplet. Kartki liczymy regułą Superbetu (żółta 1,
czerwona 2, wykluczenie za dwie żółte 3).
"""
import time

from footstats.jobs import rozliczanie as R
from footstats.sources import scores365, statshub

from test_rynki_druzynowe import _przygotuj, _rec_druzynowy

H, A = 4481, 4482


def _wiersz(mid, st, opp, dogrywka=False):
    return {"event": {"id": mid, "homeScoreOvertime": 1 if dogrywka else None,
                      "homeScorePenalties": None},
            "statistics": st, "opponentStatistics": opp}


def _bez_365(monkeypatch, wiersze, licznik=None):
    monkeypatch.setattr(R, "_gid_365", lambda r, c: None)

    def _perf(tid, limit=10):
        if licznik is not None:
            licznik.append(tid)
        return wiersze.get(tid, [])
    monkeypatch.setattr(statshub, "fetch_team_performance", _perf)


def _rozlicz(monkeypatch, rec, wiersze, licznik=None):
    store = _przygotuj(monkeypatch, rec)
    _bez_365(monkeypatch, wiersze, licznik)
    R.rozlicz([], [])
    return list(store["typy_log"].values())[0]


def test_kartki_wg_superbetu_z_licznikow_statshub():
    assert R.kartki_superbet_statshub({"yellowCards": 3}) == (3.0, 3.0)
    assert R.kartki_superbet_statshub({"yellowCards": 2, "redCards": None}) == (2.0, 2.0)
    assert R.kartki_superbet_statshub({"yellowCards": 2, "redCards": 1}) == (3.0, 4.0)
    assert R.kartki_superbet_statshub({}) is None


def test_druzynowy_rozliczony_ze_statshub_gdy_365_nie_zna_meczu(monkeypatch):
    rec = _rec_druzynowy(rynek_kod="team_corners", linia=4.5)
    w = _rozlicz(monkeypatch, rec, {H: [_wiersz(5, {"cornerKicks": 6}, {"cornerKicks": 2})]})
    assert w["wynik"] == "wygrany" and w["faktyczna"] == 6.0
    assert w["zrodlo_wyniku"] == "statshub"


def test_statshub_czeka_cztery_godziny_na_365(monkeypatch):
    rec = _rec_druzynowy(rynek_kod="team_corners", linia=4.5,
                         kickoff_ts=int(time.time()) - 3 * 3600)
    licz = []
    w = _rozlicz(monkeypatch, rec, {H: [_wiersz(5, {"cornerKicks": 6}, {})]}, licz)
    assert w["wynik"] is None and licz == []


def test_dogrywka_w_statshub_czeka(monkeypatch):
    rec = _rec_druzynowy(rynek_kod="team_corners", linia=4.5)
    w = _rozlicz(monkeypatch, rec, {H: [_wiersz(5, {"cornerKicks": 6}, {}, dogrywka=True)]})
    assert w["wynik"] is None


def test_dogrywka_wg_365_nie_pyta_statshub(monkeypatch):
    rec = _rec_druzynowy(rynek_kod="team_corners", linia=4.5)
    store = _przygotuj(monkeypatch, rec, aet=True)
    licz = []
    monkeypatch.setattr(statshub, "fetch_team_performance",
                        lambda tid, limit=10: licz.append(tid) or [])
    R.rozlicz([], [])
    assert list(store["typy_log"].values())[0]["wynik"] is None and licz == []


def test_kartki_druzyny_z_czerwona(monkeypatch):
    # Y=2, R=1 → u Superbetu 3 albo 4: linia 2,5 rozstrzygnięta, 3,5 nie
    st = {"yellowCards": 2, "redCards": 1}
    rec = _rec_druzynowy(rynek_kod="team_cards", linia=2.5)
    w = _rozlicz(monkeypatch, rec, {H: [_wiersz(5, st, {})]})
    assert w["wynik"] == "wygrany"
    rec = _rec_druzynowy(rynek_kod="team_cards", linia=3.5)
    w = _rozlicz(monkeypatch, rec, {H: [_wiersz(5, st, {})]})
    assert w["wynik"] is None


def test_suma_i_kto_wiecej_ze_statshub(monkeypatch):
    wiersze = {H: [_wiersz(5, {"totalShotsOnGoal": 12, "yellowCards": 1},
                           {"totalShotsOnGoal": 9, "yellowCards": 2})]}
    rec = _rec_druzynowy(rynek_kod="match_shots", linia=20.5)
    w = _rozlicz(monkeypatch, rec, wiersze)
    assert w["wynik"] == "wygrany" and w["faktyczna"] == 21.0
    rec = _rec_druzynowy(rynek_kod="wiecej_cards", linia=0.0, strona="gospodarz")
    w = _rozlicz(monkeypatch, rec, wiersze)
    assert w["wynik"] == "przegrany" and w["faktyczna"] == "1:2"
    assert w["zrodlo_wyniku"] == "statshub"


def test_suma_kartek_z_czerwona_tylko_gdy_jednoznaczna(monkeypatch):
    wiersze = {H: [_wiersz(5, {"yellowCards": 2, "redCards": 1}, {"yellowCards": 2})]}
    # suma 5 albo 6
    w = _rozlicz(monkeypatch, _rec_druzynowy(rynek_kod="match_cards", linia=4.5), wiersze)
    assert w["wynik"] == "wygrany"
    w = _rozlicz(monkeypatch, _rec_druzynowy(rynek_kod="match_cards", linia=5.5), wiersze)
    assert w["wynik"] is None


def test_brak_meczu_w_historii_czeka(monkeypatch):
    rec = _rec_druzynowy(rynek_kod="team_shots", linia=9.5)
    w = _rozlicz(monkeypatch, rec, {H: [_wiersz(999, {"totalShotsOnGoal": 15}, {})]})
    assert w["wynik"] is None and "zrodlo_wyniku" not in w


def test_jedna_historia_na_druzyne_w_przebiegu(monkeypatch):
    a = _rec_druzynowy(rynek_kod="team_shots", linia=9.5)
    b = _rec_druzynowy(rynek_kod="team_fouls", linia=11.5)
    store = _przygotuj(monkeypatch, a)
    store["typy_log"][R._klucz(b)] = b
    licz = []
    _bez_365(monkeypatch, {H: [_wiersz(5, {"totalShotsOnGoal": 15, "fouls": 10}, {})]}, licz)
    R.rozlicz([], [])
    wyn = {r["rynek_kod"]: r["wynik"] for r in store["typy_log"].values()}
    assert wyn == {"team_shots": "wygrany", "team_fouls": "przegrany"}
    assert licz == [H]


def test_kartki_365_wg_superbetu(monkeypatch):
    dane = {"competitors": [{"id": 1, "name": "Everton"}, {"id": 2, "name": "Ipswich"}],
            "statistics": [
                {"id": 1, "competitorId": 2, "value": "2"},
                {"id": 2, "competitorId": 2, "value": "1"},
                {"id": 1, "competitorId": 1, "value": "2"},
            ]}
    scores365._team_stats_cache.pop(4242, None)
    monkeypatch.setattr(scores365, "_get", lambda *a, **k: dane)
    try:
        st = scores365.game_team_stats(4242)
    finally:
        scores365._team_stats_cache.pop(4242, None)
    # Everton – Ipswich 05.10: 2 żółte + czerwona za drugą żółtą = 4 u Superbetu
    assert st["ipswich"]["kartki"] == 4.0 and st["everton"]["kartki"] == 2.0
