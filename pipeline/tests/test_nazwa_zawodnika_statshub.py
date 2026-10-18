"""„Nazwisko, Imię" z feedu player-trends (2026-10-18).

Od ~16.10 statshub podaje tego samego zawodnika w jednym meczu pod dwoma
zapisami („Oosting, Thijs" i „Thijs Oosting"), a klucze typów idą po nazwie
w kolejności słów — jeden człowiek dawał dwa typy na stronie.
"""
from footstats.sources import statshub


def test_odwraca_nazwisko_z_przecinkiem():
    assert statshub.nazwa_zawodnika("Oosting, Thijs") == "Thijs Oosting"
    assert (statshub.nazwa_zawodnika("Dos Santos Pedro, Fernando")
            == "Fernando Dos Santos Pedro")


def test_inne_zapisy_bez_zmian():
    assert statshub.nazwa_zawodnika("Thijs Oosting") == "Thijs Oosting"
    assert statshub.nazwa_zawodnika("Hulk") == "Hulk"
    assert statshub.nazwa_zawodnika("a, b, c") == "a, b, c"
    assert statshub.nazwa_zawodnika(", Thijs") == ", Thijs"
    assert statshub.nazwa_zawodnika(None) == ""


def test_feed_trendow_daje_jedna_nazwe(monkeypatch):
    rekord = {
        "statType": next(iter(statshub.STATTYPE_MAP)),
        "playerId": 876233, "teamId": 1, "homeTeamId": 1, "eventId": 9,
        "line": 0.5, "recentGames": [],
    }
    dane = [dict(rekord, playerName="Oosting, Thijs"),
            dict(rekord, playerName="Thijs Oosting")]
    monkeypatch.setattr(statshub, "_get", lambda url, **kw: {"data": dane})
    tr = statshub.fetch_event_trends([9])
    assert {t.player_name for t in tr} == {"Thijs Oosting"}
