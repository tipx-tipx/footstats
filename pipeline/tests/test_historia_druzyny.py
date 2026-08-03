"""Historia drużyny wprost ze statshuba — trzecie źródło, niezależne od ofert.

Znalezione 2026-08-04: Sparta Praga – Lyon, kwalifikacje LM, komplet kursów
i ZERO typów. Model widział dla Sparty 0 meczów w oknie czterech miesięcy
i odrzucał ją jako `za_stara_historia`. Powód: historię drużyn braliśmy
wyłącznie z `/props/team-trends`, a ten feed jest lustrem ofert bukmacherów
UK — w przerwie letniej ligi czeskiej i francuskiej stoi pusty.
`/team/{id}/performance` ma dla Sparty 9 meczów w tym oknie i 40 w ogóle.
"""
from footstats.sources import statshub


def _mecz(ts, tid_gospodarza, statystyki, wynik, tid=1, rywal_id=2,
          rywal="Rywal"):
    """Rekord w kształcie, jaki oddaje `/team/{id}/performance`."""
    u_siebie = tid_gospodarza == tid
    return {
        "event": {"id": ts, "timeStartTimestamp": str(ts), "score": wynik},
        "statistics": statystyki,
        "homeTeam": ({"id": tid, "name": "My"} if u_siebie
                     else {"id": rywal_id, "name": rywal}),
        "awayTeam": ({"id": rywal_id, "name": rywal} if u_siebie
                     else {"id": tid, "name": "My"}),
        "league": {"id": 7, "name": "Liga"},
    }


ST = {"cards": 2, "cornerKicks": 6, "fouls": 14,
      "totalShotsOnGoal": 12, "shotsOnGoal": 4}


def test_czyta_komplet_rynkow_druzynowych():
    """Ten feed ma to, czego nie ma żaden z dwóch poprzednich: gole i rożne
    RAZEM z kartkami, faulami, strzałami i celnymi."""
    rows = [_mecz(1_000 + i, 1, ST, {"home": 3, "away": 1}) for i in range(6)]
    h = statshub.historia_druzyny(1, rows)
    assert set(h) == {"team_cards", "team_corners", "team_fouls",
                      "team_shots", "team_sot", "team_goals"}
    assert h["team_corners"][0] == [6.0] * 6
    assert h["team_shots"][0] == [12.0] * 6


def test_gole_z_wyniku_a_nie_ze_statystyk():
    """`statistics` NIE ma pola `goals` — gole siedzą w wyniku meczu, więc
    trzeba wiedzieć, po której stronie graliśmy."""
    rows = [
        _mecz(1_000, 1, ST, {"home": 3, "away": 1}),   # my u siebie -> 3
        _mecz(2_000, 2, ST, {"home": 0, "away": 2}),   # my na wyjeździe -> 2
    ]
    h = statshub.historia_druzyny(1, rows)
    assert h["team_goals"][0] == [2.0, 3.0]            # od najnowszego


def test_wie_gdzie_gralismy():
    rows = [_mecz(1_000, 1, ST, {"home": 1, "away": 0}),
            _mecz(2_000, 2, ST, {"home": 1, "away": 0})]
    h = statshub.historia_druzyny(1, rows)
    assert h["team_corners"][4] == [False, True]       # nowszy = wyjazd


def test_historia_od_najnowszego():
    """Model waży próbkę czasem, więc kolejność nie jest kosmetyką."""
    rows = [_mecz(1_000, 1, {"cornerKicks": 1}, {"home": 0, "away": 0}),
            _mecz(3_000, 1, {"cornerKicks": 3}, {"home": 0, "away": 0}),
            _mecz(2_000, 1, {"cornerKicks": 2}, {"home": 0, "away": 0})]
    h = statshub.historia_druzyny(1, rows)
    assert h["team_corners"][0] == [3.0, 2.0, 1.0]
    assert h["team_corners"][1] == [3_000, 2_000, 1_000]


def test_mecz_bez_znacznika_czasu_odpada():
    """Bez daty nie da się ani zważyć próbki, ani sprawdzić świeżości."""
    rows = [_mecz(0, 1, ST, {"home": 1, "away": 0}),
            _mecz(1_000, 1, ST, {"home": 1, "away": 0})]
    assert len(statshub.historia_druzyny(1, rows)["team_corners"][0]) == 1


def test_brakujaca_statystyka_nie_daje_zera():
    """Mecz bez pomiaru to luka, nie zero — inaczej cicho zaniżalibyśmy
    średnie (ta sama zasada co przy zawodnikach, z jednym wyjątkiem
    na kartki, którego tu NIE ma)."""
    rows = [_mecz(1_000, 1, {"cornerKicks": 6}, {"home": 1, "away": 0}),
            _mecz(2_000, 1, {}, {"home": 1, "away": 0})]
    h = statshub.historia_druzyny(1, rows)
    assert h["team_corners"][0] == [6.0]
    assert "team_cards" not in h
