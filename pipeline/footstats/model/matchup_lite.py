"""Matchup-lite dla trybu MŚ — „kto na kogo gra" z danych statshub.

Pełny silnik matchupów (model/matchup.py) potrzebuje danych stylu z Sofascore,
niedostępnych z chmury. Ten moduł odtwarza jego najskuteczniejszą część —
świadomość STRON boiska — z tego, co statshub daje w player-trends:
pozycje per mecz (RW, LB, RCB...) i historię fauli obu drużyn.

Logika (przykład z życia: Mahrez RW vs najczęściej faulujący obrońca LB):
  * faule wywalczone skrzydłowego rosną, gdy naprzeciwko (lustrzana strona)
    gra obrońca faulujący częściej niż koledzy,
  * faule popełnione obrońcy rosną, gdy naprzeciwko gra zawodnik często
    faulowany (dużo pojedynków po tej stronie).

Mnożnik capowany i ważony wielkością próby — sygnał ma dokręcać, nie rządzić.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

CAP = (0.90, 1.15)
# pozycje "obrońcowate" (pełny zapis z recentGames, np. RB, LCB, RCDM)
DEFENSIVE_PREFIXES = ("RB", "LB", "RWB", "LWB", "RCB", "LCB", "CB", "RCDM", "LCDM", "CDM")


@dataclass(frozen=True)
class OppPlayer:
    """Zawodnik rywala z historii statshub: rynek, pozycje, tempo per90."""

    market_code: str
    positions: tuple[str, ...]
    per90: float


def side_of(pos: str | None) -> str:
    """Strona boiska z zapisu pozycji: L / R / C."""
    if not pos:
        return "C"
    p = pos.strip().upper()
    if p.startswith("L"):
        return "L"
    if p.startswith("R"):
        return "R"
    return "C"


def mirror(side: str) -> str:
    """Lustrzana strona: lewy skrzydłowy gra na prawego obrońcę."""
    return {"L": "R", "R": "L"}.get(side, "C")


def dominant_side(positions: list[str] | tuple[str, ...]) -> str:
    """Dominująca strona z ostatnich pozycji (najczęstsza; remis -> C)."""
    sides = [side_of(p) for p in positions if p]
    if not sides:
        return "C"
    cnt = Counter(sides)
    best, n = cnt.most_common(1)[0]
    if list(cnt.values()).count(n) > 1:
        return "C"
    return best


def is_defensive(positions: list[str] | tuple[str, ...]) -> bool:
    """Czy zawodnik gra na pozycji obrończej (wg ostatnich meczów)."""
    hits = sum(
        1 for p in positions if p and p.strip().upper().startswith(DEFENSIVE_PREFIXES)
    )
    return hits >= max(1, len([p for p in positions if p]) // 2)


def _side_ratio(
    opp_players: list[OppPlayer],
    market: str,
    target_side: str,
    defensive_only: bool,
) -> tuple[float, int] | None:
    """Średnie per90 zawodników rywala na danej stronie vs wszyscy — (ratio, n)."""
    pool = [
        p
        for p in opp_players
        if p.market_code == market
        and p.per90 > 0
        and (not defensive_only or is_defensive(p.positions))
    ]
    if len(pool) < 2:
        return None
    at_side = [p.per90 for p in pool if dominant_side(p.positions) == target_side]
    if not at_side:
        return None
    baseline = sum(p.per90 for p in pool) / len(pool)
    if baseline <= 0:
        return None
    return (sum(at_side) / len(at_side)) / baseline, len(at_side)


def matchup_lite_factor(
    market_code: str,
    player_positions: list[str] | tuple[str, ...],
    opp_players: list[OppPlayer],
) -> tuple[float, str]:
    """Mnożnik matchupu strony + opis PL (1.0, "" gdy brak sygnału)."""
    p_side = dominant_side(player_positions)
    if p_side == "C":
        return 1.0, ""
    facing = mirror(p_side)

    if market_code == "fouls_won":
        res = _side_ratio(opp_players, "fouls_committed", facing, defensive_only=True)
        if res is None:
            # za mało obrońców z historią fauli — policz ze wszystkich pozycji
            res = _side_ratio(
                opp_players, "fouls_committed", facing, defensive_only=False
            )
        if res is None:
            return 1.0, ""
        ratio, n = res
    elif market_code == "fouls_committed" and is_defensive(player_positions):
        res = _side_ratio(opp_players, "fouls_won", facing, defensive_only=False)
        if res is None:
            return 1.0, ""
        ratio, n = res
    else:
        return 1.0, ""

    # połowa odchylenia, ważona próbą (1 zawodnik = 50% wagi, 2+ = 100%)
    w = min(n / 2.0, 1.0)
    factor = 1.0 + 0.5 * (ratio - 1.0) * w
    factor = max(CAP[0], min(CAP[1], factor))
    if abs(factor - 1.0) < 0.02:
        return 1.0, ""
    strona_pl = {"L": "lewej", "R": "prawej"}[p_side]
    if market_code == "fouls_won":
        opis = (
            f"Po jego ({strona_pl}) stronie rywal fauluje "
            f"{'częściej' if factor > 1 else 'rzadziej'} niż średnio"
        )
    else:
        opis = (
            f"Po jego ({strona_pl}) stronie gra rywal "
            f"{'często' if factor > 1 else 'rzadko'} faulowany"
        )
    return round(factor, 3), opis
