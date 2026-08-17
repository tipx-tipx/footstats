"""Mecz, którego nie było — typ zamyka się od razu, nie po tygodniu.

POWÓD (2026-08-17). Celta Vigo – Osasuna: typy powstały 12.08 na mecz z 16.08,
mecz został PRZEŁOŻONY, a w całym kodzie nie było ani jednego miejsca, które
by to rozpoznawało. Typ wisiał klientowi na stronie do gwizdka, którego nie
było, przez siedem dni ciągnął się w „typach czekających na dane", a potem
zamykał się jako „brak danych źródła" — czyli nie do odróżnienia od meczu,
którego statystyk nie umieliśmy pobrać. Zmierzone: 14 typów na dwóch meczach,
5 z nich pokazanych klientowi.
"""

import time

from footstats.jobs import rozliczanie
from footstats.sources import statshub


def _rec(mecz_id=101, wynik=None, godzin_temu=20, **extra):
    rec = {
        "mecz_id": mecz_id,
        "mecz": "Celta Vigo – Osasuna",
        "kickoff_ts": int(time.time()) - godzin_temu * 3600,
        "rynek_kod": "team_goals",
        "podmiot": "Celta Vigo",
        "strona": "powyzej",
        "linia": 1.5,
        "wynik": wynik,
    }
    rec.update(extra)
    return rec


def _statusy(monkeypatch, mapa):
    pytania = []

    def _st(eid):
        pytania.append(int(eid))
        return mapa.get(int(eid))

    monkeypatch.setattr(statshub, "status_meczu", _st)
    return pytania


def test_mecz_przelozony_zamyka_typy_od_razu(monkeypatch):
    log = {"a": _rec(), "b": _rec()}
    _statusy(monkeypatch, {101: "postponed"})
    rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
    for rec in log.values():
        assert rec["wynik"] == "zwrot"
        assert rec["powod"] == rozliczanie.POWOD_MECZ_ODWOLANY
        assert rec["faktyczna"] is None


def test_mecz_odwolany_tez(monkeypatch):
    for status in ("canceled", "cancelled", "abandoned"):
        log = {"a": _rec()}
        _statusy(monkeypatch, {101: status})
        rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
        assert log["a"]["wynik"] == "zwrot", status


def test_mecz_rozegrany_zostaje_do_normalnego_rozliczenia(monkeypatch):
    """Typ ma się rozliczyć wynikiem, a nie zamknąć zwrotem."""
    log = {"a": _rec()}
    _statusy(monkeypatch, {101: "finished"})
    rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
    assert log["a"]["wynik"] is None
    assert log["a"]["status_zrodla_spr"] is True   # ...ale nie pytamy drugi raz


def test_o_ten_sam_mecz_pytamy_raz(monkeypatch):
    log = {"a": _rec(), "b": _rec()}
    pytania = _statusy(monkeypatch, {101: "finished"})
    rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
    rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
    assert pytania == [101]


def test_mecz_opozniony_pytamy_dalej(monkeypatch):
    """`notstarted` po godzinie gwizdka to opóźnienie, nie przełożenie —
    stempla NIE stawiamy, bo status jeszcze się zmieni."""
    log = {"a": _rec()}
    pytania = _statusy(monkeypatch, {101: "notstarted"})
    rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
    rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
    assert log["a"]["wynik"] is None
    assert pytania == [101, 101]


def test_przerwany_mecz_nie_jest_zamykany(monkeypatch):
    """Mecz przerwany bywa dokończony — wtedy statystyki dochodzą normalnie."""
    log = {"a": _rec()}
    _statusy(monkeypatch, {101: "suspended"})
    rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
    assert log["a"]["wynik"] is None


def test_nie_pytamy_przed_koncem_meczu(monkeypatch):
    """Bezpiecznik kosztu: mecz jeszcze trwa, nie ma o co pytać."""
    log = {"a": _rec(godzin_temu=0)}
    pytania = _statusy(monkeypatch, {101: "postponed"})
    rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
    assert pytania == []
    assert log["a"]["wynik"] is None


def test_rozliczony_typ_nie_jest_ruszany(monkeypatch):
    log = {"a": _rec(wynik="wygrany")}
    pytania = _statusy(monkeypatch, {101: "postponed"})
    rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
    assert pytania == []
    assert log["a"]["wynik"] == "wygrany"


def test_limit_pytan_na_przebieg(monkeypatch):
    """Bez limitu jeden zaległy dzień potrafiłby dołożyć setki zapytań."""
    log = {str(i): _rec(mecz_id=200 + i) for i in range(60)}
    pytania = _statusy(monkeypatch, {200 + i: "finished" for i in range(60)})
    rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
    assert len(pytania) == rozliczanie.LIMIT_PYTAN_O_STATUS


def test_zrodlo_nie_odpowiada_nic_nie_zamyka(monkeypatch):
    """Brak odpowiedzi to NIE jest dowód, że meczu nie było."""
    log = {"a": _rec()}
    _statusy(monkeypatch, {})     # status_meczu -> None
    rozliczanie._zamknij_odwolane_mecze(log, int(time.time()))
    assert log["a"]["wynik"] is None
    assert not log["a"].get("status_zrodla_spr")
