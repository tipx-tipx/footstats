"""Generator kuponów (AKO) z typów po analizie.

Dwa style (oba liczone co cykl):

1. PEWNIAKI (główny, wzorowany na kuponach użytkownika): legi o najwyższej
   szansie modelu — niekoniecznie value — łączone tak, by kurs łączny doszedł
   do ~10 / ~15 / ~20 / ~25 przy MAKSYMALNEJ szansie trafienia całości.
   Wybór legów zachłannie po jakości ln(p)/ln(kurs) — czyli "najmniej ryzyka
   na jednostkę kursu". Do 2 legów z jednego meczu (różni zawodnicy, jak w
   bet builderze), z karą korelacyjną do szansy kuponu.

2. VALUE: te same reguły składania (maksymalny iloczyn szans przy zadanym
   kursie = maksymalne EV kuponu), ale wyłącznie typy z WYRAŹNĄ wartością
   (EV lega >= 2%) i pewnością >= średnią, max 1 leg na mecz (zero
   korelacji) — kupon "dla zysku długoterminowego".

Wspólne: max 1 typ na zawodnika, szansa kuponu = iloczyn szans (x kara),
EV = szansa x kurs - 1. Za mało legów = brak kuponu (nie sklejamy na siłę).
"""

from __future__ import annotations

import math
import time

# przedziały kursowe — do 4 aktywnych kuponów w każdym horyzoncie (user)
PRZEDZIALY_DZIENNE = (
    (5.0, 10.0), (10.0, 15.0), (15.0, 20.0), (20.0, 25.0),
)
PRZEDZIALY_DLUGOTERMINOWE = (
    (10.0, 15.0), (15.0, 20.0), (20.0, 25.0), (25.0, 35.0),
)
PRZEDZIALY_VALUE = ((4.0, 8.0), (8.0, 16.0))
OKNO_DZIS_S = 20 * 3600       # "dziś" = mecze w ciągu ~20 h
OKNO_JUTRO_S = 44 * 3600      # rozszerzenie na jutro, gdy dziś < 2 mecze
OKNO_DLUGO_S = 4 * 86400      # długoterminowy: mecze z najbliższych 4 dni
MIN_LEG_EV = 2.0          # leg value: wyraźna przewaga w %, nie kosmetyczne 0,1
MAX_LEGI_PEWNIAKI = 12
MAX_NA_MECZ = 4           # do 4 wydarzeń z jednego meczu (jak w bet builderze)
KARA_KORELACJI = 0.95     # mnożnik szansy kuponu za KAŻDY dodatkowy leg z 1 meczu


def _kandydaci(bets: list[dict]) -> list[dict]:
    out = [
        b for b in bets
        if not b.get("sugestia")
        and b.get("kurs")
        and b.get("ev_pct") is not None
        and b["ev_pct"] >= MIN_LEG_EV
        and b.get("pewnosc") in ("wysoka", "srednia")
    ]
    out.sort(key=lambda b: -b.get("rank_score", 0.0))
    return out


def _sygnatura(kupon: dict) -> frozenset:
    """Zestaw legów kuponu — do wykrywania duplikatów między stylami."""
    return frozenset(
        (l["mecz_id"], l["podmiot"], l.get("rynek_kod", ""), l["linia"], l["strona"])
        for l in kupon["legi"]
    )


def _leg_dict(b: dict) -> dict:
    return {
        "value_bet_id": b.get("id", 0),
        "podmiot_id": b.get("podmiot_id", 0),
        "podmiot": b["podmiot"],
        "rynek_kod": b.get("rynek_kod", ""),
        "rynek": b["rynek"],
        "linia": b["linia"],
        "strona": b["strona"],
        "kurs": b["kurs"],
        "bukmacher": b.get("bukmacher", "Superbet"),
        "p_model": b["p_model"],
        "pewnosc": b.get("pewnosc", "srednia"),
        "mecz": b["mecz"],
        "mecz_id": b["mecz_id"],
        "kickoff_ts": b["kickoff_ts"],
    }


def _zloz_pewniaki(
    pool: list[dict],
    cmin: float,
    cmax: float,
    max_na_mecz: int = MAX_NA_MECZ,
    min_legi: int = 3,
) -> dict | None:
    """Maksymalizuj szansę kuponu przy kursie łącznym w przedziale [cmin, cmax].

    Jakość lega = ln(p) / ln(kurs): ile "kosztu pewności" płacimy za każdą
    jednostkę logarytmu kursu. Im bliżej zera, tym leg bezpieczniejszy
    względem tego, co dokłada do kursu. Przy ustalonym kursie łącznym
    maksymalna szansa = maksymalne EV, więc ten sam builder składa też
    kupony value (z pulą ograniczoną do legów z przewagą).
    """
    cands = sorted(
        (b for b in pool if b["kurs"] > 1.0 and 0 < b["p_model"] < 1),
        key=lambda b: -(math.log(b["p_model"]) / math.log(b["kurs"])),
    )
    kurs, p = 1.0, 1.0
    legi: list[dict] = []
    na_mecz: dict[int, int] = {}
    uzyci: set[int] = set()
    kara = 1.0
    for b in cands:
        if len(legi) >= MAX_LEGI_PEWNIAKI or kurs >= cmin:
            break
        if b["podmiot_id"] in uzyci or na_mecz.get(b["mecz_id"], 0) >= max_na_mecz:
            continue
        if kurs * b["kurs"] > cmax:
            continue  # ten leg przestrzeliłby przedział — szukaj mniejszego
        if na_mecz.get(b["mecz_id"], 0) >= 1:
            kara *= KARA_KORELACJI  # każdy dodatkowy leg z tego samego meczu
        legi.append(b)
        na_mecz[b["mecz_id"]] = na_mecz.get(b["mecz_id"], 0) + 1
        uzyci.add(b["podmiot_id"])
        kurs *= b["kurs"]
        p *= b["p_model"]
    p *= kara
    if len(legi) < min_legi or not (cmin <= kurs <= cmax):
        return None
    # legi z tego samego meczu obok siebie, mecze chronologicznie
    legi.sort(key=lambda b: (b["kickoff_ts"], b["mecz_id"], -b["p_model"]))
    return {
        "cel": int(cmin),
        "cel_label": f"{int(cmin)}–{int(cmax)}",
        "styl": "pewniaki",
        "kurs_laczny": round(kurs, 2),
        "p_model": round(p, 4),
        "fair_kurs": round(1.0 / max(p, 1e-9), 2),
        "ev_pct": round((p * kurs - 1.0) * 100.0, 1),
        "legi": [_leg_dict(b) for b in legi],
    }


def _rentgen(
    kupon: dict,
    pool: list[dict],
    cmin: float,
    cmax: float,
    max_na_mecz: int = MAX_NA_MECZ,
) -> None:
    """Rentgen kuponu (wzorzec HOF Parlay Optimizer): najsłabsze ogniwo
    + propozycja zamiany z puli, która podnosi szansę kuponu.

    Czysto doradcze — kupon pozostaje zamrożony; UI pokazuje "co by było,
    gdyby wymienić najsłabszego lega". Kurs po zamianie musi zostać
    w charakterze przedziału (>= 80% dolnej granicy, <= górna).
    """
    legi = kupon["legi"]
    idx = min(range(len(legi)), key=lambda i: legi[i]["p_model"])
    kupon["najslabszy_idx"] = idx
    slaby = legi[idx]
    kurs_bez = kupon["kurs_laczny"] / slaby["kurs"]
    p_bez = kupon["p_model"] / max(slaby["p_model"], 1e-9)
    uzyci = {l["podmiot_id"] for i, l in enumerate(legi) if i != idx}
    na_mecz: dict[int, int] = {}
    for i, l in enumerate(legi):
        if i != idx:
            na_mecz[l["mecz_id"]] = na_mecz.get(l["mecz_id"], 0) + 1
    best = None
    for b in pool:
        if b["podmiot_id"] in uzyci or b["p_model"] <= slaby["p_model"]:
            continue
        if na_mecz.get(b["mecz_id"], 0) >= max_na_mecz:
            continue
        kurs_po = kurs_bez * b["kurs"]
        if not (cmin * 0.8 <= kurs_po <= cmax):
            continue
        if best is None or b["p_model"] > best["p_model"]:
            best = b
    if best is None:
        return
    p_po = p_bez * best["p_model"]
    if p_po <= kupon["p_model"] + 1e-9:
        return
    kupon["alternatywa"] = {
        **_leg_dict(best),
        "zamiast_idx": idx,
        "kurs_po": round(kurs_bez * best["kurs"], 2),
        "p_po": round(p_po, 4),
    }


def build_kupony(
    bets: list[dict], pool: list[dict] | None = None, now_ts: int | None = None
) -> list[dict]:
    """Kupony pewniaków w dwóch horyzontach + kupony value.

    DZIENNY: mecze z dziś (gdy dziś < 2 mecze — również jutro); przedziały
    kursowe 5-10 / 10-15 / 15-20 / 20-25 (do 4 aktywnych kuponów).
    DŁUGOTERMINOWY: mecze z najbliższych 4 dni; 10-15 / 15-20 / 20-25 / 25-35.
    VALUE: przedziały 4-8 / 8-16, tylko legi z EV >= 2%, max 1 leg na mecz.
    """
    now = now_ts if now_ts is not None else int(time.time())
    pool = [b for b in (pool or []) if b["kickoff_ts"] > now - 3600]
    out: list[dict] = []

    # dzienny: każdy przedział NAJPIERW z samego "dziś"; dopiero gdy się nie
    # składa — dobiera mecze z jutra (decyzja usera)
    dzis20 = [b for b in pool if b["kickoff_ts"] <= now + OKNO_DZIS_S]
    dzis44 = [b for b in pool if b["kickoff_ts"] <= now + OKNO_JUTRO_S]
    tylko_dzis_ok = len({b["mecz_id"] for b in dzis20}) >= 2
    for cmin, cmax in PRZEDZIALY_DZIENNE:
        k = _zloz_pewniaki(dzis20, cmin, cmax) if tylko_dzis_ok else None
        pula_k = dzis20
        if k is None:
            k = _zloz_pewniaki(dzis44, cmin, cmax)
            pula_k = dzis44
        if k is not None:
            k["horyzont"] = "dzienny"
            _rentgen(k, pula_k, cmin, cmax)
            out.append(k)

    dlugo = [b for b in pool if b["kickoff_ts"] <= now + OKNO_DLUGO_S]
    for cmin, cmax in PRZEDZIALY_DLUGOTERMINOWE:
        k = _zloz_pewniaki(dlugo, cmin, cmax)
        if k is not None:
            k["horyzont"] = "dlugoterminowy"
            _rentgen(k, dlugo, cmin, cmax)
            out.append(k)

    # VALUE: ten sam builder co pewniaki (max iloczyn szans przy zadanym
    # kursie = max EV), ale pula tylko z wyraźną przewagą i 1 leg na mecz;
    # kupon identyczny z którymś kuponem pewniaków nie wchodzi drugi raz
    cands = [b for b in _kandydaci(bets) if b["kickoff_ts"] > now - 3600]
    sygnatury = {_sygnatura(k) for k in out}
    for cmin, cmax in PRZEDZIALY_VALUE:
        k = _zloz_pewniaki(cands, cmin, cmax, max_na_mecz=1, min_legi=2)
        if k is None or _sygnatura(k) in sygnatury:
            continue
        k["styl"] = "value"
        k["horyzont"] = "value"
        _rentgen(k, cands, cmin, cmax, max_na_mecz=1)
        out.append(k)
        sygnatury.add(_sygnatura(k))
    return out
