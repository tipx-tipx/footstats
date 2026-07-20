"""Pełne składy (sklady_xi): hierarchia statshub oficjalny -> przewidywany
-> backup Sofascore, wiarygodność sygnału per DRUŻYNA."""

import time

from footstats.jobs import build_wc_fast
from footstats.sources import sofascore, statshub


def _event(mid=101, h=1, a=2, confirmed=False, za_h=6):
    return {
        "id": mid, "homeTeamId": h, "awayTeamId": a,
        "lineupConfirmed": confirmed,
        "timeStartTimestamp": int(time.time()) + za_h * 3600,
    }


def _wylacz_sleep(monkeypatch):
    monkeypatch.setattr(build_wc_fast.time, "sleep", lambda s: None)


def test_predicted_statshub_pelne_xi(monkeypatch):
    _wylacz_sleep(monkeypatch)
    monkeypatch.setattr(
        statshub, "fetch_predicted_lineup",
        lambda mid: {"home": list(range(11)), "away": list(range(20, 31)),
                     "confirmed": False},
    )
    out = build_wc_fast.sklady_xi([_event()])
    v = out[101]
    assert v["zrodlo"] == "statshub przewidywany"
    assert not v["confirmed"]
    assert v["xi_by_team"][1] == set(range(11))
    assert v["xi_by_team"][2] == set(range(20, 31))


def test_oficjalny_przy_lineup_confirmed(monkeypatch):
    _wylacz_sleep(monkeypatch)
    monkeypatch.setattr(
        statshub, "fetch_team_lineup",
        lambda mid, tid: list(range(tid * 100, tid * 100 + 11)),
    )
    out = build_wc_fast.sklady_xi([_event(confirmed=True)])
    v = out[101]
    assert v["zrodlo"] == "statshub oficjalny"
    assert v["confirmed"]
    assert v["xi_by_team"][2] == set(range(200, 211))


def test_backup_sofascore_gdy_statshub_pusty(monkeypatch):
    _wylacz_sleep(monkeypatch)
    monkeypatch.setattr(
        statshub, "fetch_predicted_lineup",
        lambda mid: {"home": [], "away": [], "confirmed": False},
    )
    monkeypatch.setattr(
        sofascore, "fetch_lineups",
        lambda mid: {"confirmed": True,
                     "home": set(range(11)), "away": set(range(30, 41))},
    )
    out = build_wc_fast.sklady_xi([_event()])
    v = out[101]
    assert v["zrodlo"] == "sofascore"
    assert v["confirmed"]          # Sofascore zna potwierdzenie
    assert len(v["xi_by_team"]) == 2


def test_xi_tylko_jednej_druzyny_nie_udaje_obu(monkeypatch):
    # znamy XI gospodarzy, gości nie — sygnał tylko dla gospodarzy
    # (zawodnikom gości NIE wolno wpisać "poza składem")
    _wylacz_sleep(monkeypatch)
    monkeypatch.setattr(
        statshub, "fetch_predicted_lineup",
        lambda mid: {"home": list(range(11)), "away": [3, 4],
                     "confirmed": False},
    )
    monkeypatch.setattr(sofascore, "fetch_lineups", lambda mid: None)
    out = build_wc_fast.sklady_xi([_event()])
    assert list(out[101]["xi_by_team"].keys()) == [1]


def test_mecz_poza_oknem_pomijany(monkeypatch):
    _wylacz_sleep(monkeypatch)

    def _boom(mid):
        raise AssertionError("nie wolno pytać o mecz poza oknem")

    monkeypatch.setattr(statshub, "fetch_predicted_lineup", _boom)
    out = build_wc_fast.sklady_xi([_event(za_h=90), _event(mid=102, za_h=-2)])
    assert out == {}


def test_limit_zapytan_sofascore(monkeypatch):
    _wylacz_sleep(monkeypatch)
    monkeypatch.setattr(
        statshub, "fetch_predicted_lineup",
        lambda mid: {"home": [], "away": [], "confirmed": False},
    )
    licznik = {"n": 0}

    def _sofa(mid):
        licznik["n"] += 1
        return None

    monkeypatch.setattr(sofascore, "fetch_lineups", _sofa)
    monkeypatch.setattr(build_wc_fast, "LIMIT_SOFA_NA_CYKL", 3)
    events = [_event(mid=200 + i) for i in range(6)]
    build_wc_fast.sklady_xi(events)
    assert licznik["n"] == 3
