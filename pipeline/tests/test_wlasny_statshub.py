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


# --------------------------------------------------------------- kadra (4c) ----
def _eventy_sun(ts_list):
    return {800 + i: {"t": ts, "h": SH_SUN, "a": SH_LEE, "l": 17} for i, ts in enumerate(ts_list)}


def test_kadra_w_ksztalcie_statshub_bank_i_fotmob():
    stare = [REK["ts"] - k * 7 * 86400 for k in (1, 2)]
    z = _zrodlo(bank=_bank(stare), eventy=_eventy_sun(stare))
    k = z.fetch_team_players_performance(SH_SUN, teraz=REK["ts"] + 86400)
    assert [r["events"]["id"] for r in k["events"]] == [SH_MECZ, 800, 801]   # od najnowszego
    assert all(isinstance(r["events"], dict) for r in k["events"])
    x = next(p for p in k["data"] if p["id"] == SH_XHAKA)
    assert set(x["stats"]) == {str(SH_MECZ), "800", "801"}                    # klucze tekstem
    assert x["name"] == "Granit Xhaka" and x["position"] == "M"
    tr = statshub.trendy_kadry(k, z.fetch_extra_stats([SH_MECZ, 800, 801]), SH_SUN)[SH_XHAKA]
    assert tr["fouls_committed"].counts == [1.0, 2.0, 2.0] and tr["fouls_committed"].z_kadry
    assert tr["headed_shots"].counts == [0.0, 2.0, 2.0]                        # extra z obu części
    assert statshub.braki_druzyny(k, {}, REK["ts"] + 86400) is not None


def test_kadra_mecz_przyszly_i_bez_skladow_poza_lista():
    rek = copy.deepcopy(REK)
    rek["zawodnicy"] = []
    z = _zrodlo(rek=rek, eventy=_eventy_sun([REK["ts"] + 3 * 86400]))
    k = z.fetch_team_players_performance(SH_SUN, teraz=REK["ts"] + 86400)
    assert k["events"] == [] and z.licz["mecz_bez_skladow"] == 1


def test_kadra_limit_i_wiersz_z_innym_klubem_poza_kadra():
    stare = [REK["ts"] - k * 7 * 86400 for k in (1, 2, 3)]
    ev = _eventy_sun(stare)
    ev[900] = {"t": stare[0] + 600, "h": 77, "a": 78, "l": 18}          # inny mecz o tej porze
    bank = _bank(stare)
    for rec in bank.values():
        rec["game_opponent_ids"] = [78, SH_LEE, SH_LEE]                  # pierwszy mecz w starym klubie
    z = _zrodlo(bank=bank, eventy=ev)
    k = z.fetch_team_players_performance(SH_SUN, limit=3, teraz=REK["ts"] + 86400)
    assert len(k["events"]) == 3
    x = next(p for p in k["data"] if p["id"] == SH_XHAKA)
    assert set(x["stats"]) == {str(SH_MECZ), "801"}                     # 800 = mecz z 77, nie z Sunderlandem


def test_niepelny_bank_nie_daje_pelnej_historii():
    """Bank znający zawodnika z feedu (część meczów) – historia nie jest pełna,
    dopóki takie wiersze są w ostatnich `OKNO_PELNEJ` meczach."""
    stare = [REK["ts"] - k * 7 * 86400 for k in (1, 2)]
    z = _zrodlo(bank=_bank(stare))
    tr = statshub.trendy_z_performance(SH_XHAKA, "x", SH_SUN, z.fetch_player_performance(SH_XHAKA))
    assert not tr["fouls_committed"].historia_pelna
    bank = _bank(stare)
    for rec in bank.values():
        rec["historia_pelna"] = True
    z = _zrodlo(bank=bank)
    tr = statshub.trendy_z_performance(SH_XHAKA, "x", SH_SUN, z.fetch_player_performance(SH_XHAKA))
    assert tr["fouls_committed"].historia_pelna
    # same wiersze FotMob (pełny skład meczu) – pełna
    tr = statshub.trendy_z_performance(SH_XHAKA, "x", SH_SUN, _zrodlo().fetch_player_performance(SH_XHAKA))
    assert tr["fouls_committed"].historia_pelna


def test_extra_bez_mapy_strzalow_mecz_nie_wchodzi():
    rek = copy.deepcopy(REK)
    rek["mapa_strzalow"] = False
    assert _zrodlo(rek=rek).fetch_extra_stats([SH_MECZ]) == {}
    assert SH_MECZ in _zrodlo().fetch_extra_stats([SH_MECZ])


# ------------------------------------------- nadchodzący mecz: braki i XI (4c) ----
def _przed(nazwa):
    return json.load(gzip.open(DANE / nazwa, "rt", encoding="utf-8"))


def test_niedostepni_z_meczu_w_ksztalcie_statshub():
    d = _przed("przed_pl_chelsea_mu.json.gz")           # Chelsea 8455 – Man Utd 10260, PL
    t = T.Tozsamosc({"druzyny": {"8455": 38, "10260": 35}, "rozgrywki": {"47": 17}})
    z = W.Zrodlo(t, {}, {}, {})
    wyn = z.mecz_nadchodzacy(d)
    assert wyn["przewidywany"] and not wyn["potwierdzony"]
    k = z.fetch_team_players_performance(38)
    assert k["unavailability"] and all(u["kind"] == "injury" for u in k["unavailability"])
    nd = statshub.niedostepni_z_kadry(k, 1_800_000_000, 17)
    # „Back in training” (Chavarría) = wątpliwy, „Mid January 2027” (James) = pewny
    po = {u["reason"]: nd[u["playerId"]]["pewny"] for u in k["unavailability"] if u["playerId"] in nd}
    assert po["Back in training"] is False and po["Mid January 2027"] is True
    # przewidywany XI – 11 numerów, nieogłoszony
    xi = z.fetch_predicted_lineup(wyn["event_id"])
    assert len(xi["home"]) == 11 and len(xi["away"]) == 11 and xi["confirmed"] is False
    assert z.fetch_team_lineup(wyn["event_id"], 38) == []


def test_zawieszenie_w_rozgrywkach_meczu_i_ostatni_sklad_to_nie_przewidywanie():
    d = _przed("przed_slaven_istra.json.gz")             # lineupType lastStarting11
    t = T.Tozsamosc({"druzyny": {"1581": 501, "6038": 502}, "rozgrywki": {"252": 170}})
    z = W.Zrodlo(t, {}, {}, {})
    wyn = z.mecz_nadchodzacy(d)
    assert not wyn["przewidywany"] and not wyn["potwierdzony"]
    assert z.fetch_predicted_lineup(wyn["event_id"]) == {"home": [], "away": [], "confirmed": False}
    zaw = next(u for u in z.fetch_team_players_performance(501)["unavailability"] if u["kind"] == "suspension")
    assert zaw["status"] is None and zaw["uniqueTournamentId"] == 170 and zaw["endDateTimestamp"]


def test_sklad_przed_meczem_mapuje_po_nazwisku_bez_zamykania():
    d = _przed("przed_pl_chelsea_mu.json.gz")
    starter = d["content"]["lineup"]["homeTeam"]["starters"][0]
    bank = {"77:shots": {"player_id": 77, "player_name": starter["name"], "team_id": 38,
                         "timestamps": [], "minutes": [], "counts": []}}
    t = T.Tozsamosc({"druzyny": {"8455": 38, "10260": 35}})
    z = W.Zrodlo(t, {}, bank, {})
    wyn = z.mecz_nadchodzacy(d)
    assert wyn["xi"][38][0] == 77
    # pozostali bez pary – bez stałego zera (dostaną je dopiero, gdy zagrają)
    assert all(v != 0 for v in t.zawodnicy.values())


def test_sklad_ogloszony():
    d = copy.deepcopy(_przed("przed_pl_chelsea_mu.json.gz"))
    d["content"]["lineup"]["lineupType"] = "standard"
    z = W.Zrodlo(T.Tozsamosc({"druzyny": {"8455": 38, "10260": 35}}), {}, {}, {})
    wyn = z.mecz_nadchodzacy(d)
    assert wyn["potwierdzony"] and len(z.fetch_team_lineup(wyn["event_id"], 35)) == 11
    assert z.fetch_predicted_lineup(wyn["event_id"])["confirmed"] is True


# ------------------------------------------------- drużyny, wynik, mapa (4d) ----
def test_historia_druzyny_w_ksztalcie_statshub_i_magazyn():
    from footstats.jobs import magazyn_druzyn as M
    z = _zrodlo()
    stary = REK["ts"] - 7 * 86400
    z.ustaw_magazyn({str(SH_SUN): {"m": [
        {"e": 700, "t": stary, "h": 0, "o": 99, "l": 17, "g": 1, "gp": 2,
         "s": {"cor": 4, "sh": 10, "crd": 2}, "sp": {"cor": 7}},
        {"e": 701, "t": REK["ts"] + 60, "h": 1, "o": SH_LEE, "l": 17, "g": 9, "gp": 9, "s": {"cor": 1}}]}})
    rows = z.fetch_team_performance(SH_SUN)
    # mecz w magazynie i w bazie – raz, z magazynu; od najnowszego
    assert [r["event"]["id"] for r in rows] == [701, 700]
    r = rows[1]
    assert r["event"]["score"] == {"home": 2, "away": 1} and r["homeTeam"]["id"] == 99
    assert r["statistics"] == {"cornerKicks": 4, "totalShotsOnGoal": 10, "cards": 2}
    # bez magazynu – mecz z bazy FotMob; rekord magazynu buduje się z niego bez strat
    rows = _zrodlo().fetch_team_performance(SH_SUN)
    assert len(rows) == 1 and rows[0]["event"]["id"] == SH_MECZ
    rek = M.rekord_meczu(SH_SUN, rows[0])
    assert rek["e"] == SH_MECZ and rek["o"] == SH_LEE and rek["h"] == 1 and rek["l"] == 17
    assert {"cor", "sh", "sot", "fol", "crd", "pos", "f3"} <= set(rek["s"]) and rek["sp"]
    assert rek["g"] == REK["gole90"][0] and rek["gp"] == REK["gole90"][1]
    st = rows[0]["statistics"]
    assert st["cards"] == st.get("yellowCards", 0) + st.get("redCards", 0)
    assert rows[0]["event"]["homeScoreOvertime"] is None


def test_dogrywka_i_karne_niepuste():
    rek = fotmob.mecz_do_bazy(json.load(gzip.open(DANE / "mecz_pen_6275371.json.gz", "rt", encoding="utf-8")))
    t = T.Tozsamosc({"druzyny": {str(rek["home"]["id"]): 1, str(rek["away"]["id"]): 2}})
    z = W.Zrodlo(t, {rek["id"]: baza_meczow.spakuj(rek)}, {}, {})
    ev = z.fetch_team_performance(1)[0]["event"]
    assert ev["homeScoreOvertime"] is not None and ev["homeScorePenalties"] is not None
    w = z.fetch_event_result(T.zastepczy(rek["id"]))
    assert w["extra_time"] is True and [w["home_goals"], w["away_goals"]] == rek["gole90"]


def test_wynik_i_status_z_terminarza():
    z = _zrodlo()
    w = z.fetch_event_result(SH_MECZ)
    assert w == {"home_id": SH_SUN, "away_id": SH_LEE, "home_name": "Sunderland AFC", "away_name": "Leeds United",
                 "home_goals": float(REK["gole90"][0]), "away_goals": float(REK["gole90"][1]), "extra_time": False}
    assert z.status_meczu(SH_MECZ) == "finished" and z.fetch_event_result(123) is None
    z.dodaj_terminarz([{"id": 999, "status": "postponed", "start_ts": 1_800_000_000}])
    assert z.status_i_start(T.zastepczy(999)) == ("postponed", 1_800_000_000)
    assert z.status_i_start(5) == (None, None)


def test_mapa_strzalow_w_ksztalcie_statshub():
    z = _zrodlo()
    sm = z.fetch_event_shotmap(SH_MECZ)
    assert len(sm) == len(REK["strzaly"])
    # rozbicie z geometrii (statshub._poza_polem) = flaga FotMob, głowa i celne zgodne
    for s, surowy in zip(sm, REK["strzaly"]):
        assert statshub._poza_polem(s) == (not surowy[8])
        assert s["isHeaded"] == (surowy[5] == "Header") and s["isOnTarget"] == bool(surowy[6])
    assert {s["situation"] for s in sm} <= set(W.SYTUACJE.values())
    assert any(s["situation"] == "corner" for s in sm)
    assert {s["teamId"] for s in sm} == {SH_SUN, SH_LEE}
    assert z.fetch_event_shotmap(123) == []


def test_sedzia_profil():
    z = _zrodlo()
    sid = T.zastepczy(REK["sedzia"]["id"])
    p = z.fetch_referee(sid)
    assert p["m"] == REK["sedzia"]["m"] and p["zk"] == REK["sedzia"]["zk"]
    assert p["k"] == round(REK["sedzia"]["k"] / REK["sedzia"]["m"], 3) and p["ost"] == REK["ts"]
    assert z.fetch_referee(1) is None


def test_utid_grupy_przed_liga_nadrzedna():
    t = T.Tozsamosc({"rozgrywki": {"147": 999, "9001": 11445}})
    assert t.utid(147, 9001) == 11445 and t.utid(147, 5) == 999 and t.utid(1) is None


# ------------------------------------------- terminarz i przełącznik (4e) ----
DZIEN = 1793318400            # 31.10.2026 00:00 UTC


def _terminarz_fm(monkeypatch, mecze):
    dni = {}
    for m in mecze:
        from datetime import datetime, timezone
        dni.setdefault(datetime.fromtimestamp(m["start_ts"], timezone.utc).strftime("%Y%m%d"), []).append(m)
    monkeypatch.setattr(fotmob, "mecze_dnia", lambda d: dni.get(d, []))


def _m(mid, ts, h=8472, a=8463, status="notstarted", liga=47, grupa=47):
    return {"id": mid, "start_ts": ts, "home_id": h, "home": "Sunderland", "away_id": a, "away": "Leeds United",
            "liga_id": liga, "liga_grupa": grupa, "liga": "Premier League", "kraj": "ENG", "status": status}


def test_by_date_w_ksztalcie_statshub(monkeypatch):
    _terminarz_fm(monkeypatch, [_m(1, DZIEN + 15 * 3600), _m(2, DZIEN - 600), _m(3, DZIEN + 3600, h=1, a=2, liga=99,
                                                                                  grupa=99)])
    z = _zrodlo()
    d = z.by_date(DZIEN)["data"]
    assert [e["events"]["id"] for e in d] == [T.zastepczy(1), T.zastepczy(3)]      # mecz 2 – doba wcześniej
    e = d[0]
    assert e["events"]["homeTeamId"] == SH_SUN and e["events"]["uniqueTournamentId"] == 17
    assert e["events"]["status"] == "notstarted" and e["events"]["timeStartTimestamp"] == DZIEN + 15 * 3600
    assert e["homeTeam"] == {"id": SH_SUN, "name": "Sunderland AFC"}                # nazwa Sofascore (aliasy parowania)
    assert e["events"]["slug"] == "sunderland-afc-vs-leeds-united" and e["events"]["lineupConfirmed"] is False
    # nieznana liga i drużyny – numery zastępcze, ale mecz jest (profil domyślny)
    assert d[1]["events"]["uniqueTournamentId"] == T.zastepczy(99) and d[1]["events"]["homeTeamId"] == T.zastepczy(1)
    assert z.status_i_start(T.zastepczy(1)) == ("notstarted", DZIEN + 15 * 3600)


def test_by_date_mecz_znany_ze_statshub_pod_swoim_numerem(monkeypatch):
    # typ sprzed przełączenia stoi pod numerem Sofascore – terminarz FotMob nie dubluje meczu
    _terminarz_fm(monkeypatch, [_m(77, DZIEN + 15 * 3600)])
    z = _zrodlo()
    z._znane = [(16_400_000, DZIEN + 15 * 3600, "Sunderland AFC", "Leeds United")]
    e = z.by_date(DZIEN)["data"][0]["events"]
    assert e["id"] == 16_400_000 and z.status_i_start(16_400_000) == ("notstarted", DZIEN + 15 * 3600)
    assert z.licz["terminarz_znane_dopasowane"] == 1


def test_zbuduj_mecz_z_bazy_pod_numerem_ze_statshub(monkeypatch):
    # mecz rozegrany po 29.10 z typem sprzed przełączenia: wynik pod numerem Sofascore
    from footstats import supa
    rek = {**REK, "id": 4_242_424}
    stan = {"zakres_meczow": [{"id": 16_400_001, "gospodarz": "Sunderland AFC", "gosc": "Leeds United",
                               "kickoff_ts": rek["ts"]}],
            "trend_lib": {"x": {"team_id": SH_SUN, "team_name": "Sunderland AFC", "opponent_id": SH_LEE,
                                "opponent_name": "Leeds United", "player_id": 1}}}
    monkeypatch.setattr(supa, "get_key_ok", lambda k: (stan.get(k), True))
    monkeypatch.setattr(T, "wczytaj", lambda: (T.Tozsamosc({"druzyny": {"8472": SH_SUN, "8463": SH_LEE}}), True))
    monkeypatch.setattr(baza_meczow, "wczytaj", lambda klucze: ({rek["id"]: baza_meczow.spakuj(rek)}, []))
    import time
    monkeypatch.setattr(time, "time", lambda: rek["ts"] + 86400)
    z = W.zbuduj(miesiace=1)
    assert z.t.id_meczu(rek["id"]) == 16_400_001
    assert z.fetch_event_result(16_400_001)["home_id"] == SH_SUN


def test_by_date_bez_odpowiedzi_fotmob_to_blad(monkeypatch):
    def pada(d):
        raise RuntimeError("503")
    monkeypatch.setattr(fotmob, "mecze_dnia", pada)
    import pytest
    with pytest.raises(RuntimeError):
        _zrodlo().by_date(DZIEN)


def test_wyszukiwarka_z_indeksem_jak_pelny_przeglad():
    z = W.Zrodlo(T.Tozsamosc({}), {}, {}, {})
    z.nazwy_zawodnikow.update({1: "Wanderlan", 2: "Saied Abu Farchi", 3: "Mads Gjerstrøm", 4: "Takashi Sawada",
                               5: "Youssuf Sylla", 6: "Granit Xhaka", 7: "Jan Kowalski"})

    def pelny(q):
        oc = sorted(((T.podobienstwo_nazwisk(q, n), pid) for pid, n in z.nazwy_zawodnikow.items()
                     if T.podobienstwo_nazwisk(q, n) >= T.PROG_NAZWISKA), key=lambda x: (-x[0], x[1]))
        return [pid for _, pid in oc[:8]]
    for q in ("Vanderlan", "Sayed Abu Farkhi", "M. Gjerstrom", "Takeshi Wada", "Sylla Youssuf", "Xhaka", "Kowalsky"):
        assert [r["id"] for r in z.search_players(q)] == pelny(q), q
    assert [r["id"] for r in z.search_players("Vanderlan")] == [1]
    z.nazwy_zawodnikow[8] = "Granit Xhakaj"                  # nowy zawodnik – indeks się odświeża
    assert 8 in [r["id"] for r in z.search_players("Granit Xhaka")]


def test_przelacznik_w_module_statshub(monkeypatch):
    z = _zrodlo()
    monkeypatch.setattr(statshub, "_get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sieć statshub")))
    statshub.ustaw_wlasne_zrodlo(z)
    try:
        assert statshub.fetch_player_performance(SH_XHAKA) == z.fetch_player_performance(SH_XHAKA)
        assert statshub.fetch_event_trends([1, 2]) == [] and statshub.fetch_team_trends([1]) == []
        assert statshub.props_available(1) is False
        assert statshub.fetch_event_result(SH_MECZ)["home_id"] == SH_SUN
        assert statshub.player_shots_from_shotmap(SH_MECZ)                       # przez fetch_event_shotmap
        assert statshub.fetch_player_meta(SH_XHAKA) == {"height": None, "foot": None}
    finally:
        statshub.ustaw_wlasne_zrodlo(None)
    assert statshub.wlasne_zrodlo() is None


def test_build_league_terminarz_przez_wlasne_zrodlo(monkeypatch):
    from footstats.jobs import build_league
    _terminarz_fm(monkeypatch, [_m(1, DZIEN + 15 * 3600)])
    monkeypatch.setattr(build_league, "_sh_statshub", lambda url: (_ for _ in ()).throw(AssertionError("statshub")))
    statshub.ustaw_wlasne_zrodlo(_zrodlo())
    try:
        d = build_league._sh(f"{build_league.SH_BASE}/event/by-date?startOfDay={DZIEN}&endOfDay={DZIEN + 86399}")
        assert d["data"][0]["events"]["id"] == T.zastepczy(1)
    finally:
        statshub.ustaw_wlasne_zrodlo(None)


def test_przed_meczami_sklad_i_sedzia_w_surowym_evencie(monkeypatch):
    d = _przed("przed_pl_chelsea_mu.json.gz")
    ts = DZIEN + 12 * 3600
    _terminarz_fm(monkeypatch, [{**_m(int(d["general"]["matchId"]), ts, h=8455, a=10260)}])
    monkeypatch.setattr(fotmob, "szczegoly_meczu", lambda mid: d)
    z = W.Zrodlo(T.Tozsamosc({"druzyny": {"8455": 38, "10260": 35}}), {}, {}, {})
    ev = z.by_date(DZIEN)["data"][0]["events"]
    licz = z.przed_meczami([ev], teraz=ts - 3600)
    assert licz["pobrane"] == 1 and licz["sklad_przewidywany"] == 1 and licz["niedostepni"] > 0
    assert ev["lineupConfirmed"] is False
    assert z.fetch_predicted_lineup(ev["id"])["home"]
    # poza horyzontem – bez zapytania
    licz = z.przed_meczami([ev], teraz=ts - 3 * 86400)
    assert licz == {}


def test_przed_meczami_najpierw_mecze_z_priorytetu(monkeypatch):
    # bliższy mecz bez oferty zawodniczej ustępuje dalszemu z priorytetu
    d = _przed("przed_pl_chelsea_mu.json.gz")
    ts = DZIEN + 12 * 3600
    _terminarz_fm(monkeypatch, [_m(11, ts - 7200, h=1, a=2, liga=99, grupa=99), _m(12, ts, h=8455, a=10260)])
    pytane = []
    monkeypatch.setattr(fotmob, "szczegoly_meczu", lambda mid: pytane.append(mid) or d)
    z = W.Zrodlo(T.Tozsamosc({"druzyny": {"8455": 38, "10260": 35}}), {}, {}, {})
    evs = [e["events"] for e in z.by_date(DZIEN)["data"]]
    assert [e["timeStartTimestamp"] for e in evs] == [ts - 7200, ts]
    licz = z.przed_meczami(evs, teraz=ts - 3 * 3600, budzet=1, pierwsze={evs[1]["id"]})
    assert pytane == [12] and licz["pobrane_z_priorytetu"] == 1 and licz["poza_budzetem"] == 1
    pytane.clear()
    z.przed_meczami(evs, teraz=ts - 3 * 3600, budzet=1)                   # bez priorytetu – najbliższy
    assert pytane == [11]
