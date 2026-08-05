# -*- coding: utf-8 -*-
"""Dwa czujniki dołożone 05.08 — oba tylko mierzą, żaden nie zmienia rachunku.

1. PRZEDZIAŁ BEZ PRÓBY MA SIĘ PRZYZNAĆ. Korekta dzieli się na cztery przedziały
   szansy, ale przedział bez własnych rozliczeń dostaje wartość globalną rynku.
   Do 05.08 nic tego nie odróżniało: raport pokazywał cztery liczby w rzędzie
   i czytało się to jak cztery pomiary. Zmierzone tego dnia — na 12 rynków
   tylko trzy miały jakikolwiek przedział policzony z własnych danych.

2. POGORSZENIE MA KRZYCZEĆ. Kierunek trendu był liczony i pokazywany na
   stronie, ale cykl o nim milczał — spadek dało się zobaczyć wyłącznie wtedy,
   gdy ktoś sam wszedł w zakładkę „Czy się uczymy".
"""
import time

import pytest

from footstats.jobs import rozliczanie as R


def _typ(i: int, p: float, wynik: str, rynek: str = "team_goals") -> dict:
    return {
        "wynik": wynik,
        "p_model": p,
        "p_over": p,
        "kurs": 1.8,
        "kickoff_ts": int(time.time()) - 3600 * (i + 1),
        "rynek_kod": rynek,
        "ekran": "druzyny",
        "wersje": {},
    }


def _log(wpisy: list[dict]) -> dict:
    return {str(i): {**w, "id": i} for i, w in enumerate(wpisy)}


# --- 1. skąd wzięła się liczba w przedziale ---

def test_przedzial_bez_proby_przyznaje_sie_do_globalnej():
    """Sedno czujnika: wszystkie typy w jednym przedziale, reszta pusta."""
    log = _log([
        _typ(i, 0.75, "wygrany" if i % 3 else "przegrany")
        for i in range(R.MIN_N_KALIBRACJI + R.MIN_N_PRZEDZIAL + 10)
    ])
    wpis = R.compute_bias_full(log)["team_goals"]
    zrodla = wpis["zrodla"]
    assert len(zrodla) == len(wpis["bins"]), "etykieta na KAŻDY przedział"
    # 0,75 wpada w przedział (0.70, 0.85) — tylko on ma z czego się policzyć
    assert zrodla == [R.ZRODLO_GLOBALNA, R.ZRODLO_GLOBALNA,
                      R.ZRODLO_WLASNA, R.ZRODLO_GLOBALNA]


def test_dolewka_z_poprzedniej_epoki_nie_udaje_pomiaru():
    """Połowa korekty z martwej epoki to przyznanie się do niewiedzy."""
    stare = [
        {**_typ(i, 0.75, "wygrany" if i % 3 else "przegrany"), "epoka": "ms"}
        for i in range(R.MIN_N_KALIBRACJI + R.MIN_N_PRZEDZIAL + 10)
    ]
    wpis = R.compute_bias_full(_log(stare)).get("team_goals")
    assert wpis, "rynek bez własnych danych ma dostać dolewkę"
    assert set(wpis["zrodla"]) == {R.ZRODLO_OBCA_EPOKA}


def test_licznik_pokrycia_rozdziela_pomiar_od_przyblizenia():
    pokrycie = R.pokrycie_przedzialow({
        "team_goals": {"bins": [[0, 1, 0.1]] * 4,
                       "zrodla": [R.ZRODLO_WLASNA, R.ZRODLO_GLOBALNA,
                                  R.ZRODLO_GLOBALNA, R.ZRODLO_GLOBALNA]},
        "shots": {"bins": [[0, 1, 0.1]] * 4,
                  "zrodla": [R.ZRODLO_OBCA_EPOKA] * 4},
    })
    assert pokrycie["razem"] == 8
    assert pokrycie[R.ZRODLO_WLASNA] == 1
    assert pokrycie[R.ZRODLO_GLOBALNA] == 3
    assert pokrycie[R.ZRODLO_OBCA_EPOKA] == 4


def test_stara_korekta_bez_etykiet_nie_wlicza_sie_do_wlasnych():
    """Wpis sprzed 05.08 nie ma `zrodla` — nie wolno go zgadywać na korzyść."""
    pokrycie = R.pokrycie_przedzialow({"team_goals": {"bins": [[0, 1, 0.1]] * 4}})
    assert pokrycie["bez_etykiet"] == 4 and pokrycie[R.ZRODLO_WLASNA] == 0


@pytest.mark.parametrize("mapy", [(), (None,), ({},), ({"x": 0.3},)])
def test_licznik_znosi_skalary_i_pustki(mapy):
    """Korekta bywa jedną liczbą — nie ma przedziałów, więc nic nie wnosi."""
    assert R.pokrycie_przedzialow(*mapy)["razem"] == 0


def test_zdanie_pokrycia_mowi_ile_to_pomiar():
    zdanie = R.zdanie_pokrycia(R.pokrycie_przedzialow({
        "team_goals": {"bins": [[0, 1, 0.1]] * 4,
                       "zrodla": [R.ZRODLO_WLASNA] + [R.ZRODLO_GLOBALNA] * 3},
    }))
    assert "1 z 4 na własnych danych" in zdanie
    assert "3 × wartość globalna rynku" in zdanie


def test_zdanie_pokrycia_bez_przedzialow_nie_klamie():
    assert "żaden rynek" in R.zdanie_pokrycia(R.pokrycie_przedzialow({}))


def test_korekta_strumienia_niesie_etykiety():
    """Druga warstwa uczenia ma ten sam czujnik co kalibracja rynkowa."""
    log = _log([
        _typ(i, 0.75, "wygrany" if i % 3 else "przegrany")
        for i in range(R.KOREKTA_STRUMIENIA_MIN_N + R.KOREKTA_PRZEDZIAL_MIN_N + 10)
    ])
    wpis = R.korekta_strumienia(log).get("druzyny")
    assert isinstance(wpis, dict) and wpis.get("bins"), "korekta ma być binowana"
    assert len(wpis["zrodla"]) == len(wpis["bins"])
    # wszystkie typy siedzą w przedziale (0.70, 0.85) — tylko on jest pomiarem
    assert wpis["zrodla"] == [R.ZRODLO_GLOBALNA, R.ZRODLO_GLOBALNA,
                              R.ZRODLO_WLASNA, R.ZRODLO_GLOBALNA]


# --- 2. alarm przy pogorszeniu trendu ---

def _paczki(luki: list[float], n: int = 40, szum: float = 0.0) -> dict:
    """Raport uczenia z zadanych luk — po jednej paczce na wartość.

    Ostatnie trzy to „teraz", trzy przed nimi to „poprzednio", pierwsze trzy
    to „start". Przy sześciu wartościach start i poprzednio to ten sam odcinek.
    """
    l_start = sum(luki[:3]) / 3
    l_teraz = sum(luki[-3:]) / 3
    l_poprz = sum(luki[-6:-3]) / 3
    return {"druzyny": {"paczki": [], "trend": {
        "luka_start": l_start,
        "luka_poprzednio": l_poprz,
        "luka_teraz": l_teraz,
        "zmiana": l_teraz - l_start,
        "zmiana_ostatnio": l_teraz - l_poprz,
        "szum": szum,
        "paczek": len(luki),
        "n_teraz": n * 3,
        "n_start": n * 3,
    }}}


def test_pogorszenie_ponad_prog_krzyczy():
    zdania = R.ostrzezenia_trendu(_paczki([-0.05] * 3 + [-0.12] * 3))
    assert len(zdania) == 1
    assert "7.0 pp" in zdania[0] and "druzyny" in zdania[0]


def test_poprawa_milczy():
    assert R.ostrzezenia_trendu(_paczki([-0.12] * 3 + [-0.05] * 3)) == []


def test_drobny_ruch_milczy():
    """Model ma prawo drgnąć — alarm przy każdym pół punktu byłby szumem."""
    assert R.ostrzezenia_trendu(_paczki([-0.05] * 3 + [-0.07] * 3)) == []


def test_mala_proba_milczy():
    """Sto rozliczeń to minimum — na trzydziestu luka skacze o 30 pp sama."""
    assert R.ostrzezenia_trendu(_paczki([-0.05] * 3 + [-0.20] * 3, n=10)) == []


def test_spadek_w_granicach_szumu_milczy():
    """Strumień, który sam z siebie skacze o 15 pp, nie alarmuje przy 7 pp."""
    assert R.ostrzezenia_trendu(
        _paczki([-0.05] * 3 + [-0.12] * 3, szum=0.15)) == []


def test_spadek_ponad_szum_krzyczy_i_podaje_szum():
    zdania = R.ostrzezenia_trendu(_paczki([-0.05] * 3 + [-0.25] * 3, szum=0.08))
    assert len(zdania) == 1
    assert "20.0 pp" in zdania[0] and "przy szumie 8.0 pp" in zdania[0]


def test_raport_liczy_szum_z_rozrzutu_paczek():
    """Spokojna historia ma mały szum, roztrzęsiona duży — to ma być mierzone."""
    spokojna = R.raport_uczenia(_log([
        _typ(i, 0.7, "wygrany" if i % 2 else "przegrany")
        for i in range(R.PACZKA_UCZENIA * 2 * R.TREND_PACZEK)
    ]))["druzyny"]["trend"]
    assert spokojna["szum"] < 0.05, "równy strumień nie ma prawa mieć dużego szumu"


def test_stare_pogorszenie_przestaje_krzyczec():
    """SEDNO: alarm ma mówić „psuje się TERAZ", nie „jest gorzej niż w lipcu".

    Model spadł dawno temu i od tamtej pory stoi w miejscu. Gdyby alarm
    mierzył do początku historii, świeciłby codziennie już na zawsze —
    a alarm, który świeci zawsze, przestaje być czytany.
    """
    uczenie = _paczki([-0.05] * 3 + [-0.20] * 3 + [-0.20] * 3)
    assert uczenie["druzyny"]["trend"]["zmiana"] <= -0.10, "spadek widoczny od startu"
    assert R.ostrzezenia_trendu(uczenie) == []


def test_brak_trendu_nie_wywala():
    assert R.ostrzezenia_trendu({"druzyny": {"paczki": []}}) == []


def test_raport_uczenia_niesie_probe_i_okno_trendu():
    """Alarm czyta `n_teraz` i `zmiana_ostatnio` — bez nich milczałby zawsze."""
    log = _log([
        _typ(i, 0.7, "wygrany" if i % 2 else "przegrany")
        for i in range(R.PACZKA_UCZENIA * 2 * R.TREND_PACZEK)
    ])
    trend = R.raport_uczenia(log)["druzyny"]["trend"]
    assert trend["n_teraz"] == R.PACZKA_UCZENIA * R.TREND_PACZEK
    assert "zmiana_ostatnio" in trend and "luka_poprzednio" in trend
