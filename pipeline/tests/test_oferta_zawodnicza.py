"""Zakładka meczu ma pokazywać KURSY + wszystkie nasze statystyki indywidualne
możliwe do zagrania (zgłoszenie usera 2026-08-03).

Do tej pory tabela znała wyłącznie statystyki wymienione przez feed propsów
statshuba, a on jest lustrem ofert bukmacherów UK: na Odense – Sønderjyske dał
same strzały, a w drugą stronę Superbet kwotował celne strzały 547 razy w skanie
przy naszej formie na celne dla 15 zawodników z 1035.

`dopelnij_oferte_zawodnicza` odwraca kolejność: punktem wyjścia jest oferta
bukmachera na ten mecz. Testy niżej pilnują trzech rzeczy, które łatwo zepsuć:
dociągania historii TYLKO gdy jej brakuje, kompletu kursów w siatce oraz tego,
że mecz bez oferty zawodniczej nie kosztuje ani jednego zapytania.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from footstats.jobs import build_wc_fast
from footstats.sources import superbet


@dataclass
class FakeTrend:
    player_name: str
    team_id: int = 7
    team_name: str = "Boca Juniors"
    counts: list = field(default_factory=lambda: [2.0, 1.0, 3.0, 0.0, 2.0])


def _oferta(*rynki: str) -> dict:
    """Rekord propsów jak z superbet.fetch_stat_odds: rynek -> linia -> strony."""
    return {
        mk: {0.5: {"over": 1.75, "under": 2.05}, 1.5: {"over": 3.10}}
        for mk in rynki
    }


def _swiat(rynki_oferty, forma_startowa):
    gracze = {1: {100: FakeTrend("Milton Gimenez")}}
    sb_cache = {1: {"players": {
        superbet.norm_name("Gimenez, Milton"): _oferta(*rynki_oferty),
    }}}
    players_out = {100: {"id": 100, "forma": dict(forma_startowa)}}
    return gracze, sb_cache, players_out, {}


def test_dokłada_rynek_z_oferty_i_wszystkie_kursy():
    """Bukmacher kwotuje celne i strzały, my mamy historię tylko strzałów:
    celne mają dojść z performance, a kursy — dla obu rynków."""
    gracze, sb_cache, players_out, grid = _swiat(
        ("shots", "sot"), {"shots": {"ostatnie": [1, 2, 3]}}
    )
    zapytania = []

    def fake_perf(pid):
        zapytania.append(pid)
        return [{"rekord": "nieważny, liczy się trendy_z_performance"}]

    def fake_trendy(pid, nazwa, team_id, rows, sm_cache=None, budzet=None):
        return {"sot": FakeTrend(nazwa), "offsides": FakeTrend(nazwa)}

    n_rynkow, n_kursow = build_wc_fast.dopelnij_oferte_zawodnicza(
        gracze, sb_cache, players_out, grid,
        forma_z_trendu=lambda tr, mk: {"ostatnie": [int(c) for c in tr.counts]},
        fetch_performance=fake_perf, trendy_z_performance=fake_trendy,
    )

    assert zapytania == [100]                      # jedno zapytanie na zawodnika
    assert n_rynkow == 1 and n_kursow == 2
    forma = players_out[100]["forma"]
    assert set(forma) == {"shots", "sot"}          # spalonych nikt nie kwotuje
    assert forma["shots"] == {"ostatnie": [1, 2, 3]}   # istniejąca historia nietknięta
    # komplet kwotowanych linii "powyżej" w siatce, dla obu rynków
    assert grid[1][100]["sot"] == {"0.5": 1.75, "1.5": 3.1}
    assert grid[1][100]["shots"] == {"0.5": 1.75, "1.5": 3.1}


def test_bez_oferty_zawodniczej_zero_zapytan():
    """Mecz, w którym bukmacher nie kwotuje zawodników (3.08: 25 z 26
    sprawdzonych), ma nic nie kosztować — strona po prostu napisze, że nie ma."""
    gracze = {1: {100: FakeTrend("Milton Gimenez")}}
    sb_cache = {1: {"players": {}, "teams": {"home": {"team_goals": {}}}}}
    players_out = {100: {"forma": {"shots": {}}}}
    zapytania = []

    n_rynkow, n_kursow = build_wc_fast.dopelnij_oferte_zawodnicza(
        gracze, sb_cache, players_out, {},
        forma_z_trendu=lambda tr, mk: {},
        fetch_performance=lambda pid: zapytania.append(pid) or [],
        trendy_z_performance=lambda *a, **k: {},
    )

    assert (n_rynkow, n_kursow, zapytania) == (0, 0, [])


def test_komplet_historii_nie_wola_performance():
    """Mamy już historię wszystkich kwotowanych rynków — dociągać nie ma czego,
    ale kursy i tak mają trafić do siatki (dawniej wpadały tam wyłącznie te,
    przy których silnik doszedł do końca scoringu)."""
    gracze, sb_cache, players_out, grid = _swiat(
        ("shots",), {"shots": {"ostatnie": [1]}}
    )
    zapytania = []

    n_rynkow, n_kursow = build_wc_fast.dopelnij_oferte_zawodnicza(
        gracze, sb_cache, players_out, grid,
        forma_z_trendu=lambda tr, mk: {},
        fetch_performance=lambda pid: zapytania.append(pid) or [],
        trendy_z_performance=lambda *a, **k: {},
    )

    assert (n_rynkow, n_kursow, zapytania) == (0, 1, [])
    assert grid[1][100]["shots"] == {"0.5": 1.75, "1.5": 3.1}


def test_budzet_zapytan_zatrzymuje_dociaganie():
    """Budżet wyczerpany = nie dzwonimy po historię (cykl chodzi co ~30 min
    i nie może utknąć na zapytaniach), ale kursy rynków, które już znamy,
    nadal wchodzą do siatki."""
    gracze, sb_cache, players_out, grid = _swiat(
        ("shots", "sot"), {"shots": {}}
    )
    zapytania = []

    n_rynkow, n_kursow = build_wc_fast.dopelnij_oferte_zawodnicza(
        gracze, sb_cache, players_out, grid,
        forma_z_trendu=lambda tr, mk: {},
        budzet=0,
        fetch_performance=lambda pid: zapytania.append(pid) or [],
        trendy_z_performance=lambda *a, **k: {},
    )

    assert (n_rynkow, zapytania) == (0, [])
    assert n_kursow == 1 and "sot" not in grid[1][100]


def test_shotmapy_tylko_dla_rynkow_ktore_ich_wymagaja():
    """Shotmapy kosztują ~10 zapytań na drużynę. Gdy brakuje nam tylko celnych
    (rynek z performance), nie wolno ich w ogóle ruszać; przy „głową" — trzeba."""
    widziane = []

    def fake_trendy(pid, nazwa, team_id, rows, sm_cache=None, budzet=None):
        widziane.append(sm_cache)
        return {}

    for rynki, oczekiwany_cache in ((("sot",), None), (("headed_shots",), dict)):
        gracze, sb_cache, players_out, grid = _swiat(rynki, {"shots": {}})
        build_wc_fast.dopelnij_oferte_zawodnicza(
            gracze, sb_cache, players_out, grid,
            forma_z_trendu=lambda tr, mk: {},
            fetch_performance=lambda pid: [{"x": 1}],
            trendy_z_performance=fake_trendy,
        )
    assert widziane[0] is None                    # same celne — bez shotmap
    assert isinstance(widziane[1], dict)          # „głową" — cache podany


def test_budzet_idzie_najpierw_w_mecze_zaczynajace_sie_wczesniej():
    """Gdy budżet nie starcza dla wszystkich, dostaje go mecz, na który ktoś
    dziś stawia — nie ten, który akurat wyszedł pierwszy z pętli trendów."""
    oferta = _oferta("sot")
    gracze = {
        90: {1: FakeTrend("Pierwszy Zpetli")},     # gra za trzy dni
        91: {2: FakeTrend("Drugi Zpetli")},        # gra za godzinę
    }
    sb_cache = {
        90: {"players": {superbet.norm_name("Pierwszy Zpetli"): oferta}},
        91: {"players": {superbet.norm_name("Drugi Zpetli"): oferta}},
    }
    players_out = {1: {"forma": {"shots": {}}}, 2: {"forma": {"shots": {}}}}
    obsluzeni = []

    build_wc_fast.dopelnij_oferte_zawodnicza(
        gracze, sb_cache, players_out, {},
        forma_z_trendu=lambda tr, mk: {},
        budzet=1,
        kolejnosc={90: 3_000_000, 91: 1_000_000},
        fetch_performance=lambda pid: obsluzeni.append(pid) or [],
        trendy_z_performance=lambda *a, **k: {},
    )

    assert obsluzeni == [2]


def test_zawodnik_bez_pary_u_bukmachera_nie_kosztuje_zapytania():
    """Nazwisko, którego nie ma w ofercie (albo dwuznaczne), nie ma jak dostać
    kursów — nie ma też sensu dociągać dla niego historii."""
    gracze = {1: {100: FakeTrend("Ktoś Spoza Oferty")}}
    sb_cache = {1: {"players": _oferta("shots")}}   # klucze rynków, nie nazwisk
    players_out = {100: {"forma": {"shots": {}}}}
    zapytania = []

    n_rynkow, n_kursow = build_wc_fast.dopelnij_oferte_zawodnicza(
        gracze, sb_cache, players_out, {},
        forma_z_trendu=lambda tr, mk: {},
        fetch_performance=lambda pid: zapytania.append(pid) or [],
        trendy_z_performance=lambda *a, **k: {},
    )

    assert (n_rynkow, n_kursow, zapytania) == (0, 0, [])


# ------------------------------------------- kolejność dociągu kursów (21.08)

def test_liga_bez_oferty_idzie_na_koniec_ale_nie_znika():
    """⚑ 2026-08-21. Pętla dociągu ma budżet 150 s i sortowała mecze po
    GODZINIE KICKOFFU, więc Championship dostawał ten sam priorytet co
    Ekstraklasa. Zmierzone: 11 lig z udokumentowanym ZEREM oferty (pole
    `propsy_superbet` == 0, czyli pytaliśmy) — 61 meczów, ~30 w oknie 36 h,
    czyli ~40% budżetu na mecze, w których nie powstanie żadna drabinka.
    """
    from footstats.jobs.build_wc_fast import szansa_oferty_ligi as sz

    mapa = {"1": [0, 12], "2": [15, 15]}
    assert sz(mapa, 2) > sz(mapa, 999) > sz(mapa, 1), (
        "kolejność ma być: potwierdzona oferta > nieznana > udokumentowane zero"
    )
    # ⚑ liga z zerem NIE jest zablokowana — dostaje dodatnią wagę, więc gdy
    # budżet zostanie, i tak o nią zapytamy (inaczej byłaby to pętla
    # samopodtrzymująca się: nie pytamy -> nie wiemy -> nie pytamy)
    assert sz(mapa, 1) > 0.0


def test_nieznana_liga_wchodzi_do_probkowania_sama():
    """Nowa liga (puchary, nowy sezon) nie wymaga żadnej listy ręcznej."""
    from footstats.jobs.build_wc_fast import szansa_oferty_ligi as sz

    assert sz({}, 7) == 0.5
    assert sz({"7": []}, 7) == 0.5
    assert sz(None, 7) == 0.5
    assert sz({"7": [0, 12]}, None) == 0.5      # brak utid = nieznana


def test_scalanie_oferty_lig_gasi_stara_historie():
    """Zanik + sufit: stara historia tej ligi traci wagę przy każdym pomiarze,
    a pamięć nie rośnie w nieskończoność."""
    from footstats.jobs.build_wc_fast import scal_oferte_lig as sc

    assert sc({}, {"1": [3, 4]}) == {"1": [3.0, 4.0]}
    # 40/40 gaśnie do 32/32, plus 5/20 = 37/52 -> przycięte do sufitu 50
    out = sc({"1": [40, 40]}, {"1": [5, 20]})
    assert out["1"][1] == 50.0
    assert abs(out["1"][0] / out["1"][1] - 37.0 / 52.0) < 0.01
    # liga, o którą NIE pytaliśmy, zachowuje stan — brak pytania nie kasuje wiedzy
    assert sc({"9": [4, 8]}, {"1": [1, 1]})["9"] == [4, 8]


def test_liga_ktora_zaczela_kwotowac_odzyskuje_priorytet():
    """Scenariusz, dla którego sufit pamięci w ogóle istnieje: liga miała zero
    przez tygodnie, po czym zaczęła kwotować. Ma wrócić do gry, a nie czekać,
    aż przegłosuje ją stara historia."""
    from footstats.jobs.build_wc_fast import scal_oferte_lig as sc
    from footstats.jobs.build_wc_fast import szansa_oferty_ligi as sz

    mapa = {"1": [0, 50]}
    assert sz(mapa, 1) < 0.05
    for _ in range(6):                      # sześć cykli po pięć meczów
        mapa = sc(mapa, {"1": [5, 5]})
    assert sz(mapa, 1) > 0.5, "po serii trafień liga ma wrócić przed nieznane"
