# -*- coding: utf-8 -*-
"""Karta z hero na rynku wycofanym nie zajmuje miejsca w limicie dnia
(2026-10-05, audyt pkt 4: Katić, odbiory 1,5 z 03.10 wracał co cykl
z rejestru i spadał dopiero po scaleniu — „karty 5 → 4")."""
import inspect
import time

from footstats.jobs import build_wc_fast as B
from footstats.jobs import radar

from test_publikacje import _karta, _stub_supa


def _karta_odbiory(pid, ko):
    k = _karta(pid=pid, kickoff_ts=ko)
    k["hero"]["rynek_kod"] = "tackles"
    k["rynki"] = [{"rynek_kod": "tackles"}, {"rynek_kod": "fouls_won"}]
    return k


def test_wznowiona_karta_na_wycofanym_rynku_nie_zajmuje_limitu(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    ko = int(time.time()) + 7200
    # rejestr: karta na odbiorach opublikowana wcześniej (sprzed poprawki)
    magazyn[B.PUBLIKACJE_KART_KLUCZ] = {
        "9:5:tackles:2.5": {"wpis": _karta_odbiory(5, ko), "kickoff_ts": ko,
                            "opublikowano_ts": 1},
    }
    monkeypatch.setattr(radar, "MAX_KART_DZIEN", 1)
    out = B.scal_karty_z_publikacjami([_karta(pid=6, kickoff_ts=ko)])
    # nowa karta weszła, bo wycofana nie zajęła jedynego miejsca dnia
    assert [w["podmiot_id"] for w in out] == [6]
    # wpis zostaje w rejestrze do gwizdka (historii nie kasujemy)
    assert "9:5:tackles:2.5" in magazyn[B.PUBLIKACJE_KART_KLUCZ]


def test_wznowiona_karta_traci_tylko_wycofany_rynek_poboczny(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    ko = int(time.time()) + 7200
    k = _karta(pid=7, kickoff_ts=ko)
    k["rynki"] = [{"rynek_kod": "shots"}, {"rynek_kod": "tackles"}]
    magazyn[B.PUBLIKACJE_KART_KLUCZ] = {
        "9:7:shots:2.5": {"wpis": k, "kickoff_ts": ko, "opublikowano_ts": 1}}
    out = B.scal_karty_z_publikacjami([])
    assert len(out) == 1 and [r["rynek_kod"] for r in out[0]["rynki"]] == ["shots"]


def test_radar_zdejmuje_wycofane_rynki_przed_ocena_karty():
    zr = inspect.getsource(radar.zbuduj)
    i_zdj = zr.index("betting.rynek_wycofany(r.get(\"rynek_kod\"))")
    i_ocena = zr.index("score, hero = _oceń_karte(")
    assert i_zdj < i_ocena
