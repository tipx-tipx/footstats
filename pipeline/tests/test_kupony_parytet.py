"""P1: kuponBuilder.ts jest ręcznie utrzymywanym portem beam-searcha z
kupony.py (parytet 1:1, patrz komentarz na górze kuponBuilder.ts) — bez
testu porównującego wyjścia obu implementacji, przyszła zmiana stałej/kroku
algorytmu w jednym języku mogłaby się cicho rozjechać z drugim (generator na
żądanie zacząłby dawać inne kupony niż silnik automatyczny, bez błędu).

Ten test woła TĘ SAMĄ pulę legów przez footstats.model.kupony._zloz_pewniaki
(Python) i przez web/scripts/kupony_parity_bridge.ts (Node -> kuponBuilder.ts)
i porównuje wynik. Wymaga Node.js w PATH — środowisko bez Node dostaje SKIP,
nie FAIL (cross-toolchain test, nie blokuje resztę suity gdy Node niedostępny).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from footstats.model import kupony

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"
BRIDGE = WEB_DIR / "scripts" / "kupony_parity_bridge.ts"

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(
    NODE is None or not BRIDGE.exists(),
    reason="Node.js lub kupony_parity_bridge.ts niedostępne — test cross-toolchain pominięty",
)


def _leg(mecz_id, podmiot_id, kurs, p, druzyna="", rynek_kod="shots",
         linia=1.5, kickoff=1_000_000, **extra):
    l = {
        "id": podmiot_id, "mecz_id": mecz_id, "mecz": f"T{mecz_id}A - T{mecz_id}B",
        "kickoff_ts": kickoff, "podmiot_id": podmiot_id, "podmiot": f"P{podmiot_id}",
        "druzyna": druzyna or f"T{mecz_id}A", "przeciwnik": f"T{mecz_id}B",
        "rynek_kod": rynek_kod, "rynek": "Strzały", "linia": linia,
        "strona": "powyzej", "kurs": kurs, "bukmacher": "Superbet", "p_model": p,
    }
    l.update(extra)
    return l


def _run_ts(pool: list[dict], cmin: float, cmax: float, opts: dict) -> dict | None:
    payload = json.dumps({"pool": pool, "cmin": cmin, "cmax": cmax, "opts": opts})
    proc = subprocess.run(
        [NODE, str(BRIDGE)],
        input=payload, capture_output=True, text=True, cwd=WEB_DIR, timeout=30,
        # Node pisze UTF-8; bez tego Windows dekoduje cp1252 i wywraca się
        # na nazwiskach/pauzach z prawdziwych danych (test na migawce puli)
        encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, f"bridge TS padł: {proc.stderr}"
    return json.loads(proc.stdout)


def _run_py(pool: list[dict], cmin: float, cmax: float, opts: dict) -> dict | None:
    return kupony._zloz_pewniaki(
        pool, cmin, cmax,
        max_na_mecz=opts.get("maxNaMecz", 4),
        min_legi=opts.get("minLegi", 3),
        profil=opts.get("profil", "zbalansowany"),
        kary=opts.get("kary"),
    )


def _assert_parity(pool, cmin, cmax, opts):
    py = _run_py(pool, cmin, cmax, opts)
    ts = _run_ts(pool, cmin, cmax, opts)
    assert (py is None) == (ts is None), f"jeden None a drugi nie: py={py}, ts={ts}"
    if py is None:
        return
    assert py["kurs_laczny"] == ts["kurs_laczny"]
    assert abs(py["p_model"] - ts["p_model"]) < 1e-6
    py_legi = [l["podmiot_id"] for l in py["legi"]]
    ts_legi = [l["podmiot_id"] for l in ts["legi"]]
    assert py_legi == ts_legi, f"inna kolejność/skład legów: py={py_legi} ts={ts_legi}"


def test_parytet_podstawowy_3_legi():
    pool = [
        _leg(1, 11, 1.8, 0.62), _leg(2, 22, 1.7, 0.65), _leg(3, 33, 1.75, 0.63),
    ]
    _assert_parity(pool, 4.0, 8.0, {"minLegi": 3})


def test_parytet_z_bonusami_profil_agresywny():
    pool = [
        _leg(1, 11, 1.5, 0.70, matchup=True, ev_uk=12.0),
        _leg(2, 22, 1.6, 0.68, miekka_linia=True, ev_pct=8.0),
        _leg(3, 33, 1.4, 0.72, swieze_sklady=True),
        _leg(4, 44, 1.55, 0.66, linia=2.5),
        _leg(5, 55, 1.65, 0.64, druzyna="T5A"),
        _leg(6, 66, 1.45, 0.71, rynek_kod="sot"),
        _leg(7, 77, 1.35, 0.74),
        _leg(8, 88, 1.9, 0.60, ev_uk=20.0, matchup=True),
    ]
    _assert_parity(pool, 8.0, 16.0, {"minLegi": 4, "profil": "agresywny"})


def test_parytet_korelacja_ten_sam_mecz():
    # 2 legi z tego samego meczu (ta sama drużyna) — wymusza _kara_koszyka
    pool = [
        _leg(1, 11, 1.6, 0.68, druzyna="TA"),
        _leg(1, 12, 1.5, 0.70, druzyna="TA"),
        _leg(2, 22, 1.7, 0.65, druzyna="TB"),
        _leg(3, 33, 1.55, 0.66, druzyna="TC"),
        _leg(4, 44, 1.45, 0.69, druzyna="TD"),
    ]
    _assert_parity(pool, 5.0, 10.0, {"minLegi": 3, "maxNaMecz": 2})


def test_parytet_zmierzone_kary():
    pool = [
        _leg(1, 11, 1.6, 0.68, druzyna="TA"),
        _leg(1, 12, 1.5, 0.70, druzyna="TA"),
        _leg(2, 22, 1.7, 0.65, druzyna="TB"),
        _leg(3, 33, 1.55, 0.66, druzyna="TC"),
    ]
    kary = {"ta_sama": 0.80, "przeciwne": 0.95, "nieznane": 0.90}
    _assert_parity(pool, 4.0, 8.0, {"minLegi": 3, "maxNaMecz": 2, "kary": kary})


def test_parytet_brak_kompletu_w_obu():
    pool = [_leg(1, 11, 1.5, 0.70)]
    _assert_parity(pool, 10.0, 20.0, {"minLegi": 3})


def test_parytet_urealnienie_i_limit_ryzykownych():
    # mieszanka kotwic i ryzykownych legów z dużą deklarowaną przewagą —
    # pokrywa _p_skladania (wagi wysoka/srednia/brak), _leg_value z urealnionej
    # przewagi oraz limit MAX_RYZYKOWNE w rozszerzaniu wiązki
    pool = [
        _leg(1, 11, 1.25, 0.86, pewnosc="wysoka", ev_pct=4.0),
        _leg(1, 12, 2.90, 0.45, pewnosc="srednia", ev_pct=30.5),
        _leg(2, 22, 1.65, 0.78, pewnosc="srednia", ev_pct=28.7),
        _leg(2, 23, 2.87, 0.446, pewnosc="srednia", ev_pct=27.9),
        _leg(3, 33, 1.71, 0.717, pewnosc="srednia", ev_pct=22.5),
        _leg(3, 34, 1.55, 0.732, pewnosc="srednia", ev_pct=13.4),
        _leg(4, 44, 1.43, 0.778, ev_pct=11.3),  # bez pewności → waga domyślna
        _leg(4, 45, 2.25, 0.513, pewnosc="srednia", ev_pct=15.4),
        # ryzykowny Z niezależnym potwierdzeniem (ev_uk) — jedyny gambit,
        # który zbalansowany ma prawo wziąć
        _leg(5, 55, 2.60, 0.50, pewnosc="srednia", ev_uk=18.0),
        # legi z ci — płynna waga zaufania (wąskie/szerokie widełki) musi
        # liczyć się identycznie po obu stronach
        _leg(6, 66, 1.50, 0.75, pewnosc="srednia", ci=[0.68, 0.80]),
        _leg(6, 67, 1.72, 0.70, pewnosc="wysoka", ci=[0.48, 0.82]),
    ]
    for profil in ("bezpieczny", "zbalansowany", "agresywny"):
        _assert_parity(pool, 8.0, 16.0, {"minLegi": 3, "profil": profil})
        _assert_parity(pool, 17.0, 29.5, {"minLegi": 3, "profil": profil})
