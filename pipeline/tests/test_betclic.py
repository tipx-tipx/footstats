"""Testy drugiego cennika (Betclic): parowanie, rozjazd, wpięcie w Drabinki.

Rynków zawodniczych Betclic nie wystawia wcześniej niż na dzień-dwa przed
meczem (zmierzone 2026-07-28 na trzech bukmacherach naraz), więc ścieżki
nie da się dziś sprawdzić na żywej ofercie. Te testy trzymają ją na
syntetyce: reguły parowania i matematykę rozjazdu można sprawdzić zawsze.
"""

from footstats.jobs import radar
from footstats.sources import betclic


def _bc(mid, home, away, ts):
    return {"id": mid, "nazwa": f"{home} - {away}", "gospodarz": home,
            "gosc": away, "kickoff_ts": ts}


TS = 1_800_000_000


# ---------------------------------------------------------------------------
# Parowanie meczów
# ---------------------------------------------------------------------------

def test_paruje_mimo_ozdobnikow_w_nazwie():
    """'Lincoln Red Imps' i 'Lincoln Red Imps FC' to ten sam klub."""
    nasze = [{"klucz": 1, "home": "Lincoln Red Imps", "away": "Mjällby AIF",
              "kickoff_ts": TS}]
    bc = [_bc(99, "Lincoln Red Imps FC", "Mjallby AIF", TS)]
    pary, luka = betclic.paruj_mecze(nasze, bc)
    assert pary[1]["id"] == 99
    assert luka == []


def test_nie_podmienia_klubu_o_podobnej_nazwie():
    """Riestra vs Recoleta — pułapka podobieństwa tekstu (0,80), INNY klub.

    Brak dopasowania widać, podmianę nie — dlatego wolimy nie sparować.
    """
    nasze = [{"klucz": 1, "home": "Deportivo Riestra", "away": "Banfield",
              "kickoff_ts": TS}]
    bc = [_bc(99, "Deportivo Recoleta", "Banfield", TS)]
    pary, _ = betclic.paruj_mecze(nasze, bc)
    assert pary == {}


def test_remis_kandydatow_to_brak_pary():
    """Dwa równie dobre dopasowania = nie zgadujemy."""
    nasze = [{"klucz": 1, "home": "Sabah", "away": "Sabah", "kickoff_ts": TS}]
    bc = [_bc(1, "Sabah", "Sabah", TS), _bc(2, "Sabah", "Sabah", TS + 60)]
    pary, _ = betclic.paruj_mecze(nasze, bc)
    assert pary == {}


def test_czas_jest_twarda_brama():
    """Ta sama para drużyn, ale mecz dobę później — to inny mecz."""
    nasze = [{"klucz": 1, "home": "Legia Warszawa", "away": "Lech Poznań",
              "kickoff_ts": TS}]
    bc = [_bc(99, "Legia Warszawa", "Lech Poznan", TS + 86_400)]
    pary, _ = betclic.paruj_mecze(nasze, bc)
    assert pary == {}


def test_apostrof_nie_rozbija_nazwy():
    """'Be'er Sheva' rozpadało się na 'be' i 'er' — Betclic pisze 'Beer'."""
    nasze = [{"klucz": 1, "home": "Hapoel Be'er Sheva",
              "away": "Víkingur Reykjavík", "kickoff_ts": TS}]
    bc = [_bc(99, "Hapoel Beer Sheva", "Vikingur Reykjavik", TS)]
    pary, _ = betclic.paruj_mecze(nasze, bc)
    assert pary[1]["id"] == 99


def test_alias_spolszczonej_nazwy():
    """Betclic spolszcza kluby ('Dinamo Zagrzeb') — na to jest tablica."""
    nasze = [{"klucz": 1, "home": "GNK Dinamo Zagreb", "away": "FC Thun",
              "kickoff_ts": TS}]
    bc = [_bc(99, "Dinamo Zagrzeb", "FC Thun", TS)]
    pary, _ = betclic.paruj_mecze(nasze, bc)
    assert pary[1]["id"] == 99


# ---------------------------------------------------------------------------
# Zawodnik i rozjazd
# ---------------------------------------------------------------------------

def test_zawodnik_po_podzbiorze_tokenow_ale_jednoznacznie():
    gracze = {"lisandro semedo": {"shots": {1.5: {"over": 2.1}}}}
    assert betclic.znajdz_zawodnika(gracze, "Semedo, Lisandro")
    # dwóch kandydatów = brak dopasowania
    gracze2 = {"jan kowalski": {}, "kowalski piotr jan": {}}
    assert betclic.znajdz_zawodnika(gracze2, "Kowalski") == {}


def test_rozjazd_wskazuje_lepsza_cene_i_ostrozniejsza_szanse():
    r = betclic.rozjazd(1.37, 1.90)
    assert r["gdzie"] == "betclic"
    assert r["lepszy"] == 1.90
    assert r["przewaga_pct"] == 38.7        # 1,90/1,37 - 1
    # szansa liczona z TAŃSZEJ ceny — to ostrożniejsza ocena rynku
    assert r["p_rynku"] == round(1 / 1.37, 4)


def test_rozjazd_odrzuca_nieprawdopodobna_roznice():
    """13-krotna różnica ceny to nie okazja, tylko dwie różne statystyki."""
    assert betclic.rozjazd(28.0, 1.95) is None
    # wzorcowy wpis typera (1,37 vs 1,90 = +39%) MUSI przejść
    assert betclic.rozjazd(1.37, 1.90) is not None


def test_pewniak_u_jednego_a_pieniadze_u_drugiego():
    """NAJCENNIEJSZY układ: 1,25 „bo pewne" u jednego, 2,00 u drugiego.

    Na tym stoją wszystkie cztery wpisy typera, które user pokazał. Musi
    przechodzić bramy i być NAZWANY, żeby front mógł go wyróżnić.
    """
    r = betclic.rozjazd(1.25, 2.00)
    assert r["typ"] == "pewniak_taniej"
    assert r["gdzie"] == "betclic"
    assert r["p_rynku"] == 0.8         # szansa z TAŃSZEJ ceny: 1/1,25
    # zwykła różnica dwóch podobnych cen to nie ten układ
    assert betclic.rozjazd(2.10, 2.35)["typ"] == "zwykly"
    # i szeroki rozjazd na taniej stronie też przechodzi (1,20 vs 2,60)
    assert betclic.rozjazd(1.20, 2.60)["typ"] == "pewniak_taniej"


def test_jedna_wspolna_linia_to_za_malo():
    """Rynek liczący CO INNEGO ma z naszym najwyżej jedną wspólną linię.

    Zmierzone: Betclic kwotował Reichmutha na 4,5–6,5 strzału, Superbet na
    0,5–2,5. Jedyna część wspólna dała +1336% „przewagi" — czyli bzdurę.
    """
    sb = {5.5: {"over": 28.0}}
    bc = {5.5: {"over": 1.95}, 6.5: {"over": 2.8}}
    assert betclic.porownaj_drabinke(sb, bc) == {}
    # dwie wspólne linie = cenniki mówią o tym samym, porównujemy
    sb2 = {0.5: {"over": 1.25}, 1.5: {"over": 2.5}}
    bc2 = {0.5: {"over": 2.00}, 1.5: {"over": 2.7}}
    wynik = betclic.porownaj_drabinke(sb2, bc2)
    assert set(wynik) == {0.5, 1.5}
    assert wynik[0.5]["typ"] == "pewniak_taniej"


def test_kod_rynku_odsiewa_nie_nasze_rynki():
    assert betclic.kod_rynku("Liczba strzałów zawodnika spoza pola karnego") \
        == "shots_outside_box"
    assert betclic.kod_rynku("Liczba odbiorów zawodnika (OPTA)") == "tackles"
    # rynek drużynowy tym samym słownikiem — nie może wjechać jako zawodniczy
    assert betclic.kod_rynku("Liczba fauli (OPTA) - FC Thun") is None
    # my liczymy 90 minut
    assert betclic.kod_rynku("Liczba fauli zawodnika (OPTA) - 1. połowa") is None
    assert betclic.kod_rynku("Liczba odbiorów zawodnika (z dogrywką)") is None
    # strzały Z POLA karnego to inna statystyka niż nasze
    assert betclic.kod_rynku("Liczba strzałów zawodnika z pola karnego") is None
    # podania i asysty — nie mamy takich rynków
    assert betclic.kod_rynku("Liczba celnych podań zawodnika (OPTA)") is None
    # pusta nazwa z dekodera (bywa listą) nie może wywalić odczytu
    assert betclic.kod_rynku([]) is None


def test_linia_i_strona_znosi_pusta_nazwe_z_dekodera():
    """⚑ REGRESJA 2026-08-08. `kod_rynku` szedł przez `_tekst`, a bliźniacze
    `linia_i_strona` przez gołe `.lower()` — więc pusta wiadomość z dekodera
    (`[]` zamiast napisu) rzucała `AttributeError` w pętli po zakładach
    i kładła cały przebieg joba. Ta sama nazwa, dwie różne odporności."""
    assert betclic.linia_i_strona([]) == (None, None)
    assert betclic.linia_i_strona(None) == (None, None)
    assert betclic.linia_i_strona("") == (None, None)
    assert betclic.linia_i_strona(123) == (None, None)
    # a normalne nazwy dalej czytamy tak samo
    assert betclic.linia_i_strona("Powyżej 1,5") == (1.5, "over")
    assert betclic.linia_i_strona("Poniżej 2,5") == (2.5, "under")


def test_rozjazd_odrzuca_smieci():
    assert betclic.rozjazd(None, 1.9) is None
    assert betclic.rozjazd(1.0, 1.9) is None
    assert betclic.rozjazd(1.5, None) is None


def test_porownaj_kursy_tylko_wspolne_linie():
    """Porównujemy wyłącznie linie, które mają OBAJ bukmacherzy — i dopiero
    gdy jest ich co najmniej dwie (brama `MIN_WSPOLNYCH_LINII`)."""
    sb = {"semedo lisandro": {"shots_outside_box": {
        0.5: {"over": 1.37}, 1.5: {"over": 4.0}, 2.5: {"over": 9.0}}}}
    bc = {"semedo lisandro": {"shots_outside_box": {
        0.5: {"over": 1.90}, 1.5: {"over": 4.4}}}}
    out = betclic.porownaj_kursy(sb, bc)
    assert {x["linia"] for x in out} == {0.5, 1.5}
    assert out[0]["gdzie"] == "betclic"

    # jedna wspólna linia = za mało, żeby uwierzyć, że to ta sama statystyka
    bc_jedna = {"semedo lisandro": {"shots_outside_box": {0.5: {"over": 1.90}}}}
    assert betclic.porownaj_kursy(sb, bc_jedna) == []


# ---------------------------------------------------------------------------
# Wpięcie w kartę Drabinki
# ---------------------------------------------------------------------------

def _karta():
    return {
        "mecz_id": 7, "kickoff_ts": TS, "podmiot": "Lisandro Semedo",
        "hero": {"rynek_kod": "shots_outside_box", "linia": 0.5},
        "rynki": [{"rynek_kod": "shots_outside_box", "drabinka": [
            {"linia": 0.5, "kurs": 1.37},
            {"linia": 1.5, "kurs": 4.00},
            {"linia": 2.5, "kurs": 9.00},
        ]}],
    }


def test_dopina_druga_cene_do_szczebla(monkeypatch):
    karty = [_karta()]
    meta = {7: {"home": "Radomiak Radom", "away": "Wieczysta Kraków", "ts": TS}}
    monkeypatch.setattr(betclic, "paruj_mecze",
                        lambda nasze, *a, **k: ({7: {"id": 123, "nazwa": "x"}}, []))
    monkeypatch.setattr(betclic, "kursy_zawodnikow", lambda *a, **k: {
        "players": {"lisandro semedo": {"shots_outside_box": {
            0.5: {"over": 1.90}, 1.5: {"over": 4.40}}}}})
    radar._dopnij_betclic(karty, meta)
    szczeble = karty[0]["rynki"][0]["drabinka"]
    assert szczeble[0]["kurs_betclic"] == 1.90
    assert szczeble[0]["rozjazd"]["gdzie"] == "betclic"
    # linia bez ceny u Betclica zostaje nietknięta
    assert "kurs_betclic" not in szczeble[2]
    # rozjazd rynku, który wygrał kartę, ląduje też na wierzchu
    assert karty[0]["rozjazd_hero"]["betclic"] == 1.90
    # i układ „pewniak taniej" (1,37 vs 1,90) wyciągnięty osobno
    assert karty[0]["rozjazd_pewniak"]["linia"] == 0.5


def test_awaria_betclica_nie_wywala_przebiegu(monkeypatch):
    karty = [_karta()]
    meta = {7: {"home": "A", "away": "B", "ts": TS}}

    def bum(*a, **k):
        raise RuntimeError("Betclic padł")

    monkeypatch.setattr(betclic, "paruj_mecze", bum)
    radar._dopnij_betclic(karty, meta)          # nie rzuca
    assert "rozjazd_hero" not in karty[0]


# --- TEST PRZESUNIĘCIA DRABINEK (2026-07-29) -------------------------------


def test_drabinka_przesunieta_o_szczebel_odpada():
    """Sprawa Claudia Spinellego (żywa karta 29.07).

    Karta obiecywała „Betclic wycenia 4+ na 1,40, a Superbet płaci 1,97 —
    o 41% więcej za to samo". Wyglądało na okazję, a drabinki zachodzą na
    siebie idealnie po przesunięciu o jeden szczebel: to samo zdarzenie
    nazywa się u nich inaczej. Pomiar na 200 drabinkach: 18 takich par.
    """
    sb = {1.5: {"over": 1.10}, 2.5: {"over": 1.39}, 3.5: {"over": 1.97},
          4.5: {"over": 3.00}, 5.5: {"over": 4.70}}
    bc = {3.5: {"over": 1.40}, 4.5: {"over": 1.90}, 5.5: {"over": 2.80}}
    assert betclic.porownaj_drabinke(sb, bc) == {}


def test_uklad_pewniak_taniej_dalej_przechodzi():
    """Bramy NIE WOLNO zacieśnić tak, żeby zabiła układ, o który chodzi
    userowi: „1,20 u jednego, 2,60 u drugiego" (decyzja 2026-07-28)."""
    sb = {0.5: {"over": 1.20}, 1.5: {"over": 2.40}, 2.5: {"over": 4.60}}
    bc = {0.5: {"over": 2.60}, 1.5: {"over": 2.50}, 2.5: {"over": 4.50}}
    r = betclic.porownaj_drabinke(sb, bc)
    assert r[0.5]["typ"] == "pewniak_taniej"
    # ...i mówi, gdzie grać — rozjazd działa w OBIE strony
    assert r[0.5]["gdzie"] == "betclic"
    assert r[0.5]["lepszy"] == 2.60


def test_rozjazd_wskazuje_takze_superbet():
    """Druga strona tej samej monety: gdy to Superbet płaci więcej."""
    sb = {0.5: {"over": 2.60}, 1.5: {"over": 2.50}, 2.5: {"over": 4.50}}
    bc = {0.5: {"over": 1.20}, 1.5: {"over": 2.40}, 2.5: {"over": 4.60}}
    r = betclic.porownaj_drabinke(sb, bc)
    assert r[0.5]["gdzie"] == "superbet" and r[0.5]["lepszy"] == 2.60


def test_zgodna_drabinka_nie_jest_uznana_za_przesunieta():
    """Drabinka, która i tak się zgadza, nie ma prawa wpaść w test
    przesunięcia — inaczej wycięlibyśmy zdrowe porównania."""
    sb = {0.5: {"over": 1.50}, 1.5: {"over": 2.50}, 2.5: {"over": 4.00}}
    bc = {0.5: {"over": 1.55}, 1.5: {"over": 2.45}, 2.5: {"over": 4.10}}
    assert betclic._drabinka_przesunieta(sb, bc, 4.0) is False
    assert len(betclic.porownaj_drabinke(sb, bc)) == 3


def test_obie_wersje_zle_to_nie_dowod_przesuniecia():
    """Gdy po przesunięciu też jest źle, to nie przesunięcie — takie
    drabinki odrzuca zwykły próg zgody, z własnym powodem w liczniku."""
    sb = {0.5: {"over": 1.50}, 1.5: {"over": 2.50}, 2.5: {"over": 4.00}}
    bc = {0.5: {"over": 5.00}, 1.5: {"over": 9.00}, 2.5: {"over": 14.0}}
    mediana, _ = betclic._mediana_rozjazdu(sb, bc)
    assert betclic._drabinka_przesunieta(sb, bc, mediana) is False
    assert betclic.porownaj_drabinke(sb, bc) == {}


# ---------------------------------------------------------------------------
# Parowanie zawodnika: literówka w nazwisku (2026-08-08)
# ---------------------------------------------------------------------------

def _bc_gracze(*klucze):
    return {k: {"shots": {1.5: {"over": 2.0}}} for k in klucze}


def test_literowka_w_nazwisku_nie_gubi_zawodnika():
    """⚑ Zmierzone na 33 meczach: 91 z 779 naszych zawodników nie dostawało
    pary u Betclica, a 42 z tego miały część nazwiska wspólną. Wśród nich
    siedziały zwykłe literówki jednego znaku — a kurs bez pary nie wchodzi
    do siatki, więc karta na takiego zawodnika nie ma prawa powstać."""
    assert betclic.znajdz_zawodnika(_bc_gracze("ralf seuntjes"),
                                    "Ralf Seuntjens")
    assert betclic.znajdz_zawodnika(_bc_gracze("niang ousseynou"),
                                    "Ousseyynou Niang")


def test_dwaj_rozni_ludzie_ze_wspolnym_imieniem_dalej_nie_paruja():
    """Druga połowa tamtych 42 to NIE literówki, tylko różni zawodnicy
    dzielący imię. Rozluźnienie parowania nie ma prawa ich skleić — kurs
    trafiłby wtedy do kartoteki obcego człowieka."""
    assert not betclic.znajdz_zawodnika(_bc_gracze("rodrigo zalazar"),
                                        "Rodrigo Pinho")
    assert not betclic.znajdz_zawodnika(_bc_gracze("lucas martinez quarta"),
                                        "Lucas Beltran")
    assert not betclic.znajdz_zawodnika(_bc_gracze("gonzalez santiago"),
                                        "Santiago Lencina")
    assert not betclic.znajdz_zawodnika(_bc_gracze("da luan silva"),
                                        "Luan Santos")


def test_dwoch_kandydatow_to_dalej_brak_dopasowania():
    """Jednoznaczność obowiązuje na każdej ścieżce — imiennicy istnieją."""
    assert not betclic.znajdz_zawodnika(
        _bc_gracze("paula paulinho", "filho paulinho"), "Paulinho")


def test_dwie_literowki_to_juz_inne_nazwisko():
    """Budżet jest JEDEN znak na całe nazwisko, nie na token."""
    assert not betclic.znajdz_zawodnika(_bc_gracze("rolf seuntjes"),
                                        "Ralf Seuntjens")


def test_odleglosc_do_jeden_zna_trzy_rodzaje_pomylki():
    f = betclic._odleglosc_do_jeden
    assert f("kowalski", "kowalski")      # bez zmian
    assert f("kowalski", "kowalsky")      # podmiana
    assert f("seuntjens", "seuntjes")     # usunięcie
    assert f("ousseynou", "ousseyynou")   # wstawienie
    assert not f("pinho", "zalazar")
    assert not f("kowalski", "kowaski1")  # dwie operacje
