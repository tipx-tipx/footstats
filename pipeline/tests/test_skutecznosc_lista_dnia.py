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


# --- WIDOK ZBIORCZY liczy to samo, co zakładki strumieni (2026-08-16) ---
#
# Filtr wszedł 13.08 tylko do `skutecznosc_strumieni`, a domyślna zakładka
# Skuteczności („wszystko") czytała `skutecznosc_dzienna` liczoną z całej
# księgi. Zmierzone na produkcji 16.08: 1307 typów i −205,72 j. wobec 860
# typów i −120,52 j. na zamrożonych składach; dla 13.08 — 183 typy wobec 22.

def _rec_druzynowy(podmiot="Flamengo", wynik="przegrany", kurs=2.0):
    t = _typ(podmiot=podmiot, ts=_ts("2026-08-13", 20))
    return {
        **t, "mecz": "Flamengo – Cruzeiro", "podmiot_id": 101,
        "rynek": "Rzuty rożne drużyny", "kurs": kurs, "p_model": 0.6,
        "sugestia": False, "wynik": wynik, "opublikowano_ts": 1,
        "epoka": R.EPOKA_BIEZACA, "ekran": "druzyny",
        "rozliczono_ts": _ts("2026-08-13", 22),
    }


def _payload_skutecznosci(monkeypatch, log, lista_dnia):
    store = {"typy_log": log, "lista_dnia": lista_dnia}
    monkeypatch.setattr(R.supa, "get_key", lambda k: store.get(k))
    monkeypatch.setattr(R.supa, "get_key_ok",
                        lambda k: (store.get(k), True))
    monkeypatch.setattr(R.supa, "put_key",
                        lambda k, v: store.__setitem__(k, v) or True)
    monkeypatch.setattr(R.supa, "put_key_bezpiecznie",
                        lambda k, v, **kw: store.__setitem__(k, v) or True)
    # rozliczanie nie ma tu nic do zrobienia (rekordy już mają `wynik`),
    # ale bez tych zaślepek doszłoby do sieci — patrz conftest
    monkeypatch.setattr(R, "_snapshot_zamkniecia", lambda *a, **k: None)
    return R.rozlicz([], [])


def test_widok_zbiorczy_pomija_typy_spoza_zamrozonej_listy(monkeypatch):
    na_liscie = _rec_druzynowy(podmiot="Flamengo", wynik="wygrany")
    spoza = _rec_druzynowy(podmiot="Cruzeiro", wynik="przegrany")
    log = {R._klucz(na_liscie): na_liscie, R._klucz(spoza): spoza}
    lista = {"2026-08-13": {"klucze": [B._klucz_publikacji(na_liscie)],
                            "zamkniete_ts": _ts("2026-08-13", 6)}}
    out = _payload_skutecznosci(monkeypatch, log, lista)

    pods = out["podsumowanie"]
    assert pods["rozliczone"] == 1, "do bilansu wchodzi tylko skład dnia"
    assert pods["trafione"] == 1
    dzien = next(d for d in out["skutecznosc_dzienna"]
                 if d["dzien"] == "2026-08-13")
    assert dzien["okazje"] == 1
    assert dzien["poza_n"] == 1, "typ spoza składu ma być POLICZONY NA PRÓBĘ"

    # etykieta jest warunkiem tego, żeby `okrojDlaKlienta` wyciął ten wiersz
    # z rozwinięcia dnia — bez niej klient widziałby typ, którego na
    # ogłoszonej liście nie było, i to bez żadnego oznaczenia
    poza_wiersz = next(t for t in dzien["typy"] if t["podmiot"] == "Cruzeiro")
    assert poza_wiersz["poza_publikacja"] == "poza_lista_dnia"
    na_liscie_wiersz = next(t for t in dzien["typy"]
                            if t["podmiot"] == "Flamengo")
    assert not na_liscie_wiersz["poza_publikacja"]


def test_widok_zbiorczy_i_strumienie_licza_to_samo(monkeypatch):
    """Sedno: obie zakładki Skuteczności muszą podawać tę samą liczbę."""
    na_liscie = _rec_druzynowy(podmiot="Flamengo", wynik="wygrany")
    spoza = _rec_druzynowy(podmiot="Cruzeiro", wynik="przegrany")
    log = {R._klucz(na_liscie): na_liscie, R._klucz(spoza): spoza}
    lista = {"2026-08-13": {"klucze": [B._klucz_publikacji(na_liscie)],
                            "zamkniete_ts": _ts("2026-08-13", 6)}}
    out = _payload_skutecznosci(monkeypatch, log, lista)

    zbiorczo = out["podsumowanie"]["rozliczone"]
    strumienie = sum(s["podsumowanie"]["rozliczone"]
                     for s in out["skutecznosc_strumienie"].values())
    assert zbiorczo == strumienie == 1


def test_dzien_bez_zamrozonego_skladu_liczy_wszystko(monkeypatch):
    """Doby sprzed listy dnia zostają nietknięte — nie ma czego porównywać."""
    a = _rec_druzynowy(podmiot="Flamengo", wynik="wygrany")
    b = _rec_druzynowy(podmiot="Cruzeiro", wynik="przegrany")
    log = {R._klucz(a): a, R._klucz(b): b}
    out = _payload_skutecznosci(monkeypatch, log, {})
    assert out["podsumowanie"]["rozliczone"] == 2
