"""Historia zawodnika statshub jako ostatnie źródło rozliczenia (2026-09-13).

Typy zawodników w ligach spoza 365Scores szły po 7 dniach na „zwrot, brak
danych" (faule domykały się w ~60%). Walidacja na produkcji: 98% zgodności
wyniku zakładu z 365 na 144 rozliczonych typach.
"""

import time

from footstats.jobs import rozliczanie
from footstats.sources import statshub

from test_rozliczanie_multiliga import _przygotuj, _rec_zawodniczy


def _wiersz(mecz_id, minuty, **staty):
    return {"events": [{"id": mecz_id}],
            "player_statistics_event": [{"eventId": mecz_id,
                                         "minutesPlayed": minuty, **staty}]}


def _wynik_meczu(extra_time=False):
    return {"home_id": 1, "away_id": 2, "home_name": "A", "away_name": "B",
            "home_goals": 1, "away_goals": 0, "extra_time": extra_time}


def _ustaw(monkeypatch, rec, wiersze, extra_time=False):
    store = _przygotuj(monkeypatch, rec)
    monkeypatch.setattr(statshub, "fetch_event_result",
                        lambda eid: _wynik_meczu(extra_time))
    monkeypatch.setattr(statshub, "fetch_player_performance",
                        lambda pid, limit=20: wiersze)
    rozliczanie.rozlicz([], [])
    return list(store["typy_log"].values())[0]


def test_faule_poza_365_rozliczone_z_historii(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="fouls_committed", rynek="Faule", linia=0.5,
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _ustaw(monkeypatch, rec, [
        _wiersz(15999000, 90, fouls=3),                       # inny mecz
        _wiersz(rec["mecz_id"], 89, fouls=2, wasFouled=3),
    ])
    assert w["wynik"] == "wygrany" and w["faktyczna"] == 2.0


def test_zero_fauli_to_przegrany_nie_zwrot(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="fouls_won", linia=0.5,
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _ustaw(monkeypatch, rec, [_wiersz(rec["mecz_id"], 90, wasFouled=0)])
    assert w["wynik"] == "przegrany" and w["faktyczna"] == 0.0


def test_zero_minut_w_historii_to_nie_zagral(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="fouls_won", linia=0.5,
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _ustaw(monkeypatch, rec, [_wiersz(rec["mecz_id"], 0)])
    assert w["wynik"] == "zwrot" and w["powod"] == "nie zagrał"


def test_swiezy_pusty_wiersz_nie_zamyka_typu(monkeypatch):
    """Tuż po meczu wiersz bywa niewypełniony — a zwrot jest nieodwracalny."""
    rec = _rec_zawodniczy(rynek_kod="fouls_won", linia=0.5,
                          kickoff_ts=int(time.time()) - 3 * 3600)
    w = _ustaw(monkeypatch, rec, [_wiersz(rec["mecz_id"], None)])
    assert w["wynik"] is None


def test_dogrywka_nie_rozlicza_z_historii(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="fouls_committed", linia=0.5,
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _ustaw(monkeypatch, rec, [_wiersz(rec["mecz_id"], 120, fouls=2)],
               extra_time=True)
    assert w["wynik"] is None


def test_strzaly_poza_365_z_historii(monkeypatch):
    rec = _rec_zawodniczy(kickoff_ts=int(time.time()) - 8 * 3600)   # shots 1.5
    w = _ustaw(monkeypatch, rec, [
        _wiersz(rec["mecz_id"], 90, shots=1, onTargetScoringAttempt=0)])
    assert w["wynik"] == "przegrany" and w["faktyczna"] == 1.0


def test_rynek_niezwalidowany_nie_idzie_z_historii(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="offsides", linia=0.5,
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _ustaw(monkeypatch, rec, [_wiersz(rec["mecz_id"], 90, totalOffside=2)])
    assert w["wynik"] is None


def test_budzet_zapytan_na_przebieg(monkeypatch):
    pytania = []
    budzet, cache = [1], {}
    monkeypatch.setattr(statshub, "fetch_player_performance",
                        lambda pid, limit=20: pytania.append(pid) or [])
    rozliczanie._perf_w_meczu({"podmiot_id": 1, "mecz_id": 5}, cache, budzet)
    rozliczanie._perf_w_meczu({"podmiot_id": 1, "mecz_id": 6}, cache, budzet)
    rozliczanie._perf_w_meczu({"podmiot_id": 2, "mecz_id": 5}, cache, budzet)
    assert pytania == [1]
