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


# --- mecz → wiersz bazy (etap 2) -------------------------------------------
#
# Jeden zakończony mecz = jeden rekord bazy meczów. Liczby strzałów idą z MAPY
# STRZAŁÓW i tylko z czasu regularnego (1. i 2. połowa) – bukmacher rozlicza
# 90 minut; seria karnych (`PenaltyShootout`) i dogrywka nie wchodzą. Gdy mapy
# brak (część mniejszych lig), strzały biorą się z `playerStats` (te zawierają
# ewentualną dogrywkę – mecze z dogrywką są w takich ligach rzadkie), a rynki
# zza pola / głową / 1. połowa zostają PUSTE (None), nie zero – brak danych to
# nie „0 strzałów głową" (ta sama zasada co `extra-stats` statshub).
#
# Sprawdzone na 320 meczach 28–29.10: „Blocked shots" zawodnika = jego strzały
# zablokowane (98% zgodne z mapą), kartki: Yellow / Red / YellowRed.

OKRESY_REGULARNE = {"FirstHalf", "SecondHalf"}

# playerStats (nazwa FotMob) → nasz kod; brak pola u zawodnika ze statystykami = 0
POLA_ZAWODNIKA = {
    "Fouls committed": "fouls_committed", "Was fouled": "fouls_won",
    "Tackles": "tackles", "Interceptions": "interceptions", "Offsides": "offsides",
    "Successful dribbles": "dribbles_won", "Goals": "goals", "Assists": "assists",
    "Expected goals (xG)": "xg",
    # suma drużyny = odpowiednik `finalThirdEntries` statshub (cecha `f3` modelu
    # drużyn): korelacja 0,962, stosunek 0,912 na 449 meczach (etap 2, 30.10)
    "Passes into final third": "passes_final_third",
}
# zapas strzałów, gdy meczu nie ma na mapie strzałów
POLA_STRZALOW = {
    "Total shots": "shots", "Shots on target": "sot",
    "Shots off target": "shots_off_target", "Blocked shots": "shots_blocked",
}
RYNKI_Z_MAPY = ("shots_outside_box", "sot_outside_box", "headed_shots", "headed_sot",
                "fh_shots", "fh_sot")

# statystyki drużyny (klucz FotMob → nasz kod)
POLA_DRUZYNY = {
    "total_shots": "shots", "ShotsOnTarget": "sot", "ShotsOffTarget": "shots_off_target",
    "blocked_shots": "shots_blocked", "shots_inside_box": "shots_inside_box",
    "shots_outside_box": "shots_outside_box", "corners": "corners", "fouls": "fouls",
    "yellow_cards": "yellow_cards", "red_cards": "red_cards", "Offsides": "offsides",
    "BallPossesion": "possession", "expected_goals": "xg",
    "matchstats.headers.tackles": "tackles", "interceptions": "interceptions",
    "keeper_saves": "saves", "touches_opp_box": "touches_opp_box",
    "accurate_crosses": "accurate_crosses",
}
OKRESY_DRUZYNY = {"All": "all", "FirstHalf": "h1", "SecondHalf": "h2"}


def _liczba(v) -> float | None:
    """'283 (75%)' → 283, '0.83' → 0.83, 7 → 7; reszta → None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).split()[0].rstrip("%"))
    except (ValueError, IndexError):
        return None


def _pozycja(position_id, usual) -> str:
    """Litera pozycji G/D/M/F jak w statshub. `positionId` to miejsce w ustawieniu
    meczu (sprawdzone na 5300 starterach: 11 = bramkarz, 30–59 obrona, 60–79
    pomoc, 80–89 skrzydła – według zwykłej pozycji, 100+ atak); bez niego zwykła
    pozycja zawodnika (0 G, 1 D, 2 M, 3 F)."""
    zwykla = {0: "G", 1: "D", 2: "M", 3: "F"}.get(usual)
    p = position_id if isinstance(position_id, int) else -1
    if p == 11:
        return "G"
    if 30 <= p <= 59:
        return "D"
    if 60 <= p <= 79:
        return "M"
    if 80 <= p <= 89:
        return "F" if zwykla == "F" else "M"
    if p >= 100:
        return "F"
    return zwykla or "M"


def _gole_po_90(content: dict, koncowy: tuple[int, int], dogrywka: bool) -> tuple[int, int]:
    """Wynik po regularnym czasie: przy dogrywce z zdarzenia „Half" w 90. minucie."""
    if not dogrywka:
        return koncowy
    for e in ((content.get("matchFacts") or {}).get("events") or {}).get("events") or []:
        if e.get("type") == "Half" and int(e.get("time") or 0) == 90:
            return int(e.get("homeScore") or 0), int(e.get("awayScore") or 0)
    return koncowy


def mecz_do_bazy(dane: dict) -> dict:
    """Surowe `matchDetails` → rekord bazy meczów (kształt: docs/etap0-mapowanie.md)."""
    general = dane.get("general") or {}
    header = dane.get("header") or {}
    c = dane.get("content") or {}
    st = header.get("status") or {}
    druz = header.get("teams") or [{}, {}]
    home, away = druz[0] or {}, druz[1] or {}
    hid, aid = int(home.get("id") or 0), int(away.get("id") or 0)
    powod = str((st.get("reason") or {}).get("short") or "")
    dogrywka = powod in ("AET", "Pen")
    koncowy = (int(home.get("score") or 0), int(away.get("score") or 0))
    ts = 0
    if st.get("utcTime"):
        from datetime import datetime
        ts = int(datetime.fromisoformat(str(st["utcTime"]).replace("Z", "+00:00")).timestamp())

    # --- drużyny: statystyki per okres ------------------------------------
    druzyny: dict[str, dict] = {str(hid): {}, str(aid): {}}
    for okres, kod_okresu in OKRESY_DRUZYNY.items():
        blok = (((c.get("stats") or {}).get("Periods") or {}).get(okres) or {}).get("stats") or []
        wart: dict[str, list] = {}
        for grupa in blok:
            for s in grupa.get("stats") or []:
                kod = POLA_DRUZYNY.get(str(s.get("key")))
                para = s.get("stats")
                if kod and isinstance(para, list) and len(para) == 2 and kod not in wart:
                    wart[kod] = [_liczba(para[0]), _liczba(para[1])]
        if wart:
            for i, tid in enumerate((hid, aid)):
                druzyny[str(tid)][kod_okresu] = {k: v[i] for k, v in wart.items() if v[i] is not None}

    # --- skład, wejścia/zejścia, kartki -----------------------------------
    lu = c.get("lineup") or {}
    sklad: dict[int, dict] = {}
    for strona, tid in (("homeTeam", hid), ("awayTeam", aid)):
        t = lu.get(strona) or {}
        # zawodnik bez numeru FotMob (id 0 – bywa w składach mniejszych lig)
        # jest nie do zidentyfikowania i nie trafia do bazy
        for p in t.get("starters") or []:
            if int(p.get("id") or 0):
                sklad[int(p["id"])] = {"team_id": tid, "start": True, "name": p.get("name"),
                                       "poz": _pozycja(p.get("positionId"), p.get("usualPlayingPositionId"))}
        for p in t.get("subs") or []:
            if int(p.get("id") or 0):
                sklad.setdefault(int(p["id"]), {"team_id": tid, "start": False, "name": p.get("name"),
                                                "poz": _pozycja(None, p.get("usualPlayingPositionId"))})
    wszedl: dict[int, int] = {}
    zszedl: dict[int, int] = {}
    # kto za kogo (31.10): rozliczanie potrzebuje numeru zmiennika – reguła
    # „superzmiany” (statshub `substitutedIn` / `substitutedOut`)
    zmiana_za: dict[int, int] = {}
    zmiana_przez: dict[int, int] = {}
    zolte: Counter = Counter()
    czerwone: Counter = Counter()
    for e in ((c.get("matchFacts") or {}).get("events") or {}).get("events") or []:
        if e.get("type") == "Substitution" and len(e.get("swap") or []) == 2:
            # swap[0] wchodzi, swap[1] schodzi (sprawdzone na składach 30.10)
            na, z = int(e["swap"][0]["id"]), int(e["swap"][1]["id"])
            wszedl[na] = int(e.get("time") or 0)
            zszedl[z] = int(e.get("time") or 0)
            zmiana_za[na], zmiana_przez[z] = z, na
        elif e.get("type") == "Card" and e.get("playerId"):
            if e.get("card") == "Yellow":
                zolte[int(e["playerId"])] += 1
            elif e.get("card") in ("Red", "YellowRed"):
                czerwone[int(e["playerId"])] += 1

    # --- mapa strzałów (tylko czas regularny) -----------------------------
    strzaly = [s for s in (c.get("shotmap") or {}).get("shots") or []
               if not s.get("isOwnGoal") and s.get("period") in OKRESY_REGULARNE]
    jest_mapa = bool((c.get("shotmap") or {}).get("shots"))
    z_mapy: dict[int, Counter] = {}
    for s in strzaly:
        k = z_mapy.setdefault(int(s["playerId"]), Counter())
        zablok = bool(s.get("isBlocked"))
        celny = bool(s.get("isOnTarget")) and not zablok
        glowa = s.get("shotType") == "Header"
        k["shots"] += 1
        k["sot"] += celny
        k["shots_blocked"] += zablok
        k["shots_off_target"] += (not celny and not zablok)
        if not s.get("isFromInsideBox"):
            k["shots_outside_box"] += 1
            k["sot_outside_box"] += celny
        if glowa:
            k["headed_shots"] += 1
            k["headed_sot"] += celny
        if s.get("period") == "FirstHalf":
            k["fh_shots"] += 1
            k["fh_sot"] += celny

    # --- zawodnicy --------------------------------------------------------
    ps = c.get("playerStats") or {}
    jest_staty = bool(ps)
    zawodnicy = []
    for pid in sorted(set(sklad) | {int(x) for x in ps}):
        info = sklad.get(pid, {})
        surowe = ps.get(str(pid)) or {}
        pola: dict[str, float] = {}
        for g in surowe.get("stats") or []:
            for nazwa, v in (g.get("stats") or {}).items():
                val = _liczba((v.get("stat") or {}).get("value"))
                if val is not None:
                    pola.setdefault(nazwa, val)
        team_id = int(surowe.get("teamId") or info.get("team_id") or 0)
        start = bool(info.get("start"))
        if "Minutes played" in pola:
            minuty = pola["Minutes played"]
        elif not jest_staty and info:
            # liga bez statystyk zawodników: minuty ze składu i zmian
            if start:
                minuty = float(zszedl.get(pid, 90))
            elif pid in wszedl:
                minuty = float(max(90 - wszedl[pid], 1))
            else:
                minuty = 0.0
        else:
            minuty = 0.0
        staty: dict[str, float | None] = {}
        if surowe:
            for nazwa, kod in POLA_ZAWODNIKA.items():
                staty[kod] = pola.get(nazwa, 0.0)
            if jest_mapa:
                k = z_mapy.get(pid, Counter())
                for kod in ("shots", "sot", "shots_off_target", "shots_blocked") + RYNKI_Z_MAPY:
                    staty[kod] = float(k.get(kod, 0))
            else:
                for nazwa, kod in POLA_STRZALOW.items():
                    staty[kod] = pola.get(nazwa, 0.0)
                for kod in RYNKI_Z_MAPY:
                    staty[kod] = None
        elif minuty == 0 and jest_staty:
            # niewykorzystany rezerwowy w meczu ze statystykami: jawne zera
            for kod in list(POLA_ZAWODNIKA.values()) + list(POLA_STRZALOW.values()):
                staty[kod] = 0.0
            for kod in RYNKI_Z_MAPY:
                staty[kod] = 0.0 if jest_mapa else None
        if staty or jest_staty:
            staty["yellow_card"] = float(zolte.get(pid, 0))
            staty["red_card"] = float(czerwone.get(pid, 0))
        zawodnicy.append({
            "pid": pid,
            "name": str(surowe.get("name") or info.get("name") or ""),
            "team_id": team_id,
            "minuty": float(minuty),
            "start": start,
            "wszedl": wszedl.get(pid),
            "zszedl": zszedl.get(pid),
            "poz": info.get("poz") or _pozycja(None, surowe.get("usualPosition")),
            "staty": staty or None,
            "zmiana_za": zmiana_za.get(pid),
            "zmiana_przez": zmiana_przez.get(pid),
        })

    # --- drużyny: poprawki z bramki etapu 2 (30.10) -----------------------
    for tid in (hid, aid):
        d = druzyny.setdefault(str(tid), {})
        # odbiory i przechwyty drużyny = suma zawodników: pole drużynowe FotMob
        # ma inną definicję (zgodne ze statshub w 80%), suma zawodników w 98%
        zaw = [z["staty"] for z in zawodnicy if z["team_id"] == tid and z["staty"]]
        if jest_staty and zaw and "all" in d:
            for kod in ("tackles", "interceptions", "passes_final_third"):
                d["all"][kod] = float(sum(s.get(kod) or 0 for s in zaw))
        # czas regularny (1. + 2. połowa) – rynki drużyn rozlicza się po 90 min,
        # a „All" przy dogrywce zawiera dogrywkę
        if "h1" in d and "h2" in d:
            d["reg"] = {k: d["h1"][k] + d["h2"][k] for k in d["h1"]
                        if k in d["h2"] and k not in ("possession", "xg")}

    sedzia = ((c.get("matchFacts") or {}).get("infoBox") or {}).get("Referee") or {}
    return {
        "id": int(general.get("matchId") or 0),
        "ts": ts,
        "liga_id": int(general.get("parentLeagueId") or general.get("leagueId") or 0),
        "liga": str(general.get("leagueName") or ""),
        "kraj": str(general.get("countryCode") or ""),
        "status": status_meczu(st),
        "powod": powod,
        "home": {"id": hid, "name": str(home.get("name") or "")},
        "away": {"id": aid, "name": str(away.get("name") or "")},
        "gole": list(koncowy),
        "gole90": list(_gole_po_90(c, koncowy, dogrywka)),
        "dogrywka": dogrywka,
        "karne": powod == "Pen",
        "sedzia": ({"id": sedzia.get("id"), "nazwa": sedzia.get("text"),
                    "kraj": sedzia.get("country")} if sedzia.get("text") else None),
        "staty_zawodnikow": jest_staty,
        "mapa_strzalow": jest_mapa,
        "druzyny": druzyny,
        "zawodnicy": zawodnicy,
        # surowa mapa strzałów (31.10) – zwięźle, czas regularny, bez samobójów:
        # [zawodnik, drużyna, x, y, sytuacja, część ciała, celny, zablokowany,
        #  z pola karnego, połowa, minuta, gol]. Bank stylu potrzebuje sytuacji
        # (kontra, rożny, rzut wolny, karny) i wykonawców stałych fragmentów –
        # a mecz pobieramy RAZ, więc czego tu nie zapiszemy, tego nie odzyskamy
        "strzaly": [[int(x.get("playerId") or 0), int(x.get("teamId") or 0),
                     round(float(x.get("x") or 0), 1), round(float(x.get("y") or 0), 1),
                     str(x.get("situation") or ""), str(x.get("shotType") or ""),
                     int(bool(x.get("isOnTarget")) and not bool(x.get("isBlocked"))),
                     int(bool(x.get("isBlocked"))), int(bool(x.get("isFromInsideBox"))),
                     1 if x.get("period") == "FirstHalf" else 2, int(x.get("min") or 0),
                     int(x.get("eventType") == "Goal")] for x in strzaly],
    }
