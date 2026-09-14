"""⚑ 2026-09-14: rynki zza pola, głową i spalone w celach treningu zawodniczego.

Do tego dnia `CELE_ZAW` miało pięć rynków, a komentarz mówił „reszta ma zero
serii". Serie były — z 365Scores i z map strzałów statshub — ale bank szedł do
magazynu PRZED ich utworzeniem, więc trening nigdy ich nie widział, a typy
zza pola jechały starym rachunkiem bez pokrycia (565 wycen na cykl).
"""

from footstats.model import uczony as U


NOWE = ("shots_outside_box", "sot_outside_box", "headed_shots",
        "headed_sot", "offsides")


def _seria(kod: str, n: int = 8) -> dict:
    return {
        "player_id": 1, "market_code": kod, "position": "M",
        "counts": [1.0, 2.0, 0.0, 1.0, 2.0, 1.0, 0.0, 3.0][:n],
        "minutes": [90.0] * n,
        "timestamps": [1_700_000_000 + i * 7 * 86400 for i in range(n)],
        "started": [True] * n,
        "game_positions": ["RW"] * n,
        "league_average": None, "opponent_average": None, "is_home": True,
    }


def test_nowe_rynki_sa_celami_treningu():
    for kod in NOWE:
        assert kod in U.CELE_ZAW, kod
    # stare zostają — łącznie z odbiorami, które są wycofane z PRODUKTU,
    # ale w treningu nie szkodzą
    for kod in ("shots", "sot", "fouls_committed", "fouls_won", "tackles"):
        assert kod in U.CELE_ZAW


def test_wiersze_treningowe_powstaja_dla_zza_pola_i_glowki():
    lib = {f"{i}:{kod}": {**_seria(kod), "player_id": i}
           for i, kod in enumerate(NOWE)}
    wiersze = U.wiersze_zawodnicze(lib)
    for kod in NOWE:
        assert wiersze.get(kod), f"brak wierszy dla {kod}"
        # 8 meczów, MIN_HISTORII = 4 → co najmniej jeden wiersz z celem
        assert all("y" in w and "minuty" in w for w in wiersze[kod])


def test_rynek_spoza_celow_nadal_odpada():
    lib = {"7:shots_blocked": {**_seria("shots_blocked"), "player_id": 7}}
    assert U.wiersze_zawodnicze(lib) == {}
