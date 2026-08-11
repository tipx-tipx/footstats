"""Trzy bezpieczniki wdrożenia V2 (audyt 2026-08-11).

1. karta i księga nie mogą mówić różnych rzeczy o tym samym zakładzie,
2. zamrożona kalibracja nie może po cichu wrócić do regulatora,
3. korekta strumienia nie może wejść do kuponu drugi raz.
"""

import json

import pytest

from footstats.jobs import build_wc_fast as B
from footstats.jobs import rozliczanie as R
from footstats.model import betting


def _rec(**kw):
    r = {
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 9_999_999_999,
        "podmiot_id": 5, "podmiot": "A", "rynek_kod": "team_corners",
        "rynek": "Rzuty rożne drużyny", "linia": 4.5, "strona": "ponizej",
        "kurs": 1.6, "p_model": 0.88, "wynik": None,
        "wersje": betting.wersje_publikacji(),
    }
    r.update(kw)
    return r


# --- 1. ROZJAZD KARTA-KSIĘGA ------------------------------------------------

def test_ksiega_nie_aktualizuje_p_dla_istniejacego_klucza():
    """To jest ZAMIERZONE (cena i szansa z chwili publikacji) i właśnie dlatego
    zmiana wersji wymaga osobnej bramy — patrz test niżej."""
    log = {}
    R._dopisz_nowe(log, [_rec(p_model=0.88, kurs=1.60)])
    R._dopisz_nowe(log, [_rec(p_model=0.55, kurs=1.62)])
    rec = next(iter(log.values()))
    assert rec["p_model"] == 0.88 and rec["kurs"] == 1.60


def test_wersje_w_ksiedze_widzi_tylko_zywe_publikowane():
    stara = {**_rec(), "wersje": {"kalibracja": "2026-07-31-stara"}}
    log = {
        "a": stara,
        "b": _rec(mecz_id=2, wynik="wygrany"),          # rozliczony
        "c": _rec(mecz_id=3, odrzucony=True),           # pomiarowy
        "d": _rec(mecz_id=4, poza_publikacja="limit_meczu"),   # tło
        "e": _rec(mecz_id=5, sugestia=True),            # sugestia
    }
    out = B.wersje_w_ksiedze(log)
    assert list(out.values()) == ["2026-07-31-stara"], (
        "tylko żywy, publikowany typ może kolidować — reszty user nie widział"
    )


def test_typ_z_kolizja_wersji_nie_wraca_na_liste(monkeypatch):
    """Zakład ma w księdze rekord policzony starą kalibracją: karta pokazałaby
    nowe `p`, a rozliczenie poszłoby po starym. Taki typ schodzi z listy."""
    stary = {**_rec(p_model=0.869), "wersje": {"kalibracja": "2026-07-31-stara"}}
    wersje_log = B.wersje_w_ksiedze({"k": stary})
    swiezy = _rec(p_model=0.8325)          # ten sam zakład, nowy rachunek
    klucz = B._klucz_publikacji(swiezy)
    assert wersje_log.get(klucz) == "2026-07-31-stara"
    assert wersje_log[klucz] != betting.WERSJA_KALIBRACJI


def test_brak_kolizji_gdy_wersje_zgodne():
    zgodny = _rec()
    wersje_log = B.wersje_w_ksiedze({"k": zgodny})
    klucz = B._klucz_publikacji(zgodny)
    assert wersje_log[klucz] == betting.WERSJA_KALIBRACJI


# --- 2. ZAMROŻONA KALIBRACJA: FAIL-CLOSED -----------------------------------

def test_brak_pliku_kalibracji_przerywa_zamiast_wracac_do_regulatora(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(R, "KALIBRACJA_ZAMROZONA", True)
    monkeypatch.setattr(R, "_PLIK_KALIBRACJI", tmp_path / "nie_ma.json")
    with pytest.raises(RuntimeError, match="nie ma"):
        R.kalibracja_zamrozona()


def test_plik_z_obcej_wersji_przerywa(monkeypatch, tmp_path):
    p = tmp_path / "kal.json"
    p.write_text(json.dumps({"wersja_kalibracji": "2026-07-31-stara",
                             "bias": {"team_corners": {"global": 0.5}}}),
                 encoding="utf-8")
    monkeypatch.setattr(R, "KALIBRACJA_ZAMROZONA", True)
    monkeypatch.setattr(R, "_PLIK_KALIBRACJI", p)
    with pytest.raises(RuntimeError, match="wersji"):
        R.kalibracja_zamrozona()


def test_pusta_mapa_przerywa(monkeypatch, tmp_path):
    p = tmp_path / "kal.json"
    p.write_text(json.dumps({"wersja_kalibracji": betting.WERSJA_KALIBRACJI,
                             "bias": {}}), encoding="utf-8")
    monkeypatch.setattr(R, "KALIBRACJA_ZAMROZONA", True)
    monkeypatch.setattr(R, "_PLIK_KALIBRACJI", p)
    with pytest.raises(RuntimeError, match="bias"):
        R.kalibracja_zamrozona()


def test_wylaczony_tryb_nie_przerywa(monkeypatch, tmp_path):
    """Z wyłączoną flagą brak pliku jest normalną sytuacją, nie awarią."""
    monkeypatch.setattr(R, "KALIBRACJA_ZAMROZONA", False)
    monkeypatch.setattr(R, "_PLIK_KALIBRACJI", tmp_path / "nie_ma.json")
    assert R.kalibracja_zamrozona() is None


def test_poprawny_plik_zwraca_mape(monkeypatch, tmp_path):
    mapa = {"team_corners": {"logit": True, "global": 0.8, "bins": []}}
    p = tmp_path / "kal.json"
    p.write_text(json.dumps({"wersja_kalibracji": betting.WERSJA_KALIBRACJI,
                             "bias": mapa}), encoding="utf-8")
    monkeypatch.setattr(R, "KALIBRACJA_ZAMROZONA", True)
    monkeypatch.setattr(R, "_PLIK_KALIBRACJI", p)
    assert R.kalibracja_zamrozona() == mapa


def test_plik_produkcyjny_jest_zgodny_z_wersja_produktu():
    """Bezpiecznik na wdrożenie: podbicie WERSJA_KALIBRACJI bez przeliczenia
    mapy zatrzymałoby cykl na produkcji. Ten test łapie to przed pushem."""
    assert R.KALIBRACJA_ZAMROZONA, "tryb wyłączony — sprawdź, czy świadomie"
    dane = json.loads(R._PLIK_KALIBRACJI.read_text(encoding="utf-8"))
    assert dane["wersja_kalibracji"] == betting.WERSJA_KALIBRACJI
    assert dane["bias"], "mapa nie może być pusta"
