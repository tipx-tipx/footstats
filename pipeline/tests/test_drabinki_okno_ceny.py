# -*- coding: utf-8 -*-
"""PREMIA ZA OKNO CENY nie ma prawa sięgać pasma, które traci najwięcej.

Ranking drabinek premiuje kartę startującą w paśmie, w którym drabinki realnie
zarabiają (`OKNO_CENY_PREF_*`). Do 13.08 okno kończyło się na 1,90, powołując
się na tabelę rozliczeń — a ta sama tabela mówiła „1,70–2,00: trafia 23,5%,
zwrot −56,1%". Premia obejmowała więc połowę najgorszego pasma w zakładce.

Sprawdzone ponownie na 94 rozliczeniach bieżącej epoki (luka, bo ROI w tych
wycinkach zmienia znak; obie połowy próby zgodne):

    1,55–1,70   n=16   luka  +0,2 pp    <- skalibrowane co do punktu
    1,70–1,90   n=15   luka -28,9 pp    <- gorsze niż to, co ZOSTAJE poza oknem
    1,90+       n=53   luka -10,7 pp
"""
from footstats.jobs import radar as R

from test_drabinki_drugi_szczebel import _kandydat


def _score(kurs_hero, p_hero):
    """Ocena karty, w której zmienia się WYŁĄCZNIE cena i szansa pierwszego
    szczebla — drugi szczebel jest identyczny, żeby różnica pochodziła z premii,
    a nie z materiału."""
    w = _kandydat([(0.5, kurs_hero, p_hero), (1.5, 3.0, 0.35)])
    score, szczebel = R._oceń_karte(w)
    assert szczebel is not None, "karta miała przejść bramy"
    return score


def test_premia_dziala_w_oknie():
    """Ta sama przewaga, dwie ceny: 1,65 jest w oknie, 1,80 już nie."""
    # edge = p − 1/kurs; dobrane tak, by w obu kartach wynosił dokładnie 0,05
    w_oknie = _score(1.65, round(1 / 1.65 + 0.05, 4))
    poza = _score(1.80, round(1 / 1.80 + 0.05, 4))
    assert w_oknie > poza
    assert round(w_oknie - poza, 4) == R.BONUS_OKNA_CENY


def test_okno_nie_obejmuje_pasma_ktore_traci_najwiecej():
    """Pasmo 1,70–1,90 ma lukę −28,9 pp, stabilnie w obu połowach próby.

    Gdyby ktoś rozciągnął okno z powrotem, ranking znów wynosiłby na górę
    zakładki karty wyceniane gorzej niż te, które zostają poza oknem —
    a to jest premia działająca przeciwko sobie."""
    assert R.OKNO_CENY_PREF_DO <= 1.70
    # dolna granica zostaje: poniżej 1,55 luka to −39,4 pp (n=9)
    assert R.OKNO_CENY_PREF_OD >= 1.55


def test_premia_jest_kolejnoscia_a_nie_brama():
    """Karta spoza okna ma dalej powstawać — premia rusza tylko kolejność."""
    w = _kandydat([(0.5, 2.40, round(1 / 2.40 + 0.05, 4)), (1.5, 4.0, 0.30)])
    score, szczebel = R._oceń_karte(w)
    assert szczebel is not None and score > 0
