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
        "typy_wyniki", "odds_superbet", "legi_pool", "odrzucenia", "sts_model",
        "druzyny_forma", "radar",
        # tabela pokrycia (ligi + nasze statystyki) — liczona od dawna, ale do
        # 2026-07-27 lądowała tylko w pliku i nigdy nie docierała na stronę
        "pokrycie_liga"]


def push() -> bool:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return False

    from curl_cffi import requests

    from .. import supa

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

    # upsert (on_conflict=key) do PostgREST — JEDNYM żądaniem, celowo:
    # strona ma zobaczyć komplet danych z tego samego cyklu albo nic. Podział
    # na paczki zostawiałby ją w stanie mieszanym (świeże typy przy starym
    # radarze), co jest gorsze niż jeden cykl opóźnienia.
    #
    # ⚑ PONOWIENIA I TIMEOUT (2026-08-13). Ten POST idzie po ~31 minutach
    # liczenia i niesie ~4,9 MB, a miał `timeout=30` i ZERO ponowień. Jego
    # porażka wraca do `cycle.py` jako False, tam podnosi RuntimeError i wywala
    # cały job — czyli jedno mrugnięcie sieci na runnerze kasowało pół godziny
    # pracy i zostawiało stronę z danymi sprzed godzin. Dwa `failure` z 13.08
    # (po 31,0 i 37,6 min, oba przy zdrowym limicie 70 min) pasują dokładnie do
    # tego momentu cyklu. Upsert jest idempotentny, więc ponowienie niczego
    # nie zdubluje.
    dane = json.dumps(rows)
    print(f"Supabase: wysyłam {len(rows)} snapshotów, {len(dane) / 1e6:.2f} MB")
    r = supa._z_ponowieniem("push snapshotów", lambda: requests.post(
        f"{url}/rest/v1/app_data?on_conflict=key",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        data=dane,
        impersonate="chrome124",
        # 30 s na ~4,9 MB to było ciasno: przy wolniejszej chwili runnera albo
        # dłuższym zapisie JSONB po stronie bazy sam transfer potrafi to zjeść
        timeout=120,
    ))
    if r is None:
        print("Supabase push: brak odpowiedzi po ponowieniach", file=sys.stderr)
        return False
    if r.status_code >= 300:
        print(f"Supabase push błąd {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return False
    print(f"Supabase: wypchnięto {len(rows)} snapshotów.")
    return True


if __name__ == "__main__":
    if not push():
        print("Supabase pominięty (brak SUPABASE_URL / SUPABASE_SERVICE_KEY).")
