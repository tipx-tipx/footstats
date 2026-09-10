# -*- coding: utf-8 -*-
"""ZASILENIE MAGAZYNU STANU Z KOPII NA DYSKU (etap 3, 2026-09-10).

Bierze pliki `.json.gz` zrobione przez `ratuj_baze.py --eksport` i wgrywa je
do magazynu (`magazyn_repo`). Po każdym kluczu CZYTA GO Z POWROTEM i porównuje
z tym, co miało pójść — zapis, którego nikt nie sprawdził, nie jest kopią.

Dopiero gdy to przejdzie, wolno dopisać klucz do `supa.MAGAZYN`: od tej chwili
pipeline czyta go stąd, więc magazyn musi już mieć komplet.

    export STAN_REPO=tipx-tipx/footstats-stan
    export STAN_TOKEN=...
    python pipeline/scripts/wsyp_do_magazynu.py <katalog-kopii> [klucz ...]

Bez podanych kluczy bierze te, które są przewidziane do przeprowadzki.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from footstats import magazyn_repo as mr   # noqa: E402

# klucze pipeline'u przewidziane do wyprowadzenia z Supabase — front nie czyta
# żadnego z nich (patrz BUNDLE_KEYS w web/src/lib/data.ts)
DO_PRZEPROWADZKI = (
    "trend_lib",          # 47 MB w 39 częściach — największy pożeracz
    "styl_bank_liga",
    "styl_bank",
    "typy_log_kopia",
    *[f"hd_{i}" for i in range(10)],
    "typy_log",           # NAJGORĘTSZY, więc na końcu
)


def _wczytaj(plik: Path):
    with gzip.open(plik, "rt", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    if len(sys.argv) < 2:
        return int(bool(sys.exit(__doc__)))
    katalog = Path(sys.argv[1])
    if not katalog.is_dir():
        sys.exit(f"Nie ma katalogu {katalog}")
    klucze = sys.argv[2:] or list(DO_PRZEPROWADZKI)

    print(f"Źródło: {katalog}")
    print(f"Magazyn: {mr._konf()[0] if mr._konf() else 'NIESKONFIGUROWANY'}\n")
    if mr._konf() is None:
        sys.exit("Brak STAN_REPO/STAN_TOKEN")

    bledy = 0
    for key in klucze:
        plik = katalog / f"{key}.json.gz"
        if not plik.exists():
            print(f"  {key:<20} pomijam — brak pliku w kopii")
            continue

        dane = _wczytaj(plik)
        ile = len(dane) if isinstance(dane, (dict, list)) else "—"
        if not mr.zapisz(key, dane):
            print(f"  {key:<20} ⚑ ZAPIS PADŁ")
            bledy += 1
            continue

        # kontrola: czytamy z magazynu i porównujemy z tym, co wysłaliśmy
        mr.wyczysc_pamiec()
        wrocilo, ok = mr.pobierz(key)
        if not ok or wrocilo != dane:
            print(f"  {key:<20} ⚑ KONTROLA NIE PRZESZŁA "
                  f"(odczyt_ok={ok}, zgodne={wrocilo == dane})")
            bledy += 1
            continue
        print(f"  {key:<20} OK — {ile} wpisów, odczytane i zgodne")

    print()
    if bledy:
        print(f"⚑⚑ {bledy} kluczy NIE przeszło. NIE dopisywać ich do MAGAZYN.")
        return 1
    print("Wszystkie klucze w magazynie i potwierdzone odczytem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
