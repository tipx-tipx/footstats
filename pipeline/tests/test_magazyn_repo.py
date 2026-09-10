# -*- coding: utf-8 -*-
"""MAGAZYN STANU W PRYWATNYM REPO (2026-09-10, etap 2 przeprowadzki).

Pilnujemy tego, co odróżnia ten magazyn od naiwnego „wgraj plik przez API":

1. zapis DOPISUJE nową wersję i nigdy nie kasuje przed wgraniem — nie ma
   okna, w którym klucz nie istnieje (sedno całego projektu);
2. odczyt bierze najświeższą wersję, ale POMIJA assety w stanie `starter`,
   czyli takie, których wysyłka się urwała: mają nazwę, nie mają treści;
3. brak konfiguracji w produkcji to AWARIA, nie pusty magazyn — inaczej
   zapomniany sekret kazałby pipeline'owi zacząć historię od zera.
"""
import gzip
import io
import json

import pytest

from footstats import magazyn_repo as mr


class _Odp:
    def __init__(self, status, dane=None, tresc=b""):
        self.status_code = status
        self._dane = dane if dane is not None else {}
        self.content = tresc

    def json(self):
        return self._dane


def _gz(obj) -> bytes:
    b = io.BytesIO()
    with gzip.GzipFile(fileobj=b, mode="wb", mtime=0) as f:
        f.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    return b.getvalue()


class _GitHub:
    """Zaślepka API: trzyma assety release'u i notuje kolejność operacji."""

    def __init__(self, assety=None, upload_status=201):
        self.assety = list(assety or [])
        self.upload_status = upload_status
        self.slad: list[str] = []
        self._nastepny_id = 1000

    # --- API używane przez magazyn ---
    def get(self, url, **kw):
        if "/releases/tags/" in url:
            self.slad.append("spis")
            return _Odp(200, {"id": 7, "assets": self.assety})
        if "/releases/assets/" in url:
            aid = int(url.rsplit("/", 1)[1])
            for a in self.assety:
                if a["id"] == aid:
                    self.slad.append(f"pobierz:{a['name']}")
                    return _Odp(200, tresc=a["_tresc"])
            return _Odp(404)
        raise AssertionError(f"nieoczekiwany GET {url}")

    def post(self, url, data=None, **kw):
        if "/assets?name=" in url:
            nazwa = url.split("name=")[1]
            self.slad.append(f"wyslij:{nazwa}")
            if self.upload_status >= 300:
                return _Odp(self.upload_status)
            self._nastepny_id += 1
            asset = {"id": self._nastepny_id, "name": nazwa,
                     "state": "uploaded", "_tresc": data}
            self.assety.append(asset)
            return _Odp(201, asset)
        if url.endswith("/releases"):
            self.slad.append("zaloz-release")
            return _Odp(201, {"id": 7, "assets": []})
        raise AssertionError(f"nieoczekiwany POST {url}")

    def delete(self, url, **kw):
        aid = int(url.rsplit("/", 1)[1])
        for a in list(self.assety):
            if a["id"] == aid:
                self.slad.append(f"kasuj:{a['name']}")
                self.assety.remove(a)
                return _Odp(204)
        return _Odp(404)


@pytest.fixture
def gh(monkeypatch):
    def _zbuduj(assety=None, upload_status=201, konf=True, produkcja=False):
        api = _GitHub(assety, upload_status)
        monkeypatch.setattr(mr, "requests", api)
        monkeypatch.setattr(mr.time, "sleep", lambda _: None)
        mr.wyczysc_pamiec()
        for zmienna in ("STAN_REPO", "STAN_TOKEN", "STAN_TAG",
                        "SUPABASE_URL", "CI"):
            monkeypatch.delenv(zmienna, raising=False)
        if konf:
            monkeypatch.setenv("STAN_REPO", "tipx-tipx/footstats-stan")
            monkeypatch.setenv("STAN_TOKEN", "token-testowy")
        if produkcja:
            monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        return api
    yield _zbuduj
    mr.wyczysc_pamiec()


def _asset(nazwa, dane, stan="uploaded", aid=1):
    return {"id": aid, "name": nazwa, "state": stan, "_tresc": _gz(dane)}


# ---------------------------------------------------------------- ODCZYT ----

def test_czyta_najswiezsza_wersje(gh):
    gh([_asset("typy_log--20260901T000000Z.json.gz", {"stare": 1}, aid=1),
        _asset("typy_log--20260910T120000Z.json.gz", {"nowe": 2}, aid=2)])
    assert mr.pobierz("typy_log") == ({"nowe": 2}, True)


def test_pomija_niedokonczona_wysylke(gh):
    """Asset `starter` ma nazwę, ale nie ma treści — nie wolno go czytać."""
    gh([_asset("typy_log--20260901T000000Z.json.gz", {"dobre": 1}, aid=1),
        _asset("typy_log--20260910T120000Z.json.gz", {}, stan="starter", aid=2)])
    assert mr.pobierz("typy_log") == ({"dobre": 1}, True)


def test_brak_klucza_to_pustka(gh):
    gh([_asset("inny_klucz--20260910T120000Z.json.gz", {"x": 1})])
    assert mr.pobierz("typy_log") == (None, True)


def test_uszkodzony_plik_to_awaria_nie_pustka(gh):
    gh([{"id": 1, "name": "typy_log--20260910T120000Z.json.gz",
         "state": "uploaded", "_tresc": b"to nie jest gzip"}])
    assert mr.pobierz("typy_log") == (None, False)


def test_padniete_api_to_awaria(gh):
    api = gh([_asset("typy_log--20260910T120000Z.json.gz", {"x": 1})])
    api.get = lambda *a, **k: _Odp(500)
    assert mr.pobierz("typy_log") == (None, False)


def test_klucze_sie_nie_mieszaja(gh):
    """`typy_log` i `typy_log_kopia` mają wspólny przedrostek."""
    gh([_asset("typy_log--20260910T120000Z.json.gz", {"ksiega": 1}, aid=1),
        _asset("typy_log_kopia--20260910T130000Z.json.gz", {"kopia": 1}, aid=2)])
    assert mr.pobierz("typy_log") == ({"ksiega": 1}, True)
    assert mr.pobierz("typy_log_kopia") == ({"kopia": 1}, True)


# ------------------------------------------------------- BRAK KONFIGURACJI --

def test_lokalnie_brak_konfiguracji_to_pustka(gh):
    gh(konf=False)
    assert mr.pobierz("typy_log") == (None, True)
    assert mr.zapisz("typy_log", {"x": 1}) is False


def test_w_produkcji_brak_konfiguracji_to_awaria(gh):
    """Zapomniany sekret NIE MOŻE wyglądać jak pusty magazyn."""
    gh(konf=False, produkcja=True)
    assert mr.pobierz("typy_log") == (None, False)


# ----------------------------------------------------------------- ZAPIS ----

def test_zapis_dopisuje_nie_podmienia(gh):
    """SEDNO: stara wersja żyje, dopóki nowa nie jest w całości na miejscu."""
    api = gh([_asset("typy_log--20260901T000000Z.json.gz", {"stare": 1}, aid=1)])
    assert mr.zapisz("typy_log", {"nowe": 2}) is True

    wyslij = api.slad.index(next(s for s in api.slad if s.startswith("wyslij:")))
    kasuj = [i for i, s in enumerate(api.slad) if s.startswith("kasuj:")]
    assert all(i > wyslij for i in kasuj), \
        "kasowanie PRZED wysyłką otwiera okno, w którym klucza nie ma"


def test_zapis_i_odczyt_w_jednym_procesie(gh):
    gh()
    assert mr.zapisz("typy_log", {"a": 1}) is True
    assert mr.pobierz("typy_log") == ({"a": 1}, True)


def test_padnieta_wysylka_zostawia_stara_wersje(gh):
    api = gh([_asset("typy_log--20260901T000000Z.json.gz", {"stare": 1}, aid=1)],
             upload_status=500)
    assert mr.zapisz("typy_log", {"nowe": 2}) is False
    assert not [s for s in api.slad if s.startswith("kasuj:")]
    assert mr.pobierz("typy_log") == ({"stare": 1}, True)


def test_retencja_zostawia_ostatnie_wersje(gh):
    stare = [_asset(f"typy_log--202609{d:02d}T000000Z.json.gz", {"d": d}, aid=d)
             for d in range(1, 9)]
    api = gh(stare)
    assert mr.zapisz("typy_log", {"nowe": 1}) is True

    zostaly = [a["name"] for a in mr._wersje(api.assety, "typy_log")]
    assert len(zostaly) == mr.RETENCJA

    # 8 starych + 1 nowa, retencja 5 → zostaje nowa i CZTERY najświeższe stare
    for dzien in ("20260908", "20260907", "20260906", "20260905"):
        assert sum(1 for n in zostaly if dzien in n) == 1, f"{dzien} miał zostać"
    for dzien in ("20260901", "20260902", "20260903", "20260904"):
        assert not any(dzien in n for n in zostaly), f"{dzien} miał zostać skasowany"
    # i najświeższa z nich to ta właśnie zapisana
    assert mr.pobierz("typy_log") == ({"nowe": 1}, True)


def test_release_zakladany_gdy_go_nie_ma(gh, monkeypatch):
    api = gh()
    api.get = lambda *a, **k: _Odp(404)
    assert mr.zapisz("typy_log", {"x": 1}) is True
    assert "zaloz-release" in api.slad


# ------------------------------------------------- SPIĘCIE Z ROUTEREM supa --

def test_przez_router_supa(gh, monkeypatch):
    """Droga, którą naprawdę pójdzie pipeline: supa.get_key -> magazyn."""
    from footstats import supa
    gh([_asset("typy_log--20260910T120000Z.json.gz", {"z_repo": 1})])
    monkeypatch.setattr(supa, "MAGAZYN", {"typy_log": "repo"})
    monkeypatch.setattr(supa, "_BACKENDY", {})
    monkeypatch.setattr(supa, "_conn", lambda: (_ for _ in ()).throw(
        AssertionError("nie wolno dotknąć Supabase")))
    supa.wyczysc_pamiec()
    mr.podepnij()

    assert supa.get_key("typy_log") == {"z_repo": 1}
    supa.wyczysc_pamiec()


def test_puste_repo_dostaje_pierwszy_commit(gh):
    """Świeże repo nie ma commita, więc tag nie ma na czym wisieć (422).

    Pierwsze uruchomienie na nowym repo musi się samo z tego wygrzebać —
    to najgorszy moment na nieczytelny błąd.
    """
    api = gh()
    stan = {"pusto": True}

    def _get(url, **kw):
        if "/releases/tags/" in url:
            return _Odp(404)
        raise AssertionError(url)

    def _post(url, data=None, **kw):
        if url.endswith("/releases"):
            api.slad.append("zaloz-release")
            if stan["pusto"]:
                return _Odp(422, {"message": "Published releases must have a valid tag"})
            return _Odp(201, {"id": 7, "assets": []})
        return _GitHub.post(api, url, data=data, **kw)

    def _put(url, **kw):
        assert url.endswith("/contents/README.md")
        api.slad.append("pierwszy-commit")
        stan["pusto"] = False
        return _Odp(201, {})

    api.get, api.post, api.put = _get, _post, _put
    assert mr.zapisz("typy_log", {"x": 1}) is True
    assert api.slad[:3] == ["zaloz-release", "pierwszy-commit", "zaloz-release"]


def test_naglowki_maja_user_agent():
    """GitHub odrzuca 403 kazde zadanie bez `User-Agent` (2026-09-10).

    `curl_cffi` bez `impersonate` go nie wysyla, a odpowiedz brzmi
    „Request forbidden by administrative rules" — po samym kodzie 403
    wyglada to na zly token i mozna szukac godzinami nie tam.
    """
    assert mr._naglowki("x").get("User-Agent")
