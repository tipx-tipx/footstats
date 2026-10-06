# -*- coding: utf-8 -*-
"""Stary rachunek odcięty od typów modelu uczonego (2026-10-05).

Właściciel: „trzeba wszystko ze starego modelu odciąć, z głową". Pięć dróg,
którymi stary rachunek wpływał na to, co publikuje model uczony — każda ma
tu swojego strażnika (bramy i kwarantanny: test_kwarantanna.py,
test_korekta_strony.py).
"""
import inspect
import math

from footstats.jobs import build_wc_fast as B
from footstats.model import uczony as U


ZRODLO = inspect.getsource(B)


# --- A5: „kto więcej" liczy model uczony ------------------------------------

def test_porownanie_symetryczne_i_sumuje_sie_do_jedynki():
    p_h, p_r, p_a = U.porownanie(6.0, 9.0, 6.0, 9.0)
    assert abs(p_h - p_a) < 1e-3
    assert abs(p_h + p_r + p_a - 1.0) < 1e-3
    assert p_r > 0.05                     # przy λ≈6 remis to realna masa


def test_porownanie_faworyt_i_brak_danych():
    p_h, _, p_a = U.porownanie(14.0, 10.0, 8.0, 10.0)
    assert p_h > 0.75 and p_a < 0.2
    assert U.porownanie(None, 5.0, 8.0, 5.0) is None
    assert U.porownanie(0.0, 5.0, 8.0, 5.0) is None


def test_porownanie_zgodne_z_poissonem_policzonym_wprost():
    lh, la = 3.0, 2.0
    pois = lambda l, k: math.exp(-l) * l ** k / math.factorial(k)
    p_h = sum(pois(lh, i) * pois(la, j) for i in range(40) for j in range(i))
    assert abs(U.porownanie(lh, None, la, None)[0] - p_h) < 1e-3


def test_kto_wiecej_idzie_przez_model_i_stempluje_zrodlo():
    i = ZRODLO.index('kod_w = "wiecej_" + baza_n')
    blok = ZRODLO[i:ZRODLO.index('kod_s = "match_" + baza_n', i)]
    assert "uczony.porownanie(" in blok
    assert "uczony.stempel_zrodla(" in blok
    assert '"stary_bez_pokrycia"' in blok


# --- A4: stary rachunek nie wchodzi na stronę ani do kuponów -----------------

def test_brama_starego_rachunku_na_stronie_i_w_kuponach():
    i = ZRODLO.index("for b in value_bets_pub:")
    petla = ZRODLO[i:ZRODLO.index("do_pokazania.append(", i)]
    assert '"stary_rachunek"' in petla
    assert 'not b.get("wznowiony")' in petla      # pokazany zostaje do gwizdka
    j = ZRODLO.index("def _leg_dopuszczalny(")
    assert "rozliczanie._stary_rachunek(b)" in ZRODLO[j:j + 1200]
    k = ZRODLO.index("kupony_list = kupony.build_kupony(")
    assert "_stary_rachunek" in ZRODLO[k:k + 400]
    assert "stary_rachunek" in B.OPISY_ZDJECIA_PL


# --- A3: szerokość przedziału typu modelu bez starej kalibracji -------------

def test_szerokosc_przedzialu_modelu_z_przedzialu_surowego():
    assert "_pol_t = max((hi_o_sur - lo_o_sur) / 2.0, 0.0)" in ZRODLO
    assert "_pol_s = max((hi_o_s_sur - lo_o_s_sur) / 2.0, 0.0)" in ZRODLO
    # surowy przedział zapamiętany PRZED kalibracją
    i = ZRODLO.index("lo_o_sur, hi_o_sur = lo_o, hi_o")
    assert ZRODLO.index("lo_o = apply_bias(_bias_t_pelny, lo_o)", i) > i


# --- A6: awaria warstwy starego rachunku nie zatrzymuje cyklu ----------------

def test_awaria_warstw_starego_rachunku_nie_przerywa_cyklu():
    assert "cykl przerwany, żeby nie opublikować" not in ZRODLO
    assert "_warstwy_starego_padly" in ZRODLO
    i = ZRODLO.index("radar_wpisy = radar.zbuduj(")
    assert "_warstwy_starego_padly" in ZRODLO[i - 600:i]
