# -*- coding: utf-8 -*-
"""DOPISYWANIE BAZY MECZÓW FotMob (etap 4a, docs/plan-fotmob.md).

Raz na dobę (workflow `fm_baza.yml`) i ręcznie z `--od` do nadrobienia:
zakończone mecze z NASZEGO zakresu – drużyna z mapą tożsamości albo
rozgrywki z mapą (nowa drużyna w znanej lidze też wchodzi) – pobrane RAZ
i zapisane w `fm_baza_RRRRMM`. Ten sam przebieg mapuje nowych zawodników
(`Tozsamosc.dodaj_mecz(..., zamknij_brak=True)`): po 29.10 Sofascore nie ma
już gier do porównania, więc zostaje nazwisko w kadrze (99,28% w bramce
etapu 3), a zawodnik bez pary dostaje stały numer zastępczy.

Mecz zapisany bez statystyk zawodników (FotMob dopisuje je czasem po kilku
godzinach) jest pobierany jeszcze raz – tylko w oknie `DNI_DOPELNIENIA` od
startu i tylko z ligi, która w bazie MA mecze ze statystykami. W próbie
31.10 114 ze 185 meczów zakresu (niższe ligi) nie miało ich wcale – tam
brak to brak źródła, nie opóźnienie, i ponowne pytanie to czysty ruch.

Nic w cyklu jeszcze tego nie czyta – job nie dotyka strony ani księgi.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from .. import baza_meczow
from .. import tozsamosc as T
from ..sources import fotmob
from .fm_tozsamosc import _czytaj

DNI_DOPELNIENIA = 2


def _miesiace(od: date, do: date) -> list[str]:
    out, d = [], od.replace(day=1)
    while d <= do:
        out.append(baza_meczow.KLUCZ_WZOR.format(d.strftime("%Y%m")))
        d = (d + timedelta(days=32)).replace(day=1)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--od", default=None, help="pierwszy dzień (RRRR-MM-DD); domyślnie dziś − dni")
    ap.add_argument("--dni", type=int, default=3, help="ile dni wstecz, gdy brak --od")
    ap.add_argument("--mecze", type=int, default=560, help="limit szczegółów meczów w przebiegu")
    a = ap.parse_args(argv)
    t0 = time.time()
    dzis = datetime.now(timezone.utc).date()
    od = date.fromisoformat(a.od) if a.od else dzis - timedelta(days=a.dni)

    t, ok = T.wczytaj()
    if not ok or not t.druzyny:
        print(f"Baza FotMob: mapa tożsamości {'pusta' if ok else 'nieczytelna'} – koniec bez zapisu")
        return 1
    miesiace = _miesiace(od, dzis)
    baza, nieprzecz = baza_meczow.wczytaj(miesiace)
    if nieprzecz:
        print(f"Baza FotMob: odczyt {nieprzecz} padł – koniec bez zapisu")
        return 1
    try:
        trend_lib = _czytaj("trend_lib") or {}
    except RuntimeError as e:
        print(f"Baza FotMob: {e} – koniec bez zapisu")
        return 1
    zaw = T.zawodnicy_z_trend_lib(trend_lib)
    del trend_lib
    kad, idx = T.kadry(zaw), T.indeks_nazw(zaw)
    print(f"Baza FotMob: okno {od} – {dzis}, w bazie {len(baza)} meczów z {miesiace}")

    mecze_fm, odmowa = [], None
    d = od
    while d <= dzis:
        try:
            mecze_fm += fotmob.mecze_dnia(d.strftime("%Y%m%d"))
        except (fotmob.FotmobOdmowa, fotmob.FotmobLimit) as e:
            odmowa = str(e)
            break
        except Exception as e:
            print(f"Baza FotMob: terminarz {d} – błąd {type(e).__name__}: {e}")
        d += timedelta(days=1)
    if odmowa:
        print(f"Baza FotMob: FotMob odmówił przy terminarzu ({odmowa}) – koniec bez zapisu")
        return 1
    mecze_fm = list({m["id"]: m for m in mecze_fm}.values())

    teraz = int(time.time())
    ligi_ze_statami = {z.get("liga_id") for z in baza.values() if z.get("staty_zawodnikow")}
    zakres = Counter()
    kand = []
    for m in mecze_fm:
        if m["status"] != "finished":
            continue
        w_zakresie = (m["home_id"] in t.druzyny or m["away_id"] in t.druzyny
                      or m.get("liga_id") in t.rozgrywki or m.get("liga_grupa") in t.rozgrywki)
        zakres["w_zakresie" if w_zakresie else "poza_zakresem"] += 1
        if not w_zakresie:
            continue
        stary = baza.get(m["id"])
        if stary is None:
            kand.append(m)
        elif (not stary.get("staty_zawodnikow") and stary.get("liga_id") in ligi_ze_statami
              and teraz - m["start_ts"] < DNI_DOPELNIENIA * 86400):
            kand.append(m)
            zakres["dopelnienie"] += 1
    kand.sort(key=lambda m: m["start_ts"])
    budzet = max(0, min(a.mecze, fotmob.LIMIT_ZAPYTAN - fotmob.statystyki()["zapytania"] - 5))
    rekordy, licz, bledy, jakosc = [], Counter(), Counter(), Counter()
    for m in kand[:budzet]:
        try:
            r = fotmob.mecz_do_bazy(fotmob.szczegoly_meczu(m["id"]))
        except (fotmob.FotmobOdmowa, fotmob.FotmobLimit) as e:
            odmowa = str(e)
            break
        except Exception as e:
            bledy[type(e).__name__] += 1
            continue
        if r.get("status") != "finished":
            jakosc["nie_zakonczony_w_szczegolach"] += 1
            continue
        rekordy.append(r)
        jakosc["staty_zawodnikow" if r.get("staty_zawodnikow") else "bez_staty_zawodnikow"] += 1
        jakosc["mapa_strzalow" if r.get("mapa_strzalow") else "bez_mapy_strzalow"] += 1
        licz.update(t.dodaj_mecz(r, zaw, kad, idx, zamknij_brak=True))
    print(f"Baza FotMob: terminarz {len(mecze_fm)} meczów, zakończone {dict(zakres)}; "
          f"pobrane {len(rekordy)} z {len(kand)} (limit {budzet}); jakość {dict(jakosc)}; błędy {dict(bledy)}")
    print(f"Baza FotMob: zawodnicy {dict(licz)}; w mapie z parą "
          f"{sum(1 for v in t.zawodnicy.values() if v)}, zastępczych {sum(1 for v in t.zawodnicy.values() if not v)}, "
          f"kolizje numerów {len(t.kolizje)}")
    if len(kand) > budzet:
        print(f"Baza FotMob: zostało {len(kand) - budzet} meczów – nadrobi następny przebieg")
    if odmowa:
        print(f"Baza FotMob: FotMob odmówił przy szczegółach ({odmowa}) – zapisuję to, co zebrane")

    wynik = {}
    if rekordy:
        zmienione = baza_meczow.dopisz(baza, rekordy)
        wynik = baza_meczow.zapisz(baza, zmienione, nieprzecz)
    zapis_mapy = T.zapisz(t)
    st = fotmob.statystyki()
    print(f"Baza FotMob: zapis bazy {wynik}, mapy {'OK' if zapis_mapy else 'PADŁ'}; w bazie {len(baza)} meczów; "
          f"FotMob zapytania {st['zapytania']}, odmowa {st['odmowa']}; {time.time() - t0:.0f} s")
    return 0 if zapis_mapy and all(wynik.values()) and not odmowa else 1


if __name__ == "__main__":
    sys.exit(main())
