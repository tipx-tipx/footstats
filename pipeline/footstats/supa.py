"""Wspólny dostęp do Supabase app_data (klucz -> JSONB) dla pipeline'u.

Używane przez: bank trendów (trend_lib), log typów (typy_log), push snapshotów.
Brak env SUPABASE_URL / SUPABASE_SERVICE_KEY = tryb lokalny (zwraca puste).
"""

from __future__ import annotations

import json
import os
import sys
import time

from curl_cffi import requests

# PONOWIENIA (2026-08-13). Do dziś KAŻDE zapytanie do Supabase szło raz i tyle:
# jedno mrugnięcie sieci na runnerze GitHuba kończyło się utratą całej pracy
# cyklu, bo `push_supabase.push()` idzie na samym końcu, po ~31 minutach
# liczenia, a jego porażka podnosi RuntimeError i wywala job.
#
# Zmierzone 13.08 na 16 przebiegach: dwa `failure` (po 31,0 i 37,6 min), oba
# w środku kroku „Przelicz okazje" i oba przy ZDROWYM limicie 70 min. Czasy
# padów pokrywają się z momentem, w którym cykl kończy liczyć i wysyła 4,87 MB
# w jednym POST przy `timeout=30`.
#
# Wszystkie nasze zapytania są idempotentne (GET oraz upsert `on_conflict=key`),
# więc ponowienie jest bezpieczne — nie zdublujemy zapisu.
#
# NIE ponawiamy 4xx poza 429: to błąd po naszej stronie (zły klucz, zły JSON)
# i powtarzanie go tylko przedłuża job o kilka sekund, zanim padnie tak samo.
PROBY_SIECI = 3
PRZERWY_S = (2, 8)


def _z_ponowieniem(opis: str, wywolanie):
    """Wykonaj zapytanie, ponawiając przy awarii sieci i błędach 5xx/429.

    Zwraca odpowiedź (także tę nieudaną, po wyczerpaniu prób) albo None, gdy
    do końca leciały wyjątki. Każda ponowiona próba zostawia linię w logu —
    cichy retry ukrywałby, że źródło zaczyna się chwiać.
    """
    odp = None
    for numer in range(PROBY_SIECI):
        try:
            odp = wywolanie()
            if odp.status_code < 500 and odp.status_code != 429:
                return odp
            powod = f"HTTP {odp.status_code}"
        except Exception as ex:  # noqa: BLE001
            odp = None
            powod = type(ex).__name__
        if numer < PROBY_SIECI - 1:
            przerwa = PRZERWY_S[min(numer, len(PRZERWY_S) - 1)]
            print(f"Supabase {opis}: {powod} — ponawiam za {przerwa} s "
                  f"(próba {numer + 2}/{PROBY_SIECI})",
                  file=sys.stderr, flush=True)
            time.sleep(przerwa)
        else:
            print(f"Supabase {opis}: {powod} — wyczerpane {PROBY_SIECI} próby",
                  file=sys.stderr, flush=True)
    return odp


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


def get_key_ok(key: str) -> tuple[object | None, bool]:
    """Jak `get_key`, ale drugim polem mówi, czy ODCZYT SIĘ UDAŁ.

    `get_key` zwraca `None` w dwóch zupełnie różnych sytuacjach: klucz jest
    pusty ORAZ zapytanie padło (timeout, 5xx, brak sieci). Kod, który czyta
    rejestr, dopisuje do niego i zapisuje z powrotem, nie może tych dwóch
    mylić — przy padniętym odczycie nadpisałby wielotygodniową historię
    garstką świeżych wpisów. Brak klucza to `(None, True)`, awaria to
    `(None, False)`.

    Tryb lokalny (brak env) też jest `True`: nie ma czego stracić.
    """
    c = _conn()
    if c is None:
        return None, True
    url, headers = c
    try:
        r = _z_ponowieniem(f"odczyt '{key}'", lambda: requests.get(
            f"{url}/rest/v1/app_data?select=payload&key=eq.{key}",
            headers=headers, impersonate="chrome124", timeout=30,
        ))
        if r is None or r.status_code != 200:
            return None, False
        rows = r.json()
        return (rows[0]["payload"] if rows else None), True
    except Exception:
        return None, False


def get_key(key: str):
    """Pobierz payload spod klucza (None gdy brak/niedostępne).

    Do odczytów, które tylko CZYTAJĄ. Jeśli zamierzasz zapisać wynik z
    powrotem pod ten sam klucz, użyj `get_key_ok` albo `put_key_bezpiecznie`.
    """
    return get_key_ok(key)[0]


def waga(obj) -> int:
    """Rozmiar payloadu w bajtach JSON.

    Jedyna miara, która działa dla KAŻDEGO kształtu. Liczenie kluczy
    najwyższego poziomu myli: bank stylu ma ich cztery (`gry`, `shotmapy`,
    `wzrost`, `sytuacje`), więc mógłby stracić tysiąc meczów i przejść przez
    bezpiecznik bez mrugnięcia — zmierzone 2026-07-26: `styl_bank_liga` to
    3,06 MB w czterech kluczach.
    """
    try:
        return len(json.dumps(obj, ensure_ascii=False))
    except Exception:
        return 0


# poniżej tego rozmiaru bezpiecznik odpuszcza — mały klucz nie jest historią,
# a bywa rejestrem, który z natury pustoszeje (publikacje po gwizdku)
MIN_WAGA_BEZPIECZNIKA = 20_000


def put_key_bezpiecznie(
    key: str, payload, min_udzial: float = 0.5,
    waga_poprzednia: int | None = None,
) -> bool:
    """Upsert z bezpiecznikiem: nie nadpisuj dużego payloadu drastycznie mniejszym.

    Chroni przed klasą awarii „odczyt padł → kod myśli, że historia jest pusta
    → zapisuje kilka świeżych wpisów na miejsce tysiąca". Zanim zapiszemy,
    sprawdzamy, co pod kluczem faktycznie leży: gdy nowy payload waży mniej niż
    `min_udzial` starego, zapis WYPADA i wraca False. Gdy stanu sprzed zapisu
    nie da się odczytać — też nie zapisujemy; lepiej stracić jeden cykl niż
    historię.

    `waga_poprzednia` pozwala pominąć kontrolny odczyt, gdy wołający zna już
    rozmiar sprzed zmian (bank trendów to 8,6 MB i 2,3 s na odczyt — szkoda
    ciągnąć go drugi raz w tym samym cyklu).

    Dla kolekcji, które kurczą się z natury (rejestr wygasający po gwizdku),
    to zły bezpiecznik — tam używaj `get_key_ok` i pomijaj zapis tylko przy
    nieudanym odczycie.
    """
    if waga_poprzednia is None:
        stary, ok = get_key_ok(key)
        if not ok:
            print(f"Zapis '{key}' pominięty: nie udało się odczytać stanu "
                  "sprzed zapisu (baza nie odpowiada)")
            return False
        waga_poprzednia = waga(stary) if stary is not None else 0
    waga_nowa = waga(payload)
    if (waga_poprzednia >= MIN_WAGA_BEZPIECZNIKA
            and waga_nowa < min_udzial * waga_poprzednia):
        print(f"Zapis '{key}' WSTRZYMANY: {waga_nowa / 1e6:.2f} MB wobec "
              f"{waga_poprzednia / 1e6:.2f} MB w bazie — to wygląda na utratę "
              "danych, nie na przycinanie")
        return False
    return put_key(key, payload)


def put_key(key: str, payload) -> bool:
    """Upsert payloadu pod klucz. True = zapisano."""
    c = _conn()
    if c is None:
        return False
    url, headers = c
    try:
        r = _z_ponowieniem(f"zapis '{key}'", lambda: requests.post(
            f"{url}/rest/v1/app_data?on_conflict=key",
            headers={**headers, "Prefer": "resolution=merge-duplicates"},
            data=json.dumps([{"key": key, "payload": payload}]),
            impersonate="chrome124", timeout=60,
        ))
        return r is not None and r.status_code < 300
    except Exception:
        return False
