# -*- coding: utf-8 -*-
"""Przebieg meczu z kursów 1X2 ma zostać przy typie w księdze (2026-10-15).

Model uczony nie wie, kto jest faworytem, a jedyny ślad przebiegu w księdze
(`czynniki.scenariusz_meczu`) jest obcięty do 0,85–1,20 i nie widzi fauli
faworyta. Tempo z kursów 1X2/goli cykl liczy co przebieg — ten stempel
pilnuje, żeby nie ginęło, i żeby dało się z niego potem uczyć (patrz
`rozliczanie._stempel_tempa`). Strony nie zmienia.
"""
from pathlib import Path

import pytest

from footstats.jobs import rozliczanie as R

TEMPO = {"spread": -1.42, "total": 3.05, "p_home": 0.1612, "p_away": 0.6834}


@pytest.fixture(autouse=True)
def _czysto():
    R.ustaw_tempo_cyklu({})
    yield
    R.ustaw_tempo_cyklu({})


def _typ(**kw):
    b = {
        "id": 1, "mecz_id": 100, "mecz": "LASK – Liverpool",
        "kickoff_ts": 1787100000, "podmiot_id": 5, "podmiot": "Liverpool",
        "podmiot_typ": "druzyna", "druzyna": "Liverpool",
        "rynek_kod": "team_fouls", "rynek": "Faule drużyny",
        "linia": 10.5, "strona": "powyzej", "kurs": 2.0,
        "bukmacher": "Superbet", "p_model": 0.61, "pewnosc": "srednia",
    }
    b.update(kw)
    return b


def test_nowy_typ_dostaje_tempo_i_strone_boiska():
    R.ustaw_tempo_cyklu({100: TEMPO})
    log: dict = {}
    R._dopisz_nowe(log, [_typ()])
    rec = next(iter(log.values()))
    assert rec["tempo"]["s"] == -1.42
    assert rec["tempo"]["t"] == 3.05
    assert rec["tempo"]["ph"] == 0.1612 and rec["tempo"]["pa"] == 0.6834
    assert rec["gosp"] is False


def test_zawodnik_strona_boiska_z_druzyny():
    R.ustaw_tempo_cyklu({100: TEMPO})
    log: dict = {}
    R._dopisz_nowe(log, [_typ(podmiot="Christoph Lang", podmiot_typ="zawodnik",
                              druzyna="LASK", rynek_kod="shots", rynek="Strzały",
                              linia=0.5)])
    assert next(iter(log.values()))["gosp"] is True


def test_suma_meczowa_bez_strony_boiska():
    """Suma obu drużyn nie ma „swojej" strony — tempo tak, `gosp` nie."""
    R.ustaw_tempo_cyklu({100: TEMPO})
    log: dict = {}
    R._dopisz_nowe(log, [_typ(podmiot="LASK – Liverpool", druzyna="LASK – Liverpool",
                              rynek_kod="match_fouls", rynek="Faule w meczu")])
    rec = next(iter(log.values()))
    assert "tempo" in rec and "gosp" not in rec


def test_bez_kursow_1x2_cisza():
    """Brak kursów to „nie wiemy" — żadnego pola zastępczego."""
    R.ustaw_tempo_cyklu({100: None, 200: {"spread": None}})
    log: dict = {}
    R._dopisz_nowe(log, [_typ()])
    rec = next(iter(log.values()))
    assert "tempo" not in rec and "gosp" not in rec


def test_czekajacy_typ_dostaje_swieze_tempo():
    """Kursy 1X2 żyją do gwizdka — rekord czekający na wynik się odświeża,
    rozliczony jest zamrożony."""
    log: dict = {}
    R._dopisz_nowe(log, [_typ()])                     # pierwszy cykl: bez kursów
    k = next(iter(log))
    assert "tempo" not in log[k]
    R.ustaw_tempo_cyklu({100: TEMPO})
    R._dopisz_nowe(log, [_typ()])
    assert log[k]["tempo"]["s"] == -1.42
    log[k]["wynik"] = "przegrany"
    R.ustaw_tempo_cyklu({100: {**TEMPO, "spread": -2.0}})
    R._dopisz_nowe(log, [_typ()])
    assert log[k]["tempo"]["s"] == -1.42


def test_cykl_podaje_tempo_ksiedze():
    """Strukturalnie: cykl woła `ustaw_tempo_cyklu` z `tempo_cache`, a karty
    drabinek niosą drużynę (inaczej `gosp` zawodnika drabinki jest pusty)."""
    zrodlo = (Path(__file__).resolve().parent.parent / "footstats" / "jobs"
              / "build_wc_fast.py").read_text(encoding="utf-8")
    assert "rozliczanie.ustaw_tempo_cyklu(_tempo_ksiegi)" in zrodlo
    assert zrodlo.count('"druzyna": w.get("druzyna") or ""') == 3


# --- pomiar w tle: siła z kursu 1X2 a obecna szansa -------------------------

def test_sila_z_kursu_w_skali_rankingu():
    rowne = {"ph": 0.40, "pa": 0.40}                   # E = 0,5 → zero
    assert R.sila_z_kursu(rowne, True) == pytest.approx(0.0)
    faw = {"ph": 0.75, "pa": 0.10}                     # E = 0,825 → +0,67
    s = R.sila_z_kursu(faw, True)
    assert s == pytest.approx(0.6737, abs=1e-3)
    assert R.sila_z_kursu(faw, False) == pytest.approx(-s), "gość widzi to samo z minusem"
    assert R.sila_z_kursu({"ph": 0.97, "pa": 0.01}, True) == 1.0, "obcięte do ±1"
    assert R.sila_z_kursu(faw, None) is None and R.sila_z_kursu(None, True) is None


def _wagi_z_sila(beta_sila=0.4):
    return {"rynki": {"team_shots": {
        "cechy": ["const", "dom", "trend", "brak_rywala", "sila"],
        "beta": [2.5, 0.05, 0.0, 0.0, beta_sila], "r_nb": 16.0}}}


def _rozliczony(wynik, s_elo, tempo, gosp, rynek="team_shots", liga="Liga Mistrzów"):
    return {"wynik": wynik, "rynek_kod": rynek, "linia": 12.5, "strona": "powyzej",
            "liga": liga, "tempo": tempo, "gosp": gosp,
            "p_uczony": {"p": 0.55, "lam": 13.0, "sciag": 0.6, "r_nb": 16.0,
                         "skl": {"x": {"sila": s_elo}}}}


def test_raport_druzyny_biora_sile_z_kursu_zamiast_rankingu():
    """Ranking widział równe siły, kurs – dużego underdoga: druga szansa na
    „powyżej” spada; gdy kurs mówi to samo co ranking – nic się nie zmienia."""
    log = {"a": _rozliczony("przegrany", 0.0, {"ph": 0.75, "pa": 0.10}, False),
           "b": _rozliczony("wygrany", 0.0, {"ph": 0.40, "pa": 0.40}, True, liga="Serie A")}
    out = R.raport_sily_z_kursu(log, _wagi_z_sila())
    p = out["druzyny/puchary"]
    assert p["n"] == 1 and p["z_kursu"] < p["model"]
    assert p["brier_z_kursu"] < p["brier_model"]
    l = out["druzyny/ligi"]
    assert l["z_kursu"] == pytest.approx(l["model"])
    assert out["druzyny/razem"]["n"] == 2


def test_raport_zawodnik_obniza_tylko_slabszego():
    zaw = dict(_rozliczony("przegrany", None, {"ph": 0.75, "pa": 0.10}, False, rynek="sot"),
               linia=0.5)
    zaw["p_uczony"] = {"p": 0.6, "lam": 0.9, "sciag": 1.0, "r_nb": 8.0}
    silny = dict(zaw, gosp=True)
    out = R.raport_sily_z_kursu({"s": zaw}, {})
    assert out["zawodnicy_atak/puchary"]["z_kursu"] < out["zawodnicy_atak/puchary"]["model"]
    out2 = R.raport_sily_z_kursu({"s": silny}, {})
    assert out2["zawodnicy_atak/puchary"]["z_kursu"] == pytest.approx(out2["zawodnicy_atak/puchary"]["model"])


def test_raport_pomija_bez_stempla_i_nierozliczone():
    log = {"a": _rozliczony("przegrany", 0.0, None, False),
           "b": dict(_rozliczony(None, 0.0, {"ph": 0.5, "pa": 0.2}, True), wynik=None),
           "c": _rozliczony("wygrany", None, {"ph": 0.5, "pa": 0.2}, True)}
    assert R.raport_sily_z_kursu(log, _wagi_z_sila()) == {}
