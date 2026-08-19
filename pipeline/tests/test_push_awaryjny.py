# -*- coding: utf-8 -*-
"""PUSH WYSYŁA PACZKAMI, KTÓRE BAZA JEST W STANIE PRZYJĄĆ.

Historia (2026-08-13, przebieg #909): jeden upsert wszystkich kluczy naraz
kończył się `57014 canceling statement due to statement timeout`, a porażka
pushu wraca do `cycle.py` jako RuntimeError — czyli ~31 minut liczenia szło
do kosza. Wtedy dołożyliśmy ścieżkę zapasową: gdy zbiorczy padnie, dosyłamy
klucze po jednym.

AKTUALIZACJA 2026-08-19: zbiorczy zapis ZDJĘTY. Snapshoty urosły do 18,4 MB,
a zmierzony próg bazy to ~12 MB (14 MB → twarde 57014) — więc pierwsze
podejście padało ZAWSZE i kosztowało trzy próby z odczekaniem, zanim i tak
poszła ścieżka zapasowa. Teraz od razu składamy paczki mieszczące się w
limicie, a klucz cięższy od progu idzie przez `supa.put_key`, który potnie go
na części (`players` to 9,1 MB i pojedynczo też nie przechodził).
"""
import json

import pytest

from footstats import supa
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


def test_lekkie_klucze_jada_jedna_paczka(dane, monkeypatch):
    wywolania = []

    def _upsert(url, key, payload, opis):
        wywolania.append(opis)
        return _Odp(201)

    monkeypatch.setattr(P, "_upsert", _upsert)
    assert P.push() is True
    # trzy drobne klucze mieszczą się razem — jeden strzał, zero dosyłania
    assert wywolania == ["paczka 1/1 (3 kluczy)"]


def test_nie_probujemy_juz_zbiorczego_ponad_limit(dane, monkeypatch):
    """Sedno zmiany: żaden pojedynczy upsert nie może przekroczyć progu bazy."""
    ladunki = []

    def _upsert(url, key, payload, opis):
        ladunki.append(payload)
        return _Odp(201)

    monkeypatch.setattr(P, "_upsert", _upsert)
    monkeypatch.setattr(supa, "PROG_SZARDU", 60)     # mikroskopijny limit
    assert P.push() is True
    assert len(ladunki) > 1, "przy ciasnym limicie musi powstać kilka paczek"
    assert all(len(l) <= supa.PROG_SZARDU for l in ladunki)


def test_padnieta_paczka_dosyla_swoje_klucze_po_jednym(dane, monkeypatch):
    """Jeden chory snapshot nie może zabrać ze sobą zdrowych sąsiadów."""
    wywolania = []

    def _upsert(url, key, payload, opis):
        wywolania.append(opis)
        if opis.startswith("paczka"):
            return _Odp(500, TIMEOUT_57014)
        return _Odp(201)

    monkeypatch.setattr(P, "_upsert", _upsert)
    assert P.push() is True
    assert wywolania[0].startswith("paczka")
    assert sorted(wywolania[1:]) == [
        "push 'players'", "push 'radar'", "push 'value_bets'",
    ]


def test_kazda_dosylka_niesie_jeden_klucz(dane, monkeypatch):
    """Sens dosyłania polega na tym, że pojedynczy zapis jest MAŁY."""
    ladunki = []

    def _upsert(url, key, payload, opis):
        ladunki.append(json.loads(payload))
        return _Odp(500, TIMEOUT_57014) if opis.startswith("paczka") else _Odp(201)

    monkeypatch.setattr(P, "_upsert", _upsert)
    P.push()
    assert len(ladunki[0]) == 3                      # paczka: komplet
    assert all(len(l) == 1 for l in ladunki[1:])     # dosyłki: po jednym


def test_ciezki_klucz_idzie_przez_szardy(dane, monkeypatch):
    """`players` (9,1 MB na produkcji) nie przechodzi nawet pojedynczo —
    musi trafić do `supa.put_key`, który potnie go na części."""
    (dane / "players.json").write_text(json.dumps({"a": "x" * 500}),
                                       encoding="utf-8")
    monkeypatch.setattr(supa, "PROG_SZARDU", 200)
    przez_szardy, przez_paczki = [], []
    monkeypatch.setattr(supa, "put_key",
                        lambda k, v: przez_szardy.append(k) or True)

    def _upsert(url, key, payload, opis):
        przez_paczki.extend(w["key"] for w in json.loads(payload))
        return _Odp(201)

    monkeypatch.setattr(P, "_upsert", _upsert)
    assert P.push() is True
    assert przez_szardy == ["players"]
    assert "players" not in przez_paczki


def test_czesciowe_dowiezienie_jest_awaria(dane, monkeypatch):
    """Część kluczy świeża, część nie = rozjazd danych. `cycle.py` ma z tego
    zrobić awarię, zamiast przepuścić go po cichu."""
    def _upsert(url, key, payload, opis):
        if opis.startswith("paczka"):
            return _Odp(500, TIMEOUT_57014)
        return _Odp(201) if "players" in opis else _Odp(500, TIMEOUT_57014)

    monkeypatch.setattr(P, "_upsert", _upsert)
    assert P.push() is False


def test_niedowieziony_szard_tez_jest_awaria(dane, monkeypatch):
    (dane / "players.json").write_text(json.dumps({"a": "x" * 500}),
                                       encoding="utf-8")
    monkeypatch.setattr(supa, "PROG_SZARDU", 200)
    monkeypatch.setattr(supa, "put_key", lambda k, v: False)
    monkeypatch.setattr(P, "_upsert", lambda *a, **kw: _Odp(201))
    assert P.push() is False


def test_brak_odpowiedzi_tez_uruchamia_dosylanie(dane, monkeypatch):
    """Gdy paczka nie doczekała się odpowiedzi (None po ponowieniach),
    próbujemy tak samo — sieć mogła paść na rozmiarze, nie na treści."""
    def _upsert(url, key, payload, opis):
        return None if opis.startswith("paczka") else _Odp(201)

    monkeypatch.setattr(P, "_upsert", _upsert)
    assert P.push() is True
