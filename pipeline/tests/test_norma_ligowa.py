"""Trend z własnego banku wnosi próbki do normy ligowej.

POWÓD (2026-08-03). Norma ligi, koncesje rywala i własne próbki były zbierane
pętlą `zip(counts, timestamps, game_opponent_ids)`. Trend zbudowany z NASZEGO
banku (kartki, strzały, celne, faule — feed ich dla klubów nie wystawia) nie zna
id rywali, więc ta lista jest pusta, a `zip` ucina po najkrótszej: takie trendy
wnosiły do normy DOKŁADNIE ZERO próbek. Cicho, bez śladu w logu.

Skutek: `lg_feed` nigdy nie zbierał wymaganych 30 obserwacji, więc poziom bazowy
kartek spadał na średnią CAŁEGO banku, mieszając ligi. Zmierzone na drużynach
najbliższych meczów: Superliga duńska 1,05 kartki na drużynę-mecz, Brasileirão B
2,56, wspólny prior 1,93 — duński zespół startował z liczbą prawie dwukrotnie
zawyżoną, na rynku, na którym i tak zawyżamy.
"""

from footstats.sources.statshub import TeamTrend


def _zbierz(trendy):
    """Ta sama pętla, co w build_wc_fast — bez id rywala liczymy resztę."""
    liga, wlasne, koncesje = {}, {}, {}
    for tt in trendy:
        for i_g, (v_g, ts_g) in enumerate(zip(tt.counts, tt.timestamps)):
            opp_g = (tt.game_opponent_ids[i_g]
                     if i_g < len(tt.game_opponent_ids) else 0)
            liga.setdefault((tt.league_id, tt.market_code), []).append(v_g)
            wlasne.setdefault((tt.team_id, tt.market_code), []).append(v_g)
            if opp_g:
                koncesje.setdefault((opp_g, tt.market_code), []).append(v_g)
    return liga, wlasne, koncesje


def _trend_z_banku(**kw):
    """Dokładnie tak buduje go build_wc_fast: bez id rywali i bez miejsca gry."""
    return TeamTrend(
        team_id=1, team_name="A", opponent_name="B", opponent_id=2,
        event_id=10, is_home=True, league_id=39,
        market_code="team_cards", line=0.0,
        counts=[2.0, 1.0, 3.0], timestamps=[300, 200, 100], **kw,
    )


def test_trend_z_banku_zasila_norme_ligowa():
    liga, wlasne, koncesje = _zbierz([_trend_z_banku()])
    assert liga[(39, "team_cards")] == [2.0, 1.0, 3.0]
    assert wlasne[(1, "team_cards")] == [2.0, 1.0, 3.0]
    # bez id rywala koncesji nie ma czego przypisać — i tak ma zostać
    assert koncesje == {}


def test_trend_z_feedu_dalej_zasila_koncesje():
    tt = _trend_z_banku(game_opponent_ids=[7, 7, 8])
    liga, wlasne, koncesje = _zbierz([tt])
    assert len(liga[(39, "team_cards")]) == 3
    assert koncesje[(7, "team_cards")] == [2.0, 1.0]
    assert koncesje[(8, "team_cards")] == [3.0]


def test_niepelna_lista_rywali_nie_ucina_reszty():
    """Sedno błędu: krótsza lista skracała CAŁĄ historię, nie tylko koncesje."""
    tt = _trend_z_banku(game_opponent_ids=[7])
    liga, _wlasne, koncesje = _zbierz([tt])
    assert len(liga[(39, "team_cards")]) == 3      # wcześniej byłoby 1
    assert koncesje[(7, "team_cards")] == [2.0]
