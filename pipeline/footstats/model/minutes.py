"""Model minut — mieszanka scenariuszy występu.

P(over) liczymy jako średnią ważoną po scenariuszach minutowych, nie z jednej
punktowej liczby minut. Zawodnik rotacyjny ma zupełnie inny rozkład niż pewniak.

Scenariusze:
  * pełny mecz            (start, ~90')
  * start + zmiana        (start, ~65-75')
  * wejście z ławki       (~20-30')
  * nie zagra             (0')

Po ogłoszeniu oficjalnych składów scenariusze się upraszczają
(P(start) -> 1.0 albo 0.0) i predykcja jest dużo pewniejsza.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MinutesScenario:
    prob: float      # prawdopodobieństwo scenariusza
    minutes: float   # typowe minuty w tym scenariuszu


@dataclass(frozen=True)
class MinutesModel:
    scenarios: tuple[MinutesScenario, ...]
    p_start: float
    official_lineup: bool  # czy oparte o ogłoszony skład

    @property
    def expected_minutes(self) -> float:
        return sum(s.prob * s.minutes for s in self.scenarios)

    @property
    def p_plays(self) -> float:
        return sum(s.prob for s in self.scenarios if s.minutes > 0)

    @property
    def certainty(self) -> float:
        """0..1 — jak pewne są minuty (do confidence score).

        1.0 = skład oficjalny i zawodnik w jedenastce;
        im większe rozproszenie scenariuszy, tym niżej.
        """
        if self.official_lineup:
            return 1.0 if self.p_start > 0.5 else 0.7
        em = self.expected_minutes
        if em <= 0:
            return 0.0
        var = sum(s.prob * (s.minutes - em) ** 2 for s in self.scenarios)
        var += (1.0 - self.p_plays) * em**2
        cv = np.sqrt(var) / max(em, 1.0)
        return float(np.clip(1.0 - cv, 0.0, 1.0))


def estimate_minutes(
    recent_started: list[bool],
    recent_minutes: list[float],
    days_ago: list[float],
    injured_or_suspended: bool = False,
    official_started: bool | None = None,
    predicted_started: bool | None = None,
    tau_days: float = 60.0,
) -> MinutesModel:
    """Zbuduj scenariusze minutowe z historii występów.

    recent_started / recent_minutes / days_ago — historia ostatnich meczów drużyny
    (uwzględniając mecze, w których zawodnik NIE zagrał: started=False, minutes=0).
    official_started — jeżeli skład jest ogłoszony: True (w XI) / False (poza XI);
                       None = skład nieznany, używamy historii.
    predicted_started — przewidywany skład (media/statshub), sygnał MIĘKKI:
                       przesuwa P(start), ale nie daje pewności składu.
                       Używany tylko, gdy official_started is None.
    """
    if injured_or_suspended:
        return MinutesModel(
            scenarios=(MinutesScenario(1.0, 0.0),), p_start=0.0, official_lineup=True
        )

    started = np.asarray(recent_started, dtype=bool)
    minutes = np.asarray(recent_minutes, dtype=float)
    days = np.asarray(days_ago, dtype=float)
    w = np.exp(-np.maximum(days, 0.0) / tau_days) if len(days) else np.array([])

    if len(minutes) == 0:
        # Brak historii: ostrożny default rezerwowego.
        if official_started is not None:
            p_start = 1.0 if official_started else 0.0
        elif predicted_started is not None:
            p_start = 0.88 if predicted_started else 0.12
        else:
            p_start = 0.3
        start_min, sub_min, p_sub = 80.0, 25.0, 0.4
    else:
        p_start = float(np.average(started, weights=w))
        if official_started is None and predicted_started is not None:
            # Miękkie przesunięcie: przewidywane składy trafiają ~85-90%,
            # ale bywają błędne — mieszamy z historią zamiast nadpisywać.
            target = 0.88 if predicted_started else 0.12
            p_start = 0.35 * p_start + 0.65 * target
        start_mask = started & (minutes > 0)
        start_min = float(np.average(minutes[start_mask], weights=w[start_mask])) if start_mask.any() else 80.0
        sub_mask = (~started) & (minutes > 0)
        sub_min = float(np.average(minutes[sub_mask], weights=w[sub_mask])) if sub_mask.any() else 25.0
        bench = ~started
        p_sub = float(np.average(minutes[bench] > 0, weights=w[bench])) if bench.any() else 0.4

    if official_started is not None:
        if official_started:
            # W wyjściowym składzie: dwa scenariusze — pełny mecz albo zmiana.
            p_full = float(np.clip((start_min - 55.0) / 35.0, 0.15, 0.95))
            scen = (
                MinutesScenario(p_full, 90.0),
                MinutesScenario(1.0 - p_full, max(min(start_min, 82.0), 55.0)),
            )
            return MinutesModel(scenarios=scen, p_start=1.0, official_lineup=True)
        # Poza XI (ławka): wejdzie albo nie.
        scen = (
            MinutesScenario(p_sub, max(sub_min, 10.0)),
            MinutesScenario(1.0 - p_sub, 0.0),
        )
        return MinutesModel(scenarios=scen, p_start=0.0, official_lineup=True)

    # Skład nieznany — pełna mieszanka.
    p_full = float(np.clip((start_min - 55.0) / 35.0, 0.15, 0.95))
    p_no_play = max(0.0, (1.0 - p_start) * (1.0 - p_sub))
    scen = (
        MinutesScenario(p_start * p_full, 90.0),
        MinutesScenario(p_start * (1.0 - p_full), max(min(start_min, 82.0), 55.0)),
        MinutesScenario((1.0 - p_start) * p_sub, max(sub_min, 10.0)),
        MinutesScenario(p_no_play, 0.0),
    )
    return MinutesModel(scenarios=scen, p_start=p_start, official_lineup=False)


def p_over_mixture(minutes_model: MinutesModel, p_over_given_minutes) -> float:
    """P(over) jako mieszanka po scenariuszach.

    p_over_given_minutes(minutes: float) -> float — funkcja licząca P(over)
    dla zadanych minut (z modelu NB).
    """
    total = 0.0
    for s in minutes_model.scenarios:
        if s.prob <= 0:
            continue
        total += s.prob * (p_over_given_minutes(s.minutes) if s.minutes > 0 else 0.0)
    return float(total)
