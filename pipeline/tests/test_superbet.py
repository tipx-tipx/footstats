"""P2: superbet._get nie miało retry (kontrast ze statshub._get/http_client) —
jeden nieudany request i mecz zostawał bez kursów Superbet do następnego
cyklu. Testy niżej bez sieci i bez realnego czekania (time.sleep zaślepiony)."""
from __future__ import annotations

import time as time_mod

import pytest

from footstats.sources import superbet


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(time_mod, "sleep", lambda s: None)


def test_get_retries_after_transient_error_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def _fake_get(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("timeout")
        return _Resp(200, {"data": [1, 2, 3]})

    monkeypatch.setattr(superbet.requests, "get", _fake_get)
    out = superbet._get("http://x")
    assert out == {"data": [1, 2, 3]}
    assert calls["n"] == 3


def test_get_retries_on_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def _fake_get(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            return _Resp(429)
        return _Resp(200, {"ok": True})

    monkeypatch.setattr(superbet.requests, "get", _fake_get)
    assert superbet._get("http://x") == {"ok": True}
    assert calls["n"] == 2


def test_get_raises_after_exhausting_retries(monkeypatch):
    calls = {"n": 0}

    def _fake_get(*a, **kw):
        calls["n"] += 1
        return _Resp(500)

    monkeypatch.setattr(superbet.requests, "get", _fake_get)
    with pytest.raises(RuntimeError):
        superbet._get("http://x", retries=3)
    assert calls["n"] == 3


# --- „KTO WIĘCEJ" I SUMY MECZOWE (2026-07-30) ------------------------------


def _oferta(odds, monkeypatch):
    monkeypatch.setattr(superbet, "_get", lambda url: {"data": [{"odds": odds}]})
    return superbet.fetch_stat_odds(1, "Corinthians", "Athletico PR")


def _kurs(mname, oname, price, **spec):
    return {"marketName": mname, "name": oname, "price": price,
            "status": "active", "specifiers": spec or None}


def test_kto_wiecej_po_nazwach_druzyn(monkeypatch):
    """Rynek ma TRZY wyniki, a Superbet nazywa je raz nazwą drużyny."""
    d = _oferta([
        _kurs("Najwięcej strzałów", "Corinthians", 1.46),
        _kurs("Najwięcej strzałów", "Remis", 13.0),
        _kurs("Najwięcej strzałów", "Athletico PR", 2.90),
    ], monkeypatch)
    assert d["porownania"]["team_shots"] == {
        "home": 1.46, "remis": 13.0, "away": 2.90,
    }


def test_kto_wiecej_po_symbolach_1x2(monkeypatch):
    """...a raz „1"/„X"/„2" — ten sam rynek, inny zapis wyniku."""
    d = _oferta([
        _kurs("Najwięcej kartek", "1", 2.47),
        _kurs("Najwięcej kartek", "X", 4.30),
        _kurs("Najwięcej kartek", "2", 2.07),
    ], monkeypatch)
    assert d["porownania"]["team_cards"] == {
        "home": 2.47, "remis": 4.30, "away": 2.07,
    }


def test_kto_wiecej_pomija_polowy_i_okna_minutowe(monkeypatch):
    """Model liczy pełny mecz — połówki i okna minutowe to nie nasz zakład."""
    d = _oferta([
        _kurs("1. połowa - najwięcej rzutów rożnych", "Corinthians", 2.0),
        _kurs("Najwięcej fauli od 0:00 do 9:59 minuty", "Corinthians", 2.0),
    ], monkeypatch)
    assert d["porownania"] == {}


def test_suma_meczowa_roznych_wchodzi_z_obiema_stronami(monkeypatch):
    """„Liczba rzutów rożnych" to 42 kwotowania na mecz, a do 2026-07-30
    czytaliśmy sumy meczowe WYŁĄCZNIE dla goli — reszta leżała odłogiem."""
    d = _oferta([
        _kurs("Liczba rzutów rożnych", "Powyżej 9.5", 1.85, total="9.5"),
        _kurs("Liczba rzutów rożnych", "Poniżej 9.5", 1.95, total="9.5"),
    ], monkeypatch)
    assert d["sumy"]["match_corners"][9.5] == {"over": 1.85, "under": 1.95}


def test_suma_meczowa_nie_kradnie_rynku_druzynowego(monkeypatch):
    """„Liczba strzałów Corinthians" to rynek DRUŻYNY, a „Liczba strzałów"
    bez nazwy — suma meczowa. Dopasowanie jest po PEŁNEJ nazwie, więc jedno
    nie może zjeść drugiego."""
    d = _oferta([
        _kurs("Liczba strzałów", "Powyżej 22.5", 1.60, total="22.5"),
        _kurs("Liczba strzałów Corinthians", "Powyżej 10.5", 1.90, total="10.5"),
    ], monkeypatch)
    assert d["sumy"]["match_shots"][22.5]["over"] == 1.60
    assert d["teams"]["home"]["team_shots"][10.5]["over"] == 1.90


def test_gole_dalej_ida_stara_sciezka(monkeypatch):
    """Total goli ma własną ścieżkę (tempo/scenariusz meczu) — nowe rynki
    nie mogą jej przejąć."""
    d = _oferta([
        _kurs("Liczba goli", "Powyżej 2.5", 1.90, total="2.5"),
    ], monkeypatch)
    assert d["match"]["totals"][2.5]["over"] == 1.90
    assert "match_goals" not in d["sumy"]
