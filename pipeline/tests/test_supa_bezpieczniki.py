"""Bezpieczniki zapisu do Supabase.

`get_key` zwracał None i przy pustym kluczu, i przy padniętym zapytaniu. Kod,
który czyta rejestr, dopisuje do niego i zapisuje z powrotem (typy_log,
kupony_log, bank trendów), nadpisałby wtedy całą historię garstką świeżych
wpisów — jeden nieudany request HTTP kasował dataset kalibracji.
"""
import pytest

from footstats import supa
from footstats.jobs import rozliczanie


class _Odp:
    def __init__(self, status: int, dane):
        self.status_code = status
        self._dane = dane

    def json(self):
        return self._dane


def _stub_get(monkeypatch, odp):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setattr(supa.requests, "get", lambda *a, **kw: odp)


def test_pusty_klucz_to_nie_awaria(monkeypatch):
    _stub_get(monkeypatch, _Odp(200, []))
    assert supa.get_key_ok("typy_log") == (None, True)


def test_padniety_odczyt_jest_odrozniany_od_pustki(monkeypatch):
    _stub_get(monkeypatch, _Odp(503, []))
    assert supa.get_key_ok("typy_log") == (None, False)

    def _wybuch(*a, **kw):
        raise RuntimeError("timeout")

    monkeypatch.setattr(supa.requests, "get", _wybuch)
    assert supa.get_key_ok("typy_log") == (None, False)


def test_brak_env_to_tryb_lokalny_a_nie_awaria(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert supa.get_key_ok("typy_log") == (None, True)


def _ksiega(n: int) -> dict:
    """Payload w skali prawdziwej księgi (setki wpisów, ~100 B każdy)."""
    return {str(i): {"mecz": "A – B", "kurs": 1.5, "p_model": 0.7,
                     "podmiot": f"Zawodnik {i}"} for i in range(n)}


def test_zapis_wstrzymany_gdy_payload_gwaltownie_maleje(monkeypatch):
    zapisane: dict = {}
    monkeypatch.setattr(supa, "get_key_ok", lambda k: (_ksiega(600), True))
    monkeypatch.setattr(supa, "put_key",
                        lambda k, v: zapisane.__setitem__(k, v) or True)
    assert supa.put_key_bezpiecznie("typy_log", _ksiega(2)) is False
    assert zapisane == {}
    # normalne przycinanie (600 -> 580) przechodzi bez przeszkód
    duza = _ksiega(580)
    assert supa.put_key_bezpiecznie("typy_log", duza) is True
    assert zapisane["typy_log"] == duza


def test_bezpiecznik_widzi_utrate_w_ZAGNIEZDZONYM_payloadzie(monkeypatch):
    """Bank stylu ma cztery klucze najwyższego poziomu i 3 MB w środku —
    licznik kluczy przepuściłby utratę wszystkich meczów bez mrugnięcia."""
    zapisane: dict = {}
    stary = {"gry": _ksiega(600), "shotmapy": {}, "wzrost": {}, "sytuacje": {}}
    nowy = {"gry": _ksiega(3), "shotmapy": {}, "wzrost": {}, "sytuacje": {}}
    assert len(stary) == len(nowy) == 4
    monkeypatch.setattr(supa, "get_key_ok", lambda k: (stary, True))
    monkeypatch.setattr(supa, "put_key",
                        lambda k, v: zapisane.__setitem__(k, v) or True)
    assert supa.put_key_bezpiecznie("styl_bank_liga", nowy) is False
    assert zapisane == {}


def test_znana_waga_oszczedza_kontrolny_odczyt(monkeypatch):
    """Bank trendów to 8,6 MB i 2,3 s na odczyt — wołający, który zna rozmiar
    sprzed zmian, nie musi ciągnąć go drugi raz w tym samym cyklu."""
    odczyty: list = []
    zapisane: dict = {}
    monkeypatch.setattr(supa, "get_key_ok",
                        lambda k: (odczyty.append(k), (None, True))[1])
    monkeypatch.setattr(supa, "put_key",
                        lambda k, v: zapisane.__setitem__(k, v) or True)
    duza = _ksiega(600)
    assert supa.put_key_bezpiecznie(
        "trend_lib", duza, waga_poprzednia=supa.waga(duza)) is True
    assert odczyty == []
    # ale bezpiecznik dalej działa: skurcz wobec ZNANEJ wagi blokuje zapis
    assert supa.put_key_bezpiecznie(
        "trend_lib", _ksiega(2), waga_poprzednia=supa.waga(duza)) is False


def test_zapis_wstrzymany_gdy_nie_da_sie_odczytac_stanu(monkeypatch):
    zapisane: dict = {}
    monkeypatch.setattr(supa, "get_key_ok", lambda k: (None, False))
    monkeypatch.setattr(supa, "put_key",
                        lambda k, v: zapisane.__setitem__(k, v) or True)
    assert supa.put_key_bezpiecznie("trend_lib", {"a": 1}) is False
    assert zapisane == {}


def test_maly_zbior_moze_zniknac_bez_alarmu(monkeypatch):
    # próg wagi chroni HISTORIE, nie rejestry wygasające po gwizdku
    zapisane: dict = {}
    monkeypatch.setattr(supa, "get_key_ok", lambda k: ({"a": 1, "b": 2}, True))
    monkeypatch.setattr(supa, "put_key",
                        lambda k, v: zapisane.__setitem__(k, v) or True)
    assert supa.put_key_bezpiecznie("publikacje_typy", {}) is True


def test_rozliczanie_nie_rusza_ksiegi_gdy_odczyt_padl(monkeypatch):
    zapisy: list = []
    monkeypatch.setattr(rozliczanie.supa, "get_key_ok", lambda k: (None, False))
    monkeypatch.setattr(rozliczanie.supa, "put_key",
                        lambda k, v: zapisy.append(k) or True)
    monkeypatch.setattr(rozliczanie.supa, "put_key_bezpiecznie",
                        lambda k, v, **kw: zapisy.append(k) or True)
    with pytest.raises(RuntimeError, match="typy_log"):
        rozliczanie.rozlicz([], [], set())
    assert zapisy == []      # ani jednego zapisu przy nieczytelnej księdze
