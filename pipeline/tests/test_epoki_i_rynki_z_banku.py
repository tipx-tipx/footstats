"""Rozbicie mundial/ligi + trendy drużynowe budowane z własnego banku.

Obie rzeczy weszły 2026-07-27 i obie odpowiadają na to samo pytanie usera
(„czemu jest tak mało typów"), tylko z dwóch stron: diagnostyki i podaży.
"""

from footstats.jobs import rozliczanie
from footstats.jobs.build_wc_fast import MIN_GIER_BANKU
from footstats.sources import scores365


PRZED = rozliczanie.KONIEC_MUNDIALU_TS - 86400      # mecz reprezentacji
PO = rozliczanie.KONIEC_MUNDIALU_TS + 3 * 86400     # mecz ligowy


def _typ(**kw):
    r = {
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": PRZED,
        "podmiot_id": 7, "podmiot": "Ktoś", "rynek_kod": "shots",
        "rynek": "Strzały", "linia": 1.5, "strona": "powyzej",
        "kurs": 2.0, "p_model": 0.6, "sugestia": False,
        "odrzucony": False, "wynik": "wygrany",
    }
    r.update(kw)
    return r


def _log(*typy):
    return {str(i): t for i, t in enumerate(typy)}


def test_epoki_dziela_po_dacie_meczu_i_licza_roi():
    log = _log(
        _typ(kickoff_ts=PRZED, wynik="wygrany", kurs=2.0),
        _typ(kickoff_ts=PRZED, wynik="przegrany"),
        _typ(kickoff_ts=PO, wynik="wygrany", kurs=3.0),
    )
    ep = rozliczanie.epoki_per_rynek(log)["shots"]
    assert ep["mundial"]["n"] == 2 and ep["ligi"]["n"] == 1
    assert ep["mundial"]["skutecznosc"] == 0.5
    # ROI PO PODATKU od stawki (od 2026-07-31): z 1 j. pracuje 0,88 j.
    # mundial: (2,0×0,88 − 1) + (−1) = −0,24 na dwóch typach = −0,12
    assert ep["mundial"]["roi"] == -0.12
    # ligi: kurs 3,0 wygrany = 3,0×0,88 − 1 = +1,64 na jednym typie
    assert ep["ligi"]["roi"] == 1.64
    assert ep["nazwa"] == "Strzały"


def test_epoki_pusta_strona_to_none_a_nie_zero():
    """`None` znaczy „nie graliśmy tego wtedy", 0 znaczyłoby „graliśmy i nic".

    UI rysuje z tego „brak typów" — bez rozróżnienia rynek świeżo dodany
    wyglądałby jak rynek, który przegrał wszystko.
    """
    ep = rozliczanie.epoki_per_rynek(_log(_typ(kickoff_ts=PO)))["shots"]
    assert ep["mundial"] is None
    assert ep["ligi"]["n"] == 1


def test_epoki_pomijaja_to_samo_co_kwarantanna():
    """Ta sama próba co `rynki_kwarantanna` — inaczej liczb nie dałoby się
    zestawić z jej progiem, a po to ta tabela powstała."""
    log = _log(
        _typ(sugestia=True),                 # sugestia STS
        _typ(odrzucony=True),                # typ pomiarowy przy progu
        _typ(zrodlo="drabinka"),             # inny estymator
        _typ(kurs=None),                     # bez kursu nie ma ROI
        _typ(wynik=None),                    # nierozliczony
    )
    assert rozliczanie.epoki_per_rynek(log) == {}


def test_prog_banku_pokrywa_brame_krotkiej_historii():
    """MIN_GIER_BANKU musi być > progu `krotka_historia` (5).

    Przy czterech drużyna przestawała kwalifikować się do doganiania historii,
    ale wciąż odpadała na bramie pięciu meczów — martwe pole, w którym rynki
    drużynowe z banku nigdy by nie powstały.
    """
    assert MIN_GIER_BANKU > 5


def test_recent_finished_games_niesie_rozgrywki(monkeypatch):
    """Wariant z ID rozgrywek to jedyny sposób odróżnić beniaminka (historia
    z niższego poziomu, wymaga skalowania) od drużyny ze świeżo dołożonej ligi
    (historia z tego samego poziomu)."""
    monkeypatch.setattr(scores365, "_get", lambda url, **kw: {"games": [
        {"id": 11, "statusGroup": 4, "startTime": "2026-07-20T20:00:00+02:00",
         "competitionId": 113},
        {"id": 12, "statusGroup": 4, "startTime": "2026-07-24T20:00:00+02:00",
         "competitionId": 999},
        {"id": 13, "statusGroup": 2, "startTime": "2026-07-30T20:00:00+02:00",
         "competitionId": 113},   # jeszcze nierozegrany — odpada
    ]})
    wiersze = scores365.recent_finished_games_z_rozgrywkami(7383, n=5)
    assert [g for g, _, _ in wiersze] == [12, 11]      # najnowsze pierwsze
    assert [c for _, _, c in wiersze] == [999, 113]
    # stara sygnatura (trzy inne wywołania w kodzie) nadal zwraca pary
    assert scores365.recent_finished_games(7383, n=5) == [
        (g, t) for g, t, _ in wiersze
    ]
