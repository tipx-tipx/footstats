"""Testy pomiaru progów: odrzucenia przy progu (betting) + obieg w logu."""

import time

from footstats.jobs import rozliczanie
from footstats.model import betting


def _conf(**kw):
    base = dict(
        effective_matches=20.0, minutes_certainty=0.9, ci_width=0.10,
        context_magnitude=0.05, market_calibrated=True, is_rare_market=False,
    )
    base.update(kw)
    return betting.ConfidenceInputs(**base)


def test_near_miss_ev_zbierany():
    """EV tuż poniżej progu (jedyne złamane kryterium) -> kolektor."""
    odrz: list = []
    # p=0.50 @ 1.98 -> EV = -1.0% (próg 1.0%, tolerancja 3 pp) — reszta OK
    wyn = betting.assess(0.50, 1.98, None, _conf(), lam=2.0, odrzucone_out=odrz)
    assert wyn == []
    assert len(odrz) == 1
    assert odrz[0]["powod"] == "ev_ponizej_progu"
    assert odrz[0]["side"] == "powyzej"


def test_near_miss_za_daleko_nie_zbierany():
    """EV daleko poniżej progu -> zwykłe odrzucenie, bez pomiaru."""
    odrz: list = []
    # p=0.40 @ 1.98 -> EV = -20.8% — dużo poniżej tolerancji
    betting.assess(0.40, 1.98, None, _conf(), lam=2.0, odrzucone_out=odrz)
    assert odrz == []


def test_near_miss_dwa_kryteria_nie_zbierany():
    """Dwa złamane kryteria naraz -> nie wiadomo, które mierzyć — pomijamy."""
    odrz: list = []
    # niska pewność (mała próba, szerokie CI tuż pod MAX) ORAZ EV pod progiem
    betting.assess(
        0.50, 1.98, None,
        _conf(effective_matches=3.0, minutes_certainty=0.3, ci_width=0.28),
        lam=2.0, odrzucone_out=odrz,
    )
    assert odrz == []


def test_odrzucony_poza_kalibracja_i_diagnostyka_osobno():
    log: dict = {}
    typ = {
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": 100,
        "podmiot_id": 7, "podmiot": "Jan Testowy",
        "rynek_kod": "shots", "rynek": "Strzały", "linia": 0.5,
        "strona": "powyzej", "kurs": 1.5, "p_model": 0.62,
        "odrzucony": True, "odrzucenie_powod": "ev_ponizej_progu",
    }
    rozliczanie._dopisz_nowe(log, [typ])
    k = rozliczanie._klucz(typ)
    assert log[k]["odrzucony"] is True
    # rozliczony pomiarowy typ nie wchodzi do kalibracji...
    log[k].update(wynik="wygrany", faktyczna=1.0)
    # dołóż 30 zwykłych rozliczonych, żeby kalibracja miała próbę
    for i in range(30):
        kk = f"2:gracz {i}:shots:0.5:powyzej"
        log[kk] = {
            "mecz_id": 2, "podmiot": f"Gracz {i}", "rynek_kod": "shots",
            "linia": 0.5, "strona": "powyzej", "p_model": 0.6,
            "kurs": 1.6, "wynik": "wygrany" if i % 2 else "przegrany",
            "sugestia": False,
        }
    bias = rozliczanie.compute_bias_full(log, min_n=25)
    # ...a 30 zwykłych wystarcza — więc jego obecność nie zmienia n
    diag = rozliczanie.compute_diagnostyka(log)
    assert diag["kategorie"]["wszystkie"]["n"] == 30
    assert diag["kategorie"]["odrzucone_pomiar"]["n"] == 1
    assert "shots" in bias


def test_publikacja_czysci_flage_pomiarowa():
    log: dict = {}
    typ = {
        "mecz_id": 1, "mecz": "A – B", "kickoff_ts": int(time.time()),
        "podmiot_id": 7, "podmiot": "Jan Testowy",
        "rynek_kod": "shots", "rynek": "Strzały", "linia": 0.5,
        "strona": "powyzej", "kurs": 1.5, "p_model": 0.62,
        "odrzucony": True, "odrzucenie_powod": "ev_ponizej_progu",
    }
    rozliczanie._dopisz_nowe(log, [typ])
    # ten sam typ chwilę później PRZECHODZI progi i jest publikowany
    opublikowany = {**typ, "odrzucony": False, "odrzucenie_powod": None}
    rozliczanie._dopisz_nowe(log, [opublikowany])
    rec = log[rozliczanie._klucz(typ)]
    assert rec["odrzucony"] is False
    assert "odrzucenie_powod" not in rec
