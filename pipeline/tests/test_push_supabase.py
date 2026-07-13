"""Test regresyjny na P0: awaria w środku cyklu nie może cofnąć danych
produkcyjnych w Supabase do starych/pustych plików ze świeżego `git checkout`.

Mechanizm: build_wc_fast._main_impl (i build_demo._main_impl) zapisują
_manifest.json z listą kluczy faktycznie wygenerowanych W TYM uruchomieniu.
push_supabase.push() ma pushować WYŁĄCZNIE te klucze, gdy manifest istnieje.
"""
from __future__ import annotations

import json

import curl_cffi.requests as curl_requests

from footstats.jobs import push_supabase


def _write(dir_, name, payload):
    (dir_ / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def _fake_post_ok(calls):
    class _Resp:
        status_code = 200
        text = ""

    def _post(url, headers=None, data=None, **kw):
        calls.append(json.loads(data))
        return _Resp()

    return _post


def test_push_respects_manifest_skips_stale_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(push_supabase, "WEB_DATA_DIR", tmp_path)
    monkeypatch.setenv("SUPABASE_URL", "https://example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "dummy")

    # value_bets.json = "stary" plik ze świeżego checkoutu (NIE wygenerowany
    # w tym cyklu — statshub padł zanim doszło do dumpu). typy_wyniki.json =
    # faktycznie świeżo policzony przez rozliczanie w tym cyklu.
    _write(tmp_path, "value_bets", [{"stary": True}])
    _write(tmp_path, "typy_wyniki", {"swiezy": True})
    _write(tmp_path, "_manifest", {"keys": ["typy_wyniki"]})

    calls: list = []
    monkeypatch.setattr(curl_requests, "post", _fake_post_ok(calls))

    assert push_supabase.push() is True
    assert len(calls) == 1
    pushed_keys = {row["key"] for row in calls[0]}
    assert pushed_keys == {"typy_wyniki"}
    assert "value_bets" not in pushed_keys


def test_push_without_manifest_falls_back_to_all_present(tmp_path, monkeypatch):
    monkeypatch.setattr(push_supabase, "WEB_DATA_DIR", tmp_path)
    monkeypatch.setenv("SUPABASE_URL", "https://example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "dummy")

    _write(tmp_path, "value_bets", [{"ok": True}])
    _write(tmp_path, "typy_wyniki", {"ok": True})
    # brak _manifest.json — stare zachowanie (np. ręczne lokalne odpalenie)

    calls: list = []
    monkeypatch.setattr(curl_requests, "post", _fake_post_ok(calls))

    assert push_supabase.push() is True
    pushed_keys = {row["key"] for row in calls[0]}
    assert pushed_keys == {"value_bets", "typy_wyniki"}


def test_push_empty_manifest_pushes_nothing(tmp_path, monkeypatch):
    # scenariusz P0 realny: build_demo._main_impl wraca WCZEŚNIE (za mało
    # meczów w magazynie) przed jakimkolwiek dump() — manifest pusty.
    monkeypatch.setattr(push_supabase, "WEB_DATA_DIR", tmp_path)
    monkeypatch.setenv("SUPABASE_URL", "https://example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "dummy")

    _write(tmp_path, "value_bets", [{"stary": True}])
    _write(tmp_path, "_manifest", {"keys": []})

    calls: list = []
    monkeypatch.setattr(curl_requests, "post", _fake_post_ok(calls))

    assert push_supabase.push() is False
    assert calls == []
