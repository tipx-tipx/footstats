# -*- coding: utf-8 -*-
"""Typy nie znikają z rozliczeń (2026-09-16).

Zgłoszenie właściciela: „zniknęły typy w rozliczeniach, na pewno Hellebrand
w drabinkach z 15.09". Dwie karty z tego dnia nie miały w Skuteczności żadnego
śladu:

* Hellebrand (Korona–Górnik, strzały zza pola 0,5): grał 88 minut bez strzału,
  ale rynek zza pola miał tylko ścieżkę 365Scores, którego Ekstraklasa nie ma —
  karta wisiała bez wyniku, po tygodniu zeszłaby jako „zwrot, brak danych".
  Shotmapa statshub (ta sama, z której karta powstała) leżała gotowa.
* Saka (Ipswich–Arsenal, faule wywalczone 1,5): 0 minut → „zwrot, nie zagrał"
  — a lista dnia znała tylko wygrane, przegrane i licznik braków ze źródła.
"""

from __future__ import annotations

import time

from footstats.jobs import rozliczanie
from footstats.sources import scores365, statshub

from test_rozliczanie_multiliga import _przygotuj, _rec_zawodniczy


# --- shotmapa liczy rynki pochodne ------------------------------------------

def test_shotmapa_liczy_zza_pola_i_glowa(monkeypatch):
    sm = [
        {"playerName": "Jan Testowy", "x": 70.0, "y": 50.0, "result": "save",
         "isOnTarget": True, "isHeaded": False},          # zza pola, celny
        {"playerName": "Jan Testowy", "x": 10.0, "y": 50.0, "result": "miss",
         "isOnTarget": False, "isHeaded": True},          # w polu, głową
        {"playerName": "Ktos Inny", "x": 60.0, "y": 40.0, "result": "block",
         "isOnTarget": False, "isHeaded": False},
    ]
    monkeypatch.setattr(statshub, "fetch_event_shotmap", lambda eid: sm)
    out = statshub.player_shots_from_shotmap(1)
    jt = out["Jan Testowy"]
    assert jt["shots"] == 2 and jt["sot"] == 1
    assert jt["shots_outside_box"] == 1 and jt["sot_outside_box"] == 1
    assert jt["headed_shots"] == 1 and jt["headed_sot"] == 0
    assert out["Ktos Inny"]["shots_outside_box"] == 1


def _mecz_znany_statshubowi(monkeypatch, rec, mapa):
    """365 zna mecz (gid), ale bez mapy strzałów; statshub ma shotmapę."""
    monkeypatch.setattr(
        scores365, "finished_games_by_competition",
        lambda comp_id=None: [{"id": 4200, "home": "egzotic fc",
                               "away": "nieznani fc",
                               "ts": rec["kickoff_ts"]}],
    )
    monkeypatch.setattr(scores365, "game_player_match_stats",
                        lambda gid: {"jan testowy": {"minutes": 88.0}})
    monkeypatch.setattr(scores365, "game_player_shots", lambda gid: {})
    monkeypatch.setattr(scores365, "after_extra_time", lambda gid: False)
    monkeypatch.setattr(
        statshub, "fetch_event_result",
        lambda eid: {"home_id": 1, "away_id": 2, "home_name": "Egzotic FC",
                     "away_name": "Nieznani FC", "home_goals": 0.0,
                     "away_goals": 2.0, "extra_time": False},
    )
    monkeypatch.setattr(statshub, "player_shots_from_shotmap", lambda eid: mapa)


def test_zza_pola_rozliczone_ze_shotmapy_statshub(monkeypatch):
    rec = _rec_zawodniczy(rynek_kod="shots_outside_box",
                          rynek="Strzały zza pola karnego", linia=0.5)
    store = _przygotuj(monkeypatch, rec)
    _mecz_znany_statshubowi(monkeypatch, rec, {
        "Jan Testowy": {"shots": 3, "sot": 1, "shots_outside_box": 2,
                        "sot_outside_box": 1, "headed_shots": 0, "headed_sot": 0},
    })
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["faktyczna"] == 2.0 and wynik["wynik"] == "wygrany"


def test_hellebrand_zagral_bez_strzalu_to_przegrana_nie_wiszenie(monkeypatch):
    """Shotmapa meczu ma 16 strzałów innych zawodników, jego nie ma = 0 zza pola."""
    rec = _rec_zawodniczy(rynek_kod="shots_outside_box",
                          rynek="Strzały zza pola karnego", linia=0.5)
    store = _przygotuj(monkeypatch, rec)
    _mecz_znany_statshubowi(monkeypatch, rec, {
        "Ktos Inny": {"shots": 4, "sot": 2, "shots_outside_box": 1,
                      "sot_outside_box": 0, "headed_shots": 1, "headed_sot": 0},
    })
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] == "przegrany" and wynik["faktyczna"] == 0.0


def test_stara_shotmapa_bez_rynku_pochodnego_nie_wywraca(monkeypatch):
    """Zaślepka/starsza wersja mapy bez klucza zza pola: typ czeka, nie pada."""
    rec = _rec_zawodniczy(rynek_kod="shots_outside_box",
                          rynek="Strzały zza pola karnego", linia=0.5)
    store = _przygotuj(monkeypatch, rec)
    _mecz_znany_statshubowi(monkeypatch, rec,
                            {"Jan Testowy": {"shots": 3, "sot": 1}})
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    # zagrał, mapa kogoś zawiera, jego wpis bez rynku → dopiero wniosek „0"
    # z reguły „zagrał, źródła mecz znają" — nie KeyError
    assert wynik["wynik"] in ("przegrany", None)


def test_zero_strzalow_w_historii_domyka_zza_pola(monkeypatch):
    """Bez shotmapy, ale historia mówi 0 strzałów → 0 zza pola (podzbiór)."""
    rec = _rec_zawodniczy(rynek_kod="shots_outside_box",
                          rynek="Strzały zza pola karnego", linia=0.5,
                          kickoff_ts=int(time.time()) - 8 * 3600)
    store = _przygotuj(monkeypatch, rec)
    monkeypatch.setattr(
        statshub, "fetch_event_result",
        lambda eid: {"home_id": 1, "away_id": 2, "home_name": "Egzotic FC",
                     "away_name": "Nieznani FC", "home_goals": 0.0,
                     "away_goals": 2.0, "extra_time": False},
    )
    monkeypatch.setattr(
        statshub, "fetch_player_performance",
        lambda pid, limit=20: [{
            "events": {"id": rec["mecz_id"]},
            "player_statistics_event": {"eventId": rec["mecz_id"],
                                        "minutesPlayed": 88, "shots": 0},
        }],
    )
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] == "przegrany" and wynik["faktyczna"] == 0.0


def test_historia_z_strzalami_nie_zgaduje_zza_pola(monkeypatch):
    """2 strzały ogółem nie mówią, ile zza pola — typ czeka na shotmapę."""
    rec = _rec_zawodniczy(rynek_kod="shots_outside_box",
                          rynek="Strzały zza pola karnego", linia=0.5,
                          kickoff_ts=int(time.time()) - 8 * 3600)
    store = _przygotuj(monkeypatch, rec)
    monkeypatch.setattr(
        statshub, "fetch_event_result",
        lambda eid: {"home_id": 1, "away_id": 2, "home_name": "Egzotic FC",
                     "away_name": "Nieznani FC", "home_goals": 0.0,
                     "away_goals": 2.0, "extra_time": False},
    )
    monkeypatch.setattr(
        statshub, "fetch_player_performance",
        lambda pid, limit=20: [{
            "events": {"id": rec["mecz_id"]},
            "player_statistics_event": {"eventId": rec["mecz_id"],
                                        "minutesPlayed": 88, "shots": 2},
        }],
    )
    rozliczanie.rozlicz([], [])
    wynik = list(store["typy_log"].values())[0]
    assert wynik["wynik"] is None


# --- zwroty i typy czekające mają wiersz w liście dnia -----------------------

def _rec_dnia(**kw):
    r = {
        "mecz_id": 1, "mecz": "A – B", "podmiot": "X", "rynek_kod": "fouls_won",
        "rynek": "Faule wywalczone", "linia": 1.5, "strona": "powyzej",
        "kurs": 1.9, "p_model": 0.6, "kickoff_ts": 1789497000,
        "wynik": "wygrany", "sugestia": False,
    }
    r.update(kw)
    return r


def test_zwrot_nie_zagral_ma_wiersz_i_licznik():
    saka = _rec_dnia(podmiot="Saka", wynik="zwrot", powod="nie zagrał",
                     faktyczna=0.0)
    brak = _rec_dnia(podmiot="Y", wynik="zwrot",
                     powod=rozliczanie.POWOD_BRAK_DANYCH, faktyczna=None)
    dni = rozliczanie.skutecznosc_per_dzien(
        [_rec_dnia()], braki=[saka, brak],
    )
    d = dni[0]
    assert d["rozliczone"] == 1 and d["trafione"] == 1
    assert d["zwrot_n"] == 2 and d["brak_danych_n"] == 1
    wiersze = {t["podmiot"]: t for t in d["typy"]}
    assert wiersze["Saka"]["wynik"] == "zwrot"
    assert wiersze["Saka"]["powod"] == "nie zagrał"
    assert wiersze["Saka"]["poza_publikacja"] is None
    # kolejność: wygrane, przegrane, zwroty
    assert [t["wynik"] for t in d["typy"]] == ["wygrany", "zwrot", "zwrot"]


def test_typ_czekajacy_na_dane_ma_wiersz_bez_wyniku():
    helle = _rec_dnia(podmiot="Hellebrand", rynek_kod="shots_outside_box",
                      wynik=None)
    dni = rozliczanie.skutecznosc_per_dzien([_rec_dnia()], czekajace=[helle])
    d = dni[0]
    assert d["czeka_n"] == 1 and d["rozliczone"] == 1
    assert d["typy"][-1]["podmiot"] == "Hellebrand"
    assert d["typy"][-1]["wynik"] is None


def test_zwroty_dnia_bierze_kazdy_powod_ale_tylko_ze_strony(monkeypatch):
    monkeypatch.setattr(rozliczanie, "START_STATYSTYK", "2026-09-14")
    log = {
        "a": _rec_dnia(podmiot="Saka", wynik="zwrot", powod="nie zagrał"),
        "b": _rec_dnia(podmiot="Y", wynik="zwrot",
                       powod=rozliczanie.POWOD_BRAK_DANYCH),
        "c": _rec_dnia(podmiot="tlo", wynik="zwrot", powod="nie zagrał",
                       poza_publikacja="kwarantanna_rynku"),
        "d": _rec_dnia(podmiot="wygrany"),
    }
    z = rozliczanie._zwroty_dnia(log, None, None)
    assert sorted(r["podmiot"] for r in z) == ["Saka", "Y"]


def test_czekajace_tylko_po_koncu_meczu(monkeypatch):
    monkeypatch.setattr(rozliczanie, "START_STATYSTYK", "2026-09-14")
    now = 1789497000 + rozliczanie.CZEKA_NA_DANE_PO_S + 60
    log = {
        "a": _rec_dnia(podmiot="Hellebrand", wynik=None),
        "b": _rec_dnia(podmiot="jeszcze gra", wynik=None,
                       kickoff_ts=now - 60 * 60),
        "c": _rec_dnia(podmiot="sugestia", wynik=None, sugestia=True),
        "d": _rec_dnia(podmiot="tlo", wynik=None, poza_publikacja="limit_meczu"),
    }
    cz = rozliczanie._czekajace_dnia(log, None, None, now)
    assert [r["podmiot"] for r in cz] == ["Hellebrand"]


# --- strażnicy na przyszłość ---------------------------------------------------

def test_kazdy_rynek_zawodniczy_z_oferty_rozlicza_sie_bez_365():
    """Hellebrand wisiał, bo `shots_outside_box` miał TYLKO ścieżkę 365Scores.

    Ligi spoza 365 (Ekstraklasa, Championship, Saudi…) rozliczają się ze
    statshuba (shotmapa, historia zawodnika, bank trendów) albo z workera
    Sofascore. Każdy rynek, który bukmacher kwotuje, a my umiemy opublikować,
    musi mieć tam drogę — inaczej w takiej lidze zawsze skończy jako „zwrot".
    """
    from footstats.jobs import sofa_worker
    from footstats.sources import betclic, superbet

    oferta = set(superbet.PLAYER_MARKET_MAP.values()) | {
        mk for _, mk in betclic.WZORCE_RYNKOW
    }
    # kartki zawodnika: Betclic je kwotuje, ale silnik ich nie typuje (0 rekordów
    # w księdze do 14.09) — gdy wejdą do produktu, trzeba im dać ścieżkę
    oferta -= {"yellow_card"}
    poza_365 = (
        set(rozliczanie.RYNKI_SHOTMAPY)
        | set(rozliczanie.MARKETY_LIB)
        | set(rozliczanie.POLA_PERF_ROZLICZENIA)
        | set(sofa_worker.MAP_SEZON.values())
        | set(sofa_worker.RYNKI_ZAWODNIKA)
    )
    bez_drogi = sorted(oferta - poza_365)
    assert not bez_drogi, f"rynki bez rozliczenia poza 365: {bez_drogi}"


def test_rynki_pochodne_shotmapy_sa_w_rynkach_shotmapy():
    for mk in statshub.SHOTMAP_DERIVED:
        assert mk in rozliczanie.RYNKI_SHOTMAPY


def test_kontrola_lapie_pokazany_typ_bez_wiersza(monkeypatch):
    """`strona_bez_wiersza`: typ ze strony, który nie ma jak trafić do listy
    dnia (odrzucony / brak rekordu / rynek osobny), ma świecić na czerwono."""
    monkeypatch.setattr(rozliczanie, "START_STATYSTYK", "2026-09-14")
    ko = 1789497000
    now = ko + rozliczanie.MECZ_KONIEC_PO_S + 3600
    zdrowy = _rec_dnia(podmiot="ok", kickoff_ts=ko)
    odrzucony = _rec_dnia(podmiot="odrzucony", kickoff_ts=ko, odrzucony=True)
    osobny = _rec_dnia(podmiot="osobny", kickoff_ts=ko, rynek_kod="shots_blocked")
    log = {"k_ok": zdrowy, "k_odrz": odrzucony, "k_os": osobny}
    stan = {"od_ts": ko - 86400, "klucze": {
        "k_ok": ko, "k_odrz": ko, "k_os": ko, "k_brak": ko,
        # mecz jeszcze trwa — nie liczy się
        "k_trwa": now - 60,
    }}
    k = rozliczanie.kontrola_produktu(log, stan, now, wagi_ts=now)
    s = next(x for x in k["sprawdzenia"] if x["kod"] == "strona_bez_wiersza")
    assert not s["ok"] and s["liczba"] == 3
    assert "odrzucony 1" in s["opis"] and "brak_rekordu 1" in s["opis"]
    assert "rynek_osobny 1" in s["opis"]


def test_kontrola_zielona_gdy_kazdy_typ_ma_wiersz(monkeypatch):
    monkeypatch.setattr(rozliczanie, "START_STATYSTYK", "2026-09-14")
    ko = 1789497000
    now = ko + rozliczanie.MECZ_KONIEC_PO_S + 3600
    log = {
        "a": _rec_dnia(podmiot="wygrany", kickoff_ts=ko),
        "b": _rec_dnia(podmiot="zwrot", kickoff_ts=ko, wynik="zwrot",
                       powod="nie zagrał"),
        "c": _rec_dnia(podmiot="czeka", kickoff_ts=ko, wynik=None),
    }
    stan = {"od_ts": ko - 86400, "klucze": {"a": ko, "b": ko, "c": ko}}
    k = rozliczanie.kontrola_produktu(log, stan, now, wagi_ts=now)
    s = next(x for x in k["sprawdzenia"] if x["kod"] == "strona_bez_wiersza")
    assert s["ok"] and s["liczba"] == 0
