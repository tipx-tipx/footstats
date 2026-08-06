# -*- coding: utf-8 -*-
"""CZY KTÓREŚ ŹRÓDŁO PO CICHU STANĘŁO — kontrola świeżości, nie jakości.

Po co osobny skrypt: model może wyglądać na zepsuty tylko dlatego, że karmi
się nieświeżymi danymi. Wtedy każdy pomiar jakości opisuje nie model, lecz
zamarłe źródło — a taki wniosek prowadzi do majstrowania przy rzeczach,
które działają.

NIE UŻYWAJ `updated_at` Z SUPABASE. Ta kolumna pokazuje moment UTWORZENIA
wiersza, nie ostatniego zapisu: `value_bets` ma tam 3 lipca, choć zawiera
dane sprzed kwadransa. Świeżość czytamy wyłącznie ze stempli WEWNĄTRZ
payloadu.

Uwaga przy czytaniu wyników: część stempli to `kickoff_ts` meczów, które
dopiero się odbędą, więc „najnowszy wpis" bywa w PRZYSZŁOŚCI. To nie błąd.

    cd pipeline
    PYTHONUTF8=1 python scripts/kontrola_zrodel.py

CZYTA TYLKO — nie zapisuje nic.
"""

from __future__ import annotations

import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def wiek(ts: float | None, teraz: float) -> str:
    if not ts:
        return "brak stempla"
    dni = (teraz - float(ts)) / 86400.0
    kiedy = time.strftime("%d.%m %H:%M", time.localtime(float(ts)))
    if dni < 0:
        return f"{kiedy}  (mecz jeszcze przed nami)"
    return f"{kiedy}  ({dni:.1f} dni temu)"


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    from footstats import supa

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — kontrola potrzebuje chmury.")
        return

    teraz = time.time()
    print("=" * 74)
    print("ŹRÓDŁA, KTÓRE KARMIĄ DZISIEJSZY PRODUKT")
    print("=" * 74)

    meta = supa.get_key("meta") or {}
    print(f"cykl (meta.wygenerowano)   "
          f"{wiek(meta.get('wygenerowano_ts'), teraz)}")
    print(f"tryb produktu              {meta.get('tryb')} "
          f"— {meta.get('liga')} {meta.get('sezon')}")

    sb = supa.get_key("styl_bank_liga") or {}
    gry = sb.get("gry") or {}
    tsy = sorted(
        float(g["ts"]) for g in gry.values()
        if isinstance(g, dict) and isinstance(g.get("ts"), (int, float))
    )
    rozegrane = [t for t in tsy if t <= teraz]
    print(f"\nbank stylu (liga)          {len(gry)} meczów, "
          f"{len(sb.get('zawodnicy') or {})} zawodników")
    if rozegrane:
        print(f"  ostatni ROZEGRANY mecz   {wiek(rozegrane[-1], teraz)}")
    if tsy:
        print(f"  najstarszy w banku       "
              f"{time.strftime('%d.%m.%Y', time.localtime(tsy[0]))}")

    print("\nMECZE W BANKU DZIEŃ PO DNIU (ostatni tydzień)")
    licznik: Counter = Counter()
    for t in rozegrane:
        if t >= teraz - 7 * 86400:
            licznik[time.strftime("%d.%m (%a)", time.localtime(t))] += 1
    for d in sorted(licznik, key=lambda x: (x[3:5], x[:2])):
        print(f"  {d}   {licznik[d]:4}")
    if not licznik:
        print("  PUSTO — bank nie dostał ani jednego meczu od tygodnia.")

    pok = supa.get_key("pokrycie_liga") or {}
    if pok:
        print("\n" + "=" * 74)
        print("POKRYCIE OSTATNIEGO CYKLU — gdzie urywa się droga do typu")
        print("=" * 74)
        print(f"  meczów u bukmachera (Superbet)   {pok.get('mecze_superbet')}")
        print(f"  meczów ze statystykami (statshub){pok.get('mecze_statshub'):>5}")
        print(f"  sparowanych                      {pok.get('sparowane')}")
        print(f"  z tego BEZ historii drużyn       "
              f"{len(pok.get('mecze_bez_trendow') or [])}")
        print(f"  ostatecznie z typami             {pok.get('mecze_z_typami')}")
        bt = pok.get("mecze_bez_trendow") or []
        if bt:
            print("  przykłady bez historii: "
                  + "; ".join(str(x) for x in bt[:3]))
            print("  (typowo puchary europejskie — drużyny z dwóch różnych lig,"
                  " patrz limity źródeł drużynowych)")

    print("\n" + "=" * 74)
    print("ŹRÓDŁA ODSTAWIONE ŚWIADOMIE — stary stempel NIE jest tu awarią")
    print("=" * 74)
    sofa = supa.get_key("sofa_results") or {}
    print(f"  sofa_results   {len(sofa)} wpisów — worker Sofascore odpuszczony"
          " decyzją z 03.08")
    print("  player_sezon   karmiony tym samym workerem, więc stoi razem z nim"
          " (dotyczy sekcji „sezony” na kartach drabinek)")
    print("  elo_ratings    dotyczy WYŁĄCZNIE reprezentacji: w trybie ligowym"
          " `build_league` nawet go nie pobiera")
    print("                 (`elo_map = {} if tryb`), więc jego wiek nie ma"
          " wpływu na dzisiejsze typy")


if __name__ == "__main__":
    main()
