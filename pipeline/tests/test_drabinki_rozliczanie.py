"""Rozliczanie drabinek: własny strumień skuteczności, izolacja od modelu."""

from footstats.jobs import rozliczanie


def _rec(
    *, mk="shots", p=0.6, wynik="wygrany", ts=1_800_000_000, kurs=2.0,
    zrodlo=None, klasa=None, **kw,
) -> dict:
    r = {
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": ts,
        "podmiot_id": 7, "podmiot": "Gracz", "rynek_kod": mk, "rynek": mk,
        "linia": 1.5, "strona": "powyzej", "kurs": kurs, "p_model": p,
        "wynik": wynik, "sugestia": False, **kw,
    }
    if zrodlo:
        r["zrodlo"] = zrodlo
    if klasa:
        r["klasa"] = klasa
    return r


def _log(recs: list[dict]) -> dict:
    return {rozliczanie._klucz(r) + f":{i}": r for i, r in enumerate(recs)}


# --- IZOLACJA OD MODELU ---

def test_drabinki_nie_wpadaja_do_kwarantanny_rynku():
    """Rynek w kwarantannie to werdykt o DEKLARACJI SILNIKA.

    Drabinki liczą p innym estymatorem (pokrycie + kontekst), więc ich
    pudła nie mogą wyłączać rynku modelowi — ani odwrotnie.
    """
    drabinki = [
        _rec(mk="fouls_committed", p=0.75, wynik="przegrany", ts=i,
             zrodlo="drabinka")
        for i in range(40)
    ]
    assert rozliczanie.rynki_kwarantanna(_log(drabinki)) == {}


def test_drabinki_nie_ucza_kalibracji_modelu():
    drabinki = [
        _rec(p=0.8, wynik="przegrany", ts=i, zrodlo="drabinka")
        for i in range(60)
    ]
    assert rozliczanie.compute_bias(_log(drabinki)) == {}


def test_typ_modelu_i_drabinka_na_tej_samej_linii_to_dwa_rekordy():
    """Bez rozdzielenia kluczy jeden rekord obsługiwałby oba strumienie."""
    model = _rec()
    drabinka = _rec(zrodlo="drabinka")
    assert rozliczanie._klucz(model) != rozliczanie._klucz(drabinka)
    log: dict = {}
    rozliczanie._dopisz_nowe(log, [model, drabinka])
    assert len(log) == 2
    assert {r.get("zrodlo") for r in log.values()} == {None, "drabinka"}


def test_zrodlo_i_klasa_zapisuja_sie_w_logu():
    log: dict = {}
    rozliczanie._dopisz_nowe(
        log, [_rec(zrodlo="drabinka", klasa="top", edge=0.12)]
    )
    rec = next(iter(log.values()))
    assert rec["zrodlo"] == "drabinka"
    assert rec["klasa"] == "top"       # bez tego progów klas nie da się zmierzyć
    assert rec["edge"] == 0.12


# --- STRUMIENIE SKUTECZNOŚCI ---

def test_skutecznosc_dzieli_sie_na_trzy_strumienie():
    log = _log([
        _rec(),                                     # pewniak (zawodnik)
        _rec(mk="team_corners"),                    # rynek drużynowy
        _rec(zrodlo="drabinka", klasa="top"),       # drabinka
        _rec(zrodlo="drabinka", klasa="solidny", wynik="przegrany"),
    ])
    s = rozliczanie.skutecznosc_strumieni(log)
    assert s["pewniaki"]["podsumowanie"]["rozliczone"] == 1
    assert s["druzyny"]["podsumowanie"]["rozliczone"] == 1
    assert s["drabinki"]["podsumowanie"]["rozliczone"] == 2
    assert s["drabinki"]["podsumowanie"]["trafione"] == 1
    assert s["drabinki"]["podsumowanie"]["skutecznosc"] == 0.5


def test_strumien_drabinek_rozbija_sie_po_klasie_karty():
    """Dopiero to odpowiada, czy „top" trafia lepiej niż „solidny"."""
    log = _log(
        [_rec(zrodlo="drabinka", klasa="top", ts=i) for i in range(4)]
        + [_rec(zrodlo="drabinka", klasa="solidny", wynik="przegrany", ts=i)
           for i in range(4)]
    )
    klasy = rozliczanie.skutecznosc_strumieni(log)["drabinki"]["klasy"]
    assert klasy["top"] == {"n": 4, "trafione": 4, "skutecznosc": 1.0}
    assert klasy["solidny"]["skutecznosc"] == 0.0


def test_roi_liczony_osobno_per_strumien():
    """Bilans PO PODATKU od stawki (od 2026-07-31), osobno per strumień.

    Liczby: przy 12% od stawki z 1 j. pracuje 0,88 j., więc wygrana po
    kursie 2,0 oddaje 1,76 (zysk +0,76), a po 3,0 — 2,64 (zysk +1,64).
    """
    log = _log([
        _rec(kurs=2.0, wynik="wygrany"),                       # 2,0×0,88−1 = +0,76
        _rec(zrodlo="drabinka", kurs=3.0, wynik="wygrany"),    # 3,0×0,88−1 = +1,64
        _rec(zrodlo="drabinka", kurs=2.0, wynik="przegrany"),  # −1,00
    ])
    s = rozliczanie.skutecznosc_strumieni(log)
    assert s["pewniaki"]["podsumowanie"]["roi_flat"] == 0.76
    assert s["drabinki"]["podsumowanie"]["roi_flat"] == 0.64


def test_tryb_bez_podatku_liczy_sie_jak_dawniej():
    """Rekord z trybem `bez_podatku` (np. promocja) rozlicza się bez potrącenia
    — dowód, że tryb jedzie z rekordem, a nie jest wpisany na sztywno."""
    log = _log([_rec(kurs=2.0, wynik="wygrany")])
    for r in log.values():
        r["tryb_podatku"] = "bez_podatku"
    s = rozliczanie.skutecznosc_strumieni(log)
    assert s["pewniaki"]["podsumowanie"]["roi_flat"] == 1.0
