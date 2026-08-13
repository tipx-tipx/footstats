# -*- coding: utf-8 -*-
"""Skuteczność liczy ZAMROŻONĄ LISTĘ DNIA, nie całą księgę.

Zgłoszenie właściciela 13.08: „w Skuteczności tylko to, co się pojawia na
stronie, wszystko to, co jest w limicie".

Do tej pory do bilansu wchodził każdy rekord bez `poza_publikacja`. Ale typ
raz pokazany, który potem wypadł z listy (dzień się domknął, zmieniła się
wersja kalibracji), takiego znacznika NIE dostaje — i słusznie, bo księga
nie przepisuje historii. Skutek: doba 13.08 miała 24 typy w zamrożonym
składzie, a Skuteczność liczyła 146 rekordów.

Naprawa jest po stronie odczytu: gdy dzień ma zamrożony skład, do bilansu
wchodzi dokładnie ten skład. Reszta idzie do „policzonych na próbę".
"""

from __future__ import annotations

import datetime as dt

import pytest

from footstats.jobs import build_wc_fast as B
from footstats.jobs import rozliczanie as R


def _ts(dzien: str, godzina: int) -> int:
    d = dt.datetime.strptime(dzien, "%Y-%m-%d").replace(hour=godzina)
    if R.STREFA is not None:
        d = d.replace(tzinfo=R.STREFA)
    return int(d.timestamp())


def _typ(mecz_id=1, podmiot="Flamengo", rynek="team_corners",
         linia=4.5, strona="powyzej", ts=None):
    return {
        "mecz_id": mecz_id, "podmiot": podmiot, "rynek_kod": rynek,
        "linia": linia, "strona": strona,
        "kickoff_ts": ts if ts is not None else _ts("2026-08-13", 20),
    }


# --- doba produktowa musi się zgadzać z tą z build_wc_fast ---

def test_doba_produktowa_zgodna_z_selekcja():
    """Dwie kopie tej samej reguły (import w tę stronę byłby cykliczny)."""
    for dzien, godz in (("2026-08-13", 20), ("2026-08-13", 2),
                        ("2026-08-13", 6), ("2026-08-13", 5)):
        ts = _ts(dzien, godz)
        assert R._doba_produktowa(ts) == B.dzien_listy(ts), (dzien, godz)


def test_mecz_nad_ranem_nalezy_do_dnia_poprzedniego():
    assert R._doba_produktowa(_ts("2026-08-14", 2)) == "2026-08-13"
    assert R._doba_produktowa(_ts("2026-08-14", 7)) == "2026-08-14"


# --- klucz musi pasować do tego, co zapisuje lista dnia ---

def test_klucz_zgodny_z_kluczem_publikacji():
    t = _typ()
    assert R._klucz_listy(t) == B._klucz_publikacji(t)


def test_klucz_bez_sufiksu_zrodla():
    """Lista dnia trzyma klucze publikacji, które nie niosą `zrodlo`."""
    t = {**_typ(), "zrodlo": "drabinki"}
    assert ":drabinki" not in R._klucz_listy(t)


# --- sedno: co wchodzi do bilansu ---

def test_typ_z_zamrozonej_listy_wchodzi_do_bilansu():
    t = _typ()
    lista = {"2026-08-13": {B._klucz_publikacji(t)}}
    assert R.poza_zamrozona_lista(t, lista) is False


def test_typ_spoza_zamrozonej_listy_wypada_z_bilansu():
    """Sedno zgłoszenia: był w księdze bez znacznika, ale nie na liście."""
    t = _typ(podmiot="Cruzeiro")
    lista = {"2026-08-13": {B._klucz_publikacji(_typ(podmiot="Flamengo"))}}
    assert R.poza_zamrozona_lista(t, lista) is True


def test_dzien_bez_zamrozonej_listy_liczy_sie_jak_dotad():
    """Dni sprzed wdrożenia listy dnia nie mają czego porównywać."""
    t = _typ()
    assert R.poza_zamrozona_lista(t, {"2026-08-11": {"inny"}}) is False
    assert R.poza_zamrozona_lista(t, {}) is False
    assert R.poza_zamrozona_lista(t, None) is False


def test_pusta_lista_dnia_nie_kasuje_calego_dnia():
    """Wpis z pustym zbiorem kluczy traktujemy jak brak wpisu.

    Inaczej jeden nieudany zapis manifestu wyzerowałby bilans całego dnia.
    """
    t = _typ()
    assert R.poza_zamrozona_lista(t, {"2026-08-13": set()}) is False


def test_typ_bez_kickoffu_nie_wypada():
    t = {**_typ(), "kickoff_ts": None}
    lista = {"2026-08-13": {B._klucz_publikacji(_typ())}}
    assert R.poza_zamrozona_lista(t, lista) is False


def test_wczytaj_liste_dnia_przyjmuje_oba_ksztalty(monkeypatch):
    """Manifest bywa {dzień: {klucze: [...]}} albo {dzień: [...]}."""
    monkeypatch.setattr(R.supa, "get_key", lambda k: {
        "2026-08-12": {"klucze": ["a", "b"], "zamkniete_ts": 1},
        "2026-08-13": ["c"],
        "2026-08-14": {"klucze": []},
    })
    out = R.wczytaj_liste_dnia()
    assert out["2026-08-12"] == {"a", "b"}
    assert out["2026-08-13"] == {"c"}
    assert "2026-08-14" not in out, "pusty skład to brak składu"
