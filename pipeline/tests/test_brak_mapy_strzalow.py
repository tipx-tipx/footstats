"""05.11 (Sedláček): mecz znany ze strzałów, a nieznany rynkowi z mapy
strzałów (FotMob bez mapy) – kratka „?” (minuty −1), nie zero."""
from footstats.jobs import build_wc_fast as B

D = 86_400


def _gracz():
    return {"id": 1, "forma": {
        "shots": {"ts": [50 * D, 40 * D, 30 * D, 20 * D], "minuty": [90, 0, 90, 90],
                  "ostatnie": [0, 0, 1, 2], "rywale": ["Slavia", "Hradec", "Plzen", "Zlin"],
                  "kadra": [False] * 4},
        "shots_outside_box": {"ts": [30 * D, 20 * D], "minuty": [71, 90], "ostatnie": [1, 1],
                              "rywale": ["Plzen", "Zlin"], "kadra": [False, False]},
        "fouls_won": {"ts": [50 * D], "minuty": [90], "ostatnie": [2]},
    }}


def test_brak_mapy_dopisany_jako_brak_danych():
    g = _gracz()
    assert B.oznacz_brak_mapy_strzalow([g]) == 1
    f = g["forma"]["shots_outside_box"]
    assert f["ts"] == [50 * D, 30 * D, 20 * D]          # „nie zagrał” (0 min) nie wchodzi
    assert f["minuty"] == [B.MINUTY_BRAK_DANYCH, 71, 90]
    assert f["ostatnie"] == [0, 1, 1] and f["rywale"][0] == "Slavia"
    # rynki spoza mapy strzałów bez zmian
    assert g["forma"]["fouls_won"]["ts"] == [50 * D]


def test_rynek_bez_historii_i_pelny_bez_zmian():
    g = _gracz()
    del g["forma"]["shots_outside_box"]
    assert B.oznacz_brak_mapy_strzalow([g]) == 0
    g = _gracz()
    g["forma"]["shots_outside_box"].update(ts=[50 * D, 30 * D, 20 * D], minuty=[90, 71, 90],
                                          ostatnie=[0, 1, 1], rywale=["S", "P", "Z"], kadra=[False] * 3)
    assert B.oznacz_brak_mapy_strzalow([g]) == 0
