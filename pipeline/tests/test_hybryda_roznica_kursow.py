"""Hybryda: karta wpuszczona RÓŻNICĄ MIĘDZY BUKMACHERAMI, nie przewagą modelu.

Decyzja usera 2026-08-08. Do tego dnia różnica kursów była wyłącznie etykietą:
karta musiała najpierw przejść bramę „nasz model bije cenę", a rozjazd tylko ją
opisywał. Odwracało to kolejność dowodów — różnica między dwoma cennikami jest
przewagą, która nie zależy od tego, czy nasz model ma rację, a mamy zmierzone,
że nasza liczba jest gorsza od samego kursu w 7 z 9 rynków.

ZASTRZEŻENIE USERA, KTÓRE TE TESTY PILNUJĄ: „tylko gdy serio ten typ ma szansę
realnie wejść, nie możemy opierać się tylko na kursie".
"""
from footstats.jobs import radar as R


def _kandydat(pokrycie_traf=6, kurs=1.75, p_final=0.54, roznica_pp=None,
              traf2=5, p2=0.40, z=10):
    """Karta, która NIE ma przewagi modelu ani mocnej serii.

    Kurs 1,75 przy pokryciu 6/10 nie łapie się na żadną ścieżkę serii
    (ta wymaga 7/10 przy 1,70+ albo 6/10 przy 2,00+), a przewaga jest dodatnia,
    ale poniżej progu karty — czyli o wejściu może zdecydować wyłącznie
    rozjazd cenowy.
    """
    pierwszy = {
        "linia": 1.5, "kurs": kurs,
        "pokrycie": {"traf": pokrycie_traf, "z": z},
        "p_bazowe": p_final, "korekta": 1.0, "p_final": p_final,
    }
    if roznica_pp is not None:
        pierwszy["rozjazd"] = {
            "betclic": round(kurs * 1.2, 2), "superbet": kurs,
            "roznica_pp": roznica_pp, "przewaga_pct": 20.0, "gdzie": "betclic",
        }
    return {
        "minuty_sr6": 85, "udzial_startow": 0.9,
        "rynki": [{
            "rynek_kod": "shots", "rynek": "Strzały",
            "drabinka": [pierwszy, {
                "linia": 2.5, "kurs": 3.20,
                "pokrycie": {"traf": traf2, "z": z},
                "p_bazowe": p2, "korekta": 1.0, "p_final": p2,
            }],
        }],
    }


def test_bez_roznicy_karta_wchodzi_ale_z_innym_powodem():
    """⚑ PRZEPISANE 2026-08-08 PO ZDJĘCIU BRAMY PRZEWAGI.

    Do tego dnia ta sama karta bez drugiego cennika ODPADAŁA i to był punkt
    wyjścia dla hybrydy. Dziś przewaga nie jest już bramą (`BRAMA_PRZEWAGI`),
    bo pomiar na 86 rozliczeniach pokazał, że nie porządkuje wyników: karty
    z ujemną przewagą wypadały lepiej (−25,7%) niż te z przewagą 8 pp+
    (−57,4%). Kartę zdejmuje odtąd pokrycie, cena i rynek.

    Hybryda NIE STAJE SIĘ PRZEZ TO ZBĘDNA — przestaje być przepustką, zostaje
    nazwą powodu. Różnica cen dalej jest najmocniejszym dowodem, jaki mamy,
    więc karta z nią ma się nazywać inaczej niż karta bez niej.
    """
    _score, hero = R._oceń_karte(_kandydat(roznica_pp=None))
    assert hero is not None
    assert hero["powod_wejscia"] != "roznica_kursow"


def test_roznica_kursow_wpuszcza_karte_bez_przewagi_modelu():
    """Sedno hybrydy: dwaj bukmacherzy wyceniają to samo inaczej."""
    score, hero = R._oceń_karte(_kandydat(roznica_pp=15.0))
    assert hero is not None
    assert hero["powod_wejscia"] == "roznica_kursow"
    assert score > 0


def test_sama_roznica_nie_wystarcza_gdy_typ_realnie_nie_wchodzi():
    """⚑ Zastrzeżenie usera. Pokrycie 4/10 to nie jest typ, który „serio ma
    szansę wejść" — choćby różnica cen była ogromna."""
    _score, hero = R._oceń_karte(_kandydat(pokrycie_traf=4, roznica_pp=30.0))
    assert hero is None


def test_mala_roznica_nie_liczy_sie_jako_powod_wejscia():
    """Poniżej progu różnica jest zwykłym szumem marży, nie okazją — więc
    karta może wejść (przewaga nie jest bramą), ale NIE wolno jej się tłumaczyć
    rozjazdem cenowym, bo żadnego rozjazdu nie ma."""
    _score, hero = R._oceń_karte(
        _kandydat(roznica_pp=R.MIN_ROZJAZD_WEJSCIA - 0.1)
    )
    assert hero is not None
    assert hero["powod_wejscia"] != "roznica_kursow"


def test_prog_pokrycia_hybrydy_jest_ostrzejszy_niz_zwyklej_karty():
    """Skoro model nie wnosi przewagi, dowód ma nieść historia."""
    assert R.PROG_POKRYCIA_HYBRYDY > R.PROG_POKRYCIA_KARTY


def test_prog_wejscia_zgodny_z_etykieta_rozjazdu():
    """Dwie bramy mówiące o tym samym nie mogą stać w dwóch różnych miejscach —
    front nazywa kartę „rozjazdem" od PROG_OKAZJI_PP."""
    assert R.MIN_ROZJAZD_WEJSCIA == R.PROG_OKAZJI_PP


def test_hybryda_nie_omija_pozostalych_bram():
    """Różnica zastępuje WYŁĄCZNIE wymóg przewagi modelu. Zawodnik grający
    po 40 minut odpada tak samo jak wcześniej."""
    karta = _kandydat(roznica_pp=30.0)
    karta["minuty_sr6"] = 40
    _score, hero = R._oceń_karte(karta)
    assert hero is None


def test_hybryda_wymaga_realnego_drugiego_szczebla():
    """Karta wpuszczona różnicą to dalej DRABINKA — drugi szczebel musi
    wchodzić tak samo jak w każdej innej."""
    _score, hero = R._oceń_karte(_kandydat(roznica_pp=30.0, traf2=1, p2=0.12))
    assert hero is None
