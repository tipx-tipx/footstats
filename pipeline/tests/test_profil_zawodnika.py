"""Który warunek uciął typ zawodniczy — powód, nie zbiorcza etykieta.

POWÓD (2026-08-03). Strumień zawodniczy stoi: 3185 odrzuceń w cyklu, zero
żywych typów. Lejek pokazał, że 138 zawodników MIAŁO kurs i wszystkie zginęły
na ostatniej bramie — a ta miała jeden komunikat na trzy różne warunki
(„kwotowane linie nie łączą sensownego kursu z szansą"), więc nie dało się
zdecydować, czy winne są progi, cena, czy korekta strumienia ściągająca szansę
pod próg. Dokładnie ta sama ślepota, którą po stronie drużynowej rozdzieliliśmy
2026-07-27 — i tam wina okazała się gdzie indziej, niż wszyscy zakładali.

Progi są PRZENIESIONE, nie zmienione: pewniak 1,19–2,80 przy p≥0,52, perełka
1,90–3,60 przy p≥0,42, niszowa 1,90–3,60 przy p≥0,40 (rynek rzadki + matchup).
"""

from footstats.model import betting


def test_kurs_spoza_obu_pasm():
    assert betting.powod_profilu_zawodnika(8.0, 0.9, 0.9) == "kurs_poza_pasmem"
    assert betting.powod_profilu_zawodnika(1.10, 0.9, 0.9) == "kurs_poza_pasmem"


def test_kurs_w_pasmie_ale_szansa_ponizej_progu():
    # 2,50 mieści się w obu pasmach -> obowiązuje próg łagodniejszy (0,42)
    assert betting.powod_profilu_zawodnika(2.50, 0.40, 0.38) == "szansa_za_niska"
    # 1,50 to wyłącznie pasmo pewniaka -> próg 0,52
    assert betting.powod_profilu_zawodnika(1.50, 0.48, 0.46) == "szansa_za_niska"


def test_rynek_niszowy_z_matchupem_ma_lagodniejszy_prog():
    """Furtka kontekstowa istnieje od dawna — diagnostyka musi ją znać,
    inaczej raportowałaby „za niska szansa" tam, gdzie typ faktycznie wszedł."""
    assert betting.powod_profilu_zawodnika(
        2.50, 0.41, 0.40, rzadki=True, matchup=True) != "szansa_za_niska"
    # bez matchupu ta sama linia nie korzysta z furtki
    assert betting.powod_profilu_zawodnika(
        2.50, 0.41, 0.40, rzadki=True, matchup=False) == "szansa_za_niska"


def test_wartosc_ujemna_przy_szansie_ostroznej():
    """Kurs i szansa w normie, a typ i tak wypada — bo o publikacji decyduje
    szansa OSTROŻNA (średnia p i dolnej granicy).

    ⚑ TYLKO OD KURSU 1,80 (2026-09-11). Niżej warunek pieniężny nie działa,
    bo tani typ ma ujemną wartość z definicji — patrz
    `betting.wartosc_zawodnicza_ok`.
    """
    assert betting.powod_profilu_zawodnika(
        2.00, 0.45, 0.45) == "wartosc_ujemna_przy_ostroznym"


def test_tani_typ_nie_wypada_na_wartosci():
    """⚑ SEDNO NAPRAWY Z 11.09: ten warunek wycinał 1823 kandydatury na cykl.

    Decyzja z 24.08 zdjęła bramy wartości poniżej kursu 1,80, ale ścieżka
    zawodnicza miała warunek przepisany ręcznie w trzech miejscach i nie
    zobaczyła tej zmiany. Kurs 1,60 przy ostrożnej szansie 0,55 daje wartość
    −12% i DO 11.09 wypadał, mimo że trafność w tym paśmie jest najwyższa
    w produkcie.
    """
    assert betting.wartosc_zawodnicza_ok(1.60, 0.55) is True
    assert betting.powod_profilu_zawodnika(1.60, 0.60, 0.55) == "profil_ok"


def test_granica_1_80_jest_ta_sama_co_u_druzyn():
    """Jedno źródło prawdy: `bramy_wartosci_dotycza`, nie druga kopia progu."""
    assert betting.wartosc_zawodnicza_ok(1.79, 0.10) is True
    assert betting.wartosc_zawodnicza_ok(1.80, 0.10) is False
    assert betting.wartosc_zawodnicza_ok(
        betting.KURS_MAX_BEZ_BRAM_WARTOSCI, 0.99) is True


def test_typ_ktory_przechodzi_nie_ma_powodu():
    assert betting.powod_profilu_zawodnika(2.00, 0.60, 0.55) == "profil_ok"


def test_progi_nie_zmienily_sie_przy_przenosinach():
    """Wartości przeniesiono z build_wc_fast bez zmiany — gdyby ktoś je ruszył,
    zmieni się selekcja CAŁEGO strumienia zawodniczego, nie tylko opis."""
    assert betting.PROFIL_PEWNY_MAX_ODDS == 2.80
    assert betting.PROFIL_PEWNY_MIN_P == 0.52
    assert betting.PROFIL_PERELKA_ODDS == (1.90, 3.60)
    assert betting.PROFIL_PERELKA_MIN_P == 0.42
    assert betting.PROFIL_NISZOWA_MIN_P == 0.40
    assert betting.MIN_ODDS == 1.19
