"""Test filtra spójności kierunku (build_wc_fast.filtr_spojnosci_kierunku).

Przypadek źródłowy (rożne Legii, 24.07): model opublikował OBIE strony tej
samej linii — powyżej 4,5 @1.64 oraz poniżej 4,5 @2.12 (p=49,6%). Jedna
z definicji przegrywa. Zasada usera: „poniżej" dopiero od najwyższego
„powyżej" + 1 (korytarz legalny, kolizja nie).
"""

from footstats.jobs.build_wc_fast import (
    filtr_spojnosci_kierunku,
    kierunki_opublikowane,
)


def _leg(strona, linia, mecz_id=1, podmiot="Legia", rynek="team_corners"):
    return {"mecz_id": mecz_id, "podmiot": podmiot, "rynek_kod": rynek,
            "strona": strona, "linia": linia}


def test_kolizja_tej_samej_linii_odpada():
    legi = [_leg("powyzej", 3.5), _leg("powyzej", 4.5),
            _leg("ponizej", 4.5),   # kolizja z powyżej 4,5 -> out
            _leg("ponizej", 5.5),   # korytarz (>=4,5+1) -> zostaje
            _leg("ponizej", 6.5)]
    po = filtr_spojnosci_kierunku(legi)
    assert [(b["strona"], b["linia"]) for b in po] == [
        ("powyzej", 3.5), ("powyzej", 4.5), ("ponizej", 5.5),
        ("ponizej", 6.5),
    ]


def test_same_ponizej_bez_powyzej_przechodza():
    legi = [_leg("ponizej", 1.5), _leg("ponizej", 2.5)]
    assert filtr_spojnosci_kierunku(legi) == legi


def test_grupowanie_per_podmiot_i_rynek():
    # kolizja u Legii nie tnie typów Pogoni ani innego rynku Legii
    legi = [_leg("powyzej", 4.5),
            _leg("ponizej", 4.5),
            _leg("ponizej", 4.5, podmiot="Pogon"),
            _leg("ponizej", 0.5, rynek="team_goals")]
    po = filtr_spojnosci_kierunku(legi)
    assert _leg("ponizej", 4.5) not in po
    assert _leg("ponizej", 4.5, podmiot="Pogon") in po
    assert _leg("ponizej", 0.5, rynek="team_goals") in po


def test_rynki_zawodnicze_tylko_powyzej_bez_zmian():
    legi = [_leg("powyzej", 0.5, rynek="shots"),
            _leg("powyzej", 1.5, rynek="shots")]
    assert filtr_spojnosci_kierunku(legi) == legi


# --- SPÓJNOŚĆ MIĘDZY CYKLAMI (dziura zmierzona 2026-07-26) ---

def _log_rec(**kw):
    return {"mecz_id": 1, "podmiot": "Cracovia", "rynek_kod": "team_goals",
            "linia": 0.5, "strona": "ponizej", **kw}


def test_kierunki_z_logu_zbieraja_obie_strony():
    log = {
        "a": _log_rec(strona="ponizej", linia=0.5),
        "b": _log_rec(strona="powyzej", linia=1.5),
        "c": _log_rec(strona="powyzej", linia=2.5, odrzucony=True),
        "d": _log_rec(strona="ponizej", linia=0.5, poza_publikacja="limit_meczu"),
    }
    k = kierunki_opublikowane(log)
    slot = k[(1, "cracovia", "team_goals")]
    assert slot == {"ponizej": 0.5, "powyzej": 1.5}   # bez odrzuconych i tła


def test_nowe_powyzej_nie_przechodzi_gdy_ponizej_juz_opublikowane():
    """Realny przypadek: 21.07 poszło 'Cracovia poniżej 0,5', a 25.07 model
    zmienił zdanie i wystawił 'powyżej 0,5' — w puli nie było już strony
    'poniżej', więc stary filtr nie miał czego z czym porównać."""
    log = {"a": _log_rec(strona="ponizej", linia=0.5)}
    legi = [{"mecz_id": 1, "podmiot": "Cracovia", "rynek_kod": "team_goals",
             "linia": 0.5, "strona": "powyzej"}]
    assert filtr_spojnosci_kierunku(legi) == legi          # bez logu przechodzi
    assert filtr_spojnosci_kierunku(legi, kierunki_opublikowane(log)) == []


def test_korytarz_z_logiem_zostaje_legalny():
    """'poniżej 2,5' obok opublikowanego 'powyżej 0,5' może wygrać oba."""
    log = {"a": _log_rec(strona="powyzej", linia=0.5)}
    legi = [{"mecz_id": 1, "podmiot": "Cracovia", "rynek_kod": "team_goals",
             "linia": 2.5, "strona": "ponizej"}]
    assert filtr_spojnosci_kierunku(legi, kierunki_opublikowane(log)) == legi


def test_inny_mecz_nie_blokuje():
    log = {"a": _log_rec(mecz_id=99, strona="ponizej", linia=0.5)}
    legi = [{"mecz_id": 1, "podmiot": "Cracovia", "rynek_kod": "team_goals",
             "linia": 0.5, "strona": "powyzej"}]
    assert filtr_spojnosci_kierunku(legi, kierunki_opublikowane(log)) == legi
