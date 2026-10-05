# -*- coding: utf-8 -*-
"""Trzy sprawdzenia Kontroli z audytu 05.10 (pkt 15).

* zwrot „mecz przełożony", a mecz odbył się w terminie bukmachera
  (Sabadell – Andorra 03.10),
* kupon opublikowany i schowany przez konfigurację slotów (regres e04d93c),
* zwrot „nie zagrał", a statshub ma minuty zawodnika w tym meczu.
Rozliczenia nie zmieniamy — tylko stempel i alarm.
"""
from footstats.jobs import rozliczanie as R
from footstats.sources import statshub

TERAZ = 1_800_000_000
GODZ = 3600


def _spr(k, kod):
    return next(s for s in k["sprawdzenia"] if s["kod"] == kod)


def _odwolany(mid=7, ko=TERAZ - 3 * 86400, buk="Superbet"):
    return {"mecz_id": mid, "mecz": "Sabadell – Andorra", "kickoff_ts": ko,
            "wynik": "zwrot", "powod": R.POWOD_MECZ_ODWOLANY,
            "rozliczono_ts": TERAZ - 3600, "bukmacher": buk}


def test_przelozony_rozegrany_w_terminie_zapala_alarm(monkeypatch):
    rec = _odwolany()
    # zagrany 26 h po pierwotnym terminie — przed północą następnego dnia
    monkeypatch.setattr(statshub, "status_i_start",
                        lambda mid: ("finished", rec["kickoff_ts"] + 26 * GODZ - 12 * GODZ))
    log = {"a": rec}
    assert R.weryfikuj_przelozone(log, TERAZ) == 1
    assert rec["spr_przelozony"] == "rozegrany_w_terminie"
    assert rec["wynik"] == "zwrot"                       # rozliczenie nietknięte
    k = R.kontrola_produktu(log, None, TERAZ, TERAZ)
    s = _spr(k, "przelozony_rozegrany")
    assert not s["ok"] and s["liczba"] == 1 and "Sabadell" in s["opis"]
    # stempel = drugi raz nie pytamy
    assert R.weryfikuj_przelozone(log, TERAZ) == 0


def test_przelozony_sprzed_poprawki_bez_alarmu(monkeypatch):
    """Sabadell – Andorra zamknięte 03.10, przed poprawką terminu — znany
    przypadek: stempel jest, alarmu nie ma."""
    teraz = R.PRZELOZONE_ALARM_OD_TS + 86400
    rec = {**_odwolany(ko=teraz - 3 * 86400), "rozliczono_ts": R.PRZELOZONE_ALARM_OD_TS - 60}
    monkeypatch.setattr(statshub, "status_i_start",
                        lambda mid: ("finished", rec["kickoff_ts"] + 14 * GODZ))
    log = {"a": rec}
    R.weryfikuj_przelozone(log, teraz)
    assert rec["spr_przelozony"] == "rozegrany_w_terminie"
    assert _spr(R.kontrola_produktu(log, None, teraz, teraz), "przelozony_rozegrany")["ok"]


def test_przelozony_po_terminie_to_poprawny_zwrot(monkeypatch):
    rec = _odwolany()
    monkeypatch.setattr(statshub, "status_i_start",
                        lambda mid: ("finished", R.termin_przelozonego(rec) + GODZ))
    log = {"a": rec}
    R.weryfikuj_przelozone(log, TERAZ)
    assert rec["spr_przelozony"] == "rozegrany_po_terminie"
    assert _spr(R.kontrola_produktu(log, None, TERAZ, TERAZ), "przelozony_rozegrany")["ok"]


def test_przelozony_dalej_bez_meczu_czeka_na_potwierdzenie(monkeypatch):
    rec = _odwolany(ko=TERAZ - 2 * 86400)
    monkeypatch.setattr(statshub, "status_i_start", lambda mid: ("postponed", None))
    log = {"a": rec}
    R.weryfikuj_przelozone(log, TERAZ)
    assert "spr_przelozony" not in rec                  # mecz może jeszcze się odbyć
    R.weryfikuj_przelozone(log, R.termin_przelozonego(rec) + 4 * 86400)
    assert rec["spr_przelozony"] == "potwierdzony"


def test_przelozone_budzet_zapytan(monkeypatch):
    pytania = []
    monkeypatch.setattr(statshub, "status_i_start",
                        lambda mid: pytania.append(mid) or (None, None))
    log = {str(i): _odwolany(mid=i) for i in range(15)}
    assert R.weryfikuj_przelozone(log, TERAZ, limit=10) == 10 and len(pytania) == 10


def _kupon(przez="konfiguracja", opubl=TERAZ - GODZ, slot="hybryda:3–5"):
    return {"slot": slot, "pominiety": True, "pominiety_przez": przez,
            "opublikowano_ts": opubl}


def test_kupony_schowane_przez_konfiguracje():
    k = R.kontrola_produktu({}, None, TERAZ, TERAZ, {"a": _kupon()})
    s = _spr(k, "kupony_schowane")
    assert not s["ok"] and s["liczba"] == 1 and "hybryda" in s["opis"]
    # pominięty przez usera albo stary kupon — bez alarmu
    ok = {"u": _kupon(przez="user"), "s": _kupon(opubl=TERAZ - 3 * 86400)}
    assert _spr(R.kontrola_produktu({}, None, TERAZ, TERAZ, ok), "kupony_schowane")["ok"]
    assert _spr(R.kontrola_produktu({}, None, TERAZ, TERAZ), "kupony_schowane")["ok"]


def _nie_zagral(pid, mid=9, poza=False):
    return {"podmiot_id": pid, "podmiot": f"P{pid}", "mecz_id": mid, "mecz": "A – B",
            "kickoff_ts": TERAZ - 86400, "wynik": "zwrot", "powod": "nie zagrał",
            "rozliczono_ts": TERAZ - 3600, "poza_publikacja": poza}


def _wiersz(mid, minuty):
    return {"events": {"id": mid}, "player_statistics_event": {"minutesPlayed": minuty}}


def test_nie_zagral_ktory_gral_zapala_alarm(monkeypatch):
    historie = {1: [_wiersz(9, 67)], 2: [_wiersz(8, 90)], 3: []}
    monkeypatch.setattr(statshub, "fetch_player_performance",
                        lambda pid, limit=20: historie[pid])
    log = {"a": _nie_zagral(1), "b": _nie_zagral(2), "c": _nie_zagral(3)}
    assert R.weryfikuj_nie_zagral(log, TERAZ) == 3
    assert log["a"]["spr_nie_zagral"] == "gral"
    assert log["b"]["spr_nie_zagral"] == "potwierdzony"
    # pusta historia dzień po meczu — próbujemy dalej
    assert "spr_nie_zagral" not in log["c"]
    s = _spr(R.kontrola_produktu(log, None, TERAZ, TERAZ), "nie_zagral_probka")
    assert not s["ok"] and s["liczba"] == 1 and "P1" in s["opis"]
    R.weryfikuj_nie_zagral(log, TERAZ + 3 * 86400)
    assert log["c"]["spr_nie_zagral"] == "brak_danych"


def test_nie_zagral_najpierw_typy_ze_strony_i_budzet(monkeypatch):
    pytani = []
    monkeypatch.setattr(statshub, "fetch_player_performance",
                        lambda pid, limit=20: pytani.append(pid) or [_wiersz(1, 0)])
    log = {f"t{i}": _nie_zagral(100 + i, poza=True) for i in range(5)}
    log["strona"] = _nie_zagral(7)
    log["synt"] = _nie_zagral(950_000_001)               # numer syntetyczny 365
    R.weryfikuj_nie_zagral(log, TERAZ, limit=2)
    assert pytani[0] == 7 and len(pytani) == 2
    assert "spr_nie_zagral" not in log["synt"]


def test_kontrola_ma_dziewiec_sprawdzen():
    k = R.kontrola_produktu({}, None, TERAZ, TERAZ)
    assert len(k["sprawdzenia"]) == 9
    for kod in ("przelozony_rozegrany", "kupony_schowane", "nie_zagral_probka"):
        assert _spr(k, kod)["ok"]
