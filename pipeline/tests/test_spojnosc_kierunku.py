"""Test filtra spójności kierunku (build_wc_fast.filtr_spojnosci_kierunku).

Przypadek źródłowy (rożne Legii, 24.07): model opublikował OBIE strony tej
samej linii — powyżej 4,5 @1.64 oraz poniżej 4,5 @2.12 (p=49,6%). Jedna
z definicji przegrywa. Zasada usera: „poniżej" dopiero od najwyższego
„powyżej" + 1 (korytarz legalny, kolizja nie).
"""

from footstats.jobs.build_wc_fast import filtr_spojnosci_kierunku


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
