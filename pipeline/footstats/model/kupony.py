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

from . import betting

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
# kary korelacyjne — legi z JEDNEGO meczu nie są niezależne:
KARA_KORELACJI = 0.95         # relacja drużyn nieznana (stare dane)
KARA_TA_SAMA_DRUZYNA = 0.92   # wspólny scenariusz (dominacja/tempo drużyny)
KARA_PRZECIWNE_DRUZYNY = 0.97 # słabsza zależność (bywa wręcz przeciwna)
# dywersyfikacja: kara SELEKCJI (nie szansy) za 3. i kolejny leg z tej samej
# rodziny rynków — rodziny korelują przez tempo meczu, a kupony z samych
# strzałów 0,5 padają razem w jednym nudnym meczu
DYWERSYFIKACJA_RODZIN = 0.985
BEAM_W = 60               # szerokość wiązki w składaniu kuponu


def _kara_koszyka(legi) -> float:
    """Łączna kara korelacyjna kuponu (mnożnik szansy).

    Za każdy KOLEJNY leg z tego samego meczu: ×0.92 gdy z tej samej drużyny
    co któryś już obecny, ×0.97 gdy z przeciwnej, ×0.95 gdy drużyn nie znamy.
    """
    kara = 1.0
    seen: dict[int, list[str]] = {}
    for l in legi:
        m, d = l["mecz_id"], str(l.get("druzyna") or "")
        prev = seen.get(m)
        if prev is not None:
            if d and d in prev:
                kara *= KARA_TA_SAMA_DRUZYNA
            elif d and all(x and x != d for x in prev):
                kara *= KARA_PRZECIWNE_DRUZYNY
            else:
                kara *= KARA_KORELACJI
        seen.setdefault(m, []).append(d)
    return kara


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
        "druzyna": b.get("druzyna", ""),
        "matchup": bool(b.get("matchup")),
        "rotacja": bool(b.get("rotacja")),
        "miekka_linia": bool(b.get("miekka_linia")),
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


def _score_selekcji(p_raw: float, legi) -> float:
    """Funkcja celu składania: szansa z karami korelacji + kara SELEKCJI za
    monotonię rynków (3+ legi z jednej rodziny padają razem w nudnym meczu)."""
    s = p_raw * _kara_koszyka(legi)
    rodziny: dict[str, int] = {}
    for l in legi:
        f = betting.RODZINY_RYNKOW.get(l.get("rynek_kod", ""))
        if f:
            rodziny[f] = rodziny.get(f, 0) + 1
    nadmiar = sum(max(0, c - 2) for c in rodziny.values())
    return s * (DYWERSYFIKACJA_RODZIN ** nadmiar)


def _zloz_pewniaki(
    pool: list[dict],
    cmin: float,
    cmax: float,
    max_na_mecz: int = MAX_NA_MECZ,
    min_legi: int = 3,
    profil: str = "zbalansowany",
) -> dict | None:
    """Maksymalizuj szansę kuponu przy kursie łącznym w przedziale [cmin, cmax].

    Beam search (wiązka BEAM_W stanów) zamiast zachłannego dokładania —
    przy ograniczeniach (przedział kursu, max/mecz, dywersyfikacja) greedy
    bywał daleki od optimum albo "nie składał" istniejącej kombinacji.
    Jakość lega = ln(p)/ln(kurs) (koszt pewności na jednostkę kursu) decyduje
    o kolejności kandydatów; legi kontekstowe (matchup / świeże składy)
    dostają lekki priorytet. Przy ustalonym kursie max szansa = max EV,
    więc ten sam builder składa też kupony value.
    """
    # profil charakteru (ustawienie usera): bezpieczny = same kotwice,
    # agresywny = mocniejsza preferencja matchupów i wyższych linii
    if profil == "bezpieczny":
        pool = [b for b in pool if b["p_model"] >= 0.58]

    def _q(b: dict) -> float:
        q = math.log(b["p_model"]) / math.log(b["kurs"])
        if profil != "bezpieczny":
            if b.get("matchup"):
                q *= 0.88 if profil == "agresywny" else 0.93
            if b.get("swieze_sklady"):
                q *= 0.93 if profil == "agresywny" else 0.96
            if profil == "agresywny" and (b.get("linia") or 0) >= 1.5:
                q *= 0.95   # wyższe linie wyżej w kolejce
        return q

    cands = sorted(
        (b for b in pool if b["kurs"] > 1.0 and 0 < b["p_model"] < 1),
        key=lambda b: -_q(b),
    )[:80]
    # stan wiązki: (kurs_łączny, iloczyn_p, legi jako krotka)
    beam: list[tuple[float, float, tuple]] = [(1.0, 1.0, ())]
    komplety: list[tuple[float, float, tuple]] = []
    for b in cands:
        nowe = []
        for kurs, p, legi in beam:
            if len(legi) >= MAX_LEGI_PEWNIAKI:
                continue
            if any(l["podmiot_id"] == b["podmiot_id"] for l in legi):
                continue
            if sum(1 for l in legi if l["mecz_id"] == b["mecz_id"]) >= max_na_mecz:
                continue
            kurs2 = kurs * b["kurs"]
            if kurs2 > cmax:
                continue
            legi2 = legi + (b,)
            p2 = p * b["p_model"]
            nowe.append((kurs2, p2, legi2))
            if kurs2 >= cmin and len(legi2) >= min_legi:
                komplety.append((kurs2, p2, legi2))
        beam.extend(nowe)
        # prune: obiecujące = wysoka szansa × jak blisko dolnej granicy kursu;
        # dedup równoważnych stanów (permutacje identycznych legów zapychałyby
        # wiązkę i blokowały dojście do dłuższych kuponów)
        ocenione = []
        seen_keys: set = set()
        for st in beam:
            sc = _score_selekcji(st[1], st[2])
            key = (len(st[2]), round(st[0], 4), round(sc, 8))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            ocenione.append((sc * min(st[0] / cmin, 1.0), st))
        ocenione.sort(key=lambda x: -x[0])
        beam = [st for _, st in ocenione[:BEAM_W]]
    if not komplety:
        return None

    def _kupon_z(kurs: float, p_raw: float, legi_t: tuple) -> dict:
        p = p_raw * _kara_koszyka(legi_t)
        legi = sorted(
            legi_t, key=lambda b: (b["kickoff_ts"], b["mecz_id"], -b["p_model"])
        )
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

    komplety.sort(key=lambda s: -_score_selekcji(s[1], s[2]))
    kurs, p_raw, legi_t = komplety[0]
    kupon = _kupon_z(kurs, p_raw, legi_t)
    # wariant B: najlepszy WYRAŹNIE INNY komplet (Jaccard < 0.5) — do wyboru
    # przez usera; czysto podglądowy, nie zajmuje slotu
    sygn_a = {
        (l["mecz_id"], l["podmiot_id"], l.get("rynek_kod", ""), l["linia"])
        for l in legi_t
    }
    for kurs_b, p_b, legi_b in komplety[1:]:
        sygn_b = {
            (l["mecz_id"], l["podmiot_id"], l.get("rynek_kod", ""), l["linia"])
            for l in legi_b
        }
        if len(sygn_a & sygn_b) / max(len(sygn_a | sygn_b), 1) < 0.5:
            kupon["wariant_b"] = _kupon_z(kurs_b, p_b, legi_b)
            break
    return kupon


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
    # p kuponu zawiera karę korelacyjną — zamiana lega może ją zmienić
    # (np. replacement dokłada drugiego lega z meczu, który już ma jeden)
    legi_po = [l for i, l in enumerate(legi) if i != idx] + [best]
    p_po = (
        p_bez * best["p_model"]
        * _kara_koszyka(legi_po) / max(_kara_koszyka(legi), 1e-9)
    )
    if p_po <= kupon["p_model"] + 1e-9:
        return
    kupon["alternatywa"] = {
        **_leg_dict(best),
        "zamiast_idx": idx,
        "kurs_po": round(kurs_bez * best["kurs"], 2),
        "p_po": round(p_po, 4),
    }


def _dolozenie(
    kupon: dict,
    pool: list[dict],
    cmin: float,
    cmax: float,
    max_na_mecz: int = MAX_NA_MECZ,
) -> None:
    """Rentgen v2: kupon wisi w dolnej połowie przedziału — zaproponuj
    DOŁOŻENIE bardzo pewnego lega (p >= 0.70), który dobija kurs bliżej
    górnej granicy przy niewielkiej utracie szansy. Czysto doradcze."""
    if kupon["kurs_laczny"] >= (cmin + cmax) / 2.0:
        return
    legi = kupon["legi"]
    uzyci = {l["podmiot_id"] for l in legi}
    best = None
    for b in pool:
        if b["podmiot_id"] in uzyci or b["p_model"] < 0.70:
            continue
        if sum(1 for l in legi if l["mecz_id"] == b["mecz_id"]) >= max_na_mecz:
            continue
        if kupon["kurs_laczny"] * b["kurs"] > cmax:
            continue
        if best is None or b["p_model"] > best["p_model"]:
            best = b
    if best is None:
        return
    legi_po = list(legi) + [best]
    p_raw = kupon["p_model"] / max(_kara_koszyka(legi), 1e-9)
    p_po = p_raw * best["p_model"] * _kara_koszyka(legi_po)
    kupon["dolozenie"] = {
        **_leg_dict(best),
        "kurs_po": round(kupon["kurs_laczny"] * best["kurs"], 2),
        "p_po": round(p_po, 4),
    }


def build_kupony(
    bets: list[dict],
    pool: list[dict] | None = None,
    now_ts: int | None = None,
    profil: str = "zbalansowany",
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
        k = (
            _zloz_pewniaki(dzis20, cmin, cmax, profil=profil)
            if tylko_dzis_ok else None
        )
        pula_k = dzis20
        if k is None:
            k = _zloz_pewniaki(dzis44, cmin, cmax, profil=profil)
            pula_k = dzis44
        if k is not None:
            k["horyzont"] = "dzienny"
            _rentgen(k, pula_k, cmin, cmax)
            _dolozenie(k, pula_k, cmin, cmax)
            out.append(k)

    dlugo = [b for b in pool if b["kickoff_ts"] <= now + OKNO_DLUGO_S]
    for cmin, cmax in PRZEDZIALY_DLUGOTERMINOWE:
        k = _zloz_pewniaki(dlugo, cmin, cmax, profil=profil)
        if k is not None:
            k["horyzont"] = "dlugoterminowy"
            _rentgen(k, dlugo, cmin, cmax)
            _dolozenie(k, dlugo, cmin, cmax)
            out.append(k)

    # VALUE: ten sam builder co pewniaki (max iloczyn szans przy zadanym
    # kursie = max EV), ale pula tylko z wyraźną przewagą i 1 leg na mecz;
    # kupon identyczny z którymś kuponem pewniaków nie wchodzi drugi raz
    cands = [b for b in _kandydaci(bets) if b["kickoff_ts"] > now - 3600]
    sygnatury = {_sygnatura(k) for k in out}
    for cmin, cmax in PRZEDZIALY_VALUE:
        k = _zloz_pewniaki(
            cands, cmin, cmax, max_na_mecz=1, min_legi=2, profil=profil
        )
        if k is None or _sygnatura(k) in sygnatury:
            continue
        k["styl"] = "value"
        k["horyzont"] = "value"
        _rentgen(k, cands, cmin, cmax, max_na_mecz=1)
        _dolozenie(k, cands, cmin, cmax, max_na_mecz=1)
        out.append(k)
        sygnatury.add(_sygnatura(k))
    return out
