# -*- coding: utf-8 -*-
"""Druga ścieżka na półkę wysokiej szansy (2026-10-06) — drużyny 1,25–1,45
z rynku bijącego cenę, gdy model ≥ kurs. Patrz `uczony.DRUGA_SCIEZKA_POLKI`."""
import time

from footstats.jobs import build_wc_fast as B
from footstats.model import uczony

BIJA = frozenset({"team_cards|ponizej", "match_cards|ponizej"})


def _typ(i, p, kurs, typ="druzyna", rynek="team_cards", strona="ponizej", **kw):
    return {"id": i, "mecz_id": 100 + i, "mecz": f"A{i} – B{i}", "podmiot": f"D{i}",
            "podmiot_id": i, "podmiot_typ": typ, "rynek_kod": rynek, "rynek": "R",
            "linia": 2.5, "strona": strona, "kurs": kurs, "p_model": p,
            "kickoff_ts": int(time.time()) + 3 * 3600, "xi_sygnal": "official", **kw}


def test_definicja():
    assert uczony.DRUGA_SCIEZKA_POLKI == {
        "wysoka_szansa": {"druzyna": {"kurs_min": 1.25, "kurs_max": 1.45}}}


def test_przechodzi_rynek_bijacy_cene_gdy_model_co_najmniej_kurs():
    # kurs 1,37 → 1/kurs = 0,730
    t = _typ(1, 0.74, 1.37)
    assert B.przez_druga_sciezke(t, "wysoka_szansa", BIJA)
    assert not B.ponizej_progu_jakosci(t, "wysoka_szansa", BIJA)


def test_nie_przechodzi():
    assert B.ponizej_progu_jakosci(_typ(1, 0.72, 1.37), "wysoka_szansa", BIJA)          # model < kurs
    assert B.ponizej_progu_jakosci(_typ(1, 0.80, 1.37, rynek="team_goals"),
                                   "wysoka_szansa", BIJA)                                # rynek nie bije
    assert B.ponizej_progu_jakosci(_typ(1, 0.80, 1.37, strona="powyzej"),
                                   "wysoka_szansa", BIJA)                                # inna strona
    assert B.ponizej_progu_jakosci(_typ(1, 0.90, 1.47), "wysoka_szansa", BIJA)          # nad pasmem
    assert B.ponizej_progu_jakosci(_typ(1, 0.78, 1.37), "wysoka_szansa", frozenset())   # brak pomiaru
    assert B.ponizej_progu_jakosci(_typ(1, 0.78, 1.37), "wysoka_szansa", None)
    # zawodnicy tą ścieżką NIE wchodzą (test na księdze: 52%)
    zaw = _typ(1, 0.80, 1.37, typ="zawodnik", rynek="team_cards")
    assert B.ponizej_progu_jakosci(zaw, "wysoka_szansa", BIJA)


def test_granice_pasma_wlacznie():
    assert not B.ponizej_progu_jakosci(_typ(1, 0.81, 1.25), "wysoka_szansa", BIJA)
    assert not B.ponizej_progu_jakosci(_typ(1, 0.70, 1.45), "wysoka_szansa", BIJA)


def test_pierwsza_sciezka_bez_zmian():
    assert not B.ponizej_progu_jakosci({"p_model": 0.84, "kurs": 1.22}, "wysoka_szansa")
    assert B.ponizej_progu_jakosci({"p_model": 0.84, "kurs": 1.40}, "wysoka_szansa")


def test_wylaczenie_jedna_wartoscia(monkeypatch):
    monkeypatch.setattr(uczony, "DRUGA_SCIEZKA_POLKI", {})
    assert B.ponizej_progu_jakosci(_typ(1, 0.74, 1.37), "wysoka_szansa", BIJA)


def test_lista_wpuszcza_druga_sciezke(monkeypatch):
    monkeypatch.setattr(B, "juz_pokazany", lambda b: bool(b.get("pokazany_wczesniej")))
    kandydaci = [_typ(1, 0.74, 1.37),                                   # druga ścieżka
                 _typ(2, 0.74, 1.37, rynek="team_goals"),                # rynek nie bije
                 _typ(3, 0.86, 1.21, rynek="team_corners", strona="powyzej"),  # pierwsza
                 _typ(4, 0.60, 1.40, rynek="team_goals", pokazany_wczesniej=True)]
    lista, zdjete, _ = B.wybierz_liste_publikowana(kandydaci, B.szansa_z_ceną, bijace_cene=BIJA)
    assert {b["id"] for b in lista} == {1, 3, 4}
    assert set(zdjete.values()) == {"ponizej_progu_jakosci"}
    # bez pomiaru przewagi druga ścieżka milczy, reszta bez zmian
    lista2, _, _ = B.wybierz_liste_publikowana(kandydaci, B.szansa_z_ceną)
    assert {b["id"] for b in lista2} == {3, 4}
