# -*- coding: utf-8 -*-
"""Stempel „na czym stoi ta liczba" — warunek wdrożenia V2 z audytu.

Do 12.08 rachunek typu dawało się odtworzyć WYŁĄCZNIE dla drużyn. Zmierzone
tego dnia na produkcji: `kal_rynek` przy 423 z 684 typów drużynowych, przy
0 z 18 zawodniczych, 0 z 25 sum meczowych i 0 z 7 rynków „kto więcej";
`p_over_raw` nie istniało w ogóle. Skutek był praktyczny, nie kosmetyczny —
rozłożenie strumienia na czynniki (ile dołożyła kalibracja, ile korekta, jaki
był surowy model) było wykonalne dla jednego strumienia z czterech.

Te testy pilnują trzech rzeczy:
  1. stempel odróżnia „nie policzono" od „policzono i wyszło zero",
  2. komplet znaczy tyle samo dla każdej klasy typu,
  3. silnik zawodniczy oddaje surowe `p_over` PRZED kalibracją.
"""
import math

from footstats import engine
from footstats.model import betting


def test_puste_pola_nie_udaja_zera():
    """`None` = „ta ścieżka tego nie liczy". Zero = pomiar."""
    s = betting.stempel_rachunku(p_over_raw=0.62, kal_rynek=None,
                                 kal_strumien=0.0, p_over_final=0.62)
    assert "kal_rynek" not in s, "brak pomiaru nie może udawać zera"
    assert s["kal_strumien"] == 0.0, "zmierzone zero ma zostać zerem"
    assert s["p_over_raw"] == 0.62


def test_komplet_wymaga_calego_rachunku():
    niepelny = betting.stempel_rachunku(p_over_raw=0.62, kal_strumien=-0.4,
                                        p_over_final=0.53)
    assert not betting.stempel_kompletny(niepelny)
    pelny = betting.stempel_rachunku(p_over_raw=0.62, kal_rynek=0.1,
                                     kal_strumien=-0.4, p_over_final=0.55)
    assert betting.stempel_kompletny(pelny)
    assert not betting.stempel_kompletny({})
    assert not betting.stempel_kompletny(None)


def test_stempel_da_sie_odwrocic_do_surowego_p():
    """Sedno: z rachunku ma się dać odtworzyć, co nałożono.

    Bez tego `compute_bias_full` uczy się na `p`, z którego nie potrafi zdjąć
    własnej poprzedniej delty — powód, dla którego mapa jest dziś zamrożona.
    """
    p_raw, kal_r, kal_s = 0.62, 0.25, -0.40

    def lg(p):
        return math.log(p / (1 - p))

    p_final = 1.0 / (1.0 + math.exp(-(lg(p_raw) + kal_r + kal_s)))
    s = betting.stempel_rachunku(p_over_raw=p_raw, kal_rynek=kal_r,
                                 kal_strumien=kal_s, p_over_final=p_final)
    odtworzone = 1.0 / (1.0 + math.exp(
        -(lg(s["p_over_final"]) - s["kal_rynek"] - s["kal_strumien"])))
    assert abs(odtworzone - p_raw) < 1e-3


def test_silnik_zawodniczy_oddaje_surowe_p_over():
    """`p_over` wychodzi z silnika JUŻ skalibrowane — surowe musi jechać obok.

    Bez tego pola nie da się później powiedzieć, ile z liczby pokazanej
    klientowi jest modelem, a ile korektą z rozliczeń.
    """
    assert hasattr(engine.ScoredMarket, "__dataclass_fields__")
    pola = engine.ScoredMarket.__dataclass_fields__
    assert "p_over_raw" in pola
    assert "kal_laczna" in pola, (
        "nazwa musi mówić, że to delta ŁĄCZNA — silnik dostaje sumę "
        "kalibracji rynku i korekty strumienia (`_bias_z_korekta`)"
    )


def test_stempel_zaokragla_do_czterech_miejsc():
    """Księga rośnie o jeden słownik na typ — bez ogonów zmiennoprzecinkowych."""
    s = betting.stempel_rachunku(p_over_raw=0.6234567, kal_rynek=0.1234567,
                                 kal_strumien=-0.4, p_over_final=0.5)
    assert s["p_over_raw"] == 0.6235
    assert s["kal_rynek"] == 0.1235
