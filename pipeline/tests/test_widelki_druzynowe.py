"""Brama kurs×szansa dla rynków drużynowych (betting.WIDELKI_DRUZYNOWE).

Rozdzielona na trzy powody 2026-07-27, bo była NAJWIĘKSZYM sitem w systemie
(1372 odrzucenia w jednym cyklu) i jedynym progiem nigdy niezweryfikowanym
rozliczeniami. Testy pilnują, żeby rozdzielenie NIE zmieniło decyzji — zmienia
się tylko to, co o niej wiemy.
"""

from footstats.model import betting


def _stara_brama(odd, p, p_ostrozne):
    """Dosłownie kod sprzed rozdzielenia — punkt odniesienia."""
    pewny = (
        betting.MIN_ODDS <= odd <= 2.80
        and p >= 0.52 and p_ostrozne * odd - 1.0 >= 0.0
    )
    perelka = (
        1.90 <= odd <= 3.60
        and p >= 0.42 and p_ostrozne * odd - 1.0 >= 0.0
    )
    return pewny or perelka


def test_rozdzielenie_nie_zmienilo_ani_jednej_decyzji():
    """Siatka po całej przestrzeni kurs × szansa — decyzja musi być identyczna."""
    sprawdzonych = 0
    for i in range(0, 71):
        odd = 1.0 + i * 0.1                     # 1,0 .. 8,0
        for j in range(0, 21):
            p = j * 0.05                        # 0 .. 1
            for ubytek in (0.0, 0.05, 0.15):    # p ostrożne poniżej p
                p_ostr = max(0.0, p - ubytek)
                assert (
                    betting.widelki_druzynowe_ok(odd, p, p_ostr)
                    == _stara_brama(odd, p, p_ostr)
                ), f"rozjazd przy kurs={odd:.2f} p={p:.2f} p_ostr={p_ostr:.2f}"
                sprawdzonych += 1
    assert sprawdzonych > 4000


def test_powod_wskazuje_najbardziej_zewnetrzny_warunek():
    # kurs 5,0 jest poza OBOMA przedziałami (suma to 1,19–3,60)
    assert betting.powod_widelek(5.0, 0.90, 0.90) == "kurs_poza_widelkami"
    # kurs w widełkach „pewniaka", ale szansa poniżej obu progów
    assert betting.powod_widelek(1.50, 0.30, 0.30) == "szansa_za_niska"
    # kurs i szansa w porządku, nie wychodzi dopiero rachunek na p ostrożnym
    assert betting.powod_widelek(1.50, 0.60, 0.55) == "wartosc_ujemna"


def test_powod_liczy_progi_tylko_z_pasujacych_przedzialow():
    """Kurs 3,4 mieści się WYŁĄCZNIE w „perełce" (próg 0,42), nie w „pewniaku".

    Gdyby powód patrzył na najwyższy próg z całej tabeli, typ z p=0,45 dostałby
    „szansa za niska", choć swojemu przedziałowi odpowiada.
    """
    assert betting.powod_widelek(3.4, 0.45, 0.20) == "wartosc_ujemna"
    assert betting.powod_widelek(3.4, 0.35, 0.35) == "szansa_za_niska"


def test_blisko_progu_tylko_dla_odrzuconych_i_naprawde_blisko():
    # przechodzący typ nigdy nie jest „blisko" — jest w środku
    assert betting.widelki_druzynowe_ok(1.50, 0.70, 0.70)
    assert not betting.widelki_druzynowe_blisko(1.50, 0.70, 0.70)
    # minięcie się SAMYM rachunkiem: kurs 2,5, p ostrożne 0,39 -> −2,5%
    assert not betting.widelki_druzynowe_ok(2.50, 0.44, 0.39)
    assert betting.widelki_druzynowe_blisko(2.50, 0.44, 0.39)
    # minięcie się SAMĄ szansą: 0,36 przy progu 0,42, ale rachunek wychodzi
    assert not betting.widelki_druzynowe_ok(3.00, 0.36, 0.34)
    assert betting.widelki_druzynowe_blisko(3.00, 0.36, 0.34)
    # 0,20 przy kursie 1,5 to nie „tuż pod progiem", tylko zły zakład
    assert not betting.widelki_druzynowe_blisko(1.50, 0.20, 0.20)
    # kurs 12 jest daleko poza sufitem nawet z tolerancją 1,4x
    assert not betting.widelki_druzynowe_blisko(12.0, 0.90, 0.90)


def test_progi_szansy_pokrywaja_sie_z_progiem_oplacalnosci():
    """POMIAR, nie zgadywanka: progi 0,52 i 0,42 to prawie próg opłacalności.

    Przy kursie 1,92 do wyjścia na zero potrzeba 52% — dokładnie tyle, ile
    wymaga próg „pewniaka" na jego górnej granicy. Przy 2,38 to 42%, czyli
    próg „perełki". Wniosek jest istotny dla następnego kroku: progi szansy NIE
    są niezależnym, dodatkowym sitem — w większości zakresu wiąże ten sam
    warunek co rachunek opłacalności. Ruszanie ich osobno niewiele zmieni;
    prawdziwym sitem jest wymóg dodatniej wartości na p OSTROŻNYM (średniej
    z p i dolnej granicy przedziału), bo to znacznie mocniejsze żądanie.
    """
    for kurs, prog in ((1.92, 0.52), (2.38, 0.42)):
        assert abs(1.0 / kurs - prog) < 0.01, kurs


def test_tolerancje_pomiaru_nie_sa_szersze_niz_sama_brama():
    """Pomiar ma badać SĄSIEDZTWO progu, nie zastępować bramy drugą bramą."""
    assert 0 < betting.NEAR_WIDELKI_P <= 0.10
    assert 0 < betting.NEAR_WIDELKI_EV <= 0.05
    assert 1.0 < betting.NEAR_WIDELKI_KURS <= 1.5
