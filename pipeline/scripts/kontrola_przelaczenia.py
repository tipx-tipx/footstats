# -*- coding: utf-8 -*-
"""CZY PRZEŁĄCZENIE NA MODEL UCZONY DZIAŁA — jedno uruchomienie, jedna odpowiedź.

    cd pipeline
    PYTHONUTF8=1 python scripts/kontrola_przelaczenia.py

Po co to istnieje: 18.08 przełączyliśmy stronę na model uczony BEZ czekania na
próg 100 sparowanych rozliczeń (decyzja właściciela: „obecny model i tak nie
działa"). Warunkiem było, żeby NIGDY WIĘCEJ nie dało się odkryć po dwóch
tygodniach, że coś po cichu nie działało. To narzędzie jest tym warunkiem.

Odpowiada na CZTERY pytania, w tej kolejności — bo każde następne ma sens
tylko wtedy, gdy poprzednie wypadło dobrze:

  1. CZY MODEL W OGÓLE JEST NA STRONIE — ile typów ma `zrodlo_p = uczony`.
     Zero znaczy, że przełącznik kłamie i reszta liczb jest bez znaczenia.
  2. CZY NIE POKAZUJEMY MIESZANKI — ile spadło na stary przez brak pokrycia.
  3. CZY LICZBA JEST UCZCIWA — luka deklaracji, per rynek i strona.
  4. CZY WYGRYWAMY Z CENĄ — margines nad ceną, jedyna miara, która płaci.

CZYTA TYLKO. Decyzja o cofnięciu należy do właściciela
(`uczony.ZRODLO_SZANSY` -> "stary").
"""
from __future__ import annotations

import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# przełączenie weszło na produkcję 18.08 — wcześniejsze rozliczenia opisują
# stary rachunek i mieszanie ich z nowymi dałoby średnią z dwóch epok
PRZELACZENIE_TS = 1787000000    # 2026-08-18


def _brier(pary):
    return sum((p - y) ** 2 for p, y in pary) / max(len(pary), 1)


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
        print("Brak SUPABASE_URL — księga siedzi w chmurze.")
        return
    surowy, ok = supa.get_key_ok("typy_log")
    if not ok:
        print("⚑ NIE UDAŁO SIĘ ODCZYTAĆ KSIĘGI — nie interpretuj zer.")
        return
    log = R._migruj_log(surowy or {})
    print(f"księga: {len(log)} wpisów")
    print("przełącznik: " + ", ".join(
        f"{k}={v}" for k, v in sorted(U.ZRODLO_SZANSY.items())) + "\n")

    swieze = [r for r in log.values()
              if float(r.get("kickoff_ts") or 0) >= PRZELACZENIE_TS]
    zrodla = Counter(str(r.get("zrodlo_p") or "brak stempla") for r in swieze)

    print("=" * 78)
    print("1. CZY MODEL JEST NA STRONIE")
    print("=" * 78)
    print(f"   typów z meczów po przełączeniu: {len(swieze)}")
    for k, v in zrodla.most_common():
        print(f"      {v:6}  {k}")
    n_uczony = zrodla.get("uczony", 0)
    n_fallback = zrodla.get("stary_bez_pokrycia", 0)
    n_razem = n_uczony + n_fallback
    if not swieze:
        print("\n   Za wcześnie — żaden mecz po przełączeniu jeszcze nie wszedł.")
        return
    if not n_razem:
        print("\n   ⚑⚑ ANI JEDEN typ nie ma stempla źródła. Albo przełączenie "
              "nie doszło na produkcję, albo stempel nie dojeżdża — "
              "sprawdź `uczony.stempel_zrodla` w ścieżce wyceny.")
        return

    print("\n" + "=" * 78)
    print("2. CZY NIE POKAZUJEMY MIESZANKI")
    print("=" * 78)
    udzial = n_uczony / n_razem
    print(f"   modelem policzone: {n_uczony}/{n_razem} = {udzial:.1%}")
    if udzial < 0.90:
        print(f"   ⚑ {n_fallback} typów spadło na stary rachunek przez brak "
              "pokrycia modelu — strona pokazuje MIESZANKĘ dwóch rachunków. "
              "Szukaj w magazynie drużyn (za krótka historia), nie w wagach.")
    else:
        print("   ✓ strona liczy jednym rachunkiem")

    rozliczone = [r for r in swieze
                  if r.get("wynik") in ("wygrany", "przegrany")
                  and r.get("zrodlo_p") == "uczony" and r.get("p_model")]
    print("\n" + "=" * 78)
    print("3. CZY LICZBA JEST UCZCIWA (luka = trafność − deklaracja)")
    print("=" * 78)
    if len(rozliczone) < 30:
        print(f"   rozliczeń modelem: {len(rozliczone)} — za mało na werdykt "
              "(próg 30). Wróć za dzień.")
    else:
        def _wiersz(nazwa, rs):
            if len(rs) < 10:
                return
            n = len(rs)
            traf = sum(1 for r in rs if r["wynik"] == "wygrany") / n
            dekl = sum(float(r["p_model"]) for r in rs) / n
            luka = (traf - dekl) * 100
            se = math.sqrt(max(traf * (1 - traf), 1e-9) / n) * 100
            flaga = "  ⚑ POZA PROGIEM" if abs(luka) > 5 and abs(luka) > 2 * se else ""
            print(f"   {nazwa:<28}{n:>6}{traf:>9.1%}{dekl:>10.1%}"
                  f"{luka:>+9.1f} pp  (±{se:.1f}){flaga}")

        print(f"   {'wycinek':<28}{'n':>6}{'trafia':>9}{'deklaruje':>10}"
              f"{'luka':>12}")
        _wiersz("RAZEM", rozliczone)
        print()
        wg = defaultdict(list)
        for r in rozliczone:
            wg[str(r.get("rynek_kod"))].append(r)
        for rynek in sorted(wg):
            _wiersz(rynek, wg[rynek])
        print()
        for s in ("ponizej", "powyzej"):
            _wiersz(f"strona: {s}",
                    [r for r in rozliczone if r.get("strona") == s])

    print("\n" + "=" * 78)
    print("4. CZY WYGRYWAMY Z CENĄ (margines = trafność − 1/kurs)")
    print("=" * 78)
    zk = [r for r in rozliczone if r.get("kurs")]
    if len(zk) < 30:
        print(f"   {len(zk)} rozliczeń z kursem — za mało (próg 30).")
    else:
        n = len(zk)
        traf = sum(1 for r in zk if r["wynik"] == "wygrany") / n
        cena = sum(1.0 / float(r["kurs"]) for r in zk) / n
        se = math.sqrt(max(traf * (1 - traf), 1e-9) / n) * 100
        marg = (traf - cena) * 100
        print(f"   {n} rozliczeń: trafia {traf:.1%}, cena implikuje {cena:.1%}")
        print(f"   margines {marg:+.1f} pp  (błąd standardowy {se:.1f} pp)")
        if marg > 2 * se:
            print("   ✓ BIJEMY CENĘ poza szumem")
        elif marg > 0:
            print("   ~ margines dodatni, ale W SZUMIE — potrzeba więcej próby")
        else:
            print("   ⚑ PRZEGRYWAMY Z CENĄ — selekcja nie działa")

    print("\n" + "=" * 78)
    print("PORÓWNANIE PAROWANE — ten sam typ, oba rachunki")
    print("=" * 78)
    # ⚑⚑ TU BYŁ FAŁSZYWY ALARM (naprawione 19.08). Do dziś werdykt zapadał na
    # SAMYM ZNAKU różnicy Brier: `bu > bs` → „MODEL GORSZY, rozważ powrót".
    # Zmierzone tego dnia na 32 rozliczeniach: różnica +0,0031 przy błędzie
    # standardowym ±0,0176, czyli REMIS — a narzędzie zalecało cofnięcie
    # przełącznika. Test znaków wychodził wtedy 16:16.
    #
    # Różnica jest SPAROWANA (ten sam typ niesie obie wyceny, wynik meczu się
    # skraca), więc jej błąd liczymy z odchylenia różnic, nie z wariancji
    # dwóch Brierów osobno. To jedyny sposób, żeby odróżnić „model gorszy"
    # od „za mało danych, żeby cokolwiek powiedzieć".
    pary = [r for r in swieze
            if r.get("wynik") in ("wygrany", "przegrany")
            and r.get("p_stary") and isinstance(r.get("p_uczony"), dict)
            and r["p_uczony"].get("p") is not None]
    if len(pary) < 30:
        print(f"   {len(pary)} sparowanych — za mało (próg 30).")
        return
    y = [1.0 if r["wynik"] == "wygrany" else 0.0 for r in pary]
    st = [float(r["p_stary"]) for r in pary]
    uc = [float(r["p_uczony"]["p"]) for r in pary]
    bs = _brier(list(zip(st, y)))
    bu = _brier(list(zip(uc, y)))
    n = len(pary)
    # różnice per typ: dodatnia = model gorszy na TYM typie
    d = [(u - yy) ** 2 - (s - yy) ** 2 for s, u, yy in zip(st, uc, y)]
    sr = sum(d) / n
    war = sum((x - sr) ** 2 for x in d) / max(n - 1, 1)
    se = math.sqrt(war / n)
    print(f"   n = {n}   Brier stary {bs:.4f}   model {bu:.4f}   {bu - bs:+.4f}")
    print(f"   błąd standardowy RÓŻNICY (parowany): ±{se:.4f}")
    print(f"   95% przedział: [{sr - 1.96 * se:+.4f}, {sr + 1.96 * se:+.4f}]")
    lepszy = sum(1 for x in d if x < 0)
    gorszy = sum(1 for x in d if x > 0)
    print(f"   test znaków: model lepszy na {lepszy}, gorszy na {gorszy} typach")
    if sr - 1.96 * se > 0:
        print("   ⚑ MODEL ISTOTNIE GORSZY — rozważ powrót (uczony.ZRODLO_SZANSY)")
    elif sr + 1.96 * se < 0:
        print("   ✓ MODEL ISTOTNIE LEPSZY — przełączenie się broni")
    else:
        print("   → NIEROZSTRZYGNIĘTE: przedział obejmuje zero. NIE cofać "
              "przełącznika na tej podstawie.")
        if sr:
            trzeba = (1.96 * math.sqrt(war) / abs(sr)) ** 2
            print(f"     (żeby rozstrzygnąć różnicę TEJ wielkości, potrzeba "
                  f"~{trzeba:.0f} rozliczeń)")

    # ⚑ TEST OSTRZEJSZY NIŻ BRIER, dostępny OD RAZU. Brier jest zdominowany
    # przez wariancję wyniku, więc mikroskopijne różnice wycen toną w szumie
    # (19.08: do rozstrzygnięcia trzeba było ~4000 rozliczeń). Ale model idzie
    # SUROWY, bez warstw ściągających, więc deklaruje wyraźnie więcej niż
    # stary rachunek — a to daje ostry, jednoznaczny sprawdzian: jeśli model
    # jest uczciwy, trafność musi wyjść W POBLIŻU jego deklaracji.
    print()
    dekl = sum(uc) / n
    traf = sum(y) / n
    se_t = math.sqrt(max(traf * (1 - traf), 1e-9) / n)
    print(f"   deklaracja modelu {dekl:.1%} wobec trafności {traf:.1%} "
          f"(±{se_t * 196:.1f} pp)")
    print(f"   dla porównania stary rachunek deklarował {sum(st) / n:.1%}")
    # ⚑ „MIEŚCI SIĘ W SZUMIE" TO NIE TO SAMO CO „UCZCIWA". Przy 32 rozliczeniach
    # błąd wynosi ±17 pp, więc w szumie mieści się DOSŁOWNIE WSZYSTKO — także
    # luka −12 pp, której na pewno nie chcemy nazwać uczciwą liczbą. Werdykt
    # „uczciwa" wolno postawić dopiero wtedy, gdy próba jest na tyle duża, że
    # pomiar odróżniłby lukę większą niż próg odbioru (5 pp z planu).
    PROG_ODBIORU_PP = 5.0
    luka = (traf - dekl) * 100
    blad_pp = 2 * se_t * 100
    if blad_pp > PROG_ODBIORU_PP:
        print(f"   → luka {luka:+.1f} pp, ale błąd ±{blad_pp:.1f} pp jest "
              f"WIĘKSZY niż próg odbioru {PROG_ODBIORU_PP:.0f} pp —")
        print("     przy tej próbie pomiar nie odróżni modelu uczciwego od "
              "przeszacowującego.")
        print("     To znaczy ZA MAŁO DANYCH, a nie „w porządku”.")
        trzeba = max(traf * (1 - traf), 1e-9) / ((PROG_ODBIORU_PP / 196) ** 2)
        print(f"     (na werdykt potrzeba ~{trzeba:.0f} rozliczeń)")
    elif abs(luka) <= blad_pp:
        print(f"   ✓ luka {luka:+.1f} pp w szumie przy błędzie ±{blad_pp:.1f} pp "
              "— liczba modelu jest UCZCIWA")
    else:
        print(f"   ⚑ luka {luka:+.1f} pp poza szumem (±{blad_pp:.1f}) — model "
              f"{'PRZESZACOWUJE' if luka < 0 else 'niedoszacowuje'}")


if __name__ == "__main__":
    main()
