"""Testy detektorów radaru (jobs/radar.py) na syntetycznych trendach."""

import pytest

from footstats.jobs import radar
from footstats.sources.statshub import StatshubTrend


@pytest.fixture(autouse=True)
def _bez_betclica(monkeypatch):
    """ODETNIJ SIEĆ (naprawa 2026-07-31).

    `radar.zbuduj` dokłada do kart drugi cennik i woła w tym celu
    `betclic.paruj_mecze` — czyli robi PRAWDZIWE zapytanie gRPC-Web. Testy,
    które podają `events_meta` z nazwami drużyn, wchodziły więc w sieć, a
    połączenie do Betclica jest strumieniowe („pierwsza ramka, potem wisi") —
    i zestaw stawał na amen.

    Skutek był gorszy niż wolne testy: PEŁNY zestaw nie kończył się NIGDY,
    więc nikt go nie uruchamiał, więc 466 testów nie broniło niczego. To jest
    dokładnie ta dziura, którą zamyka CI — ale CI też by na tym zawisło.

    Zaślepka zwraca „żadnego meczu nie sparowano", czyli ścieżkę, którą kod
    i tak obsługuje (Betclic bywa niedostępny w produkcji). Test drugiego
    cennika, który tego POTRZEBUJE, podmienia zaślepkę u siebie.
    """
    monkeypatch.setattr(radar.betclic, "paruj_mecze", lambda nasze: ({}, []))

TERAZ = 1_800_000_000
DZIEN = 86_400

LIGA_NOWA = 45      # np. austriacka Bundesliga
LIGA_STARA = 202    # np. Ekstraklasa
KADRA = 16


# Historia 7/10 nad linia 1,5 — realny material na karte PO wprowadzeniu okna
# zgody z rynkiem (radar.MAX_ROZJAZD_KARTY). Dawne fikstury „14 z 14 trafien
# przy kursie 2,05" opisywaly sytuacje, ktora w praktyce nie zdarza sie inaczej
# niz przez nasz blad: bukmacher nie placi 2,05 za pewniaka. Kurs 1,80 wycenia
# to na 55%, a my po korekcie kontekstu na 64% — rozjazd ok. +10 pp, w oknie.
#
# 2026-08-08: wektor przeliczony tak, zeby dawal DWA SZCZEBLE. Dawny (same
# dwojki) przebijal linie 1,5 siedem razy na dziesiec, ale linie 2,5 ZERO razy,
# wiec opisywal karte jednoszczeblowa — produkt, ktorego juz nie wydajemy
# (radar.MIN_P_DRUGIEGO_SZCZEBLA, zgloszenie usera „drugi szczebel jest glownym
# celem"). Teraz: 7/10 nad 1,5 i 5/10 nad 2,5, co przy kursach 1,70 / 3,20 daje
# szanse 0,64 i 0,46 — realna drabinka, ktora przechodzi okno zgody z rynkiem.
SIEDEM_Z_DZIESIECIU = [3, 3, 0, 3, 2, 0, 3, 2, 3, 0, 3, 2, 0, 3]
KURS_W_OKNIE = 1.7
# Drugi szczebel do fikstur siatki kursow: linia 2,5 przy cenie, ktora zostawia
# nasza szanse (0,46) nad cena rynku, ale w granicach MAX_ROZJAZD_KARTY.
KURS_DRUGIEGO = 3.2


def _trend(
    *,
    player_id=1,
    team_id=100,
    market_code="shots",
    counts=None,
    minutes=None,
    utids=None,
    opponent_ids=None,
    dni_wstecz_start=2,
):
    """Trend z historią co 7 dni od najnowszego (indeks 0) wstecz."""
    n = len(counts or [])
    return StatshubTrend(
        player_id=player_id,
        player_name=f"Gracz {player_id}",
        position="M",
        team_id=team_id,
        team_name="Klub",
        opponent_id=200,
        opponent_name="Rywal",
        is_home=True,
        market_code=market_code,
        line=1.5,
        in_predicted_lineup=True,
        league_average=None,
        opponent_average=None,
        opponent_rank=None,
        total_ranks=None,
        event_id=999,
        counts=[float(c) for c in (counts or [])],
        minutes=[float(m) for m in (minutes or [90] * n)],
        timestamps=[TERAZ - (dni_wstecz_start + 7 * i) * DZIEN for i in range(n)],
        started=[float(m) >= 60 for m in (minutes or [90] * n)],
        game_utids=list(utids or [LIGA_NOWA] * n),
        game_opponent_ids=list(opponent_ids or [0] * n),
    )


def test_liga_konsensus_wybiera_dominujaca_lige_druzyny():
    trends = [
        _trend(player_id=1, utids=[LIGA_NOWA] * 10 + [KADRA] * 2,
               counts=[1] * 12),
        _trend(player_id=2, utids=[LIGA_NOWA] * 8 + [LIGA_STARA] * 4,
               counts=[1] * 12),
        # duplikat rynku tego samego gracza nie liczy się podwójnie
        _trend(player_id=1, market_code="fouls_committed",
               utids=[LIGA_STARA] * 12, counts=[1] * 12),
    ]
    kons = radar.liga_konsensus(trends)
    liga, wspolne = kons[100]
    assert liga == LIGA_NOWA
    # wspólny utid = grało w nim >= 2 RÓŻNYCH kolegów (liga tak, kadra nie)
    assert LIGA_NOWA in wspolne and KADRA not in wspolne


def test_sygnal_transferu_zmiana_ligi():
    # 12 ostatnich meczów w starej lidze, 1 w nowej — świeży nabytek
    tr = _trend(utids=[LIGA_NOWA] + [LIGA_STARA] * 12, counts=[2] * 13)
    s = radar.sygnal_transferu(tr, LIGA_NOWA, {LIGA_NOWA}, TERAZ)
    assert s is not None
    assert s["powod"] == "zmiana_ligi"
    assert s["stara_liga_utid"] == LIGA_STARA
    assert s["mecze_nowa"] == 1


def test_sygnal_transferu_zadomowiony_bez_sygnalu():
    # rok w nowej lidze (okno 15 meczów pełne nowej ligi) — cisza
    tr = _trend(utids=[LIGA_NOWA] * 15 + [LIGA_STARA] * 10, counts=[2] * 25)
    assert radar.sygnal_transferu(tr, LIGA_NOWA, {LIGA_NOWA}, TERAZ) is None


def test_sygnal_transferu_rozgrywki_druzyny_to_nie_stara_liga():
    # historia pełna pucharu, w którym gra CAŁA drużyna (np. CONCACAF CC,
    # druga faza tej samej ligi) — to nie transfer, tylko kalendarz klubu
    PUCHAR = 777
    tr = _trend(utids=[LIGA_NOWA] * 2 + [PUCHAR] * 11, counts=[2] * 13)
    assert (
        radar.sygnal_transferu(tr, LIGA_NOWA, {LIGA_NOWA, PUCHAR}, TERAZ)
        is None
    )


def test_sygnal_transferu_mundial_to_nie_stara_liga():
    # reprezentant wraca z MŚ: mundial nie może wyjść jako „stara liga"
    tr = _trend(
        utids=[LIGA_NOWA] * 2 + [radar.UTID_MUNDIAL] * 7 + [LIGA_NOWA] * 4,
        counts=[2] * 13,
    )
    assert radar.sygnal_transferu(tr, LIGA_NOWA, {LIGA_NOWA}, TERAZ) is None


def test_sygnal_transferu_gral_przeciw_obecnym():
    # ta sama liga, ale niedawno grał PRZECIW swojej obecnej drużynie
    tr = _trend(
        utids=[LIGA_NOWA] * 12,
        counts=[2] * 12,
        opponent_ids=[0, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    )
    s = radar.sygnal_transferu(tr, LIGA_NOWA, {LIGA_NOWA}, TERAZ)
    assert s is not None and s["powod"] == "gral_przeciw"


def test_sygnal_transferu_wymaga_swiezej_gry():
    # historia w innej lidze, ale ostatni występ pół roku temu — cisza
    tr = _trend(utids=[LIGA_STARA] * 12, counts=[2] * 12,
                dni_wstecz_start=200)
    assert radar.sygnal_transferu(tr, LIGA_NOWA, {LIGA_NOWA}, TERAZ) is None


def test_ten_sam_cykl_ligi():
    assert radar._ten_sam_cykl_ligi(
        "Liga MX, Apertura (Mexico)", "Liga MX, Clausura (Mexico)"
    )
    assert not radar._ten_sam_cykl_ligi(
        "LaLiga (Spain)", "MLS (USA)"
    )


def test_sygnal_formy_seria_nad_linia():
    # okno: 6 meczów po 3 strzały; baza: 8 meczów po 1 — wyraźny skok
    tr = _trend(counts=[3, 3, 3, 3, 3, 3] + [1] * 8)
    s = radar.sygnal_formy(tr, {0.5: 1.30, 1.5: 2.05, 2.5: 3.4}, TERAZ)
    assert s is not None
    # linia 0,5 odpada (kurs 1.30 < MIN_KURS_FORMY), zostaje najwyższa grywalna
    assert s["linia"] == 2.5
    assert s["trafienia"] == 6
    assert s["srednia90_okno"] > s["srednia90_baza"]


def test_sygnal_formy_bez_boostu_cisza():
    # równy poziom całą historię — to nie seria, to poziom gracza
    tr = _trend(counts=[3] * 14)
    assert radar.sygnal_formy(tr, {1.5: 2.0, 2.5: 3.2}, TERAZ) is None


def test_sygnal_formy_krotkie_wystepy_nie_licza_sie():
    # 3 strzały w 10-minutowych wejściach nie tworzą serii (za mało minut)
    tr = _trend(
        counts=[3, 3, 3, 3, 3, 3] + [1] * 8,
        minutes=[10, 10, 10, 10, 10, 10] + [90] * 8,
    )
    assert radar.sygnal_formy(tr, {1.5: 2.0}, TERAZ) is None


def test_zbuduj_transfer_z_drabinka_i_p_model(monkeypatch):
    # bez sieci w testach: etykiety lig z zaślepki (różne nazwy, żeby filtr
    # faz jednej ligi nie zjadł wpisu)
    monkeypatch.setattr(
        radar.statshub,
        "fetch_tournament_name",
        lambda utid: {LIGA_STARA: "Stara Liga", LIGA_NOWA: "Nowa Liga"}.get(
            utid, ""
        ),
    )
    # kolega z drużyny osadza konsensus ligi na LIGA_NOWA
    kolega = _trend(player_id=7, utids=[LIGA_NOWA] * 12, counts=[1] * 12)
    nowy = _trend(player_id=1, utids=[LIGA_NOWA] + [LIGA_STARA] * 12,
                  counts=SIEDEM_Z_DZIESIECIU)
    wpisy = radar.zbuduj(
        trends=[kolega, nowy],
        events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200,
                           "home": "Klub", "away": "Rywal"}},
        odds_grid={999: {1: {"shots": {"1.5": KURS_W_OKNIE, "2.5": 3.2}}}},
        sb_cache={},
        model_pokrycie=[{"podmiot": "Gracz 1", "rynek_kod": "shots",
                         "linia": 1.5, "strona": "powyzej",
                         "p_model": 0.65}],
        players_out={1: {"pozycja": "M", "xi": True}},
        nazwy_pl={"shots": "Strzały"},
        teraz=TERAZ,
    )
    assert len(wpisy) == 1
    w = wpisy[0]
    assert w["rodzaj"] == "transfer" and w["powod"] == "zmiana_ligi"
    assert w["podmiot"] == "Gracz 1" and w["xi"] is True
    assert w["mecz"] == "Klub – Rywal"
    (rynek,) = w["rynki"]
    assert rynek["rynek"] == "Strzały"
    s0 = rynek["drabinka"][0]
    assert (s0["linia"], s0["kurs"], s0["p_model"]) == (1.5, KURS_W_OKNIE, 0.65)
    # pokrycie: 7 z 10 ostatnich występów przebiło linię 1,5
    assert s0["pokrycie"] == {"traf": 7, "z": 10}
    # DWA SZCZEBLE, nie jeden: od 2026-08-08 karta bez realnego drugiego
    # szczebla nie jest drabinką i w ogóle nie powstaje (MIN_P_DRUGIEGO_SZCZEBLA)
    assert [s["linia"] for s in rynek["drabinka"]] == [1.5, 2.5]
    assert rynek["ostatnie"][:3] == [3, 3, 0]
    assert w["stara_liga"] == "Stara Liga"


def test_zbuduj_drabinka_bez_sygnalu_z_forma_i_rywalem():
    # gracz zadomowiony w lidze, bez serii — kiedyś radar go pomijał,
    # teraz dostaje wpis rodzaju "drabinka" z pełną analizą
    tr = _trend(utids=[LIGA_NOWA] * 14, counts=SIEDEM_Z_DZIESIECIU)
    tr.opponent_average = 11.4
    tr.opponent_rank = 3
    tr.total_ranks = 18
    wpisy = radar.zbuduj(
        trends=[tr],
        events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200,
                           "home": "Klub", "away": "Rywal"}},
        odds_grid={999: {1: {"shots": {"1.5": KURS_W_OKNIE, "2.5": 3.2}}}},
        sb_cache={},
        model_pokrycie=[],
        players_out={1: {"pozycja": "M", "xi": True}},
        nazwy_pl={"shots": "Strzały"},
        teraz=TERAZ,
    )
    assert len(wpisy) == 1
    w = wpisy[0]
    assert w["rodzaj"] == "drabinka"
    assert "powod" not in w
    (rynek,) = w["rynki"]
    # forma okno-vs-baza liczona informacyjnie na każdym rynku z historią
    assert rynek["forma"]["okno90"] > 0 and rynek["forma"]["baza90"] > 0
    assert rynek["rywal"] == {"srednia": 11.4, "rank": 3, "z": 18,
                              "liga": None}
    assert len(rynek["ostatnie"]) == 10  # OSTATNIE_N występów na karcie


def test_zbuduj_dolacza_srednie_sezonowe_z_cache():
    tr = _trend(utids=[LIGA_NOWA] * 14, counts=SIEDEM_Z_DZIESIECIU)
    sezon = {"turniej": "Serie B", "rok": "2025", "mecze": 32,
             "minuty": 1738, "na_mecz": {"shots": 1.4}, "na90": {"shots": 1.4}}
    wpisy = radar.zbuduj(
        trends=[tr],
        events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200,
                           "home": "Klub", "away": "Rywal"}},
        odds_grid={999: {1: {"shots": {"1.5": KURS_W_OKNIE, "2.5": KURS_DRUGIEGO}}}},
        sb_cache={},
        model_pokrycie=[],
        players_out={},
        nazwy_pl={},
        teraz=TERAZ,
        player_sezon={"1": {"name": "Gracz 1", "fetched_ts": TERAZ,
                            "sezony": [sezon]}},
    )
    assert wpisy[0]["sezony"] == [sezon]


def test_zbuduj_sygnaly_przed_drabinkami():
    # sortowanie: transfer przodem, zwykla drabinka na koncu
    kolega = _trend(player_id=7, utids=[LIGA_NOWA] * 12, counts=[1] * 12)
    nowy = _trend(player_id=1, utids=[LIGA_NOWA] + [LIGA_STARA] * 12,
                  counts=SIEDEM_Z_DZIESIECIU)
    # zwykła drabinka musi mieć DWA szczeble jak każda inna (2026-08-08),
    # więc dostaje tę samą historię co kandydat z transferu
    zwykly = _trend(player_id=7, utids=[LIGA_NOWA] * 14,
                    counts=SIEDEM_Z_DZIESIECIU)
    import unittest.mock as _m
    with _m.patch.object(radar.statshub, "fetch_tournament_name",
                         lambda utid: {LIGA_STARA: "Stara",
                                       LIGA_NOWA: "Nowa"}.get(utid, "")):
        wpisy = radar.zbuduj(
            trends=[kolega, nowy, zwykly],
            events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                               "hid": 100, "aid": 200,
                               "home": "Klub", "away": "Rywal"}},
            odds_grid={999: {1: {"shots": {"1.5": KURS_W_OKNIE, "2.5": KURS_DRUGIEGO}},
                             # gorsza cena = słabsza karta, więc sygnał
                             # (transfer) ma wyjść przed zwykłą drabinką
                             7: {"shots": {"1.5": 1.67,
                                           "2.5": KURS_DRUGIEGO}}}},
            sb_cache={},
            model_pokrycie=[],
            players_out={},
            nazwy_pl={},
            teraz=TERAZ,
        )
    assert [w["rodzaj"] for w in wpisy] == ["transfer", "drabinka"]


def test_drabinka_przycieta_z_szumu():
    # 8 linii, od 3. wzwyż kosmiczne kursy — karta ma pokazywać grywalne.
    # Historia z trójkami (nie dwójkami), żeby szczebel 2,5 miał realne
    # pokrycie — inaczej wycina go nowa brama pustych szczebli, a test ma
    # sprawdzać przycinanie po KURSIE.
    tr = _trend(utids=[LIGA_NOWA] * 14,
                counts=[3, 3, 0, 3, 3, 0, 3, 3, 3, 0, 3, 3, 0, 3])
    wpisy = radar.zbuduj(
        trends=[tr],
        events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200,
                           "home": "Klub", "away": "Rywal"}},
        odds_grid={999: {1: {"shots": {
            "0.5": 1.12, "1.5": KURS_W_OKNIE, "2.5": 3.4, "3.5": 6.1,
            "4.5": 13.0, "5.5": 23.0, "6.5": 41.0, "7.5": 67.0,
        }}}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    )
    (rynek,) = wpisy[0]["rynki"]
    linie = [s["linia"] for s in rynek["drabinka"]]
    # 0,5 @1.12 odpada (pierwszy szczebel od MIN_KURS_PIERWSZEGO=1.65);
    # 3,5 ma pokrycie 0/10, więc od 2026-07-27 też nie wchodzi na kartę
    assert linie == [1.5, 2.5]
    # minuty_sr6: pełne mecze w historii
    assert wpisy[0]["minuty_sr6"] == 90
    # udział startów: cała historia to pełne mecze
    assert wpisy[0]["udzial_startow"] == 1.0


def test_bramy_odrzucaja_karte_bez_przewagi_nad_kursem():
    # Gracz bez przewagi I bez mocnej serii (5/10 przy 1,70) NIE tworzy karty.
    # UWAGA na fiksturę: od 2026-07-30 karta ma DWIE ścieżki wejścia, więc
    # pokrycie 7/10 przy tym kursie weszłoby jako „mocna seria" — i dlatego
    # ten test ma teraz gracza faktycznie słabego. Ścieżkę serii sprawdzają
    # testy niżej (test_mocna_seria_wchodzi_bez_przewagi_nad_kursem).
    def _meta(ts):
        return {"label": "A – B", "ts": ts, "hid": 100, "aid": 200,
                "home": "A", "away": "B"}
    slaby = _trend(player_id=1, utids=[LIGA_NOWA] * 14,
                   counts=[1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 1, 1, 0, 1])
    mocny = _trend(player_id=2, utids=[LIGA_NOWA] * 14,
                   counts=SIEDEM_Z_DZIESIECIU)
    pozny = _trend(player_id=3, utids=[LIGA_NOWA] * 14,
                   counts=SIEDEM_Z_DZIESIECIU)
    pozny.event_id = 998
    wpisy = radar.zbuduj(
        trends=[slaby, mocny, pozny],
        events_meta={999: _meta(TERAZ + DZIEN), 998: _meta(TERAZ + 2 * DZIEN)},
        odds_grid={999: {1: {"shots": {"0.5": 1.7}},
                         2: {"shots": {"1.5": KURS_W_OKNIE, "2.5": KURS_DRUGIEGO}}},
                   998: {3: {"shots": {"1.5": KURS_W_OKNIE, "2.5": KURS_DRUGIEGO}}}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    )
    assert [w["podmiot_id"] for w in wpisy] == [2, 3]
    # hero = linia, która zdecydowała o wyborze karty
    assert wpisy[0]["hero"]["linia"] == 1.5
    assert (wpisy[0]["hero"]["traf"], wpisy[0]["hero"]["z"]) == (7, 10)


def test_krotka_proba_nie_udaje_pewniaka():
    # 5/5 = 100%, ale próba za krótka (MIN_PROBA_SCORE=8) -> brak karty
    tr = _trend(utids=[LIGA_NOWA] * 5, counts=[3] * 5)
    wpisy = radar.zbuduj(
        trends=[tr],
        events_meta={999: {"label": "A – B", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200, "home": "A", "away": "B"}},
        odds_grid={999: {1: {"shots": {"1.5": 2.1}}}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    )
    assert wpisy == []


def test_zmiennik_odpada_na_bramie_minut():
    # komplet trafień, ale ~30 min na mecz — rotacyjny to ryzyko, nie typ
    tr = _trend(utids=[LIGA_NOWA] * 14, counts=[3] * 14,
                minutes=[30] * 14)
    wpisy = radar.zbuduj(
        trends=[tr],
        events_meta={999: {"label": "A – B", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200, "home": "A", "away": "B"}},
        odds_grid={999: {1: {"shots": {"1.5": 2.1}}}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    )
    assert wpisy == []


def test_sygnal_bez_pokrycia_nie_dostaje_karty(monkeypatch):
    # transfer z historią, której kursy nie pokrywają (linia 3,5 przy 1 strzale
    # na mecz) — sam sygnał NIE jest przepustką (decyzja usera 2026-07-25)
    monkeypatch.setattr(
        radar.statshub, "fetch_tournament_name",
        lambda utid: {LIGA_STARA: "Stara", LIGA_NOWA: "Nowa"}.get(utid, ""),
    )
    kolega = _trend(player_id=7, utids=[LIGA_NOWA] * 12, counts=[1] * 12)
    nowy = _trend(player_id=1, utids=[LIGA_NOWA] + [LIGA_STARA] * 12,
                  counts=[1] * 13)
    wpisy = radar.zbuduj(
        trends=[kolega, nowy],
        events_meta={999: {"label": "A – B", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200, "home": "A", "away": "B"}},
        odds_grid={999: {1: {"shots": {"3.5": 4.0}}}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    )
    assert wpisy == []


def test_brama_jakosci_tnie_slabe_drabinki_a_sygnaly_zostawia():
    # drabinka z pokryciem 2/10 (<50%) odpada; ta sama historia z sygnalem
    # formy by została — tu bez sygnału, więc lista pusta
    rzadki = _trend(utids=[LIGA_NOWA] * 14,
                    counts=[1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    wpisy = radar.zbuduj(
        trends=[rzadki],
        events_meta={999: {"label": "A – B", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200, "home": "A", "away": "B"}},
        odds_grid={999: {1: {"shots": {"0.5": 1.9}}}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    )
    assert wpisy == []


def test_pierwszy_szczebel_od_progu_ceny():
    # piątki, żeby szczeble miały realne pokrycie — test dotyczy progu KURSU
    # pierwszego szczebla, nie pustych linii
    tr = _trend(utids=[LIGA_NOWA] * 14,
                counts=[5, 5, 0, 5, 5, 0, 5, 5, 5, 0, 5, 5, 0, 5])
    wpisy = radar.zbuduj(
        trends=[tr],
        events_meta={999: {"label": "A – B", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200, "home": "A", "away": "B"}},
        odds_grid={999: {1: {"shots": {"0.5": 1.2, "1.5": KURS_W_OKNIE,
                                       "2.5": KURS_DRUGIEGO, "3.5": 4.9}}}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    )
    (rynek,) = wpisy[0]["rynki"]
    # 0,5 @1.20 odpada na progu ceny (MIN_KURS_PIERWSZEGO), 1,5 @1.70 wchodzi.
    # 3,5 nie wchodzi od 2026-07-30: sufit linii dla strzałów to „3+" (2,5).
    assert [s["linia"] for s in rynek["drabinka"]] == [1.5, 2.5]


def test_sufit_linii_na_karcie():
    """Decyzja usera 2026-07-30: strzały i faule max „3+" (linia 2,5),
    odbiory max „4+" (linia 3,5)."""
    assert radar.MAX_LINIA_DOMYSLNA == 2.5
    assert radar.MAX_LINIA_RYNKU["tackles"] == 3.5
    # sufit tniemy przy budowie drabinki, więc badamy ją wprost — bez bram
    # selekcji karty, które są tu nie na temat
    counts = [5, 5, 0, 5, 5, 0, 5, 5, 5, 0, 5, 5, 0, 5]
    trendy = {
        "shots": _trend(counts=counts),
        "tackles": _trend(market_code="tackles", counts=counts),
    }
    kursy = {"1.5": 1.7, "2.5": 2.2, "3.5": 3.4, "4.5": 5.0}
    rynki = radar._rynki_wpisu(
        {"shots": dict(kursy), "tackles": dict(kursy)},
        trendy, {}, "Gracz 1", {}, teraz=TERAZ, minuty_proj=85.0,
    )
    per_rynek = {r["rynek_kod"]: [s["linia"] for s in r["drabinka"]]
                 for r in rynki}
    assert max(per_rynek["shots"]) == 2.5
    assert max(per_rynek["tackles"]) == 3.5


def test_klucze_dopasowane_tokenowo_w_obie_strony():
    klucze = {"lodi renan", "ba sy", "kane"}
    # pełne nazwisko z oferty vs boiskowe i odwrotnie
    assert radar._klucze_dopasowane(klucze, "Renan Augusto Lodi") == {
        "lodi renan"
    }
    assert radar._klucze_dopasowane(klucze, "Amadou Ba-Sy") == {"ba sy"}
    assert radar._klucze_dopasowane(klucze, "Nowak") == set()


# --- BRAMY KARTY: skład, świeżość, zapas na obstawienie (2026-07-27) ---


def _pod_karte(**nadpisz):
    """Zestaw argumentów radar.zbuduj dający DOKŁADNIE jedną kartę.

    Jeden gracz z długą, świeżą historią i kwotowaną drabinką — punkt
    odniesienia dla testów bram niżej (każdy zmienia jedną rzecz).
    """
    gracz = _trend(player_id=1, counts=SIEDEM_Z_DZIESIECIU)
    kolega = _trend(player_id=7, counts=[1] * 12)
    baza = dict(
        trends=[gracz, kolega],
        events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200,
                           "home": "Klub", "away": "Rywal"}},
        odds_grid={999: {1: {"shots": {"1.5": KURS_W_OKNIE, "2.5": 3.2}}}},
        sb_cache={},
        model_pokrycie=[],
        players_out={1: {"pozycja": "M", "xi": True}},
        nazwy_pl={"shots": "Strzały"},
        teraz=TERAZ,
    )
    baza.update(nadpisz)
    return baza


def test_karta_powstaje_gdy_wszystko_gra():
    assert len(radar.zbuduj(**_pod_karte())) == 1


def test_karta_nie_powstaje_dla_zawodnika_poza_skladem():
    """Zgłoszenie 2026-07-27 (Fabio Fehr): wiemy, że go nie ma w jedenastce,
    a karta i tak wisiała, bo historia wyglądała dobrze."""
    wpisy = radar.zbuduj(**_pod_karte(poza_skladem={(999, 1)}))
    assert wpisy == []


def test_karta_nie_powstaje_na_nieswiezej_historii():
    """Ostatni występ sprzed pół roku: „trafił 8/10" opisuje kogoś, kto już
    tak nie gra (kontuzja, transfer, wypadł z rotacji)."""
    stary = _trend(player_id=1, counts=SIEDEM_Z_DZIESIECIU,
                   dni_wstecz_start=radar.MAX_DNI_SWIEZOSC + 10)
    kolega = _trend(player_id=7, counts=[1] * 12)
    assert radar.zbuduj(**_pod_karte(trends=[stary, kolega])) == []


def test_karta_nie_powstaje_tuz_przed_gwizdkiem():
    """Zapas na obstawienie: nic NOWEGO na 20 minut przed meczem."""
    meta = {999: {"label": "Klub – Rywal", "ts": TERAZ + 20 * 60,
                  "hid": 100, "aid": 200, "home": "Klub", "away": "Rywal"}}
    assert radar.zbuduj(
        **_pod_karte(events_meta=meta, margines_startu_s=90 * 60)
    ) == []
    # bez marginesu (stare zachowanie) karta by powstała
    assert len(radar.zbuduj(**_pod_karte(events_meta=meta))) == 1


def test_xi_karty_odroznia_lawke_od_nieznanego_skladu():
    """False znaczy „poza składem", None — „składu jeszcze nie znamy"."""
    (w,) = radar.zbuduj(**_pod_karte(xi_znany={(999, 1): False}))
    assert w["xi"] is False
    (w2,) = radar.zbuduj(**_pod_karte(players_out={1: {"pozycja": "M"}}))
    assert w2["xi"] is None


def test_karta_nie_powstaje_gdy_za_mocno_rozjezdzamy_sie_z_kursem():
    """Sprawa Fabio Fehra (FC Thun, 2026-07-28).

    Zawodnik grał regularnie po 90 minut i przebijał linię w 7 na 10 meczów,
    więc żadna brama „czy on w ogóle gra" go nie zatrzymała. Zatrzymać go
    miała cena: Superbet płacił 2,17 za strzał, czyli wyceniał to na 43%,
    a my liczyliśmy 59%. Rozliczenia mówią, że przy takim rozjeździe to
    zwykle MY się mylimy — a karta była numerem 1 rankingu dnia.
    """
    tr = _trend(utids=[LIGA_NOWA] * 14, counts=SIEDEM_Z_DZIESIECIU)
    wspolne = dict(
        trends=[tr],
        events_meta={999: {"label": "A – B", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200, "home": "A", "away": "B"}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    )
    # kurs zgodny z naszą szansą — karta powstaje
    assert len(radar.zbuduj(
        odds_grid={999: {1: {"shots": {"1.5": KURS_W_OKNIE, "2.5": KURS_DRUGIEGO}}}}, **wspolne
    )) == 1
    # ten sam zawodnik, kurs jak u Fehra — nasza szansa 1,4x ponad cenę rynku
    assert radar.zbuduj(
        odds_grid={999: {1: {"shots": {"1.5": 2.17}}}}, **wspolne
    ) == []


def test_rzadki_rezerwowy_nie_dostaje_karty():
    """Średnia minut potrafi wyglądać dobrze u kogoś, kto raz zagrał pełne
    90 minut, a poza tym siedzi na ławce. Karta liczy z minut, których
    rezerwowy nie dostanie."""
    minuty = [90, 90, 90, 0, 0, 0, 0, 0, 0, 0, 90, 90, 0, 90]
    tr = _trend(utids=[LIGA_NOWA] * 14, counts=SIEDEM_Z_DZIESIECIU,
                minutes=minuty)
    assert radar.udzial_startow(tr) == 0.3
    assert radar.zbuduj(
        trends=[tr],
        events_meta={999: {"label": "A – B", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200, "home": "A", "away": "B"}},
        odds_grid={999: {1: {"shots": {"1.5": KURS_W_OKNIE, "2.5": KURS_DRUGIEGO}}}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    ) == []


def test_karta_bez_smieci_trzy_najlepsze_rynki():
    """Sprzątanie karty (zgłoszenie usera 2026-07-27: „randomowe rzeczy").

    Na jednej karcie: rynek mocny, rynek z ładniejszym kursem przy tym samym
    pokryciu, rynek-przypadek (jeden niezerowy mecz) i czwarty rynek słabszy.
    Oczekiwanie: przypadek znika w całości, zostają trzy rynki, a na górze ten
    z lepszym iloczynem pokrycie × kurs.
    """
    ile = [3, 3, 0, 3, 3, 0, 3, 3, 3, 0, 3, 3, 0, 3]        # 7 z 10 > 1,5
    trendy = [
        _trend(player_id=1, market_code="shots", utids=[LIGA_NOWA] * 14, counts=ile),
        _trend(player_id=1, market_code="shots_outside_box",
               utids=[LIGA_NOWA] * 14, counts=ile),
        _trend(player_id=1, market_code="headed_sot", utids=[LIGA_NOWA] * 14,
               counts=[0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0]),  # przypadek
        _trend(player_id=1, market_code="sot", utids=[LIGA_NOWA] * 14, counts=ile),
        _trend(player_id=1, market_code="fouls_won", utids=[LIGA_NOWA] * 14,
               counts=ile),
    ]
    wpisy = radar.zbuduj(
        trends=trendy,
        events_meta={999: {"label": "A – B", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200, "home": "A", "away": "B"}},
        # każdy rynek z drugim szczeblem — o kolejności decyduje pierwszy
        # (pokrycie × kurs), ale bez następnika karta w ogóle nie powstaje
        odds_grid={999: {1: {
            "shots": {"1.5": 1.70, "2.5": 3.2},              # 0,7 × 1,70 = 1,19
            "shots_outside_box": {"1.5": 1.95, "2.5": 3.6},  # 1,37 <- najlepszy
            "headed_sot": {"1.5": 9.0, "2.5": 15.0},         # rynek-przypadek
            "sot": {"1.5": 1.80, "2.5": 3.4},                # 1,26
            "fouls_won": {"1.5": 1.66, "2.5": 3.1},          # 1,16 <- wypada
        }}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    )
    kody = [r["rynek_kod"] for r in wpisy[0]["rynki"]]
    assert "headed_sot" not in kody          # 1 niezerowy mecz na 10
    assert len(kody) == radar.MAX_RYNKOW_KARTY == 3
    assert kody[0] == "shots_outside_box"    # najwyższe pokrycie × kurs
    assert "fouls_won" not in kody           # najsłabszy z czwórki wypada


# --- UCZENIE DRABINEK (2026-07-29): pomiar progu pokrycia + własna korekta ---


def _karta_do_oceny(traf, kurs=2.40, p_final=0.45, z=10,
                    drugi_p=0.40, drugi_kurs=3.6):
    """Kandydat na kartę z DWOMA szczeblami — wszystko poza pokryciem gra.

    Bramy karty (minuty, udział startów) przechodzą, kurs jest grywalny,
    przewaga nad ceną mieści się w oknie zgody z rynkiem. Jedyną zmienną
    jest `traf`, czyli pokrycie linii — dokładnie to, o co pytamy.

    KURS 2,40, NIE 2,50 (zmiana 2026-08-08): od `CENA_WYMAGAJACA_SERII` karta
    musi mieć pokrycie 0,70, więc fikstura z ceną 2,50 mieszałaby dwie różne
    bramy i testy pokrycia pytałyby po cichu o cenę. Regułę drogiej karty
    sprawdzają osobne testy niżej.

    DRUGI SZCZEBEL JEST OBOWIĄZKOWY od 2026-08-08 (radar.MIN_P_DRUGIEGO_
    SZCZEBLA): karta bez realnego następnika nie jest drabinką, więc fikstura
    z jednym szczeblem opisywałaby produkt, którego już nie wydajemy.
    `drugi_p=None` daje starą, jednoszczeblową kartę — do testów tej bramy.
    """
    drabinka = [{
        "linia": 1.5, "kurs": kurs,
        "pokrycie": {"traf": traf, "z": z},
        "p_bazowe": p_final, "korekta": 1.0, "p_final": p_final,
    }]
    if drugi_p is not None:
        drabinka.append({
            "linia": 2.5, "kurs": drugi_kurs,
            # o jedno trafienie mniej niż pierwszy szczebel — wyższa linia musi
            # wchodzić rzadziej, ale ma zostać nad progiem MIN_POKRYCIE_DRUGIEGO,
            # bo te testy pytają o INNE bramy niż pokrycie drugiego szczebla
            "pokrycie": {"traf": max(traf - 1, 0), "z": z},
            "p_bazowe": drugi_p, "korekta": 1.0, "p_final": drugi_p,
        })
    return {
        "minuty_sr6": 85,
        "udzial_startow": 0.9,
        "rynki": [{
            "rynek_kod": "shots", "rynek": "Strzały", "drabinka": drabinka,
        }],
    }


def test_szczebel_tuz_pod_progiem_idzie_do_pomiaru_a_nie_na_karte():
    """4/10 to 0,40 — pod progiem 0,5, ale w tolerancji NEAR_POKRYCIA.

    Ma się rozliczyć w tle, żeby dało się kiedyś sprawdzić, czy próg 0,5
    faktycznie broni pieniędzy. Na karcie nie ma prawa się pojawić.
    """
    pomiar = []
    score, hero = radar._oceń_karte(_karta_do_oceny(4), pomiar_out=pomiar)
    assert hero is None and score == 0.0
    assert len(pomiar) == 1
    assert pomiar[0]["rynek_kod"] == "shots" and pomiar[0]["traf"] == 4


def test_pomiar_nie_bierze_szczebli_daleko_pod_progiem():
    """3/10 to już nie „tuż pod progiem", tylko inna liga jakości —
    mierzenie tego nie odpowiada na pytanie o próg."""
    pomiar = []
    radar._oceń_karte(_karta_do_oceny(3), pomiar_out=pomiar)
    assert pomiar == []


def test_szczebel_nad_progiem_zostaje_typem_a_nie_pomiarem():
    pomiar = []
    _score, hero = radar._oceń_karte(_karta_do_oceny(6), pomiar_out=pomiar)
    assert hero is not None and hero["traf"] == 6
    assert pomiar == []


def test_pomiar_odrzuca_szczebel_ponizej_ceny_fair():
    """Pomiar bierze szczeble „warte swojej ceny" (przewaga >= 0). Kurs 1,9
    przy szansie 0,45 to strata już na papierze — takiego typu nie
    postawilibyśmy przy ŻADNYM progu pokrycia, więc nic o progu nie mówi."""
    pomiar = []
    radar._oceń_karte(_karta_do_oceny(4, kurs=1.9), pomiar_out=pomiar)
    assert pomiar == []


def test_pomiar_bierze_szczebel_spod_progu_bez_pelnej_przewagi():
    """Kluczowe dla działania pomiaru: od szczebla spod progu NIE wymagamy
    pełnego MIN_EDGE_KARTY. Pierwsza wersja tego wymagała i dała zero
    kandydatów na 99 odrzuconych pokryciem (dry-run 2026-07-29)."""
    pomiar = []
    # szansa 0,45 przy kursie 2,25 = przewaga +0,006, czyli poniżej progu
    # karty (0,03), ale powyżej ceny fair
    radar._oceń_karte(_karta_do_oceny(4, kurs=2.25), pomiar_out=pomiar)
    assert len(pomiar) == 1
    assert 0 <= pomiar[0]["edge"] < radar.MIN_EDGE_KARTY


def test_bez_kolektora_pomiar_nic_nie_zmienia():
    """Stara ścieżka (bez pomiar_out) ma działać identycznie jak wcześniej."""
    score, hero = radar._oceń_karte(_karta_do_oceny(4))
    assert hero is None and score == 0.0


def test_korekta_strumienia_sciaga_szanse_kart():
    """Własne uczenie drabinek: gdy strumień przeszacowywał, karta pokazuje
    NIŻSZĄ szansę.

    ⚑ PRZEPISANE 2026-08-08. Wcześniej test sprawdzał, że korekta ZDEJMUJE
    kartę — przez bramę przewagi. Bramy już nie ma (patrz
    `test_karta_gorsza_od_ceny_juz_NIE_odpada`), więc korekta nie usuwa kart,
    tylko urealnia liczbę na nich. Uczenie działa dalej, zmienia się miejsce,
    w którym widać jego skutek: było „karta znika", jest „karta mówi mniej".
    """
    (bez,) = radar.zbuduj(**_pod_karte())
    (mocno_sciete,) = radar.zbuduj(**_pod_karte(korekta_logit=-0.5))
    assert mocno_sciete["ocena"]["p_final"] < bez["ocena"]["p_final"]


def test_korekta_strumienia_widac_w_p_final_karty():
    """Karta pokazuje szansę JUŻ poprawioną — nie osobno „nasze 64%"
    i osobno prawdę w logu. Delta musi być mała, bo fikstura stoi
    kilka punktów nad bramą przewagi (przy -0,15 karta znika całkiem)."""
    (bez,) = radar.zbuduj(**_pod_karte())
    (z_korekta,) = radar.zbuduj(**_pod_karte(korekta_logit=-0.05))
    assert z_korekta["ocena"]["p_final"] < bez["ocena"]["p_final"]


# --- DRUGA ŚCIEŻKA WEJŚCIA: MOCNA SERIA (2026-07-30) -----------------------


def test_mocna_seria_wchodzi_bez_przewagi_nad_kursem():
    """Decyzja usera: „drabinka to nie tylko przewaga nad kursem".
    7/10 przy kursie 2,0 to wartościowa karta, nawet gdy nasza szansa nie
    bije ceny — pokazuje realny wzorzec, a nie naszą opinię o cenie."""
    karta = _karta_do_oceny(7, kurs=2.0, p_final=0.47)
    _score, hero = radar._oceń_karte(karta)
    assert hero is not None
    assert hero["powod_wejscia"] == "seria"
    assert hero["edge"] < radar.MIN_EDGE_KARTY   # przewagi NIE ma


def test_seria_z_przewaga_stoi_na_przewadze():
    """Gdy linia ma i serię, i przewagę — karta stoi na przewadze."""
    # kurs 2,3 przy szansie 0,47 to przewaga +3,5 pp i wciąż w oknie zgody
    # z rynkiem (przy 2,5 karta odpadłaby na zbyt dużym rozjeździe)
    _score, hero = radar._oceń_karte(_karta_do_oceny(7, kurs=2.3, p_final=0.47))
    assert hero is not None and hero["powod_wejscia"] == "przewaga"


def test_slaba_seria_przy_taniej_cenie_dalej_odpada():
    """68 z 87 odrzuceń to tanie linie — ich wpuszczenie zamieniłoby
    „za mało kart" na „dużo słabych kart" (pomiar 30.07)."""
    _score, hero = radar._oceń_karte(_karta_do_oceny(5, kurs=1.6, p_final=0.40))
    assert hero is None


def test_karta_gorsza_od_ceny_juz_NIE_odpada():
    """⚑ PRZEPISANE 2026-08-08 — reguła zmieniona świadomie, nie zepsuta.

    Do tego dnia karta, której nasza szansa była wyraźnie gorsza od ceny
    (tu −10 pp), odpadała. Pomiar na 86 rozliczonych kartach pokazał, że ta
    brama nie broniła pieniędzy, bo przewaga NIE PORZĄDKUJE wyników:

        przewaga < 0      n=18   trafia 33,3%   zwrot −25,7%
        przewaga 0-3 pp   n=17   trafia 17,6%   zwrot −61,9%
        przewaga 3-8 pp   n=42   trafia 35,7%   zwrot −24,1%
        przewaga 8 pp+    n= 9   trafia 22,2%   zwrot −57,4%

    Karty BEZ przewagi wypadały LEPIEJ niż te z przewagą 8 pp+. Decyzja usera:
    cel produktu to wyławianie kursów 2,00+, a o karcie mają decydować rzeczy,
    które realnie rozdzielają wyniki — pokrycie, cena i rynek.
    """
    karta = _karta_do_oceny(7, kurs=2.0, p_final=0.40)   # edge = −0,10
    _score, hero = radar._oceń_karte(karta)
    assert hero is not None
    assert hero["kurs"] == 2.0


def test_droga_karta_bez_serii_odpada():
    """...ale cena JEST bramą, bo ona akurat rozdziela wyniki.

    Zmierzone 08.08 po odsianiu fauli: kurs 2,00–2,50 daje −1,1% na 22 kartach,
    a 2,50+ nadal −35,7% na 20. Decyzja usera: „wpuszczaj, ale tylko z mocnym
    pokryciem" — powyżej 2,50 karta musi mieć serię 7/10.
    """
    # p_final dobrane do ceny, żeby test pytał WYŁĄCZNIE o pokrycie: przy 2,60
    # cena rynku bez marży to ~0,358, więc 0,40 mieści się pod górną granicą
    # rozjazdu (MAX_ROZJAZD_KARTY). Bez tego karta odpadałaby na innej bramie
    # i test kłamałby o tym, co sprawdza.
    slaba = _karta_do_oceny(6, kurs=2.60, p_final=0.40)
    assert radar._oceń_karte(slaba)[1] is None
    mocna = _karta_do_oceny(8, kurs=2.60, p_final=0.40)
    assert radar._oceń_karte(mocna)[1] is not None


def test_tansza_karta_nie_potrzebuje_serii():
    """Poniżej progu ceny zostaje zwykłe pokrycie — inaczej zabralibyśmy
    produktowi jego serce (pasmo 2,00–2,50, jedyne bliskie zeru)."""
    assert radar._oceń_karte(_karta_do_oceny(6, kurs=2.30))[1] is not None


def test_faule_nie_daja_kart_wcale():
    """18 kart na faulach popełnionych, JEDNA trafiona — i to niezależnie od
    ceny (2,00+: −80,4% na 13 kartach; poniżej 2,00: −100% na 5). Rynek nie
    jest słaby „przy wysokich kursach", jest słaby zawsze."""
    karta = _karta_do_oceny(8, kurs=2.30)
    karta["rynki"][0]["rynek_kod"] = "fouls_committed"
    assert radar._oceń_karte(karta)[1] is None
    # ...a ten sam materiał na innym rynku kartę daje
    assert radar._oceń_karte(_karta_do_oceny(8, kurs=2.30))[1] is not None
