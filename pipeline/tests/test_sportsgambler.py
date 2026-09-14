"""SportsGambler jako źródło składów (wpięte 2026-09-14).

Fragmenty HTML skopiowane ze strony 14.09 (lista + endpoint składu Como–Parma):
Liberali i Frigan siedzieli na ławce — dokładnie przypadek zgłoszony przez
właściciela (karta drabinki na zawodnika, który „nigdy nie wychodzi w podstawie").
"""
import datetime as dt

from footstats.sources import sportsgambler as SG

LISTA = '''
<h3 class="date-headline">Monday 14 September</h3>
<div class="lineup-row"> <div class="fxs-info"> <span class="fxs-time">18:30</span>
<span class="fxs-league h-sm">Serie A</span> </div> <div class="fxs-game">
<span class="fxs-team home">Como</span> <span class="vs-teams"> vs </span>
<span class="fxs-team">Parma</span> </div> <div class="fxs-btn">
<a href="#" id="5749671" onClick="reply_click(5749671)"> <span class="h-sm">Confirmed Lineups</span></a>
</div></div><!--table row-->
<div class="lineup-row"> <div class="fxs-info"> <span class="fxs-time">19:00</span>
<span class="fxs-league h-sm">Eliteserien</span> </div> <div class="fxs-game">
<span class="fxs-team home">Bodo/Glimt</span> <span class="vs-teams"> vs </span>
<span class="fxs-team">Sandefjord</span> </div> <div class="fxs-btn">
<a href="#" id="5105005" onClick="reply_click(5105005)"> <span class="h-sm">Predicted Lineups</span></a>
</div></div><!--table row-->
<h3 class="date-headline">Tuesday 15 September</h3>
<div class="lineup-row"> <div class="fxs-info"> <span class="fxs-time">20:00</span>
<span class="fxs-league h-sm">Premier League</span> </div> <div class="fxs-game">
<span class="fxs-team home">Newcastle</span> <span class="vs-teams"> vs </span>
<span class="fxs-team">Leeds</span> </div> <div class="fxs-btn">
<a href="#" id="777" onClick="reply_click(777)"> <span class="h-sm">Predicted Lineups</span></a>
</div></div><!--table row-->
'''

SKLAD = '''
<div class="lineups-formation bg-green-dark h-sm">
<h3><span>Como Confirmed Lineup</span> <span class="lineups-toggle-formation">4-2-3-1</span></h3>
<h3><span>Parma Predicted Lineup</span> <span class="lineups-toggle-formation">3-4-2-1</span></h3></div>
<div class="lineups"><div class="lineups-container"><div class="lineups-home reverse">
<div class="players-line goalie"><span class="lineups-player"><span class="player-profile">97</span><span class="player-name">Robert Sanchez</span></span></div>
<div class="players-line"><span class="lineups-player"><span class="player-profile">10</span><span class="player-name">Nico Paz</span></span></div>
</div><div class="lineups-away">
<div class="players-line goalie"><span class="lineups-player"><span class="player-profile">40</span><span class="player-name">Edoardo Corvi</span></span></div>
</div></div></div><!--lineups-->
<div class="lineups-teams"><div class="teams-item"><h3>Como Substitutes</h3><ul class="lineups-sub">
<li class="sub-player"><span class="sub-player-no">30</span>Mattia Liberali</li>
<li class="sub-player"><span class="sub-player-no">9</span>Anastasios Douvikas</li></ul></div>
<div class="teams-item"><h3>Parma Substitutes</h3><ul class="lineups-sub">
<li class="sub-player"><span class="sub-player-no">20</span>Matija Frigan</li></ul></div></div>
'''


def test_lista_meczow_zna_date_i_etykiete():
    L = SG.lista_meczow(LISTA, dzis=dt.date(2026, 9, 14))
    assert [(r["home"], r["away"], r["data"], r["confirmed"]) for r in L] == [
        ("Como", "Parma", "2026-09-14", True),
        ("Bodo/Glimt", "Sandefjord", "2026-09-14", False),
        ("Newcastle", "Leeds", "2026-09-15", False),
    ]
    assert L[0]["id"] == 5749671 and L[0]["kickoff_ts"] > 0


def test_sklad_meczu_rozdziela_xi_i_lawke():
    sk = SG.sklad_meczu(SKLAD)
    assert sk["home"]["team"] == "Como" and sk["home"]["confirmed"]
    assert sk["home"]["xi"] == {"robert sanchez", "nico paz"}
    # numer koszulki NIE skleja się z nazwiskiem (pierwsza wersja dawała „30mattia liberali")
    assert sk["home"]["bench"] == {"mattia liberali", "anastasios douvikas"}
    assert sk["away"]["xi"] == {"edoardo corvi"} and not sk["away"]["confirmed"]
    assert sk["away"]["bench"] == {"matija frigan"}


def test_pusty_sklad_gdy_strona_bez_jedenastek():
    assert SG.sklad_meczu("<div>nic</div>") == {}


def _pobierz(url):
    return LISTA if url == SG.LISTA_URL else SKLAD


def test_fetch_kluczuje_nasza_nazwa_i_paruje_skrocone_nazwy():
    """SG pisze „Newcastle", my „Newcastle United" — para przez zbiory słów,
    a wynik pod NASZĄ nazwą, żeby `rotowire.predicted_status` trafiał."""
    dzis = dt.date(2026, 9, 14)
    teraz = int(dt.datetime(2026, 9, 14, 10, tzinfo=dt.timezone.utc).timestamp())
    nasze = [
        {"klucz": 1, "home": "Como", "away": "Parma",
         "kickoff_ts": teraz + 6 * 3600},
        {"klucz": 2, "home": "Newcastle United", "away": "Leeds United",
         "kickoff_ts": teraz + 33 * 3600},
        {"klucz": 3, "home": "Wisła Kraków", "away": "Jagiellonia",
         "kickoff_ts": teraz + 5 * 3600},                    # nie ma w SG
    ]
    mapa, pamiec, lic = SG.fetch_predicted_lineups(
        nasze, {}, teraz=teraz, pobierz=_pobierz, dzis=dzis)
    assert lic["sparowane"] == 2 and lic["pobrane"] == 2
    assert "como" in mapa and mapa["como"]["confirmed"]
    assert "mattia liberali" in mapa["como"]["bench"]
    assert "newcastle united" in mapa and "leeds united" in mapa
    assert "wisla krakow" not in mapa
    assert set(pamiec) == {"5749671", "777"}


def test_pamiec_oszczedza_zapytania():
    dzis = dt.date(2026, 9, 14)
    teraz = int(dt.datetime(2026, 9, 14, 10, tzinfo=dt.timezone.utc).timestamp())
    nasze = [{"klucz": 1, "home": "Como", "away": "Parma",
              "kickoff_ts": teraz + 6 * 3600}]
    _, pamiec, _ = SG.fetch_predicted_lineups(nasze, {}, teraz=teraz,
                                              pobierz=_pobierz, dzis=dzis)
    liczby = {"n": 0}

    def _licz(url):
        liczby["n"] += 1
        return _pobierz(url)

    # skład ogłoszony (home confirmed, away predicted → confirmed=False) po 1 h:
    # przewidywany jest świeży (< 3 h) → tylko lista
    mapa, _, lic = SG.fetch_predicted_lineups(
        nasze, pamiec, teraz=teraz + 3600, pobierz=_licz, dzis=dzis)
    assert liczby["n"] == 1 and lic["z_pamieci"] == 1 and "como" in mapa
    # po 4 h przewidywany jest stary → pytamy ponownie
    SG.fetch_predicted_lineups(nasze, pamiec, teraz=teraz + 4 * 3600,
                               pobierz=_licz, dzis=dzis)
    assert liczby["n"] == 3


def test_dolacz_do_rotowire_nie_nadpisuje_rotowire_bez_powodu():
    roto = {"como": {"xi": {"a"}, "confirmed": False}}
    sg = {"como": {"xi": {"b"}, "confirmed": False, "bench": set(), "zrodlo": "sg"},
          "parma": {"xi": {"c"}, "confirmed": True, "bench": set(), "zrodlo": "sg"}}
    n = SG.dolacz_do_rotowire(roto, sg)
    assert n == 1 and roto["como"]["xi"] == {"a"} and roto["parma"]["confirmed"]
    # SG ogłoszony nadpisuje Rotowire przewidywany
    SG.dolacz_do_rotowire(roto, {"como": {"xi": {"z"}, "confirmed": True,
                                          "bench": set(), "zrodlo": "sg"}})
    assert roto["como"]["xi"] == {"z"}
