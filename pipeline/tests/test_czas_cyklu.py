"""Czas cyklu, etap 0 (05.11): pomiar pętli zawodników w meczach z ofertą
zawodniczą i bez – tylko liczy, nie zmienia wyniku cyklu."""
import time

from footstats import diagnostyka
from footstats.jobs import build_wc_fast as B


def test_podetap_sumuje_i_nie_rusza_czasu_etapow():
    diagnostyka.reset()
    diagnostyka.podetap("x", 1.04)
    diagnostyka.podetap("x", 2.0)
    r = diagnostyka.rentgen()
    assert r["czas_podetapow"] == {"x": 3.0}
    assert "czas_etapow" not in r


def test_pomiar_bez_oferty_liczy_wyniki_tylko_w_meczach_bez_oferty():
    diagnostyka.reset()
    pbo = {"t": time.monotonic(), "fl": "bez_oferty"}
    czas = {"z_oferta": 2.0, "bez_oferty": 5.0, "inne": 0.0}
    ile = {"z_oferta": 3, "bez_oferty": 7, "inne": 1}
    w = B._podsumuj_pomiar_bez_oferty(
        pbo, czas, ile, {1}, {2, 1},
        value_bets=[{"mecz_id": 1}, {"mecz_id": 2}],
        poza_publikacja=[{"mecz_id": 2}],
        legi_pool=[],
        pomiary=[{"mecz_id": 1}],
        odds_grid={1: {}, 2: {}},
        real_split={(5, "shots_blocked"): {"info": {"mid": 2}}},
    )
    # mecz 1 ma ofertę (także gdy trafił do obu zbiorów) – liczy się tylko mecz 2
    assert w["mecze_z_oferta"] == 1 and w["mecze_bez_oferty"] == 1
    assert w["obroty_bez_oferty"] == 8                     # ostatni obrót domknięty
    assert (w["wynik_value_bets"], w["wynik_poza_publikacja"], w["wynik_pomiar"],
            w["wynik_siatka_kursow"], w["wynik_sugestie_365"]) == (1, 1, 0, 1, 1)
    assert w["wynik_legi_pool"] == 0
    assert pbo["t"] is None
