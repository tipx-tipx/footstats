"""Klient FotMob (sources/fotmob.py): tempo, pamięć, limit, odmowa, terminarz.

Terminarz testowy to prawdziwa, przycięta odpowiedź z 28.10.2026 (po jednym
meczu FT, AET, Pen, PP, Can, Ab) — kształty sprawdzone na żywo 30.10.
"""

import json
from pathlib import Path

import pytest

from footstats.sources import fotmob

DZIEN = json.loads((Path(__file__).parent / "data" / "fotmob" / "dzien_20261028.json")
                   .read_text(encoding="utf-8"))


class Odp:
    def __init__(self, kod=200, dane=None, typ="application/json", tekst="", naglowki=None):
        self.status_code = kod
        self._dane = dane
        self.headers = {"content-type": typ, **(naglowki or {})}
        self.text = tekst

    def json(self):
        return self._dane

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def siec(monkeypatch):
    """Zaślepiona sieć: kolejka odpowiedzi + lista wołanych adresów, zero czekania."""
    fotmob.wyczysc()
    monkeypatch.setattr(fotmob, "ODSTEP_S", 0)
    monkeypatch.setattr(fotmob, "ROZRZUT_S", 0)
    monkeypatch.setattr(fotmob, "PAUZA_PONOWIENIA_S", 0)
    stan = {"kolejka": [], "adresy": []}

    def get(url, **kw):
        stan["adresy"].append(url)
        odp = stan["kolejka"].pop(0)
        if isinstance(odp, Exception):
            raise odp
        return odp

    monkeypatch.setattr(fotmob.requests, "get", get)
    yield stan
    fotmob.wyczysc()


def test_terminarz_plaski_ze_statusami_statshub(siec):
    siec["kolejka"].append(Odp(dane=DZIEN))
    mecze = fotmob.mecze_dnia("20261028")
    assert siec["adresy"] == [f"{fotmob.BASE}/matches?date=20261028"]
    po_powodzie = {m["powod"]: m for m in mecze}
    assert {k: v["status"] for k, v in po_powodzie.items()} == {
        "FT": "finished", "AET": "finished", "Pen": "finished",
        "PP": "postponed", "Can": "canceled", "Ab": "abandoned"}
    surowe = {int(x["id"]): x for liga in DZIEN["leagues"] for x in liga["matches"]}
    m = po_powodzie["FT"]
    assert m["start_ts"] * 1000 == surowe[m["id"]]["timeTS"]           # sekundy, nie ms
    assert (m["home_id"], m["home"]) == (surowe[m["id"]]["home"]["id"], surowe[m["id"]]["home"]["name"])
    assert m["liga"] and m["kraj"]


def test_wysyla_wlasny_user_agent(siec, monkeypatch):
    """Bez User-Agent zapora CloudFront FotMob odpowiada 403 (sprawdzone 30.10)."""
    wyslane = {}

    def get(url, **kw):
        wyslane.update(kw.get("headers") or {})
        return Odp(dane={})

    monkeypatch.setattr(fotmob.requests, "get", get)
    fotmob.szczegoly_meczu(1)
    assert wyslane.get("User-Agent", "").startswith("footstats")


def test_status_przed_i_w_trakcie():
    assert fotmob.status_meczu({"started": False, "finished": False}) == "notstarted"
    assert fotmob.status_meczu({"started": True, "finished": False}) == "inprogress"


def test_ten_sam_adres_tylko_raz(siec):
    siec["kolejka"].append(Odp(dane={"content": {}}))
    fotmob.szczegoly_meczu(1)
    fotmob.szczegoly_meczu(1)
    assert len(siec["adresy"]) == 1
    assert fotmob.statystyki()["z_pamieci"] == 1


@pytest.mark.parametrize("odp", [
    Odp(kod=403),
    Odp(kod=429),
    Odp(kod=200, naglowki={"cf-mitigated": "challenge"}),
    Odp(kod=200, typ="text/html", tekst="<html><title>Just a moment...</title>"),
])
def test_odmowa_wstrzymuje_zrodlo_bez_kolejnych_zapytan(siec, odp):
    """Po odmowie żadne kolejne wywołanie nie wychodzi do sieci (statshub
    pokazał, że ponawianie po odcięciu tylko pogarsza sprawę)."""
    siec["kolejka"].append(odp)
    with pytest.raises(fotmob.FotmobOdmowa):
        fotmob.szczegoly_meczu(1)
    with pytest.raises(fotmob.FotmobOdmowa):
        fotmob.szczegoly_meczu(2)
    assert len(siec["adresy"]) == 1
    assert fotmob.statystyki()["odmowa"]


def test_jedno_ponowienie_po_bledzie_serwera(siec):
    siec["kolejka"] += [Odp(kod=502), Odp(dane={"ok": 1})]
    assert fotmob.szczegoly_meczu(5) == {"ok": 1}
    assert fotmob.statystyki()["ponowienia"] == 1


def test_dwa_bledy_z_rzedu_rzucaja_bez_wstrzymania(siec):
    siec["kolejka"] += [TimeoutError("t"), Odp(kod=503)]
    with pytest.raises(RuntimeError):
        fotmob.szczegoly_meczu(5)
    assert not fotmob.statystyki()["odmowa"]          # awaria ≠ odmowa


def test_limit_zapytan_w_procesie(siec, monkeypatch):
    monkeypatch.setattr(fotmob, "LIMIT_ZAPYTAN", 2)
    siec["kolejka"] += [Odp(dane={}), Odp(dane={})]
    fotmob.szczegoly_meczu(1)
    fotmob.szczegoly_meczu(2)
    with pytest.raises(fotmob.FotmobLimit):
        fotmob.szczegoly_meczu(3)
    assert len(siec["adresy"]) == 2


def test_odstep_miedzy_zapytaniami(monkeypatch):
    """Tempo: każde zapytanie czeka co najmniej ODSTEP_S od poprzedniego."""
    fotmob.wyczysc()
    zegar = {"t": 1000.0}
    spane = []
    monkeypatch.setattr(fotmob.time, "monotonic", lambda: zegar["t"])
    monkeypatch.setattr(fotmob.time, "sleep", lambda s: (spane.append(s), zegar.__setitem__("t", zegar["t"] + s)))
    monkeypatch.setattr(fotmob.random, "uniform", lambda a, b: 0.5)
    monkeypatch.setattr(fotmob.requests, "get", lambda url, **kw: Odp(dane={}))
    fotmob.szczegoly_meczu(1)
    fotmob.szczegoly_meczu(2)
    assert spane and spane[-1] == pytest.approx(fotmob.ODSTEP_S + 0.5)
    fotmob.wyczysc()
