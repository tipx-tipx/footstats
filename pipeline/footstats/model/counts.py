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

import math
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

    @property
    def wariancja(self) -> float:
        """Var[liczba zdarzeń]. Dla NB(r, p) to r(1−p)/p².

        Potrzebna do korekty korelacji między drużynami (`korelacja_rynku`):
        wkład kowariancji liczy się jako 2ρ·σ_A·σ_B, więc trzeba znać σ
        KAŻDEJ strony osobno, a nie samą sumę intensywności.
        """
        if self.nb_p >= 1.0 or self.nb_p <= 0.0:
            return float(self.lam)
        return float(self.nb_r * (1.0 - self.nb_p) / (self.nb_p ** 2))


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
# ZAŁOŻENIE NIEZALEŻNOŚCI — JUŻ NIE ZAŁOŻENIE, TYLKO ZMIERZONE (2026-08-01).
#
# Oba rachunki traktowały liczby obu drużyn jako niezależne. To nieprawda:
# przebieg meczu wiąże je ze sobą (drużyna dominująca oddaje więcej strzałów,
# rywal mniej). Kierunek był przewidziany poprawnie, ale skala nie była znana,
# więc nie dało się jej naprawić — teraz jest.
#
# POMIAR: pary „obie strony tego samego meczu" z historii drużynowej
# (`druzyny_forma`, parowanie po chwili rozpoczęcia i nazwie rywala).
#
#   rzuty rożne   n=204   r = −0,127   Var(suma) = 11,00   Var(różnicy) = 14,13
#
# Stąd Var(A)+Var(B) = (11,00 + 14,13)/2 = 12,57, czyli wkład kowariancji to
# 2·Cov = −1,57. Przełożenie na nasze dwa rynki jest DOKŁADNIE PRZECIWNE:
#
#   suma meczowa   liczyliśmy 12,57 zamiast 11,00  ->  rozkład o ~14% ZA SZEROKI
#   „kto więcej"   liczyliśmy 12,57 zamiast 14,13  ->  rozkład o ~11% ZA WĄSKI
#
# Co to znaczy dla każdego z rynków — kierunki są PRZECIWNE, warto to przeczytać
# powoli, bo intuicja myli tu prawie każdego (mnie też, złapał to test):
#
#   SUMA: rozkład za szeroki = ogony za grube = zawyżone P(dużo zdarzeń)
#   ORAZ zawyżone P(mało zdarzeń). To są dwa ogony tego samego rozkładu, więc
#   poprawka ścina OBIE strony linii, a nie tylko „powyżej".
#
#   „KTO WIĘCEJ": rozkład różnicy za wąski = za dużo masy dokładnie na zerze
#   = ZAWYŻONY REMIS. A skoro remis zjada masę obu stronom drużynowym,
#   to nasze P(gospodarz więcej) i P(gość więcej) były ZANIŻONE.
#   Poprawka je więc PODNOSI — to jedyne miejsce, gdzie dzisiejsza zmiana
#   luzuje, a nie zaostrza.
#
# JAK TO POPRAWIAMY: nie przez modelowanie pełnego rozkładu łącznego (na to
# nie ma danych), tylko przez DOPASOWANIE DWÓCH PIERWSZYCH MOMENTÓW. Średnia
# zostaje nietknięta, wariancja dostaje brakujący wyraz 2ρ·σ_A·σ_B — ze
# znakiem PLUS przy sumie i MINUS przy różnicy. To jest minimalna poprawka,
# która naprawia zmierzony błąd i nie udaje wiedzy, której nie mamy.
#
# CZEGO NIE MAMY: pomiaru dla strzałów, celnych, fauli i kartek — historia
# drużynowa trzyma dziś tylko rożne (i gole, ale tych jako sumy nie gramy).
# Rynek bez pomiaru dostaje ρ = 0, czyli zachowuje się dokładnie jak dotąd.
# Pomiar powtarza `scripts/zmierz_korelacje.py`.
KORELACJA_DRUZYN: dict[str, float] = {
    "corners": -0.127,   # n=204, 2026-08-01
}


def korelacja_rynku(rynek_kod: str | None) -> float:
    """ρ między drużynami dla rynku (0 = brak pomiaru, liczymy jak dotąd).

    Przyjmuje kod w dowolnej z trzech konwencji: `corners`, `team_corners`,
    `match_corners`, `wiecej_corners` — wszystkie mówią o tej samej parze
    liczb w tym samym meczu.
    """
    kod = str(rynek_kod or "")
    for przedrostek in ("team_", "match_", "wiecej_"):
        if kod.startswith(przedrostek):
            kod = kod[len(przedrostek):]
            break
    return KORELACJA_DRUZYN.get(kod, 0.0)


# Dokąd sumujemy rozkład. Powyżej tego liczby zdarzeń w meczu nie występują,
# a reszta masy i tak trafia do normalizacji.
MAX_ZDARZEN = 40

# Poniżej tej wartości |ρ| korekta jest szumem — nie zawracamy nią głowy
# (i nie ryzykujemy, że dopasowanie momentów wprowadzi własny błąd numeryczny).
MIN_KORELACJA = 0.02


def _pmf_z_momentow(mu: float, war: float, max_k: int) -> list[float]:
    """PMF licznika o zadanej średniej i wariancji, na siatce 0..max_k.

    Trzy przypadki, każdy z rozkładem, który NATURALNIE ma taką relację
    średniej do wariancji — dzięki temu nie trzeba niczego dociskać ręcznie:
      * war > mu  -> ujemny dwumianowy (naddyspersja, tak jak nasze predykcje),
      * war < mu  -> dwumianowy (poddyspersja; Var = np(1−p) < np),
      * war ≈ mu  -> Poisson.
    """
    mu = max(float(mu), 1e-9)
    war = max(float(war), 1e-9)
    ks = np.arange(max_k + 1)
    if war > mu * (1.0 + 1e-6):
        # NB o średniej mu i wariancji war: p = mu/war, r = mu²/(war−mu)
        p = mu / war
        r = mu * p / max(1.0 - p, 1e-9)
        return [float(x) for x in stats.nbinom.pmf(ks, r, p)]
    if war < mu * (1.0 - 1e-6):
        # dwumianowy: p = 1 − war/mu, n = mu/p (zaokrąglone do siatki liczników)
        p = min(max(1.0 - war / mu, 1e-6), 1.0 - 1e-6)
        n = max(int(round(mu / p)), 1)
        p = min(max(mu / n, 1e-9), 1.0 - 1e-9)
        return [float(x) for x in stats.binom.pmf(ks, n, p)]
    return [float(x) for x in stats.poisson.pmf(ks, mu)]


def _sf_z_momentow(prog: int, mu, war):
    """P(X > prog) dla licznika o zadanych momentach — wersja wektorowa.

    Ta sama logika co `_pmf_z_momentow`, ale liczona wprost na tablicach
    (przedziały wiarygodności losują tysiące intensywności naraz, więc pętla
    po próbkach byłaby tu najdroższą rzeczą w całym cyklu).
    """
    mu = np.maximum(np.asarray(mu, dtype=float), 1e-9)
    war = np.maximum(np.asarray(war, dtype=float), 1e-9)
    out = stats.poisson.sf(prog, mu)
    nad = war > mu * (1.0 + 1e-6)
    if np.any(nad):
        p = mu[nad] / war[nad]
        r = mu[nad] * p / np.maximum(1.0 - p, 1e-9)
        out = np.where(nad, np.nan, out)
        out[nad] = stats.nbinom.sf(prog, r, p)
    pod = war < mu * (1.0 - 1e-6)
    if np.any(pod):
        p = np.clip(1.0 - war[pod] / mu[pod], 1e-6, 1.0 - 1e-6)
        n = np.maximum(np.round(mu[pod] / p), 1.0)
        p = np.clip(mu[pod] / n, 1e-9, 1.0 - 1e-9)
        out[pod] = stats.binom.sf(prog, n, p)
    return out


def _pmf_wektor(pred: "MatchPrediction", max_k: int = MAX_ZDARZEN) -> list[float]:
    """P(X=0..max_k) dla jednej drużyny."""
    return [pred.pmf(k) for k in range(max_k + 1)]


def porownanie_druzyn(
    pred_a: "MatchPrediction",
    pred_b: "MatchPrediction",
    max_k: int = MAX_ZDARZEN,
    rho: float = 0.0,
) -> tuple[float, float, float]:
    """(P(A>B), P(remis), P(B>A)) — trzy wyniki rynku „kto więcej".

    Trzy liczby MUSZĄ sumować się do jedynki: to jest cały rynek, a nie linia
    z dwiema stronami. Gdyby się nie sumowały, przewaga policzona wobec kursu
    byłaby zmyślona, a błąd niewidoczny na stronie — dlatego na końcu jest
    jawna normalizacja resztą obciętego ogona.

    `rho` — zmierzona korelacja między drużynami (patrz KORELACJA_DRUZYN).
    Przy ujemnej korelacji rozkład RÓŻNICY jest SZERSZY niż przy niezależności,
    czyli mniej masy siedzi dokładnie na zerze: REMIS ROBI SIĘ RZADSZY, a obie
    strony drużynowe rosną. Liczymy wtedy różnicę wprost rozkładem Skellama
    dopasowanym do średniej i wariancji — Skellam JEST rozkładem różnicy dwóch
    liczników, więc to nie jest przybliżenie kształtu, tylko wybór parametrów.
    """
    if abs(rho) >= MIN_KORELACJA:
        m = pred_a.lam - pred_b.lam
        v = (
            pred_a.wariancja + pred_b.wariancja
            - 2.0 * rho * math.sqrt(
                max(pred_a.wariancja, 0.0) * max(pred_b.wariancja, 0.0)
            )
        )
        # Skellam(mu1, mu2): średnia mu1−mu2, wariancja mu1+mu2
        v = max(v, abs(m) + 1e-6)
        mu1, mu2 = (v + m) / 2.0, (v - m) / 2.0
        p_remis = float(stats.skellam.pmf(0, mu1, mu2))
        p_a = float(stats.skellam.sf(0, mu1, mu2))
        p_b = max(0.0, 1.0 - p_a - p_remis)
        suma = p_a + p_remis + p_b
        if suma <= 0:
            return 0.0, 1.0, 0.0
        return p_a / suma, p_remis / suma, p_b / suma
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
    rho: float = 0.0,
) -> list[float]:
    """P(A+B = 0..2*max_k) — splot dwóch rozkładów.

    Suma dwóch rozkładów ujemnych dwumianowych o RÓŻNYM p nie jest ujemnym
    dwumianowym, więc nie ma tu wzoru zamkniętego — liczymy splotem.

    `rho` — zmierzona korelacja między drużynami (patrz KORELACJA_DRUZYN).
    Splot zakłada niezależność, więc przy ujemnej korelacji daje rozkład ZA
    SZEROKI (zmierzone na rożnych: o ~14%). Wtedy zamiast splotu bierzemy
    rozkład dopasowany do średniej i POPRAWIONEJ wariancji — średnia zostaje
    ta sama, zmienia się tylko grubość ogonów.
    """
    if abs(rho) >= MIN_KORELACJA:
        mu = pred_a.lam + pred_b.lam
        war = (
            pred_a.wariancja + pred_b.wariancja
            + 2.0 * rho * math.sqrt(
                max(pred_a.wariancja, 0.0) * max(pred_b.wariancja, 0.0)
            )
        )
        out = _pmf_z_momentow(mu, war, 2 * max_k)
        reszta = max(0.0, 1.0 - sum(out))
        if out:
            out[-1] += reszta
        return out
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
    rho: float = 0.0,
) -> float:
    """P(A+B > linia) — ta sama konwencja co `MatchPrediction.p_over`."""
    rozklad = rozklad_sumy(pred_a, pred_b, max_k, rho=rho)
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
    rho: float = 0.0,
) -> tuple[float, float]:
    """Przedział wiarygodności na P(A+B > linia) — suma meczowa.

    `rho` wchodzi WARUNKOWO na wylosowaną intensywność: przy znanych λ obie
    liczby są Poissonami, więc wariancja sumy to λ_A+λ_B, a korelacja dokłada
    2ρ√(λ_A·λ_B). Przy ujemnej korelacji robi się z tego rozkład poddyspersyjny
    — stąd dwumianowy zamiast Poissona (patrz `_pmf_z_momentow`).
    """
    rng = np.random.default_rng(seed)
    la = _losuj_lambdy(post_a, exposure_a, rng, n_samples)
    lb = _losuj_lambdy(post_b, exposure_b, rng, n_samples)
    mu = la + lb
    prog = int(np.floor(line))
    if abs(rho) >= MIN_KORELACJA:
        war = np.maximum(mu + 2.0 * rho * np.sqrt(la * lb), 1e-9)
        p_overs = _sf_z_momentow(prog, mu, war)
    else:
        p_overs = stats.poisson.sf(prog, mu)
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
    rho: float = 0.0,
) -> tuple[float, float]:
    """Przedział wiarygodności na P(A > B) — rynek „kto więcej".

    Dla drugiej strony rynku wywołać z zamienionymi argumentami; remis
    zjada część masy po obu stronach, więc P(B>A) NIE jest dopełnieniem
    P(A>B) i nie wolno go liczyć jako 1 − lo/hi.

    `rho` rozszerza rozkład różnicy przy ujemnej korelacji — Skellam zostaje
    Skellamem, zmieniają się tylko jego parametry (dopasowane do średniej
    i poprawionej wariancji różnicy).
    """
    rng = np.random.default_rng(seed)
    mu_a = _losuj_lambdy(post_a, exposure_a, rng, n_samples)
    mu_b = _losuj_lambdy(post_b, exposure_b, rng, n_samples)
    # Skellam(mu_a, mu_b) = rozkład różnicy A−B; P(A>B) = P(różnica > 0)
    if abs(rho) >= MIN_KORELACJA:
        m = mu_a - mu_b
        v = np.maximum(
            mu_a + mu_b - 2.0 * rho * np.sqrt(mu_a * mu_b), np.abs(m) + 1e-6
        )
        p_wiecej = stats.skellam.sf(0, (v + m) / 2.0, (v - m) / 2.0)
    else:
        p_wiecej = stats.skellam.sf(0, mu_a, mu_b)
    lo = (1.0 - level) / 2.0
    return float(np.quantile(p_wiecej, lo)), float(np.quantile(p_wiecej, 1.0 - lo))
