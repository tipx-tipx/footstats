# -*- coding: utf-8 -*-
"""KOREKTA STRONY ZAKŁADU — warstwa uczona i nakładana na `p` TEJ strony.

⚑ PO CO OSOBNA WARSTWA, SKORO SĄ JUŻ DWIE. Kalibracja rynku i korekta
strumienia nakładają delty na `p_over`, a „poniżej" powstaje jako
`1 − p_over`. Taka delta jest TRANSFEREM: ściągając jedną stronę, podnosi
drugą. A zmierzone 16.08 przeszacowanie dotyczy OBU stron:

    poniżej   n=813   deklaruje 57,9%   trafia 54,5%   luka  -3,5 pp
    powyżej   n=384   deklaruje 54,8%   trafia 40,1%   luka -14,7 pp

Jedną liczbą na `p_over` nie da się obniżyć obu naraz — stąd ta warstwa.
Pełny opis: `docs/warstwy-uczenia-szkodza.md`.
"""

from __future__ import annotations

import time

from footstats.jobs import rozliczanie as R
from footstats.model import betting


def _rec(strona="ponizej", rynek="team_corners", p=0.70, wynik="przegrany",
         p_over_raw=None, **kw):
    """Rozliczony typ ze stemplem `rachunek` (bez niego warstwa go nie widzi)."""
    if p_over_raw is None:
        p_over_raw = p if strona == "powyzej" else 1.0 - p
    r = {
        "mecz_id": 1, "mecz": "A – B", "podmiot_id": 7, "podmiot": "A",
        "podmiot_typ": "druzyna", "rynek_kod": rynek, "rynek": "Rożne",
        "linia": 4.5, "strona": strona, "kurs": 1.8, "p_model": p,
        "sugestia": False, "wynik": wynik, "epoka": R.EPOKA_BIEZACA,
        "kickoff_ts": int(time.time()) - 86400, "opublikowano_ts": 1,
        "rachunek": {"p_over_raw": round(float(p_over_raw), 4)},
    }
    r.update(kw)
    return r


def _log(recs):
    return {f"k{i}": r for i, r in enumerate(recs)}


# --- sedno: obie strony dostają WŁASNĄ deltę ---

def test_kazda_strona_ma_wlasna_delte():
    """„Poniżej" przeszacowuje lekko, „powyżej" mocno — delty mają to oddać."""
    recs = []
    # poniżej: deklaruje 70%, wchodzi ~60% (30 z 50)
    for i in range(50):
        recs.append(_rec(strona="ponizej", p=0.70,
                         wynik="wygrany" if i < 30 else "przegrany", mecz_id=i))
    # powyżej: deklaruje 70%, wchodzi ~30% (15 z 50) — dużo gorzej
    for i in range(50):
        recs.append(_rec(strona="powyzej", p=0.70,
                         wynik="wygrany" if i < 15 else "przegrany",
                         mecz_id=100 + i))
    out = R.korekta_strony(_log(recs))
    assert "team_corners|ponizej" in out
    assert "team_corners|powyzej" in out
    assert out["team_corners|ponizej"] < 0, "obie strony przeszacowują"
    assert out["team_corners|powyzej"] < 0
    assert out["team_corners|powyzej"] < out["team_corners|ponizej"], (
        "strona, która myli się mocniej, musi dostać MOCNIEJSZĄ korektę — "
        "inaczej wracamy do jednej delty na p_over"
    )


def test_strona_dobrze_skalibrowana_milczy():
    """Cisza znaczy „nie ma czego poprawiać", a nie „zero"."""
    recs = [
        _rec(strona="ponizej", p=0.60,
             wynik="wygrany" if i < 30 else "przegrany", mecz_id=i)
        for i in range(50)
    ]
    out = R.korekta_strony(_log(recs))
    assert "team_corners|ponizej" not in out


def test_warstwa_zbiega_zamiast_nakladac_sie_w_kolko():
    """Warstwa nie może widzieć własnego efektu — inaczej oscyluje.

    Bierzemy DWA razy ten sam typ o surowym `p` = 0,70 i trafialności 60%:
      A — jeszcze bez korekty (`p_model` 0,70),
      B — po nałożeniu −0,30 (`p_model` niższe, stempel `kal_strony`).
    Cel jest w obu wypadkach ten sam. Warstwa działa poprawnie, jeśli B jest
    BLIŻEJ celu niż A — czyli dokłada resztę, a nie całość od nowa.
    """
    import math as _m
    cel = _m.log(0.60 / 0.40) - _m.log(0.70 / 0.30)     # ~ -0,442
    p_po = 1.0 / (1.0 + _m.exp(-(_m.log(0.70 / 0.30) - 0.30)))

    a = [_rec(p=0.70, wynik="wygrany" if i < 30 else "przegrany", mecz_id=i)
         for i in range(50)]
    b = [_rec(p=p_po, wynik="wygrany" if i < 30 else "przegrany", mecz_id=i,
              kal_strony=-0.30, p_over_raw=1.0 - 0.70) for i in range(50)]
    d_a = R.korekta_strony(_log(a))["team_corners|ponizej"]
    d_b = R.korekta_strony(_log(b))["team_corners|ponizej"]
    assert abs(d_b - cel) < abs(d_a - cel), (
        f"warstwa ma DOCHODZIĆ do celu ({cel:.3f}), a nie liczyć go od nowa: "
        f"bez korekty {d_a:.3f}, po korekcie {d_b:.3f}"
    )
    assert d_b >= R.KOREKTA_STRONY_CAP[0]


def test_para_bez_proby_dziedziczy_delte_rynku():
    """Mała próba na parze nie znaczy, że rynek nic nie wie."""
    recs = []
    for i in range(70):                       # rynek ma próbę
        recs.append(_rec(strona="ponizej", p=0.75,
                         wynik="wygrany" if i < 35 else "przegrany", mecz_id=i))
    for i in range(5):                        # ta strona — prawie nic
        recs.append(_rec(strona="powyzej", p=0.75, wynik="przegrany",
                         mecz_id=500 + i))
    out = R.korekta_strony(_log(recs))
    assert "team_corners|powyzej" in out, (
        "para pod progiem ma dziedziczyć deltę RYNKU, a nie znikać — "
        "pięć rekordów to za mało na własną, ale rynek próbę ma"
    )


def test_cap_trzyma_delte_w_ryzach():
    """Skrajna próba nie może wyzerować listy jednym cyklem."""
    recs = [
        _rec(strona="ponizej", p=0.95, wynik="przegrany", mecz_id=i)
        for i in range(60)
    ]
    out = R.korekta_strony(_log(recs))
    assert out["team_corners|ponizej"] >= R.KOREKTA_STRONY_CAP[0]


# --- nakładanie: musi wejść PRZED bramami, na `p` wybranej strony ---

def test_delta_strony_czyta_wlasciwy_klucz():
    kor = {"team_corners|ponizej": -0.4, "team_corners|powyzej": -0.9}
    assert betting.delta_strony(kor, "team_corners", "ponizej") == -0.4
    assert betting.delta_strony(kor, "team_corners", "powyzej") == -0.9
    assert betting.delta_strony(kor, "team_goals", "ponizej") == 0.0
    assert betting.delta_strony(None, "team_corners", "ponizej") == 0.0


def test_korekta_obniza_szanse_i_wartosc_przed_brama():
    """Sedno: skoro `p` spada, to EV liczone z niego też — a to ono decyduje."""
    conf = betting.ConfidenceInputs(
        effective_matches=10.0, minutes_certainty=0.9, ci_width=0.10,
        context_magnitude=0.05, market_calibrated=True, is_rare_market=False,
    )
    # kurs dobrany tak, żeby „poniżej" przechodziło progi BEZ korekty —
    # inaczej test nie sprawdzałby niczego poza tym, że brama działa
    bez = betting.assess(0.30, 3.6, 1.60, conf, lam=4.0)
    z_kor = betting.assess(
        0.30, 3.6, 1.60, conf, lam=4.0,
        korekta_strony={"team_corners|ponizej": -0.2}, rynek_kod="team_corners",
    )

    def _pod(res, side):
        return next((a for a in res if a.side == side), None)

    a0, a1 = _pod(bez, "ponizej"), _pod(z_kor, "ponizej")
    assert a0 is not None, "bez korekty ta strona ma przechodzić progi"
    assert a1 is not None, "przy tej korekcie strona ma jeszcze przechodzić"
    assert a1.model_prob < a0.model_prob
    assert a1.ev_pct < a0.ev_pct, (
        "korekta ma zmieniać WARTOŚĆ, bo to na niej stoi selekcja"
    )
    assert a1.kal_strony == -0.2, "delta musi zostać ostemplowana"
    # strona „powyżej" bez wpisu w korekcie zostaje nietknięta
    b0, b1 = _pod(bez, "powyzej"), _pod(z_kor, "powyzej")
    if b0 is not None and b1 is not None:
        assert b1.model_prob == b0.model_prob


def test_stempel_kal_strony_dojezdza_do_ksiegi():
    """Bez stempla warstwa uczyłaby się na własnym efekcie i oscylowała."""
    log: dict = {}
    R._dopisz_nowe(log, [{
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": int(time.time()) + 7200,
        "podmiot_id": 5, "podmiot": "A", "podmiot_typ": "druzyna",
        "rynek_kod": "team_corners", "rynek": "Rożne", "linia": 4.5,
        "strona": "ponizej", "kurs": 1.85, "p_model": 0.55,
        "pewnosc": "wysoka", "kal_strony": -0.234,
    }])
    rec = next(iter(log.values()))
    assert rec.get("kal_strony") == -0.234


def test_warstwa_jest_w_rejestrze():
    """Warstwa spoza rejestru może paść niezauważona — patrz nota tam."""
    assert "korekta_strony" in R.WARSTWY_UCZENIA
    assert "korekta_strony" in R.JEDNOSTKI_WARSTW


# --- droga stempla: gdzie pole ginęło do 17.08 ---------------------------
#
# ⚑ ZMIERZONE NA PRODUKCJI 17.08, dobę po wdrożeniu warstwy: rejestr cyklu
# pokazywał `korekta_strony OK, n=22`, delta była realnie nakładana na typy
# drużynowe (team_cards|powyzej −0,499 przy delcie −0,497), a stempla NIE
# MIAŁ ANI JEDEN z 302 typów zapisanych po wdrożeniu. Pole ustawiało się
# w legu i ginęło na białych listach po drodze. Skutek nie jest kosmetyczny:
# warstwa uczy się na `p_model` po zdjęciu WŁASNEJ delty, więc bez stempla
# zdejmuje zero i nakłada korektę drugi raz w każdym cyklu.
#
# Testy niżej pilnują KAŻDEGO ogniwa tej drogi osobno. Trzy z nich czytają
# źródło, bo warunki siedzą w środku funkcji na kilka tysięcy linii, której
# nie da się zawołać bez całego cyklu (ten sam chwyt co w `test_publikacje`).

def test_leg_kuponu_niesie_delte_strony():
    """Rekord urodzony z lega bywa jedynym śladem po typie."""
    rec = R._kupon_leg_do_logu({
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 1, "podmiot": "A",
        "rynek": "Rożne", "rynek_kod": "team_corners", "linia": 4.5,
        "strona": "ponizej", "kurs": 1.85, "p_model": 0.55,
        "kal_strony": -0.211,
    })
    assert rec.get("kal_strony") == -0.211


def test_biala_lista_publikacji_przenosi_delte():
    """`rec_pewniaka`: co nie jest tu wymienione, ginie w drodze na stronę."""
    import inspect
    from footstats.jobs import build_wc_fast as B

    zrodlo = inspect.getsource(B)
    i = zrodlo.index('"rank_score": round(_atrakcyjnosc(b), 4)')
    blok = zrodlo[i:i + 2500]
    assert '"kal_strony"' in blok, (
        "biała lista `rec_pewniaka` znowu gubi deltę korekty strony — "
        "warstwa przestanie widzieć własny efekt i naliczy ją drugi raz"
    )


def test_wznowiony_typ_niesie_delte_strony():
    """Wznowienie niesie `p` zamrożone Z deltą, więc i stempel musi jechać.

    Rekord wznowionego typu bywa zakładany w księdze OD NOWA — odrodzenie
    typu spoza listy dnia usuwa stary wpis (`_dopisz_nowe`). Bez stempla
    taki rekord wraca z liczbą po korekcie i zerową deltą.
    """
    from footstats.jobs import build_wc_fast as B

    typ = B._typ_z_logu({
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 1,
        "podmiot_id": 5, "podmiot": "A", "podmiot_typ": "druzyna",
        "rynek_kod": "team_corners", "rynek": "Rożne", "linia": 4.5,
        "strona": "ponizej", "kurs": 1.85, "p_model": 0.55,
        "kal_strony": -0.196, "pewnosc": "wysoka",
    })
    assert typ.get("kal_strony") == -0.196


def test_typy_pomiarowe_niosa_delte_strony():
    """Typy pomiarowe uczą warstwę na równi z publikowanymi.

    Dwie trzecie próby zawodniczej to odrzucenia przy progu — rekord bez
    stempla zaniża zdjętą deltę w całej grupie.
    """
    import inspect
    from footstats.jobs import build_wc_fast as B

    zrodlo = inspect.getsource(B)
    szt = zrodlo.count("odrzucone_pomiar.append(")
    assert szt >= 2, "zmieniła się liczba ścieżek pomiarowych — sprawdź test"
    for i in range(szt):
        start = -1
        for _ in range(i + 1):
            start = zrodlo.index("odrzucone_pomiar.append(", start + 1)
        blok = zrodlo[start:start + 2200]
        assert '"kal_strony"' in blok, (
            f"{i + 1}. ścieżka typów pomiarowych nie stempluje delty strony"
        )


def test_pula_zawodnicza_liczy_p_ta_sama_delta_co_okazja():
    """Jeden zakład — jedna szansa (naprawa `4b132e5` z 13.08).

    Okazja zawodnicza jedzie z `assess`, które nakłada deltę na `p` wybranej
    strony. Pula liczyła `p` wprost z `sm.p_over`, czyli sprzed tej warstwy,
    więc ten sam zakład miał od 16.08 dwie różne szanse: jedną na karcie,
    drugą w legu kuponu.
    """
    import inspect
    from footstats.jobs import build_wc_fast as B

    zrodlo = inspect.getsource(B)
    i = zrodlo.index("p_side = sm.p_over if side_key")
    blok = zrodlo[i:i + 1200]
    assert "delta_strony(korekta_stron" in blok, (
        "pula zawodnicza znowu liczy `p` sprzed korekty strony — leg kuponu "
        "i karta pokażą różne szanse dla tego samego zakładu"
    )
    assert "_z_delta(p_side" in blok


def test_ta_sama_formula_w_puli_i_w_assess():
    """Formuła nakładania delty musi być JEDNA — inaczej liczby się rozjadą."""
    conf = betting.ConfidenceInputs(
        effective_matches=10.0, minutes_certainty=0.9, ci_width=0.10,
        context_magnitude=0.05, market_calibrated=True, is_rare_market=False,
    )
    kor = {"shots|powyzej": -0.25}
    res = betting.assess(0.62, 1.85, 3.20, conf, lam=2.0,
                         korekta_strony=kor, rynek_kod="shots")
    a = next((x for x in res if x.side == "powyzej"), None)
    assert a is not None, "przy tym kursie strona ma przechodzić progi"
    z_puli = betting._z_delta(0.62, betting.delta_strony(kor, "shots", "powyzej"))
    assert abs(a.model_prob - round(z_puli, 4)) < 1e-4, (
        "pula i `assess` liczą deltę inaczej — to wraca do dwóch szans "
        "dla jednego zakładu"
    )
