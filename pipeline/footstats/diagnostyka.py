"""Licznik CICHYCH BŁĘDÓW — jedno miejsce, w którym widać, co przepadło.

PO CO TO POWSTAŁO (2026-08-04). Przegląd całego backendu policzył **79 miejsc**,
w których wyjątek jest łapany i zamieniany na `pass` / `continue` / `return []`
— bez jednej linii logu. Rozkład: `build_wc_fast` 13, `scores365` 13,
`statshub` 8, `sofa_worker` 7, `betclic` 4, reszta rozsypana.

Każde takie miejsce to potencjalny cichy ubytek danych. Nie jest to teoria:
WSZYSTKIE cztery błędy znalezione 03–04.08 miały ten sam podpis — kartki
gubione u obu bukmacherów, historia ucięta do 10 meczów, mecze znikające
z terminarza, sumy meczowe omijające bramy. Każdy z nich znaleźliśmy
przypadkiem, bo nic o nich nie mówiło.

ZASADA (feedback usera 04.08): „każde miejsce, które coś odrzuca, ma licznik
z powodem". Ten moduł jest najtańszym sposobem, żeby ją spełnić bez pisania
79 osobnych logów: `except Exception as e: diagnostyka.cichy("statshub",
"trendy", e)` i na koniec cyklu jedna linia zbiorcza.

CZEGO TO NIE ROBI: nie zmienia zachowania. Wyjątek dalej jest połykany, dane
dalej przepadają — ale przestaje to być niewidzialne. Naprawa konkretnego
miejsca to osobna decyzja, podjęta wtedy, gdy licznik pokaże, że boli.
"""

from __future__ import annotations

from collections import Counter

# klucz: "modul:powod" -> ile razy w BIEŻĄCYM przebiegu
_licznik: Counter = Counter()
# pierwszy komunikat per klucz — żeby dało się zacząć diagnozę bez powtarzania
# przebiegu; treść wyjątku bywa jedyną wskazówką, co się stało
_pierwszy: dict[str, str] = {}


def cichy(modul: str, powod: str, blad: BaseException | None = None) -> None:
    """Odnotuj, że coś zostało po cichu odrzucone.

    `modul` — skąd (np. "statshub"), `powod` — co robiliśmy (np. "trendy_meczu").
    Wołane w bloku `except`; NIE przerywa i nie zmienia przepływu.
    """
    klucz = f"{modul}:{powod}"
    _licznik[klucz] += 1
    if blad is not None and klucz not in _pierwszy:
        # WŁASNE `try` NIE JEST OSTROŻNOŚCIĄ NA WYROST. `str(wyjątek)` potrafi
        # rzucić (własna klasa z `__str__`, biblioteka z leniwym repr), a to
        # jest kod wołany WEWNĄTRZ bloku `except`. Bez tego narzędzie do
        # łapania cichych błędów samo zamieniłoby połknięty błąd w wywalony
        # cykl — złapane własnym testem przy pisaniu tego modułu.
        try:
            tresc = str(blad).strip() or blad.__class__.__name__
            _pierwszy[klucz] = f"{blad.__class__.__name__}: {tresc[:160]}"
        except Exception:
            _pierwszy[klucz] = blad.__class__.__name__


def reset() -> None:
    """Wyzeruj przed przebiegiem (cykl woła to na starcie)."""
    _licznik.clear()
    _pierwszy.clear()


def raport() -> dict[str, int]:
    """Ile czego przepadło — do zapisania w diagnostyce cyklu."""
    return dict(_licznik)


def wypisz(prog: int = 1) -> None:
    """Jedna linia zbiorcza na koniec cyklu (nic, gdy było czysto).

    `prog` — pomijaj klucze rzadsze niż tyle. Domyślnie pokazuj wszystko:
    pojedynczy cichy błąd w źródle historii to dokładnie ten przypadek,
    którego szukaliśmy tygodniami.
    """
    istotne = {k: v for k, v in _licznik.items() if v >= prog}
    if not istotne:
        return
    razem = sum(istotne.values())
    szczegoly = ", ".join(
        f"{k}={v}" for k, v in sorted(istotne.items(), key=lambda x: -x[1])
    )
    print(f"Ciche błędy: {razem} w tym przebiegu — {szczegoly}", flush=True)
    for k, v in sorted(istotne.items(), key=lambda x: -x[1])[:5]:
        if k in _pierwszy:
            print(f"   {k} (x{v}) pierwszy: {_pierwszy[k]}", flush=True)
