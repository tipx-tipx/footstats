"""Leg z dalekiego meczu ma ściągniętą szansę przy składaniu kuponu.

ZMIERZONE 2026-08-04 na 334 legach rozliczonych kuponów — im dalej mecz,
tym gorzej trafia leg, NIEZALEŻNIE od tego, czy zawodniczy, czy drużynowy:

    na dziś       drużynowy  n=110  deklarował 74,8%  weszło 68,2%  − 6,6 pp
    na dziś       zawodniczy n= 50  deklarował 65,0%  weszło 54,0%  −11,0 pp
    na kilka dni  drużynowy  n=103  deklarował 72,9%  weszło 52,4%  −20,4 pp
    na kilka dni  zawodniczy n= 33  deklarował 64,6%  weszło 27,3%  −37,3 pp

Hipoteza „winne są legi zawodnicze" SPRAWDZONA I ODRZUCONA: kupony
długoterminowe złożone wyłącznie z drużynowych też mają 0 trafień na 19.
"""

import time

from footstats.model import kupony


def _leg(godzin_do_meczu: float, teraz: int, p: float = 0.75, kurs: float = 1.6):
    return {
        "p_model": p,
        "kurs": kurs,
        "pewnosc": "wysoka",
        "kickoff_ts": teraz + int(godzin_do_meczu * 3600),
    }


def test_leg_z_dzis_bez_kary():
    teraz = int(time.time())
    l = _leg(6, teraz)
    assert kupony._kara_horyzontu(l, teraz) == 0.0
    # bez `teraz` funkcja liczy jak dotąd — stare wywołania się nie zmieniają
    assert kupony._p_skladania(l) == kupony._p_skladania(l, None, teraz)


def test_im_dalej_mecz_tym_wieksza_kara():
    teraz = int(time.time())
    dzis = kupony._kara_horyzontu(_leg(10, teraz), teraz)
    jutro = kupony._kara_horyzontu(_leg(36, teraz), teraz)
    za_kilka_dni = kupony._kara_horyzontu(_leg(80, teraz), teraz)
    assert dzis < jutro < za_kilka_dni
    assert za_kilka_dni <= 0.20, "kara nie może przekroczyć zmierzonej luki"


def test_kara_sciaga_szanse_skladania():
    teraz = int(time.time())
    bliski = _leg(6, teraz)
    daleki = _leg(80, teraz)
    p_bliski = kupony._p_skladania(bliski, None, teraz)
    p_daleki = kupony._p_skladania(daleki, None, teraz)
    assert p_daleki < p_bliski
    # ten sam leg bez kary horyzontu = ta sama liczba co dla bliskiego
    assert kupony._p_skladania(daleki) == p_bliski


def test_szansa_nigdy_nie_schodzi_do_zera():
    """Kara nie może zrobić z lega czegoś, czego logarytm nie przyjmie."""
    teraz = int(time.time())
    slaby = _leg(200, teraz, p=0.05, kurs=20.0)
    assert kupony._p_skladania(slaby, None, teraz) > 0.0


def test_brak_kickoffu_nie_wybucha():
    teraz = int(time.time())
    assert kupony._kara_horyzontu({"kickoff_ts": None}, teraz) == 0.0
    assert kupony._kara_horyzontu({}, teraz) == 0.0
