"""Parowanie nazw drużyn statshub ↔ 365Scores (scores365.dopasuj_druzyne).

Przypadki wzięte Z POMIARU 2026-07-27: doganianie banku stylu prosiło o id dla
12 drużyn i dostawało je dla jednej, bo porównywało dokładne klucze.
"""

from footstats.sources import scores365


# fragment żywej mapy z 27.07 (nazwy 365Scores -> competitorId)
MAPA = {
    "sarmiento junin": 7117,
    "tobol kostanay": 5632,
    "levadia tallinn": 5444,
    "flora tallinn": 5443,
    "anderlecht": 1173,
    "bodo glimt": 1978,
    "kf shkendija 79": 8486,
    "kf malisheva": 8487,
    "riestra": 11940,
    "deportivo recoleta": 11941,
    "deportivo cuenca": 11942,
    "caracas fc": 8686,
    "santa fe/caracas fc": 8687,
    "santa coloma": 5585,
    "riga": 29362,
    "rigas fs": 29363,
    "bohemians": 1500,
}


def test_kosmetyka_nazwy_nie_gubi_druzyny():
    """Kropka, ukośnik, skrót typu klubu i rok założenia to nie tożsamość."""
    assert scores365.dopasuj_druzyne(MAPA, "caracas f.c.") == 8686
    assert scores365.dopasuj_druzyne(MAPA, "bodo/glimt") == 1978
    assert scores365.dopasuj_druzyne(MAPA, "kf shkendija") == 8486
    assert scores365.dopasuj_druzyne(MAPA, "fc santa coloma") == 5585
    assert scores365.dopasuj_druzyne(MAPA, "fci levadia tallinn") == 5444
    assert scores365.dopasuj_druzyne(MAPA, "rsc anderlecht") == 1173
    assert scores365.dopasuj_druzyne(MAPA, "sarmiento") == 7117


def test_nie_bierze_sasiada_o_podobnej_nazwie():
    """SEDNO całej funkcji — tu próg podobieństwa tekstu się MYLI.

    Dla „deportivo riestra" najpodobniejsze jest „deportivo recoleta" (0,80),
    dla „riga fc" — „rigas fs" (0,80). Oba to INNE KLUBY. Wpuszczenie ich
    zasiliłoby bank historią cudzej drużyny: cicho i bez śladu w logu.
    """
    assert scores365.dopasuj_druzyne(MAPA, "deportivo riestra") == 11940
    assert scores365.dopasuj_druzyne(MAPA, "riga fc") == 29362


def test_remis_to_brak_dopasowania_a_nie_strzal():
    """Dwóch kandydatów = nie zgadujemy (ta sama reguła co przy zawodnikach)."""
    mapa = {"united": 1, "united fc": 2}   # dwa różne id, identyczne słowa
    assert scores365.dopasuj_druzyne(mapa, "the united") is None
    # „bohemian" vs „bohemians" to różnica odmiany, nie zapisu — odmawiamy
    assert scores365.dopasuj_druzyne(MAPA, "bohemian fc") is None


def test_dwa_zapisy_jednej_druzyny_to_nadal_jednoznacznosc():
    """Mapa bywa zdublowana; dwa klucze na to samo id nie są remisem."""
    mapa = {"bodo glimt": 1978, "fk bodo/glimt": 1978}
    assert scores365.dopasuj_druzyne(mapa, "bodo glimt fk") == 1978


def test_dokladny_klucz_zawsze_wygrywa():
    for nazwa, cid in MAPA.items():
        assert scores365.dopasuj_druzyne(MAPA, nazwa) == cid


def test_pusta_nazwa_i_pusta_mapa():
    assert scores365.dopasuj_druzyne(MAPA, "") is None
    assert scores365.dopasuj_druzyne(MAPA, "fc") is None   # same skróty typu
    assert scores365.dopasuj_druzyne({}, "anderlecht") is None
