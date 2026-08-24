# -*- coding: utf-8 -*-
"""CZY POKRYCIE DZIAŁA U ZAWODNIKÓW — pomiar przed włączeniem wagi.

Kod pokrycia zawodniczego jest wpięty od 24.08, ale WYŁĄCZONY
(`uczony.WAGA_POKRYCIA_ZAW = 0.0`). Powód: u drużyn pokrycie WŁASNE nie
porządkowało niczego (AUC 0,499) — cały sygnał niósł RYWAL, a zawodnicy nie
mają dziś odpowiednika jego koncesji. Nie ma więc podstaw zakładać, że samo
pokrycie własne zadziała, i nie wolno go włączać „bo u drużyn pomogło".

KRYTERIUM WŁĄCZENIA, ustalone PRZED pomiarem:

    Brier mieszanki lepszy o >= 2% OUT-OF-SAMPLE, przy wadze dobranej
    na PIERWSZEJ połowie próby i ocenionej na drugiej.

Poniżej progu — waga zostaje na zerze, a wynik zapisujemy przy stałej, żeby
nikt nie sprawdzał tego po raz drugi.

⚑ POKRYCIE JEST STEMPLOWANE MIMO WYŁĄCZENIA. `prognoza_zawodnika` dokłada
`pkw` i `pkn` do wyniku niezależnie od wagi, więc księga zbiera próbę SAMA.
Ten skrypt liczy pokrycie z banku od nowa (żeby dało się mierzyć wstecz), ale
po tygodniu produkcji wystarczy porównać `p` z `p_bez_pokrycia` w księdze.

    cd pipeline
    PYTHONUTF8=1 python scripts/pomiar_pokrycia_zaw.py

CZYTA TYLKO — nie zapisuje nic.
"""

from __future__ import annotations

import bisect
import math
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN_N = 25
# pasma kursu dla strumienia zawodniczego — szersze niż drużynowe, bo oferta
# zawodnicza siedzi wyżej (patrz `uczony.KURS_MAX_PODMIOTU`)
PASMA_KURSU = [(1.19, 1.50), (1.50, 1.90), (1.90, 2.40), (2.40, 6.01)]
PROG_WLACZENIA = -2.0        # o tyle % Brier ma się poprawić OOS


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    from footstats import supa
    from footstats.jobs import rozliczanie as R
    from footstats.model import uczony as U

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — pomiar potrzebuje banku i księgi z chmury.")
        return

    lib = supa.get_key("trend_lib") or {}
    log = R._migruj_log(supa.get_key("typy_log") or {})
    if not lib or not log:
        print("Bank albo księga nie wczytały się (Supabase bywa niedostępny "
              "— HTTP 5xx). Uruchom ponownie za chwilę.")
        return
    print(f"bank zawodniczy: {len(lib)} serii")

    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and r.get("kickoff_ts") and r.get("p_model") and r.get("kurs")
        and r.get("linia") is not None
        and R._strumien(r) == "pewniaki"
        and R._z_biezacej_epoki(r) and not R._z_martwej_epoki(r)
    ]
    print(f"rozliczonych typów zawodniczych: {len(settled)}")
    if len(settled) < MIN_N * 4:
        print("Za mała próba na rozstrzygnięcie — wrócić po kolejnych "
              "rozliczeniach.")
        return
    print("rynki:", dict(Counter(str(r.get("rynek_kod")) for r in settled)
                         .most_common(6)))

    for r in settled:
        seria = lib.get(f"{r.get('podmiot_id')}:{r.get('rynek_kod')}")
        r["_pk"] = U.pokrycie_zawodnika(seria, r["linia"], do_ts=r["kickoff_ts"])

    Z = [r for r in settled if r.get("_pk") is not None]
    print(f"z policzonym pokryciem: {len(Z)} "
          f"({len(Z) / max(len(settled), 1):.0%})")
    if len(Z) < MIN_N * 4:
        print("Za mało typów z pokryciem — bank nie sięga wstecz dość daleko.")
        return

    def traf(g):
        return sum(1 for r in g if r["wynik"] == "wygrany") / len(g) if g else 0.0

    def p_mod(r):
        pu = r.get("p_uczony")
        if isinstance(pu, dict) and isinstance(pu.get("p"), (int, float)):
            return float(pu["p"])
        return float(r["p_model"])

    def po_stronie(r):
        v = r.get("_pk")
        if v is None:
            return None
        return float(v) if r.get("strona") != "ponizej" else 1.0 - float(v)

    def auc_w_pasmach(f, zbior):
        """AUC liczone OSOBNO w każdym paśmie ceny — inaczej mierzy cennik."""
        lic = mia = 0.0
        for lo, hi in PASMA_KURSU:
            g = [r for r in zbior
                 if lo <= float(r["kurs"]) < hi and f(r) is not None]
            poz = sorted(f(r) for r in g if r["wynik"] == "wygrany")
            neg = [f(r) for r in g if r["wynik"] == "przegrany"]
            if len(poz) < 15 or len(neg) < 15:
                continue
            lepiej = rowno = 0
            for q in neg:
                lepiej += len(poz) - bisect.bisect_right(poz, q)
                rowno += (bisect.bisect_right(poz, q)
                          - bisect.bisect_left(poz, q))
            lic += len(g) * ((lepiej + 0.5 * rowno) / (len(poz) * len(neg)))
            mia += len(g)
        return (lic / mia if mia else None), int(mia)

    def gora_dol(f, zbior):
        gora, dol = [], []
        for lo, hi in PASMA_KURSU:
            g = [r for r in zbior
                 if lo <= float(r["kurs"]) < hi and f(r) is not None]
            if len(g) < 45:
                continue
            g = sorted(g, key=f)
            t = len(g) // 3
            dol += g[:t]
            gora += g[-t:]
        return (traf(gora), traf(dol)) if len(gora) >= 30 else None

    print("\n" + "=" * 84)
    print("1. CZY POKRYCIE PORZĄDKUJE — przy tej samej cenie")
    print("=" * 84)
    print(f"{'sygnał':<34}{'n':>6}{'AUC':>8}{'górna 1/3':>11}{'dolna 1/3':>11}"
          f"{'różnica':>10}")
    for nazwa, f in (("pokrycie zawodnika", po_stronie),
                     ("szansa modelu (odniesienie)", p_mod)):
        a, n = auc_w_pasmach(f, Z)
        gd = gora_dol(f, Z)
        if a is None or not gd:
            print(f"{nazwa:<34}{'—':>6}   za mała próba")
            continue
        g, d = gd
        print(f"{nazwa:<34}{n:>6}{a:>8.3f}{g:>11.1%}{d:>11.1%}"
              f"{(g - d) * 100:>+10.1f}")

    def brier(g, f):
        v = [(f(r), 1.0 if r["wynik"] == "wygrany" else 0.0) for r in g]
        v = [(p, y) for p, y in v if p is not None and 0 < p < 1]
        return sum((p - y) ** 2 for p, y in v) / len(v) if v else None

    def mieszaj(waga):
        def f(r):
            p, _ = U.zmieszaj_z_pokryciem(p_mod(r), r.get("_pk"), None,
                                          str(r.get("strona") or ""),
                                          waga=waga)
            return p
        return f

    print("\n" + "=" * 84)
    print("2. BRIER — kryterium włączenia: >= 2% poprawy OUT-OF-SAMPLE")
    print("=" * 84)
    ws = sorted(Z, key=lambda r: float(r["kickoff_ts"]))
    p = len(ws) // 2
    A, B = ws[:p], ws[p:]
    bA, bB = brier(A, p_mod), brier(B, p_mod)
    print(f"   I połowa {len(A)}, II połowa {len(B)}")
    print(f"   {'sam model':<24}I {bA:.5f}   II {bB:.5f}")
    najlepsza, najlepszy = None, float("inf")
    for w in (0.2, 0.3, 0.4, 0.5, 0.6):
        a, b = brier(A, mieszaj(w)), brier(B, mieszaj(w))
        print(f"   waga {w:<19}I {a:.5f}   II {b:.5f}"
              f"   ({(b - bB) / bB * 100:+.2f}% wobec modelu)")
        if a < najlepszy:
            najlepsza, najlepszy = w, a

    print("\n" + "=" * 84)
    print("3. WERDYKT")
    print("=" * 84)
    if najlepsza is None:
        print("   Nie udało się dobrać wagi.")
        return
    zmiana = (brier(B, mieszaj(najlepsza)) - bB) / bB * 100
    print(f"   waga dobrana na I połowie: {najlepsza}")
    print(f"   jej wynik na II połowie:   {zmiana:+.2f}%  (próg {PROG_WLACZENIA}%)")
    if zmiana <= PROG_WLACZENIA:
        print(f"\n   ✓ KRYTERIUM SPEŁNIONE — ustawić "
              f"`uczony.WAGA_POKRYCIA_ZAW = {najlepsza}` i wypchnąć.")
    else:
        print("\n   ✗ PONIŻEJ PROGU — waga zostaje na zerze.")
        print("   Zapisać ten wynik przy `WAGA_POKRYCIA_ZAW`, żeby nikt nie "
              "sprawdzał tego drugi raz.")


if __name__ == "__main__":
    main()
