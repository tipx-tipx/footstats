"""Rynki z mapy strzałów (zza pola / głową) dogonione do ostatniego występu
(05.11, `build_wc_fast.dociagnij_rynki_z_mapy`). Na produkcji strzały były
świeże z FotMob, a zza pola stało na banku statshub sprzed tygodni."""
from footstats.jobs import build_wc_fast as B
from footstats.sources import statshub

DZIEN = 86400
T0 = 1_790_000_000


def _wiersz(eid, ts, strzaly, minuty=90.0):
    return {"player_statistics_event": {"eventId": eid, "teamId": 1, "minutesPlayed": minuty,
                                        "shots": strzaly, "position": "M"},
            "events": {"id": eid, "timeStartTimestamp": ts, "homeTeamId": 1, "awayTeamId": 2,
                       "uniqueTournamentId": 7, "status": "finished"},
            "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}}


# 6 meczów, od najnowszego; mecz 3 bez mapy strzałów (strzelał, rozbicia brak)
WIERSZE = [_wiersz(10 - i, T0 - i * 7 * DZIEN, s) for i, s in enumerate([2, 0, 1, 3, 1, 2])]
EXTRA = {10: {"shotsOutsideBox": 1.0}, 9: {"shotsOutsideBox": 0.0},
         7: {"shotsOutsideBox": 2.0}, 6: {"shotsOutsideBox": 0.0}, 5: {"shotsOutsideBox": 1.0}}


def _trendy(obetnij_do=None):
    tr = statshub.trendy_z_performance(77, "Jan Testowy", 1, WIERSZE, extra_meczu=EXTRA)
    if obetnij_do is not None:
        t = tr["shots_outside_box"]
        keep = [i for i, ts in enumerate(t.timestamps) if ts <= obetnij_do]
        for pole in B._POLA_HISTORII:
            v = getattr(t, pole) or []
            setattr(t, pole, [v[i] for i in keep if i < len(v)])
    return list(tr.values())


def test_opozniony_rynek_dostaje_nowsze_mecze_bez_meczu_bez_mapy():
    tr = _trendy(obetnij_do=T0 - 4 * 7 * DZIEN)          # zza pola: tylko 2 najstarsze
    zza = next(t for t in tr if t.market_code == "shots_outside_box")
    assert len(zza.counts) == 2
    licz = B.dociagnij_rynki_z_mapy(tr, fetch_performance=lambda pid: WIERSZE,
                                    extra_zawodnika=lambda pid: EXTRA)
    assert licz["trendow_odswiezonych"] >= 1
    # mecz 8 (bez mapy) nie wchodzi – brak danych, nie zero
    assert zza.timestamps == [T0, T0 - 7 * DZIEN, T0 - 3 * 7 * DZIEN, T0 - 4 * 7 * DZIEN, T0 - 5 * 7 * DZIEN]
    assert zza.counts == [1.0, 0.0, 2.0, 0.0, 1.0]


def test_rynek_na_biezaco_nie_jest_ruszany():
    tr = _trendy()
    wolania = []
    licz = B.dociagnij_rynki_z_mapy(tr, fetch_performance=lambda pid: wolania.append(pid) or WIERSZE,
                                    extra_zawodnika=lambda pid: EXTRA)
    assert not wolania and not licz


def test_bez_wlasnego_zrodla_nic_nie_robi():
    statshub.ustaw_wlasne_zrodlo(None)
    tr = _trendy(obetnij_do=T0 - 4 * 7 * DZIEN)
    assert not B.dociagnij_rynki_z_mapy(tr)


def test_extra_zawodnika_pewne_zero_gdy_nie_strzelal():
    """Mecz bez mapy, ale bez strzałów (albo bez minut) – zza pola to pewne 0,
    jak w `fetch_extra_stats`; ze strzałami – brak danych."""
    from footstats.sources import wlasny_statshub as W

    class Z:
        pass
    z = Z()
    z._historia = lambda pid: [(1, _wiersz(1, 1, 0.0), None), (2, _wiersz(2, 2, 3.0), None),
                               (3, _wiersz(3, 3, 1.0, minuty=0.0), None),
                               (4, _wiersz(4, 4, 2.0), {"shotsOutsideBox": 1.0})]
    out = W.Zrodlo.extra_zawodnika(z, 5)
    assert set(out) == {1, 3, 4}
    assert out[1]["shotsOutsideBox"] == 0.0 and out[4] == {"shotsOutsideBox": 1.0}
