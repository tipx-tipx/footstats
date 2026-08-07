# -*- coding: utf-8 -*-
"""Pomiar korelacji między drużynami w tym samym meczu, per rynek.

Skąd liczba w `counts.KORELACJA_DRUZYN`. Odpalać co jakiś czas i podmieniać
wartości w tabeli — a nie zgadywać, że „korelacja jest ujemna".

    cd pipeline
    PYTHONUTF8=1 python scripts/zmierz_korelacje.py

DWA ŹRÓDŁA, po kolei:

1. `styl_bank_liga.gry` — mecze, które sami przeskanowaliśmy (365Scores).
   Rekord trzyma OBIE drużyny naraz, więc nie trzeba niczego parować po
   nazwach: para jest z definicji. To źródło jest wielokrotnie większe
   (zmierzone 07.08: 1509 meczów) i dlatego jest teraz pierwsze.
2. `druzyny_forma` — historia per drużyna per rynek. Obie strony tego samego
   meczu parujemy po (chwila rozpoczęcia, nazwa rywala). Zostaje jako
   uzupełnienie, bo niesie rynki, których bank nie zna.

PO CO TO W OGÓLE (2026-08-07): `counts.KORELACJA_DRUZYN` ma dziś JEDNĄ
zmierzoną liczbę — rożne, −0,127. Pozostałe osiem rynków `match_*`/`wiecej_*`
jedzie na założeniu, że drużyny w jednym meczu są niezależne, a to nieprawda
i myli się w OBIE strony: przy sumach zawyża prawdopodobieństwo po obu
stronach linii, przy „kto więcej" zaniża szanse stron drużynowych (bo zaniża
remis, a remis przy kartkach to 18,8% meczów).

Co robić z wynikiem:
  * `r` wchodzi wprost do `counts.KORELACJA_DRUZYN` (tylko przy n >= 100),
  * `dysp. sumy` i `dysp. różnicy` to kontrola: przy poprawnej korekcie model
    powinien odtwarzać właśnie te dwie wariancje.
"""

from __future__ import annotations

import math
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN_PAR = 100   # poniżej tego nie wpisujemy liczby do tabeli — to jeszcze szum

# Pola banku stylu -> nazwy rynków, których korelacji szukamy. Bank trzyma
# statystyki obu drużyn w JEDNYM rekordzie meczu, więc para jest z definicji
# i nie ma ryzyka sparowania dwóch różnych spotkań.
BANK_POLA = {
    "corners": "corners",      # rożne — jedyny rynek zmierzony przed 07.08
    "kartki": "cards",
    "shots": "shots",
    "sot": "sot",
    "fouls": "fouls",
    "gole": "goals",
    "offsides": "offsides",
}


def _pary_z_banku(bank: dict) -> dict[str, list[tuple[float, float]]]:
    """{rynek: [(gospodarz, gość), ...]} — obie strony z jednego rekordu.

    Kolejność stron bierzemy z kolejności kluczy w rekordzie (gospodarz jest
    zapisywany pierwszy). Dla samej korelacji to nieistotne — r jest
    symetryczne — ale dyspersja różnicy już nie, więc trzymamy się konwencji.
    """
    out: dict[str, list] = {}
    for rec in (bank.get("gry") or {}).values():
        druzyny = rec.get("druzyny") or {}
        if len(druzyny) != 2:
            continue
        a, b = list(druzyny.values())
        for pole, rynek in BANK_POLA.items():
            va, vb = a.get(pole), b.get(pole)
            if va is None or vb is None:
                continue
            out.setdefault(rynek, []).append((float(va), float(vb)))
    return out


def _statystyki(pary: list[tuple[float, float]]) -> dict | None:
    n = len(pary)
    if n < 30:
        return None
    xs = [p[0] for p in pary]
    ys = [p[1] for p in pary]
    mx, my = sum(xs) / n, sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs) / (n - 1)
    vy = sum((y - my) ** 2 for y in ys) / (n - 1)
    cov = sum((x - mx) * (y - my) for x, y in pary) / (n - 1)
    r = cov / math.sqrt(vx * vy) if vx > 0 and vy > 0 else 0.0
    sumy = [x + y for x, y in pary]
    roz = [x - y for x, y in pary]
    ms = sum(sumy) / n
    vs = sum((s - ms) ** 2 for s in sumy) / (n - 1)
    mr = sum(roz) / n
    vr = sum((d - mr) ** 2 for d in roz) / (n - 1)
    # błąd standardowy r — bez niego nie wiadomo, czy −0,05 to sygnał czy szum
    se = (1 - r * r) / math.sqrt(max(n - 2, 1))
    return {"n": n, "r": r, "se": se, "srednia_sumy": ms,
            "dysp_sumy": vs / ms if ms else 0.0,
            "dysp_roznicy": vr / ms if ms else 0.0}


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    from footstats import supa

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — pomiar potrzebuje historii z chmury.")
        return

    # --- ŹRÓDŁO 1: bank stylu (obie drużyny w jednym rekordzie) ---
    bank = supa.get_key("styl_bank_liga") or {}
    pary_banku = _pary_z_banku(bank)
    print(f"Mecze w banku stylu: {len(bank.get('gry') or {})}")
    if pary_banku:
        print(f"\n{'rynek':<14}{'par':>6}{'r':>9}{'± błąd':>9}{'śr. suma':>11}"
              f"{'dysp. sumy':>12}{'dysp. różnicy':>15}")
        for rynek, pary in sorted(pary_banku.items()):
            s = _statystyki(pary)
            if not s:
                print(f"{rynek:<14}{len(pary):>6}   (za mała próba)")
                continue
            istotne = abs(s["r"]) > 2 * s["se"]
            znacznik = ("" if s["n"] >= MIN_PAR else "  (za mało na wpis)")
            if s["n"] >= MIN_PAR and not istotne:
                znacznik = "  (nieodróżnialne od zera)"
            print(f"{rynek:<14}{s['n']:>6}{s['r']:>9.3f}{s['se']:>9.3f}"
                  f"{s['srednia_sumy']:>11.2f}{s['dysp_sumy']:>12.2f}"
                  f"{s['dysp_roznicy']:>15.2f}{znacznik}")
        print("\n  r ujemne = gdy jedna drużyna ma dużo, druga ma mało.")
        print("  Wpisujemy do `counts.KORELACJA_DRUZYN` tylko wiersze bez uwagi.")

    # --- ŹRÓDŁO 2: historia per drużyna (uzupełnienie) ---
    forma = supa.get_key("druzyny_forma") or []
    print(f"\nDrużyn w historii per rynek: {len(forma)}")

    # rynek -> (chwila, drużyna) -> {licznik, rywal, dom}
    idx: dict[str, dict] = defaultdict(dict)
    for zesp in forma:
        nazwa = str(zesp.get("nazwa") or zesp.get("druzyna") or "")
        for mk, f in (zesp.get("forma") or {}).items():
            ost, ts = f.get("ostatnie") or [], f.get("ts") or []
            ryw, dom = f.get("rywale") or [], f.get("dom") or []
            for i in range(min(len(ost), len(ts), len(ryw))):
                idx[mk][(int(ts[i]), nazwa)] = {
                    "licznik": float(ost[i]), "rywal": str(ryw[i]),
                    "dom": bool(dom[i]) if i < len(dom) else None,
                }

    print(f"\n{'rynek':<16}{'par':>6}{'r':>9}{'śr. suma':>11}"
          f"{'dysp. sumy':>12}{'dysp. różnicy':>15}")
    for mk, wpisy in sorted(idx.items()):
        pary, uzyte = [], set()
        for (ts, nazwa), rec in wpisy.items():
            klucz_r = (ts, rec["rywal"])
            if klucz_r not in wpisy or (ts, nazwa, rec["rywal"]) in uzyte:
                continue
            uzyte.add((ts, nazwa, rec["rywal"]))
            uzyte.add((ts, rec["rywal"], nazwa))
            a, b = rec["licznik"], wpisy[klucz_r]["licznik"]
            if rec.get("dom") is False:      # gospodarz zawsze pierwszy
                a, b = b, a
            pary.append((a, b))
        if len(pary) < 30:
            print(f"{mk:<16}{len(pary):>6}   (za mała próba)")
            continue
        n = len(pary)
        xs = [p[0] for p in pary]
        ys = [p[1] for p in pary]
        mx, my = sum(xs) / n, sum(ys) / n
        vx = sum((x - mx) ** 2 for x in xs) / (n - 1)
        vy = sum((y - my) ** 2 for y in ys) / (n - 1)
        cov = sum((x - mx) * (y - my) for x, y in pary) / (n - 1)
        r = cov / math.sqrt(vx * vy) if vx > 0 and vy > 0 else 0.0
        sumy = [x + y for x, y in pary]
        roz = [x - y for x, y in pary]
        ms = sum(sumy) / n
        vs = sum((s - ms) ** 2 for s in sumy) / (n - 1)
        mr = sum(roz) / n
        vr = sum((d - mr) ** 2 for d in roz) / (n - 1)
        znacznik = "" if n >= MIN_PAR else "   (za mało na wpis do tabeli)"
        print(f"{mk:<16}{n:>6}{r:>9.3f}{ms:>11.2f}{vs / ms:>12.2f}"
              f"{vr / ms:>15.2f}{znacznik}")

    print("\nDyspersja 1,00 = dokładnie Poisson. Powyżej — ogony grubsze,")
    print("poniżej — cieńsze. To one mówią, czy korekta trafia w rzeczywistość.")


if __name__ == "__main__":
    main()
