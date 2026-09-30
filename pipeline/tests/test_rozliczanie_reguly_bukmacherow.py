"""Rozliczanie zawodników: reguły bukmacherów i źródło po numerze (2026-09-30).

Trzy usterki znalezione na księdze 30.09:
* 365 zna mecz, a nie zna nazwiska → dawniej „0 minut, nie zagrał" (149
  zwrotów dla zawodników, którzy grali, np. Artur 90', Florentin 90'),
* mecz bez 365 rozliczony migawką z trwającego meczu (Ferguson 0 fauli,
  statshub 4 — Słowenia–Szkocja 26.09),
* Superbet zwraca zakład na zawodnika spoza pierwszego składu, Betclic liczy
  każdą minutę — rozliczaliśmy oba tak samo.
"""

import time

from footstats.jobs import rozliczanie
from footstats.sources import scores365, statshub

from test_rozliczanie_historia_zawodnika import _wiersz, _wynik_meczu
from test_rozliczanie_multiliga import _przygotuj, _rec_zawodniczy


def _rozlicz(monkeypatch, rec, wiersze, trendy=None, staty_365=None,
             strzaly_365=None):
    store = _przygotuj(monkeypatch, rec, trendy=trendy)
    monkeypatch.setattr(statshub, "fetch_event_result",
                        lambda eid: _wynik_meczu())
    monkeypatch.setattr(statshub, "fetch_player_performance",
                        lambda pid, limit=20: wiersze)
    if staty_365 is not None:
        monkeypatch.setattr(rozliczanie, "_gid_365", lambda r, c: 4242)
        monkeypatch.setattr(scores365, "game_player_match_stats",
                            lambda gid: staty_365)
        monkeypatch.setattr(scores365, "game_player_shots",
                            lambda gid: strzaly_365 or {})
        monkeypatch.setattr(scores365, "after_extra_time", lambda gid: False)
    rozliczanie.rozlicz([], [])
    return list(store["typy_log"].values())[0]


def _trend_zero_fauli(rec):
    """Bank z migawką trwającego meczu: 90 minut, 0 fauli."""
    return [statshub.StatshubTrend(
        player_id=rec["podmiot_id"], player_name=rec["podmiot"], position="M",
        team_id=1, team_name="A", opponent_id=2, opponent_name="B",
        is_home=True, market_code=mk, line=0.5, in_predicted_lineup=False,
        counts=[0], timestamps=[rec["kickoff_ts"]], minutes=[90],
        league_average=None, opponent_average=None, opponent_rank=None,
        total_ranks=None,
    ) for mk in ("fouls_committed", "shots")]


def test_historia_po_numerze_wygrywa_z_bankiem(monkeypatch):
    """Ferguson: bank 0 fauli, historia statshub 4 → wygrany, nie przegrany."""
    rec = _rec_zawodniczy(rynek_kod="fouls_committed", rynek="Faule",
                          linia=1.5, bukmacher="Superbet",
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _rozlicz(monkeypatch, rec, [_wiersz(rec["mecz_id"], 90, fouls=4)],
                 trendy=_trend_zero_fauli(rec))
    assert w["wynik"] == "wygrany" and w["faktyczna"] == 4.0


def test_bez_365_nie_rozliczamy_przed_terminem(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="fouls_committed", linia=1.5,
                          kickoff_ts=int(time.time()) - 2 * 3600)
    w = _rozlicz(monkeypatch, rec, [_wiersz(rec["mecz_id"], 90, fouls=4)],
                 trendy=_trend_zero_fauli(rec))
    assert w["wynik"] is None


def test_superbet_zmiennik_to_zwrot(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="fouls_committed", linia=0.5,
                          bukmacher="Superbet",
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _rozlicz(monkeypatch, rec, [
        _wiersz(rec["mecz_id"], 25, fouls=1, substitutedOut=12345)])
    assert w["wynik"] == "zwrot"
    assert w["powod"] == rozliczanie.POWOD_Z_LAWKI


def test_betclic_zmiennik_sie_liczy(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="fouls_committed", linia=0.5,
                          bukmacher="Betclic",
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _rozlicz(monkeypatch, rec, [
        _wiersz(rec["mecz_id"], 25, fouls=1, substitutedOut=12345)])
    assert w["wynik"] == "wygrany" and w["faktyczna"] == 1.0


def test_superbet_z_pierwszego_skladu_rozliczony(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="fouls_committed", linia=0.5,
                          bukmacher="Superbet",
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _rozlicz(monkeypatch, rec, [
        _wiersz(rec["mecz_id"], 70, fouls=0, substitutedIn=999)])
    assert w["wynik"] == "przegrany"


def test_superbet_zmiennik_wedlug_365(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="fouls_committed", linia=0.5,
                          bukmacher="Superbet",
                          kickoff_ts=int(time.time()) - 3 * 3600)
    staty = {"jan testowy": {"minutes": 20.0, "started": 0.0,
                             "fouls_committed": 2.0}}
    w = _rozlicz(monkeypatch, rec, [], staty_365=staty)
    assert w["wynik"] == "zwrot" and w["powod"] == rozliczanie.POWOD_Z_LAWKI


def test_365_bez_nazwiska_to_nie_zero_minut(monkeypatch):
    """Artur (Vancouver–Houston): 365 zna mecz, nie zna zapisu nazwiska,
    statshub po numerze: 90 minut, 3 strzały → rozliczony, nie zwrot."""
    rec = _rec_zawodniczy(bukmacher="Superbet",            # shots 1.5
                          kickoff_ts=int(time.time()) - 8 * 3600)
    staty = {"ktos zupelnie inny": {"minutes": 90.0, "started": 1.0}}
    w = _rozlicz(monkeypatch, rec,
                 [_wiersz(rec["mecz_id"], 90, shots=3, onTargetScoringAttempt=1)],
                 staty_365=staty, strzaly_365={"ktos zupelnie inny": {"shots": 2}})
    assert w["wynik"] == "wygrany" and w["faktyczna"] == 3.0


def test_365_bez_nazwiska_i_bez_wiersza_w_historii_to_nie_zagral(monkeypatch):
    """Historia pobrana, a meczu w niej nie ma — statshub trzyma tylko mecze
    z minutami, więc to naprawdę „nie zagrał"."""
    rec = _rec_zawodniczy(kickoff_ts=int(time.time()) - 8 * 3600)
    staty = {"ktos zupelnie inny": {"minutes": 90.0, "started": 1.0}}
    w = _rozlicz(monkeypatch, rec, [_wiersz(15999000, 90, shots=1)],
                 staty_365=staty)
    assert w["wynik"] == "zwrot" and w["powod"] == "nie zagrał"


def test_365_bez_nazwiska_czeka_na_historie(monkeypatch):
    """Brak historii (np. budżet zapytań) przed terminem = czekamy, nie zero."""
    rec = _rec_zawodniczy(kickoff_ts=int(time.time()) - 8 * 3600)
    staty = {"ktos zupelnie inny": {"minutes": 90.0, "started": 1.0}}
    store = _przygotuj(monkeypatch, rec)
    monkeypatch.setattr(statshub, "fetch_event_result",
                        lambda eid: _wynik_meczu())

    def _pada(pid, limit=20):
        raise RuntimeError("HTTP 429")
    monkeypatch.setattr(statshub, "fetch_player_performance", _pada)
    monkeypatch.setattr(rozliczanie, "_gid_365", lambda r, c: 4242)
    monkeypatch.setattr(scores365, "game_player_match_stats", lambda gid: staty)
    monkeypatch.setattr(scores365, "game_player_shots", lambda gid: {})
    monkeypatch.setattr(scores365, "after_extra_time", lambda gid: False)
    rozliczanie.rozlicz([], [])
    assert list(store["typy_log"].values())[0]["wynik"] is None


def test_numer_syntetyczny_to_nie_dowod_ze_nie_gral(monkeypatch):
    """Pierwszy cykl na 402b92d: statshub zwraca pustą historię dla numeru
    z odkrywania oferty (≥ 900 mln), a pusta lista czytana jak „meczu nie ma"
    dała 12 fałszywych „nie zagrał" (Román 90', Montaño 66')."""
    rec = _rec_zawodniczy(podmiot_id=937286189, bukmacher="Betclic",
                          kickoff_ts=int(time.time()) - 30 * 3600)
    pytania = []
    store = _przygotuj(monkeypatch, rec)
    monkeypatch.setattr(statshub, "fetch_event_result",
                        lambda eid: _wynik_meczu())
    monkeypatch.setattr(statshub, "fetch_player_performance",
                        lambda pid, limit=20: pytania.append(pid) or [])
    rozliczanie.rozlicz([], [])
    w = list(store["typy_log"].values())[0]
    assert w["wynik"] is None
    assert pytania == []                    # budżet nie idzie na numer syntetyczny


def test_pusta_historia_prawdziwego_numeru_to_nie_dowod(monkeypatch):
    rec = _rec_zawodniczy(kickoff_ts=int(time.time()) - 30 * 3600)
    w = _rozlicz(monkeypatch, rec, [])
    assert w["wynik"] is None


def _rozlicz_z_historiami(monkeypatch, rec, historie):
    store = _przygotuj(monkeypatch, rec)
    monkeypatch.setattr(statshub, "fetch_event_result",
                        lambda eid: _wynik_meczu())
    monkeypatch.setattr(statshub, "fetch_player_performance",
                        lambda pid, limit=20: historie.get(pid, []))
    rozliczanie.rozlicz([], [])
    return list(store["typy_log"].values())[0]


def test_superzmiana_bez_365_z_historii_statshub(monkeypatch):
    """Nusa (Norwegia–Portugalia 27.09): 0 fauli, zszedł, zmiennik dołożył
    1 — u Superbetu to wygrana (superzmiana), a mecz nie ma 365."""
    rec = _rec_zawodniczy(rynek_kod="fouls_committed", linia=0.5,
                          bukmacher="Superbet",
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _rozlicz_z_historiami(monkeypatch, rec, {
        777: [_wiersz(rec["mecz_id"], 70, fouls=0, substitutedIn=555)],
        555: [_wiersz(rec["mecz_id"], 20, fouls=1, substitutedOut=777)],
    })
    assert w["wynik"] == "wygrany" and w["faktyczna"] == 1.0
    assert w.get("superzmiana") and "superzmiana" in w["powod"]


def test_betclic_bez_superzmiany(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="fouls_committed", linia=0.5,
                          bukmacher="Betclic",
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _rozlicz_z_historiami(monkeypatch, rec, {
        777: [_wiersz(rec["mecz_id"], 70, fouls=0, substitutedIn=555)],
        555: [_wiersz(rec["mecz_id"], 20, fouls=1, substitutedOut=777)],
    })
    assert w["wynik"] == "przegrany" and not w.get("superzmiana")


def test_superzmiana_nie_rusza_gdy_zmiennik_nic_nie_dolozyl(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="fouls_committed", linia=0.5,
                          bukmacher="Superbet",
                          kickoff_ts=int(time.time()) - 8 * 3600)
    w = _rozlicz_z_historiami(monkeypatch, rec, {
        777: [_wiersz(rec["mecz_id"], 70, fouls=0, substitutedIn=555)],
        555: [_wiersz(rec["mecz_id"], 20, fouls=0, substitutedOut=777)],
    })
    assert w["wynik"] == "przegrany"
