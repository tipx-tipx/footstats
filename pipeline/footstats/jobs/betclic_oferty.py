# -*- coding: utf-8 -*-
"""Pobieranie oferty Betclica JAKO OSOBNE ZADANIE (2026-08-08, decyzja usera).

PO CO ODDZIELNY JOB. Główny cykl ma twardy limit 35 minut i robi w nim
wszystko: dane, typy, kupony, rozliczenia. Betclic dostawał z tego ~3 minuty
i zdążał pobrać 3 mecze z 60 — a że pamięć oferty wygasa po dobie, wpisy
przepadały szybciej, niż je dobieraliśmy. Pełne pokrycie było nieosiągalne.

Zmierzone koszty, które o tym zdecydowały:
    oferta meczu z propsami   ~71 s   (bogaty Estoril poszedł w 4 s)
    oferta meczu bez propsów  30-40 s i tak zwraca zero
    kalendarz() do parowania  ~150 s

Ten job robi TYLKO jedno i ma na to własny czas: pobiera oferty i odkłada je
pod `betclic_oferty` w Supabase. Cykl główny czyta gotowe, kosztem zera sekund
(patrz build_wc_fast.bc_z_pamieci). Gdy job padnie, cykl pracuje na ostatnim
zapisie albo bez Betclica — dokładnie jak przed tą zmianą.

Zakres bierzemy z klucza `matches`, czyli z tego, co cykl i tak zapisał: dzięki
temu nie powtarzamy tu jego logiki (rozgrywki, parowanie, okna czasu), a job
z definicji patrzy na te same mecze co produkt.

    PYTHONUTF8=1 python -m footstats.jobs.betclic_oferty
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv

from .. import supa
from ..sources import betclic
from .build_wc_fast import (
    BETCLIC_KLUCZ, MAX_MECZOW_W_PAMIECI_BC, OKNO_ODSWIEZENIA_BC_S,
    SWIEZOSC_BETCLIC_S, bc_rotuj_pamiec, bc_z_pamieci,
)

# Ile czasu wolno zużyć na pobieranie. Job chodzi osobno, więc limit jest jego
# własny — 20 minut przy ~71 s na mecz daje ~17 meczów na przebieg, czyli pełne
# pokrycie 60 meczów po trzech–czterech uruchomieniach.
BUDZET_S = float(os.getenv("BETCLIC_BUDZET_S", "1200"))
# Jak daleko w przód pobieramy. Dalsze mecze i tak nie mają jeszcze pełnej
# oferty, a zajęłyby miejsce najbliższym.
HORYZONT_S = 4 * 86400


def _mecze_w_zakresie(matches, teraz: int) -> dict[int, int]:
    """{mecz_id: kickoff} — mecze przed gwizdkiem, w których Superbet kwotuje
    zawodników.

    Ten sam filtr co w cyklu i z tego samego powodu: rozkład jest
    zerojedynkowy (zmierzone 08.08 — 70 ze 140 meczów ma 0 propsów, reszta od
    razu 20+), a mecz bez propsów kosztuje 30-40 s i zwraca zero.
    """
    lista = matches if isinstance(matches, list) else list((matches or {}).values())
    out: dict[int, int] = {}
    for m in lista:
        try:
            mid = int(m.get("id"))
            kick = int(m.get("kickoff_ts") or 0)
        except (TypeError, ValueError):
            continue
        if not mid or kick <= teraz or kick - teraz > HORYZONT_S:
            continue
        if (m.get("propsy_superbet") or 0) <= 0:
            continue
        out[mid] = kick
    return out


def main() -> int:
    load_dotenv(".env")
    teraz = int(time.time())
    matches = supa.get_key("matches")
    if not matches:
        print("Betclic: klucz `matches` pusty — cykl jeszcze nie zapisał zakresu")
        return 0
    kolejnosc = _mecze_w_zakresie(matches, teraz)
    if not kolejnosc:
        print("Betclic: brak meczów w zakresie (przed gwizdkiem, z propsami)")
        return 0

    pamiec_raw, odczyt_ok = supa.get_key_ok(BETCLIC_KLUCZ)
    if not odczyt_ok:
        # padnięty odczyt to NIE jest pusta pamięć — zapis z tak zbudowanego
        # stanu skasowałby dorobek poprzednich przebiegów
        print("Betclic: odczyt pamięci padł — kończę bez zapisu")
        return 1
    pamiec = dict(pamiec_raw or {})
    mamy = bc_z_pamieci(kolejnosc, pamiec, teraz,
                        SWIEZOSC_BETCLIC_S, OKNO_ODSWIEZENIA_BC_S)
    do_pobrania = sorted(
        ((mid, ts) for mid, ts in kolejnosc.items() if mid not in mamy),
        key=lambda kv: kv[1],
    )
    print(f"Betclic: {len(kolejnosc)} meczów w zakresie, {len(mamy)} już w pamięci, "
          f"{len(do_pobrania)} do pobrania (budżet {BUDZET_S:.0f} s)")
    if not do_pobrania:
        return 0

    nasze = []
    for mid, ts in do_pobrania:
        rec = next(
            (m for m in (matches if isinstance(matches, list)
                         else list(matches.values()))
             if str(m.get("id")) == str(mid)),
            None,
        )
        if not rec or not rec.get("gospodarz") or not rec.get("gosc"):
            continue
        nasze.append({"klucz": mid, "home": rec["gospodarz"],
                      "away": rec["gosc"], "kickoff_ts": ts})
    if not nasze:
        print("Betclic: żadnego meczu nie da się sparować (brak nazw drużyn)")
        return 0

    start = time.time()
    try:
        pary, luka = betclic.paruj_mecze(nasze)
    except (RuntimeError, OSError, ValueError) as e:
        print(f"Betclic: parowanie meczów padło ({e})")
        return 1
    print(f"Betclic: sparowano {len(pary)}/{len(nasze)} meczów "
          f"({time.time() - start:.0f} s na kalendarz)")

    pobrane = puste = bledy = 0
    for mid, ts in do_pobrania:
        bc = pary.get(mid)
        if not bc:
            continue
        if time.time() - start > BUDZET_S:
            print(f"Betclic: budżet czasu wyczerpany — pobrano {pobrane}, "
                  "reszta przy następnym uruchomieniu")
            break
        try:
            paczka = betclic.kursy_zawodnikow(int(bc["id"]))
        except Exception as e:
            # ⚑ SZEROKO, i to jest przemyślane (2026-08-08). Wąska lista
            # wyjątków przepuściła `AttributeError` z jednego zakładu i zabiła
            # CAŁY przebieg — razem z dwiema minutami parowania i szesnastoma
            # meczami, które czekały w kolejce. Jeden mecz nie ma prawa tyle
            # kosztować. Cisza się przy tym nie robi: liczymy błędy i piszemy
            # typ wyjątku, bo bez niego „mecz X — coś" jest bezużyteczne
            # ([[ciche-odrzucenia-zasada]]).
            bledy += 1
            print(f"Betclic: mecz {bc.get('nazwa') or mid} pominięty — "
                  f"{type(e).__name__}: {e}")
            continue
        gracze = paczka.get("players") or {}
        if not gracze:
            # pustego wyniku NIE zapamiętujemy: zamroziłby mecz na dobę, a
            # Betclic bywa po prostu spóźniony z ofertą
            puste += 1
            continue
        pamiec[str(mid)] = {"ts": int(time.time()), "players": gracze}
        pobrane += 1

    pamiec = bc_rotuj_pamiec(pamiec, kolejnosc, teraz, MAX_MECZOW_W_PAMIECI_BC)
    rynki = {
        mk
        for wpis in pamiec.values()
        for d in (wpis.get("players") or {}).values()
        for mk in d
    }
    print(f"Betclic: pobrane {pobrane}, bez oferty {puste}, błędy {bledy}; "
          f"w pamięci {len(pamiec)} meczów, rynków {len(rynki)}")
    if pobrane and not supa.put_key_bezpiecznie(BETCLIC_KLUCZ, pamiec):
        print("UWAGA: zapis oferty Betclica NIE POWIÓDŁ SIĘ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
