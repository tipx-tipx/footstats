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


def _upsert(url: str, key: str, dane: str, opis: str):
    """Jeden upsert do PostgREST, z ponowieniami. Zwraca odpowiedź albo None.

    `timeout` klienta jest tu ZAPASEM, nie mechanizmem: pad z 13.08 przyszedł
    po 18 sekundach jako 57014 z Postgresa, więc to baza pilnuje czasu, nie my.
    """
    from curl_cffi import requests

    from .. import supa

    return supa._z_ponowieniem(opis, lambda: requests.post(
        f"{url}/rest/v1/app_data?on_conflict=key",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        data=dane,
        impersonate="chrome124",
        timeout=120,
    ))


def push() -> bool:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return False

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

    # ⚑ DLACZEGO NAJPIERW JEDNYM ŻĄDANIEM, A DOPIERO POTEM PO JEDNYM
    # (2026-08-13, POTWIERDZONE LOGIEM przebiegu #909):
    #
    #     Supabase push błąd 500: {"code":"57014",
    #       "message":"canceling statement due to statement timeout"}
    #     [stoper] wysyłka do Supabase: 0.3 min | CAŁY CYKL 31.0 min
    #     RuntimeError: push_supabase.push() zwrócił False …
    #
    # To NIE był timeout po naszej stronie: wysyłka trwała 18 sekund przy
    # limicie klienta 30 s. To POSTGRES przerwał własne zapytanie (57014),
    # bo jeden upsert 14 kluczy waży ~4,9 MB (samo `players` to 2,9 MB)
    # i ociera się o `statement_timeout` bazy. Pad wraca do `cycle.py`, tam
    # podnosi RuntimeError i wywala cały job — czyli ~31 minut liczenia idzie
    # do kosza, a strona zostaje z danymi sprzed godzin.
    #
    # Zbiorczy zapis ZOSTAJE jako pierwsze podejście, bo daje stronie komplet
    # danych z jednego cyklu (żadnych świeżych typów przy starym radarze).
    # Ale gdy baza go nie przyjmie, lepiej dowieźć klucze POJEDYNCZO niż nie
    # dowieźć nic: każdy upsert jest wtedy kilkanaście razy mniejszy i mieści
    # się w limicie z zapasem. Stan mieszany jest gorszy od kompletnego —
    # ale wyraźnie lepszy od zera, bo dziś zerem kończył się cały cykl.
    dane = json.dumps(rows)
    print(f"Supabase: wysyłam {len(rows)} snapshotów, {len(dane) / 1e6:.2f} MB")
    r = _upsert(url, key, dane, "push snapshotów")
    if r is not None and r.status_code < 300:
        print(f"Supabase: wypchnięto {len(rows)} snapshotów.")
        return True

    powod = "brak odpowiedzi" if r is None else f"{r.status_code}: {r.text[:200]}"
    print(f"Supabase push zbiorczy nie przeszedł ({powod}) — "
          "dosyłam po jednym kluczu", file=sys.stderr)
    udane, nieudane = [], []
    for wiersz in sorted(rows, key=lambda w: len(json.dumps(w))):
        odp = _upsert(url, key, json.dumps([wiersz]), f"push '{wiersz['key']}'")
        (udane if odp is not None and odp.status_code < 300
         else nieudane).append(wiersz["key"])
    if nieudane:
        # świadomie False: część kluczy jest świeża, część nie, a `cycle.py`
        # ma z tego zrobić awarię — inaczej rozjazd danych przeszedłby cicho
        print(f"Supabase: dowiezione {len(udane)}, NIEDOWIEZIONE {len(nieudane)}: "
              f"{', '.join(nieudane)}", file=sys.stderr)
        return False
    print(f"Supabase: wypchnięto {len(udane)} snapshotów po jednym "
          "(zbiorczy zapis nie przeszedł)")
    return True
    print(f"Supabase: wypchnięto {len(rows)} snapshotów.")
    return True


if __name__ == "__main__":
    if not push():
        print("Supabase pominięty (brak SUPABASE_URL / SUPABASE_SERVICE_KEY).")
