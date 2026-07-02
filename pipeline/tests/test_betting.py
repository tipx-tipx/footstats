"""Testy silnika bettingowego."""

import numpy as np
import pytest

from footstats.model import betting, cards


def test_two_way_devig_removes_margin():
    # kursy 1.90/1.90 => po devigu 50/50
    p_over, p_under = betting.implied_probs_two_way(1.90, 1.90)
    assert abs(p_over - 0.5) < 0.005
    assert abs(p_over + p_under - 1.0) < 1e-6


def test_power_devig_favourite_longshot():
    """Metoda potęgowa powinna zdejmować więcej marży z outsidera niż z faworyta."""
    p_fav, p_dog = betting.implied_probs_two_way(1.25, 3.80)
    raw_fav, raw_dog = 1 / 1.25, 1 / 3.80
    # względna redukcja
    red_fav = (raw_fav - p_fav) / raw_fav
    red_dog = (raw_dog - p_dog) / raw_dog
    assert red_dog > red_fav
    assert abs(p_fav + p_dog - 1.0) < 1e-6


def test_one_sided_devig():
    p = betting.implied_prob_one_sided(2.0, margin=0.07)
    assert abs(p - 0.465) < 1e-6


def test_assess_finds_value_on_over():
    conf = betting.ConfidenceInputs(
        effective_matches=25.0,
        minutes_certainty=0.9,
        ci_width=0.08,
        context_magnitude=0.05,
        market_calibrated=True,
        is_rare_market=False,
    )
    # model: 58%, kurs 2.20 (implied ~45%) => wyraźny value na over
    res = betting.assess(0.58, over_odds=2.20, under_odds=1.66, conf_inputs=conf, lam=1.8)
    overs = [r for r in res if r.side == "powyzej"]
    assert len(overs) == 1
    a = overs[0]
    assert a.ev_pct > 20.0
    assert a.edge_pp > 8.0
    assert a.fair_odds == pytest.approx(1 / 0.58, abs=0.01)
    assert a.confidence in ("wysoka", "srednia")


def test_assess_rejects_low_ev():
    conf = betting.ConfidenceInputs(25.0, 0.9, 0.08, 0.05, True, False)
    # model zgodny z rynkiem => brak okazji
    res = betting.assess(0.50, over_odds=1.90, under_odds=1.90, conf_inputs=conf, lam=1.5)
    assert res == []


def test_assess_rejects_extreme_divergence():
    """Model 40 pp od rynku = najpewniej my nie wiemy czegoś, co wie rynek."""
    conf = betting.ConfidenceInputs(25.0, 0.9, 0.08, 0.05, True, False)
    res = betting.assess(0.90, over_odds=2.10, under_odds=1.70, conf_inputs=conf, lam=2.0)
    assert res == []


def test_rare_market_needs_bigger_edge():
    conf_rare = betting.ConfidenceInputs(25.0, 0.9, 0.08, 0.05, True, True)
    # EV ~5% — wystarcza normalnie, za mało dla rzadkiego rynku
    res = betting.assess(0.50, over_odds=2.10, under_odds=1.80, conf_inputs=conf_rare, lam=0.4)
    assert all(r.side != "powyzej" for r in res)


def test_confidence_score_components():
    strong = betting.confidence_score(
        betting.ConfidenceInputs(30.0, 1.0, 0.05, 0.02, True, False)
    )
    weak_sample = betting.confidence_score(
        betting.ConfidenceInputs(3.0, 1.0, 0.05, 0.02, True, False)
    )
    weak_minutes = betting.confidence_score(
        betting.ConfidenceInputs(30.0, 0.2, 0.05, 0.02, True, False)
    )
    wide_ci = betting.confidence_score(
        betting.ConfidenceInputs(30.0, 1.0, 0.30, 0.02, True, False)
    )
    assert strong > 70
    assert weak_sample < strong - 15
    assert weak_minutes < strong - 15
    assert wide_ci < strong - 20


def test_clv():
    assert betting.clv_pct(2.20, 2.00) == 10.0
    assert betting.clv_pct(1.80, 2.00) == -10.0


def test_yellow_card_model():
    q = cards.player_card_conversion(career_yellows=8, career_fouls=40)
    assert 0.15 < q < 0.30
    p_strict = cards.p_yellow_card(2.0, q, referee_cards_multiplier=1.3)
    p_lenient = cards.p_yellow_card(2.0, q, referee_cards_multiplier=0.7)
    assert p_strict > p_lenient
    assert 0.0 < p_lenient < p_strict < 1.0


def test_card_conversion_shrinks_small_sample():
    q_small = cards.player_card_conversion(career_yellows=3, career_fouls=5)
    # surowo 0.6, ale shrink do ~0.18 powinien mocno ściągnąć
    assert q_small < 0.30
