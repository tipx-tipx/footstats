"""Kontekst meczu w drabinkach: rywal per rynek, sędzia, ranking kart.

Sedno: karta ma odpowiadać na „gra z najlepszą defensywą ligi, czemu miałby
oddać 2 strzały?". Testy pilnują KIERUNKU tej korekty — to tu siedział błąd
zmierzony 2026-07-26 (rank 1 = najszczelniejszy rywal był czytany jako
najhojniejszy, więc typy przeciw najlepszym defensywom dostawały bonus).
"""

from footstats.jobs import radar
from footstats.model import kontekst_drabinki as kd
from footstats.sources.statshub import StatshubTrend

TERAZ = 1_800_000_000
DZIEN = 86_400
LIGA = 45


def _trend(
    *, market_code="shots", counts=None, minutes=None, player_id=1,
    opponent_average=None, league_average=None, opponent_rank=None,
    total_ranks=None, opponent_ids=None, position="F", team_id=100,
):
    n = len(counts or [])
    return StatshubTrend(
        player_id=player_id, player_name=f"Gracz {player_id}",
        position=position, team_id=team_id, team_name="Klub",
        opponent_id=200, opponent_name="Rywal", is_home=True,
        market_code=market_code, line=1.5, in_predicted_lineup=True,
        league_average=league_average, opponent_average=opponent_average,
        opponent_rank=opponent_rank, total_ranks=total_ranks, event_id=999,
        counts=[float(c) for c in (counts or [])],
        minutes=[float(m) for m in (minutes or [90] * n)],
        timestamps=[TERAZ - (2 + 7 * i) * DZIEN for i in range(n)],
        game_positions=[position] * n,
        game_utids=[LIGA] * n,
        game_opponent_ids=list(opponent_ids or [300 + i for i in range(n)]),
        game_opponents=[f"Rywal {i}" for i in range(n)],
    )


# --- KIERUNEK KOREKTY RYWALA (regresja buga z odwróconym znakiem) ---

def test_szczelny_rywal_scina_a_hojny_podbija():
    szczelny = _trend(opponent_average=10.4, league_average=12.9,
                      opponent_rank=4, total_ranks=30, counts=[2] * 10)
    hojny = _trend(opponent_average=15.5, league_average=12.9,
                   opponent_rank=27, total_ranks=30, counts=[2] * 10)
    m_szczelny, opis_s = kd.mnoznik_rywala("shots", szczelny)
    m_hojny, _ = kd.mnoznik_rywala("shots", hojny)
    assert m_szczelny < 1.0 < m_hojny
    assert opis_s["zrodlo"] == "statshub"


def test_rank_sam_w_sobie_nie_decyduje_o_kierunku():
    """Rank 1 przy WYSOKIEJ dopuszczanej wartości musi podbijać.

    Zabezpieczenie na wypadek, gdyby statshub kiedyś odwrócił numerację:
    liczy stosunek średnich, rank jest tylko etykietą do UI.
    """
    tr = _trend(opponent_average=15.0, league_average=12.0,
                opponent_rank=1, total_ranks=30, counts=[2] * 10)
    m, _ = kd.mnoznik_rywala("shots", tr)
    assert m > 1.0


def test_agregat_w_niespojnych_jednostkach_jest_odrzucany():
    """Zmierzone na żywym cyklu 2026-07-26: Boca Juniors miało w feedzie
    opponentAverage=172,0 przy leagueAverage=25,18 (suma sezonu vs średnia
    na mecz). Surowy stosunek 6,8 wchodził prosto w górny cap i dawał karcie
    fałszywy bonus, jakby to była najhojniejsza defensywa świata."""
    tr = _trend(opponent_average=172.0, league_average=25.18,
                opponent_rank=32, total_ranks=60, counts=[2] * 10)
    m, opis = kd.mnoznik_rywala("shots", tr)
    assert m == 1.0
    assert opis["zrodlo"] == "brak"
    assert opis["odrzucony_agregat"] > 2.5


def test_koncesje_modelu_po_nazwie_ratuja_ligi_spoza_feedu():
    """Ekstraklasa: brak agregatów statshuba i brak historii w feedzie
    propsów — kontekst rywala musi przyjść z banku trendów modelu."""

    class _BankStub:
        def lookup(self, druzyna, market, pozycja, **kw):
            assert druzyna == "Wisła Kraków"
            return (2.4, 1.6, 9)   # dopuszcza 2,4 przy normie 1,6

    m, opis = kd.mnoznik_rywala(
        "shots", _trend(counts=[2] * 10), koncesje_nazw=_BankStub(),
        nazwa_rywala="Wisła Kraków", nazwa_druzyny="GKS Katowice",
        pozycja="F",
    )
    assert m > 1.0
    assert opis["zrodlo"] == "bank"


def test_brak_danych_rywala_jest_neutralny():
    m, opis = kd.mnoznik_rywala("shots", _trend(counts=[2] * 10))
    assert m == 1.0 and opis["zrodlo"] == "brak"


def test_koncesje_z_historii_gdy_statshub_milczy():
    """Ścieżka `performance` (Ekstraklasa): rywala liczymy z własnego banku."""
    # rywal 777 dostaje po 5 strzałów od każdego, reszta ligi po 1
    obce = {
        (1, i): {"shots": _trend(
            player_id=i, counts=[1] * 10,
            opponent_ids=[400 + j for j in range(10)],
        )}
        for i in range(2, 12)
    }
    przeciw = {
        (1, 50 + i): {"shots": _trend(
            player_id=50 + i, counts=[5] * 4, opponent_ids=[777] * 4,
        )}
        for i in range(4)
    }
    koncesje = kd.zbuduj_koncesje({**obce, **przeciw}, TERAZ)
    m, opis = kd.mnoznik_rywala(
        "shots", _trend(counts=[2] * 10), koncesje, 777, "F", TERAZ,
    )
    assert m > 1.0
    assert opis["zrodlo"] == "historia"


# --- SĘDZIA ---

def test_sedzia_dziala_tylko_na_rynki_faulowe():
    surowy = {"sedzia": "Kowalski", "mnoznik": 1.30, "n": 15}
    m_faule, opis = kd.mnoznik_sedziego("fouls_committed", surowy)
    m_strzaly, _ = kd.mnoznik_sedziego("shots", surowy)
    assert m_faule > 1.0
    assert opis["sedzia"] == "Kowalski"
    assert m_strzaly == 1.0


def test_brak_obsady_sedziego_jest_neutralny_ale_zaraportowany():
    m, opis = kd.mnoznik_sedziego("fouls_committed", None)
    assert m == 1.0
    assert opis["zrodlo"] == "brak_obsady"   # UI ma napisać „nie wiemy"


def test_pobłazliwy_sedzia_scina_faule():
    m, _ = kd.mnoznik_sedziego(
        "fouls_committed", {"sedzia": "Nowak", "mnoznik": 0.7, "n": 20}
    )
    assert m < 1.0


# --- CAŁA ŚCIEŻKA: p_final i ranking kart ---

def _zbuduj(opponent_average, league_average, sedzia_by_mid=None):
    """Jedna karta: 8/10 pokrycia linii 1,5 strzału, kurs 2,00."""
    tr = _trend(
        counts=[2, 3, 2, 2, 0, 2, 3, 2, 2, 1], league_average=league_average,
        opponent_average=opponent_average, opponent_rank=5, total_ranks=30,
    )
    trends = [tr]
    events_meta = {
        999: {"label": "Klub – Rywal", "ts": TERAZ + 3 * 3600,
              "hid": 100, "aid": 200, "home": "Klub", "away": "Rywal"},
    }
    odds_grid = {999: {1: {"shots": {"1.5": 2.0, "2.5": 4.0}}}}
    return radar.zbuduj(
        trends, events_meta, odds_grid, {}, [], {},
        {"shots": "Strzały"}, TERAZ, sedzia_by_mid=sedzia_by_mid,
    )


def test_karta_dostaje_ocene_klase_i_p_final():
    wpisy = _zbuduj(opponent_average=13.0, league_average=13.0)
    assert len(wpisy) == 1
    w = wpisy[0]
    assert w["hero"]["rynek_kod"] == "shots"
    assert w["ocena"]["miejsce"] == 1
    assert w["ocena"]["klasa"] in ("top", "mocny", "solidny")
    # p_final to skorygowane pokrycie, nie surowe 8/10
    assert 0.0 < w["ocena"]["p_final"] < 1.0
    assert w["ocena"]["kontekst"]["rywal"]["zrodlo"] == "statshub"


def test_ten_sam_zawodnik_ma_mniejsza_przewage_z_trudnym_rywalem():
    """Rdzeń pytania usera: identyczna historia, inny rywal, inna ocena."""
    latwy = _zbuduj(opponent_average=16.0, league_average=13.0)[0]
    trudny = _zbuduj(opponent_average=9.0, league_average=13.0)[0]
    assert trudny["ocena"]["p_final"] < latwy["ocena"]["p_final"]
    assert trudny["ocena"]["edge"] < latwy["ocena"]["edge"]
    # pokrycie w obu przypadkach IDENTYCZNE — różnicę robi wyłącznie kontekst
    assert trudny["ocena"]["p_bazowe"] == latwy["ocena"]["p_bazowe"]


def test_sedzia_nie_rusza_rynku_strzalow():
    bez = _zbuduj(13.0, 13.0)[0]
    z_surowym = _zbuduj(
        13.0, 13.0,
        sedzia_by_mid={999: {"sedzia": "Kowalski", "mnoznik": 1.4, "n": 20}},
    )[0]
    assert bez["ocena"]["p_final"] == z_surowym["ocena"]["p_final"]
