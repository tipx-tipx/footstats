# -*- coding: utf-8 -*-
"""MAGAZYN HISTORII DRUŻYN — pamięć, na której model może się uczyć.

Powód istnienia (2026-08-17): rynki drużynowe to 93% produkcji, a ich historia
meczowa nie była nigdzie zapisywana — cykl pobierał ją, używał i wyrzucał.
W bazie zostawały same agregaty, a ze średniej nie da się nauczyć modelu.

Te testy pilnują rzeczy, które przy magazynie danych najłatwiej złamać:
tożsamości drużyny w rekordzie, nienadpisywania historii i tego, żeby brak
pola nie udawał zera.
"""
from footstats.jobs import magazyn_druzyn as M


def _row(ev_id=1, ts=1000, home_id=10, away_id=20, gole=(2, 1),
         cor=7, cor_opp=3, braki=False):
    st = {"cornerKicks": cor, "cards": 2, "fouls": 11, "ballPossession": 61}
    stp = {"cornerKicks": cor_opp, "cards": 1, "fouls": 9, "ballPossession": 39}
    if braki:
        st = {"cornerKicks": None, "cards": 2}
        stp = {}
    return {
        "event": {"id": ev_id, "timeStartTimestamp": str(ts),
                  "score": {"home": gole[0], "away": gole[1]}},
        "league": {"id": 7, "name": "UCL"},
        "homeTeam": {"id": home_id, "name": "Nasza"},
        "awayTeam": {"id": away_id, "name": "Ich"},
        "statistics": st,
        "opponentStatistics": stp,
    }


def test_rekord_wie_ktora_druzyna_jest_nasza():
    """Gospodarz i gość nie mogą się zamienić — na tym stoi cały zbiór.

    ⚑ ZWERYFIKOWANE NA ŻYWYCH DANYCH (2026-08-17): `statistics` u źródła należy
    do drużyny PYTANEJ, nie do gospodarza. Sprawdzone na meczu Bodø/Glimt –
    Union SG zapytanym z obu stron: 44 z 45 pól `statistics(A)` zgadza się
    z `opponentStatistics(B)`, a tylko 4 z 45 są identyczne z `statistics(B)`.
    Gdyby było odwrotnie, cały zbiór miałby zamienione strony przy meczach
    wyjazdowych — a tego po fakcie nie da się rozpoznać w danych.

    Dlatego rekord dla gościa dostaje WŁASNĄ odpowiedź źródła (z jego liczbami
    w `statistics`), a nie tę samą co gospodarz.
    """
    u_siebie = M.rekord_meczu(10, _row(cor=7, cor_opp=3))
    # odpowiedź źródła na pytanie o gościa: jego liczby w `statistics`
    na_wyjezdzie = M.rekord_meczu(20, _row(cor=3, cor_opp=7))
    assert u_siebie["h"] == 1 and na_wyjezdzie["h"] == 0
    assert u_siebie["o"] == 20 and na_wyjezdzie["o"] == 10
    # gole: gospodarz 2, gość 1 — liczone z pozycji NASZEJ drużyny
    assert u_siebie["g"] == 2 and u_siebie["gp"] == 1
    assert na_wyjezdzie["g"] == 1 and na_wyjezdzie["gp"] == 2
    # statystyki własne vs rywala
    assert u_siebie["s"]["cor"] == 7 and u_siebie["sp"]["cor"] == 3
    assert na_wyjezdzie["s"]["cor"] == 3 and na_wyjezdzie["sp"]["cor"] == 7


def test_brak_pola_nie_udaje_zera():
    """`None` u źródła to „nie wiemy", a nie „zero rożnych"."""
    rec = M.rekord_meczu(10, _row(braki=True))
    assert "cor" not in rec["s"], "brak pola musi zniknąć, nie zamienić się w 0"
    assert rec["s"]["crd"] == 2
    assert rec["sp"] == {}


def test_mecz_bez_czasu_odpada():
    row = _row()
    row["event"]["timeStartTimestamp"] = None
    assert M.rekord_meczu(10, row) is None


def test_dopisanie_nie_dubluje_i_nie_nadpisuje():
    """Statystyki rozegranego meczu się nie zmieniają — przepisanie mogłoby
    tylko zamienić dobry rekord na gorszy."""
    mag: dict = {}
    assert M.dopisz(mag, 10, [_row(ev_id=1), _row(ev_id=2, ts=2000)]) == 2
    # ten sam mecz drugi raz, tym razem z gorszymi danymi
    assert M.dopisz(mag, 10, [_row(ev_id=1, cor=0, braki=True)]) == 0
    mecze = mag["10"]["m"]
    assert len(mecze) == 2
    assert mecze[0]["s"]["cor"] == 7, "istniejący rekord nie może być nadpisany"


def test_okno_trzyma_najnowsze():
    mag: dict = {}
    M.dopisz(mag, 10, [_row(ev_id=i, ts=1000 + i) for i in range(M.OKNO_MECZOW + 15)])
    mecze = mag["10"]["m"]
    assert len(mecze) == M.OKNO_MECZOW
    assert mecze[-1]["t"] == 1000 + M.OKNO_MECZOW + 14, "zostają NAJNOWSZE"


def test_szardy_rozkladaja_druzyny():
    """3,5 MB w jednym kluczu przerywało upsert Postgresa — stąd podział."""
    assert M.szard(10) != M.szard(11)
    assert M.klucz_szardu(M.szard(289)) == "hd_9"
    assert len({M.szard(i) for i in range(100)}) == M.SZARDOW


def test_statystyki_licza_obserwacje():
    mag: dict = {}
    M.dopisz(mag, 10, [_row(ev_id=1), _row(ev_id=2, ts=2000)])
    M.dopisz(mag, 21, [_row(ev_id=3, ts=3000, home_id=21)])
    st = M.statystyki(mag)
    assert st["druzyn"] == 2 and st["meczow"] == 3
    assert st["obserwacji"] == 12, "4 pola × 3 mecze"
    assert st["gole"] == 3
    assert "PUSTY" not in M.zdanie_stanu(st)


def test_puste_magazyn_krzyczy():
    """Magazyn bez licznika jest nieodróżnialny od pustego."""
    assert "PUSTY" in M.zdanie_stanu(M.statystyki({}))
