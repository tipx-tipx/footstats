"""Wynik do nauki (30.09): uczenie widzi poprawne rozstrzygnięcie,
Skuteczność — zamrożony wynik."""

import time

from footstats.jobs import rozliczanie as R
from footstats.jobs.wyniki_nauki import wynik_nauki


def _wiersz(mecz_id, minuty, **st):
    return {"events": [{"id": mecz_id}],
            "player_statistics_event": [{"eventId": mecz_id, "minutesPlayed": minuty, **st}]}


def _rec(**kw):
    r = {"mecz_id": 1, "mecz": "A – B", "kickoff_ts": int(time.time()) - 3 * 86400,
         "podmiot_id": 7, "podmiot": "Jan", "rynek_kod": "fouls_committed",
         "rynek": "Faule", "linia": 0.5, "strona": "powyzej", "kurs": 1.5,
         "p_model": 0.6, "wynik": "przegrany", "faktyczna": 0.0,
         "bukmacher": "Superbet", "sugestia": False}
    r.update(kw)
    return r


def test_superbet_zmiennik_do_nauki_to_zwrot():
    assert wynik_nauki(_rec(), [_wiersz(1, 20, fouls=0, substitutedOut=99)]) == ("zwrot", None)


def test_betclic_zmiennik_zostaje():
    assert wynik_nauki(_rec(bukmacher="Betclic"),
                       [_wiersz(1, 20, fouls=0, substitutedOut=99)]) is None


def test_falszywy_nie_zagral_dostaje_wynik():
    r = _rec(wynik="zwrot", powod="nie zagrał", faktyczna=0.0)
    assert wynik_nauki(r, [_wiersz(1, 90, fouls=2)]) == ("wygrany", 2.0)


def test_nie_ruszamy_roznic_wartosci_ani_brakujacych_meczow():
    assert wynik_nauki(_rec(), [_wiersz(1, 90, fouls=3)]) is None      # 365 vs statshub
    assert wynik_nauki(_rec(), [_wiersz(2, 90, fouls=3)]) is None      # puchar bez wiersza
    assert wynik_nauki(_rec(wynik="zwrot", powod="mecz przełożony lub odwołany"),
                       [_wiersz(1, 90, fouls=3)]) is None
    assert wynik_nauki(_rec(superzmiana=True), [_wiersz(1, 20, substitutedOut=9)]) is None


def test_widok_nauki_podmienia_tylko_dla_uczenia():
    r = _rec(wynik_nauka="zwrot")
    log = {"k": r}
    w = R.widok_nauki(log)
    assert w["k"]["wynik"] == "zwrot"
    assert log["k"]["wynik"] == "przegrany"          # zamrożony rekord nietknięty
    assert R.widok_nauki(w)["k"]["wynik"] == "zwrot"   # idempotentne
    assert R.widok_nauki(None) is None


def test_skutecznosc_pokazuje_zamrozony_wynik(monkeypatch):
    monkeypatch.setattr(R, "START_STATYSTYK", "2026-01-01")
    r = _rec(wynik_nauka="zwrot", ekran="wysokie_szanse", epoka="liga",
             opublikowano_ts=1)
    log = {R._klucz(r): r}
    pokazane = {"od_ts": 0, "klucze": {R._klucz(r): r["kickoff_ts"]}}
    s = R.skutecznosc_strumieni(log, lista_dnia={}, pokazane=pokazane)
    typy = [t for d in s["pewniaki"]["dni"] for t in d["typy"]]
    assert [t["wynik"] for t in typy] == ["przegrany"]


def test_korekta_strumienia_uczy_sie_z_wyniku_nauki():
    """Te same rekordy: przegrane jako zwroty do nauki znikają z próby."""
    rek = {f"k{i}": _rec(mecz_id=i, kickoff_ts=int(time.time()) - 86400 - i,
                         ekran="wysokie_szanse", epoka="liga", pewniak=True,
                         wynik="przegrany", wynik_nauka="zwrot")
           for i in range(200)}
    assert R.proby_strumieni(rek) != R.proby_strumieni(
        {k: {kk: vv for kk, vv in v.items() if kk != "wynik_nauka"} for k, v in rek.items()})


def test_zapis_nanosi_tylko_na_niezmieniony_rekord(monkeypatch):
    """Między liczeniem a zapisem cykl mógł rozliczyć/zmienić rekord —
    poprawkę nanosimy wyłącznie tam, gdzie wynik jest nadal ten sam."""
    from footstats.jobs import wyniki_nauki as W
    stara = {"a": _rec(), "b": _rec(mecz_id=2)}
    swieza = {"a": _rec(), "b": _rec(mecz_id=2, wynik="wygrany"), "c": _rec(mecz_id=3)}
    odczyty = [stara, swieza]
    zapisane = {}
    monkeypatch.setattr(W.supa, "get_key_ok", lambda k: (odczyty.pop(0), True))
    monkeypatch.setattr(W.supa, "put_key_bezpiecznie",
                        lambda k, v: zapisane.update(v) or True)
    monkeypatch.setattr(W, "_historia", lambda pid, c, p: [
        _wiersz(1, 20, fouls=0, substitutedOut=9), _wiersz(2, 20, fouls=0, substitutedOut=9)])
    assert W.main(zapisz=True) == 0
    assert zapisane["a"]["wynik_nauka"] == "zwrot"
    assert "wynik_nauka" not in zapisane["b"]            # zmieniony w międzyczasie
    assert "c" in zapisane                               # nowy rekord cyklu zachowany
