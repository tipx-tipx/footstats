"""Betclic Supersub poza cennikiem i pomiar przewidywanych składów (30.09)."""

from footstats.jobs import build_wc_fast as bwf
from footstats.sources import betclic


def _oferta(rynki):
    return {"id": 1, "nazwa": "A - B", "kickoff_ts": 1, "gospodarz": "A",
            "gosc": "B", "druzyny": [], "rynki": rynki}


def _rynek(nazwa, kurs, kategoria="Statystyki"):
    return {"nazwa": nazwa, "kategoria": kategoria, "podkategoria": "Strzały",
            "zaklady": [{"nazwa": "Powyżej 1,5", "kurs": kurs, "gracze": [],
                         "podmiot": "Serge Gnabry", "sciezka": ""}]}


def test_supersub_nie_nadpisuje_zwyklej_ceny(monkeypatch):
    """Niemcy–Serbia 01.10: zwykłe 2,20, Supersub 1,85 — inna reguła
    rozliczenia, więc do cennika wchodzi tylko zwykła cena."""
    monkeypatch.setattr(betclic, "oferta_pelna", lambda i, tylko_statystyki=True: _oferta([
        _rynek("Liczba celnych strzałów zawodnika (OPTA)", 2.2),
        _rynek("Liczba celnych strzałów zawodnika (Supersub)", 1.85, "SuperSub"),
        _rynek("Liczba strzałów zawodnika (Supersub)", 1.5, "SuperSub"),
    ]))
    k = betclic.kursy_zawodnikow(1)
    gracz = k["players"]["gnabry serge"]
    assert gracz["sot"][1.5]["over"] == 2.2
    assert "shots" not in gracz              # linia tylko z Supersub — pomijana
    assert k["pominiete_supersub"] == 2


def test_pomiar_xi_zapisuje_pierwszy_przewidywany_i_ogloszony(monkeypatch):
    magazyn = {}
    monkeypatch.setattr(bwf.supa, "get_key_ok",
                        lambda k: (magazyn.get(k), True))
    monkeypatch.setattr(bwf.supa, "put_key",
                        lambda k, v: magazyn.__setitem__(k, v) or True)
    ev = [{"id": 5, "timeStartTimestamp": 2_000_000_000}]
    przew = {5: {"xi_by_team": {1: {10, 11}}, "confirmed": False,
                 "zrodlo": "statshub przewidywany"}}
    bwf._zapisz_pomiar_xi(przew, ev, 1_999_900_000)
    # drugi, inny przewidywany skład NIE nadpisuje pierwszego
    bwf._zapisz_pomiar_xi({5: {"xi_by_team": {1: {10, 12}}, "confirmed": False,
                               "zrodlo": "statshub przewidywany"}},
                          ev, 1_999_950_000)
    bwf._zapisz_pomiar_xi({5: {"xi_by_team": {1: {10, 13}}, "confirmed": True,
                               "zrodlo": "statshub oficjalny"}},
                          ev, 1_999_990_000)
    w = magazyn[bwf.POMIAR_XI_KLUCZ]["5"]
    assert w["przewidywany"] == {"1": [10, 11]}
    assert w["ogloszony"] == {"1": [10, 13]}


def test_pomiar_xi_nie_wywraca_cyklu(monkeypatch):
    def _pada(k):
        raise RuntimeError("magazyn padł")
    monkeypatch.setattr(bwf.supa, "get_key_ok", _pada)
    bwf._zapisz_pomiar_xi({5: {"xi_by_team": {}, "confirmed": False}},
                          [{"id": 5}], 1)
