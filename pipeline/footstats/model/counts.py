"""Probabilistyczny rdzeń modelu — statystyki licznikowe (count stats).

Podejście: bayesowski model Gamma-Poisson z wygaszaniem czasowym obserwacji.

* Intensywność zawodnika per 90 minut: lambda ~ Gamma(alpha, beta).
* Prior (alpha0, beta0) pochodzi z grupy porównawczej (pozycja x rola x liga)
  — empiryczny Bayes: zawodnik z małą próbą jest "ściągany" do średniej grupy.
* Obserwacje ważone wykładniczo w czasie: w = exp(-dni_temu / tau).
* Rozkład predykcyjny liczby zdarzeń w meczu przy ekspozycji e
  (e = mnożniki kontekstu x minuty/90) to ujemny dwumianowy (Negative Binomial):
      X ~ NB(r = alpha, p = beta / (beta + e))
  co daje naddyspersję "za darmo" — im mniejsza próba, tym szersze ogony.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


# Domyślne tempo wygaszania: po ~pół roku obserwacja waży ~37% świeżej.
DEFAULT_TAU_DAYS = 180.0

# Minimalna efektywna liczba meczów, żeby predykcja wyszła poza "watchlistę".
MIN_EFFECTIVE_MATCHES = 4.0


@dataclass(frozen=True)
class GammaPosterior:
    """Posterior intensywności per-90 dla pary (zawodnik, statystyka)."""

    alpha: float
    beta: float
    effective_matches: float  # suma wag obserwacji (ekwiwalent pełnych meczów)

    @property
    def mean_per90(self) -> float:
        return self.alpha / self.beta

    @property
    def var_per90(self) -> float:
        return self.alpha / self.beta**2

    def credible_interval_per90(self, level: float = 0.95) -> tuple[float, float]:
        lo = (1.0 - level) / 2.0
        dist = stats.gamma(a=self.alpha, scale=1.0 / self.beta)
        return float(dist.ppf(lo)), float(dist.ppf(1.0 - lo))


@dataclass(frozen=True)
class GroupPrior:
    """Prior grupy porównawczej wyrażony jako (średnia per-90, pseudo-mecze)."""

    mean_per90: float
    pseudo_matches: float  # ile "wirtualnych meczów" waży prior (siła ściągania)
    source: str = ""       # np. "klub" = prior z historii sprzed turnieju

    @property
    def alpha0(self) -> float:
        return self.mean_per90 * self.pseudo_matches

    @property
    def beta0(self) -> float:
        return self.pseudo_matches


def estimate_group_prior(
    per90_rates: np.ndarray,
    weights: np.ndarray | None = None,
    default_pseudo_matches: float = 6.0,
) -> GroupPrior:
    """Empiryczny Bayes: dopasuj prior Gamma do rozrzutu stawek per-90 w grupie.

    Metoda momentów na rozkładzie stawek per-90 między zawodnikami grupy.
    Jeżeli wariancja międzyosobnicza jest duża, prior jest słaby (mało ściąga);
    jeżeli grupa jest jednorodna, prior jest mocny.
    """
    rates = np.asarray(per90_rates, dtype=float)
    rates = rates[np.isfinite(rates)]
    if len(rates) < 5:
        m = float(np.mean(rates)) if len(rates) else 0.5
        return GroupPrior(mean_per90=max(m, 0.05), pseudo_matches=default_pseudo_matches)

    if weights is None:
        weights = np.ones_like(rates)
    w = np.asarray(weights, dtype=float)
    m = float(np.average(rates, weights=w))
    v = float(np.average((rates - m) ** 2, weights=w))
    m = max(m, 0.02)

    # Rozkład Gamma o średniej m i wariancji v: alpha = m^2/v, beta = m/v.
    # pseudo_matches ~ beta, ale ograniczamy do sensownego zakresu [2, 20],
    # żeby prior nigdy nie zdominował realnych danych ani nie był bez znaczenia.
    if v <= 1e-9:
        pseudo = 20.0
    else:
        pseudo = float(np.clip(m / v, 2.0, 20.0))
    return GroupPrior(mean_per90=m, pseudo_matches=pseudo)


def fit_posterior(
    counts: np.ndarray,
    minutes: np.ndarray,
    days_ago: np.ndarray,
    prior: GroupPrior,
    tau_days: float = DEFAULT_TAU_DAYS,
    extra_weights: np.ndarray | None = None,
) -> GammaPosterior:
    """Policz posterior intensywności per-90 z historii meczów zawodnika.

    counts   — liczba zdarzeń w kolejnych meczach
    minutes  — rozegrane minuty w tych meczach
    days_ago — ile dni temu był każdy mecz (świeże ważą najwięcej)
    extra_weights — waga jakości próby per mecz (siła rywala: mecz z drużyną
                    poziomu MŚ liczy się pełniej niż mecz ze słabeuszem);
                    mnożona przez wagę świeżości
    """
    counts = np.asarray(counts, dtype=float)
    minutes = np.asarray(minutes, dtype=float)
    days_ago = np.asarray(days_ago, dtype=float)
    ew = (
        np.asarray(extra_weights, dtype=float)
        if extra_weights is not None and len(extra_weights) == len(counts)
        else np.ones_like(counts)
    )

    mask = (minutes > 0) & np.isfinite(counts)
    counts, minutes, days_ago = counts[mask], minutes[mask], days_ago[mask]
    ew = ew[mask]

    w = np.exp(-np.maximum(days_ago, 0.0) / tau_days) * ew
    exposure = minutes / 90.0

    alpha = prior.alpha0 + float(np.sum(w * counts))
    beta = prior.beta0 + float(np.sum(w * exposure))
    eff = float(np.sum(w * exposure))
    return GammaPosterior(alpha=alpha, beta=beta, effective_matches=eff)


@dataclass(frozen=True)
class MatchPrediction:
    """Rozkład predykcyjny liczby zdarzeń w konkretnym meczu."""

    lam: float          # E[liczba zdarzeń] w meczu
    nb_r: float         # parametr r ujemnego dwumianowego (= alpha posteriora)
    nb_p: float         # parametr p ujemnego dwumianowego
    exposure: float     # łączna ekspozycja (kontekst x minuty/90)

    def pmf(self, k: int) -> float:
        return float(stats.nbinom.pmf(k, self.nb_r, self.nb_p))

    def p_over(self, line: float) -> float:
        """P(X > linia). Dla linii .5 to P(X >= ceil(linia))."""
        threshold = int(np.floor(line))  # X > 1.5 <=> X >= 2 <=> X > 1
        return float(stats.nbinom.sf(threshold, self.nb_r, self.nb_p))

    def p_under(self, line: float) -> float:
        return 1.0 - self.p_over(line)

    def distribution(self, max_k: int = 10) -> list[float]:
        """PMF do wykresu w UI: P(X=0), P(X=1), ..., P(X>=max_k)."""
        probs = [self.pmf(k) for k in range(max_k)]
        probs.append(max(0.0, 1.0 - sum(probs)))
        return probs


def predict_match(
    posterior: GammaPosterior,
    expected_minutes: float,
    context_multiplier: float = 1.0,
) -> MatchPrediction:
    """Rozkład predykcyjny dla meczu: NB z ekspozycją kontekst x minuty/90.

    X | lambda ~ Poisson(lambda * e), lambda ~ Gamma(alpha, beta)
      => X ~ NB(r=alpha, p=beta/(beta+e))
    """
    e = max(context_multiplier, 1e-6) * max(expected_minutes, 0.0) / 90.0
    if e <= 1e-9:
        return MatchPrediction(lam=0.0, nb_r=posterior.alpha, nb_p=1.0, exposure=0.0)
    p = posterior.beta / (posterior.beta + e)
    lam = posterior.mean_per90 * e
    return MatchPrediction(lam=lam, nb_r=posterior.alpha, nb_p=p, exposure=e)


def p_over_credible_interval(
    posterior: GammaPosterior,
    expected_minutes: float,
    context_multiplier: float,
    line: float,
    level: float = 0.90,
    n_samples: int = 4000,
    seed: int = 7,
) -> tuple[float, float]:
    """Przedział wiarygodności na P(over) — przez próbkowanie posteriora lambdy.

    Pokazuje użytkownikowi, jak pewna jest sama estymata prawdopodobieństwa
    (szeroki przedział = mało danych = niska pewność).
    """
    rng = np.random.default_rng(seed)
    e = max(context_multiplier, 1e-6) * max(expected_minutes, 0.0) / 90.0
    if e <= 1e-9:
        return 0.0, 0.0
    lam_samples = rng.gamma(shape=posterior.alpha, scale=1.0 / posterior.beta, size=n_samples)
    threshold = int(np.floor(line))
    # Dla każdej próbki lambdy: P(X > linia) przy Poisson(lambda*e)
    p_overs = stats.poisson.sf(threshold, lam_samples * e)
    lo = (1.0 - level) / 2.0
    return float(np.quantile(p_overs, lo)), float(np.quantile(p_overs, 1.0 - lo))
