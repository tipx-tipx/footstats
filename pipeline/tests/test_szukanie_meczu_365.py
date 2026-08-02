"""Szukanie meczu w 365Scores (rozliczanie._gid_365).

POWÓD (2026-08-02). Rozliczanie porównywało nazwy drużyn jak napisy, więc nie
znajdowało meczów, których statystyki leżały u źródła gotowe. Zmierzone na
księdze: 115 typów zamkniętych jako „brak danych źródła" (54 z nich były na
stronie) i 45 wiszących w pięciu meczach jednego weekendu. Sprawdzone przez
odpytanie 365Scores: dla WSZYSTKICH pięciu komplet statystyk był dostępny.

Testy pilnują trzech rzeczy naraz: że tolerancja działa, że NIE jest ślepa
(mecz dwuznaczny odpada) i że drogi zapas nie odpala się bez potrzeby.
"""

import time

from footstats.jobs import rozliczanie
from footstats.sources import scores365


def _rec(mecz, kickoff_ts=None, rynek_kod="team_corners", mecz_id=1):
    return {
        "mecz_id": mecz_id, "mecz": mecz,
        "kickoff_ts": kickoff_ts or int(time.time()) - 20 * 3600,
        "rynek_kod": rynek_kod, "podmiot": mecz.split(" – ")[0],
    }


def _gra(gid, ts, home, away):
    return {"id": gid, "ts": ts, "home": home, "away": away, "gole": {}}


def _bez_sieci(monkeypatch, gry=(), mapa=None, mecze_druzyny=()):
    """Zaślepia OBA źródła meczu: pulę per rozgrywki i zapas per drużyna."""
    monkeypatch.setattr(
        scores365, "finished_games_by_competition",
        lambda comp_id=None: list(gry),
    )
    monkeypatch.setattr(
        scores365, "competitor_ids_z_rozgrywek", lambda comp_ids: dict(mapa or {})
    )
    monkeypatch.setattr(
        scores365, "recent_finished_games_z_rozgrywkami",
        lambda cid, n=6: list(mecze_druzyny),
    )


def test_znajduje_mimo_innego_zapisu_nazw(monkeypatch):
    """Bodø/Glimt – Lillestrøm SK: 12 typów wisiało 47 h przez ukośnik."""
    ts = int(time.time()) - 20 * 3600
    _bez_sieci(monkeypatch, gry=[_gra(4638342, ts, "bodo glimt", "lillestrom")])
    rec = _rec("Bodø/Glimt – Lillestrøm SK", ts)
    assert rozliczanie._gid_365(rec, {}) == 4638342


def test_dwa_pasujace_mecze_to_brak_dopasowania(monkeypatch):
    """Jednoznaczność liczona na CAŁYM oknie, nie „pierwszy z brzegu".

    W Argentynie naprawdę grają dwa różne Estudiantes (La Plata i Río Cuarto).
    Sama nazwa „Estudiantes" zawiera się w obu, więc gdyby liczyła się
    kolejność w liście, wybór byłby losowy — a rozliczenie jest nieodwracalne
    i zamknęłoby typ wynikiem cudzego meczu.
    """
    ts = int(time.time()) - 20 * 3600
    _bez_sieci(monkeypatch, gry=[
        _gra(1, ts, "estudiantes de la plata", "banfield"),
        _gra(2, ts + 600, "estudiantes de rio cuarto", "banfield fc"),
    ])
    assert rozliczanie._gid_365(_rec("Estudiantes – Banfield", ts), {}) is None


def test_nie_bierze_sasiada_o_podobnej_nazwie(monkeypatch):
    """Riestra vs Recoleta — pomyłka, która zamknęłaby typ CUDZYM wynikiem."""
    ts = int(time.time()) - 20 * 3600
    _bez_sieci(monkeypatch, gry=[
        _gra(9, ts, "deportivo recoleta", "barracas central"),
    ])
    rec = _rec("Deportivo Riestra – Barracas Central", ts)
    assert rozliczanie._gid_365(rec, {}) is None


def test_zapas_siega_glebiej_niz_ostatnia_kolejka(monkeypatch):
    """Endpoint per rozgrywki oddaje tylko ostatnią kolejkę.

    Mecz sprzed dwóch kolejek z niej wypada i typ czekał na dane, których
    nikt już nie miał skąd wziąć. Ten sam endpoint filtrowany po DRUŻYNIE
    sięga w głąb sezonu — stąd zapas.

    Do mapy competitorId idzie `dopasuj_druzyne`, które ZOSTAJE ostre: nie zna
    ani rdzeni, ani aliasów, bo tam kandydatem jest cała liga („bohemian" vs
    „bohemians" ma prawo odmówić). Dlatego pytamy o OBIE drużyny meczu —
    „Aalesunds FK" nie trafi w „aalesund", ale „Tromsø IL" trafi w „tromso",
    a mecze jednej drużyny wystarczą, żeby znaleźć ten mecz.
    """
    ts = int(time.time()) - 30 * 3600
    _bez_sieci(
        monkeypatch,
        gry=[],                                  # pula per rozgrywki: pusto
        mapa={"aalesund": 1234, "tromso": 5678},
        mecze_druzyny=[(4638343, ts, 131)],
    )
    rec = _rec("Aalesunds FK – Tromsø IL", ts)
    assert rozliczanie._gid_365(rec, {}) == 4638343


def test_zapas_nie_odpala_sie_dla_typow_zawodniczych(monkeypatch):
    """Bezpiecznik kosztu: mapa nazw to ~34 adresy, a nieudane `_get` śpi 6 s.

    Typ zawodniczy z ligi spoza zakresu drużynowego (MLS, Meksyk, Szkocja)
    rozlicza się z trendów statshub i gid nie jest mu do niczego potrzebny.
    Bez tego warunku takie typy ciągnęłyby budowę mapy w KAŻDYM przebiegu,
    co 20 minut, do skutku, którego nigdy nie będzie.
    """
    pytano = []
    ts = int(time.time()) - 30 * 3600
    _bez_sieci(monkeypatch, gry=[], mapa={"la galaxy": 1})
    monkeypatch.setattr(
        scores365, "competitor_ids_z_rozgrywek",
        lambda comp_ids: pytano.append(1) or {},
    )
    rec = _rec("LA Galaxy – FC Dallas", ts, rynek_kod="shots")
    assert rozliczanie._gid_365(rec, {}) is None
    assert pytano == []


def test_zapas_nie_odpala_sie_tuz_po_gwizdku(monkeypatch):
    """Świeżo zakończonego meczu źródło jeszcze nie opublikowało — to normalne,
    nie awaria, więc nie płacimy za drogie szukanie po drużynie."""
    pytano = []
    ts = int(time.time()) - 40 * 60
    _bez_sieci(monkeypatch, gry=[])
    monkeypatch.setattr(
        scores365, "competitor_ids_z_rozgrywek",
        lambda comp_ids: pytano.append(1) or {},
    )
    assert rozliczanie._gid_365(_rec("Lyngby – AGF", ts), {}) is None
    assert pytano == []
