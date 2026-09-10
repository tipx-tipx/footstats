# -*- coding: utf-8 -*-
"""MAGAZYN STANU PIPELINE'U W PRYWATNYM REPO GITHUBA (etap 2, 2026-09-10).

Po co
-----
`typy_log`, `trend_lib`, `styl_bank_liga`, `typy_log_kopia` i `hd_0..9` czyta
i pisze WYŁĄCZNIE pipeline — front nie tyka ich ani razu. Mimo to jechały przez
Supabase do 70 razy na dobę i dwa razy wyczerpały limit transferu Free.
Tutaj mieszkają zamiast tam. Wołający o niczym nie wie: `supa.get_key` /
`supa.put_key` kierują tu przez słownik `supa.MAGAZYN`.

Dlaczego akurat Release assets
------------------------------
* **Za darmo i bez karty.** Prywatne repo BEZ workflowów nie zużywa minut
  Actions (minuty liczą się tam, gdzie job biegnie), a repo z kodem zostaje
  publiczne — przy 1500 min/dobę uprywatnienie go byłoby nie do opłacenia.
* **Wersjonowanie gratis.** Trzymamy `RETENCJA` ostatnich wersji każdego klucza,
  więc kopia zapasowa robi się sama. Do 10.09 jedyna kopia księgi powstawała
  pod kluczem `typy_log_kopia` — w tym samym Supabase, który potrafi paść.

⚑ ZAPIS JEST ATOMOWY PRZEZ DOPISYWANIE, NIE PODMIANĘ
----------------------------------------------------
`gh release upload --clobber` kasuje asset i wgrywa nowy — między jednym
a drugim pliku NIE MA, a czytelnik trafiający w to okno dostaje 404 i (gdyby
mylił go z pustką) mógłby dopisać garść świeżych wpisów do niczego.

Dlatego NIC NIE PODMIENIAMY. Każdy zapis to NOWY asset z sygnaturą czasu
w nazwie (`typy_log--20260910T134501Z.json.gz`), a odczyt bierze najświeższą
sygnaturę. Stare wersje kasujemy DOPIERO po udanym zapisie nowej — i nawet
gdyby kasowanie padło, czytelnik i tak czyta najnowszą. Nie ma momentu,
w którym klucz nie istnieje.

⚑ `state == "uploaded"` JEST CZĘŚCIĄ TEGO SAMEGO ZABEZPIECZENIA. Asset, którego
wysyłka się urwała, zostaje w GitHubie jako `starter` — kompletny z nazwy,
pusty w środku. Czytelnik musi go pominąć, inaczej „najświeższa wersja" bywa
plikiem zerowej długości.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import sys
import time

from curl_cffi import requests

API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"

# ile wersji każdego klucza zostawiamy — to jest nasza historia kopii
RETENCJA = 5

ROZDZIELNIK = "--"          # `<klucz>--<sygnatura>.json.gz`
ROZSZERZENIE = ".json.gz"

PROBY = 3
PRZERWY_S = (2, 8)


def _konf() -> tuple[str, str, str] | None:
    """(repo, token, tag) albo None, gdy magazyn nie jest skonfigurowany."""
    repo = os.environ.get("STAN_REPO", "").strip()
    token = os.environ.get("STAN_TOKEN", "").strip()
    if not repo or not token:
        return None
    return repo, token, os.environ.get("STAN_TAG", "stan").strip() or "stan"


def _naglowki(token: str, accept: str = "application/vnd.github+json") -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        # ⚑ BEZ TEGO KAŻDE ŻĄDANIE WRACA JAKO 403 (2026-09-10). GitHub wymaga
        # `User-Agent`, a `curl_cffi` bez `impersonate` go nie wysyła — treść
        # odpowiedzi mówi wprost „Request forbidden by administrative rules",
        # co przy zwykłym patrzeniu na sam kod 403 wygląda jak zły token.
        "User-Agent": "footstats-magazyn",
    }


def _w_produkcji() -> bool:
    """Czy to produkcyjny przebieg (Actions), czy lokalny dry-run.

    ⚑ Rozróżnienie jest tu po to, żeby BRAK KONFIGURACJI nie wyglądał jak
    pusty magazyn. Lokalnie „pusto" jest prawdą (nie ma czego stracić), ale
    w produkcji to zapomniany sekret — a wtedy `(None, True)` kazałoby
    pipeline'owi zacząć historię od zera i zapisać to jako całość.
    """
    return bool(os.environ.get("SUPABASE_URL") or os.environ.get("CI"))


def _z_ponowieniem(opis: str, wywolanie):
    """Trzy podejścia; 4xx poza 429 nie ma sensu powtarzać (to nasz błąd)."""
    for nr in range(PROBY):
        try:
            r = wywolanie()
            if r.status_code < 400 or (400 <= r.status_code < 500
                                       and r.status_code != 429):
                return r
            powod = f"HTTP {r.status_code}"
        except Exception as ex:  # noqa: BLE001
            powod = repr(ex)
        if nr < PROBY - 1:
            time.sleep(PRZERWY_S[min(nr, len(PRZERWY_S) - 1)])
            continue
        print(f"Magazyn repo: {opis} — wyczerpane {PROBY} próby ({powod})",
              file=sys.stderr, flush=True)
    return None


# ------------------------------------------------------------- RELEASE -------
# Spis assetów czytamy RAZ NA PROCES. Cykl dotyka kilku kluczy, a spis jest
# jeden i ten sam — bez tego każdy klucz kosztowałby osobne zapytanie o listę.
_spis: list[dict] | None = None
_release_id: int | None = None


def wyczysc_pamiec() -> None:
    """Testy i skrypty, które chcą świeżego spisu w tym samym procesie."""
    global _spis, _release_id
    _spis = None
    _release_id = None


OPIS_RELEASE = ("Magazyn stanu roboczego pipeline'u. Zarządzany przez "
                "`pipeline/footstats/magazyn_repo.py` — nie edytować ręcznie. "
                "Każdy zapis to nowy asset z sygnaturą czasu; najświeższy jest "
                "obowiązujący, starsze to kopie zapasowe.")


def _zaloz_release(repo: str, token: str, tag: str):
    """Release pod nasze assety.

    ⚑ ŚWIEŻO ZAŁOŻONE REPO JEST PUSTE, a tag musi na czymś wisieć — GitHub
    odrzuca wtedy release z 422 („Published releases must have a valid tag").
    Dlatego przy 422 zakładamy pierwszy commit (README) i próbujemy raz jeszcze.
    Bez tego pierwsze uruchomienie na nowym repo padałoby bez zrozumiałego
    powodu, a to jest dokładnie ten moment, w którym nikt nie ma cierpliwości.
    """
    def _post():
        return requests.post(
            f"{API}/repos/{repo}/releases",
            headers=_naglowki(token), timeout=30,
            json={"tag_name": tag, "name": "Stan pipeline'u",
                  "body": OPIS_RELEASE, "draft": False, "prerelease": False},
        )

    r = _z_ponowieniem("zalozenie release", _post)
    if r is not None and r.status_code < 300:
        return r
    if r is None or r.status_code != 422:
        return None

    print("Magazyn repo: repozytorium jest puste — zakładam pierwszy commit",
          flush=True)
    import base64
    tresc = base64.b64encode(
        ("# Stan pipeline'u footstats\n\n"
         "Magazyn danych roboczych. Zawartość jest w **Releases**, nie w "
         "drzewie plików.\n\nNie edytować ręcznie — pisze tu "
         "`pipeline/footstats/magazyn_repo.py`.\n").encode("utf-8")
    ).decode("ascii")
    z = _z_ponowieniem("pierwszy commit", lambda: requests.put(
        f"{API}/repos/{repo}/contents/README.md",
        headers=_naglowki(token), timeout=30,
        json={"message": "Magazyn stanu pipeline'u", "content": tresc},
    ))
    if z is None or z.status_code >= 300:
        return None
    return _z_ponowieniem("zalozenie release (po inicjalizacji)", _post)


def _release(repo: str, token: str, tag: str) -> tuple[int, list[dict]] | None:
    """(id release'u, assety). Release zakładamy sami, gdy go nie ma."""
    global _spis, _release_id
    if _spis is not None and _release_id is not None:
        return _release_id, _spis

    r = _z_ponowieniem("odczyt release", lambda: requests.get(
        f"{API}/repos/{repo}/releases/tags/{tag}",
        headers=_naglowki(token), timeout=30,
    ))
    if r is None:
        return None
    if r.status_code == 404:
        r = _zaloz_release(repo, token, tag)
        if r is None:
            return None
    elif r.status_code != 200:
        return None

    dane = r.json()
    _release_id = int(dane["id"])
    _spis = list(dane.get("assets") or [])
    return _release_id, _spis


def _wersje(spis: list[dict], key: str) -> list[dict]:
    """Assety danego klucza, od najświeższej wersji.

    ⚑ Tylko `uploaded`: `starter` to asset, którego wysyłka się urwała —
    ma nazwę, nie ma treści.
    """
    czolo = f"{key}{ROZDZIELNIK}"
    nasze = [a for a in spis
             if a.get("name", "").startswith(czolo)
             and a.get("name", "").endswith(ROZSZERZENIE)
             and a.get("state") == "uploaded"]
    return sorted(nasze, key=lambda a: a["name"], reverse=True)


def _sygnatura() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


# ------------------------------------------------------------ INTERFEJS -----
# Kontrakt jest TAKI SAM jak `supa.get_key_ok`: brak klucza to (None, True),
# awaria to (None, False). To rozróżnienie jest tu najważniejszą rzeczą.

def pobierz(key: str) -> tuple[object | None, bool]:
    k = _konf()
    if k is None:
        if _w_produkcji():
            print(f"Magazyn repo: brak STAN_REPO/STAN_TOKEN, a to przebieg "
                  f"produkcyjny — '{key}' traktuję jak NIEDOSTĘPNY, nie pusty",
                  file=sys.stderr, flush=True)
            return None, False
        return None, True          # lokalnie: nie ma czego stracić

    repo, token, tag = k
    rel = _release(repo, token, tag)
    if rel is None:
        return None, False
    _, spis = rel

    wersje = _wersje(spis, key)
    if not wersje:
        return None, True          # magazyn działa, klucza jeszcze nie ma

    asset = wersje[0]
    r = _z_ponowieniem(f"pobranie '{asset['name']}'", lambda: requests.get(
        f"{API}/repos/{repo}/releases/assets/{asset['id']}",
        headers=_naglowki(token, "application/octet-stream"), timeout=120,
    ))
    if r is None or r.status_code != 200:
        return None, False
    try:
        with gzip.open(io.BytesIO(r.content), "rt", encoding="utf-8") as f:
            return json.load(f), True
    except Exception as ex:  # noqa: BLE001
        # uszkodzony plik to AWARIA, nie pustka — pod żadnym pozorem nie
        # wolno tu zwrócić (None, True)
        print(f"Magazyn repo: '{asset['name']}' nie daje się rozpakować "
              f"({ex!r}) — traktuję jak padnięty odczyt",
              file=sys.stderr, flush=True)
        return None, False


def zapisz(key: str, payload) -> bool:
    k = _konf()
    if k is None:
        return False
    repo, token, tag = k
    rel = _release(repo, token, tag)
    if rel is None:
        return False
    rel_id, spis = rel

    try:
        surowe = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except Exception as ex:  # noqa: BLE001
        print(f"Magazyn repo: '{key}' nie daje się zserializować ({ex!r})",
              file=sys.stderr, flush=True)
        return False
    bufor = io.BytesIO()
    # mtime=0: ten sam payload daje ten sam bajt w bajt plik, więc łatwo
    # sprawdzić, czy coś się w ogóle zmieniło między wersjami
    with gzip.GzipFile(fileobj=bufor, mode="wb", compresslevel=6, mtime=0) as f:
        f.write(surowe)
    tresc = bufor.getvalue()

    nazwa = f"{key}{ROZDZIELNIK}{_sygnatura()}{ROZSZERZENIE}"
    r = _z_ponowieniem(f"wysyłka '{nazwa}'", lambda: requests.post(
        f"{UPLOADS}/repos/{repo}/releases/{rel_id}/assets?name={nazwa}",
        headers={**_naglowki(token), "Content-Type": "application/gzip"},
        data=tresc, timeout=300,
    ))
    if r is None or r.status_code >= 300:
        return False

    print(f"Magazyn repo: '{key}' → {len(surowe) / 1e6:.2f} MB "
          f"({len(tresc) / 1e6:.2f} MB gz) jako {nazwa}", flush=True)

    # spis w pamięci procesu musi znać nową wersję, inaczej odczyt w tym samym
    # przebiegu wróciłby do poprzedniej
    try:
        _spis.append(r.json())
    except Exception:  # noqa: BLE001
        wyczysc_pamiec()

    _posprzataj(repo, token, key)
    return True


def _posprzataj(repo: str, token: str, key: str) -> None:
    """Kasuj wersje ponad `RETENCJA` — DOPIERO po udanym zapisie nowej.

    Porażka sprzątania nie jest porażką zapisu: dane są na miejscu, a nadmiar
    wersji co najwyżej zajmuje miejsce.
    """
    if _spis is None:
        return
    nadmiar = _wersje(_spis, key)[RETENCJA:]
    for asset in nadmiar:
        r = _z_ponowieniem(f"kasowanie '{asset['name']}'",
                           lambda a=asset: requests.delete(
                               f"{API}/repos/{repo}/releases/assets/{a['id']}",
                               headers=_naglowki(token), timeout=30,
                           ))
        if r is not None and r.status_code < 300:
            try:
                _spis.remove(asset)
            except ValueError:
                pass


def podepnij() -> bool:
    """Zarejestruj ten magazyn w `supa` pod nazwą 'repo'. True = jest konfiguracja."""
    from . import supa
    supa.zarejestruj_backend("repo", sys.modules[__name__])
    return _konf() is not None
