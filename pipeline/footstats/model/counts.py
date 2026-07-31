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


# --- DWA NOWE RODZAJE ZAKŁADU (2026-07-30) ---------------------------------
#
# Dotąd model umiał tylko „ile zdarzeń zrobi JEDNA drużyna" i porównywał to
# z linią. Superbet kwotuje jeszcze dwa rodzaje, których nie czytaliśmy:
#   * „kto więcej" — porównanie dwóch drużyn, trzy wyniki z remisem,
#   * suma meczowa — obie drużyny razem, linia jak przy pojedynczej drużynie.
#
# CZEMU „KTO WIĘCEJ" JEST DLA NAS SZCZEGÓLNIE WARTOŚCIOWY: zmierzony błąd
# modelu to ZAWYŻANIE przewidywanej liczby zdarzeń (pomiar 2026-07-30: typy
# „powyżej" deklarują 74%, wchodzą 59%). W porównaniu dwóch drużyn ten błąd
# w dużej mierze SIĘ SKRACA, bo zawyżamy obie strony naraz. W sumie meczowej
# przeciwnie — dodaje się, więc tam ostrożność musi być większa.
#
# ZAŁOŻENIE NIEZALEŻNOŚCI I JEGO GRANICE. Oba rachunki traktują liczby obu
# drużyn jako niezależne. To NIE jest prawda: przebieg meczu wiąże je ze sobą
# (drużyna dominująca oddaje więcej strzałów, rywal mniej), więc realnie
# korelacja jest ujemna. Skutki są przeciwne dla obu rynków i trzeba je znać:
#   * przy „kto więcej" ujemna korelacja ZANIŻA nasze P(remis) — remisy są
#     rzadsze niż przy niezależności, więc jesteśmy tu ostrożni w dobrą stronę
#     (nie przepłacamy za remis),
#   * przy sumie meczowej ujemna korelacja ZWĘŻA prawdziwy rozkład sumy,
#     czyli nasze ogony są za grube i P(over) na wysokich liniach wychodzi
#     zawyżone.
# Dlatego sumy meczowe wchodzą z tą samą ostrożnością co reszta (kwarantanna
# strony linii), a docelowo korelację trzeba ZMIERZYĆ na rozliczeniach —
# tak samo jak zmierzyliśmy korelację legów kuponu.

# Dokąd sumujemy rozkład. Powyżej tego liczby zdarzeń w meczu nie występują,
# a reszta masy i tak trafia do normalizacji.
MAX_ZDARZEN = 40


def _pmf_wektor(pred: "MatchPrediction", max_k: int = MAX_ZDARZEN) -> list[float]:
    """P(X=0..max_k) dla jednej drużyny."""
    return [pred.pmf(k) for k in range(max_k + 1)]


def porownanie_druzyn(
    pred_a: "MatchPrediction",
    pred_b: "MatchPrediction",
    max_k: int = MAX_ZDARZEN,
) -> tuple[float, float, float]:
    """(P(A>B), P(remis), P(B>A)) — trzy wyniki rynku „kto więcej".

    Trzy liczby MUSZĄ sumować się do jedynki: to jest cały rynek, a nie linia
    z dwiema stronami. Gdyby się nie sumowały, przewaga policzona wobec kursu
    byłaby zmyślona, a błąd niewidoczny na stronie — dlatego na końcu jest
    jawna normalizacja resztą obciętego ogona.
    """
    pa = _pmf_wektor(pred_a, max_k)
    pb = _pmf_wektor(pred_b, max_k)
    # skumulowane P(B < k) — liczone narastająco, bez podwójnej pętli
    p_a_wiecej = 0.0
    p_remis = 0.0
    cum_b = 0.0                      # P(B <= k-1)
    for k in range(max_k + 1):
        p_a_wiecej += pa[k] * cum_b
        p_remis += pa[k] * pb[k]
        cum_b += pb[k]
    p_b_wiecej = 0.0
    cum_a = 0.0
    for k in range(max_k + 1):
        p_b_wiecej += pb[k] * cum_a
        cum_a += pa[k]
    suma = p_a_wiecej + p_remis + p_b_wiecej
    if suma <= 0:
        return 0.0, 1.0, 0.0
    return p_a_wiecej / suma, p_remis / suma, p_b_wiecej / suma


def rozklad_sumy(
    pred_a: "MatchPrediction",
    pred_b: "MatchPrediction",
    max_k: int = MAX_ZDARZEN,
) -> list[float]:
    """P(A+B = 0..2*max_k) — splot dwóch rozkładów.

    Suma dwóch rozkładów ujemnych dwumianowych o RÓŻNYM p nie jest ujemnym
    dwumianowym, więc nie ma tu wzoru zamkniętego — liczymy splotem.
    """
    pa = _pmf_wektor(pred_a, max_k)
    pb = _pmf_wektor(pred_b, max_k)
    out = [0.0] * (2 * max_k + 1)
    for i, wa in enumerate(pa):
        if wa <= 0.0:
            continue
        for j, wb in enumerate(pb):
            out[i + j] += wa * wb
    suma = sum(out)
    return [x / suma for x in out] if suma > 0 else out


def p_over_sumy(
    pred_a: "MatchPrediction",
    pred_b: "MatchPrediction",
    line: float,
    max_k: int = MAX_ZDARZEN,
) -> float:
    """P(A+B > linia) — ta sama konwencja co `MatchPrediction.p_over`."""
    rozklad = rozklad_sumy(pred_a, pred_b, max_k)
    prog = int(np.floor(line))
    return float(sum(rozklad[prog + 1:])) if prog + 1 < len(rozklad) else 0.0


# --- PRZEDZIAŁY WIARYGODNOŚCI DLA NOWYCH RYNKÓW (2026-07-31) -----------------
#
# PO CO: brama publikacji rynków drużynowych decyduje o „p OSTROŻNYM"
# (średnia p i dolnej granicy przedziału), a nie o samym p — i to jest
# najmocniejsza część tej bramy. Nowe rynki („kto więcej", sumy meczowe)
# wchodziły na stronę BEZ przedziału, więc nie dało się ich przez tę bramę
# przepuścić: wystawialiśmy je na samym EV. Bez tych dwóch funkcji „dopięcie
# nowych rynków do bram" byłoby udawaniem kontroli, której nie ma.
#
# METODA jest ta sama, co w `p_over_credible_interval` dla jednej drużyny:
# losujemy intensywność z posteriora Gamma i liczymy prawdopodobieństwo
# WARUNKOWO na wylosowanej intensywności (wtedy licznik jest Poissona).
# Rozrzut wyników po losowaniach = niepewność samej estymaty p.
#
# Dwa fakty rachunkowe, dzięki którym jest to tanie i dokładne:
#   * suma niezależnych Poissonów to Poisson o sumie intensywności —
#     przedział dla sumy meczowej nie wymaga splotu,
#   * różnica dwóch Poissonów ma rozkład Skellama — P(A>B) = P(różnica > 0)
#     liczy się wprost, bez podwójnej pętli po wynikach.
#
# UWAGA: te przedziały dziedziczą ZAŁOŻENIE NIEZALEŻNOŚCI obu drużyn
# (patrz komentarz przy `porownanie_druzyn`). Realna korelacja jest ujemna,
# więc przedział sumy jest tu ZA SZEROKI, a przedział porównania — za wąski.
# Kierunek błędu jest po bezpiecznej stronie dokładnie tam, gdzie brama tnie
# (sumy), więc do czasu zmierzenia korelacji to jest ostrożne, nie naiwne.


def _losuj_lambdy(
    posterior: GammaPosterior, exposure: float, rng, n: int
) -> np.ndarray:
    """Wylosowane oczekiwane liczby zdarzeń (intensywność × ekspozycja)."""
    return rng.gamma(
        shape=posterior.alpha, scale=1.0 / posterior.beta, size=n
    ) * max(exposure, 1e-9)


def przedzial_sumy(
    post_a: GammaPosterior,
    exposure_a: float,
    post_b: GammaPosterior,
    exposure_b: float,
    line: float,
    level: float = 0.90,
    n_samples: int = 4000,
    seed: int = 7,
) -> tuple[float, float]:
    """Przedział wiarygodności na P(A+B > linia) — suma meczowa."""
    rng = np.random.default_rng(seed)
    mu = (
        _losuj_lambdy(post_a, exposure_a, rng, n_samples)
        + _losuj_lambdy(post_b, exposure_b, rng, n_samples)
    )
    p_overs = stats.poisson.sf(int(np.floor(line)), mu)
    lo = (1.0 - level) / 2.0
    return float(np.quantile(p_overs, lo)), float(np.quantile(p_overs, 1.0 - lo))


def przedzial_porownania(
    post_a: GammaPosterior,
    exposure_a: float,
    post_b: GammaPosterior,
    exposure_b: float,
    level: float = 0.90,
    n_samples: int = 4000,
    seed: int = 7,
) -> tuple[float, float]:
    """Przedział wiarygodności na P(A > B) — rynek „kto więcej".

    Dla drugiej strony rynku wywołać z zamienionymi argumentami; remis
    zjada część masy po obu stronach, więc P(B>A) NIE jest dopełnieniem
    P(A>B) i nie wolno go liczyć jako 1 − lo/hi.
    """
    rng = np.random.default_rng(seed)
    mu_a = _losuj_lambdy(post_a, exposure_a, rng, n_samples)
    mu_b = _losuj_lambdy(post_b, exposure_b, rng, n_samples)
    # Skellam(mu_a, mu_b) = rozkład różnicy A−B; P(A>B) = P(różnica > 0)
    p_wiecej = stats.skellam.sf(0, mu_a, mu_b)
    lo = (1.0 - level) / 2.0
    return float(np.quantile(p_wiecej, lo)), float(np.quantile(p_wiecej, 1.0 - lo))
