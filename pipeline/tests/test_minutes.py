"""Testy modelu minut."""

from footstats.model import minutes as mm


def _regular_starter():
    return dict(
        recent_started=[True] * 8,
        recent_minutes=[90.0, 88.0, 90.0, 90.0, 85.0, 90.0, 90.0, 90.0],
        days_ago=[4.0, 11.0, 18.0, 25.0, 32.0, 39.0, 46.0, 53.0],
    )


def test_regular_starter_high_expected_minutes():
    m = mm.estimate_minutes(**_regular_starter())
    assert m.expected_minutes > 75
    assert m.p_start > 0.9
    assert m.certainty > 0.6


def test_rotation_player_uncertain():
    m = mm.estimate_minutes(
        recent_started=[True, False, False, True, False, False],
        recent_minutes=[75.0, 20.0, 0.0, 68.0, 25.0, 0.0],
        days_ago=[4.0, 11.0, 18.0, 25.0, 32.0, 39.0],
    )
    assert 20 < m.expected_minutes < 65
    assert m.certainty < 0.6


def test_official_lineup_locks_start():
    base = _regular_starter()
    official_in = mm.estimate_minutes(**base, official_started=True)
    official_out = mm.estimate_minutes(**base, official_started=False)
    assert official_in.p_start == 1.0
    assert official_in.expected_minutes > 80
    assert official_out.p_start == 0.0
    assert official_out.expected_minutes < 30
    assert official_in.certainty == 1.0


def test_injury_zeroes_everything():
    m = mm.estimate_minutes(**_regular_starter(), injured_or_suspended=True)
    assert m.expected_minutes == 0.0
    assert m.p_plays == 0.0


def test_mixture_p_over():
    m = mm.estimate_minutes(**_regular_starter())
    # sztuczna funkcja: P(over) proporcjonalna do minut
    p = mm.p_over_mixture(m, lambda mins: min(mins / 90.0, 1.0) * 0.6)
    assert 0.4 < p < 0.6


def test_mixture_lower_for_rotation_player():
    starter = mm.estimate_minutes(**_regular_starter())
    rot = mm.estimate_minutes(
        recent_started=[False, True, False, False, True, False],
        recent_minutes=[15.0, 70.0, 0.0, 20.0, 65.0, 10.0],
        days_ago=[4.0, 11.0, 18.0, 25.0, 32.0, 39.0],
    )
    f = lambda mins: min(mins / 90.0, 1.0) * 0.6
    assert mm.p_over_mixture(starter, f) > mm.p_over_mixture(rot, f)
