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
# "calibration" NIE jest generowane przez build_wc_fast.py (tryb MŚ) — tylko
# przez build_demo.py (tryb ligowy). To NIE martwy klucz: /model faktycznie
# renderuje getKalibracja() ("Kalibracja po rynkach", jednorazowy backtest
# silnika na Premier League — dowód, że rdzeń modelu działa, obok bieżącej
# diagnostyki MŚ z typy_wyniki). Manifest (patrz build_wc_fast._generated_
# this_run) chroni tę wartość przed nadpisaniem starym plikiem z checkoutu —
# cykl MŚ po prostu nigdy jej nie dotyka, zostaje ostatni zapis build_demo.
KEYS = ["value_bets", "matches", "players", "calibration", "meta", "kupony",
        "typy_wyniki", "odds_superbet", "legi_pool", "odrzucenia"]


def push() -> bool:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return False

    from curl_cffi import requests

    # Jeśli job zostawił manifest (_manifest.json = klucze faktycznie
    # zapisane W TYM uruchomieniu), pushujemy WYŁĄCZNIE te klucze. Bez tego
    # przy wczesnym przerwaniu cyklu (np. statshub padł w środku) pliki
    # niedotknięte w tym uruchomieniu zostają w wersji ze świeżego
    # `git checkout` (stare/puste dane commitowane w repo) i zostałyby
    # cicho wypchnięte na produkcję, nadpisując żywe dane starymi.
    # Brak manifestu (stare joby, np. build_demo.py, lub ręczne odpalenie
    # bez pełnego przebiegu) = stare zachowanie: push wszystkiego co jest.
    manifest = WEB_DATA_DIR / "_manifest.json"
    generated: set[str] | None = None
    if manifest.exists():
        try:
            generated = set(json.loads(manifest.read_text(encoding="utf-8")).get("keys", []))
        except Exception:
            generated = None

    rows = []
    for name in KEYS:
        if generated is not None and name not in generated:
            print(f"Supabase: pomijam '{name}' (niewygenerowany w tym cyklu).")
            continue
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
