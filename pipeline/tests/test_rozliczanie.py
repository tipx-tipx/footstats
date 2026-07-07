"""Testy kalibracji z rozliczonych typów + cyklu życia kuponów (bez sieci)."""

from footstats.jobs import rozliczanie
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


def _kupon(cel_label="5–10", horyzont="dzienny", legi=None):
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
