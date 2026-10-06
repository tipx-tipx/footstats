"""Archiwum oferty zawodniczej (2026-10-06) — bez sieci."""
import time

from footstats.jobs import archiwum_ofert as A

T = int(time.mktime((2026, 10, 10, 12, 0, 0, 0, 0, 0)))
KD = {7: {101: {"shots": {"0.5": [1.4, 1.45], "1.5": [2.6, None]}}},
      8: {102: {"sot": {"0.5": [2.1, None, 1]}}}}
MECZE = {7: {"kickoff_ts": T + 3600, "sklady_ogloszone": True},
         8: {"kickoff_ts": T - 60}}                       # już po gwizdku


def test_klucz_miesiaca():
    assert A.klucz_miesiaca(T) == "archiwum_ofert_2026_10"


def test_scal_dopisuje_nadchodzace_i_zamraza_rozegrane():
    arch = {}
    assert A.scal(arch, KD, MECZE, T) == 1
    assert set(arch) == {"7"}
    w = arch["7"]
    assert w["k"] == T + 3600 and w["z"] == T and w["p"] == T and w["s"] is True
    assert w["o"] == {"101": {"shots": {"0.5": [1.4, 1.45], "1.5": [2.6, None]}}}


def test_scal_bez_zmian_nie_rusza_i_zachowuje_pierwszy_zrzut():
    arch = {}
    A.scal(arch, KD, MECZE, T)
    assert A.scal(arch, KD, MECZE, T + 600) == 0          # nic nowego
    assert arch["7"]["z"] == T
    kd2 = {7: {101: {"shots": {"0.5": [1.38, 1.45]}}}}
    assert A.scal(arch, kd2, MECZE, T + 1200) == 1         # cena się ruszyła
    assert arch["7"]["z"] == T + 1200 and arch["7"]["p"] == T


def test_mecz_po_gwizdku_nie_jest_nadpisywany():
    arch = {}
    A.scal(arch, KD, MECZE, T)
    kd2 = {7: {101: {"shots": {"0.5": [9.9, 9.9]}}}}
    assert A.scal(arch, kd2, MECZE, T + 3600) == 0         # kickoff == teraz
    assert arch["7"]["o"]["101"]["shots"]["0.5"] == [1.4, 1.45]


def test_scal_tylko_wskazany_miesiac():
    arch = {}
    assert A.scal(arch, KD, MECZE, T, klucz="archiwum_ofert_2026_11") == 0


def test_zapisz_zrzut_nie_zapisuje_po_padnietym_odczycie(monkeypatch):
    zapisy = []
    monkeypatch.setattr(A.magazyn_repo, "pobierz", lambda k: (None, False))
    monkeypatch.setattr(A.magazyn_repo, "zapisz", lambda k, p: zapisy.append(k) or True)
    opis = A.zapisz_zrzut(KD, MECZE, T)
    assert zapisy == [] and "ODCZYT PADŁ" in opis


def test_zapisz_zrzut_dopisuje_do_istniejacego(monkeypatch):
    istniejace = {"5": {"k": T - 86400, "z": T - 90000, "p": T - 90000, "s": True, "o": {}}}
    zapisy = {}
    monkeypatch.setattr(A.magazyn_repo, "pobierz", lambda k: (dict(istniejace), True))
    monkeypatch.setattr(A.magazyn_repo, "zapisz", lambda k, p: zapisy.update({k: p}) or True)
    opis = A.zapisz_zrzut(KD, MECZE, T)
    assert set(zapisy) == {"archiwum_ofert_2026_10"}
    assert set(zapisy["archiwum_ofert_2026_10"]) == {"5", "7"}   # stary mecz został
    assert "+1" in opis


def test_zapisz_zrzut_bez_zmian_nie_zapisuje(monkeypatch):
    arch = {}
    A.scal(arch, KD, MECZE, T)
    zapisy = []
    monkeypatch.setattr(A.magazyn_repo, "pobierz", lambda k: (arch, True))
    monkeypatch.setattr(A.magazyn_repo, "zapisz", lambda k, p: zapisy.append(k) or True)
    assert "bez zmian" in A.zapisz_zrzut(KD, MECZE, T + 60) and zapisy == []


def test_kickoff_w_milisekundach():
    arch = {}
    mecze = {7: {"kickoff_ts": (T - 60) * 1000}}            # po gwizdku, podane w ms
    assert A.scal(arch, KD, mecze, T) == 0
    mecze = {7: {"kickoff_ts": (T + 3600) * 1000}}
    assert A.scal(arch, KD, mecze, T) == 1 and arch["7"]["k"] == T + 3600
