# -*- coding: utf-8 -*-
"""Archiwum Opta (26.10) — tylko migawka do pomiaru, nic do wyboru typów."""
from footstats.jobs import archiwum_opta as A


def test_sciezki_obejmuja_rankingi_i_siedem_rozgrywek():
    s = A.sciezki()
    assert s["pr-reference"] == "opta-power-rankings/pr-reference.json"
    assert s["league-meta"] == "opta-power-rankings/league-meta.json"
    assert len(A.ROZGRYWKI) == 7 and len(s) == 2 + 7 * 2
    assert s["premier_league/team-stats"].endswith("6pdwluctev9iebv00r4qqukno/team-stats.json")


def test_blad_jednego_pliku_nie_przerywa_reszty():
    def pobierz(sciezka):
        if "player-stats" in sciezka:
            raise TimeoutError("wolno")
        return {"ok": sciezka}
    pliki, bledy = A.zbierz(pobierz, przerwa_s=0)
    assert len(pliki) == 2 + 7 and len(bledy) == 7
    assert all(k.endswith("player-stats") for k in bledy)


def test_klucz_dnia_osobny_na_kazdy_dzien():
    assert A.klucz_dnia(1793000000) == "opta_arch_20261026"


def test_nic_z_archiwum_nie_wchodzi_do_cyklu():
    import inspect
    from footstats.jobs import build_wc_fast as B, radar as R
    for mod in (B, R):
        assert "archiwum_opta" not in inspect.getsource(mod)
