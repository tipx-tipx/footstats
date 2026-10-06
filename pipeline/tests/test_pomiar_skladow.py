"""Pomiar przewidywanych składów per źródło (2026-10-06) — bez sieci."""
from footstats.jobs import pomiar_skladow as P
from footstats.sources.rotowire import _norm

T = 1_800_000_000
MECZE = [{"id": 7, "k": T + 7200, "h": "Real Madrid", "a": "Villarreal", "h_id": 1, "a_id": 2},
         {"id": 8, "k": T - 60, "h": "A", "a": "B", "h_id": 3, "a_id": 4}]   # po gwizdku
SH = {7: {"xi_by_team": {1: {11, 12}, 2: {21}}, "confirmed": False, "zrodlo": "statshub przewidywany"}}
ROTO = {"real madrid": {"xi": {"vinicius junior", "jude bellingham"}, "confirmed": False}}
SG = {"villarreal": {"xi": {"gerard moreno"}, "confirmed": True}}


def test_scal_zapisuje_kazde_zrodlo_osobno():
    stan = {}
    assert P.scal(stan, MECZE, SH, ROTO, SG, _norm, T) == 1
    w = stan["7"]
    assert set(stan) == {"7"}                                    # mecz po gwizdku pominięty
    assert w["statshub"]["pierwszy"]["h"] == [11, 12] and w["statshub"]["pierwszy"]["a"] == [21]
    assert w["rotowire"]["pierwszy"]["h"] == ["jude bellingham", "vinicius junior"]
    assert w["rotowire"]["pierwszy"]["a"] == []
    assert w["sportsgambler"]["pierwszy"]["a"] == ["gerard moreno"]
    assert w["sportsgambler"]["pierwszy"]["pot"] is True
    assert "ogloszony" not in w


def test_pierwszy_zostaje_ostatni_sie_zmienia():
    stan = {}
    P.scal(stan, MECZE, SH, ROTO, SG, _norm, T)
    assert P.scal(stan, MECZE, SH, ROTO, SG, _norm, T + 600) == 0        # bez zmian
    sh2 = {7: {"xi_by_team": {1: {11, 13}, 2: {21}}, "confirmed": False}}
    assert P.scal(stan, MECZE, sh2, ROTO, SG, _norm, T + 1200) == 1
    s = stan["7"]["statshub"]
    assert s["pierwszy"]["h"] == [11, 12] and s["ostatni"]["h"] == [11, 13]
    assert s["ostatni"]["ts"] == T + 1200


def test_ogloszony_raz_i_nie_nadpisuje_przewidywania():
    stan = {}
    P.scal(stan, MECZE, SH, ROTO, SG, _norm, T)
    off = {7: {"xi_by_team": {1: {11, 14}, 2: {22}}, "confirmed": True, "zrodlo": "statshub oficjalny"}}
    P.scal(stan, MECZE, off, ROTO, SG, _norm, T + 3000)
    w = stan["7"]
    assert w["ogloszony"]["h"] == [11, 14] and w["ogloszony"]["ts"] == T + 3000
    assert w["statshub"]["ostatni"]["h"] == [11, 12]                     # przewidywany zostaje


def test_mecz_po_gwizdku_zamrozony_i_retencja():
    stan = {}
    P.scal(stan, MECZE, SH, ROTO, SG, _norm, T)
    sh2 = {7: {"xi_by_team": {1: {99}}, "confirmed": False}}
    assert P.scal(stan, MECZE, sh2, ROTO, SG, _norm, T + 7200) == 0      # kickoff == teraz
    P.scal(stan, [], {}, {}, {}, _norm, T + 7200 + P.RETENCJA_S + 1)
    assert stan == {}


def test_zapis_nie_rusza_po_padnietym_odczycie(monkeypatch):
    zapisy = []
    monkeypatch.setattr(P.magazyn_repo, "pobierz", lambda k: (None, False))
    monkeypatch.setattr(P.magazyn_repo, "zapisz", lambda k, p: zapisy.append(k) or True)
    assert "ODCZYT PADŁ" in P.zapisz(MECZE, SH, ROTO, SG, _norm, T) and zapisy == []


def test_zapis_dopisuje(monkeypatch):
    zapisy = {}
    monkeypatch.setattr(P.magazyn_repo, "pobierz", lambda k: ({}, True))
    monkeypatch.setattr(P.magazyn_repo, "zapisz", lambda k, p: zapisy.update({k: p}) or True)
    opis = P.zapisz(MECZE, SH, ROTO, SG, _norm, T)
    assert "7" in zapisy["pomiar_skladow"] and "1 zmian" in opis
