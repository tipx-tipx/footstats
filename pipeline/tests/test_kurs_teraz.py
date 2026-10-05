# -*- coding: utf-8 -*-
"""„Kurs teraz" przy opublikowanym typie (2026-10-05, audyt pkt 16)."""
from footstats.jobs import build_wc_fast as B

from test_publikacje import _bet, _stub_supa


def test_siatka_i_stempel():
    oferta = {1: {7: {"shots": {"0.5": 1.29}}}}
    zrodla = {1: {7: {"shots": {"0.5": "Betclic"}}}}
    assert B.kurs_z_siatki(oferta, zrodla, 1, 7, "shots", 0.5) == (1.29, "Betclic")
    assert B.kurs_z_siatki(oferta, None, 1, 7, "shots", 1.5) is None
    b = {"kurs": 1.61}
    assert B.stempluj_kurs_teraz(b, (1.29, "Superbet")) and b["kurs_teraz"] == 1.29
    assert not B.stempluj_kurs_teraz(b, (1.61, "Superbet")) and "kurs_teraz" not in b


def test_typ_pokazany_wczesniej_dostaje_kurs_teraz(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    B.scal_z_publikacjami([_bet(kurs=1.61)], {1: {"id": 1}}, teraz=1000)
    log = {"x": {**_bet(kurs=1.61), "wynik": None}}
    out, _ = B.scal_z_publikacjami([_bet(kurs=1.29)], {1: {"id": 1}}, teraz=5000,
                                   typy_log=log)
    assert out[0]["kurs"] == 1.61 and out[0]["kurs_teraz"] == 1.29
