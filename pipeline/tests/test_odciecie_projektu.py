# -*- coding: utf-8 -*-
"""ODCIĘCIE PROJEKTU PRZEZ SUPABASE (2026-08-28).

Gdy miesięczny limit transferu się wyczerpie, Supabase odcina cały projekt:
każde zapytanie z kluczem wraca jako 402 „exceed_egress_quota" — i odczyt,
i zapis. Od 25.08 znaczyło to czerwony cykl co godzinę i tyle samo maili
„workflow failed", w których nie było czego naprawiać: kod jest sprawny,
płatny jest dostęp do bazy.

Czerwony job ma znaczyć „coś do naprawienia w kodzie", więc odcięcie kończy
przebieg zielono, ale z ostrzeżeniem. KAŻDY inny błąd musi dalej wywalać job
na czerwono — inaczej strażnik zamiótłby pod dywan realną awarię.
"""
import pytest

from footstats import supa


class _Odp:
    def __init__(self, status, tresc=None):
        self.status_code = status
        self._tresc = tresc if tresc is not None else {}
        self.text = "…"

    def json(self):
        return self._tresc


@pytest.fixture(autouse=True)
def _czysty_stan(monkeypatch):
    """Znacznik odcięcia jest globalny na przebieg — testy nie mogą go dziedziczyć."""
    monkeypatch.setattr(supa, "_odciecie", None)
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)


KOMUNIKAT = ("Service for this project is restricted due to the following "
             "violations: exceed_egress_quota.")


def test_402_zostawia_slad_z_komunikatem_bazy():
    supa._z_ponowieniem("test", lambda: _Odp(402, {"message": KOMUNIKAT}))
    assert supa.odciecie_projektu() == KOMUNIKAT


def test_402_nie_jest_ponawiane():
    """To nie jest mrugnięcie sieci — powtórka wróci z tym samym 402."""
    proby = []

    def _woła():
        proby.append(1)
        return _Odp(402, {"message": KOMUNIKAT})

    supa._z_ponowieniem("test", _woła)
    assert len(proby) == 1


def test_straz_konczy_job_zielono_z_ostrzezeniem(monkeypatch, capsys):
    monkeypatch.setattr(supa, "_conn", lambda: ("https://x", {}))
    monkeypatch.setattr(supa.requests, "get",
                        lambda *a, **k: _Odp(402, {"message": KOMUNIKAT}))
    with pytest.raises(SystemExit) as wyj:
        supa.straz_odciecia("cykl")
    assert wyj.value.code == 0
    wyjscie = capsys.readouterr().out
    assert "::warning" in wyjscie and "402" in wyjscie


def test_zdrowa_baza_przepuszcza_job(monkeypatch):
    """Bez odcięcia strażnik ma być niewidoczny — job leci dalej normalnie."""
    monkeypatch.setattr(supa, "_conn", lambda: ("https://x", {}))
    monkeypatch.setattr(supa.requests, "get", lambda *a, **k: _Odp(200, []))
    supa.straz_odciecia("cykl")
    assert supa.odciecie_projektu() is None


def test_tryb_lokalny_nie_pyta_bazy(monkeypatch):
    """Bez sekretów (lokalnie) nie ma czego badać ani czym się blokować."""
    monkeypatch.setattr(supa, "_conn", lambda: None)
    monkeypatch.setattr(supa.requests, "get", lambda *a, **k: pytest.fail(
        "tryb lokalny nie powinien wołać Supabase"))
    supa.straz_odciecia("cykl")


def test_straz_bez_badania_nie_wola_sieci(monkeypatch):
    """Wołanie z łapania wyjątku: wiemy już z przebiegu, czy padło na 402."""
    monkeypatch.setattr(supa, "_conn", lambda: ("https://x", {}))
    monkeypatch.setattr(supa.requests, "get", lambda *a, **k: pytest.fail(
        "badaj=False nie ma prawa dokładać zapytania"))
    supa.straz_odciecia("cykl", badaj=False)
    monkeypatch.setattr(supa, "_odciecie", KOMUNIKAT)
    with pytest.raises(SystemExit) as wyj:
        supa.straz_odciecia("cykl", badaj=False)
    assert wyj.value.code == 0


# --- DZIENNY ALARM (2026-09-08) -------------------------------------------
# Zielony job ukrył drugie odcięcie na pięć dni. Raz na dobę, w oknie
# `ALARM_ODCIECIA_UTC`, straż kończy przebieg CZERWONO — GitHub wysyła mail
# tylko o czerwonych przebiegach.

def _gmtime(h, m):
    import time as _t
    return _t.struct_time((2026, 9, 8, h, m, 0, 1, 251, 0))


def test_w_oknie_alarmu_job_konczy_sie_czerwono(monkeypatch, capsys):
    monkeypatch.setattr(supa, "_conn", lambda: ("https://x", {}))
    monkeypatch.setattr(supa.requests, "get",
                        lambda *a, **k: _Odp(402, {"message": KOMUNIKAT}))
    monkeypatch.setattr(supa.time, "gmtime", lambda: _gmtime(6, 10))
    with pytest.raises(SystemExit) as wyj:
        supa.straz_odciecia("cykl")
    assert wyj.value.code == 1
    assert "::error" in capsys.readouterr().out


def test_poza_oknem_alarmu_dalej_zielono(monkeypatch, capsys):
    monkeypatch.setattr(supa, "_conn", lambda: ("https://x", {}))
    monkeypatch.setattr(supa.requests, "get",
                        lambda *a, **k: _Odp(402, {"message": KOMUNIKAT}))
    for h, m in ((5, 59), (6, 30), (13, 0)):
        monkeypatch.setattr(supa.time, "gmtime", lambda h=h, m=m: _gmtime(h, m))
        with pytest.raises(SystemExit) as wyj:
            supa.straz_odciecia("cykl")
        assert wyj.value.code == 0, (h, m)


# --- PAMIĘĆ ODCZYTÓW W PROCESIE (2026-09-08) --------------------------------
# 476 MB na cykl, z czego `typy_log` czytany 14 razy. `get_key` oddaje kopię
# z pamięci, `get_key_ok` zawsze pyta bazy, `put_key` odświeża wpis.

@pytest.fixture
def _baza(monkeypatch):
    stan = {"k": {"a": 1}}
    zapytania = []

    def _get(url, **k):
        zapytania.append(url)
        return _Odp(200, [{"payload": stan["k"]}] if "key=eq.k" in url else [])

    def _post(url, data=None, **k):
        import json
        stan["k"] = json.loads(data)[0]["payload"]
        return _Odp(201, {})

    monkeypatch.setattr(supa, "_conn", lambda: ("https://x", {}))
    monkeypatch.setattr(supa.requests, "get", _get)
    monkeypatch.setattr(supa.requests, "post", _post)
    monkeypatch.setattr(supa.requests, "delete", lambda *a, **k: _Odp(204, {}))
    supa.wyczysc_pamiec()
    yield stan, zapytania
    supa.wyczysc_pamiec()


def test_get_key_drugi_raz_nie_pyta_bazy(_baza):
    _, zapytania = _baza
    a = supa.get_key("k")
    b = supa.get_key("k")
    assert a == b == {"a": 1}
    assert len(zapytania) == 1
    assert "Odczyty z pamięci" in supa.raport_egress()


def test_get_key_oddaje_kopie_nie_ten_sam_obiekt(_baza):
    a = supa.get_key("k")
    a["a"] = 999
    assert supa.get_key("k") == {"a": 1}


def test_get_key_ok_zawsze_pyta_bazy_i_odswieza_pamiec(_baza):
    stan, zapytania = _baza
    supa.get_key("k")
    stan["k"] = {"a": 2}
    assert supa.get_key_ok("k") == ({"a": 2}, True)
    assert len(zapytania) == 2
    assert supa.get_key("k") == {"a": 2}
    assert len(zapytania) == 2


def test_put_key_podmienia_wpis_w_pamieci(_baza):
    _, zapytania = _baza
    supa.get_key("k")
    assert supa.put_key("k", {"a": 3})
    assert supa.get_key("k") == {"a": 3}
    assert len([u for u in zapytania if "key=eq.k" in u]) == 1


def test_brak_klucza_tez_jest_pamietany(_baza):
    _, zapytania = _baza
    assert supa.get_key("nie_ma") is None
    assert supa.get_key("nie_ma") is None
    assert len(zapytania) == 1
