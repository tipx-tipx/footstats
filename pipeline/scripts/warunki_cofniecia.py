# -*- coding: utf-8 -*-
"""Czy zmiany z 04.08 trzymają się na świeżych rozliczeniach.

Dwa warunki cofnięcia, zapisane przy wdrożeniu:

  1. OKNO ZGODY +12 -> +16 pp (commit `ac58331`, 04.08 12:39). Wpuściliśmy
     pasmo, które wcześniej odcinaliśmy. Umowa: jeśli pasmo 12–16 pp zejdzie
     poniżej −8% ROI na ŚWIEŻYCH rozliczeniach, wracamy na +12.
  2. KARA HORYZONTU w kuponach (commit `04d618f`, 04.08 16:32). Kupony
     długoterminowe deklarowały 73% i wchodziły w 52% (0 trafień na 27).
     Umowa: sprawdzić, czy przestały.

    cd pipeline
    PYTHONUTF8=1 python scripts/warunki_cofniecia.py

CZYTA TYLKO — nie zapisuje do Supabase nic.

PUŁAPKA, KTÓRA ZEPSUŁA JUŻ DWA POMIARY: „świeże rozliczenie" to nie to samo,
co „świeży typ". Typ opublikowany pod STARĄ regułą rozlicza się jeszcze przez
kilka dni po zmianie i wchodzi do próby, wyglądając na dowód. Dlatego każde
pasmo pokazujemy w trzech cięciach: cała księga (odniesienie do pomiaru
z 04.08), rozliczone po zmianie i OPUBLIKOWANE po zmianie. Rozstrzyga
wyłącznie to trzecie — patrz [[wersjonowanie-i-martwe-epoki]].
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Chwile wdrożenia (czas lokalny PL) — do sekundy nie ma znaczenia, bo zmiana
# wchodzi na produkcję dopiero z najbliższym cyklem chmurowym (~1–1,5 h).
WDROZENIE_OKNO = int(time.mktime((2026, 8, 4, 12, 39, 0, 0, 0, -1)))
WDROZENIE_HORYZONT = int(time.mktime((2026, 8, 4, 16, 32, 0, 0, 0, -1)))

PASMA = [(0.00, 0.04), (0.04, 0.08), (0.08, 0.12), (0.12, 0.16),
         (0.16, 0.20), (0.20, 9.99)]

# granica długiego horyzontu — ta sama, na której stoi kara (patrz kupony.py)
DOBA_S = 86400


def _tabela_pasm(rekordy: list[dict], naglowek: str) -> None:
    from footstats.model import betting

    print(f"\n{naglowek}")
    if not rekordy:
        print("   (brak rozliczeń w tym cięciu)")
        return
    print(f"   {'pasmo':<14}{'n':>5}{'ROI':>9}{'trafień':>10}{'deklaracja':>12}")
    for lo, hi in PASMA:
        grp = [
            r for r in rekordy
            if lo <= float(r["p_model"]) - betting.implied_prob_one_sided(
                float(r["kurs"])) < hi
        ]
        if not grp:
            continue
        traf = sum(1 for r in grp if r["wynik"] == "wygrany")
        roi = sum(
            (float(r["kurs"]) - 1.0) if r["wynik"] == "wygrany" else -1.0
            for r in grp
        ) / len(grp)
        dekl = sum(float(r["p_model"]) for r in grp) / len(grp)
        etyk = f"+{lo * 100:.0f}..+{hi * 100:.0f} pp" if hi < 9 else f"+{lo * 100:.0f} pp i dalej"
        uwaga = "   <- pasmo sporne" if (lo, hi) == (0.12, 0.16) else ""
        print(f"   {etyk:<14}{len(grp):>5}{roi:>8.1%}{traf / len(grp):>10.0%}"
              f"{dekl:>12.0%}{uwaga}")


def okno_zgody(log: dict) -> None:
    from footstats.jobs import rozliczanie as R

    print("=" * 74)
    print("1. OKNO ZGODY +16 pp — czy pasmo 12–16 nie leci na łeb")
    print("=" * 74)

    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and R._z_modelu(r)              # drabinki mają własne progi
        and r.get("kurs") and float(r["kurs"]) > 1.0
        and r.get("p_model")
        and R._z_biezacej_epoki(r)      # mundial to archiwum, nie nauczyciel
        and not R._z_martwej_epoki(r)
    ]
    print(f"Rozliczonych typów modelu w bieżącej epoce: {len(settled)}")

    _tabela_pasm(settled, "CAŁA KSIĘGA (odniesienie do pomiaru z 04.08):")

    po_rozl = [r for r in settled
               if (r.get("rozliczono_ts") or 0) >= WDROZENIE_OKNO]
    _tabela_pasm(po_rozl, "ROZLICZONE PO ZMIANIE (typy w większości sprzed niej):")

    po_pub = [r for r in settled
              if (r.get("opublikowano_ts") or 0) >= WDROZENIE_OKNO]
    _tabela_pasm(po_pub, "OPUBLIKOWANE PO ZMIANIE (jedyne rozstrzygające cięcie):")

    # ile jeszcze wisi nierozliczone w spornym paśmie — skala ekspozycji
    from footstats.model import betting
    wiszace = [
        r for r in log.values()
        if not r.get("wynik") and r.get("kurs") and r.get("p_model")
        and not r.get("sugestia") and not r.get("odrzucony")
        and not r.get("poza_publikacja")
        and 0.12 <= float(r["p_model"]) - betting.implied_prob_one_sided(
            float(r["kurs"])) < 0.16
    ]
    print(f"\nW paśmie 12–16 pp wisi teraz nierozliczonych: {len(wiszace)}")
    if wiszace:
        naj = min(int(r.get("kickoff_ts") or 0) for r in wiszace)
        print("   najbliższy gwizdek: "
              f"{time.strftime('%d.%m %H:%M', time.localtime(naj))}")


def kara_horyzontu(kupony_log: dict, wygrane: dict) -> None:
    print("\n" + "=" * 74)
    print("2. KARA HORYZONTU — czy kupony na kilka dni przestały pudłować")
    print("=" * 74)

    # SELEKCJA PRZEŻYWALNOŚCI — PUŁAPKA, W KTÓRĄ WPADŁEM PRZY PISANIU TEGO
    # SKRYPTU (05.08). `kupony_log` jest przycinany po 21 dniach od rozliczenia,
    # a `kupony_wygrane` trzyma wygrane NA ZAWSZE. Doklejenie wygranych do logu
    # „żeby nie zaniżyć próby" tworzy zbiór, z którego przegrane wyparowują,
    # a wygrane zostają: to samo cięcie dawało 16 trafień na 34 z samego logu
    # i 24 na 42 po doklejeniu. Wygranych używamy WYŁĄCZNIE do pytania
    # „czy kiedykolwiek jakiś wszedł", nigdy do liczenia odsetka.
    rozliczone = [
        r for r in kupony_log.values()
        if not r.get("pominiety")
        and r.get("wynik") in ("wygrany", "przegrany", "zwrot")
    ]
    wygrane_kiedykolwiek = len(set(wygrane or {}) - set(kupony_log))
    print(f"Rozliczonych kuponów w logu: {len(rozliczone)}"
          f"   (+{wygrane_kiedykolwiek} wygranych już wypadło z okna 21 dni)")
    if rozliczone:
        wieki = sorted(
            (int(time.time()) - int(r.get("rozliczono_ts") or 0)) / 86400
            for r in rozliczone
        )
        print(f"Wiek rozliczeń: {wieki[0]:.1f}–{wieki[-1]:.1f} dnia — próba "
              "ROTUJE, więc pomiaru sprzed tygodnia nie da się odtworzyć.")

    def _dlugi(r: dict) -> bool:
        """Kupon jest długi, gdy NAJDALSZY leg jest dalej niż doba.

        Po najbliższym liczyć nie wolno: builder kotwiczy kupon na meczach
        dzisiejszych i dokłada dalekie legi, żeby dobić do kursu docelowego —
        więc po `min` każdy kupon wychodzi „na dziś", łącznie z takim, który
        ma nogę za 92 godziny. O tym, kiedy kupon się rozstrzygnie i gdzie
        siedzi ryzyko horyzontu, decyduje `max`.
        """
        legi = r.get("legi") or []
        if not legi:
            return False
        pub = int(r.get("opublikowano_ts") or 0)
        return max(int(l.get("kickoff_ts") or 0) for l in legi) - pub > DOBA_S

    print(f"\n{'grupa':<34}{'n':>4}{'wygrane':>9}{'ROI':>9}")
    for nazwa, sel in (
        ("na dziś (< 24 h)", lambda r: not _dlugi(r)),
        ("na kilka dni (> 24 h)", _dlugi),
    ):
        for etap, warunek in (
            ("wszystkie", lambda r: True),
            ("opublikowane PO karze", lambda r: int(
                r.get("opublikowano_ts") or 0) >= WDROZENIE_HORYZONT),
        ):
            grp = [r for r in rozliczone if sel(r) and warunek(r)]
            if not grp:
                print(f"{nazwa + ' / ' + etap:<34}{0:>4}{'—':>9}{'—':>9}")
                continue
            wyg = sum(1 for r in grp if r["wynik"] == "wygrany")
            roi = sum(
                float(r.get("kurs_rozliczony") or r.get("kurs_laczny") or 0) - 1.0
                if r["wynik"] == "wygrany"
                else (0.0 if r["wynik"] == "zwrot" else -1.0)
                for r in grp
            ) / len(grp)
            print(f"{nazwa + ' / ' + etap:<34}{len(grp):>4}{wyg:>9}{roi:>8.0%}")

    # LEGI — próba jest tu kilka razy większa niż na kuponach i to ona
    # pokazała lukę 04.08 (deklaracja vs wejścia).
    #
    # HORYZONT LICZONY PER LEG, nie z kuponu. Kupon bywa mieszany (jeden mecz
    # dziś, drugi za trzy dni), więc klasyfikacja całego kuponu wrzuciłaby te
    # legi do jednego worka i zatarła dokładnie tę różnicę, którą mierzymy.
    print(f"\n{'legi wg horyzontu (per leg)':<34}{'n':>5}{'deklarował':>12}"
          f"{'weszło':>9}{'luka':>9}")
    for nazwa, sel_leg in (
        ("na dziś", lambda pub, ko: ko - pub <= DOBA_S),
        ("na kilka dni", lambda pub, ko: ko - pub > DOBA_S),
    ):
        for etap, warunek in (
            ("wszystkie", lambda r: True),
            ("PO karze", lambda r: int(
                r.get("opublikowano_ts") or 0) >= WDROZENIE_HORYZONT),
        ):
            legi = [
                l for r in rozliczone if warunek(r)
                for l in (r.get("legi") or [])
                if l.get("wynik") in ("wygrany", "przegrany") and l.get("p_model")
                and sel_leg(int(r.get("opublikowano_ts") or 0),
                            int(l.get("kickoff_ts") or 0))
            ]
            if not legi:
                print(f"{nazwa + ' / ' + etap:<34}{0:>5}{'—':>12}{'—':>9}{'—':>9}")
                continue
            for typ, sel_typ in (
                ("drużynowe", lambda l: str(l.get("rynek_kod") or "").startswith(
                    ("team_", "match_", "wiecej_"))),
                ("zawodnicze", lambda l: not str(
                    l.get("rynek_kod") or "").startswith(
                        ("team_", "match_", "wiecej_"))),
            ):
                grp = [l for l in legi if sel_typ(l)]
                if not grp:
                    continue
                dekl = sum(float(l["p_model"]) for l in grp) / len(grp)
                weszlo = sum(
                    1 for l in grp if l["wynik"] == "wygrany") / len(grp)
                etyk = f"{nazwa} / {typ} / {etap}"
                print(f"{etyk:<34}{len(grp):>5}{dekl:>12.1%}"
                      f"{weszlo:>9.1%}{(weszlo - dekl) * 100:>+8.1f} pp")

    # co dziś WISI — kara ma zmieniać deklarację, więc to widać od razu,
    # bez czekania na rozliczenia
    wiszace = [
        r for r in kupony_log.values()
        if not r.get("wynik") and not r.get("pominiety") and r.get("legi")
    ]
    print(f"\nKupony nierozliczone: {len(wiszace)}")
    for r in sorted(wiszace, key=lambda r: -(r.get("opublikowano_ts") or 0))[:12]:
        pub = int(r.get("opublikowano_ts") or 0)
        po = "PO karze  " if pub >= WDROZENIE_HORYZONT else "przed karą"
        legi = r.get("legi") or []
        godz = sorted((int(l.get("kickoff_ts") or 0) - pub) / 3600 for l in legi)
        print(f"   {po}  {str(r.get('slot') or '')[:26]:<26}"
              f"kurs {float(r.get('kurs_laczny') or 0):>6.2f}"
              f"   szansa {float(r.get('p_model') or 0):>5.1%}"
              f"   legi od +{godz[0]:.0f} h do +{godz[-1]:.0f} h")


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    from footstats import supa
    from footstats.jobs import rozliczanie as R

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — pomiar potrzebuje księgi z chmury.")
        return

    log_raw, ok = supa.get_key_ok("typy_log")
    if not ok:
        print("Nie udało się odczytać typy_log — przerywam.")
        return
    log = R._migruj_log(log_raw or {})
    okno_zgody(log)

    kupony_log, ok_k = supa.get_key_ok("kupony_log")
    if not ok_k:
        print("\nNie udało się odczytać kupony_log — druga część pominięta.")
        return
    kara_horyzontu(kupony_log or {}, supa.get_key("kupony_wygrane") or {})


if __name__ == "__main__":
    main()
