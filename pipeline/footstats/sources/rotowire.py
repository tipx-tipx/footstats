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

_BAZA = "https://www.rotowire.com/soccer/lineups.php"

# ⚑ MUNDIAL SKOŃCZYŁ SIĘ 19.07, A MY PYTALIŚMY O NIEGO DO 11.08 (trzy tygodnie).
#
# Adres był zaszyty jako `?league=WOC` — kod mistrzostw świata — z czasów, gdy
# to był cały nasz produkt. Po przejściu na ligi strona oddawała pustą listę,
# a `fetch_predicted_lineups` traktuje pustkę i awarię tak samo, więc **nic
# nie krzyczało**. Skutek zmierzony 11.08: składy dla 13 z 307 meczów, 199 par
# (mecz, zawodnik) odpadało jako „poza znanym składem", zakładka zawodnicza
# bez typu od 05.08, drabinki na trzech wznowionych kartach.
#
# UCZCIWIE O ZASIĘGU: Rotowire kwotuje głównie Europę Zachodnią i MLS, a nasz
# zakres to w większości Ameryka Południowa i Skandynawia. To źródło NIE
# rozwiąże problemu składów — jest darmowe i warto je mieć, ale głównym
# zostaje Sofascore. Lista kodów poniżej to te ligi Rotowire, które faktycznie
# przecinają się z naszym terminarzem; nieznany kod oddaje pustą stronę, więc
# nadmiar w tej liście kosztuje jedno zapytanie, a nie awarię.
LIGI = (
    "EPL",          # Premier League
    "LALIGA",       # La Liga
    "SERIEA",       # Serie A
    "BUNDESLIGA",
    "LIGUE1",
    "MLS",
    "UCL",          # Liga Mistrzów (u nas kwalifikacje)
    "UEL",          # Liga Europy
)

# zostawione dla zgodności z testami i starymi wywołaniami
URL = f"{_BAZA}?league={LIGI[0]}"


# Litery, których NFKD NIE rozkłada, bo w Unicode są OSOBNYMI znakami
# alfabetu, a nie "literą + diakrytem": ł nie jest "l z kreską", tylko własnym
# kodem. Rozkład na znaki łączące ich nie tyka, więc przechodziły przez
# normalizację nietknięte — a źródła (statshub, bank stylu, Rotowire) trzymają
# nazwy już zwinięte do ASCII. Efekt: każda drużyna z ł w nazwie nigdy nie
# trafiała w bank. Zmierzone 2026-07-26: 0 z 287 kluczy banku ligowego
# zawierało ł, a lookup Wisły Kraków szedł po "wisła krakow" i wracał pusty —
# padały przez to Wisła (obie), Widzew Łódź, Zagłębie Lubin, Jagiellonia
# Białystok, Śląsk Wrocław, czyli pół Ekstraklasy.
# Reszta tablicy to ten sam problem w ligach, które i tak obsługujemy:
# skandynawskie ø/æ, bałkańskie đ, islandzkie þ/ð, niemieckie ß.
_NIEROZKLADALNE = str.maketrans({
    "ł": "l", "Ł": "L",
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D", "ð": "d", "Ð": "D",
    "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
    "þ": "th", "Þ": "TH",
    "ß": "ss", "ı": "i",
})


def _norm(s: str) -> str:
    """Normalizacja nazwy (zawodnik/drużyna): bez akcentów, małe litery."""
    s = s.translate(_NIEROZKLADALNE)
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
    urls = []
    for liga in LIGI:
        urls.append(f"{_BAZA}?league={liga}")
        if include_tomorrow:
            urls.append(f"{_BAZA}?league={liga}&date=tomorrow")
    ok_stron = 0
    for url in urls:
        try:
            r = requests.get(url, impersonate="chrome124", timeout=30)
            r.raise_for_status()
        except Exception:
            continue
        ok_stron += 1
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
    # ⚑ ROZRÓŻNIENIE „PUSTO" OD „PADŁO" — brak tego przepuścił mundial przez
    # trzy tygodnie. Zero składów przy zero odpowiedziach to awaria źródła;
    # zero składów przy działających stronach to normalna noc bez meczów.
    if not ok_stron:
        print("Rotowire: ŻADNA ze stron nie odpowiedziała "
              f"({len(urls)} prób) — źródło niedostępne, nie brak meczów")
    elif not out:
        print(f"Rotowire: {ok_stron} stron odpowiedziało, ale ani jednego "
              "składu — sprawdź kody lig w `LIGI`, jeśli to się powtarza")
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
