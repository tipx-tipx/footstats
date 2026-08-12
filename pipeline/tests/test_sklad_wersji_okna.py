# -*- coding: utf-8 -*-
"""Czujnik: ile z okna korekty strumienia liczy BIEŻĄCA wersja produktu.

Audyt zalecił twardy filtr wersji w trzech warstwach uczenia. Pomiar z 12.08
pokazał, że filtr byłby SZKODLIWY — okno 120 ostatnich rozliczeń samo izoluje
wersję tam, gdzie strumień żyje (drużyny: -0,439 wobec -0,428, czyli różnica
poniżej progu istotności warstwy), a tam gdzie nie żyje, skasowałby korektę
do zera (zawodnicy mieli 0 rozliczeń nowej wersji, drabinki 2).

Zamiast filtra jest licznik. Te testy pilnują, żeby mówił prawdę — bo to on
zastępuje mechanizm, którego świadomie nie wprowadziliśmy.
"""
import time

from footstats.jobs import rozliczanie as R
from footstats.model import betting


def _typ(i: int, strumien_ekran: str, wersja: str | None, p=0.7) -> dict:
    r = {
        "wynik": "wygrany" if i % 3 else "przegrany",
        "p_model": p, "kurs": 1.8,
        "kickoff_ts": int(time.time()) - 3600 * (i + 1),
        "rynek_kod": "team_goals",
        "ekran": strumien_ekran,
        "wersje": {"kalibracja": wersja} if wersja else {},
    }
    return r


def _log(wpisy):
    return {str(i): {**w, "id": i} for i, w in enumerate(wpisy)}


def test_liczy_udzial_biezacej_wersji():
    biezaca = betting.WERSJA_KALIBRACJI
    log = _log(
        [_typ(i, "druzyny", biezaca) for i in range(30)]
        + [_typ(100 + i, "druzyny", "2026-07-31-stara") for i in range(10)]
    )
    sklad = R.sklad_wersji_okna(log)
    assert sklad["druzyny"]["n"] == 40
    assert sklad["druzyny"]["biezaca"] == 30
    assert abs(sklad["druzyny"]["udzial"] - 0.75) < 1e-6


def test_rekord_bez_stempla_wersji_nie_liczy_sie_jako_biezacy():
    """Brak stempla to NIE jest bieżąca wersja — mylenie tych dwóch rzeczy
    kazałoby czujnikowi meldować spokój dokładnie wtedy, gdy jest najgorzej."""
    log = _log([_typ(i, "druzyny", None) for i in range(20)])
    sklad = R.sklad_wersji_okna(log)
    assert sklad["druzyny"]["n"] == 20
    assert sklad["druzyny"]["biezaca"] == 0
    assert sklad["druzyny"]["udzial"] == 0.0


def test_strumien_bez_rozliczen_nie_wywala_czujnika():
    sklad = R.sklad_wersji_okna(_log([]))
    for strumien in R.STRUMIENIE:
        assert sklad[strumien]["n"] == 0
        assert sklad[strumien]["udzial"] == 0.0
    assert "brak rozliczeń" in R.zdanie_skladu_wersji(sklad)


def test_okno_przycina_probe_tak_samo_jak_korekta():
    """Czujnik ma opisywać TO SAMO okno, którego używa korekta — inaczej
    mierzyłby inną populację niż ta, która realnie uczy."""
    biezaca = betting.WERSJA_KALIBRACJI
    ile = R.KOREKTA_STRUMIENIA_OKNO + 50
    log = _log([_typ(i, "druzyny", biezaca) for i in range(ile)])
    sklad = R.sklad_wersji_okna(log)
    assert sklad["druzyny"]["n"] == R.KOREKTA_STRUMIENIA_OKNO


def test_zdanie_jest_czytelne():
    biezaca = betting.WERSJA_KALIBRACJI
    log = _log([_typ(i, "druzyny", biezaca) for i in range(20)])
    zdanie = R.zdanie_skladu_wersji(R.sklad_wersji_okna(log))
    assert "BIEŻĄCA" in zdanie
    assert "druzyny: 20/20 (100%)" in zdanie
