"""Lekkie klucze nowej strony (redesign 7B) – `jobs/lekkie_klucze.py`."""

import json

from footstats.jobs import lekkie_klucze as L


def _znajdz(gracze: dict, nazwa: str) -> dict:
    return gracze.get(nazwa) or {}


def test_mecze_dostaja_numery_druzyn_i_podsumowanie_oferty():
    mecze = {7: {"id": 7, "gospodarz": "A", "gosc": "B"},
             8: {"id": 8, "gospodarz": "C", "gosc": "D"}}
    ev = {7: {"homeTeamId": 11, "awayTeamId": 12, "uniqueTournamentId": 17},
          8: {"homeTeamId": 13, "awayTeamId": None,
              "tournament": {"uniqueTournamentId": 8}}}
    siatka = {7: {101: {"shots": {"0.5": 1.3, "1.5": 2.4}, "fouls": {"0.5": 1.5}},
                  102: {"shots": {"0.5": 1.4}}}}
    L.uzupelnij_mecze(mecze, ev, siatka)
    assert mecze[7]["gospodarz_id"] == 11 and mecze[7]["gosc_id"] == 12
    assert mecze[7]["turniej_id"] == 17
    assert mecze[7]["oferta"] == {"zawodnicy": 2, "rynki": 2, "linie": 4}
    # brak numeru = brak pola, nigdy zero ani zgadnięta wartość
    assert "gosc_id" not in mecze[8] and mecze[8]["turniej_id"] == 8
    assert mecze[8]["oferta"] == {"zawodnicy": 0, "rynki": 0, "linie": 0}


def test_dwa_kursy_osobno_z_pelnych_ofert():
    siatka = {7: {101: {"shots": {"0.5": 1.45, "1.5": 2.6}}}}
    sb = {7: {"players": {"Jan Kowal": {"shots": {0.5: {"over": 1.4}, 1.5: {"over": 2.6}}}}}}
    bc = {7: {"players": {"Jan Kowal": {"shots": {0.5: {"over": 1.45}}}}}}
    wynik = L.siatka_dwoch_kursow(siatka, {}, {101: "Jan Kowal"}, sb, bc, _znajdz, _znajdz)
    assert wynik[7][101]["shots"] == {"0.5": [1.4, 1.45], "1.5": [2.6, None]}


def test_bez_oferty_cena_zostaje_u_wlasciciela_z_siatki():
    """Odkrywanie bywa pod inną pisownią – wtedy cena z siatki trafia do tego
    bukmachera, którego wskazuje `zrodla_grid`, a drugi kurs zostaje pusty."""
    siatka = {7: {101: {"shots": {"0.5": 1.45, "1.5": 2.6}}}}
    zrodla = {7: {101: {"shots": {"0.5": "Betclic"}}}}
    wynik = L.siatka_dwoch_kursow(siatka, zrodla, {101: "Inna Pisownia"}, {}, {}, _znajdz, _znajdz)
    assert wynik[7][101]["shots"] == {"0.5": [None, 1.45], "1.5": [2.6, None]}


def test_koszyki_kursow_zawsze_komplet():
    out = L.klucze_kursow_meczow({33: {1: {}}, "65": {2: {}}})
    assert len(out) == L.KOSZYKI_KURSOW
    assert "33" in out["kursy_m01"] and "65" in out["kursy_m01"]
    assert out["kursy_m05"] == {}


def test_zawodnicy_tylko_z_kursem_albo_typem_i_okno_10():
    players = [
        {"id": 101, "nazwa": "Jan", "pozycja": "M", "druzyna": "A", "xi": True,
         "minuty_lacznie": 900,
         "forma": {"shots": {"ostatnie": list(range(20)), "minuty": [90] * 20,
                             "rywale": ["X"] * 20, "kadra": [False] * 20,
                             "ts": list(range(20)), "srednia90": 1.2}}},
        {"id": 165, "nazwa": "Piotr", "pozycja": "D", "druzyna": "B", "forma": {}},
        {"id": 999, "nazwa": "Bez oferty", "druzyna": "C", "forma": {}},
    ]
    # kursy z pliku JSON – klucze tekstem
    kursy_dwa = json.loads(json.dumps({7: {101: {"shots": {"0.5": [1.4, 1.45]}}},
                                       9: {101: {"shots": {"0.5": [1.3, None]}}}}))
    vb = [{"podmiot_typ": "zawodnik", "podmiot_id": 165, "mecz_id": 9},
          {"podmiot_typ": "druzyna", "podmiot_id": 999, "mecz_id": 9}]
    mecze = [{"id": 7, "kickoff_ts": 2000}, {"id": 9, "kickoff_ts": 1000}]
    out = L.klucze_zawodnikow(players, kursy_dwa, vb, mecze)
    assert len([k for k in out if k.startswith("zaw_k")]) == L.KOSZYKI_ZAWODNIKOW
    jan = out["zaw_k37"][0]          # 101 % 64
    assert jan["mecz_id"] == 9       # najbliższy z dwóch meczów z kursem
    assert jan["kursy"] == {"shots": {"0.5": [1.3, None]}}
    assert jan["forma"]["shots"]["ostatnie"] == list(range(10))
    assert jan["forma"]["shots"]["srednia90"] == 1.2
    assert out["zaw_k37"][1]["id"] == 165 and out["zaw_k37"][1]["kursy"] == {}
    # typ drużynowy nie robi z drużyny zawodnika; bez kursu i typu – brak strony
    assert {z["id"] for z in out["zaw_indeks"]} == {101, 165}
    assert {"id": 165, "n": "Piotr", "d": "B", "m": 9} in out["zaw_indeks"]
