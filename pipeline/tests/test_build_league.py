"""Testy parownika statshub↔Superbet dla klubów (build_league, etap 1).

Pary nazw wzięte z ŻYWEGO raportu pokrycia 2026-07-20 — to realne rozjazdy
nazewnictwa między źródłami, nie wymyślone przykłady.
"""

import pytest

from footstats.jobs import build_league as bl


# --- normalizacja nazw klubów ---

def test_norm_klub_zrzuca_ozdobniki_i_diakrytyki():
    assert bl.norm_klub("IFK Göteborg") == bl.norm_klub("Goteborg IFK")
    assert bl.norm_klub("FC København") == "kobenhavn"


def test_norm_klub_nazwa_z_samych_ozdobnikow_zostaje():
    """AIK: wszystkie tokeny to 'śmieci' — nazwa nie może wyjść pusta."""
    assert bl.norm_klub("AIK") == "aik"


# --- podobieństwo (żywe pary z raportu 2026-07-20) ---

@pytest.mark.parametrize("statshub_nazwa,superbet_nazwa", [
    ("Atlético Mineiro", "Atletico MG"),          # alias
    ("América Mineiro", "America MG"),            # alias
    ("Djurgårdens IF", "Djurgarden IF"),          # prefiks (odmiana -s)
    ("FCI Levadia Tallinn", "Levadia Tallinn"),   # nadzbiór tokenów
    ("Örgryte IS", "Orgryte"),                    # diakrytyki + ozdobnik
    ("AGF Aarhus", "AGF Aarhus"),                 # wprost
])
def test_podobienstwo_zywe_pary_pasuja(statshub_nazwa, superbet_nazwa):
    assert bl.podobienstwo_klubu(statshub_nazwa, superbet_nazwa) >= 0.99


# Żywe pary z 2026-08-03: sześć kwalifikacji pucharów, których model NIE widział,
# bo Superbet pisze nazwy po polsku albo skraca. Każda dawała dokładnie 0,50
# przy progu 0,51 — jedna strona idealnie, druga wcale.
@pytest.mark.parametrize("statshub_nazwa,superbet_nazwa,dlaczego", [
    ("AC Sparta Praha", "Sparta Praga", "polska nazwa miasta"),
    ("Olympique Lyonnais", "Olympique Lyon", "krótszy wariant (4 znaki)"),
    ("FC Nordsjælland", "Nordsjalland", "uproszczony zapis"),
    ("Debreceni VSC", "Debreczyn VSC", "polska nazwa miasta"),
    ("FC København", "FC Kopenhaga", "polska nazwa miasta"),
    ("RFS", "Riga FS", "skrót vs rozwinięcie"),
    ("DAC 1904", "Dunajska Streda", "skrót vs miasto"),
])
def test_podobienstwo_polskie_nazwy_bukmachera(statshub_nazwa, superbet_nazwa,
                                               dlaczego):
    assert bl.podobienstwo_klubu(statshub_nazwa, superbet_nazwa) >= 0.99, dlaczego


@pytest.mark.parametrize("a,b", [
    ("Valencia CF", "Palencia"),            # 0,88 zgodności znaków, inne miasto
    ("Sporting CP", "Sportivo Luqueño"),
    ("Lech Poznań", "Lechia Gdańsk"),
    ("Atlético Madrid", "Atlético Mineiro"),
    ("Nacional Potosí", "Nacional Montevideo"),
])
def test_wariant_zapisu_nie_skleja_roznych_klubow(a, b):
    """Reguła „wariant zapisu" ma łapać spolszczenia, nie podobne nazwy.
    Warunek na dwie pierwsze litery jest tu jedynym bezpiecznikiem."""
    assert bl.podobienstwo_klubu(a, b) < bl.PROG_PODOBIENSTWA


def test_rocznik_zalozenia_zostaje_czescia_nazwy():
    """Sprawdzone i odrzucone 03.08: wycięcie rocznika jak ozdobnika zabiera
    połowę tożsamości klubom, które mają go w nazwie."""
    assert "1860" in bl.norm_klub("TSV 1860 München")
    # dłuższa strona z rocznikiem i tak nie szkodzi — dzielimy przez krótszą
    assert bl.podobienstwo_klubu("FC St. Gallen 1879", "St. Gallen") >= 0.99


def test_podobienstwo_rozne_kluby_nie_pasuja():
    assert bl.podobienstwo_klubu("Real Madryt", "Betis") == 0.0
    # wspólne "Atletico" nie skleja różnych klubów powyżej progu pary
    assert bl.podobienstwo_klubu("Atlético Madrid", "Atletico Mineiro") \
        < bl.PROG_PODOBIENSTWA
    # krótkie skróty nie łapią się prefiksem ('mg' vs 'mineiro' — od tego aliasy)
    assert not bl._tokeny_pasuja("mg", "mineiro")


# --- kickoff Superbetu ---

def test_sb_kickoff_bierze_unixdatemillis_nie_matchtimestamp():
    """matchTimestamp = czas aktualizacji oferty (pułapka zmierzona
    2026-07-20), kickoff siedzi w unixDateMillis."""
    ev = {"unixDateMillis": 1784673000000, "matchTimestamp": 1784504936670}
    assert bl._sb_kickoff(ev) == 1784673000


# --- parowanie ---

def _mecz(eid, home, away, ts):
    return bl.MeczLigowy(
        event_id=eid, utid=390, rozgrywki_nazwa="Brasileirão Série B",
        kraj="Brazylia", home_id=1, away_id=2, home=home, away=away,
        kickoff_ts=ts, has_odd=True, druzynowe=False,
    )


def _sb(eid, name, ts):
    return {"eventId": eid, "matchName": name, "unixDateMillis": ts * 1000}


def test_paruj_bramkuje_czasem():
    """Te same drużyny grają w lidze wielokrotnie — okno ±3 h musi wybrać
    właściwy termin, a mecz poza oknem zostawić bez pary."""
    m = _mecz(1, "Avaí", "América Mineiro", 1_784_673_000)
    dobry = _sb(101, "Avai·America MG", 1_784_673_000)
    inny_termin = _sb(102, "Avai·America MG", 1_784_673_000 + 14 * 86400)
    n, luka = bl.paruj_superbet([m], [inny_termin, dobry])
    assert n == 1
    assert m.sb_event["eventId"] == 101
    assert luka == [inny_termin]


def test_paruj_kazdy_event_najwyzej_raz():
    m1 = _mecz(1, "Avaí", "América Mineiro", 1_784_673_000)
    m2 = _mecz(2, "Avaí", "América Mineiro", 1_784_673_000)
    sb = [_sb(101, "Avai·America MG", 1_784_673_000)]
    n, _ = bl.paruj_superbet([m1, m2], sb)
    assert n == 1
    assert (m1.sb_event is None) != (m2.sb_event is None)


def test_paruj_odrzuca_slabe_podobienstwo():
    m = _mecz(1, "Nacional Potosí", "Real Oruro", 1_784_673_000)
    sb = [_sb(101, "Nacional Montevideo·CA Tigre", 1_784_673_000)]
    n, luka = bl.paruj_superbet([m], sb)
    assert n == 0 and m.sb_event is None and len(luka) == 1


def _mecz_druzynowy(eid, home, away, ts):
    m = _mecz(eid, home, away, ts)
    m.druzynowe = True
    return m


def test_raport_lapie_rozjazd_obu_nazw_naraz():
    """NAJWAŻNIEJSZY przypadek raportu, i ten, którego reguła oparta na
    podobieństwie by nie złapała: bukmacher spolszcza OBIE nazwy, więc
    podobieństwo wynosi 0,00. Zbieżna godzina jest jedynym dowodem, że to ten
    sam mecz (żywy przypadek 06.08: Debreceni VSC – FC København)."""
    m = _mecz_druzynowy(1, "Debreceni VSC", "FC København", 1_784_673_000)
    sb = [_sb(101, "Debreczyn·FC Kopenhaskie", 1_784_673_000)]
    prawie: list[dict] = []
    n, _luka = bl.paruj_superbet([m], sb, prawie=prawie)
    assert n == 0
    assert len(prawie) == 1
    assert prawie[0]["statshub"] == "Debreceni VSC - FC København"
    assert prawie[0]["superbet"] == "Debreczyn - FC Kopenhaskie"


def test_raport_pomija_mecze_ktore_sie_sparowaly():
    """Mecz sparowany z właściwym eventem nie jest problemem do zgłoszenia,
    nawet jeśli po drodze otarł się o słabszego kandydata."""
    m = _mecz(1, "Avaí", "América Mineiro", 1_784_673_000)
    sb = [_sb(101, "Avai·America MG", 1_784_673_000),
          _sb(102, "Avai·Atletico MG", 1_784_673_000)]
    prawie: list[dict] = []
    n, _luka = bl.paruj_superbet([m], sb, prawie=prawie)
    assert n == 1 and prawie == []


def test_raport_nie_zbiera_meczow_z_innej_godziny():
    """Bez bramki czasu raport zgłaszałby każdy niesparowany mecz przeciwko
    każdej niesparowanej ofercie — czyli nie zgłaszałby nic użytecznego."""
    m = _mecz_druzynowy(1, "Avaí", "Coritiba", 1_784_673_000)
    sb = [_sb(101, "Flamengo·Palmeiras", 1_784_673_000 + 3600)]
    prawie: list[dict] = []
    bl.paruj_superbet([m], sb, prawie=prawie)
    assert prawie == []


def test_raport_milczy_poza_zakresem_druzynowym():
    """Pierwszy żywy przebieg raportu: 28 z 30 wierszy to mecze, których
    bukmacher w ogóle nie kwotuje (puchar Rosji, Liga Mistrzyń), sparowane
    z przypadkową ofertą z tej samej minuty. Raport, który tonie w szumie,
    nie zostanie przeczytany."""
    poza = _mecz(1, "Rodina Moscow", "Rubin Kazan", 1_784_673_000)
    w_zakresie = _mecz_druzynowy(2, "Debreceni VSC", "FC København",
                                 1_784_673_000)
    sb = [_sb(101, "Montana·PFC Nesebar", 1_784_673_000),
          _sb(102, "Debreczyn·FC Kopenhaskie", 1_784_673_000)]
    prawie: list[dict] = []
    bl.paruj_superbet([poza, w_zakresie], sb, prawie=prawie)
    # o meczu spoza zakresu drużynowego raport nie mówi ani słowa
    assert {p["statshub"] for p in prawie} == {"Debreceni VSC - FC København"}
    # a właściwy kandydat stoi pierwszy — kolejne to podpowiedzi z tej minuty
    assert prawie[0]["superbet"] == "Debreczyn - FC Kopenhaskie"


# --- dopasowanie zawodników do kluczy kursów Superbetu ---

def test_znajdz_zawodnika_pelne_vs_boiskowe():
    """Superbet w klubach kwotuje pod PEŁNYM nazwiskiem, statshub daje
    boiskowe (żywy przypadek 2026-07-20: Renan Lodi / Ademir, Brasileirão)."""
    from footstats.sources.superbet import znajdz_zawodnika
    players = {
        "augusto dos lodi renan santos": {"shots": {0.5: {"over": 1.5}}},
        "ademir da junior santos silva": {"shots": {0.5: {"over": 1.8}}},
        "da jose silva willian": {"shots": {}},
        "jose silva willian": {"shots": {}},
    }
    assert znajdz_zawodnika(players, "Renan Lodi") \
        == players["augusto dos lodi renan santos"]
    assert znajdz_zawodnika(players, "Ademir") \
        == players["ademir da junior santos silva"]
    # dwóch kandydatów (Willian) = niejednoznaczne = brak dopasowania
    assert znajdz_zawodnika(players, "Willian") == {}
    # dokładny klucz ma pierwszeństwo i działa jak dotąd (tryb MŚ)
    assert znajdz_zawodnika({"kane harry": {"sot": {}}}, "Harry Kane") \
        == {"sot": {}}
