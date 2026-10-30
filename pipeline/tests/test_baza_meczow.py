"""Własna baza meczów (baza_meczow): zapis zwięzły, dopisywanie, zapis miesięcy, indeksy."""

import copy
import gzip
import json
from pathlib import Path

import pytest

from footstats import baza_meczow as B
from footstats import supa
from footstats.sources import fotmob

DANE = Path(__file__).parent / "data" / "fotmob"
PLIKI = ["mecz_pl_5795494.json.gz", "mecz_pen_6275371.json.gz", "mecz_bez_statystyk_1000007990.json.gz"]


def _rek(nazwa):
    return fotmob.mecz_do_bazy(json.load(gzip.open(DANE / nazwa, "rt", encoding="utf-8")))


@pytest.mark.parametrize("plik", PLIKI)
def test_zapis_zwiezly_odtwarza_rekord_co_do_pola(plik):
    r = _rek(plik)
    z = B.spakuj(r)
    assert B.rozpakuj(json.loads(json.dumps(z))) == json.loads(json.dumps(r))


def test_brak_mapy_to_none_nie_zero():
    """Liga bez mapy strzałów: rynki głową / zza pola po odczycie = None."""
    r = _rek("mecz_pl_5795494.json.gz")
    r["mapa_strzalow"] = False
    for z in r["zawodnicy"]:
        if z["staty"]:
            for kod in fotmob.RYNKI_Z_MAPY:
                z["staty"][kod] = None
    po = B.rozpakuj(B.spakuj(r))
    zaw = next(z for z in po["zawodnicy"] if z["staty"])
    assert all(zaw["staty"][k] is None for k in fotmob.RYNKI_Z_MAPY)
    assert zaw["staty"]["fouls_committed"] is not None


def test_klucz_miesiaca():
    assert B.klucz_miesiaca(1793215800) == "fm_baza_202610"      # 28.10.2026


def test_dopisz_nie_nadpisuje_ubozszym():
    r = _rek("mecz_pl_5795494.json.gz")
    baza = {}
    assert B.dopisz(baza, [r]) == {"fm_baza_202610"}
    ubozszy = copy.deepcopy(r)
    ubozszy["mapa_strzalow"] = False
    ubozszy["zawodnicy"] = []
    assert B.dopisz(baza, [ubozszy]) == set()
    assert len(B.rozpakuj(baza[r["id"]])["zawodnicy"]) == len(r["zawodnicy"])


def test_dopisz_nadpisuje_bogatszym():
    r = _rek("mecz_pl_5795494.json.gz")
    ubogi = copy.deepcopy(r)
    ubogi["staty_zawodnikow"] = False
    ubogi["mapa_strzalow"] = False
    baza = {}
    B.dopisz(baza, [ubogi])
    assert B.dopisz(baza, [r]) == {"fm_baza_202610"}
    assert baza[r["id"]]["mapa_strzalow"]


def test_dopisz_pomija_niezakonczone():
    r = _rek("mecz_pl_5795494.json.gz")
    r["status"] = "inprogress"
    baza = {}
    assert B.dopisz(baza, [r]) == set() and baza == {}


def test_wczytaj_odroznia_awarie_od_pustki(monkeypatch):
    odp = {"fm_baza_202609": (None, False), "fm_baza_202610": ({"1": {"ts": 1793215800}}, True),
           "fm_baza_202611": (None, True)}
    monkeypatch.setattr(supa, "get_key_ok", lambda k: odp[k])
    baza, braki = B.wczytaj(list(odp))
    assert set(baza) == {1} and braki == ["fm_baza_202609"]


def test_zapisz_pomija_miesiac_nieprzeczytany(monkeypatch):
    zapisane = {}
    monkeypatch.setattr(supa, "put_key", lambda k, v: zapisane.setdefault(k, v) is not None)
    r = _rek("mecz_pl_5795494.json.gz")
    baza = {}
    zm = B.dopisz(baza, [r])
    assert B.zapisz(baza, zm, nieprzeczytane=["fm_baza_202610"]) == {"fm_baza_202610": False}
    assert zapisane == {}
    assert B.zapisz(baza, zm, nieprzeczytane=[]) == {"fm_baza_202610": True}
    assert set(zapisane["fm_baza_202610"]) == {str(r["id"])}


def test_indeksy_druzyn_i_zawodnikow():
    rek = [_rek(p) for p in PLIKI]
    baza = {}
    B.dopisz(baza, rek)
    hd = B.historia_druzyn(baza)
    pl = rek[0]
    assert [r["id"] for r in hd[pl["home"]["id"]]] == [pl["id"]]
    hz = B.historia_zawodnikow(baza)
    mecz, wiersz = hz[207236][0]                       # Xhaka
    assert mecz["id"] == pl["id"] and wiersz["staty"]["fouls_won"] == 3


@pytest.mark.magazyn_produkcyjny
def test_klucze_bazy_w_magazynie_repo():
    """Produkcyjny MAGAZYN (nie pusty z conftestu) kieruje miesiące bazy do repo."""
    assert supa.MAGAZYN.get("fm_baza_202610") == "repo"
    assert supa.MAGAZYN.get("fm_baza_203012") == "repo"
    assert supa.MAGAZYN.get("fm_tozsamosc") == "repo"
