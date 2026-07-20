"""Brama jakości trybu ligowego: świeżość próby zawodnika.

fit_posterior waży starość z tau=180 dni (skala sezonu), więc historia
sprzed przerwy letniej wciąż waży sporo — świeżości pilnuje osobny próg
w build_wc_fast (swiezosc_proby + stałe OKNO/MIN/STARE_DANE).
"""

import time

from footstats.jobs.build_wc_fast import (
    MIN_MECZE_W_OKNIE,
    OKNO_SWIEZEJ_PROBY_S,
    STARE_DANE_S,
    swiezosc_proby,
)

NOW = int(time.time())
DZIEN = 86400


def _ts(dni_temu: int) -> int:
    return NOW - dni_temu * DZIEN


def test_swieza_historia_liczy_wystapienia_w_oknie():
    ts = [_ts(3), _ts(10), _ts(200)]
    minutes = [90.0, 85.0, 90.0]
    n, dni = swiezosc_proby(ts, minutes, NOW)
    assert n == 2  # mecz sprzed 200 dni poza oknem 120 dni
    assert 2.9 < dni < 3.1


def test_mecze_bez_minut_nie_sa_wystepami():
    # siedział na ławce: świeże wpisy z 0 minut nie ratują świeżości
    ts = [_ts(2), _ts(5), _ts(150)]
    minutes = [0.0, 0.0, 90.0]
    n, dni = swiezosc_proby(ts, minutes, NOW)
    assert n == 0
    assert dni > 149


def test_pusta_historia_daje_zero_i_nieskonczonosc():
    n, dni = swiezosc_proby([], [], NOW)
    assert n == 0
    assert dni == float("inf")
    # same zera minut = jak brak historii
    n2, dni2 = swiezosc_proby([_ts(1)], [0.0], NOW)
    assert (n2, dni2) == (0, float("inf"))


def test_zepsute_timestampy_ignorowane():
    # statshub potrafi dać eventTimestamp=0 — nie może udawać meczu sprzed epoki
    n, dni = swiezosc_proby([0, _ts(4)], [90.0, 88.0], NOW)
    assert n == 1
    assert 3.9 < dni < 4.1


def test_progi_bramy_spojne_z_przerwa_letnia():
    # Przerwa letnia top lig to ~75-85 dni. Zawodnik z regularnymi meczami
    # do końca sezonu NIE wypada z twardej bramy (okno 120 dni je łapie)...
    ts = [_ts(80), _ts(87), _ts(94), _ts(101)]
    minutes = [90.0] * 4
    n, dni = swiezosc_proby(ts, minutes, NOW)
    assert n >= MIN_MECZE_W_OKNIE
    # ...ale jest degradowany do "w tle" (ostatni występ dawniej niż 45 dni)
    assert dni * DZIEN > STARE_DANE_S


def test_martwa_historia_pod_twarda_brame():
    # kontuzja/wypadł z rotacji: wszystko starsze niż okno świeżości
    okno_dni = OKNO_SWIEZEJ_PROBY_S // DZIEN
    ts = [_ts(okno_dni + 10), _ts(okno_dni + 40), _ts(okno_dni + 70)]
    n, _ = swiezosc_proby(ts, [90.0, 90.0, 90.0], NOW)
    assert n < MIN_MECZE_W_OKNIE
