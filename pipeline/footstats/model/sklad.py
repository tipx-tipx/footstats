"""Własne przewidywanie składu — „pewność startu” zawodnika (2026-10-18).

⚑ SKĄD TO SIĘ WZIĘŁO. Właściciel 18.10: „składy mają potwierdzać typy, a nie
że się opierać na potwierdzonym składzie — musimy przewidywać jak najlepiej
składy i na tym się opierać”. Dzisiejszy sygnał to tak/nie z hierarchii
źródeł (statshub > Rotowire > SportsGambler) i jest słaby: statshub, który stoi
najwyżej, trafia najgorzej, a 20–28% zawodników „poza przewidywanym XI”
wychodzi w pierwszym składzie (pomiar_skladow 06–18.10, 662 mecze).

Model: dwa etapy regresji logistycznej (numpy, bez nowych zależności).
  1. historia klubu: starty i minuty w 5/10 ostatnich meczach DRUŻYNY, start
     w ostatnim i przedostatnim, puchar (rozgrywki ≠ liga domowa), starty
     w meczach tej samej klasy (liga/puchar — to łapie rotację);
  2. logit(historia) + źródła dostępne w cyklu: statshub (przewidywany XI,
     gdy jest) i Rotowire-albo-SportsGambler (jak `dolacz_do_rotowire`).

Pomiar (89 661 par zawodnik–mecz 01.09–18.10, bank trendów; uczenie < 13.10,
test 13–18.10, 3293 pary z pomiarem źródeł): dzisiejsza hierarchia Brier
0,190 / AUC 0,752, sama historia 0,213 / 0,752, model 0,164 / 0,830; przy
pewności ≥ 0,90 wyszło 90,5% (18% zawodników), ≥ 0,80 — 86,4% (36%).
W pucharach dzisiejszy sygnał AUC 0,53 (zgadywanie), model 0,62.
Skrypty: scratchpad sesji 18.10 (xi_zbior.py, xi_model.py, xi_wagi.py).

⚑ NA RAZIE W CIENIU: liczba trafia do księgi (`p_start`), nic nie decyduje.
Po ~tygodniu żywych meczów porównanie z `xi_sygnal` i dopiero wtedy
przełączenie bramek składu i minut. Etykieta uczenia (start z banku) nie jest
czysta — nawet przy ogłoszonym składzie bank pokazuje start w 90,8% — więc
liczby porównywać między sobą, nie ze 100%.
"""
from __future__ import annotations

import math
from collections import Counter

WERSJA = "2026-10-18-v1"
ODSTEP_S = 3 * 3600          # mecz ± 3 h = ten sam mecz (występ zawodnika vs kalendarz)
MIN_MECZOW_DRUZYNY = 5

# wagi z xi_wagi.py (dopasowanie na całości): [stała, cechy...]
WAGI = {
    "start": {
        "hist": [-1.1221, -1.4627, -0.2053, -2.3773, 0.9272, 0.3773, 0.564, 4.5081,
                 0.4652, -0.0014, 0.5253, 1.6747, -1.2902, 0.301, -0.7157, -1.3487],
        "zrodla": [0.1549, 0.6024, 0.2244, 1.2794, -0.2574, 0.0784],
    },
    "60": {
        "hist": [-1.261, -2.6693, 0.0637, -2.1584, 0.8862, 0.332, 0.506, 4.4039,
                 1.5632, 0.0404, 0.518, 1.5837, -1.317, 0.3013, -0.6821, -1.2288],
        "zrodla": [0.1653, 0.6139, 0.2092, 1.2584, -0.2156, 0.052],
    },
}


def cechy_historii(mecze_druzyny: list[dict], wystepy: list[tuple[int, float, bool]],
                   liga_meczu: int | None = None) -> list[float] | None:
    """Cechy etapu 1 (kolejność jak w xi_logit.py).

    `mecze_druzyny`: ostatnie mecze drużyny przed meczem, najnowszy pierwszy
    ({"t": start, "l": rozgrywki} — `argumenty.Indeks.przed`), `wystepy`:
    (start, minuty, wyszedł w XI) zawodnika. None = za mało meczów drużyny
    albo zawodnik nie grał w żadnym z 5 ostatnich (nie wiemy, czy jest w kadrze).
    """
    prev = [m for m in mecze_druzyny if m.get("t")][:10]
    if len(prev) < MIN_MECZOW_DRUZYNY:
        return None
    hist = []
    for m in prev:
        t = int(m["t"])
        h = next(((mi, st) for ts, mi, st in wystepy if abs(int(ts) - t) < ODSTEP_S), None)
        hist.append(h)
    if not any(hist[:5]):
        return None
    ligi = Counter(m.get("l") for m in prev if m.get("l"))
    ld = ligi.most_common(1)[0][0] if ligi else None
    puchar = 1.0 if (liga_meczu and ld and int(liga_meczu) != int(ld)) else 0.0
    prev_puchar = 1.0 if (prev[0].get("l") and ld and prev[0].get("l") != ld) else 0.0
    s5 = sum(1 for h in hist[:5] if h and h[1]) / 5
    s10 = sum(1 for h in hist if h and h[1]) / len(hist)
    a5 = sum(1 for h in hist[:5] if h) / 5
    st1 = 1.0 if (hist[0] and hist[0][1]) else 0.0
    st2 = 1.0 if (len(hist) > 1 and hist[1] and hist[1][1]) else 0.0
    gr1 = 1.0 if hist[0] else 0.0
    m5 = sum(h[0] for h in hist[:5] if h) / 5
    m60_5 = sum(1 for h in hist[:5] if h and h[0] >= 60) / 5
    same = [h for m, h in zip(prev, hist) if ((m.get("l") != ld) == bool(puchar))][:5]
    ss = (sum(1 for h in same if h and h[1]) / len(same)) if same else s5
    return [s5, s10, a5, st1, st2, gr1, m5 / 90, m60_5, puchar, prev_puchar, ss,
            puchar * s5, puchar * ss, prev_puchar * st1, s5 ** 2]


def _sig(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def pewnosc(cechy: list[float], statshub: bool | None = None,
            rotowire: bool | None = None, cel: str = "start") -> dict:
    """{"p": pewność (start albo ≥ 60 min), "h": sama historia}.
    `statshub` / `rotowire`: True = w przewidywanym XI, False = poza, None = źródło
    milczy (Rotowire = Rotowire albo SportsGambler, jak w cyklu)."""
    w = WAGI[cel]
    ph = _sig(w["hist"][0] + sum(a * b for a, b in zip(w["hist"][1:], cechy)))
    if statshub is None and rotowire is None:
        # żadne źródło nic nie mówi — etap 2 uczył się tylko na meczach ze
        # źródłami, więc tu zostaje sama historia (uczona na wszystkich meczach)
        return {"p": round(ph, 3), "h": round(ph, 3)}
    sh = 0.0 if statshub is None else (1.0 if statshub else -1.0)
    rs = 0.0 if rotowire is None else (1.0 if rotowire else -1.0)
    zgoda_tak = 1.0 if (statshub is True and rotowire is True) else 0.0
    zgoda_nie = 1.0 if (statshub is False and rotowire is False) else 0.0
    z = w["zrodla"]
    p = _sig(z[0] + z[1] * _logit(ph) + z[2] * sh + z[3] * rs + z[4] * zgoda_tak + z[5] * zgoda_nie)
    return {"p": round(p, 3), "h": round(ph, 3)}


def stempel(mecze_druzyny, wystepy, liga_meczu, statshub, rotowire) -> dict | None:
    """Stempel do księgi: {"s": pewność startu, "60": ≥ 60 min, "h": historia,
    "zr": [statshub, rotowire], "v": wersja}. None = brak historii."""
    c = cechy_historii(mecze_druzyny, wystepy, liga_meczu)
    if c is None:
        return None
    s = pewnosc(c, statshub, rotowire, "start")
    m = pewnosc(c, statshub, rotowire, "60")
    return {"s": s["p"], "60": m["p"], "h": s["h"],
            "zr": [statshub, rotowire], "v": WERSJA}
