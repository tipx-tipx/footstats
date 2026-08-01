"""Raport „czy bijemy cenę bukmachera" — mapa roboty nad modelem.

Po co to istnieje: jedyne pytanie, które rozstrzyga, czy model ma na danym
rynku cokolwiek do powiedzenia, brzmi — czy nasza liczba jest lepszą prognozą
niż liczba wyciągnięta z samego kursu. Zmierzone 2026-08-01 na 576
rozliczeniach: bijemy cenę w 2 rynkach na 9, i zarabiamy DOKŁADNIE w tym,
w którym bijemy ją wyraźnie (`team_goals|ponizej`).

To NIE jest narzędzie do wycinania rynków — niczego nie blokujemy. To jest
mapa: pokazuje, gdzie model jeszcze nie umie, żeby było wiadomo, nad czym
pracować i czy praca dała efekt.

Odpalanie (nic nie zapisuje, sam odczyt):
    cd pipeline
    PYTHONUTF8=1 python -m footstats.jobs.przewaga
    PYTHONUTF8=1 python -m footstats.jobs.przewaga --dni 14
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except Exception:
    pass

from .. import supa
from . import rozliczanie


def _strzalka(x: float | None) -> str:
    if x is None:
        return "   ?"
    if x > 0.002:
        return " lepiej"
    if x < -0.002:
        return " gorzej"
    return "  bez zmian"


def main() -> None:
    dni = 7
    if "--dni" in sys.argv:
        try:
            dni = int(sys.argv[sys.argv.index("--dni") + 1])
        except (IndexError, ValueError):
            pass

    log = rozliczanie._migruj_log(supa.get_key("typy_log") or {})
    rynki = rozliczanie.przewaga_rynkow(log)
    pasma = rozliczanie.przewaga_pasm(log)

    print("=" * 78)
    print("CZY NASZA LICZBA BIJE CENĘ BUKMACHERA — wg rynku i strony")
    print("=" * 78)
    if not rynki:
        print(f"  (żaden rynek nie ma jeszcze {rozliczanie.PRZEWAGA_MIN_N} rozliczeń)")
    hist = rozliczanie.get_key_ok_przewagi()[0] or {}
    ostatni = sorted(hist)[-1] if hist else None
    ukryte = rozliczanie.rynki_do_ukrycia(
        rynki, hist,
        set((hist.get(ostatni) or {}).get("ukryte") or ()) if ostatni else set(),
    )
    print(f"  {'rynek':18} {'strona':9} {'n':>5} {'nasz':>8} {'cena':>8} "
          f"{'przewaga':>10} {'ile SE':>7}  stan")
    for k, v in sorted(rynki.items(), key=lambda kv: -kv[1]["przewaga"]):
        se = float(v.get("se") or 0.0)
        if k in ukryte:
            stan = "UKRYTY (do dopracowania)"
        elif v["przewaga"] > 0:
            stan = ("BIJEMY CENĘ" if se >= 2
                    else "lepsi, ale jeszcze nie dowód")
        elif se > rozliczanie.UKRYCIE_SE:
            stan = "w granicach szumu"
        elif v["n"] < rozliczanie.UKRYCIE_MIN_N:
            stan = "istotnie gorsi, za mała próba"
        else:
            stan = f"istotnie gorsi — czeka na {rozliczanie.UKRYCIE_DNI} dni"
        print(f"  {str(v['rynek_kod']):18} {str(v['strona']):9} {v['n']:>5} "
              f"{v['brier_model']:>8.4f} {v['brier_kurs']:>8.4f} "
              f"{v['przewaga']:>+10.4f} {v.get('se', 0):>+7.2f}  {stan}")
    print(f"\n  Próg ukrycia: {rozliczanie.UKRYCIE_SE} błędu std, min "
          f"{rozliczanie.UKRYCIE_MIN_N} rozliczeń, {rozliczanie.UKRYCIE_DNI} dni "
          f"z rzędu. Powrót przy {rozliczanie.POWROT_SE}.")

    print()
    print("=" * 78)
    print("TO SAMO WG PRZEDZIAŁU KURSU")
    print("=" * 78)
    print(f"  {'kurs':12} {'n':>5} {'weszło':>8} {'nasz':>8} {'cena':>8} "
          f"{'przewaga':>10}")
    for k, v in sorted(pasma.items(), key=lambda kv: kv[1]["od"]):
        kto = "BIJEMY" if v["przewaga"] > 0 else ""
        print(f"  {k:12} {v['n']:>5} {100*v['hit']:>7.1f}% "
              f"{v['brier_model']:>8.4f} {v['brier_kurs']:>8.4f} "
              f"{v['przewaga']:>+10.4f}  {kto}")

    print()
    print("=" * 78)
    print(f"KIERUNEK — zmiana wobec pomiaru sprzed {dni} dni")
    print("=" * 78)
    trend = rozliczanie.trend_przewagi(dni)
    if not trend:
        print("  (za krótka historia — pierwszy stempel powstaje przy cyklu)")
    else:
        print(f"  {'co':28} {'było':>9} {'teraz':>9} {'zmiana':>9}  {'próba':>12}")
        for k, v in sorted(trend.items(),
                           key=lambda kv: -(kv[1]["zmiana"] or -9)):
            b = f"{v['bylo']:+.4f}" if v["bylo"] is not None else "  —"
            t = f"{v['teraz']:+.4f}" if v["teraz"] is not None else "  —"
            z = f"{v['zmiana']:+.4f}" if v["zmiana"] is not None else "  —"
            proba = (f"{v['n_bylo']}->{v['n_teraz']}"
                     if v["n_bylo"] is not None else f"{v['n_teraz']}")
            print(f"  {k:28} {b:>9} {t:>9} {z:>9}  {proba:>12}"
                  f"{_strzalka(v['zmiana'])}")

    print()
    print("Przypomnienie: to jest mapa, nie brama. Nic nie blokujemy —")
    print("rynek o ujemnej przewadze zostaje w grze i czeka, aż model się go nauczy.")


if __name__ == "__main__":
    main()
