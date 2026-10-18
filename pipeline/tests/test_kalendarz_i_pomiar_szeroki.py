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


# ---------------------------------------------------------------- braki kadrowe
from footstats.sources import statshub as S


def _kadra(unav, wystepy):
    """`wystepy`: {zawodnik: [(ts, minuty, strzały)]}"""
    evs = sorted({ts for w in wystepy.values() for ts, _, _ in w})
    eid = {ts: 1000 + i for i, ts in enumerate(evs)}
    return {
        "events": [{"events": {"id": eid[ts], "timeStartTimestamp": ts}} for ts in evs],
        "data": [{"id": pid, "stats": {str(eid[ts]): {"minutesPlayed": mi,
                                                      "onTargetScoringAttempt": sh}
                                       for ts, mi, sh in w}}
                 for pid, w in wystepy.items()],
        "unavailability": unav,
    }


def test_niedostepni_zasady():
    ko = KO
    w = {1: [(ko - 4 * DZIEN, 90, 3)], 2: [(ko - 4 * DZIEN, 0, 0)],
         3: [(ko - 4 * DZIEN, 90, 1)], 4: [(ko - 4 * DZIEN, 90, 0)],
         5: [(ko - 30 * DZIEN, 90, 0)], 6: [(ko - 4 * DZIEN, 80, 0)]}
    unav = [
        # kontuzja bez daty końca, nie grał od początku wpisu → pewny brak
        {"playerId": 2, "kind": "injury", "status": "out", "startDateTimestamp": ko - 10 * DZIEN},
        # wątpliwy
        {"playerId": 3, "kind": "injury", "status": "dayToDay",
         "startDateTimestamp": ko - DZIEN, "endDateTimestamp": ko + 5 * DZIEN},
        # zawieszenie w LIDZE (utid 8), mecz w LM (utid 7) → gra
        {"playerId": 4, "kind": "suspension", "status": None, "uniqueTournamentId": 8,
         "startDateTimestamp": ko - DZIEN, "endDateTimestamp": ko + 20 * DZIEN},
        # wpis nieaktualny: zagrał po początku wpisu
        {"playerId": 1, "kind": "injury", "status": "out", "startDateTimestamp": ko - 10 * DZIEN},
        # wraca przed meczem
        {"playerId": 5, "kind": "injury", "status": "out",
         "startDateTimestamp": ko - 40 * DZIEN, "endDateTimestamp": ko - DZIEN},
        # zawieszenie w tych rozgrywkach
        {"playerId": 6, "kind": "suspension", "status": None, "uniqueTournamentId": 7,
         "reason": "red_card_suspension", "startDateTimestamp": ko - DZIEN,
         "endDateTimestamp": ko + 3 * DZIEN},
    ]
    nd = S.niedostepni_z_kadry(_kadra(unav, w), ko, utid=7)
    assert set(nd) == {2, 3, 6}
    assert nd[2]["pewny"] and nd[2]["r"] == "kontuzja"
    assert not nd[3]["pewny"]
    assert nd[6]["pewny"] and nd[6]["r"] == "zawieszenie"
    # rozgrywki meczu nieznane → zawieszenie nie działa (bez fałszywego zdjęcia)
    assert 6 not in S.niedostepni_z_kadry(_kadra(unav, w), ko, utid=None)


def test_braki_druzyny_udzialy_i_lider():
    ko = KO
    w = {1: [(ko - 4 * DZIEN, 90, 4), (ko - 11 * DZIEN, 90, 4)],
         2: [(ko - 4 * DZIEN, 90, 1), (ko - 11 * DZIEN, 90, 1)],
         3: [(ko - 4 * DZIEN, 90, 1), (ko - 11 * DZIEN, 90, 0)]}
    k = _kadra([], w)
    br = S.braki_druzyny(k, {1: {"pewny": True}, 3: {"pewny": False}}, ko)
    assert br["n"] == 1 and br["w"] == 1
    assert br["lid"] == 1 and br["lid_w"] == 0
    assert abs(br["sh"] - 8 / 11) < 0.01 and abs(br["min"] - 1 / 3) < 0.01
    assert S.braki_druzyny(_kadra([], {}), {}, ko) is None


def test_braki_typu():
    mecze = {5: (1, 2)}
    bk = {(5, 1): {"braki": {"n": 1}}, (5, 2): {"braki": {"n": 3}}}
    t = B.braki_typu({"mecz_id": 5, "podmiot_typ": "druzyna", "podmiot_id": -2,
                      "rynek_kod": "team_shots"}, bk, mecze, {})
    assert t == {"my": {"n": 3}, "ryw": {"n": 1}}
    z = B.braki_typu({"mecz_id": 5, "podmiot_typ": "zawodnik", "podmiot_id": 9,
                      "rynek_kod": "shots"}, bk, mecze, {(5, 9): 1})
    assert z == {"my": {"n": 1}, "ryw": {"n": 3}}
    assert B.braki_typu({"mecz_id": 5, "rynek_kod": "match_cards"}, bk, mecze, {}) == \
        {"g": {"n": 1}, "a": {"n": 3}}
    assert B.braki_typu({"mecz_id": 6, "rynek_kod": "match_cards"}, bk, mecze, {}) is None


def test_dolacz_kadry_niedostepni_per_mecz():
    ko = KO
    w = {7: [(ko - 4 * DZIEN, 90, 2)], 8: [(ko - 30 * DZIEN, 90, 0)]}
    unav = [{"playerId": 8, "kind": "injury", "status": "out",
             "startDateTimestamp": ko - 20 * DZIEN}]
    kadra = _kadra(unav, w)
    ev = {"id": 55, "timeStartTimestamp": ko, "homeTeamId": 1, "awayTeamId": 2,
          "uniqueTournamentId": 7}
    braki: dict = {}
    licz = B.dolacz_pelne_kadry(
        [], [ev], ko - 3600, oferta=lambda e: {"sb": {"x": {}}, "bc": {}},
        fetch_kadra=lambda tid: kadra, fetch_extra=lambda ids: {}, braki_out=braki)
    assert set(braki) == {(55, 1), (55, 2)}
    assert braki[(55, 1)]["nd"][8]["pewny"]
    assert licz["niedostepni_pewni"] == 2          # ta sama kadra po obu stronach


# ---------------------------------------------------------------- sędziowie
def test_sedziowie_pamiec_i_limit():
    pobrane = []

    def fetch(rid):
        pobrane.append(rid)
        return {"m": 50, "zk": 4.0, "ck": 0.2, "k": 0.3, "ost": KO}

    ev = [{"id": 1 + i, "refereeId": 100 + i, "timeStartTimestamp": KO + i} for i in range(5)]
    pam: dict = {"100": {"ts": KO, "p": {"m": 9, "zk": 1.0, "ck": 0.0, "k": 0.0}}}
    po, n = B.odswiez_sedziow_sh(ev, pam, KO + 60, fetch=fetch, limit=2)
    assert n == 2 and pobrane == [101, 102]          # 100 świeży, limit 2
    assert po[1] == {"id": 100, "m": 9, "zk": 1.0, "ck": 0.0, "k": 0.0}
    assert set(po) == {1, 2, 3}
    # po terminie świeżości pobiera ponownie
    po, n = B.odswiez_sedziow_sh(ev[:1], pam, KO + B.SEDZIOWIE_SH_SWIEZOSC_S + 1,
                                 fetch=fetch, limit=5)
    assert n == 1 and pobrane[-1] == 100


# ---------------------------------------------------------------- księga
def test_ksiega_braki_sedzia_i_odrodzenie_szerokiego():
    log: dict = {}
    R._dopisz_nowe(log, [_typ(kurs=2.4, p_model=0.41, odrzucony=True,
                              odrzucenie_powod=R.POWOD_POMIARU_SZEROKIEGO,
                              braki={"my": {"n": 1}}, sedzia_sh={"id": 1, "m": 50})])
    k = next(iter(log))
    assert log[k]["braki"] == {"my": {"n": 1}} and log[k]["sedzia_sh"]["m"] == 50
    # ta sama linia pokazana później — rekord od nowa, z ceną publikacji
    R._dopisz_nowe(log, [_typ(kurs=2.1, p_model=0.5)])
    rec = log[k]
    assert rec["kurs"] == 2.1 and rec["p_model"] == 0.5 and not rec["odrzucony"]
    assert rec["kurs_otw"] == 2.4


def test_awans_pomiaru_zapisuje_cene_publikacji():
    log: dict = {}
    R._dopisz_nowe(log, [_typ(kurs=1.9, odrzucony=True, odrzucenie_powod="ev_ponizej_progu")])
    R._dopisz_nowe(log, [_typ(kurs=1.8)])
    rec = next(iter(log.values()))
    assert rec["kurs"] == 1.9 and rec["kurs_pub"] == 1.8 and rec["pub_ts"]
    R._dopisz_nowe(log, [_typ(kurs=1.7)])
    assert rec["kurs_pub"] == 1.8                     # tylko pierwszy awans


def test_cykl_niedostepni_przed_bramka_zawodnika():
    src = inspect.getsource(B)
    i_def = src.index("kontuzje_zawieszenia: dict[tuple[int, int], dict] = {}")
    i_bram = src.index('_odrzuc(mid, tr, "niedostepny"')
    i_poza = src.index('_odrzuc(mid, tr, "poza_skladem"')
    assert i_def < i_bram < i_poza


# ---------------------------------------------------------------- pewność startu
from footstats.model import sklad as SK


def _mecze_dr(n=10, l=17, puchar_od=None):
    return [{"t": KO - (i + 1) * 7 * DZIEN, "l": (7 if puchar_od is not None and i in puchar_od else l)}
            for i in range(n)]


def test_pewnosc_startu_regularny_vs_rezerwowy():
    m = _mecze_dr()
    regularny = [(x["t"], 90.0, True) for x in m]
    rezerwowy = [(x["t"], 15.0, False) for x in m[:4]]
    pr = SK.stempel(m, regularny, 17, None, None)
    pz = SK.stempel(m, rezerwowy, 17, None, None)
    assert pr["s"] > 0.8 > 0.3 > pz["s"]
    # źródła przesuwają w swoją stronę, zgoda mocniej
    tak = SK.stempel(m, rezerwowy, 17, True, True)["s"]
    nie = SK.stempel(m, regularny, 17, False, False)["s"]
    assert tak > pz["s"] and nie < pr["s"]
    assert pr["v"] == SK.WERSJA and pr["zr"] == [None, None]


def test_pewnosc_startu_bez_historii():
    m = _mecze_dr()
    assert SK.stempel(m[:4], [(x["t"], 90.0, True) for x in m[:4]], 17, None, None) is None
    # nie grał w żadnym z 5 ostatnich meczów drużyny — nie wiemy, czy jest w kadrze
    assert SK.stempel(m, [(x["t"], 90.0, True) for x in m[6:]], 17, None, None) is None


def test_pewnosc_startu_puchar_i_tolerancja_godziny():
    m = _mecze_dr()
    # występ zapisany z godziną przesuniętą o 2 h (przełożony start) to ten sam mecz
    przes = [(x["t"] + 2 * 3600, 90.0, True) for x in m]
    assert SK.cechy_historii(m, przes, 17)[0] == 1.0
    c = SK.cechy_historii(m, [(x["t"], 90.0, True) for x in m], 7)
    assert c[8] == 1.0                                  # puchar: rozgrywki ≠ liga domowa


def test_ksiega_p_start_i_najswiezszy():
    log: dict = {}
    R._dopisz_nowe(log, [_typ(p_start={"s": 0.7})])
    rec = next(iter(log.values()))
    assert rec["p_start"] == {"s": 0.7}
    R._dopisz_nowe(log, [_typ(p_start={"s": 0.9})])
    assert rec["p_start"] == {"s": 0.7} and rec["p_start_ost"] == {"s": 0.9}
