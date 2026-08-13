# -*- coding: utf-8 -*-
"""Prior ściąga zawodnika do GRUPY, a nie do niego samego.

`model/counts.py` obiecuje w nagłówku: „prior pochodzi z grupy porównawczej —
zawodnik z małą próbą jest ściągany do średniej grupy". Do 13.08
`group_prior_from_context` wpisywała tam ŚREDNIĄ TEGO SAMEGO ZAWODNIKA, więc
prior nie ściągał do niczego zewnętrznego.

Skutek był mierzalny: bez ściągania do populacji wysoka estymata zostaje
wysoka, a typy powstają właśnie tam, gdzie liczba wyszła za wysoko. Zmierzone
na 1284 obserwacjach na rynek (walidacja czasowa, średnia grupy z INNYCH
zawodników): bias na górnych 20% rozkładu spadł z 1,09-1,24 do 0,95-1,07,
a Brier poprawił się o 2,5-7,8%.

Pełny pomiar: docs/pomiar-skad-luka-deklaracji.md.
"""

from __future__ import annotations

import pytest

from footstats.jobs import build_wc_fast


class _Trend:
    def __init__(self, counts, minutes, market_code="shots",
                 league_average=None):
        self.counts = counts
        self.minutes = minutes
        self.market_code = market_code
        self.league_average = league_average


def _grupa(**pary):
    """Mapa rynek -> (średnia, liczebność) w wygodnej formie."""
    srednie = {k: v[0] for k, v in pary.items()}
    licz = {k: v[1] for k, v in pary.items()}
    return srednie, licz


# --- średnia grupy ---

def test_srednie_grupowe_wazy_minutami_nie_zawodnikami():
    """Zawodnik z jednym meczem nie może ważyć tyle, co ten z dziesięcioma."""
    duzo = _Trend(counts=[1.0] * 10, minutes=[90.0] * 10)
    malo = _Trend(counts=[10.0], minutes=[90.0])
    sr = build_wc_fast.srednie_grupowe([duzo, malo])
    # 10 zdarzeń na 10 meczów + 10 na 1 mecz = 20 zdarzeń / 11 ekspozycji
    assert sr["shots"] == pytest.approx(20.0 / 11.0)


def test_srednie_grupowe_pomija_mecze_bez_minut():
    tr = _Trend(counts=[3.0, 5.0], minutes=[90.0, 0.0])
    assert build_wc_fast.srednie_grupowe([tr])["shots"] == pytest.approx(3.0)


def test_srednie_grupowe_rozdziela_rynki():
    a = _Trend(counts=[4.0], minutes=[90.0], market_code="shots")
    b = _Trend(counts=[1.0], minutes=[90.0], market_code="tackles")
    sr = build_wc_fast.srednie_grupowe([a, b])
    assert sr["shots"] == pytest.approx(4.0)
    assert sr["tackles"] == pytest.approx(1.0)


# --- prior ---

def test_prior_bierze_srednia_grupy_a_nie_zawodnika():
    """Sedno naprawy: snajper z 5 strzałami dostaje prior grupy, nie swój."""
    tr = _Trend(counts=[5.0] * 10, minutes=[90.0] * 10)
    srednie, licz = _grupa(shots=(2.0, 30))
    prior = build_wc_fast.group_prior_from_context(tr, srednie, licz)
    assert prior.mean_per90 == pytest.approx(2.0), (
        "prior ma ściągać do grupy; przy własnej średniej wyszłoby 5,0 "
        "i zawodnik nie byłby ściągany do niczego"
    )


def test_mala_grupa_wraca_do_historii_zawodnika():
    """Lepiej nie ściągać wcale niż do średniej z kilku przypadkowych osób."""
    tr = _Trend(counts=[5.0] * 10, minutes=[90.0] * 10)
    srednie, licz = _grupa(shots=(2.0, build_wc_fast.MIN_GRUPY_DO_PRIORU - 1))
    prior = build_wc_fast.group_prior_from_context(tr, srednie, licz)
    assert prior.mean_per90 == pytest.approx(5.0)


def test_brak_mapy_grup_zachowuje_stare_zachowanie():
    """Ścieżki bez policzonej grupy (MŚ, testy) mają działać jak dotąd."""
    tr = _Trend(counts=[3.0, 3.0], minutes=[90.0, 90.0])
    assert build_wc_fast.group_prior_from_context(tr).mean_per90 == pytest.approx(3.0)


def test_rynek_spoza_mapy_nie_wywraca_prioru():
    tr = _Trend(counts=[3.0], minutes=[90.0], market_code="offsides")
    srednie, licz = _grupa(shots=(2.0, 40))
    prior = build_wc_fast.group_prior_from_context(tr, srednie, licz)
    assert prior.mean_per90 == pytest.approx(3.0)


def test_jednostki_per90_takze_przy_grupie():
    """Fallback na historię zawodnika dalej liczy NA 90 MINUT, nie na mecz."""
    tr = _Trend(counts=[2.0, 2.0], minutes=[45.0, 45.0])
    assert build_wc_fast.group_prior_from_context(tr).mean_per90 == pytest.approx(4.0)


def test_sila_prioru_domyslna_dla_wiekszosci_rynkow():
    """Siła 5,0 jest zmierzona i dla większości rynków optymalna.

    1284 obserwacje, walidacja czasowa: `shots` ma przy 5,0 bias 0,97,
    `sot` 0,99. Zmiana wymaga własnego pomiaru per rynek.
    """
    tr = _Trend(counts=[2.0], minutes=[90.0])
    srednie, licz = _grupa(shots=(2.0, 40))
    assert build_wc_fast.group_prior_from_context(
        tr, srednie, licz).pseudo_matches == 5.0


# --- siła ściągania zależna od rynku ---

def test_faule_sciagane_mocniej_bo_historia_ich_nie_przewiduje():
    """Historia fauli tłumaczy 8% następnego meczu (korelacja 0,282).

    Przy sile 5,0 model deklarował ~51% na „powyżej 1,5 faula" przy realnych
    25,8%. Pomiar (1283 obserwacje): pseudo 25 daje Brier 0,2304 i bias 0,98,
    wobec 0,2361 i 1,09 przy pięciu.
    """
    tr = _Trend(counts=[3.0] * 10, minutes=[90.0] * 10,
                market_code="fouls_committed")
    srednie, licz = _grupa(fouls_committed=(1.2, 40))
    prior = build_wc_fast.group_prior_from_context(tr, srednie, licz)
    assert prior.pseudo_matches == 25.0
    assert prior.mean_per90 == pytest.approx(1.2)


def test_mocniejsze_sciaganie_tylko_gdy_JEST_do_czego():
    """Bez grupy silniejszy prior ściągałby zawodnika do niego samego.

    Przy fallbacku na własną historię `mean_per90` to średnia tego zawodnika,
    więc podnoszenie siły nic nie zmienia — poza tym, że wygląda, jakby coś
    robiło. Zostaje wartość domyślna.
    """
    tr = _Trend(counts=[3.0] * 10, minutes=[90.0] * 10,
                market_code="fouls_committed")
    assert build_wc_fast.group_prior_from_context(tr).pseudo_matches == 5.0
    srednie, licz = _grupa(fouls_committed=(1.2, 3))   # grupa za mała
    assert build_wc_fast.group_prior_from_context(
        tr, srednie, licz).pseudo_matches == 5.0


def test_pozostale_rynki_bez_zmiany_sily():
    """⚑ Zmieniamy JEDEN rynek, nie wszystkie „dla porządku".

    Przy `fouls_won` (2) i `tackles` (8) Brier poprawiał się o ułamek, ale
    bias się psuł: 1,01 -> 1,11 i 0,96 -> 0,90. Zmiana kompletu stałych
    pogorszyłaby trzy rynki, żeby poprawić jeden.
    """
    for mk in ("shots", "sot", "fouls_won", "tackles"):
        tr = _Trend(counts=[2.0], minutes=[90.0], market_code=mk)
        srednie, licz = {mk: 1.5}, {mk: 40}
        assert build_wc_fast.group_prior_from_context(
            tr, srednie, licz).pseudo_matches == 5.0, mk


def test_podloga_dziala_takze_dla_grupy():
    tr = _Trend(counts=[0.0], minutes=[90.0])
    srednie, licz = _grupa(shots=(0.0, 40))
    prior = build_wc_fast.group_prior_from_context(tr, srednie, licz)
    assert prior.mean_per90 == pytest.approx(0.15)
