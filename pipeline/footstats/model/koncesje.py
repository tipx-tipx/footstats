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

from collections import defaultdict

from ..sources import rotowire

MIN_MINUTY_OBS = 20.0   # występ krótszy niż 20 minut nie mówi nic o rywalu
MIN_OBS_NORMA = 12      # norma turnieju wymaga sensownej próby globalnej


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
        # (druzyna_norm, market, kubelek) -> [(count, minuty, ts)]
        self._obs: dict[tuple, list] = defaultdict(list)
        # (market, kubelek) -> [(count, minuty)]
        self._base: dict[tuple, list] = defaultdict(list)

    def lookup(
        self, druzyna: str, market: str, pozycja: str | None
    ) -> tuple[float, float, int] | None:
        """(dopuszczane_per90, norma_per90, ~liczba_meczy) albo None."""
        kub = kubelek_pozycji(pozycja)
        if not kub:
            return None
        obs = self._obs.get((rotowire._norm(str(druzyna)), market, kub))
        base = self._base.get((market, kub))
        if not obs or not base or len(base) < MIN_OBS_NORMA:
            return None
        suma_min = sum(m for _, m, _ in obs)
        base_min = sum(m for _, m in base)
        if suma_min < 90.0 or base_min <= 0:
            return None
        allowed = sum(c for c, _, _ in obs) / suma_min * 90.0
        norma = sum(c for c, _ in base) / base_min * 90.0
        if norma <= 0:
            return None
        # próba w "meczach" (do shrinkage), nie w obserwacjach zawodnik-mecz:
        # kilku zawodników z tej samej pozycji w jednym meczu to JEDEN mecz
        n_meczy = len({round(ts / 43200.0) for _, _, ts in obs})
        return allowed, norma, n_meczy


def zbuduj_koncesje(
    trend_lib: dict, wc_names: set[str], min_ts: float = 0.0
) -> Koncesje:
    """Zbuduj tabelę z banku trendów.

    wc_names — ZNORMALIZOWANE (rotowire._norm) nazwy uczestników MŚ; mecze
    przeciw drużynom spoza zbioru (klubowe) nie wchodzą do profilu rywala.
    min_ts — licz tylko mecze od tego momentu (start turnieju): profil
    "jak ta drużyna broni się NA TYM turnieju", nie sprzed lat.
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
            if opp_n not in wc_names:
                continue
            kub = kubelek_pozycji(
                poss[i] if i < len(poss) and poss[i] else pos_fallback
            )
            if not kub:
                continue
            c = float(counts[i] or 0)
            k._obs[(opp_n, mk, kub)].append((c, m, float(tss[i] or 0)))
            k._base[(mk, kub)].append((c, m))
    return k
