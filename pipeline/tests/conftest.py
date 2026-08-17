"""Sieć w testach jest DOMYŚLNIE ZABLOKOWANA.

PO CO TO ISTNIEJE. 2026-07-31 okazało się, że dwa pliki testów naprawdę
dzwoniły do Betclica — zestaw 470 testów NIGDY się nie kończył, czyli przez
jakiś czas nie chronił niczego. Zaślepienie tamtych dwóch wywołań naprawiło
objaw, ale nie klasę problemu: za miesiąc dojdzie kolejne źródło i historia
się powtórzy, tyle że wykryjemy ją znowu dopiero po tym, jak CI zacznie
wisieć.

Dlatego sieć jest tu ZAMKNIĘTA NA GŁUCHO, a test, który naprawdę jej
potrzebuje, musi o to poprosić jawnie:

    @pytest.mark.siec
    def test_prawdziwy_odczyt_z_superbetu(): ...

Blokada stoi na DWÓCH poziomach, bo jeden nie wystarcza:
  * `curl_cffi` (którym chodzi CAŁY pipeline) używa libcurl w C i NIE
    przechodzi przez pythonowy moduł `socket` — samo załatanie gniazd
    przepuściłoby każde nasze realne zapytanie,
  * `socket` łapie wszystko inne (`urllib`, `requests`, biblioteki trzecie),
    czyli to, czego jeszcze nie ma w repo.

Localhost zostaje otwarty — blokujemy wyjście na świat, nie testy, które
podnoszą własny serwer w pamięci.
"""

from __future__ import annotations

import socket

import pytest
from curl_cffi import requests as _curl


class WyjscieDoSieciWTescie(RuntimeError):
    """Test spróbował wyjść do internetu bez znacznika `@pytest.mark.siec`."""


_LOKALNE = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}

# funkcje modułu curl_cffi.requests, którymi realnie chodzi pipeline
_FUNKCJE_CURL = (
    "get", "post", "put", "patch", "delete", "head", "options", "request",
)


def _host(adres) -> str:
    if isinstance(adres, (tuple, list)) and adres:
        return str(adres[0])
    return str(adres)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "siec: test celowo wychodzi do internetu (domyślnie sieć jest "
        "zablokowana — patrz tests/conftest.py)",
    )


@pytest.fixture(autouse=True)
def _sieciowa_zapora(request, monkeypatch):
    """Domyślnie DENY. `@pytest.mark.siec` otwiera ruch dla jednego testu."""
    if request.node.get_closest_marker("siec"):
        yield
        return

    def _stop(co: str):
        def _blokada(*args, **kwargs):
            raise WyjscieDoSieciWTescie(
                f"test próbował wyjść do sieci przez {co}. Zaślep źródło "
                "(monkeypatch) albo oznacz test @pytest.mark.siec, jeśli "
                "kontakt z internetem jest tu celem."
            )
        return _blokada

    for nazwa in _FUNKCJE_CURL:
        if hasattr(_curl, nazwa):
            monkeypatch.setattr(_curl, nazwa, _stop(f"curl_cffi.{nazwa}"), raising=False)
    if hasattr(_curl, "Session"):
        monkeypatch.setattr(
            _curl.Session, "request", _stop("curl_cffi.Session.request"),
            raising=False,
        )

    connect_org = socket.socket.connect
    create_org = socket.create_connection

    def _connect(self, adres, *a, **kw):
        if _host(adres) in _LOKALNE:
            return connect_org(self, adres, *a, **kw)
        _stop("socket.connect")()

    def _create(adres, *a, **kw):
        if _host(adres) in _LOKALNE:
            return create_org(adres, *a, **kw)
        _stop("socket.create_connection")()

    monkeypatch.setattr(socket.socket, "connect", _connect)
    monkeypatch.setattr(socket, "create_connection", _create)

    # BACKOFF PONOWIEŃ NIE OBOWIĄZUJE W TESTACH (2026-08-13). Zapora wyżej
    # rzuca wyjątkiem, a `supa._z_ponowieniem` traktuje każdy wyjątek jak
    # awarię sieci i odczekuje 2 + 8 s, zanim się podda. Zestaw urósł przez to
    # z 8 do 78 sekund — sześć testów wołających Supabase przez zaślepki
    # płaciło pełny backoff. Zerujemy SAM CZAS, nie liczbę prób: inaczej testy
    # ponowień przestałyby pilnować tego, po co powstały.
    from footstats import supa
    monkeypatch.setattr(supa, "PRZERWY_S", (0, 0))
    # TO SAMO DLA ŹRÓDEŁ (2026-08-17). `statshub._get` ponawia trzy razy ze snem
    # 3 i 6 s, więc każdy mecz, o którego status pyta rozliczanie przez
    # zaślepioną sieć, kosztował zestaw 9 sekund — 13 s urosło do 5 minut.
    # Zerujemy sam odstęp; liczba prób zostaje, żeby testy ponowień dalej miały
    # czego pilnować.
    from footstats.sources import statshub
    monkeypatch.setattr(statshub, "PAUZA_PONOWIENIA_S", 0)
    yield
