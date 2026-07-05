"""Źródło siły reprezentacji: eloratings.net (otwarte TSV, działa z chmury).

Dwa pliki:
  * World.tsv     — ranking: kolumny [rank, rank_lokalny?, KOD, ELO, ...],
  * en.teams.tsv  — mapa KOD -> nazwa angielska (+ kolumny aliasów).

Rating służy do:
  * ciągłego WAŻENIA PRÓBY siłą rywala (mecz z Francją ~2140 liczy się
    pełniej niż mecz z Botswaną ~1400) zamiast binarnego 1.0/0.75,
  * syntetycznego spreadu, gdy Superbet nie kwotuje jeszcze 1X2 meczu.

Cache w Supabase (app_data.elo_ratings) — świeży fetch raz na kilka dni,
awaryjnie stara kopia (siła reprezentacji zmienia się wolno).
"""

from __future__ import annotations

import time
import unicodedata

from curl_cffi import requests

from .. import supa

BASE = "https://www.eloratings.net"
CACHE_KEY = "elo_ratings"
CACHE_MAX_AGE_S = 3 * 86400

# rozjazdy nazw naszych źródeł vs eloratings
ALIASY = {
    "usa": "united states",
    "ivory coast": "cote divoire",
    "turkiye": "turkey",
    "czechia": "czech republic",
    "bosnia & herzegovina": "bosnia and herzegovina",
    "dr congo": "congo dr",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = " ".join(s.replace("-", " ").replace("'", "").split()).lower()
    return ALIASY.get(s, s)


def _fetch_tsv(path: str) -> list[list[str]]:
    r = requests.get(
        f"{BASE}/{path}", impersonate="chrome124", timeout=20,
        headers={"Referer": f"{BASE}/"},
    )
    r.raise_for_status()
    return [line.split("\t") for line in r.text.splitlines() if line.strip()]


def fetch_ratings() -> dict[str, int]:
    """Pobierz świeże ratingi: znormalizowana nazwa (i aliasy) -> Elo."""
    code_names: dict[str, list[str]] = {}
    for row in _fetch_tsv("en.teams.tsv"):
        if len(row) >= 2 and row[0].strip():
            code_names[row[0].strip()] = [c.strip() for c in row[1:] if c.strip()]
    out: dict[str, int] = {}
    for row in _fetch_tsv("World.tsv"):
        # format: [pozycja, rank, KOD, ELO, ...]
        if len(row) < 4:
            continue
        code, elo_s = row[2].strip(), row[3].strip()
        try:
            elo = int(elo_s)
        except ValueError:
            continue
        for name in code_names.get(code, []):
            out[_norm(name)] = elo
    return out


def get_ratings() -> dict[str, int]:
    """Ratingi z cache Supabase; fetch gdy cache stary; pusta mapa = brak Elo."""
    cached = None
    try:
        cached = supa.get_key(CACHE_KEY)
    except Exception:
        pass
    now = int(time.time())
    if cached and now - int(cached.get("ts", 0)) < CACHE_MAX_AGE_S:
        return {str(k): int(v) for k, v in cached.get("ratings", {}).items()}
    try:
        ratings = fetch_ratings()
        if ratings:
            try:
                supa.put_key(CACHE_KEY, {"ts": now, "ratings": ratings})
            except Exception:
                pass
            return ratings
    except Exception:
        pass
    if cached:  # stara kopia lepsza niż nic
        return {str(k): int(v) for k, v in cached.get("ratings", {}).items()}
    return {}


# --- użycie ratingów w modelu ---

# typowy poziom mocnej reprezentacji na MŚ — waga 1.0
ELO_REF = 1900.0


def sample_weight(elo: int | None, is_wc_participant: bool = False) -> float:
    """Ciągła waga próby z Elo rywala (zamiast binarnej 1.0/0.75).

    ~2100 (Francja) -> 1.1, ~1900 -> 1.0, ~1650 -> 0.84, ~1400 (Botswana)
    -> 0.68. Rywal bez ratingu (klub, nieznany): uczestnik MŚ 0.95, inny 0.8.
    """
    if elo is None:
        return 0.95 if is_wc_participant else 0.8
    return float(min(max(0.5 + (elo - 1150.0) / 1500.0, 0.6), 1.1))


def synthetic_spread(elo_team: int | None, elo_opp: int | None) -> float | None:
    """Syntetyczny spread golowy z różnicy Elo (fallback, gdy brak kursów 1X2).

    Heurystyka eloratings: ~każde 100 pkt różnicy to ~0.2 gola przewagi.
    """
    if elo_team is None or elo_opp is None:
        return None
    return float(min(max((elo_team - elo_opp) / 500.0, -2.5), 2.5))
