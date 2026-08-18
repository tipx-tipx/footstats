# -*- coding: utf-8 -*-
"""CHARAKTERYSTYKA DRABINKI DOJEŻDŻA DO KSIĘGI (2026-08-18).

Zgłoszenie właściciela: „musimy patrzeć na pokrycia, na charakterystykę
i dobierać takie drabinki, które mają sens — to nie tylko matematyka".

Przy próbie odpowiedzi okazało się, że NIE DA SIĘ. Zmierzone na 171
rozliczeniach drabinkowych: `matchup`, `matchup_styl`, `xi_sygnal`, `rotacja`,
`pewnosc`, `miekka_linia` były puste w 171 na 171 rekordów, choć karta
wszystkie te rzeczy liczy. Analiza mogła więc dotyczyć wyłącznie gołej szansy
wobec ceny — czyli dokładnie tego, co właściciel słusznie skrytykował.

Ten test pilnuje CAŁEJ drogi: karta → rekord typu → księga. Każdy odcinek ma
własną białą listę pól i każda potrafiła te stemple zjeść.
"""
import inspect
import textwrap

from footstats.jobs import build_wc_fast as B
from footstats.jobs import rozliczanie as R


def _helper():
    """`_charakter_drabinki` jest zagnieżdżony w `_main_impl` — wyciągamy go
    ze źródła, bo to jedyny sposób, żeby przetestować go bez cyklu."""
    src = inspect.getsource(B._main_impl)
    i = src.index("    def _charakter_drabinki")
    j = src.index("    drabinki_typy = []", i)
    g: dict = {}
    exec(compile(textwrap.dedent(src[i:j]), "<charakter>", "exec"), g)
    return g["_charakter_drabinki"]


# kształt sprawdzony na ŻYWYM dumpie radaru 18.08, nie zgadnięty
KARTA = {
    "minuty_sr6": 87, "udzial_startow": 1.0, "rodzaj": "debiutant",
    "kategoria": "analiza", "pozycja": "F", "xi": True,
    "ocena": {"klasa": "solidny"},
}
HERO = {
    "traf": 7, "z": 10, "p_bazowe": 0.595, "korekta": 1.053,
    "drugi_traf": 5, "drugi_z": 10, "drugi_p_bazowe": 0.396,
    "drugi_korekta": 1.178,
}


def test_pierwszy_szczebel_niesie_pokrycie_i_skladniki():
    out = _helper()(KARTA, HERO)
    assert out["pokrycie_traf"] == 7 and out["pokrycie_z"] == 10
    assert out["pokrycie"] == 0.7, "udział liczony, żeby pomiar nie dzielił sam"
    assert out["p_bazowe"] == 0.595, "pokrycie Wilsona — pierwszy człon"
    assert out["korekta"] == 1.053, "mnożnik meczowy — drugi człon"
    assert out["minuty_sr6"] == 87 and out["udzial_startow"] == 1.0
    assert out["pozycja"] == "F" and out["xi"] is True
    assert out["klasa_karty"] == "solidny"


def test_drugi_szczebel_bierze_SWOJE_liczby_a_nie_hero():
    out = _helper()(KARTA, HERO, drugi=True)
    assert out["pokrycie_traf"] == 5 and out["pokrycie"] == 0.5
    assert out["p_bazowe"] == 0.396 and out["korekta"] == 1.178
    # cechy KARTY zostają te same — to ten sam zawodnik i ten sam mecz
    assert out["minuty_sr6"] == 87 and out["klasa_karty"] == "solidny"


def test_brak_pokrycia_nie_udaje_zera():
    out = _helper()({}, {"traf": None, "z": None})
    assert "pokrycie" not in out and "pokrycie_traf" not in out
    assert "p_bazowe" not in out


def test_ksiega_PRZEPUSZCZA_charakterystyke():
    """⚑ Czwarta biała lista na drodze tych pól. Bez niej stempel powstaje
    na karcie i ginie przy zapisie — dokładnie ta klasa błędu, która w tym
    repo kosztowała najwięcej."""
    zrodlo = inspect.getsource(R._dopisz_nowe)
    for pole in ("pokrycie", "pokrycie_traf", "pokrycie_z", "p_bazowe",
                 "korekta", "minuty_sr6", "udzial_startow",
                 "rodzaj_karty", "kategoria_karty", "klasa_karty",
                 "pozycja", "xi"):
        assert f'"{pole}"' in zrodlo, (
            f"`{pole}` nie przechodzi przez `_dopisz_nowe` — charakterystyka "
            "drabinki zginie przy zapisie do księgi"
        )
