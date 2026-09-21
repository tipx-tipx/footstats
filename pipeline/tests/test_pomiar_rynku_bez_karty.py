"""Pomiar rynku bez karty (faule popełnione) — 2026-09-21.

Właściciel chce fauli popełnionych z powrotem w drabinkach; backtest na
księdze (nota przy radar.POWOD_POMIARU_RYNKU) mówi, że po dzisiejszym sicie
trafiają 37% przy cenie 53%. Kompromis: linia fauli, która przeszła CAŁE sito,
rozlicza się w tle z własnym stemplem, a na kartę nie wchodzi, dopóki pomiar
nie dogoni ceny. Tu pilnujemy, że (1) taka linia trafia do pomiaru tylko po
pełnym sicie, (2) nigdy nie jest hero, (3) bez kolektora nic się nie zmienia,
(4) rozliczanie liczy ją w osobnej grupie.
"""
from footstats.jobs import radar, rozliczanie


def _karta_fauli(traf, kurs=2.05, p_final=0.62, forma5=None, minuty=85,
                 z=10, drugi=True):
    """Kandydat, którego JEDYNYM rynkiem są faule popełnione."""
    drabinka = [{
        "linia": 1.5, "kurs": kurs,
        "pokrycie": {"traf": traf, "z": z},
        "pokrycie5": {"traf": min(traf, 5) if forma5 is None else forma5, "z": 5},
        "p_bazowe": p_final, "korekta": 1.0, "p_final": p_final,
    }]
    if drugi:
        drabinka.append({
            "linia": 2.5, "kurs": 3.6,
            "pokrycie": {"traf": max(traf - 2, 0), "z": z},
            "pokrycie5": {"traf": min(max(traf - 2, 0), 5), "z": 5},
            "p_bazowe": 0.40, "korekta": 1.0, "p_final": 0.40,
        })
    return {
        "minuty_sr6": minuty, "udzial_startow": 0.9, "krotkie_wystepy5": 0,
        "rynki": [{"rynek_kod": "fouls_committed", "rynek": "Faule popełnione",
                   "drabinka": drabinka}],
    }


def test_stemple_radaru_i_rozliczania_sa_zgodne():
    assert radar.POWOD_POMIARU_RYNKU == rozliczanie.POWOD_POMIARU_RYNKU
    assert radar.POWOD_POMIARU_RYNKU != rozliczanie.POWOD_POMIARU_POKRYCIA
    assert "fouls_committed" in radar.RYNKI_BEZ_KARTY


def test_faule_po_pelnym_sicie_ida_do_pomiaru_nie_na_karte():
    """8/10, forma 5/5, kurs 2,05, pełne minuty — dokładnie kształt Mukairu
    (Pogoń, 20.09). Karta NIE powstaje, pomiar dostaje tę linię."""
    pomiar: list = []
    score, hero = radar._oceń_karte(_karta_fauli(8), pomiar_out=pomiar)
    assert hero is None and score == 0.0
    assert len(pomiar) == 1
    p = pomiar[0]
    assert p["rynek_kod"] == "fouls_committed" and p["linia"] == 1.5
    assert p["powod_pomiaru"] == radar.POWOD_POMIARU_RYNKU
    assert p["traf"] == 8 and p["kurs"] == 2.05


def test_faule_pod_sitem_nie_ida_do_pomiaru():
    """4/10 to nie jest linia, która poszłaby na kartę po zdjęciu banu —
    mierzenie jej nic nie mówi o banie. (Guendouzi: 4/10 → nic.)"""
    pomiar: list = []
    _score, hero = radar._oceń_karte(_karta_fauli(4), pomiar_out=pomiar)
    assert hero is None and pomiar == []
    # 6/10 z formą 2/5: siła 0,4·0,6 + 0,6·0,4 = 0,48 < 0,70 — sito, nie pomiar
    pomiar = []
    radar._oceń_karte(_karta_fauli(6, forma5=2), pomiar_out=pomiar)
    assert pomiar == []


def test_bramy_karty_obowiazuja_pomiar_rynku_tak_samo():
    """Zmiennik (54 min śr.) nie idzie do pomiaru — mierzymy porównywalne."""
    pomiar: list = []
    radar._oceń_karte(_karta_fauli(8, minuty=54), pomiar_out=pomiar)
    assert pomiar == []


def test_bez_kolektora_pomiaru_ban_dziala_jak_dotad(monkeypatch):
    from collections import Counter
    powody: Counter = Counter()
    score, hero = radar._oceń_karte(_karta_fauli(8), powody)
    assert hero is None and score == 0.0
    assert powody["rynek_bez_karty"] == 1


def test_pomiar_rynku_nie_wypycha_pomiaru_progu_pokrycia():
    """Zawodnik z dwoma rynkami: strzały 4/10 (pomiar progu) i faule 8/10
    (pomiar rynku) — oba pomiary zostają, każdy ze swoim stemplem."""
    w = _karta_fauli(8)
    w["rynki"].append({"rynek_kod": "shots", "rynek": "Strzały", "drabinka": [
        {"linia": 1.5, "kurs": 2.40, "pokrycie": {"traf": 4, "z": 10},
         "pokrycie5": {"traf": 4, "z": 5}, "p_bazowe": 0.45, "korekta": 1.0,
         "p_final": 0.45},
        {"linia": 2.5, "kurs": 3.6, "pokrycie": {"traf": 3, "z": 10},
         "pokrycie5": {"traf": 3, "z": 5}, "p_bazowe": 0.40, "korekta": 1.0,
         "p_final": 0.40},
    ]})
    pomiar: list = []
    _score, hero = radar._oceń_karte(w, pomiar_out=pomiar)
    assert hero is None
    stemple = sorted(p.get("powod_pomiaru") or "pokrycie" for p in pomiar)
    assert stemple == ["pokrycie", radar.POWOD_POMIARU_RYNKU]


def test_rozliczanie_liczy_pomiar_rynku_w_osobnej_grupie():
    def rec(powod, wynik, **kw):
        return {"zrodlo": rozliczanie.ZRODLO_DRABINKA, "wynik": wynik,
                "kurs": 2.0, "p_model": 0.55, "odrzucony": True,
                "odrzucenie_powod": powod, "rynek_kod": "fouls_committed", **kw}
    log = {
        "a": rec(rozliczanie.POWOD_POMIARU_RYNKU, "wygrany"),
        "b": rec(rozliczanie.POWOD_POMIARU_RYNKU, "przegrany"),
        "c": rec(rozliczanie.POWOD_POMIARU_POKRYCIA, "wygrany"),
        "d": {"zrodlo": rozliczanie.ZRODLO_DRABINKA, "wynik": "wygrany",
              "kurs": 1.9, "p_model": 0.6, "rynek_kod": "shots"},
    }
    out = rozliczanie.pomiar_progu_drabinek(log)
    assert out["rynek_bez_karty"]["n"] == 2 and out["rynek_bez_karty"]["hit"] == 0.5
    assert out["pod_progiem"]["n"] == 1
    assert out["opublikowane"]["n"] == 1


# --- pomiar 6/10 w tle (sito v4, 21.09) ------------------------------------

def _karta_6_z_10(traf=6, forma5=5, kurs=2.40):
    """Kształt Gintera: 6/10, forma 5/5, cena grywalna, realny drugi szczebel."""
    from tests.test_radar import _karta_do_oceny
    w = _karta_do_oceny(traf, kurs=kurs)
    w["rynki"][0]["drabinka"][0]["pokrycie5"] = {"traf": forma5, "z": 5}
    return w


def test_stempel_pokrycia6_zgodny():
    assert radar.POWOD_POMIARU_POKRYCIA6 == rozliczanie.POWOD_POMIARU_POKRYCIA6
    assert radar.PROG_POKRYCIA_POMIARU < radar.PROG_POKRYCIA_SILY


def test_6_z_10_po_sicie_v3_idzie_do_pomiaru_nie_na_karte():
    pomiar: list = []
    score, hero = radar._oceń_karte(_karta_6_z_10(), pomiar_out=pomiar)
    assert hero is None and score == 0.0
    assert [p.get("powod_pomiaru") for p in pomiar] == [radar.POWOD_POMIARU_POKRYCIA6]
    assert pomiar[0]["traf"] == 6 and pomiar[0]["sila"] >= 0.70


def test_6_z_10_ze_slaba_forma_nie_idzie_do_pomiaru():
    """Siła 0,4·0,6 + 0,6·0,4 = 0,48 — nie przeszłaby sita v3, więc nie mierzy
    niczego o progu."""
    pomiar: list = []
    radar._oceń_karte(_karta_6_z_10(forma5=2), pomiar_out=pomiar)
    assert pomiar == []


def test_5_z_10_nie_idzie_do_pomiaru_6():
    pomiar: list = []
    radar._oceń_karte(_karta_6_z_10(traf=5), pomiar_out=pomiar)
    assert [p.get("powod_pomiaru") for p in pomiar if p.get("powod_pomiaru")] == []


def test_7_z_10_dalej_jest_karta_a_nie_pomiarem():
    pomiar: list = []
    _score, hero = radar._oceń_karte(_karta_6_z_10(traf=7), pomiar_out=pomiar)
    assert hero is not None and hero["sito"] is True
    assert pomiar == []


def test_rozliczanie_liczy_pomiar_6_z_10_w_osobnej_grupie():
    rec = {"zrodlo": rozliczanie.ZRODLO_DRABINKA, "wynik": "wygrany", "kurs": 2.0,
           "p_model": 0.55, "odrzucony": True,
           "odrzucenie_powod": rozliczanie.POWOD_POMIARU_POKRYCIA6}
    out = rozliczanie.pomiar_progu_drabinek({"a": rec})
    assert out["pokrycie_6_z_10"]["n"] == 1 and out["pod_progiem"]["n"] == 0


# --- rekord pomiaru niesie pełny stempel do księgi (21.09) -------------------

def test_rekord_pomiaru_niesie_pokrycie_forme_sile_i_bramy_karty():
    import inspect
    from footstats.jobs import build_wc_fast as B
    p = {"mecz_id": 1, "mecz": "A – B", "kickoff_ts": 1, "podmiot_id": 7,
         "podmiot": "X", "rynek_kod": "shots", "linia": 1.5, "kurs": 2.05,
         "p_final": 0.55, "edge": 0.06, "traf": 6, "z": 10, "traf5": 5, "z5": 5,
         "sila": 0.84, "p_bazowe": 0.5, "korekta": 1.1, "sito_wersja": "v4",
         "minuty_sr6": 85, "udzial_startow": 0.9, "krotkie_wystepy5": 0,
         "ostatni_wystep_min": 90, "xi": True,
         "powod_pomiaru": radar.POWOD_POMIARU_POKRYCIA6}
    r = B._rekord_pomiaru_drabinki(p)
    assert r["odrzucony"] is True and r["odrzucenie_powod"] == "pokrycie_6_z_10"
    assert r["pokrycie_traf"] == 6 and r["pokrycie_z"] == 10 and r["pokrycie"] == 0.6
    assert r["forma5_traf"] == 5 and r["sila"] == 0.84 and r["korekta"] == 1.1
    assert r["ostatni_wystep_min"] == 90 and r["xi"] is True
    # ...i KAŻDE z tych pól przechodzi przez białą listę księgi
    zrodlo = inspect.getsource(rozliczanie._dopisz_nowe)
    for pole in ("pokrycie_traf", "pokrycie_z", "pokrycie", "forma5_traf",
                 "forma5_z", "sila", "p_bazowe", "korekta", "sito_wersja",
                 "minuty_sr6", "udzial_startow", "krotkie_wystepy5", "xi",
                 "ostatni_wystep_min", "edge"):
        assert f'"{pole}"' in zrodlo, f"`{pole}` zginie w _dopisz_nowe"
    # bez pomiaru rynku/6-z-10 stempel = dawny pomiar progu pokrycia
    p.pop("powod_pomiaru")
    assert B._rekord_pomiaru_drabinki(p)["odrzucenie_powod"] == rozliczanie.POWOD_POMIARU_POKRYCIA
