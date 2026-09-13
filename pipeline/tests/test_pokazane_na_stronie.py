# -*- coding: utf-8 -*-
"""Skuteczność liczy to, co REALNIE poszło na stronę (2026-09-13).

Zgłoszenie właściciela: „mają być tylko te typy, które pojawiają się realnie
na stronie w zakładkach Zawodnicy i Drużyny, reszta ma być w tle".

Skład listy dnia z 6:00 okazał się złym świadkiem: nie zna kart Drabinek
(od 11.09 każda szła do „prób") ani typów pokazanych przed swoją dobą
i zdjętych przed 6:00. Cykl zapisuje więc wprost, co wystawił na stronę.
"""

from __future__ import annotations

from footstats.jobs import build_wc_fast as B
from footstats.jobs import rozliczanie as R

TERAZ = 1_789_300_000


def _typ(mecz_id=1, podmiot="Flamengo", rynek="team_corners", linia=4.5,
         strona="powyzej", ts=TERAZ + 3600, **extra):
    return {"mecz_id": mecz_id, "podmiot": podmiot, "rynek_kod": rynek,
            "linia": linia, "strona": strona, "kickoff_ts": ts,
            "kurs": 1.6, **extra}


# --- odczyt: kto jest w bilansie ---

def test_zapis_rozstrzyga_w_obie_strony():
    pokazany = _typ()
    niepokazany = _typ(podmiot="Vasco")
    # znacznik sprzed publikacji nie może wypchnąć typu, który stał na stronie
    pokazany["poza_publikacja"] = "leg_kuponu"
    stan = {"od_ts": TERAZ, "klucze": {R._klucz(pokazany): pokazany["kickoff_ts"]}}
    # skład dnia mówi odwrotnie niż zapis — wygrywa zapis
    lista = {R._doba_produktowa(niepokazany["kickoff_ts"]):
             {R._klucz_listy(niepokazany)}}
    assert R.opublikowany(pokazany, lista, stan)
    assert not R.opublikowany(niepokazany, lista, stan)


def test_mecze_sprzed_zapisu_licza_sie_po_staremu():
    stary = _typ(ts=TERAZ - 86400)
    stan = {"od_ts": TERAZ, "klucze": {}}
    assert R.opublikowany(stary, None, stan)             # bez znacznika
    stary["poza_publikacja"] = "poza_lista_dnia"
    assert not R.opublikowany(stary, None, stan)


def test_drabinka_bez_zapisu_nie_idzie_do_prob_przez_sklad_dnia():
    """Karta nie przechodzi przez listę dnia, więc skład jej nie zna."""
    karta = _typ(rynek="shots", podmiot="Haaland", linia=1.5,
                 zrodlo=R.ZRODLO_DRABINKA)
    lista = {R._doba_produktowa(karta["kickoff_ts"]): {"inny:klucz"}}
    assert R.opublikowany(karta, lista, None)
    karta["poza_publikacja"] = "cokolwiek"
    assert not R.opublikowany(karta, lista, None)


def test_skutecznosc_strumieni_liczy_drabinki_z_zapisu():
    karta = _typ(rynek="shots", podmiot="Haaland", linia=1.5,
                 zrodlo=R.ZRODLO_DRABINKA, wynik="wygrany", p_model=0.6,
                 sugestia=False, mecz="A – B", rynek_nazwa="Strzały")
    karta["rynek"] = "Strzały"
    tlo = dict(karta, podmiot="Kane")
    log = {R._klucz(karta): karta, R._klucz(tlo): tlo}
    stan = {"od_ts": TERAZ, "klucze": {R._klucz(karta): karta["kickoff_ts"]}}
    out = R.skutecznosc_strumieni(log, lista_dnia={}, pokazane=stan)
    assert out["drabinki"]["podsumowanie"]["rozliczone"] == 1
    assert out["drabinki"]["podsumowanie"]["poza_n"] == 1


# --- zapis: co cykl dopisuje ---

def test_klucze_pokazane_bierze_liste_i_dziesiec_kart_frontu():
    lista = [_typ(), _typ(podmiot="x", sugestia=True)]
    radar = []
    drabinki = []
    for i in range(12):
        w = {"mecz_id": 100 + i, "podmiot": f"Gracz {i}", "kickoff_ts": TERAZ + 60,
             "ocena": {"miejsce": i + 1},
             "hero": {"rynek_kod": "shots", "linia": 1.5}}
        radar.append(w)
        drabinki.append(_typ(mecz_id=100 + i, podmiot=f"Gracz {i}", rynek="shots",
                             linia=1.5, zrodlo=R.ZRODLO_DRABINKA, szczebel=1))
        # drugi szczebel i pomiar nie są na karcie
        drabinki.append(_typ(mecz_id=100 + i, podmiot=f"Gracz {i}", rynek="shots",
                             linia=2.5, zrodlo=R.ZRODLO_DRABINKA, szczebel=2,
                             odrzucony=True))
    k = B.klucze_pokazane(lista, radar, drabinki, TERAZ)
    assert R._klucz(lista[0]) in k
    kart = [x for x in k if x.endswith(":drabinka")]
    assert len(kart) == B.DRABINKI_NA_STRONIE
    assert R._klucz(drabinki[0]) in k            # miejsce 1
    assert R._klucz(drabinki[-2]) not in k       # miejsce 12 — poza stroną


def test_klucz_raz_pokazany_nie_znika_a_stary_wygasa():
    s1 = B.dopisz_pokazane(None, {"a": TERAZ + 10}, TERAZ)
    assert s1["od_ts"] == TERAZ
    s2 = B.dopisz_pokazane(s1, {"b": TERAZ + 20}, TERAZ + 3600)
    assert set(s2["klucze"]) == {"a", "b"} and s2["od_ts"] == TERAZ
    s3 = B.dopisz_pokazane(s2, {}, TERAZ + (B.RETENCJA_POKAZANYCH_DNI + 1) * 86400)
    assert s3["klucze"] == {}


def test_nieudany_odczyt_nie_nadpisuje_zapisu(monkeypatch):
    zapisy = []
    monkeypatch.setattr(B.supa, "get_key_ok", lambda k: (None, False))
    monkeypatch.setattr(B.supa, "put_key", lambda k, v: zapisy.append(v) or True)
    B.zapisz_pokazane([_typ()], [], [], TERAZ)
    assert zapisy == []
