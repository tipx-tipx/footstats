"""Tempo/scenariusz meczu z kursów meczowych Superbetu (1X2 + liczba goli).

Rynek meczowy jest najefektywniejszym dostępnym sygnałem siły drużyn TU i TERAZ
(uwzględnia składy, motywację, kontuzje). Zamieniamy go na dwie liczby, które
rozumie context.game_script_factor:

  * implied_total  — oczekiwana suma goli (z linii najbliższej 2.5),
  * implied_spread — oczekiwana różnica goli gospodarz-gość (dopasowana tak,
    by model Poissona odtworzył odsianą z marży szansę wygranej gospodarza).
"""

from __future__ import annotations

from scipy import optimize, stats

# Licznik cichych fallbacków w BIEŻĄCYM cyklu — _total_from_line/
# _spread_from_home_prob wracały do neutralnej wartości (2.6 / 0.0) bez
# śladu, gdy solver nie zbiegł. Bez tego nie było wiadomo, jak często tempo
# meczu jest ZGADYWANE zamiast liczone z realnych kursów. reset_fallback_
# stats() wołane na początku cyklu (build_wc_fast.py), fallback_stats() do
# logu na końcu.
_fallback_stats = {"total_ok": 0, "total_fallback": 0, "spread_ok": 0, "spread_fallback": 0}


def reset_fallback_stats() -> None:
    for k in _fallback_stats:
        _fallback_stats[k] = 0


def fallback_stats() -> dict:
    return dict(_fallback_stats)


def _devig(odds: list[float]) -> list[float]:
    """Usuń marżę metodą POTĘGOWĄ — spójnie z betting.implied_probs_two_way.

    Szukamy k: Σ (1/oddsᵢ)^k = 1. Potęgowa lepiej niż proporcjonalna oddaje
    favourite-longshot bias (rynek zawyża szanse outsiderów); dotyczy to też
    1X2, z którego liczymy tempo. Fallback proporcjonalny, gdy brak zbieżności.
    """
    inv = [1.0 / o for o in odds]
    s = sum(inv)
    if s <= 1.0:  # brak marży / arbitraż — bierzemy wprost
        return inv

    def overround(k: float) -> float:
        return sum(p**k for p in inv) - 1.0

    try:
        k = optimize.brentq(overround, 1.0, 5.0, xtol=1e-10)
        return [p**k for p in inv]
    except ValueError:
        return [p / s for p in inv]


def _total_from_line(line: float, p_over: float) -> float:
    """Znajdź T: P(Poisson(T) > line) = p_over."""
    thr = int(line)

    def f(t: float) -> float:
        return float(stats.poisson.sf(thr, t)) - p_over

    try:
        v = float(optimize.brentq(f, 0.2, 7.0))
        _fallback_stats["total_ok"] += 1
        return v
    except ValueError:
        _fallback_stats["total_fallback"] += 1
        return 2.6


def _spread_from_home_prob(total: float, p_home: float, p_away: float) -> float:
    """Znajdź s: udział wygranych gospodarza (bez remisów) jak w kursach.

    Dopasowujemy P(H>A)/(P(H>A)+P(A>H)) zamiast bezwzględnego P(H>A) —
    Poisson zaniża remisy, a udział warunkowy jest na to odporny
    (symetryczne kursy => dokładnie s=0).
    """
    cel = p_home / max(p_home + p_away, 1e-9)

    def f(s: float) -> float:
        mu_h = max((total + s) / 2.0, 0.05)
        mu_a = max((total - s) / 2.0, 0.05)
        ph = float(stats.skellam.sf(0, mu_h, mu_a))
        pa = float(stats.skellam.cdf(-1, mu_h, mu_a))
        return ph / max(ph + pa, 1e-9) - cel

    try:
        v = float(optimize.brentq(f, -total + 0.1, total - 0.1))
        _fallback_stats["spread_ok"] += 1
        return v
    except ValueError:
        _fallback_stats["spread_fallback"] += 1
        return 0.0


def tempo_from_match_odds(match: dict | None) -> dict | None:
    """{'h','x','a','totals'} z superbet.fetch_stat_odds -> tempo meczu.

    Zwraca {'spread': gole H−A, 'total': suma goli, 'p_home', 'p_away'}
    albo None, gdy brak kompletu kursów 1X2.
    """
    if not match:
        return None
    h, x, a = match.get("h"), match.get("x"), match.get("a")
    if not (h and x and a):
        return None
    p_home, _, p_away = _devig([h, x, a])

    total = 2.6
    totals = match.get("totals") or {}
    if totals:
        # linia najbliższa 2.5 z oboma stronami kursu
        line = min(
            (l for l, v in totals.items() if v.get("over") and v.get("under")),
            key=lambda l: abs(l - 2.5),
            default=None,
        )
        if line is not None:
            po, pu = _devig([totals[line]["over"], totals[line]["under"]])
            total = _total_from_line(line, po)

    return {
        "spread": round(_spread_from_home_prob(total, p_home, p_away), 3),
        "total": round(total, 3),
        "p_home": round(p_home, 4),
        "p_away": round(p_away, 4),
    }
