"""Testy rynków drużynowych: parser team-trends + rozliczanie z 365."""

import time

from footstats.jobs import rozliczanie
from footstats.sources import scores365, statshub


def test_fetch_team_trends_mapuje_stattypes(monkeypatch):
    fixture = {"data": [
        {
            "teamId": 4481, "teamName": "France", "opponentTeamName": "Spain",
            "eventId": 1, "homeTeamId": 4481, "statType": "totalShotsOnGoal",
            "line": 12.5, "oddsType": "over",
            "recentGames": [
                {"statValue": 22, "eventTimestamp": 100, "opponentName": "Morocco"},
                {"statValue": 9, "eventTimestamp": 90, "opponentName": "Brazil"},
            ],
            "bookmakers": [{"oddsValue": 1.85}, {"oddsValue": 1.9}],
        },
        {"teamId": 4481, "teamName": "France", "eventId": 1, "homeTeamId": 4481,
         "statType": "goals", "line": 1.5,
         "recentGames": [{"statValue": 2, "eventTimestamp": 80}]},
        {"teamId": 4481, "teamName": "France", "eventId": 1, "homeTeamId": 4481,
         "statType": "cornerKicks", "line": 4.5,
         "recentGames": [{"statValue": 6, "eventTimestamp": 80}]},
        {"teamId": 4481, "eventId": 1, "statType": "possession", "line": 50.5,
         "recentGames": []},   # nieznany statType odpada
        {"teamId": 4698, "teamName": "Spain", "opponentTeamName": "France",
         "eventId": 1, "homeTeamId": 4481, "statType": "cards", "line": 1.5,
         "recentGames": [{"statValue": 2, "eventTimestamp": 50}]},
    ]}
    monkeypatch.setattr(statshub, "_get", lambda url: fixture)
    tt = statshub.fetch_team_trends([1])
    assert len(tt) == 4                      # possession odfiltrowane
    fr = tt[0]
    assert fr.market_code == "team_shots" and fr.is_home
    assert fr.counts == [22.0, 9.0] and fr.ref_odds == [1.85, 1.9]
    # kluby: gole i rożne są mapowane (sonda 2026-07-20 — to główne
    # trendy drużynowe statshub poza reprezentacjami)
    assert tt[1].market_code == "team_goals" and tt[1].counts == [2.0]
    assert tt[2].market_code == "team_corners" and tt[2].counts == [6.0]
    assert tt[3].market_code == "team_cards" and not tt[3].is_home


def _mock_supa(monkeypatch, store: dict) -> None:
    monkeypatch.setattr(
        rozliczanie.supa, "get_key", lambda k: store.get(k)
    )
    monkeypatch.setattr(
        rozliczanie.supa, "get_key_ok", lambda k: (store.get(k), True)
    )
    monkeypatch.setattr(
        rozliczanie.supa, "put_key",
        lambda k, v: store.__setitem__(k, v),
    )
    monkeypatch.setattr(
        rozliczanie.supa, "put_key_bezpiecznie",
        lambda k, v, **kw: store.__setitem__(k, v) or True,
    )


def _rec_druzynowy(**kw):
    r = {
        "mecz_id": 5, "mecz": "France – Spain",
        "kickoff_ts": int(time.time()) - 4 * 3600,
        "podmiot_id": 4481, "podmiot": "France",
        "rynek_kod": "team_fouls", "rynek": "Faule drużyny",
        "linia": 11.5, "strona": "powyzej", "kurs": 1.8, "p_model": 0.6,
        "sugestia": False, "wynik": None, "opublikowano_ts": 1,
    }
    r.update(kw)
    return r


def _przygotuj(monkeypatch, rec, aet=False, staty=None):
    store = {"typy_log": {rozliczanie._klucz(rec): rec}}
    _mock_supa(monkeypatch, store)
    monkeypatch.setattr(rozliczanie, "_gid_365", lambda r, c: 777)
    monkeypatch.setattr(scores365, "after_extra_time", lambda gid: aet)
    monkeypatch.setattr(
        scores365, "game_team_stats",
        lambda gid: staty if staty is not None else {
            "france": {"fouls": 14.0, "shots": 18.0},
            "spain": {"fouls": 9.0, "shots": 11.0},
        },
    )
    monkeypatch.setattr(
        rozliczanie, "_snapshot_zamkniecia", lambda *a, **k: None
    )
    monkeypatch.setattr(
        rozliczanie.scores365, "finished_games_by_competition", lambda *a: []
    )
    return store


def test_rozliczanie_team_fouls_wygrany(monkeypatch):
    rec = _rec_druzynowy()
    store = _przygotuj(monkeypatch, rec)
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] == "wygrany"        # 14 fauli > linia 11.5
    assert wynik["faktyczna"] == 14.0


def test_rozliczanie_team_dogrywka_czeka(monkeypatch):
    """Mecz z dogrywką: statystyki 365 obejmują 120 min — typ drużynowy
    NIE rozlicza się z nich (czeka; po terminie zamknie się jako zwrot)."""
    rec = _rec_druzynowy()
    store = _przygotuj(monkeypatch, rec, aet=True)
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] is None


def test_rozliczanie_team_zwrot_po_terminie(monkeypatch):
    rec = _rec_druzynowy(
        kickoff_ts=int(time.time()) - 3 * 86400   # dawno po terminie danych
    )
    store = _przygotuj(monkeypatch, rec, staty={})
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] == "zwrot"
    assert wynik["powod"] == "brak danych źródła"


def test_rozliczanie_team_goals_z_wyniku_meczu(monkeypatch):
    """Gole drużynowe: game/stats ich nie ma — rozliczamy z wyniku meczu
    (scores365.game_scores), nie z game_team_stats."""
    rec = _rec_druzynowy(
        rynek_kod="team_goals", rynek="Gole drużyny", linia=1.5,
    )
    store = _przygotuj(monkeypatch, rec, staty={})   # stats PUSTE — nie mogą pomóc
    monkeypatch.setattr(
        scores365, "game_scores",
        lambda gid: {"france": 2.0, "spain": 0.0},
    )
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] == "wygrany"       # 2 gole > linia 1.5
    assert wynik["faktyczna"] == 2.0


def test_rozliczanie_team_corners_z_stats(monkeypatch):
    rec = _rec_druzynowy(
        rynek_kod="team_corners", rynek="Rzuty rożne drużyny", linia=5.5,
    )
    store = _przygotuj(monkeypatch, rec, staty={
        "france": {"corners": 4.0}, "spain": {"corners": 7.0},
    })
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] == "przegrany"     # 4 rożne < linia 5.5
    assert wynik["faktyczna"] == 4.0


def test_slowniki_rynkow_druzynowych_spojne():
    """Każdy kod team_* z map źródeł ma polską nazwę i ścieżkę rozliczenia —
    rozjazd słowników między modułami to cichy KeyError w środku cyklu."""
    from footstats.jobs.build_demo import MARKET_NAMES_PL
    from footstats.sources import superbet

    kody = set(statshub.TEAM_STATTYPE_MAP.values()) | {
        c for c in superbet.TEAM_MARKET_SUFFIX.values()
        if c.startswith("team_")
    }
    for kod in kody:
        assert kod in MARKET_NAMES_PL, f"brak nazwy PL dla {kod}"
        assert kod in rozliczanie.MARKETY_DRUZYNOWE, f"brak rozliczenia {kod}"


def test_kod_rynku_druzyny_obie_konwencje_nazw():
    """Superbet nazywa rynek drużynowy na dwa sposoby — czytamy oba.

    Nazwy wzięte z żywej oferty 2026-07-27 (Rosario Central–Racing Club,
    Santos–Universidad Central Venezuela). Do tego dnia parser znał wyłącznie
    wariant „drużyna z przodu", więc strzały, celne i faule drużynowe nie
    trafiały do oferty wcale.
    """
    from footstats.sources import superbet

    kod = superbet._kod_rynku_druzyny
    H, A = "Rosario Central", "Racing Club"

    # drużyna z przodu (wariant znany od zawsze)
    assert kod("Rosario Central - liczba goli", H, A) == ("home", "team_goals")
    assert kod("Racing Club - liczba kartek", H, A) == ("away", "team_cards")
    # drużyna z tyłu, z myślnikiem
    assert kod("Liczba celnych strzałów - Racing Club", H, A) == (
        "away", "team_sot")
    assert kod("Liczba fauli - Rosario Central", H, A) == (
        "home", "team_fouls")
    # drużyna z tyłu, BEZ myślnika
    assert kod("Liczba strzałów Racing Club", H, A) == ("away", "team_shots")

    # nie nasze: rynek meczowy, combo, bramkarz, słupki
    assert kod("Liczba fauli", H, A)[1] is None
    assert kod("Rosario Central powyżej 8.5 fauli; Racing Club otrzyma kartkę",
               H, A)[1] is None
    assert kod("Racing Club - liczba obronionych strzałów przez bramkarza",
               H, A)[1] is None
    assert kod("Rosario Central - Liczba strzałów w obramowanie bramki",
               H, A)[1] is None


def test_kod_rynku_druzyny_wybiera_dluzsza_nazwe():
    """Gdy nazwa jednej drużyny jest końcówką drugiej, kurs musi trafić do
    właściwej — inaczej River Plate dostaje kursy CA River Plate."""
    from footstats.sources import superbet

    kod = superbet._kod_rynku_druzyny
    assert kod("Liczba goli - CA River Plate", "River Plate", "CA River Plate") == (
        "away", "team_goals")
    assert kod("Liczba goli - River Plate", "River Plate", "CA River Plate") == (
        "home", "team_goals")


def test_strona_zakladu_niewrazliwa_na_wielkosc_liter(monkeypatch):
    """Superbet pisze wynik raz 'poniżej', raz 'Poniżej' — musimy łapać oba.

    Zgłoszenie usera 2026-07-27 („mylisz się, że tego nie kwotują").
    Rynek istniał w ofercie, ale wynik zapisany z wielkiej litery nie ustawiał
    strony zakładu i cały rynek znikał jako `brak_kursu`. Nazwy z żywej oferty
    (Rosario Central–Racing Club, eventId 13875754).
    """
    from footstats.sources import superbet

    fixture = {"data": [{"odds": [
        # celne: wynik małą literą (ten wariant działał od zawsze)
        {"marketName": "Liczba celnych strzałów - Racing Club",
         "name": "powyżej 3.5", "price": 2.1, "status": "active",
         "specifiers": {"total": "3.5"}},
        # strzały: ten sam rynek, wynik WIELKĄ literą
        {"marketName": "Liczba strzałów Racing Club",
         "name": "Powyżej 10.5", "price": 1.8, "status": "active",
         "specifiers": {"total": "10.5"}},
        {"marketName": "Liczba strzałów Racing Club",
         "name": "Poniżej 10.5", "price": 1.9, "status": "active",
         "specifiers": {"total": "10.5"}},
    ]}]}
    monkeypatch.setattr(superbet, "_get", lambda url: fixture)
    out = superbet.fetch_stat_odds(1, "Rosario Central", "Racing Club")
    away = out["teams"]["away"]
    assert away["team_sot"][3.5]["over"] == 2.1
    assert away["team_shots"][10.5] == {"over": 1.8, "under": 1.9}
