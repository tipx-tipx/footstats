# -*- coding: utf-8 -*-
"""PRZEŁĄCZENIE ŹRÓDŁA SZANSY — model uczony na stronie (2026-08-18).

Decyzja właściciela: przełączamy od razu, ale z warunkiem — ma być NIEMOŻLIWE,
żeby za dwa tygodnie okazało się, że model po cichu nie liczył. Stąd testy
pilnują nie samego wyboru liczby, ale przede wszystkim ŚLADU po nim.
"""
from footstats.model import uczony as U


def test_druzyny_zawodnicy_i_sumy_licza_modelem_drabinki_nie():
    # drabinki zostają na starym rachunku — decyzja właściciela 18.08,
    # mają własną korektę i wymagają osobnej roboty modelowej
    assert U.na_stronie("druzyny")
    assert U.na_stronie("pewniaki")
    assert U.na_stronie("sumy")
    assert not U.na_stronie("drabinki")


def test_nieznany_strumien_zostaje_na_starym():
    # domyślnie NIE przełączamy — nowy strumień musi zostać dopisany świadomie
    assert not U.na_stronie("cokolwiek_nowego")
    assert not U.na_stronie("")
    assert not U.na_stronie(None)


def test_model_z_pokryciem_idzie_na_strone():
    p, zrodlo = U.wybierz_szanse("druzyny", 0.65, {"p": 0.51, "lam": 4.2})
    assert p == 0.51 and zrodlo == "uczony"


def test_brak_pokrycia_wraca_na_stary_ALE_ZOSTAWIA_SLAD():
    # ⚑ najważniejszy test: cichy fallback byłby tu najgorszy z możliwych —
    # strona pokazywałaby mieszankę, a pomiar przypisywał wszystko modelowi
    p, zrodlo = U.wybierz_szanse("druzyny", 0.65, None)
    assert p == 0.65
    assert zrodlo == "stary_bez_pokrycia", "fallback MUSI być odróżnialny"

    p, zrodlo = U.wybierz_szanse("druzyny", 0.65, {"lam": 4.2})   # p brakuje
    assert p == 0.65 and zrodlo == "stary_bez_pokrycia"


def test_strumien_na_starym_nie_dostaje_liczby_modelu():
    p, zrodlo = U.wybierz_szanse("drabinki", 0.65, {"p": 0.51})
    assert p == 0.65 and zrodlo == "stary"


def test_ksiega_dostaje_OBIE_liczby_niezaleznie_od_przelacznika():
    # bez tego nie da się po fakcie odpowiedzieć, czy przełączenie pomogło
    s = U.stempel_zrodla(0.65, {"p": 0.51, "lam": 4.2}, "uczony")
    assert s["p_stary"] == 0.65
    assert s["p_uczony"]["p"] == 0.51
    assert s["zrodlo_p"] == "uczony"

    # także gdy na stronie został STARY rachunek
    s = U.stempel_zrodla(0.65, {"p": 0.51}, "stary")
    assert s["p_stary"] == 0.65 and s["p_uczony"]["p"] == 0.51
    assert s["zrodlo_p"] == "stary"


def test_stempel_bez_prognozy_nie_udaje_ze_ja_ma():
    s = U.stempel_zrodla(0.65, None, "stary_bez_pokrycia")
    assert "p_uczony" not in s
    assert s["zrodlo_p"] == "stary_bez_pokrycia"


def test_przelacznik_powrotu_dziala_bez_ruszania_kodu(monkeypatch):
    # warunek właściciela: cofnięcie ma być jedną stałą, bez rewertowania
    monkeypatch.setitem(U.ZRODLO_SZANSY, "druzyny", "stary")
    p, zrodlo = U.wybierz_szanse("druzyny", 0.65, {"p": 0.51})
    assert p == 0.65 and zrodlo == "stary"


# --- WARSTWY UCZENIA NIE MOGĄ MIESZAĆ DWÓCH RACHUNKÓW --------------------

def test_warstwy_ucza_sie_wylacznie_na_starym_rachunku():
    """Warstwa mierzy „o ile rachunek zawyża". Typ policzony modelem nie
    zawyża, więc wrzucony do tej samej próby rozwadnia korektę dla drabinek,
    które NA WARSTWACH ZOSTAJĄ."""
    from footstats.jobs import rozliczanie as R
    assert not R._stary_rachunek({"zrodlo_p": "uczony"})
    assert R._stary_rachunek({"zrodlo_p": "stary"})
    # fallback przy braku pokrycia to STARY rachunek — ma uczyć warstwy
    assert R._stary_rachunek({"zrodlo_p": "stary_bez_pokrycia"})
    # rekordy sprzed 18.08 nie mają stempla i są z definicji stare
    assert R._stary_rachunek({})


# --- WARSTWY WYŚWIETLANIA NIE RUSZAJĄ LICZBY MODELU ------------------------

def test_proba_ceny_nie_miesza_dwoch_rachunkow():
    """Waga ściągania odpowiada na pytanie „ile NASZEJ liczby zostawić obok
    ceny" — a to zależy od tego, CZYJA to liczba. Na starym rachunku wyszło
    w=0,05 (karta w 95% pokazywała cenę), bo tamten zawyżał o 14 pp. Model ma
    lukę −0,7 pp, więc to INNY pomiar."""
    from footstats.jobs import rozliczanie as R

    log = {
        "a": {"wynik": "wygrany", "kurs": 1.8, "p_model": 0.70,
              "zrodlo_p": "stary", "kickoff_ts": 1_787_000_000},
        "b": {"wynik": "przegrany", "kurs": 2.0, "p_model": 0.52,
              "zrodlo_p": "uczony", "kickoff_ts": 1_787_000_000},
        "c": {"wynik": "wygrany", "kurs": 1.6, "p_model": 0.66,
              "kickoff_ts": 1_787_000_000},          # sprzed stempla = stary
    }
    stary = R._proba_ceny(log, "stary")
    uczony = R._proba_ceny(log, "uczony")
    assert {round(p, 2) for p, _, _ in stary} == {0.70, 0.66}
    assert {round(p, 2) for p, _, _ in uczony} == {0.52}
    assert not (set(stary) & set(uczony)), "próby nie mogą się przecinać"


def test_urealnienie_pokazywanej_szansy_omija_model():
    """Delta jest duża (drużyny −0,63 logitu): z uczciwych 51% modelu robi na
    karcie 36%, a razem z nią przewraca kurs uczciwy, przewagę i wartość."""
    import inspect
    from footstats.jobs import build_wc_fast as B

    zrodlo = inspect.getsource(B)
    i = zrodlo.index("def _urealnij_do_pokazania")
    blok = zrodlo[i:i + 1600]
    assert 'zrodlo_p' in blok and '"uczony"' in blok, (
        "warstwa `szansa_pokazywana` znowu ściąga liczbę modelu — a model "
        "nie przeszacowuje, więc nie ma tu czego urealniać"
    )


def test_sciaganie_karty_ma_osobna_wage_dla_modelu():
    import inspect
    from footstats.jobs import build_wc_fast as B

    zrodlo = inspect.getsource(B)
    i = zrodlo.index("def _sciagnij_karte_do_ceny")
    blok = zrodlo[i:i + 1400]
    assert "_waga_karty_uczony" in blok, (
        "karta liczona modelem używa wagi zmierzonej na STARYM rachunku"
    )
