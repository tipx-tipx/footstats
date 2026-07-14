"""Testy kalibracji wag zaufania (pomiar w rozliczanie, aplikacja w kupony)."""

from footstats.jobs import rozliczanie
from footstats.model import kupony


def _log_z_kubelka(n: int, p: float, kurs: float, hit_rate: float,
                   kubelek: str = "srednia") -> dict:
    log = {}
    n_hit = round(n * hit_rate)
    for i in range(n):
        log[f"1:gracz {i} {kubelek}:shots:0.5:powyzej"] = {
            "mecz_id": 1, "podmiot": f"Gracz {i}", "rynek_kod": "shots",
            "linia": 0.5, "strona": "powyzej", "kurs": kurs,
            "p_model": p, "pewnosc": kubelek, "sugestia": False,
            "wynik": "wygrany" if i < n_hit else "przegrany",
        }
    return log


def test_pomiar_w_cel_kierunek():
    """Model deklaruje 70%, trafia jak rynek — w_cel ma być blisko zera."""
    # kurs 1.5 -> p_rynku po devigu ~0.62; hit 62% = dokładnie cena rynku
    log = _log_z_kubelka(100, 0.70, 1.5, 0.62)
    pomiar = rozliczanie.compute_wagi_zaufania(log)
    assert pomiar["srednia"]["n"] == 100
    assert pomiar["srednia"]["w_cel"] is not None
    assert abs(pomiar["srednia"]["w_cel"]) < 0.05
    # a gdy trafia dokładnie tyle, ile deklaruje — w_cel ~1 (pełna wiara)
    log2 = _log_z_kubelka(100, 0.70, 1.5, 0.70)
    pomiar2 = rozliczanie.compute_wagi_zaufania(log2)
    assert abs(pomiar2["srednia"]["w_cel"] - 1.0) < 0.05


def test_pomiar_ignoruje_sugestie_odrzucone_i_mala_probe():
    log = _log_z_kubelka(4, 0.7, 1.5, 0.5)          # za mała próba
    for r in _log_z_kubelka(30, 0.7, 1.5, 0.5, "wysoka").values():
        r["sugestia"] = True                          # sugestie poza pomiarem
    pomiar = rozliczanie.compute_wagi_zaufania(log)
    assert pomiar == {}


def test_delty_shrink_i_cap():
    # przeszacowujący kubełek: w_cel 0.1 przy bazie 0.55 -> delta ujemna,
    # shrinkowana n/(n+60) i capowana do -0.25
    pomiar = {"srednia": {"n": 60, "w_cel": 0.10},
              "wysoka": {"n": 6, "w_cel": 0.10}}
    delty = kupony.wagi_zaufania_z_pomiaru(pomiar)
    # n=60: k=0.5, surowa delta -0.45*0.5 = -0.225
    assert abs(delty["srednia"] + 0.225) < 1e-9
    # n=6: k=6/66 ~ 0.09, delta ~ -0.059 (mocny shrink przy małej próbie)
    assert -0.07 < delty["wysoka"] < -0.05
    # cap: ekstremalny pomiar nie przebija ±0.25
    delty2 = kupony.wagi_zaufania_z_pomiaru(
        {"srednia": {"n": 5000, "w_cel": 0.0}}
    )
    assert delty2["srednia"] == -0.25


def test_waga_modelu_stosuje_delte_i_widelki():
    leg = {"pewnosc": "srednia", "p_model": 0.7, "kurs": 1.5}
    bazowa = kupony._waga_modelu(leg)
    assert bazowa == 0.55
    assert kupony._waga_modelu(leg, {"srednia": -0.15}) == 0.40
    # widełki: delta nie zbije wagi poniżej WAGA_EFF_MIN
    assert kupony._waga_modelu(leg, {"srednia": -0.25}) == kupony.WAGA_EFF_MIN
    # leg z ci: delta nakłada się NA wagę z ci
    leg_ci = {**leg, "ci": [0.66, 0.74]}   # szer 0.08 -> w=0.77
    assert abs(kupony._waga_modelu(leg_ci) - 0.77) < 1e-9
    assert abs(kupony._waga_modelu(leg_ci, {"srednia": -0.15}) - 0.62) < 1e-9
    # pusta mapa delt = zachowanie bez kalibracji
    assert kupony._waga_modelu(leg_ci, {}) == kupony._waga_modelu(leg_ci)
