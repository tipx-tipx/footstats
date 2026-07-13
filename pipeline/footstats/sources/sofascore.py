"""Źródło danych: Sofascore (nieoficjalne API) — kręgosłup systemu.

Zweryfikowane endpointy (2026-07-02):
  * /unique-tournament/{tid}/seasons                       — sezony ligi
  * /unique-tournament/{tid}/season/{sid}/events/last/{p}  — mecze sezonu (stronicowane)
  * /event/{eid}                                           — szczegóły meczu (sędzia, wynik)
  * /event/{eid}/lineups                                   — składy + statystyki zawodników
  * /event/{eid}/shotmap                                   — strzały (współrzędne, część ciała, minuta)
  * /event/{eid}/statistics                                — statystyki drużynowe

Uwagi:
  * to nieoficjalne API — zawsze uruchamiać lokalnie, powoli, z cache;
  * bukmacherzy rozliczają propsy wg Opta; Sofascore też bazuje na Opta,
    więc definicje (odbiory, przechwyty) są zgodne z rozliczeniem zakładów.

STATUS: NIEUŻYWANE w cyklu chmurowym (jobs/cycle.py -> build_wc_fast.py, tryb
produkcyjny "ms2026") — Sofascore blokuje IP serwerowni/datacenter (zweryfikowane
empirycznie), więc RateLimitedClient stąd działa TYLKO lokalnie (domowe IP).
Cykl chmurowy MŚ jedzie na statshub+365Scores+Superbet (patrz build_wc_fast.py
nagłówek). Ten moduł żyje w jobs/backfill.py (lokalny, jednorazowy zasiew
danych ligowych do build_demo.py) — wróci do gry przy trybie ligowym na
domowym IP/Pi (patrz PLAN.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from ..http_client import RateLimitedClient

BASE = "https://api.sofascore.com/api/v1"

# unique_tournament_id lig w Sofascore (top 5 na start; rozszerzenie = dopisanie wpisu)
TOURNAMENTS = {
    "EPL": 17,
    "LALIGA": 8,
    "SERIE_A": 23,
    "BUNDESLIGA": 35,
    "LIGUE_1": 34,
    "WC": 16,          # Mistrzostwa Świata
}

# Sofascore: układ współrzędnych strzałów (zweryfikowany empirycznie na xG):
# playerCoordinates.x = odległość od linii bramkowej PRZECIWNIKA (0 = bramka),
# w % długości boiska (105 m). playerCoordinates.y = pozycja w poprzek (50 = środek),
# w % szerokości boiska (68 m).
# Pole karne: 16,5 m w głąb (x <= 15.71) i 40,32 m szerokości (y w [20.4, 79.6]).
BOX_X_MAX = (16.5 / 105.0) * 100.0                    # ~15.71
BOX_Y_HALF = (40.32 / 2.0) / 68.0 * 100.0             # ~29.65
BOX_Y_MIN = 50.0 - BOX_Y_HALF                          # ~20.35
BOX_Y_MAX = 50.0 + BOX_Y_HALF                          # ~79.65


def is_outside_box(x: float | None, y: float | None) -> bool | None:
    if x is None or y is None:
        return None
    inside = x <= BOX_X_MAX and BOX_Y_MIN <= y <= BOX_Y_MAX
    return not inside


@dataclass
class PlayerMatchRow:
    """Znormalizowany wiersz statystyk zawodnika w meczu."""

    sofascore_player_id: int
    player_name: str
    position: str | None
    team_sofascore_id: int
    started: bool
    minutes: int
    shots: int = 0
    shots_on_target: int = 0
    fouls_committed: int = 0
    fouls_won: int = 0
    tackles: int = 0
    interceptions: int = 0
    offsides: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    # uzupełniane z shotmapy:
    shots_outside_box: int = 0
    sot_outside_box: int = 0
    headed_shots: int = 0
    headed_sot: int = 0
    fh_shots: int = 0
    fh_sot: int = 0
    shots_blocked: int = 0      # strzały zawodnika zablokowane przez obrońców
    shots_off_target: int = 0   # strzały niecelne (obok + słupek/poprzeczka)
    # dane stylu gry — pod silnik matchupów (kto na kogo gra)
    contests: int = 0           # próby dryblingu (totalContest) — miara "kiwania"
    contests_won: int = 0       # udane drybling (wonContest)
    duels_won: int = 0
    aerial_won: int = 0         # wygrane pojedynki powietrzne
    aerial_lost: int = 0        # przegrane w powietrzu (słabość przy grze głową)
    crosses: int = 0            # dośrodkowania (totalCross)
    long_balls: int = 0         # długie podania (totalLongBalls) — gra direct
    dribbled_past: int = 0      # ile razy ograny 1v1 (challengeLost)
    key_passes: int = 0
    touches: int = 0
    clearances: int = 0
    height: int = 0             # wzrost zawodnika (cm) — target man
    detailed_position: str = "" # np. 'LB','RW' gdy dostępne (statshub), inaczej litera
    setpiece_shots: int = 0     # strzały ze stałych fragmentów/karnych — egzekutor


@dataclass
class MatchBundle:
    """Wszystko, co pobieramy dla jednego meczu."""

    event: dict
    player_rows: list[PlayerMatchRow] = field(default_factory=list)
    team_stats: dict = field(default_factory=dict)   # team_id -> {stat: wartość}
    shotmap: list[dict] = field(default_factory=list)


class SofascoreSource:
    def __init__(self, client: RateLimitedClient | None = None):
        self.client = client or RateLimitedClient()

    # -- terminarze ---------------------------------------------------------

    def seasons(self, tournament_id: int) -> list[dict]:
        d = self.client.get_json(f"{BASE}/unique-tournament/{tournament_id}/seasons")
        return d.get("seasons", [])

    def find_season_id(self, tournament_id: int, year_label: str) -> int | None:
        """year_label np. '25/26'."""
        for s in self.seasons(tournament_id):
            if s.get("year") == year_label:
                return s["id"]
        return None

    def season_events(
        self, tournament_id: int, season_id: int, finished_only: bool = True
    ) -> Iterator[dict]:
        """Wszystkie mecze sezonu (stronicowane po 30)."""
        page = 0
        while True:
            try:
                d = self.client.get_json(
                    f"{BASE}/unique-tournament/{tournament_id}/season/{season_id}/events/last/{page}"
                )
            except LookupError:
                return
            events = d.get("events", [])
            for ev in events:
                status = ev.get("status", {}).get("type")
                if finished_only and status != "finished":
                    continue
                yield ev
            if not d.get("hasNextPage"):
                return
            page += 1

    def upcoming_events(self, tournament_id: int, season_id: int) -> list[dict]:
        """Nadchodzące mecze sezonu."""
        out = []
        page = 0
        while True:
            try:
                d = self.client.get_json(
                    f"{BASE}/unique-tournament/{tournament_id}/season/{season_id}/events/next/{page}",
                    use_cache=False,
                )
            except LookupError:
                break
            out.extend(d.get("events", []))
            if not d.get("hasNextPage"):
                break
            page += 1
        return out

    # -- pojedynczy mecz ----------------------------------------------------

    def event_details(self, event_id: int, use_cache: bool = True) -> dict:
        return self.client.get_json(f"{BASE}/event/{event_id}", use_cache=use_cache)["event"]

    def fetch_match(self, event_id: int) -> MatchBundle:
        """Pobierz komplet danych meczu zakończonego."""
        event = self.event_details(event_id)
        bundle = MatchBundle(event=event)

        # 1) składy + statystyki zawodników
        try:
            lineups = self.client.get_json(f"{BASE}/event/{event_id}/lineups")
        except LookupError:
            lineups = {}
        for side in ("home", "away"):
            team = event.get(f"{side}Team", {})
            for p in lineups.get(side, {}).get("players", []):
                st = p.get("statistics") or {}
                minutes = int(st.get("minutesPlayed") or 0)
                bundle.player_rows.append(
                    PlayerMatchRow(
                        sofascore_player_id=p["player"]["id"],
                        player_name=p["player"]["name"],
                        position=p.get("position"),
                        team_sofascore_id=team.get("id"),
                        started=not p.get("substitute", False),
                        minutes=minutes,
                        shots=int(st.get("totalShots") or (st.get("onTargetScoringAttempt") or 0) + (st.get("shotOffTarget") or 0) + (st.get("blockedScoringAttempt") or 0)),
                        shots_on_target=int(st.get("onTargetScoringAttempt") or 0),
                        fouls_committed=int(st.get("fouls") or 0),
                        fouls_won=int(st.get("wasFouled") or 0),
                        tackles=int(st.get("totalTackle") or 0),
                        interceptions=int(st.get("interceptionWon") or 0),
                        offsides=int(st.get("totalOffside") or 0),
                        contests=int(st.get("totalContest") or 0),
                        contests_won=int(st.get("wonContest") or 0),
                        duels_won=int(st.get("duelWon") or 0),
                        aerial_won=int(st.get("aerialWon") or 0),
                        aerial_lost=int(st.get("aerialLost") or 0),
                        crosses=int(st.get("totalCross") or 0),
                        long_balls=int(st.get("totalLongBalls") or 0),
                        dribbled_past=int(st.get("challengeLost") or 0),
                        key_passes=int(st.get("keyPass") or 0),
                        touches=int(st.get("touches") or 0),
                        clearances=int(st.get("totalClearance") or 0),
                        height=int((p.get("player") or {}).get("height") or 0),
                        detailed_position=p.get("position") or "",
                    )
                )

        # 2) kartki z incydentów (bardziej wiarygodne niż statystyki zawodnika)
        try:
            incidents = self.client.get_json(f"{BASE}/event/{event_id}/incidents").get(
                "incidents", []
            )
        except LookupError:
            incidents = []
        cards: dict[int, dict[str, int]] = {}
        for inc in incidents:
            if inc.get("incidentType") != "card":
                continue
            pid = (inc.get("player") or {}).get("id")
            if pid is None:
                continue
            slot = cards.setdefault(pid, {"yellow": 0, "red": 0})
            klass = inc.get("incidentClass")
            if klass in ("yellow", "yellowRed"):
                slot["yellow"] += 1
            if klass in ("red", "yellowRed"):
                slot["red"] += 1
        for row in bundle.player_rows:
            c = cards.get(row.sofascore_player_id)
            if c:
                row.yellow_cards = c["yellow"]
                row.red_cards = c["red"]

        # 3) shotmapa -> rynki pochodne strzałów
        try:
            bundle.shotmap = self.client.get_json(f"{BASE}/event/{event_id}/shotmap").get(
                "shotmap", []
            )
        except LookupError:
            bundle.shotmap = []
        by_player = {r.sofascore_player_id: r for r in bundle.player_rows}
        for shot in bundle.shotmap:
            pid = (shot.get("player") or {}).get("id")
            row = by_player.get(pid)
            if row is None:
                continue
            coords = shot.get("playerCoordinates") or {}
            outside = is_outside_box(coords.get("x"), coords.get("y"))
            on_target = shot.get("shotType") in ("goal", "save")  # gol lub obroniony = celny
            headed = shot.get("bodyPart") == "head"
            minute = shot.get("time") or 0

            if outside:
                row.shots_outside_box += 1
                if on_target:
                    row.sot_outside_box += 1
            if headed:
                row.headed_shots += 1
                if on_target:
                    row.headed_sot += 1
            if minute <= 45:
                row.fh_shots += 1
                if on_target:
                    row.fh_sot += 1
            if shot.get("shotType") == "block":
                row.shots_blocked += 1
            if shot.get("shotType") in ("miss", "post"):
                row.shots_off_target += 1
            if shot.get("situation") in (
                "penalty", "free-kick", "corner", "throw-in-set-piece"
            ):
                row.setpiece_shots += 1

        # 4) statystyki drużynowe
        try:
            stats = self.client.get_json(f"{BASE}/event/{event_id}/statistics")
        except LookupError:
            stats = {"statistics": []}
        for period in stats.get("statistics", []):
            if period.get("period") != "ALL":
                continue
            for group in period.get("groups", []):
                for item in group.get("statisticsItems", []):
                    name = item.get("name")
                    for side, team_key in (("home", "homeTeam"), ("away", "awayTeam")):
                        team_id = event.get(team_key, {}).get("id")
                        slot = bundle.team_stats.setdefault(team_id, {})
                        val = item.get(f"{side}Value", item.get(side))
                        if name and val is not None:
                            slot[name] = val

        return bundle
