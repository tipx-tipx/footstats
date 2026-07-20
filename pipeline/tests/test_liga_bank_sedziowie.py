"""Tryb ligowy: bank stylu i profil sędziów na rozgrywkach z profili.

Wersja ligowa różni się od MŚ trzema parametrami: lista comp365 zamiast
jednego turnieju, rozegrane eventy statshub zakresu drużynowego (shotmapy)
i OSOBNE klucze Supabase (styl klubów nie miesza się z reprezentacjami).
"""

import time

from footstats.jobs import build_wc_fast
from footstats.sources import scores365


def _mock_supa(monkeypatch, store: dict) -> None:
    monkeypatch.setattr(build_wc_fast.supa, "get_key", lambda k: store.get(k))
    monkeypatch.setattr(
        build_wc_fast.supa, "put_key", lambda k, v: store.__setitem__(k, v)
    )


def test_bank_stylu_liga_osobny_klucz_i_comp_ids(monkeypatch):
    store: dict = {}
    _mock_supa(monkeypatch, store)
    pytane_comp = []

    def _finished(comp_id=None):
        pytane_comp.append(comp_id)
        return [{"id": 900 + (comp_id or 0), "ts": int(time.time()) - 3600,
                 "home": "lech", "away": "legia"}]

    monkeypatch.setattr(scores365, "finished_games_by_competition", _finished)
    monkeypatch.setattr(
        scores365, "game_team_stats",
        lambda gid: {"lech": {"shots": 14.0}, "legia": {"shots": 9.0}},
    )
    monkeypatch.setattr(scores365, "game_player_match_stats", lambda gid: {})

    bank = build_wc_fast.aktualizuj_bank_stylu(
        set(), comp_ids=[153, 572], past_events=[], klucz="styl_bank_liga"
    )
    assert pytane_comp == [153, 572]          # pętla po rozgrywkach z profili
    assert "styl_bank_liga" in store           # zapis pod kluczem ligowym
    assert "styl_bank" not in store            # bank MŚ nietknięty
    assert len(bank["gry"]) == 2


def test_profil_sedziow_liga_cache_i_comp_ids(monkeypatch):
    store: dict = {}
    _mock_supa(monkeypatch, store)
    now = int(time.time())

    monkeypatch.setattr(
        scores365, "finished_games_by_competition",
        lambda comp_id=None: [
            {"id": 11, "ts": now - 86400, "home": "lech", "away": "legia"},
            {"id": 12, "ts": now - 2 * 86400, "home": "wisla", "away": "lech"},
        ],
    )
    monkeypatch.setattr(scores365, "game_referee", lambda gid: "Szymon Marciniak")
    monkeypatch.setattr(scores365, "after_extra_time", lambda gid: False)
    monkeypatch.setattr(
        scores365, "game_player_match_stats",
        lambda gid: {"a": {"fouls_committed": 14.0}, "b": {"fouls_committed": 12.0}},
    )
    monkeypatch.setattr(
        scores365, "scheduled_games_by_competition",
        lambda comp_id=None: [
            {"id": 77, "ts": now + 3600, "home": "lech", "away": "legia"},
        ],
    )
    events = [{"id": 501, "homeTeamId": 1, "awayTeamId": 2,
               "timeStartTimestamp": now + 3600}]
    team_name = {1: "Lech", 2: "Legia"}

    out = build_wc_fast.profil_sedziow(
        events, team_name, comp_ids=[153], cache_key="sedziowie_cache_liga"
    )
    assert "sedziowie_cache_liga" in store     # cache ligowy, nie MŚ
    assert "sedziowie_cache" not in store
    assert out[501]["sedzia"] == "Szymon Marciniak"
    assert out[501]["n"] == 2                  # obie gry z historii sędziego
