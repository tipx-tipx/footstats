# -*- coding: utf-8 -*-
"""OKNO KOREKTY STRUMIENIA: LICZYĆ TYPY CZY MECZE — walidacja czasowa.

Powód (kontrola startowa 2026-08-14). Okno 120 ostatnich rozliczeń drużynowych
było tego dnia CZTEREMA meczami z jednej nocy, z czego jeden dawał 33% okna.
Wynik w obrębie meczu jest silnie zgodny — rożne albo padają, albo nie, dla
wszystkich typów naraz — więc warstwa ściągająca szansę KAŻDEGO publikowanego
typu stała wtedy na jednym wieczorze ([[okno-uczenia-to-kilka-meczow]]).

Cztery warianty tego samego okna, liczone WYŁĄCZNIE z przeszłości i oceniane
na następnych rozliczeniach:

  A  ostatnie 120 typów, każdy typ waży 1        <- dziś na produkcji
  B  ostatnie 120 typów, każdy MECZ waży 1
  C  ostatnie 40 meczów, każdy typ waży 1
  D  ostatnie 40 meczów, każdy MECZ waży 1

Kryterium: Brier i log-loss out-of-sample (czy korekta faktycznie poprawia
prognozę) plus średni skok delty między kolejnymi przeliczeniami — warstwa,
która skacze, przenosi szum wprost na karty.

⚑ NIE ZAKŁADAĆ, ŻE WAŻENIE MECZEM WYGRA. Publikujemy TYPY, nie mecze, więc
kalibracja po typach może być właściwym celem i wystarczy poszerzyć okno.
Od tego, co wygra, zależy zmiana w `rozliczanie.korekta_strumienia` — i tylko
od tego.

    cd pipeline
    PYTHONUTF8=1 python scripts/pomiar_okna_uczenia.py

CZYTA TYLKO — nie zapisuje nic.
"""

from __future__ import annotations

import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PL = timezone(timedelta(hours=2))

# co ile rozliczeń przesuwamy punkt walidacji i ile następnych oceniamy
KROK, TEST, START = 20, 40, 200
OKNO_MECZE = 40


def _staty(grp: list[dict]) -> tuple:
    n = max(len(grp), 1)
    dekl = sum(float(r["p_model"]) for r in grp) / n
    traf = sum(1 for r in grp if r["wynik"] == "wygrany") / n
    return len(grp), dekl, traf


def okno_typy(hist: list[dict], R) -> list[dict]:
    return hist[-R.KOREKTA_STRUMIENIA_OKNO:]


def okno_mecze(hist: list[dict], _R, n_meczy: int = OKNO_MECZE) -> list[dict]:
    """Ostatnie N MECZÓW, ze wszystkimi ich typami."""
    widziane: list = []
    out: list[dict] = []
    for r in reversed(hist):
        m = r.get("mecz_id")
        if m not in widziane:
            if len(widziane) >= n_meczy:
                break
            widziane.append(m)
        out.append(r)
    return list(reversed(out))


def wagi_po_meczach(grp: list[dict]) -> list[float]:
    """Każdy mecz waży 1, jego typy dzielą tę wagę między siebie."""
    ile = Counter(r.get("mecz_id") for r in grp)
    return [1.0 / ile[r.get("mecz_id")] for r in grp]


WARIANTY = {
    "A dziś: 120 typów, typ=1": (okno_typy, False),
    "B 120 typów, mecz=1": (okno_typy, True),
    f"C {OKNO_MECZE} meczów, typ=1": (okno_mecze, False),
    f"D {OKNO_MECZE} meczów, mecz=1": (okno_mecze, True),
}


def delta(hist: list[dict], wybierz, wazyc: bool, R):
    """Korekta policzona dokładnie tak jak w produkcji: surowe `p`, orientacja
    „powyżej", tłumienie do średniej już nałożonej delty i cap."""
    grp = wybierz(hist, R)
    if len(grp) < R.KOREKTA_STRUMIENIA_MIN_N:
        return None, 0, 0
    sur = R.w_orientacji_over([{**r, "p_model": R._p_surowe(r)} for r in grp])
    b = R._bias_logit(sur, wagi_po_meczach(grp) if wazyc else None)
    juz = [R._delta_zapisana(r) for r in grp]
    sr = sum(juz) / len(juz)
    b = sr + R.KOREKTA_STRUMIENIA_TLUMIENIE * (b - sr)
    b = max(R.KOREKTA_STRUMIENIA_CAP[0], min(R.KOREKTA_STRUMIENIA_CAP[1], b))
    return b, len(grp), len({r.get("mecz_id") for r in grp})


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


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
    log = R._migruj_log(supa.get_key("typy_log") or {})
    if not log:
        print("Supabase nie oddał księgi — spróbuj później.")
        return
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and r.get("p_model")
        and not R._z_martwej_epoki(r) and R._z_biezacej_epoki(r)
        and (R._z_modelu(r) or r.get("zrodlo") == R.ZRODLO_DRABINKA)
    ]
    druzyny = sorted((r for r in settled if R._strumien(r) == "druzyny"),
                     key=lambda r: r.get("kickoff_ts") or 0)
    print(f"Rozliczeń drużynowych: {len(druzyny)}, "
          f"meczów: {len({r.get('mecz_id') for r in druzyny})}")
    if len(druzyny) < START + TEST:
        print(f"Za mało historii na walidację (trzeba {START + TEST}).")
        return

    wyniki = defaultdict(lambda: {"brier": [], "ll": [], "delty": [],
                                  "n": [], "mecze": []})
    baza = {"brier": [], "ll": []}
    punkty = 0
    for i in range(START, len(druzyny) - TEST, KROK):
        hist, test = druzyny[:i], druzyny[i:i + TEST]
        sur_test = R.w_orientacji_over(
            [{**r, "p_model": R._p_surowe(r)} for r in test])
        punkty += 1
        for r in sur_test:
            p = min(max(float(r["p_model"]), 1e-6), 1 - 1e-6)
            y = 1.0 if r["wynik"] == "wygrany" else 0.0
            baza["brier"].append((p - y) ** 2)
            baza["ll"].append(-(y * math.log(p) + (1 - y) * math.log(1 - p)))
        for nazwa, (wybierz, wazyc) in WARIANTY.items():
            b, n, mecze = delta(hist, wybierz, wazyc, R)
            if b is None:
                continue
            w = wyniki[nazwa]
            w["delty"].append(b)
            w["n"].append(n)
            w["mecze"].append(mecze)
            for r in sur_test:
                p0 = min(max(float(r["p_model"]), 1e-6), 1 - 1e-6)
                p = min(max(_sig(R._logit(p0) + b), 1e-6), 1 - 1e-6)
                y = 1.0 if r["wynik"] == "wygrany" else 0.0
                w["brier"].append((p - y) ** 2)
                w["ll"].append(
                    -(y * math.log(p) + (1 - y) * math.log(1 - p)))

    print(f"\nWALIDACJA CZASOWA — {punkty} punktów, każdy oceniany na "
          f"{TEST} następnych rozliczeniach\n")
    b0 = sum(baza["brier"]) / max(len(baza["brier"]), 1)
    l0 = sum(baza["ll"]) / max(len(baza["ll"]), 1)
    print(f"{'wariant':<28}{'Brier':>9}{'vs bez':>9}{'log-loss':>10}"
          f"{'skok delty':>12}{'typów':>8}{'meczów':>8}")
    print(f"{'BEZ KOREKTY':<28}{b0:>9.4f}{'—':>9}{l0:>10.4f}"
          f"{'—':>12}{'—':>8}{'—':>8}")
    for nazwa in WARIANTY:
        w = wyniki[nazwa]
        if not w["brier"]:
            print(f"{nazwa:<28} — za mało danych")
            continue
        br = sum(w["brier"]) / len(w["brier"])
        ll = sum(w["ll"]) / len(w["ll"])
        skoki = [abs(w["delty"][j] - w["delty"][j - 1])
                 for j in range(1, len(w["delty"]))]
        print(f"{nazwa:<28}{br:>9.4f}{(br - b0) / b0 * 100:>8.1f}%{ll:>10.4f}"
              f"{sum(skoki) / max(len(skoki), 1):>12.3f}"
              f"{median(w['n']):>8.0f}{median(w['mecze']):>8.0f}")

    print("\nCO KTÓRY WARIANT MÓWI DZIŚ:")
    for nazwa, (wybierz, wazyc) in WARIANTY.items():
        b, n, mecze = delta(druzyny, wybierz, wazyc, R)
        if b is None:
            print(f"   {nazwa:<28} poniżej progu próby")
            continue
        grp = wybierz(druzyny, R)
        dni = {datetime.fromtimestamp(r.get("kickoff_ts") or 0, PL).date()
               for r in grp}
        najw = Counter(r.get("mecz_id") for r in grp).most_common(1)[0][1]
        print(f"   {nazwa:<28} delta {b:+.3f}   {n} typów / {mecze} meczów / "
              f"{len(dni)} dni, największy mecz {najw / max(n, 1):.0%} okna")


if __name__ == "__main__":
    main()
