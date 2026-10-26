# -*- coding: utf-8 -*-
"""Opis typu modelu uczonego z rozkładu λ (właściciel 11.10: „dokładnie”,
14.10: „krótko, z głową”)."""
from footstats.model import opis_uczony as O

REF = {"w6": 4.0, "w12": 4.2, "w_dom": 4.1, "opp12": 4.3, "liga": 4.2}


def _typ(strona="powyzej", ref=REF, **pu):
    p_uczony = {"p": 0.66, "p_bez_pokrycia": 0.56, "lam": 4.44, "pkw": 0.8, "pkn": 10,
                "pkr": 0.8, "pkrn": 10,
                "skl": {"mn": {"forma": 1.08, "dom": 0.95, "rywal": 1.14, "liga": 1.0, "styl": 1.2},
                        "x": {"w6": 4.4, "w12": 4.0, "w_dom": 3.6, "opp12": 5.0, "liga": 4.2, "dom": 0},
                        "ref": ref,
                        "styl": [["posiadanie piłki", 1.2]]}}
    p_uczony.update(pu)
    return {"podmiot_typ": "druzyna", "strona": strona, "linia": 3.5, "podmiot": "Lazio",
            "rynek_kod": "team_corners", "przeciwnik": "Atalanta", "p_uczony": p_uczony}


def _opis(c, nazwa):
    return next(x for x in c if x["nazwa"] == nazwa)["opis"]


def test_druzyna_powyzej_kolejnosc_i_teksty():
    c = O.czynniki(_typ())
    assert c[0]["nazwa"] == "Spodziewana liczba" and "4,4" in c[0]["opis"]
    nazwy = [x["nazwa"] for x in c]
    # liga 1,00 bez wpływu; styl gry nigdy (nieczytelny dla gracza)
    assert "Liga" not in nazwy and "Styl gry" not in nazwy
    assert nazwy[1] == "Linia w historii" and "w 8 z 10 ostatnich meczów drużyny Lazio" in c[1]["opis"]
    # każda liczba z porównaniem do przeciętnej – względem niej model liczy kierunek
    assert _opis(c, "Rywal") == ("Przeciwnicy drużyny Atalanta notują średnio 5,0 rzutu rożnego "
                                 "na mecz, a przy przeciętnym rywalu 4,3")
    # w12 (4,0) jest PONIŻEJ przeciętnej, a forma podnosi λ – opis bierze w6 (4,4 > 4,0)
    assert _opis(c, "Forma") == ("Lazio w ostatnich 6 meczach notuje średnio 4,4 rzutu rożnego "
                                 "na mecz, a przeciętna drużyna 4,0")
    assert _opis(c, "Gdzie gra") == ("Drużyna Lazio gra na wyjeździe, a goście notują zwykle "
                                     "mniej rzutów rożnych")
    assert c[0]["opis"] == ("Nasz model spodziewa się, że Lazio zanotuje ok. 4,4 rzutu "
                            "rożnego – linia wynosi 3,5")
    assert next(x for x in c if x["nazwa"] == "Gdzie gra")["mnoznik"] < 1
    assert all(";" not in x["opis"] and "(" not in x["opis"] for x in c)


def test_ponizej_odwraca_kierunek_i_liczy_mecze_ponizej():
    c = O.czynniki(_typ(strona="ponizej", p=0.4, p_bez_pokrycia=0.5))
    rywal = next(x for x in c if x["nazwa"] == "Rywal")
    assert rywal["mnoznik"] < 1                  # rywal podnosi λ – przeciw „poniżej”
    gdzie = next(x for x in c if x["nazwa"] == "Gdzie gra")
    assert gdzie["mnoznik"] > 1                  # wyjazd obniża λ – za „poniżej”
    hist = next(x for x in c if x["nazwa"] == "Linia w historii")
    assert hist["opis"].startswith("Mniej niż 3,5 rzutu rożnego było w 2 z 10")


def test_liczba_sprzeczna_z_kierunkiem_nie_trafia_na_karte():
    # rywal pcha λ w górę, ale jego liczba jest PONIŻEJ przeciętnej – karta
    # pokazałaby „za” przy liczbie, która na oko przeczy (Thun 14.10)
    t = _typ()
    t["p_uczony"]["skl"]["x"]["opp12"] = 3.5
    nazwy = [x["nazwa"] for x in O.czynniki(t)]
    assert "Rywal" not in nazwy
    # bez odniesienia (typ wznowiony sprzed 14.10) – liczby bez porównania nie idą
    nazwy = [x["nazwa"] for x in O.czynniki(_typ(ref={}))]
    assert "Rywal" not in nazwy and "Forma" not in nazwy
    assert "Gdzie gra" in nazwy and "Linia w historii" in nazwy


def test_zawodnik():
    t = {"podmiot_typ": "zawodnik", "strona": "powyzej", "linia": 0.5, "przeciwnik": "Bayern",
         "podmiot": "Kane", "rynek_kod": "shots",
         "p_uczony": {"lam": 1.3, "pkw": 0.7, "pkn": 10,
                      "skl": {"mn": {"forma": 1.3, "minuty": 0.94, "rywal": 1.12, "dom": 1.0},
                              "x": {"t3": 2.0, "t6": 1.6, "t12": 1.5, "min": 85, "rywal": 1.18, "dom": 1},
                              "ref": {"t3": 1.2, "t6": 1.2, "t12": 1.2}}}}
    c = O.czynniki(t)
    nazwy = [x["nazwa"] for x in c]
    # „ostatnie mecze” karta zawodnika pokazuje kratkami – w opisie bez dubla
    assert "Ostatnie mecze" not in nazwy
    assert nazwy[:2] == ["Spodziewana liczba", "Tempo"]
    assert c[1]["opis"] == ("Kane ma średnio 1,5 strzału na 90 minut, w ostatnich 3 meczach 2,0, "
                            "a przeciętny zawodnik 1,2")
    assert _opis(c, "Rywal") == ("Zawodnicy na tej pozycji grający przeciw drużynie Bayern mają "
                                 "o 18% więcej strzałów niż średnio w lidze")
    assert _opis(c, "Minuty gry") == "Kane powinien zagrać ok. 85 minut"
    assert next(x for x in c if x["nazwa"] == "Minuty gry")["mnoznik"] < 1


def test_bez_skladnikow_pusto():
    assert O.czynniki({"strona": "powyzej", "p_uczony": {"p": 0.6}}) == []
