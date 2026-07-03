"""Wspólny dostęp do Supabase app_data (klucz -> JSONB) dla pipeline'u.

Używane przez: bank trendów (trend_lib), log typów (typy_log), push snapshotów.
Brak env SUPABASE_URL / SUPABASE_SERVICE_KEY = tryb lokalny (zwraca puste).
"""

from __future__ import annotations

import json
import os

from curl_cffi import requests


def _conn() -> tuple[str, dict] | None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    return url, {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def get_key(key: str):
    """Pobierz payload spod klucza (None gdy brak/niedostępne)."""
    c = _conn()
    if c is None:
        return None
    url, headers = c
    try:
        r = requests.get(
            f"{url}/rest/v1/app_data?select=payload&key=eq.{key}",
            headers=headers, impersonate="chrome124", timeout=30,
        )
        rows = r.json() if r.status_code == 200 else []
        return rows[0]["payload"] if rows else None
    except Exception:
        return None


def put_key(key: str, payload) -> bool:
    """Upsert payloadu pod klucz. True = zapisano."""
    c = _conn()
    if c is None:
        return False
    url, headers = c
    try:
        r = requests.post(
            f"{url}/rest/v1/app_data?on_conflict=key",
            headers={**headers, "Prefer": "resolution=merge-duplicates"},
            data=json.dumps([{"key": key, "payload": payload}]),
            impersonate="chrome124", timeout=60,
        )
        return r.status_code < 300
    except Exception:
        return False
