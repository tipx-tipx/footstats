# -*- coding: utf-8 -*-
"""CZY PRZEŁĄCZAĆ NA MODEL UCZONY — jedno uruchomienie, jedna odpowiedź.

    cd pipeline
    PYTHONUTF8=1 python scripts/porownaj_rachunki.py

Czyta księgę i bierze WYŁĄCZNIE rozliczenia, które mają OBA rachunki: stary
`p_model` (to, co poszło na stronę) i stempel `p_uczony` (model uczony liczony
obok, od 17.08). Porównanie jest więc PAROWANE — te same typy, te same mecze,
ta sama prawda. Backtest tego nie zastąpi: tam model widział historię, tu
widział ją w chwili publikacji.

Co decyduje, sformułowane z góry, żeby nie dobierać kryterium po wyniku:

  1. Brier NIŻSZY u modelu na ≥ 100 sparowanych rozliczeniach,
  2. przewaga stabilna: ten sam znak w obu połowach próby (po czasie),
  3. luka deklaracji bliżej zera, bo to ona psuła selekcję,
  4. żaden strumień nie wychodzi WYRAŹNIE gorzej (drabinki i zawodnicy mają
     mniejsze próby, więc patrzymy na kierunek, nie na trzecie miejsce po
     przecinku).

Skrypt CZYTA TYLKO. Decyzja o przełączeniu należy do właściciela.
"""
from __future__ import annotations

import math
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROG_PROBY = 100


def _brier(pary: list[tuple[float, float]]) -> float:
    return sum((p - y) ** 2 for p, y in pary) / max(len(pary), 1)


def _logloss(pary: list[tuple[float, float]]) -> float:
    out = 0.0
    for p, y in pary:
        p = min(max(p, 1e-6), 1 - 1e-6)
        out -= y * math.log(p) + (1 - y) * math.log(1 - p)
    return out / max(len(pary), 1)


def _wiersz(nazwa: str, dane: list[dict]) -> None:
    n = len(dane)
    if not n:
        print(f"   {nazwa:<26}—")
        return
    y = [d["y"] for d in dane]
    st = [(d["stary"], d["y"]) for d in dane]
    no = [(d["nowy"], d["y"]) for d in dane]
    traf = sum(y) / n
    dekl_st = sum(d["stary"] for d in dane) / n
    dekl_no = sum(d["nowy"] for d in dane) / n
    print(f"   {nazwa:<26}{n:>6}"
          f"{dekl_st:>11.1%}{(traf - dekl_st) * 100:>+8.1f}{_brier(st):>9.4f}"
          f"{dekl_no:>11.1%}{(traf - dekl_no) * 100:>+8.1f}{_brier(no):>9.4f}"
          f"{(_brier(no) - _brier(st)):>+9.4f}")


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    from footstats import supa
    from footstats.jobs import rozliczanie as R

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — księga siedzi w chmurze.")
        return
    surowy, ok = supa.get_key_ok("typy_log")
    if not ok:
        print("NIE UDAŁO SIĘ ODCZYTAĆ KSIĘGI — nie interpretuj zer.")
        return
    log = R._migruj_log(surowy or {})

    dane = []
    for r in log.values():
        if r.get("wynik") not in ("wygrany", "przegrany"):
            continue
        pu = r.get("p_uczony")
        if not isinstance(pu, dict) or pu.get("p") is None or not r.get("p_model"):
            continue
        dane.append({
            "y": 1.0 if r["wynik"] == "wygrany" else 0.0,
            "stary": float(r["p_model"]),
            "nowy": float(pu["p"]),
            "rynek": str(r.get("rynek_kod") or "?"),
            "strumien": R._strumien(r),
            "kurs": float(r.get("kurs") or 0) or None,
            "ts": float(r.get("kickoff_ts") or 0),
            "odl": pu.get("odl"),
        })

    print(f"księga: {len(log)} wpisów")
    print(f"rozliczeń z OBOMA rachunkami: {len(dane)}   (próg oceny: {PROG_PROBY})\n")
    if not dane:
        print("Jeszcze żadne rozliczenie nie ma stempla `p_uczony`.\n"
              "To normalne przez pierwszą dobę po wdrożeniu (17.08): stempel\n"
              "dostają typy powstające OD TERAZ, a rozliczają się po meczu.")
        return

    NAGL = (f"   {'wycinek':<26}{'n':>6}"
            f"{'STARY dekl.':>11}{'luka':>8}{'Brier':>9}"
            f"{'NOWY dekl.':>11}{'luka':>8}{'Brier':>9}{'Δ Brier':>9}")
    print("=" * 106)
    print("PORÓWNANIE PAROWANE (te same typy, oba rachunki)")
    print("=" * 106)
    print(NAGL)
    _wiersz("RAZEM", dane)

    print("\n   per strumień:")
    for s in sorted({d["strumien"] for d in dane}):
        _wiersz(s, [d for d in dane if d["strumien"] == s])

    print("\n   per rynek (od największej próby):")
    grupy = defaultdict(list)
    for d in dane:
        grupy[d["rynek"]].append(d)
    for rynek, grp in sorted(grupy.items(), key=lambda kv: -len(kv[1]))[:12]:
        _wiersz(rynek, grp)

    # --- stabilność: obie połowy próby po czasie ---
    print("\n   stabilność (połowy próby po czasie meczu):")
    po_czasie = sorted(dane, key=lambda d: d["ts"])
    pol = len(po_czasie) // 2
    _wiersz("pierwsza połowa", po_czasie[:pol])
    _wiersz("druga połowa", po_czasie[pol:])

    # --- werdykt ---
    st = [(d["stary"], d["y"]) for d in dane]
    no = [(d["nowy"], d["y"]) for d in dane]
    d_brier = _brier(no) - _brier(st)
    d_ll = _logloss(no) - _logloss(st)
    traf = sum(d["y"] for d in dane) / len(dane)
    luka_st = traf - sum(d["stary"] for d in dane) / len(dane)
    luka_no = traf - sum(d["nowy"] for d in dane) / len(dane)
    p1, p2 = po_czasie[:pol], po_czasie[pol:]

    def _d(grp):
        if not grp:
            return 0.0
        return (_brier([(g["nowy"], g["y"]) for g in grp])
                - _brier([(g["stary"], g["y"]) for g in grp]))

    zgodne = (_d(p1) < 0) == (_d(p2) < 0)

    print("\n" + "=" * 106)
    print("WERDYKT")
    print("=" * 106)
    print(f"   1. próba:            {len(dane)} / {PROG_PROBY}"
          f"   {'OK' if len(dane) >= PROG_PROBY else 'ZA MAŁA'}")
    print(f"   2. Brier:            {d_brier:+.4f}"
          f"   {'model LEPSZY' if d_brier < 0 else 'model gorszy'}"
          f"   (log-loss {d_ll:+.4f})")
    print(f"   3. stabilność:       połowy {_d(p1):+.4f} / {_d(p2):+.4f}"
          f"   {'ten sam znak' if zgodne else 'ZNAK SIĘ ODWRACA'}")
    print(f"   4. luka deklaracji:  {luka_st * 100:+.1f} pp → {luka_no * 100:+.1f} pp"
          f"   {'bliżej zera' if abs(luka_no) < abs(luka_st) else 'DALEJ od zera'}")
    gorsze = [s for s in sorted({d["strumien"] for d in dane})
              if _d([d for d in dane if d["strumien"] == s]) > 0.005]
    print(f"   5. strumienie wyraźnie gorsze: "
          f"{', '.join(gorsze) if gorsze else 'żaden'}")

    warunki = (len(dane) >= PROG_PROBY, d_brier < 0, zgodne,
               abs(luka_no) < abs(luka_st), not gorsze)
    if all(warunki):
        print("\n   ⚑ WSZYSTKIE PIĘĆ WARUNKÓW SPEŁNIONE — materiał na decyzję "
              "o przełączeniu strony na model uczony.")
    else:
        print("\n   ⚑ NIE WSZYSTKIE WARUNKI SPEŁNIONE — nie przełączać. "
              "Kryteria były ustalone PRZED pomiarem i tak zostają.")


if __name__ == "__main__":
    main()
