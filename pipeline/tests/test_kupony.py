"""Testy generatora kuponów."""

from footstats.model import kupony


def _bet(id_, mecz_id, podmiot_id, kurs, p, ev=5.0, pewnosc="wysoka", rank=1.0):
    return {
        "id": id_, "mecz_id": mecz_id, "podmiot_id": podmiot_id,
        "podmiot": f"P{podmiot_id}", "rynek": "Strzały", "linia": 1.5,
        "strona": "powyzej", "kurs": kurs, "bukmacher": "Superbet",
        "p_model": p, "ev_pct": ev, "pewnosc": pewnosc,
        "rank_score": rank, "mecz": f"M{mecz_id}", "kickoff_ts": 0,
        "sugestia": False,
    }


def test_kupon_x5_from_three_legs():
    bets = [
        _bet(1, 1, 11, 1.8, 0.62, rank=3.0),
        _bet(2, 2, 22, 1.7, 0.65, rank=2.5),
        _bet(3, 3, 33, 1.75, 0.63, rank=2.0),
    ]
    out = kupony.build_kupony(bets)
    x5 = next((k for k in out if k["cel"] == 5), None)
    assert x5 is not None
    assert 4.25 <= x5["kurs_laczny"] <= 8.0
    assert len(x5["legi"]) == 3
    assert abs(x5["p_model"] - 0.62 * 0.65 * 0.63) < 1e-4  # zaokrąglenie do 4 miejsc


def test_max_one_leg_per_match_and_player():
    bets = [
        _bet(1, 1, 11, 2.0, 0.6, rank=3.0),
        _bet(2, 1, 12, 2.0, 0.6, rank=2.9),   # ten sam mecz — odpada
        _bet(3, 2, 11, 2.0, 0.6, rank=2.8),   # ten sam zawodnik — odpada
        _bet(4, 3, 44, 2.0, 0.6, rank=2.0),
        _bet(5, 4, 55, 1.6, 0.68, rank=1.5),
    ]
    out = kupony.build_kupony(bets)
    for k in out:
        mecze = [l["mecz_id"] for l in k["legi"]]
        gracze = [l["podmiot"] for l in k["legi"]]
        assert len(mecze) == len(set(mecze))
        assert len(gracze) == len(set(gracze))


def test_no_coupon_when_not_enough_legs():
    bets = [_bet(1, 1, 11, 1.5, 0.72)]
    assert kupony.build_kupony(bets) == []


def _leg(mecz_id, podmiot_id, kurs, p):
    return {
        "id": 0, "mecz_id": mecz_id, "podmiot_id": podmiot_id,
        "podmiot": f"P{podmiot_id}", "rynek": "Strzały", "linia": 0.5,
        "strona": "powyzej", "kurs": kurs, "bukmacher": "Superbet",
        "p_model": p, "mecz": f"M{mecz_id}", "kickoff_ts": 0,
    }


def test_pewniaki_reach_target_with_max_4_per_match():
    pool = []
    pid = 0
    for mecz in range(1, 4):
        for _ in range(6):
            pid += 1
            pool.append(_leg(mecz, pid, 1.45, 0.72))
    out = kupony.build_kupony([], pool)
    pewniaki = [k for k in out if k["styl"] == "pewniaki"]
    assert pewniaki, "przy 18 legach 1.45 kupon x10 musi się złożyć"
    for k in pewniaki:
        licznik = {}
        for l in k["legi"]:
            licznik[l["mecz_id"]] = licznik.get(l["mecz_id"], 0) + 1
        assert max(licznik.values()) <= 4
        assert k["cel"] * 0.85 <= k["kurs_laczny"] <= k["cel"] * 1.6
        # kara korelacyjna: p kuponu <= iloczyn szans legów
        iloczyn = 1.0
        for l in k["legi"]:
            iloczyn *= l["p_model"]
        assert k["p_model"] <= round(iloczyn, 4) + 1e-9


def test_low_confidence_and_negative_ev_excluded():
    bets = [
        _bet(1, 1, 11, 2.0, 0.6, pewnosc="niska"),
        _bet(2, 2, 22, 2.0, 0.6, ev=-3.0),
        _bet(3, 3, 33, 2.0, 0.6),
    ]
    out = kupony.build_kupony(bets)
    assert out == []  # tylko 1 kwalifikowany leg -> brak kuponu
