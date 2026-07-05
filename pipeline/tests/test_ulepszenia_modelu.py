"""Testy warstw ulepszeń modelu: prior klubowy, tempo z 1X2, Elo,
kalibracja przedziałowa."""

import numpy as np
import pytest

from footstats.engine import PlayerHistory, MatchContext, score_player_market, _select_bias
from footstats.jobs import rozliczanie
from footstats.jobs.build_wc_fast import WC_START_TS, klub_prior
from footstats.model import counts, tempo
from footstats.sources import eloratings, statshub


# ---- tempo meczu z kursów 1X2 + total ----

def test_tempo_z_kursow_faworyt_domowy():
    t = tempo.tempo_from_match_odds({
        "h": 1.85, "x": 3.65, "a": 4.45,
        "totals": {2.5: {"over": 1.71, "under": 2.15}},
    })
    assert t is not None
    assert t["spread"] > 0.3          # gospodarz wyraźnym faworytem
    assert 2.3 < t["total"] < 3.4     # total z linii 2.5 przy kursach ~równych
    assert t["p_home"] > 0.5


def test_tempo_brak_kompletu_kursow():
    assert tempo.tempo_from_match_odds(None) is None
    assert tempo.tempo_from_match_odds({"h": 1.8, "x": None, "a": 4.0}) is None


def test_tempo_symetryczny_mecz():
    t = tempo.tempo_from_match_odds({
        "h": 2.9, "x": 3.2, "a": 2.9, "totals": {}
    })
    assert abs(t["spread"]) < 0.05
    assert t["total"] == 2.6          # fallback bez rynku goli


# ---- Elo: waga próby i syntetyczny spread ----

def test_elo_waga_proby_ciagla():
    w_fra = eloratings.sample_weight(2140)
    w_srednia = eloratings.sample_weight(1900)
    w_slaba = eloratings.sample_weight(1400)
    assert w_fra > w_srednia > w_slaba
    assert w_fra <= 1.1 and w_slaba >= 0.6
    assert abs(w_srednia - 1.0) < 0.05


def test_elo_waga_fallback_bez_ratingu():
    assert eloratings.sample_weight(None, is_wc_participant=True) == 0.95
    assert eloratings.sample_weight(None, is_wc_participant=False) == 0.8


def test_elo_syntetyczny_spread():
    assert eloratings.synthetic_spread(2100, 1600) == 1.0
    assert eloratings.synthetic_spread(1600, 2100) == -1.0
    assert eloratings.synthetic_spread(None, 1800) is None


def test_elo_norm_aliasy():
    assert eloratings._norm("USA") == "united states"
    assert eloratings._norm("Côte d'Ivoire") == "cote divoire"


# ---- prior klubowy ----

def _trend(n_pre: int, n_turniej: int, c_pre=2.0, c_t=0.0) -> statshub.StatshubTrend:
    """n_pre meczów sprzed turnieju (po c_pre zdarzeń), n_turniej po starcie."""
    ts_pre = [WC_START_TS - (i + 1) * 7 * 86400 for i in range(n_pre)]
    ts_t = [WC_START_TS + (i + 1) * 4 * 86400 for i in range(n_turniej)]
    ts = ts_t[::-1] + ts_pre  # od najnowszych
    return statshub.StatshubTrend(
        player_id=1, player_name="Test", position="F", team_id=1,
        team_name="France", opponent_id=2, opponent_name="Paraguay",
        is_home=True, market_code="shots", line=0.5,
        in_predicted_lineup=True, league_average=None, opponent_average=None,
        opponent_rank=None, total_ranks=None,
        counts=[c_t] * n_turniej + [c_pre] * n_pre,
        minutes=[90.0] * (n_turniej + n_pre),
        timestamps=ts,
        started=[True] * (n_turniej + n_pre),
    )


def test_klub_prior_silny_z_historii_przedturniejowej():
    tr = _trend(n_pre=12, n_turniej=3, c_pre=2.0, c_t=0.0)
    now = WC_START_TS + 20 * 86400
    kp = klub_prior(tr, now, None)
    assert kp is not None
    prior, mask = kp
    assert prior.source == "klub"
    assert prior.mean_per90 == pytest.approx(2.0, abs=0.01)
    assert 4.0 <= prior.pseudo_matches <= 12.0
    # maska: turniej True, przedturniejowe False
    assert mask == [True] * 3 + [False] * 12


def test_klub_prior_none_przy_malej_probie():
    tr = _trend(n_pre=2, n_turniej=5)
    assert klub_prior(tr, WC_START_TS + 10 * 86400, None) is None


def test_maska_likelihood_nie_liczy_podwojnie():
    """Posterior z maską = prior klubowy + tylko mecze turnieju."""
    tr = _trend(n_pre=10, n_turniej=2, c_pre=2.0, c_t=2.0)
    now = WC_START_TS + 15 * 86400
    prior, mask = klub_prior(tr, now, None)
    hist = PlayerHistory(
        counts=tr.counts, minutes=tr.minutes,
        days_ago=[(now - t) / 86400.0 for t in tr.timestamps],
        started=tr.started, likelihood_mask=mask,
    )
    ctx = MatchContext(is_home=True, is_favourite=False, neutral_venue=True)
    sm = score_player_market("shots", 1.5, hist, prior, ctx)
    # efektywna próba posteriora ~2 mecze turnieju (nie 12)
    assert sm.reasoning["czynniki"][0]["opis"].startswith("Średnio 2.0")
    assert "sprzed turnieju" in sm.reasoning["czynniki"][0]["opis"]


# ---- scenariusz meczu wchodzi do scoringu ----

def test_tempo_podbija_strzaly_faworyta():
    tr = _trend(n_pre=10, n_turniej=2, c_pre=2.0, c_t=2.0)
    now = WC_START_TS + 15 * 86400
    prior, mask = klub_prior(tr, now, None)
    hist = PlayerHistory(
        counts=tr.counts, minutes=tr.minutes,
        days_ago=[(now - t) / 86400.0 for t in tr.timestamps],
        started=tr.started, likelihood_mask=mask,
    )
    bez = score_player_market("shots", 1.5, hist, prior, MatchContext(
        is_home=True, is_favourite=False, neutral_venue=True))
    z_tempem = score_player_market("shots", 1.5, hist, prior, MatchContext(
        is_home=True, is_favourite=True, neutral_venue=True,
        implied_spread=1.2, implied_total=3.2))
    assert z_tempem.p_over > bez.p_over


# ---- kalibracja przedziałowa ----

def _rec(mk, p, wynik):
    return {"rynek_kod": mk, "p_model": p, "wynik": wynik}


def test_bias_full_rodzina_i_przedzialy():
    log = {}
    # 30 rozliczonych shots: model mówił 0.75, trafiało 60% (przeszacowanie)
    for i in range(30):
        log[f"s{i}"] = _rec("shots", 0.75, "wygrany" if i < 18 else "przegrany")
    # 10 rozliczonych sot — za mało samodzielnie, ale rodzina "strzelanie" ma 40
    for i in range(10):
        log[f"o{i}"] = _rec("sot", 0.60, "wygrany" if i < 4 else "przegrany")
    full = rozliczanie.compute_bias_full(log, min_n=25)
    assert "shots" in full and "sot" in full        # sot dzięki rodzinie
    assert full["shots"]["global"] < 1.0            # przeszacowanie wykryte
    assert len(full["shots"]["bins"]) == 3
    # przedział 0.70-1.01 ma 30 obserwacji -> bias przedziałowy aktywny
    hi_bin = full["shots"]["bins"][2]
    assert hi_bin[0] == 0.70 and 0.85 <= hi_bin[2] <= 1.15


def test_bias_full_pomija_rynek_bez_danych_i_rodziny():
    log = {f"x{i}": _rec("offsides", 0.6, "wygrany") for i in range(10)}
    assert rozliczanie.compute_bias_full(log, min_n=25) == {}


def test_select_bias_wybiera_przedzial():
    mb = {"global": 0.95, "bins": [[0.0, 0.55, 1.05], [0.55, 0.70, 0.97],
                                   [0.70, 1.01, 0.90]]}
    assert _select_bias(mb, 0.80) == 0.90
    assert _select_bias(mb, 0.60) == 0.97
    assert _select_bias(mb, 0.30) == 1.05
    assert _select_bias(0.93, 0.80) == 0.93         # stary format: skalar


# ---- CLV: snapshot kursu zamkniecia ----

def test_clv_snapshot_przed_meczem():
    log = {"1:kane:sot:0.5:powyzej": {
        "mecz_id": 1, "podmiot": "Kane", "rynek_kod": "sot", "linia": 0.5,
        "strona": "powyzej", "kurs": 1.85, "kickoff_ts": 10_000, "wynik": None,
    }}
    bets = [{"mecz_id": 1, "podmiot": "Kane", "rynek_kod": "sot",
             "linia": 0.5, "strona": "powyzej", "kurs": 1.62}]
    rozliczanie._snapshot_zamkniecia(log, bets, [], now=5_000)
    assert log["1:kane:sot:0.5:powyzej"]["kurs_zamkniecia"] == 1.62
    # po kickoffie snapshot juz sie nie zmienia
    bets[0]["kurs"] = 1.40
    rozliczanie._snapshot_zamkniecia(log, bets, [], now=11_000)
    assert log["1:kane:sot:0.5:powyzej"]["kurs_zamkniecia"] == 1.62


def test_clv_snapshot_nie_dotyka_rozliczonych():
    log = {"1:kane:sot:0.5:powyzej": {
        "mecz_id": 1, "podmiot": "Kane", "rynek_kod": "sot", "linia": 0.5,
        "strona": "powyzej", "kurs": 1.85, "kickoff_ts": 10_000,
        "wynik": "wygrany",
    }}
    bets = [{"mecz_id": 1, "podmiot": "Kane", "rynek_kod": "sot",
             "linia": 0.5, "strona": "powyzej", "kurs": 1.62}]
    rozliczanie._snapshot_zamkniecia(log, bets, [], now=5_000)
    assert "kurs_zamkniecia" not in log["1:kane:sot:0.5:powyzej"]


# ---- rentgen kuponu: najslabsze ogniwo + alternatywa ----

def _leg_pool(pid, mecz_id, p, kurs, kickoff=50_000):
    return {"id": 0, "podmiot_id": pid, "podmiot": f"P{pid}",
            "rynek_kod": "shots", "rynek": "Strzaly", "linia": 0.5,
            "strona": "powyzej", "kurs": kurs, "bukmacher": "Superbet",
            "p_model": p, "pewnosc": "wysoka", "mecz": f"M{mecz_id}",
            "mecz_id": mecz_id, "kickoff_ts": kickoff}


def test_rentgen_wskazuje_najslabszy_i_alternatywe():
    from footstats.model import kupony as kmod
    legi = [_leg_pool(1, 1, 0.80, 1.5), _leg_pool(2, 2, 0.55, 2.0),
            _leg_pool(3, 3, 0.75, 1.6)]
    kupon = {"kurs_laczny": round(1.5 * 2.0 * 1.6, 2), "p_model": 0.33,
             "legi": [kmod._leg_dict(b) for b in legi]}
    # pula: lepszy kandydat z nowego meczu o podobnym kursie
    pool = legi + [_leg_pool(9, 9, 0.72, 1.9)]
    kmod._rentgen(kupon, pool, 4.0, 6.0)
    assert kupon["najslabszy_idx"] == 1
    alt = kupon["alternatywa"]
    assert alt["podmiot_id"] == 9 and alt["zamiast_idx"] == 1
    assert alt["p_po"] > kupon["p_model"]
    assert 4.0 * 0.8 <= alt["kurs_po"] <= 6.0


def test_rentgen_bez_lepszego_kandydata():
    from footstats.model import kupony as kmod
    legi = [_leg_pool(1, 1, 0.80, 1.5), _leg_pool(2, 2, 0.55, 2.0)]
    kupon = {"kurs_laczny": 3.0, "p_model": 0.44,
             "legi": [kmod._leg_dict(b) for b in legi]}
    kmod._rentgen(kupon, legi, 2.5, 4.0)
    assert kupon["najslabszy_idx"] == 1
    assert "alternatywa" not in kupon
