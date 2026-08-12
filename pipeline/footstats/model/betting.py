"""Silnik bettingowy — od prawdopodobieństwa modelu do rankingu okazji.

Kroki:
  1. devig — usunięcie marży bukmachera z kursów (metoda potęgowa; przy
     jednostronnym kwotowaniu odejmujemy szacowaną marżę rynku),
  2. fair odds = 1 / p_model,
  3. edge (pp) i wartość oczekiwana EV%,
  4. confidence 0-100 z komponentów (próba, pewność minut, szerokość CI,
     struktura czynników),
  5. risk — osobno od confidence (rzadkość zdarzenia, rotacja, definicje),
  6. rank_score do sortowania listy okazji.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import optimize
from scipy import stats as _stats

from .. import diagnostyka

# Typowa marża polskich bukmacherów na player props (do jednostronnych kwotowań).
DEFAULT_ONE_SIDED_MARGIN = 0.07


# ---------------------------------------------------------------------------
# PODATEK OD STAWKI — jedno miejsce dla całego systemu (2026-07-31)
# ---------------------------------------------------------------------------
#
# CZEGO BRAKOWAŁO: do 31.07 podatku nie było NIGDZIE — ani w EV, ani w bramach,
# ani w rozliczeniach, ani w kwocie wypłaty na stronie. Wszystkie liczby
# produktu były o kilkanaście punktów procentowych za dobre.
#
# JAK TO DZIAŁA W PL: 12% pobierane od STAWKI przy zawieraniu zakładu. Przy
# stawce 1 j. do gry idzie 0,88 j., więc zwrot z wygranej to 0,88 × kurs.
# Konsekwencja, która nie jest oczywista: przy kursie poniżej 1/0,88 = 1,136
# zakład traci NAWET przy stuprocentowej pewności. Zmierzone 31.07: 28 typów
# na stronie było poniżej tej granicy.
#
# CZEMU TRYB, A NIE STAŁA 0,88: Betclic reklamuje ofertę „bez podatku", część
# operatorów robi zwrot podatku jako bonus, a promocje bywają warunkowe.
# Wpisanie 0,88 na sztywno oznaczałoby, że przy pierwszej takiej ofercie
# trzeba przerabiać rachunek I rozstrzygać, co ze starymi rekordami. Dlatego
# tryb jest ZAPISYWANY PRZY TYPIE (pole `tryb_podatku` w typy_log): historia
# wie, w czym była liczona, a zmiana domyślnego trybu nie tyka przeszłości.
#
# ZWROTY: przy zakładzie anulowanym stawka wraca w całości razem z podatkiem,
# więc `kurs_netto` NIE dotyczy zwrotów — tam zwrot to zawsze dokładnie 1 j.

TRYB_PODATKU_DOMYSLNY = "standard"

WSPOLCZYNNIK_PODATKU = {
    "standard": 0.88,      # 12% od stawki (Superbet, STS — stan na 2026-07)
    "bez_podatku": 1.0,    # promocja „bez podatku" — potwierdzać per oferta
    "zwrot": 1.0,          # podatek oddawany bonusem; rachunek jak bez podatku
}

# Domyślny tryb per bukmacher. Zmiana TUTAJ dotyczy tylko NOWYCH typów —
# stare mają tryb zapisany przy sobie.
TRYB_PODATKU_BUKMACHERA: dict[str, str] = {
    "Superbet": "standard",
    "STS": "standard",
    "Betclic": "standard",
}

# Kurs, poniżej którego zakład jest stratny nawet przy pewności 100%.
# Przy trybie „standard" to 1/0,88 = 1,136.
KURS_GRANICZNY_PODATKU = 1.0 / WSPOLCZYNNIK_PODATKU["standard"]


def tryb_podatku(bukmacher: str | None = None, tryb: str | None = None) -> str:
    """Tryb podatkowy: jawnie podany, po bukmacherze, albo domyślny."""
    if tryb in WSPOLCZYNNIK_PODATKU:
        return tryb
    if bukmacher:
        return TRYB_PODATKU_BUKMACHERA.get(bukmacher, TRYB_PODATKU_DOMYSLNY)
    return TRYB_PODATKU_DOMYSLNY


def wspolczynnik_podatku(tryb: str | None = None) -> float:
    """Ile ze stawki realnie pracuje (0,88 przy standardowym podatku).

    Nieznany tryb (np. rekord z przyszłej wersji) traktujemy jak standardowy —
    bezpieczniej zaniżyć wynik niż go zawyżyć.
    """
    return WSPOLCZYNNIK_PODATKU.get(
        tryb or TRYB_PODATKU_DOMYSLNY,
        WSPOLCZYNNIK_PODATKU[TRYB_PODATKU_DOMYSLNY],
    )


def kurs_netto(kurs: float, tryb: str | None = None) -> float:
    """Kurs po podatku — tyle realnie wraca z 1 j. stawki przy wygranej."""
    return float(kurs) * wspolczynnik_podatku(tryb)


def ev_pct(p: float, kurs: float, tryb: str | None = None) -> float:
    """Wartość oczekiwana zakładu w %, PO PODATKU — liczba dla użytkownika.

    ROZDZIAŁ DWÓCH LICZB (decyzja usera 2026-07-31): `ev_netto` (ta funkcja)
    jest tym, co POKAZUJEMY i czym ROZLICZAMY, a `ev_brutto` niżej zostaje
    tym, czym BRAMY DECYDUJĄ. Powód jest pomiarowy, nie kosmetyczny: gdyby
    podatek wszedł od razu do bram, selekcja zmieniłaby się w tym samym
    momencie co rachunek i w rozliczeniach nie dałoby się rozdzielić skutku
    jednego od drugiego.
    """
    return (float(p) * kurs_netto(kurs, tryb) - 1.0) * 100.0


def ev_brutto_pct(p: float, kurs: float) -> float:
    """Wartość oczekiwana bez podatku — TYLKO do bram publikacji.

    Istnieje po to, żeby miejsca decydujące o publikacji były jawnie
    oznaczone jako liczące brutto, zamiast mieć rozsiane `p * kurs - 1`,
    o których po miesiącu nikt nie wie, czy są celowe.
    """
    return (float(p) * float(kurs) - 1.0) * 100.0


def delta_dla_p(korekta, p: float) -> float:
    """Rozwiąż korektę logitową dla konkretnej szansy `p`.

    Korekta bywa w dwóch postaciach i to jest celowe:
      * `float` — jedna delta na cały strumień (tak było do 2026-07-31),
      * `dict` — `{"global": g, "bins": [[lo, hi, b], ...]}`, czyli delta
        zależna od tego, JAK PEWNY jest model.

    PO CO PRZEDZIAŁY (pomiar 2026-07-31): błąd modelu nie jest jednym
    przesunięciem — on ZMIENIA ZNAK. Na stronie „powyżej" model przeszacowuje
    o 5-11 pp, a na „poniżej" przy kursach 1,9+ NIEDOSZACOWUJE o 16,7 pp
    (mówi 45,8%, wchodzi 62,5%). Jedna liczba na strumień uśrednia dwa błędy
    o przeciwnych znakach i psuje oba naraz. Kalibracja rynkowa ma przedziały
    od dawna; korekta strumienia jako jedyna warstwa uczenia ich nie miała.

    Nieznana postać albo brak korekty = 0.0, czyli „nie ruszaj".
    """
    if isinstance(korekta, dict):
        for lo, hi, b in korekta.get("bins") or []:
            if lo <= p < hi:
                return float(b)
        return float(korekta.get("global", 0.0))
    try:
        return float(korekta or 0.0)
    except (TypeError, ValueError):
        return 0.0


def delta_globalna(korekta) -> float:
    """Sama część globalna korekty — dla miejsc, które nie znają `p`."""
    if isinstance(korekta, dict):
        return float(korekta.get("global", 0.0))
    try:
        return float(korekta or 0.0)
    except (TypeError, ValueError):
        return 0.0


def prog_oplacalnosci(kurs: float, tryb: str | None = None) -> float:
    """Jaka szansa jest potrzebna, żeby wyjść na zero przy tym kursie."""
    netto = kurs_netto(kurs, tryb)
    return 1.0 / netto if netto > 0 else 1.0


# --- NA CZYM STOI LICZBA POKAZANA KLIENTOWI (2026-08-12) -------------------
#
# Warunek wdrożenia V2 z audytu: „100% wymaganych stempli dla wszystkich klas
# typów". Do 12.08 stempel miała WYŁĄCZNIE pętla drużynowa — zmierzone na
# produkcji tego dnia: `kal_rynek` przy 418 z 708 typów drużynowych, przy
# 0 z 4 zawodniczych i 0 z 14 drabinek, a `p_over_raw` nie istniało wcale.
#
# Konsekwencja była praktyczna, nie kosmetyczna: rozłożenie strumienia na
# czynniki (ile dołożyła kalibracja, ile korekta, jaki był surowy model) dało
# się zrobić TYLKO dla drużyn. Dla dwóch strumieni, o które pyta właściciel,
# taki pomiar był niewykonalny — nie z braku danych, tylko dlatego, że typ nie
# zapisywał, skąd wzięła się jego własna liczba.
#
# Stempel jest JEDNYM słownikiem, nie pięcioma polami, bo każde pole osobno
# musiałoby przejść przez białe listy w `build_wc_fast` (`rec_pewniaka`,
# `rec_druzyny`, legi kuponów) — a to jest udokumentowana pułapka: co nie
# zostanie tam wymienione, ginie w drodze z puli na stronę i do księgi.
# Jeden klucz przechodzi raz, a jego zawartość może rosnąć bez ruszania
# tamtych list.
def stempel_rachunku(
    p_over_raw: float | None,
    kal_rynek: float | None = None,
    kal_strumien: float | None = None,
    p_over_final: float | None = None,
    p_pokazane: float | None = None,
    kal_pokazywana: float | None = None,
) -> dict:
    """Komplet „skąd się wzięła ta liczba" — jeden słownik na typ.

    Wszystkie korekty to DELTY LOGITOWE na `p_over` (nie na stronie zakładu),
    bo tylko w tej orientacji mają jeden znak — patrz `w_orientacji_over`
    w `rozliczanie` i awaria odwróconego znaku z 11.08.

    Pola nieznane w danej ścieżce zostają puste. `None` znaczy „ta ścieżka
    tego nie liczy", a nie „zero" — mylenie tych dwóch rzeczy kosztowało nas
    już raz cały pomiar (`brak_kursu` nigdy nie dowodziło braku oferty).
    """
    out: dict[str, float] = {}
    for klucz, wart in (
        ("p_over_raw", p_over_raw),
        ("kal_rynek", kal_rynek),
        ("kal_strumien", kal_strumien),
        ("p_over_final", p_over_final),
        # ⚑ OSTATNIA WARSTWA, JUŻ PO STRONIE ZAKŁADU (2026-08-12). `p_pokazane`
        # to liczba, którą realnie widzi klient — a nie jest ona dopełnieniem
        # `p_over_final`. Zmierzone na dumpie tego dnia: typ team_fouls
        # „poniżej" miał p_over_final 0,3681, więc strona zakładu wychodziła
        # 0,6319, a karta pokazywała 0,6663. Różnicę robi `szansa_pokazywana`
        # (+0,151 logita dla drużyn), nakładana PO wyborze strony i po bramie.
        # Bez tych dwóch pól stempel tłumaczyłby rachunek modelu, ale nie
        # liczbę na karcie — czyli nie to, o co klient by zapytał.
        ("p_pokazane", p_pokazane),
        ("kal_pokazywana", kal_pokazywana),
    ):
        if wart is not None:
            out[klucz] = round(float(wart), 4)
    return out


# ile pól musi mieć stempel, żeby dało się z niego odtworzyć rachunek:
# surowe p, obie korekty i wynik. `p_pokazane` dochodzi dopiero po bramach,
# więc nie wchodzi do kompletu liczonego przy narodzinach typu.
STEMPEL_KOMPLET = ("p_over_raw", "kal_rynek", "kal_strumien", "p_over_final")


def stempel_kompletny(stempel: dict | None) -> bool:
    """Czy z tego stempla da się odtworzyć rachunek typu."""
    return bool(stempel) and all(k in stempel for k in STEMPEL_KOMPLET)

# pokrewne rynki dzielą błąd modelu i korelują przez tempo meczu — wspólna
# mapa dla kalibracji (rozliczanie) i dywersyfikacji kuponów (kupony)
RODZINY_RYNKOW = {
    "shots": "strzelanie", "sot": "strzelanie",
    "shots_outside_box": "strzelanie", "sot_outside_box": "strzelanie",
    "headed_shots": "strzelanie", "headed_sot": "strzelanie",
    "shots_blocked": "strzelanie", "shots_off_target": "strzelanie",
    "fouls_committed": "faule", "fouls_won": "faule", "yellow_card": "faule",
    "tackles": "defensywa", "interceptions": "defensywa",
}

# Przedrostki rynków DRUŻYNOWYCH — jedno źródło prawdy dla klasyfikacji
# strumienia (rozliczanie._strumien) i doboru korekty legów
# (kupony._strumien_lega).
#
# PO CO OSOBNA STAŁA: `match_` (suma meczowa) i `wiecej_` („kto więcej")
# doszły 2026-07-30. Rozliczanie rozpoznawało strumień drużynowy po samym
# `team_`, więc oba nowe rynki liczyły się jako typy ZAWODNICZE, a kupony
# miały już wtedy własną, pełną listę przedrostków. Ten sam typ dostawał
# więc na stronie i w kuponie dwie różne korekty. Skutki po stronie
# rozliczania były ciche, ale realne:
#   * korekta zawodnicza zamiast drużynowej (2026-08-01 przy szansie
#     pokazywanej: −0,482 zamiast −0,197),
#   * 18 rozliczonych nowych rynków zatruwało pomiar strumienia zawodniczego.
PRZEDROSTKI_DRUZYNOWE = ("team_", "match_", "wiecej_")


# --- NA KTÓRYM EKRANIE TYP BYŁ POKAZANY (2026-08-02) ---
#
# Księga zapisywała, CZY typ poszedł na stronę (`poza_publikacja`), ale nigdy
# GDZIE. Skuteczność musiała więc zgadywać po kodzie rynku — i zgadywała źle:
# `match_corners` nie zaczyna się od `team_`, więc rożne całych meczów lądowały
# w zakładce „Zawodnicy" (zgłoszenie usera 2026-08-02: „są jakieś typy
# z niedzieli, mimo że nic nie pokazywało").
#
# Stempel zdejmuje zgadywanie: ekran zapisuje ten sam kod, który decyduje,
# dokąd typ trafia. Zakładka Skuteczności pokazuje wtedy DOKŁADNIE to, co user
# widział, a nie rekonstrukcję.
#
# CZTERY WARTOŚCI, BO TYLE JEST NAPRAWDĘ — a czwarta jest tu najważniejsza:
#   wysokie_szanse — lista na stronie głównej (typ zawodniczy z `pewniak`),
#   druzyny        — zakładka Drużyny,
#   drabinki       — karta w Drabinkach (typ „hero" z radaru),
#   poza_lista     — typ ZAWODNICZY bez `pewniak`. Policzony, opublikowany,
#                    rozliczany… i niewidoczny: od 2026-08-01 nie ma zakładki,
#                    która by go listowała („Wszystko" i „Okazje" zniknęły),
#                    więc trafia najwyżej do paska u góry strony głównej.
#                    Bez tej wartości Skuteczność liczyłaby go do wyniku
#                    ekranu, na którym go nie było.
#
# UWAGA NA EPOKĘ UI przy stemplach ODTWORZONYCH wstecz. „poza_lista" opisuje
# dzisiejszy układ strony. Typy opublikowane PRZED 2026-08-01 stały na wspólnej
# liście, której dziś nie ma — czyli były widoczne, choć reguła nazywa je tak
# samo. Dlatego rekonstrukcja zostawia `ekran_odtworzony`, a UI ma przy takich
# dniach powiedzieć wprost, że podział jest odtworzony. Nie próbujemy zgadywać
# epoki po dacie: układ strony zmieniał się częściej niż raz i pierwsza taka
# heurystyka byłaby fałszywą precyzją.
EKRANY = ("wysokie_szanse", "druzyny", "drabinki", "poza_lista")


def ekran_typu(b: dict) -> str:
    """Ekran, na którym typ się pokazał — po rekordzie, bez zgadywania.

    Czyta zarówno świeży rekord (ma `podmiot_typ`), jak i wpis z księgi
    (ma tylko `rynek_kod`), żeby ten sam kod dał się użyć do stemplowania
    nowych typów i do odtworzenia stempla dla historii.
    """
    if b.get("zrodlo"):
        return "drabinki"
    if b.get("podmiot_typ") == "druzyna" or str(
        b.get("rynek_kod") or ""
    ).startswith(PRZEDROSTKI_DRUZYNOWE):
        return "druzyny"
    return "wysokie_szanse" if b.get("pewniak") else "poza_lista"


# --- WERSJONOWANIE POLITYKI (2026-08-01) ---
#
# Problem, który to rozwiązuje, nazywa się „selection-induced miscalibration",
# ale objawia się bardzo konkretnie: kalibracja ściąga `p` CAŁEGO strumienia,
# a brama publikacji natychmiast wybiera nowy czub rozkładu — więc opublikowany
# zbiór ZAWSZE deklaruje ~71%, choćby korekta była dowolnie duża. Bez zapisu,
# WEDŁUG JAKIEJ REGUŁY typ został wybrany, nie da się rozdzielić „model się
# poprawił" od „zmieniliśmy selekcję".
#
# To nie jest teoria. Dwa razy w ciągu tygodnia pomiar na tym logu dał zły
# wynik, bo mieszał epoki:
#   * 2026-07-31: okno zgody weszło 27.07, a w logu leżały starsze rekordy
#     publikowane regułą ±22 pp — wniosek „wstrzymane typy zarabiają +13,2%"
#     trzeba było odwołać,
#   * 2026-08-01: nowe rynki sprzed dopięcia bram (18 rozliczeń, trafiły 83%
#     przy deklarowanych 58%) przesunęły korektę strumienia drużynowego
#     z −0,324 na −0,179 — czyli liczbę POKAZYWANĄ userowi ruszyło 18 rekordów
#     z polityki, której już nie ma.
#
# ZASADA: każda zmiana, która rusza SELEKCJĄ (progi, bramy, okna), podbija
# `WERSJA_POLITYKI`. Zmiana w rachunku `p` podbija `WERSJA_MODELU`. Zmiana
# w warstwach uczenia (kalibracja rynkowa, korekta strumienia) podbija
# `WERSJA_KALIBRACJI`. Zmiana źródeł/zakresu danych — `WERSJA_DANYCH`.
# Wersja jedzie ZAMROŻONA przy typie, więc historia zawsze wie, czym była.
#
# Format: data wdrożenia + krótki slug. Data pierwsza, żeby sortowanie
# leksykalne dawało chronologię.
# ⚑ 2026-08-11: kalibracja uczona w orientacji „powyżej"
# (rozliczanie.w_orientacji_over). Delty dla rynków drużynowych ZMIENIAJĄ ZNAK,
# więc rekordy sprzed tej chwili opisują inny produkt i NIE WOLNO ich mieszać
# z nowymi w żadnym pomiarze kalibracji. Epoka produktu zostaje „liga" —
# zmienia się rachunek, nie zakres rozgrywek.
# ⚑ 2026-08-12: prior przedziału kalibracji to ZERO, nie wartość rynku
# (rozliczanie: PRIOR PRZEDZIAŁU). Delty w górnych przedziałach zmieniają
# znak — `team_corners` 0,70-0,85 idzie z +0,443 na −0,588 — więc rekordy
# sprzed tej chwili znowu opisują inny produkt. Rachunek `p` bez zmian, stąd
# `WERSJA_MODELU` stoi.
WERSJA_MODELU = "2026-08-11-orientacja-over"
WERSJA_KALIBRACJI = "2026-08-12-prior-przedzialu"
WERSJA_POLITYKI = "2026-08-01-podloga-kursu"
WERSJA_DANYCH = "2026-07-27-liga-klubowa"


def wersje_publikacji() -> dict[str, str]:
    """Stempel wersji do zamrożenia przy publikowanym typie."""
    return {
        "model": WERSJA_MODELU,
        "kalibracja": WERSJA_KALIBRACJI,
        "polityka": WERSJA_POLITYKI,
        "dane": WERSJA_DANYCH,
    }


def implied_probs_two_way(over_odds: float, under_odds: float) -> tuple[float, float]:
    """Devig dwustronny metodą potęgową.

    Szukamy k takiego, że (1/over)^k + (1/under)^k = 1.
    Metoda potęgowa lepiej niż proporcjonalna oddaje favourite-longshot bias,
    który na propsach jest silny.
    """
    p_over_raw = 1.0 / over_odds
    p_under_raw = 1.0 / under_odds
    total = p_over_raw + p_under_raw
    if total <= 1.0:  # brak marży / kurs arbitrażowy — bierzemy wprost
        return p_over_raw, p_under_raw

    def overround(k: float) -> float:
        return p_over_raw**k + p_under_raw**k - 1.0

    try:
        k = optimize.brentq(overround, 1.0, 5.0, xtol=1e-10)
        return float(p_over_raw**k), float(p_under_raw**k)
    except ValueError:
        # awaryjnie: proporcjonalnie
        return p_over_raw / total, p_under_raw / total


def implied_prob_one_sided(odds: float, margin: float = DEFAULT_ONE_SIDED_MARGIN) -> float:
    """Devig jednostronny: odejmij szacowaną marżę rynku od kursu."""
    return float(np.clip((1.0 / odds) * (1.0 - margin), 1e-6, 1.0 - 1e-6))


# Typowa marża JEDNOSTRONNA konsensusu UK na propsach zawodniczych. Niższa niż
# PL (DEFAULT_ONE_SIDED_MARGIN=0.07), bo mediana z kilku ostrych buków (Bet365,
# Skybet...) częściowo znosi wychylenia. Świadome założenie — statshub daje tylko
# stronę „over", więc marży nie da się usunąć dwustronnie (over/under). Kandydat
# do kalibracji z rozliczeń: porównać p_novig do realnej częstości trafień.
UK_CONSENSUS_MARGIN = 0.045


def no_vig_prob_uk(
    uk_over_odds: list[float], margin: float = UK_CONSENSUS_MARGIN
) -> tuple[float, float] | None:
    """No-vig z konsensusu bukmacherów UK (statshub) — benchmark uczciwej ceny.

    statshub oddaje wyłącznie stronę „over" z kilku buków UK. Bierzemy medianę
    (odporną na jednego odstającego buka) i zdejmujemy jednostronną marżę UK.
    To najczystszy dostępny sygnał „prawdziwej" ceny rynku: linia Superbetu
    płacąca wyraźnie WIĘCEJ, niż wynika z no-vig UK, to miękka linia.

    Zwraca (p_fair, fair_odds) albo None, gdy brak sensownych kursów UK.
    """
    ok = [o for o in uk_over_odds if o and o > 1.0]
    if not ok:
        return None
    med = float(np.median(ok))
    p_fair = implied_prob_one_sided(med, margin)
    return p_fair, 1.0 / p_fair


def internal_fair_odds(lines_probs: dict[float, float]) -> dict[float, float]:
    """Samospójność SIATKI LINII jednego bukmachera — line shopping bez
    zewnętrznych kursów.

    Wszystkie linie jednego rynku (0,5 / 1,5 / 2,5...) opisują JEDEN rozkład
    zliczeniowy. Dla każdej linii dopasowujemy Poissona do POZOSTAŁYCH
    (leave-one-out) i liczymy jej fair kurs netto. Linia płacąca wyraźnie
    więcej, niż wynika z reszty siatki, to pomyłka tradera — dokładnie
    wzorzec "reszta rynku 1,55, a tu 2,20", tylko z własnej oferty buka.

    lines_probs: {linia: p_over po devigu}. Zwraca {linia: fair_kurs_netto}
    tylko dla linii, gdzie fit z pozostałych jest wiarygodny (>=2 zgodne
    punkty, rozrzut lambd <= 1.35x).
    """
    out: dict[float, float] = {}
    items = sorted(lines_probs.items())
    if len(items) < 3:
        return out

    def _lam(line: float, p: float) -> float | None:
        thr = math.floor(line)          # "powyżej l,5" = X > floor(l)

        def f(lam: float) -> float:
            return float(_stats.poisson.sf(thr, lam)) - p

        try:
            if f(0.01) * f(15.0) > 0:
                return None
            return float(optimize.brentq(f, 0.01, 15.0))
        except Exception as e:
            # solver nie zbiegł = nie wykryjemy „miękkiej linii" (błędu
            # tradera) w tym meczu. Cicho, bo to normalna ścieżka — ale gdy
            # zdarza się MASOWO, znaczy że siatka kursów przyszła połamana
            diagnostyka.cichy("betting", "solver_fair_odds", e)
            return None

    lams = {
        l: _lam(l, p) for l, p in items if 0.03 < p < 0.97
    }
    for l, _p in items:
        rest = [v for k, v in lams.items() if k != l and v is not None]
        if len(rest) < 2 or min(rest) <= 0:
            continue
        if max(rest) / min(rest) > 1.35:
            continue  # siatka wewnętrznie niespójna — nie ufaj fitowi
        lam_ref = sum(rest) / len(rest)
        p_fair = float(_stats.poisson.sf(math.floor(l), lam_ref))
        if p_fair > 1e-6:
            out[l] = 1.0 / p_fair
    return out


@dataclass(frozen=True)
class ConfidenceInputs:
    effective_matches: float      # efektywna próba zawodnika (po wygaszaniu)
    minutes_certainty: float      # 0..1 z modelu minut
    ci_width: float               # szerokość przedziału na P(over), 0..1
    context_magnitude: float      # |iloczyn czynników - 1| — jak mocno kontekst dźwiga edge
    market_calibrated: bool       # czy rynek ma potwierdzoną kalibrację w backteście
    is_rare_market: bool


def confidence_score(inp: ConfidenceInputs) -> float:
    """Zwraca 0-100. Składowe ważone, projektowane tak, żeby:
    * mała próba lub niepewne minuty zabijały pewność,
    * szeroki przedział na p obniżał ją mocno,
    * edge zbudowany głównie na kontekście (a nie bazie) był karany.
    """
    # próba: 0 przy 2 meczach, ~1 przy 25+
    sample = float(np.clip((inp.effective_matches - 2.0) / 23.0, 0.0, 1.0))
    minutes = float(np.clip(inp.minutes_certainty, 0.0, 1.0))
    # szerokość CI: 0.05 -> świetnie, 0.30 -> fatalnie
    precision = float(np.clip(1.0 - (inp.ci_width - 0.05) / 0.25, 0.0, 1.0))
    # kontekst > +-15% => kara narastająca
    context_penalty = float(np.clip((inp.context_magnitude - 0.15) / 0.25, 0.0, 1.0))

    score = 100.0 * (0.35 * sample + 0.30 * minutes + 0.35 * precision)
    score *= 1.0 - 0.30 * context_penalty
    if not inp.market_calibrated:
        score *= 0.85
    if inp.is_rare_market:
        score *= 0.75
    return float(np.clip(score, 0.0, 100.0))


def confidence_level(score: float) -> str:
    if score >= 65.0:
        return "wysoka"
    if score >= 40.0:
        return "srednia"
    return "niska"


def risk_level(
    lam: float,
    is_rare_market: bool,
    minutes_certainty: float,
    is_prob_market: bool = False,
) -> str:
    """Ryzyko — niezależne od pewności modelu: zmienność samego zdarzenia.

    Dla rynków LICZNIKOWYCH (strzały, faule...) `lam` to oczekiwana liczba
    zdarzeń — progi 0.6/1.2 mierzą, jak rzadkie (a więc kapryśne) jest zdarzenie.

    Dla rynków BINARNYCH (`is_prob_market`, np. żółta kartka) `lam` to
    prawdopodobieństwo zdarzenia w [0,1] — progi licznikowe są tu bez sensu
    (P<0.6 dawało zawsze „wysokie"). Zamiast tego mierzymy zdecydowanie zdarzenia:
    im bliżej 50/50, tym większa loteria.
    """
    if is_prob_market:
        decisiveness = abs(lam - 0.5) * 2.0   # 0 = rzut monetą, 1 = zdarzenie pewne
        if minutes_certainty < 0.5 or decisiveness < 0.30:
            return "wysokie"
        if decisiveness < 0.60:
            return "srednie"
        return "niskie"
    if is_rare_market or lam < 0.6:
        return "wysokie"
    if lam < 1.2 or minutes_certainty < 0.5:
        return "srednie"
    return "niskie"


@dataclass(frozen=True)
class ValueAssessment:
    side: str                 # 'powyzej' | 'ponizej'
    model_prob: float
    implied_prob: float
    fair_odds: float
    edge_pp: float
    ev_pct: float          # BRUTTO — tym decydują bramy
    ev_netto: float        # PO PODATKU — to widzi użytkownik
    tryb_podatku: str
    confidence: str
    confidence_score: float
    risk: str
    rank_score: float


# Minimalne progi publikacji okazji
MIN_EV_PCT = 1.0   # decyzja użytkownika 2026-07-03: pokazuj każdą dodatnią wartość od +1%
MIN_EV_PCT_RARE = 5.0
MIN_CONFIDENCE_SCORE = 25.0
# MAX_MODEL_MARKET_DIVERGENCE/MAX_RELATIVE_DIVERGENCE: ZAŁOŻENIA ustawione "na
# oko" (jak było UK_CONSENSUS_MARGIN przed pomiarem) — nie ma jeszcze gruntu
# kalibracji mierzącego, ile typów odrzuconych tymi progami faktycznie by
# trafiło, gdyby je przepuścić. Kandydat na kolejny "grunt pomiaru": logować w
# typy_log próbki TUŻ PONIŻEJ progu (odrzucone, ale bliskie) i porównać ich
# realny hit-rate z przepuszczonymi, zanim ruszy się same liczby.
MAX_MODEL_MARKET_DIVERGENCE = 0.22  # różnica p_model vs p_rynku > 22 pp = podejrzana
MAX_RELATIVE_DIVERGENCE = 1.9       # p_model / p_rynku > 1.9x = podejrzane (longshoty!)

# --- OKNO ZGODY Z RYNKIEM: brama PUBLIKACJI (pomiar 2026-07-27) ---
# Grunt pomiaru zapowiadany wyżej wreszcie jest. 336 rozliczonych typów
# z kursem, pogrupowanych po tym, o ile p_model przebija cenę rynku po devigu:
#
#   poniżej ceny   n= 36   trafia 58,3%   ROI −22,4%
#   +0 do +2 pp    n= 26   trafia 80,8%   ROI  +7,0%
#   +2 do +5 pp    n= 44   trafia 72,7%   ROI  +4,0%
#   +5 do +8 pp    n= 48   trafia 68,8%   ROI  −6,6%
#   +8 do +12 pp   n= 55   trafia 61,8%   ROI  −5,9%
#   +12 do +18 pp  n= 83   trafia 44,6%   ROI −27,7%
#   ponad +18 pp   n= 44   trafia 45,5%   ROI −29,3%
#
# Zależność jest MONOTONICZNA na całej rozpiętości: im mocniej rozchodzimy się
# z bukmacherem, tym gorzej trafiamy. To nie jest dopasowanie do szumu, tylko
# klasyczna selekcja negatywna — bukmacher rozjeżdża się z nami najbardziej
# tam, gdzie wie coś, czego my nie wiemy (kontuzja, rotacja, waga meczu).
# Stary limit 22 pp przepuszczał CAŁE pole straty.
#
# Odcięcie samym tym oknem: 336 -> 151 typów, ROI −13,9% -> −1,3%.
# Razem z kwarantanną rynków (już działa): 69 typów, ROI +11,6%, bilans +8u.
#
# Dolna granica nie jest kosmetyczna: typy WYCENIONE PONIŻEJ ceny rynku
# (bierzemy je dla samej wysokiej szansy) tracą 22% — nie ma powodu ich grać.
#
# To brama PUBLIKACJI, nie scoringu: typ poza oknem dalej się liczy, rozlicza
# i uczy kalibrację (poza_publikacja="rozjazd_z_rynkiem"), więc za miesiąc da
# się ten pomiar powtórzyć i próg poprawić.
#
# --- POPRAWKA GRANIC (powtórzony pomiar 2026-07-27, 408 rozliczonych typów) ---
# Ten sam pomiar na cieńszych plasterkach pokazał, że +10 pp cięło 2 pp ZA
# WCZEŚNIE — pole straty zaczyna się dopiero przy +14 pp, i to skokiem:
#
#   dół:  −4..−3 pp  n=13  69,2%  −11,6%     góra:  +8..+10 pp  n=34  67,6%   −6,1%
#         −3..−2 pp  n= 8  62,5%  −13,0%            +10..+12 pp n=23  56,5%   +4,5%
#         −2..−1 pp  n=11  54,5%  −29,8%            +12..+14 pp n=26  61,5%   +0,1%
#         −1..0  pp  n=16  56,2%  −25,4%            +14..+18 pp n=58  37,9%  −39,2%
#         +0..+1 pp  n=12  66,7%   −7,1%            ponad +18   n=44  45,5%  −29,3%
#         +1..+2 pp  n=15  86,7%  +11,1%
#
# DOLNA granica potwierdzona po raz drugi: pod zerem nie ma nic do odzyskania,
# każdy plasterek traci. Hipoteza "dopuśćmy −2..0 pp przy wysokiej szansie"
# jest OBALONA (to najgorsze plasterki w całym zestawieniu), nie wracamy do niej.
#
# GÓRNA idzie z +10 na +12: 157 -> 180 typów, bilans −0,6u -> +0,5u, a do klifu
# przy +14 zostaje 2 pp zapasu. Wariant +14 (206 typów, +0,5u, drużynowe +8,4u)
# jest kuszący, ale stoi dokładnie na krawędzi — decyzja użytkownika 2026-07-27:
# bierzemy +12 i wracamy do tego po kolejnej setce rozliczeń.
# --- TRZECI POMIAR (2026-08-04, 727 rozliczeń BIEŻĄCEJ EPOKI, bez mundialu) ---
# Wróciliśmy tu „po kolejnej setce rozliczeń", tak jak zapowiedziano wyżej —
# i próba jest dziś inna: tamte granice powstały na księdze, która w 27% była
# mundialem, a produktem jest liga.
#
#   pasmo         n     ROI      trafień
#   +0..+4 pp    31   +11,9%      58%
#   +4..+8 pp    90    −8,3%      51%
#   +8..+12 pp  238    −0,8%      63%     <- koniec dzisiejszego okna
#   +12..+16 pp 163    −2,0%      58%     <- ODCINANE, a zachowuje się TAK SAMO
#   +16..+20 pp 126   −11,2%      54%     <- tu jest prawdziwy klif
#   +20 pp i da  63    −5,9%      57%
#
# Brama przy +12 NIE ODDZIELA dobrego od złego: pasmo tuż za nią ma −2,0%
# wobec −1,6% dla całego dzisiejszego okna, a rozbicie na czas daje ten sam
# obraz po obu stronach (starsza połowa +7,2% vs +9,0%, nowsza −10,6% vs −11,2%).
# Klif, dla którego tę bramę stawiano, przesunął się na +16 pp.
#
# KOSZT I ZYSK: okno do +16 dokłada 163 rozliczone typy (podaż +45%), a ROI
# całości nie rusza się z miejsca (−1,6% -> −1,7%). To jest zmiana o PODAŻ,
# nie o zysk — i tak została przedstawiona użytkownikowi.
#
# SŁABOŚĆ NAZWANA WPROST: wewnątrz pasma 12–16 wynik skacze (12–14 wypada źle,
# 14–16 dobrze), więc +16 jest wyborem OSTROŻNYM, nie optimum. Dane mówią
# pewnie tylko dwie rzeczy: „+12 jest za nisko" i „za +16 zaczyna się strata".
#
# Powód, dla którego to w ogóle mierzyliśmy: ta brama zjadała 54 z 86 gotowych
# kandydatów jednego cyklu — dwie trzecie całego głodu typów na stronie.
OKNO_ZGODY_MIN = 0.00   # p_model musi być co najmniej na poziomie ceny rynku
OKNO_ZGODY_MAX = 0.16   # ...i najwyżej 16 pp nad nią (2026-08-04, było 0.12)


def w_oknie_zgody(p_model: float, kurs: float) -> bool:
    """Czy typ mieści się w oknie zgody z rynkiem (patrz OKNO_ZGODY_*)."""
    if not kurs or kurs <= 1.0:
        return False
    roznica = float(p_model) - implied_prob_one_sided(float(kurs))
    return OKNO_ZGODY_MIN <= roznica < OKNO_ZGODY_MAX
MAX_ODDS = 6.0                      # kursy wyżej to loteria, nie systematyczny betting
MIN_ODDS = 1.19                     # poniżej 1.19 gra się nie opłaca (decyzja użytkownika)
MAX_CI_WIDTH = 0.30                 # zbyt szerokie widełki szansy = nie stawiamy

# --- BRAMA UZASADNIEŃ: półka „więcej płacą" (2026-08-05) -------------------
#
# Strona dzieli typy na dwie półki: „częściej wchodzą" (szansa >= 70%)
# i „więcej płacą" (niżej, za to wyższy kurs). Typ z tej drugiej BEZ rozpisanego
# rachunku jest dla kupującego strzałem w ciemno, a dla nas rzeczą najtrudniejszą
# do obrony — bo jedyne, co go usprawiedliwia, to nasze liczenie.
#
# WŁĄCZONE DOPIERO PO POMIARZE, w kolejności, która była warunkiem, nie
# preferencją (patrz notatka „druzyny: przeglad sprzedazowy"):
#   02.08  półka miała 9 typów, komplet materiału JEDEN — brama zostawiłaby 1 z 9,
#   05.08  po dosypaniu formy i naprawie rejestru: 6 z 9. Dopiero to jest cena,
#          którą wolno zapłacić.
#
# Trzy typy, które dziś odpadają, to dokładnie te, których nie umiemy wytłumaczyć
# (brak czynników albo brak przedziału ufności) — czyli brama robi to, co ma.
#
# PRÓG MUSI SIĘ ZGADZAĆ Z FRONTEM (`PROG_PEWNE` w `web/src/components/
# DruzynyTablica.tsx`) — inaczej brama tnie inną półkę, niż strona pokazuje.
# Pilnuje tego `test_brama_uzasadnien.py`; nie zmieniać jednego bez drugiego.
PROG_POLKI_PEWNE = 0.70


def wymaga_uzasadnienia(p_model: float) -> bool:
    """Czy typ jest na półce „więcej płacą" i musi mieć rozpisany rachunek."""
    return float(p_model or 0.0) < PROG_POLKI_PEWNE


def ma_komplet_uzasadnienia(b: dict) -> bool:
    """Czy da się z tego zbudować kroki „skąd ta liczba" i „co ją zmienia".

    Sprawdzamy DOKŁADNIE to, z czego karta buduje rozwinięcie: czynniki
    (mnożniki rywala, sędziego, wyjazdu...) i przedział ufności. Historii formy
    tu NIE wymagamy — dosypuje ją `scal_forme_druzyn` już po publikacji, więc
    warunek na nią byłby sprawdzany za wcześnie i kasowałby typy, które na
    stronie mają komplet. Zmierzone 05.08: na drużynowych warunek na sam
    rachunek daje ten sam wynik co rachunek + forma (6 z 9).
    """
    ci = b.get("ci") or [None, None]
    return bool(b.get("czynniki")) and ci[0] is not None

# --- PROFILE LEGA ZAWODNICZEGO (przeniesione z build_wc_fast 2026-08-03) ---
#
# To jest POLITYKA, a nie szczegół budowania listy — a leżała wpisana liczbami
# w środku pętli, więc nie dało się jej ani przetestować, ani nazwać w
# diagnostyce. Wartości bez zmian; przenosiny są po to, żeby powiedzieć, KTÓRY
# warunek uciął typ (patrz `powod_profilu_zawodnika`).
PROFIL_PEWNY_MAX_ODDS = 2.80        # pewniak: niski kurs, wysoka szansa
PROFIL_PEWNY_MIN_P = 0.52
PROFIL_PERELKA_ODDS = (1.90, 3.60)  # perełka: wyższy kurs, wciąż solidna szansa
PROFIL_PERELKA_MIN_P = 0.42
PROFIL_NISZOWA_MIN_P = 0.40         # rynek niszowy + sprzyjający profil rywala


def powod_profilu_zawodnika(
    odd: float, p_side: float, p_dec: float,
    rzadki: bool = False, matchup: bool = False,
) -> str:
    """Dlaczego ta linia nie weszła w żaden profil lega — kod powodu.

    POWÓD ROZDZIELENIA (2026-08-03). Wszystkie te warunki miały jeden wspólny
    komunikat („kwotowane linie nie łączą sensownego kursu z szansą"), więc
    137 odrzuceń dziennie nie mówiło NIC o tym, co właściwie tnie. Dokładnie
    ta sama ślepota, którą po stronie drużynowej rozdzieliliśmy 2026-07-27
    (`powod_widelek`) — i tam się okazało, że wina jest gdzie indziej, niż
    wszyscy zakładali.

    Kolejność od NAJBLIŻSZYCH publikacji: typ, któremu zabrakło tylko wartości,
    jest ciekawszy niż taki, którego kurs w ogóle nie mieści się w paśmie.
    """
    lo_p, hi_p = PROFIL_PERELKA_ODDS
    w_pasmie_pewny = MIN_ODDS <= odd <= PROFIL_PEWNY_MAX_ODDS
    w_pasmie_perelka = lo_p <= odd <= hi_p
    if not w_pasmie_pewny and not w_pasmie_perelka:
        return "kurs_poza_pasmem"
    prog = min(
        PROFIL_PEWNY_MIN_P if w_pasmie_pewny else 1.0,
        PROFIL_PERELKA_MIN_P if w_pasmie_perelka else 1.0,
        PROFIL_NISZOWA_MIN_P if (rzadki and matchup and w_pasmie_perelka) else 1.0,
    )
    if p_side < prog:
        return "szansa_za_niska"
    if p_dec * odd - 1.0 < 0.0:
        return "wartosc_ujemna_przy_ostroznym"
    return "profil_ok"


# nazwy powodów po ludzku — do `odrzucenia` i podsumowania cyklu
POWODY_PROFILU_PL = {
    "kurs_poza_pasmem": "kurs poza pasmem profilu (1,19–2,80 lub 1,90–3,60)",
    "szansa_za_niska": "kurs w paśmie, ale szansa poniżej progu profilu",
    "wartosc_ujemna_przy_ostroznym": (
        "kurs i szansa w normie, ale przy szansie OSTROŻNEJ wartość wychodzi ujemna"
    ),
}


def kurs_w_widelkach(kurs) -> bool:
    """Czy kurs mieści się w widełkach produktu (MIN_ODDS..MAX_ODDS).

    PODŁOGA NA WYJŚCIU, nie tylko przy narodzinach typu (2026-08-01).
    `MIN_ODDS` był sprawdzany wyłącznie tam, gdzie typ POWSTAJE (`assess`,
    widełki drużynowe). Tymczasem lista na stronie w większości składa się
    z typów WZNOWIONYCH — a ścieżka wznowienia (`scal_z_publikacjami`, drugie
    źródło: księga rozliczeń) nie sprawdzała niczego. Skutek zgłoszony przez
    usera i zmierzony na produkcji 2026-08-01: pięć typów „rożne w meczu —
    poniżej" po kursie 1,05–1,09, opublikowanych 31.07 PRZED naprawą bram
    nowych rynków, wracało na stronę i do puli kuponów (28 takich legów)
    aż do gwizdka, czyli jeszcze przez dwa dni.

    Brak kursu (sugestia) NIE jest odrzuceniem — sugestia nie jest zakładem.
    """
    if kurs is None:
        return True
    try:
        k = float(kurs)
    except (TypeError, ValueError):
        return False
    return MIN_ODDS <= k <= MAX_ODDS

# GRUNT POMIARU progów (zapowiadany w komentarzu wyżej): typ odrzucony
# DOKŁADNIE JEDNYM kryterium o mniej niż poniższe tolerancje trafia do
# typy_log z flagą `odrzucony` — rozlicza się w tle (POZA kalibracją,
# skutecznością i UI), a diagnostyka porównuje jego realny hit-rate z
# przepuszczonymi. Dopiero ten pomiar uzasadni ruszanie samych progów.
NEAR_EV_PP = 3.0        # EV do 3 pp poniżej progu
NEAR_CONF = 10.0        # confidence do 10 pkt poniżej progu
NEAR_DIV = 0.06         # rozjazd model-rynek do 6 pp ponad limit
NEAR_REL = 0.3          # rozjazd względny do 0.3x ponad limit


# --- WIDEŁKI KURS×SZANSA DLA RYNKÓW DRUŻYNOWYCH ---
# Typ drużynowy wchodzi do puli, jeśli mieści się w którymkolwiek przedziale:
# kurs w widełkach ORAZ szansa nad progiem ORAZ dodatnia wartość na p ostrożnym.
#
# TO SĄ ZAŁOŻENIA, NIE POMIAR — i to NAJWIĘKSZE sito w całym systemie.
# Dry-run 2026-07-27: 1372 odrzucenia tą bramą wobec 66 oknem zgody z rynkiem
# i 12 krótką historią. Każdy inny próg w projekcie przeszedł już weryfikację
# rozliczeniami (rozjazd z rynkiem, kwarantanna rynków, kwarantanna kategorii);
# ten stoi nietknięty od czasu, gdy go wpisano „na oko".
#
# Co już wiadomo BEZ czekania na rozliczenia (rachunek, nie przeczucie):
#  * progi szansy 0,52 i 0,42 to niemal dokładnie PRÓG OPŁACALNOŚCI na górnych
#    granicach swoich przedziałów: 1/1,92 = 0,52 i 1/2,38 = 0,42. Czyli nie są
#    niezależnym sitem — w większości zakresu wiąże ten sam warunek, co żądanie
#    dodatniej wartości. Ruszanie ich osobno niewiele da.
#  * PRAWDZIWYM sitem jest wymóg dodatniej wartości na p OSTROŻNYM, czyli na
#    średniej z p i dolnej granicy przedziału ufności. Przy szerokim przedziale
#    (a rynki drużynowe świeżo z banku mają szerokie) to schodzi kilka-kilkanaście
#    pp poniżej p i zabiera typ, który na samym p wychodziłby na plus.
#  * sufit kursów wychodzi na 3,60 (suma obu przedziałów to 1,19–3,60), podczas
#    gdy typy zawodnicze mają MAX_ODDS=6,0. Nikt nie uzasadnił tej różnicy.
# ŻADNEGO z nich nie ruszamy bez rozliczeń — po to są typy pomiarowe niżej.
#
# Dlatego zamiast ruszać liczby: rozdzielamy DIAGNOSTYKĘ na trzy powody
# (widziemy wreszcie, który warunek tnie) i logujemy odrzucenia TUŻ pod progiem
# jako typy pomiarowe — dokładnie tak, jak zmierzyliśmy próg rozjazdu.
WIDELKI_DRUZYNOWE = (
    # (kurs_min, kurs_max, minimalna szansa)
    (MIN_ODDS, 2.80, 0.52),   # „pewniak": niski kurs, wysoka szansa
    (1.90, 3.60, 0.42),       # „perełka": wyższy kurs, niższa szansa
)
# tolerancje pomiaru: o ile typ może minąć się z progiem, żeby trafić do logu
# jako `odrzucony` (rozlicza się w tle, poza kalibracją, skutecznością i UI)
NEAR_WIDELKI_KURS = 1.4     # kurs do 1,4x ponad sufit widełek
NEAR_WIDELKI_P = 0.08       # szansa do 8 pp poniżej progu
NEAR_WIDELKI_EV = 0.04      # wartość na p ostrożnym do 4 pp pod zerem


def widelki_druzynowe_ok(odd: float, p: float, p_ostrozne: float) -> bool:
    """Czy typ drużynowy przechodzi bramę kurs×szansa (patrz WIDELKI_DRUZYNOWE).

    LICZONE BRUTTO, ŚWIADOMIE (decyzja usera 2026-07-31). Policzone zostało,
    co się stanie po wpięciu podatku TU: lista 138 -> 6 typów, bo model gra
    medianą kursu 1,25, a po podatku sens mają dopiero kursy od ~1,96.
    Podatek wchodzi więc najpierw do TEGO, CO POKAZUJEMY I ROZLICZAMY
    (`ev_netto`, bilans, próg opłacalności), a bramy zostają nietknięte, żeby
    zmiana nie ruszyła selekcji ani o jeden typ — inaczej nie dałoby się
    odróżnić skutku podatku od skutku nowej selekcji w rozliczeniach.

    Do ruszenia progów wracamy z pomiarem, tak jak przy oknie zgody z rynkiem.
    Uwaga na przyszłość: progi 0,52 i 0,42 były wprost definiowane jako próg
    opłacalności (1/1,92 i 1/2,38) — po podatku te same definicje dają
    0,59 i 0,48, więc przeliczenie ich ZAOSTRZA bramę, a nie luzuje.
    """
    return any(
        lo <= odd <= hi and p >= p_min and p_ostrozne * odd - 1.0 >= 0.0
        for lo, hi, p_min in WIDELKI_DRUZYNOWE
    )


def powod_widelek(odd: float, p: float, p_ostrozne: float) -> str:
    """KTÓRY z trzech warunków wyciął typ — wyłącznie do diagnostyki.

    Jeden licznik na trzy różne przyczyny nie mówił nic: nie dało się odróżnić
    „bukmacher daje za wysoki kurs" od „model daje za niską szansę" od „to po
    prostu nie ma wartości". Kolejność od najbardziej zewnętrznego warunku.
    """
    w_kursie = [b for b in WIDELKI_DRUZYNOWE if b[0] <= odd <= b[1]]
    if not w_kursie:
        return "kurs_poza_widelkami"
    if not any(p >= p_min for _, _, p_min in w_kursie):
        return "szansa_za_niska"
    return "wartosc_ujemna"


def widelki_druzynowe_blisko(odd: float, p: float, p_ostrozne: float) -> bool:
    """Czy typ minął się z bramą NIEWIELE — kandydat na typ pomiarowy.

    Sens: za miesiąc porównamy hit-rate i ROI tych typów z przepuszczonymi
    i dopiero wtedy będzie wiadomo, czy brama zarabia, czy tylko chudzi listę.
    """
    if widelki_druzynowe_ok(odd, p, p_ostrozne):
        return False
    return any(
        lo <= odd <= hi * NEAR_WIDELKI_KURS
        and p >= p_min - NEAR_WIDELKI_P
        and p_ostrozne * odd - 1.0 >= -NEAR_WIDELKI_EV
        for lo, hi, p_min in WIDELKI_DRUZYNOWE
    )


def assess(
    p_model_over: float,
    over_odds: float | None,
    under_odds: float | None,
    conf_inputs: ConfidenceInputs,
    lam: float,
    is_prob_market: bool = False,
    odrzucone_out: list | None = None,
    tryb: str | None = None,
) -> list[ValueAssessment]:
    """Oceń obie strony rynku. Zwraca tylko strony przechodzące progi.

    is_prob_market — rynek binarny (kartka): `lam` to prawdopodobieństwo, nie
    licznik; ryzyko liczone inną skalą (patrz risk_level).
    odrzucone_out — kolektor odrzuceń TUŻ przy progu (patrz NEAR_*): strony
    odrzucone dokładnie jednym kryterium w tolerancji lądują tu jako
    {side, powod, p_model, implied, odds, ev_pct, confidence_score}.
    """
    results: list[ValueAssessment] = []

    if over_odds is not None and under_odds is not None:
        imp_over, imp_under = implied_probs_two_way(over_odds, under_odds)
    elif over_odds is not None:
        imp_over, imp_under = implied_prob_one_sided(over_odds), None
    elif under_odds is not None:
        imp_over, imp_under = None, implied_prob_one_sided(under_odds)
    else:
        return results

    score = confidence_score(conf_inputs)
    risk = risk_level(
        lam, conf_inputs.is_rare_market, conf_inputs.minutes_certainty, is_prob_market
    )
    min_ev = MIN_EV_PCT_RARE if conf_inputs.is_rare_market else MIN_EV_PCT

    if conf_inputs.ci_width > MAX_CI_WIDTH:
        # Sam model nie wie, ile wynosi prawdopodobieństwo — nie stawiamy.
        return results

    for side, p_model, implied, odds in (
        ("powyzej", p_model_over, imp_over, over_odds),
        ("ponizej", 1.0 - p_model_over, imp_under, under_odds),
    ):
        if implied is None or odds is None:
            continue
        edge_pp = (p_model - implied) * 100.0
        # EV PO PODATKU (2026-07-31). `edge_pp` zostaje bez podatku celowo:
        # to porównanie dwóch szans (modelu i rynku), a nie zysk — podatek
        # skracałby się po obu stronach i tylko zaciemniał sygnał.
        # BRAMA liczy brutto (patrz `ev_brutto_pct`), UŻYTKOWNIK widzi netto
        ev = ev_brutto_pct(p_model, odds)
        ev_netto = ev_pct(p_model, odds, tryb)
        # bramki publikacji — każda z parą (odrzuca?, czy TUŻ przy progu?);
        # komentarze przy stałych MAX_* wyżej tłumaczą intuicje
        powody: list[tuple[str, bool]] = []
        if ev < min_ev:
            powody.append(("ev_ponizej_progu", ev >= min_ev - NEAR_EV_PP))
        if score < MIN_CONFIDENCE_SCORE:
            powody.append(
                ("niska_pewnosc", score >= MIN_CONFIDENCE_SCORE - NEAR_CONF)
            )
        if odds > MAX_ODDS or odds < MIN_ODDS:
            # wysokie kursy = loteria, groszowe = niewarte ryzyka; celowo BEZ
            # strefy pomiaru (decyzja o widełkach kursów jest usera, nie modelu)
            powody.append(("kurs_poza_widelkami", False))
        if abs(p_model - implied) > MAX_MODEL_MARKET_DIVERGENCE:
            powody.append((
                "rozjazd_z_rynkiem",
                abs(p_model - implied) <= MAX_MODEL_MARKET_DIVERGENCE + NEAR_DIV,
            ))
        if implied > 0 and p_model / implied > MAX_RELATIVE_DIVERGENCE:
            powody.append((
                "rozjazd_wzgledny",
                p_model / implied <= MAX_RELATIVE_DIVERGENCE + NEAR_REL,
            ))
        if powody:
            if odrzucone_out is not None and len(powody) == 1 and powody[0][1]:
                odrzucone_out.append({
                    "side": side, "powod": powody[0][0],
                    "p_model": round(p_model, 4),
                    "implied": round(implied, 4), "odds": odds,
                    "ev_pct": round(ev, 2),
                    "ev_netto": round(ev_netto, 2),
                    "confidence_score": round(score, 1),
                })
            continue
        # Ranking: przewaga w pp ważona pewnością — celowo NIE po EV,
        # żeby longshoty nie wypychały solidnych okazji.
        rank = edge_pp * (score / 100.0) ** 1.5
        results.append(
            ValueAssessment(
                side=side,
                model_prob=round(p_model, 4),
                implied_prob=round(implied, 4),
                fair_odds=round(1.0 / max(p_model, 1e-6), 3),
                edge_pp=round(edge_pp, 2),
                ev_pct=round(ev, 2),
                ev_netto=round(ev_netto, 2),
                tryb_podatku=tryb_podatku(tryb=tryb),
                confidence=confidence_level(score),
                confidence_score=round(score, 1),
                risk=risk,
                rank_score=round(rank, 3),
            )
        )
    return results


def clv_pct(odds_taken: float, closing_odds: float) -> float:
    """Closing Line Value: o ile lepszy kurs wzięliśmy vs kurs zamknięcia."""
    return round((odds_taken / closing_odds - 1.0) * 100.0, 2)
