"""Imienny rentgen drabinek (jobs/radar_imienny.py, 2026-09-21).

Rentgen radaru trzymał same sumy per brama, więc „czemu nie było Mandragory?"
nie miało odpowiedzi po meczu. Tu pilnujemy trzech rzeczy: każda para z oferty
dostaje werdykt po nazwisku, zapis nie czyta nic z bazy (return=minimal) i brak
tabeli nie kładzie cyklu.
"""
import json

import pytest

from footstats import supa
from footstats.jobs import radar, radar_imienny
from footstats.sources.statshub import StatshubTrend

TERAZ = 1_800_000_000
DZIEN = 86_400
LIGA_NOWA = 45
LIGA_STARA = 202
SIEDEM_Z_DZIESIECIU = [3, 3, 0, 3, 2, 0, 3, 2, 3, 0, 3, 2, 0, 3]


@pytest.fixture(autouse=True)
def _bez_sieci(monkeypatch):
    monkeypatch.setattr(radar.betclic, "paruj_mecze", lambda nasze: ({}, []))
    monkeypatch.setattr(
        radar.statshub, "fetch_tournament_name",
        lambda utid: {LIGA_STARA: "Stara Liga", LIGA_NOWA: "Nowa Liga"}.get(utid, ""),
    )


def _trend(*, player_id=1, team_id=100, market_code="shots", counts=None,
           utids=None):
    n = len(counts or [])
    return StatshubTrend(
        player_id=player_id, player_name=f"Gracz {player_id}", position="M",
        team_id=team_id, team_name="Klub", opponent_id=200, opponent_name="Rywal",
        is_home=True, market_code=market_code, line=1.5, in_predicted_lineup=True,
        league_average=None, opponent_average=None, opponent_rank=None,
        total_ranks=None, event_id=999,
        counts=[float(c) for c in (counts or [])],
        minutes=[90.0] * n,
        timestamps=[TERAZ - (2 + 7 * i) * DZIEN for i in range(n)],
        started=[True] * n,
        game_utids=list(utids or [LIGA_NOWA] * n),
        game_opponent_ids=[0] * n,
    )


# --- moduł -------------------------------------------------------------------

def test_odnotuj_ostatni_werdykt_wygrywa_i_wiersz_ma_dzien_meczu():
    im: dict = {}
    radar_imienny.odnotuj(im, 7, 11, "ocena_przeszla", podmiot="Ktoś",
                          kickoff_ts=TERAZ + DZIEN, minuty_sr6=88)
    radar_imienny.odnotuj(im, 7, 11, "karta", miejsce=3, hero="shots 1.5@1.9")
    (w,) = radar_imienny.wiersze(im, TERAZ)
    assert w["brama"] == "karta" and w["podmiot"] == "Ktoś"
    assert w["dzien"] == "2027-01-16"          # TERAZ + doba, UTC
    szczegol = json.loads(w["szczegol"])
    assert szczegol["miejsce"] == 3 and szczegol["minuty_sr6"] == 88
    assert "podmiot" not in szczegol           # kolumny nie dublują się w szczególe


def test_szczegol_przyciety_do_limitu():
    im: dict = {}
    radar_imienny.odnotuj(im, 1, 2, "x", powody={f"p{i}": i for i in range(200)})
    (w,) = radar_imienny.wiersze(im, TERAZ)
    assert len(w["szczegol"]) <= radar_imienny.MAX_SZCZEGOL


def test_opis_rynkow_jest_krotki_i_czytelny():
    rynki = [{"rynek_kod": "shots", "drabinka": [
        {"linia": 0.5, "kurs": 1.62, "pokrycie": {"traf": 6, "z": 10},
         "pokrycie5": {"traf": 3, "z": 5}},
        {"linia": 1.5, "kurs": 2.9, "pokrycie": {"traf": 3, "z": 10},
         "pokrycie5": {"traf": 1, "z": 5}},
    ]}]
    assert radar_imienny.opis_rynkow(rynki) == {
        "shots": "0.5@1.62 6/10 f3/5 | 1.5@2.9 3/10 f1/5"}


# --- radar: każda para z oferty dostaje werdykt ------------------------------

def test_zbuduj_daje_werdykt_kazdej_parze_z_oferty():
    kolega = _trend(player_id=7, utids=[LIGA_NOWA] * 12, counts=[1] * 12)
    nowy = _trend(player_id=1, utids=[LIGA_NOWA] + [LIGA_STARA] * 12,
                  counts=SIEDEM_Z_DZIESIECIU)
    im: dict = {}
    wpisy = radar.zbuduj(
        trends=[kolega, nowy],
        events_meta={999: {"label": "Klub – Rywal", "ts": TERAZ + DZIEN,
                           "hid": 100, "aid": 200, "home": "Klub", "away": "Rywal"}},
        odds_grid={
            999: {
                1: {"shots": {"1.5": 1.7, "2.5": 3.2}},   # karta
                2: {"shots": {"1.5": 1.7}},               # bukmacher kwotuje, historii brak
                3: {"shots": {"1.5": 1.7}},               # poza ogłoszonym składem
            },
            555: {4: {"shots": {"0.5": 1.5}}},            # mecz bez meta
        },
        sb_cache={}, model_pokrycie=[],
        players_out={1: {"pozycja": "M", "xi": True},
                     2: {"nazwa": "Bez Historii", "druzyna": "Klub"}},
        nazwy_pl={"shots": "Strzały"}, teraz=TERAZ,
        poza_skladem={(999, 3)},
        imienny_out=im,
    )
    assert [w["podmiot"] for w in wpisy] == ["Gracz 1"]
    bramy = {k: v["brama"] for k, v in im.items()}
    assert bramy == {
        (999, 1): "karta",
        (999, 2): "zawodnik_bez_historii",
        (999, 3): "zawodnik_poza_skladem",
        (555, 4): "mecz_bez_meta",
    }
    karta = im[(999, 1)]
    assert karta["miejsce"] == 1 and karta["hero"].startswith("shots 1.5@")
    assert karta["mecz"] == "Klub – Rywal" and karta["kickoff_ts"] == TERAZ + DZIEN
    # nazwisko z `players_out`, gdy trendu nie ma
    assert im[(999, 2)]["podmiot"] == "Bez Historii"
    assert im[(999, 2)]["rynki_oferty"] == ["shots"]
    # wiersze do tabeli — jeden na parę
    assert len(radar_imienny.wiersze(im, TERAZ)) == 4


def test_zbuduj_bez_imienny_out_nic_nie_zapisuje():
    """Parametr jest opcjonalny — stare wywołania działają bez zmian."""
    wpisy = radar.zbuduj(trends=[], events_meta={}, odds_grid={1: {2: {}}},
                         sb_cache={}, model_pokrycie=[], players_out={},
                         nazwy_pl={}, teraz=TERAZ)
    assert wpisy == []


# --- zapis: bez odczytu, bez odpowiedzi, bez wyjątku -------------------------

class _Odp:
    def __init__(self, status):
        self.status_code = status
        self.text = ""

    def json(self):
        return []


@pytest.fixture()
def baza(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setattr(supa.time, "sleep", lambda _: None)
    wywolania = {"post": [], "delete": [], "get": []}
    monkeypatch.setattr(supa.requests, "post",
                        lambda url, headers=None, data=None, **kw:
                        (wywolania["post"].append((url, headers, json.loads(data)))
                         or _Odp(201)))
    monkeypatch.setattr(supa.requests, "delete",
                        lambda url, headers=None, **kw:
                        (wywolania["delete"].append((url, headers)) or _Odp(204)))
    monkeypatch.setattr(supa.requests, "get",
                        lambda url, headers=None, **kw:
                        (wywolania["get"].append(url) or _Odp(200)))
    return wywolania


def test_zapisz_upsertuje_bez_odpowiedzi_i_sprzata_stare_dni(baza):
    im: dict = {}
    for i in range(2500):
        radar_imienny.odnotuj(im, 1, i, "sito_sila_ponizej_progu", kickoff_ts=TERAZ)
    assert radar_imienny.zapisz(im, TERAZ) is True
    # 2500 wierszy w paczkach po 1000, każda z return=minimal i kluczem konfliktu
    assert [len(w) for _u, _h, w in baza["post"]] == [1000, 1000, 500]
    url, h, _ = baza["post"][0]
    assert url.endswith("/rest/v1/radar_imienny?on_conflict=mecz_id,podmiot_id")
    assert "return=minimal" in h["Prefer"] and "merge-duplicates" in h["Prefer"]
    # sprzątanie: jeden DELETE z granicą retencji, też bez odpowiedzi
    (durl, dh), = baza["delete"]
    assert "radar_imienny?dzien=lt.2027-01-11" in durl     # TERAZ − 4 dni
    assert dh["Prefer"] == "return=minimal"
    # i ANI JEDNEGO odczytu — to jest cały sens tabeli zamiast klucza
    assert baza["get"] == []


def test_brak_tabeli_nie_klade_cyklu(baza, monkeypatch, capsys):
    monkeypatch.setattr(supa.requests, "post",
                        lambda url, headers=None, data=None, **kw: _Odp(404))
    supa._tabele_bez_migracji.clear()
    im: dict = {}
    radar_imienny.odnotuj(im, 1, 2, "karta", kickoff_ts=TERAZ)
    assert radar_imienny.zapisz(im, TERAZ) is False
    assert radar_imienny.zapisz(im, TERAZ) is False
    err = capsys.readouterr().err
    assert err.count("wklej migrację") == 1, "komunikat raz na przebieg, nie co zapis"
    assert baza["delete"] == [], "bez zapisu nie ma sprzątania"


def test_zapisz_pusty_slownik_nic_nie_robi(baza):
    assert radar_imienny.zapisz({}, TERAZ) is False
    assert radar_imienny.zapisz(None, TERAZ) is False
    assert baza["post"] == []
