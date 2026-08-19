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
        payload = rows[0]["payload"] if rows else None
        n = ile_czesci(payload)
        if n is None:
            return payload, True

        # klucz szardowany: dociągamy kawałki jednym zapytaniem i sklejamy.
        # BRAK CHOĆ JEDNEGO KAWAŁKA TO AWARIA, NIE PUSTKA — inaczej wołający
        # dopisałby świeże wpisy do połowy historii i zapisał to jako całość
        rc = _z_ponowieniem(f"odczyt części '{key}'", lambda: requests.get(
            f"{url}/rest/v1/app_data?select=key,payload&key=like.{key}__cz*",
            headers=headers, impersonate="chrome124", timeout=60,
        ))
        if rc is None or rc.status_code != 200:
            return None, False
        mapa = {w["key"]: w["payload"] for w in rc.json()}
        czesci = [mapa.get(klucz_czesci(key, i)) for i in range(n)]
        if any(cz is None for cz in czesci):
            braki = [i for i, cz in enumerate(czesci) if cz is None]
            print(f"Odczyt '{key}': marker mówi o {n} częściach, brakuje "
                  f"{len(braki)} ({braki[:5]}) — traktuję jak padnięty odczyt",
                  file=sys.stderr, flush=True)
            return None, False
        return sklej_czesci(czesci), True
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


# ------------------------------------------------------------ SZARDY ---------
# ⚑ DLACZEGO DUŻY KLUCZ IDZIE W KAWAŁKACH (2026-08-19, zmierzone na żywej bazie)
#
# Zapis do `app_data` kosztuje tym więcej, im większy payload, i rośnie
# SZYBCIEJ NIŻ LINIOWO — pomiar upsertów tej samej struktury:
#
#      2 MB → 2,3 s     8 MB →  7,8 s     12 MB → 34,8 s
#      4 MB → 5,1 s    10 MB → 23,2 s     14 MB → 500 (57014 statement timeout)
#
# Powyżej ~12 MB Postgres przerywa własne zapytanie, a między 8 a 12 MB wynik
# zależy od obciążenia bazy — czyli zapis „czasem przechodzi". Tak właśnie
# zachowywały się nasze trzy najcięższe klucze: `trend_lib` (14,0 MB),
# `typy_log` (12,4 MB) i `players` (9,1 MB) — w logach cyklu zostawiały serie
# „wyczerpane 3 próby", a `players` wywalał cały job po 36 minutach liczenia
# ([[cykl-pada-losowo-co-kilkanascie]]).
#
# Dzielimy więc payload na części po ~3 MB pod kluczami `<klucz>__cz00`,
# `<klucz>__cz01`… Pod GŁÓWNYM kluczem zostaje mały marker `{"__czesci": n}`,
# po którym czytelnik poznaje, że ma dociągnąć resztę. Ten sam pomysł co
# magazyn drużyn (`hd_0..hd_9`), tylko PRZEZROCZYSTY: `put_key`/`get_key_ok`
# dzielą i sklejają same, a wołający o niczym nie wie.
#
# KOLEJNOŚĆ ZAPISU JEST CZĘŚCIĄ BEZPIECZEŃSTWA: najpierw wszystkie części,
# marker DOPIERO na końcu. Gdy któraś część nie dojdzie, marker nie powstaje
# i pod głównym kluczem zostaje POPRZEDNIA, spójna wersja — czytelnik nigdy
# nie dostanie połowy nowych danych sklejonej z połową starych.
PROG_SZARDU = 4_000_000      # powyżej tej wagi zapis idzie w kawałkach
CEL_CZESCI = 3_000_000       # docelowa waga jednego kawałka
MARKER_CZESCI = "__czesci"


def klucz_czesci(key: str, nr: int) -> str:
    return f"{key}__cz{int(nr):02d}"


def ile_czesci(payload) -> int | None:
    """Ile kawałków ma ten payload, jeśli to marker szardów (inaczej None)."""
    if isinstance(payload, dict) and isinstance(payload.get(MARKER_CZESCI), int):
        return payload[MARKER_CZESCI]
    return None


def _potnij(payload) -> list | None:
    """Podziel payload na kawałki po ~CEL_CZESCI. None = nie da się dzielić.

    Tniemy po elementach najwyższego poziomu, więc kawałek ma ZAWSZE ten sam
    kształt co całość (słownik → słowniki, lista → listy) i sklejenie nie
    wymaga wiedzy o zawartości.

    ⚑ JEDEN GRUBY ELEMENT TEŻ MUSI SIĘ PODZIELIĆ. Kopia księgi typów to
    `{"ts": …, "log": {12 MB}}` — dwa elementy najwyższego poziomu, z czego
    jeden waży tyle, co całość. Podział „po wierzchu" dałby kawałek równy
    oryginałowi i zapis padłby dokładnie tak samo. Dlatego element cięższy
    od limitu tniemy REKURENCYJNIE i owijamy podkawałki z powrotem w jego
    klucz; `sklej_czesci` scala takie słowniki w głąb.
    """
    if isinstance(payload, dict):
        elementy = list(payload.items())
        pusty, dodaj = dict, lambda cz, e: cz.__setitem__(e[0], e[1])
    elif isinstance(payload, list):
        elementy = payload
        pusty, dodaj = list, lambda cz, e: cz.append(e)
    else:
        return None
    czesci, biezaca, waga_biezacej = [], pusty(), 0
    for element in elementy:
        w = len(json.dumps(element, ensure_ascii=False))
        if w > CEL_CZESCI:
            wnetrze = element[1] if isinstance(payload, dict) else element
            podkawalki = _potnij(wnetrze) if w > CEL_CZESCI else None
            if podkawalki and len(podkawalki) > 1:
                if waga_biezacej:
                    czesci.append(biezaca)
                    biezaca, waga_biezacej = pusty(), 0
                for pod in podkawalki:
                    czesci.append({element[0]: pod} if isinstance(payload, dict)
                                  else [pod])
                continue
        if waga_biezacej and waga_biezacej + w > CEL_CZESCI:
            czesci.append(biezaca)
            biezaca, waga_biezacej = pusty(), 0
        dodaj(biezaca, element)
        waga_biezacej += w
    if waga_biezacej or not czesci:
        czesci.append(biezaca)
    return czesci


def sklej_czesci(czesci: list):
    """Odwrotność `_potnij` — z kawałków robi z powrotem całość."""
    if czesci and isinstance(czesci[0], list):
        calosc: list = []
        for cz in czesci:
            calosc.extend(cz or [])
        return calosc
    scalony: dict = {}
    for cz in czesci:
        _scal_w_glab(scalony, cz or {})
    return scalony


def _scal_w_glab(cel: dict, dolozenie: dict) -> None:
    """Scal słowniki, wchodząc do środka — patrz rekurencja w `_potnij`."""
    for k, v in dolozenie.items():
        if isinstance(v, dict) and isinstance(cel.get(k), dict):
            _scal_w_glab(cel[k], v)
        elif isinstance(v, list) and isinstance(cel.get(k), list):
            cel[k].extend(v)
        else:
            cel[k] = v


def _spis_czesci(url: str, headers: dict, key: str) -> list[str] | None:
    """Nazwy kluczy-kawałków leżących teraz w bazie (None = odczyt padł)."""
    r = _z_ponowieniem(f"spis części '{key}'", lambda: requests.get(
        f"{url}/rest/v1/app_data?select=key&key=like.{key}__cz*",
        headers=headers, impersonate="chrome124", timeout=30,
    ))
    if r is None or r.status_code != 200:
        return None
    try:
        return [w["key"] for w in r.json()]
    except Exception:
        return None


def _wyslij(url: str, headers: dict, key: str, payload) -> bool:
    """Jeden upsert, bez dzielenia — wspólny spód całości i kawałka."""
    r = _z_ponowieniem(f"zapis '{key}'", lambda: requests.post(
        f"{url}/rest/v1/app_data?on_conflict=key",
        headers={**headers, "Prefer": "resolution=merge-duplicates"},
        data=json.dumps([{"key": key, "payload": payload}]),
        impersonate="chrome124", timeout=120,
    ))
    return r is not None and r.status_code < 300


def _posprzataj_czesci(url: str, headers: dict, key: str, zostawiam: int):
    """Usuń kawałki, których nowy zapis już nie używa.

    Osierocony kawałek niczego nie psuje (marker mówi, ilu szukać), ale
    zostaje w bazie na zawsze — po kilku takich cyklach `app_data` puchnie
    od danych, których nikt nie czyta.
    """
    sa = _spis_czesci(url, headers, key)
    if sa is None:
        return
    chciane = {klucz_czesci(key, i) for i in range(zostawiam)}
    for nazwa in sa:
        if nazwa in chciane:
            continue
        _z_ponowieniem(f"kasowanie '{nazwa}'", lambda n=nazwa: requests.delete(
            f"{url}/rest/v1/app_data?key=eq.{n}",
            headers=headers, impersonate="chrome124", timeout=30,
        ))


def put_key(key: str, payload) -> bool:
    """Upsert payloadu pod klucz. True = zapisano.

    Payload cięższy niż `PROG_SZARDU` jedzie w kawałkach — patrz SZARDY wyżej.
    """
    c = _conn()
    if c is None:
        return False
    url, headers = c
    try:
        waga_calosci = len(json.dumps(payload, ensure_ascii=False))
        if waga_calosci <= PROG_SZARDU:
            if not _wyslij(url, headers, key, payload):
                return False
            # klucz mógł być wcześniej szardowany i właśnie schudł — wtedy
            # kawałki muszą zniknąć, inaczej zostaną w bazie bez czytelnika
            _posprzataj_czesci(url, headers, key, 0)
            return True

        czesci = _potnij(payload)
        if czesci is None:      # payload nie do podziału (liczba, napis)
            return _wyslij(url, headers, key, payload)
        print(f"Supabase zapis '{key}': {waga_calosci / 1e6:.1f} MB — dzielę "
              f"na {len(czesci)} części (limit zapisu bazy)", flush=True)
        for nr, cz in enumerate(czesci):
            if not _wyslij(url, headers, klucz_czesci(key, nr), cz):
                print(f"Supabase zapis '{key}': część {nr} nie doszła — "
                      "zostawiam pod kluczem poprzednią wersję",
                      file=sys.stderr, flush=True)
                return False
        # marker DOPIERO teraz: do tej chwili pod `key` leży spójna starszyzna
        if not _wyslij(url, headers, key, {MARKER_CZESCI: len(czesci)}):
            return False
        _posprzataj_czesci(url, headers, key, len(czesci))
        return True
    except Exception:
        return False
