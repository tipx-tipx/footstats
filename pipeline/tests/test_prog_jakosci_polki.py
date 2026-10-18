# -*- coding: utf-8 -*-
"""Próg jakości półki wysokiej szansy (2026-10-05, cel właściciela: 80%+
trafionych typów na stronie) — patrz `uczony.PROG_JAKOSCI_POLKI`."""
import time

from footstats.jobs import build_wc_fast as B
from footstats.model import uczony


def _typ(i, p, kurs, typ="druzyna", **kw):
    return {"id": i, "mecz_id": 100 + i, "mecz": f"A{i} – B{i}", "podmiot": f"D{i}",
            "podmiot_id": i, "podmiot_typ": typ, "rynek_kod": "team_corners" if typ == "druzyna" else "shots",
            "rynek": "R", "linia": 4.5, "strona": "powyzej", "kurs": kurs,
            "p_model": p, "kickoff_ts": int(time.time()) + 3 * 3600,
            "xi_sygnal": "official", **kw}


def test_prog_definicja():
    assert uczony.PROG_JAKOSCI_POLKI["wysoka_szansa"] == {"p": 0.80, "cena": 0.75}
    assert "wyzsze_kursy" not in uczony.PROG_JAKOSCI_POLKI


def test_ponizej_progu_jakosci():
    assert not B.ponizej_progu_jakosci({"p_model": 0.84, "kurs": 1.22}, "wysoka_szansa")
    assert B.ponizej_progu_jakosci({"p_model": 0.78, "kurs": 1.22}, "wysoka_szansa")   # model
    assert B.ponizej_progu_jakosci({"p_model": 0.84, "kurs": 1.40}, "wysoka_szansa")   # cena
    # liczy szansa sprzed ściągnięcia do ceny
    assert not B.ponizej_progu_jakosci(
        {"p_model": 0.76, "p_przed_sciagnieciem": 0.83, "kurs": 1.22}, "wysoka_szansa")
    assert not B.ponizej_progu_jakosci({"p_model": 0.55, "kurs": 1.95}, "wyzsze_kursy")


def test_lista_wpuszcza_tylko_typy_nad_progiem(monkeypatch):
    monkeypatch.setattr(B, "juz_pokazany", lambda b: bool(b.get("pokazany_wczesniej")))
    kandydaci = [_typ(1, 0.86, 1.21), _typ(2, 0.74, 1.30), _typ(3, 0.84, 1.40),
                 _typ(4, 0.70, 1.33, pokazany_wczesniej=True),          # już pokazany
                 _typ(5, 0.56, 1.95)]                                    # wyższe kursy
    lista, zdjete, _ = B.wybierz_liste_publikowana(kandydaci, B.szansa_z_ceną)
    ids = {b["id"] for b in lista}
    assert ids == {1, 4, 5}
    powody = set(zdjete.values())
    assert powody == {"ponizej_progu_jakosci"}
    assert "ponizej_progu_jakosci" in B.OPISY_ZDJECIA_PL


# --- najtańsze typy drużynowe (2026-10-18, uczony.TANIE_DRUZYNY_POLKI) ---

def test_tani_typ_druzyny_definicja():
    assert B.tani_typ_druzyny({"podmiot_typ": "druzyna", "kurs": 1.22, "p_model": 0.70})
    assert B.tani_typ_druzyny({"podmiot_typ": "druzyna", "kurs": 1.20, "p_model": 0.65})
    assert not B.tani_typ_druzyny({"podmiot_typ": "druzyna", "kurs": 1.25, "p_model": 0.70})
    assert not B.tani_typ_druzyny({"podmiot_typ": "druzyna", "kurs": 1.19, "p_model": 0.70})
    assert not B.tani_typ_druzyny({"podmiot_typ": "druzyna", "kurs": 1.22, "p_model": 0.64})
    assert not B.tani_typ_druzyny({"podmiot_typ": "zawodnik", "kurs": 1.22, "p_model": 0.70})
    # szansa sprzed ściągnięcia do ceny, jak w progu jakości
    assert B.tani_typ_druzyny({"podmiot_typ": "druzyna", "kurs": 1.22,
                               "p_model": 0.60, "p_przed_sciagnieciem": 0.70})


def test_tani_typ_druzyny_przechodzi_prog_jakosci():
    b = {"podmiot_typ": "druzyna", "kurs": 1.22, "p_model": 0.70}
    assert not B.ponizej_progu_jakosci(b, "wysoka_szansa")
    # zawodnik w tym samym miejscu dalej podlega progowi
    assert B.ponizej_progu_jakosci(dict(b, podmiot_typ="zawodnik"), "wysoka_szansa")


def test_tanie_typy_jeden_na_mecz():
    kand = [_typ(1, 0.72, 1.22), _typ(2, 0.71, 1.23, mecz_id=101, linia=3.5),
            _typ(3, 0.70, 1.21, mecz_id=102)]
    lista, zdjete, _ = B.wybierz_liste_publikowana(kand, B.szansa_z_ceną)
    assert {b["id"] for b in lista} == {1, 3}       # mecz 101 tylko raz
    assert set(zdjete.values()) == {"poza_lista_dnia"}


def test_tani_nie_blokuje_zwyklego_typu_tego_meczu():
    """Limit „1 na mecz" dotyczy tylko najtańszych — typ nad progiem z tego
    samego meczu wchodzi normalnie."""
    kand = [_typ(1, 0.72, 1.22), _typ(2, 0.86, 1.22, mecz_id=101, linia=2.5)]
    lista, _zdjete, _ = B.wybierz_liste_publikowana(kand, B.szansa_z_ceną)
    assert {b["id"] for b in lista} == {1, 2}


# --- dokładanie drużyn po domknięciu doby (2026-10-18) ---

def _zamknieta_doba(b):
    return {B.dzien_listy(b["kickoff_ts"]): {"inny-klucz"}}


def test_druzyna_z_wysokiej_szansy_dochodzi_po_domknieciu():
    nowy = _typ(1, 0.86, 1.21)
    dolozone = {}
    lista, zdjete, _ = B.wybierz_liste_publikowana(
        [nowy], B.szansa_z_ceną, zamkniete=_zamknieta_doba(nowy), dolozone=dolozone)
    assert [b["id"] for b in lista] == [1]
    assert lista[0]["dolozony_po_domknieciu"] is True
    assert sum(len(v) for v in dolozone.values()) == 1


def test_po_domknieciu_druzyna_ponizej_progu_i_wyzsze_kursy_nie_dochodza():
    slaby = _typ(1, 0.74, 1.30)                 # nie przechodzi progu jakości
    drogi = _typ(2, 0.56, 1.95)                 # wyższe kursy — bez dokładania
    zamk = _zamknieta_doba(slaby)
    lista, zdjete, _ = B.wybierz_liste_publikowana(
        [slaby, drogi], B.szansa_z_ceną, zamkniete=zamk, dolozone={})
    assert lista == []
    assert set(zdjete.values()) == {"dzien_zamkniety"}


def test_po_domknieciu_tani_tez_jeden_na_mecz():
    a = _typ(1, 0.72, 1.22)
    b = _typ(2, 0.71, 1.23, mecz_id=101, linia=3.5)
    lista, _zdjete, _ = B.wybierz_liste_publikowana(
        [a, b], B.szansa_z_ceną, zamkniete=_zamknieta_doba(a), dolozone={})
    assert [x["id"] for x in lista] == [1]
