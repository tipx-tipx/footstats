"""Źródło danych: Rotowire — przewidywane składy (drugie źródło obok statshub).

https://www.rotowire.com/soccer/lineups.php?league=WOC pokazuje dla każdego
meczu MŚ przewidywane (is-expected) lub potwierdzone (is-confirmed) jedenastki.
Strona jest publiczna i NIE blokuje IP serwerowni (działa z GitHub Actions).

Parsowanie: każdy mecz to blok `class="lineup is-soccer"`, w nim dwie nazwy
drużyn (lineup__mteam) i dwie listy (lineup__list). Lista zaczyna się od
znacznika statusu, potem 11 pozycji XI, potem separator `lineup__title`
i sekcja kontuzji/wątpliwych — bierzemy tylko zawodników PRZED separatorem.

Używane w build_wc_fast jako drugi głos przy przewidywanych składach:
zgoda obu źródeł = mocny sygnał, spór = wracamy do historii minut.
"""

from __future__ import annotations

import re
import unicodedata

from curl_cffi import requests

URL = "https://www.rotowire.com/soccer/lineups.php?league=WOC"


def _norm(s: str) -> str:
    """Normalizacja nazwy (zawodnik/drużyna): bez akcentów, małe litery."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def fetch_predicted_lineups(include_tomorrow: bool = True) -> dict[str, dict]:
    """Pobierz przewidywane XI z Rotowire.

    Zwraca mapę: znormalizowana nazwa drużyny -> {
        "xi": zbiór znormalizowanych pełnych nazwisk w przewidywanej XI,
        "confirmed": bool (Rotowire oznaczył skład jako potwierdzony),
    }
    Pusta mapa = strona niedostępna / brak meczów.
    """
    out: dict[str, dict] = {}
    urls = [URL] + ([URL + "&date=tomorrow"] if include_tomorrow else [])
    for url in urls:
        try:
            r = requests.get(url, impersonate="chrome124", timeout=30)
            r.raise_for_status()
        except Exception:
            continue
        for blok in r.text.split('class="lineup is-soccer"')[1:]:
            teams = [
                s.strip()
                for s in re.findall(r"lineup__mteam[^>]*>\s*([^<]{2,40})", blok)
            ]
            lists = re.findall(r'lineup__list[^"]*"(.*?)</ul>', blok, re.S)
            if len(teams) < 2 or len(lists) < 2:
                continue
            for team, lst in zip(teams[:2], lists[:2]):
                confirmed = "is-confirmed" in lst[:400]
                # tylko XI: zawodnicy przed separatorem sekcji kontuzji
                xi_html = lst.split("lineup__title")[0]
                players = {
                    _norm(n) for n in re.findall(r'title="([^"]+)"', xi_html)
                }
                if players:
                    key = _norm(team)
                    # nie nadpisuj dzisiejszego meczu jutrzejszym
                    if key not in out:
                        out[key] = {"xi": players, "confirmed": confirmed}
    return out


def _in_xi(xi: set[str], player: str) -> bool:
    """Dopasowanie nazwiska z tolerancją na warianty imion.

    Najpierw dokładne; potem nazwisko + inicjał imienia
    ("nicolas paz" ~ "nico paz", "julian alvarez" ~ "julian alvarez").
    """
    p = _norm(player)
    if p in xi:
        return True
    pt = p.split()
    if not pt:
        return False
    for cand in xi:
        ct = cand.split()
        if ct and pt[-1] == ct[-1] and pt[0][:1] == ct[0][:1]:
            return True
    return False


def predicted_status(
    lineups: dict[str, dict], team_name: str, player_name: str
) -> bool | None:
    """Czy zawodnik jest w przewidywanej XI wg Rotowire.

    True/False gdy Rotowire ma skład tej drużyny; None gdy drużyny brak.
    """
    entry = lineups.get(_norm(team_name))
    if entry is None:
        return None
    return _in_xi(entry["xi"], player_name)


def is_confirmed(lineups: dict[str, dict], team_name: str) -> bool:
    """Czy Rotowire oznaczył skład drużyny jako potwierdzony."""
    entry = lineups.get(_norm(team_name))
    return bool(entry and entry["confirmed"])
