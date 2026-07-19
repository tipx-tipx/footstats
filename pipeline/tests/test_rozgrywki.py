"""Testy profili rozgrywek (fundament trybu ligowego, 2026-07-20)."""

from footstats import rozgrywki


def test_zakres_druzynowy_dokladnie_9_rozgrywek():
    """Top 5 + Ekstraklasa + LM/LE/LK — dokładnie tyle i nic więcej."""
    druzynowe = [p for p in rozgrywki.PROFILE.values() if p.druzynowe]
    assert len(druzynowe) == 9
    nazwy = {p.nazwa for p in druzynowe}
    assert nazwy == {
        "Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1",
        "Ekstraklasa", "Liga Mistrzów", "Liga Europy", "Liga Konferencji",
    }


def test_ms_poza_zakresem_druzynowym():
    """MŚ (utid=16) skończyło się i nie jest w zakresie drużynowym."""
    assert rozgrywki.czy_druzynowe(16) is False
    assert rozgrywki.profil(16) is None


def test_potwierdzone_utidy_z_sondy():
    """utid-y zweryfikowane na żywo 2026-07-20 (event/by-date statshub)."""
    assert rozgrywki.czy_druzynowe(202)      # Ekstraklasa
    assert rozgrywki.czy_druzynowe(7)        # Liga Mistrzów
    assert rozgrywki.czy_druzynowe(679)      # Liga Europy
    assert rozgrywki.czy_druzynowe(17015)    # Liga Konferencji
    for utid in (202, 7, 679, 17015):
        assert rozgrywki.profil(utid).utid_potwierdzony


def test_top5_do_potwierdzenia_po_starcie_sezonu():
    """Top 5 lig nie grało po przerwie — flaga przypomina o sondzie."""
    assert sorted(rozgrywki.utidy_niepotwierdzone()) == [8, 17, 23, 34, 35]


def test_comp365_bez_dubli_i_z_kwalifikacjami():
    ids = rozgrywki.comp365_druzynowe()
    assert len(ids) == len(set(ids))
    # kwalifikacje LM (332) i LE (596) to w 365Scores osobne rozgrywki
    assert 332 in ids and 596 in ids
    # Liga Konferencji zawiera kwalifikacje w jednym id
    assert 7685 in ids


def test_profil_domyslny_dla_egzotyki():
    """Mecz spoza rejestru (np. Copa Libertadores): propsy tak, drużynowe nie."""
    p = rozgrywki.profil_lub_domyslny(9999, nazwa="Copa Libertadores",
                                      kraj="Ameryka Południowa")
    assert p.druzynowe is False
    assert p.nazwa == "Copa Libertadores"
    assert rozgrywki.czy_druzynowe(9999) is False


def test_profil_none_i_domyslny_bez_danych():
    assert rozgrywki.profil(None) is None
    p = rozgrywki.profil_lub_domyslny(None)
    assert p.druzynowe is False and p.nazwa == "Inne rozgrywki"
