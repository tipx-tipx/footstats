# -*- coding: utf-8 -*-
"""BUDOWA MAPY TOŻSAMOŚCI FotMob → Sofascore (etap 3, docs/plan-fotmob.md).

Job ręczny (workflow `fm_tozsamosc.yml`), bez wpływu na produkcję: nic
w cyklu jeszcze nie czyta `fm_tozsamosc`. Mapa tylko rośnie, więc job można
puszczać kilka razy – drugi przebieg nie pyta o mecze już przetworzone.

Kroki
-----
1. Odczyt: mapa (`fm_tozsamosc`), magazyn drużyn `hd_0..9`, `trend_lib`,
   księga i zakres meczów (nazwy drużyn). Każda awaria odczytu = koniec bez
   zapisu – mapa ze stałymi decyzjami nie może się zbudować na pustce.
2. Terminarze FotMob z `--dni` dni do `--do` (1 zapytanie na dzień) →
   drużyny po terminarzu i rywalach + zapas po nazwie → mecze, rozgrywki.
3. Szczegóły zakończonych meczów (do `--mecze`, najpierw najnowsze i te
   z drużynami z `trend_lib`) → zawodnicy po nazwisku i po grze Sofascore
   z tego samego meczu. Mecze trafiają też do bazy meczów (`fm_baza_*`) –
   każdy mecz pobieramy RAZ.
4. Zapis mapy i raport pokrycia (bramka etapu 3: ≥ 95% zawodników, którzy
   wg Sofascore grali w zmapowanym meczu).

⚑ Okno kończy się na 29.10: wtedy statshub przestał odpowiadać, więc po tej
dacie nie ma już meczów Sofascore do porównania.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from .. import baza_meczow, supa
from .. import tozsamosc as T
from ..sources import fotmob

KLUCZE_HD = [f"hd_{i}" for i in range(10)]


def _czytaj(klucz: str):
    dane, ok = supa.get_key_ok(klucz)
    if not ok:
        raise RuntimeError(f"odczyt '{klucz}' padł")
    return dane


def _pokrycie(t: T.Tozsamosc, rekordy: list[dict], zaw: dict, kad: dict) -> Counter:
    """Zawodnicy, którzy wg Sofascore grali w zmapowanym meczu: ilu ma parę
    w tym meczu (także przez drugi numer tej samej osoby – dubel statshub)."""
    s: Counter = Counter()
    odwr = {v: k for k, v in t.zawodnicy.items() if v}
    for r in rekordy:
        druz = {t.druzyny.get(r["home"]["id"]), t.druzyny.get(r["away"]["id"])} - {None}
        w_meczu = {t.zawodnicy.get(z["pid"]) for z in r["zawodnicy"]} - {None, 0}
        for d in druz:
            for pid in kad.get(d, ()):
                if not T._gra_w_meczu(zaw[pid], r["ts"]):
                    continue
                s["aktywni"] += 1
                if pid in w_meczu:
                    s["zmapowani"] += 1
                elif any(p2 in odwr and T.podobienstwo_nazwisk(zaw[p2]["name"], zaw[pid]["name"]) >= 0.9
                         for p2 in w_meczu if p2 != pid):
                    s["zmapowani"] += 1
                    s["przez_dubel"] += 1
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--do", default="2026-10-29", help="ostatni dzień okna (RRRR-MM-DD)")
    ap.add_argument("--dni", type=int, default=45, help="ile dni terminarza")
    ap.add_argument("--mecze", type=int, default=480, help="limit szczegółów meczów w przebiegu")
    ap.add_argument("--dni-szczegolow", type=int, default=7, help="szczegóły z ostatnich N dni okna")
    a = ap.parse_args(argv)
    t0 = time.time()
    do = date.fromisoformat(a.do)

    t, ok = T.wczytaj()
    if not ok:
        print("Tożsamość: odczyt mapy padł – koniec bez zapisu")
        return 1
    print(f"Tożsamość: mapa na starcie – drużyny {len(t.druzyny)}, zawodnicy {len(t.zawodnicy)}, "
          f"mecze przetworzone {len(t.przetworzone)}")
    try:
        hd = {}
        for k in KLUCZE_HD:
            hd.update(_czytaj(k) or {})
        trend_lib = _czytaj("trend_lib") or {}
        ksiega = _czytaj("typy_log") or {}
        zakres = _czytaj("zakres_meczow") or []
    except RuntimeError as e:
        print(f"Tożsamość: {e} – koniec bez zapisu")
        return 1
    eventy = T.eventy_z_magazynu(hd)
    zaw = T.zawodnicy_z_trend_lib(trend_lib)
    kad = T.kadry(zaw)
    idx = T.indeks_nazw(zaw)
    nazwy_sh = T.nazwy_druzyn_sh(trend_lib, ksiega, zakres, eventy)
    del trend_lib, ksiega
    print(f"Tożsamość: mecze Sofascore {len(eventy)}, zawodnicy trend_lib {len(zaw)}, "
          f"nazwy drużyn Sofascore {len(nazwy_sh)}")

    # --- 2. terminarze i drużyny ---------------------------------------------
    mecze_fm: list[dict] = []
    odmowa = None
    for i in range(a.dni - 1, -1, -1):
        d = do - timedelta(days=i)
        try:
            mecze_fm += fotmob.mecze_dnia(d.strftime("%Y%m%d"))
        except (fotmob.FotmobOdmowa, fotmob.FotmobLimit) as e:
            odmowa = str(e)
            break
        except Exception as e:     # pojedynczy dzień bez odpowiedzi – reszta okna zostaje
            print(f"Tożsamość: terminarz {d} – błąd {type(e).__name__}: {e}")
    if odmowa:
        print(f"Tożsamość: FotMob odmówił przy terminarzu ({odmowa}) – koniec bez zapisu")
        return 1
    mecze_fm = list({m["id"]: m for m in mecze_fm}.values())
    w = T.mapuj_druzyny(mecze_fm, eventy)
    po_nazwie = T.dopasuj_druzyny_po_nazwie(mecze_fm, eventy, nazwy_sh, w["druzyny"])
    nowe_d = t.dodaj_druzyny(w) + t.dodaj_druzyny({"druzyny": po_nazwie})
    print(f"Tożsamość: terminarz {a.dni} dni – mecze FotMob {len(mecze_fm)}; {w['raport']}; "
          f"po nazwie {len(po_nazwie)}; nowe drużyny w mapie {nowe_d}")
    druz_tl = Counter(z["team"] for z in zaw.values())
    zm = set(t.druzyny.values())
    print(f"Tożsamość: drużyny trend_lib {len(druz_tl)} – z parą "
          f"{sum(1 for d in druz_tl if d in zm)} ({sum(n for d, n in druz_tl.items() if d in zm) / max(1, sum(druz_tl.values())):.1%} zawodników)")

    # --- 3. zawodnicy z meczów ---------------------------------------------
    granica = int(datetime.combine(do - timedelta(days=a.dni_szczegolow - 1), datetime.min.time(),
                                   tzinfo=timezone.utc).timestamp())
    kand = [m for m in mecze_fm if m["status"] == "finished" and m["start_ts"] >= granica
            and m["id"] not in t.przetworzone
            and (t.druzyny.get(m["home_id"]) or t.druzyny.get(m["away_id"]))]
    kand.sort(key=lambda m: (bool(kad.get(t.druzyny.get(m["home_id"])) or kad.get(t.druzyny.get(m["away_id"]))),
                             m["start_ts"]), reverse=True)
    budzet = max(0, min(a.mecze, fotmob.LIMIT_ZAPYTAN - fotmob.statystyki()["zapytania"] - 5))
    rekordy, licz, bledy = [], Counter(), Counter()
    for m in kand[:budzet]:
        try:
            r = fotmob.mecz_do_bazy(fotmob.szczegoly_meczu(m["id"]))
        except (fotmob.FotmobOdmowa, fotmob.FotmobLimit) as e:
            odmowa = str(e)
            break
        except Exception as e:
            bledy[type(e).__name__] += 1
            continue
        rekordy.append(r)
        licz.update(t.dodaj_mecz(r, zaw, kad, idx))
    print(f"Tożsamość: szczegóły {len(rekordy)} z {len(kand)} kandydatów (limit {budzet}); "
          f"zawodnicy {dict(licz)}; błędy {dict(bledy)}")
    if odmowa:
        print(f"Tożsamość: FotMob odmówił przy szczegółach ({odmowa}) – zapisuję to, co zebrane")
    s = _pokrycie(t, rekordy, zaw, kad)
    if s["aktywni"]:
        print(f"Tożsamość: BRAMKA – grali wg Sofascore w zmapowanym meczu {s['aktywni']}, z parą "
              f"{s['zmapowani']} = {s['zmapowani'] / s['aktywni']:.2%} (przez dubel {s['przez_dubel']}); "
              f"niejednoznaczni {len(t.niejednoznaczne)}, kolizje numerów FotMob {len(t.kolizje)}")

    # --- baza meczów: każdy mecz pobrany raz ---------------------------------
    if rekordy:
        miesiace = sorted({baza_meczow.klucz_miesiaca(r["ts"]) for r in rekordy})
        baza, nieprzecz = baza_meczow.wczytaj(miesiace)
        zmienione = baza_meczow.dopisz(baza, rekordy)
        wynik = baza_meczow.zapisz(baza, zmienione, nieprzecz)
        print(f"Tożsamość: baza meczów – zapis {wynik}, nieprzeczytane {nieprzecz}")

    # --- 4. zapis mapy ---------------------------------------------------------
    zapisano = T.zapisz(t)
    st = fotmob.statystyki()
    print(f"Tożsamość: zapis mapy {'OK' if zapisano else 'PADŁ'} – drużyny {len(t.druzyny)}, "
          f"zawodnicy {sum(1 for v in t.zawodnicy.values() if v)}, mecze {len(t.mecze)}, "
          f"rozgrywki {len(t.rozgrywki)}; FotMob zapytania {st['zapytania']}, odmowa {st['odmowa']}; "
          f"{time.time() - t0:.0f} s")
    return 0 if zapisano and not odmowa else 1


if __name__ == "__main__":
    sys.exit(main())
