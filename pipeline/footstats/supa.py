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
            if odp.status_code == 402:
                _zapamietaj_odciecie(odp)
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


# ------------------------------------------------------ ODCIĘCIE PROJEKTU ---
# ⚑ HTTP 402 TO NIE JEST AWARIA KODU (2026-08-28). Gdy miesięczny limit
# transferu się wyczerpie, Supabase odcina CAŁY projekt: każde zapytanie
# z kluczem — odczyt i zapis — wraca jako 402 „exceed_egress_quota". Od
# 25.08 znaczyło to czerwony cykl co godzinę i tyle samo maili „workflow
# failed", w których nie było czego naprawiać: kod jest sprawny, płatny
# jest dostęp do bazy.
#
# Czerwony job musi znaczyć „coś do naprawienia w kodzie". Dlatego odcięcie
# rozpoznajemy po komunikacie i kończymy job ZIELONO, ale z ostrzeżeniem
# (`::warning::` widać w podsumowaniu przebiegu w Actions). Każdy inny błąd
# dalej wywala job na czerwono, czyli sygnał zostaje tam, gdzie ma być.
#
# Straż stoi na POCZĄTKU joba, a nie tylko w łapaniu wyjątku: cykl liczył
# przez 38 minut, żeby dopiero na wysyłce dowiedzieć się, że nie ma dokąd
# wysyłać.
ODCIECIE_ZNACZNIK = "exceed_egress_quota"
_odciecie: str | None = None


def _zapamietaj_odciecie(r) -> None:
    """Zapisz komunikat Supabase o odcięciu projektu (HTTP 402)."""
    global _odciecie
    try:
        powod = str((r.json() or {}).get("message") or "").strip()
    except Exception:  # noqa: BLE001
        powod = ""
    _odciecie = powod or "HTTP 402 — projekt odcięty przez Supabase"


def odciecie_projektu() -> str | None:
    """Komunikat, jeśli w tym przebiegu Supabase odciął projekt; inaczej None."""
    return _odciecie


def zbadaj_odciecie() -> str | None:
    """Jedno lekkie zapytanie sprawdzające, czy projekt nie jest odcięty.

    Przy odcięciu odpowiedź waży ~190 bajtów, więc sama kontrola nie ma jak
    pogłębić problemu. W trybie lokalnym (brak sekretów) nie pyta o nic.
    """
    c = _conn()
    if c is None:
        return None
    url, headers = c
    _z_ponowieniem("kontrola dostępu", lambda: requests.get(
        f"{url}/rest/v1/app_data?select=key&limit=1",
        headers=headers, impersonate="chrome124", timeout=20,
    ))
    return _odciecie


# ⚑ RAZ NA DOBĘ ODCIĘCIE MA KRZYCZEĆ (2026-09-08). Zielony job z ostrzeżeniem
# (28.08) sprawił, że drugie odcięcie od 04.09 przez PIĘĆ DNI nikt nie
# zauważył — GitHub wysyła mail tylko o czerwonym przebiegu. Dlatego przebiegi
# w tym oknie UTC kończą się czerwono; reszta doby dalej zielono, żeby skrzynka
# nie tonęła w 150 mailach dziennie. 6:00 UTC = 8:00 czasu polskiego.
ALARM_ODCIECIA_UTC = (6, 0, 6, 30)   # (od_godz, od_min, do_godz, do_min)


def _w_oknie_alarmu(teraz=None) -> bool:
    t = teraz if teraz is not None else time.gmtime()
    od_h, od_m, do_h, do_m = ALARM_ODCIECIA_UTC
    minuta = t.tm_hour * 60 + t.tm_min
    return od_h * 60 + od_m <= minuta < do_h * 60 + do_m


def straz_odciecia(job: str, *, badaj: bool = True) -> None:
    """Zakończ job z ostrzeżeniem, gdy Supabase odciął projekt.

    Zielono przez większość doby, CZERWONO w oknie `ALARM_ODCIECIA_UTC` —
    żeby raz dziennie przyszedł mail, że produkt stoi.

    `badaj=False` dla wywołań z łapania wyjątku — tam wiemy już z przebiegu,
    czy padło na 402, i nie ma po co dokładać zapytania.
    """
    powod = zbadaj_odciecie() if badaj else odciecie_projektu()
    if not powod:
        return
    alarm = _w_oknie_alarmu()
    poziom = "error" if alarm else "warning"
    print(f"::{poziom} title=Supabase odciął projekt (402)::{job}: {powod}",
          flush=True)
    print(f"[{job}] Supabase odciął projekt (402 {ODCIECIE_ZNACZNIK}) — "
          "nie ma z czego czytać ani dokąd pisać. Kończę bez pracy; to nie "
          "jest błąd kodu, tylko limit transferu do zdjęcia w panelu Supabase.",
          flush=True)
    if alarm:
        print(f"[{job}] DZIENNY ALARM: przebieg kończy się CZERWONO, żeby "
              "właściciel dostał mail. Produkt nie tworzy typów ani nie "
              "rozlicza od chwili odcięcia.", flush=True)
    sys.exit(1 if alarm else 0)


# ------------------------------------------------------- LICZNIK TRANSFERU ---
# ⚑ DLACZEGO MIERZYMY POBRANE BAJTY (2026-08-25). Projekt stanął na 402
# „exceed_egress_quota": Supabase odciął CAŁY ruch z kluczem — odczyty i zapisy
# naraz — bo miesięczny transfer wyszedł poza plan. Z logu cyklu nie dało się
# powiedzieć, co ten transfer zjada: `get_key_ok` przy nie-200 zwraca
# `(None, False)` bez śladu, więc widać było tylko kaskadę „odczyt PADŁ".
#
# Liczy się wyłącznie strona ODCZYTU: egress to bajty, które baza WYSYŁA do
# nas. Nasze POST-y obciążają wejście, a tego Supabase nie limituje — dlatego
# licznik siedzi tylko na GET-ach.
#
# ⚑ ZLICZAMY TAKŻE ODCZYTY NIEUDANE. Przy odcięciu każda odpowiedź waży 189
# bajtów, więc same bajty nic nie powiedzą — ale KROTNOŚĆ zostaje prawdziwa,
# a to ona pokazuje klucz ciągnięty kilkanaście razy w jednym cyklu.
_egress: dict[str, list[int]] = {}


def _zlicz(key: str, r) -> None:
    """Dopisz jeden odczyt klucza do licznika transferu."""
    poz = _egress.setdefault(key, [0, 0])
    poz[0] += 1
    try:
        if r is not None:
            poz[1] += len(r.content)
    except Exception:  # noqa: BLE001
        pass


def raport_egress(ile: int = 12) -> str:
    """Rozkład pobranych bajtów po kluczach — najcięższe na górze."""
    if not _egress:
        return "Transfer z Supabase: brak odczytów w tym przebiegu."
    poz = sorted(_egress.items(), key=lambda x: -x[1][1])
    suma = sum(w[1] for _, w in poz)
    razem = sum(w[0] for _, w in poz)
    linie = [f"Transfer z Supabase (odczyty): {suma / 1e6:.1f} MB "
             f"w {razem} zapytaniach, {len(poz)} kluczy"]
    for nazwa, (ile_razy, bajty) in poz[:ile]:
        na_odczyt = (f"  ({bajty / ile_razy / 1e6:.2f} MB/odczyt)"
                     if ile_razy > 1 else "")
        linie.append(f"   {nazwa:<28} {bajty / 1e6:7.2f} MB  x{ile_razy}"
                     + na_odczyt)
    if len(poz) > ile:
        reszta = sum(w[1] for _, w in poz[ile:])
        linie.append(f"   … {len(poz) - ile} lżejszych kluczy, razem "
                     f"{reszta / 1e6:.2f} MB")
    if raport_pamieci():
        linie.append("   " + raport_pamieci())
    return "\n".join(linie)


# ⚑⚑⚑ PAMIĘĆ ODCZYTÓW W OBRĘBIE JEDNEGO PROCESU (2026-09-08).
#
# Zmierzone w logu cyklu 01.09: 476 MB odczytów na JEDEN cykl, z czego
# `typy_log` 22,9 MB × 14 razy = 320 MB — czternaście warstw uczenia czytało
# tę samą księgę osobno. Przy ~25 cyklach dziennie to ~10 GB/dobę wobec
# limitu Free 5 GB/MIESIĄC; projekt został odcięty (402) drugi raz w cztery
# dni po odblokowaniu. Front naprawiony 25.08 nie miał tu nic do rzeczy.
#
# Zasada: `get_key` (odczyt TYLKO do czytania — patrz jego docstring) oddaje
# kopię z pamięci procesu, jeśli klucz był już w tym przebiegu pobrany.
# `get_key_ok` (odczyt PRZED zapisem) ZAWSZE idzie do bazy i odświeża pamięć,
# a `put_key` po udanym zapisie podmienia wpis — więc „przeczytaj, dopisz,
# zapisz" widzi stan bieżący, a czytacze dostają snapshot z tego przebiegu.
# Kopia (json.loads z zapamiętanego tekstu), nie ten sam obiekt: `_migruj_log`
# i warstwy modyfikują rekordy w miejscu.
_pamiec: dict[str, str | None] = {}
_z_pamieci: dict[str, list[int]] = {}


def wyczysc_pamiec() -> None:
    """Testy i skrypty, które chcą świeżego odczytu w tym samym procesie."""
    _pamiec.clear()
    _z_pamieci.clear()


def _zapamietaj(key: str, payload) -> None:
    try:
        _pamiec[key] = None if payload is None else json.dumps(payload, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        _pamiec.pop(key, None)


def raport_pamieci() -> str:
    if not _z_pamieci:
        return ""
    razem = sum(v[0] for v in _z_pamieci.values())
    bajty = sum(v[1] for v in _z_pamieci.values())
    return (f"Odczyty z pamięci procesu (zaoszczędzony transfer): {razem} "
            f"× {bajty / 1e6:.1f} MB")


def egress_surowy() -> dict[str, list[int]]:
    """Licznik do rentgenu w `meta` — logi Actions wymagają praw admina."""
    return {k: list(v) for k, v in _egress.items()}


# ---------------------------------------------------------- MAGAZYNY --------
# ⚑ DLACZEGO KLUCZ MOŻE MIESZKAĆ POZA SUPABASE (2026-09-10)
#
# Supabase był używany jako PAMIĘĆ ROBOCZA pipeline'u, a nie jako baza frontu.
# `typy_log` (25 MB), `trend_lib` (47 MB), `styl_bank_liga` (21 MB),
# `typy_log_kopia` (22 MB) i magazyn drużyn `hd_0..hd_9` czyta i pisze WYŁĄCZNIE
# pipeline — front nie tyka ich ani razu (patrz `BUNDLE_KEYS` w
# `web/src/lib/data.ts`). Mimo to jechały przez sieć do 70 razy na dobę
# (25 cykli + 72 przebiegi `rozlicz_only`) i to one, a nie strona, wyczerpały
# limit transferu Free — dwa razy: 25.08 i 04.09.
#
# Zamiast przepisywać 131 wywołań `get_key`/`put_key` rozsianych po pipelinie
# (74 z nich siedzą w `rozliczanie.py` i `build_wc_fast.py`), podmieniamy sam
# TRANSPORT wewnątrz tego modułu. Wołający o niczym nie wie, API się nie zmienia,
# a testy — które mockują `_conn` i `requests` — zostają nietknięte.
#
# ⚑ PUSTY `MAGAZYN` = ZACHOWANIE DOKŁADNIE JAK PRZED ZMIANĄ. Przeprowadzka
# klucza to dopisanie jednej linijki, a cofnięcie — skasowanie jej.
MAGAZYN: dict[str, str] = {}

# nazwa backendu -> obiekt z `pobierz(key) -> (payload, ok)` i
# `zapisz(key, payload) -> bool`. Kontrakt `pobierz` jest TAKI SAM jak
# `get_key_ok`: brak klucza to `(None, True)`, awaria to `(None, False)` —
# i to rozróżnienie jest tu najważniejszą rzeczą do zaimplementowania.
# Backend, który myli te dwa przypadki, pozwoli wołającemu dopisać garść
# świeżych wpisów do pustki i zapisać to jako całą historię.
_BACKENDY: dict[str, object] = {}

# ruch, który NIE poszedł przez Supabase — osobno, żeby `raport_egress`
# pokazywał, ile transferu realnie zdjęliśmy z limitu
_ruch_poza: dict[str, list[int]] = {}


def zarejestruj_backend(nazwa: str, backend) -> None:
    """Podłącz magazyn pod nazwę używaną w `MAGAZYN`."""
    _BACKENDY[nazwa] = backend


BRAK_BACKENDU = object()   # wpis w MAGAZYN jest, backendu nie ma = AWARIA

# Magazyny podpinane SAME przy pierwszym użyciu. Alternatywą było wołanie
# `podepnij()` na starcie każdego jobu — a jobów jest sześć i łatwo o nowy,
# w którym ktoś tego nie doda. Zapomniane podpięcie znaczyłoby awarię klucza
# (albo, gdyby spadało na Supabase, cichy odczyt nieaktualnej wersji).
_AUTO_MAGAZYNY = {"repo": "footstats.magazyn_repo"}


def _podepnij_automatycznie(nazwa: str) -> None:
    sciezka = _AUTO_MAGAZYNY.get(nazwa)
    if not sciezka:
        return
    try:
        import importlib
        _BACKENDY[nazwa] = importlib.import_module(sciezka)
    except Exception as ex:  # noqa: BLE001
        print(f"Magazyn '{nazwa}' nie daje się zaimportować: {ex!r}",
              file=sys.stderr, flush=True)


def _backend(key: str):
    """Backend dla klucza, None gdy klucz mieszka w Supabase.

    Trzeci przypadek — `BRAK_BACKENDU` — to konfiguracja niespójna z kodem.
    """
    nazwa = MAGAZYN.get(key)
    if not nazwa:
        return None
    if nazwa not in _BACKENDY:
        _podepnij_automatycznie(nazwa)
    b = _BACKENDY.get(nazwa)
    if b is None:
        # ⚑ NIE spadamy cicho na Supabase. Klucz jest już przeniesiony, więc
        # w bazie leży nieaktualna wersja: odczyt stamtąd cofnąłby produkt
        # o kilka dni, a zapis zgubiłby wszystko, co przyszło po migracji.
        # Awaria jest tu bezpieczniejsza niż nieświeże dane.
        print(f"Klucz '{key}' wskazuje na magazyn '{nazwa}', którego NIE MA "
              "w rejestrze — traktuję jak niedostępny, NIE schodzę na Supabase",
              file=sys.stderr, flush=True)
        return BRAK_BACKENDU
    return b


def _zlicz_poza(nazwa: str, key: str, bajty: int) -> None:
    poz = _ruch_poza.setdefault(f"{key} [{nazwa}]", [0, 0])
    poz[0] += 1
    poz[1] += max(int(bajty or 0), 0)


def raport_poza_supabase() -> str:
    """Ile transferu przeszło magazynami spoza Supabase (nie liczy się do limitu)."""
    if not _ruch_poza:
        return ""
    razem = sum(v[0] for v in _ruch_poza.values())
    bajty = sum(v[1] for v in _ruch_poza.values())
    return (f"Transfer poza Supabase (nie liczy się do limitu): "
            f"{bajty / 1e6:.1f} MB w {razem} operacjach")


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
    b = _backend(key)
    if b is BRAK_BACKENDU:
        return None, False
    if b is not None:
        payload, ok = b.pobierz(key)
        if ok:
            # ta sama pamięć procesu co przy Supabase — `get_key` ma działać
            # identycznie niezależnie od tego, gdzie klucz mieszka
            _zapamietaj(key, payload)
            _zlicz_poza(MAGAZYN[key], key, len(_pamiec.get(key) or ""))
        return payload, ok

    c = _conn()
    if c is None:
        return None, True
    url, headers = c
    try:
        r = _z_ponowieniem(f"odczyt '{key}'", lambda: requests.get(
            f"{url}/rest/v1/app_data?select=payload&key=eq.{key}",
            headers=headers, impersonate="chrome124", timeout=30,
        ))
        _zlicz(key, r)
        if r is None or r.status_code != 200:
            return None, False
        rows = r.json()
        payload = rows[0]["payload"] if rows else None
        n = ile_czesci(payload)
        if n is None:
            _zapamietaj(key, payload)
            return payload, True

        # klucz szardowany: dociągamy kawałki jednym zapytaniem i sklejamy.
        # BRAK CHOĆ JEDNEGO KAWAŁKA TO AWARIA, NIE PUSTKA — inaczej wołający
        # dopisałby świeże wpisy do połowy historii i zapisał to jako całość
        rc = _z_ponowieniem(f"odczyt części '{key}'", lambda: requests.get(
            f"{url}/rest/v1/app_data?select=key,payload&key=like.{key}__cz*",
            headers=headers, impersonate="chrome124", timeout=60,
        ))
        _zlicz(f"{key} (części)", rc)
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
        calosc = sklej_czesci(czesci)
        _zapamietaj(key, calosc)
        return calosc, True
    except Exception:
        return None, False


def get_key(key: str):
    """Pobierz payload spod klucza (None gdy brak/niedostępne).

    Do odczytów, które tylko CZYTAJĄ. Jeśli zamierzasz zapisać wynik z
    powrotem pod ten sam klucz, użyj `get_key_ok` albo `put_key_bezpiecznie`.
    """
    if key in _pamiec:
        tekst = _pamiec[key]
        poz = _z_pamieci.setdefault(key, [0, 0])
        poz[0] += 1
        poz[1] += len(tekst or "")
        return None if tekst is None else json.loads(tekst)
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
# ⚑ PROGI OBNIŻONE 2026-08-25 — DECYDUJE O NICH CACHE FRONTU, NIE BAZA.
# Do dziś progi pilnowały tylko tego, żeby upsert nie padł na `statement
# timeout` (stąd 4 MB / 3 MB). Ale te same części czyta potem strona, a Next
# odmawia wpisania do Data Cache odpowiedzi cięższej niż 2 MB — wtedy każdy
# render idzie po dane do Supabase od nowa. `players` (4,6 MB) był tak
# pobierany przy KAŻDYM z renderów 189 podstron meczu i to on wyczerpał
# miesięczny limit transferu (402 „exceed_egress_quota").
#
# Część ~1,2 MB mieści się w limicie z zapasem na narzut PostgREST
# (opakowanie w tablicę, escaping), więc każda cache'uje się osobno —
# patrz `sklejCzesci` w `web/src/lib/data.ts`, które pobiera je pojedynczo.
PROG_SZARDU = 1_500_000      # powyżej tej wagi zapis idzie w kawałkach
CEL_CZESCI = 1_200_000       # docelowa waga jednego kawałka
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
    _zlicz(f"{key} (spis części)", r)
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
    _pamiec.pop(key, None)
    ok = _put_key(key, payload)
    if ok:
        _zapamietaj(key, payload)
    return ok


def _put_key(key: str, payload) -> bool:
    b = _backend(key)
    if b is BRAK_BACKENDU:
        return False
    if b is not None:
        ok = b.zapisz(key, payload)
        if ok:
            try:
                _zlicz_poza(MAGAZYN[key], key,
                            len(json.dumps(payload, ensure_ascii=False)))
            except Exception:  # noqa: BLE001
                pass
        return ok

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
