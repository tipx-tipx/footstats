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
        r = requests.get(
            f"{url}/rest/v1/app_data?select=payload&key=eq.{key}",
            headers=headers, impersonate="chrome124", timeout=30,
        )
        if r.status_code != 200:
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
        r = requests.post(
            f"{url}/rest/v1/app_data?on_conflict=key",
            headers={**headers, "Prefer": "resolution=merge-duplicates"},
            data=json.dumps([{"key": key, "payload": payload}]),
            impersonate="chrome124", timeout=60,
        )
        return r.status_code < 300
    except Exception:
        return False
