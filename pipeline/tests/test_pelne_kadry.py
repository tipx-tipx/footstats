"""Pełne kadry ze statshub: `team/{id}/players/performance` + `extra-stats-batch`.

Zgłoszenie właściciela 2026-09-18: Chery (NEC) — strzały zza pola miały
„za mało historii” (1 mecz), choć statshub pokazuje je w każdym meczu;
Piazón (Wieczysta) — z meczu Widzew–Wieczysta nie mieliśmy ANI JEDNEGO
zawodnika, a Superbet kwotował 41 (faule wywalczone 1,5 @2,17).
"""
from footstats.jobs import build_wc_fast as B
from footstats.sources import statshub
from footstats.sources.statshub import StatshubTrend

TERAZ = 1_800_000_000
DZIEN = 86_400
NEC, RYWAL = 2962, 3115
MECZ_NADCHODZACY = 777


def _ev(eid, dni_temu, dom=NEC, gosc=900):
    return {
        "events": {"id": eid, "timeStartTimestamp": TERAZ - dni_temu * DZIEN,
                   "homeTeamId": dom, "awayTeamId": gosc, "status": "finished",
                   "uniqueTournamentId": 37},
        "homeTeam": {"name": "NEC Nijmegen" if dom == NEC else "Inny"},
        "awayTeam": {"name": "Rywal" if gosc != NEC else "NEC Nijmegen"},
    }


def _st(eid, minuty, strzaly, faule_wyw=1, druzyna=NEC):
    return {"eventId": eid, "teamId": druzyna, "minutesPlayed": minuty,
            "shots": strzaly, "onTargetScoringAttempt": 0, "fouls": 0,
            "wasFouled": faule_wyw, "totalTackle": 0, "interceptionWon": 0,
            "totalOffside": 0, "shotOffTarget": 0, "blockedScoringAttempt": 0,
            "position": "RF"}


def _kadra(team_id=NEC, kontuzja=None):
    return {
        "events": [_ev(11, 3), _ev(12, 10), _ev(13, 17)],
        "data": [
            {"id": 35208, "slug": "tjaronn-chery", "name": "Tjaronn Chery",
             "position": "F",
             "stats": {"11": _st(11, 90, 3), "12": _st(12, 0, 0), "13": _st(13, 85, 4)}},
            {"id": 555, "slug": "bramkarz", "name": "Jasper Cillessen",
             "position": "G", "stats": {"11": _st(11, 90, 0)}},
        ],
        "unavailability": ([{"playerId": kontuzja, "status": "out",
                             "endDateTimestamp": TERAZ + 30 * DZIEN}]
                           if kontuzja else []),
    }


# zza pola: mecz 11 ma dane (slug z diakrytykami jak w API), mecz 13 ma dane
# BEZ Chery'ego (zagrał, nie strzelał zza pola = 0), mecz 12 nie ma danych
EXTRA = {
    11: [{"playerId": "tjaronn-chéry", "playerSlug": "tjaronn-chery",
          "playerName": "Tjaronn Chery", "shotsOutsideBox": 2,
          "shotsOnTargetOutsideBox": 1, "headedShot": 0, "headedShotOnTarget": 0}],
    13: [{"playerId": "ktos-inny", "playerSlug": "ktos-inny", "playerName": "Ktoś",
          "shotsOutsideBox": 5}],
}


def test_trendy_kadry_zza_pola_wprost_ze_statshub():
    tr = statshub.trendy_kadry(_kadra(), EXTRA, NEC)
    chery = tr[35208]
    zza = chery["shots_outside_box"]
    # mecz bez danych (12) pominięty, nie fałszywe zero; mecz 13 = 0 (grał)
    assert zza.counts == [2.0, 0.0]
    assert zza.minutes == [90.0, 85.0]
    assert chery["sot_outside_box"].counts == [1.0, 0.0]
    # rynki z performance — każdy mecz drużyny, z ławką (0 minut)
    assert chery["shots"].counts == [3.0, 0.0, 4.0]
    assert chery["shots"].minutes == [90.0, 0.0, 85.0]
    assert all(t.historia_pelna and t.z_kadry for t in chery.values())
    assert chery["shots"].position == "F"
    assert chery["shots"].game_opponents[0] == "Rywal"


def test_scal_historie_pelna_wygrywa_stara_uzupelnia():
    pelny = statshub.trendy_kadry(_kadra(), EXTRA, NEC)[35208]["shots"]
    stary = StatshubTrend(
        player_id=35208, player_name="Tjaronn Chery", position="F", team_id=NEC,
        team_name="NEC Nijmegen", opponent_id=1, opponent_name="X", is_home=True,
        market_code="shots", line=1.5, in_predicted_lineup=True,
        league_average=None, opponent_average=None, opponent_rank=None,
        total_ranks=None, event_id=MECZ_NADCHODZACY,
        # ten sam mecz 11 z innym znacznikiem (±1 h) + mecz z poprzedniego klubu
        counts=[9.0, 1.0], minutes=[90.0, 90.0],
        timestamps=[TERAZ - 3 * DZIEN + 3600, TERAZ - 400 * DZIEN],
        started=[True, True],
    )
    wynik = B._scal_historie(stary, pelny)
    assert wynik["counts"] == [3.0, 0.0, 4.0, 1.0]
    assert wynik["timestamps"][-1] == TERAZ - 400 * DZIEN


def _mecz():
    return {"id": MECZ_NADCHODZACY, "homeTeamId": NEC, "awayTeamId": RYWAL,
            "timeStartTimestamp": TERAZ + 5 * 3600}


def test_nowe_trendy_tylko_dla_wycenionych_rynkow():
    """Chery wyceniony na zza pola i faule wywalczone — dostaje dokładnie te
    rynki; bramkarz i drużyna bez oferty nic; wyceniony spoza kadry liczony."""
    trends: list = []
    oferta = {"sb": {"tjaronn chery": {"shots_outside_box": {1.5: {"over": 2.4}},
                                       "fouls_won": {0.5: {"over": 1.5}}},
                     "zenon nieznany": {"shots": {0.5: {"over": 1.3}}}},
              "bc": {}}
    licz = B.dolacz_pelne_kadry(
        trends, [_mecz()], TERAZ, oferta=lambda e: oferta,
        fetch_kadra=lambda tid: _kadra() if tid == NEC else None,
        fetch_extra=lambda ids: EXTRA)
    klucze = {(t.player_id, t.market_code) for t in trends}
    assert klucze == {(35208, "shots_outside_box"), (35208, "fouls_won")}
    t = next(t for t in trends if t.market_code == "shots_outside_box")
    assert t.event_id == MECZ_NADCHODZACY and t.is_home and t.opponent_id == RYWAL
    assert t.line == 0.0 and t.historia_pelna
    assert licz["nowe"] == 2 and licz["druzyn_bez_danych"] == 1
    assert licz["wyceniani_bez_kadry"] == 1


def test_istniejacy_trend_dostaje_pelna_historie_i_zostaje_kontekst():
    feed = StatshubTrend(
        player_id=35208, player_name="Tjaronn Chery", position="F", team_id=NEC,
        team_name="NEC Nijmegen", opponent_id=RYWAL, opponent_name="Widzew",
        is_home=True, market_code="shots_outside_box", line=1.5,
        in_predicted_lineup=True, league_average=None, opponent_average=1.1,
        opponent_rank=3, total_ranks=18, event_id=MECZ_NADCHODZACY,
        counts=[3.0], minutes=[86.0], timestamps=[TERAZ - 200 * DZIEN],
        started=[True], ref_odds=[2.2],
    )
    trends = [feed]
    licz = B.dolacz_pelne_kadry(
        trends, [_mecz()], TERAZ, oferta=lambda e: {"sb": {"x": {}}, "bc": {}},
        fetch_kadra=lambda tid: _kadra() if tid == NEC else None,
        fetch_extra=lambda ids: EXTRA)
    assert len(trends) == 1 and licz["wzbogacone"] >= 1
    assert feed.counts == [2.0, 0.0, 3.0] and feed.historia_pelna
    assert feed.line == 1.5 and feed.ref_odds == [2.2] and feed.opponent_rank == 3


def test_mecz_bez_oferty_nie_kosztuje_zapytania_a_kontuzja_blokuje():
    pytano = []

    def _k(tid):
        pytano.append(tid)
        return _kadra(kontuzja=35208) if tid == NEC else None

    licz = B.dolacz_pelne_kadry([], [_mecz()], TERAZ, oferta=lambda e: None,
                                fetch_kadra=_k, fetch_extra=lambda ids: {})
    assert pytano == [] and licz["meczow_bez_oferty"] == 1
    trends: list = []
    licz = B.dolacz_pelne_kadry(
        trends, [_mecz()], TERAZ,
        oferta=lambda e: {"sb": {"tjaronn chery": {"shots": {0.5: {"over": 1.2}}}}},
        fetch_kadra=_k, fetch_extra=lambda ids: {})
    assert trends == [] and licz["pominieci_kontuzja"] == 1


def test_nazwiska_z_literami_bez_rozkladu_i_apostrofem_paruja_sie():
    """Superbet pisze „hojlund oscar”, statshub „Oscar Højlund” — ø, ł, ı
    cięły nazwisko, apostrof rozcinał „N'Dicka”."""
    from footstats.sources import superbet
    assert superbet.norm_name("Oscar Højlund") == "hojlund oscar"
    assert superbet.norm_name("Łukasz Łakomy") == "lakomy lukasz"
    assert superbet.norm_name("Berkay Yılmaz") == "berkay yilmaz"
    assert superbet.norm_name("Evan N'Dicka") == superbet.norm_name("Evan Ndicka")
    oferta = {"hojlund oscar": {"shots": {}}}
    assert superbet.znajdz_zawodnika(oferta, "Oscar Højlund") is oferta["hojlund oscar"]


def test_zdrobnienia_i_pelne_nazwiska_z_superbetu():
    """Albacete–Córdoba 18.09: sześciu wycenionych bez pary z kadrą."""
    from footstats.sources import superbet
    oferta = {
        "del fraile javier villar": {"a": 1}, "ismael ruiz sanchez": {"b": 2},
        "daniel esmoris tasende": {"c": 3}, "dicka evan": {"d": 4},
        "canseco diego pertejo": {"e": 5}, "gabriel pedro": {"f": 6},
    }
    z = superbet.znajdz_zawodnika
    assert z(oferta, "Javi Villar") == {"a": 1}
    assert z(oferta, "Isma Ruiz") == {"b": 2}
    assert z(oferta, "Dani Tasende") == {"c": 3}
    assert z(oferta, "Evan Ndicka") == {"d": 4}
    # dwaj różni ludzie — wspólne imię to nie para
    assert z(oferta, "Diego Percan") == {}
    assert z(oferta, "Pedro Vitor") == {}
    # niejednoznaczne = brak pary
    assert z({"javier villar": {}, "javier villarreal": {}}, "Javi Villar") in ({}, )


def test_zakres_meczow_dla_joba_betclica():
    """Każdy analizowany mecz, z nazwami drużyn i znacznikiem oferty SB."""
    class _Tryb:
        events = [{"id": 1, "homeTeamId": 10, "awayTeamId": 20, "timeStartTimestamp": 5},
                  {"id": 2, "homeTeamId": 30, "awayTeamId": 40, "timeStartTimestamp": 6}]
        sb_ev_by_mid = {1: {"marketCount": 227}, 2: {"marketCount": 90}}
        team_name = {10: "Widzew Łódź", 20: "Wieczysta Kraków", 30: "A", 40: "B"}
    z = B.zakres_meczow(_Tryb())
    assert z[0] == {"id": 1, "gospodarz": "Widzew Łódź", "gosc": "Wieczysta Kraków",
                    "kickoff_ts": 5, "propsy_superbet": 1}
    assert z[1]["propsy_superbet"] == 0


def test_mecz_poza_oknem_pominiety():
    daleki = dict(_mecz(), timeStartTimestamp=TERAZ + 7 * DZIEN)
    licz = B.dolacz_pelne_kadry([], [daleki], TERAZ,
                                oferta=lambda e: {"sb": {"a": {}}},
                                fetch_kadra=lambda tid: _kadra(),
                                fetch_extra=lambda ids: {})
    assert licz["meczow_z_oferta"] == 0 and licz["druzyn"] == 0


def test_syntetyczny_numer_365_przepiety_po_odkrywaniu():
    """Cykl 18.09 14:34: 47 dubli — odkrywanie z oferty dało prawdziwy numer
    PO dopełnianiu z 365 (Real Sociedad B, Lebarbier 1413858 + 985557989)."""
    def t(pid, mk, name="Alex Lebarbier", team=77, ev=5):
        return StatshubTrend(
            player_id=pid, player_name=name, position="D", team_id=team,
            team_name="Real Sociedad B", opponent_id=1, opponent_name="X",
            is_home=True, market_code=mk, line=0.5, in_predicted_lineup=False,
            league_average=None, opponent_average=None, opponent_rank=None,
            total_ranks=None, event_id=ev, counts=[1.0], minutes=[90.0],
            timestamps=[TERAZ], started=[True])
    trends = [t(1413858, "shots"), t(985557989, "shots"), t(985557989, "fouls_won"),
              t(955555555, "shots", name="Ktoś Inny")]
    r = B.przepnij_syntetyczne_numery(trends)
    assert r["zdjete"] == 1 and r["przepiete"] == 1
    klucze = sorted((x.player_id, x.market_code) for x in r["trends"])
    assert klucze == [(1413858, "fouls_won"), (1413858, "shots"), (955555555, "shots")]
