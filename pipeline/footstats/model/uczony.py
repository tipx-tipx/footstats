# -*- coding: utf-8 -*-
"""MODEL UCZONY NA DANYCH — jeden rachunek zamiast formuły i dziesięciu warstw.

⚑ PO CO TO ISTNIEJE (zadanie właściciela 2026-08-17: „chcę prosty system
z prostym modelem, dobrze nauczonym — nie wiem, czy on się w ogóle uczy").

Nie uczył się. Dzisiejszy rachunek to λ ze średnich historycznych pomnożona
przez pięć mnożników WPISANYCH RĘCZNIE (rywal, sędzia, dom/wyjazd, tempo,
matchup) — ani jeden parametr nie pochodzi z danych. Uczyło się dziesięć
warstw korekt NA JEGO WYJŚCIU, a każda poprawiała jedno i psuła drugie.

Zmierzone na 4398 rozliczonych typach, które faktycznie poszły na stronę
(model trenowany wyłącznie na danych starszych, pełne liczby
w `docs/model-uczony-pomiar.md`):

                       deklaruje   weszło    luka       Brier
    DZIŚ (produkcja)     65,1%     50,6%   −14,4 pp    0,2434
    MODEL UCZONY         51,4%     50,6%    −0,7 pp    0,2291

Ta sama luka, którą dziesięć warstw ścigało tygodniami, znika w jednym kroku.

## JAK TO DZIAŁA

Regresja Poissona na liczbę zdarzeń: `log λ = β · cechy`. Cechy WYŁĄCZNIE
z meczów wcześniejszych — własne średnie w oknach, koncesje rywala zmierzone
z JEGO meczów, średnia ligi, dom/wyjazd i statystyki powiązane mechanicznie
(dośrodkowania i wejścia w tercję rodzą rożne, posiadanie rodzi jedno
i drugie). Z λ liczymy `P(powyżej linii)` z rozkładu.

`numpy` + `scipy` wystarczają (IRLS z karą L2) — `sklearn` NIE jest w produkcji
i nie musi być. Trening idzie osobnym jobem raz na dobę, wagi lądują w Supabase,
a cykl tylko mnoży macierze.

## CZEGO TU CELOWO NIE MA

* **KURSU** — decyzja właściciela 17.08. Model liczy sport, cena służy wyłącznie
  do wyboru, czy warto grać. Tylko tak da się uczciwie zmierzyć, czy bijemy
  rynek: dziś kurs wchodzi do prognozy i rusza ją o 41%.
* **Mnożników wpisanych ręcznie** — jeśli sędzia albo tempo mają znaczenie,
  wyjdzie to z danych jako współczynnik. Jeśli nie wyjdzie, nie mają.
* **Zgadywania przy braku danych** — drużyna bez historii nie dostaje prognozy
  (`None`), a nie prognozy ze średniej ligi udającej pomiar.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict

import numpy as np

WERSJA_MODELU_UCZONEGO = "2026-08-17-uczony-1"
KLUCZ_WAG = "model_wagi"

# ------------------------------------------------------------------- cele ----
# kod statystyki w magazynie -> kod rynku produktu
CELE = {
    "cor": "team_corners",
    "sh": "team_shots",
    "sot": "team_sot",
    "crd": "team_cards",
    "fol": "team_fouls",
    "gole": "team_goals",
}
RYNEK_NA_KOD = {v: k for k, v in CELE.items()}

# statystyki, których średnie idą jako cechy pomocnicze
POMOCNICZE = ("pos", "crs", "f3", "box", "ins", "out", "off", "tck", "int", "xg")

# cechy wchodzące przez logarytm (wszystkie są liczbami zdarzeń albo udziałami)
#
# ⚑ CELOWO BEZ `w3` I `opp6` (2026-08-17, po pierwszym treningu). Średnie
# z okien 3/6/12 to liczby z zagnieżdżonych okien, czyli prawie ta sama
# informacja trzy razy. Skutek było widać w wagach: `log_w6` dostawało +0,09
# przy kartkach (własna forma prawie bez wpływu), a flagi braków +0,49
# i −0,45 kompensowały się nawzajem. Model nie „nie widział" formy — miał ją
# rozsmarowaną po trzech skorelowanych kolumnach i po flagach.
#
# Zostają: DŁUGIE okno (poziom drużyny) i KRÓTKIE jako osobna cecha trendu,
# liczona jako różnica logarytmów — bo „ostatnio lepiej niż zwykle" to inna
# informacja niż sam poziom.
CECHY_LOG = ["w6", "w12", "w_dom", "opp12", "liga"] + [
    f"p_{p}" for p in POMOCNICZE
]
# cechy wchodzące wprost (bez logarytmu)
CECHY_LIN = ["dom", "trend", "brak_rywala"]

# Ile meczów historii musi być, żeby wiersz w ogóle powstał. Poniżej tego
# własna średnia jest szumem, a model nauczyłby się, że „mało historii"
# znaczy tyle samo co „słaba drużyna".
MIN_HISTORII = 4
# Kara L2 w IRLS. 2,0 wyszło z pomiaru — przy 0 model przeuczał się na
# rynkach o mniejszej próbie (faule, strzały).
RIDGE = 2.0
# Poniżej tylu wierszy nie trenujemy rynku wcale — cisza znaczy „nie wiemy",
# nie „zero" ([[ciche-odrzucenia-zasada]]).
MIN_WIERSZY_RYNKU = 800


# --------------------------------------------------------- cechy z magazynu --
def _wartosc(mecz: dict, kod: str, wlasne: bool = True):
    """Liczba zdarzeń w meczu — `None` gdy źródło jej nie podało."""
    if kod == "gole":
        return mecz.get("g" if wlasne else "gp")
    return (mecz.get("s" if wlasne else "sp") or {}).get(kod)


def _sr(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return float(np.mean(xs)) if xs else None


def _serie(mag: dict) -> dict[str, list]:
    """{team_id: mecze posortowane po czasie} — bez pola technicznego `_braki`."""
    serie = {}
    for tid, rec in mag.items():
        if tid == "_braki" or not isinstance(rec, dict):
            continue
        mecze = list(rec.get("m") or [])
        mecze.sort(key=lambda m: m.get("t") or 0)
        serie[str(tid)] = mecze
    return serie


def srednie_ligowe(serie: dict[str, list], min_n: int = 20) -> dict:
    """{(liga, kod): średnia} — punkt odniesienia dla drużyny bez historii."""
    zbior: dict = defaultdict(list)
    for mecze in serie.values():
        for m in mecze:
            for kod in CELE:
                v = _wartosc(m, kod)
                if v is not None:
                    zbior[(m.get("l"), kod)].append(float(v))
    return {k: float(np.mean(v)) for k, v in zbior.items() if len(v) >= min_n}


def cechy_wiersza(kod: str, hist: list[dict], opp_hist: list[dict],
                  dom: int, liga_sr: float | None) -> dict | None:
    """Cechy dla jednego (mecz, drużyna, rynek) — WYŁĄCZNIE z przeszłości.

    `hist` to mecze naszej drużyny sprzed tego meczu, `opp_hist` — mecze rywala
    sprzed tego meczu (z nich bierzemy, ile w tym rynku DOPUSZCZA).
    """
    wlasne = [_wartosc(h, kod) for h in hist]
    w6 = _sr(wlasne[-6:])
    if w6 is None:
        return None
    w3 = _sr(wlasne[-3:])
    w12 = _sr(wlasne[-12:])
    hist_dom = [h for h in hist if int(h.get("h") or 0) == dom]
    opp12 = _sr([_wartosc(h, kod, wlasne=False) for h in opp_hist[-12:]])
    return {
        "w6": w6,
        "w12": w12,
        "w_dom": _sr([_wartosc(h, kod) for h in hist_dom[-8:]]),
        "opp12": opp12,
        "liga": liga_sr,
        "dom": dom,
        # TREND: ostatnie trzy mecze wobec dłuższego okna, w logarytmach —
        # osobna cecha, bo „ostatnio więcej niż zwykle" to inna informacja niż
        # sam poziom drużyny. Zero, gdy nie ma z czym porównać (nie zgadujemy).
        "trend": (math.log((w3 + 0.5) / (w12 + 0.5))
                  if w3 is not None and w12 else 0.0),
        # JEDNA flaga braku historii rywala zamiast dwóch skorelowanych —
        # patrz nota przy CECHY_LOG.
        "brak_rywala": 1.0 if opp12 is None else 0.0,
        "n_hist": len(hist),
        **{f"p_{p}": _sr([(h.get("s") or {}).get(p) for h in hist[-6:]])
           for p in POMOCNICZE},
    }


def wiersze_treningowe(mag: dict) -> dict[str, list[dict]]:
    """{rynek: wiersze} — cel + cechy, po jednym wierszu na (mecz, drużyna)."""
    serie = _serie(mag)
    liga_sr = srednie_ligowe(serie)
    out: dict[str, list[dict]] = defaultdict(list)
    for tid, mecze in serie.items():
        for i, m in enumerate(mecze):
            if i < MIN_HISTORII:
                continue
            hist = mecze[:i]
            dom = int(m.get("h") or 0)
            czas = int(m.get("t") or 0)
            opp_hist = [
                h for h in serie.get(str(m.get("o")), [])
                if int(h.get("t") or 0) < czas
            ]
            for kod, rynek in CELE.items():
                y = _wartosc(m, kod)
                if y is None:
                    continue
                c = cechy_wiersza(kod, hist, opp_hist, dom,
                                  liga_sr.get((m.get("l"), kod)))
                if c is None:
                    continue
                out[rynek].append({**c, "y": float(y), "t": czas, "team": tid})
    return dict(out)


def przygotuj(mag: dict) -> dict:
    """Kontekst liczony RAZ na cykl: serie meczów i średnie ligowe.

    ⚑ BEZ TEGO CYKL BY KLĘKAŁ. `cechy_na_mecz` przelicza cały magazyn (289
    drużyn) przy każdym wywołaniu, a cykl pyta o ~240 drużyn × 6 rynków, czyli
    1400 razy na przebieg. Kontekst zamienia to na jedno przeliczenie.
    """
    serie = _serie(mag)
    return {"serie": serie, "liga_sr": srednie_ligowe(serie)}


def cechy_z_kontekstu(ctx: dict, team_id: int | str, rynek: str,
                      opp_id: int | str | None, dom: int, liga: int | None,
                      do_ts: int | None = None) -> dict | None:
    """Cechy dla NADCHODZĄCEGO meczu — to samo, co w treningu, tą samą drogą.

    ⚑ JEDNA FUNKCJA CECH DLA TRENINGU I PRODUKCJI. Gdyby produkcja liczyła je
    własną kopią kodu, model dostawałby liczby z innego rozkładu niż te, na
    których się uczył, i nikt by tego nie zauważył — a to najdroższa klasa
    błędu w tym repo (patrz kopia konfiguracji we froncie,
    [[kupony-przebudowa-domknieta]]).

    `do_ts` to godzina meczu: historia liczy się WYŁĄCZNIE z meczów
    wcześniejszych, dokładnie jak przy treningu.
    """
    kod = RYNEK_NA_KOD.get(rynek)
    if kod is None:
        return None
    serie = ctx.get("serie") or {}
    prog = int(do_ts or time.time())
    hist = [h for h in serie.get(str(team_id), []) if int(h.get("t") or 0) < prog]
    if len(hist) < MIN_HISTORII:
        return None
    opp_hist = [h for h in serie.get(str(opp_id), []) if int(h.get("t") or 0) < prog]
    return cechy_wiersza(kod, hist, opp_hist, int(dom),
                         (ctx.get("liga_sr") or {}).get((liga, kod)))


def cechy_na_mecz(mag: dict, team_id: int | str, rynek: str,
                  opp_id: int | str | None, dom: int, liga: int | None,
                  do_ts: int | None = None,
                  liga_sr: dict | None = None) -> dict | None:
    """Wygodna nakładka na `cechy_z_kontekstu` — przelicza magazyn za każdym
    razem, więc do jednorazowych pomiarów, NIE do cyklu."""
    ctx = przygotuj(mag)
    if liga_sr is not None:
        ctx["liga_sr"] = liga_sr
    return cechy_z_kontekstu(ctx, team_id, rynek, opp_id, dom, liga, do_ts)


def prognoza(wagi: dict | None, ctx: dict, team_id: int | str, rynek: str,
             opp_id: int | str | None, dom: int, liga: int | None,
             linia: float, strona: str,
             do_ts: int | None = None) -> dict | None:
    """Pełna prognoza modelu dla jednego zakładu — albo None, gdy nie wiemy.

    Zwraca `{"p", "lam", "r_nb", "odl"}`. `odl` to odległość linii od λ, czyli
    to, na czym stoi reguła zasięgu (patrz `MAX_ODLEGLOSC_LINII`).
    """
    wr = ((wagi or {}).get("rynki") or {}).get(rynek)
    if not wr or not ctx:
        return None
    cechy = cechy_z_kontekstu(ctx, team_id, rynek, opp_id, dom, liga, do_ts)
    if cechy is None:
        return None
    lm = lam(wr, cechy)
    if lm is None:
        return None
    p = p_strony(lm, linia, strona, wr.get("r_nb"))
    if p is None:
        return None
    return {"p": round(float(p), 4), "lam": round(float(lm), 3),
            "r_nb": wr.get("r_nb"),
            "odl": round(abs(float(linia) - float(lm)), 2)}


# ------------------------------------------------------------------ trening --
def schemat(wiersze: list[dict]) -> dict:
    """Schemat cech USTALONY NA TRENINGU: mediany do imputacji i flagi braków.

    ⚑ Bez tego produkcja miałaby inny zestaw kolumn niż trening (flaga braku
    powstaje tylko wtedy, gdy braków jest dużo). Pierwsza wersja eksperymentu
    wywaliła się dokładnie na tym i to jest najłatwiejszy błąd do popełnienia
    przy każdej zmianie cech.
    """
    uzyte, med, flagi = [], {}, []
    for c in CECHY_LOG:
        sur = np.array([w.get(c) if w.get(c) is not None else np.nan
                        for w in wiersze], dtype=float)
        if np.isnan(sur).all():
            continue
        uzyte.append(c)
        med[c] = float(np.nanmedian(sur))
        if float(np.isnan(sur).mean()) > 0.02:
            flagi.append(c)
    return {"log": uzyte, "med": med, "flagi": flagi}


def nazwy_cech(sch: dict) -> list[str]:
    return (["const"] + [f"log_{c}" for c in sch["log"]]
            + [f"brak_{c}" for c in sch["flagi"]] + list(CECHY_LIN))


def macierz(wiersze: list[dict], sch: dict) -> np.ndarray:
    """X według schematu — kolejność kolumn MUSI zgadzać się z `nazwy_cech`."""
    n = len(wiersze)
    kolumny = [np.ones(n)]
    for c in sch["log"]:
        sur = np.array([w.get(c) if w.get(c) is not None else np.nan
                        for w in wiersze], dtype=float)
        sur[np.isnan(sur)] = sch["med"][c]
        kolumny.append(np.log(np.maximum(sur, 0.0) + 0.5))
    for c in sch["flagi"]:
        kolumny.append(np.array([1.0 if w.get(c) is None else 0.0
                                 for w in wiersze]))
    for c in CECHY_LIN:
        kolumny.append(np.array([float(w.get(c) or 0) for w in wiersze]))
    return np.column_stack(kolumny)


def _irls(X: np.ndarray, y: np.ndarray, ridge: float = RIDGE,
          iteracji: int = 30) -> np.ndarray:
    """Regresja Poissona metodą Newtona z karą L2 (stała bez kary)."""
    beta = np.zeros(X.shape[1])
    beta[0] = math.log(max(float(y.mean()), 1e-3))
    kara = np.eye(X.shape[1]) * float(ridge)
    kara[0, 0] = 0.0
    for _ in range(iteracji):
        mu = np.exp(np.clip(X @ beta, -8.0, 8.0))
        grad = X.T @ (y - mu) - kara @ beta
        H = (X * mu[:, None]).T @ X + kara
        try:
            krok = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        nowe = beta + krok
        if not np.all(np.isfinite(nowe)):
            break
        if float(np.max(np.abs(nowe - beta))) < 1e-7:
            return nowe
        beta = nowe
    return beta


def naddyspersja(y: np.ndarray, mu: np.ndarray) -> float:
    """Ile razy wariancja przewyższa Poissona (1,0 = dokładnie Poisson)."""
    mu = np.maximum(mu, 1e-6)
    return float(np.mean((y - mu) ** 2 / mu))


def kształt_nb(y: np.ndarray, mu: np.ndarray) -> float | None:
    """Parametr `r` rozkładu ujemnego dwumianowego (None = zostajemy przy Poissonie).

    ⚑ POISSON JEST ZA WĄSKI I TO JEST ZMIERZONE (2026-08-17): naddyspersja
    wyszła 1,56 na rożnych i 1,90 na strzałach, czyli realna wariancja jest
    o połowę do dwóch razy większa, niż zakłada Poisson. Skutek nie jest
    teoretyczny: przy zbyt wąskim rozkładzie szansa na skrajnych liniach
    (rożne 9,5+, kartki 3,5+) wychodzi za NISKA po stronie „powyżej" i za
    wysoka po „poniżej" — a to jest dokładnie liczba, którą sprzedajemy.

    NB2: Var = μ + μ²/r, więc r = mean(μ²) / (mean((y−μ)²) − mean(μ)).
    Gdy mianownik ≤ 0, dane nie są nadmiernie rozproszone i Poisson wystarcza.
    """
    mu = np.maximum(np.asarray(mu, dtype=float), 1e-6)
    y = np.asarray(y, dtype=float)
    nadwyzka = float(np.mean((y - mu) ** 2) - np.mean(mu))
    if nadwyzka <= 1e-9:
        return None
    r = float(np.mean(mu ** 2) / nadwyzka)
    # r poniżej 1 znaczy rozkład skrajnie rozlany — przy naszych liczbach
    # zdarzeń to bardziej objaw złego dopasowania niż własność zjawiska
    return r if 0.5 <= r <= 500.0 else None


def trenuj_rynek(wiersze: list[dict], ridge: float = RIDGE) -> dict | None:
    """Wagi jednego rynku albo None, gdy próba za mała."""
    if len(wiersze) < MIN_WIERSZY_RYNKU:
        return None
    sch = schemat(wiersze)
    X = macierz(wiersze, sch)
    y = np.array([w["y"] for w in wiersze], dtype=float)
    beta = _irls(X, y, ridge)
    mu = np.exp(np.clip(X @ beta, -8.0, 8.0))
    r = kształt_nb(y, mu)
    return {
        "beta": [round(float(b), 6) for b in beta],
        "cechy": nazwy_cech(sch),
        "log": sch["log"], "med": {k: round(v, 4) for k, v in sch["med"].items()},
        "flagi": sch["flagi"],
        "n": len(wiersze),
        "sr_y": round(float(y.mean()), 4),
        "naddyspersja": round(naddyspersja(y, mu), 4),
        # kształt rozkładu: None = Poisson wystarcza dla tego rynku
        "r_nb": round(r, 3) if r is not None else None,
        "od": int(min(w.get("t") or 0 for w in wiersze)),
        "do": int(max(w.get("t") or 0 for w in wiersze)),
    }


def trenuj(mag: dict, ridge: float = RIDGE) -> dict:
    """Wagi wszystkich rynków + metryczka do zapisania w Supabase."""
    wiersze = wiersze_treningowe(mag)
    rynki = {}
    for rynek, grp in sorted(wiersze.items()):
        w = trenuj_rynek(grp, ridge)
        if w is not None:
            rynki[rynek] = w
    return {
        "wersja": WERSJA_MODELU_UCZONEGO,
        "trenowano_ts": int(time.time()),
        "ridge": float(ridge),
        "rynki": rynki,
    }


# ---------------------------------------------------------------- predykcja --
def lam(wagi_rynku: dict, cechy: dict) -> float | None:
    """Oczekiwana liczba zdarzeń dla jednego (mecz, drużyna, rynek)."""
    if not wagi_rynku or not cechy:
        return None
    sch = {"log": wagi_rynku.get("log") or [],
           "med": wagi_rynku.get("med") or {},
           "flagi": wagi_rynku.get("flagi") or []}
    X = macierz([cechy], sch)
    beta = np.array(wagi_rynku.get("beta") or [], dtype=float)
    if X.shape[1] != beta.shape[0]:
        # ⚑ Rozjazd schematu z wagami: NIE zgadujemy, bo prognoza z niepełnym
        # zestawem cech wygląda jak każda inna. Cisza znaczy „nie wiemy".
        return None
    return float(np.exp(np.clip(X @ beta, -8.0, 8.0))[0])


def p_powyzej(lambda_: float | None, linia: float,
              r_nb: float | None = None) -> float | None:
    """P(liczba zdarzeń > linia). Poisson, a przy `r_nb` — ujemny dwumianowy.

    Linia bukmachera jest połówkowa (4,5 / 12,5), więc „powyżej 4,5" znaczy
    „co najmniej 5" — bez remisów na linii.

    `r_nb` bierze się z pomiaru rozrzutu na danych treningowych
    (`kształt_nb`). Przy rożnych i strzałach Poisson jest za wąski, a to psuje
    szansę dokładnie na tych liniach, na których zakład jest ciekawy.
    """
    if lambda_ is None or lambda_ <= 0:
        return None
    prog = math.floor(float(linia))
    if r_nb and r_nb > 0:
        # NB2 z μ i r: p = r/(r+μ), P(X=k) = C(k+r−1,k) p^r (1−p)^k
        p0 = r_nb / (r_nb + lambda_)
        skladnik = p0 ** r_nb
        suma = skladnik
        for k in range(1, prog + 1):
            skladnik *= (r_nb + k - 1.0) / k * (1.0 - p0)
            suma += skladnik
    else:
        skladnik = math.exp(-lambda_)
        suma = skladnik
        for k in range(1, prog + 1):
            skladnik *= lambda_ / k
            suma += skladnik
    return float(min(max(1.0 - suma, 1e-6), 1.0 - 1e-6))


def p_strony(lambda_: float | None, linia: float, strona: str,
             r_nb: float | None = None) -> float | None:
    """Szansa WYBRANEJ strony zakładu — jedna λ, dwie strony, suma równa 1."""
    p = p_powyzej(lambda_, linia, r_nb)
    if p is None:
        return None
    return p if strona == "powyzej" else 1.0 - p


# ------------------------------------------------------- zasięg i widełki ----
#
# ⚑ GDZIE MODEL MA POKRYCIE, A GDZIE ZGADUJE (zmierzone 2026-08-17 na 4470
# rozliczonych typach). Luka deklaracji wobec odległości linii od λ:
#
#     |linia − λ|    n      udział   deklaruje   trafia    luka
#     0–1          2730      61%      50,8%     50,5%    −0,3 pp
#     1–2          1182      26%      50,8%     49,6%    −1,2 pp
#     2–3           423       9%      53,4%     52,2%    −1,1 pp
#     3–4            95       2%      65,0%     60,0%    −5,0 pp
#     4+             40       1%      85,5%     70,0%   −15,5 pp
#
# Trzy procent typów niesie CAŁĄ lukę na górze rozkładu. Model liczy λ
# poprawnie — myli się dopiero w skrajnym ogonie, gdzie „poniżej 8,5 rożnych"
# przy λ = 4 deklaruje 85%, a wchodzi 70%.
#
# ⚑ PRÓBOWAŁEM TEGO KALIBRACJĄ I NIE DZIAŁA (nie wracać bez nowego pomysłu).
# Krzywa Platta uczona out-of-fold na 18 tys. par syntetycznych linii wyszła
# b ≈ 1,00–1,05, Brier bez zmian, a na realnych typach nawet gorzej
# (0,2276 → 0,2284). Powód: w typowym zakresie model jest dobrze skalibrowany,
# więc jedna krzywa nie ma czego naprawiać — problem jest LOKALNY, w ogonie.
# Zamiast jedenastej warstwy: nie gramy tam, gdzie nie mamy pokrycia.
MAX_ODLEGLOSC_LINII = 2.5


def w_zasiegu(lambda_: float | None, linia: float,
              max_odl: float = MAX_ODLEGLOSC_LINII) -> bool:
    """Czy linia leży na tyle blisko λ, żeby model miał tam pokrycie."""
    if lambda_ is None:
        return False
    return abs(float(linia) - float(lambda_)) <= float(max_odl)


# WIDEŁKI PÓŁEK — cztery liczby i jedno kryterium kolejności (szansa modelu).
# Decyzja właściciela 17.08: „wyższe kursy realnie przeanalizowane przez model,
# bez zbędnych widełek", cel to TRAFNOŚĆ w obu zakładkach.
#
# Zmierzone (4470 typów, 22 dni):
#   wysoka szansa, limit 15/d, z regułą zasięgu   trafność 75,1%
#   wyższe kursy,  limit  6/d, BEZ reguły         trafność 53,4%, kurs 1,93
#
# ⚑ GÓRNE 2,20 NIE JEST WIDEŁKĄ Z BIURKA. Powyżej model jest ANTY-SYGNAŁEM:
# przy kursach 2,40–2,80 typy z najwyższą szansą trafiają 30,8%, a z najniższą
# 46,7% (górna tercja wobec dolnej, n=360). Bez tej granicy zakładka „wyższe
# kursy" pokazywałaby najpewniejsze typy o trafności 31%.
#
# ⚑ REGUŁA ZASIĘGU DOTYCZY TYLKO PÓŁKI PEWNIAKÓW. Na wyższych kursach
# POGARSZA wynik (53,4% → 48,9%), bo wysoki kurs to z definicji zdarzenie
# rzadkie, czyli linia daleka od λ. To reguła jednej półki, nie modelu.
POLKI = {
    "wysoka_szansa": {
        "kurs_min": 1.20, "kurs_max": 1.80,
        "limit_dobowy": 15, "zasieg": MAX_ODLEGLOSC_LINII,
    },
    "wyzsze_kursy": {
        "kurs_min": 1.80, "kurs_max": 2.20,
        "limit_dobowy": 6, "zasieg": None,
    },
}


def polka_dla(kurs: float | None) -> str | None:
    """Na której półce stoi typ o tym kursie (None = poza zakresem produktu)."""
    if not kurs:
        return None
    k = float(kurs)
    for nazwa, p in POLKI.items():
        if p["kurs_min"] <= k < p["kurs_max"]:
            return nazwa
    return None


def dopuszczony(kurs: float | None, lambda_: float | None,
                linia: float) -> tuple[bool, str | None]:
    """Czy typ wchodzi na którąkolwiek półkę. Zwraca (czy, powód odrzucenia).

    Powód jest zwracany zawsze, gdy typ odpada — cichych odrzuceń nie ma
    ([[ciche-odrzucenia-zasada]]).
    """
    polka = polka_dla(kurs)
    if polka is None:
        return False, "kurs_poza_polkami"
    zasieg = POLKI[polka]["zasieg"]
    if zasieg is not None and not w_zasiegu(lambda_, linia, zasieg):
        return False, "linia_poza_zasiegiem_modelu"
    return True, None


# ------------------------------------------------------------------ pomiary --
def zdanie_stanu(wagi: dict | None) -> str:
    """Jedna linia do logu cyklu — wagi bez licznika są nieodróżnialne od braku."""
    if not wagi or not (wagi.get("rynki") or {}):
        return ("Model uczony: BRAK WAG — cykl liczy starą formułą "
                "(uruchom scripts/trenuj_model.py)")
    r = wagi["rynki"]
    naj = ", ".join(
        f"{k.replace('team_', '')} n={v['n']}" for k, v in sorted(r.items())
    )
    wiek = (int(time.time()) - int(wagi.get("trenowano_ts") or 0)) / 3600.0
    return (f"Model uczony: wersja {wagi.get('wersja')}, {len(r)} rynków "
            f"({naj}), wagi sprzed {wiek:.0f} h")
