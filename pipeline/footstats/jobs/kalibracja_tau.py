"""Kalibracja pamięci formy DRUŻYN (tau) z własnych rozliczeń.

DEFAULT_TAU_DAYS=180 w counts.py jest strojone pod sezon ZAWODNIKA;
statystyki drużynowe żyją szybciej (zmiana trenera, stylu, kontuzje
w bloku obronnym), ale skracanie pamięci "na oko" grozi gonieniem szumu.
Ten skrypt liczy, jak kalibrowałby się każdy kandydat tau na typach
drużynowych, które FAKTYCZNIE się rozliczyły: dla rozliczonego typa
odtwarza posterior z historii zapisanej przy predykcji (pole kal_tau
w typy_log, pisane od 2026-07-21), przelicza szansę przy danym tau
i porównuje z wynikiem (Brier + log-loss). Uruchamiać ręcznie:

    python -m footstats.jobs.kalibracja_tau

Decyzję o zmianie tau dla drużyn podejmujemy dopiero przy >= MIN_N
rozliczeń i WYRAŹNEJ przewadze kandydata — kosmetyczna różnica Briera
na małej próbie to szum, nie sygnał.
"""

from __future__ import annotations

import math

import numpy as np

from .. import supa
from ..model import counts

TAUS = (30.0, 45.0, 60.0, 90.0, 120.0, 180.0, 240.0)
MIN_N = 40


def rekordy_druzynowe(log: dict) -> list[dict]:
    """Rozliczone typy drużynowe z pełnym payloadem kalibracyjnym."""
    out = []
    for rec in log.values():
        kt = rec.get("kal_tau") or {}
        if (
            rec.get("wynik") in ("wygrany", "przegrany")
            and str(rec.get("rynek_kod", "")).startswith("team_")
            and kt.get("hist") and kt.get("ts")
            and len(kt["hist"]) == len(kt["ts"])
            and kt.get("prior")
        ):
            out.append(rec)
    return out


def p_przy_tau(rec: dict, tau: float) -> float:
    """Szansa typu odtworzona z zapisanej historii przy zadanym tau.

    days_ago liczone od kickoffu (deterministycznie), nie od momentu
    przebiegu skryptu — różnica godzin względem predykcji jest pomijalna,
    a wynik nie zależy od tego, KIEDY odpalimy kalibrację.
    """
    kt = rec["kal_tau"]
    n = len(kt["hist"])
    kickoff = float(rec.get("kickoff_ts") or max(kt["ts"]))
    days_ago = np.maximum((kickoff - np.array(kt["ts"], dtype=float)) / 86400.0, 0.0)
    posterior = counts.fit_posterior(
        np.array(kt["hist"], dtype=float),
        np.array([90.0] * n),
        days_ago,
        prior=counts.GroupPrior(
            mean_per90=max(float(kt["prior"]), 0.5), pseudo_matches=4.0
        ),
        tau_days=tau,
    )
    pred = counts.predict_match(posterior, 90.0, float(kt.get("factor") or 1.0))
    p_over = pred.p_over(float(rec["linia"]))
    return p_over if rec.get("strona") == "powyzej" else 1.0 - p_over


def ocena_tau(rekordy: list[dict], tau: float) -> dict:
    """Brier i log-loss kandydata tau na rozliczonych typach."""
    brier, ll, n = 0.0, 0.0, 0
    for rec in rekordy:
        y = 1.0 if rec["wynik"] == "wygrany" else 0.0
        p = min(max(p_przy_tau(rec, tau), 1e-6), 1.0 - 1e-6)
        brier += (p - y) ** 2
        ll += -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))
        n += 1
    return {
        "tau": tau,
        "n": n,
        "brier": brier / n if n else float("nan"),
        "logloss": ll / n if n else float("nan"),
    }


def sweep(rekordy: list[dict], taus: tuple[float, ...] = TAUS) -> list[dict]:
    return [ocena_tau(rekordy, tau) for tau in taus]


def main() -> None:
    log = supa.get_key("typy_log") or {}
    rekordy = rekordy_druzynowe(log)
    print(f"Rozliczone typy drużynowe z payloadem kal_tau: {len(rekordy)}")
    if not rekordy:
        print("Payload pisze się od 2026-07-21 — wróć po kilku dniach cykli.")
        return
    wyniki = sweep(rekordy)
    najlepszy = min(wyniki, key=lambda w: w["brier"])
    print(f"{'tau (dni)':>10} {'n':>5} {'Brier':>8} {'log-loss':>9}")
    for w in wyniki:
        znak = "  <-- najlepszy" if w is najlepszy else ""
        print(
            f"{w['tau']:>10.0f} {w['n']:>5} {w['brier']:>8.4f} "
            f"{w['logloss']:>9.4f}{znak}"
        )
    if len(rekordy) < MIN_N:
        print(
            f"UWAGA: próba {len(rekordy)} < {MIN_N} — traktuj wyłącznie "
            "poglądowo, nie zmieniaj tau na tej podstawie."
        )
    else:
        obecny = next((w for w in wyniki if w["tau"] == 180.0), None)
        if obecny and najlepszy["tau"] != 180.0:
            delta = obecny["brier"] - najlepszy["brier"]
            print(
                f"Kandydat tau={najlepszy['tau']:.0f} lepszy od obecnych 180 "
                f"o {delta:.4f} Briera — zmiana ma sens przy wyraźnej "
                "przewadze (i stabilnej na rosnącej próbie)."
            )


if __name__ == "__main__":
    main()
