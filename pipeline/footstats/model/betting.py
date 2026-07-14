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

import math
from dataclasses import dataclass

import numpy as np
from scipy import optimize
from scipy import stats as _stats

# Typowa marża polskich bukmacherów na player props (do jednostronnych kwotowań).
DEFAULT_ONE_SIDED_MARGIN = 0.07

# pokrewne rynki dzielą błąd modelu i korelują przez tempo meczu — wspólna
# mapa dla kalibracji (rozliczanie) i dywersyfikacji kuponów (kupony)
RODZINY_RYNKOW = {
    "shots": "strzelanie", "sot": "strzelanie",
    "shots_outside_box": "strzelanie", "sot_outside_box": "strzelanie",
    "headed_shots": "strzelanie", "headed_sot": "strzelanie",
    "shots_blocked": "strzelanie", "shots_off_target": "strzelanie",
    "fouls_committed": "faule", "fouls_won": "faule", "yellow_card": "faule",
    "tackles": "defensywa", "interceptions": "defensywa",
}


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


# Typowa marża JEDNOSTRONNA konsensusu UK na propsach zawodniczych. Niższa niż
# PL (DEFAULT_ONE_SIDED_MARGIN=0.07), bo mediana z kilku ostrych buków (Bet365,
# Skybet...) częściowo znosi wychylenia. Świadome założenie — statshub daje tylko
# stronę „over", więc marży nie da się usunąć dwustronnie (over/under). Kandydat
# do kalibracji z rozliczeń: porównać p_novig do realnej częstości trafień.
UK_CONSENSUS_MARGIN = 0.045


def no_vig_prob_uk(
    uk_over_odds: list[float], margin: float = UK_CONSENSUS_MARGIN
) -> tuple[float, float] | None:
    """No-vig z konsensusu bukmacherów UK (statshub) — benchmark uczciwej ceny.

    statshub oddaje wyłącznie stronę „over" z kilku buków UK. Bierzemy medianę
    (odporną na jednego odstającego buka) i zdejmujemy jednostronną marżę UK.
    To najczystszy dostępny sygnał „prawdziwej" ceny rynku: linia Superbetu
    płacąca wyraźnie WIĘCEJ, niż wynika z no-vig UK, to miękka linia.

    Zwraca (p_fair, fair_odds) albo None, gdy brak sensownych kursów UK.
    """
    ok = [o for o in uk_over_odds if o and o > 1.0]
    if not ok:
        return None
    med = float(np.median(ok))
    p_fair = implied_prob_one_sided(med, margin)
    return p_fair, 1.0 / p_fair


def internal_fair_odds(lines_probs: dict[float, float]) -> dict[float, float]:
    """Samospójność SIATKI LINII jednego bukmachera — line shopping bez
    zewnętrznych kursów.

    Wszystkie linie jednego rynku (0,5 / 1,5 / 2,5...) opisują JEDEN rozkład
    zliczeniowy. Dla każdej linii dopasowujemy Poissona do POZOSTAŁYCH
    (leave-one-out) i liczymy jej fair kurs netto. Linia płacąca wyraźnie
    więcej, niż wynika z reszty siatki, to pomyłka tradera — dokładnie
    wzorzec "reszta rynku 1,55, a tu 2,20", tylko z własnej oferty buka.

    lines_probs: {linia: p_over po devigu}. Zwraca {linia: fair_kurs_netto}
    tylko dla linii, gdzie fit z pozostałych jest wiarygodny (>=2 zgodne
    punkty, rozrzut lambd <= 1.35x).
    """
    out: dict[float, float] = {}
    items = sorted(lines_probs.items())
    if len(items) < 3:
        return out

    def _lam(line: float, p: float) -> float | None:
        thr = math.floor(line)          # "powyżej l,5" = X > floor(l)

        def f(lam: float) -> float:
            return float(_stats.poisson.sf(thr, lam)) - p

        try:
            if f(0.01) * f(15.0) > 0:
                return None
            return float(optimize.brentq(f, 0.01, 15.0))
        except Exception:
            return None

    lams = {
        l: _lam(l, p) for l, p in items if 0.03 < p < 0.97
    }
    for l, _p in items:
        rest = [v for k, v in lams.items() if k != l and v is not None]
        if len(rest) < 2 or min(rest) <= 0:
            continue
        if max(rest) / min(rest) > 1.35:
            continue  # siatka wewnętrznie niespójna — nie ufaj fitowi
        lam_ref = sum(rest) / len(rest)
        p_fair = float(_stats.poisson.sf(math.floor(l), lam_ref))
        if p_fair > 1e-6:
            out[l] = 1.0 / p_fair
    return out


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


def risk_level(
    lam: float,
    is_rare_market: bool,
    minutes_certainty: float,
    is_prob_market: bool = False,
) -> str:
    """Ryzyko — niezależne od pewności modelu: zmienność samego zdarzenia.

    Dla rynków LICZNIKOWYCH (strzały, faule...) `lam` to oczekiwana liczba
    zdarzeń — progi 0.6/1.2 mierzą, jak rzadkie (a więc kapryśne) jest zdarzenie.

    Dla rynków BINARNYCH (`is_prob_market`, np. żółta kartka) `lam` to
    prawdopodobieństwo zdarzenia w [0,1] — progi licznikowe są tu bez sensu
    (P<0.6 dawało zawsze „wysokie"). Zamiast tego mierzymy zdecydowanie zdarzenia:
    im bliżej 50/50, tym większa loteria.
    """
    if is_prob_market:
        decisiveness = abs(lam - 0.5) * 2.0   # 0 = rzut monetą, 1 = zdarzenie pewne
        if minutes_certainty < 0.5 or decisiveness < 0.30:
            return "wysokie"
        if decisiveness < 0.60:
            return "srednie"
        return "niskie"
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
# MAX_MODEL_MARKET_DIVERGENCE/MAX_RELATIVE_DIVERGENCE: ZAŁOŻENIA ustawione "na
# oko" (jak było UK_CONSENSUS_MARGIN przed pomiarem) — nie ma jeszcze gruntu
# kalibracji mierzącego, ile typów odrzuconych tymi progami faktycznie by
# trafiło, gdyby je przepuścić. Kandydat na kolejny "grunt pomiaru": logować w
# typy_log próbki TUŻ PONIŻEJ progu (odrzucone, ale bliskie) i porównać ich
# realny hit-rate z przepuszczonymi, zanim ruszy się same liczby.
MAX_MODEL_MARKET_DIVERGENCE = 0.22  # różnica p_model vs p_rynku > 22 pp = podejrzana
MAX_RELATIVE_DIVERGENCE = 1.9       # p_model / p_rynku > 1.9x = podejrzane (longshoty!)
MAX_ODDS = 6.0                      # kursy wyżej to loteria, nie systematyczny betting
MIN_ODDS = 1.19                     # poniżej 1.19 gra się nie opłaca (decyzja użytkownika)
MAX_CI_WIDTH = 0.30                 # zbyt szerokie widełki szansy = nie stawiamy

# GRUNT POMIARU progów (zapowiadany w komentarzu wyżej): typ odrzucony
# DOKŁADNIE JEDNYM kryterium o mniej niż poniższe tolerancje trafia do
# typy_log z flagą `odrzucony` — rozlicza się w tle (POZA kalibracją,
# skutecznością i UI), a diagnostyka porównuje jego realny hit-rate z
# przepuszczonymi. Dopiero ten pomiar uzasadni ruszanie samych progów.
NEAR_EV_PP = 3.0        # EV do 3 pp poniżej progu
NEAR_CONF = 10.0        # confidence do 10 pkt poniżej progu
NEAR_DIV = 0.06         # rozjazd model-rynek do 6 pp ponad limit
NEAR_REL = 0.3          # rozjazd względny do 0.3x ponad limit


def assess(
    p_model_over: float,
    over_odds: float | None,
    under_odds: float | None,
    conf_inputs: ConfidenceInputs,
    lam: float,
    is_prob_market: bool = False,
    odrzucone_out: list | None = None,
) -> list[ValueAssessment]:
    """Oceń obie strony rynku. Zwraca tylko strony przechodzące progi.

    is_prob_market — rynek binarny (kartka): `lam` to prawdopodobieństwo, nie
    licznik; ryzyko liczone inną skalą (patrz risk_level).
    odrzucone_out — kolektor odrzuceń TUŻ przy progu (patrz NEAR_*): strony
    odrzucone dokładnie jednym kryterium w tolerancji lądują tu jako
    {side, powod, p_model, implied, odds, ev_pct, confidence_score}.
    """
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
    risk = risk_level(
        lam, conf_inputs.is_rare_market, conf_inputs.minutes_certainty, is_prob_market
    )
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
        # bramki publikacji — każda z parą (odrzuca?, czy TUŻ przy progu?);
        # komentarze przy stałych MAX_* wyżej tłumaczą intuicje
        powody: list[tuple[str, bool]] = []
        if ev_pct < min_ev:
            powody.append(("ev_ponizej_progu", ev_pct >= min_ev - NEAR_EV_PP))
        if score < MIN_CONFIDENCE_SCORE:
            powody.append(
                ("niska_pewnosc", score >= MIN_CONFIDENCE_SCORE - NEAR_CONF)
            )
        if odds > MAX_ODDS or odds < MIN_ODDS:
            # wysokie kursy = loteria, groszowe = niewarte ryzyka; celowo BEZ
            # strefy pomiaru (decyzja o widełkach kursów jest usera, nie modelu)
            powody.append(("kurs_poza_widelkami", False))
        if abs(p_model - implied) > MAX_MODEL_MARKET_DIVERGENCE:
            powody.append((
                "rozjazd_z_rynkiem",
                abs(p_model - implied) <= MAX_MODEL_MARKET_DIVERGENCE + NEAR_DIV,
            ))
        if implied > 0 and p_model / implied > MAX_RELATIVE_DIVERGENCE:
            powody.append((
                "rozjazd_wzgledny",
                p_model / implied <= MAX_RELATIVE_DIVERGENCE + NEAR_REL,
            ))
        if powody:
            if odrzucone_out is not None and len(powody) == 1 and powody[0][1]:
                odrzucone_out.append({
                    "side": side, "powod": powody[0][0],
                    "p_model": round(p_model, 4),
                    "implied": round(implied, 4), "odds": odds,
                    "ev_pct": round(ev_pct, 2),
                    "confidence_score": round(score, 1),
                })
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
