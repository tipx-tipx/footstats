# -*- coding: utf-8 -*-
"""Brama uzasadnień: półka „więcej płacą" bez rozpisanego rachunku nie wchodzi.

Osobny plik, bo ta brama ma jedną cechę, której nie ma żadna inna: jej próg
dotyczy półki, którą rysuje front. Od redesignu (2026-10-01) front bierze
półkę z danych zamiast liczyć ją drugi raz własnym progiem – test pilnuje,
żeby druga kopia progu nie wróciła (ta sama klasa błędu co przedziały kuponów
wpisane na sztywno w starej `KuponyScena.tsx`, dwa dni pustej zakładki, 2026-08-01).
"""

from __future__ import annotations

import re
from pathlib import Path

from footstats.model import betting

WEB_SRC = Path(__file__).resolve().parent.parent.parent / "web" / "src"
FRONT = WEB_SRC / "app" / "projekt" / "_dane" / "przygotuj.ts"


def test_front_bierze_polke_z_danych_zamiast_wlasnego_progu():
    """Redesign (2026-10-01): strona nie liczy półki sama – bierze `polka`
    typu z pipeline'u. Stary test porównywał `PROG_KURSU_POLEK` wpisany we
    froncie z tym w `betting`; teraz pilnujemy, żeby drugiej kopii progu
    w ogóle nie było, a półka z danych przechodziła na stronę bez zmian.
    """
    assert FRONT.exists(), f"nie znalazłem {FRONT}"
    zrodlo = FRONT.read_text("utf-8")
    m = re.search(r"export function polkaNaStronie\(.*?\n}\n", zrodlo, flags=re.S)
    assert m, "nie znalazłem polkaNaStronie w przygotuj.ts"
    assert 'if (polka === "wysoka_szansa" || polka === "wyzsze_kursy") return polka;' in m.group(0)
    kopie = [p for p in WEB_SRC.rglob("*.ts*") if "PROG_KURSU_POLEK" in p.read_text("utf-8")]
    assert not kopie, f"druga kopia progu półek we froncie: {kopie}"


def test_polka_wiecej_placa_wymaga_uzasadnienia():
    assert betting.wymaga_uzasadnienia(2.50)
    assert betting.wymaga_uzasadnienia(1.91)
    # granica należy do półki „więcej płacą" — tak samo jak we froncie,
    # gdzie „częściej wchodzą" to kurs OSTRO poniżej progu
    assert betting.wymaga_uzasadnienia(1.90)
    assert not betting.wymaga_uzasadnienia(1.89)
    assert not betting.wymaga_uzasadnienia(1.35)


def test_brak_kursu_nie_wymaga_uzasadnienia():
    """Typ bez kursu nie jest „droższy" — nie ma go czym zmierzyć.

    Wpuszczenie go do bramy zdejmowałoby z listy typy, o których nic złego nie
    wiemy; `brak_kursu` nigdy nie dowodził niczego poza brakiem odczytu.
    """
    assert not betting.wymaga_uzasadnienia(None)
    assert not betting.wymaga_uzasadnienia(0.0)


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
