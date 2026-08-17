# -*- coding: utf-8 -*-
"""TRENING MODELU UCZONEGO — raz na dobę, wagi do Supabase.

    cd pipeline
    PYTHONUTF8=1 python scripts/trenuj_model.py            # trenuj i zapisz
    PYTHONUTF8=1 python scripts/trenuj_model.py --pokaz    # tylko policz, nie zapisuj

Po co osobny job: cykl ma tylko MNOŻYĆ macierze (milisekundy), a nie trenować.
Trening czyta cały magazyn (~4 MB) i przelicza 54 tys. wierszy — w cyklu,
który bywa dławiony przez cron GitHuba do co 1-3 h, to strata czasu na coś,
co zmienia się raz na dobę.

Zapisuje klucz `model_wagi`: wersja, znacznik czasu, wagi per rynek. Kilka kB.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    from footstats import supa
    from footstats.jobs import magazyn_druzyn as M
    from footstats.model import uczony as U

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — magazyn i wagi siedzą w chmurze.")
        return

    pokaz = "--pokaz" in sys.argv

    mag = M.wczytaj()
    if M.braki(mag):
        print(f"⚑ nie odczytano szardów magazynu {M.braki(mag)} — PRZERYWAM. "
              "Trening na części danych dałby wagi, których nikt by nie "
              "odróżnił od pełnych.")
        return
    st = M.statystyki(mag)
    print(M.zdanie_stanu(st))
    if not st.get("meczow"):
        return

    # bank trendów zawodniczych — ten sam model, offset minut (patrz sekcja
    # ZAWODNICY w `uczony.py`). Brak banku nie przerywa treningu drużynowego.
    lib = supa.get_key("trend_lib") or {}
    print(f"Bank trendów zawodniczych: {len(lib)} serii")

    wagi = U.trenuj(mag, lib=lib)
    rynki = wagi.get("rynki") or {}
    if not rynki:
        print("⚑ ŻADEN rynek nie zebrał progu próby — wagi nie powstały.")
        return

    zaw = wagi.get("rynki_zaw") or {}
    sumy = wagi.get("rynki_sum") or {}
    print(f"\nwytrenowane rynki: {len(rynki)} drużynowych, "
          f"{len(sumy)} sum meczowych, {len(zaw)} zawodniczych")
    print(f"{'rynek':<20}{'wierszy':>9}{'śr. zdarzeń':>13}"
          f"{'naddyspersja':>14}{'r_nb':>9}{'cech':>6}")
    for rynek, w in (sorted(rynki.items()) + sorted(sumy.items())
                     + sorted(zaw.items())):
        r_nb = w.get("r_nb")
        opis_r = f"{r_nb:.1f}" if r_nb else "—"
        print(f"{rynek:<20}{w['n']:>9}{w['sr_y']:>13.2f}"
              f"{w['naddyspersja']:>14.2f}{opis_r:>9}{len(w['cechy']):>6}")

    # NAJWIĘKSZE WSPÓŁCZYNNIKI — jedyny sposób, żeby zobaczyć, CZEGO model się
    # nauczył. Bez tego wagi są czarną skrzynką, a pytanie „czy model myśli
    # logicznie" zostaje bez odpowiedzi.
    print("\nCZEGO MODEL SIĘ NAUCZYŁ (5 najmocniejszych cech per rynek):")
    for rynek, w in (sorted(rynki.items()) + sorted(sumy.items())
                     + sorted(zaw.items())):
        pary = sorted(zip(w["cechy"], w["beta"]),
                      key=lambda kv: -abs(kv[1]))
        opis = ", ".join(f"{n} {b:+.2f}" for n, b in pary[:5] if n != "const")
        print(f"   {rynek:<16}{opis}")

    if pokaz:
        print("\n--pokaz: wagi NIE zostały zapisane")
        return

    if supa.put_key_bezpiecznie(U.KLUCZ_WAG, wagi):
        print(f"\nzapisano `{U.KLUCZ_WAG}` — {U.zdanie_stanu(wagi)}")
    else:
        print("\n⚑ ZAPIS WAG SIĘ NIE UDAŁ — w chmurze zostają poprzednie")


if __name__ == "__main__":
    main()
