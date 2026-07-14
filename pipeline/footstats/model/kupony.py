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
# nowy kupon bierze WYŁĄCZNIE mecze jeszcze nierozpoczęte, z zapasem na
# obstawienie — leg z meczu, który już się odbył/trwa, nie może wejść do
# świeżo składanego kuponu (spójnie z regułą publikacji: kupon z pierwszym
# meczem startującym za <15 min i tak nie jest publikowany)
MARGINES_STARTU_S = 15 * 60
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
BEAM_W = 90               # szerokość wiązki w składaniu kuponu (szersza = mniej gubienia optimum)
# minimalna reprezentacja KAŻDEJ długości kuponu w wiązce — ranking miesza
# stany różnych długości i premiuje bliskość dolnej granicy kursu, więc
# krótkie, drogie stany wypychały długie, tanie trajektorie zanim zdążyły
# urosnąć (zmierzone: "dokładnie 7-8 legów" zwracało brak kuponu, choć
# komplet istniał). Stany ponad BEAM_W wchodzą dodatkowo, jeśli ich długość
# ma mniej niż tylu reprezentantów — wiązka jest NADZBIOREM starej, więc
# wynik nigdy nie jest gorszy.
MIN_NA_DLUGOSC = 10
MAX_KANDYDATOW = 120      # ilu najlepszych legów wchodzi do przeszukiwania
# ilu RÓŻNYCH zestawów legów o przypadkowo identycznym (długość, kurs, score)
# przetrwa dedup wiązki — patrz komentarz przy prune w _zloz_pewniaki
MAX_TIE_REPR = 3

# --- urealnienie szansy przy SKŁADANIU (selekcja, nie wyświetlanie) ---
# p_model bywa najbardziej przestrzelone dokładnie tam, gdzie deklaruje
# największą przewagę (wysokie linie, legi "średniej" pewności) — a stary
# scoring ufał mu w 100%, więc beam ładował do kuponów o wysokim kursie
# pojedyncze ryzykowne legi (strzały 2,5+ @2,9 z "przewagą" +30%) zamiast
# dokładać pewniejsze zdarzenia. Przy wyborze legów ściągamy więc szansę
# modelu ku cenie rynku (devig jednostronny, lustro betting.DEFAULT_ONE_
# SIDED_MARGIN) wagą zależną od pewności estymaty. WYŚWIETLANA szansa
# kuponu pozostaje iloczynem p_model — zmienia się tylko dobór legów.
MARZA_RYNKU = 0.07
WAGA_MODELU = {"wysoka": 0.75, "srednia": 0.55}
WAGA_MODELU_DEFAULT = 0.55
# płynna waga z szerokości przedziału wiarygodności (ci z puli legów):
# w = 0.85 - szerokość, ujęte w [0.50, 0.80]. Wąski przedział (duża próba,
# stabilna estymata) -> prawie pełna wiara; szeroki -> pół na pół z rynkiem.
# Progi spójne z kubełkami pewności (wysoka = ci<=0.18 -> w>=0.67).
WAGA_CI_BAZA = 0.85
WAGA_CI_MIN = 0.50
WAGA_CI_MAX = 0.80
# twardy limit legów ryzykownych (p_model < progu) per kupon — "wysoki kurs"
# ma się składać z WIĘKSZEJ liczby pewnych zdarzeń, nie z coraz grubszych
# pojedynczych strzałów; agresywny świadomie dopuszcza dwa. W profilu
# zbalansowanym (domyślnym) ryzykowny leg wchodzi WYŁĄCZNIE z niezależnym
# potwierdzeniem wartości (ev_uk > 0, no-vig konsensusu UK) — sam model nie
# może już przekonać kuponu do gambita własną, niezweryfikowaną przewagą
PROG_RYZYKA_P = 0.55
MAX_RYZYKOWNE = {"bezpieczny": 0, "zbalansowany": 1, "agresywny": 2}

# --- premia za WARTOŚĆ w selekcji legów (profil steruje apetytem na przewagę) ---
# Cel: kupon ma ciągnąć ku legom z REALNĄ przewagą (no-vig UK / value), nie ku
# "nudnym faworytom" @1,10. Premia proporcjonalna do ev (liczbowo, nie sztywny
# mnożnik). Bezpieczny = same kotwice o najwyższej szansie (zero premii value).
WAGA_VALUE_Q = {"bezpieczny": 0.0, "zbalansowany": 0.006, "agresywny": 0.011}
BONUS_MIEKKA = {"bezpieczny": 1.0, "zbalansowany": 0.95, "agresywny": 0.92}
BONUS_MATCHUP = {"bezpieczny": 1.0, "zbalansowany": 0.93, "agresywny": 0.88}
BONUS_SWIEZE = {"bezpieczny": 1.0, "zbalansowany": 0.96, "agresywny": 0.93}
# premia za średnią wartość legów w FUNKCJI CELU wyboru kompletu (nie tylko w
# kolejności kandydatów) — bez tego value wpływałoby marginalnie
WAGA_VALUE_SELEKCJA = {"bezpieczny": 0.0, "zbalansowany": 0.15, "agresywny": 0.30}


def _zaokr(x: float, dp: int) -> float:
    """Zaokrąglenie "pół w górę" jak Math.round w JS — wbudowany round()
    Pythona zaokrągla bankiersko (pół do parzystej) i przy wartości dokładnie
    na granicy dawał inną końcówkę niż kuponBuilder.ts (złamany parytet)."""
    m = 10 ** dp
    return math.floor(x * m + 0.5) / m


def _p_rynku(kurs: float) -> float:
    """Cena rynku po zdjęciu szacowanej marży (devig jednostronny)."""
    return min(max((1.0 / kurs) * (1.0 - MARZA_RYNKU), 1e-6), 1.0 - 1e-6)


def _waga_modelu(l: dict, wagi: dict | None = None) -> float:
    """Ile ufamy p_model vs cenie rynku: płynnie z szerokości przedziału
    wiarygodności (ci), fallback na kubełek pewności, gdy ci brak.

    `wagi` — ZMIERZONE delty per kubełek (wagi_zaufania_z_pomiaru): korekta
    z realnej trafności rozliczonych typów, nakładana NA wagę z ci."""
    ci = l.get("ci")
    w = WAGA_MODELU.get(str(l.get("pewnosc") or ""), WAGA_MODELU_DEFAULT)
    if isinstance(ci, (list, tuple)) and len(ci) == 2:
        try:
            szer = float(ci[1]) - float(ci[0])
        except (TypeError, ValueError):
            szer = -1.0
        if szer >= 0.0:
            w = min(max(WAGA_CI_BAZA - szer, WAGA_CI_MIN), WAGA_CI_MAX)
    if wagi:
        kubelek = str(l.get("pewnosc") or "srednia")
        w = min(max(w + float(wagi.get(kubelek, 0.0)), WAGA_EFF_MIN),
                WAGA_EFF_MAX)
    return w


def _p_skladania(l: dict, wagi: dict | None = None) -> float:
    """Szansa lega DO SKŁADANIA: p_model ściągnięte ku cenie rynku.

    Średnia geometryczna (log-liniowa) p_model i p_rynku, ważona zaufaniem
    do estymaty (_waga_modelu). Im mocniej model rozjeżdża się z rynkiem i im
    szersze widełki szansy, tym mocniej ta korekta obcina deklarowaną
    przewagę; legi zgodne z rynkiem prawie nie drgną.
    """
    w = _waga_modelu(l, wagi)
    return math.exp(
        w * math.log(l["p_model"]) + (1.0 - w) * math.log(_p_rynku(l["kurs"]))
    )


def _leg_value(l: dict, wagi: dict | None = None) -> float:
    """Realna przewaga lega w % (0–30, ujęte w widełki): no-vig UK (ev_uk) to
    najczystszy sygnał (niezależny od naszego modelu — wchodzi wprost).
    Fallback: przewaga deklarowana przez model, ale liczona z UREALNIONEJ
    szansy (_p_skladania) — samodeklarowane +30% na legu średniej pewności
    nie może już windować go w rankingu selekcji. None/ujemne → 0."""
    ev = l.get("ev_uk")
    if ev is None:
        ev = (_p_skladania(l, wagi) * l["kurs"] - 1.0) * 100.0
    try:
        return max(0.0, min(float(ev), 30.0))
    except (TypeError, ValueError):
        return 0.0


# --- kalibracja WAG ZAUFANIA z rozliczeń (pomiar: rozliczanie.compute_wagi_
# zaufania). Zmierzone "ile naprawdę ufać p_model" per kubełek pewności
# zastępuje zgadywane stałe — ten sam wzorzec co kary korelacji niżej.
WAGI_PRIOR = 60.0        # shrink zmierzonej wagi do bazowej (n/(n+prior))
WAGI_DELTA_CAP = 0.25    # maksymalne przesunięcie wagi względem bazowej
WAGA_EFF_MIN, WAGA_EFF_MAX = 0.35, 0.85   # twarde widełki wagi efektywnej


def wagi_zaufania_z_pomiaru(pomiar: dict, prior: float = WAGI_PRIOR) -> dict:
    """Delty wag zaufania per kubełek pewności — ZMIERZONE zamiast zgadywanych.

    `pomiar` = rozliczanie.compute_wagi_zaufania (per kubełek: n, sr_p,
    sr_rynek, hit, w_cel). Delta = (w_cel - waga_bazowa) ściągnięta wagą
    n/(n+prior) i capowana ±WAGI_DELTA_CAP. Zwraca {kubelek: delta}; pusta
    mapa / brak kubełka = zachowanie bez kalibracji.
    """
    out: dict[str, float] = {}
    for kubelek, d in (pomiar or {}).items():
        w_cel, n = d.get("w_cel"), d.get("n", 0)
        if w_cel is None or n < 1:
            continue
        baza = WAGA_MODELU.get(kubelek, WAGA_MODELU_DEFAULT)
        k = n / (n + prior)
        delta = k * (float(w_cel) - baza)
        out[kubelek] = round(
            max(-WAGI_DELTA_CAP, min(WAGI_DELTA_CAP, delta)), 3
        )
    return out


# domyślne kary korelacji jako mapa (nadpisywalna zmierzonymi z rozliczeń)
KARY_DEFAULT = {
    "ta_sama": KARA_TA_SAMA_DRUZYNA,
    "przeciwne": KARA_PRZECIWNE_DRUZYNY,
    "nieznane": KARA_KORELACJI,
}
KARA_PRIOR = 30.0   # shrinkage zmierzonej korelacji do domyślnej (mała próba par)
KARA_MIN = 0.50     # nie tniemy szansy kuponu poniżej połowy (ochrona przed szumem)


def kary_korelacji_z_diagnostyki(korelacja: dict, prior: float = KARA_PRIOR) -> dict:
    """Efektywne kary korelacji per relacja legów — ZMIERZONE zamiast zgadywanych.

    `wsp` = obs_oba/exp_indep z rozliczonych kuponów (rozliczanie.compute_kupony_
    diagnostyka): <1 = legi z jednego meczu padają razem rzadziej niż niezależność
    (kara w dół słuszna), >1 = częściej. Ściągamy zmierzony wsp shrinkage do kary
    domyślnej wagą n/(n+prior) — przy małej próbie zostajemy blisko domyślnej,
    przy dużej ufamy pomiarowi. Cap [KARA_MIN, 1.0]."""
    out = dict(KARY_DEFAULT)
    for rel, d in (korelacja or {}).items():
        if rel not in KARY_DEFAULT:
            continue
        wsp, n = d.get("wsp"), d.get("n_par", 0)
        if wsp is None or n < 1:
            continue
        w = n / (n + prior)
        eff = KARY_DEFAULT[rel] + w * (float(wsp) - KARY_DEFAULT[rel])
        out[rel] = round(max(KARA_MIN, min(1.0, eff)), 3)
    return out


def _kara_koszyka(legi, kary: dict | None = None) -> float:
    """Łączna kara korelacyjna kuponu (mnożnik szansy).

    Za każdy KOLEJNY leg z tego samego meczu: kara zależna od relacji drużyn
    (ta sama / przeciwna / nieznana). `kary` = mapa ZMIERZONA z rozliczeń
    (kary_korelacji_z_diagnostyki); None → domyślne stałe.
    """
    k = kary or KARY_DEFAULT
    ta = k.get("ta_sama", KARA_TA_SAMA_DRUZYNA)
    prz = k.get("przeciwne", KARA_PRZECIWNE_DRUZYNY)
    nzn = k.get("nieznane", KARA_KORELACJI)
    kara = 1.0
    seen: dict[int, list[str]] = {}
    for l in legi:
        m, d = l["mecz_id"], str(l.get("druzyna") or "")
        prev = seen.get(m)
        if prev is not None:
            if d and d in prev:
                kara *= ta
            elif d and all(x and x != d for x in prev):
                kara *= prz
            else:
                kara *= nzn
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
        "matchup_styl": bool(b.get("matchup_styl")),
        "rotacja": bool(b.get("rotacja")),
        "wyzsza_linia": bool(b.get("wyzsza_linia")),
        "miekka_linia": bool(b.get("miekka_linia")),
        # sygnał składu i konsensus UK w chwili selekcji — MUSZĄ jechać dalej
        # do typy_log przez rozliczanie.rozlicz(), inaczej legi trafiające do
        # logu WYŁĄCZNIE przez kupon (większość puli — nie każdy leg zostaje
        # też best-per-side publikowaną okazją) są na zawsze "bezkategoriowe"
        # w diagnostyce miękkich linii / sygnałów XI / marży UK.
        "xi_sygnal": b.get("xi_sygnal"),
        "kurs_ref": b.get("kurs_ref"),
        # realna przewaga lega — do UI (dlaczego ten leg) i scoringu wartości
        "ev_uk": b.get("ev_uk"),
        "ev_pct": b.get("ev_pct"),
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


def _score_selekcji(p_raw: float, legi, waga_value: float = 0.0,
                    kary: dict | None = None,
                    wagi: dict | None = None) -> float:
    """Funkcja celu składania: szansa z karami korelacji + kara SELEKCJI za
    monotonię rynków (3+ legi z jednej rodziny padają razem w nudnym meczu)
    + premia za średnią WARTOŚĆ legów (waga_value>0 = kupon ciągnie ku przewadze)."""
    s = p_raw * _kara_koszyka(legi, kary)
    rodziny: dict[str, int] = {}
    for l in legi:
        f = betting.RODZINY_RYNKOW.get(l.get("rynek_kod", ""))
        if f:
            rodziny[f] = rodziny.get(f, 0) + 1
    nadmiar = sum(max(0, c - 2) for c in rodziny.values())
    s *= DYWERSYFIKACJA_RODZIN ** nadmiar
    if waga_value > 0 and legi:
        sr_ev = sum(_leg_value(l, wagi) for l in legi) / len(legi)
        s *= 1.0 + waga_value * sr_ev / 100.0
    return s


def _zloz_pewniaki(
    pool: list[dict],
    cmin: float,
    cmax: float,
    max_na_mecz: int = MAX_NA_MECZ,
    min_legi: int = 3,
    profil: str = "zbalansowany",
    kary: dict | None = None,
    wagi: dict | None = None,
) -> dict | None:
    """Maksymalizuj szansę kuponu przy kursie łącznym w przedziale [cmin, cmax].

    Beam search (wiązka BEAM_W stanów) zamiast zachłannego dokładania —
    przy ograniczeniach (przedział kursu, max/mecz, dywersyfikacja) greedy
    bywał daleki od optimum albo "nie składał" istniejącej kombinacji.
    Jakość lega = ln(p)/ln(kurs) (koszt pewności na jednostkę kursu) decyduje
    o kolejności kandydatów, przy czym p to szansa UREALNIONA (_p_skladania:
    shrink p_model ku cenie rynku wg pewności estymaty) — model nie może już
    sam siebie przekonać, że ryzykowny leg z deklarowaną przewagą jest lepszy
    od kotwicy. Legi kontekstowe (matchup / świeże składy) dostają lekki
    priorytet. Dodatkowo twardy limit legów ryzykownych (PROG_RYZYKA_P /
    MAX_RYZYKOWNE): wysoki kurs docelowy składa się z większej liczby
    pewnych zdarzeń, nie z pojedynczych grubych strzałów. Przy ustalonym
    kursie max szansa = max EV, więc ten sam builder składa też kupony value.
    """
    # profil charakteru (ustawienie usera): bezpieczny = same kotwice,
    # agresywny = mocniejsza preferencja matchupów i wyższych linii
    if profil == "bezpieczny":
        pool = [b for b in pool if b["p_model"] >= 0.58]
    waga_sel = WAGA_VALUE_SELEKCJA.get(profil, 0.0)
    max_ryzykowne = MAX_RYZYKOWNE.get(profil, 1)

    def _q(b: dict) -> float:
        # bazowa jakość: koszt pewności na jednostkę kursu (q<0; bliżej 0 =
        # lepiej), liczony z UREALNIONEJ szansy — patrz _p_skladania
        q = math.log(_p_skladania(b, wagi)) / math.log(b["kurs"])
        if profil == "bezpieczny":
            return q
        # PREMIA ZA WARTOŚĆ (liczbowo): leg z realną przewagą wchodzi wyżej
        v = _leg_value(b, wagi)
        if v > 0:
            q *= 1.0 - v * WAGA_VALUE_Q[profil]
        if b.get("miekka_linia"):
            q *= BONUS_MIEKKA[profil]
        if b.get("matchup"):
            q *= BONUS_MATCHUP[profil]
        if b.get("swieze_sklady"):
            q *= BONUS_SWIEZE[profil]
        if profil == "agresywny" and (b.get("linia") or 0) >= 1.5:
            q *= 0.97   # wyższe linie wyżej w kolejce
        return q

    def _dopuszczalny(b: dict) -> bool:
        # zbalansowany: gambit (p_model < progu) tylko z niezależnym
        # potwierdzeniem ceny (ev_uk > 0) — filtr na wejściu do przeszukiwania,
        # żeby nie zajmował slotu kandydata
        if profil != "zbalansowany" or b["p_model"] >= PROG_RYZYKA_P:
            return True
        return (b.get("ev_uk") or 0) > 0

    cands = sorted(
        (
            b for b in pool
            if b["kurs"] > 1.0 and 0 < b["p_model"] < 1 and _dopuszczalny(b)
        ),
        key=lambda b: -_q(b),
    )[:MAX_KANDYDATOW]
    # stan wiązki: (kurs_łączny, iloczyn UREALNIONYCH szans do selekcji, legi
    # jako krotka) — wyświetlana szansa kuponu i tak liczy się z p_model legów
    beam: list[tuple[float, float, tuple]] = [(1.0, 1.0, ())]
    komplety: list[tuple[float, float, tuple]] = []
    for b in cands:
        ryzykowny = b["p_model"] < PROG_RYZYKA_P
        nowe = []
        p_sel_b = _p_skladania(b, wagi)
        for kurs, p, legi in beam:
            if len(legi) >= MAX_LEGI_PEWNIAKI:
                continue
            if any(l["podmiot_id"] == b["podmiot_id"] for l in legi):
                continue
            if sum(1 for l in legi if l["mecz_id"] == b["mecz_id"]) >= max_na_mecz:
                continue
            # wysoki kurs = WIĘCEJ pewnych zdarzeń, nie grubsze pojedyncze
            # strzały — limit legów o szansie modelu poniżej progu
            if ryzykowny and sum(
                1 for l in legi if l["p_model"] < PROG_RYZYKA_P
            ) >= max_ryzykowne:
                continue
            kurs2 = kurs * b["kurs"]
            if kurs2 > cmax:
                continue
            legi2 = legi + (b,)
            p2 = p * p_sel_b
            nowe.append((kurs2, p2, legi2))
            if kurs2 >= cmin and len(legi2) >= min_legi:
                komplety.append((kurs2, p2, legi2))
        beam.extend(nowe)
        # prune: obiecujące = wysoka szansa × jak blisko dolnej granicy kursu.
        # Dedup w DWÓCH warstwach:
        #  1) PRAWDZIWE duplikaty (permutacje TEGO SAMEGO zestawu legów) —
        #     zawsze zwiń do jednego, inaczej zapychają wiązkę.
        #  2) RÓŻNE zestawy o przypadkowo identycznym (długość, kurs, score)
        #     (częste przy zbliżonych p_model) — kiedyś zwijane do jednego,
        #     co po cichu gubiło alternatywną, potencjalnie lepszą ścieżkę
        #     dalej w przeszukiwaniu; teraz zostaje kilka reprezentantów per
        #     próg (MAX_TIE_REPR), nie nieskończenie wiele — inaczej pula z
        #     wieloma niemal identycznymi legami (typowe przy dużej lidze)
        #     zapycha CAŁĄ wiązkę stanami tej samej długości i blokuje dojście
        #     do dłuższych kompletów.
        ocenione = []
        tie_repr: dict[tuple, set] = {}
        for st in beam:
            sc = _score_selekcji(st[1], st[2], waga_sel, kary, wagi)
            ident = frozenset(l["podmiot_id"] for l in st[2])
            tier = (len(st[2]), _zaokr(st[0], 4), _zaokr(sc, 8))
            repr_seen = tie_repr.setdefault(tier, set())
            if ident in repr_seen:
                continue
            if len(repr_seen) >= MAX_TIE_REPR:
                continue
            repr_seen.add(ident)
            ocenione.append((sc * min(st[0] / cmin, 1.0), st))
        ocenione.sort(key=lambda x: -x[0])
        # top BEAM_W ogółem + gwarancja MIN_NA_DLUGOSC reprezentantów każdej
        # długości (patrz komentarz przy stałej) — nadzbiór starej wiązki
        wybrane = []
        per_dl: dict[int, int] = {}
        for i, (_, st) in enumerate(ocenione):
            dl = len(st[2])
            if i < BEAM_W or per_dl.get(dl, 0) < MIN_NA_DLUGOSC:
                wybrane.append(st)
                per_dl[dl] = per_dl.get(dl, 0) + 1
        beam = wybrane
    if not komplety:
        return None

    def _kupon_z(kurs: float, legi_t: tuple) -> dict:
        # wyświetlana szansa: iloczyn p_model legów (bez shrinku selekcji)
        p_raw = math.prod(l["p_model"] for l in legi_t)
        p = p_raw * _kara_koszyka(legi_t, kary)
        legi = sorted(
            legi_t, key=lambda b: (b["kickoff_ts"], b["mecz_id"], -b["p_model"])
        )
        return {
            "cel": int(cmin),
            "cel_label": f"{int(cmin)}–{int(cmax)}",
            "styl": "pewniaki",
            "kurs_laczny": _zaokr(kurs, 2),
            "p_model": _zaokr(p, 4),
            "fair_kurs": _zaokr(1.0 / max(p, 1e-9), 2),
            "ev_pct": _zaokr((p * kurs - 1.0) * 100.0, 1),
            "legi": [_leg_dict(b) for b in legi],
        }

    # stabilny tie-break (zestaw podmiotów) — przy równym score zawsze wygrywa
    # ten sam komplet, więc drobna zmiana puli nie „przerzuca” kuponu (mniej churnu
    # zanim slot się zamrozi; opublikowane kupony i tak są zamrożone w logu)
    komplety.sort(
        key=lambda s: (
            -_score_selekcji(s[1], s[2], waga_sel, kary, wagi),
            tuple(sorted(l["podmiot_id"] for l in s[2])),
        )
    )
    kurs, _p_sel, legi_t = komplety[0]
    kupon = _kupon_z(kurs, legi_t)
    # wariant B: najlepszy WYRAŹNIE INNY komplet (Jaccard < 0.5) — do wyboru
    # przez usera; czysto podglądowy, nie zajmuje slotu
    sygn_a = {
        (l["mecz_id"], l["podmiot_id"], l.get("rynek_kod", ""), l["linia"])
        for l in legi_t
    }
    for kurs_b, _p_b, legi_b in komplety[1:]:
        sygn_b = {
            (l["mecz_id"], l["podmiot_id"], l.get("rynek_kod", ""), l["linia"])
            for l in legi_b
        }
        if len(sygn_a & sygn_b) / max(len(sygn_a | sygn_b), 1) < 0.5:
            kupon["wariant_b"] = _kupon_z(kurs_b, legi_b)
            break
    return kupon


def _rentgen(
    kupon: dict,
    pool: list[dict],
    cmin: float,
    cmax: float,
    max_na_mecz: int = MAX_NA_MECZ,
    kary: dict | None = None,
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
        * _kara_koszyka(legi_po, kary) / max(_kara_koszyka(legi, kary), 1e-9)
    )
    if p_po <= kupon["p_model"] + 1e-9:
        return
    kupon["alternatywa"] = {
        **_leg_dict(best),
        "zamiast_idx": idx,
        "kurs_po": _zaokr(kurs_bez * best["kurs"], 2),
        "p_po": _zaokr(p_po, 4),
    }


def _dolozenie(
    kupon: dict,
    pool: list[dict],
    cmin: float,
    cmax: float,
    max_na_mecz: int = MAX_NA_MECZ,
    kary: dict | None = None,
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
    p_raw = kupon["p_model"] / max(_kara_koszyka(legi, kary), 1e-9)
    p_po = p_raw * best["p_model"] * _kara_koszyka(legi_po, kary)
    kupon["dolozenie"] = {
        **_leg_dict(best),
        "kurs_po": _zaokr(kupon["kurs_laczny"] * best["kurs"], 2),
        "p_po": _zaokr(p_po, 4),
    }


def build_kupony(
    bets: list[dict],
    pool: list[dict] | None = None,
    now_ts: int | None = None,
    profil: str = "zbalansowany",
    kary: dict | None = None,
    wagi: dict | None = None,
) -> list[dict]:
    """Kupony pewniaków w dwóch horyzontach + kupony value.

    DZIENNY: mecze z dziś (gdy dziś < 2 mecze — również jutro); przedziały
    kursowe 5-10 / 10-15 / 15-20 / 20-25 (do 4 aktywnych kuponów).
    DŁUGOTERMINOWY: mecze z najbliższych 4 dni; 10-15 / 15-20 / 20-25 / 25-35.
    VALUE: przedziały 4-8 / 8-16, tylko legi z EV >= 2%, max 1 leg na mecz.
    """
    now = now_ts if now_ts is not None else int(time.time())
    pool = [b for b in (pool or []) if b["kickoff_ts"] > now + MARGINES_STARTU_S]
    out: list[dict] = []

    # dzienny: każdy przedział NAJPIERW z samego "dziś"; dopiero gdy się nie
    # składa — dobiera mecze z jutra (decyzja usera)
    dzis20 = [b for b in pool if b["kickoff_ts"] <= now + OKNO_DZIS_S]
    dzis44 = [b for b in pool if b["kickoff_ts"] <= now + OKNO_JUTRO_S]
    tylko_dzis_ok = len({b["mecz_id"] for b in dzis20}) >= 2
    for cmin, cmax in PRZEDZIALY_DZIENNE:
        k = (
            _zloz_pewniaki(dzis20, cmin, cmax, profil=profil, kary=kary, wagi=wagi)
            if tylko_dzis_ok else None
        )
        pula_k = dzis20
        if k is None:
            k = _zloz_pewniaki(dzis44, cmin, cmax, profil=profil, kary=kary, wagi=wagi)
            pula_k = dzis44
        if k is not None:
            k["horyzont"] = "dzienny"
            _rentgen(k, pula_k, cmin, cmax, kary=kary)
            _dolozenie(k, pula_k, cmin, cmax, kary=kary)
            out.append(k)

    dlugo = [b for b in pool if b["kickoff_ts"] <= now + OKNO_DLUGO_S]
    for cmin, cmax in PRZEDZIALY_DLUGOTERMINOWE:
        k = _zloz_pewniaki(dlugo, cmin, cmax, profil=profil, kary=kary, wagi=wagi)
        if k is not None:
            k["horyzont"] = "dlugoterminowy"
            _rentgen(k, dlugo, cmin, cmax, kary=kary)
            _dolozenie(k, dlugo, cmin, cmax, kary=kary)
            out.append(k)

    # VALUE: ten sam builder co pewniaki (max iloczyn szans przy zadanym
    # kursie = max EV), ale pula tylko z wyraźną przewagą i 1 leg na mecz;
    # kupon identyczny z którymś kuponem pewniaków nie wchodzi drugi raz
    cands = [b for b in _kandydaci(bets) if b["kickoff_ts"] > now + MARGINES_STARTU_S]
    sygnatury = {_sygnatura(k) for k in out}
    for cmin, cmax in PRZEDZIALY_VALUE:
        k = _zloz_pewniaki(
            cands, cmin, cmax, max_na_mecz=1, min_legi=2, profil=profil,
            kary=kary, wagi=wagi
        )
        if k is None or _sygnatura(k) in sygnatury:
            continue
        k["styl"] = "value"
        k["horyzont"] = "value"
        _rentgen(k, cands, cmin, cmax, max_na_mecz=1, kary=kary)
        _dolozenie(k, cands, cmin, cmax, max_na_mecz=1, kary=kary)
        out.append(k)
        sygnatury.add(_sygnatura(k))
    return out
