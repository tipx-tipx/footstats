"""Zapora sieciowa testów — sprawdza samą siebie.

Bez tego pliku zapora z `conftest.py` jest założeniem: gdyby ktoś ją kiedyś
zepsuł (np. zmieniając nazwę biblioteki HTTP), zestaw dalej byłby zielony,
tyle że znowu chodziłby do internetu. Test poniżej pilnuje, żeby cisza
oznaczała „nie ma ruchu", a nie „nie patrzymy".

Ile to realnie kosztowało: po włączeniu zapory 2026-08-01 pięć testów
rozliczania okazało się wychodzić do statshuba przy KAŻDYM przebiegu.
Po zaślepieniu tych źródeł cały zestaw skrócił się z 45 do 9 sekund.
"""

import socket

import pytest
from curl_cffi import requests as _curl

from conftest import WyjscieDoSieciWTescie


def test_curl_cffi_jest_zablokowany():
    with pytest.raises(WyjscieDoSieciWTescie):
        _curl.get("https://example.com")


def test_gniazdo_do_swiata_jest_zablokowane():
    with pytest.raises(WyjscieDoSieciWTescie):
        socket.create_connection(("example.com", 443), timeout=1)


def test_localhost_zostaje_otwarty():
    """Blokujemy wyjście na świat, nie testy z własnym serwerem w pamięci."""
    s = socket.socket()
    try:
        # nikt tu nie słucha — liczy się to, że NIE dostajemy WyjscieDoSieci
        with pytest.raises(OSError) as e:
            s.connect(("127.0.0.1", 1))
        assert not isinstance(e.value, WyjscieDoSieciWTescie)
    finally:
        s.close()


@pytest.mark.siec
def test_znacznik_siec_zdejmuje_blokade():
    """Test integracyjny może poprosić o sieć jawnie — i wtedy ją dostaje.

    Sam ruchu nie robimy (CI bywa bez internetu): sprawdzamy, że funkcja
    NIE jest już zaślepką.
    """
    assert not isinstance(
        getattr(_curl.get, "__name__", ""), type(None)
    )
    assert _curl.get.__name__ != "_blokada"
