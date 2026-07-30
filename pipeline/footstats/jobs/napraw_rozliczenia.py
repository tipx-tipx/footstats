"""Naprawa błędnie rozliczonych typów w księdze — jednorazowy przebieg.

PO CO. Rozliczony rekord jest w księdze zamrożony: pętla rozliczania pomija
wszystko, co ma już `wynik`. Gdy źródło w chwili rozliczenia podało złą liczbę,
błąd zostaje na zawsze — i psuje kalibrację, kwarantannę rynków, skuteczność
i ROI, czyli wszystko, co na księdze stoi.

Dwa błędy znalezione 2026-07-30 (zgłoszenia usera) i naprawione w kodzie:
  * pusta mapa strzałów 365 czytana jako „zawodnik oddał 0 strzałów"
    (Marcel Reguła: zapisane 0, naprawdę 6),
  * wynik meczu czytany, gdy mecz jeszcze trwał — bo `fetch_event_result`
    nie sprawdzał statusu (Górnik Zabrze i Remo: zapisane 0 goli, naprawdę 1).
Kod już tak nie zrobi, ale rekordy sprzed poprawki trzeba przeliczyć.

OSTROŻNIE I WĄSKO. Poprawiamy WYŁĄCZNIE przypadki o jednoznacznym podpisie
błędu, nigdy „bo źródło mówi co innego":
  * strzały/celne, gdzie zapisaliśmy 0, a shotmapa statshub ma >0,
  * gole drużyny, gdzie zapisaliśmy 0, a zakończony mecz ma >0.
Rozbieżności w drugą stronę (mieliśmy WIĘCEJ niż shotmapa) zostawiamy —
zmierzone 2026-07-30: to mecze mundialu, gdzie źródła liczą strzały inaczej,
a nie nasza pomyłka.

Użycie:
    python -m footstats.jobs.napraw_rozliczenia          # tylko pokaż
    python -m footstats.jobs.napraw_rozliczenia --zapisz # zapisz do księgi
"""
from __future__ import annotations

import os
import sys
import time

# .env MUSI wejść przed pierwszym dotknięciem `supa` — bez tego job idzie
# w TRYB LOKALNY, w którym `get_key_ok` oddaje „klucz pusty, odczyt się udał",
# czyli księga wygląda na pustą (patrz [[dry-run-lokalny]]).
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except ImportError:
    pass

from .. import supa
from ..sources import scores365
from . import rozliczanie as R


def znajdz_bledy(log: dict) -> list[tuple[dict, float, str]]:
    """Rekordy z jednoznacznym podpisem błędu: (rekord, prawda, nowy_wynik)."""
    cache_w: dict = {}
    cache_sm: dict = {}
    bledy: list[tuple[dict, float, str]] = []
    for rec in log.values():
        if rec.get("wynik") not in ("wygrany", "przegrany"):
            continue
        if rec.get("faktyczna") != 0.0:
            continue        # podpis obu błędów to zapisane ZERO
        mk = rec.get("rynek_kod")
        prawda = None
        if mk in ("shots", "sot"):
            sr = R._statshub_wynik(rec["mecz_id"], cache_w)
            if sr is None or sr["extra_time"]:
                continue    # dogrywki shotmapa nie dzieli — nie ruszamy
            sm = R._statshub_strzaly(rec["mecz_id"], cache_sm)
            if not sm:
                continue
            normed = {scores365._norm(n): v for n, v in sm.items()}
            skey = scores365.resolve_player_key(set(normed), rec["podmiot"])
            if skey is None:
                continue
            prawda = float(normed[skey].get(mk, 0))
        elif mk == "team_goals":
            sr = R._statshub_wynik(rec["mecz_id"], cache_w)
            if sr is None or sr["extra_time"]:
                continue
            pid = rec.get("podmiot_id")
            if pid and pid == sr.get("home_id"):
                prawda = sr["home_goals"]
            elif pid and pid == sr.get("away_id"):
                prawda = sr["away_goals"]
        if prawda is None or prawda <= 0:
            continue        # zero potwierdzone albo brak danych — zostawiamy
        traf = (prawda > rec["linia"] if rec["strona"] == "powyzej"
                else prawda < rec["linia"])
        nowy = "wygrany" if traf else "przegrany"
        if nowy != rec["wynik"] or rec.get("faktyczna") != prawda:
            bledy.append((rec, prawda, nowy))
    return bledy


def do_ponownego_otwarcia(log: dict) -> list[dict]:
    """Typy zamknięte jako „zwrot — brak danych źródła", którym warto dać
    drugą szansę.

    Błąd `after_extra_time` (doliczony czas czytany jako dogrywka) blokował
    rozliczanie rynków drużynowych, a po 48 godzinach bez danych typ zamykał
    się jako zwrot. Po poprawce źródła te dane mają — więc zdejmujemy wynik
    i pozwalamy normalnej pętli rozliczyć je jeszcze raz. Gdy danych naprawdę
    nie ma, typ zamknie się jako zwrot ponownie i nic się nie zmieni.
    """
    return [
        r for r in log.values()
        if r.get("wynik") == "zwrot"
        and r.get("powod") == "brak danych źródła"
    ]


def main(zapisz: bool = False) -> int:
    log_raw, ok = supa.get_key_ok("typy_log")
    if not ok:
        print("Nie udało się odczytać księgi — przerywam (nic nie zapisuję).")
        return 1
    log = R._migruj_log(log_raw or {})
    print(f"Wpisów w księdze: {len(log)}")
    bledy = znajdz_bledy(log)
    print(f"Rekordów z podpisem błędu: {len(bledy)}\n")
    zmiana_j = 0.0
    for rec, prawda, nowy in sorted(
            bledy, key=lambda x: -(x[0].get("kickoff_ts") or 0)):
        d = time.strftime("%d.%m", time.localtime(rec.get("kickoff_ts") or 0))
        kurs = float(rec.get("kurs") or 0)
        if rec["wynik"] == "przegrany" and nowy == "wygrany" and kurs:
            zmiana_j += kurs          # było −1, będzie +(kurs−1)
        elif rec["wynik"] == "wygrany" and nowy == "przegrany" and kurs:
            zmiana_j -= kurs
        print(f"  {d} {str(rec.get('podmiot'))[:22]:<22} "
              f"{str(rec.get('rynek'))[:16]:<16} {rec['strona']} {rec['linia']}"
              f" | {rec['wynik']} (0) -> {nowy} ({prawda:g})")
    print(f"\nRóżnica w bilansie: {zmiana_j:+.1f} jednostek "
          f"({zmiana_j*10:+.0f} zł przy stawce 10 zł)")

    ponownie = do_ponownego_otwarcia(log)
    print(f"\nDo ponownego rozliczenia (brak danych źródła): {len(ponownie)}")
    if ponownie:
        rynki: dict[str, int] = {}
        for r in ponownie:
            rynki[r["rynek_kod"]] = rynki.get(r["rynek_kod"], 0) + 1
        print("   " + ", ".join(f"{k}={v}" for k, v in sorted(
            rynki.items(), key=lambda kv: -kv[1])))

    if not zapisz:
        print("\nTryb podglądu — nic nie zapisano. `--zapisz`, żeby poprawić.")
        return 0
    now = int(time.time())
    for rec, prawda, nowy in bledy:
        rec.update(wynik=nowy, faktyczna=prawda, rozliczono_ts=now,
                   powod="poprawka rozliczenia 2026-07-30")
    for rec in ponownie:
        rec.update(wynik=None, faktyczna=None, rozliczono_ts=None,
                   powod="ponowna próba po poprawce dogrywki 2026-07-30")
    if supa.put_key_bezpiecznie("typy_log", log):
        print(f"\nZapisano: poprawiono {len(bledy)} rekordów, "
              f"otwarto ponownie {len(ponownie)}.")
        return 0
    print("\nZapis ODRZUCONY przez bezpiecznik — księga bez zmian.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main("--zapisz" in sys.argv))
