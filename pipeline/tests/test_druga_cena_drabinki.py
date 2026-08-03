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
import pytest

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


# --- od kiedy różnica jest OKAZJĄ, a od kiedy to tylko dwie marże ---

def _karta(sb, bc):
    """Karta z jednym rozjazdem policzonym tak, jak liczy go produkcja."""
    return {"rynki": [{"drabinka": [{"rozjazd": betclic.rozjazd(sb, bc)}]}]}


@pytest.mark.parametrize("sb,bc,kategoria,pp,dlaczego", [
    # Zgłoszenie usera 04.08: „1,59 wobec 1,82 bez sensu pokazywać, to już
    # lepiej jako normalna drabinka". Prog stal na 8% i taka karta dostawala
    # bursztyn, jakby byla okazja.
    (1.59, 1.82, "rynek_zgodny", 7.9, "dwie marze, nie spor"),
    # ...a te user wskazal jako dobre
    (1.70, 2.30, "rozjazd", 15.3, "przyklad usera"),
    (1.70, 2.50, "rozjazd", 18.8, "przyklad usera"),
    (1.30, 2.00, "rozjazd", 26.9, "przyklad usera"),
])
def test_prog_okazji_trafia_w_szczeline(sb, bc, kategoria, pp, dlaczego):
    from footstats.jobs import radar
    r = betclic.rozjazd(sb, bc)
    assert r["roznica_pp"] == pp, dlaczego
    assert radar._kategoria_karty(_karta(sb, bc)) == kategoria, dlaczego


def test_procent_klamie_przy_wysokich_kursach():
    """SEDNO przejscia na punkty: ten sam procent, dwa rozne zdarzenia.
    Przy 4,00/5,00 prawie cala roznica to marza, przy 1,20/1,50 to realna
    niezgoda co do tego, czy zdarzenie w ogole nastapi."""
    from footstats.jobs import radar
    drogie = betclic.rozjazd(4.00, 5.00)
    tanie = betclic.rozjazd(1.20, 1.50)
    assert round(drogie["przewaga_pct"]) == round(tanie["przewaga_pct"]) == 25
    assert drogie["roznica_pp"] == 5.0
    assert tanie["roznica_pp"] == 16.7
    assert radar._kategoria_karty(_karta(4.00, 5.00)) == "rynek_zgodny"
    assert radar._kategoria_karty(_karta(1.20, 1.50)) == "rozjazd"


def test_prog_okazji_zgodny_z_ukladem_pewniak_taniej():
    """Dwie bramy mówiące o tym samym nie mogą stać w dwóch miejscach:
    „pewniak taniej" to 1,45 wobec 1,75, czyli 11,8 punktu na własnej granicy."""
    from footstats.jobs import radar
    granica = betclic.rozjazd(betclic.PEWNIAK_MAX_KURS,
                              betclic.PEWNIAK_MIN_LEPSZY)["roznica_pp"]
    assert radar.PROG_OKAZJI_PP >= granica
