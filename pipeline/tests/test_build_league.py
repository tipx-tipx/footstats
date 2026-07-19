"""Testy parownika statshub↔Superbet dla klubów (build_league, etap 1).

Pary nazw wzięte z ŻYWEGO raportu pokrycia 2026-07-20 — to realne rozjazdy
nazewnictwa między źródłami, nie wymyślone przykłady.
"""

import pytest

from footstats.jobs import build_league as bl


# --- normalizacja nazw klubów ---

def test_norm_klub_zrzuca_ozdobniki_i_diakrytyki():
    assert bl.norm_klub("IFK Göteborg") == bl.norm_klub("Goteborg IFK")
    assert bl.norm_klub("FC København") == "kobenhavn"


def test_norm_klub_nazwa_z_samych_ozdobnikow_zostaje():
    """AIK: wszystkie tokeny to 'śmieci' — nazwa nie może wyjść pusta."""
    assert bl.norm_klub("AIK") == "aik"


# --- podobieństwo (żywe pary z raportu 2026-07-20) ---

@pytest.mark.parametrize("statshub_nazwa,superbet_nazwa", [
    ("Atlético Mineiro", "Atletico MG"),          # alias
    ("América Mineiro", "America MG"),            # alias
    ("Djurgårdens IF", "Djurgarden IF"),          # prefiks (odmiana -s)
    ("FCI Levadia Tallinn", "Levadia Tallinn"),   # nadzbiór tokenów
    ("Örgryte IS", "Orgryte"),                    # diakrytyki + ozdobnik
    ("AGF Aarhus", "AGF Aarhus"),                 # wprost
])
def test_podobienstwo_zywe_pary_pasuja(statshub_nazwa, superbet_nazwa):
    assert bl.podobienstwo_klubu(statshub_nazwa, superbet_nazwa) >= 0.99


def test_podobienstwo_rozne_kluby_nie_pasuja():
    assert bl.podobienstwo_klubu("Real Madryt", "Betis") == 0.0
    # wspólne "Atletico" nie skleja różnych klubów powyżej progu pary
    assert bl.podobienstwo_klubu("Atlético Madrid", "Atletico Mineiro") \
        < bl.PROG_PODOBIENSTWA
    # krótkie skróty nie łapią się prefiksem ('mg' vs 'mineiro' — od tego aliasy)
    assert not bl._tokeny_pasuja("mg", "mineiro")


# --- kickoff Superbetu ---

def test_sb_kickoff_bierze_unixdatemillis_nie_matchtimestamp():
    """matchTimestamp = czas aktualizacji oferty (pułapka zmierzona
    2026-07-20), kickoff siedzi w unixDateMillis."""
    ev = {"unixDateMillis": 1784673000000, "matchTimestamp": 1784504936670}
    assert bl._sb_kickoff(ev) == 1784673000


# --- parowanie ---

def _mecz(eid, home, away, ts):
    return bl.MeczLigowy(
        event_id=eid, utid=390, rozgrywki_nazwa="Brasileirão Série B",
        kraj="Brazylia", home_id=1, away_id=2, home=home, away=away,
        kickoff_ts=ts, has_odd=True, druzynowe=False,
    )


def _sb(eid, name, ts):
    return {"eventId": eid, "matchName": name, "unixDateMillis": ts * 1000}


def test_paruj_bramkuje_czasem():
    """Te same drużyny grają w lidze wielokrotnie — okno ±3 h musi wybrać
    właściwy termin, a mecz poza oknem zostawić bez pary."""
    m = _mecz(1, "Avaí", "América Mineiro", 1_784_673_000)
    dobry = _sb(101, "Avai·America MG", 1_784_673_000)
    inny_termin = _sb(102, "Avai·America MG", 1_784_673_000 + 14 * 86400)
    n, luka = bl.paruj_superbet([m], [inny_termin, dobry])
    assert n == 1
    assert m.sb_event["eventId"] == 101
    assert luka == [inny_termin]


def test_paruj_kazdy_event_najwyzej_raz():
    m1 = _mecz(1, "Avaí", "América Mineiro", 1_784_673_000)
    m2 = _mecz(2, "Avaí", "América Mineiro", 1_784_673_000)
    sb = [_sb(101, "Avai·America MG", 1_784_673_000)]
    n, _ = bl.paruj_superbet([m1, m2], sb)
    assert n == 1
    assert (m1.sb_event is None) != (m2.sb_event is None)


def test_paruj_odrzuca_slabe_podobienstwo():
    m = _mecz(1, "Nacional Potosí", "Real Oruro", 1_784_673_000)
    sb = [_sb(101, "Nacional Montevideo·CA Tigre", 1_784_673_000)]
    n, luka = bl.paruj_superbet([m], sb)
    assert n == 0 and m.sb_event is None and len(luka) == 1
