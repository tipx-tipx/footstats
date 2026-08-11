"""Testy profili rozgrywek (fundament trybu ligowego, 2026-07-20)."""

from footstats import rozgrywki


def test_zakres_druzynowy_dokladnie_19_rozgrywek():
    """Europa (top 5 + Ekstraklasa + puchary) + Ameryka Płd. + Skandynawia.

    Rozszerzone 2026-07-27: rynki drużynowe to jedyny dochodowy produkt, więc
    zakres poszedł tam, gdzie sonda statshub pokazała komplet danych. Lista
    jest zamknięta celowo — każda dołożona rozgrywka kosztuje czas cyklu
    (bank stylu + terminarze 365Scores), więc nie rośnie sama z siebie.

    Rozszerzone 2026-08-11 o Leagues Cup i Libertadores. Powód pomiarowy:
    67 ze 160 nadchodzących meczów było POZA rejestrem, czyli nie liczyliśmy
    dla nich ani jednego rynku drużynowego — przy celu „różne typy na jak
    największej liczbie meczów" to była największa pojedyncza blokada podaży.
    Obie dołożone rozgrywki mają POTWIERDZONE `comp365` (patrz test niżej);
    South African Premier Division czeka na identyfikator.
    """
    druzynowe = [p for p in rozgrywki.PROFILE.values() if p.druzynowe]
    assert len(druzynowe) == 19
    nazwy = {p.nazwa for p in druzynowe}
    assert nazwy == {
        # Europa (zakres pierwotny 2026-07-20)
        "Premier League", "LaLiga", "Serie A", "Bundesliga", "Ligue 1",
        "Ekstraklasa", "Liga Mistrzów", "Liga Europy", "Liga Konferencji",
        # Ameryka Płd. — grają cały rok
        "Liga Profesional", "Brasileirão Série A", "Brasileirão Série B",
        "CONMEBOL Sudamericana",
        # Skandynawia — sezon letni, luka przed startem top 5
        "Allsvenskan", "Superettan", "Eliteserien", "Superliga",
        # dołożone 2026-08-11 pod podaż typów
        "Leagues Cup", "CONMEBOL Libertadores",
    }


def test_nowe_ligi_maja_obie_polowki_pary_id():
    """utid BEZ comp365 = rynki drużynowe, które nigdy się nie rozliczą.

    Rozliczanie szuka wyniku meczu po `comp365` (games/results per rozgrywki).
    Brak tego id nie daje błędu — typ po prostu wisi i po 48h zamyka się jako
    zwrot. Pary poniżej zweryfikowane 2026-07-27 porównaniem nazw drużyn
    między statshub (utid) a 365Scores (comp365).
    """
    PARY = {155: 72, 325: 113, 390: 116, 480: 389,
            40: 122, 46: 123, 20: 131, 39: 119,
            # 2026-08-11: id z wyszukiwarki 365 (`/search/?query=`),
            # sprawdzone na realnych meczach — Leagues Cup 18 gier
            # w fixtures i results, Libertadores 15 i 33
            13783: 7242, 384: 102}
    for utid, comp in PARY.items():
        p = rozgrywki.profil(utid)
        assert p is not None and p.druzynowe, f"utid {utid} poza zakresem"
        assert p.comp365 == (comp,), f"utid {utid}: comp365 {p.comp365}"
    # każda rozgrywka w zakresie MUSI mieć comp365 — inaczej cicha strata
    for p in rozgrywki.PROFILE.values():
        if p.druzynowe:
            assert p.comp365, f"{p.nazwa} bez comp365"


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
