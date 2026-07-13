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
