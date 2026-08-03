"""Rynek znika ze strony, gdy jest TRAGICZNY — nie gdy jest dokładnie zmierzony.

POWÓD (2026-08-03). Kryterium stało na samej istotności statystycznej, a `se`
to różnica podzielona przez błąd standardowy, który maleje jak √n. Przy stałej,
choćby maleńkiej stracie do ceny bukmachera `se` rośnie więc z próbą bez końca
i każdy rynek, który nie bije kursu, prędzej czy później przekracza próg. Strona
pustoszałaby sama z siebie, mimo że nic się nie pogorszyło.

Złapane w ostatniej chwili: `team_corners|ponizej` (7 z 18 typów na stronie,
178 publikacji) miał se −2,78 przy różnicy −0,025 i dzieliły go od zniknięcia
najwyżej trzy dni.
"""

from footstats.jobs import rozliczanie


def _rynek(se: float, roznica: float, n: int = 200) -> dict:
    return {"n": n, "se": se, "roznica": roznica}


def _hist(klucz: str, se: float, dni: int = 4) -> dict:
    return {f"2026-08-{d:02d}": {"rynki": {klucz: {"se": se}}}
            for d in range(1, 1 + dni)}


def test_maly_dystans_nie_ukrywa_choc_jest_istotny():
    """SEDNO poprawki: −0,025 Briera to nie tragedia, tylko dokładny pomiar."""
    teraz = {"team_corners|ponizej": _rynek(-2.78, -0.025, 216)}
    assert rozliczanie.rynki_do_ukrycia(
        teraz, _hist("team_corners|ponizej", -2.78), set()) == set()


def test_duzy_dystans_dalej_ukrywa():
    teraz = {"kiepski|powyzej": _rynek(-3.4, -0.09, 120)}
    assert rozliczanie.rynki_do_ukrycia(
        teraz, _hist("kiepski|powyzej", -3.4), set()) == {"kiepski|powyzej"}


def test_sam_duzy_dystans_bez_istotnosci_nie_wystarcza():
    """Dwa warunki, nie jeden — pechowa seria na małej próbie nie jest wyrokiem."""
    teraz = {"pechowy|powyzej": _rynek(-1.2, -0.20, 80)}
    assert rozliczanie.rynki_do_ukrycia(
        teraz, _hist("pechowy|powyzej", -1.2), set()) == set()


def test_za_mala_proba_nadal_chroni():
    teraz = {"nowy|powyzej": _rynek(-4.0, -0.30, 30)}
    assert rozliczanie.rynki_do_ukrycia(
        teraz, _hist("nowy|powyzej", -4.0), set()) == set()


def test_brak_pomiaru_dystansu_nie_ukrywa():
    """Rekord bez `roznica` (starszy pomiar) nie jest dowodem tragedii.
    Ukrycie zabiera produkt, więc przy niepewności zostajemy przy stronie."""
    teraz = {"stary|powyzej": {"n": 200, "se": -3.5}}
    assert rozliczanie.rynki_do_ukrycia(
        teraz, _hist("stary|powyzej", -3.5), set()) == set()


def test_histereza_nietknieta_nic_nie_wraca_nagle():
    """Rynek już ukryty wychodzi na STARYCH zasadach. Ta zmiana ma przestać
    zabierać produkt, a nie nagle go przywracać."""
    teraz = {"shots|powyzej": _rynek(-2.91, -0.026, 156)}
    juz = {"shots|powyzej"}
    assert rozliczanie.rynki_do_ukrycia(
        teraz, _hist("shots|powyzej", -2.91), juz) == {"shots|powyzej"}
    # ...i wraca dopiero po realnej poprawie, tak jak dotąd
    lepszy = {"shots|powyzej": _rynek(-0.4, -0.004, 156)}
    assert rozliczanie.rynki_do_ukrycia(
        lepszy, _hist("shots|powyzej", -0.4), juz) == set()
