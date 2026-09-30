# -*- coding: utf-8 -*-
"""WYNIK DO NAUKI — jednorazowe uzupełnienie `wynik_nauka` (2026-09-30).

PO CO. Rozliczony rekord jest zamrożony na zawsze (Skuteczność pokazuje to,
co zapadło — zasada właściciela). Warstwy korekt uczą się jednak z tej samej
księgi (`rozliczanie.widok_nauki`), a do 30.09 rozliczanie miało dwa błędy:

  * typ Superbetu na zawodnika spoza pierwszego składu liczony jak zwykły
    (Superbet go zwraca) — 1206 rekordów, prawie zawsze „przegrany",
  * „nie zagrał"/„brak danych" przy zawodniku, który grał (365 nie rozpoznało
    nazwiska) — ~550 rekordów.

Pole `wynik_nauka` niesie poprawne rozstrzygnięcie WYŁĄCZNIE dla warstw
uczenia; `wynik` zostaje nietknięty.

WĄSKO — tylko przypadki udowodnione historią statshub PO NUMERZE zawodnika:
  * Superbet + zawodnik wszedł z ławki (`substitutedOut`) → „zwrot",
  * zapisany „zwrot", a statshub ma mecz z minutami → wynik z wartości statshub.
Nie ruszamy: różnic wartości 365 vs statshub (nie wiadomo, kto ma rację —
1,9% linii, w obie strony), meczów bez wiersza w historii (puchary, których
statshub nie ma — Recoleta–Boca), zera minut przy rozliczonym typie,
superzmiany i meczów przełożonych.

    PYTHONUTF8=1 python -m footstats.jobs.wyniki_nauki                # podgląd
    PYTHONUTF8=1 python -m footstats.jobs.wyniki_nauki --zapisz       # zapis
    ... --cache <katalog>   # historie {pid}.json pobrane wcześniej (limit 429)
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
except ImportError:
    pass

from .. import supa
from ..sources import statshub
from . import rozliczanie as R

POLA = R.POLA_PERF_ROZLICZENIA          # shots, sot, fouls_committed, fouls_won
POWODY_ZWROTU_DO_SPRAWDZENIA = ("nie zagrał", R.POWOD_BRAK_DANYCH)


def wynik_nauki(rec: dict, wiersze: list[dict]) -> tuple[str, float | None] | None:
    """(wynik, faktyczna) do nauki albo None, gdy rekordu nie ruszamy."""
    mk = rec.get("rynek_kod")
    if mk not in POLA or rec.get("superzmiana"):
        return None
    if rec.get("wynik") not in ("wygrany", "przegrany", "zwrot"):
        return None
    if rec.get("wynik") == "zwrot" and rec.get("powod") not in POWODY_ZWROTU_DO_SPRAWDZENIA:
        return None                     # przełożony/odwołany — zwrot słuszny
    ps = None
    for w in wiersze or []:
        ev = statshub._pierwszy(w.get("events"))
        p = statshub._pierwszy(w.get("player_statistics_event"))
        if int(ev.get("id") or p.get("eventId") or 0) == int(rec["mecz_id"]):
            ps = p
            break
    if ps is None or not (ps.get("minutesPlayed") or 0):
        return None                     # brak wiersza / zero minut — nie rozstrzygamy
    superbet = "superbet" in str(rec.get("bukmacher") or "").lower()
    if superbet and ps.get("substitutedOut") is not None:
        return ("zwrot", None) if rec["wynik"] != "zwrot" else None
    if rec["wynik"] != "zwrot":
        return None                     # rozliczony z danymi — nie przepisujemy
    v = ps.get(POLA[mk])
    if v is None:
        return None
    v = float(v)
    traf = v > rec["linia"] if rec["strona"] == "powyzej" else v < rec["linia"]
    return ("wygrany" if traf else "przegrany"), v


def _historia(pid: int, cache_dir: str | None, pamiec: dict) -> list[dict] | None:
    if pid in pamiec:
        return pamiec[pid]
    if cache_dir:
        p = os.path.join(cache_dir, f"{pid}.json")
        if os.path.exists(p):
            pamiec[pid] = json.load(open(p, encoding="utf-8"))
            return pamiec[pid]
    for proba in range(4):
        try:
            pamiec[pid] = statshub.fetch_player_performance(pid, limit=40)
            time.sleep(0.3)
            return pamiec[pid]
        except Exception as e:                               # noqa: BLE001
            time.sleep(15 * (proba + 1) if "429" in str(e) else 2)
    pamiec[pid] = None
    return None


def main(zapisz: bool = False, cache_dir: str | None = None) -> int:
    log, ok = supa.get_key_ok("typy_log")
    if not ok or not log:
        print("Nie udało się odczytać księgi — nic nie robię.")
        return 1
    n0 = len(log)
    kandydaci = [
        (k, r) for k, r in log.items()
        if r.get("rynek_kod") in POLA and not r.get("wynik_nauka")
        and r.get("wynik") in ("wygrany", "przegrany", "zwrot")
        and 0 < int(r.get("podmiot_id") or 0) < R.PID_SYNTETYCZNY
        and str(r.get("podmiot_typ", "zawodnik")) == "zawodnik"
    ]
    print(f"Księga: {n0} rekordów, kandydatów: {len(kandydaci)}")
    pamiec: dict = {}
    zmiany: Counter = Counter()
    # KROK 1 — liczymy poprawki na odczycie (trwa minuty: historie statshub).
    # Księgi w tym czasie NIE trzymamy do zapisu: cykl mógł ją zmienić.
    poprawki: dict[str, tuple] = {}
    for i, (k, r) in enumerate(kandydaci):
        h = _historia(int(r["podmiot_id"]), cache_dir, pamiec)
        if h is None:
            zmiany["bez_historii"] += 1
            continue
        w = wynik_nauki(r, h)
        if w is None:
            continue
        poprawki[k] = (r["wynik"], w[0], w[1])
        zmiany[(r["wynik"], w[0])] += 1
        if i % 2000 == 0:
            print(f"  {i}/{len(kandydaci)}", flush=True)
    for k, v in sorted(zmiany.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v}")
    if not zapisz:
        print("Podgląd — nic nie zapisano (`--zapisz`, żeby zapisać).")
        return 0
    # KROK 2 — świeży odczyt tuż przed zapisem; poprawkę nanosimy tylko tam,
    # gdzie rekord ma NADAL ten sam wynik (sekundy między odczytem a zapisem)
    swieza, ok2 = supa.get_key_ok("typy_log")
    if not ok2 or not swieza or len(swieza) < n0:
        print("Świeży odczyt księgi nieudany albo krótszy — przerywam.")
        return 1
    teraz = int(time.time())
    naniesione = 0
    for k, (stary, nowy, fakt) in poprawki.items():
        r = swieza.get(k)
        if not r or r.get("wynik") != stary or r.get("wynik_nauka"):
            continue
        r["wynik_nauka"] = nowy
        if fakt is not None:
            r["faktyczna_nauka"] = fakt
        r["wynik_nauka_ts"] = teraz
        naniesione += 1
    if supa.put_key_bezpiecznie("typy_log", swieza):
        print(f"Zapisano wynik_nauka: {naniesione} rekordów "
              f"(z {len(poprawki)} policzonych).")
        return 0
    print("Zapis ODRZUCONY przez bezpiecznik — księga bez zmian.")
    return 1

if __name__ == "__main__":
    _c = sys.argv[sys.argv.index("--cache") + 1] if "--cache" in sys.argv else None
    raise SystemExit(main("--zapisz" in sys.argv, _c))
