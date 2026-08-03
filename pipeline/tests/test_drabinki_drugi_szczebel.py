"""Drugi szczebel drabinki ma być realny — i decyduje o rodzaju gry.

Zgłoszenie usera 2026-08-03: „ważne jest, aby realne było wejście też drugiego
szczebla; możemy podzielić drabinki na dwa typy — jedno z mniejszym kursem,
drugie value, np. 2+ kurs na pierwszy szczebel, ale realna szansa wejścia".

Pomiar, który to potwierdził (bieżący przebieg, 8 drugich szczebli):
0,08 · 0,13 · 0,15 · 0,17 · 0,17 · 0,27 · 0,28 · 0,40 — sześć z ośmiu poniżej
0,27. Powód był mechaniczny: MIN_P_SZCZEBLA obowiązuje dopiero OD TRZECIEGO
szczebla, więc pierwszy i drugi nie miały żadnej podłogi.
"""
import pytest

from footstats.jobs import radar as R


def _karta(rynek="shots", szczeble=()):
    drabinka = [{"linia": l, "kurs": k, "p_final": p} for l, k, p in szczeble]
    return {
        "hero": {"rynek_kod": rynek, "linia": drabinka[0]["linia"]},
        "rynki": [{"rynek_kod": rynek, "drabinka": drabinka}],
    }


# --- rodzaj gry ---

def test_pewna_gdy_drugi_szczebel_realnie_wchodzi():
    w = _karta(szczeble=[(0.5, 1.45, 0.72), (1.5, 2.60, 0.44)])
    assert R._profil_gry(w) == "pewna"


def test_value_gdy_kurs_od_2_a_szansa_bliska_polowie():
    """Bukmacher wycenia jak rzut monetą, my mamy wyraźnie lepiej."""
    w = _karta(szczeble=[(1.5, 2.30, 0.51), (2.5, 4.10, 0.28)])
    assert R._profil_gry(w) == "value"


def test_tani_pewniak_z_martwym_drugim_szczeblem_bez_etykiety():
    """Cała rzecz w tym, żeby OBA szczeble dały się zagrać — pierwszy sam
    nie wystarczy."""
    w = _karta(szczeble=[(0.5, 1.30, 0.78), (1.5, 6.70, 0.09)])
    assert R._profil_gry(w) is None


def test_karta_bez_drugiego_szczebla_bez_etykiety():
    w = _karta(szczeble=[(0.5, 1.40, 0.75)])
    assert R._profil_gry(w) is None


def test_szczebel_bez_policzonej_szansy_nie_daje_etykiety():
    """Brak liczby to brak wiedzy — nie obiecujemy po cichu."""
    w = _karta(szczeble=[(0.5, 1.40, None), (1.5, 2.50, 0.45)])
    assert R._profil_gry(w) is None


def test_value_wymaga_kursu_od_dwoch():
    """Ta sama szansa przy taniej cenie to nie value, tylko słaby pewniak."""
    w = _karta(szczeble=[(1.5, 1.70, 0.51), (2.5, 3.00, 0.28)])
    assert R._profil_gry(w) is None


# --- podłoga drugiego szczebla (progi, nie sama funkcja) ---

def test_progi_maja_sens_wzgledem_siebie():
    """Etykieta «pewna» nie może być łatwiejsza od samej podłogi drabinki —
    inaczej obiecywalibyśmy realny drugi szczebel tam, gdzie go ucięliśmy."""
    assert R.PEWNA_MIN_P_DRUGI >= R.MIN_P_DRUGIEGO_SZCZEBLA
    assert R.VALUE_MIN_P_DRUGI >= R.MIN_P_DRUGIEGO_SZCZEBLA
    assert R.MIN_P_DRUGIEGO_SZCZEBLA > R.MIN_P_SZCZEBLA


@pytest.mark.parametrize("p_drugiego,zostaje", [
    (0.40, 2),   # realny — zostaje
    (0.25, 2),   # dokładnie na progu — zostaje
    (0.24, 1),   # pod progiem — drabinka kończy się na pierwszym
    (0.08, 1),
])
def test_podloga_ucina_martwy_drugi_szczebel(p_drugiego, zostaje):
    """Odtworzenie reguły z `_rynki_wpisu`: ucinamy na pierwszym szczeblu
    (poza pierwszym), który nie sięga progu."""
    drabinka = [
        {"linia": 0.5, "kurs": 1.4, "p_final": 0.7},
        {"linia": 1.5, "kurs": 3.0, "p_final": p_drugiego},
        {"linia": 2.5, "kurs": 8.0, "p_final": 0.05},
    ]
    for i, s in enumerate(drabinka):
        p_f = s.get("p_final")
        if i >= 1 and p_f is not None and p_f < R.MIN_P_DRUGIEGO_SZCZEBLA:
            drabinka = drabinka[:i]
            break
    assert len(drabinka) == zostaje
