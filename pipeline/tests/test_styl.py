"""Testy banku/profili stylu (model/styl.py) i parserów 365 pod matchupy."""

from footstats.model import matchup, styl
from footstats.sources import scores365


def test_stat_pair_formaty():
    assert scores365._stat_pair("20/26 (77%)") == (20.0, 26.0)
    assert scores365._stat_pair("59%") == (59.0, None)
    assert scores365._stat_pair("3") == (3.0, None)
    assert scores365._stat_pair("90'") == (90.0, None)
    assert scores365._stat_pair(None) == (0.0, None)


def test_game_team_stats_parsuje_liste(monkeypatch):
    fixture = {
        "competitors": [
            {"id": 2378, "name": "Argentina"},
            {"id": 5032, "name": "Switzerland"},
        ],
        "statistics": [
            {"id": 10, "competitorId": 2378, "value": "59%"},
            {"id": 12, "competitorId": 2378, "value": "14"},
            {"id": 54, "competitorId": 2378, "value": "12/16 (75%)"},
            {"id": 56, "competitorId": 2378, "value": "20/34 (59%)"},
            {"id": 52, "competitorId": 2378, "value": "7/22 (32%)"},
            {"id": 1, "competitorId": 2378, "value": "2"},
            {"id": 2, "competitorId": 2378, "value": "1"},
            {"id": 147, "competitorId": 5032, "value": "6"},
            {"id": 3, "competitorId": 5032, "value": "9"},
            {"id": 6, "competitorId": 5032, "value": "3"},
        ],
    }
    monkeypatch.setattr(scores365, "_get", lambda url, **kw: fixture)
    scores365._team_stats_cache.clear()
    out = scores365.game_team_stats(123)
    arg = out["argentina"]
    assert arg["possession"] == 59.0
    assert arg["fouls"] == 14.0
    assert arg["dribbles_att"] == 16.0       # mianownik pary, nie licznik
    assert arg["aerial_won"] == 20.0 and arg["aerial_att"] == 34.0
    assert arg["crosses_att"] == 22.0
    assert arg["kartki"] == 3.0              # żółte + czerwone
    swi = out["switzerland"]
    assert swi["shots_outside"] == 6.0 and swi["shots"] == 9.0


def _bank_syntetyczny():
    """Bank: Norwegia gra fizycznie i z kontr, rywal X drybluje z lewej."""
    gry = {}
    zaw = {}
    for i in range(4):
        gid = str(100 + i)
        gry[gid] = {
            "ts": 1000 + i,
            "druzyny": {
                "norwegia": {
                    "fouls": 16, "kartki": 3, "corners": 4, "possession": 42,
                    "dribbles_att": 24, "duels_won": 55, "crosses_att": 22,
                    "longballs_att": 70, "aerial_won": 10, "aerial_att": 30,
                    "shots": 9, "shots_outside": 3, "shots_blocked": 2,
                    "offsides": 1,
                },
                "rywal": {
                    "fouls": 10, "kartki": 1, "corners": 6, "possession": 58,
                    "dribbles_att": 12, "duels_won": 40, "crosses_att": 10,
                    "longballs_att": 40, "aerial_won": 20, "aerial_att": 30,
                    "shots": 15, "shots_outside": 8, "shots_blocked": 5,
                    "offsides": 4,
                },
            },
        }
        zaw.setdefault("jan kowalski", {"druzyna": "norwegia", "gry": {}})[
            "gry"
        ][gid] = {
            "ts": 1000 + i, "min": 90, "dribbles_att": 4, "dribbled_past": 2,
            "aerial_won": 3, "aerial_att": 5, "ground_att": 8,
            "key_passes": 2, "crosses_att": 3,
        }
    shot = {
        "777": {
            "ts": 1000,
            "druzyny": {"55": {"shots": 12, "kontra": 4}},
            "stale": {"901": 3},
        },
    }
    return {
        "gry": gry, "zawodnicy": zaw, "shotmap": shot,
        "wzrost": {"901": 190},
    }


def test_opponent_style_agregaty():
    st = styl.StyleTurnieju(
        _bank_syntetyczny(),
        strony_zawodnikow={"jan kowalski": "L"},
        team_id_by_norm={"norwegia": 55},
    )
    opp = st.opponent("Norwegia")
    assert opp is not None
    assert opp.sample == 4
    assert opp.fouls_pm == 16
    assert opp.contests_pm == 24
    assert opp.possession == 42
    # weak_aerial = przegrane górą = att - won = 20
    assert opp.weak_aerial == 20
    # offsides_forced = spalone RYWALI Norwegii
    assert opp.offsides_forced == 4
    # bloki Norwegii = zablokowane strzały jej rywali
    assert opp.blocks_made_pm == 5
    # udział strzałów rywali zza pola: 8*4 / 15*4
    assert abs(opp.outside_share_conceded - 8 / 15) < 1e-9
    # kontry z shotmapy: 4/12
    assert abs(opp.fastbreak_share - 4 / 12) < 1e-9
    # zagrożenie lewą flanką: (4+3) na mecz od Kowalskiego
    assert abs(opp.left_threat_pm - 7.0) < 1e-9
    assert opp.right_threat_pm is None
    # brak profilu dla drużyny spoza banku
    assert st.opponent("Brazylia") is None


def test_player_style_klasyfikacja():
    st = styl.StyleTurnieju(
        _bank_syntetyczny(), strony_zawodnikow={}, team_id_by_norm={}
    )
    p = st.player("Jan Kowalski", "M", ["LM", "LM", "LW"], player_id_sh=901)
    assert p is not None
    assert p.detailed_position == "LM"
    assert p.side == "L"
    assert p.height == 190
    # 4 dryblingi / 90 min = 4.0 per90 >= 2.5
    assert p.is_dribbler
    # 2 dribbled_past per90 >= 1.3
    assert p.is_weak_1v1
    # wzrost 190 i 3 aerial_won per90 >= 1.5
    assert p.is_target_man
    # key_passes 2 per90 >= 1.5, pozycja M
    assert p.is_playmaker
    # stałe fragmenty: 3 strzały / 4 mecze = 0.75 >= 0.4
    assert p.takes_setpieces
    # zawodnik spoza banku -> None (engine spada na matchup-lite)
    assert st.player("Ktos Inny", "M", [], player_id_sh=1) is None


def test_pelny_matchup_z_profili():
    """Smoke: profile z banku wchodzą do matchup_factor i ruszają predykcję."""
    st = styl.StyleTurnieju(
        _bank_syntetyczny(),
        strony_zawodnikow={"jan kowalski": "L"},
        team_id_by_norm={"norwegia": 55},
    )
    opp = st.opponent("Norwegia")
    gracz = st.player("Jan Kowalski", "F", ["LW"], player_id_sh=901)
    # drybler przeciwko często faulującej Norwegii -> faule wywalczone w górę
    f, opis = matchup.matchup_factor("fouls_won", gracz, opp)
    assert f > 1.0
    assert opis
    assert f <= matchup.CAP_MATCHUP[1]
