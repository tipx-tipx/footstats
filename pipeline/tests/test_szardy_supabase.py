# -*- coding: utf-8 -*-
"""DUŻY KLUCZ ZAPISYWANY W CZĘŚCIACH (2026-08-19).

Zapis do `app_data` rośnie w czasie SZYBCIEJ NIŻ LINIOWO wraz z payloadem —
zmierzone upserty tej samej struktury: 8 MB → 7,8 s, 10 MB → 23,2 s,
12 MB → 34,8 s, 14 MB → HTTP 500 (57014 „canceling statement due to statement
timeout"). Trzy nasze najcięższe klucze siedziały w tym paśmie: `trend_lib`
(14,0 MB), `typy_log` (12,4 MB) i `players` (9,1 MB) — ten ostatni wywalał
CAŁY cykl po 36 minutach liczenia, bo `cycle.py` robi z porażki pushu
RuntimeError.

Testujemy trzy rzeczy, każda odpowiada innej klasie awarii:
  1. duży payload w ogóle idzie w kawałkach i wraca w całości,
  2. marker powstaje DOPIERO po częściach (inaczej czytelnik zobaczyłby
     nowy nagłówek nad starymi danymi),
  3. brak choćby jednej części to AWARIA ODCZYTU, nie pusty klucz — bo
     wołający dopisuje do historii i zapisuje ją z powrotem.
"""
import json

import pytest

from footstats import supa


class _Odp:
    def __init__(self, status: int, dane=None):
        self.status_code = status
        self._dane = dane if dane is not None else []
        self.text = "…"

    def json(self):
        return self._dane


class _Baza:
    """Atrapa `app_data`: pamięta klucze i kolejność zapisów."""

    def __init__(self, zawartosc: dict | None = None):
        self.dane: dict = dict(zawartosc or {})
        self.kolejnosc: list[str] = []
        self.padaja: set[str] = set()

    # --- podpięcie pod curl_cffi ---------------------------------------
    def post(self, url, headers=None, data=None, **kw):
        wiersze = json.loads(data)
        for w in wiersze:
            if w["key"] in self.padaja:
                return _Odp(500, {"code": "57014"})
            self.dane[w["key"]] = w["payload"]
            self.kolejnosc.append(w["key"])
        return _Odp(201)

    def get(self, url, headers=None, **kw):
        if "key=like." in url:
            wzor = url.split("key=like.")[1].split("&")[0].rstrip("*")
            trafione = [k for k in self.dane if k.startswith(wzor)]
            if "select=key,payload" in url:
                return _Odp(200, [{"key": k, "payload": self.dane[k]}
                                  for k in trafione])
            return _Odp(200, [{"key": k} for k in trafione])
        klucz = url.split("key=eq.")[1].split("&")[0]
        if klucz not in self.dane:
            return _Odp(200, [])
        return _Odp(200, [{"payload": self.dane[klucz]}])

    def delete(self, url, headers=None, **kw):
        klucz = url.split("key=eq.")[1].split("&")[0]
        self.dane.pop(klucz, None)
        return _Odp(204)


@pytest.fixture()
def baza(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)
    b = _Baza()
    monkeypatch.setattr(supa.requests, "post", b.post)
    monkeypatch.setattr(supa.requests, "get", b.get)
    monkeypatch.setattr(supa.requests, "delete", b.delete)
    return b


def _ksiega(n: int) -> dict:
    """Payload w kształcie prawdziwej księgi typów."""
    return {f"{i}:zawodnik:sot:0.5:powyzej": {
        "mecz": "Drużyna A – Drużyna B", "kurs": 1.85, "p_model": 0.71,
        "podmiot": f"Zawodnik {i}", "rynek": "sot", "czynniki": ["forma", "rywal"],
    } for i in range(n)}


def _duzy(monkeypatch, ile_czesci: int = 3) -> dict:
    """Księga na tyle ciężka, że musi pójść w `ile_czesci` kawałkach."""
    ksiega = _ksiega(400)
    waga = supa.waga(ksiega)
    monkeypatch.setattr(supa, "PROG_SZARDU", waga // 2)
    monkeypatch.setattr(supa, "CEL_CZESCI", waga // ile_czesci + 1)
    return ksiega


def test_maly_klucz_idzie_jak_dotad(baza):
    assert supa.put_key("meta", {"ts": 1}) is True
    assert baza.dane == {"meta": {"ts": 1}}
    assert supa.get_key_ok("meta") == ({"ts": 1}, True)


def test_duzy_klucz_wraca_w_calosci(baza, monkeypatch):
    ksiega = _duzy(monkeypatch)
    assert supa.put_key("typy_log", ksiega) is True
    assert supa.ile_czesci(baza.dane["typy_log"]) is not None, \
        "pod głównym kluczem powinien zostać marker, nie dane"
    assert supa.get_key_ok("typy_log") == (ksiega, True)


def test_lista_tez_wraca_w_kolejnosci(baza, monkeypatch):
    zawodnicy = [{"id": i, "nazwa": f"Zawodnik {i}", "forma": {"shots": [1] * 20}}
                 for i in range(300)]
    waga = supa.waga(zawodnicy)
    monkeypatch.setattr(supa, "PROG_SZARDU", waga // 2)
    monkeypatch.setattr(supa, "CEL_CZESCI", waga // 3 + 1)
    assert supa.put_key("players", zawodnicy) is True
    odczyt, ok = supa.get_key_ok("players")
    assert ok and odczyt == zawodnicy       # kolejność też, nie tylko zawartość


def test_marker_powstaje_DOPIERO_po_czesciach(baza, monkeypatch):
    """Odwrotna kolejność zostawiałaby czytelnikowi nagłówek bez treści."""
    ksiega = _duzy(monkeypatch)
    supa.put_key("typy_log", ksiega)
    assert baza.kolejnosc[-1] == "typy_log", \
        "marker musi być ostatni — inaczej czytelnik trafia na niekomplet"
    assert all(k.startswith("typy_log__cz") for k in baza.kolejnosc[:-1])


def test_padnieta_czesc_nie_rusza_glownego_klucza(baza, monkeypatch):
    ksiega = _duzy(monkeypatch)
    baza.dane["typy_log"] = _ksiega(5)          # poprzednia, spójna wersja
    baza.padaja = {"typy_log__cz01"}
    assert supa.put_key("typy_log", ksiega) is False
    assert baza.dane["typy_log"] == _ksiega(5), \
        "gdy część nie doszła, pod kluczem ma zostać STARA całość"


def test_brak_czesci_to_awaria_odczytu_a_nie_pustka(baza, monkeypatch):
    """Najgroźniejszy przypadek: wołający dopisuje do historii i zapisuje ją
    z powrotem — sklejona połowa skończyłaby się skasowaniem reszty."""
    ksiega = _duzy(monkeypatch)
    supa.put_key("typy_log", ksiega)
    baza.dane.pop("typy_log__cz01")
    assert supa.get_key_ok("typy_log") == (None, False)


def test_schudniety_klucz_sprzata_po_sobie(baza, monkeypatch):
    ksiega = _duzy(monkeypatch)
    supa.put_key("typy_log", ksiega)
    assert [k for k in baza.dane if "__cz" in k]
    # ta sama nazwa, ale payload już mieści się w limicie
    monkeypatch.setattr(supa, "PROG_SZARDU", 4_000_000)
    assert supa.put_key("typy_log", {"a": 1}) is True
    assert [k for k in baza.dane if "__cz" in k] == [], \
        "kawałki bez czytelnika zostałyby w bazie na zawsze"
    assert supa.get_key_ok("typy_log") == ({"a": 1}, True)


def test_mniej_czesci_niz_poprzednio_kasuje_ogon(baza, monkeypatch):
    supa.put_key("typy_log", _duzy(monkeypatch, ile_czesci=4))
    bylo = sorted(k for k in baza.dane if "__cz" in k)
    supa.put_key("typy_log", _duzy(monkeypatch, ile_czesci=2))
    jest = sorted(k for k in baza.dane if "__cz" in k)
    assert len(jest) < len(bylo)
    assert supa.get_key_ok("typy_log")[1] is True


def test_bezpiecznik_wagi_dziala_na_sklejonej_calosci(baza, monkeypatch):
    """`put_key_bezpiecznie` porównuje wagi — musi widzieć całość, nie kawałek,
    inaczej każdy szardowany klucz wyglądałby na gwałtownie schudnięty."""
    ksiega = _duzy(monkeypatch)
    supa.put_key("typy_log", ksiega)
    assert supa.put_key_bezpiecznie("typy_log", _ksiega(3)) is False
    assert supa.get_key_ok("typy_log") == (ksiega, True)


def test_payload_nie_do_podzialu_leci_jak_stal(baza, monkeypatch):
    monkeypatch.setattr(supa, "PROG_SZARDU", 5)
    assert supa.put_key("kupony_profil", "zbalansowany") is True
    assert supa.get_key_ok("kupony_profil") == ("zbalansowany", True)


def test_jeden_gruby_element_tez_sie_dzieli(baza, monkeypatch):
    """Kopia księgi to `{"ts": …, "log": {cała księga}}` — podział „po
    wierzchu" dałby kawałek równy oryginałowi i zapis padłby tak samo."""
    kopia = {"ts": 1787112204, "log": _ksiega(400)}
    waga = supa.waga(kopia)
    monkeypatch.setattr(supa, "PROG_SZARDU", waga // 2)
    monkeypatch.setattr(supa, "CEL_CZESCI", waga // 4)
    assert supa.put_key("typy_log_kopia", kopia) is True
    kawalki = [v for k, v in baza.dane.items() if "__cz" in k]
    assert len(kawalki) > 1
    assert all(supa.waga(k) <= supa.PROG_SZARDU for k in kawalki), \
        "żaden kawałek nie może przekroczyć progu — inaczej cały podział jest bez sensu"
    assert supa.get_key_ok("typy_log_kopia") == (kopia, True)


def test_glebokie_scalanie_nie_gubi_stempla(baza, monkeypatch):
    """`ts` siedzi w innym kawałku niż większość księgi — musi przetrwać."""
    kopia = {"ts": 42, "log": _ksiega(400)}
    waga = supa.waga(kopia)
    monkeypatch.setattr(supa, "PROG_SZARDU", waga // 2)
    monkeypatch.setattr(supa, "CEL_CZESCI", waga // 5)
    supa.put_key("typy_log_kopia", kopia)
    odczyt, ok = supa.get_key_ok("typy_log_kopia")
    assert ok and odczyt["ts"] == 42 and len(odczyt["log"]) == 400
