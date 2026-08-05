# -*- coding: utf-8 -*-
"""Brama wartości kuponu: nie publikujemy zakładu, który traci wg nas samych.

Liczby w testach to REALNE kupony z 2026-08-05 (patrz komentarz przy
`kupony.MIN_WARTOSC_KUPONU`), żeby test pilnował konkretnego przypadku, który
tę bramę wywołał, a nie wymyślonej arytmetyki.
"""

from __future__ import annotations

import pytest

from footstats.model import kupony


def _kupon(kurs: float, p: float, horyzont: str = "dzienny") -> dict:
    return {
        "kurs_laczny": kurs, "p_model": p, "horyzont": horyzont,
        "cel": 0, "cel_label": "test", "legi": [],
    }


def test_wartosc_brutto_to_szansa_razy_kurs():
    assert kupony.wartosc_brutto(_kupon(2.54, 0.309)) == pytest.approx(0.785, abs=5e-3)
    assert kupony.wartosc_brutto(_kupon(19.24, 0.060)) == pytest.approx(1.154, abs=5e-3)


def test_zdejmuje_dokladnie_ten_kupon_ktory_wywolal_brame():
    """Realna piątka z 05.08 — zdjęty ma być JEDEN, ten za 0,79 zł."""
    lista = [
        _kupon(4.89, 0.217, "dzienny"),
        _kupon(9.09, 0.127, "dlugoterminowy"),
        _kupon(19.24, 0.060, "dlugoterminowy"),
        _kupon(2.22, 0.462, "dzienny"),
        _kupon(2.54, 0.309, "dlugoterminowy"),   # <- 0,79 zł
    ]
    zostaje = [k for k in lista if kupony.kupon_oplacalny(k)]
    zdjete = [k for k in lista if not kupony.kupon_oplacalny(k)]
    assert len(zostaje) == 4
    assert len(zdjete) == 1
    assert zdjete[0]["kurs_laczny"] == 2.54


def test_granica_nalezy_do_publikowanych():
    """Dokładnie 1,00 to zero, nie strata — nie ma powodu tego zdejmować."""
    assert kupony.kupon_oplacalny(_kupon(2.0, 0.5))
    assert not kupony.kupon_oplacalny(_kupon(2.0, 0.4999))


def test_brak_danych_nie_przepuszcza():
    """Kupon bez kursu albo bez szansy nie ma jak udowodnić wartości."""
    assert not kupony.kupon_oplacalny({"kurs_laczny": None, "p_model": 0.5})
    assert not kupony.kupon_oplacalny({"kurs_laczny": 3.0, "p_model": None})
    assert not kupony.kupon_oplacalny({})
    # śmieci w polu nie mogą wywalić cyklu — brama ma odrzucić, nie rzucić
    assert not kupony.kupon_oplacalny({"kurs_laczny": "x", "p_model": 0.5})


def test_brama_nie_rusza_generatora_recznego():
    """`build_kupony` NIE filtruje — parytet z kuponBuilder.ts musi zostać.

    Brama stoi w jobie (build_wc_fast), bo generator na stronie meczu ma prawo
    zbudować to, o co user prosi. Gdyby filtr wszedł do `build_kupony`, wersja
    pythonowa i TS-owa dawałyby różne wyniki i test parytetu by to wykrył —
    ale dopiero po wdrożeniu.
    """
    import inspect
    zrodlo = inspect.getsource(kupony.build_kupony)
    assert "kupon_oplacalny" not in zrodlo
    assert "MIN_WARTOSC_KUPONU" not in zrodlo
