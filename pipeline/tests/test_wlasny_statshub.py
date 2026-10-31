"""Własny statshub (etap 4b): wiersze zawodnika w kształcie statshub z banku i bazy FotMob."""

import copy
import gzip
import json
from pathlib import Path

from footstats import baza_meczow
from footstats import tozsamosc as T
from footstats.sources import fotmob, statshub
from footstats.sources import wlasny_statshub as W

DANE = Path(__file__).parent / "data" / "fotmob"
REK = fotmob.mecz_do_bazy(json.load(gzip.open(DANE / "mecz_pl_5795494.json.gz", "rt", encoding="utf-8")))
XHAKA = 207236
SH_XHAKA, SH_SUN, SH_LEE, SH_MECZ = 111, 41, 42, 15_000_001


def _mapa():
    t = T.Tozsamosc({"druzyny": {"8472": SH_SUN, "8463": SH_LEE}, "mecze": {str(REK["id"]): SH_MECZ},
                     "rozgrywki": {"47": 17}})
    t.zawodnicy[XHAKA] = SH_XHAKA
    t.nazwy[XHAKA] = "Granit Xhaka"
    return t


def _bank(ts_list, druzyna=SH_SUN, rywal=SH_LEE):
    return {f"{SH_XHAKA}:{rk}": {
        "player_id": SH_XHAKA, "player_name": "Granit Xhaka", "team_id": druzyna, "team_name": "Sunderland",
        "market_code": rk, "timestamps": list(ts_list), "counts": [2.0] * len(ts_list),
        "minutes": [90.0] * len(ts_list), "game_positions": ["DM"] * len(ts_list),
        "game_opponent_ids": [rywal] * len(ts_list), "game_opponents": ["Leeds"] * len(ts_list),
        "game_utids": [17] * len(ts_list)} for rk in ("fouls_committed", "headed_shots")}


def _zrodlo(bank=None, eventy=None, mapa=None, rek=REK):
    return W.Zrodlo(mapa or _mapa(), {rek["id"]: baza_meczow.spakuj(rek)}, bank or {}, eventy or {},
                    {SH_SUN: "Sunderland AFC", SH_LEE: "Leeds United"})


def test_wiersz_fotmob_w_ksztalcie_statshub():
    w = _zrodlo().fetch_player_performance(SH_XHAKA)
    assert len(w) == 1
    ps, ev = w[0]["player_statistics_event"], w[0]["events"]
    assert isinstance(ps, dict) and isinstance(ev, dict)          # rozliczanie czyta bez _pierwszy
    assert ev == {"id": SH_MECZ, "timeStartTimestamp": REK["ts"], "homeTeamId": SH_SUN,
                  "awayTeamId": SH_LEE, "uniqueTournamentId": 17, "status": "finished"}
    assert ps["teamId"] == SH_SUN and ps["eventId"] == SH_MECZ and ps["minutesPlayed"] == 90.0
    assert ps["wasFouled"] == 3.0 and ps["fouls"] == 1.0 and "yellowCard" not in ps
    assert w[0]["homeTeam"] == {"name": "Sunderland AFC"}          # nazwa Sofascore, nie FotMob


def test_trendy_z_performance_na_nowych_wierszach():
    z = _zrodlo()
    tr = statshub.trendy_z_performance(SH_XHAKA, "Granit Xhaka", SH_SUN, z.fetch_player_performance(SH_XHAKA),
                                       extra_meczu=z.extra_zawodnika(SH_XHAKA))
    assert tr["fouls_won"].counts == [3.0] and tr["fouls_won"].game_opponent_ids == [SH_LEE]
    assert tr["headed_shots"].counts == [0.0]                     # mecz z mapą strzałów: zero to zero
    assert tr["yellow_card"].counts == [0.0]


def test_bez_mapy_strzalow_brak_rynkow_pochodnych():
    rek = copy.deepcopy(REK)
    rek["mapa_strzalow"] = False
    z = _zrodlo(rek=rek)
    assert z.extra_zawodnika(SH_XHAKA) == {}
    tr = statshub.trendy_z_performance(SH_XHAKA, "x", SH_SUN, z.fetch_player_performance(SH_XHAKA),
                                       extra_meczu=z.extra_zawodnika(SH_XHAKA))
    assert "headed_shots" not in tr and "fouls_won" in tr


def test_bank_i_fotmob_razem_bez_dubla():
    """Mecz w obu częściach – raz, z banku; starsze z banku zostają, od najnowszego."""
    starszy = REK["ts"] - 7 * 86400
    z = _zrodlo(bank=_bank([REK["ts"] + 600, starszy]))
    w = z.fetch_player_performance(SH_XHAKA)
    assert [x["events"]["timeStartTimestamp"] for x in w] == [REK["ts"] + 600, starszy]
    assert w[0]["player_statistics_event"]["fouls"] == 2.0          # z banku, nie z FotMob
    # bank kończy się przed meczem FotMob – mecz FotMob dochodzi na początek
    z = _zrodlo(bank=_bank([starszy]))
    w = z.fetch_player_performance(SH_XHAKA)
    assert [x["events"]["id"] for x in w][0] == SH_MECZ and len(w) == 2
    assert len(z.fetch_player_performance(SH_XHAKA, limit=1)) == 1


def test_bank_numer_meczu_z_magazynu_takze_przez_rywala():
    ts = REK["ts"] - 7 * 86400
    ev = {900: {"t": ts + 120, "h": 77, "a": SH_LEE, "l": 18}}
    # zawodnik grał wtedy w drużynie 77 (bank zna już nowy klub SH_SUN) – mecz po rywalu
    z = _zrodlo(bank=_bank([ts]), eventy=ev)
    w = [x for x in z.fetch_player_performance(SH_XHAKA) if x["events"]["timeStartTimestamp"] == ts][0]
    assert w["events"]["id"] == 900 and w["player_statistics_event"]["teamId"] == 77
    assert w["events"]["uniqueTournamentId"] == 17                # z banku (game_utids) ma pierwszeństwo


def test_bank_bez_meczu_w_magazynie_staly_numer():
    ts = REK["ts"] - 30 * 86400
    a = _zrodlo(bank=_bank([ts])).fetch_player_performance(SH_XHAKA)[-1]["events"]["id"]
    b = _zrodlo(bank=_bank([ts])).fetch_player_performance(SH_XHAKA)[-1]["events"]["id"]
    assert a == b and W.MECZ_BANKU <= a < T.ZASTEPCZY


def test_bank_odtwarza_serie_przez_trendy():
    ts = [REK["ts"] - k * 7 * 86400 for k in range(1, 6)]
    z = _zrodlo(bank=_bank(ts), mapa=T.Tozsamosc({"druzyny": {"8472": SH_SUN}}))
    rows = z.fetch_player_performance(SH_XHAKA)
    tr = statshub.trendy_z_performance(SH_XHAKA, "x", SH_SUN, rows, extra_meczu=z.extra_zawodnika(SH_XHAKA))
    assert tr["fouls_committed"].timestamps == ts and tr["fouls_committed"].counts == [2.0] * 5
    assert tr["headed_shots"].counts == [2.0] * 5


def test_zmiany_i_kolizja_numeru():
    t = _mapa()
    zmien = next(z for z in REK["zawodnicy"] if z["zmiana_przez"])
    t.zawodnicy[zmien["pid"]] = 500
    t.nazwy[zmien["pid"]] = zmien["name"]
    t.zawodnicy[zmien["zmiana_przez"]] = 501
    z = _zrodlo(mapa=t)
    assert z.fetch_player_performance(500)[0]["player_statistics_event"]["substitutedIn"] == 501
    assert z.fetch_player_performance(501)[0]["player_statistics_event"]["substitutedOut"] == 500
    # ten sam numer FotMob pod innym nazwiskiem – wiersz nie wchodzi
    t2 = _mapa()
    t2.nazwy[XHAKA] = "Ktoś Zupełnie Inny"
    z2 = _zrodlo(mapa=t2)
    assert z2.fetch_player_performance(SH_XHAKA) == [] and z2.licz["kolizja_numeru"] == 1


def test_zawodnik_bez_pary_pod_numerem_zastepczym():
    z = _zrodlo(mapa=T.Tozsamosc({"druzyny": {"8472": SH_SUN}}))
    w = z.fetch_player_performance(T.zastepczy(XHAKA))
    assert w and w[0]["events"]["awayTeamId"] == T.zastepczy(8463)
