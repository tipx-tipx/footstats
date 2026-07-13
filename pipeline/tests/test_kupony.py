"""Testy generatora kuponów."""

from footstats.model import kupony


def _bet(id_, mecz_id, podmiot_id, kurs, p, ev=5.0, pewnosc="wysoka", rank=1.0):
    return {
        "id": id_, "mecz_id": mecz_id, "podmiot_id": podmiot_id,
        "podmiot": f"P{podmiot_id}", "rynek": "Strzały", "linia": 1.5,
        "strona": "powyzej", "kurs": kurs, "bukmacher": "Superbet",
        "p_model": p, "ev_pct": ev, "pewnosc": pewnosc,
        "rank_score": rank, "mecz": f"M{mecz_id}", "kickoff_ts": 100_000,
        "sugestia": False,
    }


def test_kupon_value_sklada_sie_w_przedziale_4_8():
    bets = [
        _bet(1, 1, 11, 1.8, 0.62, rank=3.0),
        _bet(2, 2, 22, 1.7, 0.65, rank=2.5),
        _bet(3, 3, 33, 1.75, 0.63, rank=2.0),
    ]
    out = kupony.build_kupony(bets, now_ts=0)
    v = next((k for k in out if k.get("styl") == "value" and k["cel"] == 4), None)
    assert v is not None
    assert 4.0 <= v["kurs_laczny"] <= 8.0
    assert v["cel_label"] == "4–8"
    assert len(v["legi"]) == 3
    assert abs(v["p_model"] - 0.62 * 0.65 * 0.63) < 1e-4  # zaokrąglenie do 4 miejsc


def test_kupon_pomija_mecze_juz_rozpoczete():
    # nowy kupon nie może zawierać legów z meczów, które już się odbyły/trwają
    # (ani startujących w ciągu 15 min) — tylko świeże, obstawialne wydarzenia
    teraz = 1_000_000
    bets = [
        _bet(1, 1, 11, 1.8, 0.62, rank=3.0),
        _bet(2, 2, 22, 1.7, 0.65, rank=2.5),
        _bet(3, 3, 33, 1.75, 0.63, rank=2.0),
    ]
    for b in bets:
        b["kickoff_ts"] = teraz - 60  # mecze zaczęły się minutę temu
    assert kupony.build_kupony(bets, now_ts=teraz) == []
    # ten sam zestaw, ale mecze w przyszłości — kupon powstaje
    for b in bets:
        b["kickoff_ts"] = teraz + 3 * 3600
    assert kupony.build_kupony(bets, now_ts=teraz) != []


def test_max_one_leg_per_match_and_player():
    bets = [
        _bet(1, 1, 11, 2.0, 0.6, rank=3.0),
        _bet(2, 1, 12, 2.0, 0.6, rank=2.9),   # ten sam mecz — odpada
        _bet(3, 2, 11, 2.0, 0.6, rank=2.8),   # ten sam zawodnik — odpada
        _bet(4, 3, 44, 2.0, 0.6, rank=2.0),
        _bet(5, 4, 55, 1.6, 0.68, rank=1.5),
    ]
    out = kupony.build_kupony(bets, now_ts=0)
    for k in out:
        mecze = [l["mecz_id"] for l in k["legi"]]
        gracze = [l["podmiot"] for l in k["legi"]]
        assert len(mecze) == len(set(mecze))
        assert len(gracze) == len(set(gracze))


def test_no_coupon_when_not_enough_legs():
    bets = [_bet(1, 1, 11, 1.5, 0.72)]
    assert kupony.build_kupony(bets, now_ts=0) == []


def _leg(mecz_id, podmiot_id, kurs, p, kickoff=10_000):
    return {
        "id": 0, "mecz_id": mecz_id, "podmiot_id": podmiot_id,
        "podmiot": f"P{podmiot_id}", "rynek": "Strzały", "linia": 0.5,
        "strona": "powyzej", "kurs": kurs, "bukmacher": "Superbet",
        "p_model": p, "mecz": f"M{mecz_id}", "kickoff_ts": kickoff,
    }


def test_pewniaki_two_horizons_and_max_4_per_match():
    pool = []
    pid = 0
    for mecz in range(1, 4):  # mecze "dzisiaj"
        for _ in range(6):
            pid += 1
            pool.append(_leg(mecz, pid, 1.45, 0.72, kickoff=10_000))
    for mecz in range(4, 7):  # mecze za 2-3 dni
        for _ in range(6):
            pid += 1
            pool.append(_leg(mecz, pid, 1.45, 0.72, kickoff=2 * 86400))
    out = kupony.build_kupony([], pool, now_ts=0)
    dzienne = [k for k in out if k.get("horyzont") == "dzienny"]
    dlugie = [k for k in out if k.get("horyzont") == "dlugoterminowy"]
    assert dzienne, "kupon dzienny musi się złożyć z dzisiejszych meczów"
    assert dlugie, "kupon długoterminowy musi się złożyć"
    for k in dzienne:
        # dzienny bierze wyłącznie mecze z okna "dziś"
        assert all(l["kickoff_ts"] <= kupony.OKNO_DZIS_S for l in k["legi"])
    for k in dzienne + dlugie:
        licznik = {}
        for l in k["legi"]:
            licznik[l["mecz_id"]] = licznik.get(l["mecz_id"], 0) + 1
        assert max(licznik.values()) <= 4
        # kurs w zadeklarowanym przedziale
        cmin, cmax = (float(x) for x in k["cel_label"].split("–"))
        assert cmin <= k["kurs_laczny"] <= cmax
        # kara korelacyjna: p kuponu <= iloczyn szans legów
        iloczyn = 1.0
        for l in k["legi"]:
            iloczyn *= l["p_model"]
        assert k["p_model"] <= round(iloczyn, 4) + 1e-9


def test_low_confidence_and_small_ev_excluded():
    bets = [
        _bet(1, 1, 11, 2.0, 0.6, pewnosc="niska"),
        _bet(2, 2, 22, 2.0, 0.6, ev=-3.0),
        _bet(3, 3, 33, 2.0, 0.6, ev=1.0),   # poniżej progu 2% — odpada
        _bet(4, 4, 44, 2.0, 0.6),
    ]
    out = kupony.build_kupony(bets, now_ts=0)
    assert out == []  # tylko 1 kwalifikowany leg -> brak kuponu


def _pleg(mecz_id, podmiot_id, kurs, p):
    return {**_leg(mecz_id, podmiot_id, kurs, p), "p_model": p}


def test_kara_koszyka_dwupoziomowa():
    l_a1 = {"mecz_id": 1, "druzyna": "A"}
    l_a2 = {"mecz_id": 1, "druzyna": "A"}
    l_b = {"mecz_id": 1, "druzyna": "B"}
    l_inny = {"mecz_id": 2, "druzyna": "C"}
    l_bez = {"mecz_id": 1, "druzyna": ""}
    assert kupony._kara_koszyka([l_a1, l_inny]) == 1.0     # różne mecze
    assert kupony._kara_koszyka([l_a1, l_a2]) == kupony.KARA_TA_SAMA_DRUZYNA
    assert kupony._kara_koszyka([l_a1, l_b]) == kupony.KARA_PRZECIWNE_DRUZYNY
    assert kupony._kara_koszyka([l_a1, l_bez]) == kupony.KARA_KORELACJI


def test_rentgen_najslabszy_i_alternatywa_z_kara_korelacji():
    # mecz 1 ma już 2 legi (kara ×0.95 w p kuponu), mecz 2 — najsłabszego lega
    legi = [_pleg(1, 11, 1.5, 0.7), _pleg(1, 12, 1.5, 0.7), _pleg(2, 22, 2.0, 0.5)]
    p_kuponu = 0.7 * 0.7 * 0.5 * kupony.KARA_KORELACJI
    kupon = {"legi": legi, "kurs_laczny": 4.5, "p_model": p_kuponu}
    # kandydat z meczu 1: pewniejszy, ale dokłada TRZECIEGO lega z meczu 1
    pool = [_pleg(1, 13, 2.0, 0.9)]
    kupony._rentgen(kupon, pool, 4.0, 8.0)
    assert kupon["najslabszy_idx"] == 2
    alt = kupon["alternatywa"]
    assert alt["podmiot_id"] == 13 and alt["zamiast_idx"] == 2
    # p_po = iloczyn szans po zamianie x kara za DWA dodatkowe legi z meczu 1
    oczekiwane = 0.7 * 0.7 * 0.9 * kupony.KARA_KORELACJI ** 2
    assert abs(alt["p_po"] - oczekiwane) < 1e-4
    assert alt["kurs_po"] == 4.5


def test_rentgen_bez_alternatywy_gdy_nic_nie_poprawia():
    legi = [_pleg(1, 11, 1.5, 0.7), _pleg(2, 22, 2.0, 0.5)]
    kupon = {"legi": legi, "kurs_laczny": 3.0, "p_model": 0.35}
    # kandydat słabszy od najsłabszego lega — nie ma czego proponować
    kupony._rentgen(kupon, [_pleg(3, 33, 2.0, 0.4)], 2.5, 6.0)
    assert kupon["najslabszy_idx"] == 1
    assert "alternatywa" not in kupon


def test_wariant_b_wyraznie_inny():
    pool = [
        _leg(mecz, mecz * 10 + i, 1.45, 0.72, kickoff=10_000)
        for mecz in range(1, 4)
        for i in range(6)
    ]
    out = kupony.build_kupony([], pool, now_ts=0)
    k = next(k for k in out if k.get("horyzont") == "dzienny")
    wb = k.get("wariant_b")
    assert wb is not None
    assert wb["cel_label"] == k["cel_label"]
    sa = {(l["mecz_id"], l["podmiot_id"]) for l in k["legi"]}
    sb = {(l["mecz_id"], l["podmiot_id"]) for l in wb["legi"]}
    assert len(sa & sb) / len(sa | sb) < 0.5  # wyraźnie inny zestaw


def test_limit_ryzykownych_legow_zbalansowany():
    # pula z wieloma "perełkami" (p<0.55, wysokie kursy) i kotwicami: kupon
    # o wysokim kursie ma się składać z kotwic + max 1 ryzykownego lega,
    # a nie z samych grubych strzałów. Bez ev_uk (niezależne potwierdzenie)
    # zbalansowany nie bierze gambitów W OGÓLE; z ev_uk — najwyżej jeden.
    kotwice = [_leg(m, m * 10 + i, 1.5, 0.74, kickoff=10_000)
               for m in range(1, 5) for i in range(4)]
    samodeklarowane = [
        {**_leg(m, 800 + m, 2.9, 0.45, kickoff=10_000), "ev_pct": 30.0}
        for m in range(1, 5)
    ]
    out = kupony.build_kupony([], kotwice + samodeklarowane, now_ts=0,
                              profil="zbalansowany")
    assert out
    for k in out:
        assert all(l["p_model"] >= kupony.PROG_RYZYKA_P for l in k["legi"]), (
            f"kupon {k['cel_label']} wziął gambit bez potwierdzenia ev_uk"
        )
    potwierdzone = [
        {**_leg(m, 800 + m, 2.9, 0.45, kickoff=10_000), "ev_uk": 20.0}
        for m in range(1, 5)
    ]
    out2 = kupony.build_kupony([], kotwice + potwierdzone, now_ts=0,
                               profil="zbalansowany")
    assert out2
    for k in out2:
        n_ryzyk = sum(1 for l in k["legi"] if l["p_model"] < kupony.PROG_RYZYKA_P)
        assert n_ryzyk <= kupony.MAX_RYZYKOWNE["zbalansowany"], (
            f"kupon {k['cel_label']} ma {n_ryzyk} ryzykownych legów"
        )


def test_waga_modelu_z_ci_i_fallback():
    # wąskie widełki -> prawie pełna wiara (cap 0.80); szerokie -> 0.50;
    # brak ci -> kubełek pewności; śmieciowe ci -> też fallback
    assert kupony._waga_modelu({"ci": [0.70, 0.74]}) == 0.80
    assert abs(kupony._waga_modelu({"ci": [0.55, 0.75]}) - 0.65) < 1e-9
    assert kupony._waga_modelu({"ci": [0.30, 0.70]}) == 0.50
    assert kupony._waga_modelu({"pewnosc": "wysoka"}) == 0.75
    assert kupony._waga_modelu({"pewnosc": "srednia"}) == 0.55
    assert kupony._waga_modelu({}) == kupony.WAGA_MODELU_DEFAULT
    assert kupony._waga_modelu({"ci": ["x", "y"], "pewnosc": "wysoka"}) == 0.75


def test_p_skladania_sciaga_do_rynku():
    # leg "średniej" pewności z ogromną deklarowaną przewagą: szansa składania
    # ma leżeć między p_model a ceną rynku, bliżej modelu dla "wysokiej"
    ryzykowny = {"p_model": 0.45, "kurs": 2.9, "pewnosc": "srednia"}
    p_rynek = (1.0 / 2.9) * (1.0 - kupony.MARZA_RYNKU)
    p_sel = kupony._p_skladania(ryzykowny)
    assert p_rynek < p_sel < 0.45
    pewny = {"p_model": 0.45, "kurs": 2.9, "pewnosc": "wysoka"}
    assert p_sel < kupony._p_skladania(pewny) < 0.45
    # leg zgodny z rynkiem prawie nie drga
    zgodny = {"p_model": 0.62, "kurs": 1.5, "pewnosc": "wysoka"}
    assert abs(kupony._p_skladania(zgodny) - 0.62) < 0.01


def test_leg_value_z_urealnionej_przewagi():
    # samodeklarowane ev_pct=31% nie wchodzi już wprost — wartość liczona
    # z urealnionej szansy jest wyraźnie niższa; ev_uk (niezależne) wprost
    leg = {"p_model": 0.4442, "kurs": 2.95, "pewnosc": "srednia", "ev_pct": 31.0}
    v = kupony._leg_value(leg)
    assert 0.0 < v < 20.0
    leg_uk = {**leg, "ev_uk": 25.0}
    assert kupony._leg_value(leg_uk) == 25.0


def test_profil_bezpieczny_odrzuca_ryzykowne_legi():
    pool = [_leg(m, m * 10 + i, 1.45, 0.72, kickoff=10_000)
            for m in range(1, 4) for i in range(4)]
    ryzykowne = [_leg(m, 900 + m, 2.4, 0.45, kickoff=10_000) for m in range(1, 4)]
    out = kupony.build_kupony([], pool + ryzykowne, now_ts=0, profil="bezpieczny")
    for k in out:
        assert all(l["p_model"] >= 0.58 for l in k["legi"])


def test_dzienne_do_czterech_przedzialow():
    pool = [
        _leg(mecz, mecz * 10 + i, 1.45, 0.72, kickoff=10_000)
        for mecz in range(1, 4)
        for i in range(6)
    ]
    out = kupony.build_kupony([], pool, now_ts=0)
    dzienne = [k for k in out if k.get("horyzont") == "dzienny"]
    assert 2 <= len(dzienne) <= 4
    assert len({k["cel_label"] for k in dzienne}) == len(dzienne)
