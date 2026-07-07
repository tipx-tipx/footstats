"""Testy profilu rywala (koncesje per rynek × pozycja)."""

from footstats.model import koncesje


def test_kubelek_pozycji():
    assert koncesje.kubelek_pozycji("RCB") == "obrona"
    assert koncesje.kubelek_pozycji("LB") == "obrona"
    assert koncesje.kubelek_pozycji("RWB") == "obrona"
    assert koncesje.kubelek_pozycji("DM") == "pomoc"
    assert koncesje.kubelek_pozycji("M") == "pomoc"
    assert koncesje.kubelek_pozycji("RW") == "atak"
    assert koncesje.kubelek_pozycji("ST") == "atak"
    assert koncesje.kubelek_pozycji("GK") == ""
    assert koncesje.kubelek_pozycji(None) == ""


def _rec(pid, market, opps, counts, minutes=None, poss=None, tss=None):
    n = len(counts)
    return {
        "player_id": pid, "market_code": market,
        "counts": counts, "minutes": minutes or [90.0] * n,
        "timestamps": tss or [1_800_000_000] * n,
        "game_opponents": opps, "game_positions": poss or ["CB"] * n,
        "position": "D",
    }


def test_koncesje_lookup_i_filtr_klubowy():
    wc = {"francja", "brazylia", "norwegia", "polska"}
    lib = {}
    # 5 obrońców grało z Francją i notowało po 3 odbiory (dużo);
    # przeciw innym drużynom MŚ norma to 1 odbiór
    for pid in range(5):
        lib[f"{pid}:tackles"] = _rec(
            pid, "tackles",
            ["Francja", "Brazylia", "FC Klubowo"],   # klubowy rywal wypada
            [3.0, 1.0, 9.0],
            tss=[1_800_000_100 + pid, 1_800_100_000 + pid, 1_800_200_000],
        )
    # dopełnij normę do MIN_OBS_NORMA obserwacji
    for pid in range(5, 9):
        lib[f"{pid}:tackles"] = _rec(pid, "tackles", ["Norwegia"], [1.0])
    k = koncesje.zbuduj_koncesje(lib, wc)
    out = k.lookup("Francja", "tackles", "D")
    assert out is not None
    allowed, norma, n = out
    assert allowed == 3.0                # Francja oddaje 3/90 obrońcom
    assert allowed > norma               # wyraźnie ponad normę turnieju
    # 5 zawodników w tym samym meczu z Francją = ~1 mecz próby (nie 5)
    assert n == 1
    # rywal spoza banku / pozycja bramkarza -> brak profilu
    assert k.lookup("Marsjanie", "tackles", "D") is None
    assert k.lookup("Francja", "tackles", "GK") is None


def test_koncesje_wazenie_sila_rywala():
    # Norwegia dopuszczała: obrońcom MOCNEJ drużyny 3.0, słabej 1.0 —
    # przed meczem z mocną drużyną profil ma ciążyć ku 3.0
    lib = {}
    for pid in range(6):
        lib[f"{pid}:tackles"] = {**_rec(pid, "tackles", ["Norwegia"], [3.0]),
                                 "team_name": "France"}
    for pid in range(6, 12):
        lib[f"{pid}:tackles"] = {**_rec(pid, "tackles", ["Norwegia"], [1.0]),
                                 "team_name": "Botswana"}
    k = koncesje.zbuduj_koncesje(lib, {"norwegia"})
    elo = {"france": 2100, "england": 2050, "botswana": 1300}
    bez_wag = k.lookup("Norwegia", "tackles", "D")
    z_wagami = k.lookup("Norwegia", "tackles", "D", elo_map=elo,
                        team_name="England")
    assert bez_wag is not None and z_wagami is not None
    assert abs(bez_wag[0] - 2.0) < 1e-9          # zwykła średnia
    assert z_wagami[0] > 2.3                      # mocni ważą więcej
    # bez_teamu w elo -> wagi neutralne, dalej liczy się sensownie
    assert k.lookup("Norwegia", "tackles", "D", elo_map=elo,
                    team_name="Marsjanie") is not None


def test_koncesje_min_ts_odcina_stare_mecze():
    wc = {"francja", "norwegia"}
    lib = {
        f"{pid}:shots": _rec(
            pid, "shots", ["Francja", "Norwegia"], [5.0, 1.0],
            tss=[100, 1_800_000_000],  # mecz z Francją sprzed turnieju
        )
        for pid in range(12)
    }
    k = koncesje.zbuduj_koncesje(lib, wc, min_ts=1_000_000)
    assert k.lookup("Francja", "shots", "D") is None  # stare wypadły
    out = k.lookup("Norwegia", "shots", "D")
    assert out is not None and out[0] == 1.0
