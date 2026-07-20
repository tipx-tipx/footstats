"""Rozliczanie multi-liga: świeże trendy z feedu statshub + fallback banku
dla strzałów, gdy 365Scores nie zna rozgrywek (globalne propsy)."""

import time

from footstats.jobs import rozliczanie
from footstats.sources import scores365, statshub


def _mock_supa(monkeypatch, store: dict) -> None:
    monkeypatch.setattr(rozliczanie.supa, "get_key", lambda k: store.get(k))
    monkeypatch.setattr(
        rozliczanie.supa, "put_key", lambda k, v: store.__setitem__(k, v)
    )


def _rec_zawodniczy(**kw):
    r = {
        "mecz_id": 15999001, "mecz": "Egzotic FC – Nieznani FC",
        "kickoff_ts": int(time.time()) - 4 * 3600,
        "podmiot_id": 777, "podmiot": "Jan Testowy", "podmiot_typ": "zawodnik",
        "rynek_kod": "shots", "rynek": "Strzały",
        "linia": 1.5, "strona": "powyzej", "kurs": 1.8, "p_model": 0.6,
        "sugestia": False, "wynik": None, "opublikowano_ts": 1,
    }
    r.update(kw)
    return r


def _przygotuj(monkeypatch, rec, trendy=None):
    store = {"typy_log": {rozliczanie._klucz(rec): rec}}
    _mock_supa(monkeypatch, store)
    # 365 nie zna meczu (liga bez comp365): gid None dla wszystkich rozgrywek
    monkeypatch.setattr(
        scores365, "finished_games_by_competition", lambda comp_id=None: []
    )
    monkeypatch.setattr(
        statshub, "fetch_event_trends", lambda mids: trendy or []
    )
    monkeypatch.setattr(
        rozliczanie, "_snapshot_zamkniecia", lambda *a, **k: None
    )
    return store


def test_shots_rozliczone_ze_swiezych_trendow(monkeypatch):
    rec = _rec_zawodniczy()
    trend = statshub.StatshubTrend(
        player_id=777, player_name="Jan Testowy", position="M",
        team_id=1, team_name="Egzotic FC", opponent_id=2,
        opponent_name="Nieznani FC", is_home=True,
        market_code="shots", line=1.5, in_predicted_lineup=False,
        league_average=None, opponent_average=None,
        opponent_rank=None, total_ranks=None,
        counts=[3.0, 1.0], minutes=[88.0, 90.0],
        timestamps=[rec["kickoff_ts"], rec["kickoff_ts"] - 7 * 86400],
    )
    store = _przygotuj(monkeypatch, rec, trendy=[trend])
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] == "wygrany"        # 3 strzały > linia 1.5
    assert wynik["faktyczna"] == 3.0


def test_bez_trendow_czeka_potem_zwrot(monkeypatch):
    # świeży mecz bez danych: czeka; po terminie zamyka się jako zwrot
    rec = _rec_zawodniczy()
    store = _przygotuj(monkeypatch, rec, trendy=[])
    rozliczanie.rozlicz([], [])
    assert list(store["typy_log"].values())[0]["wynik"] is None

    rec2 = _rec_zawodniczy(kickoff_ts=int(time.time()) - 3 * 86400)
    store2 = _przygotuj(monkeypatch, rec2, trendy=[])
    rozliczanie.rozlicz([], [])
    wynik2 = list(store2["typy_log"].values())[0]
    assert wynik2["wynik"] == "zwrot"
    assert wynik2["powod"] == "brak danych źródła"


def test_dolewka_nie_pyta_o_stare_i_druzynowe(monkeypatch):
    pytane = []

    def _fet(mids):
        pytane.append(list(mids))
        return []

    now = int(time.time())
    log = {
        "a": _rec_zawodniczy(mecz_id=1, kickoff_ts=now - 4 * 3600),
        "b": _rec_zawodniczy(mecz_id=2, kickoff_ts=now - 10 * 86400),  # po terminie
        "c": _rec_zawodniczy(mecz_id=3, kickoff_ts=now - 4 * 3600,
                             podmiot_typ="druzyna", rynek_kod="team_goals"),
        "d": _rec_zawodniczy(mecz_id=4, kickoff_ts=now - 4 * 3600,
                             wynik="wygrany"),  # już rozliczony
    }
    monkeypatch.setattr(statshub, "fetch_event_trends", _fet)
    rozliczanie._dolej_swieze_trendy(log, {}, now)
    assert pytane == [[1]]
