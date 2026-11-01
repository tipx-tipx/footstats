"""Własny statshub – rozliczenia (etap 6 planu FotMob): dociąganie meczów z typami,
wiersz po nazwisku, „nie zagrał” tylko u znanego zawodnika, liczniki strzałów."""

import copy

from footstats import baza_meczow, supa
from footstats import tozsamosc as T
from footstats.jobs import rozliczanie
from footstats.sources import fotmob, statshub
from footstats.sources import wlasny_statshub as W

from test_wlasny_statshub import REK, SH_MECZ, SH_SUN, SH_XHAKA, XHAKA, _mapa, _zrodlo


def _rek_z(*dodatkowi):
    rek = copy.deepcopy(REK)
    wzor = next(z for z in rek["zawodnicy"] if z["pid"] == XHAKA)
    for pid, nazwa in dodatkowi:
        rek["zawodnicy"].append({**copy.deepcopy(wzor), "pid": pid, "name": nazwa})
    return rek


def test_wiersz_po_nazwisku_i_niejednoznacznosc():
    z = _zrodlo()
    ps = z.wiersz_meczu_po_nazwie(SH_MECZ, "Granit Xhaka")
    assert ps is not None and ps["teamId"] == SH_SUN and ps["minutesPlayed"] == 90.0
    assert z.wiersz_meczu_po_nazwie(SH_MECZ, "Ktoś Zupełnie Inny") is None
    # drugi zawodnik o nazwisku powyżej progu (Victor Hugo / Vitor Hugo) – nie zgadujemy
    z2 = _zrodlo(rek=_rek_z((990001, "Granit Xhakaa")))
    assert z2.wiersz_meczu_po_nazwie(SH_MECZ, "Granit Xhaka") is None


def test_mecz_ze_skladami_i_znany_zawodnik():
    z = _zrodlo()
    assert z.mecz_ze_skladami(SH_MECZ) and not z.mecz_ze_skladami(123)
    assert z.zna_zawodnika(SH_XHAKA) and not z.zna_zawodnika(1_142_576)
    assert z.fetch_event_result(SH_MECZ)["sklady"] is True


def _rec(pid, podmiot="Granit Xhaka", mk="fouls_won"):
    return {"podmiot_id": pid, "podmiot": podmiot, "mecz_id": SH_MECZ, "rynek_kod": mk}


def test_rozliczanie_po_numerze_po_nazwisku_i_nie_zagral_tylko_u_znanego(monkeypatch):
    z = _zrodlo()
    monkeypatch.setattr(statshub, "_WLASNE", z)
    # po numerze
    assert rozliczanie._perf_w_meczu(_rec(SH_XHAKA), {}, [0])["wasFouled"] == 3.0
    # inny numer w typie (para po nazwisku nie powstała) – wiersz po nazwisku
    assert rozliczanie._perf_w_meczu(_rec(777), {}, [0])["wasFouled"] == 3.0
    # zawodnik nieznany FotMob, którego nie ma w meczu: brak dowodu „nie zagrał”
    assert not rozliczanie._perf_pobrana(_rec(1_142_576, "Emanuel Fernandes"), {})
    # znany (ma wiersze w bazie) – brak w meczu ze składami to dowód
    assert rozliczanie._perf_pobrana(_rec(SH_XHAKA), {})


def test_liczniki_strzalow_z_wierszy_przez_przelacznik(monkeypatch):
    z = _zrodlo()
    monkeypatch.setattr(statshub, "_WLASNE", z)
    c = statshub.player_shots_from_shotmap(SH_MECZ)
    w = next(x for x in REK["zawodnicy"] if x["pid"] == XHAKA)["staty"]
    assert c["Granit Xhaka"]["shots"] == w["shots"] and c["Granit Xhaka"]["sot"] == w["sot"]
    assert c["Granit Xhaka"]["shots_outside_box"] == w["shots_outside_box"]
    assert z.rynek_mapy_w_meczu(SH_XHAKA, SH_MECZ, "headed_shots") == w["headed_shots"]
    # mecz bez mapy strzałów – rynki pochodne nieobecne (brak danych, nie zero)
    z2 = _zrodlo(rek={**REK, "mapa_strzalow": False})
    c2 = z2.player_shots_from_shotmap(SH_MECZ)
    assert "shots_outside_box" not in c2["Granit Xhaka"]
    assert z2.rynek_mapy_w_meczu(SH_XHAKA, SH_MECZ, "headed_shots") is None


def test_dociagnij_pobiera_tylko_czekajace_mecze(monkeypatch):
    t = T.Tozsamosc({"druzyny": {"8472": SH_SUN}})
    teraz = REK["ts"] + 5 * 3600
    zap = []
    monkeypatch.setattr(fotmob, "szczegoly_meczu", lambda mid: zap.append(mid) or {"mid": mid})
    monkeypatch.setattr(fotmob, "mecz_do_bazy", lambda d: (
        copy.deepcopy(REK) if d["mid"] == REK["id"] else {"id": d["mid"], "ts": REK["ts"], "status": "postponed"}))
    ksiega = {
        "a": {"mecz_id": T.zastepczy(REK["id"]), "kickoff_ts": REK["ts"]},
        "b": {"mecz_id": T.zastepczy(REK["id"]), "kickoff_ts": REK["ts"]},              # ten sam mecz raz
        "c": {"mecz_id": T.zastepczy(55), "kickoff_ts": REK["ts"]},                      # przełożony
        "d": {"mecz_id": T.zastepczy(56), "kickoff_ts": teraz - 3600},                    # za wcześnie
        "e": {"mecz_id": T.zastepczy(57), "kickoff_ts": REK["ts"], "wynik": "wygrany"},   # rozliczony
    }
    baza = {}
    zm, statusy, licz = W.dociagnij_zakonczone(t, baza, ksiega, [], {}, budzet=10, teraz=teraz)
    assert sorted(zap) == sorted([REK["id"], 55])
    assert REK["id"] in baza and baza[REK["id"]]["pobrano_ts"] == teraz
    assert zm == {baza_meczow.klucz_miesiaca(REK["ts"])}
    assert statusy[T.zastepczy(55)][0] == "postponed" and licz["status_postponed"] == 1
    # drugi przebieg: mecz ze statystykami już w bazie – zero zapytań
    zap.clear()
    W.dociagnij_zakonczone(t, baza, ksiega, [], {}, budzet=10, teraz=teraz + 1200)
    assert zap == [55]


def test_dociagnij_odmowa_konczy_bez_wyjatku(monkeypatch):
    def odmowa(mid):
        raise fotmob.FotmobOdmowa("403")
    monkeypatch.setattr(fotmob, "szczegoly_meczu", odmowa)
    ksiega = {"a": {"mecz_id": T.zastepczy(REK["id"]), "kickoff_ts": REK["ts"]}}
    zm, _, licz = W.dociagnij_zakonczone(T.Tozsamosc({}), {}, ksiega, [], {}, budzet=10, teraz=REK["ts"] + 5 * 3600)
    assert zm == set() and licz["odmowa"] == 1


def test_zapis_bazy_scala_z_wersja_zapisana_w_miedzyczasie(monkeypatch):
    k = baza_meczow.klucz_miesiaca(REK["ts"])
    obcy = {**baza_meczow.spakuj({**REK, "id": 999}), "id": 999}
    stan = {k: {"999": obcy}}
    monkeypatch.setattr(supa, "get_key_ok", lambda kl: (copy.deepcopy(stan.get(kl)), True))
    monkeypatch.setattr(supa, "put_key", lambda kl, v: stan.__setitem__(kl, v) or True)
    monkeypatch.setattr(supa, "_backend", lambda kl: None)
    baza = {}
    zm = baza_meczow.dopisz(baza, [REK])
    assert baza_meczow.zapisz(baza, zm, []) == {k: True}
    assert set(stan[k]) == {"999", str(REK["id"])}           # mecz drugiego joba przeżył


def test_mapa_meczow_odwrotnosc_po_dopisaniu():
    t = _mapa()
    assert t.mecz_fm(SH_MECZ) == REK["id"]
    t.mecze[4242] = 16_000_000
    assert t.mecz_fm(16_000_000) == 4242


def test_spalone_z_historii_tylko_na_wlasnym_zrodle(monkeypatch):
    monkeypatch.setattr(statshub, "_WLASNE", None)
    assert "offsides" not in rozliczanie.pola_perf()
    monkeypatch.setattr(statshub, "_WLASNE", _zrodlo())
    assert rozliczanie.pola_perf()["offsides"] == "totalOffside"


def test_mapa_meczow_odwrotnosc_po_skasowaniu_przez_dopasowanie():
    # cykl 41307600253: dopasuj_mecze_znane kasuje _odwr_mecze, licznik zostawał
    t = _mapa()
    assert t.mecz_fm(SH_MECZ) == REK["id"]
    t.mecze[4243] = 16_000_001
    t.__dict__.pop("_odwr_mecze", None)
    t._odwr_n = len(t.mecze)
    assert t.mecz_fm(16_000_001) == 4243
