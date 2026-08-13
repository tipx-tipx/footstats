# -*- coding: utf-8 -*-
"""PONOWIENIA ZAPYTAŃ DO SUPABASE (2026-08-13).

Do dziś każde zapytanie szło raz i tyle. To bolało najbardziej na końcu cyklu:
`push_supabase.push()` wysyła ~4,9 MB w jednym POST po ~31 minutach liczenia,
a jego porażka wraca do `cycle.py`, tam podnosi RuntimeError i wywala cały job.
Jedno mrugnięcie sieci na runnerze kasowało pół godziny pracy i zostawiało
stronę z danymi sprzed godzin (13.08: dwa takie pady na szesnaście przebiegów,
po 31,0 i 37,6 min, oba przy ZDROWYM limicie 70 min).

Wszystkie nasze zapytania są idempotentne (GET, upsert `on_conflict=key`),
więc ponowienie niczego nie dubluje.
"""
import pytest

from footstats import supa


class _Odp:
    def __init__(self, status):
        self.status_code = status
        self.text = "…"

    def json(self):
        return []


def test_ponawia_piatki_i_oddaje_sukces(monkeypatch):
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)
    wyniki = iter([_Odp(503), _Odp(500), _Odp(200)])
    proby = []

    def _woła():
        proby.append(1)
        return next(wyniki)

    r = supa._z_ponowieniem("test", _woła)
    assert r.status_code == 200
    assert len(proby) == 3


def test_ponawia_wyjatki_sieciowe(monkeypatch):
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)
    stan = {"i": 0}

    def _woła():
        stan["i"] += 1
        if stan["i"] < 3:
            raise ConnectionError("zerwane połączenie")
        return _Odp(200)

    assert supa._z_ponowieniem("test", _woła).status_code == 200
    assert stan["i"] == 3


def test_nie_ponawia_bledu_po_naszej_stronie(monkeypatch):
    """4xx to zły klucz albo zły JSON — powtarzanie tego tylko przedłuża job."""
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)
    proby = []

    def _woła():
        proby.append(1)
        return _Odp(401)

    assert supa._z_ponowieniem("test", _woła).status_code == 401
    assert len(proby) == 1


def test_ponawia_przeciazenie(monkeypatch):
    """429 to jedyny 4xx wart ponowienia — baza prosi o zwolnienie."""
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)
    wyniki = iter([_Odp(429), _Odp(200)])
    assert supa._z_ponowieniem("test", lambda: next(wyniki)).status_code == 200


def test_po_wyczerpaniu_prob_oddaje_ostatnia_odpowiedz(monkeypatch):
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)
    proby = []

    def _woła():
        proby.append(1)
        return _Odp(500)

    r = supa._z_ponowieniem("test", _woła)
    assert r.status_code == 500
    assert len(proby) == supa.PROBY_SIECI


def test_same_wyjatki_do_konca_daja_none(monkeypatch):
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)

    def _woła():
        raise TimeoutError("timeout")

    assert supa._z_ponowieniem("test", _woła) is None


def test_zapis_przezywa_chwilowa_awarie(monkeypatch):
    """`put_key` ma wrócić True, gdy druga próba się uda — inaczej cykl
    zgłasza utratę danych, których wcale nie stracił."""
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)
    monkeypatch.setattr(supa, "_conn", lambda: ("https://x", {}))
    wyniki = iter([_Odp(503), _Odp(201)])
    monkeypatch.setattr(supa.requests, "post", lambda *a, **k: next(wyniki))
    assert supa.put_key("test", {"a": 1}) is True


def test_odczyt_przezywa_chwilowa_awarie(monkeypatch):
    """Padnięty odczyt oznacza „nie zapisuj" w połowie pipeline'u — chwilowa
    awaria nie może więc wstrzymywać zapisów bez próby ponowienia."""
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)
    monkeypatch.setattr(supa, "_conn", lambda: ("https://x", {}))
    wyniki = iter([_Odp(500), _Odp(200)])
    monkeypatch.setattr(supa.requests, "get", lambda *a, **k: next(wyniki))
    dane, ok = supa.get_key_ok("test")
    assert ok is True and dane is None
