"""Silnik bettingowy — od prawdopodobieństwa modelu do rankingu okazji.

Kroki:
  1. devig — usunięcie marży bukmachera z kursów (metoda potęgowa; przy
     jednostronnym kwotowaniu odejmujemy szacowaną marżę rynku),
  2. fair odds = 1 / p_model,
  3. edge (pp) i wartość oczekiwana EV%,
  4. confidence 0-100 z komponentów (próba, pewność minut, szerokość CI,
     struktura czynników),
  5. risk — osobno od confidence (rzadkość zdarzenia, rotacja, definicje),
  6. rank_score do sortowania listy okazji.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize

# Typowa marża polskich bukmacherów na player props (do jednostronnych kwotowań).
DEFAULT_ONE_SIDED_MARGIN = 0.07


def implied_probs_two_way(over_odds: float, under_odds: float) -> tuple[float, float]:
    """Devig dwustronny metodą potęgową.

    Szukamy k takiego, że (1/over)^k + (1/under)^k = 1.
    Metoda potęgowa lepiej niż proporcjonalna oddaje favourite-longshot bias,
    który na propsach jest silny.
    """
    p_over_raw = 1.0 / over_odds
    p_under_raw = 1.0 / under_odds
    total = p_over_raw + p_under_raw
    if total <= 1.0:  # brak marży / kurs arbitrażowy — bierzemy wprost
        return p_over_raw, p_under_raw

    def overround(k: float) -> float:
        return p_over_raw**k + p_under_raw**k - 1.0

    try:
        k = optimize.brentq(overround, 1.0, 5.0, xtol=1e-10)
        return float(p_over_raw**k), float(p_under_raw**k)
    except ValueError:
        # awaryjnie: proporcjonalnie
        return p_over_raw / total, p_under_raw / total


def implied_prob_one_sided(odds: float, margin: float = DEFAULT_ONE_SIDED_MARGIN) -> float:
    """Devig jednostronny: odejmij szacowaną marżę rynku od kursu."""
    return float(np.clip((1.0 / odds) * (1.0 - margin), 1e-6, 1.0 - 1e-6))


@dataclass(frozen=True)
class ConfidenceInputs:
    effective_matches: float      # efektywna próba zawodnika (po wygaszaniu)
    minutes_certainty: float      # 0..1 z modelu minut
    ci_width: float               # szerokość przedziału na P(over), 0..1
    context_magnitude: float      # |iloczyn czynników - 1| — jak mocno kontekst dźwiga edge
    market_calibrated: bool       # czy rynek ma potwierdzoną kalibrację w backteście
    is_rare_market: bool


def confidence_score(inp: ConfidenceInputs) -> float:
    """Zwraca 0-100. Składowe ważone, projektowane tak, żeby:
    * mała próba lub niepewne minuty zabijały pewność,
    * szeroki przedział na p obniżał ją mocno,
    * edge zbudowany głównie na kontekście (a nie bazie) był karany.
    """
    # próba: 0 przy 2 meczach, ~1 przy 25+
    sample = float(np.clip((inp.effective_matches - 2.0) / 23.0, 0.0, 1.0))
    minutes = float(np.clip(inp.minutes_certainty, 0.0, 1.0))
    # szerokość CI: 0.05 -> świetnie, 0.30 -> fatalnie
    precision = float(np.clip(1.0 - (inp.ci_width - 0.05) / 0.25, 0.0, 1.0))
    # kontekst > +-15% => kara narastająca
    context_penalty = float(np.clip((inp.context_magnitude - 0.15) / 0.25, 0.0, 1.0))

    score = 100.0 * (0.35 * sample + 0.30 * minutes + 0.35 * precision)
    score *= 1.0 - 0.30 * context_penalty
    if not inp.market_calibrated:
        score *= 0.85
    if inp.is_rare_market:
        score *= 0.75
    return float(np.clip(score, 0.0, 100.0))


def confidence_level(score: float) -> str:
    if score >= 65.0:
        return "wysoka"
    if score >= 40.0:
        return "srednia"
    return "niska"


def risk_level(lam: float, is_rare_market: bool, minutes_certainty: float) -> str:
    """Ryzyko — niezależne od pewności modelu: zmienność samego zdarzenia."""
    if is_rare_market or lam < 0.6:
        return "wysokie"
    if lam < 1.2 or minutes_certainty < 0.5:
        return "srednie"
    return "niskie"


@dataclass(frozen=True)
class ValueAssessment:
    side: str                 # 'powyzej' | 'ponizej'
    model_prob: float
    implied_prob: float
    fair_odds: float
    edge_pp: float
    ev_pct: float
    confidence: str
    confidence_score: float
    risk: str
    rank_score: float


# Minimalne progi publikacji okazji
MIN_EV_PCT = 1.0   # decyzja użytkownika 2026-07-03: pokazuj każdą dodatnią wartość od +1%
MIN_EV_PCT_RARE = 5.0
MIN_CONFIDENCE_SCORE = 25.0
MAX_MODEL_MARKET_DIVERGENCE = 0.22  # różnica p_model vs p_rynku > 22 pp = podejrzana
MAX_RELATIVE_DIVERGENCE = 1.9       # p_model / p_rynku > 1.9x = podejrzane (longshoty!)
MAX_ODDS = 6.0                      # kursy wyżej to loteria, nie systematyczny betting
MIN_ODDS = 1.19                     # poniżej 1.19 gra się nie opłaca (decyzja użytkownika)
MAX_CI_WIDTH = 0.30                 # zbyt szerokie widełki szansy = nie stawiamy


def assess(
    p_model_over: float,
    over_odds: float | None,
    under_odds: float | None,
    conf_inputs: ConfidenceInputs,
    lam: float,
) -> list[ValueAssessment]:
    """Oceń obie strony rynku. Zwraca tylko strony przechodzące progi."""
    results: list[ValueAssessment] = []

    if over_odds is not None and under_odds is not None:
        imp_over, imp_under = implied_probs_two_way(over_odds, under_odds)
    elif over_odds is not None:
        imp_over, imp_under = implied_prob_one_sided(over_odds), None
    elif under_odds is not None:
        imp_over, imp_under = None, implied_prob_one_sided(under_odds)
    else:
        return results

    score = confidence_score(conf_inputs)
    risk = risk_level(lam, conf_inputs.is_rare_market, conf_inputs.minutes_certainty)
    min_ev = MIN_EV_PCT_RARE if conf_inputs.is_rare_market else MIN_EV_PCT

    if conf_inputs.ci_width > MAX_CI_WIDTH:
        # Sam model nie wie, ile wynosi prawdopodobieństwo — nie stawiamy.
        return results

    for side, p_model, implied, odds in (
        ("powyzej", p_model_over, imp_over, over_odds),
        ("ponizej", 1.0 - p_model_over, imp_under, under_odds),
    ):
        if implied is None or odds is None:
            continue
        edge_pp = (p_model - implied) * 100.0
        ev_pct = (p_model * odds - 1.0) * 100.0
        if ev_pct < min_ev or score < MIN_CONFIDENCE_SCORE:
            continue
        if odds > MAX_ODDS or odds < MIN_ODDS:
            # Wysokie kursy = mały błąd modelu daje absurdalne EV;
            # bardzo niskie kursy = groszowa wartość niewarta ryzyka. Pomijamy.
            continue
        if abs(p_model - implied) > MAX_MODEL_MARKET_DIVERGENCE:
            # Model skrajnie niezgodny z rynkiem — najpewniej my się mylimy
            # (kontuzja, rotacja, wiadomość, której nie znamy). Nie publikujemy.
            continue
        if implied > 0 and p_model / implied > MAX_RELATIVE_DIVERGENCE:
            # Przy małych prawdopodobieństwach różnica względna zdradza
            # "fałszywy edge" lepiej niż różnica w punktach procentowych.
            continue
        # Ranking: przewaga w pp ważona pewnością — celowo NIE po EV,
        # żeby longshoty nie wypychały solidnych okazji.
        rank = edge_pp * (score / 100.0) ** 1.5
        results.append(
            ValueAssessment(
                side=side,
                model_prob=round(p_model, 4),
                implied_prob=round(implied, 4),
                fair_odds=round(1.0 / max(p_model, 1e-6), 3),
                edge_pp=round(edge_pp, 2),
                ev_pct=round(ev_pct, 2),
                confidence=confidence_level(score),
                confidence_score=round(score, 1),
                risk=risk,
                rank_score=round(rank, 3),
            )
        )
    return results


def clv_pct(odds_taken: float, closing_odds: float) -> float:
    """Closing Line Value: o ile lepszy kurs wzięliśmy vs kurs zamknięcia."""
    return round((odds_taken / closing_odds - 1.0) * 100.0, 2)
