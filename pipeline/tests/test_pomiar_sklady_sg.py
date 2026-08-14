"""Parowanie w pomiarze składów SportsGamblera.

Cały wynik pomiaru stoi na dwóch funkcjach: czy to ten sam klub i czy to ten
sam zawodnik. Pomyłka w którejkolwiek daje liczbę, która wygląda jak wynik
prognozy, a mówi o dopasowywaniu tekstu — dokładnie ta pułapka przewróciła
pierwsze podejście 13.08.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pomiar_sklady_sg as P


# --- KLUBY -----------------------------------------------------------------

def test_ta_sama_druzyna_lapie_skroty_i_ogonki():
    assert P.ta_sama_druzyna("Athletico PR", "Athletico Paranaense")
    assert P.ta_sama_druzyna("São Paulo", "Sao Paulo")
    assert P.ta_sama_druzyna("Vasco da Gama", "Vasco da Gama")
    assert P.ta_sama_druzyna("Bragantino", "Red Bull Bragantino")


def test_ta_sama_druzyna_nie_myli_klubow_z_tego_samego_miasta():
    """Podobieństwo tekstu wybrałoby tu źle — patrz [[parowanie-nazw-druzyn]]."""
    assert not P.ta_sama_druzyna("Racing Club", "Racing Santander")
    assert not P.ta_sama_druzyna("Atlético Madrid", "Atlético Mineiro")
    assert not P.ta_sama_druzyna("River Plate", "Plate United")
    assert not P.ta_sama_druzyna("Real Sociedad B", "Real Sociedad")


def test_skrot_nie_moze_pasowac_gdziekolwiek_w_slowie():
    """Sam podciąg parował hiszpański mecz z emirackim: „al" z „Al-Nasr Dubai"
    siedzi w „Mallorca" (m-A-L-lorca). Skrót musi zaczynać się tą samą literą."""
    assert not P.ta_sama_druzyna("Mallorca", "Al-Nasr Dubai")
    assert not P.ta_sama_druzyna("A. Bielefeld", "Guingamp")
    assert P.ta_sama_druzyna("A. Bielefeld", "Arminia Bielefeld")
    assert P.ta_sama_druzyna("Athletico PR", "Athletico Paranaense")
    assert not P.ta_sama_druzyna("Atlético MG", "Atlético Madrid")


def test_puste_nazwy_nie_paruja_sie_z_niczym():
    assert not P.ta_sama_druzyna("", "Palmeiras")
    assert not P.ta_sama_druzyna("FC", "SC")      # same sufiksy = pusty zbiór


# --- ZAWODNICY -------------------------------------------------------------

def test_klucz_zawodnika_sprowadza_oba_zrodla_do_wspolnej_postaci():
    assert P.klucz_zawodnika("Thiago Silva") == P.klucz_zawodnika("T. Silva")
    assert P.klucz_zawodnika("Joaquín Piquerez") == P.klucz_zawodnika(
        "J. Piquerez")


def test_bracia_w_jednym_skladzie_nie_sa_tym_samym_zawodnikiem():
    """Zmierzone na Forward Madison FC: „R. Carmichael" i „K. Carmichael"
    stali w jednym XI. Sam człon nazwiska liczyłby jednego dwa razy."""
    assert P.klucz_zawodnika("R. Carmichael") != P.klucz_zawodnika(
        "K. Carmichael")
    assert P.trafienia(["Ryan Carmichael"],
                       ["K. Carmichael", "J. Harms"]) == 0
    assert P.trafienia(["Ryan Carmichael"],
                       ["R. Carmichael", "J. Harms"]) == 1


def test_zawodnik_bez_imienia_paruje_sie_po_samym_nazwisku():
    """Jednoczłonowe nazwy („Fabio", „Hulk") są w Brazylii regułą."""
    assert P.trafienia(["Fabio"], ["Fabio", "T. Silva"]) == 1
    assert P.trafienia(["Hulk"], ["Hulk"]) == 1


def test_trafienia_nie_licza_jednego_zawodnika_dwa_razy():
    assert P.trafienia(["T. Silva", "Thiago Silva"], ["T. Silva"]) == 1


def test_trafienia_licza_tylko_pierwszy_sklad():
    prognoza = ["A. Kowalski", "B. Nowak", "C. Wisniewski"]
    faktyczne = ["A. Kowalski", "D. Zielinski"]
    assert P.trafienia(prognoza, faktyczne) == 1


def test_prog_decyzyjny_jest_ten_z_wlasnej_jedenastki():
    """Gdyby ktoś go ruszył, pomiar zacząłby odpowiadać na inne pytanie."""
    assert P.PROG == 0.686
