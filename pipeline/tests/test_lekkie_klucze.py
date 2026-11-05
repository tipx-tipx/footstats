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


def test_rozjazd_cen_betclica_widoczny_inna_statystyka_ukryta():
    """05.11 (Ángelo Martino, zza pola 1,5: Superbet 5,20, Betclic 12,00):
    brama mówi „ceny mocno się różnią” → cena Betclica zostaje z flagą 2;
    drabinka przesunięta (inna statystyka) → ukryta, flaga 1, jak dotąd."""
    from footstats.sources import betclic as BC
    siatka = {7: {101: {"shots_outside_box": {"0.5": 1.97, "1.5": 5.2}}}}
    sb = {7: {"players": {"Angelo Martino": {"shots_outside_box": {
        0.5: {"over": 1.97}, 1.5: {"over": 5.2}}}}}}
    bc = {7: {"players": {"Angelo Martino": {"shots_outside_box": {
        0.5: {"over": 3.0}, 1.5: {"over": 12.0}}}}}}
    wynik = L.siatka_dwoch_kursow(siatka, {}, {101: "Angelo Martino"}, sb, bc, _znajdz, _znajdz,
                                  brama_bc=BC.linie_do_scalenia,
                                  rozjazd_cen=BC.POWODY_ROZJAZDU_CEN)
    assert wynik[7][101]["shots_outside_box"] == {"0.5": [1.97, 3.0, 2], "1.5": [5.2, 12.0, 2]}
    # inna statystyka (powód spoza rozjazdu) – cena ukryta jak przed 05.11
    wynik = L.siatka_dwoch_kursow(siatka, {}, {101: "Angelo Martino"}, sb, bc, _znajdz, _znajdz,
                                  brama_bc=lambda _s, _b: ({}, "drabinka_przesunieta"),
                                  rozjazd_cen=BC.POWODY_ROZJAZDU_CEN)
    assert wynik[7][101]["shots_outside_box"] == {"0.5": [1.97, None, 1], "1.5": [5.2, None, 1]}
    # stara brama (same linie) dalej działa: pusto = ukryte
    wynik = L.siatka_dwoch_kursow(siatka, {}, {101: "Angelo Martino"}, sb, bc, _znajdz, _znajdz,
                                  brama_bc=lambda _s, _b: {})
    assert wynik[7][101]["shots_outside_box"]["1.5"] == [5.2, None, 1]


def test_rozjazd_cen_w_liniach_dnia_i_stemplach():
    kursy = {7: {1: {"shots": {"1.5": [1.5, 3.4, 2]}}}}
    players = [_zaw(1, [3, 2, 2, 3, 2, 4, 2, 2, 3, 2])]
    k = L.klucz_linii_dnia(players, kursy, [{"id": 7, "kickoff_ts": 2000}], teraz=1000)
    assert k["linie"] == [[7, 1, "shots", 1.5, 1.5, 3.4, 2]]
    typy = [{"mecz_id": 7, "podmiot_id": 1, "rynek_kod": "shots", "linia": 1.5,
             "strona": "powyzej"}]
    assert L.stempluj_ceny_bukmacherow(typy, kursy) == 1
    assert typy[0]["kursy_bukmacherow"] == {"Superbet": 1.5, "Betclic": 3.4}
    kursy[7][1]["shots"]["1.5"] = [1.5, None, 1]
    assert L.stempluj_ceny_bukmacherow(typy, kursy) == 0


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


def _zaw(pid, ost, mins=None, xi=False):
    return {"id": pid, "nazwa": f"Z{pid}", "pozycja": "F", "druzyna": "A", "xi": xi,
            "forma": {"shots": {"ostatnie": ost, "minuty": mins or [90] * len(ost)}}}


def test_linie_dnia_tylko_przyszle_mecze_cena_i_pokrycie():
    players = [_zaw(1, [3, 2, 2, 3, 2, 4, 2, 2, 3, 2]),       # 10/10 powyżej 1,5
               _zaw(2, [0, 1, 0, 2, 0, 1, 0, 0, 1, 0])]       # słabe pokrycie
    kursy = {7: {1: {"shots": {"0.5": [1.05, 1.08], "1.5": [1.40, 1.62], "2.5": [2.6, None]}},
                 2: {"shots": {"0.5": [1.9, 2.0]}}},
             8: {1: {"shots": {"1.5": [1.5, 1.5]}}}}
    mecze = [{"id": 7, "kickoff_ts": 2000}, {"id": 8, "kickoff_ts": 500}]
    k = L.klucz_linii_dnia(players, kursy, mecze, teraz=1000)
    # mecz 8 już trwa; 0,5 za tanio (1,08 < 1,30); 2,5: 3/10 – odpada; Z2 słaby
    assert k["linie"] == [[7, 1, "shots", 1.5, 1.4, 1.62]]
    # piąte pole: mecze do dymka kratek (tu bez `ts` – pusta lista)
    assert k["zaw"] == {"1": ["Z1", "F", "A", False, []]}
    assert k["forma"]["1|shots"][0][:3] == [3, 2, 2]
    assert k["w"] == 2 and k["prog"] == 0.5


def test_linie_dnia_prog_50_procent():
    # 5/10 powyżej 1,5 – wchodzi od 05.11 (było od 70%); 4/10 nie
    # (w oknie 5 obaj 2/5 – okno 5 ich nie ratuje)
    players = [_zaw(1, [0, 2, 0, 2, 0, 2, 2, 0, 2, 0]),
               _zaw(2, [0, 2, 0, 2, 0, 2, 0, 0, 2, 0])]
    kursy = {7: {1: {"shots": {"1.5": [1.9, None]}}, 2: {"shots": {"1.5": [1.9, None]}}}}
    k = L.klucz_linii_dnia(players, kursy, [{"id": 7, "kickoff_ts": 2000}], teraz=1000)
    assert k["linie"] == [[7, 1, "shots", 1.5, 1.9, None]]


def test_linie_dnia_rywale_do_dymka():
    z = _zaw(1, [3, 2, 2, 2])
    z["forma"]["shots"].update(ts=[400 * 86400, 300 * 86400, 200 * 86400, 100 * 86400],
                               rywale=["Legia", "Lech", "", "Legia"])
    # kartki: inna historia (bez meczów z dni 300 i 200) – własne pozycje
    z["forma"]["yellow_card"] = {"ostatnie": [1, 1, 1, 1, 1], "minuty": [90] * 5,
                                 "ts": [400 * 86400, 100 * 86400, 90 * 86400, 80 * 86400, 70 * 86400],
                                 "rywale": ["Legia", "Legia", "Wisła", "Lech", "Lech"]}
    kursy = {7: {1: {"shots": {"1.5": [1.5, None]}, "yellow_card": {"0.5": [3.0, None]}}}}
    k = L.klucz_linii_dnia([z], kursy, [{"id": 7, "kickoff_ts": 2000}], teraz=1000)
    assert k["druzyny"] == ["Legia", "Lech", "", "Wisła"]
    assert k["zaw"]["1"][4] == [[400, 0], [300, 1], [200, 2], [100, 0], [90, 3], [80, 1], [70, 1]]
    assert len(k["forma"]["1|shots"]) == 2              # początek listy – bez pozycji
    assert k["forma"]["1|yellow_card"][2] == [0, 3, 4, 5, 6]
    # rynek bez `ts` – kratki bez dymka, zamiast zgadywać
    del z["forma"]["shots"]["ts"]
    k = L.klucz_linii_dnia([z], kursy, [{"id": 7, "kickoff_ts": 2000}], teraz=1000)
    assert k["forma"]["1|shots"][2] is None


def test_linie_dnia_bezpiecznik_rozmiaru(monkeypatch):
    # za duży klucz przy 50% → wyższy próg (strona dostaje go w `prog`)
    players = [_zaw(1, [0, 2, 0, 2, 2, 2, 0, 2, 2, 0]),     # 6/10, w oknie 5: 3/5
               _zaw(2, [0, 2, 0, 2, 0, 2, 2, 0, 2, 0])]     # 5/10, w oknie 5: 2/5
    kursy = {7: {1: {"shots": {"1.5": [1.9, None]}}, 2: {"shots": {"1.5": [1.9, None]}}}}
    k = L.klucz_linii_dnia(players, kursy, [{"id": 7, "kickoff_ts": 2000}], teraz=1000)
    duzy = len(__import__("json").dumps(k, ensure_ascii=False, separators=(",", ":")))
    monkeypatch.setattr(L, "MAX_BAJTOW_LINII", duzy - 1)
    k = L.klucz_linii_dnia(players, kursy, [{"id": 7, "kickoff_ts": 2000}], teraz=1000)
    # 60% (= 3/5 i 6/10 – zmiennoprzecinkowo równe progowi) musi wejść
    assert k["prog"] == 0.6 and [l[1] for l in k["linie"]] == [1]


def test_linie_dnia_nie_zagral_i_betclic_inaczej():
    # 4 rozegrane z 10 (reszta bez minut) – za mało w oknie 10, ale 4/4 w oknie 5
    players = [_zaw(1, [2, 3, 0, 0, 0, 0, 0, 2, 2, 0],
                    [90, 80, 0, 0, 0, 0, 0, 90, 90, 0])]
    kursy = {7: {1: {"shots": {"1.5": [1.2, 1.9, 1]}}}}
    k = L.klucz_linii_dnia(players, kursy, [{"id": 7, "kickoff_ts": 2000}], teraz=1000)
    # Betclic liczy inaczej: jego 1,90 nie podnosi linii ponad próg ceny
    assert k["linie"] == []
    kursy = {7: {1: {"shots": {"1.5": [1.35, 1.9, 1]}}}}
    k = L.klucz_linii_dnia(players, kursy, [{"id": 7, "kickoff_ts": 2000}], teraz=1000)
    # tylko 2 rozegrane w oknie 5 – za mało; w oknie 10: 4 rozegrane – też za mało
    assert k["linie"] == []
    players = [_zaw(1, [2, 3, 2, 3, 0, 2], [90, 80, 70, 90, 0, 90])]
    k = L.klucz_linii_dnia(players, kursy, [{"id": 7, "kickoff_ts": 2000}], teraz=1000)
    assert k["linie"] == [[7, 1, "shots", 1.5, 1.35, None, 1]]
