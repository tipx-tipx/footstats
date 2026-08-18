# -*- coding: utf-8 -*-
"""RYNEK WYCOFANY — rynek, którego nie umiemy ZAMKNĄĆ, nie wychodzi na produkt.

Dlaczego to ma test: `tackles` domykał się w 36,9% (pomiar 18.08 na księdze
8530 wpisów), a typ, którego nie da się rozliczyć, po siedmiu dniach idzie na
zwrot i znika z pomiaru — mimo że user go widział. Kanały są CZTERY (lista,
księga, karty, pula kuponów) i każdy ma osobną drogę wznowienia, więc brama
w jednym miejscu nie wystarcza ([[wznowione-omijaly-bramy]]).
"""
from footstats.jobs import build_wc_fast as B
from footstats.model import betting


def test_odbiory_sa_wycofane():
    assert betting.rynek_wycofany("tackles")
    assert not betting.rynek_wycofany("shots")
    assert not betting.rynek_wycofany("team_corners")
    assert not betting.rynek_wycofany(None)


def test_karta_bez_wycofanego_rynku_zostaje_nietknieta():
    w = {"rynki": [{"rynek_kod": "shots"}, {"rynek_kod": "sot"}],
         "hero": {"rynek_kod": "shots"}}
    assert B._bez_wycofanych_rynkow(w) is w      # ten sam obiekt, bez kopii


def test_karta_traci_wycofany_rynek_a_reszte_zachowuje():
    w = {"rynki": [{"rynek_kod": "shots"}, {"rynek_kod": "tackles"}],
         "hero": {"rynek_kod": "shots"}}
    out = B._bez_wycofanych_rynkow(w)
    assert [r["rynek_kod"] for r in out["rynki"]] == ["shots"]
    assert w["rynki"] and len(w["rynki"]) == 2   # wejście nietknięte


def test_karta_wylacznie_z_wycofanego_rynku_znika():
    w = {"rynki": [{"rynek_kod": "tackles"}], "hero": {"rynek_kod": "tackles"}}
    assert B._bez_wycofanych_rynkow(w) is None


def test_karta_z_hero_na_wycofanym_rynku_znika_mimo_innych_rynkow():
    # nagłówek obiecywałby typ, którego nie umiemy zamknąć
    w = {"rynki": [{"rynek_kod": "shots"}, {"rynek_kod": "tackles"}],
         "hero": {"rynek_kod": "tackles"}}
    assert B._bez_wycofanych_rynkow(w) is None


def test_wycofany_rynek_nie_wchodzi_do_rodzin_kuponu_jako_zywy():
    # rynek zostaje w maszynerii (model, kalibracja, matchup) — usuwamy go
    # z PRODUKTU, nie z kodu; ta asercja pilnuje, żeby ktoś nie "posprzątał"
    # mapy rodzin i nie wysypał kalibracji rynków defensywnych
    assert betting.RODZINY_RYNKOW["tackles"] == "defensywa"
