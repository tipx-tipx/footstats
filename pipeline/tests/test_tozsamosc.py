"""Tożsamość FotMob → Sofascore (etap 3): nazwiska, drużyny po terminarzu,
zawodnicy w meczu, kolizje numerów FotMob, zapis i odczyt mapy."""

import itertools

import pytest

from footstats import supa
from footstats import tozsamosc as T

DZIEN = 86400
T0 = 1_790_000_000


# ------------------------------------------------------------ nazwiska ----
@pytest.mark.parametrize("a, b", [
    ("Bjørn Inge Utvik", "Bjorn Inge Utvik"),        # ø bez rozkładu w NFKD
    ("Herman Jorsett-Udnæs", "Herman Jorsett Udnaes"),
    ("Cristián Gutiérrez", "Cristian Gutierrez"),
])
def test_nazwy_po_normalizacji_rowne(a, b):
    assert T.podobienstwo_nazwisk(a, b) == 1.0


def test_podobienstwo_progi():
    assert T.podobienstwo_nazwisk("John Montaño", "John Edwin Montaño") == 0.92
    assert T.podobienstwo_nazwisk("M. Gjerstrom", "Mathias Berg Gjerstrøm") == 0.9
    assert T.podobienstwo_nazwisk("Saied Abu Farchi", "Sayed Abu Farkhi") >= T.PROG_NAZWISKA
    # dwie różne osoby z podobnym napisem nie przechodzą progu
    assert T.podobienstwo_nazwisk("Takeshi Wada", "Takashi Sawada") < T.PROG_NAZWISKA
    assert T.podobienstwo_nazwisk("Alan Vega", "Jesús Vega") < T.PROG_NAZWISKA


def test_numer_zastepczy_poza_zakresem_sofascore_i_syntetycznych():
    assert T.zastepczy(123) == 4_000_000_123
    assert T.czy_zastepczy(T.zastepczy(1)) and not T.czy_zastepczy(T.PID_SYNTETYCZNY + 5)


# -------------------------------------------------------------- drużyny ----
def _liga(fm_ids, sh_ids, start, liga_fm, utid, eid0, mid0, przesuniecie=0):
    """Pełna liga każdy z każdym (metoda kołowa): mecze FotMob i Sofascore
    tej samej ligi. Każdy mecz o innej godzinie w obrębie kolejki."""
    n = len(fm_ids)
    kolej = list(range(n))
    mecze_fm, eventy = [], {}
    eid, mid = eid0, mid0
    for runda in range(n - 1):
        for i in range(n // 2):
            a, b = kolej[i], kolej[n - 1 - i]
            if runda % 2:
                a, b = b, a
            ts = start + runda * 7 * DZIEN + i * 7200 + przesuniecie
            mecze_fm.append({"id": mid, "start_ts": ts, "home_id": fm_ids[a], "home": f"F{fm_ids[a]}",
                             "away_id": fm_ids[b], "away": f"F{fm_ids[b]}", "liga_id": liga_fm,
                             "status": "finished"})
            eventy[eid] = {"t": ts, "h": sh_ids[a], "a": sh_ids[b], "l": utid}
            eid += 1
            mid += 1
        kolej = [kolej[0]] + [kolej[-1]] + kolej[1:-1]
    return mecze_fm, eventy


def test_druzyny_po_terminarzu_i_rywalach():
    fm_a, ev_a = _liga([1, 2, 3, 4, 5, 6], [101, 102, 103, 104, 105, 106], T0, 900, 17, 1000, 5000)
    # druga liga tych samych dni, mecze w tych samych slotach co 2 h – część
    # godzin wspólna z ligą A, więc o parze rozstrzygają kolejne kolejki i rywale
    fm_b, ev_b = _liga([11, 12, 13, 14, 15, 16], [201, 202, 203, 204, 205, 206], T0, 901, 18, 2000, 6000,
                       przesuniecie=7200)
    w = T.mapuj_druzyny(fm_a + fm_b, {**ev_a, **ev_b})
    assert w["druzyny"] == {**{i: 100 + i for i in range(1, 7)}, **{10 + i: 200 + i for i in range(1, 7)}}
    assert len(w["mecze"]) == len(fm_a) + len(fm_b)
    assert w["rozgrywki"] == {900: 17, 901: 18}


def test_symetria_bez_rozstrzygniecia_to_brak_par():
    """Dwie ligi o identycznym układzie i identycznych godzinach są nie do
    rozróżnienia – wtedy nie zgadujemy (żadna para jest lepsza od złej)."""
    fm_a, ev_a = _liga([1, 2, 3, 4], [101, 102, 103, 104], T0, 900, 17, 1000, 5000)
    fm_b, ev_b = _liga([11, 12, 13, 14], [201, 202, 203, 204], T0, 901, 18, 2000, 6000)
    w = T.mapuj_druzyny(fm_a + fm_b, {**ev_a, **ev_b})
    assert all(w["druzyny"].get(f) in (None, 100 + f) for f in (1, 2, 3, 4))
    assert all(w["druzyny"].get(f) in (None, 190 + f) for f in (11, 12, 13, 14))


def test_druzyna_z_jednym_meczem_przez_pewnego_rywala():
    fm_a, ev_a = _liga([1, 2, 3, 4], [101, 102, 103, 104], T0, 900, 17, 1000, 5000)
    # puchar: drużyna 50 (Sofascore 150) gra raz z drużyną 1
    ts = T0 + 30 * DZIEN
    fm_a.append({"id": 9999, "start_ts": ts, "home_id": 50, "home": "Puchar", "away_id": 1, "away": "F1",
                 "liga_id": 777, "status": "finished"})
    ev_a[8888] = {"t": ts, "h": 150, "a": 101, "l": 99}
    w = T.mapuj_druzyny(fm_a, ev_a)
    assert w["druzyny"][50] == 150
    assert w["mecze"][9999] == 8888


def test_obca_liga_o_tej_porze_nie_dostaje_pary():
    """Liga Sofascore bez odpowiednika w FotMob, grająca o tych samych
    godzinach, nie może „przejąć” drużyn ligi, której nie ma w Sofascore."""
    fm_a, ev_a = _liga([1, 2, 3, 4], [101, 102, 103, 104], T0, 900, 17, 1000, 5000)
    fm_x, _ = _liga([21, 22, 23, 24], [0, 0, 0, 0], T0 + 3 * 3600, 902, 0, 3000, 7000)
    _, ev_y = _liga([0, 0, 0, 0], [301, 302, 303, 304], T0 + 3 * 3600, 0, 19, 4000, 8000)
    # inne pary w kolejkach: liga Y gra te same godziny, ale nie te same mecze
    for e, v in ev_y.items():
        v["h"], v["a"] = v["a"], v["h"]
    w = T.mapuj_druzyny(fm_a + fm_x, {**ev_a, **ev_y})
    assert all(f not in w["druzyny"] for f in (21, 22, 23, 24))
    assert w["druzyny"][1] == 101


def test_mecz_po_parze_mimo_przesunietej_godziny():
    fm_a, ev_a = _liga([1, 2, 3, 4, 5, 6], [101, 102, 103, 104, 105, 106], T0, 900, 17, 1000, 5000)
    m = fm_a[-1]
    m["start_ts"] += 3600        # FotMob: start godzinę później
    w = T.mapuj_druzyny(fm_a, ev_a)
    assert w["mecze"][m["id"]] == max(ev_a)


def test_dopasowanie_po_nazwie_tylko_jedyne_i_bez_sprzecznosci():
    mecze_fm = [
        {"id": 1, "start_ts": T0, "home_id": 10, "home": "Şanlıurfaspor", "away_id": 11, "away": "X",
         "status": "finished"},
        {"id": 2, "start_ts": T0, "home_id": 20, "home": "Olimpia", "away_id": 21, "away": "Y",
         "status": "finished"},
        {"id": 3, "start_ts": T0 + DZIEN, "home_id": 22, "home": "Olimpia", "away_id": 23, "away": "Z",
         "status": "finished"},
        {"id": 4, "start_ts": T0, "home_id": 30, "home": "Egypt", "away_id": 31, "away": "W",
         "status": "finished"},
    ]
    nazwy = {500: "Sanliurfaspor", 600: "Olimpia", 700: "Egypt"}
    # Egipt Sofascore grał w oknie, ale o innej porze niż Egipt FotMob – sprzeczność
    eventy = {1: {"t": T0 + 5 * 3600, "h": 700, "a": 701, "l": 1}}
    assert T.dopasuj_druzyny_po_nazwie(mecze_fm, eventy, nazwy, {}) == {10: 500}


# ------------------------------------------------------------ zawodnicy ----
def _zaw(name, team, gry=None, poz="M"):
    gry = gry or {}
    return {"name": name, "team": team, "poz": poz, "gry": gry, "ost": max(gry, default=0)}


def _rek(zawodnicy, ts=T0):
    return {"id": 1, "ts": ts, "home": {"id": 10, "name": "Dom"}, "away": {"id": 20, "name": "Gość"},
            "zawodnicy": [{"pid": pid, "name": n, "team_id": t, "minuty": mi, "poz": poz}
                          for pid, n, t, mi, poz in zawodnicy]}


def test_dubel_syntetyczny_przegrywa_z_prawdziwym():
    """Nasz numer syntetyczny ma ten mecz, prawdziwy ma długą historię – wygrywa prawdziwy."""
    zaw = {
        936901: _zaw("Sebastián Sáez", 100, {T0 - k * 7 * DZIEN: 90.0 for k in range(1, 16)}),
        955549043: _zaw("Sebastian Saez", 100, {T0: 90.0}),
    }
    w, n = T.mapuj_zawodnikow_meczu(_rek([(1, "Sebastián Sáez", 10, 90.0, "F")]), 100, 200, zaw, T.kadry(zaw))
    assert w[1][0] == 936901 and not n


def test_dwie_rozne_osoby_to_niejednoznaczne():
    zaw = {1: _zaw("Danilo Santos", 100), 2: _zaw("Danilo Pereira", 100)}
    w, n = T.mapuj_zawodnikow_meczu(_rek([(7, "Danilo", 10, 90.0, "M")]), 100, 200, zaw, T.kadry(zaw))
    assert not w and sorted(n[7]) == [1, 2]


def test_gra_w_meczu_rozstrzyga_remis_nazw():
    zaw = {1: _zaw("Danilo Santos", 100), 2: _zaw("Danilo Pereira", 100, {T0: 67.0})}
    w, _ = T.mapuj_zawodnikow_meczu(_rek([(7, "Danilo", 10, 67.0, "M")]), 100, 200, zaw, T.kadry(zaw))
    assert w[7][0] == 2


def test_zawodnik_zapisany_pod_rywalem():
    """statshub potrafi zapisać zawodnika pod drużyną rywala – kandydaci z obu kadr."""
    zaw = {5: _zaw("Bayron Oyarzo", 200)}
    w, _ = T.mapuj_zawodnikow_meczu(_rek([(9, "Bayron Oyarzo", 10, 45.0, "M")]), 100, 200, zaw, T.kadry(zaw))
    assert w[9][0] == 5


def test_pseudonim_po_jednoznacznych_minutach_i_pozycji():
    zaw = {1: _zaw("Cebolinha", 100, {T0: 73.0}, "F"), 2: _zaw("Ktoś Inny", 100, {T0: 90.0}, "D")}
    rek = _rek([(7, "Everton", 10, 73.0, "F"), (8, "Ktoś Inny", 10, 90.0, "D")])
    w, _ = T.mapuj_zawodnikow_meczu(rek, 100, 200, zaw, T.kadry(zaw))
    assert w[7][0] == 1 and w[8][0] == 2


def test_pseudonim_bez_gry_sofascore_nie_zgadujemy():
    zaw = {1: _zaw("Cebolinha", 100, {}, "F")}
    w, _ = T.mapuj_zawodnikow_meczu(_rek([(7, "Everton", 10, 73.0, "F")]), 100, 200, zaw, T.kadry(zaw))
    assert not w


def test_transfer_tylko_z_dowodem_gry():
    """Pełna nazwa jedyna w bazie, ale spoza kadr obu drużyn: bez gry Sofascore
    w tym meczu (te same minuty) – nie łączymy („Juan Pérez” jest wielu)."""
    zaw = {77: _zaw("Ally Samatta", 999)}
    idx = T.indeks_nazw(zaw)
    rek = _rek([(3, "Ally Samatta", 10, 80.0, "F")])
    assert not T.mapuj_zawodnikow_meczu(rek, 100, 200, zaw, T.kadry(zaw), indeks=idx)[0]
    zaw[77]["gry"] = {T0: 81.0}
    assert T.mapuj_zawodnikow_meczu(rek, 100, 200, zaw, T.kadry(zaw), indeks=idx)[0][3][0] == 77


def test_zajety_numer_nie_jest_proponowany():
    zaw = {1: _zaw("Jan Kowalski", 100)}
    w, _ = T.mapuj_zawodnikow_meczu(_rek([(7, "Jan Kowalski", 10, 90.0, "M")]), 100, 200, zaw,
                                    T.kadry(zaw), zajete={1})
    assert not w


# ------------------------------------------------------------ mapa ----
def _mapa():
    t = T.Tozsamosc()
    t.druzyny = {10: 100, 20: 200}
    return t


def test_kolizja_numeru_fotmob():
    """Ten sam numer FotMob, inne nazwisko (750027: Brahim Díaz / Fabricio Perez)
    – wiersz nie dokleja się do historii zmapowanej osoby."""
    zaw = {835485: _zaw("Brahim Díaz", 100), 1836754: _zaw("Fabricio Perez", 300)}
    t = _mapa()
    assert t.dodaj_mecz(_rek([(750027, "Brahim Díaz", 10, 0.0, "F")]), zaw, T.kadry(zaw))["para"] == 1
    licz = t.dodaj_mecz(_rek([(750027, "Fabricio Perez", 20, 0.0, "M")]), zaw, T.kadry(zaw))
    assert licz["kolizja_numeru"] == 1
    assert t.zawodnicy[750027] == 835485
    assert not t.wiersz_zgodny(750027, "Fabricio Perez") and t.wiersz_zgodny(750027, "Brahim Diaz")
    assert t.kolizje[750027] == ["Fabricio Perez"]


def test_zamkniety_bez_pary_oddaje_numer_osobie_z_para():
    """Ławka w Boliwii przyszła pierwsza i dostała 0 – Brahim Díaz i tak dostaje parę."""
    zaw = {835485: _zaw("Brahim Díaz", 100)}
    t = _mapa()
    t.druzyny[30] = 300
    rek_bol = {**_rek([(750027, "Fabricio Perez", 30, 0.0, "M")]),
               "home": {"id": 30, "name": "Oriente"}, "away": {"id": 31, "name": "Strongest"}}
    t.dodaj_mecz(rek_bol, zaw, T.kadry(zaw), zamknij_brak=True)
    assert t.zawodnicy[750027] == 0
    licz = t.dodaj_mecz(_rek([(750027, "Brahim Díaz", 10, 0.0, "F")]), zaw, T.kadry(zaw), zamknij_brak=True)
    assert licz["para"] == 1 and licz["kolizja_numeru"] == 1
    assert t.zawodnicy[750027] == 835485 and t.kolizje[750027] == ["Fabricio Perez"]


def test_decyzja_stala_i_zastepczy():
    zaw = {1: _zaw("Jan Kowalski", 100)}
    t = _mapa()
    t.dodaj_mecz(_rek([(7, "Jan Kowalski", 10, 90.0, "M"), (8, "Nowy Gracz", 10, 20.0, "F")]),
                 zaw, T.kadry(zaw), zamknij_brak=True)
    assert t.id_zawodnika(7) == 1 and t.id_zawodnika(8) == T.zastepczy(8)
    # później pojawia się kandydat – zamknięta decyzja się nie zmienia
    zaw[2] = _zaw("Nowy Gracz", 100)
    assert not t.dodaj_mecz(_rek([(8, "Nowy Gracz", 10, 20.0, "F")]), zaw, T.kadry(zaw))
    assert t.id_zawodnika(8) == T.zastepczy(8)


def test_druzyna_niezmapowana_bez_prob():
    zaw = {1: _zaw("Jan Kowalski", 100)}
    t = T.Tozsamosc()
    licz = t.dodaj_mecz(_rek([(7, "Jan Kowalski", 10, 90.0, "M")]), zaw, T.kadry(zaw))
    assert licz == {"bez_druzyny": 1} and 7 not in t.zawodnicy
    assert t.id_druzyny(10) == T.zastepczy(10)


def test_dodaj_druzyny_nie_zmienia_par_i_nie_dubluje():
    t = _mapa()
    n = t.dodaj_druzyny({"druzyny": {10: 555, 30: 200, 40: 400}, "mecze": {1: 11}, "rozgrywki": {5: 17}})
    assert n == 1 and t.druzyny == {10: 100, 20: 200, 40: 400}
    assert t.id_meczu(1) == 11 and t.mecz_fm(11) == 1 and t.utid(5) == 17


def test_zapis_i_odczyt_co_do_pola():
    zaw = {1: _zaw("Jan Kowalski", 100)}
    t = _mapa()
    t.dodaj_druzyny({"mecze": {1: 11}, "rozgrywki": {5: 17}})
    t.dodaj_mecz(_rek([(7, "Jan Kowalski", 10, 90.0, "M")]), zaw, T.kadry(zaw), zamknij_brak=True)
    t.kolizje[9] = ["Ktoś"]
    t.niejednoznaczne[8] = [1, 2]
    import json
    t2 = T.Tozsamosc(json.loads(json.dumps(t.do_zapisu())))
    assert t2.do_zapisu() == t.do_zapisu()


def test_wczytaj_awaria_to_brak_mapy(monkeypatch):
    monkeypatch.setattr(supa, "get_key_ok", lambda k: (None, False))
    assert T.wczytaj() == (None, False)
    monkeypatch.setattr(supa, "get_key_ok", lambda k: (None, True))
    t, ok = T.wczytaj()
    assert ok and t.druzyny == {}


def test_eventy_z_magazynu_strony():
    hd = {"101": {"m": [{"e": 5, "t": T0, "h": 1, "o": 202, "l": 17}]},
          "202": {"m": [{"e": 5, "t": T0, "h": 0, "o": 101, "l": 17}, {"e": 6, "t": 0, "h": 1, "o": 1}]}}
    assert T.eventy_z_magazynu(hd) == {5: {"t": T0, "h": 101, "a": 202, "l": 17}}


def test_nazwy_druzyn_sh_z_ksiegi_i_trendow():
    ev = {5: {"t": T0, "h": 101, "a": 202, "l": 17}}
    n = T.nazwy_druzyn_sh({"1:sot": {"team_id": 303, "team_name": "Trzecia", "opponent_id": 101,
                                     "opponent_name": "Pierwsza"}},
                          {"k": {"mecz_id": 5, "mecz": "Pierwsza FC – Druga"}}, [], ev)
    assert n == {303: "Trzecia", 101: "Pierwsza", 202: "Druga"}


def test_znane_mecze_z_zakresu_i_ksiegi_bez_zastepczych():
    zak = [{"id": 16434076, "gospodarz": "FC Bayern München", "gosc": "Borussia Dortmund", "kickoff_ts": T0},
           {"id": T.zastepczy(7), "gospodarz": "A", "gosc": "B", "kickoff_ts": T0},
           {"id": 5, "gospodarz": "Stary", "gosc": "Mecz", "kickoff_ts": T0 - 99 * 86400}]
    ks = {"k1": {"mecz_id": 16363908, "mecz": "Manchester City – Brighton & Hove Albion", "kickoff_ts": T0 + 3600},
          "k2": {"mecz_id": 16434076, "mecz": "Inna nazwa – Inna", "kickoff_ts": T0}}
    z = sorted(T.znane_mecze_sofascore(zak, ks, od_ts=T0 - 86400))
    assert z == [(16363908, T0 + 3600, "Manchester City", "Brighton & Hove Albion"),
                 (16434076, T0, "FC Bayern München", "Borussia Dortmund")]


def test_mecz_fotmob_dostaje_znany_numer_sofascore():
    t = T.Tozsamosc({"druzyny": {"9823": 2672, "9789": 2673, "8456": 17, "10204": 30}})
    nazwy = {2672: "FC Bayern München", 2673: "Borussia Dortmund", 17: "Manchester City",
             30: "Brighton & Hove Albion"}
    znane = [(16434076, T0, "FC Bayern München", "Borussia Dortmund"),
             (16363908, T0 + 7200, "Manchester City", "Brighton & Hove Albion")]
    mecze = [{"id": 1, "start_ts": T0 + 120 * 60, "home_id": 9823, "away_id": 9789},   # godzina przełożona
             {"id": 2, "start_ts": T0 + 7200, "home_id": 10204, "away_id": 8456},      # strony odwrotnie
             {"id": 3, "start_ts": T0, "home_id": 9823, "away_id": 555}]               # drużyna spoza mapy
    n, licz = T.dopasuj_mecze_znane(t, mecze, znane, nazwy)
    assert n == 1 and t.id_meczu(1) == 16434076 and t.mecz_fm(16434076) == 1
    assert t.id_meczu(2) == T.zastepczy(2) and licz["bez_znanego"] == 1 and licz["bez_druzyn"] == 1
    # numer już zajęty i mecz z parą – bez zmian; dwa dni później to inny mecz
    assert T.dopasuj_mecze_znane(t, [{"id": 4, "start_ts": T0, "home_id": 9823, "away_id": 9789}],
                                 znane, nazwy)[0] == 0
    t2 = T.Tozsamosc({"druzyny": {"9823": 2672, "9789": 2673}})
    assert T.dopasuj_mecze_znane(t2, [{"id": 5, "start_ts": T0 + 3 * 86400, "home_id": 9823, "away_id": 9789}],
                                 znane, nazwy)[0] == 0


def test_kombinacje_nazw_symetryczne():
    for a, b in itertools.combinations(["Jan Kowalski", "J. Kowalski", "Jan Maria Kowalski", "Kowalski"], 2):
        assert T.podobienstwo_nazwisk(a, b) == T.podobienstwo_nazwisk(b, a)
