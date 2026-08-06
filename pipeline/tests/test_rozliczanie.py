"""Testy kalibracji z rozliczonych typów + cyklu życia kuponów (bez sieci)."""

import time

from footstats.jobs import rozliczanie
from footstats.model import kupony as kupony_model
from footstats.sources import scores365


def _rec(mk, p, wynik):
    return {"rynek_kod": mk, "p_model": p, "wynik": wynik}


def test_bias_needs_min_sample():
    log = {str(i): _rec("shots", 0.7, "wygrany") for i in range(10)}
    assert rozliczanie.compute_bias(log, min_n=25) == {}


def test_bias_detects_overconfidence():
    # model mówił 80%, wchodziło 60% -> bias < 1 (przeszacowanie)
    log = {}
    for i in range(30):
        log[str(i)] = _rec("shots", 0.8, "wygrany" if i < 18 else "przegrany")
    bias = rozliczanie.compute_bias(log, min_n=25)["shots"]
    assert bias < 1.0
    assert bias >= rozliczanie.BIAS_CAP[0]


def test_bias_capped_and_ignores_voids():
    log = {}
    for i in range(40):
        log[str(i)] = _rec("fouls_won", 0.5, "wygrany")  # 100% trafień przy p=50%
    log["void"] = _rec("fouls_won", 0.5, "zwrot")  # zwroty nie liczą się do próby
    bias = rozliczanie.compute_bias(log, min_n=25)["fouls_won"]
    assert bias == rozliczanie.BIAS_CAP[1]  # capowane, mimo że surowo ~1.9


def _rec_s(mk, p, wynik, sugestia=False):
    return {"rynek_kod": mk, "p_model": p, "wynik": wynik, "sugestia": sugestia}


def test_bias_sugestii_liczony_osobno():
    log = {}
    # typy z kursem: dobrze skalibrowane (70% traf przy p=0.7)
    for i in range(30):
        log[f"t{i}"] = _rec_s("shots", 0.7, "wygrany" if i < 21 else "przegrany")
    # sugestie STS: fatalne (17% traf przy p=0.6) — nie mogą psuć typów
    for i in range(30):
        log[f"s{i}"] = _rec_s(
            "shots_off_target", 0.6, "wygrany" if i < 5 else "przegrany",
            sugestia=True,
        )
    typy = rozliczanie.compute_bias_full(log)
    assert "shots_off_target" not in typy          # sugestie odfiltrowane
    assert abs(typy["shots"]["global"]) < 0.10     # dobrze skalibrowane ~0
    sug = rozliczanie.compute_bias_full(
        log, sugestie=True, cap=rozliczanie.SUGESTIA_BIAS_CAP_LOGIT
    )
    assert "shots" not in sug                      # typy odfiltrowane
    # surowa delta ~-1.9, ale cap sugestii pozwala zejść niżej niż typom
    assert sug["shots_off_target"]["global"] == rozliczanie.SUGESTIA_BIAS_CAP_LOGIT[0]


# ---- cykl życia kuponów w logu ----

def _leg(mecz_id, podmiot_id, kickoff=10_000, kurs=2.0):
    return {
        "value_bet_id": 0, "podmiot_id": podmiot_id, "podmiot": f"P{podmiot_id}",
        "rynek_kod": "shots", "rynek": "Strzały", "linia": 1.5,
        "strona": "powyzej", "kurs": kurs, "bukmacher": "Superbet",
        "p_model": 0.6, "pewnosc": "wysoka", "mecz": f"A{mecz_id} – B{mecz_id}",
        "mecz_id": mecz_id, "kickoff_ts": kickoff,
    }


# przedział z AKTUALNEJ konfiguracji — testy zamrażania kuponu sprawdzają
# zachowanie slotu, a slot istnieje tylko dla przedziałów, które naprawdę
# są w `PRZEDZIALY_DZIENNE`. Po przebudowie 2026-07-30 (4 przedziały -> 2)
# stara etykieta „5–10" przestała być slotem i testy mierzyły co innego,
# niż deklarowały. Bierzemy pierwszy dzienny przedział z konfiguracji,
# żeby ta pułapka nie wróciła przy kolejnej zmianie progów.
_CEL_DZIENNY = kupony_model.etykieta_celu(*kupony_model.PRZEDZIALY_DZIENNE[0])


def _kupon(cel_label=_CEL_DZIENNY, horyzont="dzienny", legi=None):
    legi = legi or [
        _leg(1, 11, kickoff=10_000),
        _leg(2, 22, kickoff=12_000),
        _leg(3, 33, kickoff=14_000),
    ]
    return {
        "cel": 5, "cel_label": cel_label, "styl": "pewniaki",
        "horyzont": horyzont, "kurs_laczny": 7.5, "p_model": 0.3,
        "fair_kurs": 3.33, "ev_pct": 10.0, "legi": legi,
    }


def test_kupon_leg_niesie_flagi_do_typy_log():
    # P0: legi trafiające do typy_log WYŁĄCZNIE przez kupon (żaden value_bet
    # ich nie publikuje osobno) muszą przenosić miekka_linia/xi_sygnal/
    # kurs_ref/wyzsza_linia — inaczej diagnostyka per kategoria ma ślepą plamę
    # na większości puli (patrz kupony.py:_leg_dict + rozliczanie.py:rozlicz).
    leg = _leg(1, 11)
    leg.update(
        miekka_linia=True, xi_sygnal="official", kurs_ref=2.05,
        wyzsza_linia=True, matchup=True, rotacja=False,
    )
    log: dict = {}
    rozliczanie._dopisz_nowe(log, [rozliczanie._kupon_leg_do_logu(leg)])
    assert len(log) == 1
    rec = next(iter(log.values()))
    assert rec["miekka_linia"] is True
    assert rec["xi_sygnal"] == "official"
    assert rec["kurs_ref"] == 2.05
    assert rec["wyzsza_linia"] is True
    assert rec["matchup"] is True


def test_kupon_zamrozony_po_publikacji():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000)
    assert len(log) == 1
    rec = next(iter(log.values()))
    # kolejny cykl z INNYM kuponem w tym samym slocie — rekord bez zmian
    inny = _kupon(legi=[_leg(4, 44), _leg(5, 55), _leg(6, 66)])
    rozliczanie._kupon_do_logu(log, [inny], now=2_000)
    assert len(log) == 1
    assert [l["podmiot_id"] for l in rec["legi"]] == [11, 22, 33]
    assert rec["opublikowano_ts"] == 1_000


def test_zmiana_skladu_anuluje_i_tworzy_nowy():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000)
    # zawodnik 22 wypada ze składu przed meczem -> anulowanie + nowy kupon
    nowy = _kupon(legi=[_leg(1, 11), _leg(2, 25), _leg(3, 33)])
    rozliczanie._kupon_do_logu(log, [nowy], now=2_000, niedostepni={22})
    stare = [r for r in log.values() if r["wynik"] == "anulowany"]
    aktywne = [r for r in log.values() if r["wynik"] is None]
    assert len(stare) == 1 and "P22" in stare[0]["powod"]
    assert len(aktywne) == 1
    assert [l["podmiot_id"] for l in aktywne[0]["legi"]] == [11, 25, 33]


def test_nowy_kupon_po_przegranym():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000)
    next(iter(log.values())).update(wynik="przegrany")
    rozliczanie._kupon_do_logu(log, [_kupon()], now=2_000)
    assert len(log) == 2  # klucze unikalne mimo tego samego dnia
    assert sum(1 for r in log.values() if r["wynik"] is None) == 1


def test_brak_publikacji_gdy_mecz_juz_trwa():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=11_000)  # 1. mecz wystartował
    assert log == {}


def test_brak_publikacji_gdy_leg_poza_skladem():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000, niedostepni={11})
    assert log == {}


def test_rozliczenie_kuponu_z_legow():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000)
    typy_log = {
        "1:p11:shots:1.5:powyzej": {"wynik": "wygrany"},
        "2:p22:shots:1.5:powyzej": {"wynik": "zwrot"},
        "3:p33:shots:1.5:powyzej": {"wynik": "wygrany"},
    }
    hist = rozliczanie._rozlicz_kupony(log, typy_log, now=50_000)
    assert hist[0]["wynik"] == "wygrany"
    assert hist[0]["kurs_rozliczony"] == 4.0  # zwrot wyłącza lega z kursu


def test_kupon_z_samych_zwrotow_to_zwrot():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000)
    typy_log = {
        "1:p11:shots:1.5:powyzej": {"wynik": "zwrot"},
        "2:p22:shots:1.5:powyzej": {"wynik": "zwrot"},
        "3:p33:shots:1.5:powyzej": {"wynik": "zwrot"},
    }
    hist = rozliczanie._rozlicz_kupony(log, typy_log, now=50_000)
    assert hist[0]["wynik"] == "zwrot"          # stawka wraca, nie "wygrany"
    assert hist[0]["kurs_rozliczony"] == 1.0


def test_przegrany_od_pierwszego_pudla():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000)
    typy_log = {"1:p11:shots:1.5:powyzej": {"wynik": "przegrany"}}
    hist = rozliczanie._rozlicz_kupony(log, typy_log, now=50_000)
    assert hist[0]["wynik"] == "przegrany"


def test_pominiety_kupon_zwalnia_slot_ale_rozlicza_sie_w_tle():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000)
    klucz = next(iter(log))
    # user klika "pomiń" — slot wolny, ale wynik pusty (rozliczanie w tle)
    rozliczanie._kupon_do_logu(log, [_kupon()], now=2_000, pominiete={klucz})
    rec = log[klucz]
    assert rec["pominiety"] is True
    assert rec["wynik"] is None
    # identyczny zestaw legów NIE wraca do zwolnionego slotu
    assert len(log) == 1
    # inny zestaw legów — wchodzi normalnie
    inny = _kupon(legi=[_leg(4, 44), _leg(5, 55), _leg(6, 66)])
    rozliczanie._kupon_do_logu(log, [inny], now=3_000, pominiete={klucz})
    assert len(log) == 2
    # pominięty kupon rozlicza się z legów jak każdy inny
    typy_log = {"1:p11:shots:1.5:powyzej": {"wynik": "przegrany"}}
    rozliczanie._rozlicz_kupony(log, typy_log, now=50_000)
    assert log[klucz]["wynik"] == "przegrany"


def test_pominiety_blokuje_tez_prawie_identyczny_zestaw():
    log = {}
    legi7 = [_leg(i, 10 + i, kickoff=100_000 + i) for i in range(7)]
    rozliczanie._kupon_do_logu(log, [_kupon(legi=legi7)], now=1_000)
    klucz = next(iter(log))
    # 7 legów z JEDNĄ zamianą (Jaccard 6/8 = 0.75) — nie wraca do slotu
    podobne = legi7[:6] + [_leg(9, 99, kickoff=100_009)]
    rozliczanie._kupon_do_logu(
        log, [_kupon(legi=podobne)], now=2_000, pominiete={klucz}
    )
    assert len(log) == 1
    # wyraźnie inny zestaw (3 wspólne z 7) — wchodzi normalnie
    inne = legi7[:3] + [_leg(20 + i, 200 + i, kickoff=100_020 + i) for i in range(4)]
    rozliczanie._kupon_do_logu(
        log, [_kupon(legi=inne)], now=3_000, pominiete={klucz}
    )
    assert len(log) == 2


def test_wymiana_lega_publikuje_wariant_w_slocie():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000)
    klucz = next(iter(log))
    rec = log[klucz]
    rec["alternatywa"] = {
        **_leg(3, 99, kickoff=14_000, kurs=2.5),
        "zamiast_idx": 2, "kurs_po": 10.0, "p_po": 0.35,
    }
    rozliczanie._kupon_do_logu(log, [], now=2_000, wymiany={klucz})
    assert rec["pominiety"] is True
    assert rec["pomin_powod"] == "wymiana lega"
    nowe = [r for r in log.values() if r.get("z_wymiany")]
    assert len(nowe) == 1
    n = nowe[0]
    assert n["slot"] == rec["slot"] and n["wynik"] is None
    assert n["kurs_laczny"] == 10.0 and n["p_model"] == 0.35
    assert {l["podmiot_id"] for l in n["legi"]} == {11, 22, 99}


def test_przywrocenie_pominietego_gdy_slot_wolny():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000)
    klucz = next(iter(log))
    rozliczanie._kupon_do_logu(log, [], now=2_000, pominiete={klucz})
    assert log[klucz]["pominiety"] is True
    # klucz znika z pominiętych (user kliknął "przywróć") -> kupon wraca
    rozliczanie._kupon_do_logu(log, [], now=3_000, pominiete=set())
    assert log[klucz]["pominiety"] is False


def test_stary_przedzial_schodzi_z_widoku_jak_pominiety():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon(cel_label="12–25")], now=1_000)
    # przedziału 12–25 nie ma już w konfiguracji — kolejny cykl chowa kupon
    # (rozliczy się w tle), a aktualne przedziały mają wolne sloty
    rozliczanie._kupon_do_logu(log, [_kupon(cel_label="5–10")], now=2_000)
    stary = next(r for r in log.values() if r["slot"] == "dzienny:12–25")
    assert stary["pominiety"] is True and stary["wynik"] is None
    assert any(r["slot"] == "dzienny:5–10" for r in log.values())


def test_kupon_odwrocony_gdy_superzmiana_uratowala_lega():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000)
    typy_log = {
        "1:p11:shots:1.5:powyzej": {"wynik": "przegrany"},
        "2:p22:shots:1.5:powyzej": {"wynik": "wygrany"},
        "3:p33:shots:1.5:powyzej": {"wynik": "wygrany"},
    }
    hist = rozliczanie._rozlicz_kupony(log, typy_log, now=50_000)
    assert hist[0]["wynik"] == "przegrany"
    # rewizja superzmiany odwraca lega -> kolejny cykl odwraca kupon
    typy_log["1:p11:shots:1.5:powyzej"]["wynik"] = "wygrany"
    hist = rozliczanie._rozlicz_kupony(log, typy_log, now=60_000)
    assert hist[0]["wynik"] == "wygrany"
    assert hist[0]["kurs_rozliczony"] == 8.0
    assert "superzmiana" in hist[0]["powod"]


# ---- superzmiana (Superbet): zmiennik dolicza się do lega "powyżej" ----

def _rec_superzmiana(**over):
    rec = {
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 10_000,
        "podmiot": "Jan Kowalski", "rynek_kod": "shots", "rynek": "Strzały",
        "linia": 1.5, "strona": "powyzej", "kurs": 1.5, "bukmacher": "Superbet",
    }
    rec.update(over)
    return rec


def test_superzmiana_ratuje_lega(monkeypatch):
    monkeypatch.setattr(
        scores365, "game_substitutions",
        lambda gid: {"jan kowalski": {"wszedl": "adam nowak", "minuta": 60.0}},
    )
    monkeypatch.setattr(
        scores365, "game_player_shots",
        lambda gid: {"jan kowalski": {"shots": 1}, "adam nowak": {"shots": 1}},
    )
    sz = rozliczanie._superzmiana(_rec_superzmiana(), 7, None, {}, 1.0)
    assert sz is not None
    suma, powod = sz
    assert suma == 2.0
    assert "adam nowak" in powod


def test_superzmiana_nie_dotyczy(monkeypatch):
    monkeypatch.setattr(
        scores365, "game_substitutions",
        lambda gid: {"jan kowalski": {"wszedl": "adam nowak", "minuta": 60.0}},
    )
    monkeypatch.setattr(
        scores365, "game_player_shots",
        lambda gid: {"adam nowak": {"shots": 5}},
    )
    # strona "poniżej" — nie ruszamy
    assert rozliczanie._superzmiana(
        _rec_superzmiana(strona="ponizej"), 7, None, {}, 1.0) is None
    # rynek spoza regulaminu superzmiany
    assert rozliczanie._superzmiana(
        _rec_superzmiana(rynek_kod="interceptions"), 7, None, {}, 1.0) is None
    # inny bukmacher
    assert rozliczanie._superzmiana(
        _rec_superzmiana(bukmacher="STS"), 7, None, {}, 1.0) is None
    # zawodnik nie był zmieniany
    monkeypatch.setattr(scores365, "game_substitutions", lambda gid: {})
    assert rozliczanie._superzmiana(
        _rec_superzmiana(), 7, None, {}, 1.0) is None


def test_superzmiana_suma_za_niska(monkeypatch):
    monkeypatch.setattr(
        scores365, "game_substitutions",
        lambda gid: {"jan kowalski": {"wszedl": "adam nowak", "minuta": 60.0}},
    )
    monkeypatch.setattr(
        scores365, "game_player_shots",
        lambda gid: {"adam nowak": {"shots": 1}},
    )
    # 0 + 1 = 1 <= linia 1.5 — dalej przegrany
    assert rozliczanie._superzmiana(
        _rec_superzmiana(), 7, None, {}, 0.0) is None


def test_superzmiana_odbiory_z_banku(monkeypatch):
    monkeypatch.setattr(
        scores365, "game_substitutions",
        lambda gid: {"jan kowalski": {"wszedl": "adam nowak", "minuta": 55.0}},
    )
    lib = {
        "77:tackles": {
            "player_name": "Adam Nowak", "market_code": "tackles",
            "timestamps": [10_500], "counts": [3.0],
        },
    }
    sz = rozliczanie._superzmiana(
        _rec_superzmiana(rynek_kod="tackles", linia=2.5), 7, None, lib, 0.0)
    assert sz is not None
    assert sz[0] == 3.0


def test_minuta_regularny_czas():
    assert scores365._minuta("4'") == 4
    assert scores365._minuta("90 + 2'") == 90
    assert scores365._minuta("45 + 1'") == 45
    assert scores365._minuta("104'") == 104  # dogrywka — odpada z agregatów
    assert scores365._minuta(None) is None


def test_migracja_scala_duplikaty_po_nazwisku():
    # era randomizowanego hash(): ten sam typ z innym player_id co cykl
    log = {
        "1:111:sot:0.5:powyzej": {
            "mecz_id": 1, "podmiot": "Michael Olise", "rynek_kod": "sot",
            "linia": 0.5, "strona": "powyzej", "kurs": 1.42,
            "opublikowano_ts": 100, "wynik": None,
        },
        "1:222:sot:0.5:powyzej": {
            "mecz_id": 1, "podmiot": "Michael Olise", "rynek_kod": "sot",
            "linia": 0.5, "strona": "powyzej", "kurs": 1.38,
            "opublikowano_ts": 200, "wynik": "przegrany", "faktyczna": 0.0,
        },
    }
    nowy = rozliczanie._migruj_log(log)
    assert len(nowy) == 1
    r = nowy["1:michael olise:sot:0.5:powyzej"]
    assert r["kurs"] == 1.42          # zamrozony z pierwszej publikacji
    assert r["wynik"] == "przegrany"  # wynik z rozliczonego duplikatu
    assert r["faktyczna"] == 0.0


# ---- skuteczność dzień po dniu (przełącznik na Skuteczności) ----

def test_skutecznosc_per_dzien_grupuje_i_liczy_roi():
    A = 100_000            # ~1970-01-02, dowolna doba
    B = A + 86_400         # kolejny dzień
    settled = [
        {"kickoff_ts": A, "wynik": "wygrany", "kurs": 2.0, "sugestia": False,
         "podmiot": "B"},
        {"kickoff_ts": A, "wynik": "przegrany", "kurs": 2.0, "sugestia": False,
         "podmiot": "A"},
        {"kickoff_ts": B, "wynik": "wygrany", "kurs": 3.0, "sugestia": False},
        # sugestia (bez zakładu) — liczy się do rozliczonych, ale NIE do ROI
        {"kickoff_ts": B, "wynik": "wygrany", "kurs": 9.0, "sugestia": True},
    ]
    out = rozliczanie.skutecznosc_per_dzien(settled)
    # posortowane malejąco po dniu (najnowszy pierwszy)
    assert [d["dzien"] for d in out] == sorted(
        (d["dzien"] for d in out), reverse=True
    )
    by = {d["dzien"]: d for d in out}
    da = time.strftime("%Y-%m-%d", time.localtime(A))
    db = time.strftime("%Y-%m-%d", time.localtime(B))
    assert by[da]["rozliczone"] == 2 and by[da]["trafione"] == 1
    # BILANS PO PODATKU (od 2026-07-31): z 1 j. pracuje 0,88 j., więc wygrana
    # po 2,0 oddaje 1,76, a nie 2,0. Dzień A: 1,76 − 2 j. = −0,24.
    assert by[da]["okazje"] == 2 and by[da]["roi_flat"] == -0.24
    assert by[db]["rozliczone"] == 2 and by[db]["trafione"] == 2
    assert by[db]["okazje"] == 1 and by[db]["roi_flat"] == 1.64  # 3,0×0,88 − 1 j.
    assert "_zwrot_j" not in by[da]           # pole robocze usunięte
    # lista typów dnia (co siadło): trafiony na górze, komplet wpisów
    assert len(by[da]["typy"]) == 2
    assert by[da]["typy"][0]["wynik"] == "wygrany"   # trafione przed przegranymi
    assert len(by[db]["typy"]) == 2                  # sugestia też jest na liście


def test_skutecznosc_per_dzien_limit_dni():
    settled = [
        {"kickoff_ts": i * 86_400, "wynik": "wygrany", "kurs": 2.0,
         "sugestia": False}
        for i in range(1, 40)
    ]
    assert len(rozliczanie.skutecznosc_per_dzien(settled, dni=7)) == 7


# --- RAPORT UCZENIA: czy model robi postępy (2026-07-29) -------------------

DZIEN = 86_400


def _typ_uczenia(i, p, wynik, kurs=1.9, rynek="shots"):
    """Rozliczony typ w księdze; kolejne i = kolejne dni meczów."""
    return {
        "mecz_id": i, "mecz": "A – B",
        "kickoff_ts": 1_700_000_000 + i * DZIEN,
        "podmiot": f"G{i}", "rynek_kod": rynek, "rynek": "R",
        "linia": 1.5, "strona": "powyzej", "kurs": kurs,
        "p_model": p, "wynik": wynik,
    }


def test_raport_uczenia_tnie_na_paczki_stalej_wielkosci():
    log = {
        str(i): _typ_uczenia(i, 0.70, "wygrany" if i % 2 == 0 else "przegrany")
        for i in range(90)
    }
    p = rozliczanie.raport_uczenia(log, rozmiar=40)["pewniaki"]["paczki"]
    assert [x["n"] for x in p] == [40, 40, 10]
    assert [x["pelna"] for x in p] == [True, True, False]
    # deklaracja vs trafienia: model mówił 70%, wchodzi 50% -> luka -20 pp
    assert p[0]["deklaracja"] == 0.7
    assert p[0]["hit"] == 0.5
    assert p[0]["luka"] == -0.2


def test_raport_uczenia_doklada_krotki_ogon_do_poprzedniej_paczki():
    """Paczka „3 typy, 33%" jako osobny wiersz sugerowałaby załamanie,
    a jest szumem — dlatego ogon poniżej minimum wsiąka w poprzedni wiersz."""
    log = {str(i): _typ_uczenia(i, 0.6, "wygrany") for i in range(43)}
    p = rozliczanie.raport_uczenia(log, rozmiar=40)["pewniaki"]["paczki"]
    assert len(p) == 1 and p[0]["n"] == 43


def test_raport_uczenia_granice_nie_ruszaja_sie_po_nowych_rozliczeniach():
    """Wiersz raz pokazany ma zostać taki sam — inaczej tabela wyglądałaby
    co dzień inaczej, mimo że historia jest ta sama."""
    log = {str(i): _typ_uczenia(i, 0.6, "wygrany") for i in range(80)}
    przed = rozliczanie.raport_uczenia(log, rozmiar=40)["pewniaki"]["paczki"]
    for i in range(80, 95):
        log[str(i)] = _typ_uczenia(i, 0.6, "przegrany")
    po = rozliczanie.raport_uczenia(log, rozmiar=40)["pewniaki"]["paczki"]
    assert po[:2] == przed[:2]


def test_raport_uczenia_widzi_postep_i_regres():
    """Trend liczy trzy pierwsze paczki wobec trzech ostatnich."""
    log = {}
    for i in range(120):        # start: mówi 70%, trafia 50% (luka -20 pp)
        log[f"a{i}"] = _typ_uczenia(i, 0.70, "wygrany" if i % 2 == 0 else "przegrany")
    for i in range(120, 240):   # teraz: mówi 55%, trafia 50% (luka -5 pp)
        log[f"b{i}"] = _typ_uczenia(i, 0.55, "wygrany" if i % 2 == 0 else "przegrany")
    t = rozliczanie.raport_uczenia(log, rozmiar=40)["pewniaki"]["trend"]
    assert t["luka_start"] < t["luka_teraz"]
    assert t["zmiana"] > 0.1          # dodatnia zmiana = luka się zamyka
    assert t["paczek"] == 6


def test_raport_uczenia_trend_pomija_niedokonczona_paczke():
    """Ostatni wiersz potrafi mieć 12 typów i skakać o 30 pp — w trendzie
    robiłby fałszywy alarm."""
    log = {
        f"a{i}": _typ_uczenia(i, 0.55, "wygrany" if i % 2 == 0 else "przegrany")
        for i in range(240)
    }
    for i in range(240, 252):   # ogon: 12 typów, same pudła
        log[f"b{i}"] = _typ_uczenia(i, 0.55, "przegrany")
    r = rozliczanie.raport_uczenia(log, rozmiar=40)["pewniaki"]
    assert r["paczki"][-1]["pelna"] is False
    assert r["trend"]["paczek"] == 6     # 240/40, ogon poza trendem


def test_raport_uczenia_rozdziela_strumienie():
    log = {}
    for i in range(50):
        log[f"p{i}"] = _typ_uczenia(i, 0.7, "wygrany")
    for i in range(50):
        log[f"d{i}"] = _typ_uczenia(i, 0.7, "przegrany", rynek="team_goals")
    r = rozliczanie.raport_uczenia(log, rozmiar=40)
    assert r["pewniaki"]["paczki"][0]["hit"] == 1.0
    assert r["druzyny"]["paczki"][0]["hit"] == 0.0


def test_raport_uczenia_pomija_typy_pomiarowe_i_spoza_publikacji():
    """Raport ma pokazywać to, co user MÓGŁ zagrać — nic więcej."""
    log = {}
    for i in range(40):
        log[f"ok{i}"] = _typ_uczenia(i, 0.6, "wygrany")
    for i in range(40, 60):
        log[f"x{i}"] = {**_typ_uczenia(i, 0.6, "przegrany"), "odrzucony": True}
    for i in range(60, 80):
        log[f"y{i}"] = {
            **_typ_uczenia(i, 0.6, "przegrany"),
            "poza_publikacja": "kwarantanna_rynku",
        }
    p = rozliczanie.raport_uczenia(log, rozmiar=40)["pewniaki"]["paczki"]
    assert len(p) == 1 and p[0]["n"] == 40 and p[0]["hit"] == 1.0


def test_raport_uczenia_nie_liczy_poprzedniej_epoki():
    """Raport odpowiada na „czy uczymy się TERAZ", więc mundial go nie dotyczy.

    Zmierzone 06.08 na żywej księdze: okno alarmu dla zawodników miało 104
    typy mundialowe i 16 ligowych, a okno porównawcze — 120 mundialowych
    w całości. Alarm mówił o produkcie, którego już nie ma.
    """
    log = {}
    for i in range(40):
        log[f"ms{i}"] = {**_typ_uczenia(i, 0.7, "przegrany"), "epoka": "ms"}
    for i in range(40, 80):
        log[f"liga{i}"] = {**_typ_uczenia(i, 0.7, "wygrany"), "epoka": "liga"}
    p = rozliczanie.raport_uczenia(log, rozmiar=40)["pewniaki"]["paczki"]
    assert len(p) == 1 and p[0]["n"] == 40
    assert p[0]["hit"] == 1.0, "same ligowe — mundialowe przegrane nie wchodzą"


# --- WYNIK MECZU TYLKO Z MECZU ZAKOŃCZONEGO (2026-07-30) --------------------


def test_wynik_meczu_tylko_gdy_status_finished(monkeypatch):
    """Sprawy Górnika Zabrze i Remo (29–30.07): rozliczaliśmy w trakcie gry.

    `fetch_event_result` obiecywało w docstringu „None, gdy mecz niezakończony",
    ale statusu nie sprawdzało — a `homeScoreCurrent` to wynik BIEŻĄCY, więc
    odczyt w 80. minucie zapisywał stan z tej minuty jako ostateczny.
    """
    from footstats.sources import statshub

    def payload(status):
        return {"data": {"events": [{
            "status": status, "homeTeamId": 1, "awayTeamId": 2,
            "homeScoreCurrent": 1, "awayScoreCurrent": 1,
        }], "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}}}

    monkeypatch.setattr(statshub, "_get", lambda url: payload("inprogress"))
    assert statshub.fetch_event_result(1) is None

    monkeypatch.setattr(statshub, "_get", lambda url: payload("finished"))
    r = statshub.fetch_event_result(2)
    assert r is not None and r["home_goals"] == 1.0


def test_rozliczamy_dopiero_po_realnym_koncu_meczu():
    """105 minut od gwizdka to dla wielu meczów jeszcze druga połowa:
    90 gry + 15 przerwy + doliczony to 115–125 minut."""
    assert rozliczanie.MECZ_KONIEC_PO_S >= 125 * 60


def test_wersje_i_kurs_ts_zamrozone_przy_typie():
    """Nowy typ w księdze niesie stempel epoki (2026-08-01).

    Bez tego pomiar na logu miesza polityki — zdarzyło się dwa razy w jednym
    tygodniu i za każdym razem trzeba było odwołać wniosek.
    """
    log = {}
    rozliczanie._dopisz_nowe(log, [{
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 1_800_000_000,
        "podmiot_id": 7, "podmiot": "A", "rynek_kod": "team_corners",
        "rynek": "Rożne", "linia": 4.5, "strona": "ponizej", "kurs": 1.90,
        "p_model": 0.60, "kurs_ts": 1_799_999_000,
    }])
    from footstats.model import betting

    rec = next(iter(log.values()))
    assert rec["wersje"] == betting.wersje_publikacji()
    assert set(rec["wersje"]) == {"model", "kalibracja", "polityka", "dane"}
    assert rec["kurs_ts"] == 1_799_999_000


def test_martwa_epoka_nowych_rynkow_nie_uczy_korekty():
    """Nowy rynek sprzed dopięcia bram nie steruje liczbą pokazywaną userowi.

    18 takich rozliczeń (trafiły 83% przy deklarowanych 58%) przesuwało
    korektę strumienia drużynowego z −0,324 na −0,179.
    """
    from footstats.model import betting

    stary = {"rynek_kod": "match_corners", "wynik": "wygrany", "p_model": 0.9}
    nowy = {**stary, "wersje": betting.wersje_publikacji()}
    zwykly = {"rynek_kod": "team_corners", "wynik": "wygrany", "p_model": 0.9}
    assert rozliczanie._z_martwej_epoki(stary)
    assert not rozliczanie._z_martwej_epoki(nowy)
    assert not rozliczanie._z_martwej_epoki(zwykly)


def test_forward_test_liczy_tylko_nowa_epoke():
    """Pre-rejestracja: docs/forward-test-druzynowe-ponizej.md.

    Segment liczy sie WYLACZNIE na rekordach ze stemplem `wersje` — na
    starszych model juz sie uczyl (bin korekty `druzyny 0,00-0,55` to
    dokladnie ten segment), wiec mierzylibysmy wlasne dopasowanie.
    """
    from footstats.model import betting

    def _typ(**kw):
        r = {
            "rynek_kod": "team_corners", "strona": "ponizej",
            "kurs": 2.20, "p_model": 0.50, "wynik": "wygrany",
            "tryb_podatku": "standard",
            "wersje": betting.wersje_publikacji(),
        }
        r.update(kw)
        return r

    # p 0,50 przy kursie 2,20: cena rynku ~0,455, rozjazd +4,5 pp = w oknie
    assert betting.w_oknie_zgody(0.50, 2.20)

    log = {
        "a": _typ(),
        "b": _typ(wynik="przegrany"),
        "stara_epoka": _typ(wersje=None),          # sprzed pre-rejestracji
        "za_tani": _typ(kurs=1.50),                # ponizej 1,90
        "powyzej": _typ(strona="powyzej"),         # zla strona
        "zawodniczy": _typ(rynek_kod="shots"),     # zly strumien
        "poza_pub": _typ(poza_publikacja="kwarantanna_rynku"),
    }
    out = rozliczanie.forward_test(log)
    assert out["n"] == 2 and out["trafione"] == 1
    assert out["cel"] == rozliczanie.FORWARD_TEST_CEL_N
    assert out["gotowy"] is False          # 2 z 40 to nie jest wynik
    # ROI po podatku: jedna wygrana po 2,20 -> 2,20 x 0,88 = 1,936 z dwoch stawek
    assert abs(out["roi"] - (1.936 / 2 - 1.0)) < 1e-6


def test_forward_test_milczy_gdy_pusto():
    out = rozliczanie.forward_test({})
    assert out["n"] == 0 and out["gotowy"] is False
    assert out["dokument"].startswith("docs/")


def test_skutecznosc_per_zdarzenie_nie_liczy_tej_samej_rzeczy_kilka_razy():
    """Zagnieżdżone linie tego samego zakładu to JEDNO zdarzenie.

    Wisła Płock, rożne w meczu: padło 11, więc „poniżej 13,5", „poniżej 14,5"
    i „poniżej 15,5" wchodzą razem. Liczone osobno zawyżają trafienia.
    """
    def _l(linia, wynik, kurs=1.10):
        return {"mecz_id": 7, "rynek_kod": "match_corners", "podmiot": "Wisła",
                "strona": "ponizej", "linia": linia, "kurs": kurs,
                "wynik": wynik, "tryb_podatku": "standard"}

    recs = [
        _l(13.5, "wygrany"), _l(14.5, "wygrany"), _l(15.5, "wygrany"),
        # osobne zdarzenie: inna drużyna, ten sam mecz
        {"mecz_id": 7, "rynek_kod": "team_goals", "podmiot": "Widzew",
         "strona": "ponizej", "linia": 1.5, "kurs": 2.0,
         "wynik": "przegrany", "tryb_podatku": "standard"},
    ]
    out = rozliczanie.skutecznosc_zdarzen(recs)
    assert out["wierszy"] == 4 and out["n"] == 2
    assert out["skupisk"] == 1
    # per wiersz byłoby 75% trafień; per zdarzenie jest 50%
    assert out["hit"] == 0.5
    assert out["trafione"] == 1.0
    # bilans: zdarzenie wygrane po 1,10 x 0,88 = 0,968 z jednej jednostki,
    # drugie przegrane -> 0,968 - 2 = -1,032
    assert abs(out["bilans_j"] - (0.968 - 2)) < 0.01


def test_skutecznosc_per_zdarzenie_bez_skupisk_zgadza_sie_z_wierszami():
    recs = [
        {"mecz_id": i, "rynek_kod": "shots", "podmiot": f"P{i}",
         "strona": "powyzej", "linia": 1.5, "kurs": 2.0,
         "wynik": "wygrany" if i < 3 else "przegrany",
         "tryb_podatku": "standard"}
        for i in range(5)
    ]
    out = rozliczanie.skutecznosc_zdarzen(recs)
    assert out["n"] == out["wierszy"] == 5
    assert out["skupisk"] == 0
    assert out["hit"] == 0.6
