"""Okno kwarantanny liczy DNI MECZOWE, nie tylko rekordy.

POWÓD (zgłoszenie usera 2026-08-03: „znowu przestały się generować kupony").
Okna liczone w sztukach powstały, gdy rozliczaliśmy 5–10 typów dziennie —
czterdzieści rekordów było wtedy „ostatnim tygodniem". Dziś jedna niedziela
rozlicza 41 typów na samym `team_goals`, więc okno po cichu zmieniło znaczenie
na „wczoraj":

    team_goals   ostatnie 40 (okno):  trafień 38%   ROI −34,5%   <- kwarantanna
                 ostatnie 120:        trafień 54%   ROI  −1,3%
                 dni: 31.07 +26%, 01.08 +42%, 02.08 −44% (n=41), 03.08 +39%

Rynek praktycznie na zero wpadł do kwarantanny za JEDEN zły dzień. Że stoi na
nim 12 z 20 typów strony, pula kuponów została z jednym legiem i kupony
przestały powstawać.
"""

from footstats.jobs import rozliczanie as R

DOBA = 86400


def _rek(dzien: int, i: int = 0) -> dict:
    return {"kickoff_ts": dzien * DOBA + i}


def test_okno_rozszerza_sie_do_pieciu_dni():
    """Jeden dzień z ogromnym wolumenem nie może wypełnić całego okna."""
    rek = ([_rek(100, i) for i in range(10)]     # 5 wcześniejszych dni po 2
           + [_rek(101, i) for i in range(2)]
           + [_rek(102, i) for i in range(2)]
           + [_rek(103, i) for i in range(2)]
           + [_rek(104, i) for i in range(2)]
           + [_rek(105, i) for i in range(50)])  # jedna „niedziela"
    okno = R.okno_kroczace(rek, sztuk=40)
    dni = {R.dzien_pl(r["kickoff_ts"]) for r in okno}
    assert len(dni) >= R.KWARANTANNA_MIN_DNI
    assert len(okno) > 40          # rozszerzone poza sztywne 40


def test_gdy_dni_wystarcza_okno_zostaje_male():
    """Rynek grający codziennie po trochu nie dostaje szerszego okna."""
    rek = [_rek(100 + i // 4, i) for i in range(40)]   # 10 dni po 4
    okno = R.okno_kroczace(rek, sztuk=40)
    assert len(okno) == 40


def test_sufit_chroni_kroczacosc_okna():
    """Rynek grający rzadko (albo cała historia w jednej dobie) nie może cofać
    okna przez całą księgę — inaczej przestaje być kroczące i rynek nigdy nie
    wraca po poprawie."""
    rek = [_rek(100, i) for i in range(500)]           # wszystko jednego dnia
    okno = R.okno_kroczace(rek, sztuk=40)
    assert len(okno) == 120                            # 3 x sztuk, nie 500


def test_pusta_historia_nie_wywala():
    assert R.okno_kroczace([], sztuk=40) == []


def test_zla_passa_jednego_dnia_nie_wystarcza_na_kwarantanne():
    """Test na całej bramie, nie na samym oknie: rynek z dobrą historią i jedną
    fatalną niedzielą ZOSTAJE, a rynek zły w każdym oknie wchodzi."""
    def _typ(rynek, dzien, wynik, i):
        return {
            "mecz_id": 1, "mecz": "Lech – Legia", "podmiot": "Lech",
            "podmiot_id": 1, "rynek_kod": rynek, "rynek": rynek,
            "linia": 1.5, "strona": "ponizej", "kurs": 1.9, "p_model": 0.6,
            "wynik": wynik, "kickoff_ts": dzien * DOBA + i,
        }
    # liczby odwzorowują rzeczywistość z 03.08: dobre dni trafiały ~67%,
    # feralna niedziela 34% przy wolumenie 41 typów
    dobre_dni = [_typ("team_goals", 100 + d, "wygrany" if i % 3 else "przegrany", i)
                 for d in range(6) for i in range(12)]
    zla_niedziela = [_typ("team_goals", 110,
                          "wygrany" if i % 3 == 0 else "przegrany", i)
                     for i in range(41)]
    log = {f"a{i}": r for i, r in enumerate(dobre_dni + zla_niedziela)}
    assert "team_goals" not in R.rynki_kwarantanna(log)

    stale_zly = {f"b{i}": _typ("team_corners", 100 + i // 8, "przegrany", i)
                 for i in range(60)}
    assert "team_corners" in R.rynki_kwarantanna(stale_zly)
