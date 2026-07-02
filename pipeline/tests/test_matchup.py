"""Testy silnika matchupów 'kto na kogo gra' (interfejs profili stylu)."""

from footstats.model import matchup
from footstats.model.matchup import OpponentStyle, PlayerStyle


def _opp(**kw):
    kw.setdefault("sample", 15)
    return OpponentStyle(**kw)


def test_defender_vs_dribbler_more_tackles():
    high = matchup.matchup_factor("tackles", PlayerStyle(position="D"), _opp(contests_pm=26.0))[0]
    low = matchup.matchup_factor("tackles", PlayerStyle(position="D"), _opp(contests_pm=10.0))[0]
    assert high > 1.05 and low < 0.95 and high > low


def test_defender_vs_dribbler_more_fouls():
    f = matchup.matchup_factor("fouls_committed", PlayerStyle(position="D"), _opp(contests_pm=26.0))[0]
    assert f > 1.02


def test_weak_1v1_defender_extra_fouls():
    weak = matchup.matchup_factor(
        "fouls_committed", PlayerStyle(position="D", is_weak_1v1=True), _opp(contests_pm=24.0))[0]
    solid = matchup.matchup_factor(
        "fouls_committed", PlayerStyle(position="D", is_weak_1v1=False), _opp(contests_pm=24.0))[0]
    assert weak > solid


def test_dribbler_wins_fouls():
    f, opis = matchup.matchup_factor(
        "fouls_won", PlayerStyle(position="F", is_dribbler=True), _opp(fouls_pm=15.0))
    assert f > 1.05 and opis is not None
    f2 = matchup.matchup_factor("fouls_won", PlayerStyle(position="F"), _opp())[0]
    assert f2 == 1.0


def test_holdup_striker_wins_fouls():
    f = matchup.matchup_factor(
        "fouls_won", PlayerStyle(position="F", is_holdup=True), _opp(duels_pm=52.0))[0]
    assert f > 1.03


def test_target_man_headers_vs_weak_aerial():
    strong = matchup.matchup_factor(
        "headed_shots", PlayerStyle(position="F", is_target_man=True), _opp(weak_aerial=13.0))[0]
    assert strong > 1.05
    neutral = matchup.matchup_factor("headed_shots", PlayerStyle(position="F"), _opp())[0]
    assert neutral == 1.0


def test_outside_box_vs_deep_block():
    deep = matchup.matchup_factor(
        "shots_outside_box", PlayerStyle(position="F"),
        _opp(outside_share_conceded=0.60, blocks_made_pm=5.0, possession=40.0))[0]
    assert deep > 1.05


def test_blocked_shots_vs_blocking_team():
    f = matchup.matchup_factor(
        "shots_blocked", PlayerStyle(position="F"),
        _opp(blocks_made_pm=6.0, outside_share_conceded=0.55, possession=42.0))[0]
    assert f > 1.05


def test_interceptions_vs_long_balls():
    f = matchup.matchup_factor(
        "interceptions", PlayerStyle(position="D"), _opp(long_balls_pm=80.0, contests_pm=18.0))[0]
    assert f > 1.03


def test_offsides_vs_high_line():
    f = matchup.matchup_factor(
        "offsides", PlayerStyle(position="F"), _opp(offsides_forced=4.0))[0]
    assert f > 1.05


def test_side_awareness_left_back_vs_right_winger():
    """Lewy obrońca vs mocna prawa flanka rywala → więcej odbiorów."""
    lb = matchup.matchup_factor(
        "tackles", PlayerStyle(position="D", detailed_position="LB"),
        _opp(contests_pm=18.0, right_threat_pm=14.0, left_threat_pm=4.0))[0]
    # ten sam obrońca, ale rywal atakuje głównie lewą (nie jego) stroną
    lb_safe = matchup.matchup_factor(
        "tackles", PlayerStyle(position="D", detailed_position="LB"),
        _opp(contests_pm=18.0, right_threat_pm=4.0, left_threat_pm=14.0))[0]
    assert lb > lb_safe


def test_favourite_vs_deep_block_shots():
    f_shots = matchup.matchup_factor(
        "shots", PlayerStyle(position="F"),
        _opp(outside_share_conceded=0.58, blocks_made_pm=5.0, possession=40.0),
        is_favourite=True)[0]
    assert f_shots > 1.03


def test_setpiece_taker_shots():
    f = matchup.matchup_factor("shots", PlayerStyle(position="M", takes_setpieces=True), _opp())[0]
    assert f > 1.05


def test_team_fouls_vs_dribblers():
    f = matchup.matchup_factor("team_fouls", PlayerStyle(position="T"), _opp(contests_pm=26.0))[0]
    assert f > 1.03


def test_team_cards_two_aggressive():
    f = matchup.matchup_factor("team_cards", PlayerStyle(position="T"), _opp(cards_pm=2.8))[0]
    assert f > 1.03


def test_capped():
    f = matchup.matchup_factor(
        "tackles", PlayerStyle(position="D"), _opp(contests_pm=100.0, duels_pm=100.0))[0]
    assert f <= matchup.CAP_MATCHUP[1]


def test_small_sample_neutral():
    f = matchup.matchup_factor("tackles", PlayerStyle(position="D"), _opp(sample=0, contests_pm=26.0))[0]
    assert abs(f - 1.0) < 0.05


def test_attacker_market_ignores_defensive_matchup():
    f = matchup.matchup_factor("shots", PlayerStyle(position="F"), _opp(contests_pm=26.0))[0]
    assert f == 1.0


def test_player_style_side_parsing():
    assert PlayerStyle(detailed_position="LB").side == "L"
    assert PlayerStyle(detailed_position="RW").side == "R"
    assert PlayerStyle(detailed_position="CM").side is None


def test_classifiers():
    assert matchup.is_dribbler(3.0) and not matchup.is_dribbler(1.0)
    assert matchup.is_target_man(190, 2.0) and not matchup.is_target_man(175, 2.0)
    assert matchup.is_weak_1v1(1.5) and not matchup.is_weak_1v1(0.5)
    assert matchup.takes_setpieces(0.6) and not matchup.takes_setpieces(0.1)
