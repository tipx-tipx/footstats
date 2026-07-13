"""P0: MŚ 2026 nie jest w pełni neutralny turniej — USA/Meksyk/Kanada są
współgospodarzami. venue_context() musi aktywować efekt dom/wyjazd dla ich
meczów, a zostawić neutralny dla meczów dwóch niegospodarzy."""

from footstats.jobs.build_wc_fast import venue_context


def test_gospodarz_u_siebie_jest_home_i_nie_neutralny():
    is_home, neutral = venue_context("USA", "Wales", is_home_raw=False)
    assert is_home is True
    assert neutral is False


def test_rywal_gospodarza_jest_away_i_nie_neutralny():
    is_home, neutral = venue_context("Wales", "Mexico", is_home_raw=True)
    assert is_home is False
    assert neutral is False


def test_dwoch_niegospodarzy_zostaje_neutralne():
    is_home, neutral = venue_context("Poland", "Brazil", is_home_raw=True)
    assert is_home is True  # bez znaczenia — neutral_venue i tak wyłącza efekt
    assert neutral is True


def test_kanada_jako_rywal_tez_liczy_sie_jako_gospodarz():
    is_home, neutral = venue_context("Belgium", "Canada", is_home_raw=False)
    assert is_home is False
    assert neutral is False
