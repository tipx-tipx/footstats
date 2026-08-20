"""Zawodnicy odkrywani WPROST Z OFERTY bukmachera.

Zgłoszenie usera 2026-08-03: „w wielu meczach nie ma tabel pokryć ani kursów".
Wzbogacanie oferty działało tylko dla zawodników znanych z feedu propsów
statshuba, a ten na kwalifikacjach pucharów jest pusty. Zmierzone: Sparta
Praga – Lyon, 66 kwotowanych zawodników i ZERO w siatce pokryć.
"""
from footstats.jobs import build_wc_fast as B


class _Trend:
    def __init__(self, counts, minutes):
        self.counts = counts
        self.minutes = minutes


def _forma(tr, mk):
    return {"ostatnie": [int(c) for c in tr.counts], "srednia90": 1.0}


def _sb(players):
    return {"players": players, "player_names": {k: k for k in players}}


def _stub_debiutanci(znalezieni):
    def f(sb_odds, znane, team_ids, licznik, **kw):
        licznik[0] += 1
        return list(znalezieni)
    return f


def test_odkryty_zawodnik_trafia_do_pokryc_i_kursow():
    players_out, odds_grid = {}, {}
    sb_cache = {5: _sb({"nartey noah": {"yellow_card": {0.5: {"over": 3.3}}}})}
    n_gr, n_ku = B.odkryj_zawodnikow_z_oferty(
        [(5, (1, 2), 100, {1: "Sparta", 2: "Lyon"})],
        sb_cache, players_out, odds_grid, _forma,
        debiutanci=_stub_debiutanci([{
            "klucz_sb": "nartey noah", "nazwa": "Noah Nartey",
            "profil": {"id": 77, "team_id": 1, "position": "M"},
        }]),
        fetch_performance=lambda pid: [{"x": 1}],
        trendy_z_performance=lambda *a, **k: {
            "yellow_card": _Trend([0, 1, 0], [90, 90, 90])},
    )
    assert (n_gr, n_ku) == (1, 1)
    assert players_out[77]["nazwa"] == "Noah Nartey"
    assert players_out[77]["druzyna"] == "Sparta"
    assert odds_grid[5][77]["yellow_card"] == {"0.5": 3.3}


def test_bez_historii_nie_wchodzi_na_liste():
    """Sama cena to nie pokrycie — bez naszej historii wiersz nie ma treści."""
    players_out, odds_grid = {}, {}
    sb_cache = {5: _sb({"x": {"shots": {1.5: {"over": 2.0}}}})}
    n_gr, _ = B.odkryj_zawodnikow_z_oferty(
        [(5, (1, 2), 100, {1: "A", 2: "B"})],
        sb_cache, players_out, odds_grid, _forma,
        debiutanci=_stub_debiutanci([{
            "klucz_sb": "x", "nazwa": "X",
            "profil": {"id": 9, "team_id": 1, "position": "M"},
        }]),
        fetch_performance=lambda pid: [{"x": 1}],
        trendy_z_performance=lambda *a, **k: {},   # historia pusta
    )
    assert n_gr == 0 and players_out == {} and odds_grid == {}


def test_budzet_globalny_zatrzymuje_odkrywanie():
    """Jeden bogaty mecz nie może zjeść cyklu: 66 kwotowanych zawodników to
    ~200 zapytań, a cały cykl ma limit czasu."""
    players_out, odds_grid = {}, {}
    kand = [{"klucz_sb": f"g{i}", "nazwa": f"G{i}",
             "profil": {"id": 100 + i, "team_id": 1, "position": "M"}}
            for i in range(10)]
    sb_cache = {5: _sb({f"g{i}": {"shots": {1.5: {"over": 2.0}}}
                        for i in range(10)})}
    n_gr, _ = B.odkryj_zawodnikow_z_oferty(
        [(5, (1, 2), 100, {1: "A", 2: "B"})],
        sb_cache, players_out, odds_grid, _forma,
        budzet=3,
        debiutanci=_stub_debiutanci(kand),
        fetch_performance=lambda pid: [{"x": 1}],
        trendy_z_performance=lambda *a, **k: {"shots": _Trend([1, 2], [90, 90])},
    )
    assert n_gr == 3


def test_mecze_obslugiwane_od_najblizszego_kickoffu():
    """Budżet ma iść na mecze, na które ktoś dziś stawia."""
    kolejnosc = []

    def _deb(sb_odds, znane, team_ids, licznik, **kw):
        kolejnosc.append(team_ids)
        return []

    B.odkryj_zawodnikow_z_oferty(
        [(1, (1, 2), 9_000, {}), (2, (3, 4), 100, {}), (3, (5, 6), 5_000, {})],
        {1: _sb({"a": {}}), 2: _sb({"b": {}}), 3: _sb({"c": {}})},
        {}, {}, _forma, debiutanci=_deb, rundy=1,
    )
    assert kolejnosc == [(3, 4), (5, 6), (1, 2)]


def test_pusta_tabela_ma_pierwszenstwo_przed_wczesniejszym_kickoffem():
    """Sama kolejność kickoffu oddawała cały budżet meczom dzisiejszym, które
    tabelę mają z feedu propsów i tak — a pusty mecz jutro stał pusty
    (zmierzone 03.08: 50 odkryć i Sparta Praga – Lyon dalej bez wiersza)."""
    kolejnosc = []

    def _deb(sb_odds, znane, team_ids, licznik, **kw):
        kolejnosc.append(team_ids)
        return []

    odds_grid = {1: {99: {"shots": {}}}}      # mecz 1 JUŻ ma pokrycia
    B.odkryj_zawodnikow_z_oferty(
        [(1, (1, 2), 100, {}), (2, (3, 4), 9_000, {})],
        {1: _sb({"a": {}}), 2: _sb({"b": {}})},
        {}, odds_grid, _forma, debiutanci=_deb, rundy=1,
    )
    assert kolejnosc == [(3, 4), (1, 2)]


def test_rundami_zeby_kazdy_mecz_dostal_wiersze():
    """SZEROKOŚĆ przed głębią: zgłoszenie brzmiało „w WIELU meczach nie ma
    tabel", więc sześć wierszy w każdym meczu bije komplet w trzech. Pierwsza
    wersja szła mecz po meczu do wyczerpania budżetu — 51 odkryć i Sparta
    Praga – Lyon dalej pusta, bo budżet skończył się przed nią."""
    kolejnosc = []

    def _deb(sb_odds, znane, team_ids, licznik, **kw):
        kolejnosc.append(team_ids[0])
        return []

    B.odkryj_zawodnikow_z_oferty(
        [(1, (1, 2), 100, {}), (2, (3, 4), 200, {})],
        {1: _sb({"a": {}}), 2: _sb({"b": {}})},
        {}, {}, _forma, debiutanci=_deb, rundy=3,
    )
    assert kolejnosc == [1, 3, 1, 3, 1, 3]


def test_ten_sam_zawodnik_nie_liczy_sie_dwa_razy():
    """Bezpiecznik rund: w kolejnej rundzie odkryty gracz wraca jako „znany",
    ale podwójne liczenie zjadałoby budżet po cichu."""
    players_out, odds_grid = {}, {}
    sb_cache = {5: _sb({"x": {"shots": {1.5: {"over": 2.0}}}})}
    n_gr, _ = B.odkryj_zawodnikow_z_oferty(
        [(5, (1, 2), 100, {1: "A", 2: "B"})],
        sb_cache, players_out, odds_grid, _forma, rundy=3,
        debiutanci=_stub_debiutanci([{
            "klucz_sb": "x", "nazwa": "X",
            "profil": {"id": 9, "team_id": 1, "position": "M"},
        }]),
        fetch_performance=lambda pid: [{"x": 1}],
        trendy_z_performance=lambda *a, **k: {"shots": _Trend([1, 2], [90, 90])},
    )
    assert n_gr == 1


def test_mecz_bez_oferty_zawodniczej_pomijany():
    wywolania = []
    B.odkryj_zawodnikow_z_oferty(
        [(1, (1, 2), 100, {})], {1: {"players": {}}}, {}, {}, _forma,
        debiutanci=lambda *a, **k: wywolania.append(1) or [],
    )
    assert wywolania == []


# --- BUDŻETY: czas, nie sztywna liczba (2026-08-20) ---------------------------

def test_budzet_czasu_przerywa_odkrywanie():
    """⚑ Dry-run 20.08 dnia pucharowego: „220 zawodników, 677 zapytań, BUDŻET
    WYCZERPANY" — oba sufity dobiły do końca, więc nie dało się powiedzieć,
    ilu zawodników jeszcze czekało w ofercie.

    Sufity zostają jako bezpiecznik, ale o przerwaniu decyduje BUDŻET CZASU:
    liczba dobra dla spokojnego wtorku obcina czwartek pucharowy, a cyklu nie
    wolno wywalić w żadnym z nich. Ten test pilnuje, żeby budżet czasu nie
    wrócił do bycia stałą liczbą.
    """
    players_out, odds_grid = {}, {}
    mecze = [(m, (1, 2), 100 + m, {1: "A", 2: "B"}) for m in range(40)]
    sb_cache = {
        m: _sb({f"gracz {m}": {"shots": {0.5: {"over": 2.0}}}})
        for m in range(40)
    }

    def _wolny_debiutant(sb_odds, znane, team_ids, licznik, **kw):
        licznik[0] += 1
        return []

    n_gr, _ = B.odkryj_zawodnikow_z_oferty(
        mecze, sb_cache, players_out, odds_grid, _forma,
        budzet_s=0.0,                       # budżet wyczerpany od pierwszego meczu
        debiutanci=_wolny_debiutant,
    )
    assert n_gr == 0, "budżet czasu nie przerwał odkrywania"


def test_sufity_maja_zapas_na_dzien_pucharowy():
    """Zmierzone 20.08: 62 mecze w oknie 36 h, 220 odkrytych zawodników przy
    suficie 220 i 677 zapytań przy suficie 700 — OBA na styk.

    Podniesienie samego `DOCIAG_MAX` (pierwsza ściana lejka) nic by nie dało,
    bo kandydaci stanęliby tutaj. Sufity mają mieć zapas nad zmierzonym dnem.
    """
    assert B.MAX_ODKRYC_CYKL >= 400, (
        "sufit odkryć bez zapasu — dzień pucharowy znów obetnie lejek"
    )
    assert B.MAX_WYSZUKAN_ODKRYC >= 1200
    assert B.BUDZET_ODKRYWANIA_S > 0, (
        "budżet czasu to jedyne, co chroni cykl przed przekroczeniem limitu"
    )


def test_odkrywanie_jest_przed_radarem():
    """⚑⚑⚑ KOLEJNOŚĆ ETAPÓW TO NIE KOSMETYKA (2026-08-20).

    Do 20.08 `odkryj_zawodnikow_z_oferty` stało ~390 linii PO `radar.zbuduj`.
    Zmierzone na dry-runie: 251 zawodników odkrytych kosztem 247 sekund i 759
    zapytań, a jedynym użyciem `odds_grid` po tej linii był dump do
    `odds_superbet.json` (tabela pokryć). Czyli ani jeden odkryty zawodnik
    nie mógł dostać drabinki — karty powstawały wcześniej.

    `odds_grid` nie przeżywa cyklu (powstaje pusty), więc nie było nawet
    pociechy „zadziała w następnym przebiegu".

    Test jest STRUKTURALNY, bo kolejność w funkcji na 9000 linii jest
    niewidoczna dla testu jednostkowego, a jej odwrócenie nic nie wywala —
    po prostu po cichu zabiera drabinkom cały strumień kandydatów.
    """
    from pathlib import Path
    zrodlo = (Path(__file__).resolve().parent.parent
              / "footstats" / "jobs" / "build_wc_fast.py").read_text(encoding="utf-8")
    i_odkrycie = zrodlo.index("odkryj_zawodnikow_z_oferty(\n            _do_odkrycia")
    i_radar = zrodlo.index("radar_wpisy = radar.zbuduj(")
    assert i_odkrycie < i_radar, (
        "odkrywanie zawodników wróciło ZA radar — odkryci zawodnicy nie "
        "trafią do drabinek w tym cyklu, a odds_grid nie przeżywa do "
        "następnego (patrz nota w tym teście)"
    )
