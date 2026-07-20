"""Warstwa kontekstowa — multiplikatywne czynniki korygujące intensywność.

Finalna ekspozycja: lambda_meczu = lambda_per90 x (minuty/90) x iloczyn czynników.

Zasady bezpieczeństwa:
  * każdy czynnik jest SHRINKOWANY do 1.0 proporcjonalnie do wielkości próby,
  * każdy czynnik jest CAPOWANY do widełek — kontekst koryguje model,
    ale nigdy nim nie rządzi,
  * czynniki raportujemy osobno w JSON, żeby UI mogło pokazać
    "wodospad": baza -> minuty -> rywal -> sędzia -> dom/wyjazd -> wynik.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Widełki czynników (mnożniki)
CAP_OPPONENT = (0.78, 1.30)
CAP_REFEREE = (0.75, 1.35)
CAP_HOME_AWAY = (0.90, 1.10)
CAP_GAME_SCRIPT = (0.85, 1.20)
# Łączny bezpiecznik na ILOCZYN czynników. Każdy czynnik jest już capowany
# osobno, ale nałożenie kilku skrajnych mnożników (np. rywal + sędzia +
# scenariusz + matchup, wszystkie w górę) potrafi dać ~2.4x i zdominować bazę,
# co przeczy zasadzie „kontekst koryguje, nie rządzi". Zakres celowo LUŹNY:
# na normalnych typach (w tym uzasadnionych matchupach ~1.3x) nieaktywny,
# ucina tylko ekstremalne złożenia. W trybie MŚ (boisko neutralne, małe próby
# → mocny shrink) prawie nigdy nie wchodzi; realnie chroni tryb ligowy, gdzie
# dochodzi efekt dom/wyjazd i większe próby dopychają czynniki do widełek.
CAP_COMBINED = (0.60, 1.80)


def shrink_factor(raw: float, sample_size: float, prior_strength: float = 10.0) -> float:
    """Ściągnij surowy mnożnik do 1.0 przy małej próbie.

    sample_size — np. liczba meczów, na których czynnik policzono.
    prior_strength — ile "wirtualnych meczów" waży neutralność.
    """
    if not np.isfinite(raw) or raw <= 0:
        return 1.0
    k = sample_size / (sample_size + prior_strength)
    return float(1.0 + k * (raw - 1.0))


def cap(value: float, bounds: tuple[float, float]) -> float:
    return float(np.clip(value, bounds[0], bounds[1]))


@dataclass
class ContextFactors:
    """Komplet czynników dla jednej predykcji, z metadanymi do UI."""

    opponent: float = 1.0        # ile rywal "dopuszcza" danej statystyki
    referee: float = 1.0         # tylko rynki dyscyplinarne
    home_away: float = 1.0
    game_script: float = 1.0     # z kursów meczowych (spread/total)
    matchup: float = 1.0         # styl rywala "kto na kogo gra"
    notes: dict = field(default_factory=dict)  # opisy po polsku do uzasadnienia

    @property
    def combined(self) -> float:
        raw = (
            self.opponent * self.referee * self.home_away
            * self.game_script * self.matchup
        )
        return cap(raw, CAP_COMBINED)

    def as_dict(self) -> dict:
        return {
            "rywal": round(self.opponent, 3),
            "sedzia": round(self.referee, 3),
            "dom_wyjazd": round(self.home_away, 3),
            "scenariusz_meczu": round(self.game_script, 3),
            "matchup": round(self.matchup, 3),
            "lacznie": round(self.combined, 3),
            "opisy": self.notes,
        }


def opponent_factor(
    opponent_allowed_per90: float,
    league_avg_per90: float,
    sample_matches: int,
) -> float:
    """Czynnik rywala: ile przeciwnik dopuszcza danej statystyki vs średnia ligi."""
    if league_avg_per90 <= 0:
        return 1.0
    raw = opponent_allowed_per90 / league_avg_per90
    return cap(shrink_factor(raw, sample_matches, prior_strength=12.0), CAP_OPPONENT)


def referee_factor(
    referee_fouls_multiplier: float | None,
    sample_matches: int,
    market_is_disciplinary: bool,
) -> float:
    """Czynnik sędziego — tylko faule i kartki. Brak obsady = neutralnie."""
    if not market_is_disciplinary or referee_fouls_multiplier is None:
        return 1.0
    return cap(shrink_factor(referee_fouls_multiplier, sample_matches, 8.0), CAP_REFEREE)


def home_away_factor(is_home: bool, market_code: str) -> float:
    """Efekt dom/wyjazd per rodzina rynków (stałe skalibrowane z literatury/danych).

    Gospodarze strzelają więcej i faulują mniej; goście odwrotnie.
    Wartości celowo skromne — resztę i tak niesie czynnik rywala i game script.
    """
    offensive = market_code.startswith(
        ("shots", "sot", "headed", "fh_",
         "team_shots", "team_sot", "team_goals", "team_corners")
    )
    disciplinary = "foul" in market_code or "card" in market_code or market_code == "yellow_card"
    if offensive:
        return 1.06 if is_home else 0.94
    if disciplinary:
        return 0.96 if is_home else 1.05
    return 1.0


def game_script_factor(
    implied_spread: float | None,
    implied_total: float | None,
    market_code: str,
    is_favourite: bool,
) -> float:
    """Scenariusz meczu z rynku 1X2/goli (rynek meczowy jest efektywny — używamy go).

    Intuicja:
      * duży total -> otwarty mecz -> więcej strzałów, mniej fauli taktycznych,
      * wyraźny faworyt -> underdog broni się głęboko -> jego obrońcy mają
        więcej odbiorów/przechwytów, faworyt więcej strzałów (też z dystansu).
    """
    f = 1.0
    offensive = market_code.startswith(
        ("shots", "sot", "headed", "fh_",
         "team_shots", "team_sot", "team_goals", "team_corners")
    )
    defensive = market_code in ("tackles", "interceptions")
    disciplinary = "foul" in market_code or "card" in market_code or market_code == "yellow_card"

    if implied_total is not None:
        # Odchylenie totalu od 2.6 gola: +-0.1 mnożnika na gol dla rynków ofensywnych.
        dev = (implied_total - 2.6) / 2.6
        if offensive:
            f *= 1.0 + 0.35 * dev
        if disciplinary:
            f *= 1.0 - 0.15 * dev  # otwarte mecze = mniej cynicznych fauli

    if implied_spread is not None:
        edge = abs(implied_spread)
        if defensive:
            # Obrońcy underdoga mają więcej pracy defensywnej.
            f *= (1.0 + 0.08 * edge) if not is_favourite else (1.0 - 0.06 * edge)
        if offensive:
            f *= (1.0 + 0.06 * edge) if is_favourite else (1.0 - 0.05 * edge)
        if disciplinary and not is_favourite:
            f *= 1.0 + 0.05 * edge  # goniący/broniący się faulują więcej

    return cap(f, CAP_GAME_SCRIPT)
