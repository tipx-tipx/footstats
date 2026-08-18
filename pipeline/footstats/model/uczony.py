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

# ---------------------------------------------------------------------------
# CO IDZIE NA STRONĘ — PRZEŁĄCZNIK ŹRÓDŁA SZANSY (2026-08-18)
# ---------------------------------------------------------------------------
#
# Decyzja właściciela 18.08: przełączamy na model uczony OD RAZU, bez czekania
# na próg 100 sparowanych rozliczeń — „obecny model i tak nie działa".
#
# DOWÓD, NA KTÓRYM TO STOI (powtórzony 18.08 na 4794 typach, wagi trenowane
# wyłącznie na meczach starszych niż testowe):
#
#     luka deklaracji   −14,3 pp  ->  −1,0 pp
#     Brier              0,2437   ->   0,2280
#     log-loss           0,6943   ->   0,6513
#     lepszy na WSZYSTKICH sześciu rynkach drużynowych
#
# ⚑⚑ MODEL IDZIE SUROWY, BEZ WARSTW KALIBRACYJNYCH — I TO NIE JEST SKRÓT.
# Warstwy (`kal_rynek`, `kal_strumien`, `korekta_strony`) uczą się z rozliczeń,
# O ILE MODEL ZAWYŻA, i o tyle ściągają. Są dopasowane do STAREGO rachunku,
# który zawyża o 14 pp. Nałożone na liczbę, która już nie zawyża, ściągnęłyby
# ją poniżej prawdy — czyli przełączenie źródła BEZ zdjęcia warstw dałoby
# wynik GORSZY niż przed zmianą. Backtest wyżej mierzył model SUROWY i taki
# wygrał, więc taki idzie na stronę.
#
# ⚑ DRABINKI ZOSTAJĄ NA STARYM (decyzja właściciela 18.08). Mają własną
# korektę, własny pomiar drugiego szczebla i wymagają osobnej roboty modelowej
# — patrz [[PLAN-do-29-08]]. Model liczy im drugą liczbę od 17.08, ale strona
# jej nie używa.
#
# POWRÓT: zmienić wartość na "stary" i wypchnąć. Nie trzeba rewertować ani
# jednego commita — obie liczby są stemplowane w księdze niezależnie od tego,
# która poszła na stronę (patrz `stempel_zrodla`).
ZRODLO_SZANSY: dict[str, str] = {
    "druzyny":   "uczony",     # 93% produkcji
    "pewniaki":  "uczony",     # zawodnicy
    "sumy":      "uczony",     # sumy meczowe i „kto więcej"
    "drabinki":  "stary",      # ⚑ decyzja właściciela — osobna robota modelowa
}


def na_stronie(strumien: str) -> bool:
    """Czy TEN strumień liczy stronę modelem uczonym."""
    return ZRODLO_SZANSY.get(str(strumien or ""), "stary") == "uczony"


def wybierz_szanse(
    strumien: str, p_stary: float, p_uczony: dict | None,
) -> tuple[float, str]:
    """Która liczba idzie na stronę. Zwraca (p, źródło).

    Model bez pokrycia (za krótka historia drużyny) NIE jest błędem — wtedy
    zostaje stary rachunek, a stempel mówi „stary_bez_pokrycia", żeby dało się
    policzyć, jak często to się zdarza. Cichy fallback byłby tu najgorszy
    z możliwych: strona pokazywałaby mieszankę dwóch rachunków, a pomiar
    przypisywałby wszystko modelowi.
    """
    if not na_stronie(strumien):
        return float(p_stary), "stary"
    if not isinstance(p_uczony, dict) or p_uczony.get("p") is None:
        return float(p_stary), "stary_bez_pokrycia"
    return float(p_uczony["p"]), "uczony"


def stempel_zrodla(p_stary: float, p_uczony: dict | None, zrodlo: str) -> dict:
    """Komplet do księgi: OBIE liczby plus informacja, która poszła na stronę.

    ⚑ Stemplujemy obie ZAWSZE, niezależnie od przełącznika. To jest jedyny
    sposób, żeby za dwa tygodnie dało się odpowiedzieć na pytanie „czy to
    działa" bez odtwarzania backtestu — i warunek postawiony przez właściciela
    przy zatwierdzaniu przełączenia.
    """
    out = {"zrodlo_p": zrodlo, "p_stary": round(float(p_stary), 4)}
    if isinstance(p_uczony, dict) and p_uczony.get("p") is not None:
        out["p_uczony"] = p_uczony
    return out
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


def _ligi_zakresu() -> set:
    """Rozgrywki, dla których LICZYMY rynki drużynowe (jedyne, na których
    warto trenować — patrz `wiersze_treningowe`)."""
    try:
        from .. import rozgrywki
        return set(rozgrywki.PROFILE.keys())
    except Exception:                                          # noqa: BLE001
        return set()


def wiersze_treningowe(mag: dict, tylko_zakres: bool = True) -> dict[str, list[dict]]:
    """{rynek: wiersze} — cel + cechy, po jednym wierszu na (mecz, drużyna).

    ⚑⚑ TRENUJEMY WYŁĄCZNIE NA ROZGRYWKACH, KTÓRE WYCENIAMY (2026-08-18).
    Magazyn urósł 18.08 z 309 do 1299 drużyn, bo backfill zaczął pytać też
    o kluby z nadchodzącego terminarza ([[magazyn-gubil-top-ligi]]). Terminarz
    obejmuje WSZYSTKIE rozgrywki statshuba, więc do magazynu weszło 177 lig,
    a rynki drużynowe liczymy dla 21 — zmierzone: tylko 26,1% meczów magazynu
    było „nasze".

    ZMIERZONE, nie założone (ten sam zbiór testowy, dwa treningi):

        A. cały magazyn, 177 lig, 221 765 wierszy
           luka −0,9 pp   Brier 0,2287   selekcja: trafia 56,9%, margines −2,0 pp
        B. tylko zakres, 21 rozgrywek, 57 256 wierszy
           luka −0,7 pp   Brier 0,2279   selekcja: trafia 58,2%, margines −0,7 pp

    Mniejsza próba wygrywa NA KAŻDEJ MIERZE. To spójne z krzywą uczenia
    zmierzoną tego samego dnia: poczwórna próba treningowa poprawia dewiancję
    o 0,4%, czyli model jest danymi NASYCONY — a wtedy dokładanie obcego
    rozkładu może już tylko szkodzić.

    Historia klubu spoza zakresu ZOSTAJE w magazynie i dalej służy jako profil
    RYWALA (koncesje) — wycinamy ją z treningu, nie z danych.
    """
    serie = _serie(mag)
    zakres = _ligi_zakresu() if tylko_zakres else set()
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
            if zakres and m.get("l") not in zakres:
                continue        # mecz spoza zakresu drużynowego — patrz wyżej
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
          iteracji: int = 30, offset: np.ndarray | None = None) -> np.ndarray:
    """Regresja Poissona metodą Newtona z karą L2 (stała bez kary).

    `offset` to znany z góry składnik `log λ`, którego nie szacujemy — przy
    zawodnikach jest to `log(minuty/90)`. Bez niego model próbowałby
    wytłumaczyć cechami to, że ktoś raz zagrał 20, a raz 90 minut.
    """
    off = np.zeros(len(y)) if offset is None else np.asarray(offset, dtype=float)
    beta = np.zeros(X.shape[1])
    beta[0] = math.log(max(float(y.mean()), 1e-3))
    kara = np.eye(X.shape[1]) * float(ridge)
    kara[0, 0] = 0.0
    for _ in range(iteracji):
        mu = np.exp(np.clip(off + X @ beta, -8.0, 8.0))
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


def trenuj(mag: dict, ridge: float = RIDGE, lib: dict | None = None) -> dict:
    """Wagi wszystkich rynków + metryczka do zapisania w Supabase.

    `mag` to magazyn drużynowy, `lib` — bank trendów zawodniczych. Oba
    strumienie idą jednym modelem i jedną wersją, żeby nie powtórzyła się
    historia, w której jeden rynek jechał na innym zestawie warstw niż resztа.
    """
    rynki = {}
    for rynek, grp in sorted(wiersze_treningowe(mag).items()):
        w = trenuj_rynek(grp, ridge)
        if w is not None:
            rynki[rynek] = w
    out = {
        "wersja": WERSJA_MODELU_UCZONEGO,
        "trenowano_ts": int(time.time()),
        "ridge": float(ridge),
        "rynki": rynki,
    }
    out["rynki_sum"] = trenuj_sumy(mag, ridge)
    if lib:
        out["rynki_zaw"] = trenuj_zawodnikow(lib, ridge)
    return out


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
    r = (wagi or {}).get("rynki") or {}
    zaw = (wagi or {}).get("rynki_zaw") or {}
    # ⚑ WARUNEK MUSI ZNAĆ WSZYSTKIE GRUPY. Dwa razy z rzędu (zawodnicy 17.08,
    # potem sumy) dopisanie nowej grupy zostawiało tu stary warunek, więc log
    # mówił „BRAK WAG", choć wagi były — i nikt by nie sprawdził, czy cykl
    # liczy nowym rachunkiem. Test na to jest.
    if not r and not zaw and not ((wagi or {}).get("rynki_sum") or {}):
        return ("Model uczony: BRAK WAG — cykl liczy starą formułą "
                "(uruchom scripts/trenuj_model.py)")
    wiek = (int(time.time()) - int((wagi or {}).get("trenowano_ts") or 0)) / 3600.0
    czesci = []
    if r:
        czesci.append(f"{len(r)} drużynowych (" + ", ".join(
            f"{k.replace('team_', '')} n={v['n']}" for k, v in sorted(r.items())
        ) + ")")
    else:
        # ⚑ brak jednego strumienia nie może wyglądać jak brak wag ani jak
        # komplet — cykl liczyłby wtedy drużyny starą formułą po cichu
        czesci.append("⚑ ZERO drużynowych")
    if zaw:
        czesci.append(f"{len(zaw)} zawodniczych ({', '.join(sorted(zaw))})")
    else:
        czesci.append("⚑ ZERO zawodniczych")
    sumy = (wagi or {}).get("rynki_sum") or {}
    czesci.append(f"{len(sumy)} sum meczowych" if sumy
                  else "⚑ ZERO sum meczowych")
    return (f"Model uczony: wersja {(wagi or {}).get('wersja')}, "
            + ", ".join(czesci) + f", wagi sprzed {wiek:.0f} h")


# ===========================================================================
# ZAWODNICY — ten sam model, trzy różnice
# ===========================================================================
#
# ⚑ MINUTY. Zawodnik grający 60 minut ma inną szansę niż grający 90, więc model
# uczy się TEMPA na 90 minut: `log λ = log(minuty/90) + β·cechy`. Offset nie
# jest szacowany — jest znany. Bez niego model próbowałby wytłumaczyć cechami
# to, że ktoś raz zagrał 20, a raz pełny mecz.
#
# ⚑ POZYCJA. Napastnik strzela więcej niż obrońca, a pozycja zmienia się
# z meczu na mecz (bank trzyma `game_positions` per mecz). Wchodzi jako trzy
# grupy, DEF jako odniesienie.
#
# ⚑ ŹRÓDŁO. Nie magazyn drużynowy, a bank `trend_lib` (176 718 obserwacji,
# 4997 serii). Ten istniał od dawna i właśnie dlatego strumień zawodniczy się
# POPRAWIAŁ, gdy drużynowy się psuł ([[model-nie-ma-pamieci-druzyn]]).
#
# Zmierzone 17.08 na 260 rozliczonych typach zawodniczych (model widział tylko
# historię sprzed meczu, minuty z oczekiwanych):
#
#                        deklaruje   weszło    luka      Brier   log-loss
#     DZIŚ (produkcja)     49,4%    36,9%   −12,5 pp   0,2305    0,6559
#     MODEL UCZONY         43,6%    36,9%    −6,7 pp   0,2263    0,6494
#
# Czego się nauczył: strzały — własne tempo +0,52, napastnik +0,45, środkowy
# +0,29; faule — tempo +0,42, środkowy +0,15; odbiory — napastnik −0,16.
# Minuty mają współczynnik UJEMNY (−0,09…−0,14): kto gra pełne mecze, ma niższe
# tempo na 90 minut, bo to częściej obrońcy i gracze bez rotacji.

# Rynki zawodnicze, które bank realnie niesie (reszta ma zero serii).
CELE_ZAW = ("shots", "sot", "fouls_committed", "fouls_won", "tackles")
# Mecz krótszy niż to nic nie mówi o tempie: 5 minut z jednym strzałem dałoby
# tempo 18 na 90 minut.
MIN_MINUT_ZAW = 15.0
CECHY_LOG_ZAW = ["t3", "t6", "t12", "min6", "liga", "opp"]
CECHY_LIN_ZAW = ["dom", "udzial_startow"]
GRUPY_POZYCJI = ("DEF", "MID", "FWD")     # DEF = odniesienie, bez kolumny
_POZ_MAPA = {
    "G": "GK",
    "D": "DEF", "CB": "DEF", "LB": "DEF", "RB": "DEF", "LWB": "DEF", "RWB": "DEF",
    "M": "MID", "CM": "MID", "DM": "MID", "AM": "MID", "LM": "MID", "RM": "MID",
    "F": "FWD", "ST": "FWD", "CF": "FWD", "LW": "FWD", "RW": "FWD",
}


def grupa_pozycji(poz) -> str:
    """Pozycja z feedu na jedną z trzech grup (`NIE` = nie wiemy)."""
    p = str(poz or "").upper().strip()
    if not p:
        return "NIE"
    if p in _POZ_MAPA:
        return _POZ_MAPA[p]
    for ostatnia, grupa in (("G", "GK"), ("B", "DEF"), ("D", "DEF"),
                            ("M", "MID"), ("W", "FWD"), ("F", "FWD"),
                            ("S", "FWD"), ("T", "FWD")):
        if p.endswith(ostatnia):
            return grupa
    return "NIE"


def _chronologicznie(czasy: list) -> list[int]:
    """Indeksy serii od najstarszego. ⚑ Bank trzyma je MALEJĄCO."""
    n = len(czasy)
    idx = list(range(n))
    if n > 1 and (czasy[0] or 0) > (czasy[-1] or 0):
        idx = idx[::-1]
    return idx


def cechy_zawodnika(seria: dict, do_ts: int | None = None,
                    oczekiwane_minuty: float | None = None) -> dict | None:
    """Cechy zawodnika z jego serii w banku — tylko z meczów sprzed `do_ts`.

    ⚑ JEDNA FUNKCJA DLA TRENINGU I PRODUKCJI (jak przy drużynach). W treningu
    `do_ts` to czas meczu, którego wynik jest celem; w produkcji — godzina
    nadchodzącego meczu.
    """
    counts = seria.get("counts") or []
    minuty = seria.get("minutes") or []
    czasy = seria.get("timestamps") or []
    n = min(len(counts), len(minuty), len(czasy))
    if n < MIN_HISTORII:
        return None
    prog = int(do_ts) if do_ts else int(time.time())
    idx = [j for j in _chronologicznie(czasy[:n]) if int(czasy[j] or 0) < prog]
    tempa = [float(counts[j] or 0) / float(minuty[j]) * 90.0
             for j in idx if float(minuty[j] or 0) >= MIN_MINUT_ZAW]
    if len(tempa) < MIN_HISTORII:
        return None
    min_hist = [float(minuty[j] or 0) for j in idx]
    started = seria.get("started") or []
    ostatnie = idx[-10:]
    pozycje = seria.get("game_positions") or []
    poz = grupa_pozycji(
        pozycje[idx[-1]] if idx and idx[-1] < len(pozycje) else None)
    return {
        "t3": _sr(tempa[-3:]), "t6": _sr(tempa[-6:]), "t12": _sr(tempa[-12:]),
        "min6": (float(oczekiwane_minuty) if oczekiwane_minuty
                 else (_sr(min_hist[-6:]) or 90.0)),
        "udzial_startow": (
            sum(1 for j in ostatnie if j < len(started) and started[j])
            / max(len(ostatnie), 1)
        ),
        "liga": float(seria.get("league_average") or 0) or None,
        "opp": float(seria.get("opponent_average") or 0) or None,
        "dom": 1 if seria.get("is_home") else 0,
        "poz": poz,
        "n_hist": len(tempa),
    }


def wiersze_zawodnicze(lib: dict) -> dict[str, list[dict]]:
    """{rynek: wiersze} z banku — cel, minuty i cechy z przeszłości."""
    out: dict[str, list[dict]] = defaultdict(list)
    for _, seria in (lib or {}).items():
        if not isinstance(seria, dict):
            continue
        mk = str(seria.get("market_code") or "")
        if mk not in CELE_ZAW:
            continue
        counts = seria.get("counts") or []
        minuty = seria.get("minutes") or []
        czasy = seria.get("timestamps") or []
        n = min(len(counts), len(minuty), len(czasy))
        if n < MIN_HISTORII + 1:
            continue
        for i in _chronologicznie(czasy[:n]):
            m_i = float(minuty[i] or 0)
            if m_i < MIN_MINUT_ZAW:
                continue
            c = cechy_zawodnika(seria, do_ts=int(czasy[i] or 0))
            if c is None:
                continue
            out[mk].append({**c, "y": float(counts[i] or 0), "minuty": m_i,
                            "t": int(czasy[i] or 0),
                            "gracz": str(seria.get("player_id") or "")})
    return dict(out)


def schemat_zaw(wiersze: list[dict]) -> dict:
    uzyte, med = [], {}
    for c in CECHY_LOG_ZAW:
        sur = np.array([w.get(c) if w.get(c) is not None else np.nan
                        for w in wiersze], dtype=float)
        if np.isnan(sur).all():
            continue
        uzyte.append(c)
        med[c] = float(np.nanmedian(sur))
    return {"log": uzyte, "med": med}


def nazwy_cech_zaw(sch: dict) -> list[str]:
    return (["const"] + [f"log_{c}" for c in sch["log"]] + list(CECHY_LIN_ZAW)
            + [f"poz_{p}" for p in GRUPY_POZYCJI[1:]])


def macierz_zaw(wiersze: list[dict], sch: dict) -> np.ndarray:
    n = len(wiersze)
    kol = [np.ones(n)]
    for c in sch["log"]:
        sur = np.array([w.get(c) if w.get(c) is not None else np.nan
                        for w in wiersze], dtype=float)
        sur[np.isnan(sur)] = sch["med"][c]
        kol.append(np.log(np.maximum(sur, 0.0) + 0.1))
    for c in CECHY_LIN_ZAW:
        kol.append(np.array([float(w.get(c) or 0) for w in wiersze]))
    for p in GRUPY_POZYCJI[1:]:
        kol.append(np.array([1.0 if w.get("poz") == p else 0.0 for w in wiersze]))
    return np.column_stack(kol)


def trenuj_rynek_zaw(wiersze: list[dict], ridge: float = RIDGE) -> dict | None:
    """Wagi jednego rynku zawodniczego albo None, gdy próba za mała."""
    if len(wiersze) < MIN_WIERSZY_RYNKU:
        return None
    sch = schemat_zaw(wiersze)
    X = macierz_zaw(wiersze, sch)
    y = np.array([w["y"] for w in wiersze], dtype=float)
    off = np.log(np.maximum(
        np.array([w["minuty"] for w in wiersze], dtype=float), 1.0) / 90.0)
    beta = _irls(X, y, ridge, offset=off)
    mu = np.exp(np.clip(off + X @ beta, -8.0, 8.0))
    r = kształt_nb(y, mu)
    return {
        "beta": [round(float(b), 6) for b in beta],
        "cechy": nazwy_cech_zaw(sch),
        "log": sch["log"], "med": {k: round(v, 4) for k, v in sch["med"].items()},
        "n": len(wiersze),
        "sr_y": round(float(y.mean()), 4),
        "naddyspersja": round(naddyspersja(y, mu), 4),
        "r_nb": round(r, 3) if r is not None else None,
        "od": int(min(w.get("t") or 0 for w in wiersze)),
        "do": int(max(w.get("t") or 0 for w in wiersze)),
    }


def trenuj_zawodnikow(lib: dict, ridge: float = RIDGE) -> dict:
    """Wagi rynków zawodniczych z banku trendów."""
    out = {}
    for rynek, grp in sorted(wiersze_zawodnicze(lib).items()):
        w = trenuj_rynek_zaw(grp, ridge)
        if w is not None:
            out[rynek] = w
    return out


def lam_zaw(wagi_rynku: dict, cechy: dict,
            oczekiwane_minuty: float | None = None) -> float | None:
    """Oczekiwana liczba zdarzeń zawodnika, przeskalowana o minuty."""
    if not wagi_rynku or not cechy:
        return None
    sch = {"log": wagi_rynku.get("log") or [], "med": wagi_rynku.get("med") or {}}
    X = macierz_zaw([cechy], sch)
    beta = np.array(wagi_rynku.get("beta") or [], dtype=float)
    if X.shape[1] != beta.shape[0]:
        return None       # rozjazd schematu z wagami — cisza, nie zgadywanie
    minuty = float(oczekiwane_minuty or cechy.get("min6") or 90.0)
    off = math.log(max(minuty, 1.0) / 90.0)
    return float(np.exp(np.clip(off + X @ beta, -8.0, 8.0))[0])


def prognoza_zawodnika(wagi: dict | None, seria: dict, rynek: str,
                       linia: float, strona: str,
                       oczekiwane_minuty: float | None = None,
                       do_ts: int | None = None) -> dict | None:
    """Pełna prognoza dla zakładu zawodniczego — albo None, gdy nie wiemy."""
    wr = ((wagi or {}).get("rynki_zaw") or {}).get(rynek)
    if not wr or not seria:
        return None
    cechy = cechy_zawodnika(seria, do_ts=do_ts,
                            oczekiwane_minuty=oczekiwane_minuty)
    if cechy is None:
        return None
    lm = lam_zaw(wr, cechy, oczekiwane_minuty)
    if lm is None:
        return None
    p = p_strony(lm, linia, strona, wr.get("r_nb"))
    if p is None:
        return None
    return {"p": round(float(p), 4), "lam": round(float(lm), 3),
            "r_nb": wr.get("r_nb"),
            "odl": round(abs(float(linia) - float(lm)), 2),
            "min": round(float(oczekiwane_minuty or cechy.get("min6") or 90.0), 1)}


# ===========================================================================
# SUMY MECZOWE — cel liczony BEZPOŚREDNIO, nie splotem dwóch drużyn
# ===========================================================================
#
# ⚑ DLACZEGO NIE SPLOT. Sumę można by policzyć jako Poisson(λ_gosp + λ_gość)
# z modelu drużynowego, ale to zakłada NIEZALEŻNOŚĆ zdarzeń obu drużyn, a ona
# nie istnieje: korelacja rożnych między drużynami jest zmierzona i wynosi
# −0,127 ([[korelacja-druzyn]]). Magazyn ma w każdym rekordzie statystyki
# NASZE (`s`) i RYWALA (`sp`) z tego samego meczu, więc suma jest po prostu
# w danych i można się jej nauczyć wprost.
#
# ⚑ KAŻDY MECZ JEST W MAGAZYNIE DWA RAZY (raz z perspektywy każdej drużyny).
# Wiersz budujemy tylko z perspektywy GOSPODARZA i deduplikujemy po `event_id`
# — bez tego ta sama suma wchodziłaby do treningu podwójnie.
#
# Zmierzone 17.08 na 900 rozliczonych typach `match_*`:
#
#                        deklaruje   weszło    luka      Brier   log-loss
#     DZIŚ (produkcja)     65,5%    55,3%   −10,2 pp   0,2232    0,6401
#     MODEL UCZONY         53,8%    55,3%    +1,5 pp   0,2173    0,6237
#
# ⚑⚑ ALE NIE NA KAŻDYM RYNKU — przy przełączaniu patrzeć PER RYNEK:
#
#     match_corners  n=459   luka −11,5 → +0,4   Brier 0,2188 → 0,2054  lepszy
#     match_shots    n= 81   luka −28,6 → −16,9  Brier 0,2936 → 0,2490  lepszy
#     match_cards    n=201   luka  −5,1 → +6,5   Brier 0,2074 → 0,2213  GORSZY
#     match_sot      n=124   luka  −3,7 → +7,3   Brier 0,2187 → 0,2259  GORSZY
#
# Na kartkach i celnych meczowych model ZANIŻA — odwrotnie niż wszędzie
# indziej. Globalna średnia to ukrywa, więc decyzja o przełączeniu tych dwóch
# rynków musi mieć własny pomiar.

CELE_SUM = {"cor": "match_corners", "sh": "match_shots", "sot": "match_sot",
            "crd": "match_cards", "fol": "match_fouls"}
RYNEK_SUM_NA_KOD = {v: k for k, v in CELE_SUM.items()}
CECHY_LOG_SUM = ["suma6", "suma12", "gosp6", "gosc6", "kon_gosp", "kon_gosc",
                 "liga"]
MIN_WIERSZY_SUMY = 500     # rynków sum jest mniej niż drużynowych (mecz ≠ para)


def _suma_meczu(m: dict, kod: str) -> float | None:
    a = (m.get("s") or {}).get(kod)
    b = (m.get("sp") or {}).get(kod)
    if a is None or b is None:
        return None
    return float(a) + float(b)


def srednie_ligowe_sum(serie: dict[str, list], min_n: int = 20) -> dict:
    """{(liga, kod): średnia SUMY} — liczona z perspektywy gospodarza."""
    zbior: dict = defaultdict(list)
    for mecze in serie.values():
        for m in mecze:
            if int(m.get("h") or 0) != 1:
                continue
            for kod in CELE_SUM:
                v = _suma_meczu(m, kod)
                if v is not None:
                    zbior[(m.get("l"), kod)].append(v)
    return {k: float(np.mean(v)) for k, v in zbior.items() if len(v) >= min_n}


def cechy_sumy(kod: str, hist_gosp: list[dict], hist_gosc: list[dict],
               liga_sr: float | None) -> dict | None:
    """Cechy sumy meczowej — z historii OBU drużyn, tylko sprzed meczu."""
    sumy_g = [v for v in (_suma_meczu(h, kod) for h in hist_gosp) if v is not None]
    sumy_a = [v for v in (_suma_meczu(h, kod) for h in hist_gosc) if v is not None]
    if len(sumy_g) < MIN_HISTORII or len(sumy_a) < MIN_HISTORII:
        return None
    return {
        # ile pada W MECZACH obu drużyn — to jest istota tego rynku
        "suma6": _sr(sumy_g[-6:] + sumy_a[-6:]),
        "suma12": _sr(sumy_g[-12:] + sumy_a[-12:]),
        # ile notuje każda z nich i ile dopuszcza
        "gosp6": _sr([(h.get("s") or {}).get(kod) for h in hist_gosp[-6:]]),
        "gosc6": _sr([(h.get("s") or {}).get(kod) for h in hist_gosc[-6:]]),
        "kon_gosp": _sr([(h.get("sp") or {}).get(kod) for h in hist_gosp[-6:]]),
        "kon_gosc": _sr([(h.get("sp") or {}).get(kod) for h in hist_gosc[-6:]]),
        "liga": liga_sr,
    }


def wiersze_sum(mag: dict) -> dict[str, list[dict]]:
    """{rynek sumy: wiersze} — jeden wiersz na MECZ, nie na parę (mecz, drużyna)."""
    serie = _serie(mag)
    liga_sr = srednie_ligowe_sum(serie)
    out: dict[str, list[dict]] = defaultdict(list)
    widziane: set = set()
    for _tid, mecze in serie.items():
        for i, m in enumerate(mecze):
            if int(m.get("h") or 0) != 1 or i < MIN_HISTORII:
                continue
            ev = m.get("e")
            if ev in widziane:
                continue
            widziane.add(ev)
            czas = int(m.get("t") or 0)
            hist_g = mecze[:i]
            hist_a = [h for h in serie.get(str(m.get("o")), [])
                      if int(h.get("t") or 0) < czas]
            if len(hist_a) < MIN_HISTORII:
                continue
            for kod, rynek in CELE_SUM.items():
                y = _suma_meczu(m, kod)
                if y is None:
                    continue
                c = cechy_sumy(kod, hist_g, hist_a,
                               liga_sr.get((m.get("l"), kod)))
                if c is None:
                    continue
                out[rynek].append({**c, "y": y, "t": czas})
    return dict(out)


def schemat_sum(wiersze: list[dict]) -> dict:
    uzyte, med = [], {}
    for c in CECHY_LOG_SUM:
        sur = np.array([w.get(c) if w.get(c) is not None else np.nan
                        for w in wiersze], dtype=float)
        if np.isnan(sur).all():
            continue
        uzyte.append(c)
        med[c] = float(np.nanmedian(sur))
    return {"log": uzyte, "med": med}


def nazwy_cech_sum(sch: dict) -> list[str]:
    return ["const"] + [f"log_{c}" for c in sch["log"]]


def macierz_sum(wiersze: list[dict], sch: dict) -> np.ndarray:
    kol = [np.ones(len(wiersze))]
    for c in sch["log"]:
        sur = np.array([w.get(c) if w.get(c) is not None else np.nan
                        for w in wiersze], dtype=float)
        sur[np.isnan(sur)] = sch["med"][c]
        kol.append(np.log(np.maximum(sur, 0.0) + 0.5))
    return np.column_stack(kol)


def trenuj_rynek_sum(wiersze: list[dict], ridge: float = RIDGE) -> dict | None:
    if len(wiersze) < MIN_WIERSZY_SUMY:
        return None
    sch = schemat_sum(wiersze)
    X = macierz_sum(wiersze, sch)
    y = np.array([w["y"] for w in wiersze], dtype=float)
    beta = _irls(X, y, ridge)
    mu = np.exp(np.clip(X @ beta, -8.0, 8.0))
    r = kształt_nb(y, mu)
    return {
        "beta": [round(float(b), 6) for b in beta],
        "cechy": nazwy_cech_sum(sch),
        "log": sch["log"], "med": {k: round(v, 4) for k, v in sch["med"].items()},
        "n": len(wiersze),
        "sr_y": round(float(y.mean()), 4),
        "naddyspersja": round(naddyspersja(y, mu), 4),
        "r_nb": round(r, 3) if r is not None else None,
        "od": int(min(w.get("t") or 0 for w in wiersze)),
        "do": int(max(w.get("t") or 0 for w in wiersze)),
    }


def trenuj_sumy(mag: dict, ridge: float = RIDGE) -> dict:
    out = {}
    for rynek, grp in sorted(wiersze_sum(mag).items()):
        w = trenuj_rynek_sum(grp, ridge)
        if w is not None:
            out[rynek] = w
    return out


def przygotuj_sumy(mag: dict, ctx: dict | None = None) -> dict:
    """Kontekst sum — dokłada średnie ligowe SUM do kontekstu drużynowego."""
    ctx = dict(ctx or przygotuj(mag))
    ctx["liga_sr_sum"] = srednie_ligowe_sum(ctx["serie"])
    return ctx


def prognoza_sumy(wagi: dict | None, ctx: dict, gospodarz_id, gosc_id,
                  liga, rynek: str, linia: float, strona: str,
                  do_ts: int | None = None) -> dict | None:
    """Prognoza sumy meczowej — albo None, gdy którejś drużyny nie znamy."""
    wr = ((wagi or {}).get("rynki_sum") or {}).get(rynek)
    kod = RYNEK_SUM_NA_KOD.get(rynek)
    if not wr or not kod or not ctx:
        return None
    serie = ctx.get("serie") or {}
    prog = int(do_ts or time.time())
    hist_g = [h for h in serie.get(str(gospodarz_id), [])
              if int(h.get("t") or 0) < prog]
    hist_a = [h for h in serie.get(str(gosc_id), [])
              if int(h.get("t") or 0) < prog]
    # ⚑ LIGA Z HISTORII, GDY WOŁAJĄCY JEJ NIE ZNA. Ścieżka sum meczowych nie ma
    # pod ręką id rozgrywek, a średnia ligowa jest najmocniejszą cechą tego
    # modelu (log_liga +0,36…+0,77). Bez tego fallbacku wchodziłaby mediana
    # WSZYSTKICH lig, czyli liczba z innego poziomu rozgrywek.
    if liga is None and hist_g:
        liga = hist_g[-1].get("l")
    cechy = cechy_sumy(kod, hist_g, hist_a,
                       (ctx.get("liga_sr_sum") or {}).get((liga, kod)))
    if cechy is None:
        return None
    sch = {"log": wr.get("log") or [], "med": wr.get("med") or {}}
    X = macierz_sum([cechy], sch)
    beta = np.array(wr.get("beta") or [], dtype=float)
    if X.shape[1] != beta.shape[0]:
        return None
    lm = float(np.exp(np.clip(X @ beta, -8.0, 8.0))[0])
    p = p_strony(lm, linia, strona, wr.get("r_nb"))
    if p is None:
        return None
    return {"p": round(float(p), 4), "lam": round(lm, 3),
            "r_nb": wr.get("r_nb"),
            "odl": round(abs(float(linia) - lm), 2)}
