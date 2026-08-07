"""Wkład zależności zamrożony przy typie (2026-08-07).

Do dziś księga zapisywała sam WYNIK rachunku, więc po rozliczeniu dało się
powiedzieć tylko „przeszacowaliśmy o 12 pp", nigdy „bo czynnik rywala był za
mocny". Bez tego stempla uczenie może przesunąć całą prognozę naraz i nic
ponadto — a pięć mnożników kontekstu jest wpisanych ręcznie i żaden nigdy nie
został porównany z wynikiem.
"""
import time

from footstats.jobs import rozliczanie as R

CZYNNIKI = {"rywal": 0.9412, "sedzia": 1.0, "dom_wyjazd": 1.06,
            "scenariusz_meczu": 1.0203, "matchup": 0.909, "lacznie": 0.9587}


def _typ(**kw) -> dict:
    b = {
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": int(time.time()) + 7200,
        "podmiot_id": 500, "podmiot": "Drużyna", "rynek_kod": "team_corners",
        "rynek": "Rzuty rożne", "linia": 6.5, "strona": "ponizej",
        "kurs": 1.5, "p_model": 0.7,
    }
    b.update(kw)
    return b


def test_czynniki_ladują_w_ksiedze():
    log: dict = {}
    R._dopisz_nowe(log, [_typ(czynniki=CZYNNIKI)])
    rec = next(iter(log.values()))
    assert rec["czynniki"]["rywal"] == 0.941        # zaokrąglone do 3 miejsc
    assert rec["czynniki"]["dom_wyjazd"] == 1.06
    assert set(rec["czynniki"]) == set(CZYNNIKI)


def test_opisy_i_smieci_nie_wchodza():
    """`czynniki` niesie też `opisy` (teksty na kartę) — do księgi mają iść
    same liczby, inaczej rekord puchnie bez powodu."""
    log: dict = {}
    R._dopisz_nowe(log, [_typ(czynniki={**CZYNNIKI, "opisy": ["tekst"]})])
    rec = next(iter(log.values()))
    assert "opisy" not in rec["czynniki"]
    assert all(isinstance(v, float) for v in rec["czynniki"].values())


def test_typ_bez_czynnikow_nie_dostaje_pustego_pola():
    """Karta wznowiona z księgi nie ma rentgenu — pusty słownik w rekordzie
    kłamałby, że czynniki policzono i wyszły neutralne."""
    log: dict = {}
    R._dopisz_nowe(log, [_typ()])
    rec = next(iter(log.values()))
    assert "czynniki" not in rec

    log2: dict = {}
    R._dopisz_nowe(log2, [_typ(czynniki={})])
    assert "czynniki" not in next(iter(log2.values()))


def test_stempel_zamrozony_przy_pierwszej_publikacji():
    """Jak cena i szansa: czynniki mają zostać z chwili, gdy typ powstał —
    inaczej pomiar 'który czynnik się mylił' badałby inny rachunek niż ten,
    po którym typ się rozlicza."""
    log: dict = {}
    R._dopisz_nowe(log, [_typ(czynniki=CZYNNIKI)])
    R._dopisz_nowe(log, [_typ(czynniki={**CZYNNIKI, "rywal": 1.25})])
    rec = next(iter(log.values()))
    assert rec["czynniki"]["rywal"] == 0.941
