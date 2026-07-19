"""Silnik scoringu — spina model licznikowy, minuty, kontekst i betting.

Wejście: historia zawodnika + kontekst meczu + linia i kursy.
Wyjście: pełna predykcja z uzasadnieniem po polsku (gotowa do zapisu w DB / UI).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .model import betting, cards, context, counts, matchup, minutes as minutes_mod

RARE_MARKETS = {"sot_outside_box", "headed_shots", "headed_sot", "fh_sot", "offsides"}
DISCIPLINARY_MARKETS = {"fouls_committed", "yellow_card", "team_fouls", "team_cards"}


def _select_bias(market_bias, p: float) -> float:
    """Kalibracja z rozliczeń: skalar-mnożnik (stary format) albo dict
    z przedziałami szansy {"global": g, "bins": [[lo, hi, b], ...]}.
    Dict z "logit": True niesie DELTY LOGITOWE (neutralne = 0.0)."""
    if isinstance(market_bias, dict):
        neutral = 0.0 if market_bias.get("logit") else 1.0
        for lo, hi, b in market_bias.get("bins", []):
            if lo <= p < hi:
                return float(b)
        return float(market_bias.get("global", neutral))
    return float(market_bias)


def apply_bias(market_bias, p: float) -> float:
    """Zastosuj kalibrację do pojedynczej szansy p (poza pełnym scoringiem —
    np. sugestie STS liczone z rozkładu). Obsługuje oba formaty."""
    b = _select_bias(market_bias, p)
    if isinstance(market_bias, dict) and market_bias.get("logit"):
        if abs(b) < 1e-9:
            return float(p)
        x = min(max(float(p), 1e-6), 1.0 - 1e-6)
        return float(1.0 / (1.0 + np.exp(-(np.log(x / (1.0 - x)) + b))))
    return float(min(max(float(p) * b, 0.0), 1.0))


@dataclass
class PlayerHistory:
    """Historia zawodnika dla jednej statystyki (posortowana od najnowszych)."""

    counts: list[float]
    minutes: list[float]
    days_ago: list[float]
    started: list[bool]
    # waga jakości próby per mecz (siła rywala); None = wszystkie równe
    opp_weights: list[float] | None = None
    # mecze wchodzące do posteriora intensywności (True); False = mecz
    # sprzed turnieju, ujęty już w priorze klubowym (bez podwójnego liczenia).
    # Model minut zawsze korzysta z PEŁNEJ historii. None = wszystkie True.
    likelihood_mask: list[bool] | None = None


@dataclass
class MatchContext:
    is_home: bool
    is_favourite: bool
    neutral_venue: bool = False   # turnieje (MŚ/ME): brak efektu dom/wyjazd
    implied_spread: float | None = None
    implied_total: float | None = None
    opponent_allowed_per90: float | None = None   # ile rywal dopuszcza tej statystyki
    league_avg_per90: float | None = None
    opponent_sample_matches: int = 0
    # gotowy opis koncesji rywala z liczbami (model/koncesje.py) do uzasadnienia
    opponent_concession_opis: str = ""
    referee_fouls_multiplier: float | None = None
    # NIEUŻYWANE w trybie MŚ: build_wc_fast.py nigdy go nie ustawia (zawsze
    # None -> referee_factor dostaje neutralne 1.0), bo "yellow_card" nigdy
    # nie pojawia się jako market_code w tym trybie (statshub/365/bank nie
    # generują dla niego trendów, choć Superbet kwotuje kartki — superbet.py).
    # Dopiero gdyby ktoś aktywował rynek kartek w WC, trzeba by go tu wypełnić
    # osobnym profil_sedziow() dla kartek (dziś liczony tylko dla fauli).
    referee_cards_multiplier: float | None = None
    referee_sample_matches: int = 0
    official_started: bool | None = None          # None = skład nieogłoszony
    predicted_started: bool | None = None         # przewidywany skład (miękki sygnał)
    injured_or_suspended: bool = False
    opponent_name: str = ""
    referee_name: str = ""
    # matchup "kto na kogo gra" — profile stylu (patrz model/matchup.py)
    player_style: "matchup.PlayerStyle | None" = None
    opponent_style: "matchup.OpponentStyle | None" = None
    # matchup-lite (tryb MŚ): gotowy mnożnik strony boiska z model/matchup_lite.py
    matchup_factor: float | None = None
    matchup_opis: str = ""


@dataclass
class ScoredMarket:
    market_code: str
    line: float
    lam: float
    p_over: float
    ci_low: float
    ci_high: float
    fair_odds_over: float
    expected_minutes: float
    factors: dict
    assessments: list[betting.ValueAssessment] = field(default_factory=list)
    reasoning: dict = field(default_factory=dict)
    # odrzucenia TUŻ przy progu (betting.NEAR_*) — do rejestru pomiaru progów
    odrzucone: list = field(default_factory=list)


def _build_reasoning(
    market_code: str,
    posterior: counts.GammaPosterior,
    mm: minutes_mod.MinutesModel,
    ctx_factors: context.ContextFactors,
    ctx: MatchContext,
    lam: float,
    prior: counts.GroupPrior | None = None,
) -> dict:
    """Uzasadnienie po polsku — najważniejsze czynniki dla UI."""
    czynniki = []
    # liczby w opisach po polsku (przecinek dziesiętny) — te teksty idą 1:1 do UI
    sr90 = f"{posterior.mean_per90:.2f}".replace(".", ",")
    if prior is not None and prior.source == "klub":
        opis_bazy = (
            f"Średnio {sr90} na 90 minut "
            f"(baza: {prior.pseudo_matches:.0f} meczów sprzed turnieju "
            f"+ {posterior.effective_matches:.0f} na turnieju)"
        )
    else:
        opis_bazy = (
            f"Średnio {sr90} na 90 minut "
            f"(efektywna próba: {posterior.effective_matches:.0f} meczów)"
        )
    czynniki.append({"nazwa": "Poziom bazowy", "opis": opis_bazy, "mnoznik": None})
    czynniki.append(
        {
            "nazwa": "Minuty",
            "opis": (
                "Skład ogłoszony: pewny występ" if mm.official_lineup and mm.p_start > 0.5
                else "Skład ogłoszony: zawodnik poza XI (możliwe wejście z ławki)"
                if mm.official_lineup
                else f"Przewidywane {mm.expected_minutes:.0f} min gry, "
                f"{mm.p_start * 100:.0f}% szans na pierwszy skład"
                + (" (wg przewidywanego składu)" if ctx.predicted_started is not None else "")
            ),
            "mnoznik": round(mm.expected_minutes / 90.0, 2),
        }
    )
    if abs(ctx_factors.opponent - 1.0) > 0.02 and ctx.opponent_name:
        kier = "więcej" if ctx_factors.opponent > 1 else "mniej"
        czynniki.append(
            {
                "nazwa": "Profil rywala",
                "opis": ctx.opponent_concession_opis
                or f"{ctx.opponent_name} dopuszcza {kier} takich akcji niż średnia ligi",
                "mnoznik": round(ctx_factors.opponent, 2),
            }
        )
    if abs(ctx_factors.referee - 1.0) > 0.02 and ctx.referee_name:
        kier = "surowy" if ctx_factors.referee > 1 else "pobłażliwy"
        czynniki.append(
            {
                "nazwa": "Sędzia",
                "opis": f"{ctx.referee_name}: {kier} (vs średnia ligi)",
                "mnoznik": round(ctx_factors.referee, 2),
            }
        )
    if abs(ctx_factors.game_script - 1.0) > 0.02:
        czynniki.append(
            {
                "nazwa": "Scenariusz meczu",
                "opis": "Z kursów meczowych: przewidywany przebieg sprzyja"
                if ctx_factors.game_script > 1
                else "Z kursów meczowych: przewidywany przebieg nie sprzyja",
                "mnoznik": round(ctx_factors.game_script, 2),
            }
        )
    if abs(ctx_factors.matchup - 1.0) > 0.02:
        default = (
            "Styl tego rywala sprzyja temu rynkowi"
            if ctx_factors.matchup > 1
            else "Styl tego rywala nie sprzyja temu rynkowi"
        )
        czynniki.append(
            {
                "nazwa": "Matchup (kto na kogo)",
                "opis": ctx_factors.notes.get("matchup", default),
                "mnoznik": round(ctx_factors.matchup, 2),
            }
        )
    if not ctx.neutral_venue:
        czynniki.append(
            {
                "nazwa": "Dom / wyjazd",
                "opis": "Mecz u siebie" if ctx.is_home else "Mecz na wyjeździe",
                "mnoznik": round(ctx_factors.home_away, 2),
            }
        )
    return {
        "czynniki": czynniki,
        "oczekiwana_liczba": round(lam, 2),
        "rynek_rzadki": market_code in RARE_MARKETS,
    }


def score_player_market(
    market_code: str,
    line: float,
    history: PlayerHistory,
    group_prior: counts.GroupPrior,
    ctx: MatchContext,
    over_odds: float | None = None,
    under_odds: float | None = None,
    market_calibrated: bool = False,
    card_conversion: float | None = None,
    market_bias: float | dict = 1.0,
) -> ScoredMarket:
    """Pełny scoring jednego rynku zawodnika dla jednego meczu.

    market_bias — kalibracja z ROZLICZONYCH typów (jobs/rozliczanie.py):
    zmierzone odchylenie rzeczywistej częstości od szans modelu na tym rynku.
    """

    # 1) posterior bazowej intensywności per-90 — tylko mecze z maski
    # likelihood (mecze sprzed turnieju siedzą w priorze klubowym)
    lm = (
        np.array(history.likelihood_mask, dtype=bool)
        if history.likelihood_mask
        and len(history.likelihood_mask) == len(history.counts)
        else np.ones(len(history.counts), dtype=bool)
    )
    ow = (
        np.array(history.opp_weights)[lm]
        if history.opp_weights and len(history.opp_weights) == len(history.counts)
        else None
    )
    posterior = counts.fit_posterior(
        np.array(history.counts)[lm],
        np.array(history.minutes)[lm],
        np.array(history.days_ago)[lm],
        prior=group_prior,
        extra_weights=ow,
    )

    # 2) model minut
    mm = minutes_mod.estimate_minutes(
        recent_started=history.started,
        recent_minutes=history.minutes,
        days_ago=history.days_ago,
        injured_or_suspended=ctx.injured_or_suspended,
        official_started=ctx.official_started,
        predicted_started=ctx.predicted_started,
    )

    # 3) czynniki kontekstowe
    cf = context.ContextFactors(
        opponent=context.opponent_factor(
            ctx.opponent_allowed_per90 or (ctx.league_avg_per90 or 1.0),
            ctx.league_avg_per90 or 1.0,
            ctx.opponent_sample_matches,
        ),
        referee=context.referee_factor(
            ctx.referee_fouls_multiplier
            if market_code != "yellow_card"
            else ctx.referee_cards_multiplier,
            ctx.referee_sample_matches,
            market_is_disciplinary=market_code in DISCIPLINARY_MARKETS,
        ),
        home_away=1.0 if ctx.neutral_venue
        else context.home_away_factor(ctx.is_home, market_code),
        game_script=context.game_script_factor(
            ctx.implied_spread, ctx.implied_total, market_code, ctx.is_favourite
        ),
    )

    # 3b) matchup "kto na kogo gra" — mnożnik stylu rywala i zawodnika
    if ctx.player_style is not None and ctx.opponent_style is not None:
        mf, matchup_opis = matchup.matchup_factor(
            market_code=market_code,
            player=ctx.player_style,
            opp=ctx.opponent_style,
            is_favourite=ctx.is_favourite,
        )
        cf.matchup = mf
        if matchup_opis:
            cf.notes["matchup"] = matchup_opis
    elif ctx.matchup_factor is not None:
        # matchup-lite (tryb MŚ): mnożnik strony boiska policzony ze statshub
        cf.matchup = ctx.matchup_factor
        if ctx.matchup_opis:
            cf.notes["matchup"] = ctx.matchup_opis

    # 4) P(over) jako mieszanka po scenariuszach minutowych
    if market_code == "yellow_card":
        q = card_conversion if card_conversion is not None else cards.LEAGUE_CARD_PER_FOUL
        ref_mult = ctx.referee_cards_multiplier or 1.0

        def p_over_given_minutes(mins: float) -> float:
            pred = counts.predict_match(posterior, mins, cf.combined)
            return cards.p_yellow_card(pred.lam, q, ref_mult)

        pred_center = counts.predict_match(posterior, mm.expected_minutes, cf.combined)
        lam = cards.p_yellow_card(pred_center.lam, q, ref_mult)  # tu lam = P w [0,1]
    else:

        def p_over_given_minutes(mins: float) -> float:
            return counts.predict_match(posterior, mins, cf.combined).p_over(line)

        pred_center = counts.predict_match(posterior, mm.expected_minutes, cf.combined)
        lam = pred_center.lam

    p_over = minutes_mod.p_over_mixture(mm, p_over_given_minutes)
    # samokalibracja z rozliczeń: nowy format = delta logitowa
    # (p' = sigmoid(logit(p)+b), równa korekta w całej skali), stary = mnożnik
    bias = _select_bias(market_bias, p_over)
    logit_mode = isinstance(market_bias, dict) and bool(market_bias.get("logit"))
    neutral = (abs(bias) < 1e-9) if logit_mode else (bias == 1.0)

    def _kalibruj(x: float) -> float:
        x = float(np.clip(x, 1e-4, 1.0 - 1e-4))
        if logit_mode:
            return float(1.0 / (1.0 + np.exp(-(np.log(x / (1.0 - x)) + bias))))
        return float(np.clip(x * bias, 1e-4, 1.0 - 1e-4))

    if not neutral:
        p_przed = p_over
        p_over = _kalibruj(p_over)
        eff = p_over / max(p_przed, 1e-9)
        eff_s = f"{eff:.2f}".replace(".", ",")
        cf.notes["kalibracja"] = (
            f"Korekta z rozliczonych typów: ×{eff_s} "
            f"({'model niedoszacowywał' if eff > 1 else 'model przeszacowywał'})"
        )
    p_over = float(np.clip(p_over, 1e-4, 1.0 - 1e-4))

    # 5) przedział wiarygodności (na centrum minutowym)
    ci_low, ci_high = counts.p_over_credible_interval(
        posterior, mm.expected_minutes, cf.combined, line
    )
    if not neutral:
        # CI w tej samej skali co skalibrowane p — karta pokazuje spójne liczby
        ci_low, ci_high = _kalibruj(ci_low), _kalibruj(ci_high)
    if market_code == "yellow_card":
        # dla kartek CI liczymy uproszczeniowo wokół p_over
        half = (ci_high - ci_low) / 2.0 if ci_high > ci_low else 0.08
        ci_low, ci_high = max(0.0, p_over - half), min(1.0, p_over + half)

    # 6) ocena bettingowa
    conf_inputs = betting.ConfidenceInputs(
        effective_matches=posterior.effective_matches,
        minutes_certainty=mm.certainty,
        ci_width=max(ci_high - ci_low, 0.0),
        context_magnitude=abs(cf.combined - 1.0),
        market_calibrated=market_calibrated,
        is_rare_market=market_code in RARE_MARKETS,
    )
    odrzucone_przy_progu: list = []
    assessments = betting.assess(
        p_over, over_odds, under_odds, conf_inputs, lam,
        is_prob_market=(market_code == "yellow_card"),
        odrzucone_out=odrzucone_przy_progu,
    )

    return ScoredMarket(
        market_code=market_code,
        line=line,
        lam=round(float(lam), 3),
        p_over=round(p_over, 4),
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
        fair_odds_over=round(1.0 / p_over, 3),
        expected_minutes=round(mm.expected_minutes, 1),
        factors=cf.as_dict(),
        assessments=assessments,
        reasoning=_build_reasoning(market_code, posterior, mm, cf, ctx, lam,
                                   prior=group_prior),
        odrzucone=odrzucone_przy_progu,
    )
