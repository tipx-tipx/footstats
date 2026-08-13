# -*- coding: utf-8 -*-
"""Prior zawodniczy liczy się NA 90 MINUT, nie na mecz.

`group_prior_from_context` wypełnia `GroupPrior.mean_per90`. Do 13.08 wkładała
tam średnią liczbę zdarzeń NA MECZ — dla zawodnika grającego pełne mecze to
to samo, dla rotacyjnego prior był zaniżony proporcjonalnie do brakujących
minut (zmierzone: 0,83 przy 40 meczach po ~72 minuty).

Skutek dla posteriora był mały (~2,5%, bo prior waży ~14%), ale pomyłka
jednostek fałszuje KAŻDY następny pomiar priora — i przy niej mierzono już
dwa razy. Ten test pilnuje, żeby nie wróciła.
"""

from __future__ import annotations

import pytest

from footstats.jobs import build_wc_fast


class _Trend:
    """Minimalny trend: tyle, ile czyta `group_prior_from_context`."""

    def __init__(self, counts, minutes, league_average=None):
        self.counts = counts
        self.minutes = minutes
        self.league_average = league_average


def test_pelne_mecze_bez_zmiany():
    """Przy 90 minutach 'na mecz' i 'na 90 minut' to ta sama liczba."""
    tr = _Trend(counts=[2.0, 3.0, 1.0, 2.0], minutes=[90.0] * 4)
    prior = build_wc_fast.group_prior_from_context(tr)
    assert prior.mean_per90 == pytest.approx(2.0)


def test_zawodnik_rotacyjny_nie_jest_zanizany():
    """Zawodnik z 45 minutami i 2 zdarzeniami ma per-90 = 4, nie 2."""
    tr = _Trend(counts=[2.0, 2.0], minutes=[45.0, 45.0])
    prior = build_wc_fast.group_prior_from_context(tr)
    assert prior.mean_per90 == pytest.approx(4.0), (
        "prior musi liczyć na 90 minut — przy liczeniu 'na mecz' wyszłoby 2,0"
    )


def test_mieszana_historia_wazy_minutami():
    """Mecze liczą się proporcjonalnie do minut, a nie po równo.

    90' z 4 zdarzeniami i 30' z 1 zdarzeniem to 5 zdarzeń na 120 minut,
    czyli 3,75 na 90 — a nie średnia arytmetyczna z (4, 1) = 2,5.
    """
    tr = _Trend(counts=[4.0, 1.0], minutes=[90.0, 30.0])
    prior = build_wc_fast.group_prior_from_context(tr)
    assert prior.mean_per90 == pytest.approx(3.75)


def test_mecze_bez_minut_wypadaja():
    """Mecz, w którym zawodnik nie zagrał, nie ma prawa wejść do priora."""
    tr = _Trend(counts=[3.0, 0.0], minutes=[90.0, 0.0])
    prior = build_wc_fast.group_prior_from_context(tr)
    assert prior.mean_per90 == pytest.approx(3.0)


def test_brak_historii_schodzi_na_srednia_ligi():
    tr = _Trend(counts=[], minutes=[], league_average=1.4)
    prior = build_wc_fast.group_prior_from_context(tr)
    assert prior.mean_per90 == pytest.approx(1.4)


def test_podloga_chroni_przed_zerem():
    """Zero zdarzeń nie może dać priora 0,0 — posterior byłby zdegenerowany."""
    tr = _Trend(counts=[0.0, 0.0], minutes=[90.0, 90.0])
    prior = build_wc_fast.group_prior_from_context(tr)
    assert prior.mean_per90 == pytest.approx(0.15)


def test_sila_prioru_bez_zmian():
    """Naprawa dotyczy JEDNOSTEK, nie siły ściągania.

    Pomiar 13.08 (1284 obserwacje, walidacja czasowa): dzisiejsze 5,0 jest
    blisko optimum dla rynków zawodniczych — Brier 0,1782 przy pseudo=5
    wobec 0,1769 przy pseudo=2 i 0,1885 przy pseudo=20. Zmiana tej liczby
    wymaga własnego pomiaru, nie jest efektem ubocznym poprawki jednostek.
    """
    tr = _Trend(counts=[2.0], minutes=[90.0])
    assert build_wc_fast.group_prior_from_context(tr).pseudo_matches == 5.0
