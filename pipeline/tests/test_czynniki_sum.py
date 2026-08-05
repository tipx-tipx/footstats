# -*- coding: utf-8 -*-
"""Sumy meczowe muszą umieć się wytłumaczyć.

Audyt z 05.08 (znalezisko nr 7): `match_cards` i `match_corners` szły na stronę
z `czynniki: {}`. Wyglądało to na kosmetykę — karta nie miała czym wypełnić
kroku „skąd ta liczba" — ale konsekwencja była twarda: brama uzasadnień
(`betting.ma_komplet_uzasadnienia`) patrzy DOKŁADNIE na to pole, więc każdy typ
na sumie poniżej progu półki pewnej wypadał z listy jako „bez uzasadnienia".
Model liczył pełen zestaw poprawek dla obu drużyn, tylko nigdzie ich nie
zapisywał.
"""
from types import SimpleNamespace

import pytest

from footstats.model import betting
from footstats.jobs.build_wc_fast import czynniki_pary, mnozniki_pary


def _druzyna(nazwa: str, lam: float, **czynniki) -> dict:
    baza = {"rywal": 1.0, "sedzia": 1.0, "dom_wyjazd": 1.0,
            "scenariusz_meczu": 1.0, "matchup": 1.0, "lacznie": 1.0}
    baza.update(czynniki)
    return {
        "nazwa": nazwa,
        "pred": SimpleNamespace(lam=lam),
        "czynniki": baza,
    }


def test_mnozniki_sa_srednia_geometryczna_obu_stron():
    """Suma nie ma „swojego" rywala — każda drużyna ma innego."""
    h = _druzyna("Gospodarz", 1.2, rywal=1.44)
    a = _druzyna("Gość", 1.0, rywal=1.0)
    mn = mnozniki_pary(h, a)
    assert mn["rywal"] == pytest.approx(1.2, abs=1e-3)   # sqrt(1,44 * 1,00)


def test_brak_mnoznikow_po_jednej_stronie_daje_pustke_a_nie_jedynki():
    """Cisza jest uczciwsza niż wpisanie 1,00 tam, gdzie nic nie policzyliśmy."""
    h = _druzyna("Gospodarz", 1.2, rywal=1.2)
    a = {"nazwa": "Gość", "pred": SimpleNamespace(lam=1.0)}
    assert mnozniki_pary(h, a) == {}


def test_suma_przechodzi_brame_uzasadnien():
    """Sedno naprawy: z tym polem typ na sumie NIE wypada już jako bez rachunku."""
    h, a = _druzyna("Gospodarz", 1.2, rywal=1.1), _druzyna("Gość", 1.0)
    typ = {
        "p_model": 0.55,                     # poniżej PROG_POLKI_PEWNE
        "ci": [0.48, 0.63],
        "czynniki": mnozniki_pary(h, a),
    }
    assert betting.wymaga_uzasadnienia(typ["p_model"])
    assert betting.ma_komplet_uzasadnienia(typ)


def test_pusty_czynnik_nadal_wypada_z_listy():
    """Brama ma dalej działać — naprawiamy dane, nie rozbrajamy kontroli."""
    typ = {"p_model": 0.55, "ci": [0.48, 0.63], "czynniki": {}}
    assert not betting.ma_komplet_uzasadnienia(typ)


def test_poziom_bazowy_jest_zawsze_pierwszy():
    """`skadTaLiczba` po stronie web zwraca null bez „Poziomu bazowego"."""
    h, a = _druzyna("Gospodarz", 1.2), _druzyna("Gość", 0.9)
    lista = czynniki_pary(h, a, "corners", rho=0.0)
    assert lista[0]["nazwa"] == "Poziom bazowy"
    assert "1.2" in lista[0]["opis"] and "0.9" in lista[0]["opis"]


def test_mnoznik_bez_wplywu_nie_produkuje_zdania():
    """Mnożnik 1,00 nic nie robi — zdanie o nim byłoby szumem."""
    h, a = _druzyna("Gospodarz", 1.2), _druzyna("Gość", 0.9)
    lista = czynniki_pary(h, a, "corners", rho=0.0)
    assert [c["nazwa"] for c in lista] == ["Poziom bazowy"]


def test_kazdy_mnoznik_ma_swoje_zdanie_i_kierunek():
    h = _druzyna("Gospodarz", 1.2, rywal=1.30, dom_wyjazd=1.20,
                 scenariusz_meczu=0.80, matchup=1.15, sedzia=1.10)
    a = _druzyna("Gość", 0.9, rywal=1.30, dom_wyjazd=1.20,
                 scenariusz_meczu=0.80, matchup=1.15, sedzia=1.10)
    lista = czynniki_pary(h, a, "cards", rho=0.0)
    nazwy = [c["nazwa"] for c in lista]
    for oczekiwana in ("Profil rywali", "Dom i wyjazd", "Scenariusz meczu",
                       "Styl rywali", "Sędzia"):
        assert oczekiwana in nazwy
    wg_nazwy = {c["nazwa"]: c for c in lista}
    assert "podnos" in wg_nazwy["Profil rywali"]["opis"]
    assert "obniża" in wg_nazwy["Scenariusz meczu"]["opis"]
    # mnożnik ma trafić na kartę jako liczba, nie tylko jako słowo
    assert wg_nazwy["Sędzia"]["mnoznik"] == pytest.approx(1.10, abs=1e-3)


def test_korelacja_ponizej_progu_milczy():
    """Zdanie o zerowej korelacji jest zdaniem o naszej kuchni, nie o meczu."""
    h, a = _druzyna("Gospodarz", 1.2), _druzyna("Gość", 0.9)
    assert all(c["nazwa"] != "Zależność między drużynami"
               for c in czynniki_pary(h, a, "corners", rho=0.01))
    assert any(c["nazwa"] == "Zależność między drużynami"
               for c in czynniki_pary(h, a, "corners", rho=-0.13))
