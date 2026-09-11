# -*- coding: utf-8 -*-
"""OD KIEDY LICZYMY TO, CO POKAZUJEMY.

Zgłoszenie właściciela 11.09: „w rozliczeniach mają się pokazywać tylko typy,
które były pokazywane na stronie; typy w tle mają być w tle".

Filtr zamrożonej listy dnia to zapewnia — ale wyłącznie dla dni z zapisanym
składem, a manifesty starszych dób zostały skasowane, gdy retencja stała na
czterech dniach. Dla tamtych dni „co było na stronie" jest bezpowrotnie nie do
ustalenia, więc bilans liczył się z księgi, czyli z tłem: doba 20.08 miała
w Skuteczności 165 typów przy limicie 21 na dobę.

Stąd data startu. Te testy pilnują trzech rzeczy, na których stoi jej sens:
  1. pokazywane liczby liczą się WYŁĄCZNIE od niej,
  2. uczenie jej NIE widzi (warstwy potrzebują próby, nie „tego, co user
     widział"),
  3. typy sprzed startu mają swoją liczbę — żadnego cichego odrzucenia.
"""

from __future__ import annotations

import datetime as dt

import pytest

from footstats.jobs import rozliczanie as R

pytestmark = pytest.mark.data_startu

START = "2026-09-11"


def _ts(dzien: str, godzina: int = 20) -> int:
    d = dt.datetime.strptime(dzien, "%Y-%m-%d").replace(hour=godzina)
    if R.STREFA is not None:
        d = d.replace(tzinfo=R.STREFA)
    return int(d.timestamp())


def _rec(dzien: str, podmiot="Flamengo", wynik="wygrany", kurs=2.0):
    return {
        "mecz_id": 1, "mecz": "Flamengo – Cruzeiro", "podmiot": podmiot,
        "podmiot_id": 101, "rynek_kod": "team_corners",
        "rynek": "Rzuty rożne drużyny", "linia": 4.5, "strona": "powyzej",
        "kickoff_ts": _ts(dzien), "kurs": kurs, "p_model": 0.6,
        "sugestia": False, "wynik": wynik, "opublikowano_ts": 1,
        "epoka": R.EPOKA_BIEZACA, "ekran": "druzyny",
        "rozliczono_ts": _ts(dzien, 22),
    }


def _payload(monkeypatch, log):
    store = {"typy_log": log, "lista_dnia": {}}
    monkeypatch.setattr(R.supa, "get_key", lambda k: store.get(k))
    monkeypatch.setattr(R.supa, "get_key_ok", lambda k: (store.get(k), True))
    monkeypatch.setattr(R.supa, "put_key",
                        lambda k, v: store.__setitem__(k, v) or True)
    monkeypatch.setattr(R.supa, "put_key_bezpiecznie",
                        lambda k, v, **kw: store.__setitem__(k, v) or True)
    monkeypatch.setattr(R, "_snapshot_zamkniecia", lambda *a, **k: None)
    return R.rozlicz([], [])


# --- 1. sama reguła --------------------------------------------------------

def test_dzien_przed_startem_wypada_z_pokazywanych(monkeypatch):
    monkeypatch.setattr(R, "START_STATYSTYK", START)
    assert R.w_oknie_statystyk(_rec("2026-09-11")) is True
    assert R.w_oknie_statystyk(_rec("2026-09-12")) is True
    assert R.w_oknie_statystyk(_rec("2026-08-20")) is False


def test_wylaczona_data_liczy_wszystko(monkeypatch):
    """None = zachowanie sprzed 11.09. Cofnięcie decyzji to jedna linia."""
    monkeypatch.setattr(R, "START_STATYSTYK", None)
    assert R.w_oknie_statystyk(_rec("2026-08-20")) is True


def test_rekord_bez_kickoffu_nie_wchodzi(monkeypatch):
    """Typ bez godziny meczu nie da się przypisać do doby — nie zgadujemy."""
    monkeypatch.setattr(R, "START_STATYSTYK", START)
    assert R.w_oknie_statystyk({**_rec("2026-09-12"), "kickoff_ts": None}) is False


# --- 2. cały payload Skuteczności -----------------------------------------

def test_werdykt_liczy_tylko_dni_od_startu(monkeypatch):
    monkeypatch.setattr(R, "START_STATYSTYK", START)
    log = {}
    for dzien, podmiot in (("2026-08-20", "Cruzeiro"), ("2026-08-23", "Santos"),
                           ("2026-09-11", "Flamengo")):
        r = _rec(dzien, podmiot=podmiot)
        log[R._klucz(r)] = r
    out = _payload(monkeypatch, log)

    pods = out["podsumowanie"]
    assert pods["rozliczone"] == 1, "do werdyktu wchodzi tylko doba od startu"
    assert pods["start_statystyk"] == START
    assert pods["przed_startem_n"] == 2, "reszta MUSI mieć swoją liczbę"
    dni = [d["dzien"] for d in out["skutecznosc_dzienna"]]
    assert dni == [START], dni


def test_strumienie_licza_to_samo_co_werdykt(monkeypatch):
    monkeypatch.setattr(R, "START_STATYSTYK", START)
    log = {}
    for dzien, podmiot in (("2026-08-20", "Cruzeiro"), ("2026-09-11", "Flamengo")):
        r = _rec(dzien, podmiot=podmiot)
        log[R._klucz(r)] = r
    out = _payload(monkeypatch, log)
    zbiorczo = out["podsumowanie"]["rozliczone"]
    strumienie = sum(s["podsumowanie"]["rozliczone"]
                     for s in out["skutecznosc_strumienie"].values())
    assert zbiorczo == strumienie == 1


def test_bez_daty_startu_werdykt_widzi_cala_ksiege(monkeypatch):
    monkeypatch.setattr(R, "START_STATYSTYK", None)
    log = {}
    for dzien, podmiot in (("2026-08-20", "Cruzeiro"), ("2026-09-11", "Flamengo")):
        r = _rec(dzien, podmiot=podmiot)
        log[R._klucz(r)] = r
    out = _payload(monkeypatch, log)
    assert out["podsumowanie"]["rozliczone"] == 2
    assert out["podsumowanie"]["przed_startem_n"] == 0


# --- 3. UCZENIE NIE WIDZI DATY STARTU — to jest tu najważniejsze ----------

def test_warstwy_uczenia_czytaja_cala_ksiege(monkeypatch):
    """⚑ Reset widoku NIE JEST resetem pamięci modelu.

    Korekta strony uczy się na 300 rozliczeniach pary (rynek, strona),
    korekta strumienia na 120. Gdyby data startu obowiązywała też je,
    włączenie jej uciszyłoby wszystkie warstwy na tygodnie — i wyglądałoby
    to jak „model przestał się uczyć", bez żadnego śladu w kodzie.
    """
    monkeypatch.setattr(R, "START_STATYSTYK", START)
    log = {}
    for i in range(60):
        r = _rec("2026-08-20", podmiot=f"Klub {i}",
                 wynik="wygrany" if i % 2 else "przegrany")
        r["mecz_id"] = 1000 + i
        r["podmiot_id"] = 1000 + i
        log[R._klucz(r)] = r

    # warstwa liczy z księgi, nie z okna pokazywanego
    korekta = R.korekta_strumienia(log)
    assert korekta, "warstwa nie może stracić próby przez datę startu widoku"

    out = _payload(monkeypatch, log)
    assert out["podsumowanie"]["rozliczone"] == 0, "widok jest pusty..."
    assert out["podsumowanie"]["przed_startem_n"] == 60, "...a księga pełna"
