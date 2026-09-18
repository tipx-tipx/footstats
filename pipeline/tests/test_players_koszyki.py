"""Zawodnicy w kawałkach dla strony (2026-09-18, transfer Supabase).

Pełny `players` (~44 MB) szedł na stronę w całości przy każdym odświeżeniu.
Pipeline wysyła obok niego `players_typy` (strona główna) i koszyki po nazwie
drużyny (strona meczu). Funkcja koszyka MUSI dawać te same numery co
`koszykDruzyny` w web/src/lib/data.ts — wartości niżej policzone tamtym kodem.
"""
from footstats.jobs import push_supabase as P


def test_koszyk_zgodny_z_frontem():
    # policzone przez `koszykDruzyny` (FNV-1a po punktach kodowych, % 96) w TS
    assert P.KOSZYKI_PLAYERS == 96
    assert P.koszyk_druzyny("Widzew Łódź") == 27
    assert P.koszyk_druzyny("Wieczysta Kraków") == 29
    assert P.koszyk_druzyny("NEC Nijmegen") == 56
    assert P.koszyk_druzyny("FC Bayern München") == 60
    assert P.koszyk_druzyny("Atlético Madrid") == 15
    assert P.koszyk_druzyny("") == 37


def _z(pid, druzyna, rynki):
    return {"id": pid, "nazwa": f"Z{pid}", "druzyna": druzyna, "pozycja": "M",
            "minuty_lacznie": 900, "xi": False,
            "forma": {mk: {"ostatnie": [1], "minuty": [90], "srednia90": 1.0}
                      for mk in rynki}}


def test_klucze_pochodne_to_dokladnie_to_co_strona_wycinala():
    players = [_z(1, "Widzew Łódź", ["shots", "fouls_won"]),
               _z(2, "Wieczysta Kraków", ["shots"]),
               _z(3, "Widzew Łódź", ["sot"])]
    vb = [{"podmiot_id": 1, "rynek_kod": "fouls_won"},
          {"podmiot_id": 99, "rynek_kod": "shots"}]         # drużyna/nieznany
    out = P.klucze_pochodne_players(players, vb)
    # strona główna: tylko zawodnicy z typami i tylko rynki typów (zawodnicyLite)
    assert out["players_typy"] == [{**players[0], "forma": {
        "fouls_won": players[0]["forma"]["fouls_won"]}}]
    # koszyki: każdy zawodnik w DOKŁADNIE jednym, wszystkie klucze zawsze są
    koszyki = {k: v for k, v in out.items() if k.startswith("players_d")}
    assert len(koszyki) == P.KOSZYKI_PLAYERS
    assert sorted(z["id"] for v in koszyki.values() for z in v) == [1, 2, 3]
    widzew = koszyki[f"players_d{P.koszyk_druzyny('Widzew Łódź'):02d}"]
    assert {z["id"] for z in widzew if z["druzyna"] == "Widzew Łódź"} == {1, 3}
