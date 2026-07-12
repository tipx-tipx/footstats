"""Testy wpięcia WARTOŚCI do selekcji kuponów (2026-07-12):
_leg_value, premia wartości w funkcji celu, profile w _zloz_pewniaki."""

from footstats.jobs import rozliczanie
from footstats.model import kupony


def _leg(mecz_id, pid, p, kurs, ev_uk=None, ev_pct=None, matchup=False, miekka=False):
    return {
        "mecz_id": mecz_id, "podmiot_id": pid, "podmiot": f"P{pid}",
        "druzyna": f"D{mecz_id}", "rynek_kod": "shots", "rynek": "Strzaly",
        "linia": 0.5, "strona": "powyzej", "kurs": kurs, "p_model": p,
        "kickoff_ts": 1000, "mecz": "A vs B", "pewnosc": "wysoka",
        "ev_uk": ev_uk, "ev_pct": ev_pct, "matchup": matchup, "miekka_linia": miekka,
    }


def test_leg_value_priorytet_ev_uk():
    assert kupony._leg_value({"ev_uk": 12.0, "ev_pct": 3.0}) == 12.0  # no-vig wygrywa
    assert kupony._leg_value({"ev_pct": 8.0}) == 8.0                  # fallback na EV
    assert kupony._leg_value({"ev_uk": None, "ev_pct": None}) == 0.0
    assert kupony._leg_value({"ev_uk": -5.0}) == 0.0                  # ujemne -> 0
    assert kupony._leg_value({"ev_uk": 99.0}) == 30.0                 # widelki 0-30


def test_score_selekcji_premiuje_wartosc():
    legi_bez = [_leg(1, 1, 0.7, 1.5), _leg(2, 2, 0.7, 1.5)]
    legi_val = [_leg(1, 1, 0.7, 1.5, ev_uk=20), _leg(2, 2, 0.7, 1.5, ev_uk=20)]
    # ta sama szansa bazowa, ale kupon wartosciowy ma wyzszy score przy wadze>0
    assert (
        kupony._score_selekcji(0.49, legi_val, waga_value=0.30)
        > kupony._score_selekcji(0.49, legi_bez, waga_value=0.30)
    )
    # bezpieczny (waga 0) — wartosc bez wplywu
    assert (
        kupony._score_selekcji(0.49, legi_val, 0.0)
        == kupony._score_selekcji(0.49, legi_bez, 0.0)
    )


def test_zloz_pewniaki_wszystkie_profile_skladaja():
    pool = [_leg(m, m, 0.70, 1.60, ev_uk=m * 3) for m in range(1, 7)]
    for profil in ("bezpieczny", "zbalansowany", "agresywny"):
        k = kupony._zloz_pewniaki(pool, 4.0, 10.0, profil=profil, min_legi=3)
        assert k is not None, profil
        assert k["kurs_laczny"] >= 4.0 and len(k["legi"]) >= 3
        # legi w kuponie nosza teraz swoja wartosc (do UI / scoringu)
        assert all("ev_uk" in l for l in k["legi"])


def test_agresywny_ciagnie_ku_wartosci():
    # przedzial osiagalny na dwa sposoby: 4 faworyci albo 3 value legi.
    # agresywny (premia value) powinien zebrac wyzsza laczna wartosc niz bezpieczny.
    pool = [
        _leg(1, 1, 0.80, 1.20), _leg(2, 2, 0.80, 1.20),
        _leg(3, 3, 0.80, 1.20), _leg(4, 4, 0.80, 1.20),
        _leg(5, 5, 0.62, 1.75, ev_uk=22), _leg(6, 6, 0.60, 1.80, ev_uk=25),
        _leg(7, 7, 0.63, 1.72, ev_uk=20),
    ]
    k_agr = kupony._zloz_pewniaki(pool, 5.0, 8.0, profil="agresywny", min_legi=3)
    k_bezp = kupony._zloz_pewniaki(pool, 5.0, 8.0, profil="bezpieczny", min_legi=3)
    assert k_agr is not None and k_bezp is not None
    ev_agr = sum(kupony._leg_value(l) for l in k_agr["legi"])
    ev_bezp = sum(kupony._leg_value(l) for l in k_bezp["legi"])
    assert ev_agr >= ev_bezp


# --- uczenie kuponów: kalibracja + zmierzona korelacja legów -----------------

def test_kupony_diagnostyka_kalibracja_i_korelacja():
    log = {
        "k1": {
            "horyzont": "dzienny", "p_model": 0.5, "wynik": "wygrany", "pominiety": False,
            "legi": [
                {"mecz_id": 1, "druzyna": "A", "p_model": 0.7, "wynik": "wygrany"},
                {"mecz_id": 1, "druzyna": "A", "p_model": 0.7, "wynik": "wygrany"},
            ],
        },
        "k2": {
            "horyzont": "dzienny", "p_model": 0.5, "wynik": "przegrany", "pominiety": False,
            "legi": [
                {"mecz_id": 2, "druzyna": "B", "p_model": 0.6, "wynik": "przegrany"},
                {"mecz_id": 2, "druzyna": "C", "p_model": 0.6, "wynik": "wygrany"},
            ],
        },
    }
    d = rozliczanie.compute_kupony_diagnostyka(log)
    kd = d["kalibracja"]["dzienny"]
    assert kd["n"] == 2 and kd["hit"] == 0.5 and kd["sr_p"] == 0.5
    ts = d["korelacja"]["ta_sama"]
    assert ts["n_par"] == 1 and ts["obs_oba"] == 1.0
    assert abs(ts["exp_indep"] - 0.49) < 0.01     # 0.7 * 0.7
    assert d["korelacja"]["przeciwne"]["n_par"] == 1
    assert d["korelacja"]["przeciwne"]["obs_oba"] == 0.0


def test_kupony_diagnostyka_pomija_pominiete():
    log = {"k": {"horyzont": "value", "p_model": 0.3, "wynik": "wygrany",
                 "pominiety": True, "legi": []}}
    d = rozliczanie.compute_kupony_diagnostyka(log)
    assert d["kalibracja"] == {} and d["korelacja"] == {}


def test_kary_z_diagnostyki_shrinkage():
    # duża próba + wsp < domyślna -> kara zmierzona (niższa niż 0.92)
    k = kupony.kary_korelacji_z_diagnostyki({"ta_sama": {"wsp": 0.58, "n_par": 120}})
    assert 0.58 <= k["ta_sama"] < kupony.KARA_TA_SAMA_DRUZYNA
    # mała próba -> blisko domyślnej (shrinkage chroni przed szumem)
    k2 = kupony.kary_korelacji_z_diagnostyki({"ta_sama": {"wsp": 0.58, "n_par": 3}})
    assert k2["ta_sama"] > k["ta_sama"]
    # brak danych -> domyślne
    assert kupony.kary_korelacji_z_diagnostyki({}) == kupony.KARY_DEFAULT
    # cap dolny — skrajny wsp nie zjedzie poniżej KARA_MIN
    k3 = kupony.kary_korelacji_z_diagnostyki({"ta_sama": {"wsp": 0.01, "n_par": 999}})
    assert k3["ta_sama"] >= kupony.KARA_MIN


def test_kara_koszyka_uzywa_zmierzonych():
    legi = [{"mecz_id": 1, "druzyna": "A"}, {"mecz_id": 1, "druzyna": "A"}]
    assert kupony._kara_koszyka(legi) == kupony.KARA_TA_SAMA_DRUZYNA   # domyślnie 0.92
    zmierz = kupony._kara_koszyka(
        legi, {"ta_sama": 0.6, "przeciwne": 0.97, "nieznane": 0.95}
    )
    assert abs(zmierz - 0.6) < 1e-9
