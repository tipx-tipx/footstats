"""Testy czystych funkcji workera Sofascore (jobs/sofa_worker.py)."""

from footstats.jobs import sofa_worker


def test_srednie_sezonu_mapuje_i_liczy():
    st = {
        "appearances": 32, "minutesPlayed": 1738,
        "totalShots": 64, "shotsOnTarget": 27,
        "shotsFromOutsideTheBox": 24,
        "fouls": 27, "wasFouled": 28, "offsides": 4,
        "tackles": 10, "interceptions": 5, "blockedShots": 17,
        "goals": 6,  # pole spoza mapy — ignorowane
    }
    agg = sofa_worker._srednie_sezonu(st)
    assert agg["mecze"] == 32 and agg["minuty"] == 1738
    assert agg["na_mecz"]["shots"] == 2.0
    assert agg["na_mecz"]["sot"] == 0.84
    assert agg["na_mecz"]["shots_outside_box"] == 0.75
    assert agg["na_mecz"]["fouls_committed"] == 0.84
    assert agg["na_mecz"]["fouls_won"] == 0.88
    assert agg["na_mecz"]["offsides"] == 0.12
    assert agg["na90"]["shots"] == 3.31
    assert "goals" not in agg["na_mecz"]


def test_srednie_sezonu_odrzuca_krotka_probe():
    # 2 mecze = agregat-szum (SEZON_MIN_MECZE=4)
    assert sofa_worker._srednie_sezonu(
        {"appearances": 2, "minutesPlayed": 180, "totalShots": 6}
    ) is None


def test_srednie_sezonu_bez_zadnego_rynku():
    # sezon bramkarski bez pol z mapy -> None, nie pusty rekord
    assert sofa_worker._srednie_sezonu(
        {"appearances": 30, "minutesPlayed": 2700, "saves": 88}
    ) is None


def test_staty_druzyny_mapuje_etykiety_sofascore():
    raw = {
        "Corner kicks": 7, "Fouls": 18, "Total shots": 20,
        "Shots on target": 6, "Yellow cards": 4, "Red cards": 1,
        "Ball possession": 52,
    }
    out = sofa_worker._staty_druzyny(raw)
    assert out == {
        "team_corners": 7.0, "team_fouls": 18.0, "team_shots": 20.0,
        "team_sot": 6.0, "team_cards": 5.0,
    }
