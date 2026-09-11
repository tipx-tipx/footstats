# -*- coding: utf-8 -*-
"""RENTGEN ZAPISANY PRZED `diagnostyka.reset()` GINIE BEZ SŁADU.

Zdarzyło się 11.09: stan magazynu drużyn odkładałem do `meta.rentgen` w
miejscu, w którym cykl wczytuje wagi modelu — a to dzieje się PRZED
`diagnostyka.reset()`, który czyści cały rentgen razem z licznikami przebiegu.
Na produkcji wyglądało to tak, że `model_pokrycie` (zapisywane na końcu) było
w meta, a `magazyn_druzyn` (zapisywane przy wczytaniu wag) nie istniało —
i nie było po tym ŻADNEGO śladu: `zapisz_rentgen` nie zawodzi, tylko wpis
znika przy resecie.

Ten test czyta ŹRÓDŁO, bo to jedyny sposób złapania kolejności bez odpalania
całego cyklu. Jest strukturalny i celowo prosty: wystarczy, żeby następny
`zapisz_rentgen` wstawiony za wysoko zapalił się na czerwono.

Wyjątek: wywołania w ciałach funkcji zdefiniowanych wcześniej, a wołanych
później (`budzet_odkrywania`, `budzet_dociagu_kursow`) — te są bezpieczne,
bo wykonują się dopiero podczas przebiegu. Rozpoznajemy je po wcięciu:
zapis w ciele funkcji wewnętrznej ma wcięcie 8+ spacji, zapis w ciele `main`
— dokładnie 4.
"""

from __future__ import annotations

import re
from pathlib import Path

ZRODLO = Path(__file__).resolve().parent.parent / "footstats" / "jobs" / "build_wc_fast.py"


def test_zapisy_rentgenu_w_main_stoja_za_resetem():
    linie = ZRODLO.read_text(encoding="utf-8").splitlines()

    reset = [i for i, w in enumerate(linie)
             if re.match(r"^\s*diagnostyka\.reset\(\)", w)]
    assert len(reset) == 1, f"spodziewam się jednego resetu, jest {len(reset)}"
    nr_resetu = reset[0]

    # zapisy wykonywane wprost w ciele `main` (wcięcie 4) — tylko te mają
    # ustaloną kolejność wobec resetu
    zbyt_wczesne = [
        (i + 1, w.strip())
        for i, w in enumerate(linie)
        if re.match(r"^ {4}diagnostyka\.zapisz_rentgen\(", w) and i < nr_resetu
    ]
    assert not zbyt_wczesne, (
        "zapis rentgenu przed diagnostyka.reset() zostanie wyczyszczony "
        f"i NIE trafi do meta: {zbyt_wczesne}"
    )


def test_reset_czysci_rentgen():
    """Podkładka pod test wyżej: gdyby reset przestał czyścić rentgen, ta
    kolejność przestałaby mieć znaczenie i test wyżej byłby martwy."""
    from footstats import diagnostyka
    diagnostyka.zapisz_rentgen("probny", {"a": 1})
    assert diagnostyka.rentgen().get("probny"), "zapis nie doszedł"
    diagnostyka.reset()
    assert "probny" not in diagnostyka.rentgen()
