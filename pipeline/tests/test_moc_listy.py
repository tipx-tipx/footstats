"""Kolejność „polecane" — jedna miara, liczona przez backend przy dumpie.

Do 14.08 kolejność liczył FRONT (`moc` w DruzynyTablica): p × √kurs i nic
więcej, bo `rank_score` z backendu znaczy co innego w każdym kanale i jest
zerem przy typach wznowionych, czyli przy większości listy.

Teraz liczy ją backend i dokłada jeden ZMIERZONY czynnik — bogactwo materiału
meczu (366 rozliczeń epoki ligowej, bez drabinek):

    1 typ w meczu    n= 33  luka -10,9 pp  ROI +6,4%   (próba za mała)
    2-4 typy         n=176  luka -13,3 pp  ROI -6,7%
    5 i więcej       n=157  luka  -5,3 pp  ROI +8,3%

To jest KOLEJNOŚĆ, nie brama: żaden typ przez to nie znika z listy i żadna
liczba na karcie się nie zmienia.
"""

import math

from footstats.jobs.build_wc_fast import (
    PREMIA_BOGATEGO_MECZU,
    PROG_BOGATEGO_MECZU,
    moc_listy,
)


def _typ(p: float = 0.6, kurs: float = 1.8, **kw) -> dict:
    return {"p_model": p, "kurs": kurs, **kw}


def test_podstawa_to_szansa_razy_pierwiastek_kursu():
    assert moc_listy(_typ(0.64, 2.25), 1) == round(0.64 * 1.5, 4)


def test_tani_pewniak_bije_dlugi_strzal():
    """Sedno pierwiastka: 87% po 1,21 ma wygrać z 43% po 3,55."""
    assert moc_listy(_typ(0.87, 1.21), 1) > moc_listy(_typ(0.43, 3.55), 1)


def test_bogaty_mecz_dostaje_premie():
    zwykly = moc_listy(_typ(), PROG_BOGATEGO_MECZU - 1)
    bogaty = moc_listy(_typ(), PROG_BOGATEGO_MECZU)
    assert bogaty > zwykly
    assert math.isclose(bogaty, round(zwykly * PREMIA_BOGATEGO_MECZU, 4),
                        abs_tol=1e-4)


def test_premia_nie_rosnie_dalej_z_liczba_typow():
    """Próg, nie skala — pomiar miał trzy kubełki, nie krzywą."""
    assert moc_listy(_typ(), PROG_BOGATEGO_MECZU) == moc_listy(
        _typ(), PROG_BOGATEGO_MECZU + 7)


def test_premia_nie_przewraca_kolejnosci_na_glowie():
    """Typ 40% z bogatego meczu NIE ma wyprzedzać typu 85% po tym samym kursie.

    Premia ma przesuwać w obrębie porównywalnych typów, a nie robić z
    bogactwa meczu ważniejszego kryterium niż sam zakład.
    """
    slaby_z_bogatego = moc_listy(_typ(0.40, 1.8), PROG_BOGATEGO_MECZU)
    mocny_z_ubogiego = moc_listy(_typ(0.85, 1.8), 1)
    assert mocny_z_ubogiego > slaby_z_bogatego


def test_sugestia_bez_kursu_liczy_sie_z_fair_kursu():
    """Typ bez kursu bukmachera (sugestia) też musi dostać swoje miejsce."""
    assert moc_listy({"p_model": 0.5, "fair_kurs": 2.0}, 1) == round(
        0.5 * math.sqrt(2.0), 4)


def test_brak_liczb_nie_wywraca_cyklu():
    """Rekord wznowiony sprzed stempli bywa niekompletny — ma dać 0, nie padać."""
    assert moc_listy({}, 1) == 0.0
    assert moc_listy({"p_model": None, "kurs": None}, 9) == 0.0


def test_nie_mutuje_typu():
    """Kolejność nie ma prawa dotknąć liczby, którą widzi klient."""
    t = _typ(0.7, 1.5)
    przed = dict(t)
    moc_listy(t, 9)
    assert t == przed
