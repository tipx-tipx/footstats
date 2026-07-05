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


def test_przegrany_od_pierwszego_pudla():
    log = {}
    rozliczanie._kupon_do_logu(log, [_kupon()], now=1_000)
    typy_log = {"1:p11:shots:1.5:powyzej": {"wynik": "przegrany"}}
    hist = rozliczanie._rozlicz_kupony(log, typy_log, now=50_000)
    assert hist[0]["wynik"] == "przegrany"


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
