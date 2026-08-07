# -*- coding: utf-8 -*-
"""JEDNORAZOWE zbudowanie profilu drużyn — ile notują, ile dopuszczają.

Po co: czynnik rywala brał kontekst z feedu propsów, czyli z lustra oferty
bukmacherów UK. Dla Ekstraklasy, kwalifikacji pucharów i części Ameryki
Południowej tego lustra nie ma wcale, więc czynnik wychodził 1,00 — zmierzone
2026-08-07: komplet czynników miało 18 ze 134 kandydatów. Historia drużyny
(`/team/{id}/performance`) działa w KAŻDEJ lidze i niesie statystyki obu stron.

Cykl odświeża profil sam, ale najwyżej raz na dobę i w ramach budżetu zapytań,
więc od zera dochodziłby do kompletu kilka dni. Ten skrypt robi to za jednym
razem — i od tej pory cykl tylko dopisuje zmiany.

    cd pipeline
    PYTHONUTF8=1 python scripts/backfill_profilu.py            # na sucho
    PYTHONUTF8=1 python scripts/backfill_profilu.py --zapisz   # z zapisem

Domyślnie CZYTA I POKAZUJE, nie zapisuje. Zapis dopiero z `--zapisz`.
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ile meczów historii pobieramy na drużynę. Feed oddaje do 182 (limit=200),
# ale profil waży świeżością z półokresem 45 dni, więc mecze sprzed roku i tak
# nie ruszają liczby — 60 to kompromis między próbą a czasem przebiegu.
LIMIT_MECZOW = 60
# przerwa między zapytaniami: nie zalewamy źródła, z którego korzystamy za darmo
PRZERWA_S = 0.15


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — ten skrypt pracuje na żywej bazie.")
        return 1

    from footstats import supa
    from footstats.model import profil_druzyn
    from footstats.sources import statshub
    from footstats.jobs import build_wc_fast as B

    zapisz = "--zapisz" in sys.argv
    teraz = int(time.time())

    # --- kogo w ogóle profilujemy ---
    ids: dict[int, str] = {}
    for m in supa.get_key("matches") or []:
        for strona in ("gospodarz", "gosc"):
            nazwa = m.get(strona)
            if nazwa:
                ids.setdefault(0, "")      # terminarz nie niesie id drużyn
    log = supa.get_key("typy_log") or {}
    for r in log.values():
        tid = r.get("podmiot_id")
        if tid and str(r.get("rynek_kod") or "").startswith(
                ("team_", "match_", "wiecej_")):
            ids[abs(int(tid))] = str(r.get("podmiot") or "")
    ids.pop(0, None)
    print(f"Drużyn do sprofilowania: {len(ids)}")

    magazyn, odczyt_ok = supa.get_key_ok(B.PROFIL_DRUZYN_KLUCZ)
    if not odczyt_ok:
        print("Odczyt profilu PADŁ — przerywam, żeby nie nadpisać pamięci.")
        return 1
    magazyn = magazyn or {}
    zastano = len(magazyn.get("druzyny") or {})
    print(f"W pamięci zastano: {zastano} drużyn\n")

    licz = Counter()
    for i, (tid, nazwa) in enumerate(sorted(ids.items()), 1):
        stary = profil_druzyn.pobierz(magazyn, tid)
        if stary and not profil_druzyn.wymaga_odswiezenia(stary, teraz):
            licz["swieze_pominiete"] += 1
            continue
        try:
            rek = statshub.fetch_team_performance(tid, limit=LIMIT_MECZOW)
        except Exception as e:
            licz["blad_pobrania"] += 1
            print(f"  [{i}/{len(ids)}] {nazwa or tid}: błąd ({e})")
            continue
        time.sleep(PRZERWA_S)
        if not rek:
            licz["pusta_historia"] += 1
            continue
        profil = profil_druzyn.zbuduj(
            tid, rek, teraz, statshub.TEAM_PERF_MAP
        )
        if not profil:
            licz["za_chuda_historia"] += 1
            continue
        magazyn = profil_druzyn.scal(magazyn, tid, profil)
        licz["zbudowane"] += 1
        if licz["zbudowane"] % 25 == 0:
            print(f"  [{i}/{len(ids)}] zbudowano {licz['zbudowane']}...")

    magazyn, zeszlo = profil_druzyn.przytnij(magazyn, teraz)
    if zeszlo:
        licz["zeszlo_z_pamieci"] = zeszlo

    print("\nWYNIK:")
    for k, v in licz.most_common():
        print(f"  {k}: {v}")
    ile = len(magazyn.get("druzyny") or {})
    print(f"  w pamięci po przebiegu: {ile} (było {zastano})")
    waga = supa.waga(magazyn)
    print(f"  rozmiar: {waga / 1024:.0f} kB")

    # --- podgląd, żeby dało się ocenić sensowność liczb przed zapisem ---
    print("\nPRZYKŁADY (ile notuje / ile dopuszcza):")
    for tid, p in list((magazyn.get("druzyny") or {}).items())[:5]:
        rynki = p.get("rynki") or {}
        opis = ", ".join(
            f"{mk.replace('team_', '')} {w.get('notuje')}/{w.get('dopuszcza')}"
            for mk, w in list(rynki.items())[:4]
        )
        print(f"  {ids.get(int(tid), tid)}: {opis}  (n={p.get('n')})")

    if not zapisz:
        print("\nTo był przebieg NA SUCHO. Zapis: --zapisz")
        return 0
    if not supa.put_key(B.PROFIL_DRUZYN_KLUCZ, magazyn):
        print("\nZAPIS NIE POWIÓDŁ SIĘ.")
        return 1
    print("\nZapisano.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
