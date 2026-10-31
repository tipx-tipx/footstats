"""Job bazy meczów FotMob (etap 4a): zakres, jednorazowe pobranie, dopełnianie, mapowanie zawodników."""

import gzip
import json
from pathlib import Path

import pytest

from footstats import baza_meczow
from footstats import tozsamosc as T
from footstats.jobs import fm_baza as J
from footstats.sources import fotmob

DANE = Path(__file__).parent / "data" / "fotmob"
SUROWY = json.load(gzip.open(DANE / "mecz_pl_5795494.json.gz", "rt", encoding="utf-8"))
REK = fotmob.mecz_do_bazy(SUROWY)          # Sunderland 8472 – Leeds 8463, 25.10.2026


def _terminarz(mid, home, away, liga=47, status="finished", ts=REK["ts"]):
    return {"id": mid, "start_ts": ts, "home_id": home, "home": "A", "away_id": away, "away": "B",
            "liga_id": liga, "status": status}


@pytest.fixture
def srodowisko(monkeypatch):
    stan = {"baza": {}, "mapa": T.Tozsamosc({"druzyny": {"8472": 41}, "rozgrywki": {"47": 17}}),
            "pytania": [], "zapis_mapy": []}
    dzien = {"20261025": [_terminarz(REK["id"], 8472, 8463),
                          _terminarz(1, 900, 901, liga=999),                 # poza zakresem
                          _terminarz(2, 8472, 77, status="notstarted")]}
    monkeypatch.setattr(T, "wczytaj", lambda: (stan["mapa"], True))
    monkeypatch.setattr(T, "zapisz", lambda t: stan["zapis_mapy"].append(t) or True)
    monkeypatch.setattr(baza_meczow, "wczytaj", lambda m: (dict(stan["baza"]), []))

    def zapisz(baza, miesiace, nieprzecz):
        stan["baza"] = dict(baza)
        return {k: True for k in miesiace}
    monkeypatch.setattr(baza_meczow, "zapisz", zapisz)
    monkeypatch.setattr(J, "_czytaj", lambda k: {
        "1:sot": {"player_id": 1, "player_name": REK["zawodnicy"][0]["name"], "team_id": 41,
                  "timestamps": [], "minutes": []}})
    monkeypatch.setattr(fotmob, "mecze_dnia", lambda d: dzien.get(d, []))

    def szczegoly(mid):
        stan["pytania"].append(mid)
        return SUROWY
    monkeypatch.setattr(fotmob, "szczegoly_meczu", szczegoly)
    return stan


def test_pobiera_raz_tylko_zakonczone_z_zakresu(srodowisko):
    assert J.main(["--od", "2026-10-25"]) == 0
    assert srodowisko["pytania"] == [REK["id"]]
    assert REK["id"] in srodowisko["baza"]
    # zawodnik z trend_lib dostał parę po nazwisku, reszta – stały numer zastępczy
    mapa = srodowisko["zapis_mapy"][-1]
    assert mapa.zawodnicy[REK["zawodnicy"][0]["pid"]] == 1
    assert sum(1 for v in mapa.zawodnicy.values() if v == 0) > 10
    # drugi przebieg: mecz już w bazie – zero pytań o szczegóły
    srodowisko["pytania"].clear()
    assert J.main(["--od", "2026-10-25"]) == 0
    assert srodowisko["pytania"] == []


def test_dopelnienie_tylko_mlody_mecz_z_ligi_ze_statystykami(srodowisko, monkeypatch):
    ubogi = baza_meczow.spakuj({**REK, "staty_zawodnikow": False})
    inny = baza_meczow.spakuj({**REK, "id": 5, "staty_zawodnikow": True})
    srodowisko["baza"] = {REK["id"]: ubogi, 5: inny}
    monkeypatch.setattr(J.time, "time", lambda: REK["ts"] + 3600)
    assert J.main(["--od", "2026-10-25"]) == 0
    assert srodowisko["pytania"] == [REK["id"]]
    assert srodowisko["baza"][REK["id"]]["staty_zawodnikow"]
    # liga bez meczów ze statystykami – brak to brak źródła, nie pytamy ponownie
    srodowisko["pytania"].clear()
    srodowisko["baza"] = {REK["id"]: ubogi}
    assert J.main(["--od", "2026-10-25"]) == 0
    assert srodowisko["pytania"] == []


def test_pusta_mapa_to_koniec_bez_zapisu(srodowisko, monkeypatch):
    monkeypatch.setattr(T, "wczytaj", lambda: (T.Tozsamosc(), True))
    assert J.main(["--od", "2026-10-25"]) == 1
    assert srodowisko["pytania"] == [] and srodowisko["zapis_mapy"] == []


def test_odmowa_przy_terminarzu_bez_zapisu(srodowisko, monkeypatch):
    def odmowa(d):
        raise fotmob.FotmobOdmowa("403")
    monkeypatch.setattr(fotmob, "mecze_dnia", odmowa)
    assert J.main(["--od", "2026-10-25"]) == 1
    assert srodowisko["zapis_mapy"] == []
