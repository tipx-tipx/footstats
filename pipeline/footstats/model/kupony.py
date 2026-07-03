"""Generator kuponów (AKO) z typów po analizie.

Dwa style (oba liczone co cykl):

1. PEWNIAKI (główny, wzorowany na kuponach użytkownika): legi o najwyższej
   szansie modelu — niekoniecznie value — łączone tak, by kurs łączny doszedł
   do ~10 / ~15 / ~20 / ~25 przy MAKSYMALNEJ szansie trafienia całości.
   Wybór legów zachłannie po jakości ln(p)/ln(kurs) — czyli "najmniej ryzyka
   na jednostkę kursu". Do 2 legów z jednego meczu (różni zawodnicy, jak w
   bet builderze), z karą korelacyjną do szansy kuponu.

2. VALUE: tylko typy z dodatnią wartością i pewnością >= średnią, cele ~5/~10,
   max 1 leg na mecz — kupon "dla zysku długoterminowego".

Wspólne: max 1 typ na zawodnika, szansa kuponu = iloczyn szans (x kara),
EV = szansa x kurs - 1. Za mało legów = brak kuponu (nie sklejamy na siłę).
"""

from __future__ import annotations

import math
import time

CELE = (5.0, 10.0)
# przedziały kursowe (user: "nie muszą być dokładnie, np. od 5 do 10, od 10 do 15")
PRZEDZIALY_DZIENNE = ((5.0, 10.0), (10.0, 15.0), (15.0, 20.0), (20.0, 25.0))
PRZEDZIALY_DLUGOTERMINOWE = ((10.0, 15.0), (15.0, 20.0), (20.0, 25.0), (25.0, 35.0))
OKNO_DZIS_S = 20 * 3600       # "dziś" = mecze w ciągu ~20 h
OKNO_JUTRO_S = 44 * 3600      # rozszerzenie na jutro, gdy dziś < 2 mecze
OKNO_DLUGO_S = 4 * 86400      # długoterminowy: mecze z najbliższych 4 dni
MIN_LEG_EV = 0.0          # leg value musi mieć nieujemną wartość
MAX_LEGI = 8
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


def _zloz(cands: list[dict], cel: float) -> dict | None:
    kurs, p = 1.0, 1.0
    legi: list[dict] = []
    uzyte_mecze: set[int] = set()
    uzyci: set[int] = set()
    for b in cands:
        if len(legi) >= MAX_LEGI or kurs >= cel * 0.85:
            break
        if b["mecz_id"] in uzyte_mecze or b["podmiot_id"] in uzyci:
            continue
        legi.append(b)
        uzyte_mecze.add(b["mecz_id"])
        uzyci.add(b["podmiot_id"])
        kurs *= b["kurs"]
        p *= b["p_model"]
    if len(legi) < 2 or not (cel * 0.85 <= kurs <= cel * 1.6):
        return None
    legi.sort(key=lambda b: (b["kickoff_ts"], b["mecz_id"]))
    return {
        "cel": int(cel),
        "kurs_laczny": round(kurs, 2),
        "p_model": round(p, 4),
        "fair_kurs": round(1.0 / max(p, 1e-9), 2),
        "ev_pct": round((p * kurs - 1.0) * 100.0, 1),
        "legi": [
            {
                "value_bet_id": b["id"],
                "podmiot": b["podmiot"],
                "rynek": b["rynek"],
                "linia": b["linia"],
                "strona": b["strona"],
                "kurs": b["kurs"],
                "bukmacher": b["bukmacher"],
                "p_model": b["p_model"],
                "pewnosc": b["pewnosc"],
                "mecz": b["mecz"],
                "mecz_id": b["mecz_id"],
                "kickoff_ts": b["kickoff_ts"],
            }
            for b in legi
        ],
    }


def _leg_dict(b: dict) -> dict:
    return {
        "value_bet_id": b.get("id", 0),
        "podmiot": b["podmiot"],
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


def _zloz_pewniaki(pool: list[dict], cmin: float, cmax: float) -> dict | None:
    """Maksymalizuj szansę kuponu przy kursie łącznym w przedziale [cmin, cmax].

    Jakość lega = ln(p) / ln(kurs): ile "kosztu pewności" płacimy za każdą
    jednostkę logarytmu kursu. Im bliżej zera, tym leg bezpieczniejszy
    względem tego, co dokłada do kursu.
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
        if b["podmiot_id"] in uzyci or na_mecz.get(b["mecz_id"], 0) >= MAX_NA_MECZ:
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
    if len(legi) < 3 or not (cmin <= kurs <= cmax):
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


def build_kupony(
    bets: list[dict], pool: list[dict] | None = None, now_ts: int | None = None
) -> list[dict]:
    """Kupony pewniaków w dwóch horyzontach + kupony value.

    DZIENNY: mecze z dziś (gdy dziś < 2 mecze — również jutro); przedziały
    kursowe 5-10 / 10-15 / 15-20 / 20-25.
    DŁUGOTERMINOWY: mecze z najbliższych 4 dni; przedziały od 10-15 do 25-35.
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
        if k is None:
            k = _zloz_pewniaki(dzis44, cmin, cmax)
        if k is not None:
            k["horyzont"] = "dzienny"
            out.append(k)

    dlugo = [b for b in pool if b["kickoff_ts"] <= now + OKNO_DLUGO_S]
    for cmin, cmax in PRZEDZIALY_DLUGOTERMINOWE:
        k = _zloz_pewniaki(dlugo, cmin, cmax)
        if k is not None:
            k["horyzont"] = "dlugoterminowy"
            out.append(k)

    cands = _kandydaci(bets)
    for cel in CELE:
        k = _zloz(cands, cel)
        if k is not None:
            k["styl"] = "value"
            k["horyzont"] = "value"
            k["cel_label"] = f"~{int(cel)}"
            out.append(k)
    return out
