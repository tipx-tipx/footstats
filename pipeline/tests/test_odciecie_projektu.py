# -*- coding: utf-8 -*-
"""ODCIĘCIE PROJEKTU PRZEZ SUPABASE (2026-08-28).

Gdy miesięczny limit transferu się wyczerpie, Supabase odcina cały projekt:
każde zapytanie z kluczem wraca jako 402 „exceed_egress_quota" — i odczyt,
i zapis. Od 25.08 znaczyło to czerwony cykl co godzinę i tyle samo maili
„workflow failed", w których nie było czego naprawiać: kod jest sprawny,
płatny jest dostęp do bazy.

Czerwony job ma znaczyć „coś do naprawienia w kodzie", więc odcięcie kończy
przebieg zielono, ale z ostrzeżeniem. KAŻDY inny błąd musi dalej wywalać job
na czerwono — inaczej strażnik zamiótłby pod dywan realną awarię.
"""
import pytest

from footstats import supa


class _Odp:
    def __init__(self, status, tresc=None):
        self.status_code = status
        self._tresc = tresc if tresc is not None else {}
        self.text = "…"

    def json(self):
        return self._tresc


@pytest.fixture(autouse=True)
def _czysty_stan(monkeypatch):
    """Znacznik odcięcia jest globalny na przebieg — testy nie mogą go dziedziczyć."""
    monkeypatch.setattr(supa, "_odciecie", None)
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)


KOMUNIKAT = ("Service for this project is restricted due to the following "
             "violations: exceed_egress_quota.")


def test_402_zostawia_slad_z_komunikatem_bazy():
    supa._z_ponowieniem("test", lambda: _Odp(402, {"message": KOMUNIKAT}))
    assert supa.odciecie_projektu() == KOMUNIKAT


def test_402_nie_jest_ponawiane():
    """To nie jest mrugnięcie sieci — powtórka wróci z tym samym 402."""
    proby = []

    def _woła():
        proby.append(1)
        return _Odp(402, {"message": KOMUNIKAT})

    supa._z_ponowieniem("test", _woła)
    assert len(proby) == 1


def test_straz_konczy_job_zielono_z_ostrzezeniem(monkeypatch, capsys):
    monkeypatch.setattr(supa, "_conn", lambda: ("https://x", {}))
    monkeypatch.setattr(supa.requests, "get",
                        lambda *a, **k: _Odp(402, {"message": KOMUNIKAT}))
    with pytest.raises(SystemExit) as wyj:
        supa.straz_odciecia("cykl")
    assert wyj.value.code == 0
    wyjscie = capsys.readouterr().out
    assert "::warning" in wyjscie and "402" in wyjscie


def test_zdrowa_baza_przepuszcza_job(monkeypatch):
    """Bez odcięcia strażnik ma być niewidoczny — job leci dalej normalnie."""
    monkeypatch.setattr(supa, "_conn", lambda: ("https://x", {}))
    monkeypatch.setattr(supa.requests, "get", lambda *a, **k: _Odp(200, []))
    supa.straz_odciecia("cykl")
    assert supa.odciecie_projektu() is None


def test_tryb_lokalny_nie_pyta_bazy(monkeypatch):
    """Bez sekretów (lokalnie) nie ma czego badać ani czym się blokować."""
    monkeypatch.setattr(supa, "_conn", lambda: None)
    monkeypatch.setattr(supa.requests, "get", lambda *a, **k: pytest.fail(
        "tryb lokalny nie powinien wołać Supabase"))
    supa.straz_odciecia("cykl")


def test_straz_bez_badania_nie_wola_sieci(monkeypatch):
    """Wołanie z łapania wyjątku: wiemy już z przebiegu, czy padło na 402."""
    monkeypatch.setattr(supa, "_conn", lambda: ("https://x", {}))
    monkeypatch.setattr(supa.requests, "get", lambda *a, **k: pytest.fail(
        "badaj=False nie ma prawa dokładać zapytania"))
    supa.straz_odciecia("cykl", badaj=False)
    monkeypatch.setattr(supa, "_odciecie", KOMUNIKAT)
    with pytest.raises(SystemExit) as wyj:
        supa.straz_odciecia("cykl", badaj=False)
    assert wyj.value.code == 0
