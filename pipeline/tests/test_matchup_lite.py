"""Testy matchup-lite (strony boiska ze statshub)."""

from footstats.model import matchup_lite as ml


def _opp(market, positions, per90):
    return ml.OppPlayer(market_code=market, positions=tuple(positions), per90=per90)


def test_side_and_mirror():
    assert ml.side_of("RW") == "R"
    assert ml.side_of("LCB") == "L"
    assert ml.side_of("CAM") == "C"
    assert ml.mirror("L") == "R"
    assert ml.mirror("C") == "C"


def test_dominant_side_mode_and_tie():
    assert ml.dominant_side(["RW", "RW", "RM", "ST"]) == "R"
    assert ml.dominant_side(["LW", "RW"]) == "C"  # remis -> brak sygnału
    assert ml.dominant_side([]) == "C"


def test_fouls_won_boost_against_fouling_defender():
    """Skrzydłowy R gra na obrońcę L, który fauluje 2x częściej niż inni."""
    opp = [
        _opp("fouls_committed", ["LB", "LB", "LB"], 3.0),   # faulujący po stronie
        _opp("fouls_committed", ["RB", "RB"], 1.0),
        _opp("fouls_committed", ["RCB", "RCB"], 1.0),
    ]
    f, opis = ml.matchup_lite_factor("fouls_won", ["RW", "RW", "RW"], opp)
    assert f > 1.0
    assert f <= ml.CAP[1]
    assert "częściej" in opis


def test_no_signal_for_central_player_or_missing_data():
    opp = [_opp("fouls_committed", ["LB"], 2.0)]
    assert ml.matchup_lite_factor("fouls_won", ["ST", "ST"], opp) == (1.0, "")
    # za mało zawodników rywala (min 2 w puli)
    assert ml.matchup_lite_factor("fouls_won", ["RW", "RW"], opp) == (1.0, "")
    # rynek bez logiki stron
    assert ml.matchup_lite_factor("shots", ["RW", "RW"], opp) == (1.0, "")


def test_fouls_committed_only_for_defenders():
    opp = [
        _opp("fouls_won", ["LW", "LW"], 3.0),
        _opp("fouls_won", ["RW", "RW"], 1.0),
        _opp("fouls_won", ["ST"], 1.0),
    ]
    # obrońca RB gra na często faulowanego LW rywala -> więcej fauli
    f, _ = ml.matchup_lite_factor("fouls_committed", ["RB", "RB", "RB"], opp)
    assert f > 1.0
    # pomocnik ofensywny — brak sygnału
    assert ml.matchup_lite_factor("fouls_committed", ["CAM", "CAM"], opp) == (1.0, "")


def test_factor_capped_low():
    opp = [
        _opp("fouls_committed", ["LB", "LB"], 0.1),  # prawie nie fauluje
        _opp("fouls_committed", ["RB", "RB"], 4.0),
        _opp("fouls_committed", ["RCB"], 4.0),
    ]
    f, _ = ml.matchup_lite_factor("fouls_won", ["RW", "RW"], opp)
    assert ml.CAP[0] <= f < 1.0
