"""Źródło danych: 365Scores — mapy strzałów (alternatywa dla Sofascore).

Sofascore blokuje IP serwerowni, więc rynki wymagające danych per strzał
(głową, zza pola karnego, zablokowane, niecelne) nie działały w chmurze.
365Scores (webws.365scores.com) daje to samo i DZIAŁA z GitHub Actions
(potwierdzone). Każdy strzał w chartEvents ma:

  * bodyPart:  "Header" / "Left foot" / "Right Foot",
  * outcome.id: 0=Goal, 1=Missed (niecelny), 2=Saved (celny, obroniony),
                4=Blocked (zablokowany),
  * side: pozycja wzdłuż boiska w % (bramka=100; rzut karny ~88.5;
          linia pola karnego ~84 — strzał zza pola: side < 84),
  * xG / xGOT (bonus, nieużywane).

Przepływ: competitor_ids (z bieżących meczów) -> games/results per drużyna
-> game/?gameId= (members + chartEvents) -> agregacja per zawodnik per mecz.
Wyniki cache'owane w pamięci procesu (jeden cykl = jedno pobranie).
"""

from __future__ import annotations

import time as _time

from curl_cffi import requests

from .rotowire import _norm

BASE = "https://webws.365scores.com/web"
Q = "appTypeId=5&langId=1&timezoneName=Europe/Warsaw&userCountryId=1"

# linia pola karnego: 16.5 m z ~105 m boiska => ~84% (karny side~88.5 potwierdza skalę)
BOX_SIDE_THRESHOLD = 84.0

# competitionId Mistrzostw Świata 2026 (endpoint /search)
WC_COMPETITION_ID = 5930

# rynki liczone są w REGULARNYM czasie gry (90 min + doliczony): zdarzenia
# z bazową minutą > 90 ("104'", "120 + 5'") to dogrywka/karne — pomijamy
REGULARNY_CZAS_MIN = 90.0

_game_cache: dict[int, dict] = {}
# gameId -> mecz miał dogrywkę (gameTime > 90) — staty lineups obejmują wtedy
# całe 120 min i NIE nadają się do rozliczania rynków regularnego czasu
_et_cache: dict[int, bool] = {}


def _minuta(t) -> float | None:
    """Bazowa minuta zdarzenia: "90 + 2'" -> 90; "104'" -> 104; brak -> None."""
    s = str(t or "").replace("'", "").strip()
    if not s:
        return None
    try:
        return float(s.split("+")[0].strip())
    except ValueError:
        return None


def _zapamietaj_et(game_id: int, game: dict) -> None:
    try:
        gt = float(game.get("gameTime") or 0)
    except (TypeError, ValueError):
        gt = 0.0
    _et_cache[game_id] = (
        gt > REGULARNY_CZAS_MIN + 0.5
        or "ET" in str(game.get("shortStatusText") or "")
    )


def after_extra_time(game_id: int) -> bool:
    """Czy mecz miał dogrywkę (wg wcześniej pobranych danych meczu)."""
    if game_id not in _et_cache:
        try:
            game = _get(f"{BASE}/game/?{Q}&gameId={game_id}").get("game", {})
            _zapamietaj_et(game_id, game)
        except Exception:
            return False
    return _et_cache.get(game_id, False)


def _get(url: str, timeout: int = 25, retries: int = 2) -> dict:
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, impersonate="chrome124", timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            _time.sleep(2 * (attempt + 1))
    raise last


def competitor_ids(team_names: list[str]) -> dict[str, int]:
    """Mapa: znormalizowana nazwa drużyny -> competitorId.

    Szuka w bieżących meczach ORAZ w oknie najbliższych dni (drużyny grające
    za 2-3 dni nie występują w "current").
    """
    wanted = {_norm(n) for n in team_names}
    out: dict[str, int] = {}

    def _scan(games: list[dict]) -> None:
        for g in games:
            for side in ("homeCompetitor", "awayCompetitor"):
                c = g.get(side) or {}
                key = _norm(str(c.get("name", "")))
                if key in wanted and key not in out and c.get("id"):
                    out[key] = int(c["id"])

    wc_comp_id = None
    try:
        data = _get(f"{BASE}/games/current/?{Q}&sports=1")
        _scan(data.get("games", []))
        for g in data.get("games", []):
            if "World Cup" in str(g.get("competitionDisplayName", "")):
                wc_comp_id = g.get("competitionId")
                break
    except Exception:
        pass
    # terminarz i wyniki MŚ po znanym id rozgrywek — /games/current często
    # w ogóle nie zawiera meczów MŚ (ucina do ~100 bieżących wszystkich lig)
    if len(out) < len(wanted):
        for comp in {wc_comp_id, WC_COMPETITION_ID} - {None}:
            for endpoint in ("fixtures", "results"):
                try:
                    data = _get(f"{BASE}/games/{endpoint}/?{Q}&competitions={comp}")
                    _scan(data.get("games", []))
                except Exception:
                    pass
            if len(out) >= len(wanted):
                break
    return out


def finished_games_by_competition(comp_id: int = WC_COMPETITION_ID) -> list[dict]:
    """Ostatnie zakończone mecze rozgrywek: [{id, ts, home, away}, ...].

    /games/results per rozgrywki — pewniejsze do rozliczeń niż /games/current,
    który IGNORUJE parametry startDate/endDate i zwraca tylko ~100 bieżących
    meczów (wczorajszy mecz MŚ zwykle w ogóle się w nim nie pojawia).
    """
    from datetime import datetime

    data = _get(f"{BASE}/games/results/?{Q}&competitions={comp_id}")
    out = []
    for g in data.get("games", []):
        if g.get("statusGroup") != 4:
            continue
        try:
            ts = int(datetime.fromisoformat(str(g.get("startTime", ""))).timestamp())
        except Exception:
            continue
        out.append({
            "id": int(g["id"]), "ts": ts,
            "home": _norm(str((g.get("homeCompetitor") or {}).get("name", ""))),
            "away": _norm(str((g.get("awayCompetitor") or {}).get("name", ""))),
        })
    return out


def recent_finished_games(competitor_id: int, n: int = 6) -> list[tuple[int, int]]:
    """Ostatnie n zakończonych meczów drużyny: [(gameId, timestamp_unix), ...] od najnowszych."""
    data = _get(f"{BASE}/games/results/?{Q}&competitors={competitor_id}")
    rows = []
    for g in data.get("games", []):
        if g.get("statusGroup") != 4:
            continue
        st = str(g.get("startTime", ""))  # np. "2026-06-25T20:00:00+02:00"
        try:
            from datetime import datetime

            ts = int(datetime.fromisoformat(st).timestamp())
        except Exception:
            continue
        rows.append((int(g["id"]), ts))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:n]


def classify_event(e: dict) -> dict[str, int] | None:
    """Zamień jedno zdarzenie chartEvents na liczniki rynków (None = pomiń)."""
    if e.get("type") not in (0, None):  # 0 = strzał
        return None
    out_id = (e.get("outcome") or {}).get("id")
    body = str(e.get("bodyPart") or "")
    side = e.get("side")
    headed = body == "Header"
    left = "left" in body.lower()
    right = "right" in body.lower()
    on_target = out_id in (0, 2)
    outside = side is not None and float(side) < BOX_SIDE_THRESHOLD
    return {
        "shots": 1,
        "sot": 1 if on_target else 0,
        "headed": 1 if headed else 0,
        "headed_sot": 1 if headed and on_target else 0,
        "outside": 1 if outside else 0,
        "sot_outside": 1 if outside and on_target else 0,
        "blocked": 1 if out_id == 4 else 0,
        "off_target": 1 if out_id == 1 else 0,
        "left_foot": 1 if left else 0,
        "left_foot_sot": 1 if left and on_target else 0,
        "right_foot": 1 if right else 0,
        "right_foot_sot": 1 if right and on_target else 0,
    }


def resolve_player_key(all_keys: set[str], player_name: str) -> str | None:
    """Znajdź klucz zawodnika w historii 365 (dokładnie albo nazwisko+inicjał)."""
    p = _norm(player_name)
    if p in all_keys:
        return p
    pt = p.split()
    if not pt:
        return None
    for k in all_keys:
        kt = k.split()
        if kt and pt[-1] == kt[-1] and pt[0][:1] == kt[0][:1]:
            return k
    return None


def game_player_shots(game_id: int) -> dict[str, dict[str, int]]:
    """Agregat strzałów per zawodnik (znormalizowane nazwisko) dla meczu.

    Liczony WYŁĄCZNIE w regularnym czasie (90 min + doliczony) — tak rozlicza
    bukmacher; strzały z dogrywki i serii karnych nie wchodzą do agregatu.
    """
    if game_id in _game_cache:
        return _game_cache[game_id]
    data = _get(f"{BASE}/game/?{Q}&gameId={game_id}")
    game = data.get("game", {})
    _zapamietaj_et(game_id, game)
    names = {int(m["id"]): str(m.get("name", "")) for m in game.get("members", []) if m.get("id")}
    per_player: dict[str, dict[str, int]] = {}
    for e in (game.get("chartEvents") or {}).get("events", []):
        m_ev = _minuta(e.get("time"))
        if m_ev is not None and m_ev > REGULARNY_CZAS_MIN:
            continue  # dogrywka / seria karnych
        counts = classify_event(e)
        if counts is None:
            continue
        name = names.get(int(e.get("playerId") or 0))
        if not name:
            continue
        slot = per_player.setdefault(_norm(name), dict.fromkeys(counts, 0))
        for k, v in counts.items():
            slot[k] += v
    _game_cache[game_id] = per_player
    return per_player


def team_shot_history(
    competitor_id: int, n_games: int = 6
) -> list[tuple[int, dict[str, dict[str, int]]]]:
    """Historia drużyny: [(timestamp, {zawodnik: liczniki}), ...] od najnowszych."""
    out = []
    for gid, ts in recent_finished_games(competitor_id, n_games):
        try:
            out.append((ts, game_player_shots(gid)))
        except Exception:
            continue
        _time.sleep(0.3)  # grzecznie dla API
    return out


# ---- pełne statystyki meczowe per zawodnik (lineups.members[].stats) ----
# nazwa statystyki 365 -> nasz kod rynku (odbiory NIE występują w 365)
STAT_NAME_MAP = {
    "Minutes": "minutes",
    "Total Shots": "shots",
    "Fouls Made": "fouls_committed",
    "Was Fouled": "fouls_won",
    "Interceptions": "interceptions",
    "Offsides": "offsides",
}

_full_cache: dict[int, dict] = {}


def _stat_val(v) -> float:
    """"90'" -> 90; "20/26 (77%)" -> 20; "2" -> 2."""
    s = str(v).strip().rstrip("'")
    s = s.split("/")[0].split("(")[0].strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def game_player_match_stats(game_id: int) -> dict[str, dict[str, float]]:
    """Pełne staty meczu per zawodnik: minuty, strzały, faule, przechwyty...

    Zwraca {znormalizowane nazwisko: {"minutes": 90, "shots": 2, ...,
    "started": 1.0/0.0, "sot": ... (z chartEvents)}}.
    """
    if game_id in _full_cache:
        return _full_cache[game_id]
    data = _get(f"{BASE}/game/?{Q}&gameId={game_id}")
    game = data.get("game", {})
    _zapamietaj_et(game_id, game)
    names = {int(m["id"]): str(m.get("name", "")) for m in game.get("members", []) if m.get("id")}
    out: dict[str, dict[str, float]] = {}
    for side in ("homeCompetitor", "awayCompetitor"):
        lu = (game.get(side) or {}).get("lineups") or {}
        for m in lu.get("members") or []:
            name = names.get(int(m.get("id") or 0))
            if not name:
                continue
            rec: dict[str, float] = {
                "started": 1.0 if m.get("statusText") == "Starting" else 0.0,
            }
            for s in m.get("stats") or []:
                kod = STAT_NAME_MAP.get(str(s.get("name")))
                if kod:
                    rec[kod] = _stat_val(s.get("value"))
            if rec.get("minutes"):
                out[_norm(name)] = rec
    # celne strzały z mapy strzałów (nie ma ich w lineups)
    try:
        for pkey, cnts in game_player_shots(game_id).items():
            if pkey in out:
                out[pkey]["sot"] = float(cnts.get("sot", 0))
    except Exception:
        pass
    _full_cache[game_id] = out
    return out


def team_match_history(
    competitor_id: int, n_games: int = 6
) -> list[tuple[int, dict[str, dict[str, float]]]]:
    """Historia pełnych statystyk drużyny: [(timestamp, {zawodnik: staty}), ...]."""
    out = []
    for gid, ts in recent_finished_games(competitor_id, n_games):
        try:
            out.append((ts, game_player_match_stats(gid)))
        except Exception:
            continue
        _time.sleep(0.3)
    return out
