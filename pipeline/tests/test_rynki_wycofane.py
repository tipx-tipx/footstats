# -*- coding: utf-8 -*-
"""RYNEK WYCOFANY — rynek, którego nie umiemy ZAMKNĄĆ, nie wychodzi na produkt.

Dlaczego to ma test: `tackles` domykał się w 36,9% (pomiar 18.08 na księdze
8530 wpisów), a typ, którego nie da się rozliczyć, po siedmiu dniach idzie na
zwrot i znika z pomiaru — mimo że user go widział. Kanały są CZTERY (lista,
księga, karty, pula kuponów) i każdy ma osobną drogę wznowienia, więc brama
w jednym miejscu nie wystarcza ([[wznowione-omijaly-bramy]]).
"""
from footstats.jobs import build_wc_fast as B
from footstats.model import betting


def test_odbiory_sa_wycofane():
    assert betting.rynek_wycofany("tackles")
    assert not betting.rynek_wycofany("shots")
    assert not betting.rynek_wycofany("team_corners")
    assert not betting.rynek_wycofany(None)


def test_karta_bez_wycofanego_rynku_zostaje_nietknieta():
    w = {"rynki": [{"rynek_kod": "shots"}, {"rynek_kod": "sot"}],
         "hero": {"rynek_kod": "shots"}}
    assert B._bez_wycofanych_rynkow(w) is w      # ten sam obiekt, bez kopii


def test_karta_traci_wycofany_rynek_a_reszte_zachowuje():
    w = {"rynki": [{"rynek_kod": "shots"}, {"rynek_kod": "tackles"}],
         "hero": {"rynek_kod": "shots"}}
    out = B._bez_wycofanych_rynkow(w)
    assert [r["rynek_kod"] for r in out["rynki"]] == ["shots"]
    assert w["rynki"] and len(w["rynki"]) == 2   # wejście nietknięte


def test_karta_wylacznie_z_wycofanego_rynku_znika():
    w = {"rynki": [{"rynek_kod": "tackles"}], "hero": {"rynek_kod": "tackles"}}
    assert B._bez_wycofanych_rynkow(w) is None


def test_karta_z_hero_na_wycofanym_rynku_znika_mimo_innych_rynkow():
    # nagłówek obiecywałby typ, którego nie umiemy zamknąć
    w = {"rynki": [{"rynek_kod": "shots"}, {"rynek_kod": "tackles"}],
         "hero": {"rynek_kod": "tackles"}}
    assert B._bez_wycofanych_rynkow(w) is None


def test_wycofany_rynek_nie_wchodzi_do_rodzin_kuponu_jako_zywy():
    # rynek zostaje w maszynerii (model, kalibracja, matchup) — usuwamy go
    # z PRODUKTU, nie z kodu; ta asercja pilnuje, żeby ktoś nie "posprzątał"
    # mapy rodzin i nie wysypał kalibracji rynków defensywnych
    assert betting.RODZINY_RYNKOW["tackles"] == "defensywa"


def test_sezony_na_karcie_tez_traca_wycofany_rynek():
    """Decyzja właściciela 18.08: „zdejmij odbiory całkowicie".

    Sekcja `sezony` to średnie OPISOWE, nie zakład — ale karta pokazuje je pod
    tą samą etykietą co rynki („odbiory 0,94 na 90 min"), więc zostawienie ich
    znaczyłoby, że rynek wycofany dalej jest na stronie.
    """
    from footstats.jobs import radar as R

    cache = {"77": {"sezony": [
        {"rok": "2026", "minuty": 900,
         "na90": {"shots": 2.2, "tackles": 0.9, "sot": 0.8},
         "na_mecz": {"shots": 1.6, "tackles": 0.7, "sot": 0.6}},
    ]}}
    out = R._sezony_wpisu(cache, 77)
    assert out, "sekcja sezonów ma zostać, tylko bez wycofanego rynku"
    assert "tackles" not in out[0]["na90"]
    assert "tackles" not in out[0]["na_mecz"]
    # reszta statystyk NIETKNIĘTA — wycinamy rynek, nie sekcję
    assert out[0]["na90"]["shots"] == 2.2 and out[0]["na90"]["sot"] == 0.8
    assert out[0]["rok"] == "2026" and out[0]["minuty"] == 900
    # wejście nietknięte (nie mutujemy cache workera)
    assert "tackles" in cache["77"]["sezony"][0]["na90"]


def test_etykiety_historyczne_zostaja():
    """Wycofanie NIE JEST kasowaniem historii. Typy na odbiory rozliczone
    wcześniej muszą się dalej poprawnie wyświetlać w Skuteczności, więc
    mapy nazw rynków ZOSTAJĄ — tu pilnujemy, żeby ktoś ich nie „posprzątał"."""
    from footstats.jobs import rozliczanie as R
    assert "tackles" in R.MARKETY_LIB, (
        "bez tego rozliczanie nie zamknie typów sprzed wycofania"
    )


def _rec(*, mk: str, **kw) -> dict:
    """Rekord w kształcie, jakiego wymaga `_dopisz_nowe` (patrz jego biała
    lista pól) — ten sam wzorzec co w `test_drabinki_rozliczanie`."""
    return {"mecz_id": 1, "mecz": "A – B", "kickoff_ts": 1_800_000_000,
            "podmiot_id": 7, "podmiot": f"Gracz {mk}", "rynek_kod": mk,
            "rynek": mk, "linia": 1.5, "strona": "powyzej", "kurs": 1.9,
            "p_model": 0.6, "sugestia": False, **kw}


def test_typ_POMIAROWY_na_wycofanym_rynku_tez_nie_wchodzi_do_ksiegi():
    """PIĄTY KANAŁ, znaleziony 19.08 przy weryfikacji wdrożenia.

    Brama z 18.08 stanęła na ścieżce PUBLIKACJI, więc zatrzymywała typy, które
    mogłyby trafić na stronę. Ale typ POMIAROWY — odrzucony przy progu
    (`ev_ponizej_progu`, `niska_pewnosc`) albo drabinkowy spod progu pokrycia —
    idzie do księgi prosto przez `_dopisz_nowe` i tamtej bramy nie mijał.

    Zmierzone dobę po wycofaniu: 14 nowych `tackles` w księdze, wszystkie
    `odrzucony=True`, a 25 z 73 „typów czekających na dane" (34%) to odbiory,
    których NIE MA CZYM ZAMKNĄĆ.
    """
    from footstats.jobs import rozliczanie as R

    log: dict = {}
    R._dopisz_nowe(log, [
        _rec(mk="tackles", odrzucony=True, odrzucenie_powod="ev_ponizej_progu"),
        _rec(mk="shots", odrzucony=True, odrzucenie_powod="ev_ponizej_progu"),
    ])
    rynki = {v.get("rynek_kod") for v in log.values()}
    assert "tackles" not in rynki, (
        "typ pomiarowy na wycofanym rynku wisi potem jako „czekający na dane”"
    )
    assert "shots" in rynki, "pozostałe rynki mają wchodzić normalnie"


def test_wycofany_rynek_nie_wchodzi_do_ksiegi_takze_jako_opublikowany():
    from footstats.jobs import rozliczanie as R

    log: dict = {}
    R._dopisz_nowe(log, [_rec(mk="tackles")])
    assert log == {}


def test_historia_wycofanego_rynku_zostaje_w_ksiedze():
    """Wycofanie NIE JEST kasowaniem historii: rekord sprzed zmiany ma zostać,
    żeby rozliczanie mogło go domknąć wynikiem albo zwrotem."""
    from footstats.jobs import rozliczanie as R

    stary = _rec(mk="tackles", wynik=None)
    log = {R._klucz(stary): dict(stary)}
    R._dopisz_nowe(log, [dict(stary)])
    assert len(log) == 1, "istniejący rekord ma zostać nietknięty"
