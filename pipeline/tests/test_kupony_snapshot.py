"""Testy regresyjne na MIGAWCE prawdziwej puli legów (2026-07-14: 37 legów,
2 mecze MŚ — Anglia–Argentyna, Francja–Hiszpania).

Zamrożone przypadki, w których stara wiązka GUBIŁA istniejące komplety
(istnienie udowodnione pełnym przeszukaniem kombinacji, brute force):
  * "dokładnie 7 typów" przy celu ×10  -> BRAK mimo kompletu o p=0.172,
  * "dokładnie 8 typów" przy celu ×10  -> BRAK mimo kompletu o p=0.132,
  * bezpieczny "dokładnie 8" przy ×25  -> BRAK mimo kompletu o p=0.096.
Przyczyna: ranking przycinania miesza długości stanów i premiuje bliskość
dolnej granicy kursu — naprawione kwotą MIN_NA_DLUGOSC per długość.

Tryb "dokładnie N" (maxLegi) istnieje tylko w TS (GeneratorKuponu), więc
przypadki exact-N idą przez most parytetu; "co najmniej" też przez Pythona.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from footstats.model import kupony
from test_kupony_parytet import BRIDGE, NODE, _assert_parity, _run_ts

DATA = Path(__file__).parent / "data" / "legi_pool_snapshot.json"
POOL = json.loads(DATA.read_text(encoding="utf-8"))

wymaga_node = pytest.mark.skipif(
    NODE is None or not BRIDGE.exists(),
    reason="Node.js lub kupony_parity_bridge.ts niedostępne",
)


def test_co_najmniej_3_cel_6_blisko_optimum():
    # brute force (kary domyślne) daje optimum p=0.3612 — wiązka ma być
    # co najwyżej o włos od niego
    k = kupony._zloz_pewniaki(POOL, 5.1, 7.08, min_legi=3)
    assert k is not None
    assert k["p_model"] >= 0.35


def test_zbalansowany_wysoki_kurs_bez_gambitow():
    # cel ×20: żaden leg poniżej progu ryzyka (w migawce brak ev_uk, więc
    # gambity są w całości poza grą dla profilu zbalansowanego)
    k = kupony._zloz_pewniaki(POOL, 17.0, 23.6, min_legi=3)
    assert k is not None
    assert len(k["legi"]) >= 5
    assert all(l["p_model"] >= kupony.PROG_RYZYKA_P for l in k["legi"])


@wymaga_node
def test_ts_dokladnie_7_znajduje_komplet():
    ts = _run_ts(POOL, 8.5, 11.8, {"minLegi": 7, "maxLegi": 7})
    assert ts is not None, "dokładnie 7 typów przy ×10 istnieje (brute: p=0.172)"
    assert len(ts["legi"]) == 7
    assert 8.5 <= ts["kurs_laczny"] <= 11.8
    assert ts["p_model"] >= 0.15
    assert all(l["p_model"] >= kupony.PROG_RYZYKA_P for l in ts["legi"])


@wymaga_node
def test_ts_dokladnie_8_znajduje_komplet():
    ts = _run_ts(POOL, 8.5, 11.8, {"minLegi": 8, "maxLegi": 8})
    assert ts is not None, "dokładnie 8 typów przy ×10 istnieje (brute: p=0.132)"
    assert len(ts["legi"]) == 8
    assert 8.5 <= ts["kurs_laczny"] <= 11.8


@wymaga_node
def test_ts_bezpieczny_dokladnie_8_wysoki_kurs():
    ts = _run_ts(
        POOL, 21.25, 29.5,
        {"minLegi": 8, "maxLegi": 8, "profil": "bezpieczny"},
    )
    assert ts is not None, "bezpieczny 8 typów przy ×25 istnieje (brute: p=0.096)"
    assert len(ts["legi"]) == 8
    assert all(l["p_model"] >= 0.58 for l in ts["legi"])
    assert ts["p_model"] >= 0.09


@wymaga_node
def test_parytet_na_migawce():
    # prawdziwe dane przecinają wszystkie ścieżki naraz (wagi zaufania,
    # kary korelacji, dywersyfikację rodzin, tie-breaki)
    for profil in ("bezpieczny", "zbalansowany", "agresywny"):
        for cmin, cmax in ((5.1, 7.08), (8.5, 11.8), (21.25, 29.5)):
            _assert_parity(POOL, cmin, cmax, {"minLegi": 3, "profil": profil})
