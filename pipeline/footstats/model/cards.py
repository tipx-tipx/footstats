"""Model kartek — rynek binarny modelowany WARSTWOWO przez faule.

Bezpośrednie częstości kartek to za mało zdarzeń na zawodnika. Zamiast tego:

    P(żółta) = 1 - exp(-lambda_fauli x q_zawodnika x m_sędziego)

gdzie:
  * lambda_fauli — przewidywane faule zawodnika w meczu (z modelu NB),
  * q_zawodnika  — indywidualna konwersja faul->kartka (shrinkowana do średniej ligi),
  * m_sędziego   — mnożnik surowości sędziego (kartki/faul vs liga).
"""

from __future__ import annotations

import numpy as np

# Średnia konwersja faul -> żółta kartka w top 5 ligach (~0.16-0.20)
LEAGUE_CARD_PER_FOUL = 0.18


def player_card_conversion(
    career_yellows: float,
    career_fouls: float,
    prior_strength: float = 25.0,
) -> float:
    """Konwersja faul->kartka zawodnika, ściągana do średniej ligi.

    prior_strength = 25 "wirtualnych fauli" — zawodnik z 10 faulami w próbie
    prawie w całości gra średnią ligową.
    """
    if career_fouls <= 0:
        return LEAGUE_CARD_PER_FOUL
    raw = career_yellows / career_fouls
    k = career_fouls / (career_fouls + prior_strength)
    q = LEAGUE_CARD_PER_FOUL + k * (raw - LEAGUE_CARD_PER_FOUL)
    return float(np.clip(q, 0.05, 0.45))


def p_yellow_card(
    lambda_fouls: float,
    card_conversion: float,
    referee_cards_multiplier: float = 1.0,
    extra_intensity: float = 1.0,
) -> float:
    """P(co najmniej jedna żółta) przy Poissonowskim strumieniu kartkogennych fauli.

    extra_intensity — korekta na derby / stawkę meczu (1.0 = neutralnie).
    """
    rate = lambda_fouls * card_conversion * referee_cards_multiplier * extra_intensity
    return float(1.0 - np.exp(-max(rate, 0.0)))
