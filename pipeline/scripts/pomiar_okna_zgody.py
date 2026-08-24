# -*- coding: utf-8 -*-
"""OKNO ZGODY Z RYNKIEM — obie granice mierzone TRAFNOŚCIĄ, nie luką.

Pytanie z 2026-08-24: po zdjęciu bram wartości (a220da8) brama
`rozjazd_z_rynkiem` została największym wąskim gardłem produktu — 4 odrzucenia
na cykl przed zmianą, 158 po niej. Czy zdejmuje materiał gorszy, czy tylko inny?

⚑ CZTERY WCZEŚNIEJSZE POMIARY TEJ BRAMY (komentarz przy `OKNO_ZGODY_MAX`) SZŁY
PO LUCE I ROI. Cel produktu zmienił się 20.08 na TRAFNOŚĆ, a w tym produkcie te
miary idą w przeciwne strony — więc próg uzasadniony luką nie jest jeszcze
uzasadniony dzisiejszym celem. Skrypt liczy jedno i drugie obok siebie, żeby
różnicę było widać, a nie trzeba jej pamiętać.

TRZY PUŁAPKI, KTÓRE TEN SKRYPT OMIJA ŚWIADOMIE:

  1. SKŁAD CEN. Materiał spod dolnej granicy ma 35,3% typów poniżej kursu 1,45
     wobec 23,8% w oknie. Surowe porównanie trafności mierzy więc cennik, nie
     jakość typu — dlatego różnica jest ważona składem pasm kursu.
  2. LIMITY PÓŁEK. O produkcie decyduje LISTA DNIA, nie cały materiał: półka
     pewniaków bierze 15 typów posortowanych PO SZANSIE, a typy z dużym
     rozjazdem mają szansę zawyżoną — czyli po dopuszczeniu wchodzą NA GÓRĘ
     listy i wypychają uczciwsze. Surowa różnica tego nie widzi, symulacja tak.
  3. NIESPAROWANE PORÓWNANIE. Lista „przed" i „po" mają dużą część wspólną,
     więc dwie średnie mylą co do siły efektu. Liczy się, kto WSZEDŁ i kto
     WYPADŁ — oraz jak te dwie grupy trafiły.

    cd pipeline
    PYTHONUTF8=1 python scripts/pomiar_okna_zgody.py

CZYTA TYLKO — nie zapisuje nic.
"""

from __future__ import annotations

import datetime as _dt
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Poniżej tylu rozliczeń wycinek nie jest wynikiem, tylko ciekawostką.
MIN_N = 25
# Pasma kursu do ważenia — te same, którymi produkt myśli o cenie.
PASMA_KURSU = [(1.19, 1.45), (1.45, 1.80), (1.80, 2.20), (2.20, 3.00), (3.00, 6.01)]
# Limity różnorodności listy dnia (build_wc_fast.LISTA_PER_*). Trzymane tu
# kopią, bo import całego joba ściąga pipeline razem ze źródłami sieciowymi.
LISTA_PER_MECZ, LISTA_PER_RYNEK, LISTA_PER_PASMO = 3, 4, 4
LISTA_PER_RODZINA, LISTA_PER_ZAWODNIKA = 4, 1


def _p_decyzji(r: dict) -> float | None:
    """Liczba, która REALNIE decydowała o typie.

    ⚑ `p_model` w księdze to STARY rachunek — model uczony trzyma swój
    w `p_uczony`. Pomiar po `p_model` opisałby maszynerię, której już nie
    używamy; raz już tak się stało (23.08, pomiar czynników).
    """
    pu = r.get("p_uczony")
    if isinstance(pu, dict):
        for k in ("p", "p_model", "p_over_final"):
            v = pu.get(k)
            if isinstance(v, (int, float)) and 0 < float(v) < 1:
                return float(v)
    return float(r["p_model"]) if r.get("p_model") else None


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    from footstats import supa
    from footstats.jobs import rozliczanie as R
    from footstats.model import betting, uczony

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — pomiar potrzebuje księgi z chmury.")
        return

    log = R._migruj_log(supa.get_key("typy_log") or {})
    wszystko = [
        r for r in log.values()
        if not r.get("sugestia") and not r.get("odrzucony") and r.get("kickoff_ts")
        and R._z_biezacej_epoki(r) and not R._z_martwej_epoki(r)
    ]
    settled = [r for r in wszystko
               if r.get("wynik") in ("wygrany", "przegrany")
               and r.get("p_model") and r.get("kurs")]
    print(f"Rozliczeń w bieżącej epoce: {len(settled)}")
    if len(settled) < MIN_N:
        return

    def rozjazd(r: dict) -> float | None:
        try:
            k = float(r.get("kurs") or 0)
        except (TypeError, ValueError):
            return None
        p = _p_decyzji(r)
        if k <= 1.0 or p is None:
            return None
        return p - betting.implied_prob_one_sided(k)

    def traf(g):
        return sum(1 for r in g if r["wynik"] == "wygrany") / len(g) if g else 0.0

    def dekl(g):
        return sum(_p_decyzji(r) for r in g) / len(g) if g else 0.0

    def pasmo(lo, hi, zbior=None):
        return [r for r in (settled if zbior is None else zbior)
                if (x := rozjazd(r)) is not None and lo <= x < hi]

    okno = pasmo(betting.OKNO_ZGODY_MIN, betting.OKNO_ZGODY_MAX)

    def wazona(grupa, odniesienie=None, minn=10):
        """Różnica trafności wobec okna, WAŻONA składem cen `grupa`.

        Bez tego ważenia porównanie mierzy cennik, nie jakość — pułapka 1.
        """
        odn = okno if odniesienie is None else odniesienie
        licznik = mianownik = 0.0
        uzyte = 0
        for lo, hi in PASMA_KURSU:
            a = [r for r in grupa if lo <= float(r["kurs"]) < hi]
            b = [r for r in odn if lo <= float(r["kurs"]) < hi]
            if len(a) < minn or len(b) < minn:
                continue
            licznik += len(a) * (traf(a) - traf(b))
            mianownik += len(a)
            uzyte += 1
        return (licznik * 100 / mianownik if mianownik else None), int(mianownik), uzyte

    # ------------------------------------------------------------------ 1
    print("\n" + "=" * 88)
    print("1. OBIE GRANICE — TRAFNOŚĆ obok LUKI, ta sama próba")
    print("=" * 88)
    print(f"{'pasmo rozjazdu':<20}{'n':>6}{'trafia':>9}{'dekl':>8}{'luka pp':>10}"
          f"{'traf. vs okno':>16}")
    for nazwa, lo, hi in [
        ("poniżej ceny", -2.0, betting.OKNO_ZGODY_MIN),
        ("okno (odniesienie)", betting.OKNO_ZGODY_MIN, betting.OKNO_ZGODY_MAX),
        ("16-20 pp", 0.16, 0.20),
        ("20-26 pp", 0.20, 0.26),
        ("26 pp i dalej", 0.26, 3.0),
    ]:
        g = pasmo(lo, hi)
        if len(g) < MIN_N:
            print(f"{nazwa:<20}{len(g):>6}   za mała próba")
            continue
        d, _n, _u = wazona(g)
        ds = f"{d:>+8.1f} pp" if d is not None else "       –"
        print(f"{nazwa:<20}{len(g):>6}{traf(g):>9.1%}{dekl(g):>8.1%}"
              f"{(traf(g) - dekl(g)) * 100:>+10.1f}{ds:>16}")

    # ------------------------------------------------------------------ 2
    print("\n" + "=" * 88)
    print("2. STABILNOŚĆ — tercje próby; próg bez znaku w tercjach nie ma pokrycia")
    print("=" * 88)
    ws = sorted(settled, key=lambda r: float(r["kickoff_ts"]))
    t = len(ws) // 3
    for nazwa, lo, hi in [("poniżej ceny", -2.0, betting.OKNO_ZGODY_MIN),
                          ("16-22 pp", betting.OKNO_ZGODY_MAX, 0.22)]:
        print(f"   {nazwa}:")
        for i, cz in enumerate([ws[:t], ws[t:2 * t], ws[2 * t:]], 1):
            g = pasmo(lo, hi, cz)
            o = pasmo(betting.OKNO_ZGODY_MIN, betting.OKNO_ZGODY_MAX, cz)
            d, n, _u = wazona(g, o)
            okres = (f"{R.dzien_pl(cz[0]['kickoff_ts'])}"
                     f"..{R.dzien_pl(cz[-1]['kickoff_ts'])}")
            luka = ((traf(g) - dekl(g)) - (traf(o) - dekl(o))) * 100 if g and o else 0.0
            wynik = (f"trafność {d:>+6.1f} pp (n={n})" if d is not None
                     else "za mała próba          ")
            print(f"      tercja {i} {okres:<24}{wynik}   |  luka {luka:>+6.1f} pp")

    # ------------------------------------------------------------------ 3
    print("\n" + "=" * 88)
    print("3. SYMULACJA LISTY DNIA — o produkcie decyduje półka, nie cały materiał")
    print("=" * 88)

    def doba(r):
        d = _dt.datetime.fromtimestamp(int(r["kickoff_ts"]), _dt.timezone.utc)
        d = d.astimezone(R.STREFA) if R.STREFA else d
        if d.hour < 6:                       # doba PRODUKTOWA 6:00 -> 6:00
            d -= _dt.timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    def rodzina(kod):
        k = str(kod or "")
        for x in ("cards", "corners", "goals", "shots", "sot", "fouls", "tackles"):
            if x in k:
                return x
        return k

    def pasmo_kursu(kurs):
        k = float(kurs or 0)
        for lo, hi, n in [(0, 1.45, "a"), (1.45, 1.8, "b"), (1.8, 2.2, "c"),
                          (2.2, 3.0, "d"), (3.0, 99, "e")]:
            if lo <= k < hi:
                return n
        return "?"

    def klucz(r):
        return (r.get("mecz_id"), r.get("podmiot_id"), r.get("rynek_kod"),
                r.get("strona"), r.get("linia"))

    # Kandydaci: to, co przeszło, plus to, co zdjęła WYŁĄCZNIE ta brama.
    # Pozostałe bramy zostają — symulujemy zmianę JEDNEJ granicy.
    kandydaci = [r for r in settled if (r.get("poza_publikacja") or "") in
                 {"", "poza_lista_dnia", "dzien_zamkniety", "za_pozno",
                  "rozjazd_z_rynkiem"}]

    def zbuduj(okno_min, okno_max):
        wybrane, wg_doby = {}, defaultdict(list)
        for r in kandydaci:
            x = rozjazd(r)
            if x is None or not (okno_min <= x < okno_max):
                continue
            if uczony.polka_dla(r.get("kurs"), r.get("podmiot_typ")) is None:
                continue
            wg_doby[doba(r)].append(r)
        cap = sum(int(p["limit_dobowy"]) for p in uczony.POLKI.values())
        for _dzien, grp in wg_doby.items():
            z_p = Counter(); z_m = Counter(); z_r = Counter()
            z_pa = Counter(); z_ro = Counter(); z_z = Counter(); n_dnia = 0
            # półki mają RÓŻNE klucze sortowania — patrz `_klucz_listy`
            for polka, kl in (
                ("wysoka_szansa", lambda r: _p_decyzji(r)),
                ("wyzsze_kursy", lambda r: _p_decyzji(r) * math.sqrt(float(r["kurs"]))),
            ):
                na_polce = [
                    x for x in grp
                    if uczony.polka_dla(x.get("kurs"), x.get("podmiot_typ")) == polka
                ]
                for r in sorted(na_polce, key=kl, reverse=True):
                    mecz = r.get("mecz_id")
                    rynek = (r.get("rynek_kod"), r.get("strona"))
                    pas = pasmo_kursu(r["kurs"])
                    rodz = rodzina(r.get("rynek_kod"))
                    zaw = (str(r.get("podmiot") or "")
                           if r.get("podmiot_typ") == "zawodnik" else None)
                    if (z_p[polka] >= uczony.POLKI[polka]["limit_dobowy"]
                            or n_dnia >= cap
                            or z_m[mecz] >= LISTA_PER_MECZ
                            or z_r[rynek] >= LISTA_PER_RYNEK
                            or z_pa[pas] >= LISTA_PER_PASMO
                            or z_ro[rodz] >= LISTA_PER_RODZINA
                            or (zaw is not None and z_z[zaw] >= LISTA_PER_ZAWODNIKA)):
                        continue
                    z_p[polka] += 1; n_dnia += 1; z_m[mecz] += 1; z_r[rynek] += 1
                    z_pa[pas] += 1; z_ro[rodz] += 1
                    if zaw is not None:
                        z_z[zaw] += 1
                    wybrane[klucz(r)] = r
        return wybrane

    def sparowany(a, b, nazwa):
        """Kto WSZEDŁ, kto WYPADŁ — dwie średnie mylą co do siły efektu."""
        weszly = [v for k, v in b.items() if k not in a]
        wypadly = [v for k, v in a.items() if k not in b]
        if len(weszly) < MIN_N or len(wypadly) < MIN_N:
            print(f"   {nazwa:<32} bez zmian albo za mała próba "
                  f"(weszły {len(weszly)}, wypadły {len(wypadly)})")
            return
        d = (traf(weszly) - traf(wypadly)) * 100
        se = math.sqrt(traf(weszly) * (1 - traf(weszly)) / len(weszly)
                       + traf(wypadly) * (1 - traf(wypadly)) / len(wypadly)) * 100
        print(f"   {nazwa:<32} weszły {len(weszly):>4} {traf(weszly):>6.1%}"
              f" | wypadły {len(wypadly):>4} {traf(wypadly):>6.1%}"
              f" | różnica {d:>+5.1f} pp +-{se:.1f}")

    dzis = zbuduj(betting.OKNO_ZGODY_MIN, betting.OKNO_ZGODY_MAX)
    for pol in ("wysoka_szansa", "wyzsze_kursy"):
        g = [r for r in dzis.values()
             if uczony.polka_dla(r.get("kurs"), r.get("podmiot_typ")) == pol]
        if g:
            print(f"   dziś {pol:<16} n={len(g):>4}  trafia {traf(g):>6.1%}"
                  f"  deklaruje {dekl(g):>6.1%}")
    print()
    sparowany(dzis, zbuduj(betting.OKNO_ZGODY_MIN, 0.22), "górna granica 16 -> 22 pp")
    sparowany(dzis, zbuduj(betting.OKNO_ZGODY_MIN, 3.0), "górna granica ZDJĘTA")
    sparowany(dzis, zbuduj(-2.0, betting.OKNO_ZGODY_MAX), "dolna granica ZDJĘTA")

    # ------------------------------------------------------------------ 4
    print("\n" + "=" * 88)
    print("4. CZY LIMIT PÓŁKI WIĄŻE — bez tego symulacja nie testuje wypychania")
    print("=" * 88)
    wg = defaultdict(list)
    for r in kandydaci:
        x = rozjazd(r)
        if (x is not None and betting.OKNO_ZGODY_MIN <= x < betting.OKNO_ZGODY_MAX
                and uczony.polka_dla(r.get("kurs"),
                                     r.get("podmiot_typ")) == "wysoka_szansa"):
            wg[doba(r)].append(r)
    limit = uczony.POLKI["wysoka_szansa"]["limit_dobowy"]
    ile = sorted(len(g) for g in wg.values())
    wiaze = sum(1 for g in wg.values() if len(g) >= limit)
    if ile:
        print(f"   dób w próbie: {len(ile)}, limit wiąże w {wiaze}")
        print(f"   kandydatów na dobę: mediana {ile[len(ile) // 2]}, "
              f"maks {ile[-1]}, przy limicie {limit}")
    print("\n   ⚑ Pokrycie rozliczeń — pasmo świeże ma go mniej i to nie jest wada")
    print("     danych, tylko wiek próby; różnicę trzeba znać PRZED wnioskiem:")
    for nazwa, lo, hi in [("poniżej ceny", -2.0, betting.OKNO_ZGODY_MIN),
                          ("okno", betting.OKNO_ZGODY_MIN, betting.OKNO_ZGODY_MAX),
                          ("16-22 pp", betting.OKNO_ZGODY_MAX, 0.22)]:
        g = [r for r in wszystko if (x := rozjazd(r)) is not None and lo <= x < hi]
        roz = [r for r in g if r.get("wynik") in ("wygrany", "przegrany")]
        if g:
            print(f"     {nazwa:<16}{len(roz):>6} z {len(g):<6} {len(roz) / len(g):>7.1%}")


if __name__ == "__main__":
    main()
