"""Ratunek historii spoza feedu propsów: świeżość jest PER RYNEK.

Audyt 16.09: feed UK daje historię rynku tylko z meczów, w których ten rynek
kwotowano — zawodnik grający co tydzień miał świeże strzały i „0 występów"
w odbiorach. Ratunek omijał go, bo patrzył, czy CAŁY zawodnik jest martwy.
"""

from footstats.jobs import build_wc_fast as B
from footstats.sources.statshub import StatshubTrend

TERAZ = 1_800_000_000
DZIEN = 86_400


def _trend(market, dni_temu, player_id=7):
    n = len(dni_temu)
    return StatshubTrend(
        player_id=player_id, player_name="Gracz", position="M",
        team_id=100, team_name="Klub", opponent_id=200, opponent_name="Rywal",
        is_home=True, market_code=market, line=1.5, in_predicted_lineup=False,
        league_average=None, opponent_average=None, opponent_rank=None,
        total_ranks=None, event_id=999,
        counts=[1.0] * n, minutes=[90.0] * n,
        timestamps=[TERAZ - d * DZIEN for d in dni_temu],
        game_positions=["M"] * n, game_utids=[1] * n,
        game_opponent_ids=[300 + i for i in range(n)],
        game_opponents=[f"R{i}" for i in range(n)],
    )


def _swieze_z_performance(pid, name, team_id, rows, **_):
    """Performance zna wszystkie rynki z 10 ostatnich meczów."""
    return {
        mk: _trend(mk, [3, 10, 17, 24], player_id=pid)
        for mk in ("shots", "tackles", "fouls_committed")
    }


def _podepnij(monkeypatch, wywolania):
    monkeypatch.setattr(
        B.statshub, "fetch_player_performance",
        lambda pid: wywolania.append(pid) or [{"mecz": 1}],
    )
    monkeypatch.setattr(B.statshub, "trendy_z_performance", _swieze_z_performance)


def test_martwy_rynek_zawodnika_z_zywym_innym_rynkiem_jest_ratowany(monkeypatch):
    zywy = _trend("shots", [2, 9, 16, 23])          # gra co tydzień
    martwy = _trend("tackles", [200, 230, 260])      # feed nie kwotował od wiosny
    wyw: list = []
    _podepnij(monkeypatch, wyw)

    n_graczy, n_trendow = B.odswiez_stare_trendy([zywy, martwy], TERAZ)

    assert (n_graczy, n_trendow) == (1, 1)
    assert wyw == [7], "jedno zapytanie na zawodnika"
    assert B.swiezosc_proby(martwy.timestamps, martwy.minutes, TERAZ)[0] >= B.MIN_MECZE_W_OKNIE
    # żywy rynek zostaje z feedu — ma dłuższą historię niż performance
    assert zywy.timestamps == [TERAZ - d * DZIEN for d in (2, 9, 16, 23)]


def test_zawodnik_bez_martwych_rynkow_nie_kosztuje_zapytania(monkeypatch):
    wyw: list = []
    _podepnij(monkeypatch, wyw)
    trendy = [_trend("shots", [2, 9, 16]), _trend("tackles", [4, 11, 18])]
    assert B.odswiez_stare_trendy(trendy, TERAZ) == (0, 0)
    assert wyw == []


def test_rynek_pochodny_bez_shotmapy_zostaje_martwy(monkeypatch):
    """Performance nie zna strzałów zza pola — ratunek go nie zmyśla."""
    wyw: list = []
    _podepnij(monkeypatch, wyw)
    zywy = _trend("shots", [2, 9, 16, 23])
    zza_pola = _trend("shots_outside_box", [200, 230])
    assert B.odswiez_stare_trendy([zywy, zza_pola], TERAZ) == (0, 0)
    assert zza_pola.timestamps == [TERAZ - 200 * DZIEN, TERAZ - 230 * DZIEN]


def test_przy_ciasnym_budzecie_pierwszy_idzie_ten_kto_gra(monkeypatch):
    wyw: list = []
    _podepnij(monkeypatch, wyw)
    calkiem_martwy = [_trend("shots", [200, 230], player_id=1),
                      _trend("tackles", [200, 230], player_id=1)]
    mieszany = [_trend("shots", [2, 9, 16, 23], player_id=2),
                _trend("tackles", [200, 230], player_id=2)]
    B.odswiez_stare_trendy(calkiem_martwy + mieszany, TERAZ, budzet=1)
    assert wyw == [2]
