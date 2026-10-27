# -*- coding: utf-8 -*-
"""H2H zawodników z 80 meczów kadry (2026-10-27, etap 1 = pomiar i karta)."""
from footstats.jobs import build_wc_fast as B
from footstats.model import argumenty as A
from footstats.sources import statshub as S

DZIEN = 86400
KO = 1_800_000_000


def _hist(n=10, c=2.0, mi=90.0, opp=8):
    ts = [KO - (i + 1) * 7 * DZIEN for i in range(n)]
    return [c] * n, [mi] * n, ts, [opp] * n


def _idx():
    return A.Indeks({})


def test_glebokie_h2h_liczy_sie_obok_starego_i_nie_zmienia_argumentow():
    # Semedo 26.10: w krótkiej historii żadnego meczu z rywalem (7)
    c, mi, ts, opp = _hist(c=2.0)
    bez = A.argumenty_zawodnika(_idx(), 7, KO, "fouls_committed", 1.5, c, mi, ts, opp)
    gleb = [[KO - 200 * DZIEN, 3.0, 90.0], [KO - 380 * DZIEN, 1.0, 85.0]]
    z = A.argumenty_zawodnika(_idx(), 7, KO, "fouls_committed", 1.5, c, mi, ts, opp,
                              h2h_gleb=gleb)
    assert z["dane"]["h2h_gl"] == [1, 2]
    assert "h2h" not in z["dane"]
    # wybór typów bez zmian: te same argumenty za i przeciw
    assert (z["za"], z["przeciw"]) == (bez["za"], bez["przeciw"])
    assert "h2h_gl" not in bez["dane"]


def test_glebokie_h2h_bez_dubli_minut_i_meczow_po_starcie():
    c, mi, ts, opp = _hist(c=2.0)
    opp[0] = 7                                        # ten sam mecz w trendzie...
    gleb = [[ts[0], 2.0, 90.0],                       # ...i w kadrze — liczy się raz
            [KO - 300 * DZIEN, 3.0, 10.0],            # 10 minut — nie występ
            [KO - 3600, 3.0, 90.0]]                   # godzina przed meczem — nie
    a = A.argumenty_zawodnika(_idx(), 7, KO, "fouls_committed", 1.5, c, mi, ts, opp,
                              h2h_gleb=gleb)
    assert a["dane"]["h2h_gl"] == [1, 1]
    assert a["dane"]["h2h"] == [1, 1]


def test_para_znana_bez_meczow_to_zero_z_zera():
    c, mi, ts, opp = _hist()
    a = A.argumenty_zawodnika(_idx(), 7, KO, "shots", 1.5, c, mi, ts, opp, h2h_gleb=[])
    assert a["dane"]["h2h_gl"] == [0, 0]


def _kadra(tid=10):
    """Trzy mecze drużyny 10: dwa z 20, jeden z 30."""
    ev = []
    for eid, rywal, dni in ((1, 20, 30), (2, 30, 60), (3, 20, 400)):
        ev.append({"events": {"id": eid, "timeStartTimestamp": KO - dni * DZIEN,
                              "homeTeamId": tid, "awayTeamId": rywal, "uniqueTournamentId": 1},
                   "homeTeam": {"name": "Nasi"}, "awayTeam": {"name": f"R{rywal}"}})
    st = {str(eid): {"teamId": tid, "minutesPlayed": 90, "fouls": f, "wasFouled": 1}
          for eid, f in ((1, 3), (2, 0), (3, 1))}
    return {"events": ev, "data": [{"id": 5, "name": "Semedo", "position": "D", "stats": st}]}


def test_h2h_z_kadry_i_odczyt():
    h = S.h2h_z_kadry(_kadra(), 10, [20, 40], {"fouls_committed"})
    assert set(h) == {20, 40} and h[40] == {}
    mecze = h[20]["5"]["fouls_committed"]
    assert [m[1] for m in mecze] == [3.0, 1.0]        # najnowszy pierwszy
    assert "fouls_won" not in h[20]["5"]              # tylko zamówione rynki
    pam = {"10:20": {"ts": KO, "g": h[20]}, "10:40": {"ts": KO, "g": {}}}
    assert S.h2h_gracza(pam, 10, 20, 5, "fouls_committed") == mecze
    assert S.h2h_gracza(pam, 10, 40, 5, "fouls_committed") == []    # para znana, meczów brak
    assert S.h2h_gracza(pam, 10, 50, 5, "fouls_committed") is None  # nie wiemy
    assert S.h2h_gracza(None, 10, 20, 5, "fouls_committed") is None


def test_odswiezanie_raz_na_dobe_i_sprzatanie():
    teraz = KO - 2 * DZIEN
    events = [{"id": 1, "timeStartTimestamp": KO, "homeTeamId": 10, "awayTeamId": 20},
              {"id": 2, "timeStartTimestamp": KO + 30 * DZIEN, "homeTeamId": 11, "awayTeamId": 21}]
    wolania = []

    def fetch(tid):
        wolania.append(tid)
        return _kadra(tid)

    pam = {"1:2": {"ts": teraz - 10 * DZIEN, "g": {}}}          # stara para
    nowe, stare = B.odswiez_h2h_kadr(events, pam, teraz, fetch=fetch)
    assert (nowe, stare) == (2, 1) and sorted(wolania) == [10, 20]  # mecz 2 poza oknem
    assert set(pam) == {"10:20", "20:10"}
    assert pam["10:20"]["g"]["5"]["fouls_committed"][0][1] == 3.0
    wolania.clear()
    assert B.odswiez_h2h_kadr(events, pam, teraz + 3600, fetch=fetch) == (0, 0)
    assert wolania == []                                        # świeże — bez zapytań
    # limit drużyn na cykl
    assert B.odswiez_h2h_kadr(events, {}, teraz, fetch=fetch, limit=1)[0] == 1


def test_awaria_pobrania_nie_zapisuje_pary():
    def zly(tid):
        raise RuntimeError("429")
    pam: dict = {}
    events = [{"id": 1, "timeStartTimestamp": KO, "homeTeamId": 10, "awayTeamId": 20}]
    assert B.odswiez_h2h_kadr(events, pam, KO - DZIEN, fetch=zly) == (0, 0)
    assert pam == {}


def test_argumenty_typu_czyta_pamiec_h2h():
    import types
    c, mi, ts, opp = _hist(c=2.0)
    tr = types.SimpleNamespace(counts=c, minutes=mi, timestamps=ts, game_opponent_ids=opp,
                               opponent_id=7, team_id=10)
    zaw = {"podmiot_typ": "zawodnik", "podmiot_id": 5, "mecz_id": 77, "kickoff_ts": KO,
           "rynek_kod": "fouls_committed", "linia": 1.5, "strona": "powyzej"}
    pam = {"10:7": {"ts": KO, "g": {"5": {"fouls_committed": [[KO - 200 * DZIEN, 3.0, 90.0],
                                                             [KO - 380 * DZIEN, 2.0, 90.0]]}}}}
    a = B.argumenty_typu(zaw, _idx(), {}, {(77, 5, "fouls_committed"): tr}, None, pam)
    assert a["dane"]["h2h_gl"] == [2, 2]
    a = B.argumenty_typu(zaw, _idx(), {}, {(77, 5, "fouls_committed"): tr})
    assert "h2h_gl" not in a["dane"]
