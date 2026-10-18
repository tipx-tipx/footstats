"""Kalendarz drużyny, skład przy drabinkach i szeroki zapis kandydatów w księdze
(2026-10-18, plan „90%”: materiał dla selektora typów, nic nie zmienia na stronie)."""
import inspect

from footstats.jobs import build_wc_fast as B
from footstats.jobs import rozliczanie as R
from footstats.model import argumenty as A

DZIEN = 86400
KO = 1_800_000_000


def _mag():
    """Drużyna 1: liga 10, mecze co 7 dni, ostatni 3 dni przed meczem (puchar 7)."""
    ms = [{"t": KO - 3 * DZIEN, "o": 50, "l": 7, "h": 1, "s": {}, "sp": {}}]
    ms += [{"t": KO - (10 + 7 * i) * DZIEN, "o": 60 + i, "l": 10, "h": 1, "s": {}, "sp": {}}
           for i in range(9)]
    return {"1": {"m": ms}, "2": {"m": [{"t": KO - 6 * DZIEN, "o": 1, "l": 10, "h": 0,
                                        "s": {}, "sp": {}}]}}


def test_kalendarz_druzyny():
    idx = A.Indeks(_mag())
    k = A.kalendarz(idx, 1, KO, liga_meczu=7, nast_ts=KO + 4 * DZIEN)
    assert k["odp"] == 3.0
    assert k["m14"] == 2                       # 3 i 10 dni przed
    assert k["ld"] == 10 and k["l"] == 7       # puchar: rozgrywki ≠ liga domowa
    assert k["nast"] == 4.0
    assert A.kalendarz(idx, 999, KO) is None   # brak historii — brak stempla
    # mecz sprzed 3 h (ten sam, już w magazynie) nie liczy się jako „ostatni"
    mag = _mag()
    mag["1"]["m"].append({"t": KO - 3600, "o": 2, "l": 10, "h": 1, "s": {}, "sp": {}})
    assert A.kalendarz(A.Indeks(mag), 1, KO)["odp"] == 3.0


def test_kalendarz_typu_druzyny_zawodnika_i_sumy():
    idx = A.Indeks(_mag())
    mecze = {5: (1, 2)}
    zaw = {(5, 77): 1}
    liga = {5: 7}
    nast = lambda tid, ko: None
    d = B.kalendarz_typu({"mecz_id": 5, "kickoff_ts": KO, "podmiot_typ": "druzyna",
                          "podmiot_id": -1, "rynek_kod": "team_shots"},
                         idx, mecze, zaw, liga, nast)
    assert d["odp"] == 3.0 and d["l"] == 7
    z = B.kalendarz_typu({"mecz_id": 5, "kickoff_ts": KO, "podmiot_typ": "zawodnik",
                          "podmiot_id": 77, "rynek_kod": "shots"}, idx, mecze, zaw, liga, nast)
    assert z == d
    m = B.kalendarz_typu({"mecz_id": 5, "kickoff_ts": KO, "rynek_kod": "match_corners"},
                         idx, mecze, zaw, liga, nast)
    assert m["g"]["odp"] == 3.0 and m["a"]["odp"] == 6.0
    assert B.kalendarz_typu({"mecz_id": 5, "kickoff_ts": KO, "podmiot_typ": "zawodnik",
                             "podmiot_id": 78, "rynek_kod": "shots"},
                            idx, mecze, zaw, liga, nast) is None
    assert B.kalendarz_typu({"mecz_id": 5, "kickoff_ts": KO}, None, mecze, zaw, liga, nast) is None


def test_pomiar_szeroki_wybor_linii():
    lo, hi = B.POMIAR_SZEROKI_KURS
    # stała decyzja dla klucza (ta sama linia w każdym cyklu)
    wyb = [B.do_pomiaru_szerokiego(1, p, "shots", 1.5, 2.0, 80.0) for p in range(400)]
    assert wyb == [B.do_pomiaru_szerokiego(1, p, "shots", 1.5, 2.0, 80.0) for p in range(400)]
    udzial = sum(wyb) / len(wyb)
    assert abs(udzial - B.POMIAR_SZEROKI_UDZIAL / 100) < 0.08
    p = next(i for i in range(400) if wyb[i])
    assert not B.do_pomiaru_szerokiego(1, p, "shots", 1.5, lo - 0.01, 80.0)   # za tani
    assert not B.do_pomiaru_szerokiego(1, p, "shots", 1.5, hi + 0.01, 80.0)   # za drogi
    assert not B.do_pomiaru_szerokiego(1, p, "shots", 1.5, 2.0, 30.0)         # rezerwowy
    assert not B.do_pomiaru_szerokiego(1, p, "shots", 1.5, None, 80.0)


def test_pokrycie_historii():
    counts = [3, 0, 2, 2, 1, 4, 0, 2, 3, 1, 5]
    minutes = [90, 5, 90, 80, 90, 90, 70, 90, 90, 90, 90]   # 5 min się nie liczy
    assert B.pokrycie_historii(counts, minutes, 1.5, 5) == (4, 5)
    assert B.pokrycie_historii(counts, minutes, 1.5, 10) == (7, 10)
    assert B.pokrycie_historii([], [], 1.5, 10) == (0, 0)


def _typ(**kw) -> dict:
    baza = {"mecz": "A – B", "rynek_kod": "shots", "rynek": "Strzały",
            "podmiot": "X", "podmiot_id": 1, "linia": 1.5, "strona": "powyzej",
            "kurs": 2.0, "p_model": 0.5, "kickoff_ts": 1785000000, "mecz_id": 1}
    baza.update(kw)
    return baza


def test_ksiega_zapisuje_kalendarz_i_sklad_drabinki():
    log: dict = {}
    kal = {"odp": 3.0, "m14": 2, "l": 7, "ld": 10}
    R._dopisz_nowe(log, [_typ(kalendarz=kal, xi_sygnal="poza_przewidywanym",
                              odrzucony=True,
                              odrzucenie_powod=R.POWOD_POMIARU_SZEROKIEGO,
                              pokrycie_traf=7, pokrycie_z=10, forma5_traf=4,
                              forma5_z=5, minuty_sr6=84.0)])
    rec = next(iter(log.values()))
    assert rec["kalendarz"] == kal
    assert rec["xi_sygnal"] == "poza_przewidywanym"
    assert rec["odrzucony"] and rec["odrzucenie_powod"] == "pomiar_szeroki"
    assert rec["pokrycie_z"] == 10 and rec["forma5_traf"] == 4 and rec["minuty_sr6"] == 84.0


def test_kalendarz_dopisany_do_nierozliczonego_rekordu():
    log: dict = {}
    R._dopisz_nowe(log, [_typ()])
    rec = next(iter(log.values()))
    assert "kalendarz" not in rec
    R._dopisz_nowe(log, [_typ(kalendarz={"odp": 5.0, "m14": 2})])
    assert rec["kalendarz"] == {"odp": 5.0, "m14": 2}
    # pierwszy stempel zostaje (stan sprzed meczu z chwili zapisu)
    R._dopisz_nowe(log, [_typ(kalendarz={"odp": 1.0, "m14": 3})])
    assert rec["kalendarz"]["odp"] == 5.0


def test_szeroki_zapis_bierze_tylko_nadwyzke_budzetu_rozliczen():
    """Rekord pomiarowy nie zjada zapytań historii statshub typom ze strony."""
    rec = _typ(podmiot_id=123, odrzucenie_powod=R.POWOD_POMIARU_SZEROKIEGO)
    budzet = [R.REZERWA_PERF_DLA_TYPOW]
    assert R._perf_w_meczu(rec, {}, budzet) is None
    assert budzet == [R.REZERWA_PERF_DLA_TYPOW]          # nic nie pobrano
    src = inspect.getsource(R._perf_w_meczu)
    assert "REZERWA_PERF_DLA_TYPOW" in src


def test_cykl_stempluje_i_dolacza_szeroki_zapis():
    """Kolejność w cyklu: szeroki zapis dołącza do typów pomiarowych PRZED
    pętlą stempli (inaczej rekord bez argumentów i kalendarza), a lista idzie
    do `_rozlicz_i_zapisz` jako `odrzucone_pomiar`."""
    src = inspect.getsource(B)
    i_dol = src.index("odrzucone_pomiar = list(odrzucone_pomiar) + _szerokie")
    i_petla = src.index("_stempel_kalendarza(_b)\n        _ile = _kandydatow_w_meczu")
    i_zapis = src.index("_rozlicz_i_zapisz(value_bets, kupony_list")
    assert i_dol < i_petla < i_zapis
    assert src.index("for _b in drabinki_typy:\n        _stempel_kalendarza(_b)") < i_zapis
