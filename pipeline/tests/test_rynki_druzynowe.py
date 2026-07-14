"""Testy rynków drużynowych: parser team-trends + rozliczanie z 365."""

import time

from footstats.jobs import rozliczanie
from footstats.sources import scores365, statshub


def test_fetch_team_trends_mapuje_stattypes(monkeypatch):
    fixture = {"data": [
        {
            "teamId": 4481, "teamName": "France", "opponentTeamName": "Spain",
            "eventId": 1, "homeTeamId": 4481, "statType": "totalShotsOnGoal",
            "line": 12.5, "oddsType": "over",
            "recentGames": [
                {"statValue": 22, "eventTimestamp": 100, "opponentName": "Morocco"},
                {"statValue": 9, "eventTimestamp": 90, "opponentName": "Brazil"},
            ],
            "bookmakers": [{"oddsValue": 1.85}, {"oddsValue": 1.9}],
        },
        {"teamId": 4481, "eventId": 1, "statType": "goals", "line": 1.5,
         "recentGames": []},   # goli nie modelujemy
        {"teamId": 4698, "teamName": "Spain", "opponentTeamName": "France",
         "eventId": 1, "homeTeamId": 4481, "statType": "cards", "line": 1.5,
         "recentGames": [{"statValue": 2, "eventTimestamp": 50}]},
    ]}
    monkeypatch.setattr(statshub, "_get", lambda url: fixture)
    tt = statshub.fetch_team_trends([1])
    assert len(tt) == 2                      # goals odfiltrowane
    fr = tt[0]
    assert fr.market_code == "team_shots" and fr.is_home
    assert fr.counts == [22.0, 9.0] and fr.ref_odds == [1.85, 1.9]
    assert tt[1].market_code == "team_cards" and not tt[1].is_home


def _mock_supa(monkeypatch, store: dict) -> None:
    monkeypatch.setattr(
        rozliczanie.supa, "get_key", lambda k: store.get(k)
    )
    monkeypatch.setattr(
        rozliczanie.supa, "put_key",
        lambda k, v: store.__setitem__(k, v),
    )


def _rec_druzynowy(**kw):
    r = {
        "mecz_id": 5, "mecz": "France – Spain",
        "kickoff_ts": int(time.time()) - 4 * 3600,
        "podmiot_id": 4481, "podmiot": "France",
        "rynek_kod": "team_fouls", "rynek": "Faule drużyny",
        "linia": 11.5, "strona": "powyzej", "kurs": 1.8, "p_model": 0.6,
        "sugestia": False, "wynik": None, "opublikowano_ts": 1,
    }
    r.update(kw)
    return r


def _przygotuj(monkeypatch, rec, aet=False, staty=None):
    store = {"typy_log": {rozliczanie._klucz(rec): rec}}
    _mock_supa(monkeypatch, store)
    monkeypatch.setattr(rozliczanie, "_gid_365", lambda r, c: 777)
    monkeypatch.setattr(scores365, "after_extra_time", lambda gid: aet)
    monkeypatch.setattr(
        scores365, "game_team_stats",
        lambda gid: staty if staty is not None else {
            "france": {"fouls": 14.0, "shots": 18.0},
            "spain": {"fouls": 9.0, "shots": 11.0},
        },
    )
    monkeypatch.setattr(
        rozliczanie, "_snapshot_zamkniecia", lambda *a, **k: None
    )
    monkeypatch.setattr(
        rozliczanie.scores365, "finished_games_by_competition", lambda *a: []
    )
    return store


def test_rozliczanie_team_fouls_wygrany(monkeypatch):
    rec = _rec_druzynowy()
    store = _przygotuj(monkeypatch, rec)
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] == "wygrany"        # 14 fauli > linia 11.5
    assert wynik["faktyczna"] == 14.0


def test_rozliczanie_team_dogrywka_czeka(monkeypatch):
    """Mecz z dogrywką: statystyki 365 obejmują 120 min — typ drużynowy
    NIE rozlicza się z nich (czeka; po terminie zamknie się jako zwrot)."""
    rec = _rec_druzynowy()
    store = _przygotuj(monkeypatch, rec, aet=True)
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] is None


def test_rozliczanie_team_zwrot_po_terminie(monkeypatch):
    rec = _rec_druzynowy(
        kickoff_ts=int(time.time()) - 3 * 86400   # dawno po terminie danych
    )
    store = _przygotuj(monkeypatch, rec, staty={})
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] == "zwrot"
    assert wynik["powod"] == "brak danych źródła"
