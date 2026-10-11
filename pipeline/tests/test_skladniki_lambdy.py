# -*- coding: utf-8 -*-
"""Składniki λ do opisu typu (2026-10-11, właściciel: „opisy przepisać dokładnie”).

Opis karty ma mówić to, na czym stoi liczba modelu. Rozkład jest dokładny:
λ = exp(stała + Σ β·odniesienie) × Π czynników grup – test pilnuje tej
tożsamości, żeby opis nigdy nie rozjechał się z wyceną.
"""
import math

import pytest

from footstats.model import uczony as U

WAGI_DRUZYNY = {
    "log": ["w6", "w12", "w_dom", "opp12", "liga", "p_crs"],
    "med": {"w6": 4.0, "w12": 4.2, "w_dom": 4.1, "opp12": 4.3, "liga": 4.2, "p_crs": 15.0},
    "flagi": ["w_dom"],
    "beta": [0.1, 0.3, 0.4, 0.1, 0.35, 0.2, 0.3, -0.02, 0.06, 0.04, 0.03],
}
CECHY_DRUZYNY = {"w6": 5.5, "w12": 5.0, "w_dom": None, "opp12": 5.2, "liga": 4.0,
                 "p_crs": 18.0, "dom": 1, "trend": 0.2, "brak_rywala": 0.0}


def _lam_z_rozkladu(wagi, cechy, skl, ref_dom=0.5, eps=0.5, minuty=None):
    stala = wagi["beta"][0]
    for c, b in zip(wagi["log"], wagi["beta"][1:]):
        stala += b * math.log(wagi["med"][c] + eps)
    return math.exp(stala) * math.prod(skl["mn"].values())


def test_czynniki_druzyny_skladaja_sie_w_lambde():
    assert len(U.nazwy_cech({"log": WAGI_DRUZYNY["log"], "flagi": WAGI_DRUZYNY["flagi"]})) == len(WAGI_DRUZYNY["beta"])
    lam = U.lam(WAGI_DRUZYNY, CECHY_DRUZYNY)
    skl = U.skladniki_druzyny(WAGI_DRUZYNY, CECHY_DRUZYNY)
    # dom odniesiony do 0,5 – dokładamy połowę β_dom z powrotem do stałej
    b_dom = WAGI_DRUZYNY["beta"][U.nazwy_cech({"log": WAGI_DRUZYNY["log"], "flagi": WAGI_DRUZYNY["flagi"]}).index("dom")]
    assert _lam_z_rozkladu(WAGI_DRUZYNY, CECHY_DRUZYNY, skl) * math.exp(0.5 * b_dom) == pytest.approx(lam, rel=0.01)
    assert skl["mn"]["forma"] > 1.0          # 5,5 / 5,0 przy medianie ~4
    assert skl["x"]["w6"] == 5.5 and skl["x"]["dom"] == 1
    assert skl["styl"][0][0] == "dośrodkowania"


WAGI_ZAW = {
    "log": ["t3", "t6", "t12", "min6", "liga", "rywal"],
    "med": {"t3": 1.5, "t6": 1.5, "t12": 1.5, "min6": 80.0, "liga": 1.4, "rywal": 1.0},
    "beta": [-0.2, 0.1, 0.2, 0.4, 0.05, 0.1, 0.15, 0.02, 0.1, 0.05, 0.08],
}
CECHY_ZAW = {"t3": 2.5, "t6": 2.2, "t12": 2.0, "min6": 85.0, "liga": 1.4,
             "rywal": 1.2, "dom": 0, "udzial_startow": 0.9, "poz": "FWD"}


def test_czynniki_zawodnika_z_minutami():
    lam = U.lam_zaw(WAGI_ZAW, CECHY_ZAW, 85.0)
    skl = U.skladniki_zawodnika(WAGI_ZAW, CECHY_ZAW, 85.0)
    nazwy = U.nazwy_cech_zaw({"log": WAGI_ZAW["log"]})
    b = dict(zip(nazwy, WAGI_ZAW["beta"]))
    stala = WAGI_ZAW["beta"][0] + sum(b[f"log_{c}"] * math.log(WAGI_ZAW["med"][c] + 0.1) for c in WAGI_ZAW["log"])
    stala += 0.5 * b["dom"] + 1.0 * b["udzial_startow"]
    assert math.exp(stala) * math.prod(skl["mn"].values()) == pytest.approx(lam, rel=0.01)
    assert skl["mn"]["forma"] > 1.0 and skl["mn"]["rywal"] > 1.0
    assert skl["mn"]["minuty"] < 1.0          # 85 minut to mniej niż pełny mecz
    assert skl["x"]["min"] == 85
