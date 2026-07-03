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

CELE = (5.0, 10.0)
CELE_PEWNIAKI = (10.0, 15.0, 20.0, 25.0)
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


def _zloz_pewniaki(pool: list[dict], cel: float) -> dict | None:
    """Maksymalizuj szansę kuponu przy kursie łącznym ~cel.

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
        if len(legi) >= MAX_LEGI_PEWNIAKI or kurs >= cel * 0.9:
            break
        if b["podmiot_id"] in uzyci or na_mecz.get(b["mecz_id"], 0) >= MAX_NA_MECZ:
            continue
        if na_mecz.get(b["mecz_id"], 0) >= 1:
            kara *= KARA_KORELACJI  # każdy dodatkowy leg z tego samego meczu
        legi.append(b)
        na_mecz[b["mecz_id"]] = na_mecz.get(b["mecz_id"], 0) + 1
        uzyci.add(b["podmiot_id"])
        kurs *= b["kurs"]
        p *= b["p_model"]
    p *= kara
    if len(legi) < 3 or not (cel * 0.85 <= kurs <= cel * 1.6):
        return None
    return {
        "cel": int(cel),
        "styl": "pewniaki",
        "kurs_laczny": round(kurs, 2),
        "p_model": round(p, 4),
        "fair_kurs": round(1.0 / max(p, 1e-9), 2),
        "ev_pct": round((p * kurs - 1.0) * 100.0, 1),
        "legi": [_leg_dict(b) for b in legi],
    }


def build_kupony(bets: list[dict], pool: list[dict] | None = None) -> list[dict]:
    """Kupony pewniaków (z puli wszystkich kwotowanych linii) + kupony value."""
    out: list[dict] = []
    for cel in CELE_PEWNIAKI:
        k = _zloz_pewniaki(pool or [], cel)
        if k is not None:
            out.append(k)
    cands = _kandydaci(bets)
    for cel in CELE:
        k = _zloz(cands, cel)
        if k is not None:
            k["styl"] = "value"
            out.append(k)
    out.sort(key=lambda k: (k["styl"] != "pewniaki", k["cel"]))
    return out
