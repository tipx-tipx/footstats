# -*- coding: utf-8 -*-
"""ŚLAD PO PADNIĘTYM CYKLU (2026-08-13).

Cykl pada raz na kilkanaście przebiegów (13.08: dwa razy na szesnaście) i za
każdym razem traciliśmy diagnozę w całości: traceback szedł wyłącznie na
stderr, czyli do logu GitHub Actions, a tego bez tokena nie da się pobrać.
Zostawało „padło i tyle".

Te testy pilnują trzech rzeczy: że ślad powstaje, że NIE niesie sekretów
i że awaria samego zapisu nie przykrywa awarii, którą opisuje.
"""
import pytest

from footstats.jobs import cycle


class _Supa:
    """Atrapa bazy: pamięta zapisany klucz i umie udawać padnięty odczyt."""

    def __init__(self, stan=None, odczyt_ok=True):
        self.stan = stan
        self.odczyt_ok = odczyt_ok
        self.zapisane = None

    def get_key_ok(self, key):
        return (self.stan, self.odczyt_ok)

    def put_key(self, key, payload):
        self.zapisane = (key, payload)
        return True


@pytest.fixture
def supa(monkeypatch):
    atrapa = _Supa()
    monkeypatch.setattr("footstats.supa.get_key_ok", atrapa.get_key_ok)
    monkeypatch.setattr("footstats.supa.put_key", atrapa.put_key)
    return atrapa


def _wyjatek(tresc="coś padło"):
    try:
        raise RuntimeError(tresc)
    except RuntimeError as ex:
        return ex


def test_slad_zapisuje_gdzie_stanal_cykl(supa):
    cycle._zapisz_slad_awarii("2026-08-13 20:00:00", 37.6, _wyjatek())
    klucz, lista = supa.zapisane
    assert klucz == cycle.KLUCZ_AWARII
    wpis = lista[-1]
    assert wpis["minuty"] == 37.6
    assert wpis["wyjatek"] == "RuntimeError"
    assert wpis["komunikat"] == "coś padło"
    # ślad ma wskazywać PLIK I LINIĘ, inaczej nie wiadomo, gdzie szukać
    assert wpis["slad"] and "test_slad_awarii.py:" in wpis["slad"][-1]


def test_slad_dokleja_sie_do_historii_i_przycina(supa):
    supa.stan = [{"kiedy": f"stary {i}"} for i in range(cycle.AWARIE_ILE + 5)]
    cycle._zapisz_slad_awarii("2026-08-13 20:00:00", 1.0, _wyjatek())
    _, lista = supa.zapisane
    assert len(lista) == cycle.AWARIE_ILE
    assert lista[-1]["wyjatek"] == "RuntimeError"      # najnowsze na końcu
    assert lista[0]["kiedy"] != "stary 0"              # najstarsze wypadły


def test_slad_nie_wpuszcza_sekretow_do_bazy():
    """Wyjątek sieciowy potrafi nieść cały URL z kluczem albo nagłówek
    Authorization. Ślad ma być diagnostyką, nie wyciekiem."""
    brudne = (
        "401 dla https://abcdefgh.supabase.co/rest/v1/app_data?apikey=tajne123"
        " (Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9zzz)"
    )
    czyste = cycle._bez_sekretow(brudne)
    for zakazane in ("tajne123", "abcdefgh.supabase.co", "eyJhbGciOiJIUzI1NiI"):
        assert zakazane not in czyste
    assert "401" in czyste and "app_data" in czyste   # diagnostyka zostaje


def test_nieudany_odczyt_nie_kasuje_historii(supa):
    """Gdy baza nie oddaje poprzedniej listy, NIE zapisujemy — inaczej jeden
    nieudany odczyt kasuje całą historię awarii (ta sama pułapka co przy
    księdze typów)."""
    supa.odczyt_ok = False
    supa.stan = None
    cycle._zapisz_slad_awarii("2026-08-13 20:00:00", 1.0, _wyjatek())
    assert supa.zapisane is None


def test_awaria_zapisu_nie_przykrywa_awarii_cyklu(monkeypatch):
    """Gdyby zapis śladu sam rzucił, cykl ma dalej zgłosić SWÓJ błąd."""
    def _pad(*a, **k):
        raise ConnectionError("baza nie odpowiada")

    monkeypatch.setattr("footstats.supa.get_key_ok", _pad)
    # nie rzuca — wyjątek zapisu jest połykany, bo opisujemy inną awarię
    cycle._zapisz_slad_awarii("2026-08-13 20:00:00", 1.0, _wyjatek())


def test_klucz_awarii_nie_jest_publiczny():
    """Ślad niesie treść wyjątków — nie ma prawa trafić na listę kluczy
    czytanych przez anona (migracja 0004)."""
    from pathlib import Path
    rls = Path(__file__).resolve().parents[2] / "supabase" / "migrations" \
        / "0004_app_data_rls.sql"
    assert cycle.KLUCZ_AWARII not in rls.read_text(encoding="utf-8")
