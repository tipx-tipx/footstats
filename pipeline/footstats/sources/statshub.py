"""Źródło danych: statshub.com — SZYBKA ŚCIEŻKA (otwarte API, bez limitów).

Odkrycie (2026-07-02): statshub jest zbudowany na tych samych ID co Sofascore,
ale jego API jest OTWARTE (nie dławi ruchu jak bezpośredni Sofascore) i zwraca
dane już zagregowane. Endpoint `/api/props/player-trends?games=...` daje dla
każdej pary (zawodnik, rynek, linia) w jednym zapytaniu:

  * recentGames — pełną historię mecz-po-meczu (statValue, minuty, rywal, u siebie),
  * leagueAverage / opponentAverage / opponentRank — gotowy kontekst rywala,
  * inPredictedLineup — przewidywany skład,
  * line + bookmakers — linie i kursy (bukmacherzy UK, orientacyjnie).

To zastępuje: backfill per-mecz z Sofascore, własne liczenie średnich rywala
i pobieranie składów — dla 5 rynków rdzeniowych.

OGRANICZENIA:
  * pokrywa tylko 5 rynków: strzały, celne, faule, odbiory, faule wywalczone
    (rynki z map strzałów — zza pola, głową, zablokowane, niecelne — dalej
    pochodzą z shotmap Sofascore),
  * propsy ładują się ~24-48 h przed meczem (wcześniej feed jest pusty).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from curl_cffi import requests

BASE = "https://www.statshub.com/api"
HEADERS = {"Accept": "application/json", "Referer": "https://www.statshub.com/"}

# statType statshub -> nasz kod rynku
STATTYPE_MAP = {
    "shots": "shots",
    "onTargetScoringAttempt": "sot",
    "fouls": "fouls_committed",
    "totalTackle": "tackles",
    "wasFouled": "fouls_won",
}


def _get(url: str, timeout: int = 30) -> dict:
    r = requests.get(url, impersonate="chrome124", timeout=timeout, headers=HEADERS)
    r.raise_for_status()
    return r.json()


@dataclass
class StatshubTrend:
    """Jeden rekord trendu: (zawodnik, rynek, linia) z historią i kontekstem."""

    player_id: int
    player_name: str
    position: str | None
    team_id: int
    team_name: str
    opponent_id: int
    opponent_name: str
    is_home: bool
    market_code: str
    line: float
    in_predicted_lineup: bool
    league_average: float | None
    opponent_average: float | None
    opponent_rank: int | None
    total_ranks: int | None
    # historia: listy równoległe (od najnowszych)
    counts: list[float] = field(default_factory=list)
    minutes: list[float] = field(default_factory=list)
    timestamps: list[int] = field(default_factory=list)
    started: list[bool] = field(default_factory=list)
    # kursy referencyjne (UK) — do sanity-checku, nie do rozliczeń
    ref_odds: list[float] = field(default_factory=list)


def fetch_event_trends(event_ids: list[int]) -> list[StatshubTrend]:
    """Pobierz trendy propsów dla podanych meczów (jedno zapytanie).

    Zwraca pustą listę, jeśli propsy nie są jeszcze wystawione (za wcześnie).
    """
    if not event_ids:
        return []
    games = ",".join(str(e) for e in event_ids)
    data = _get(f"{BASE}/props/player-trends?games={games}").get("data", [])
    out: list[StatshubTrend] = []
    for rec in data:
        mk = STATTYPE_MAP.get(rec.get("statType"))
        if mk is None:
            continue
        rg = rec.get("recentGames", [])
        # minutesPlayed>0 => zagrał; started przybliżamy przez minuty (>60 ~ start)
        out.append(
            StatshubTrend(
                player_id=rec["playerId"],
                player_name=rec["playerName"],
                position=(rec.get("position") or "M")[:1],
                team_id=rec.get("teamId"),
                team_name=rec.get("teamName", ""),
                opponent_id=rec.get("opponentTeamId"),
                opponent_name=rec.get("opponentTeamName", ""),
                is_home=rec.get("homeTeamId") == rec.get("teamId"),
                market_code=mk,
                line=float(rec.get("line", 0.5)),
                in_predicted_lineup=bool(rec.get("inPredictedLineup")),
                league_average=rec.get("leagueAverage"),
                opponent_average=rec.get("opponentAverage"),
                opponent_rank=rec.get("opponentRank"),
                total_ranks=rec.get("totalRanks"),
                counts=[float(g.get("statValue") or 0) for g in rg],
                minutes=[float(g.get("minutesPlayed") or 0) for g in rg],
                timestamps=[int(g.get("eventTimestamp") or 0) for g in rg],
                started=[float(g.get("minutesPlayed") or 0) >= 60 for g in rg],
                ref_odds=[
                    float(b["oddsValue"])
                    for b in rec.get("bookmakers", [])
                    if b.get("oddsValue")
                ],
            )
        )
    return out


def props_available(event_id: int) -> bool:
    """Czy statshub ma już wystawione propsy dla meczu (feed niepusty)."""
    try:
        return len(fetch_event_trends([event_id])) > 0
    except Exception:
        return False
