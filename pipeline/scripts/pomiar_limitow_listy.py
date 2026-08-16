# -*- coding: utf-8 -*-
"""CZY TYPY WCHODZĄCE PONAD LIMIT TRAFIAJĄ GORZEJ OD TYCH W LIMICIE.

Pytanie właściciela (2026-08-16), po tym jak kontrola startowa pokazała, że
limity różnorodności nie trzymają: doba zbudowana w całości pod limitami ma
**8 typów z jednego rynku przy limicie 4**, a doba domknięta — 24.

Mechanizm jest znany ([[limity-roznorodnosci-nie-trzymaja]]): `z_dnia`,
`z_rynku` i `z_meczu` zerują się w każdym cyklu, a typ raz pokazany wraca
bezwarunkowo, więc każde chwilowe zniknięcie typu z przeliczenia trwale
poszerza listę. Naprawa (liczyć limit wobec rejestru publikacji) zmniejszy
widoczną podaż typów — więc **najpierw trzeba wiedzieć, czy nadmiar w ogóle
szkodzi**. Ta sama kolejność co przy oknie zgody: pomiar przed progiem.

## Jak odtwarzamy „ponad limit" wstecz

Księga nie zapisuje, którym z kolei typ wszedł. Ale limit działa w kolejności
wejścia, więc gdyby liczył się SKUMULOWANE na dobę, weszłoby pierwszych N
chronologicznie. Rangę liczymy więc po `opublikowano_ts` w obrębie:

* doby produktowej (6:00 → 6:00)  -> ranga wobec LISTA_CAP (12)
* doby i rynku|strony             -> ranga wobec LISTA_PER_RYNEK (4)
* doby i meczu                    -> ranga wobec LISTA_PER_MECZ (3)

⚑ To jest REKONSTRUKCJA, nie zapis. Mówi, co by odpadło przy limicie
skumulowanym — i tylko o to pytamy.

⚑ Liczymy WYŁĄCZNIE typy, które user widział (bez `odrzucony`,
`poza_publikacja` i bez tych, które wypadły z zamrożonego składu dnia), bo
pytanie brzmi „czy nadmiar na LIŚCIE szkodzi", a nie „czy model umie liczyć".

Uruchomienie:

    cd pipeline
    PYTHONUTF8=1 python scripts/pomiar_limitow_listy.py

CZYTA TYLKO — nie zapisuje nic.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# data wdrożenia zamrożonej listy dnia — dopiero od niej „lista" znaczy to
# samo co dziś (przedtem skład zmieniał się w ciągu dnia)
OD_LISTY_DNIA = "2026-08-12"


def _staty(grp: list[dict]) -> tuple[int, float, float, float, float, float]:
    """n, deklaracja, trafienia, luka, ROI i WŁASNY SZUM wycinka."""
    if not grp:
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0
    n = len(grp)
    dekl = sum(float(r["p_model"]) for r in grp) / n
    traf = sum(1 for r in grp if r["wynik"] == "wygrany") / n
    roi = sum((float(r["kurs"]) - 1.0) if r["wynik"] == "wygrany" else -1.0
              for r in grp if r.get("kurs")) / n
    szum = (traf * (1.0 - traf) / n) ** 0.5
    return n, dekl, traf, traf - dekl, roi, szum


def _werdykt(w_limicie: list[dict], ponad: list[dict]) -> str:
    """Czy różnica przewyższa własny szum obu grup (ta sama zasada co alarm)."""
    if len(w_limicie) < 25 or len(ponad) < 25:
        return "za mała próba"
    _, _, _, _, roi_a, szum_a = _staty(w_limicie)
    _, _, _, _, roi_b, szum_b = _staty(ponad)
    roznica = (roi_b - roi_a) * 100
    szum_r = ((szum_a ** 2 + szum_b ** 2) ** 0.5) * 100
    if roznica < -2 * szum_r:
        return "⚑ NADMIAR SZKODZI"
    if roznica > 2 * szum_r:
        return "⚑ nadmiar wypada LEPIEJ"
    return "w szumie"


def _tabela(nazwa: str, limit: int, grupy: dict[str, list[dict]]) -> None:
    print(f"\n{nazwa}  (limit w kodzie: {limit})")
    print(f"   {'grupa':<22}{'n':>6}{'deklaruje':>11}{'trafia':>9}"
          f"{'luka':>8}{'ROI':>9}{'szum':>8}")
    for etykieta in ("w limicie", "ponad limit"):
        n, dekl, traf, luka, roi, szum = _staty(grupy[etykieta])
        if not n:
            print(f"   {etykieta:<22}{0:>6}   — brak typów")
            continue
        print(f"   {etykieta:<22}{n:>6}{dekl:>10.1%}{traf:>9.1%}"
              f"{luka*100:>+7.1f}{roi:>9.1%}{szum*100:>7.1f}")
    print(f"   WERDYKT: {_werdykt(grupy['w limicie'], grupy['ponad limit'])}")


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    from footstats import supa
    from footstats.jobs import build_wc_fast as B
    from footstats.jobs import rozliczanie as R

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — pomiar potrzebuje księgi z chmury.")
        return
    # padnięty odczyt nie może wyglądać jak pusta księga
    surowy, odczyt_ok = supa.get_key_ok("typy_log")
    if not odczyt_ok:
        print("NIE UDAŁO SIĘ ODCZYTAĆ KSIĘGI — pomiar PRZERWANY.\n"
              "Zera we wszystkich tabelach byłyby fałszywe.")
        return
    log = R._migruj_log(surowy or {})
    lista_dnia = R.wczytaj_liste_dnia()

    widziane = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and r.get("rynek_kod") not in R.RYNKI_OSOBNE
        and not r.get("odrzucony") and not r.get("poza_publikacja")
        and not r.get("sugestia")
        and r.get("p_model") and r.get("kurs") and r.get("opublikowano_ts")
        and R._z_modelu(r)
        and R._z_biezacej_epoki(r) and not R._z_martwej_epoki(r)
        and not R.poza_zamrozona_lista(r, lista_dnia)
    ]
    print(f"Księga: {len(log)} wpisów; typów z LISTY, rozliczonych: "
          f"{len(widziane)}")
    if len(widziane) < 60:
        print("Za mało rozliczeń na jakikolwiek wniosek — przerywam.")
        return

    for etykieta_okresu, zbior in (
        ("CAŁA BIEŻĄCA EPOKA", widziane),
        (f"OD ZAMROŻONEJ LISTY DNIA ({OD_LISTY_DNIA})",
         [r for r in widziane
          if R._doba_produktowa(r.get("kickoff_ts")) >= OD_LISTY_DNIA]),
    ):
        print("\n" + "=" * 78)
        print(f"{etykieta_okresu}  —  {len(zbior)} rozliczeń")
        print("=" * 78)
        if len(zbior) < 60:
            print("   za mało rozliczeń w tym okresie")
            continue

        # rangi liczone w kolejności PUBLIKACJI, osobno w każdym koszyku
        for nazwa, limit, klucz in (
            ("LIMIT DZIENNY", B.LISTA_CAP,
             lambda r: (R._doba_produktowa(r.get("kickoff_ts")),)),
            ("LIMIT NA RYNEK|STRONĘ", B.LISTA_PER_RYNEK,
             lambda r: (R._doba_produktowa(r.get("kickoff_ts")),
                        r.get("rynek_kod"), r.get("strona"))),
            ("LIMIT NA MECZ", B.LISTA_PER_MECZ,
             lambda r: (R._doba_produktowa(r.get("kickoff_ts")),
                        r.get("mecz_id"))),
        ):
            koszyki: dict[tuple, list[dict]] = defaultdict(list)
            for r in zbior:
                koszyki[klucz(r)].append(r)
            grupy: dict[str, list[dict]] = {"w limicie": [], "ponad limit": []}
            for _k, grp in koszyki.items():
                grp.sort(key=lambda r: r.get("opublikowano_ts") or 0)
                for i, r in enumerate(grp):
                    grupy["w limicie" if i < limit else "ponad limit"].append(r)
            _tabela(nazwa, limit, grupy)

    # --- ile materiału w ogóle wchodzi ponad limit (skala sprawy)
    print("\n" + "=" * 78)
    print("SKALA: ILE TYPÓW NA LIŚCIE WCHODZI PONAD LIMIT")
    print("=" * 78)
    per_doba: dict[str, list[dict]] = defaultdict(list)
    for r in widziane:
        per_doba[R._doba_produktowa(r.get("kickoff_ts"))].append(r)
    print(f"   {'doba':<13}{'typów':>7}{'ponad 12':>10}{'ponad 4/rynek':>15}")
    for d in sorted(per_doba)[-8:]:
        grp = sorted(per_doba[d], key=lambda r: r.get("opublikowano_ts") or 0)
        ponad_dzien = max(0, len(grp) - B.LISTA_CAP)
        per_rynek: dict[tuple, int] = defaultdict(int)
        ponad_rynek = 0
        for r in grp:
            k = (r.get("rynek_kod"), r.get("strona"))
            per_rynek[k] += 1
            if per_rynek[k] > B.LISTA_PER_RYNEK:
                ponad_rynek += 1
        print(f"   {d:<13}{len(grp):>7}{ponad_dzien:>10}{ponad_rynek:>15}")

    # --- KONTROLA SEGMENTU: czy to nie mówi o RYNKU zamiast o limicie
    #
    # „Ponad limit na rynek" z definicji zbiera typy z rynków, które danego
    # dnia mają ICH DUŻO — a to są dziś dwa rynki (`team_corners|powyzej`,
    # `team_goals|ponizej`), które same z siebie tracą. Bez tego porównania
    # liczba wyżej mogłaby opisywać segment, nie limit. Ta sama poprawka co
    # w części 5 audytu (2026-08-13).
    print("\n" + "=" * 78)
    print("TO SAMO W OBRĘBIE SEGMENTU (ten sam rynek|strona)")
    print("=" * 78)
    for nazwa, limit, klucz in (
        ("LIMIT NA RYNEK|STRONĘ", B.LISTA_PER_RYNEK,
         lambda r: (R._doba_produktowa(r.get("kickoff_ts")),
                    r.get("rynek_kod"), r.get("strona"))),
        ("LIMIT NA MECZ", B.LISTA_PER_MECZ,
         lambda r: (R._doba_produktowa(r.get("kickoff_ts")),
                    r.get("mecz_id"))),
    ):
        koszyki: dict[tuple, list[dict]] = defaultdict(list)
        for r in widziane:
            koszyki[klucz(r)].append(r)
        # etykieta w limicie / ponad, ale porównujemy WEWNĄTRZ rynku|strony
        w_seg: dict[str, dict[str, list[dict]]] = defaultdict(
            lambda: {"w limicie": [], "ponad limit": []})
        for _k, grp in koszyki.items():
            grp.sort(key=lambda r: r.get("opublikowano_ts") or 0)
            for i, r in enumerate(grp):
                seg = f'{r.get("rynek_kod")}|{r.get("strona")}'
                w_seg[seg]["w limicie" if i < limit else "ponad limit"].append(r)
        print(f"\n{nazwa}")
        print(f"   {'segment':<26}{'w lim.':>8}{'ROI':>8}"
              f"{'ponad':>8}{'ROI':>8}{'różnica':>10}")
        wazone, waga = 0.0, 0
        for seg in sorted(w_seg, key=lambda s: -len(w_seg[s]["ponad limit"])):
            a, b = w_seg[seg]["w limicie"], w_seg[seg]["ponad limit"]
            if len(a) < 15 or len(b) < 15:
                continue
            _, _, _, _, roi_a, _ = _staty(a)
            _, _, _, _, roi_b, _ = _staty(b)
            print(f"   {seg:<26}{len(a):>8}{roi_a:>8.1%}"
                  f"{len(b):>8}{roi_b:>8.1%}{(roi_b-roi_a)*100:>+9.1f} pp")
            wazone += (roi_b - roi_a) * len(b)
            waga += len(b)
        if waga:
            print(f"   ŚREDNIO W OBRĘBIE SEGMENTU: {wazone/waga*100:>+.1f} pp "
                  f"(na {waga} typach ponad limitem)")
        else:
            print("   brak segmentu z próbą po obu stronach")

    print("\n   Jak to czytać: 'ponad limit' to typy, które NIE weszłyby na")
    print("   listę, gdyby limity liczyły się skumulowanie na dobę. Werdykt")
    print("   'w szumie' znaczy, że nadmiar nie szkodzi WYNIKOWI — sprawa")
    print("   pozostaje wtedy produktowa (różnorodność), nie finansowa.")


if __name__ == "__main__":
    main()
