# -*- coding: utf-8 -*-
"""Rynki drużynowe ściągane do średniej ligi z siłą DOBRANĄ POMIAREM.

Ścieżka drużynowa ma własny prior — średnią ligi — i do 13.08 ściągała do niej
z siłą 4,0 dla wszystkich rynków naraz. Zmierzone na banku ligowym (1677
meczów, walidacja czasowa) NA GÓRZE ROZKŁADU, czyli tam, gdzie powstają typy:

    rynek     deklarowało   realnie    luka       po naprawie
    corners      71,2%       52,3%   -18,9 pp    -7,6  (siła 15)
    sot          80,1%       68,8%   -11,4 pp    -3,8  (siła 15)
    gole         57,8%       46,3%   -11,5 pp    -4,1  (siła 15)
    shots        82,9%       72,5%   -10,4 pp    -1,3  (siła 15)
    fouls        72,4%       66,7%    -5,7 pp    -1,0  (siła  8)
    kartki       70,9%       66,7%    -4,2 pp    -0,7  (siła  8)

⚑ To była większość luki −12 pp, którą produkt niósł od tygodni.

Ten test pilnuje trzech rzeczy: że siły są takie, jakie wyszły z pomiaru;
że rynki dyscyplinarne mają INNĄ siłę niż strzałowe (przy 15 przereagowują
na plus); i że rynki niezmierzone zostają na wartości sprzed zmiany.
"""

from __future__ import annotations

import pytest

from footstats.jobs import build_wc_fast as B


def _sila(mk: str) -> float:
    return B.SILA_PRIORU_DRUZYNY.get(mk, B.SILA_PRIORU_DRUZYNY_DOMYSLNA)


def test_rynki_dyscyplinarne_maja_slabsze_sciaganie():
    """Kartki i faule trafiają w zero przy 8; przy 15 przereagowują (+2,4/+4,0)."""
    assert _sila("team_cards") == 8.0
    assert _sila("team_fouls") == 8.0


def test_rynki_strzalowe_i_rozne_sciagane_mocniej():
    for mk in ("team_shots", "team_sot", "team_corners", "team_goals"):
        assert _sila(mk) == 15.0, mk


def test_kazdy_zmierzony_rynek_sciagany_mocniej_niz_bylo():
    """Pomiar wskazał 8-30 w każdym rynku; było 4,0 wszędzie."""
    for mk, sila in B.SILA_PRIORU_DRUZYNY.items():
        assert sila > B.SILA_PRIORU_DRUZYNY_DOMYSLNA, mk


def test_rynki_niezmierzone_zostaja_bez_zmian():
    """`match_*` i `wiecej_*` nie były mierzone — nie zmieniamy ich przez analogię.

    `match_corners` ma dziś lukę podobnego rzędu (hit 52% vs p 81%) i jest
    naturalnym kolejnym kandydatem, ale wymaga własnego pomiaru.
    """
    for mk in ("match_corners", "match_cards", "match_shots", "wiecej_shots"):
        assert _sila(mk) == 4.0, mk


def test_sciezka_zawodnicza_ma_wlasne_stale():
    """Dwie ścieżki, dwa priory — drużynowa ściąga do średniej LIGI,
    zawodnicza do średniej GRUPY zawodników. Pomiary są osobne i stałe też."""
    assert B.SILA_PRIORU_DRUZYNY is not B.SILA_PRIORU_RYNKU
    assert B.SILA_PRIORU_DRUZYNY_DOMYSLNA != B.SILA_PRIORU_DOMYSLNA


def test_mocniejszy_prior_obniza_prognoze_przy_wysokiej_historii():
    """Sedno naprawy, policzone wprost na wzorze posteriora.

    Drużyna z historią 7 rożnych przy średniej ligi 5,0 i próbie 20 meczów:
    przy sile 4 dostaje 6,67, przy 15 już 6,14 — bliżej tego, co realnie padnie.
    """
    lg_mean, historia, ess = 5.0, 7.0, 20.0
    lam_stare = (lg_mean * 4.0 + historia * ess) / (4.0 + ess)
    lam_nowe = (lg_mean * 15.0 + historia * ess) / (15.0 + ess)
    assert lam_stare == pytest.approx(6.667, abs=0.01)
    assert lam_nowe == pytest.approx(6.143, abs=0.01)
    assert lam_nowe < lam_stare
