"""Tryb ligowy — cykl budowy (faza 2 roadmapy, w budowie).

ETAP 1 (ten plik dziś): fundament danych — odkrywanie meczów i parowanie
statshub ↔ Superbet dla KLUBÓW + raport pokrycia (dry-run, bez publikacji).

Czym różni się od build_wc_fast:

* mecze ze WSZYSTKICH rozgrywek statshub (nie tylko utid=16); zakres
  drużynowy wyznacza footstats.rozgrywki, propsy — oferta bukmachera,
* parowanie z Superbetem po ZNORMALIZOWANYCH nazwach klubów z bramkowaniem
  czasem (±3 h) — w lidze te same drużyny grają wielokrotnie, a słownik
  TEAM_PL_EN (reprezentacje po polsku) jest bezużyteczny dla klubów,
* luka pokrycia jest MIERZONA i raportowana, nie ignorowana: mecze
  Superbetu z propsami bez danych statshub to świadomie odłożony kawałek
  świata, o którym wiemy.

Scoring/typy/kupony dojdą w następnych etapach — będą reużywać klocków
z build_wc_fast (score_from_trend, bank trendów, rozliczenia).
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field

from curl_cffi import requests

from .. import rozgrywki
from ..sources import superbet

SH_BASE = "https://www.statshub.com/api"
SH_HEADERS = {"Accept": "application/json", "Referer": "https://www.statshub.com/"}

# maksymalna różnica kickoffu statshub vs Superbet przy parowaniu meczu
OKNO_CZASU_S = 3 * 3600

# minimalne podobieństwo nazw (średnia z obu stron), żeby uznać parę
PROG_PODOBIENSTWA = 0.51


def _sh(url: str) -> dict:
    r = requests.get(url, impersonate="chrome124", timeout=30, headers=SH_HEADERS)
    r.raise_for_status()
    return r.json()


@dataclass
class MeczLigowy:
    """Nadchodzący mecz z statshub, wzbogacony o profil i (po parowaniu)
    o event Superbetu."""

    event_id: int
    utid: int
    rozgrywki_nazwa: str
    kraj: str
    home_id: int
    away_id: int
    home: str
    away: str
    kickoff_ts: int
    has_odd: bool
    druzynowe: bool
    sb_event: dict | None = None
    sb_podobienstwo: float = 0.0


def upcoming_events(days: int = 6) -> list[MeczLigowy]:
    """Nadchodzące mecze WSZYSTKICH rozgrywek z statshub (event/by-date).

    Nazwy drużyn i rozgrywek siedzą w polach RÓWNOLEGŁYCH do events
    (homeTeam/awayTeam/unique_tournaments/categories) — build_wc_fast ich
    nie potrzebował (reprezentacje szły przez slug), kluby potrzebują.
    """
    now = int(time.time())
    out: dict[int, MeczLigowy] = {}
    for d in range(days):
        start = now + d * 86400
        start -= start % 86400
        try:
            data = _sh(
                f"{SH_BASE}/event/by-date?startOfDay={start}&endOfDay={start + 86399}"
            ).get("data", [])
        except Exception:
            continue
        for e in data:
            ev = e.get("events") or {}
            if ev.get("status") != "notstarted":
                continue
            ut = e.get("unique_tournaments") or {}
            utid = ev.get("uniqueTournamentId") or ut.get("id")
            ht, at = e.get("homeTeam") or {}, e.get("awayTeam") or {}
            if not (utid and ev.get("id") and ht.get("name") and at.get("name")):
                continue
            p = rozgrywki.profil_lub_domyslny(
                utid, nazwa=str(ut.get("name") or ""),
                kraj=str((e.get("categories") or {}).get("name") or ""),
            )
            out[ev["id"]] = MeczLigowy(
                event_id=ev["id"],
                utid=int(utid),
                rozgrywki_nazwa=p.nazwa,
                kraj=p.kraj,
                home_id=int(ht.get("id") or 0),
                away_id=int(at.get("id") or 0),
                home=str(ht.get("name")),
                away=str(at.get("name")),
                kickoff_ts=int(ev.get("timeStartTimestamp") or 0),
                has_odd=bool(e.get("hasOdd")),
                druzynowe=p.druzynowe,
            )
    return sorted(out.values(), key=lambda m: m.kickoff_ts)


# ---------------------------------------------------------------------------
# Parowanie nazw klubów statshub ↔ Superbet
# ---------------------------------------------------------------------------

# tokeny-ozdobniki form prawnych/przydomków — nie niosą tożsamości klubu
_SMIECI = {
    "fc", "cf", "afc", "cfr", "fk", "sk", "sc", "ac", "as", "ca", "cd", "cs",
    "sv", "vfb", "vfl", "tsg", "rb", "bk", "if", "ff", "aik", "ks", "mks",
    "gks", "rks", "lks", "club", "cp", "ud", "ss", "us", "u", "de", "do",
    "the", "team", "kf", "nk", "hnk", "pfc",
}

# aliasy: znormalizowana nazwa Superbetu -> znormalizowana nazwa statshub.
# Dopisywać, gdy raport pokrycia zgłosi niedopasowaną parę, którą człowiek
# widzi na oko (skróty regionalne, przydomki). Klucze i wartości MUSZĄ być
# w postaci po norm_klub().
KLUB_ALIASY: dict[str, str] = {
    "atletico mg": "atletico mineiro",
    "atletico pr": "athletico paranaense",
    "america mg": "america mineiro",
}


# litery, których NFKD NIE rozkłada (to osobne znaki, nie diakrytyki):
# bez tej tablicy 'København' gubi 'ø', a 'Łódź' gubi 'ł'
_TRANSLITERACJA = str.maketrans({
    "ø": "o", "Ø": "o", "ł": "l", "Ł": "l", "đ": "d", "Đ": "d",
    "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe", "ß": "ss",
    "þ": "th", "Þ": "th", "ð": "d", "Ð": "d",
})


def norm_klub(nazwa: str) -> str:
    """Znormalizowana nazwa klubu: bez diakrytyków, małe litery, bez
    ozdobników (FC/IF/SK...), tokeny posortowane.

    'IFK Göteborg' i 'Goteborg IFK' -> 'goteborg ifk' -> po sortowaniu equal.
    """
    s = str(nazwa or "").translate(_TRANSLITERACJA)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    tokeny = [t for t in re.split(r"[^a-z0-9]+", s) if t]
    istotne = [t for t in tokeny if t not in _SMIECI]
    if not istotne:  # nazwa złożona z samych "śmieci" (np. "AIK") — zostaw
        istotne = tokeny
    return " ".join(sorted(istotne))


def podobienstwo_klubu(a: str, b: str) -> float:
    """Podobieństwo znormalizowanych nazw klubów w [0,1].

    Nakładanie tokenów względem KRÓTSZEJ nazwy (Superbet skraca: 'Atletico
    MG' vs 'Atlético Mineiro'), z bonusem za pełną równość i aliasami na
    trudne przypadki.
    """
    na, nb = norm_klub(a), norm_klub(b)
    if not na or not nb:
        return 0.0
    na = KLUB_ALIASY.get(na, na)
    nb = KLUB_ALIASY.get(nb, nb)
    if na == nb:
        return 1.0
    ta, tb = na.split(), nb.split()
    zajete: set[int] = set()
    wspolne = 0
    for x in ta:
        for j, y in enumerate(tb):
            if j in zajete:
                continue
            if _tokeny_pasuja(x, y):
                zajete.add(j)
                wspolne += 1
                break
    return wspolne / min(len(ta), len(tb))


def _tokeny_pasuja(a: str, b: str) -> bool:
    """Tokeny równe albo jeden prefiksem drugiego (>=5 znaków).

    Łapie odmiany typu 'Djurgarden' vs 'Djurgardens' bez ryzyka sklejenia
    krótkich skrótów ('mg' vs 'mineiro' NIE przechodzi — od tego aliasy).
    """
    if a == b:
        return True
    return len(a) >= 5 and len(b) >= 5 and (a.startswith(b) or b.startswith(a))


def _sb_kickoff(ev: dict) -> int:
    """Kickoff eventu Superbetu w sekundach.

    UWAGA pułapka: matchTimestamp to czas AKTUALIZACJI oferty (zmierzone
    2026-07-20: równy „teraz"), prawdziwy kickoff siedzi w unixDateMillis
    (zgodny co do sekundy z timeStartTimestamp statshub).
    """
    try:
        ts = int(ev.get("unixDateMillis") or 0)
        return ts // 1000 if ts > 1e11 else ts
    except (TypeError, ValueError):
        return 0


def paruj_superbet(
    mecze: list[MeczLigowy], sb_events: list[dict]
) -> tuple[int, list[dict]]:
    """Dopasuj mecze statshub do eventów Superbetu (nazwy + okno czasu).

    Mutuje mecze (sb_event/sb_podobienstwo). Zwraca (ile sparowano,
    lista eventów Superbetu, które zostały BEZ pary — luka pokrycia).
    Każdy event Superbetu może być użyty raz (najlepsza para wygrywa).
    """
    kandydaci: list[tuple[float, MeczLigowy, int]] = []
    sb_parsed: list[tuple[int, str, str, int]] = []  # (idx, home, away, ts)
    for i, ev in enumerate(sb_events):
        parts = [p.strip() for p in str(ev.get("matchName") or "").split("·")]
        if len(parts) != 2:
            continue
        sb_parsed.append((i, parts[0], parts[1], _sb_kickoff(ev)))
    for m in mecze:
        for i, sb_h, sb_a, sb_ts in sb_parsed:
            if sb_ts and m.kickoff_ts and abs(sb_ts - m.kickoff_ts) > OKNO_CZASU_S:
                continue
            sim = (podobienstwo_klubu(m.home, sb_h)
                   + podobienstwo_klubu(m.away, sb_a)) / 2.0
            if sim >= PROG_PODOBIENSTWA:
                kandydaci.append((sim, m, i))
    # zachłannie od najlepszych par; mecz i event użyte najwyżej raz
    kandydaci.sort(key=lambda k: -k[0])
    zajete_sb: set[int] = set()
    zajete_m: set[int] = set()
    n = 0
    for sim, m, i in kandydaci:
        if i in zajete_sb or m.event_id in zajete_m:
            continue
        zajete_sb.add(i)
        zajete_m.add(m.event_id)
        m.sb_event = sb_events[i]
        m.sb_podobienstwo = sim
        n += 1
    luka = [sb_events[i] for i, _h, _a, _ts in sb_parsed if i not in zajete_sb]
    return n, luka


# ---------------------------------------------------------------------------
# Raport pokrycia (dry-run etapu 1)
# ---------------------------------------------------------------------------

def raport_pokrycia(days: int = 4) -> dict:
    """Zmierz na żywo: co statshub widzi, co Superbet kwotuje, co się paruje.

    Zwraca strukturę raportu; wypisuje czytelne podsumowanie na stdout.
    """
    mecze = upcoming_events(days)
    print(f"statshub: {len(mecze)} nadchodzących meczów "
          f"({len(set(m.utid for m in mecze))} rozgrywek, {days} dni)")
    sb_events = superbet.list_events(days_ahead=days)
    print(f"Superbet: {len(sb_events)} meczów w ofercie")
    n_par, luka = paruj_superbet(mecze, sb_events)
    print(f"Sparowano: {n_par}")

    per_rozgrywki: dict[str, dict] = {}
    for m in mecze:
        r = per_rozgrywki.setdefault(
            m.rozgrywki_nazwa,
            {"kraj": m.kraj, "mecze": 0, "sparowane": 0, "druzynowe": m.druzynowe},
        )
        r["mecze"] += 1
        if m.sb_event is not None:
            r["sparowane"] += 1

    print("\nPokrycie per rozgrywki (sparowane/mecze; * = zakres drużynowy):")
    for nazwa, r in sorted(per_rozgrywki.items(),
                           key=lambda kv: -kv[1]["sparowane"]):
        gw = "*" if r["druzynowe"] else " "
        print(f"  {gw} {r['sparowane']:>3}/{r['mecze']:<3} [{r['kraj']}] {nazwa}")

    # luka pokrycia: bogata oferta Superbetu (heurystyka: dużo rynków =
    # prawie na pewno propsy) bez odpowiednika w statshub
    luka_propsy = [ev for ev in luka if (ev.get("marketCount") or 0) >= 100]
    print(f"\nLuka pokrycia: {len(luka)} meczów Superbetu bez pary, "
          f"w tym {len(luka_propsy)} z bogatą ofertą (marketCount>=100):")
    for ev in sorted(luka_propsy, key=lambda e: -(e.get("marketCount") or 0))[:15]:
        print(f"    {ev.get('matchName')} (rynków: {ev.get('marketCount')})")

    niedopasowane = [m for m in mecze if m.sb_event is None]
    return {
        "mecze": mecze,
        "sparowane": n_par,
        "per_rozgrywki": per_rozgrywki,
        "luka_superbet": luka,
        "statshub_bez_superbetu": niedopasowane,
    }


def main() -> None:
    raport_pokrycia()


if __name__ == "__main__":
    main()
