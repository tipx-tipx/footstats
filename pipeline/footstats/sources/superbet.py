"""Źródło kursów: Superbet (wewnętrzne API ofertowe ich strony).

Zweryfikowane 2026-07-02:
  * lista meczów:  /v2/pl-PL/events/by-date?...&sportId=5
  * pełna oferta:  /v2/pl-PL/events/{eventId}  (kilkaset rynków, w tym
    per-zawodnik: strzały, celne, zza pola, głową, faule, faule na zawodniku,
    odbiory, spalone — dokładnie nasze rynki)

Kursy zmieniają się w czasie → NIE cache'ujemy odpowiedzi z kursami.
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections import defaultdict

from curl_cffi import requests

BASE = "https://production-superbet-offer-pl.freetls.fastly.net/v2/pl-PL"
HEADERS = {
    "Accept": "application/json",
    "Origin": "https://superbet.pl",
    "Referer": "https://superbet.pl/",
}

# rynki zawodnicze Superbetu -> nasze kody
PLAYER_MARKET_MAP = {
    "Zawodnik - liczba strzałów": "shots",
    "Zawodnik - liczba celnych strzałów": "sot",
    "Zawodnik - liczba strzałów spoza pola karnego": "shots_outside_box",
    "Zawodnik - liczba celnych strzałów spoza pola karnego": "sot_outside_box",
    "Zawodnik - liczba strzałów głową": "headed_shots",
    "Zawodnik - liczba celnych strzałów głową": "headed_sot",
    "Zawodnik - liczba popełnionych fauli": "fouls_committed",
    "Zawodnik - liczba fauli na zawodniku": "fouls_won",
    "Zawodnik - liczba odbiorów": "tackles",
    "Zawodnik - liczba spalonych": "offsides",
    "Zawodnik - liczba niecelnych strzałów": "shots_off_target",
    "Zawodnik - liczba zablokowanych strzałów": "shots_blocked",
}

# rynki drużynowe (nazwa zawiera nazwę drużyny, np. "Francja liczba fauli")
TEAM_MARKET_SUFFIX = {
    "liczba fauli": "team_fouls",
    "liczba strzałów": "team_shots",
    "liczba celnych strzałów": "team_sot",
    "liczba żółtych kartek": "team_cards",
    "liczba kartek": "team_cards",
}

# nazwy reprezentacji: Superbet (PL) -> Sofascore/statshub (EN)
TEAM_PL_EN = {
    "Hiszpania": "Spain", "Austria": "Austria", "USA": "USA",
    "Bośnia i Hercegowina": "Bosnia & Herzegovina", "Belgia": "Belgium",
    "Senegal": "Senegal", "Anglia": "England", "DR Konga": "DR Congo",
    "Meksyk": "Mexico", "Ekwador": "Ecuador", "Francja": "France",
    "Szwecja": "Sweden", "Norwegia": "Norway", "Maroko": "Morocco",
    "Holandia": "Netherlands", "Niemcy": "Germany", "Paragwaj": "Paraguay",
    "Brazylia": "Brazil", "Japonia": "Japan", "Kanada": "Canada",
    "Wybrzeże Kości Słoniowej": "Ivory Coast", "Portugalia": "Portugal",
    "Argentyna": "Argentina", "Włochy": "Italy", "Chorwacja": "Croatia",
    "Polska": "Poland", "Urugwaj": "Uruguay", "Kolumbia": "Colombia",
    # pozostałe reprezentacje MŚ 2026
    "Szwajcaria": "Switzerland", "Algieria": "Algeria", "Australia": "Australia",
    "Egipt": "Egypt", "Ghana": "Ghana",
    "Republika Zielonego Przylądka": "Cape Verde", "Zielony Przylądek": "Cape Verde",
    "Korea Południowa": "South Korea", "Iran": "Iran", "Arabia Saudyjska": "Saudi Arabia",
    "Katar": "Qatar", "Tunezja": "Tunisia", "Nigeria": "Nigeria",
    "Kamerun": "Cameroon", "RPA": "South Africa", "Ekwador ": "Ecuador",
    "Kostaryka": "Costa Rica", "Panama": "Panama", "Honduras": "Honduras",
    "Peru": "Peru", "Chile": "Chile", "Wenezuela": "Venezuela",
    "Nowa Zelandia": "New Zealand", "Turcja": "Türkiye", "Serbia": "Serbia",
    "Dania": "Denmark", "Szkocja": "Scotland", "Walia": "Wales",
    "Grecja": "Greece", "Ukraina": "Ukraine", "Czechy": "Czechia",
    "Węgry": "Hungary", "Rumunia": "Romania", "Słowacja": "Slovakia",
    "Mali": "Mali", "Burkina Faso": "Burkina Faso", "RD Konga": "DR Congo",
    "Jordania": "Jordan", "Irak": "Iraq", "Uzbekistan": "Uzbekistan",
}


def norm_name(name: str) -> str:
    """Normalizacja nazwiska do dopasowania między źródłami.

    'Mateta, Jean-Philippe' i 'Jean-Philippe Mateta' -> ten sam klucz.
    """
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    tokens = sorted(t for t in re.split(r"[^a-z]+", s) if len(t) > 1)
    return " ".join(tokens)


def _get(url: str, min_interval: float = 1.5) -> dict:
    time.sleep(min_interval)
    r = requests.get(url, impersonate="chrome124", timeout=25, headers=HEADERS)
    r.raise_for_status()
    return r.json()


def list_events(days_ahead: int = 7) -> list[dict]:
    start = time.strftime("%Y-%m-%d+%H:%M:%S", time.localtime())
    end = time.strftime(
        "%Y-%m-%d+23:59:00", time.localtime(time.time() + days_ahead * 86400)
    )
    url = (
        f"{BASE}/events/by-date?currentStatus=active&offerState=prematch"
        f"&startDate={start}&endDate={end}&sportId=5"
    )
    return _get(url).get("data", [])


def match_superbet_event(
    events: list[dict], home_en: str, away_en: str, kickoff_ts: int
) -> dict | None:
    """Znajdź mecz Superbetu odpowiadający meczowi Sofascore (nazwy + czas)."""
    en_pl = {v: k for k, v in TEAM_PL_EN.items()}
    home_pl, away_pl = en_pl.get(home_en), en_pl.get(away_en)
    for ev in events:
        name = ev.get("matchName") or ""
        parts = [p.strip() for p in name.split("·")]
        if len(parts) != 2:
            continue
        # Dokładne dopasowanie nazw (PL) — w turnieju mecz jest jednoznaczny,
        # więc NIE bramkujemy czasem (matchTimestamp Superbetu bywa przesunięty).
        if home_pl and away_pl and parts == [home_pl, away_pl]:
            return ev
        # awaryjnie: znormalizowane nazwy + luźne okno czasowe (±30 h)
        if norm_name(parts[0]) == norm_name(home_en) and norm_name(parts[1]) == norm_name(away_en):
            try:
                ev_ts = int(ev.get("matchTimestamp") or 0)
                if ev_ts > 1e11:
                    ev_ts //= 1000
            except (TypeError, ValueError):
                ev_ts = 0
            if not ev_ts or abs(ev_ts - kickoff_ts) < 30 * 3600:
                return ev
    return None


def fetch_stat_odds(event_id: int, home_pl: str, away_pl: str) -> dict:
    """Pobierz i znormalizuj kursy statystyczne meczu.

    Zwraca:
      players: norm_name -> market_code -> line -> {'over': kurs, 'under': kurs}
      teams:   'home'/'away' -> market_code -> line -> {'over': ..., 'under': ...}
    """
    d = _get(f"{BASE}/events/{event_id}")
    data = d.get("data")
    event = data[0] if isinstance(data, list) else data
    odds = event.get("odds", [])

    players: dict = defaultdict(lambda: defaultdict(dict))
    teams: dict = {"home": defaultdict(dict), "away": defaultdict(dict)}

    for o in odds:
        if o.get("status") == "block":
            continue
        price = o.get("price")
        if not price or price <= 1.0:
            continue
        mname = (o.get("marketName") or "").strip()
        oname = (o.get("name") or "").strip()
        spec = o.get("specifiers") or {}

        side = None
        if "powyżej" in oname or "powyżej" in mname:
            side = "over"
        elif "poniżej" in oname or "poniżej" in mname:
            side = "under"

        # --- zawodnicy ---
        code = PLAYER_MARKET_MAP.get(mname)
        if code and spec.get("player_name") and spec.get("total") and side:
            try:
                line = float(spec["total"])
            except ValueError:
                continue
            key = norm_name(spec["player_name"])
            players[key][code].setdefault(line, {})[side] = float(price)
            continue

        # --- kartka zawodnika ---
        if mname in ("Zawodnik otrzyma kartkę", "Zawodnik otrzyma żółtą kartkę") and spec.get(
            "player_name"
        ):
            key = norm_name(spec["player_name"])
            players[key]["yellow_card"].setdefault(0.5, {})["over"] = float(price)
            continue

        # --- drużyny: pełny mecz, nazwa rynku zaczyna się od nazwy drużyny ---
        if "połowa" in mname:
            continue
        for team_pl, slot in ((home_pl, "home"), (away_pl, "away")):
            if not mname.startswith(team_pl):
                continue
            rest = mname[len(team_pl):].strip(" -")
            code = TEAM_MARKET_SUFFIX.get(rest)
            total = spec.get("total")
            if code and total and side:
                try:
                    line = float(total)
                except ValueError:
                    break
                teams[slot][code].setdefault(line, {})[side] = float(price)
            break

    return {"players": {k: dict(v) for k, v in players.items()},
            "teams": {k: dict(v) for k, v in teams.items()}}
