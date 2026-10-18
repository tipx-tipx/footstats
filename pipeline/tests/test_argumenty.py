"""Argumenty typu „jak u typera" (model/argumenty.py, 2026-10-18)."""
from footstats.model import argumenty as A

DZIEN = 86400
KO = 1_800_000_000


def _mecz(t, o, l=1, s=None, sp=None, g=1, gp=1, h=1):
    return {"t": t, "o": o, "l": l, "h": h, "g": g, "gp": gp, "s": s or {}, "sp": sp or {}}


def _magazyn(liczba_druzyn=10, oddaje=None, pole="sh"):
    """Liga 1: drużyny 1..N, 10 meczów każda. `oddaje[tid]` = ile rywale
    oddają strzałów przeciw tej drużynie (sp)."""
    oddaje = oddaje or {}
    mag = {}
    for tid in range(1, liczba_druzyn + 1):
        ms = []
        for i in range(10):
            ms.append(_mecz(KO - (i + 1) * 7 * DZIEN, o=100 + i,
                            s={pole: 10}, sp={pole: oddaje.get(tid, 10 + tid * 0.1)}))
        mag[str(tid)] = {"m": ms}
    return mag


def test_ranga_rywala_w_lidze():
    idx = A.Indeks(_magazyn(oddaje={5: 30}))
    assert idx.ranga(5, KO, ("sp", "sh")) == 1.0            # oddaje najwięcej
    assert idx.ranga(1, KO, ("sp", "sh")) == 0.0
    assert idx.ranga(999, KO, ("sp", "sh")) is None          # brak w magazynie
    assert idx.miejsce(5, KO, ("sp", "sh")) == (1, 10)       # „1. na 10"
    assert idx.miejsce(5, KO, ("sp", "sh"), od_najwiekszej=False) == (10, 10)


def test_dane_do_opisu():
    mag = _magazyn(oddaje={5: 30})
    for i in range(3):
        mag["1"]["m"].append(_mecz(KO - (100 + i) * DZIEN, o=5, s={"sh": 15}))
    idx = A.Indeks(mag)
    a = A.argumenty_druzyny(idx, 1, 5, KO, "team_shots", 12.5, "powyzej", pkw=0.9)
    assert a["dane"]["rywal_miejsce"] == [1, 10]
    assert a["dane"]["h2h"] == [3, 3]
    assert a["dane"]["pokrycie"] == 0.9
    c, mi, ts, opp = _hist(c=3.0, opp=5)
    z = A.argumenty_zawodnika(idx, 5, KO, "shots", 1.5, c, mi, ts, opp)
    assert z["dane"]["forma"] == [5, 5] and z["dane"]["pokrycie"] == [10, 10]
    assert z["dane"]["h2h"] == [5, 5] and z["dane"]["na_90"] == 3.0
    import json
    json.dumps(a), json.dumps(z)                              # da się zapisać do księgi


def test_mala_liga_bez_rankingu():
    idx = A.Indeks(_magazyn(liczba_druzyn=5))
    assert idx.ranga(3, KO, ("sp", "sh")) is None


def test_mecze_po_meczu_nie_licza_sie():
    """Stan sprzed meczu — mecz rozegrany po starcie nie wchodzi."""
    mag = _magazyn()
    mag["1"]["m"].append(_mecz(KO + DZIEN, o=2, s={"sh": 99}))
    idx = A.Indeks(mag)
    assert all(m["t"] < KO for m in idx.przed(1, KO))


def test_rywal_top_dla_powyzej_i_odwrotnie_dla_ponizej():
    idx = A.Indeks(_magazyn(oddaje={5: 30}))
    a = A.argumenty_druzyny(idx, 1, 5, KO, "team_shots", 12.5, "powyzej")
    assert "rywal_top" in a["za"]
    b = A.argumenty_druzyny(idx, 1, 5, KO, "team_shots", 12.5, "ponizej")
    assert "rywal_slaby" in b["przeciw"]


def test_h2h_druzyny():
    mag = _magazyn()
    for i in range(3):
        mag["1"]["m"].append(_mecz(KO - (100 + i) * DZIEN, o=2, s={"sh": 15}))
    idx = A.Indeks(mag)
    a = A.argumenty_druzyny(idx, 1, 2, KO, "team_shots", 12.5, "powyzej")
    assert "h2h_wszystkie" in a["za"]
    b = A.argumenty_druzyny(idx, 1, 2, KO, "team_shots", 12.5, "ponizej")
    assert "h2h_nie" in b["przeciw"]


def test_pokrycie_strony_ponizej():
    idx = A.Indeks(_magazyn())
    a = A.argumenty_druzyny(idx, 1, 2, KO, "team_shots", 12.5, "ponizej", pkw=0.1)
    assert "pokrycie" in a["za"]
    b = A.argumenty_druzyny(idx, 1, 2, KO, "team_shots", 12.5, "powyzej", pkw=0.1)
    assert "pokrycie" not in b["za"]


def test_nieznany_rynek_bez_argumentow():
    idx = A.Indeks(_magazyn())
    assert A.argumenty_druzyny(idx, 1, 2, KO, "match_shots", 22.5, "powyzej") is None
    assert A.argumenty_druzyny(idx, 1, 2, KO, "wiecej_shots", 0, "gospodarz") is None


def _hist(n=10, c=2.0, mi=90.0, opp=7):
    ts = [KO - (i + 1) * 7 * DZIEN for i in range(n)]
    return [c] * n, [mi] * n, ts, [opp] * n


def test_zawodnik_forma_pokrycie_na90_h2h():
    idx = A.Indeks(_magazyn(oddaje={7: 30}))
    c, mi, ts, opp = _hist(c=3.0)
    a = A.argumenty_zawodnika(idx, 7, KO, "shots", 1.5, c, mi, ts, opp)
    assert {"rywal_top", "forma", "pokrycie", "na_90", "h2h_wszystkie"} <= set(a["za"])
    assert a["przeciw"] == []
    assert A.czysty_pakiet(a)


def test_zawodnik_slaba_forma_i_rzadko_w_skladzie():
    idx = A.Indeks(_magazyn())
    c, mi, ts, opp = _hist(c=0.0, mi=30.0, opp=8)
    a = A.argumenty_zawodnika(idx, 3, KO, "shots", 0.5, c, mi, ts, opp)
    assert "forma_slaba" in a["przeciw"] and "rzadko_sklad" in a["przeciw"]
    assert not A.czysty_pakiet(a)
    assert A.bilans(a) < 0


def test_zawodnik_krotka_historia():
    idx = A.Indeks(_magazyn())
    c, mi, ts, opp = _hist(n=4)
    assert A.argumenty_zawodnika(idx, 3, KO, "shots", 0.5, c, mi, ts, opp) is None


def test_magazyn_z_polem_technicznym():
    mag = _magazyn()
    mag["_braki"] = {"szardy": [3]}
    assert 1 in A.Indeks(mag).mecze


def test_argumenty_typu_druzyny_i_zawodnika():
    """build_wc_fast.argumenty_typu: rywal z listy meczów cyklu, zawodnik z trendu."""
    import types
    from footstats.jobs import build_wc_fast as B
    idx = A.Indeks(_magazyn(oddaje={5: 30}))
    druz = {"podmiot_typ": "druzyna", "podmiot_id": -1, "mecz_id": 77, "kickoff_ts": KO,
            "rynek_kod": "team_shots", "linia": 12.5, "strona": "powyzej"}
    a = B.argumenty_typu(druz, idx, {77: (1, 5)}, {})
    assert "rywal_top" in a["za"]                    # minus w numerze drużyny nie przeszkadza
    assert B.argumenty_typu(druz, idx, {}, {}) is None     # nie znamy rywala
    c, mi, ts, opp = _hist(c=3.0, opp=5)
    tr = types.SimpleNamespace(counts=c, minutes=mi, timestamps=ts, game_opponent_ids=opp,
                               opponent_id=5)
    zaw = {"podmiot_typ": "zawodnik", "podmiot_id": 9, "mecz_id": 77, "kickoff_ts": KO,
           "rynek_kod": "shots", "linia": 1.5, "strona": "powyzej"}
    a = B.argumenty_typu(zaw, idx, {}, {(77, 9, "shots"): tr})
    assert {"rywal_top", "h2h_wszystkie", "forma"} <= set(a["za"])
    assert B.argumenty_typu(zaw, None, {}, {(77, 9, "shots"): tr}) is None


def test_opisy_dla_wszystkich_kodow():
    kody = {"rywal_top", "rywal_slaby", "h2h_wszystkie", "h2h_wiekszosc", "h2h_nie", "pokrycie",
            "forma", "forma_slaba", "na_90", "rzadko_sklad", "druzyna_top", "slabsza_ponizej"}
    assert kody <= set(A.OPISY)
