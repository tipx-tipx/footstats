# -*- coding: utf-8 -*-
"""Suma meczowa przechodzi przez te same warstwy uczenia co rynki drużynowe.

Znalezione 12.08 przy wpinaniu stempli: `match_*` liczyło `p` z SUROWYCH
rozkładów obu drużyn i szło prosto do `p_model`, omijając kalibrację rynku
i korektę strumienia. `match_corners` ma przy tym własną kalibrację ze
wszystkich czterech przedziałów — i nigdy jej nie używał.

Zmierzone na 95 rozliczeniach (skala `p_over`):
    dziś                 Brier 0,1718   luka -7,9 pp
    + korekta strumienia Brier 0,1617   luka +1,2 pp

Te testy pilnują dwóch rzeczy, które przy tej zmianie najłatwiej złamać:
komplementarności stron i tego, że „kto więcej" ZOSTAJE bez korekty.
"""
import math

from footstats.engine import apply_bias
from footstats.model import betting


def _dodaj_delte(v, d):
    """Kopia wzoru z `build_wc_fast._main_impl` — patrz test niżej."""
    if not d:
        return v
    if isinstance(v, dict) and v.get("logit"):
        biny = [[lo, hi, round(float(b) + betting.delta_dla_p(d, (lo + hi) / 2.0), 3)]
                for lo, hi, b in (v.get("bins") or [])]
        return {**v, "bins": biny,
                "global": round(float(v.get("global", 0.0))
                                + betting.delta_globalna(d), 3)}
    return v


BIAS = {"logit": True, "global": 0.2,
        "bins": [[0.0, 0.55, 0.5], [0.55, 0.7, 0.1],
                 [0.7, 0.85, -0.2], [0.85, 1.01, -0.1]]}
KOREKTA = {"logit": True, "global": -0.44,
           "bins": [[0.0, 0.55, -0.53], [0.55, 0.7, -0.8],
                    [0.7, 0.85, -0.58], [0.85, 1.01, -0.44]]}


def test_strony_sumy_sumuja_sie_do_jedynki():
    """⚑ Korekta leci na `p_over`, więc „poniżej" zostaje dopełnieniem.

    Gdyby nakładać ją na wybraną stronę, obie strony tej samej linii dostałyby
    liczby, które nie sumują się do jedynki — to jest ta sama rodzina błędu co
    awaria odwróconego znaku z 11.08.
    """
    pelny = _dodaj_delte(BIAS, KOREKTA)
    for p_sur in (0.12, 0.35, 0.5, 0.68, 0.83, 0.95):
        p_over = apply_bias(pelny, p_sur)
        p_under = 1.0 - p_over
        assert abs(p_over + p_under - 1.0) < 1e-9


def test_stempel_sumy_odtwarza_rachunek():
    """Z zapisanego rachunku ma się dać wrócić do surowego `p_over`."""
    p_sur = 0.62
    kal_rynek = betting.delta_dla_p(BIAS, p_sur)
    kal_strum = betting.delta_dla_p(KOREKTA, p_sur)
    p_final = apply_bias(_dodaj_delte(BIAS, KOREKTA), p_sur)
    s = betting.stempel_rachunku(
        p_over_raw=p_sur, kal_rynek=kal_rynek, kal_strumien=kal_strum,
        p_over_final=p_final,
    )
    assert betting.stempel_kompletny(s)

    def lg(p):
        return math.log(p / (1 - p))

    odtworzone = 1.0 / (1.0 + math.exp(
        -(lg(s["p_over_final"]) - s["kal_rynek"] - s["kal_strumien"])))
    assert abs(odtworzone - p_sur) < 2e-3


def test_korekta_realnie_rusza_liczbe():
    """Test bez tego asertu przechodziłby też dla korekty równej zeru."""
    p_sur = 0.62
    assert abs(apply_bias(_dodaj_delte(BIAS, KOREKTA), p_sur) - p_sur) > 0.05


def test_kto_wiecej_nie_dostaje_delty():
    """„Kto więcej" to TRÓJMIAN — delta na jedną nogę rozerwałaby sumę do 1.

    Rynki `wiecej_*` celowo nie mają wpisu w mapie kalibracji. Ten test
    pilnuje, żeby nikt ich tam nie dopisał bez policzenia korekty dla trzech
    wyników naraz.
    """
    import json
    from pathlib import Path

    plik = (Path(__file__).resolve().parent.parent
            / "footstats" / "kalibracja_zamrozona.json")
    mapa = json.loads(plik.read_text(encoding="utf-8"))["bias"]
    trojmiany = [k for k in mapa if k.startswith("wiecej_")]
    assert not trojmiany, (
        f"rynki trójmianowe w mapie kalibracji: {trojmiany} — delta logitowa "
        "na p_over nie jest dla nich zdefiniowana"
    )
