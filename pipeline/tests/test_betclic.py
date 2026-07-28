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
