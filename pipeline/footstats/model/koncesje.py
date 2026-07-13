"""Profil rywala per rynek — ile drużyna DOPUSZCZA danej statystyki (per 90).

Automatyzacja ręcznej analizy matchupów: odbiory obrońcy rosną przeciw
drużynie pełnej dryblerów, spalone napastnika przeciw wysokiej linii obrony,
przechwyty przeciw zespołowi grającemu ryzykowne prostopadłe podania.
Zamiast oglądać mecze, liczymy z banku trendów, ile zawodnicy z danego
kubełka pozycji (obrona/pomoc/atak) faktycznie notowali PRZECIWKO tej
drużynie, i porównujemy z normą turnieju dla tego rynku i pozycji.

Wynik zasila MatchContext.opponent_allowed_per90/league_avg_per90 —
istniejący czynnik "rywal" (shrink + cap w context.opponent_factor).
"""

from __future__ import annotations

import math
import time
from collections import defaultdict

from ..sources import eloratings, rotowire

MIN_MINUTY_OBS = 20.0   # występ krótszy niż 20 minut nie mówi nic o rywalu
MIN_OBS_NORMA = 12      # norma turnieju wymaga sensownej próby globalnej
# half-life świeżości obserwacji koncesji — 5x krótszy niż counts.
# DEFAULT_TAU_DAYS (180, skalowane pod CAŁY sezon klubowy): profil koncesji
# żyje tylko w oknie turnieju (tygodnie, nie sezon), więc mecz sprzed 3
# tygodni powinien ważyć wyraźnie mniej niż wczorajszy — ZAŁOŻENIE (jak
# UK_CONSENSUS_MARGIN), nie zmierzone: za mało rozliczeń typów z koncesji,
# żeby to skalibrować jak marżę UK.
KONCESJA_TAU_DAYS = 14.0


def _waga_swiezosci(ts: float, now: float, tau_days: float = KONCESJA_TAU_DAYS) -> float:
    dni = max(now - ts, 0.0) / 86400.0
    return math.exp(-dni / tau_days)


def _waga_podobienstwa(elo_obs: int | None, elo_ref: int | None) -> float:
    """Obserwacja z meczu przeciw drużynie o podobnej sile mówi najwięcej.

    "Norwegia dopuściła obrońcom Brazylii 7 odbiorów" waży pełne 1.0 przed
    meczem z Anglią (podobne Elo), a obserwacja z meczu ze słabeuszem mniej —
    słabszy rywal broni się głębiej / dominuje mniej, więc profil wygląda
    inaczej niż to, co czeka naszego zawodnika.
    """
    if elo_obs is None or elo_ref is None:
        return 0.7                      # brak ratingu = neutralnie, nie zero
    d = abs(elo_obs - elo_ref)
    if d < 150:
        return 1.0
    if d < 300:
        return 0.7
    return 0.4


def kubelek_pozycji(pos: str | None) -> str:
    """RCB/LB/RWB -> obrona, DM/CM/AM -> pomoc, LW/ST/CF -> atak, GK -> ''."""
    p = (pos or "").strip().upper()
    if not p or p in ("G", "GK"):
        return ""
    if p in ("D", "DF") or "B" in p:   # D (statshub) / LB/RB/CB/RCB/LWB/RWB...
        return "obrona"
    if p.endswith("W") or p in ("F", "FW", "ST", "CF", "SS", "LF", "RF"):
        return "atak"
    return "pomoc"                     # M/DM/CM/AM/MF...


class Koncesje:
    """Tabela koncesji: (rywal, rynek, kubełek pozycji) -> obserwacje."""

    def __init__(self) -> None:
        # (druzyna_norm, market, kubelek) -> [(count, minuty, ts, druzyna_notujaca)]
        self._obs: dict[tuple, list] = defaultdict(list)
        # (market, kubelek) -> [(count, minuty)]
        self._base: dict[tuple, list] = defaultdict(list)

    def lookup(
        self,
        druzyna: str,
        market: str,
        pozycja: str | None,
        elo_map: dict[str, int] | None = None,
        team_name: str | None = None,
        now: float | None = None,
    ) -> tuple[float, float, int] | None:
        """(dopuszczane_per90, norma_per90, ~liczba_meczy) albo None.

        elo_map + team_name (drużyna NASZEGO zawodnika): obserwacje ważone
        podobieństwem siły — to, co rywal dopuszczał drużynom podobnej klasy,
        mówi najwięcej o nadchodzącym meczu. `now` (domyślnie: bieżący czas):
        obserwacje ważone też ŚWIEŻOŚCIĄ (KONCESJA_TAU_DAYS) — mecz sprzed 3
        tygodni turnieju liczy się mniej niż wczorajszy, spójnie z resztą
        modelu (counts.fit_posterior, minutes.estimate_minutes).
        """
        kub = kubelek_pozycji(pozycja)
        if not kub:
            return None
        obs = self._obs.get((rotowire._norm(str(druzyna)), market, kub))
        base = self._base.get((market, kub))
        if not obs or not base or len(base) < MIN_OBS_NORMA:
            return None
        now_ts = now if now is not None else time.time()
        elo_ref = (elo_map or {}).get(eloratings._norm(team_name or ""))
        wagi = [
            (_waga_podobienstwa((elo_map or {}).get(eloratings._norm(tn)), elo_ref)
             if elo_map else 1.0) * _waga_swiezosci(ts, now_ts)
            for _, _, ts, tn in obs
        ]
        suma_min = sum(w * m for w, (_, m, _, _) in zip(wagi, obs))
        base_min = sum(m for _, m in base)
        if suma_min < 60.0 or base_min <= 0:
            return None
        allowed = sum(w * c for w, (c, _, _, _) in zip(wagi, obs)) / suma_min * 90.0
        norma = sum(c for c, _ in base) / base_min * 90.0
        if norma <= 0:
            return None
        # próba w "meczach" (do shrinkage), nie w obserwacjach zawodnik-mecz:
        # kilku zawodników z tej samej pozycji w jednym meczu to JEDEN mecz
        n_meczy = len({round(ts / 43200.0) for _, _, ts, _ in obs})
        return allowed, norma, n_meczy


def zbuduj_koncesje(
    trend_lib: dict, wc_names: set[str] | None = None, min_ts: float = 0.0
) -> Koncesje:
    """Zbuduj tabelę z banku trendów.

    wc_names — ZNORMALIZOWANE (rotowire._norm) nazwy uczestników MŚ; mecze
    przeciw drużynom spoza zbioru (klubowe) nie wchodzą do profilu rywala.
    None = bez filtra nazw — WSZYSTKIE mecze wszystkich drużyn od min_ts
    (nie tylko przeciw aktualnym przeciwnikom; norma z całego turnieju).
    min_ts — licz tylko mecze od tego momentu (start turnieju): profil
    "jak ta drużyna broni się NA TYM turnieju", nie sprzed lat; przy MŚ
    sam z siebie odcina mecze klubowe (sezon skończony przed turniejem).
    """
    k = Koncesje()
    for rec in trend_lib.values():
        mk = rec.get("market_code")
        counts = rec.get("counts") or []
        minutes = rec.get("minutes") or []
        opps = rec.get("game_opponents") or []
        poss = rec.get("game_positions") or []
        tss = rec.get("timestamps") or []
        if not mk or not opps:
            continue
        pos_fallback = rec.get("position")
        n = min(len(counts), len(minutes), len(opps), len(tss))
        for i in range(n):
            m = float(minutes[i] or 0)
            if m < MIN_MINUTY_OBS or float(tss[i] or 0) < min_ts:
                continue
            opp_n = rotowire._norm(str(opps[i]))
            if wc_names is not None and opp_n not in wc_names:
                continue
            kub = kubelek_pozycji(
                poss[i] if i < len(poss) and poss[i] else pos_fallback
            )
            if not kub:
                continue
            c = float(counts[i] or 0)
            k._obs[(opp_n, mk, kub)].append(
                (c, m, float(tss[i] or 0), str(rec.get("team_name") or ""))
            )
            k._base[(mk, kub)].append((c, m))
    return k
