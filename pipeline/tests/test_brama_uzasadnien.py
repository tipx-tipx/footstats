# -*- coding: utf-8 -*-
"""Brama uzasadnień: półka „więcej płacą" bez rozpisanego rachunku nie wchodzi.

Osobny plik, bo ta brama ma jedną cechę, której nie ma żadna inna: jej próg
MUSI się zgadzać z liczbą we froncie. Backend tnie półkę, którą front rysuje —
jeśli te dwie liczby się rozjadą, brama zdejmie typy z innej półki, niż strona
pokazuje, i nikt tego nie zauważy, bo obie strony będą wewnętrznie spójne.
To ta sama klasa błędu co przedziały kursowe kuponów wpisane na sztywno
w `KuponyScena.tsx` (dwa dni pustej zakładki, 2026-08-01).
"""

from __future__ import annotations

import re
from pathlib import Path

from footstats.model import betting

FRONT = (
    Path(__file__).resolve().parent.parent.parent
    / "web" / "src" / "components" / "DruzynyTablica.tsx"
)


def test_prog_polki_zgadza_sie_z_frontem():
    """`PROG_PEWNE` w DruzynyTablica.tsx == `PROG_POLKI_PEWNE` w betting.py."""
    assert FRONT.exists(), f"nie znalazłem {FRONT}"
    m = re.search(r"const PROG_PEWNE\s*=\s*([0-9.]+)\s*;", FRONT.read_text("utf-8"))
    assert m, "nie znalazłem PROG_PEWNE w DruzynyTablica.tsx"
    assert float(m.group(1)) == betting.PROG_POLKI_PEWNE


def test_polka_wiecej_placa_wymaga_uzasadnienia():
    assert betting.wymaga_uzasadnienia(0.45)
    assert betting.wymaga_uzasadnienia(0.69)
    # granica należy do półki „częściej wchodzą" — tam brama nie sięga
    assert not betting.wymaga_uzasadnienia(0.70)
    assert not betting.wymaga_uzasadnienia(0.91)


def test_komplet_to_czynniki_ORAZ_przedzial():
    pelny = {"czynniki": {"rywal": 1.1}, "ci": [0.4, 0.55]}
    assert betting.ma_komplet_uzasadnienia(pelny)
    # typ wznowiony z księgi: wraca bez czynników — to on jest powodem bramy
    assert not betting.ma_komplet_uzasadnienia({"czynniki": {}, "ci": [0.4, 0.55]})
    assert not betting.ma_komplet_uzasadnienia({"ci": [0.4, 0.55]})
    # przedział ufności bywa pusty przy typie odtworzonym — też brak kompletu
    assert not betting.ma_komplet_uzasadnienia(
        {"czynniki": {"rywal": 1.1}, "ci": [None, None]}
    )
    assert not betting.ma_komplet_uzasadnienia({"czynniki": {"rywal": 1.1}})


def test_brama_nie_rusza_polki_czesciej_wchodza():
    """Typ o wysokiej szansie bez czynników ZOSTAJE — brama go nie dotyczy."""
    b = {"p_model": 0.85, "czynniki": {}, "ci": [None, None]}
    zdejmuje = betting.wymaga_uzasadnienia(b["p_model"]) and not (
        betting.ma_komplet_uzasadnienia(b)
    )
    assert not zdejmuje
