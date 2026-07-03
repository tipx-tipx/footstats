"""Testy kalibracji z rozliczonych typów (bez sieci)."""

from footstats.jobs import rozliczanie


def _rec(mk, p, wynik):
    return {"rynek_kod": mk, "p_model": p, "wynik": wynik}


def test_bias_needs_min_sample():
    log = {str(i): _rec("shots", 0.7, "wygrany") for i in range(10)}
    assert rozliczanie.compute_bias(log, min_n=25) == {}


def test_bias_detects_overconfidence():
    # model mówił 80%, wchodziło 60% -> bias < 1 (przeszacowanie)
    log = {}
    for i in range(30):
        log[str(i)] = _rec("shots", 0.8, "wygrany" if i < 18 else "przegrany")
    bias = rozliczanie.compute_bias(log, min_n=25)["shots"]
    assert bias < 1.0
    assert bias >= rozliczanie.BIAS_CAP[0]


def test_bias_capped_and_ignores_voids():
    log = {}
    for i in range(40):
        log[str(i)] = _rec("fouls_won", 0.5, "wygrany")  # 100% trafień przy p=50%
    log["void"] = _rec("fouls_won", 0.5, "zwrot")  # zwroty nie liczą się do próby
    bias = rozliczanie.compute_bias(log, min_n=25)["fouls_won"]
    assert bias == rozliczanie.BIAS_CAP[1]  # capowane, mimo że surowo ~1.9
