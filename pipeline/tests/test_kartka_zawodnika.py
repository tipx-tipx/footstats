"""Żółta kartka zawodnika: kursy Superbetu + historia ze statshuba.

Rynek gubiony OD ZAWSZE, znaleziony 2026-08-03 przy zgłoszeniu „w wielu
meczach nie ma tabel pokryć ani kursów". Na kwalifikacjach pucharów Superbet
NIE kwotuje strzałów ani fauli — kartka bywa tam JEDYNĄ naszą statystyką
z kursem (66 kwotowanych zawodników na Sparcie Praga – Lyonie, 38 na
Olympiakosie), a czytaliśmy z niej zero.
"""
import pytest

from footstats.sources.superbet import _zawodnik_kartka
from footstats.sources import betclic, statshub


# --- kursy: dwa niezależne rozjazdy nazewnictwa naraz ---

@pytest.mark.parametrize("mname,spec,oczekiwany", [
    # MYŚLNIK w nazwie — tak wygląda żywa oferta (03.08)
    ("zawodnik - otrzyma kartkę", {"player": "Nartey, Noah"}, "Nartey, Noah"),
    # klucz `player`, nie `player_name` jak przy rynkach liczbowych
    ("zawodnik - otrzyma żółtą kartkę", {"player": "Tolisso, Corentin"},
     "Tolisso, Corentin"),
    # stary wariant bez myślnika ma dalej działać
    ("zawodnik otrzyma kartkę", {"player_name": "Kane, Harry"}, "Kane, Harry"),
])
def test_czyta_kartke_zawodnika(mname, spec, oczekiwany):
    assert _zawodnik_kartka(mname, spec) == oczekiwany


@pytest.mark.parametrize("mname,spec,dlaczego", [
    ("zawodnik - otrzyma czerwoną kartkę", {"player": "X"}, "inne zdarzenie"),
    ("zawodnik - otrzyma 1. kartkę", {"player": "X"}, "kto pierwszy w meczu"),
    ("zawodnik - otrzyma kartkę - 1. połowa", {"player": "X"}, "my liczymy 90 min"),
    ("liczba kartek olympiacos", {}, "kartki DRUŻYNY"),
    ("zawodnik - liczba strzałów", {"player_name": "Y"}, "inny rynek"),
])
def test_nie_bierze_cudzych_rynkow(mname, spec, dlaczego):
    assert _zawodnik_kartka(mname, spec) is None, dlaczego


@pytest.mark.parametrize("mname", [
    "el kaabi, ayoub strzeli gola; scipioni, lorenzo otrzyma kartkę",
    "olympiacos powyżej 9.5 fauli; scipioni, lorenzo otrzyma kartkę",
    "retsos otrzyma kartkę; maffeo otrzyma kartkę; sano otrzyma kartkę",
])
def test_kupony_laczone_odpadaja(mname):
    """Kupony BetBuilder mają słowo „kartkę" w nazwie, ale trzymają graczy
    pod `ss_player_*` i nie mają słowa „zawodnik". Wciągnięcie ich zrobiłoby
    z ceny kombinacji cenę pojedynczego zdarzenia."""
    spec = {"ss_player_h_card_pm_0": "Scipioni, Lorenzo", "id": "abc"}
    assert _zawodnik_kartka(mname, spec) is None


# --- historia: brak wpisu znaczy ZERO, nie „nie zmierzono" ---

def _rec(ts, minuty, faule, kartka=None):
    ps = {"minutesPlayed": minuty, "fouls": faule, "teamId": 1, "position": "M"}
    if kartka is not None:
        ps["yellowCard"] = kartka
    return {
        "player_statistics_event": ps,
        "events": {"id": ts, "timeStartTimestamp": ts, "homeTeamId": 1},
        "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"},
    }


def test_mecz_bez_kartki_liczy_sie_jako_zero():
    """Statshub wysyła `yellowCard` TYLKO w meczach z kartką. Pomijanie
    reszty dawało historię z samych meczów z kartką — zmierzone na
    Palavecino: 1 mecz w kartkach wobec 10 w faulach, czyli pokrycie 1/1."""
    rows = [_rec(1_000 + i, 90, 1, kartka=(1 if i == 3 else None))
            for i in range(10)]
    t = statshub.trendy_z_performance(7, "Test", 1, rows)
    yc, fc = t["yellow_card"], t["fouls_committed"]
    assert len(yc.counts) == len(fc.counts) == 10
    assert sum(yc.counts) == 1


def test_lawka_nie_jest_dowodem_na_brak_kartki():
    """Zero dopisujemy tylko temu, kto wyszedł na boisko."""
    rows = [_rec(1_000, 90, 1, kartka=1), _rec(2_000, 0, 0)]
    t = statshub.trendy_z_performance(7, "Test", 1, rows)
    assert len(t["yellow_card"].counts) == 1


# --- drugi bukmacher: ten sam rynek, inna odmiana słowa ---

@pytest.mark.parametrize("nazwa,kod", [
    ("Liczba kartek zawodnika", "yellow_card"),
    ("Liczba kartek zawodnika (OPTA)", "yellow_card"),
    ("Liczba strzałów zawodnika", "shots"),
])
def test_betclic_czyta_kartki(nazwa, kod):
    """Wzorzec był „kartk", a Betclic pisze „kartEk" (dopełniacz liczby
    mnogiej). Jedna litera kasowała cały rynek u drugiego bukmachera —
    i to akurat ten, którego Superbet kwotuje najszerzej."""
    assert betclic.kod_rynku(nazwa) == kod


@pytest.mark.parametrize("nazwa", [
    "Liczba czerwonych kartek zawodnika",   # inne zdarzenie
    "Liczba kartek zawodnika - 1. połowa",  # my liczymy 90 minut
    "Liczba kartek",                        # rynek DRUŻYNOWY
    "Więcej kartek",                        # kto więcej, nie ile
])
def test_betclic_nie_bierze_cudzych_kartek(nazwa):
    assert betclic.kod_rynku(nazwa) is None


def test_pozostale_rynki_nie_dostaja_zer():
    """Brak pola przy statystyce mierzonej zawsze to luka w danych i ma
    zostać luką — inaczej cicho zaniżalibyśmy średnie."""
    rows = [{
        "player_statistics_event": {"minutesPlayed": 90, "teamId": 1},
        "events": {"id": 1, "timeStartTimestamp": 1, "homeTeamId": 1},
        "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"},
    }]
    t = statshub.trendy_z_performance(7, "Test", 1, rows)
    assert "shots" not in t and "tackles" not in t
    # ...ale kartka owszem: zagrał i jej nie dostał
    assert t["yellow_card"].counts == [0.0]
