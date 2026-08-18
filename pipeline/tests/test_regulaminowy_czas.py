# -*- coding: utf-8 -*-
"""DOGRYWKA NIE ZAWIESZA ZAKŁADU — zakład liczy 90 minut.

Do 18.08 mecz z dogrywką nie rozliczał żadnego rynku drużynowego, bo
`game/stats/` podaje sumy za 120 minut. 66 typów wisiało na sześciu meczach
kwalifikacji europejskich. Gole i kartki da się odczytać dokładnie:
`stages` niosą wynik na koniec 90 minut, a `events` mają `stageId`.
"""
import pytest

from footstats.sources import scores365 as S


@pytest.fixture(autouse=True)
def _czysty_cache():
    S._scores90_cache.clear()
    S._cards90_cache.clear()
    S._et_cache.clear()
    yield
    S._scores90_cache.clear()
    S._cards90_cache.clear()
    S._et_cache.clear()


def _mecz(stages, events=None):
    return {"game": {
        "homeCompetitor": {"id": 1, "name": "Bodo Glimt", "score": 3},
        "awayCompetitor": {"id": 2, "name": "Union SG", "score": 2},
        "stages": stages,
        "events": events or [],
    }}


ETAPY_Z_DOGRYWKA = [
    {"id": 7, "name": "Halftime", "homeCompetitorScore": 0.0, "awayCompetitorScore": 0.0},
    {"id": 9, "name": "End of 90 Minutes", "homeCompetitorScore": 2.0, "awayCompetitorScore": 2.0},
    {"id": 10, "name": "Extra Time", "homeCompetitorScore": 3.0, "awayCompetitorScore": 2.0},
    {"id": 1, "name": "Current", "homeCompetitorScore": 3.0, "awayCompetitorScore": 2.0},
]


def test_gole_liczone_do_90_minuty_a_nie_po_dogrywce(monkeypatch):
    monkeypatch.setattr(S, "_get", lambda *a, **k: _mecz(ETAPY_Z_DOGRYWKA))
    assert S.game_scores_90(111) == {"bodo glimt": 2.0, "union sg": 2.0}


def test_brak_etapu_90_nie_zgaduje(monkeypatch):
    # mecz przerwany: nie wolno podstawić wyniku końcowego
    etapy = [{"id": 7, "homeCompetitorScore": 0.0, "awayCompetitorScore": 0.0}]
    monkeypatch.setattr(S, "_get", lambda *a, **k: _mecz(etapy))
    assert S.game_scores_90(112) == {}


def test_kartki_tylko_z_etapow_regulaminowych(monkeypatch):
    events = [
        {"stageId": 7, "competitorId": 1, "eventType": {"name": "Yellow Card"}},
        {"stageId": 9, "competitorId": 2, "eventType": {"name": "Yellow Card"}},
        {"stageId": 9, "competitorId": 2, "eventType": {"name": "Red Card"}},
        {"stageId": 10, "competitorId": 1, "eventType": {"name": "Yellow Card"}},
        {"stageId": 11, "competitorId": 2, "eventType": {"name": "Yellow Card"}},
        {"stageId": 9, "competitorId": 1, "eventType": {"name": "Substitution"}},
    ]
    monkeypatch.setattr(S, "_get", lambda *a, **k: _mecz(ETAPY_Z_DOGRYWKA, events))
    # dogrywka (10) i karne (11) NIE liczą się; zmiana to nie kartka
    assert S.game_team_cards_90(113) == {"bodo glimt": 1.0, "union sg": 2.0}


def test_zero_kartek_to_nie_to_samo_co_brak_zdarzen(monkeypatch):
    tylko_dogrywka = [
        {"stageId": 10, "competitorId": 1, "eventType": {"name": "Yellow Card"}},
    ]
    monkeypatch.setattr(S, "_get", lambda *a, **k: _mecz(ETAPY_Z_DOGRYWKA, tylko_dogrywka))
    # ani jedno zdarzenie regulaminowe -> brak danych, NIE zero
    assert S.game_team_cards_90(114) == {}

    czyste = [{"stageId": 9, "competitorId": 1, "eventType": {"name": "Substitution"}}]
    monkeypatch.setattr(S, "_get", lambda *a, **k: _mecz(ETAPY_Z_DOGRYWKA, czyste))
    # zdarzenia regulaminowe SĄ, kartek nie ma -> uczciwe zero
    assert S.game_team_cards_90(115) == {"bodo glimt": 0.0, "union sg": 0.0}


def test_pusta_lista_zdarzen_to_brak_danych(monkeypatch):
    monkeypatch.setattr(S, "_get", lambda *a, **k: _mecz(ETAPY_Z_DOGRYWKA, []))
    assert S.game_team_cards_90(116) == {}


def test_rynki_bez_rozbicia_zostaja_poza_zakresem():
    from footstats.jobs import rozliczanie as R
    # rożnych/strzałów/fauli endpoint statystyk nie dzieli na okresy — gdyby
    # ktoś je tu dopisał bez nowego źródła, rozliczyłby 90 minut liczbą ze 120
    assert R.MARKETY_DRUZYNOWE_90 == {"team_goals", "team_cards"}
    for mk in ("team_corners", "team_shots", "team_sot", "team_fouls"):
        assert mk not in R.MARKETY_DRUZYNOWE_90
