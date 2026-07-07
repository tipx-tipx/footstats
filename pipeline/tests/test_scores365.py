"""Testy klasyfikacji strzałów 365Scores (bez sieci)."""

from footstats.sources import scores365 as s365


def _ev(outcome_id, body="Right Foot", side=90.0, type_=0):
    return {
        "type": type_,
        "bodyPart": body,
        "side": side,
        "outcome": {"id": outcome_id, "name": "?"},
    }


def test_classify_goal_inside_box():
    c = s365.classify_event(_ev(0, side=90.0))
    assert c["shots"] == 1 and c["sot"] == 1
    assert c["outside"] == 0 and c["blocked"] == 0 and c["off_target"] == 0


def test_classify_header_saved():
    c = s365.classify_event(_ev(2, body="Header", side=95.0))
    assert c["headed"] == 1 and c["headed_sot"] == 1 and c["sot"] == 1


def test_classify_blocked_outside_box():
    c = s365.classify_event(_ev(4, side=70.0))
    assert c["blocked"] == 1 and c["outside"] == 1
    assert c["sot"] == 0 and c["sot_outside"] == 0


def test_classify_missed_outside():
    c = s365.classify_event(_ev(1, side=60.0))
    assert c["off_target"] == 1 and c["outside"] == 1 and c["sot"] == 0


def test_classify_skips_non_shot_types():
    assert s365.classify_event(_ev(0, type_=2)) is None


def test_box_threshold_penalty_is_inside():
    # rzut karny (side ~88.5) musi być w polu karnym
    c = s365.classify_event(_ev(0, side=88.5))
    assert c["outside"] == 0


def test_resolve_player_key_exact_and_fuzzy():
    keys = {"nico paz", "mohamed salah"}
    assert s365.resolve_player_key(keys, "Mohamed Salah") == "mohamed salah"
    assert s365.resolve_player_key(keys, "Nicolás Paz") == "nico paz"
    assert s365.resolve_player_key(keys, "Julian Alvarez") is None


def test_poz_z_formacji_mapuje_kubelki():
    def m(nazwa):
        return {"formation": {"name": nazwa}}
    assert s365._poz_z_formacji(m("Goalkeeper")) == "G"
    assert s365._poz_z_formacji(m("Centre Back")) == "D"
    assert s365._poz_z_formacji(m("Left Wing Back")) == "D"   # wahadlowy to obrona
    assert s365._poz_z_formacji(m("Central Midfield")) == "M"
    assert s365._poz_z_formacji(m("Defensive Midfield")) == "M"
    assert s365._poz_z_formacji(m("Right Winger")) == "F"
    assert s365._poz_z_formacji(m("Striker")) == "F"
    assert s365._poz_z_formacji(m("")) == ""
    assert s365._poz_z_formacji({}) == ""
