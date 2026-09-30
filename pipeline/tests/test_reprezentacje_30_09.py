"""Przerwa reprezentacyjna 22–30.09: parowanie, Skuteczność, imienny rentgen.

* Superbet pisze reprezentacje po polsku — „Francja·Włochy" miało
  z „France – Italy" podobieństwo 0,00 (Liga Narodów sparowana 18 z 34),
* Skuteczność wycinała mecze dwóch reprezentacji (epoka „ms"), choć user je
  widział na liście — 25 typów od 24.09,
* imienny rentgen nadpisywał prawdziwą bramę werdyktem „za blisko gwizdka".
"""

import time

import pytest

from footstats.jobs import build_league as bl
from footstats.jobs import radar_imienny
from footstats.jobs import rozliczanie as R
from footstats.sources import betclic, superbet

T0 = 1_790_880_300


def _mecz(eid, home, away, ts=T0, rozgrywki="UEFA Nations League"):
    return bl.MeczLigowy(
        event_id=eid, utid=10783, rozgrywki_nazwa=rozgrywki, kraj="Europe",
        home_id=1, away_id=2, home=home, away=away, kickoff_ts=ts,
        has_odd=True, druzynowe=False,
    )


def _sb(eid, name, ts=T0):
    return {"eventId": eid, "matchName": name, "unixDateMillis": ts * 1000}


@pytest.mark.parametrize("pl,en", [
    ("Włochy", "Italy"), ("Turcja", "Türkiye"), ("Niemcy", "Germany"),
    ("Irlandia Północna", "Northern Ireland"), ("Irlandia", "Ireland"),
    ("Węgry U21", "Hungary U21"), ("Wyspy Owcze", "Faroe Islands"),
    ("Macedonia Północna", "North Macedonia"), ("Czechy", "Czechia"),
    ("Wegry", "Hungary"),                       # bez ogonków też
])
def test_nazwa_reprezentacji_po_angielsku(pl, en):
    assert superbet.nazwa_po_angielsku(pl) == en


@pytest.mark.parametrize("klub", ["Polonia Warszawa", "FC Andorra", "Legia Ladies (K)"])
def test_klub_nie_jest_tlumaczony(klub):
    assert superbet.nazwa_po_angielsku(klub) == klub


def test_liga_narodow_paruje_sie_o_tej_samej_minucie():
    """20:45: pięć meczów naraz, żaden nie miał wspólnego słowa z ofertą."""
    mecze = [_mecz(1, "France", "Italy"), _mecz(2, "Belgium", "Türkiye"),
             _mecz(3, "Poland", "Romania"), _mecz(4, "Hungary", "Georgia"),
             _mecz(5, "Faroe Islands", "Slovakia")]
    sb = [_sb(101, "Francja·Włochy"), _sb(102, "Belgia·Turcja"),
          _sb(103, "Polska·Rumunia"), _sb(104, "Węgry·Gruzja"),
          _sb(105, "Wyspy Owcze·Słowacja")]
    n, luka = bl.paruj_superbet(mecze, sb)
    assert n == 5 and luka == []
    assert [m.sb_event["eventId"] for m in mecze] == [101, 102, 103, 104, 105]


def test_seniorzy_nie_paruja_sie_z_mlodziezowka():
    seniorzy = _mecz(1, "Hungary", "Georgia", ts=T0)
    u21 = _mecz(2, "Hungary U21", "Georgia U21", ts=T0 - 2 * 3600)
    sb = [_sb(101, "Węgry U21·Gruzja U21", ts=T0 - 2 * 3600),
          _sb(102, "Węgry·Gruzja", ts=T0)]
    n, _ = bl.paruj_superbet([seniorzy, u21], sb)
    assert n == 2
    assert seniorzy.sb_event["eventId"] == 102 and u21.sb_event["eventId"] == 101


def test_irlandia_to_nie_irlandia_polnocna():
    assert bl.podobienstwo_klubu("Northern Ireland",
                                 superbet.nazwa_po_angielsku("Irlandia")) == 0.0
    assert bl.podobienstwo_klubu("Northern Ireland",
                                 superbet.nazwa_po_angielsku("Irlandia Północna")) == 1.0


def test_betclic_rozpoznaje_reprezentacje_i_kategorie():
    assert betclic._nazwy_pokrywaja("Italy", betclic._pl_en("Włochy"))
    assert betclic._nazwy_pokrywaja("Hungary U21", betclic._pl_en("Węgry U21"))
    assert not betclic._nazwy_pokrywaja("Hungary", betclic._pl_en("Węgry U21"))


# --- Skuteczność ---

def _typ_reprezentacji(**kw):
    ko = int(time.time()) - 3 * 86400
    r = {"mecz_id": 15534128, "mecz": "Hungary – Ukraine", "kickoff_ts": ko,
         "podmiot_id": 1, "podmiot": "Yehor Nazaryna", "rynek_kod": "shots",
         "rynek": "Strzały", "linia": 0.5, "strona": "powyzej", "kurs": 1.5,
         "p_model": 0.7, "sugestia": False, "wynik": "przegrany",
         "faktyczna": 0.0, "epoka": "ms", "ekran": "wysokie_szanse",
         "opublikowano_ts": ko - 86400}
    r.update(kw)
    return r


def test_skutecznosc_liczy_pokazany_mecz_reprezentacji(monkeypatch):
    monkeypatch.setattr(R, "START_STATYSTYK", "2026-01-01")
    r = _typ_reprezentacji()
    log = {R._klucz(r): r}
    pokazane = {"od_ts": 0, "klucze": {R._klucz(r): r["kickoff_ts"]}}
    s = R.skutecznosc_strumieni(log, lista_dnia={}, pokazane=pokazane)
    typy = [t for d in s["pewniaki"]["dni"] for t in d["typy"]]
    assert [t["podmiot"] for t in typy] == ["Yehor Nazaryna"]


def test_mundial_sprzed_startu_statystyk_dalej_poza_skutecznoscia(monkeypatch):
    monkeypatch.setattr(R, "START_STATYSTYK", "2099-01-01")
    assert not R._do_skutecznosci(_typ_reprezentacji())


def test_uczenie_dalej_bez_reprezentacji():
    """Zmiana dotyczy WYŁĄCZNIE pokazywanych liczb — epoka uczenia bez zmian."""
    assert not R._z_biezacej_epoki(_typ_reprezentacji())


# --- imienny rentgen ---

def test_za_blisko_gwizdka_nie_nadpisuje_bramy(monkeypatch):
    wywolania = []
    monkeypatch.setattr(
        radar_imienny.supa, "upsert_wiersze",
        lambda tabela, wiersze, klucz, tylko_nowe=False:
            wywolania.append(([w["brama"] for w in wiersze], tylko_nowe)) or True)
    monkeypatch.setattr(radar_imienny.supa, "usun_wiersze", lambda *a: True)
    imienny = {
        (1, 10): {"brama": "rzadko_w_pierwszym_skladzie", "kickoff_ts": T0},
        (2, 20): {"brama": "mecz_za_blisko_gwizdka", "kickoff_ts": T0},
    }
    assert radar_imienny.zapisz(imienny, T0)
    assert (["rzadko_w_pierwszym_skladzie"], False) in wywolania
    assert (["mecz_za_blisko_gwizdka"], True) in wywolania
