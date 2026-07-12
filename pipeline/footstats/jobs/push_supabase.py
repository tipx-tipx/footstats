"""Wypchnij wygenerowane dane (JSON) do Supabase, żeby aplikacja na Vercel je czytała.

Czyta web/src/data/demo/*.json i upsertuje do tabeli app_data (klucz -> JSONB).
Wywoływane na końcu każdego cyklu (cycle.py), jeśli ustawione są zmienne środowiskowe:
    SUPABASE_URL          np. https://xxxx.supabase.co
    SUPABASE_SERVICE_KEY  klucz service_role (NIE anon — service omija RLS przy zapisie)

Bez tych zmiennych job cicho się pomija (tryb lokalny: aplikacja czyta pliki).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WEB_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "web" / "src" / "data" / "demo"
KEYS = ["value_bets", "matches", "players", "calibration", "meta", "kupony",
        "typy_wyniki", "odds_superbet", "legi_pool"]


def push() -> bool:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return False

    from curl_cffi import requests

    rows = []
    for name in KEYS:
        f = WEB_DATA_DIR / f"{name}.json"
        if f.exists():
            rows.append({"key": name, "payload": json.loads(f.read_text(encoding="utf-8"))})
    if not rows:
        return False

    # upsert (on_conflict=key) do PostgREST
    r = requests.post(
        f"{url}/rest/v1/app_data?on_conflict=key",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        data=json.dumps(rows),
        impersonate="chrome124",
        timeout=30,
    )
    if r.status_code >= 300:
        print(f"Supabase push błąd {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return False
    print(f"Supabase: wypchnięto {len(rows)} snapshotów.")
    return True


if __name__ == "__main__":
    if not push():
        print("Supabase pominięty (brak SUPABASE_URL / SUPABASE_SERVICE_KEY).")
