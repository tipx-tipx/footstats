# -*- coding: utf-8 -*-
"""MAGAZYN SUROWEJ HISTORII MECZOWEJ DRUŻYN — pamięć, na której model może się uczyć.

⚑ PO CO TO ISTNIEJE (zmierzone 2026-08-17, zadanie właściciela „nie wiem, czy
model się uczy").

Rynki drużynowe to 93% produkcji (rożne 1781 rozliczeń, gole 1527, kartki 447)
i do dziś ich historia meczowa NIE BYŁA NIGDZIE ZAPISYWANA. Cykl pobierał ją
z `statshub.fetch_team_performance`, silnik jej używał i wyrzucał. W bazie
zostawały wyłącznie AGREGATY (`druzyny_profil`: „notuje 6,8 / dopuszcza 2,4"
na 40 meczach) — a ze średniej nie da się nauczyć modelu, bo średnia nie wie,
przeciw komu, u siebie czy na wyjeździe i kiedy.

Skutek był taki, że jedyne, co się w produkcie uczyło, to DZIESIĘĆ WARSTW
KOREKT NA WYJŚCIU formuły. Sam rachunek (λ ze średnich × pięć ręcznie
wpisanych mnożników) nie ma ani jednego parametru z danych. Stąd pętla, w
której każda korekta poprawia jedno i psuje drugie: delta na `p_over` jest
transferem między stronami ([[korekta-strony-zakladu]]).

Porównanie, które to tłumaczy: bank zawodniczy (`trend_lib`) ma 176 718
obserwacji i strumień zawodniczy SIĘ POPRAWIA, drużynowy nie ma nic i SIĘ
PSUJE — mimo że to on niesie prawie całą produkcję.

## CO ZAPISUJEMY

Jeden rekord = jeden mecz jednej drużyny. Oprócz celów (rożne, strzały, celne,
kartki, faule, gole) idą też pola, które mogą być CECHAMI modelu, i te same
liczby po stronie RYWALA — czyli koncesje zmierzone, nie przybliżane.
Statshub oddaje 45 pól własnych i 44 rywala; bierzemy 15+15, bo reszta
(dokładność podań, wyrzuty z autu) nie ma związku z żadnym naszym rynkiem.
Zasada: lepiej zapisać pole, którego jeszcze nie używamy, niż odkryć po
miesiącu, że nie ma z czego policzyć cechy ([[statshub-49-pol-uzywamy-5]]).

## DLACZEGO SZARDY

Magazyn to ~11 500 meczów × ~37 liczb ≈ 3,5 MB w jednym JSON-ie. Postgres
przerywał już własny upsert przy 4,9 MB w żądaniu
([[cykl-pada-losowo-co-kilkanascie]]), więc dzielimy po ostatniej cyfrze
`team_id` na 10 kluczy po ~350 KB i zapisujemy TYLKO te, które się zmieniły.

CZYTA I ZAPISUJE, ale nie liczy prognoz — to jest magazyn, nie model.
"""

from __future__ import annotations

from typing import Iterable

from footstats import supa
from footstats.sources import statshub

# ---------------------------------------------------------------- klucze -----
KLUCZ_WZOR = "hd_{}"      # hd_0 .. hd_9, szard = team_id % SZARDOW
SZARDOW = 10
# Ile meczów historii trzymamy na drużynę. Statshub oddaje 40 i tyle wystarcza:
# przy 289 drużynach to 11 560 obserwacji, a mecze starsze niż rok opisują
# inny skład i innego trenera.
OKNO_MECZOW = 60

# POLA, KTÓRE ZAPISUJEMY — krótkie kody, bo nazwa pola powtarza się 11 tysięcy
# razy i w JSON-ie waży tyle samo co dane. Klucz = nazwa u źródła.
POLA = {
    # cele naszych rynków
    "cornerKicks": "cor",
    "totalShotsOnGoal": "sh",        # wszystkie strzały (nazwa u źródła myli)
    "shotsOnGoal": "sot",            # celne
    "cards": "crd",
    "fouls": "fol",
    # kandydaci na cechy — związane z powyższymi mechanicznie, nie „na wszelki
    # wypadek": dośrodkowania i wejścia w tercję rodzą rożne, posiadanie rodzi
    # jedno i drugie, spalone i odbiory opisują wysokość obrony rywala
    "ballPossession": "pos",
    "accurateCross": "crs",
    "finalThirdEntries": "f3",
    "touchesInOppBox": "box",
    "totalShotsInsideBox": "ins",
    "totalShotsOutsideBox": "out",
    "offsides": "off",
    "totalTackle": "tck",
    "interceptionWon": "int",
    "expectedGoals": "xg",
}

# Rynki, dla których magazyn ma bezpośredni cel (do walidacji pokrycia).
RYNKI_CELE = ("team_corners", "team_shots", "team_sot", "team_cards",
              "team_fouls", "team_goals")


def szard(team_id: int | str) -> int:
    return abs(int(team_id)) % SZARDOW


def klucz_szardu(nr: int) -> str:
    return KLUCZ_WZOR.format(int(nr))


# ------------------------------------------------------------- odczyt/zapis --
def wczytaj(szardy: Iterable[int] | None = None) -> dict[str, dict]:
    """Magazyn jako {team_id (str): {"m": [rekordy meczów]}}.

    ⚑ Nieudany odczyt szardu POMIJAMY, ale nie udajemy, że jest pusty —
    zwracamy to, co się udało, i mówimy o brakach przez `braki`. Ta sama
    zasada co przy księdze: pusta odpowiedź z awarii wygląda jak pusty magazyn
    i skończyłaby się nadpisaniem historii ([[supabase-read-modify-write]]).
    """
    out: dict[str, dict] = {}
    for nr in (range(SZARDOW) if szardy is None else szardy):
        dane, ok = supa.get_key_ok(klucz_szardu(nr))
        if not ok:
            out.setdefault("_braki", {}).setdefault("szardy", []).append(nr)
            continue
        for tid, rec in (dane or {}).items():
            out[str(tid)] = rec
    return out


def braki(mag: dict) -> list[int]:
    """Szardy, których nie udało się odczytać (pusty = wszystko na miejscu)."""
    return list((mag.get("_braki") or {}).get("szardy") or [])


def zapisz(mag: dict, tylko: Iterable[int] | None = None) -> tuple[int, int]:
    """Zapisz magazyn szardami. Zwraca (zapisane, nieudane).

    `tylko` ogranicza zapis do wskazanych szardów — po dopisaniu kilku drużyn
    nie ma powodu przepisywać całości (to 3,5 MB na próżno).
    """
    do_zapisu = set(range(SZARDOW)) if tylko is None else {int(t) for t in tylko}
    ok_n = zle_n = 0
    for nr in sorted(do_zapisu):
        czesc = {
            tid: rec for tid, rec in mag.items()
            if tid != "_braki" and szard(tid) == nr
        }
        if supa.put_key_bezpiecznie(klucz_szardu(nr), czesc):
            ok_n += 1
        else:
            zle_n += 1
    return ok_n, zle_n


# ----------------------------------------------------------- budowa rekordu --
def _liczba(v):
    """Wartość pola jako liczba albo None (żeby brak nie udawał zera)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else round(f, 3)


def rekord_meczu(team_id: int, row: dict) -> dict | None:
    """Jeden mecz jednej drużyny w formacie magazynu (None = rekord bez sensu).

    `s` to nasze liczby, `sp` — te same po stronie rywala (koncesje).
    """
    ev = row.get("event") or {}
    try:
        ts = int(ev.get("timeStartTimestamp") or 0)
    except (TypeError, ValueError):
        ts = 0
    if not ts:
        return None
    home = row.get("homeTeam") or {}
    away = row.get("awayTeam") or {}
    try:
        u_siebie = int(home.get("id") or 0) == int(team_id)
    except (TypeError, ValueError):
        return None
    rywal = (away if u_siebie else home) or {}
    wynik = (ev.get("score") or {})
    gole_my = _liczba(wynik.get("home" if u_siebie else "away"))
    gole_ich = _liczba(wynik.get("away" if u_siebie else "home"))
    st = row.get("statistics") or {}
    stp = row.get("opponentStatistics") or {}
    rec = {
        "t": ts,
        "e": _liczba(ev.get("id")),
        "o": _liczba(rywal.get("id")),
        "h": 1 if u_siebie else 0,
        "l": _liczba((row.get("league") or {}).get("id")),
        "s": {kod: v for pole, kod in POLA.items()
              if (v := _liczba(st.get(pole))) is not None},
        "sp": {kod: v for pole, kod in POLA.items()
               if (v := _liczba(stp.get(pole))) is not None},
    }
    if gole_my is not None:
        rec["g"] = gole_my
    if gole_ich is not None:
        rec["gp"] = gole_ich
    return rec


def dopisz(mag: dict, team_id: int, rows: list[dict]) -> int:
    """Dopisz mecze drużyny do magazynu. Zwraca liczbę NOWYCH meczów.

    ⚑ NIE NADPISUJEMY istniejących meczów. Statystyki meczu rozegranego się
    nie zmieniają, a gdyby źródło raz oddało je niepełne, przepisanie
    zamieniłoby dobry rekord na gorszy. Klucz meczu to `event_id`, a gdy go
    brak — znacznik czasu.
    """
    if not rows:
        return 0
    tid = str(int(team_id))
    rec = mag.setdefault(tid, {})
    mecze = rec.setdefault("m", [])
    znane = {(m.get("e") or m.get("t")) for m in mecze}
    nowe = 0
    for row in rows:
        m = rekord_meczu(team_id, row)
        if m is None:
            continue
        k = m.get("e") or m.get("t")
        if k in znane:
            continue
        mecze.append(m)
        znane.add(k)
        nowe += 1
    if nowe:
        mecze.sort(key=lambda m: m.get("t") or 0)
        rec["m"] = mecze[-OKNO_MECZOW:]
    return nowe


def pobierz_i_dopisz(mag: dict, team_id: int) -> int:
    """Jedno zapytanie do statshuba + dopisanie. Zwraca liczbę nowych meczów."""
    return dopisz(mag, team_id, statshub.fetch_team_performance(team_id))


# ------------------------------------------------------------------ pomiary --
def statystyki(mag: dict) -> dict:
    """Ile obserwacji magazyn realnie niesie — do logu cyklu i audytu."""
    druzyny = [r for tid, r in mag.items() if tid != "_braki"]
    mecze = [m for r in druzyny for m in (r.get("m") or [])]
    pola = {}
    for m in mecze:
        for kod in (m.get("s") or {}):
            pola[kod] = pola.get(kod, 0) + 1
    return {
        "druzyn": len(druzyny),
        "meczow": len(mecze),
        "obserwacji": sum(pola.values()),
        "pola": pola,
        "gole": sum(1 for m in mecze if m.get("g") is not None),
        "od": min((m.get("t") or 0) for m in mecze) if mecze else 0,
        "do": max((m.get("t") or 0) for m in mecze) if mecze else 0,
    }


def zdanie_stanu(st: dict) -> str:
    """Jedna linia do logu cyklu — magazyn bez licznika jest nieodróżnialny
    od pustego ([[ciche-odrzucenia-zasada]])."""
    if not st.get("meczow"):
        return ("Magazyn drużyn: PUSTY — model drużynowy nie ma na czym się "
                "uczyć (patrz scripts/backfill_magazyn_druzyn.py)")
    return (f"Magazyn drużyn: {st['druzyn']} drużyn, {st['meczow']} meczów, "
            f"{st['obserwacji']} obserwacji statystyk "
            f"(gole przy {st['gole']} meczach)")
