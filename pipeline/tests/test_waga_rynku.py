"""Ile naszej liczby warto mieszać z ceną — pomiar, nie brama.

`przewaga_rynkow` odpowiada „czy bijemy cenę". To jest pytanie następne
i praktyczniejsze: ILE naszego zdania warto dołożyć do ceny, żeby wyszła
najlepsza prognoza.

PIERWSZY POMIAR (932 rozliczenia ligowe, 2026-08-03) był niewygodny:
    całość                 w*=0,00   Brier 0,2073 zamiast 0,2282
    shots|powyzej    n=37  w*=1,00   ROI +20,4%
    team_corners|powyzej n=67  w*=0,70   ROI  +8,5%
    team_corners|ponizej n=331 w*=0,00   ROI -12,2%
Nasza liczba wnosi coś w trzech wąskich miejscach, a w największym wolumenie
tylko psuje cenę. Dlatego pomiar leci w każdym cyklu — zanim cokolwiek
wepniemy w publikację.
"""

import math

from footstats.jobs import rozliczanie as R


def _typ(p_model: float, kurs: float, wygrany: bool, i: int,
         rynek="shots", strona="powyzej") -> dict:
    return {
        "mecz": "Lech – Legia", "mecz_id": 1, "podmiot": "X", "podmiot_id": 1,
        "rynek_kod": rynek, "rynek": rynek, "linia": 1.5, "strona": strona,
        "kurs": kurs, "p_model": p_model,
        "wynik": "wygrany" if wygrany else "przegrany",
        "kickoff_ts": 1785000000 + i,
    }


def test_mieszanie_to_zwykla_interpolacja_w_logicie():
    assert R._wymieszaj(0.8, 0.5, 1.0) == 0.8       # w=1 -> tylko model
    assert R._wymieszaj(0.8, 0.5, 0.0) == 0.5       # w=0 -> tylko cena
    srodek = R._wymieszaj(0.8, 0.5, 0.5)
    assert 0.5 < srodek < 0.8


def test_model_ktory_wie_lepiej_dostaje_wage_jeden():
    """Model mówi 80% i trafia 80%, cena implikuje ~59% — nasza liczba wygrywa."""
    log = {f"a{i}": _typ(0.8, 1.7, i % 5 != 0, i) for i in range(50)}
    w = R.waga_rynku_pomiar(log)["shots|powyzej"]
    assert w["w"] >= 0.9
    assert w["brier_model"] < w["brier_kurs"]


def test_model_ktory_przeszacowuje_dostaje_wage_zero():
    """Model mówi 80%, wchodzi 55%, a cena implikuje ~59% — cena wie lepiej."""
    log = {f"a{i}": _typ(0.8, 1.7, i % 20 < 11, i) for i in range(60)}
    w = R.waga_rynku_pomiar(log)["shots|powyzej"]
    assert w["w"] <= 0.2
    assert w["brier_kurs"] < w["brier_model"]


def test_za_mala_proba_nie_dostaje_werdyktu():
    log = {f"a{i}": _typ(0.8, 1.7, True, i) for i in range(R.WAGA_MIN_N - 1)}
    assert R.waga_rynku_pomiar(log) == {}


def test_typy_pomiarowe_wchodza_do_proby():
    """Bez nich mierzylibyśmy wyłącznie to, co sami wybraliśmy — czyli czub
    własnego rozkładu. To jest ten błąd selekcji, który zawyża deklarację."""
    log = {f"a{i}": {**_typ(0.8, 1.7, i % 5 != 0, i), "odrzucony": True}
           for i in range(50)}
    assert "shots|powyzej" in R.waga_rynku_pomiar(log)


def test_mundial_nie_wchodzi_do_pomiaru():
    log = {f"m{i}": {**_typ(0.8, 1.7, False, i), "mecz": "Hiszpania – Francja"}
           for i in range(50)}
    assert R.waga_rynku_pomiar(log) == {}


def test_kazda_strona_liczy_sie_osobno():
    """Sedno pierwszego pomiaru: `team_corners` powyżej ma w=0,70, a poniżej
    w=0,00 — jeden rynek, dwa różne produkty."""
    log = {}
    for i in range(40):
        log[f"g{i}"] = _typ(0.8, 1.7, i % 5 != 0, i,
                            rynek="team_corners", strona="powyzej")
    for i in range(40):
        log[f"d{i}"] = _typ(0.8, 1.7, i % 20 < 11, 100 + i,
                            rynek="team_corners", strona="ponizej")
    w = R.waga_rynku_pomiar(log)
    assert w["team_corners|powyzej"]["w"] > w["team_corners|ponizej"]["w"]
