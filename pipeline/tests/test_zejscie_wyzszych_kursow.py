# -*- coding: utf-8 -*-
"""Zejście półki „wyższe kursy” do 1,45 u drużyn (2026-10-06) — typ 1,45–1,80
nie miał żadnej półki. Patrz `uczony.ZEJSCIE_WYZSZYCH_KURSOW`."""
import time

from footstats.jobs import build_wc_fast as B
from footstats.model import uczony

BIJA = frozenset({"team_cards|ponizej", "team_fouls|ponizej", "team_goals|powyzej"})


def _typ(i, p, kurs, typ="druzyna", rynek="team_cards", strona="ponizej", mecz=None, **kw):
    return {"id": i, "mecz_id": mecz or 100 + i, "mecz": f"A{i} – B{i}", "podmiot": f"D{i}",
            "podmiot_id": i, "podmiot_typ": typ, "rynek_kod": rynek, "rynek": "R",
            "linia": 2.5, "strona": strona, "kurs": kurs, "p_model": p,
            "kickoff_ts": int(time.time()) + 3 * 3600, "xi_sygnal": "official", **kw}


def test_definicja():
    assert uczony.ZEJSCIE_WYZSZYCH_KURSOW == {
        "druzyna": {"kurs_min": 1.45, "kurs_max": 1.80, "limit_dobowy": 6}}


def test_polka_typu():
    assert B.polka_typu(_typ(1, 0.66, 1.62), BIJA) == ("wyzsze_kursy", True)
    assert B.polka_typu(_typ(1, 0.60, 1.62), BIJA) == (None, False)                    # model < kurs
    assert B.polka_typu(_typ(1, 0.66, 1.62, rynek="team_sot"), BIJA) == (None, False)    # rynek nie bije
    assert B.polka_typu(_typ(1, 0.66, 1.62), None) == (None, False)                     # brak pomiaru
    assert B.polka_typu(_typ(1, 0.66, 1.62, typ="zawodnik", rynek="team_cards"), BIJA)[1] is False
    # granice: 1,45 to jeszcze wysoka szansa, 1,80 to już zwykłe wyższe kursy
    assert B.polka_typu(_typ(1, 0.80, 1.45), BIJA) == ("wysoka_szansa", False)
    assert B.polka_typu(_typ(1, 0.70, 1.80), BIJA) == ("wyzsze_kursy", False)


def test_wylaczenie(monkeypatch):
    monkeypatch.setattr(uczony, "ZEJSCIE_WYZSZYCH_KURSOW", {})
    assert B.polka_typu(_typ(1, 0.66, 1.62), BIJA) == (None, False)


def test_osobny_limit_nie_zjada_wyzszych_kursow(monkeypatch):
    monkeypatch.setattr(B, "juz_pokazany", lambda b: False)
    # 9 kandydatów z TRZECH rodzin — limit 4 na rodzinę statystyk (LISTA_PER_RODZINA)
    # nie może tu zasłonić limitu zejścia
    rynki = [("team_cards", "ponizej"), ("team_fouls", "ponizej"), ("team_goals", "powyzej")]
    zejscie = [_typ(i, 0.66, 1.62, rynek=rynki[i % 3][0], strona=rynki[i % 3][1], mecz=1000 + i)
               for i in range(1, 10)]
    zwykle = [_typ(i, 0.56, 1.90, rynek=rk, strona="powyzej", mecz=2000 + i)
              for i, rk in zip(range(20, 25), ("team_corners", "team_shots", "team_sot",
                                               "team_corners", "team_shots"))]  # 5 kandydatów
    lista, zdjete, _ = B.wybierz_liste_publikowana(zejscie + zwykle, B.szansa_z_ceną,
                                                    bijace_cene=BIJA)
    z = [b for b in lista if b["kurs"] == 1.62]
    w = [b for b in lista if b["kurs"] == 1.90]
    assert len(z) == 6                      # własny limit 6
    assert len(w) == 5                      # 1,80–2,20 nietknięte
    assert all(b["polka"] == "wyzsze_kursy" for b in z + w)
    # bez pomiaru przewagi typy 1,45–1,80 dalej nie mają półki
    lista2, zdjete2, _ = B.wybierz_liste_publikowana(zejscie + zwykle, B.szansa_z_ceną)
    assert all(b["kurs"] == 1.90 for b in lista2)
    assert "kurs_poza_polkami" in set(zdjete2.values())
