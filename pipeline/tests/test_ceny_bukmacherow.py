"""Cena u drugiego bukmachera na karcie typu (właściciel 06.10).

Stempel `kursy_bukmacherow` powstaje WYŁĄCZNIE, gdy znamy obie ceny tej
samej linii – „jak nie da się sczytać, to się nie wyświetla”.
"""

from footstats.jobs import lekkie_klucze as L


def _typ(**kw):
    t = {"mecz_id": 7, "podmiot_id": 101, "podmiot_typ": "zawodnik",
         "rynek_kod": "shots", "linia": 0.5, "strona": "powyzej", "kurs": 1.4}
    t.update(kw)
    return t


SIATKA = {7: {101: {"shots": {"0.5": [1.4, 1.45], "1.5": [2.6, None]},
                    "sot": {"0.5": [None, 2.1]},
                    "fouls_committed": {"0.5": [1.3, None, 1]},
                    "fouls_won": {"0.5": [1.2, 0]}}}}


def test_obie_ceny_daja_stempel():
    t = _typ()
    assert L.stempluj_ceny_bukmacherow([t], SIATKA) == 1
    assert t["kursy_bukmacherow"] == {"Superbet": 1.4, "Betclic": 1.45}


def test_jedna_cena_nie_daje_stempla():
    typy = [_typ(linia=1.5), _typ(rynek_kod="sot")]
    assert L.stempluj_ceny_bukmacherow(typy, SIATKA) == 0
    assert all("kursy_bukmacherow" not in t for t in typy)


def test_betclic_liczy_inaczej_nie_daje_stempla():
    t = _typ(rynek_kod="fouls_committed")
    L.stempluj_ceny_bukmacherow([t], SIATKA)
    assert "kursy_bukmacherow" not in t


def test_zero_jako_cena_nie_jest_cena():
    t = _typ(rynek_kod="fouls_won")
    L.stempluj_ceny_bukmacherow([t], SIATKA)
    assert "kursy_bukmacherow" not in t


def test_ponizej_druzynowe_sugestie_i_brak_w_siatce_bez_stempla():
    typy = [_typ(strona="ponizej"), _typ(podmiot_typ="druzyna"),
            _typ(sugestia=True), _typ(mecz_id=8), _typ(podmiot_id=999),
            _typ(mecz_id=None)]
    assert L.stempluj_ceny_bukmacherow(typy, SIATKA) == 0
    assert all("kursy_bukmacherow" not in t for t in typy)


def test_linia_jako_napis_i_liczba_calkowita():
    assert L.stempluj_ceny_bukmacherow([_typ(linia="0.5")], SIATKA) == 1
    siatka = {7: {101: {"shots": {"1.0": [1.9, 2.0]}}}}
    assert L.stempluj_ceny_bukmacherow([_typ(linia=1)], siatka) == 1


def test_stary_stempel_znika_gdy_cena_przepadla():
    """Typ wznowiony niesie stempel z poprzedniego cyklu – gdy teraz drugiej
    ceny nie ma, stary stempel nie może zostać na karcie."""
    t = _typ(linia=1.5, kursy_bukmacherow={"Superbet": 2.6, "Betclic": 2.7})
    L.stempluj_ceny_bukmacherow([t], SIATKA)
    assert "kursy_bukmacherow" not in t


def test_pusta_siatka_nie_wywraca():
    t = _typ()
    assert L.stempluj_ceny_bukmacherow([t], {}) == 0
    assert L.stempluj_ceny_bukmacherow([t], None) == 0
    assert L.stempluj_ceny_bukmacherow(None, SIATKA) == 0
