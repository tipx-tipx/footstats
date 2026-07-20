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


def scheduled_games_by_competition(comp_id: int = WC_COMPETITION_ID) -> list[dict]:
    """Nadchodzące mecze rozgrywek: [{id, ts, home, away}, ...] (statusGroup 2)."""
    from datetime import datetime

    data = _get(f"{BASE}/games/fixtures/?{Q}&competitions={comp_id}")
    out = []
    for g in data.get("games", []):
        if g.get("statusGroup") != 2:
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


_ref_cache: dict[int, str | None] = {}


def game_referee(game_id: int) -> str | None:
    """Sędzia główny meczu (officials[0]) — znany zwykle 1-2 dni przed meczem.

    365 dopisuje kraj w nawiasie ("Ismail Elfath (USA )") — ucinamy go.
    """
    if game_id in _ref_cache:
        return _ref_cache[game_id]
    import re as _re

    name = ""
    try:
        data = _get(f"{BASE}/game/?{Q}&gameId={game_id}")
        offs = (data.get("game") or {}).get("officials") or []
        if offs:
            name = _re.sub(r"\s*\(.*?\)\s*$", "", str(offs[0].get("name") or "")).strip()
    except Exception:
        pass
    _ref_cache[game_id] = name or None
    return _ref_cache[game_id]


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


_subs_cache: dict[int, dict[str, dict]] = {}


def game_substitutions(game_id: int) -> dict[str, dict]:
    """Zmiany w meczu: {znormalizowane nazwisko SCHODZĄCEGO: {"wszedl":
    znormalizowane nazwisko wchodzącego, "minuta": float}}.

    Z game.events (eventType.id == 1000): playerId = WCHODZĄCY,
    extraPlayers[0] = SCHODZĄCY — kierunek potwierdzony minutami i składem
    wyjściowym (wchodzący ma started=0 i minuty = 90 − minuta zmiany).
    Tylko regularny czas — zmiany w dogrywce nie dotyczą rynków 90 min.
    """
    if game_id in _subs_cache:
        return _subs_cache[game_id]
    data = _get(f"{BASE}/game/?{Q}&gameId={game_id}")
    game = data.get("game", {})
    _zapamietaj_et(game_id, game)
    names = {
        int(m["id"]): str(m.get("name", ""))
        for m in game.get("members", [])
        if m.get("id")
    }
    out: dict[str, dict] = {}
    for e in game.get("events") or []:
        if (e.get("eventType") or {}).get("id") != 1000:
            continue
        try:
            gt = float(e.get("gameTime") or 0)
        except (TypeError, ValueError):
            continue
        if gt > REGULARNY_CZAS_MIN:
            continue
        wszedl = names.get(int(e.get("playerId") or 0))
        zszedl = names.get(int((e.get("extraPlayers") or [0])[0] or 0))
        if wszedl and zszedl:
            out[_norm(zszedl)] = {"wszedl": _norm(wszedl), "minuta": gt}
    _subs_cache[game_id] = out
    return out


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
# nazwa statystyki 365 -> nasz kod rynku. UWAGA: wbrew wcześniejszej nocie
# "odbiory nie występują w 365" — istnieje "Tackles Won" ("8/17"), ale jako
# para udane/próby, NIE licznik zdarzeń jak w statshub, więc do ROZLICZANIA
# rynku tackles się nie nadaje (definicje bukmacherskie liczą próby odbioru
# wg Opta) — zostaje w banku STYLU niżej, nie tutaj.
STAT_NAME_MAP = {
    "Minutes": "minutes",
    "Total Shots": "shots",
    "Fouls Made": "fouls_committed",
    "Was Fouled": "fouls_won",
    "Interceptions": "interceptions",
    "Offsides": "offsides",
}

# statystyki STYLU zawodnika (pełne matchupy, model/styl.py):
# nazwa 365 -> (klucz licznika, klucz mianownika | None) — "12/16 (75%)"
# niesie i udane (12), i PRÓBY (16); dotychczasowy _stat_val gubił mianownik,
# a to właśnie próby (dryblingi, pojedynki) opisują styl gry
STAT_STYLE_MAP = {
    "Successful Dribbles": ("dribbles_succ", "dribbles_att"),
    "Was Dribbled Past": ("dribbled_past", None),
    "Aerial Duels Won": ("aerial_won", "aerial_att"),
    "Ground Duels Won": ("ground_won", "ground_att"),
    "Key Passes": ("key_passes", None),
    "Crosses Completed": ("crosses_succ", "crosses_att"),
    "Long Passes Completed": ("longballs_succ", "longballs_att"),
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


def _stat_pair(v) -> tuple[float, float | None]:
    """"20/26 (77%)" -> (20, 26); "59%" -> (59, None); "3" -> (3, None)."""
    s = str(v).strip().rstrip("'").split("(")[0].strip()
    parts = [p.strip().rstrip("%") for p in s.split("/")]
    try:
        num = float(parts[0])
    except (ValueError, IndexError):
        return 0.0, None
    if len(parts) >= 2:
        try:
            return num, float(parts[1])
        except ValueError:
            return num, None
    return num, None


def _poz_z_formacji(m: dict) -> str:
    """365 formation.name ("Centre Back", "Central Midfield") -> G/D/M/F."""
    nm = str(((m.get("formation") or {}).get("name")) or "").upper()
    if "GOALKEEPER" in nm:
        return "G"
    if "MIDFIELD" in nm:               # też Defensive/Attacking Midfield
        return "M"
    if "BACK" in nm or "DEFEN" in nm:  # też Left/Right Wing Back
        return "D"
    if "WING" in nm or "FORWARD" in nm or "STRIKER" in nm or "ATTACK" in nm:
        return "F"
    return ""


def game_player_match_stats(game_id: int) -> dict[str, dict[str, float]]:
    """Pełne staty meczu per zawodnik: minuty, strzały, faule, przechwyty...

    Zwraca {znormalizowane nazwisko: {"minutes": 90, "shots": 2, ...,
    "started": 1.0/0.0, "sot": ... (z chartEvents), "pos": "D"/"M"/"F"/"G"
    (litera formacji — pod kubełki profilu rywala)}}.
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
        druzyna = _norm(str((game.get(side) or {}).get("name", "")))
        for m in lu.get("members") or []:
            name = names.get(int(m.get("id") or 0))
            if not name:
                continue
            rec: dict = {
                "started": 1.0 if m.get("statusText") == "Starting" else 0.0,
                "pos": _poz_z_formacji(m),
                # drużyna zawodnika — bank stylu (model/styl.py) grupuje po niej
                "druzyna": druzyna,
            }
            for s in m.get("stats") or []:
                nazwa = str(s.get("name"))
                kod = STAT_NAME_MAP.get(nazwa)
                if kod:
                    rec[kod] = _stat_val(s.get("value"))
                para = STAT_STYLE_MAP.get(nazwa)
                if para:
                    num, den = _stat_pair(s.get("value"))
                    rec[para[0]] = num
                    if para[1] and den is not None:
                        rec[para[1]] = den
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


# ---- statystyki DRUŻYNOWE per mecz (endpoint game/stats) — bank STYLU ----
# id statystyki 365 -> (nasz klucz, czy brać MIANOWNIK pary "x/y")
# Mianownik = PRÓBY (dośrodkowania, długie piłki, dryblingi) — to one opisują
# styl gry drużyny, nie skuteczność. Sprawdzone na żywym meczu MŚ 2026-07-14.
TEAM_STATS_MAP = {
    1: ("zolte", False), 2: ("czerwone", False),
    3: ("shots", False), 4: ("sot", False), 6: ("shots_blocked", False),
    8: ("corners", False), 9: ("offsides", False),
    10: ("possession", False), 12: ("fouls", False),
    52: ("crosses_att", True), 53: ("longballs_att", True),
    54: ("dribbles_att", True), 150: ("duels_won", False),
    56: ("aerial", None),          # para: won i attempts — oba potrzebne
    147: ("shots_outside", False),
}

_scores_cache: dict[int, dict] = {}


def game_scores(game_id: int) -> dict[str, float]:
    """Gole drużyn w meczu: {znormalizowana nazwa: gole} (endpoint game/).

    Do rozliczania rynku team_goals. Wynik obejmuje dogrywkę, ale rynki
    drużynowe z dogrywką i tak zamykają się jako zwrot (after_extra_time)
    ZANIM ktokolwiek zajrzy do tej funkcji.
    """
    if game_id in _scores_cache:
        return _scores_cache[game_id]
    game = _get(f"{BASE}/game/?{Q}&gameId={game_id}").get("game", {})
    out: dict[str, float] = {}
    for side in ("homeCompetitor", "awayCompetitor"):
        c = game.get(side) or {}
        nm = _norm(str(c.get("name") or ""))
        sc = c.get("score")
        if nm and sc is not None and float(sc) >= 0:
            out[nm] = float(sc)
    _zapamietaj_et(game_id, game)  # przy okazji: cache dogrywki bez 2. requestu
    _scores_cache[game_id] = out
    return out


_team_stats_cache: dict[int, dict] = {}


def game_team_stats(game_id: int) -> dict[str, dict[str, float]]:
    """Statystyki drużynowe meczu: {znormalizowana nazwa: {klucz: wartość}}.

    Endpoint `game/stats/?...&games=` (NIE `game/`) — płaska lista ~40
    statystyk per competitorId; nazwy drużyn z pola `competitors` tej samej
    odpowiedzi. `kartki` = żółte + czerwone (skala matchup.LG_TEAM_CARDS).
    """
    if game_id in _team_stats_cache:
        return _team_stats_cache[game_id]
    data = _get(f"{BASE}/game/stats/?{Q}&games={game_id}")
    nazwa_cid = {
        int(c["id"]): _norm(str(c.get("name", "")))
        for c in data.get("competitors") or []
        if c.get("id")
    }
    per_cid: dict[int, dict[str, float]] = {}
    for s in data.get("statistics") or []:
        mapowanie = TEAM_STATS_MAP.get(s.get("id"))
        cid = s.get("competitorId")
        if not mapowanie or cid is None:
            continue
        klucz, bierz_mianownik = mapowanie
        num, den = _stat_pair(s.get("value"))
        slot = per_cid.setdefault(int(cid), {})
        if klucz == "aerial":
            slot["aerial_won"] = num
            if den is not None:
                slot["aerial_att"] = den
        elif bierz_mianownik:
            if den is not None:
                slot[klucz] = den
        else:
            slot[klucz] = num
    out: dict[str, dict[str, float]] = {}
    for cid, st in per_cid.items():
        nm = nazwa_cid.get(cid)
        if not nm:
            continue
        st["kartki"] = st.pop("zolte", 0.0) + st.pop("czerwone", 0.0)
        out[nm] = st
    _team_stats_cache[game_id] = out
    return out
