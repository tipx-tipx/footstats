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
    # ⚑ AKTUALIZACJA 2026-08-19: ZBIORCZY ZAPIS ZOSTAŁ ZDJĘTY.
    #
    # Do dziś próbowaliśmy najpierw jednego POST-a z całością i dopiero po
    # jego porażce dosyłali po kluczu. Przy 13 snapshotach to 18,4 MB —
    # rozmiar, przy którym baza NIE MA SZANS zdążyć (zmierzone: 14 MB to już
    # twarde 57014, patrz supa.SZARDY). Czyli pierwsze podejście padało
    # ZAWSZE: trzy próby z odczekaniem 2 i 8 s, ~40 s zmarnowane w każdym
    # cyklu i strona hałasu w logu, po którym i tak szła ścieżka zapasowa.
    #
    # Teraz wysyłamy od razu paczkami mieszczącymi się w limicie, a klucz
    # cięższy od progu idzie przez `supa.put_key`, który potnie go na części
    # (`players` to 9,1 MB — pojedynczo też nie przechodził i to on wywalał
    # cały job po 36 minutach liczenia).
    #
    # Paczka wciąż jest lepsza od zapisu po jednym kluczu: mniej round-tripów,
    # a klucze, które wchodzą razem, są ze sobą spójne.
    from .. import supa

    lekkie = [w for w in rows if len(json.dumps(w)) <= supa.PROG_SZARDU]
    ciezkie = [w for w in rows if len(json.dumps(w)) > supa.PROG_SZARDU]
    laczna = sum(len(json.dumps(w)) for w in rows)
    print(f"Supabase: wysyłam {len(rows)} snapshotów, {laczna / 1e6:.2f} MB"
          + (f" (w tym {len(ciezkie)} w częściach: "
             f"{', '.join(w['key'] for w in ciezkie)})" if ciezkie else ""))

    paczki, biezaca, waga = [], [], 0
    for wiersz in sorted(lekkie, key=lambda w: len(json.dumps(w))):
        w_wiersza = len(json.dumps(wiersz))
        if biezaca and waga + w_wiersza > supa.PROG_SZARDU:
            paczki.append(biezaca)
            biezaca, waga = [], 0
        biezaca.append(wiersz)
        waga += w_wiersza
    if biezaca:
        paczki.append(biezaca)

    udane, nieudane = [], []
    for nr, paczka in enumerate(paczki, 1):
        nazwy = [w["key"] for w in paczka]
        odp = _upsert(url, key, json.dumps(paczka),
                      f"paczka {nr}/{len(paczki)} ({len(nazwy)} kluczy)")
        if odp is not None and odp.status_code < 300:
            udane.extend(nazwy)
            continue
        # paczka padła — dosyłamy jej klucze po jednym, żeby jeden chory
        # snapshot nie zabrał ze sobą zdrowych sąsiadów
        powod = "brak odpowiedzi" if odp is None else f"{odp.status_code}"
        print(f"Supabase: paczka {nr} nie przeszła ({powod}) — dosyłam po "
              "jednym kluczu", file=sys.stderr)
        for wiersz in paczka:
            pojedyncza = _upsert(url, key, json.dumps([wiersz]),
                                 f"push '{wiersz['key']}'")
            (udane if pojedyncza is not None and pojedyncza.status_code < 300
             else nieudane).append(wiersz["key"])

    for wiersz in ciezkie:
        (udane if supa.put_key(wiersz["key"], wiersz["payload"])
         else nieudane).append(wiersz["key"])

    if nieudane:
        # świadomie False: część kluczy jest świeża, część nie, a `cycle.py`
        # ma z tego zrobić awarię — inaczej rozjazd danych przeszedłby cicho
        print(f"Supabase: dowiezione {len(udane)}, NIEDOWIEZIONE {len(nieudane)}: "
              f"{', '.join(nieudane)}", file=sys.stderr)
        return False
    print(f"Supabase: wypchnięto {len(udane)} snapshotów "
          f"({len(paczki)} paczek + {len(ciezkie)} w częściach)")
    return True


if __name__ == "__main__":
    if not push():
        print("Supabase pominięty (brak SUPABASE_URL / SUPABASE_SERVICE_KEY).")
