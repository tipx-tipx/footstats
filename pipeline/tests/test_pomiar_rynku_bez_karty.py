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
