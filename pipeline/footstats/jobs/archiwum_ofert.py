"""ARCHIWUM OFERTY ZAWODNICZEJ (2026-10-06, właściciel: „drabinki da się
trafiać, tylko trzeba poprawnie znajdować takie typy — dużo nam umyka").

Po co
-----
Żeby sprawdzić, które szczeble (np. pierwszy szczebel po 2,00–3,25) wchodzą,
a my ich nie bierzemy, potrzebna jest PEŁNA oferta z przeszłości: wszystkie
linie wszystkich zawodników z ceną u obu bukmacherów — nie tylko to, co
pipeline wybrał do oceny (księga). Do dziś nikt jej nie zapisywał: magazyn
trzyma `RETENCJA` ostatnich wersji każdego klucza, czyli kilka godzin.

Co zapisujemy
-------------
Ostatni zrzut przed gwizdkiem, per mecz, z siatki `kursy_dwa` cyklu
(`lekkie_klucze.siatka_dwoch_kursow` — linie „powyżej", [Superbet, Betclic]
i trzeci element 1 = „Betclic liczy inaczej"):

    {mecz_id: {"k": kickoff_ts, "z": ts zrzutu, "p": ts pierwszego zrzutu,
               "s": czy skład ogłoszony w chwili zrzutu,
               "o": {zawodnik_id: {rynek: {linia: [sb, bc(, 1)]}}}}}

Wyniki dokłada analiza z banku trendów (`trend_lib`), więc tu ich nie ma.

Zasady
------
* Mecz po gwizdku jest ZAMROŻONY — późniejszy cykl go nie nadpisuje.
* Jeden klucz na MIESIĄC meczu (`archiwum_ofert_RRRR_MM`), żeby plik nie
  rósł bez końca. Cykl na przełomie miesiąca dotyka dwóch.
* Nieudany odczyt = NIE ZAPISUJEMY (pusty odczyt z awarii nadpisałby
  historię — ta sama zasada co przy księdze).
* Zapis tylko, gdy coś się zmieniło.
"""
from __future__ import annotations

import time

from .. import magazyn_repo

PRZEDROSTEK = "archiwum_ofert_"


def _sekundy(ts) -> int | None:
    """Znacznik w sekundach — część źródeł podaje milisekundy (epoka ms)."""
    try:
        t = int(ts)
    except (TypeError, ValueError):
        return None
    return t // 1000 if t > 10**11 else t


def klucz_miesiaca(kickoff_ts: int | float) -> str:
    return PRZEDROSTEK + time.strftime("%Y_%m", time.gmtime(_sekundy(kickoff_ts)))


def scal(archiwum: dict, kursy_dwa: dict, mecze: dict, teraz: int,
         klucz: str | None = None) -> int:
    """Dopisuje do `archiwum` (w miejscu) zrzuty meczów, które jeszcze się nie
    zaczęły. Zwraca liczbę zmienionych meczów. `klucz` ogranicza scalanie do
    meczów danego miesiąca (None = wszystkie)."""
    zmienione = 0
    for mid, oferta in (kursy_dwa or {}).items():
        mecz = (mecze or {}).get(mid) or (mecze or {}).get(int(mid)) \
            or (mecze or {}).get(str(mid)) or {}
        ko = _sekundy(mecz.get("kickoff_ts"))
        if not ko or not oferta:
            continue
        if ko <= int(teraz):
            continue                      # po gwizdku: zamrożony
        if klucz is not None and klucz_miesiaca(ko) != klucz:
            continue
        o = {str(pid): {str(mk): {str(l): list(p) for l, p in (linie or {}).items()}
                        for mk, linie in (rynki or {}).items()}
             for pid, rynki in oferta.items()}
        stary = archiwum.get(str(mid))
        nowy = {"k": ko, "z": int(teraz),
                "p": int((stary or {}).get("p") or teraz),
                "s": bool(mecz.get("sklady_ogloszone")), "o": o}
        if stary and stary.get("o") == o and stary.get("s") == nowy["s"] \
                and stary.get("k") == ko:
            continue                      # nic nowego — nie ruszamy
        archiwum[str(mid)] = nowy
        zmienione += 1
    return zmienione


def zapisz_zrzut(kursy_dwa: dict, mecze: dict, teraz: int | None = None) -> str:
    """Odczytaj–scal–zapisz dla każdego miesiąca, którego dotyczy oferta.
    Zwraca zdanie do logu. Nie rzuca wyjątków na zewnątrz w ścieżce awarii
    magazynu — tylko mówi, co się stało."""
    teraz = int(teraz or time.time())
    klucze = set()
    for mid in (kursy_dwa or {}):
        mecz = (mecze or {}).get(mid) or (mecze or {}).get(str(mid)) or {}
        ko = _sekundy(mecz.get("kickoff_ts"))
        if ko and ko > teraz:
            klucze.add(klucz_miesiaca(ko))
    if not klucze:
        return "Archiwum ofert: brak nadchodzących meczów z ofertą zawodniczą"
    opisy = []
    for klucz in sorted(klucze):
        archiwum, ok = magazyn_repo.pobierz(klucz)
        if not ok:
            opisy.append(f"{klucz}: ODCZYT PADŁ — nie zapisuję (historia zostaje)")
            continue
        archiwum = archiwum if isinstance(archiwum, dict) else {}
        n = scal(archiwum, kursy_dwa, mecze, teraz, klucz=klucz)
        if not n:
            opisy.append(f"{klucz}: bez zmian ({len(archiwum)} meczów)")
            continue
        if magazyn_repo.zapisz(klucz, archiwum):
            opisy.append(f"{klucz}: +{n} zrzutów meczów, razem {len(archiwum)}")
        else:
            opisy.append(f"{klucz}: ZAPIS PADŁ ({n} zrzutów do powtórki w następnym cyklu)")
    return "Archiwum ofert: " + "; ".join(opisy)
