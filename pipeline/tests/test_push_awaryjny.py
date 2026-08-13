# -*- coding: utf-8 -*-
"""PUSH DOSYŁA PO JEDNYM, GDY BAZA NIE PRZYJMIE ZBIORCZEGO (2026-08-13).

Potwierdzone logiem przebiegu #909:

    Supabase push błąd 500: {"code":"57014",
      "message":"canceling statement due to statement timeout"}
    RuntimeError: push_supabase.push() zwrócił False …

To NIE był timeout po naszej stronie — wysyłka trwała 18 s przy limicie
klienta 30 s. Postgres przerwał WŁASNE zapytanie, bo jeden upsert 14 kluczy
waży ~4,9 MB. Efekt: ~31 minut liczenia szło do kosza, a strona zostawała
z danymi sprzed godzin.
"""
import json

import pytest

from footstats.jobs import push_supabase as P


class _Odp:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text


TIMEOUT_57014 = json.dumps({
    "code": "57014", "message": "canceling statement due to statement timeout",
})


@pytest.fixture
def dane(tmp_path, monkeypatch):
    """Trzy klucze na dysku, jak po zwykłym cyklu."""
    monkeypatch.setattr(P, "WEB_DATA_DIR", tmp_path)
    monkeypatch.setattr(P, "KEYS", ["value_bets", "players", "radar"])
    for nazwa, tresc in (("value_bets", [1, 2]), ("players", {"a": 1}),
                         ("radar", {"wpisy": []})):
        (tmp_path / f"{nazwa}.json").write_text(json.dumps(tresc), encoding="utf-8")
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "klucz")
    return tmp_path


def test_zbiorczy_zapis_wystarcza_gdy_baza_wyrabia(dane, monkeypatch):
    wywolania = []

    def _upsert(url, key, payload, opis):
        wywolania.append(opis)
        return _Odp(201)

    monkeypatch.setattr(P, "_upsert", _upsert)
    assert P.push() is True
    # jeden strzał, bez dosyłania po kluczu
    assert wywolania == ["push snapshotów"]


def test_po_57014_dosyla_klucze_pojedynczo(dane, monkeypatch):
    """Zbiorczy pada tak jak w #909, ale cykl ma dowieźć dane, nie polec."""
    wywolania = []

    def _upsert(url, key, payload, opis):
        wywolania.append(opis)
        if opis == "push snapshotów":
            return _Odp(500, TIMEOUT_57014)
        return _Odp(201)

    monkeypatch.setattr(P, "_upsert", _upsert)
    assert P.push() is True
    assert wywolania[0] == "push snapshotów"
    # każdy klucz osobno, od najmniejszego
    assert sorted(wywolania[1:]) == [
        "push 'players'", "push 'radar'", "push 'value_bets'",
    ]


def test_kazdy_dosylany_upsert_niesie_jeden_klucz(dane, monkeypatch):
    """Sens dosyłania polega na tym, że pojedynczy zapis jest MAŁY."""
    ladunki = []

    def _upsert(url, key, payload, opis):
        ladunki.append(json.loads(payload))
        return _Odp(500, TIMEOUT_57014) if opis == "push snapshotów" else _Odp(201)

    monkeypatch.setattr(P, "_upsert", _upsert)
    P.push()
    assert len(ladunki[0]) == 3                      # zbiorczy: komplet
    assert all(len(l) == 1 for l in ladunki[1:])     # dosyłki: po jednym


def test_czesciowe_dowiezienie_jest_awaria(dane, monkeypatch):
    """Część kluczy świeża, część nie = rozjazd danych. `cycle.py` ma z tego
    zrobić awarię, zamiast przepuścić go po cichu."""
    def _upsert(url, key, payload, opis):
        if opis == "push snapshotów":
            return _Odp(500, TIMEOUT_57014)
        return _Odp(201) if "players" in opis else _Odp(500, TIMEOUT_57014)

    monkeypatch.setattr(P, "_upsert", _upsert)
    assert P.push() is False


def test_brak_odpowiedzi_tez_uruchamia_dosylanie(dane, monkeypatch):
    """Gdy zbiorczy nie doczekał się odpowiedzi (None po ponowieniach),
    próbujemy tak samo — sieć mogła paść na rozmiarze, nie na treści."""
    def _upsert(url, key, payload, opis):
        return None if opis == "push snapshotów" else _Odp(201)

    monkeypatch.setattr(P, "_upsert", _upsert)
    assert P.push() is True
