"""Wiarygodność cen Betclica (2026-10-05).

Karta Oguza Aydina (Italy–Türkiye 05.10) pokazała strzały 0,5 @2,05 i 1,5 @6,0
„u Betclica" — to były kursy rynku „1. połowa". Za cały mecz: Betclic 1,42 /
2,90, Superbet 1,13 / 1,70. Druga usterka tego samego dnia: dwaj „Juan
Quintero" w Medellín–Santa Fe i jedna, zlana drabinka (0,5 @3,0, 1,5 @12,
3,5 @1,55). Testy pilnują obu bram: odczytu oferty i scalania cenników.
"""
from footstats.jobs import build_wc_fast as bwf
from footstats.sources import betclic


# Superbet i Betclic z 04/05.10 dla Aydina (strzały)
SB_AYDIN = {0.5: {"over": 1.13}, 1.5: {"over": 1.70}, 2.5: {"over": 3.15},
            3.5: {"over": 5.9}, 4.5: {"over": 12.0}, 5.5: {"over": 25.0}}
BC_POLOWA = {"0.5": {"over": 2.05}, "1.5": {"over": 6.0}}


# --------------------------------------------------------- brama scalania ---

def test_drabinka_z_innej_statystyki_nie_wchodzi_do_cennika():
    dobre, powod = betclic.linie_do_scalenia(SB_AYDIN, BC_POLOWA)
    assert dobre == {} and powod == "drabinka_niezgodna"


def test_scalanie_zostawia_ceny_superbetu_przy_niezgodnej_drabince():
    out = bwf._scal_oferty_zawodnika({"shots": SB_AYDIN}, {"shots": BC_POLOWA})
    assert out["shots"][0.5]["over"] == 1.13
    assert out["shots"][1.5]["over"] == 1.70
    # i karta nie podpisze tej ceny Betclikiem
    assert bwf.zrodla_kursow({"shots": SB_AYDIN}, {"shots": BC_POLOWA}) == {}


def test_zgodna_drabinka_dalej_daje_wyzszy_kurs_betclica():
    """Ten sam rynek, Betclic płaci trochę więcej — decyzja 08.08 zostaje."""
    sb = {0.5: {"over": 1.20}, 1.5: {"over": 1.80}, 2.5: {"over": 3.20}}
    bc = {0.5: {"over": 1.25}, 1.5: {"over": 1.95}, 2.5: {"over": 3.40}}
    out = bwf._scal_oferty_zawodnika({"sot": sb}, {"sot": bc})
    assert out["sot"][1.5]["over"] == 1.95
    assert bwf.zrodla_kursow({"sot": sb}, {"sot": bc})["sot"]["1.5"] == "Betclic"


def test_pewniak_taniej_przy_zgodnej_reszcie_drabinki_przechodzi():
    """1,25 u Superbetu, 2,00 u Betclica, reszta drabinki zgodna — okazja,
    nie błąd (najcenniejszy układ wg właściciela)."""
    sb = {0.5: {"over": 1.25}, 1.5: {"over": 2.40}, 2.5: {"over": 4.50},
          3.5: {"over": 8.00}}
    bc = {0.5: {"over": 2.00}, 1.5: {"over": 2.50}, 2.5: {"over": 4.60},
          3.5: {"over": 8.20}}
    dobre, powod = betclic.linie_do_scalenia(sb, bc)
    assert powod is None and dobre[0.5]["over"] == 2.00


def test_jedna_wspolna_linia_nie_moze_odjezdzac_daleko():
    sb = {0.5: {"over": 1.13}}
    assert betclic.linie_do_scalenia(sb, {0.5: {"over": 1.30}})[1] is None
    assert betclic.linie_do_scalenia(sb, {0.5: {"over": 2.05}})[1] == "jedna_wspolna_za_daleko"


def test_rynek_tylko_u_betclica_wchodzi_jesli_jest_spojny():
    bc = {0.5: {"over": 1.30}, 1.5: {"over": 2.40}}
    assert betclic.linie_do_scalenia({}, bc) == (bc, None)
    zlany = {0.5: {"over": 3.0}, 1.5: {"over": 12.0}, 3.5: {"over": 1.55}}
    assert betclic.linie_do_scalenia({}, zlany) == ({}, "niemonotoniczna")


def test_scalenie_nie_moze_odwrocic_kolejnosci_kursow():
    """Bez wspólnych linii, ale po scaleniu 1,5 płaciłoby więcej niż 2,5."""
    sb = {2.5: {"over": 3.15}, 3.5: {"over": 5.9}}
    bc = {1.5: {"over": 6.0}}
    assert betclic.linie_do_scalenia(sb, bc) == ({}, "niemonotoniczna")


def test_brama_nie_rusza_wejscia_i_liczy_tylko_na_zyczenie():
    przed = dict(betclic.ODRZUCONE_SCALENIA)
    bc = {"0.5": {"over": 2.05}, "1.5": {"over": 6.0}}
    betclic.linie_do_scalenia(SB_AYDIN, bc)
    assert betclic.ODRZUCONE_SCALENIA == przed
    betclic.linie_do_scalenia(SB_AYDIN, bc, licz=True)
    assert betclic.ODRZUCONE_SCALENIA["drabinka_niezgodna"] == przed["drabinka_niezgodna"] + 1
    assert bc == {"0.5": {"over": 2.05}, "1.5": {"over": 6.0}}
    assert "odrzucone rynki Betclica" in betclic.raport_scalen()


def test_smieciowe_kursy_nie_wywalaja_bramy():
    sb = {0.5: {"over": None}, "x": {"over": 1.5}}
    bc = {0.5: {"over": "—"}, 1.5: {"over": 2.1}}
    dobre, _ = betclic.linie_do_scalenia(sb, bc)
    assert 1.5 in dobre


# ------------------------------------------------------------ odczyt oferty ---

def _oferta(rynki):
    return {"id": 1, "nazwa": "A - B", "kickoff_ts": 1, "gospodarz": "A",
            "gosc": "B", "druzyny": [], "rynki": rynki}


def _zaklad(osoba, linia, kurs, sciezka=None):
    return {"nazwa": f"Powyżej {str(linia).replace('.', ',')}", "kurs": kurs,
            "gracze": [], "podmiot": osoba,
            "sciezka": sciezka if sciezka is not None else f"/{osoba}[{linia}]"}


def _rynek(nazwa, zaklady):
    return {"nazwa": nazwa, "kategoria": "Statystyki", "podkategoria": "Strzały",
            "zaklady": zaklady}


def test_polowa_w_nazwie_rynku_w_kazdej_odmianie_odpada(monkeypatch):
    monkeypatch.setattr(betclic, "oferta_pelna", lambda i, tylko_statystyki=True: _oferta([
        _rynek("Liczba strzałów zawodnika (OPTA)", [_zaklad("Oguz Aydin", 0.5, 1.42)]),
        _rynek("Liczba strzałów zawodnika (OPTA) - 1. połowa", [_zaklad("Oguz Aydin", 0.5, 2.05)]),
        _rynek("Liczba strzałów zawodnika w 1. połowie", [_zaklad("Oguz Aydin", 1.5, 6.0)]),
        _rynek("Liczba strzałów zawodnika (OPTA) - 2. poł.", [_zaklad("Oguz Aydin", 2.5, 9.0)]),
    ]))
    k = betclic.kursy_zawodnikow(1)
    assert k["players"]["aydin oguz"]["shots"] == {0.5: {"over": 1.42}}


def test_zakladka_polowa_pod_nazwa_zwyklego_rynku_odpada(monkeypatch):
    """Widżet z zakładkami „Mecz" / „1. połowa" pod jedną nazwą rynku."""
    monkeypatch.setattr(betclic, "oferta_pelna", lambda i, tylko_statystyki=True: _oferta([
        _rynek("Liczba strzałów zawodnika (OPTA)", [
            _zaklad("Oguz Aydin", 0.5, 1.42, "/Mecz/Oguz Aydin[0.5]"),
            _zaklad("Oguz Aydin", 0.5, 2.05, "/1. połowa/Oguz Aydin[0.5]"),
            _zaklad("Oguz Aydin", 1.5, 6.0, "/1. połowa/Oguz Aydin[1.5]"),
        ]),
    ]))
    k = betclic.kursy_zawodnikow(1)
    assert k["players"]["aydin oguz"]["shots"] == {0.5: {"over": 1.42}}
    assert k["pominiete_czesc_meczu"] == 2


def test_nazwisko_w_sciezce_nie_jest_mylone_z_rynkiem(monkeypatch):
    """Lista ODRZUCANE_WZORCE ma „podań" — w ścieżce byłoby to nazwisko
    „Podański", dlatego ścieżka ma osobną, wąską listę."""
    monkeypatch.setattr(betclic, "oferta_pelna", lambda i, tylko_statystyki=True: _oferta([
        _rynek("Liczba strzałów zawodnika (OPTA)", [_zaklad("Jan Podański", 0.5, 1.5)]),
    ]))
    k = betclic.kursy_zawodnikow(1)
    assert k["players"]["jan podanski"]["shots"][0.5]["over"] == 1.5


def test_dwie_rozne_ceny_jednej_linii_to_brak_rynku(monkeypatch):
    """Dwaj „Juan Quintero" (Medellín–Santa Fe 05.10): jedna nazwa, dwie
    drabinki. Nie wiadomo, która cena jest czyja — rynek odpada."""
    monkeypatch.setattr(betclic, "oferta_pelna", lambda i, tylko_statystyki=True: _oferta([
        _rynek("Liczba celnych strzałów zawodnika (OPTA)", [
            _zaklad("Juan Quintero", 0.5, 1.30), _zaklad("Juan Quintero", 0.5, 11.0),
            _zaklad("Juan Quintero", 1.5, 2.50),
        ]),
        _rynek("Liczba strzałów zawodnika (OPTA)", [
            _zaklad("Juan Quintero", 3.5, 1.55), _zaklad("Juan Quintero", 4.5, 2.2),
            _zaklad("Juan Quintero", 0.5, 3.0), _zaklad("Juan Quintero", 1.5, 12.0),
        ]),
        _rynek("Liczba fauli zawodnika (OPTA)", [_zaklad("Inny Gracz", 0.5, 1.4)]),
    ]))
    k = betclic.kursy_zawodnikow(1)
    assert "juan quintero" not in k["players"]
    assert k["konflikty_cen"] == 1 and k["niespojne_drabinki"] == 1
    assert k["players"]["gracz inny"]["fouls_committed"][0.5]["over"] == 1.4


def test_ten_sam_rynek_z_dwoch_kategorii_to_nie_konflikt(monkeypatch):
    monkeypatch.setattr(betclic, "oferta_pelna", lambda i, tylko_statystyki=True: _oferta([
        _rynek("Liczba strzałów zawodnika (OPTA)", [_zaklad("Oguz Aydin", 0.5, 1.42)]),
        {**_rynek("Liczba strzałów zawodnika (OPTA)", [_zaklad("Oguz Aydin", 0.5, 1.42)]),
         "kategoria": "Strzelcy"},
    ]))
    k = betclic.kursy_zawodnikow(1)
    assert k["konflikty_cen"] == 0
    assert k["players"]["aydin oguz"]["shots"][0.5]["over"] == 1.42
