# -*- coding: utf-8 -*-
"""Warstwa uczenia nie ma prawa umrzeć po cichu.

Kontekst: 01.08 jeden `print` z polskim znakiem wywalił `korekta_strumienia`
w środku bloku `try/except`, który łapał wyjątek i leciał dalej z pustym
słownikiem. Przez półtorej doby model publikował typy bez korekty i wyglądało
to identycznie jak „korekta wyszła zero". Ten zestaw pilnuje trzech rzeczy:

1. KAŻDA warstwa z `WARSTWY_UCZENIA` jest realnie wpięta w kod cyklu —
   dopisanie nowej warstwy bez `with warstwa_uczenia(...)` wywala test.
2. Padnięcie warstwy zostawia ślad (`ok=False` + treść błędu), a nie ciszę.
3. Dwie warstwy krytyczne (`korekta_strumienia`, `szansa_pokazywana`) po
   padnięciu są raportowane przez `krytyczne_padniete()` — na tym stoi twardy
   stop w `build_wc_fast` i pominięcie zapisu kuponów w `rozlicz_only`.
"""
import io
import re
from pathlib import Path

import pytest

from footstats.jobs import rozliczanie

BAZA = Path(__file__).resolve().parents[1] / "footstats" / "jobs"


def _zrodlo(nazwa: str) -> str:
    return io.open(BAZA / nazwa, encoding="utf-8").read()


@pytest.fixture(autouse=True)
def _czysty_rejestr():
    rozliczanie.reset_stanu_uczenia()
    yield
    rozliczanie.reset_stanu_uczenia()


def test_kazda_warstwa_jest_wpieta_w_cykl():
    """Lista warstw i kod cyklu muszą się zgadzać w obie strony."""
    kod = _zrodlo("build_wc_fast.py") + _zrodlo("rozlicz_only.py")
    wpiete = set(re.findall(r'warstwa_uczenia\(\s*"([a-z_]+)"', kod))
    brakuje = set(rozliczanie.WARSTWY_UCZENIA) - wpiete
    assert not brakuje, (
        "warstwy z WARSTWY_UCZENIA bez `with warstwa_uczenia(...)` w cyklu: "
        + ", ".join(sorted(brakuje))
        + " — taka warstwa może paść i nikt tego nie zobaczy")
    nadmiar = wpiete - set(rozliczanie.WARSTWY_UCZENIA)
    assert not nadmiar, (
        "warstwy wpięte w cyklu, ale nieobecne w WARSTWY_UCZENIA: "
        + ", ".join(sorted(nadmiar))
        + " — nie trafią do meta.uczenie_stan ani do tabeli w logu")


def test_krytyczne_sa_podzbiorem_listy():
    assert set(rozliczanie.WARSTWY_KRYTYCZNE) <= set(rozliczanie.WARSTWY_UCZENIA)


def test_warstwa_udana_raportuje_probe():
    with rozliczanie.warstwa_uczenia("kwarantanna_rynkow") as w:
        w.opisz(n=3, opis="team_goals, shots")
    stan = rozliczanie.stan_uczenia()["kwarantanna_rynkow"]
    assert stan["ok"] is True
    assert stan["n"] == 3
    assert stan["blad"] is None
    assert not rozliczanie.krytyczne_padniete()


def test_warstwa_padnieta_zostawia_slad_i_nie_wysadza_cyklu():
    with rozliczanie.warstwa_uczenia("kwarantanna_rynkow"):
        raise ValueError("cokolwiek")
    stan = rozliczanie.stan_uczenia()["kwarantanna_rynkow"]
    assert stan["ok"] is False
    assert "ValueError" in stan["blad"] and "cokolwiek" in stan["blad"]
    # warstwa poboczna NIE zatrzymuje cyklu
    assert not rozliczanie.krytyczne_padniete()


def test_padniecie_krytycznej_jest_wykrywane():
    with rozliczanie.warstwa_uczenia("korekta_strumienia"):
        raise RuntimeError("brak danych")
    assert rozliczanie.krytyczne_padniete() == ["korekta_strumienia"]


def test_print_z_polskim_znakiem_nie_przechodzi_niezauwazony():
    """Dokładnie incydent z 01.08 — UnicodeEncodeError w środku warstwy."""
    with rozliczanie.warstwa_uczenia("szansa_pokazywana"):
        raise UnicodeEncodeError("charmap", "ł", 0, 1, "brak znaku")
    assert rozliczanie.krytyczne_padniete() == ["szansa_pokazywana"]
    assert "UnicodeEncodeError" in rozliczanie.stan_uczenia()["szansa_pokazywana"]["blad"]


def test_raport_wymienia_kazda_warstwe_takze_nieuruchomiona():
    """Warstwa, która w ogóle się nie uruchomiła, musi być widoczna jako brak.

    Bez tego zniknięcie wywołania (np. przy refaktorze) wyglądałoby jak cisza,
    a nie jak ubytek uczenia."""
    with rozliczanie.warstwa_uczenia("korekta_strumienia") as w:
        w.opisz(n=3)
    raport = rozliczanie.raport_stanu_uczenia()
    for nazwa in rozliczanie.WARSTWY_UCZENIA:
        assert nazwa in raport, f"{nazwa} nie pojawia się w tabeli stanu"


def test_twardy_stop_jest_w_kodzie_cyklu():
    """Sam rejestr nic nie daje, jeśli nikt nie sprawdza jego werdyktu."""
    kod = _zrodlo("build_wc_fast.py")
    assert "krytyczne_padniete()" in kod
    assert "stan_uczenia()" in kod, "meta.uczenie_stan nie byłoby zapisane"
    assert "raport_stanu_uczenia()" in kod, "tabela nie drukuje się w cyklu"
    assert "krytyczne_padniete()" in _zrodlo("rozlicz_only.py")


def test_kazda_warstwa_ma_jednostke_dla_swojego_n():
    """`n` znaczy co innego w każdej warstwie — panel nie ma prawa zgadywać.

    Do 05.08 front podpisywał każdą liczbę słowem „rozliczeń", a rozliczenia
    liczy DOKŁADNIE JEDNA warstwa z dziewięciu. Reszta liczy rynki, strony,
    kubełki pewności albo horyzonty kuponów."""
    brak = [n for n in rozliczanie.WARSTWY_UCZENIA
            if len(rozliczanie.JEDNOSTKI_WARSTW.get(n) or ()) != 3]
    assert not brak, ("warstwy bez trzech form odmiany w JEDNOSTKI_WARSTW: "
                      + ", ".join(brak))


def test_jednostka_trafia_do_stanu_warstwy():
    with rozliczanie.warstwa_uczenia("kwarantanna_rynkow") as w:
        w.opisz(n=3)
    stan = rozliczanie.stan_uczenia()["kwarantanna_rynkow"]
    assert stan["jednostka"] == ["rynek", "rynki", "rynków"]


def test_raport_odmienia_jednostke_a_nie_pisze_n_rowna_sie():
    with rozliczanie.warstwa_uczenia("kwarantanna_rynkow") as w:
        w.opisz(n=3)
    with rozliczanie.warstwa_uczenia("wagi_zaufania") as w:
        w.opisz(n=1)
    raport = rozliczanie.raport_stanu_uczenia()
    assert "3 rynki" in raport
    assert "1 kubełek pewności" in raport
