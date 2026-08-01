# -*- coding: utf-8 -*-
"""Pomiar korelacji między drużynami w tym samym meczu, per rynek.

Skąd liczba w `counts.KORELACJA_DRUZYN`. Odpalać co jakiś czas i podmieniać
wartości w tabeli — a nie zgadywać, że „korelacja jest ujemna".

    cd pipeline
    PYTHONUTF8=1 python scripts/zmierz_korelacje.py

Źródło: klucz `druzyny_forma` w Supabase (historia per drużyna per rynek:
liczby zdarzeń, rywale, chwile rozpoczęcia). Obie strony tego samego meczu
parujemy po (chwila rozpoczęcia, nazwa rywala) — to jedyny klucz, który mamy
po obu stronach.

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

    forma = supa.get_key("druzyny_forma") or []
    print(f"Drużyn w historii: {len(forma)}")

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
