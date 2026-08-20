# -*- coding: utf-8 -*-
"""ODCIĘCIE ZA NADMIAR ZAPYTAŃ (429/403) TO NIE „chwilowo wolny".

⚑ PO CO OSOBNY PLIK (2026-08-20). `statshub._get` traktował 429 tą samą
ścieżką co timeout i 5xx: pauza 3 s, potem 6 s, potem poddaje się — a wtedy
`build_wc_fast._main_impl` łapie wyjątek i POMIJA CAŁY CYKL. Jedno odcięcie
kosztuje komplet typów, drabinek i kuponów na godzinę.

Źródło odblokowuje się po minutach, więc trzysekundowa pauza gwarantowała
porażkę wszystkich trzech prób. Zmierzone tego dnia po serii dry-runów:
429 i cykl pusty w 0,8 min.

To zabezpieczenie jest WARUNKIEM podniesienia budżetów odkrywania
(`MAX_WYSZUKAN_ODKRYC` 700 → 1400 tego samego dnia): większy budżet to
większa szansa na odcięcie, więc najpierw musi istnieć droga wyjścia.
"""
import pytest

from footstats import diagnostyka
from footstats.sources import statshub


class _Odpowiedz:
    def __init__(self, status: int):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP Error {self.status_code}: ")

    def json(self):
        return {"ok": True}


@pytest.fixture
def czysta_diagnostyka():
    diagnostyka._licznik.clear()
    diagnostyka._pierwszy.clear()
    yield
    diagnostyka._licznik.clear()
    diagnostyka._pierwszy.clear()


def test_odciecie_jest_liczone(monkeypatch, czysta_diagnostyka):
    """Bez licznika odcięcie widać dopiero po tym, jak strona pół dnia
    pokazuje stare dane."""
    monkeypatch.setattr(statshub.requests, "get",
                        lambda *a, **k: _Odpowiedz(429))
    with pytest.raises(Exception):
        statshub._get("https://example.test/x")
    assert diagnostyka.raport().get("statshub:odciecie_429"), (
        "429 nie trafiło do diagnostyki — cykl przepadnie bez śladu w raporcie"
    )


def test_odciecie_ma_wlasny_dluzszy_backoff(monkeypatch, czysta_diagnostyka):
    """Pauza odcięcia musi być WYRAŹNIE dłuższa niż zwykłe ponowienie —
    inaczej trzy próby mieszczą się w kilku sekundach i wszystkie padają."""
    spane: list[float] = []
    monkeypatch.setattr(statshub.requests, "get",
                        lambda *a, **k: _Odpowiedz(429))
    monkeypatch.setattr(statshub, "PAUZA_ODCIECIA_S", 7)
    import time as _t
    monkeypatch.setattr(_t, "sleep", lambda s: spane.append(s))
    with pytest.raises(Exception):
        statshub._get("https://example.test/x")
    assert spane == [7, 14, 21], (
        f"backoff odcięcia nie rośnie z próbą: {spane}"
    )


def test_zwykly_blad_nie_udaje_odciecia(monkeypatch, czysta_diagnostyka):
    """Timeout i 5xx zostają na krótkiej ścieżce — inaczej każdy chwilowy
    błąd źródła kosztowałby cykl półtorej minuty czekania."""
    monkeypatch.setattr(statshub.requests, "get",
                        lambda *a, **k: _Odpowiedz(503))
    with pytest.raises(Exception):
        statshub._get("https://example.test/x")
    assert "statshub:odciecie_429" not in diagnostyka.raport()


def test_pauza_odciecia_jest_realnie_dluga():
    """⚑ Wartość czytamy ZE ŹRÓDŁA, nie z modułu: `conftest` zeruje pauzy,
    żeby zestaw nie czekał minut — więc `statshub.PAUZA_ODCIECIA_S` widziane
    z testu to zawsze 0 i asercja na nim niczego nie pilnuje.
    """
    import re
    from pathlib import Path
    zrodlo = (Path(__file__).resolve().parent.parent / "footstats"
              / "sources" / "statshub.py").read_text(encoding="utf-8")
    m = re.search(r"^PAUZA_ODCIECIA_S = (\d+)", zrodlo, re.M)
    assert m, "stała PAUZA_ODCIECIA_S zniknęła ze źródła"
    assert int(m.group(1)) >= 15, (
        "pauza odcięcia zbliżyła się do zwykłego ponowienia — trzy próby "
        "zmieszczą się w kilku sekundach i wszystkie padną, a wtedy cykl "
        "przepada w całości"
    )
