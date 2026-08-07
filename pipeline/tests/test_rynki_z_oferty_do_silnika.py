"""Rynki dociągnięte z oferty mają móc trafić do SILNIKA TYPÓW (2026-08-07).

Zmierzone tego dnia: z 46 typów zawodniczych z trzech dni 41 to strzały,
a celnych, „zza pola", odbiorów i spalonych nie było ANI JEDNEGO — mimo że
kursy i historia były w ręku. Powód: `dopelnij_oferte_zawodnicza` zapisywała
dociągniętą historię wyłącznie do formy (tabela pokryć) i do siatki kursów,
a nigdy do listy trendów, z której silnik robi typy.

Mechanizm poniżej jest przygotowany i przetestowany, ale w cyklu jeszcze
NIEAKTYWNY: żeby zadziałał, oferta bukmachera musi być pobrana przed pętlą
scoringu, a dziś powstaje w jej trakcie. To osobna zmiana kolejności cyklu.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from footstats.jobs import build_wc_fast
from footstats.sources import statshub, superbet


@dataclass
class FakeTrend:
    """Trend bazowy z feedu — niesie kontekst nadchodzącego meczu."""

    player_name: str
    player_id: int = 100
    position: str = "F"
    team_id: int = 7
    team_name: str = "Boca Juniors"
    opponent_id: int = 9
    opponent_name: str = "River Plate"
    is_home: bool = True
    event_id: int = 555
    in_predicted_lineup: bool = True
    counts: list = field(default_factory=lambda: [2.0, 1.0, 3.0, 0.0, 2.0])


def _trend_statshub(mk: str) -> statshub.StatshubTrend:
    """Trend z `performance`: ma historię, NIE zna nadchodzącego meczu."""
    return statshub.StatshubTrend(
        player_id=100, player_name="Milton Gimenez", position=None,
        team_id=0, team_name="", opponent_id=0, opponent_name="",
        is_home=False, market_code=mk, line=0.0, in_predicted_lineup=False,
        league_average=None, opponent_average=None, opponent_rank=None,
        total_ranks=None, counts=[1.0, 2.0, 0.0, 1.0, 3.0],
        minutes=[90.0] * 5, timestamps=[1, 2, 3, 4, 5],
    )


def _swiat(rynki_oferty, forma_startowa):
    gracze = {1: {100: FakeTrend("Milton Gimenez")}}
    sb_cache = {1: {"players": {
        superbet.norm_name("Gimenez, Milton"): {
            mk: {0.5: {"over": 1.75}} for mk in rynki_oferty
        },
    }}}
    players_out = {100: {"id": 100, "forma": dict(forma_startowa)}}
    return gracze, sb_cache, players_out, {}


def _wywolaj(trends_out, swieze):
    gracze, sb_cache, players_out, grid = _swiat(
        ("shots", "sot"), {"shots": {"ostatnie": [1, 2, 3]}}
    )
    return build_wc_fast.dopelnij_oferte_zawodnicza(
        gracze, sb_cache, players_out, grid,
        forma_z_trendu=lambda tr, mk: {"ostatnie": list(tr.counts)},
        fetch_performance=lambda pid: [{"nieważne": 1}],
        trendy_z_performance=lambda *a, **k: swieze,
        trends_out=trends_out,
    )


def test_dociagniety_rynek_trafia_do_silnika_z_kontekstem_meczu():
    trends: list = []
    _wywolaj(trends, {"sot": _trend_statshub("sot")})

    assert len(trends) == 1
    t = trends[0]
    assert t.market_code == "sot"
    assert t.counts == [1.0, 2.0, 0.0, 1.0, 3.0]     # historia z performance
    # kontekst NADCHODZĄCEGO meczu — bez niego nie ma czynnika rywala
    assert t.event_id == 555
    assert (t.opponent_id, t.opponent_name) == (9, "River Plate")
    assert t.is_home is True
    assert t.team_name == "Boca Juniors"
    assert t.in_predicted_lineup is True
    assert t.line == 0.0            # linię dobiera silnik z liczby zdarzeń


def test_bez_trends_out_zachowanie_jak_dawniej():
    """Domyślnie nic się nie zmienia — tabela pokryć i siatka kursów jak były."""
    n_rynkow, n_kursow = _wywolaj(None, {"sot": _trend_statshub("sot")})
    assert n_rynkow == 1 and n_kursow == 2


def test_rynek_bez_historii_nie_trafia_do_silnika():
    trends: list = []
    pusty = _trend_statshub("sot")
    pusty.counts = []
    _wywolaj(trends, {"sot": pusty})
    assert trends == []


@dataclass
class UbogiTrend:
    """Trend bez pól kontekstu — kształt, który mógłby przyjść po zmianie
    w źródle. Przepisujemy tylko te pola, które faktycznie istnieją."""

    player_name: str
    counts: list = field(default_factory=lambda: [1.0, 2.0])


def test_trend_bez_pol_kontekstu_nie_wywala_cyklu():
    trends: list = []
    n_rynkow, _n = _wywolaj(trends, {"sot": UbogiTrend("Milton Gimenez")})
    assert n_rynkow == 1                  # forma dołożona jak zwykle
    assert len(trends) == 1
    assert not hasattr(trends[0], "event_id")   # nic nie dorobiliśmy na siłę


def test_obiekt_ktory_nie_jest_trendem_jest_pomijany():
    """Zamiast wywalić przebieg — pomijamy wpis. Cykl liczy setki typów
    i jeden dziwny rekord nie może położyć całości."""
    assert build_wc_fast._trend_z_kontekstem_meczu(
        object(), FakeTrend("X"), 1
    ) is None
    assert build_wc_fast._trend_z_kontekstem_meczu(
        None, FakeTrend("X"), 1
    ) is None
