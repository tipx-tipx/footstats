"""Druga cena (Betclic) na karcie drabinki: na czym sprawdzamy, co pokazujemy.

Prześledzone 2026-08-04 na siedmiu żywych kartach — z pięciu meczów druga cena
nie doszła do ANI JEDNEJ, i za każdym razem z innego powodu:

    parowanie meczu       5/5   ✓
    zawodnicy u Betclica  3/5   dwa mecze: pusta lista
    dopasowanie nazwiska  1/4   trzy karty: gracza nie ma u Betclica
    wspólne linie         0/1   jedna karta: nasza drabinka miała JEDEN szczebel

Ostatni powód był nasz: karta pokazuje drabinkę przyciętą do tego, co grywalne,
a porównanie cen wymaga dwóch wspólnych linii. Podłoga drugiego szczebla
(dołożona dzień wcześniej) skracała drabinki i przez to pogarszała porównanie —
poprawka w jednym miejscu psuła drugie.
"""
from footstats.sources import betclic


def test_dwie_wspolne_linie_daja_porownanie():
    nasze = {0.5: {"over": 1.85}, 1.5: {"over": 4.35}}
    bc = {0.5: {"over": 1.60}, 1.5: {"over": 3.90}}
    assert betclic.porownaj_drabinke(nasze, bc)


def test_jedna_wspolna_linia_to_za_malo():
    """Jedna wspólna linia nie dowodzi, że obaj liczą to samo — drabinki
    potrafią zachodzić przesunięte o szczebel (przypadek Spinellego 29.07)."""
    nasze = {0.5: {"over": 1.85}}
    bc = {0.5: {"over": 1.60}, 1.5: {"over": 3.90}}
    assert betclic.porownaj_drabinke(nasze, bc) == {}


def test_pelna_lista_ratuje_jednoszczeblowa_karte():
    """SEDNO POPRAWKI: sprawdzamy na wszystkich kwotowanych liniach, a nie na
    przyciętej drabince. Ta sama oferta, ta sama karta — raz porównanie nie ma
    prawa powstać, raz powstaje."""
    bc = {0.5: {"over": 1.60}, 1.5: {"over": 3.90}}
    # to, co karta POKAZUJE (drugi szczebel uciął próg realności)
    drabinka = {0.5: {"over": 1.85}}
    # to, co bukmacher KWOTUJE
    pelne = {0.5: {"over": 1.85}, 1.5: {"over": 4.35}}
    assert betclic.porownaj_drabinke(drabinka, bc) == {}
    assert betclic.porownaj_drabinke(pelne, bc)


def test_rozjazd_wskazuje_gdzie_lepsza_cena():
    """Liczba na karcie („+41% u Betclica") musi wiedzieć, u KOGO jest lepiej —
    bez tego procent wisi w próżni."""
    r = betclic.rozjazd(1.40, 1.97)
    assert r and r["gdzie"] == "betclic"
    assert round(r["przewaga_pct"]) == 41
    odwrotnie = betclic.rozjazd(1.97, 1.40)
    assert odwrotnie and odwrotnie["gdzie"] == "superbet"
