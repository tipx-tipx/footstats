# -*- coding: utf-8 -*-
"""CZY MODEL UCZY SIĘ NA WSZYSTKIM — audyt warstw uczenia, strumień po strumieniu.

Pytanie usera (2026-08-05): „czy model faktycznie uczy się na wszystkie rodzaje
typów i wszystkie funkcje — zawodnicy, drużyny, drabinki".

Odpowiada na trzy rzeczy, których nie widać z kodu:

  1. KTÓRY STRUMIEŃ MA DOŚĆ ROZLICZEŃ, żeby którakolwiek warstwa ruszyła.
     Każda warstwa ma własny próg (MIN_N). Poniżej progu NIE dzieje się nic
     i nikt o tym nie krzyczy — warstwa po prostu zwraca wartość globalną
     albo zero, a produkt wygląda, jakby się uczył.
  2. ILE KAŻDA WARSTWA REALNIE POPRAWIA — deklaracja kontra trafienia przed
     korektą i po niej.
  3. CZY CZYNNIKI MODELU ŻYJĄ. `czynniki` to mnożniki (rywal, sędzia,
     dom/wyjazd, scenariusz meczu, styl). Mnożnik równy 1,00 nic nie robi —
     pole może istnieć i być martwe. Sprawdzamy, ile typów danego rynku ma
     dany czynnik RÓŻNY od 1,00, czyli ile razy realnie ruszył liczbę.

    cd pipeline
    PYTHONUTF8=1 python scripts/audyt_uczenia.py

CZYTA TYLKO — nie zapisuje nic.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

NAZWY_STRUMIENI = {
    "pewniaki": "ZAWODNICY",
    "druzyny": "DRUŻYNY",
    "drabinki": "DRABINKI",
}


def _roi(grp: list[dict]) -> float:
    if not grp:
        return 0.0
    return sum(
        (float(r["kurs"]) - 1.0) if r["wynik"] == "wygrany" else -1.0
        for r in grp if r.get("kurs")
    ) / max(len(grp), 1)


def rozliczone(log: dict, R) -> list[dict]:
    return [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and r.get("p_model") and r.get("kurs")
        and R._z_biezacej_epoki(r) and not R._z_martwej_epoki(r)
    ]


def czesc1_strumienie(settled: list[dict], R) -> None:
    print("=" * 78)
    print("1. CZY KAŻDY STRUMIEŃ MA Z CZEGO SIĘ UCZYĆ")
    print("=" * 78)
    print(f"{'strumień':<12}{'rozliczeń':>10}{'deklaruje':>11}{'trafia':>9}"
          f"{'luka':>9}{'ROI':>9}")
    grupy: dict[str, list] = defaultdict(list)
    for r in settled:
        grupy[R._strumien(r)].append(r)
    for kod in ("pewniaki", "druzyny", "drabinki"):
        grp = grupy.get(kod) or []
        nazwa = NAZWY_STRUMIENI[kod]
        if not grp:
            print(f"{nazwa:<12}{0:>10}   — BRAK ROZLICZEŃ, warstwy stoją")
            continue
        n = len(grp)
        dekl = sum(float(r["p_model"]) for r in grp) / n
        traf = sum(1 for r in grp if r["wynik"] == "wygrany") / n
        print(f"{nazwa:<12}{n:>10}{dekl:>10.1%}{traf:>9.1%}"
              f"{(traf - dekl) * 100:>+8.1f}{_roi(grp):>9.1%}")

    print(f"\n{'PROGI WARSTW — poniżej nich warstwa NIE działa:':<60}")
    print(f"  korekta strumienia   MIN_N = {R.KOREKTA_STRUMIENIA_MIN_N}"
          f"   (okno {R.KOREKTA_STRUMIENIA_OKNO})")
    print(f"  kalibracja rynku     MIN_N = {R.MIN_N_KALIBRACJI}")
    print(f"  kwarantanna rynku    MIN_N = {R.KWARANTANNA_MIN_N}"
          f"   (okno {R.KWARANTANNA_OKNO}, min. dni {R.KWARANTANNA_MIN_DNI})")
    print(f"  korekta drabinek     MIN_N = {R.KOREKTA_DRABINEK_MIN_N}")
    print(f"  przedziały korekty   MIN_N = {R.KOREKTA_PRZEDZIAL_MIN_N}")


def czesc2_warstwy(log: dict, R) -> None:
    print("\n" + "=" * 78)
    print("2. CO KAŻDA WARSTWA REALNIE WYLICZYŁA")
    print("=" * 78)

    print("\nKOREKTA STRUMIENIA (o ile ściągamy szansę przed publikacją):")
    try:
        kor = R.korekta_strumienia(log)
        if not kor:
            print("   PUSTA — żaden strumień nie zebrał progu")
        for k, v in sorted(kor.items()):
            if isinstance(v, dict):
                g = v.get("global")
                biny = v.get("bins") or []
                print(f"   {NAZWY_STRUMIENI.get(k, k):<12} {g:+.3f}"
                      f"   (+{len(biny)} przedziałów)")
            else:
                print(f"   {NAZWY_STRUMIENI.get(k, k):<12} {v:+.3f}")
    except Exception as e:
        print(f"   BŁĄD: {e}")

    print("\nKALIBRACJA PER RYNEK (bias logitowy z rozliczeń):")
    bias = {}
    try:
        bias = R.compute_bias_full(log)
        if not bias:
            print("   PUSTA")
        for k, v in sorted(bias.items(), key=lambda x: str(x[0]))[:20]:
            print(f"   {str(k):<28} {v if not isinstance(v, dict) else v}")
    except Exception as e:
        print(f"   BŁĄD: {e}")

    # SKĄD SIĘ WZIĘŁA KAŻDA Z TYCH LICZB (czujnik z 05.08). Wiersz wyżej
    # pokazuje cztery liczby na rynek i wygląda to jak cztery pomiary —
    # a przedział bez własnej próby dostaje po prostu wartość globalną.
    print("\n   ILE Z TEGO TO POMIAR:")
    try:
        kor = R.korekta_strumienia(log)
        print("   " + R.zdanie_pokrycia(R.pokrycie_przedzialow(bias, kor)))
        for k, v in sorted(bias.items(), key=lambda x: str(x[0])):
            zr = (v or {}).get("zrodla") or []
            wlasne = sum(1 for z in zr if z == R.ZRODLO_WLASNA)
            if zr:
                print(f"   {str(k):<28} {wlasne}/{len(zr)}  {', '.join(zr)}")
    except Exception as e:
        print(f"   BŁĄD: {e}")

    print("\nKWARANTANNY (co jest chwilowo wstrzymane):")
    for nazwa, fn in (("rynki", R.rynki_kwarantanna),
                      ("strony", R.strony_kwarantanna),
                      ("kategorie", R.kategorie_kwarantanna)):
        try:
            d = fn(log)
            print(f"   {nazwa:<10} {len(d)}"
                  + (f"  ({', '.join(sorted(d)[:6])})" if d else "  — nic"))
        except Exception as e:
            print(f"   {nazwa:<10} BŁĄD: {e}")

    print("\nCZY SIĘ PSUJE (trzy ostatnie paczki wobec trzech poprzednich):")
    try:
        uczenie = R.raport_uczenia(log)
        for nazwa, rec in sorted(uczenie.items()):
            t = rec.get("trend")
            if not t:
                print(f"   {NAZWY_STRUMIENI.get(nazwa, nazwa):<12} za krótka historia")
                continue
            print(f"   {NAZWY_STRUMIENI.get(nazwa, nazwa):<12}"
                  f" {t['luka_poprzednio'] * 100:+.1f} -> {t['luka_teraz'] * 100:+.1f} pp"
                  f"   (szum {t['szum'] * 100:.1f} pp)")
        for z in R.ostrzezenia_trendu(uczenie):
            print(f"   ALARM: {z}")
    except Exception as e:
        print(f"   BŁĄD: {e}")

    print("\nPRZEWAGA NAD CENĄ (czy nasza liczba bije kurs):")
    try:
        p = R.przewaga_rynkow(log)
        bija = [k for k, v in p.items() if v.get("przewaga", 0) > 0]
        print(f"   {len(bija)} z {len(p)} rynków bije cenę"
              + (f": {', '.join(bija)}" if bija else ""))
    except Exception as e:
        print(f"   BŁĄD: {e}")


def czesc3_czynniki(vb: list[dict]) -> None:
    """Czy czynniki modelu ŻYJĄ — mnożnik 1,00 niczego nie zmienia."""
    print("\n" + "=" * 78)
    print("3. CZY CZYNNIKI MODELU ŻYJĄ (mnożnik ≠ 1,00 = realnie ruszył liczbę)")
    print("=" * 78)
    zyw = [b for b in vb if not b.get("sugestia")]
    grupy: dict[str, list] = defaultdict(list)
    for b in zyw:
        grupy[str(b.get("rynek_kod") or "?")].append(b)

    czynniki_kolejnosc = [
        "rywal", "sedzia", "dom_wyjazd", "scenariusz_meczu", "matchup",
        "minuty", "forma", "tempo",
    ]
    naglowek = "".join(f"{c[:9]:>11}" for c in czynniki_kolejnosc)
    print(f"{'rynek':<18}{'n':>4}{naglowek}")
    for rynek, grp in sorted(grupy.items(), key=lambda x: -len(x[1])):
        wiersz = f"{rynek[:18]:<18}{len(grp):>4}"
        for c in czynniki_kolejnosc:
            ile = 0
            for b in grp:
                cz = b.get("czynniki") or {}
                v = cz.get(c)
                if isinstance(v, (int, float)) and abs(float(v) - 1.0) > 0.02:
                    ile += 1
            wiersz += f"{(f'{ile}/{len(grp)}' if ile else '–'):>11}"
        print(wiersz)
    print("\n„–" + "\" = ten czynnik NIE ruszył ani jednego typu na tym rynku.")
    print("Powód bywa niewinny (rynek go nie używa) albo nie — patrz raport.")


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    from footstats import supa
    from footstats.jobs import rozliczanie as R

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — audyt potrzebuje księgi z chmury.")
        return
    log = R._migruj_log(supa.get_key("typy_log") or {})
    settled = rozliczone(log, R)
    print(f"Księga: {len(log)} wpisów, rozliczonych w bieżącej epoce: {len(settled)}\n")
    czesc1_strumienie(settled, R)
    czesc2_warstwy(log, R)
    czesc3_czynniki(supa.get_key("value_bets") or [])


if __name__ == "__main__":
    main()
