# -*- coding: utf-8 -*-
"""Szansa na karcie ściągana do ceny — decyzja właściciela z 12.08.

Trzy niezależne pomiary pokazały, że wartość jest w cenie, a nasze odchylenia
od niej są w większości błędem. Ściąganie poprawia kalibrację o ~10% Briera
(walidacja czasowa, pięć podziałów) i NIE poprawia ROI.

⚑ DECYZJA, KTÓREJ PILNUJĄ TE TESTY: ściągamy WYŁĄCZNIE liczbę pokazywaną.
Selekcja zostaje na naszej liczbie. Gdyby ściągnięta szansa trafiła przed
bramę „ujemna po korekcie", lista spadłaby z 967 typów do 64 — zmierzone.
"""
import math

import pytest

from footstats.jobs import rozliczanie as R
from footstats.model import betting


def test_sciaganie_przesuwa_szanse_w_strone_ceny():
    kurs = 1.80
    p_rynku = betting.implied_prob_one_sided(kurs)
    p_model = 0.75
    p = R.sciagnij_do_ceny(p_model, kurs, 0.10)
    assert p_rynku < p < p_model, "ściągnięta szansa leży MIĘDZY ceną a modelem"
    assert abs(p - p_rynku) < abs(p - p_model), (
        "przy w=0,10 karta ma być bliżej ceny niż naszej liczby"
    )


def test_waga_jeden_zostawia_nasza_liczbe():
    """w=1 to „nie ruszaj" — potrzebne, żeby dało się wyłączyć bez if-a."""
    for kurs, p_model in ((1.5, 0.8), (2.4, 0.45), (4.0, 0.3)):
        assert abs(R.sciagnij_do_ceny(p_model, kurs, 1.0) - p_model) < 1e-6


def test_waga_zero_pokazuje_sama_cene():
    kurs = 2.10
    p = R.sciagnij_do_ceny(0.9, kurs, 0.0)
    assert abs(p - betting.implied_prob_one_sided(kurs)) < 1e-6


def test_kierunek_dziala_w_obie_strony():
    """Model NIŻSZY od ceny ma być podciągnięty W GÓRĘ, nie zawsze w dół."""
    kurs = 1.60
    p_rynku = betting.implied_prob_one_sided(kurs)
    p = R.sciagnij_do_ceny(p_rynku - 0.20, kurs, 0.10)
    assert p > p_rynku - 0.20
    assert p < p_rynku


def test_za_mala_proba_nie_rusza_karty():
    """Bez próby wolimy nie ruszać liczby, niż ruszyć ją zgadywaniem."""
    log = {str(i): {"wynik": "wygrany", "p_model": 0.7, "kurs": 1.8,
                    "kickoff_ts": 1, "rynek_kod": "team_goals", "wersje": {}}
           for i in range(R.WAGA_SCIAGANIA_MIN_N - 1)}
    assert R.waga_sciagania(log) is None


def test_waga_ma_podloge():
    """`w` = 0 znaczyłoby, że karta pokazuje samą cenę i udaje naszą liczbę.

    Wolimy wtedy przyznać się wprost, że nie mamy nic ponad rynek — a nie
    publikować ceny pod własnym szyldem. Stąd podłoga.
    """
    log = {}
    for i in range(R.WAGA_SCIAGANIA_MIN_N + 50):
        # model kompletnie oderwany od wyników: optimum w* wyszłoby 0,00
        log[str(i)] = {
            "wynik": "wygrany" if i % 2 else "przegrany",
            "p_model": 0.95, "kurs": 1.80, "kickoff_ts": 1000 + i,
            "rynek_kod": "team_goals", "strona": "powyzej", "wersje": {},
        }
    w = R.waga_sciagania(log)
    assert w is not None
    assert w >= R.WAGA_SCIAGANIA_PODLOGA


def test_sciaganie_jest_w_rejestrze_warstw():
    """Warstwa spoza rejestru może paść niezauważona — patrz WARSTWY_UCZENIA."""
    assert "sciaganie_karty" in R.WARSTWY_UCZENIA
    assert "sciaganie_karty" in R.JEDNOSTKI_WARSTW


def test_sciaganie_nie_jest_krytyczne():
    """Ta warstwa dotyczy PREZENTACJI. Gdyby padła, produkt ma pokazać liczbę
    sprzed ściągnięcia, a nie przerwać cykl — inaczej awaria kosmetyki
    zdejmowałaby całą stronę."""
    assert "sciaganie_karty" not in R.WARSTWY_KRYTYCZNE
