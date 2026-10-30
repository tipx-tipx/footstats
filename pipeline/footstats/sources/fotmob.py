"""Źródło statystyk: FotMob — zastępca statshub od 30.10.2026 (plan: docs/plan-fotmob.md).

PO CO. 29.10 ~18 UTC statshub postawił przed API wyzwanie Cloudflare (403
z chmury i z domu). Pomiar 30.10 na tych samych zawodnikach i meczach:
liczby FotMob = statshub w 96–100% na każdym rynku, a mapa strzałów ma wprost
„z pola / spoza pola", część ciała i połowę.

JAK GRAMY ZE ŹRÓDŁEM (warunek, żeby działało latami, a nie tygodniami):
  * mały, równy ruch: odstęp ODSTEP_S + losowy rozrzut, żadnych zrywów;
    mecz zakończony pobieramy RAZ (potem baza meczów), w procesie wszystko
    przechodzi przez pamięć podręczną,
  * twardy limit zapytań na proces (LIMIT_ZAPYTAN) — przekroczenie to błąd
    w kodzie wołającym, nie powód, żeby źródło dostało tysiąc zapytań,
  * odmowa (403/429/wyzwanie) = natychmiastowa PAUZA do końca procesu: kolejne
    wywołania rzucają `FotmobOdmowa` bez wychodzenia do sieci. Statshub
    pokazał, że ponawianie w kółko po odcięciu niczego nie ratuje,
  * zwykłe zapytania — bez podszywania się i bez obchodzenia zabezpieczeń.

Kształty odpowiedzi (sprawdzone na żywo 30.10, docs/etap0-mapowanie.md):
  * `matches?date=RRRRMMDD` → leagues[].{id, name, ccode, matches[]}; mecz:
    id, timeTS (ms), home/away {id, name, score}, status {utcTime, started,
    finished, cancelled, reason.short: FT/AET/Pen/PP/Can/Ab}
  * `matchDetails?matchId=` → general, header.status, content.{playerStats,
    shotmap.shots, stats.Periods.All/FirstHalf/SecondHalf, lineup,
    matchFacts.events.events, matchFacts.infoBox.Referee}
  * `teams?id=`, `playerData?id=` — kadra, profil (wzrost, noga), ostatnie mecze
"""

from __future__ import annotations

import random
import time
from collections import Counter

from curl_cffi import requests

from .. import diagnostyka

BASE = "https://www.fotmob.com/api/data"
# ⚑ USER-AGENT JEST OBOWIĄZKOWY (30.10): zapora CloudFront przed FotMob odrzuca
# zapytanie BEZ tego nagłówka („403 Request blocked"), a curl_cffi bez
# `impersonate` żadnego nie wysyła. Uczciwy, własny – nie udajemy przeglądarki
HEADERS = {"Accept": "application/json", "User-Agent": "footstats-pipeline/1.0"}

ODSTEP_S = 2.0            # minimalny odstęp między zapytaniami
ROZRZUT_S = 1.0           # losowy dodatek do odstępu (równy, nieskokowy ruch)
LIMIT_ZAPYTAN = 600       # na proces; cykl docelowo mieści się w ułamku tego
TIMEOUT_S = 30
PAUZA_PONOWIENIA_S = 10   # jedno ponowienie przy timeoucie / 5xx

# kody i treści, które znaczą „źródło nie chce nas obsłużyć" — wtedy pauza
KODY_ODMOWY = {401, 403, 429}
ZNAKI_WYZWANIA = ("just a moment", "challenge-platform", "cf-mitigated", "captcha")


class FotmobOdmowa(RuntimeError):
    """Źródło odmówiło (albo wcześniej w tym procesie odmówiło) — nie pytamy dalej."""


class FotmobLimit(RuntimeError):
    """Przekroczony LIMIT_ZAPYTAN w procesie — błąd w kodzie wołającym."""


_stan: dict = {"wstrzymany": None, "ostatnie": 0.0}
_licznik: Counter = Counter()
_cache: dict[str, dict] = {}


def statystyki() -> dict:
    """Do logu cyklu: ile zapytań poszło, ile z pamięci, czy była odmowa."""
    return {"zapytania": _licznik["zapytania"], "z_pamieci": _licznik["z_pamieci"],
            "ponowienia": _licznik["ponowienia"], "odmowa": _stan["wstrzymany"]}


def wyczysc() -> None:
    """Reset stanu procesu (testy, osobne przebiegi w jednym procesie)."""
    _stan.update(wstrzymany=None, ostatnie=0.0)
    _licznik.clear()
    _cache.clear()


def _odczekaj() -> None:
    teraz = time.monotonic()
    czekaj = _stan["ostatnie"] + ODSTEP_S + random.uniform(0, ROZRZUT_S) - teraz
    if czekaj > 0:
        time.sleep(czekaj)
    _stan["ostatnie"] = time.monotonic()


def _to_odmowa(r) -> str | None:
    kod = getattr(r, "status_code", None)
    if kod in KODY_ODMOWY:
        return f"HTTP {kod}"
    if (getattr(r, "headers", None) or {}).get("cf-mitigated"):
        return "cf-mitigated"
    typ = str((getattr(r, "headers", None) or {}).get("content-type", ""))
    if "html" in typ:
        tekst = (getattr(r, "text", "") or "")[:3000].lower()
        if any(z in tekst for z in ZNAKI_WYZWANIA):
            return "strona wyzwania"
    return None


def _get(sciezka: str, **params) -> dict:
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}/{sciezka}" + (f"?{q}" if q else "")
    if url in _cache:
        _licznik["z_pamieci"] += 1
        return _cache[url]
    if _stan["wstrzymany"]:
        raise FotmobOdmowa(f"FotMob wstrzymany w tym procesie ({_stan['wstrzymany']})")
    blad = None
    for proba in range(2):
        if _licznik["zapytania"] >= LIMIT_ZAPYTAN:
            raise FotmobLimit(f"przekroczony limit {LIMIT_ZAPYTAN} zapytań FotMob w procesie")
        _odczekaj()
        _licznik["zapytania"] += 1
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT_S)
        except Exception as e:                                  # timeout, sieć
            blad = e
        else:
            powod = _to_odmowa(r)
            if powod:
                _stan["wstrzymany"] = powod
                diagnostyka.cichy("fotmob", "odmowa", RuntimeError(f"{powod}: {sciezka}"))
                raise FotmobOdmowa(f"FotMob odmówił ({powod}) na {sciezka}")
            if getattr(r, "status_code", 200) >= 500:
                blad = RuntimeError(f"HTTP {r.status_code}")
            else:
                r.raise_for_status()
                dane = r.json()
                _cache[url] = dane
                return dane
        if proba == 0:
            _licznik["ponowienia"] += 1
            time.sleep(PAUZA_PONOWIENIA_S)
    raise RuntimeError(f"FotMob nie odpowiedział na {sciezka}: {blad!r}")


# --- terminarz -------------------------------------------------------------

def status_meczu(status: dict) -> str:
    """Status FotMob → słownik statshub (notstarted/inprogress/finished/
    postponed/canceled/abandoned), którego używa reszta pipeline'u."""
    powod = str(((status or {}).get("reason") or {}).get("short") or "")
    if powod == "PP":
        return "postponed"
    if powod == "Can":
        return "canceled"
    if powod == "Ab":
        return "abandoned"
    if (status or {}).get("finished"):
        return "finished"
    if (status or {}).get("started"):
        return "inprogress"
    return "notstarted"


def mecze_dnia(data: str) -> list[dict]:
    """Mecze dnia `RRRRMMDD` w płaskiej postaci (jedno zapytanie na dzień)."""
    d = _get("matches", date=data)
    out = []
    for liga in d.get("leagues") or []:
        for m in liga.get("matches") or []:
            st = m.get("status") or {}
            out.append({
                "id": int(m["id"]),
                "start_ts": int(m.get("timeTS") or 0) // 1000,
                "home_id": int((m.get("home") or {}).get("id") or 0),
                "home": str((m.get("home") or {}).get("name") or ""),
                "away_id": int((m.get("away") or {}).get("id") or 0),
                "away": str((m.get("away") or {}).get("name") or ""),
                "liga_id": int(liga.get("primaryId") or liga.get("id") or 0),
                "liga": str(liga.get("name") or ""),
                "kraj": str(liga.get("ccode") or ""),
                "status": status_meczu(st),
                "powod": str((st.get("reason") or {}).get("short") or ""),
            })
    return out


# --- mecz, drużyna, zawodnik -----------------------------------------------

def szczegoly_meczu(match_id: int) -> dict:
    """Pełne szczegóły meczu (surowe: general, header, content)."""
    return _get("matchDetails", matchId=int(match_id))


def druzyna(team_id: int) -> dict:
    return _get("teams", id=int(team_id))


def zawodnik(player_id: int) -> dict:
    return _get("playerData", id=int(player_id))
