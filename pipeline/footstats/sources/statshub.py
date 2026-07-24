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


def _get(url: str, timeout: int = 25, retries: int = 3) -> dict:
    """GET z retry — statshub bywa chwilowo wolny/niedostępny (zwłaszcza z chmury)."""
    import time as _t

    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, impersonate="chrome124", timeout=timeout, headers=HEADERS)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # timeout, 5xx, itp.
            last = e
            _t.sleep(3 * (attempt + 1))
    raise last


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
    event_id: int = 0
    odds_type: str = "over"  # strona, której dotyczą line i ref_odds
    # historia: listy równoległe (od najnowszych)
    counts: list[float] = field(default_factory=list)
    minutes: list[float] = field(default_factory=list)
    timestamps: list[int] = field(default_factory=list)
    started: list[bool] = field(default_factory=list)
    # pozycje per mecz (RW, LB, RCB...) — pod matchup-lite stron boiska
    game_positions: list[str] = field(default_factory=list)
    # rywal per mecz — do formy w UI i ważenia próby siłą rywala
    game_opponents: list[str] = field(default_factory=list)
    # id rywala per mecz — radar: mecz PRZECIW obecnej drużynie w historii
    # = zawodnik grał wtedy gdzie indziej (transfer wewnątrz ligi)
    game_opponent_ids: list[int] = field(default_factory=list)
    # rozgrywki per mecz (uniqueTournamentId) — radar wykrywa z tego zmianę
    # ligi/klubu (historia podąża za ZAWODNIKIEM, nie klubem)
    game_utids: list[int] = field(default_factory=list)
    # ile meczów temu ostatni występ w OBECNEJ drużynie (activityInfo feedu;
    # None = feed nie podał). Semantyka niepewna (sonda 2026-07-22), radar
    # traktuje wyłącznie jako sygnał pomocniczy.
    last_game_with_team: int | None = None
    # kursy referencyjne bukmacherów UK dla linii `line` (Bet365, WH, ...)
    ref_odds: list[float] = field(default_factory=list)


def fetch_event_trends(event_ids: list[int]) -> list[StatshubTrend]:
    """Pobierz trendy propsów dla podanych meczów (Z PAGINACJĄ).

    PUŁAPKA zmierzona 2026-07-20: endpoint jest stronicowany z domyślnym
    pageSize=25 — bez iterowania po stronach feed jest CICHO ucinany do
    25 rekordów niezależnie od liczby meczów (a `limit=` jest ignorowany).
    Działa pageSize + page; bierzemy pageSize=100 i idziemy do wyczerpania.

    Zwraca pustą listę, jeśli propsy nie są jeszcze wystawione (za wcześnie).
    """
    if not event_ids:
        return []
    games = ",".join(str(e) for e in event_ids)
    data: list[dict] = []
    page = 1
    PAGE_SIZE = 100
    while True:
        czesc = _get(
            f"{BASE}/props/player-trends?games={games}"
            f"&pageSize={PAGE_SIZE}&page={page}"
        ).get("data", [])
        data += czesc
        # bezpiecznik 40 stron = 4000 rekordów; realnie kilkaset
        if len(czesc) < PAGE_SIZE or page >= 40:
            break
        page += 1
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
                event_id=int(rec.get("eventId") or 0),
                odds_type=str(rec.get("oddsType") or "over"),
                league_average=rec.get("leagueAverage"),
                opponent_average=rec.get("opponentAverage"),
                opponent_rank=rec.get("opponentRank"),
                total_ranks=rec.get("totalRanks"),
                counts=[float(g.get("statValue") or 0) for g in rg],
                minutes=[float(g.get("minutesPlayed") or 0) for g in rg],
                timestamps=[int(g.get("eventTimestamp") or 0) for g in rg],
                started=[float(g.get("minutesPlayed") or 0) >= 60 for g in rg],
                game_positions=[str(g.get("position") or "") for g in rg],
                game_opponents=[str(g.get("opponentName") or "") for g in rg],
                game_opponent_ids=[int(g.get("opponentId") or 0) for g in rg],
                game_utids=[int(g.get("uniqueTournamentId") or 0) for g in rg],
                last_game_with_team=(rec.get("activityInfo") or {}).get(
                    "lastGameWithTeam"
                ),
                ref_odds=[
                    float(b["oddsValue"])
                    for b in rec.get("bookmakers", [])
                    if b.get("oddsValue")
                ],
            )
        )
    return out


def fetch_predicted_lineup(event_id: int) -> dict:
    """Przewidywane XI OBU drużyn: {'home': [pid...], 'away': [...], 'confirmed': bool}.

    Endpoint NIEUDOKUMENTOWANY (podejrzany w XHR strony fixture 2026-07-20):
    pełne 11/11 już ~36 h przed meczem dla lig z pokryciem propsów
    (Brasileirão tak; egzotyka typu Finlandia/Bułgaria bywa pusta do końca).
    Dużo pewniejsze niż migotliwa flaga inPredictedLineup w player-trends.
    """
    d = _get(f"{BASE}/event/{event_id}/predicted-teams-lineup")
    d = d.get("data", d) or {}
    out: dict = {"home": [], "away": [], "confirmed": False}
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        for p in ((d.get(key) or {}).get("data")) or []:
            pid = p.get("playerId")
            if pid:
                out[side].append(int(pid))
            if str(p.get("predictionType") or "") == "confirmed":
                out["confirmed"] = True
    return out


def fetch_team_lineup(event_id: int, team_id: int) -> list[int]:
    """Oficjalny skład drużyny w meczu (XI bez ławki); [] przed ogłoszeniem.

    Ten sam nieudokumentowany zestaw co predicted-teams-lineup; para z flagą
    event.lineupConfirmed. eventId = events.id (NIE internalId).
    """
    d = _get(f"{BASE}/event/{event_id}/team-lineup?teamId={team_id}&heatmap=false")
    data = d.get("data", d)
    if not isinstance(data, list):
        return []
    return [
        int(p["playerId"]) for p in data
        if p.get("playerId") and p.get("isSubstitute") is not True
    ]


def props_available(event_id: int) -> bool:
    """Czy statshub ma już wystawione propsy dla meczu (feed niepusty)."""
    try:
        return len(fetch_event_trends([event_id])) > 0
    except Exception:
        return False


# statType team-trends -> nasz kod rynku DRUŻYNOWEGO. UWAGA na nazwy statshub:
# "totalShotsOnGoal" to strzały OGÓŁEM (statDisplay "Shots"), "shotsOnGoal" —
# celne. Fauli drużynowych team-trends nie wystawia (historia z banku stylu).
# Sonda klubowa 2026-07-20: dla klubów feed niesie głównie "goals" (673/750
# rekordów) i "cornerKicks" (75) — a Superbet kwotuje czysto właśnie gole,
# rożne i kartki drużynowe, więc mapujemy i te.
TEAM_STATTYPE_MAP = {
    "totalShotsOnGoal": "team_shots",
    "shotsOnGoal": "team_sot",
    "cards": "team_cards",
    "goals": "team_goals",
    "cornerKicks": "team_corners",
}


@dataclass
class TeamTrend:
    """Trend DRUŻYNOWY: (drużyna, rynek) z historią ~20 meczów i linią."""

    team_id: int
    team_name: str
    opponent_name: str
    event_id: int
    is_home: bool
    market_code: str
    line: float
    odds_type: str = "over"
    # kontekst ligi (recentGames całego feedu = próbka ligi i koncesje rywali)
    opponent_id: int = 0
    league_id: int = 0
    league_name: str = ""
    counts: list[float] = field(default_factory=list)
    timestamps: list[int] = field(default_factory=list)
    game_opponents: list[str] = field(default_factory=list)
    # per mecz historii: id rywala i czy grali u siebie (isHome z feedu)
    game_opponent_ids: list[int] = field(default_factory=list)
    game_is_home: list[bool] = field(default_factory=list)
    ref_odds: list[float] = field(default_factory=list)


def fetch_team_trends(event_ids: list[int]) -> list[TeamTrend]:
    """Trendy drużynowe (`/api/props/team-trends`) dla podanych meczów.

    Zwraca gole / rożne / strzały / celne / kartki per drużyna z historią
    recentGames (statValue per mecz, ~20 wstecz) i kursami referencyjnymi.
    Z PAGINACJĄ — ta sama pułapka co player-trends (domyślne pageSize=25
    cicho ucina feed; zmierzone 2026-07-20: 750 rekordów w 8 stronach).
    """
    if not event_ids:
        return []
    games = ",".join(str(e) for e in event_ids)
    data: list[dict] = []
    page = 1
    PAGE_SIZE = 100
    while True:
        czesc = _get(
            f"{BASE}/props/team-trends?games={games}"
            f"&pageSize={PAGE_SIZE}&page={page}"
        ).get("data", [])
        data += czesc
        # bezpiecznik 40 stron, jak w fetch_event_trends
        if len(czesc) < PAGE_SIZE or page >= 40:
            break
        page += 1
    out: list[TeamTrend] = []
    for rec in data:
        mk = TEAM_STATTYPE_MAP.get(rec.get("statType"))
        if mk is None:
            continue
        rg = rec.get("recentGames", [])
        out.append(TeamTrend(
            team_id=int(rec.get("teamId") or 0),
            team_name=rec.get("teamName", ""),
            opponent_name=rec.get("opponentTeamName", ""),
            event_id=int(rec.get("eventId") or 0),
            is_home=rec.get("homeTeamId") == rec.get("teamId"),
            market_code=mk,
            line=float(rec.get("line", 0.5)),
            odds_type=str(rec.get("oddsType") or "over"),
            opponent_id=int(rec.get("opponentTeamId") or 0),
            league_id=int(rec.get("leagueId") or 0),
            league_name=str(rec.get("leagueName") or ""),
            counts=[float(g.get("statValue") or 0) for g in rg],
            timestamps=[int(g.get("eventTimestamp") or 0) for g in rg],
            game_opponents=[str(g.get("opponentName") or "") for g in rg],
            game_opponent_ids=[int(g.get("opponentId") or 0) for g in rg],
            game_is_home=[bool(g.get("isHome")) for g in rg],
            ref_odds=[
                float(b["oddsValue"])
                for b in rec.get("bookmakers", [])
                if b.get("oddsValue")
            ],
        ))
    return out


def fetch_event_shotmap(event_id: int) -> list[dict]:
    """Mapa strzałów meczu — lista strzałów z `playerId`, `teamId`, `minute`,
    `situation` (assisted/regular/fast-break/corner/free-kick/set-piece),
    `bodyPart`, `isBlockedShot`, `blockedByPlayerId`, `xG`.

    Dla banku STYLU (model/styl.py): udział strzałów z kontr per drużyna
    i strzały ze stałych fragmentów per zawodnik. Kształt sprawdzony na
    żywym meczu MŚ (2026-07-14)."""
    data = _get(f"{BASE}/event/{event_id}/shotmap").get("data", [])
    return data if isinstance(data, list) else []


# wynik strzału w shotmapie -> czy CELNY (on target). Gol i obroniony = celny;
# blok/niecelny/słupek = niecelny. Zgodne z definicją SoT bukmachera.
_SHOTMAP_CELNE = {"goal", "save", "saved"}


def fetch_event_result(event_id: int) -> dict | None:
    """Wynik meczu w REGULARNYM czasie dla DOWOLNEJ ligi (otwarte API, z chmury).

    Zwraca {home_id, away_id, home_name, away_name, home_goals, away_goals,
    extra_time} albo None, gdy mecz niezakończony / brak wyniku. Gole bierze z
    pól *ScoreNormaltime (bez dogrywki) — pod rynki 90-minutowe; extra_time=True
    gdy *Current != *Normaltime (była dogrywka/karne). To domyka rozliczanie
    goli drużynowych egzotyki, której 365Scores nie zna (te same id co statshub).
    """
    try:
        d = _get(f"{BASE}/event/{event_id}")
    except Exception:
        return None
    root = d.get("data", d) or {}
    ev = root.get("events")
    ev = (ev[0] if isinstance(ev, list) and ev else ev) or {}
    if not isinstance(ev, dict):
        return None
    hn, an = ev.get("homeScoreNormaltime"), ev.get("awayScoreNormaltime")
    hc, ac = ev.get("homeScoreCurrent"), ev.get("awayScoreCurrent")
    hg = hn if hn is not None else hc
    ag = an if an is not None else ac
    if hg is None or ag is None:
        return None
    extra = hn is not None and hc is not None and (hn != hc or an != ac)

    def _nazwa(side: str) -> str | None:
        t = root.get(side) or {}
        t = (t[0] if isinstance(t, list) and t else t) or {}
        return t.get("name") if isinstance(t, dict) else None

    return {
        "home_id": ev.get("homeTeamId"),
        "away_id": ev.get("awayTeamId"),
        "home_name": _nazwa("homeTeam"),
        "away_name": _nazwa("awayTeam"),
        "home_goals": float(hg),
        "away_goals": float(ag),
        "extra_time": bool(extra),
    }


def player_shots_from_shotmap(event_id: int) -> dict[str, dict] | None:
    """{nazwa_zawodnika: {"shots": n, "sot": n}} z shotmapy meczu (otwarte API).

    Kluczem jest NAZWISKO (nie playerId) — id zawodników statshub bywają w innej
    przestrzeni niż odbiorca (kupon), więc rozliczanie dopasowuje po nazwisku
    (jak ścieżka 365, resolve_player_key). None = brak shotmapy (egzotyka bez
    pokrycia — nie mylić z 0 strzałów). Liczy CAŁĄ shotmapę, więc używać tylko
    dla meczów bez dogrywki (patrz fetch_event_result.extra_time).
    """
    try:
        sm = fetch_event_shotmap(event_id)
    except Exception:
        return None
    if not sm:
        return None
    out: dict[str, dict] = {}
    for s in sm:
        name = s.get("playerName")
        if not name:
            continue
        d = out.setdefault(str(name), {"shots": 0, "sot": 0})
        d["shots"] += 1
        if str(s.get("result") or "").lower() in _SHOTMAP_CELNE:
            d["sot"] += 1
    return out


_TOURNAMENT_NAME_CACHE: dict[int, str] = {}


def fetch_tournament_name(utid: int) -> str:
    """Nazwa rozgrywek po uniqueTournamentId (`/api/unique-tournament/{id}`).

    Radar etykietuje tym „starą ligę" transferu (np. 'Championnat National,
    Francja'). Cache w pamięci procesu — jeden cykl pyta o kilka utid-ów."""
    if utid in _TOURNAMENT_NAME_CACHE:
        return _TOURNAMENT_NAME_CACHE[utid]
    nazwa = ""
    try:
        d = _get(f"{BASE}/unique-tournament/{utid}", timeout=12, retries=1)
        rec = d.get("data") or {}
        nazwa = str(rec.get("name") or "")
        kraj = str(rec.get("categoryName") or "")
        if nazwa and kraj and kraj.lower() not in nazwa.lower():
            nazwa = f"{nazwa} ({kraj})"
    except Exception:
        pass
    _TOURNAMENT_NAME_CACHE[utid] = nazwa
    return nazwa


def search_players(nazwa: str) -> list[dict]:
    """Wyszukiwarka zawodników `/api/search?q=` (odkryta 2026-07-22).

    Zwraca listę {id, name, slug, countrySlug} — radar używa jej do
    zidentyfikowania debiutantów kwotowanych przez Superbet, których nie ma
    w feedzie propsów (bukmacherzy UK nie wystawili im linii)."""
    try:
        d = _get(f"{BASE}/search?q={nazwa}", timeout=15, retries=2)
    except Exception:
        return []
    out = d.get("players") or []
    return out if isinstance(out, list) else []


def fetch_player_profile(player_id: int) -> dict:
    """Pełniejszy profil niż fetch_player_meta — pod kartę debiutanta radaru.

    KLUCZOWE pole: team_id (obecny klub wg statshub) — weryfikuje, że
    wyszukany po nazwisku gracz faktycznie należy do drużyny z meczu."""
    try:
        data = _get(f"{BASE}/player/{player_id}", timeout=15, retries=2).get(
            "data", {}
        )
    except Exception:
        return {}
    rec = data.get("players")
    if isinstance(rec, list):
        rec = rec[0] if rec else {}
    if not isinstance(rec, dict):
        return {}
    h = rec.get("height")
    mv = rec.get("marketvalue")
    return {
        "id": rec.get("id"),
        "name": rec.get("name"),
        "position": rec.get("position"),
        "height": int(h) if isinstance(h, (int, float)) and h else None,
        "foot": rec.get("preferredfoot") or None,
        "team_id": int(rec.get("teamid") or 0) or None,
        "country": rec.get("countrySlug"),
        "market_value": float(mv) if mv else None,
        "birth_ts": rec.get("dateofbirth"),
    }


def fetch_player_meta(player_id: int) -> dict:
    """Metadane zawodnika: {"height": int|None, "foot": str|None}.

    `/api/player/{id}` zwraca {"data": {"players": [rekord]}} — m.in. height
    (cm) i preferredfoot. Wzrost zasila matchup.is_target_man."""
    data = _get(f"{BASE}/player/{player_id}").get("data", {})
    rec = data.get("players")
    if isinstance(rec, list):
        rec = rec[0] if rec else {}
    if not isinstance(rec, dict):
        rec = {}
    h = rec.get("height")
    return {
        "height": int(h) if isinstance(h, (int, float)) and h else None,
        "foot": rec.get("preferredfoot") or None,
    }
