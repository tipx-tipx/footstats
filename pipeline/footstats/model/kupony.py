"""Generator kuponów (AKO) z typów po analizie.

Cel: kupony o łącznym kursie ~5 / ~10 / ~15 / ~20 zbudowane z pojedynczych
typów z wartością, tak żeby ŁĄCZNA wartość kuponu była jak najwyższa.

Zasady bezpieczeństwa:
  * tylko typy z kursem i EV >= 0 oraz pewnością co najmniej średnią,
  * maksymalnie JEDEN typ z danego meczu (wyniki w meczu są skorelowane —
    iloczyn prawdopodobieństw kłamie, gdy legi zależą od siebie),
  * maksymalnie jeden typ na zawodnika,
  * szansa kuponu = iloczyn szans modelu, EV = szansa x kurs łączny - 1.

Budowa zachłanna: legi w kolejności rankingu (wartość x pewność), dokładamy
aż kurs łączny wpadnie w widełki celu [0.85x, 1.6x]. Za mało legów = brak
kuponu (nie sklejamy śmieci na siłę).
"""

from __future__ import annotations

CELE = (5.0, 10.0, 15.0, 20.0)
MIN_LEG_EV = 0.0          # leg musi mieć nieujemną wartość
MAX_LEGI = 8


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


def build_kupony(bets: list[dict]) -> list[dict]:
    """Zbuduj kupony dla celów 5/10/15/20 (pomija cele nieosiągalne)."""
    cands = _kandydaci(bets)
    out = []
    for cel in CELE:
        k = _zloz(cands, cel)
        if k is not None:
            out.append(k)
    return out
