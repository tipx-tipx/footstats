"""Testy detektorów radaru (jobs/radar.py) na syntetycznych trendach."""

from footstats.jobs import radar
from footstats.sources.statshub import StatshubTrend

TERAZ = 1_800_000_000
DZIEN = 86_400

LIGA_NOWA = 45      # np. austriacka Bundesliga
LIGA_STARA = 202    # np. Ekstraklasa
KADRA = 16


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
                  counts=[2] * 13)
    wpisy = radar.zbuduj(
        trends=[kolega, nowy],
        events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200,
                           "home": "Klub", "away": "Rywal"}},
        odds_grid={999: {1: {"shots": {"1.5": 2.05, "2.5": 3.2}}}},
        sb_cache={},
        model_pokrycie=[{"podmiot": "Gracz 1", "rynek_kod": "shots",
                         "linia": 1.5, "strona": "powyzej",
                         "p_model": 0.44}],
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
    assert (s0["linia"], s0["kurs"], s0["p_model"]) == (1.5, 2.05, 0.44)
    # pokrycie: wszystkie ostatnie występy (2 zdarzenia) przebiły linię 1,5
    assert s0["pokrycie"] == {"traf": 10, "z": 10}
    assert rynek["drabinka"][1]["p_model"] is None
    assert rynek["ostatnie"][:3] == [2, 2, 2]
    assert w["stara_liga"] == "Stara Liga"


def test_zbuduj_drabinka_bez_sygnalu_z_forma_i_rywalem():
    # gracz zadomowiony w lidze, bez serii — kiedyś radar go pomijał,
    # teraz dostaje wpis rodzaju "drabinka" z pełną analizą
    tr = _trend(utids=[LIGA_NOWA] * 14, counts=[2] * 14)
    tr.opponent_average = 11.4
    tr.opponent_rank = 3
    tr.total_ranks = 18
    wpisy = radar.zbuduj(
        trends=[tr],
        events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200,
                           "home": "Klub", "away": "Rywal"}},
        odds_grid={999: {1: {"shots": {"1.5": 2.05, "2.5": 3.2}}}},
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
    assert rynek["forma"]["okno90"] == rynek["forma"]["baza90"] == 2.0
    assert rynek["rywal"] == {"srednia": 11.4, "rank": 3, "z": 18,
                              "liga": None}
    assert len(rynek["ostatnie"]) == 10  # OSTATNIE_N występów na karcie


def test_zbuduj_dolacza_srednie_sezonowe_z_cache():
    tr = _trend(utids=[LIGA_NOWA] * 14, counts=[2] * 14)
    sezon = {"turniej": "Serie B", "rok": "2025", "mecze": 32,
             "minuty": 1738, "na_mecz": {"shots": 2.0}, "na90": {"shots": 3.31}}
    wpisy = radar.zbuduj(
        trends=[tr],
        events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200,
                           "home": "Klub", "away": "Rywal"}},
        odds_grid={999: {1: {"shots": {"1.5": 2.05}}}},
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
                  counts=[2] * 13)
    zwykly = _trend(player_id=7, utids=[LIGA_NOWA] * 12, counts=[1] * 12)
    import unittest.mock as _m
    with _m.patch.object(radar.statshub, "fetch_tournament_name",
                         lambda utid: {LIGA_STARA: "Stara",
                                       LIGA_NOWA: "Nowa"}.get(utid, "")):
        wpisy = radar.zbuduj(
            trends=[kolega, nowy, zwykly],
            events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                               "hid": 100, "aid": 200,
                               "home": "Klub", "away": "Rywal"}},
            odds_grid={999: {1: {"shots": {"1.5": 2.05}},
                             7: {"shots": {"0.5": 1.5}}}},
            sb_cache={},
            model_pokrycie=[],
            players_out={},
            nazwy_pl={},
            teraz=TERAZ,
        )
    assert [w["rodzaj"] for w in wpisy] == ["transfer", "drabinka"]


def test_drabinka_przycieta_z_szumu():
    # 8 linii, od 3. wzwyż kosmiczne kursy — karta ma pokazywać grywalne
    tr = _trend(utids=[LIGA_NOWA] * 14, counts=[2] * 14)
    wpisy = radar.zbuduj(
        trends=[tr],
        events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200,
                           "home": "Klub", "away": "Rywal"}},
        odds_grid={999: {1: {"shots": {
            "0.5": 1.12, "1.5": 1.85, "2.5": 3.4, "3.5": 6.1,
            "4.5": 13.0, "5.5": 23.0, "6.5": 41.0, "7.5": 67.0,
        }}}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    )
    (rynek,) = wpisy[0]["rynki"]
    linie = [s["linia"] for s in rynek["drabinka"]]
    # kurs 13.0 na linii 4,5 przekracza MAX_KURS_SZCZEBLA -> reszta ucięta
    assert linie == [0.5, 1.5, 2.5, 3.5]
    # minuty_sr6: pełne mecze w historii
    assert wpisy[0]["minuty_sr6"] == 90


def test_sortowanie_po_meczach_potem_po_score():
    # dwa mecze: późniejszy ma "lepszego" gracza, ale wcześniejszy mecz
    # i tak idzie pierwszy (chronologia); w meczu decyduje score
    def _meta(ts):
        return {"label": "A – B", "ts": ts, "hid": 100, "aid": 200,
                "home": "A", "away": "B"}
    slaby = _trend(player_id=1, utids=[LIGA_NOWA] * 14,
                   counts=[0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0])
    mocny = _trend(player_id=2, utids=[LIGA_NOWA] * 14, counts=[3] * 14)
    pozny = _trend(player_id=3, utids=[LIGA_NOWA] * 14, counts=[3] * 14)
    pozny.event_id = 998
    wpisy = radar.zbuduj(
        trends=[slaby, mocny, pozny],
        events_meta={999: _meta(TERAZ + DZIEN), 998: _meta(TERAZ + 2 * DZIEN)},
        odds_grid={999: {1: {"shots": {"1.5": 2.1}},
                         2: {"shots": {"1.5": 2.1}}},
                   998: {3: {"shots": {"1.5": 2.1}}}},
        sb_cache={}, model_pokrycie=[], players_out={}, nazwy_pl={},
        teraz=TERAZ,
    )
    assert [w["podmiot_id"] for w in wpisy] == [2, 1, 3]


def test_klucze_dopasowane_tokenowo_w_obie_strony():
    klucze = {"lodi renan", "ba sy", "kane"}
    # pełne nazwisko z oferty vs boiskowe i odwrotnie
    assert radar._klucze_dopasowane(klucze, "Renan Augusto Lodi") == {
        "lodi renan"
    }
    assert radar._klucze_dopasowane(klucze, "Amadou Ba-Sy") == {"ba sy"}
    assert radar._klucze_dopasowane(klucze, "Nowak") == set()
