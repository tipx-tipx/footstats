"""Testy rdzenia probabilistycznego."""

import numpy as np
import pytest

from footstats.model import counts


def test_posterior_shrinks_small_sample_to_prior():
    """Zawodnik z 2 meczami gra prawie średnią grupy."""
    prior = counts.GroupPrior(mean_per90=2.0, pseudo_matches=10.0)
    post = counts.fit_posterior(
        counts=np.array([6.0, 5.0]),        # ekstremalne 5-6 strzałów
        minutes=np.array([90.0, 90.0]),
        days_ago=np.array([3.0, 10.0]),
        prior=prior,
    )
    # surowa średnia = 5.5/90, ale posterior powinien być znacznie bliżej 2.0
    assert 2.0 < post.mean_per90 < 3.0


def test_posterior_follows_data_with_large_sample():
    prior = counts.GroupPrior(mean_per90=1.0, pseudo_matches=6.0)
    n = 60
    post = counts.fit_posterior(
        counts=np.full(n, 3.0),
        minutes=np.full(n, 90.0),
        days_ago=np.linspace(1, 200, n),
        prior=prior,
    )
    assert 2.4 < post.mean_per90 < 3.1


def test_time_decay_weights_recent_more():
    prior = counts.GroupPrior(mean_per90=1.5, pseudo_matches=4.0)
    recent_hot = counts.fit_posterior(
        counts=np.array([4.0, 4.0, 0.0, 0.0]),
        minutes=np.full(4, 90.0),
        days_ago=np.array([5.0, 10.0, 300.0, 310.0]),  # świeże mecze gorące
        prior=prior,
    )
    recent_cold = counts.fit_posterior(
        counts=np.array([0.0, 0.0, 4.0, 4.0]),
        minutes=np.full(4, 90.0),
        days_ago=np.array([5.0, 10.0, 300.0, 310.0]),  # świeże mecze zimne
        prior=prior,
    )
    assert recent_hot.mean_per90 > recent_cold.mean_per90


def test_nb_predictive_is_overdispersed_for_small_sample():
    """Mała próba => rozkład predykcyjny szerszy niż Poisson o tej samej średniej."""
    prior = counts.GroupPrior(mean_per90=2.0, pseudo_matches=3.0)
    post = counts.fit_posterior(
        counts=np.array([2.0, 3.0]),
        minutes=np.array([90.0, 90.0]),
        days_ago=np.array([5.0, 12.0]),
        prior=prior,
    )
    pred = counts.predict_match(post, expected_minutes=90.0)
    # wariancja NB = lam * (1 + lam/alpha) > lam (wariancja Poissona)
    var_nb = pred.lam * (1.0 + pred.lam / post.alpha)
    assert var_nb > pred.lam * 1.05


def test_p_over_monotonic_in_line():
    prior = counts.GroupPrior(mean_per90=2.0, pseudo_matches=6.0)
    post = counts.fit_posterior(
        counts=np.array([2.0, 1.0, 3.0, 2.0]),
        minutes=np.full(4, 90.0),
        days_ago=np.array([4.0, 11.0, 18.0, 25.0]),
        prior=prior,
    )
    pred = counts.predict_match(post, 90.0)
    assert pred.p_over(0.5) > pred.p_over(1.5) > pred.p_over(2.5)
    assert abs(pred.p_over(1.5) + pred.p_under(1.5) - 1.0) < 1e-9


def test_p_over_scales_with_minutes():
    prior = counts.GroupPrior(mean_per90=2.0, pseudo_matches=6.0)
    post = counts.fit_posterior(
        counts=np.array([2.0, 2.0, 2.0]),
        minutes=np.full(3, 90.0),
        days_ago=np.array([4.0, 11.0, 18.0]),
        prior=prior,
    )
    p90 = counts.predict_match(post, 90.0).p_over(1.5)
    p60 = counts.predict_match(post, 60.0).p_over(1.5)
    p30 = counts.predict_match(post, 30.0).p_over(1.5)
    assert p90 > p60 > p30


def test_distribution_sums_to_one():
    prior = counts.GroupPrior(mean_per90=1.5, pseudo_matches=6.0)
    post = counts.fit_posterior(
        counts=np.array([1.0, 2.0]),
        minutes=np.array([90.0, 85.0]),
        days_ago=np.array([3.0, 9.0]),
        prior=prior,
    )
    dist = counts.predict_match(post, 88.0).distribution(max_k=10)
    assert abs(sum(dist) - 1.0) < 1e-6
    assert all(p >= 0 for p in dist)


def test_group_prior_estimation():
    rng = np.random.default_rng(42)
    rates = rng.gamma(shape=4.0, scale=0.5, size=200)  # średnia 2.0
    prior = counts.estimate_group_prior(rates)
    assert 1.7 < prior.mean_per90 < 2.3
    assert 2.0 <= prior.pseudo_matches <= 20.0


def test_credible_interval_narrows_with_data():
    prior = counts.GroupPrior(mean_per90=2.0, pseudo_matches=5.0)
    small = counts.fit_posterior(
        np.array([2.0, 2.0]), np.full(2, 90.0), np.array([5.0, 10.0]), prior
    )
    big = counts.fit_posterior(
        np.full(50, 2.0), np.full(50, 90.0), np.linspace(1, 150, 50), prior
    )
    lo_s, hi_s = counts.p_over_credible_interval(small, 90.0, 1.0, 1.5)
    lo_b, hi_b = counts.p_over_credible_interval(big, 90.0, 1.0, 1.5)
    assert (hi_b - lo_b) < (hi_s - lo_s)
