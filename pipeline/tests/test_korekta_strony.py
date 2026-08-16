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
