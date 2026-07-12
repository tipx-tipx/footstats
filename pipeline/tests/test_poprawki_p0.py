"""Testy poprawek P0 (2026-07-12): łączny cap kontekstu, ryzyko rynków
binarnych (kartki), ujednolicony devig potęgowy w tempie, no-vig UK oraz
pomiar marży UK w diagnostyce."""

from footstats.jobs import rozliczanie
from footstats.model import betting, context, tempo


# --- łączny cap na iloczyn czynników ---------------------------------------

def test_laczny_cap_ucina_ekstremalne_zlozenie():
    # każdy czynnik na skraju swojego capa -> iloczyn ~2.4x, ma być ograniczony
    cf = context.ContextFactors(
        opponent=1.30, referee=1.35, home_away=1.0, game_script=1.20, matchup=1.15
    )
    assert cf.combined <= context.CAP_COMBINED[1] + 1e-9
    cf_low = context.ContextFactors(
        opponent=0.78, referee=0.75, home_away=1.0, game_script=0.85, matchup=0.90
    )
    assert cf_low.combined >= context.CAP_COMBINED[0] - 1e-9


def test_laczny_cap_nie_rusza_realnego_typu_matchup():
    # realny typ z produkcji (Tchouameni tackles, iloczyn ~1.31) — nietknięty
    cf = context.ContextFactors(
        opponent=1.164, referee=1.0, home_away=1.0, game_script=0.984, matchup=1.147
    )
    raw = 1.164 * 1.0 * 1.0 * 0.984 * 1.147
    assert abs(cf.combined - raw) < 1e-9
    assert cf.combined < context.CAP_COMBINED[1]


def test_laczny_cap_neutralny_zostaje_jeden():
    assert abs(context.ContextFactors().combined - 1.0) < 1e-9


# --- ryzyko rynków binarnych (kartki) --------------------------------------

def test_ryzyko_binarne_skala_zdecydowania():
    # p bliskie 50/50 = loteria = wysokie; zdarzenie zdecydowane = niższe ryzyko
    assert betting.risk_level(0.50, False, 0.9, is_prob_market=True) == "wysokie"
    assert betting.risk_level(0.70, False, 0.9, is_prob_market=True) == "srednie"
    assert betting.risk_level(0.92, False, 0.9, is_prob_market=True) == "niskie"
    # niepewne minuty degradują niezależnie od zdecydowania zdarzenia
    assert betting.risk_level(0.92, False, 0.3, is_prob_market=True) == "wysokie"


def test_ryzyko_licznikowe_bez_regresji():
    # domyślna ścieżka (liczniki) niezmieniona
    assert betting.risk_level(0.4, False, 0.9) == "wysokie"   # lam < 0.6
    assert betting.risk_level(1.0, False, 0.9) == "srednie"   # lam < 1.2
    assert betting.risk_level(2.0, False, 0.9) == "niskie"
    assert betting.risk_level(2.0, True, 0.9) == "wysokie"    # rynek rzadki


# --- devig potęgowy w tempie ------------------------------------------------

def test_devig_potegowy_sumuje_i_symetryczny():
    p = tempo._devig([2.0, 2.0])
    assert abs(sum(p) - 1.0) < 1e-6
    assert abs(p[0] - p[1]) < 1e-9            # symetryczne kursy -> dokładnie 50/50
    p3 = tempo._devig([1.5, 4.0, 7.0])
    assert abs(sum(p3) - 1.0) < 1e-6
    assert p3[0] > p3[1] > p3[2]              # faworyt najwyżej


def test_devig_bez_marzy_bierze_wprost():
    # kursy arbitrażowe (Σ 1/o < 1) — nie skalujemy w górę
    p = tempo._devig([3.0, 3.0, 3.0])
    assert all(abs(x - 1.0 / 3.0) < 1e-9 for x in p)


def test_tempo_z_kursow_dziala_po_zmianie_devig():
    m = {"h": 1.8, "x": 3.6, "a": 4.5,
         "totals": {2.5: {"over": 1.9, "under": 1.9}}}
    out = tempo.tempo_from_match_odds(m)
    assert out is not None
    assert out["total"] > 0
    assert out["p_home"] + out["p_away"] < 1.0   # bez remisu suma < 1
    assert out["spread"] > 0                      # faworyt-gospodarz -> spread H-A > 0


# --- no-vig z konsensusu UK (łapanie okazji) --------------------------------

def test_no_vig_uk_zdejmuje_marze():
    res = betting.no_vig_prob_uk([1.40, 1.42, 1.38])   # mediana 1.40
    assert res is not None
    p, fair = res
    assert p < 1.0 / 1.40        # marża zdjęta -> uczciwe p niższe niż surowe
    assert fair > 1.40           # uczciwy kurs wyższy niż mediana z marżą
    assert abs(p - (1.0 / 1.40) * (1.0 - betting.UK_CONSENSUS_MARGIN)) < 1e-6


def test_no_vig_uk_odrzuca_smieci():
    assert betting.no_vig_prob_uk([]) is None
    assert betting.no_vig_prob_uk([0.9, 1.0]) is None   # kursy <= 1 odrzucone


def test_no_vig_uk_rozroznia_miekka_od_twardej_linii():
    p, _ = betting.no_vig_prob_uk([1.40])
    # Superbet płaci 1.65 przy uczciwym ~1.47 -> realna wartość (miękka linia)
    assert (p * 1.65 - 1.0) * 100.0 > 4.0
    # Superbet równy medianie UK (1.40) -> wartość ujemna (marża zjada edge)
    assert (p * 1.40 - 1.0) * 100.0 < 0.0


# --- pomiar marży UK w diagnostyce (grunt pod kalibrację stałej) -------------

def test_diagnostyka_mierzy_marze_uk():
    log = {
        "a": {"p_model": 0.70, "wynik": "wygrany", "strona": "powyzej",
              "kurs_ref": 1.40, "sugestia": False},
        "b": {"p_model": 0.60, "wynik": "przegrany", "strona": "powyzej",
              "kurs_ref": 1.60, "sugestia": False},
    }
    d = rozliczanie.compute_diagnostyka(log)
    assert "marza_uk" in d
    mu = d["marza_uk"]
    assert mu["n"] == 2
    assert mu["hit"] == 0.5                        # 1 z 2 trafionych
    assert abs(mu["implied_sr"] - 0.670) < 0.005   # (1/1.40 + 1/1.60)/2
    assert abs(mu["marza_est"] - 0.254) < 0.01     # 1 - 0.5/0.670
    assert mu["marza_uzywana"] == betting.UK_CONSENSUS_MARGIN


def test_diagnostyka_bez_ref_odds_nie_ma_marzy():
    log = {"a": {"p_model": 0.7, "wynik": "wygrany", "strona": "powyzej"}}
    d = rozliczanie.compute_diagnostyka(log)
    assert "marza_uk" not in d
