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
    kolejka: str = ""
    raw: dict = field(default_factory=dict)  # surowy event statshub (dla silnika)
    sb_event: dict | None = None
    sb_podobienstwo: float = 0.0


def _kolejka(ev: dict, tournaments: dict) -> str:
    """Etykieta rundy: 'Kolejka 3' z roundInfo albo faza z roundSlug/nazwy
    turnieju ('2nd-qualifying-round' -> '2nd qualifying round')."""
    slug = str(ev.get("roundSlug") or "").strip()
    if slug:
        return slug.replace("-", " ")
    # "LigaPro Serie A, Second Stage" -> "Second Stage"
    tname = str((tournaments or {}).get("name") or "")
    if "," in tname:
        return tname.split(",", 1)[1].strip()
    ri = ev.get("roundInfo")
    if isinstance(ri, int) and ri > 0:
        return f"Kolejka {ri}"
    return ""


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
                kolejka=_kolejka(ev, e.get("tournaments") or {}),
                raw=ev,
            )
    return sorted(out.values(), key=lambda m: m.kickoff_ts)


def past_events(
    team_ids: set[int], days_back: int = 10
) -> tuple[list[int], list[dict]]:
    """Rozegrane mecze z jednej pętli by-date wstecz, dwa cele naraz:

    * lista id meczów z udziałem podanych drużyn (bank historii trendów) —
      filtr po drużynach trzyma liczbę zapytań o trendy w ryzach,
    * surowe eventy rozgrywek z zakresu DRUŻYNOWEGO (bank stylu: shotmapy
      statshub potrzebują id + kickoff, niezależnie od drużyn cyklu).
    """
    now = int(time.time())
    ids: list[int] = []
    druzynowe: list[dict] = []
    for d in range(1, days_back + 1):
        start = now - d * 86400
        start -= start % 86400
        try:
            data = _sh(
                f"{SH_BASE}/event/by-date?startOfDay={start}&endOfDay={start + 86399}"
            ).get("data", [])
        except Exception:
            continue
        for e in data:
            ev = e.get("events") or {}
            if ev.get("status") == "notstarted" or not ev.get("id"):
                continue
            tids = {(e.get("homeTeam") or {}).get("id"),
                    (e.get("awayTeam") or {}).get("id")}
            if tids & team_ids:
                ids.append(ev["id"])
            utid = ev.get("uniqueTournamentId") or (e.get("unique_tournaments") or {}).get("id")
            if rozgrywki.czy_druzynowe(utid):
                druzynowe.append(ev)
    return ids, druzynowe


def past_event_ids(team_ids: set[int], days_back: int = 10) -> list[int]:
    """Zgodność wstecz: same id meczów drużyn (patrz past_events)."""
    return past_events(team_ids, days_back)[0]


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
# Raport pokrycia (dry-run etapu 1 + brama jakości etapu 3)
# ---------------------------------------------------------------------------

def _per_rozgrywki(mecze: list[MeczLigowy]) -> dict[str, dict]:
    """Statystyka sparowane/mecze per rozgrywki (wspólna dla raportu
    na żądanie i raportu pokrycia zapisywanego co cykl)."""
    out: dict[str, dict] = {}
    for m in mecze:
        r = out.setdefault(
            m.rozgrywki_nazwa,
            {"kraj": m.kraj, "mecze": 0, "sparowane": 0, "druzynowe": m.druzynowe},
        )
        r["mecze"] += 1
        if m.sb_event is not None:
            r["sparowane"] += 1
    return out


def _luka_propsy(luka: list[dict]) -> list[dict]:
    """Mecze Superbetu bez pary w statshub z bogatą ofertą (heurystyka:
    marketCount>=100 = prawie na pewno propsy) — zmierzona luka pokrycia."""
    bogate = [ev for ev in luka if (ev.get("marketCount") or 0) >= 100]
    bogate.sort(key=lambda e: -(e.get("marketCount") or 0))
    return [
        {
            "mecz": str(ev.get("matchName") or "").replace("·", " - "),
            "rynkow": int(ev.get("marketCount") or 0),
            "kickoff_ts": _sb_kickoff(ev),
        }
        for ev in bogate[:30]
    ]


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

    per_rozgrywki = _per_rozgrywki(mecze)

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


# ---------------------------------------------------------------------------
# Adapter trybu — wstrzykiwany w build_wc_fast._main_impl (szwy `tryb`)
# ---------------------------------------------------------------------------

@dataclass
class TrybLigowy:
    """Wszystko, czym tryb ligowy różni się od MŚ z perspektywy silnika."""

    events: list[dict]                 # surowe eventy statshub (jak z upcoming_wc_events)
    team_name: dict[int, str]          # id -> nazwa (z by-date, pełniejsze niż z trendów)
    sb_events: list[dict]              # pełna oferta Superbetu (do warunku w pętli)
    sb_ev_by_mid: dict[int, dict]      # mecz statshub -> sparowany event Superbetu
    liga_by_mid: dict[int, dict]       # mecz -> {"liga","sezon","kolejka"}
    past_event_ids: list[int]          # rozegrane mecze do banku historii
    koncesje_min_ts: int               # okno obserwacji profili rywali
    rotacja_min_ts: int                # "grał ostatnio" dla triggera rotacji
    publikuj: bool = False             # False = dry-run (zero zapisów Supabase/web)
    liga_glowna: str = "Liga"          # etykieta do meta.json
    sezon: str = "2026/27"
    # zmierzona luka pokrycia z parowania (brama jakości: luka jest LOGOWANA,
    # nie ignorowana) — silnik dopisze swoją część i zrzuci pokrycie_liga.json
    pokrycie: dict = field(default_factory=dict)
    # mecze rozgrywek z zakresu DRUŻYNOWEGO (top 5 + Ekstraklasa + puchary,
    # rozgrywki.druzynowe=True) — tylko dla nich silnik liczy rynki drużynowe
    druzynowe_mids: set[int] = field(default_factory=set)
    # ROZEGRANE eventy zakresu drużynowego (statshub, id+kickoff) —
    # bank stylu ligowego pobiera z nich shotmapy
    past_druzynowe_events: list[dict] = field(default_factory=list)


def zbuduj_tryb(days: int = 5, publikuj: bool = False) -> TrybLigowy | None:
    """Odkryj mecze, sparuj z Superbetem i złóż adapter dla silnika.

    Do silnika idą WYŁĄCZNIE mecze sparowane z Superbetem (bez kursów nie
    powstanie ani typ, ani okazja — szkoda zapytań). Reszta to zmierzona
    luka pokrycia (raport_pokrycia).
    """
    mecze = upcoming_events(days)
    try:
        sb_events = superbet.list_events(days_ahead=days)
    except Exception as e:
        print(f"Superbet niedostępny: {e}")
        return None
    n_par, luka = paruj_superbet(mecze, sb_events)
    pary = [m for m in mecze if m.sb_event is not None]
    print(f"Tryb ligowy: {len(mecze)} meczów statshub, {len(sb_events)} Superbet, "
          f"sparowano {n_par}")
    if not pary:
        return None
    now = int(time.time())
    pokrycie = {
        "mecze_statshub": len(mecze),
        "mecze_superbet": len(sb_events),
        "sparowane": n_par,
        "per_rozgrywki": _per_rozgrywki(mecze),
        "luka_superbet_propsy": _luka_propsy(luka),
    }
    team_ids = {m.home_id for m in pary} | {m.away_id for m in pary}
    past_ids, past_druzynowe = past_events(team_ids)
    return TrybLigowy(
        events=[m.raw for m in pary],
        team_name={
            **{m.home_id: m.home for m in pary},
            **{m.away_id: m.away for m in pary},
        },
        sb_events=sb_events,
        sb_ev_by_mid={m.event_id: m.sb_event for m in pary},
        liga_by_mid={
            m.event_id: {"liga": m.rozgrywki_nazwa, "sezon": "2026/27",
                         "kolejka": m.kolejka}
            for m in pary
        },
        past_event_ids=past_ids,
        koncesje_min_ts=now - 180 * 86400,
        rotacja_min_ts=now - 45 * 86400,
        publikuj=publikuj,
        liga_glowna="Piłka klubowa",
        sezon="2026/27",
        pokrycie=pokrycie,
        druzynowe_mids={m.event_id for m in pary if m.druzynowe},
        past_druzynowe_events=past_druzynowe,
    )


def main(publikuj: bool = False) -> None:
    """Pełny cykl ligowy. Domyślnie DRY-RUN: silnik liczy wszystko,
    ale dumpy idą do web/src/data/.../liga_dryrun, a Supabase/rozliczenia
    są nietknięte (patrz build_wc_fast._dry_run)."""
    from . import build_wc_fast

    tryb = zbuduj_tryb(publikuj=publikuj)
    if tryb is None:
        print("Brak sparowanych meczów — cykl ligowy pominięty.")
        return
    build_wc_fast.main(tryb)


if __name__ == "__main__":
    import sys
    if "--raport" in sys.argv:
        raport_pokrycia()
    else:
        main(publikuj="--publikuj" in sys.argv)
