"""Profil drużyny pamiętany między cyklami (2026-08-07).

Powód powstania: pytanie o historię drużyn przy każdym cyklu wydłużyło dry-run
z ~15 do ~23 minut przy twardym limicie 35. Profil trzymamy więc w bazie
i odświeżamy przyrostowo — cykl czyta gotowe liczby.
"""
import time

from footstats.model import profil_druzyn as P

TERAZ = 1_800_000_000
DZIEN = 86_400
MAPA = {"cornerKicks": "team_corners", "cards": "team_cards",
        "totalShotsOnGoal": "team_shots"}


def _mecz(dni_temu, moje, rywala, wynik=None, tid=1, gospodarz=1):
    ts = TERAZ - int(dni_temu * DZIEN)
    u_siebie = gospodarz == tid
    return {
        "event": {"timeStartTimestamp": str(ts),
                  "score": wynik or {"home": 1, "away": 0}},
        "statistics": moje,
        "opponentStatistics": rywala,
        "homeTeam": {"id": tid if u_siebie else 2},
        "awayTeam": {"id": 2 if u_siebie else tid},
    }


MOJE = {"cornerKicks": 6, "cards": 2, "totalShotsOnGoal": 14}
RYWALA = {"cornerKicks": 3, "cards": 1, "totalShotsOnGoal": 8}


# --- budowanie profilu ---

def test_liczy_obie_strony_osobno():
    rek = [_mecz(i, MOJE, RYWALA) for i in range(1, 9)]
    p = P.zbuduj(1, rek, TERAZ, MAPA)
    assert p["rynki"]["team_corners"]["notuje"] == 6.0
    assert p["rynki"]["team_corners"]["dopuszcza"] == 3.0
    assert p["rynki"]["team_corners"]["n_notuje"] == 8
    assert p["n"] == 8


def test_swiezsze_mecze_waza_wiecej():
    """Mecz sprzed 45 dni ma ważyć o połowę mniej niż wczorajszy — inaczej
    profil drużyny, która zmieniła trenera, kłamie przez pół sezonu."""
    rek = ([_mecz(1, {"cornerKicks": 10}, {"cornerKicks": 10}) for _ in range(5)]
           + [_mecz(200, {"cornerKicks": 0}, {"cornerKicks": 0}) for _ in range(5)])
    p = P.zbuduj(1, rek, TERAZ, MAPA)
    assert p["rynki"]["team_corners"]["notuje"] > 9.0     # stare prawie nie liczą


def test_gole_biora_wlasciwa_strone_wyniku():
    rek = [_mecz(i, MOJE, RYWALA, {"home": 3, "away": 1}, gospodarz=1)
           for i in range(1, 7)]
    p = P.zbuduj(1, rek, TERAZ, MAPA)
    assert p["rynki"]["team_goals"]["notuje"] == 3.0
    assert p["rynki"]["team_goals"]["dopuszcza"] == 1.0

    rek_wyjazd = [_mecz(i, MOJE, RYWALA, {"home": 3, "away": 1}, gospodarz=2)
                  for i in range(1, 7)]
    p2 = P.zbuduj(1, rek_wyjazd, TERAZ, MAPA)
    assert p2["rynki"]["team_goals"]["notuje"] == 1.0
    assert p2["rynki"]["team_goals"]["dopuszcza"] == 3.0


def test_chuda_historia_nie_daje_profilu():
    """Profil z dwóch meczów zrobiłby z przeciętnej obrony twierdzę."""
    assert P.zbuduj(1, [_mecz(i, MOJE, RYWALA) for i in range(1, 3)],
                    TERAZ, MAPA) == {}
    assert P.zbuduj(1, [], TERAZ, MAPA) == {}


def test_mecz_bez_daty_i_z_przyszlosci_odpada():
    rek = [_mecz(i, MOJE, RYWALA) for i in range(1, 7)]
    rek.append({"event": {"timeStartTimestamp": "0"}, "statistics": MOJE,
                "opponentStatistics": RYWALA, "homeTeam": {"id": 1},
                "awayTeam": {"id": 2}})
    rek.append(_mecz(-5, {"cornerKicks": 99}, {"cornerKicks": 99}))
    p = P.zbuduj(1, rek, TERAZ, MAPA)
    assert p["n"] == 6
    assert p["rynki"]["team_corners"]["notuje"] == 6.0


def test_brakujaca_statystyka_to_luka_nie_zero():
    rek = [_mecz(i, {"cornerKicks": 6}, {"cornerKicks": 3}) for i in range(1, 7)]
    p = P.zbuduj(1, rek, TERAZ, MAPA)
    assert "team_corners" in p["rynki"]
    assert "team_cards" not in p["rynki"]


# --- odczyt ---

def test_wartosc_zwraca_probe_i_milczy_przy_chudej():
    rek = [_mecz(i, MOJE, RYWALA) for i in range(1, 9)]
    p = P.zbuduj(1, rek, TERAZ, MAPA)
    assert P.wartosc(p, "team_corners") == (3.0, 8)
    assert P.wartosc(p, "team_corners", "notuje") == (6.0, 8)
    assert P.wartosc(p, "team_fouls") == (None, 0)
    assert P.wartosc(None, "team_corners") == (None, 0)


# --- odświeżanie ---

def test_brak_profilu_wymaga_odswiezenia():
    assert P.wymaga_odswiezenia(None, TERAZ) is True
    assert P.wymaga_odswiezenia({}, TERAZ) is True
    assert P.wymaga_odswiezenia({"ts": TERAZ, "rynki": {}}, TERAZ) is True


def test_swiezy_profil_nie_kosztuje_zapytania():
    p = {"ts": TERAZ - 3600, "rynki": {"team_corners": {"dopuszcza": 3.0}}}
    assert P.wymaga_odswiezenia(p, TERAZ) is False


def test_stary_profil_idzie_do_odswiezenia():
    p = {"ts": TERAZ - 30 * 3600, "rynki": {"team_corners": {"dopuszcza": 3.0}}}
    assert P.wymaga_odswiezenia(p, TERAZ) is True


# --- magazyn ---

def test_scalanie_nie_mutuje_wejscia():
    magazyn = {"druzyny": {"7": {"ts": 1, "rynki": {"x": {}}}}}
    kopia = {"druzyny": dict(magazyn["druzyny"])}
    nowy = P.scal(magazyn, 9, {"ts": 2, "rynki": {"y": {}}})
    assert set(nowy["druzyny"]) == {"7", "9"}
    assert magazyn["druzyny"] == kopia["druzyny"]     # oryginał nietknięty


def test_scalanie_bierze_wartosc_bezwzgledna_id():
    """Numer drużyny bywa w księdze ujemny (wyciek z pomiaru progów) —
    profil musi być pod jednym kluczem, inaczej klub ma dwa różne profile."""
    m = P.scal({}, 3205, {"ts": 1, "rynki": {"a": {}}})
    assert P.pobierz(m, -3205) == P.pobierz(m, 3205)


def test_przycinanie_wyrzuca_martwe_druzyny():
    magazyn = {"druzyny": {
        "1": {"ostatni_mecz": TERAZ - 10 * DZIEN, "rynki": {}},
        "2": {"ostatni_mecz": TERAZ - 200 * DZIEN, "rynki": {}},
        "3": {"rynki": {}},                     # bez daty = martwy
    }}
    out, zeszlo = P.przytnij(magazyn, TERAZ)
    assert set(out["druzyny"]) == {"1"}
    assert zeszlo == 2


def test_pobierz_odporne_na_smieci():
    assert P.pobierz(None, 1) is None
    assert P.pobierz({"druzyny": {}}, None) is None
    assert P.pobierz({"druzyny": {}}, "abc") is None


def test_profil_ma_stempel_czasu_i_ostatniego_meczu():
    rek = [_mecz(i, MOJE, RYWALA) for i in range(1, 9)]
    p = P.zbuduj(1, rek, TERAZ, MAPA)
    assert p["ts"] == TERAZ
    assert p["ostatni_mecz"] == TERAZ - DZIEN
