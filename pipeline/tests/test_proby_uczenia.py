# -*- coding: utf-8 -*-
"""Rozmiar próby ma być widoczny ZANIM warstwa zniknie.

Audyt z 05.08: strumień zawodniczy miał 41 rozliczeń przy progu 40. Jedno
rozliczenie mniej i `korekta_strumienia` przestaje zwracać dla niego wartość —
bez błędu, bez wpisu, bez różnicy w logu. Strumień pod progiem wygląda wtedy
dokładnie tak samo jak strumień idealnie skalibrowany (oba są nieobecne).

Drugi czujnik z tej samej rodziny: rynki, które publikujemy, mimo że nie mają
własnej kalibracji. 78% materiału do uczenia dawały dwa rynki, a jeden z nich
siedział w kwarantannie i miał zero typów na stronie.
"""
import time

import pytest

from footstats.jobs import rozliczanie as R


def _typ(strumien: str, i: int, wynik: str = "wygrany") -> dict:
    """Rozliczony typ danego strumienia, z bieżącej epoki."""
    baza = {
        "wynik": wynik,
        "p_model": 0.7,
        "kurs": 1.8,
        "kickoff_ts": int(time.time()) - 3600 * (i + 1),
        "rynek_kod": "team_goals",
        "wersje": {},
    }
    # BEZ `zrodlo` = typ policzony przez silnik (`_z_modelu`). Wpisanie tu
    # czegokolwiek — nawet "model" — wyklucza typ z uczenia.
    if strumien == "drabinki":
        baza["zrodlo"] = R.ZRODLO_DRABINKA
    if strumien == "druzyny":
        baza["ekran"] = "druzyny"
    elif strumien == "pewniaki":
        baza["ekran"] = "pewniaki"
    return baza


def _log(wpisy: list[dict]) -> dict:
    return {str(i): {**w, "id": i} for i, w in enumerate(wpisy)}


def _proby(strumien: str, ile: int) -> dict[str, dict]:
    return R.proby_strumieni(_log([_typ(strumien, i) for i in range(ile)]))


def test_kazdy_strumien_jest_w_raporcie_takze_pusty():
    """Strumień z zerem rozliczeń MUSI być widoczny jako zero, nie jako brak."""
    proby = R.proby_strumieni(_log([]))
    assert set(proby) == set(R.STRUMIENIE)
    assert all(p["n"] == 0 and not p["dziala"] for p in proby.values())


def test_ponizej_progu_jest_zglaszane():
    proby = _proby("druzyny", 5)
    assert proby["druzyny"]["dziala"] is False
    zdania = R.ostrzezenia_prob(proby)
    assert any("druzyny" in z and "BRAK własnej korekty" in z for z in zdania)


def test_na_styk_progu_jest_zglaszane_zanim_warstwa_zniknie():
    """Sedno czujnika: ostrzeżenie leci, gdy warstwa JESZCZE działa."""
    n = R.KOREKTA_STRUMIENIA_MIN_N + 1          # dokładnie sytuacja z 05.08
    proby = _proby("druzyny", n)
    assert proby["druzyny"]["dziala"] is True, "warstwa ma jeszcze działać"
    assert proby["druzyny"]["na_styk"] is True
    zdania = R.ostrzezenia_prob(proby)
    assert any("NA STYK" in z for z in zdania)


def test_zdrowa_proba_nie_halasuje():
    proby = _proby("druzyny", R.KOREKTA_STRUMIENIA_MIN_N * 2)
    assert proby["druzyny"]["dziala"] and not proby["druzyny"]["na_styk"]
    assert all("druzyny" not in z for z in R.ostrzezenia_prob(proby))


def test_drabinki_maja_wlasny_prog():
    """Drabinki mierzą się niższym progiem — nie wolno ich mierzyć progiem modelu."""
    proby = _proby("drabinki", R.KOREKTA_DRABINEK_MIN_N)
    assert proby["drabinki"]["prog"] == R.KOREKTA_DRABINEK_MIN_N
    assert proby["drabinki"]["dziala"] is True


def test_proba_nie_przekracza_okna_korekty():
    """Korekta i tak patrzy na ostatnie N — raport nie ma prawa obiecywać więcej."""
    proby = _proby("druzyny", R.KOREKTA_STRUMIENIA_OKNO + 50)
    assert proby["druzyny"]["n"] == R.KOREKTA_STRUMIENIA_OKNO


# --- rynki publikowane bez własnej kalibracji ---

def test_rynek_publikowany_bez_rozliczen_jest_wskazany():
    log = _log([])
    bez = R.rynki_bez_kalibracji([{"rynek_kod": "match_cards"}] * 3, log)
    assert bez and bez[0]["rynek"] == "match_cards"
    assert bez[0]["publikacji"] == 3 and bez[0]["rozliczen"] == 0


def test_rynek_z_pelna_proba_nie_jest_wskazany():
    log = _log([_typ("druzyny", i) for i in range(R.MIN_N_KALIBRACJI + 5)])
    bez = R.rynki_bez_kalibracji([{"rynek_kod": "team_goals"}], log)
    assert bez == []


def test_rynek_uczony_ale_nieopublikowany_nie_jest_alarmem():
    """Kwarantanna to nie jest usterka — raport dotyczy tego, co SPRZEDAJEMY."""
    log = _log([_typ("druzyny", i) for i in range(R.MIN_N_KALIBRACJI + 5)])
    assert R.rynki_bez_kalibracji([], log) == []


def test_typy_probne_nie_licza_sie_jako_publikacja():
    log = _log([])
    assert R.rynki_bez_kalibracji(
        [{"rynek_kod": "match_cards", "sugestia": True}], log) == []


@pytest.mark.parametrize("opublikowane", [None, []])
def test_pusty_wsad_nie_wywala(opublikowane):
    assert R.rynki_bez_kalibracji(opublikowane, _log([])) == []


# --- odmiana liczebnika (te zdania czyta człowiek, nie parser) ---

@pytest.mark.parametrize("n,oczekiwane", [
    (0, "0 rozliczeń"), (1, "1 rozliczenie"), (2, "2 rozliczenia"),
    (4, "4 rozliczenia"), (5, "5 rozliczeń"), (12, "12 rozliczeń"),
    (13, "13 rozliczeń"), (14, "14 rozliczeń"), (22, "22 rozliczenia"),
    (25, "25 rozliczeń"), (101, "101 rozliczeń"), (102, "102 rozliczenia"),
])
def test_odmiana_liczebnika(n, oczekiwane):
    assert R.odmien(n, "rozliczenie", "rozliczenia", "rozliczeń") == oczekiwane


def test_ostrzezenie_uzywa_poprawnej_odmiany():
    proby = _proby("druzyny", R.KOREKTA_STRUMIENIA_MIN_N + 1)
    zdanie = next(z for z in R.ostrzezenia_prob(proby) if z.startswith("druzyny"))
    assert "41 rozliczeń" in zdanie and "2 rozliczenia od zniknięcia" in zdanie
