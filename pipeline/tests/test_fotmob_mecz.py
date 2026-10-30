"""Parser meczu FotMob → rekord bazy (`fotmob.mecz_do_bazy`), na prawdziwych meczach.

  * Sunderland – Leeds, Premier League 25.10.2026 (pełne dane, mapa strzałów),
  * Liverpool – Chelsea, EFL Cup 28.10.2026 (1:1, karne 6:5),
  * Pärnu JK Vaprus – FC Kuressaare, Estonia 28.10.2026 (bez statystyk zawodników).

Oczekiwane liczby odczytane wprost z surowych odpowiedzi (nie z parsera).
Zgodność parsera ze statshub mierzy bramka etapu 2 (docs/plan-fotmob.md).
"""

import gzip
import json
from pathlib import Path

import pytest

from footstats.sources import fotmob

DANE = Path(__file__).parent / "data" / "fotmob"


def _mecz(nazwa):
    return fotmob.mecz_do_bazy(json.load(gzip.open(DANE / nazwa, "rt", encoding="utf-8")))


@pytest.fixture(scope="module")
def pl():
    return _mecz("mecz_pl_5795494.json.gz")


@pytest.fixture(scope="module")
def pen():
    return _mecz("mecz_pen_6275371.json.gz")


@pytest.fixture(scope="module")
def bez():
    return _mecz("mecz_bez_statystyk_1000007990.json.gz")


def _zaw(rec, pid):
    return next(z for z in rec["zawodnicy"] if z["pid"] == pid)


def test_naglowek_meczu(pl):
    assert pl["id"] == 5795494 and pl["liga"] == "Premier League"
    assert (pl["home"]["name"], pl["away"]["name"]) == ("Sunderland", "Leeds United")
    assert pl["status"] == "finished" and pl["gole"] == [0, 0] and not pl["dogrywka"]
    assert pl["sedzia"]["nazwa"] == "Stuart Attwell"
    assert pl["staty_zawodnikow"] and pl["mapa_strzalow"]


def test_statystyki_druzyn_z_okresami(pl):
    sun = pl["druzyny"][str(pl["home"]["id"])]
    lee = pl["druzyny"][str(pl["away"]["id"])]
    assert (sun["all"]["shots"], lee["all"]["shots"]) == (15, 11)
    assert (sun["all"]["corners"], lee["all"]["corners"]) == (4, 5)
    assert (sun["all"]["fouls"], lee["all"]["fouls"]) == (10, 14)
    assert sun["all"]["accurate_crosses"] == 3                 # '3 (15%)' → 3
    assert "h1" in sun and "h2" in sun and sun["reg"]["shots"] == sun["all"]["shots"]


def test_zawodnik_z_playerstats(pl):
    xhaka = _zaw(pl, 207236)
    assert xhaka["minuty"] == 90 and xhaka["start"] and xhaka["poz"] == "M"
    assert xhaka["staty"]["fouls_committed"] == 1 and xhaka["staty"]["fouls_won"] == 3
    assert xhaka["staty"]["tackles"] == 0 and xhaka["staty"]["shots"] == 0


def test_strzaly_z_mapy_zablokowany_celny_to_zablokowany(pl):
    """Bogle: 3' z daleka obok (1. połowa), 60' z pola celny ALE zablokowany –
    liczy się jako zablokowany, nie celny (zgodne ze statshub w 99,8%)."""
    s = _zaw(pl, 789646)["staty"]
    assert (s["shots"], s["sot"], s["shots_blocked"], s["shots_off_target"]) == (2, 0, 1, 1)
    assert (s["shots_outside_box"], s["sot_outside_box"]) == (1, 0)
    assert (s["fh_shots"], s["fh_sot"]) == (1, 0)


def test_strzaly_glowa(pl):
    """Na mapie 5 strzałów głową, w tym Muharemović celny nie zablokowany."""
    glowa = sum(z["staty"]["headed_shots"] for z in pl["zawodnicy"] if z["staty"])
    celne = sum(z["staty"]["headed_sot"] for z in pl["zawodnicy"] if z["staty"])
    assert (glowa, celne) == (5, 1)


def test_suma_zawodnikow_rowna_druzynie(pl):
    for tid in (pl["home"]["id"], pl["away"]["id"]):
        zaw = [z["staty"] for z in pl["zawodnicy"] if z["team_id"] == tid and z["staty"]]
        d = pl["druzyny"][str(tid)]["all"]
        assert sum(s["shots"] for s in zaw) == d["shots"]
        assert sum(s["fouls_committed"] for s in zaw) == d["fouls"]
        assert sum(s["tackles"] for s in zaw) == d["tackles"]   # drużyna = suma zawodników


def test_kartka_i_zmiany(pl):
    assert _zaw(pl, 780432)["staty"]["yellow_card"] == 1          # Ampadu 29'
    wszedl = next(z for z in pl["zawodnicy"] if z["name"] == "Omar Alderete")
    zszedl = next(z for z in pl["zawodnicy"] if z["name"] == "Nordi Mukiele")
    assert wszedl["wszedl"] == 52 and not wszedl["start"]
    assert zszedl["zszedl"] == 52 and zszedl["start"]


def test_karne_poza_strzalami_i_golami(pen):
    """Liverpool – Chelsea 1:1, karne 6:5: 16 strzałów serii karnych NIE wchodzi."""
    assert pen["gole"] == [1, 1] and pen["gole90"] == [1, 1]
    assert pen["dogrywka"] and pen["karne"] and pen["status"] == "finished"
    for tid in (pen["home"]["id"], pen["away"]["id"]):
        zaw = [z["staty"] for z in pen["zawodnicy"] if z["team_id"] == tid and z["staty"]]
        assert sum(s["shots"] for s in zaw) == pen["druzyny"][str(tid)]["reg"]["shots"]
    assert pen["druzyny"][str(pen["home"]["id"])]["reg"]["shots"] == 10      # 6 + 4


def test_liga_bez_statystyk_zawodnikow(bez):
    assert not bez["staty_zawodnikow"] and not bez["mapa_strzalow"]
    assert all(z["pid"] for z in bez["zawodnicy"])            # zawodnik bez id pominięty
    zagrali = [z for z in bez["zawodnicy"] if z["minuty"] > 0]
    assert zagrali and all(z["staty"] is None for z in bez["zawodnicy"])
    startery = [z for z in bez["zawodnicy"] if z["start"]]
    assert all(z["minuty"] > 0 for z in startery)              # minuty ze składu i zmian


@pytest.mark.parametrize("pid,usual,oczekiwana", [
    (11, 0, "G"), (34, 1, "D"), (64, 2, "M"), (77, 2, "M"), (83, 3, "F"),
    (83, 2, "M"), (105, 3, "F"), (None, 1, "D"), (2, 2, "M"), (None, None, "M"),
])
def test_pozycja(pid, usual, oczekiwana):
    assert fotmob._pozycja(pid, usual) == oczekiwana


@pytest.mark.parametrize("v,oczekiwana", [
    ("283 (75%)", 283), ("0.83", 0.83), (7, 7), (None, None), (True, None), ("x", None),
])
def test_liczba(v, oczekiwana):
    assert fotmob._liczba(v) == oczekiwana
