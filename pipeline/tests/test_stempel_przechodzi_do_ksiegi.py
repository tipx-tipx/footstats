# -*- coding: utf-8 -*-
"""Stempel `rachunek` ma DOJECHAĆ do księgi — trzy białe listy po drodze.

⚑ PO CO OSOBNY PLIK. W tym repo pole może istnieć w rekordzie i i tak zniknąć,
bo droga typu z puli na stronę i do księgi prowadzi przez trzy miejsca, które
przepisują pola PO JEDNYM:

    build_wc_fast.rec_pewniaka        (pula -> value_bets)
    rozliczanie._dopisz_nowe          (value_bets -> księga)
    rozliczanie._kupon_leg_do_logu    (leg kuponu -> księga)

Ta pułapka zjadła już `kal_tau` i `swieze_sklady`, a wcześniej cały stempel
czynników. Testy jednostkowe samego `stempel_rachunku` tego NIE łapią — mierzą
funkcję, nie drogę. Stąd ten plik: sprawdza przejście, nie liczenie.
"""
import time

from footstats.jobs import rozliczanie as R
from footstats.model import betting


RACHUNEK = betting.stempel_rachunku(
    p_over_raw=0.61, kal_rynek=0.18, kal_strumien=-0.44, p_over_final=0.55,
)


def _typ(**nadpisz) -> dict:
    b = {
        "id": 1, "mecz_id": 100, "mecz": "A – B",
        "kickoff_ts": int(time.time()) + 7200,
        "podmiot_id": 5, "podmiot": "A", "podmiot_typ": "druzyna",
        "rynek_kod": "team_corners", "rynek": "Rzuty rożne drużyny",
        "linia": 4.5, "strona": "powyzej",
        "kurs": 1.85, "bukmacher": "Superbet",
        "p_model": 0.55, "pewnosc": "wysoka",
        "rachunek": dict(RACHUNEK),
    }
    b.update(nadpisz)
    return b


def test_rachunek_dojezdza_do_ksiegi():
    log: dict = {}
    R._dopisz_nowe(log, [_typ()])
    assert log, "typ nie trafił do księgi"
    rec = next(iter(log.values()))
    assert rec.get("rachunek") == RACHUNEK, (
        "stempel zginął w `_dopisz_nowe` — sprawdź białą listę pól"
    )


def test_rachunek_dojezdza_z_lega_kuponu():
    """Leg bywa JEDYNYM śladem po typie, który nie wszedł na listę."""
    leg = _typ()
    rec = R._kupon_leg_do_logu(leg)
    assert rec.get("rachunek") == RACHUNEK, (
        "stempel zginął w `_kupon_leg_do_logu` — sprawdź białą listę pól"
    )
    assert rec["poza_publikacja"] == "leg_kuponu"


def test_pusty_rachunek_nie_zasmieca_ksiegi():
    """Ścieżka, która stempla nie liczy, nie ma zostawiać pustego słownika —
    inaczej `stempel_kompletny` mierzyłby obecność klucza, nie wiedzy."""
    log: dict = {}
    R._dopisz_nowe(log, [_typ(rachunek={})])
    rec = next(iter(log.values()))
    assert "rachunek" not in rec

    leg = R._kupon_leg_do_logu(_typ(rachunek=None))
    assert "rachunek" not in leg


def test_kolejnosc_dojezdza_do_ksiegi():
    """⚑ 2026-08-14. `moc_listy` decyduje, kto WCHODZI na listę dnia i w jakiej
    stoi kolejności, ale jej głównego składnika — ilu kandydatów model dorobił
    się w meczu PRZED bramami — nie da się odtworzyć wstecz, bo księga zna
    tylko to, co przez bramy przeszło."""
    log: dict = {}
    kolejnosc = {"moc": 1.0234, "kandydatow": 17}
    R._dopisz_nowe(log, [_typ(kolejnosc=dict(kolejnosc))])
    rec = next(iter(log.values()))
    assert rec.get("kolejnosc") == kolejnosc, (
        "stempel kolejności zginął w `_dopisz_nowe` — sprawdź białą listę pól"
    )


def test_pusta_kolejnosc_nie_zasmieca_ksiegi():
    log: dict = {}
    R._dopisz_nowe(log, [_typ(kolejnosc={})])
    assert "kolejnosc" not in next(iter(log.values()))


def test_rachunek_dojezdza_dla_typu_zawodniczego():
    """Ścieżka zawodnicza dostała stempel dopiero 16.08 — patrz niżej."""
    log: dict = {}
    R._dopisz_nowe(log, [_typ(
        podmiot_typ="zawodnik", podmiot_id=777, podmiot="Jan Testowy",
        rynek_kod="shots", rynek="Strzały",
    )])
    rec = next(iter(log.values()))
    assert rec.get("rachunek") == RACHUNEK


def test_typ_pomiarowy_niesie_rachunek_i_lambde():
    """⚑ TYP POMIAROWY TO DWIE TRZECIE PRÓBY ZAWODNICZEJ (2026-08-16).

    Zmierzone przy diagnozie strumienia: 92 ze 170 rozliczonych typów
    zawodniczych to odrzucenia przy progu, rozliczane w tle. Bez ich stempli
    diagnoza liczy się na 77 rekordach zamiast 170 — i faktycznie stała na
    OŚMIU, bo `rachunek` miały wyłącznie legi puli kuponów.

    `lambda` z tego samego powodu: pasmo tuż nad progiem λ jest jedynym
    miejscem, gdzie ten próg da się kiedykolwiek ocenić — poniżej progu
    księga ma zero rozliczeń, bo brama wycina przed publikacją.
    """
    log: dict = {}
    R._dopisz_nowe(log, [_typ(
        podmiot_typ="zawodnik", podmiot_id=777, podmiot="Jan Testowy",
        rynek_kod="shots", rynek="Strzały",
        odrzucony=True, odrzucenie_powod="ev_ponizej_progu",
        **{"lambda": 1.42},
    )])
    rec = next(iter(log.values()))
    assert rec.get("rachunek") == RACHUNEK, (
        "typ pomiarowy stracił rachunek — to dwie trzecie próby zawodniczej"
    )
    assert rec.get("lambda") == 1.42, (
        "typ pomiarowy stracił λ — bez niej progu λ nie da się ocenić"
    )
    assert rec.get("odrzucony") is True


def test_kolejnosc_dojezdza_dla_typu_zdjetego_brama():
    """Stempel obejmuje od 16.08 także to, co brama wycięła.

    Bez tego nie da się porównać kolejności POKAZANYCH z kolejnością
    ZDJĘTYCH — a to samo porównanie zdecydowało 13.08 o kwarantannach.
    """
    log: dict = {}
    kolejnosc = {"moc": 0.8845, "kandydatow": 3}
    R._dopisz_nowe(log, [_typ(
        poza_publikacja="rozjazd_z_rynkiem", kolejnosc=dict(kolejnosc),
    )])
    rec = next(iter(log.values()))
    assert rec.get("kolejnosc") == kolejnosc
    assert rec.get("poza_publikacja") == "rozjazd_z_rynkiem"


def test_stempel_przezywa_odrodzenie_typu():
    """Typ spoza listy dnia rodzi się od nowa przy prawdziwej publikacji —
    z ceną i stemplami z TAMTEJ chwili. Nowy rachunek ma zastąpić stary."""
    log: dict = {}
    R._dopisz_nowe(log, [_typ(poza_publikacja="poza_lista_dnia")])
    nowy = betting.stempel_rachunku(
        p_over_raw=0.70, kal_rynek=0.10, kal_strumien=-0.40, p_over_final=0.62,
    )
    R._dopisz_nowe(log, [_typ(rachunek=dict(nowy), p_model=0.62)])
    rec = next(iter(log.values()))
    assert rec.get("rachunek") == nowy, (
        "po odrodzeniu w księdze został stempel z cyklu, w którym typu "
        "nikt nie widział"
    )
