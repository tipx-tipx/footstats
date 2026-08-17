# -*- coding: utf-8 -*-
"""Stempel „na czym stoi ta liczba" — warunek wdrożenia V2 z audytu.

Do 12.08 rachunek typu dawało się odtworzyć WYŁĄCZNIE dla drużyn. Zmierzone
tego dnia na produkcji: `kal_rynek` przy 423 z 684 typów drużynowych, przy
0 z 18 zawodniczych, 0 z 25 sum meczowych i 0 z 7 rynków „kto więcej";
`p_over_raw` nie istniało w ogóle. Skutek był praktyczny, nie kosmetyczny —
rozłożenie strumienia na czynniki (ile dołożyła kalibracja, ile korekta, jaki
był surowy model) było wykonalne dla jednego strumienia z czterech.

Te testy pilnują trzech rzeczy:
  1. stempel odróżnia „nie policzono" od „policzono i wyszło zero",
  2. komplet znaczy tyle samo dla każdej klasy typu,
  3. silnik zawodniczy oddaje surowe `p_over` PRZED kalibracją.
"""
import math

from footstats import engine
from footstats.model import betting


def test_puste_pola_nie_udaja_zera():
    """`None` = „ta ścieżka tego nie liczy". Zero = pomiar."""
    s = betting.stempel_rachunku(p_over_raw=0.62, kal_rynek=None,
                                 kal_strumien=0.0, p_over_final=0.62)
    assert "kal_rynek" not in s, "brak pomiaru nie może udawać zera"
    assert s["kal_strumien"] == 0.0, "zmierzone zero ma zostać zerem"
    assert s["p_over_raw"] == 0.62


def test_komplet_wymaga_calego_rachunku():
    niepelny = betting.stempel_rachunku(p_over_raw=0.62, kal_strumien=-0.4,
                                        p_over_final=0.53)
    assert not betting.stempel_kompletny(niepelny)
    pelny = betting.stempel_rachunku(p_over_raw=0.62, kal_rynek=0.1,
                                     kal_strumien=-0.4, p_over_final=0.55)
    assert betting.stempel_kompletny(pelny)
    assert not betting.stempel_kompletny({})
    assert not betting.stempel_kompletny(None)


def test_stempel_da_sie_odwrocic_do_surowego_p():
    """Sedno: z rachunku ma się dać odtworzyć, co nałożono.

    Bez tego `compute_bias_full` uczy się na `p`, z którego nie potrafi zdjąć
    własnej poprzedniej delty — powód, dla którego mapa jest dziś zamrożona.
    """
    p_raw, kal_r, kal_s = 0.62, 0.25, -0.40

    def lg(p):
        return math.log(p / (1 - p))

    p_final = 1.0 / (1.0 + math.exp(-(lg(p_raw) + kal_r + kal_s)))
    s = betting.stempel_rachunku(p_over_raw=p_raw, kal_rynek=kal_r,
                                 kal_strumien=kal_s, p_over_final=p_final)
    odtworzone = 1.0 / (1.0 + math.exp(
        -(lg(s["p_over_final"]) - s["kal_rynek"] - s["kal_strumien"])))
    assert abs(odtworzone - p_raw) < 1e-3


def test_silnik_zawodniczy_oddaje_surowe_p_over():
    """`p_over` wychodzi z silnika JUŻ skalibrowane — surowe musi jechać obok.

    Bez tego pola nie da się później powiedzieć, ile z liczby pokazanej
    klientowi jest modelem, a ile korektą z rozliczeń.
    """
    assert hasattr(engine.ScoredMarket, "__dataclass_fields__")
    pola = engine.ScoredMarket.__dataclass_fields__
    assert "p_over_raw" in pola
    assert "kal_laczna" in pola, (
        "nazwa musi mówić, że to delta ŁĄCZNA — silnik dostaje sumę "
        "kalibracji rynku i korekty strumienia (`_bias_z_korekta`)"
    )


def test_p_pokazane_nie_jest_dopelnieniem_p_over_final():
    """⚑ Liczba na karcie NIE wynika z `p_over_final` (zmierzone 12.08).

    Typ `team_fouls` „poniżej" miał p_over_final 0,3681, więc strona zakładu
    wychodziła 0,6319 — a karta pokazywała 0,6663. Różnicę robi
    `szansa_pokazywana`, nakładana PO wyborze strony i po bramie publikacji.
    Stempel bez tych pól tłumaczyłby rachunek modelu, ale nie to, o co klient
    faktycznie by zapytał.
    """
    s = betting.stempel_rachunku(
        p_over_raw=0.4866, kal_rynek=0.04, kal_strumien=-0.527,
        p_over_final=0.3681, p_pokazane=0.6663, kal_pokazywana=0.151,
    )
    strona_zakladu = 1.0 - s["p_over_final"]
    assert abs(strona_zakladu - 0.6319) < 1e-3
    assert abs(s["p_pokazane"] - strona_zakladu) > 0.03, (
        "test straciłby sens, gdyby obie liczby były równe"
    )
    # ...i da się przejść z jednej do drugiej deltą, która jest w stemplu
    def lg(p):
        return math.log(p / (1 - p))
    odtworzone = 1.0 / (1.0 + math.exp(-(lg(strona_zakladu) + s["kal_pokazywana"])))
    assert abs(odtworzone - s["p_pokazane"]) < 2e-3


def test_komplet_nie_wymaga_liczby_z_karty():
    """`p_pokazane` dochodzi PO bramach, więc typ liczony w tle go nie ma —
    i to nie znaczy, że jego rachunek jest niepełny."""
    s = betting.stempel_rachunku(p_over_raw=0.6, kal_rynek=0.1,
                                 kal_strumien=-0.4, p_over_final=0.52)
    assert betting.stempel_kompletny(s)
    assert "p_pokazane" not in s


def test_stempel_zaokragla_do_czterech_miejsc():
    """Księga rośnie o jeden słownik na typ — bez ogonów zmiennoprzecinkowych."""
    s = betting.stempel_rachunku(p_over_raw=0.6234567, kal_rynek=0.1234567,
                                 kal_strumien=-0.4, p_over_final=0.5)
    assert s["p_over_raw"] == 0.6235
    assert s["kal_rynek"] == 0.1235


# --- DROGA STEMPLA PRZEZ CZTERY BIAŁE LISTY (2026-08-17) -----------------
#
# Stempel jest wart tyle, ile jego pokrycie. Zmierzone na rekordach księgi
# powstałych po wdrożeniu stempla `kolejnosc` (14.08):
#
#     typy pomiarowe   257 rekordów    0% stempla
#     legi kuponów       4 rekordy     0%
#     POKAZANE          140 rekordów  19%
#
# Te 19% u pokazanych to skutek dwóch zer wyżej: rekord rodzi się często jako
# typ pomiarowy albo leg kuponu i dopiero potem awansuje na listę, a
# `_dopisz_nowe` przy awansie nowych pól nie dopisuje („historii nie
# przepisujemy"). Rekord bez stempla u narodzin zostaje bez niego na zawsze.

def test_wznowiony_typ_niesie_komplet_stempli():
    """Odrodzenie typu spoza listy dnia zakłada rekord OD NOWA z tej wyceny."""
    from footstats.jobs import build_wc_fast as B

    rec = {
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 1,
        "podmiot_id": 5, "podmiot": "A", "podmiot_typ": "druzyna",
        "rynek_kod": "team_corners", "rynek": "Rożne", "linia": 4.5,
        "strona": "ponizej", "kurs": 1.85, "p_model": 0.55,
        "pewnosc": "wysoka",
        "rachunek": {"p_over_raw": 0.4, "p_over_final": 0.45},
        "kal_strony": -0.196, "kal_strumien": -0.4, "kal_rynek": 0.22,
        "kolejnosc": {"moc": 0.74, "kandydatow": 9},
        "lambda": 4.2, "ess": 10.3, "udzial_priora": 0.28, "liga": "Ekstraklasa",
    }
    typ = B._typ_z_logu(rec)
    braki = [p for p in B._STEMPLE_PUBLIKACJI if typ.get(p) != rec.get(p)]
    assert not braki, (
        f"wznowiony typ gubi stemple: {braki} — po odrodzeniu rekord mówi, "
        "że liczba jest bez warstw, choć `p_model` jest po warstwach"
    )


def test_stempel_kolejnosci_obejmuje_wszystkie_drogi_do_ksiegi():
    """Cztery listy, z których rodzi się rekord — cztery, nie dwie."""
    import inspect

    from footstats.jobs import build_wc_fast as B

    zrodlo = inspect.getsource(B)
    i = zrodlo.index('_b["kolejnosc"] = {"moc"')
    petla = zrodlo[max(0, i - 400):i]
    for lista in ("value_bets", "typy_poza_publikacja",
                  "odrzucone_pomiar", "legi_pool_pub"):
        assert lista in petla, (
            f"pętla stemplująca omija `{lista}` — rekordy stamtąd rodzą się "
            "bez `kolejnosc` i zostają bez niego także po awansie na listę"
        )


def test_leg_kuponu_niesie_kolejnosc():
    """Leg bywa PIERWSZYM rekordem typu w księdze."""
    from footstats.jobs import rozliczanie as R

    rec = R._kupon_leg_do_logu({
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 1, "podmiot": "A",
        "rynek": "Rożne", "rynek_kod": "team_corners", "linia": 4.5,
        "strona": "ponizej", "kurs": 1.85, "p_model": 0.55,
        "kolejnosc": {"moc": 0.74, "kandydatow": 9},
    })
    assert rec.get("kolejnosc") == {"moc": 0.74, "kandydatow": 9}
