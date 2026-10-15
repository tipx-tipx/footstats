# -*- coding: utf-8 -*-
"""SIŁA KLUBU Z WYNIKÓW — ranking typu Elo z poziomem ligi (2026-10-15).

⚑ PO CO (właściciel 15.10: „od wtorku gorzej”, Osimhen i Bardakci na
Barcelonę, Andre Luiz przy kursie 10 na rywala). Model uczony liczył λ
z formy drużyny i z tego, ile rywal dopuszcza W SWOJEJ lidze — nie wiedział,
kto w meczu jest faworytem. Zmierzone na księdze od 01.09: typy ataku „pod
prąd” przebiegu meczu model wyceniał na 59%, a wchodziło 50% (n=6655).

JAK: R(drużyna) = L[liga krajowa] + W[drużyna]. Mecz w obrębie ligi rusza
tylko W obu drużyn; mecz międzyligowy (puchary, sparingi) rusza też L —
dzięki temu poziom lig wynika z wyników pucharów, a nie z założenia.
Liga krajowa = najczęstsze rozgrywki drużyny w magazynie. Wynik z bramkami
(mnożnik różnicy goli jak w World Football Elo), przewaga gospodarza 60 pkt.

PARAMETRY Z POMIARU (magazyn 06.10, 54,8 tys. meczów, ocena od 15.08 na
7145 meczach, błąd kwadratowy oczekiwanego wyniku; „bez siły” 0,1916):
    K=20, BETA=0,0 → 0,1777     K=20, BETA=0,5 → 0,1665
    K=15, BETA=0,5 → 0,1678     K=30, BETA=0,5 → 0,1661
Bez poziomu ligi (BETA=0) ranking jest wyraźnie gorszy — to on niesie
różnicę między ligami. 30 ≈ 20, zostaje 20 (spokojniejszy).
Zgodność z kursami 1X2: w 2026 z 2043 wyraźnych przypadków siła wskazuje tego
samego faworyta co mnożnik scenariusza z kursów Superbetu.

⚑ CO TO JEST, A CO NIE: to CECHA modelu (sport), nie cena. Kursów do modelu
nie wpuszczamy (decyzja właściciela 17.08) — ranking liczy się wyłącznie
z wyników w magazynie.
"""
from __future__ import annotations

import bisect
from collections import Counter, defaultdict

K = 20.0
BETA = 0.5
PRZEWAGA_DOMU = 60.0
SKALA = 400.0


def klucz_meczu(m: dict, tid) -> object:
    """Ten sam mecz widziany z obu stron ma ten sam klucz."""
    if m.get("e"):
        return m["e"]
    return (int(m.get("t") or 0), tuple(sorted((str(tid), str(m.get("o"))))))


def _mecze(serie: dict[str, list]) -> list[tuple]:
    """Unikalne rozegrane mecze: (t, klucz, gosp, gość, gole_g, gole_go, liga)."""
    out: dict = {}
    for tid, mecze in serie.items():
        for m in mecze:
            if m.get("g") is None or m.get("gp") is None or m.get("o") is None:
                continue
            k = klucz_meczu(m, tid)
            if k in out:
                continue
            if int(m.get("h") or 0) == 1:
                out[k] = (int(m["t"]), k, str(tid), str(m["o"]), m["g"], m["gp"], m.get("l"))
            else:
                out[k] = (int(m["t"]), k, str(m["o"]), str(tid), m["gp"], m["g"], m.get("l"))
    return sorted(out.values(), key=lambda x: (x[0], str(x[1])))


def licz(serie: dict[str, list]) -> dict:
    """Ranking z całego magazynu.

    Zwraca:
      `przed`  {klucz meczu: (gosp, gość, R_gosp, R_gość)} — siła PRZED meczem
               (do wierszy treningowych, bez przecieku z wyniku),
      `R`      {drużyna: siła teraz} — do nadchodzących meczów,
      `hist`   {drużyna: ([t], [R po meczu])} — siła na dowolną chwilę,
      `ost_t`  czas ostatniego meczu w magazynie.
    """
    mecze = _mecze(serie)
    ile = defaultdict(Counter)
    for t, k, h, a, gh, ga, l in mecze:
        ile[h][l] += 1
        ile[a][l] += 1
    dom = {d: c.most_common(1)[0][0] for d, c in ile.items()}
    L: dict = defaultdict(float)
    W: dict = defaultdict(float)
    przed, hist = {}, defaultdict(lambda: ([], []))
    for t, k, h, a, gh, ga, l in mecze:
        lh, la = dom.get(h), dom.get(a)
        rh, ra = L[lh] + W[h], L[la] + W[a]
        przed[k] = (h, a, rh, ra)
        oczek = 1.0 / (1.0 + 10 ** (-(rh + PRZEWAGA_DOMU - ra) / SKALA))
        wynik = 1.0 if gh > ga else (0.5 if gh == ga else 0.0)
        roz = abs(gh - ga)
        mn = 1.0 if roz <= 1 else (1.5 if roz == 2 else (11 + roz) / 8.0)
        d = K * mn * (wynik - oczek)
        if lh == la:
            W[h] += d
            W[a] -= d
        else:
            W[h] += d * (1 - BETA)
            W[a] -= d * (1 - BETA)
            L[lh] += d * BETA
            L[la] -= d * BETA
        for dr, lg in ((h, lh), (a, la)):
            hist[dr][0].append(t)
            hist[dr][1].append(L[lg] + W[dr])
    return {
        "przed": przed,
        "R": {d: L[dom[d]] + W[d] for d in dom},
        "hist": dict(hist),
        "ost_t": mecze[-1][0] if mecze else 0,
    }


def sila_na(stan: dict, druzyna, do_ts: int | None) -> float | None:
    """Siła drużyny przed chwilą `do_ts` (None = drużyny nie ma w rankingu).

    Mecz po ostatnim w magazynie (czyli każdy nadchodzący) bierze siłę
    bieżącą — z poziomem ligi przesuniętym przez puchary innych drużyn,
    dokładnie jak wiersz treningowy. Chwila w przeszłości bierze siłę po
    ostatnim WŁASNYM meczu sprzed niej (bez przecieku z przyszłości).
    """
    d = str(druzyna)
    if not stan or d not in (stan.get("R") or {}):
        return None
    if do_ts is None or int(do_ts) > int(stan.get("ost_t") or 0):
        return float(stan["R"][d])
    czasy, wart = stan["hist"][d]
    i = bisect.bisect_left(czasy, int(do_ts)) - 1
    return float(wart[i]) if i >= 0 else 0.0


# ⚑ OBCIĘCIE DO ZAKRESU TRENINGU. Wiersze treningowe (rozgrywki z zakresu)
# mają różnicę w ±0,93 na 99,8% (kwantyle 0,1% / 99,9%: −0,93 / +0,94), ale
# nadchodzący mecz pucharowy potrafi dać 3,0 (czołówka Premier League
# z najsłabszą ligą rankingu) — a cecha wchodzi do log λ liniowo, więc bez
# obcięcia sprawdzenie 15.10 dało 45,6 strzałów drużyny. Poza zakresem
# treningu model nie wie nic, więc nie ekstrapolujemy.
MAX_ROZNICY = 1.0


def roznica(r_druzyny: float | None, r_rywala: float | None,
            dom: int | bool) -> float | None:
    """Cecha modelu: (siła − siła rywala ± przewaga domu) / 400, w ±1."""
    if r_druzyny is None or r_rywala is None:
        return None
    s = (float(r_druzyny) - float(r_rywala)
         + (PRZEWAGA_DOMU if dom else -PRZEWAGA_DOMU)) / SKALA
    return max(-MAX_ROZNICY, min(MAX_ROZNICY, s))
