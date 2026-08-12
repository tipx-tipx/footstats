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


# --- DO JAKIEJ CENY ŚCIĄGAMY (2026-08-13) --------------------------------
#
# ⚑ REGRESJA, KTÓRA TU DOPROWADZIŁA: ściągaliśmy do ceny po zdjęciu ZAŁOŻONYCH
# 7% marży, a wartość i uczciwy kurs liczyliśmy wobec kursu Z marżą. Pierwszy
# cykl z aktywnym ściąganiem dał 0 z 31 typów z dodatnią wartością — przy
# w=0,10 typ musiałby mieć szansę o 63% wyższą niż cena, czyli poniżej kursu
# 1,63 było to arytmetycznie niemożliwe. Karta ogłaszała „kurs poniżej
# wartości" przy KAŻDYM typie, niezależnie od tego, co model policzył.


def _log_ceny(n: int, kurs: float, hit: float) -> dict:
    """Księga, w której cena 1/kurs jest znana, a trafienia zadane wprost."""
    ile_wygranych = round(n * hit)
    return {
        str(i): {
            "wynik": "wygrany" if i < ile_wygranych else "przegrany",
            "p_model": 0.70, "kurs": kurs, "kickoff_ts": 1000 + i,
            "rynek_kod": "team_goals", "strona": "ponizej", "wersje": {},
        }
        for i in range(n)
    }


def test_marza_odtwarza_zmierzona_cene():
    """Kurs 2,00 mówi 50%, wchodzi 47,5% — marża to 5%, nie założone 7%."""
    m = R.marza_sciagania(_log_ceny(2000, 2.00, 0.475))
    assert 0.05 <= m <= 0.055, f"marża z pomiaru wyszła {m}"


def test_marza_shrinka_do_domyslnej_przy_malej_probie():
    """Krótka seria wyników nie ma prawa przestawić cennika."""
    duza = R.marza_sciagania(_log_ceny(2000, 2.00, 0.50))
    mala = R.marza_sciagania(_log_ceny(100, 2.00, 0.50))
    dom = R.MARZA_SCIAGANIA_DOMYSLNA
    assert abs(mala - dom) < abs(duza - dom), (
        "przy małej próbie marża ma zostać bliżej domyślnej"
    )


def test_marza_nie_wychodzi_poza_zakres():
    """Ujemna marża znaczyłaby, że bukmacher dopłaca; 20% — że zepsuły się dane."""
    assert R.marza_sciagania(_log_ceny(2000, 2.00, 0.70)) == 0.0
    assert R.marza_sciagania(_log_ceny(2000, 2.00, 0.10)) <= R.MARZA_SCIAGANIA_SUFIT


def test_bez_proby_zostaje_domyslna():
    assert R.marza_sciagania({}) == R.MARZA_SCIAGANIA_DOMYSLNA


def test_karta_nie_oglasza_ujemnej_wartosci_przy_uczciwej_cenie():
    """⚑ SEDNO: gdy nasza liczba zgadza się z ceną, wartość ma wyjść ~0.

    Do 13.08 wychodziło −7%, bo ściągaliśmy do ceny bez marży, a wartość
    liczyliśmy wobec kursu z marżą. Ten test pilnuje, żeby obie strony
    rachunku używały TEJ SAMEJ ceny.
    """
    kurs = 1.80
    p_model = 1.0 / kurs
    p = R.sciagnij_do_ceny(p_model, kurs, 0.10, marza=0.0)
    assert abs(betting.ev_brutto_pct(p, kurs)) < 0.5, (
        "typ wyceniony dokładnie po cenie nie może pokazywać ujemnej wartości"
    )


def test_marza_z_pomiaru_wpuszcza_typy_z_przewaga_na_plus():
    """Typ z realną przewagą ma pokazać dodatnią wartość, a nie ujemną.

    Przy założonych 7% ten sam typ wychodził na minus — i to nie zależało od
    tego, jak dobry był: mieszanie idzie w LOGICIE, więc próg przewagi rośnie
    z marżą i przy 7% robi się nieosiągalny na krótkich kursach.
    """
    kurs = 2.20
    p_model = 1.0 / kurs + 0.20          # +20 pp nad ceną
    p_zmierzona = R.sciagnij_do_ceny(p_model, kurs, 0.10, marza=0.03)
    p_zalozona = R.sciagnij_do_ceny(p_model, kurs, 0.10, marza=0.07)
    assert betting.ev_brutto_pct(p_zmierzona, kurs) > 0
    assert betting.ev_brutto_pct(p_zalozona, kurs) < 0, (
        "dokumentuje stan sprzed naprawy — przy założonych 7% ten sam typ "
        "wychodził na minus"
    )


def test_prog_przewagi_rosnie_z_marza():
    """Ile przewagi trzeba mieć, żeby karta pokazała plus — przy każdej marży.

    Zmierzone przy w=0,10 (próg w pp nad ceną): kurs 1,75 wymaga 28,0 pp przy
    marży 7%, 16,3 pp przy 3,5% i 9,8 pp przy 2%. Nasze typy mają medianę
    przewagi ~10 pp, więc przy założonych 7% na plus nie wychodził ŻADEN.
    Mieszanie idzie w logicie, nie liniowo — próg liczy się przeszukiwaniem,
    a nie wzorem, bo wzór liniowy dawał tu wcześniej zły wynik.
    """
    def prog(kurs: float, marza: float, w: float = 0.10) -> float:
        lo, hi = 1.0 / kurs, 0.99999
        for _ in range(80):
            sr = (lo + hi) / 2
            if R.sciagnij_do_ceny(sr, kurs, w, marza) > 1.0 / kurs:
                hi = sr
            else:
                lo = sr
        return hi - 1.0 / kurs

    assert prog(1.75, 0.07) > prog(1.75, 0.035) > prog(1.75, 0.02), (
        "wyższa marża = wyższy próg przewagi"
    )
    assert prog(1.75, 0.07) > 0.20, "przy 7% próg wypada poza zasięg naszych typów"


def test_waga_dobiera_sie_pod_podana_cene():
    """Waga i marża muszą opisywać tę samą cenę — inaczej karta ściąga się
    do jednej, a waga była liczona pod inną."""
    log = _log_ceny(600, 1.80, 0.55)
    assert R.waga_sciagania(log, marza=0.0) is not None
    assert R.waga_sciagania(log, marza=0.07) is not None


def test_sciaganie_jest_w_rejestrze_warstw():
    """Warstwa spoza rejestru może paść niezauważona — patrz WARSTWY_UCZENIA."""
    assert "sciaganie_karty" in R.WARSTWY_UCZENIA
    assert "sciaganie_karty" in R.JEDNOSTKI_WARSTW


def test_sciaganie_nie_jest_krytyczne():
    """Ta warstwa dotyczy PREZENTACJI. Gdyby padła, produkt ma pokazać liczbę
    sprzed ściągnięcia, a nie przerwać cykl — inaczej awaria kosmetyki
    zdejmowałaby całą stronę."""
    assert "sciaganie_karty" not in R.WARSTWY_KRYTYCZNE
