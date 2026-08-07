"""Koncesje MIERZONE: ile drużyna dopuszcza, wprost z historii (2026-08-07).

Czynnik rywala miał dotąd dwa źródła — bank stylu i `recentGames` z feedu
propsów. To drugie jest lustrem oferty bukmacherów UK, więc dla Ekstraklasy,
kwalifikacji pucharów i części Ameryki Południowej nie istnieje. Zmierzone
07.08: komplet czynników miało 18 ze 134 kandydatów.

`opponentStatistics` przychodzi w KAŻDYM rekordzie historii drużyny i działa
w każdej lidze — czyli mamy koncesje zmierzone, a nie przybliżane, bez ani
jednego dodatkowego zapytania.
"""
from footstats.sources import statshub


def _mecz(ts, tid_gospodarza, moje, rywala, wynik, tid=1, rywal_id=2,
          rywal="Rywal"):
    u_siebie = tid_gospodarza == tid
    return {
        "event": {"id": ts, "timeStartTimestamp": str(ts), "score": wynik},
        "statistics": moje,
        "opponentStatistics": rywala,
        "homeTeam": ({"id": tid, "name": "My"} if u_siebie
                     else {"id": rywal_id, "name": rywal}),
        "awayTeam": ({"id": rywal_id, "name": rywal} if u_siebie
                     else {"id": tid, "name": "My"}),
        "league": {"id": 7, "name": "Liga"},
    }


MOJE = {"cards": 1, "cornerKicks": 7, "fouls": 9,
        "totalShotsOnGoal": 15, "shotsOnGoal": 6}
RYWALA = {"cards": 3, "cornerKicks": 2, "fouls": 16,
          "totalShotsOnGoal": 5, "shotsOnGoal": 1}


def test_czyta_komplet_rynkow_z_drugiej_strony():
    rows = [_mecz(1_000 + i, 1, MOJE, RYWALA, {"home": 2, "away": 1})
            for i in range(6)]
    k = statshub.koncesje_druzyny(1, rows)
    assert set(k) == {"team_cards", "team_corners", "team_fouls",
                      "team_shots", "team_sot", "team_goals"}
    assert k["team_corners"][0] == [2.0] * 6      # tyle rożnych DOPUŚCILIŚMY
    assert k["team_shots"][0] == [5.0] * 6


def test_nie_myli_swoich_z_cudzymi():
    """Ta sama historia czytana dwiema funkcjami musi dać różne liczby —
    inaczej cicho podstawialibyśmy własną formę pod profil rywala."""
    rows = [_mecz(1_000, 1, MOJE, RYWALA, {"home": 2, "away": 1})]
    swoje = statshub.historia_druzyny(1, rows)
    cudze = statshub.koncesje_druzyny(1, rows)
    assert swoje["team_corners"][0] == [7.0]
    assert cudze["team_corners"][0] == [2.0]


def test_gole_stracone_biora_wlasciwa_strone_wyniku():
    """Gole nie są w `statistics` — trzeba wiedzieć, po której stronie graliśmy,
    i wziąć DRUGĄ (ta sama pułapka co przy golach strzelonych)."""
    rows = [
        _mecz(1_000, 1, MOJE, RYWALA, {"home": 3, "away": 1}),   # u siebie -> 1
        _mecz(2_000, 2, MOJE, RYWALA, {"home": 4, "away": 0}),   # wyjazd  -> 4
    ]
    k = statshub.koncesje_druzyny(1, rows)
    assert k["team_goals"][0] == [4.0, 1.0]        # od najnowszego


def test_historia_od_najnowszego():
    rows = [_mecz(1_000, 1, MOJE, {"cornerKicks": 1}, {"home": 0, "away": 0}),
            _mecz(3_000, 1, MOJE, {"cornerKicks": 3}, {"home": 0, "away": 0}),
            _mecz(2_000, 1, MOJE, {"cornerKicks": 2}, {"home": 0, "away": 0})]
    k = statshub.koncesje_druzyny(1, rows)
    assert k["team_corners"][0] == [3.0, 2.0, 1.0]
    assert k["team_corners"][1] == [3_000, 2_000, 1_000]


def test_brak_statystyk_rywala_to_luka_nie_zero():
    """Mecz bez pomiaru to luka. Zero zaniżyłoby profil rywala i zrobiło
    z przeciętnej obrony twierdzę."""
    rows = [_mecz(1_000, 1, MOJE, {"cornerKicks": 4}, {"home": 1, "away": 0}),
            _mecz(2_000, 1, MOJE, {}, {"home": 1, "away": 0})]
    k = statshub.koncesje_druzyny(1, rows)
    assert k["team_corners"][0] == [4.0]
    assert "team_cards" not in k


def test_mecz_bez_znacznika_czasu_odpada():
    rows = [_mecz(0, 1, MOJE, RYWALA, {"home": 1, "away": 0}),
            _mecz(1_000, 1, MOJE, RYWALA, {"home": 1, "away": 0})]
    assert len(statshub.koncesje_druzyny(1, rows)["team_corners"][0]) == 1


def test_wie_gdzie_gralismy():
    """Kontekst „u siebie / na wyjeździe" musi zostać, bo drużyny dopuszczają
    inaczej w domu, a inaczej w gościach."""
    rows = [_mecz(1_000, 1, MOJE, RYWALA, {"home": 1, "away": 0}),
            _mecz(2_000, 2, MOJE, RYWALA, {"home": 1, "away": 0})]
    k = statshub.koncesje_druzyny(1, rows)
    assert k["team_corners"][4] == [False, True]


def test_pusta_historia_nie_wybucha():
    assert statshub.koncesje_druzyny(1, []) == {}
