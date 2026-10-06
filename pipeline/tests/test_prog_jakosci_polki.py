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
