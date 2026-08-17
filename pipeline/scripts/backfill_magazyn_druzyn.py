# -*- coding: utf-8 -*-
"""JEDNORAZOWE NAPEŁNIENIE MAGAZYNU HISTORII DRUŻYN.

    cd pipeline
    PYTHONUTF8=1 python scripts/backfill_magazyn_druzyn.py            # próbnie, 10 drużyn
    PYTHONUTF8=1 python scripts/backfill_magazyn_druzyn.py --wszystkie

Po co: patrz nota na górze `footstats/jobs/magazyn_druzyn.py`. Skrót — rynki
drużynowe to 93% produkcji, a ich historia meczowa nigdy nie była zapisywana,
więc model nie miał na czym się uczyć i uczyły się wyłącznie warstwy korekt
na jego wyjściu.

Drużyny bierzemy z `druzyny_profil` (289 sztuk — dokładnie te, o których
produkt cokolwiek wie). Jedno zapytanie na drużynę, 40 meczów każde.

⚑ ZAPISUJEMY PARTIAMI, nie na końcu. Przy 289 zapytaniach przerwanie w połowie
jest normalne (limit źródła, timeout), a robota nie może wtedy przepadać.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARTIA = 25          # co ile drużyn zapisujemy stan
PROBNIE = 10         # ile drużyn bez `--wszystkie`


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    from footstats import supa
    from footstats.jobs import magazyn_druzyn as M

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — magazyn siedzi w chmurze.")
        return

    wszystkie = "--wszystkie" in sys.argv
    prof = (supa.get_key("druzyny_profil") or {}).get("druzyny") or {}
    ids = [int(t) for t in prof]
    if not ids:
        print("`druzyny_profil` puste — nie wiem, o które drużyny pytać.")
        return
    if not wszystkie:
        ids = ids[:PROBNIE]
        print(f"PRÓBNIE: {len(ids)} drużyn (pełne pobranie: --wszystkie)")

    mag = M.wczytaj()
    if M.braki(mag):
        print(f"⚑ nie odczytano szardów {M.braki(mag)} — przerywam, żeby nie "
              "nadpisać istniejącej historii pustką")
        return
    st0 = M.statystyki(mag)
    print(M.zdanie_stanu(st0))

    nowe_razem = 0
    zmienione: set[int] = set()
    t0 = time.time()
    for i, tid in enumerate(ids, 1):
        try:
            n = M.pobierz_i_dopisz(mag, tid)
        except Exception as e:  # noqa: BLE001
            print(f"   {i:>3}/{len(ids)}  team {tid}: BŁĄD {type(e).__name__}: {e}")
            continue
        nowe_razem += n
        if n:
            zmienione.add(M.szard(tid))
        if i % 10 == 0 or i == len(ids):
            print(f"   {i:>3}/{len(ids)}  nowych meczów razem: {nowe_razem}"
                  f"   ({time.time() - t0:.0f} s)")
        if i % PARTIA == 0 and zmienione:
            ok_n, zle_n = M.zapisz(mag, zmienione)
            print(f"      zapis partii: {ok_n} szardów ok, {zle_n} nieudanych")
            if zle_n:
                print("      ⚑ zapis się nie udał — przerywam, dane w chmurze "
                      "zostają nietknięte")
                return
            zmienione.clear()

    if zmienione:
        ok_n, zle_n = M.zapisz(mag, zmienione)
        print(f"   zapis końcowy: {ok_n} szardów ok, {zle_n} nieudanych")

    st = M.statystyki(mag)
    print("\n" + M.zdanie_stanu(st))
    print(f"   nowych meczów w tym przebiegu: {nowe_razem}")
    if st.get("meczow"):
        import datetime as _d
        print("   zakres historii: "
              f"{_d.datetime.fromtimestamp(st['od']):%Y-%m-%d} – "
              f"{_d.datetime.fromtimestamp(st['do']):%Y-%m-%d}")
        print("   pokrycie pól (ile meczów ma daną statystykę):")
        for kod, n in sorted(st["pola"].items(), key=lambda kv: -kv[1]):
            print(f"      {kod:<6}{n:>7}  ({n / st['meczow']:.0%})")


if __name__ == "__main__":
    main()
