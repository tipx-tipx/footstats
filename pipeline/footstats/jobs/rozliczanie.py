"""Automatyczne rozliczanie publikowanych typów + baza pod uczenie modelu.

Przepływ (wywoływane na końcu każdego cyklu):
  1. każdy publikowany typ (okazja i sugestia) trafia do logu `typy_log`
     w Supabase — z ZAMROŻONYM p_model i kursem z chwili pierwszej publikacji,
  2. po zakończonym meczu (kickoff + ~105 min) cykl szuka faktycznej wartości
     — wszystko liczone w REGULARNYM czasie gry (bez dogrywki, jak u buka):
       * rynki strzałowe — z 365Scores (chartEvents per strzał, minuta <= 90),
       * faule/wywalczone/przechwyty — z pełnych statystyk meczu 365Scores
         (od razu po meczu; przy dogrywce NIE używamy — obejmują 120 min),
         fallback: bank trendów statshub (parowanie po timestampie),
       * odbiory — tylko bank trendów (365 ich nie podaje),
       * zawodnik nie zagrał (brak w statystykach meczu / 0 minut) -> "zwrot",
       * brak danych źródłowych po 48 h -> "zwrot" (nic nie wisi "w grze"),
       * SUPERZMIANA (Superbet): gdy zawodnik zszedł, a jego zmiennik dołożył
         brakującą statystykę, leg "powyżej" rozliczamy z sumy (patrz
         SUPERZMIANA_RYNKI); rewizja wsteczna naprawia też stare przegrane,

  3. podsumowanie `typy_wyniki` (trafienia, ROI flat, per rynek) idzie na
     stronę Skuteczności. Odchylenie trafień od średniego p_model per rynek
     (bias) to surowiec do dokręcenia kalibracji — STOSUJEMY je w modelu
     dopiero od n>=25 rozliczonych typów na rynku (na razie tylko raport).
"""

from __future__ import annotations

import math
import time

from .. import supa
from ..model import betting
from ..model import kupony as kupony_model
from ..sources import rotowire, scores365

# rynek -> pole w agregacie 365Scores (classify_event)
MARKETY_365 = {
    "shots": "shots", "sot": "sot",
    "headed_shots": "headed", "headed_sot": "headed_sot",
    "shots_outside_box": "outside", "sot_outside_box": "sot_outside",
    "shots_blocked": "blocked", "shots_off_target": "off_target",
}
# rynki z pełnych statystyk meczowych 365Scores (lineups.members[].stats) —
# dostępne od razu po meczu, bez czekania na odświeżenie banku trendów
MARKETY_365_STATY = {"fouls_committed", "fouls_won", "interceptions", "offsides"}
# rynki rozliczane z banku trendów statshub (odbiory nie występują w 365)
MARKETY_LIB = {"fouls_committed", "tackles", "fouls_won", "interceptions",
               "offsides"}
# rynki DRUŻYNOWE -> pole w statystykach drużynowych 365 (game_team_stats).
# Rozliczane osobną, prostszą ścieżką: bez modelu minut, bez superzmiany;
# mecz z dogrywką NIE rozlicza się z tych statystyk (obejmują 120 min,
# a rynek dotyczy 90) — po terminie zamyka się jako zwrot
MARKETY_DRUZYNOWE = {
    "team_shots": "shots", "team_sot": "sot",
    "team_fouls": "fouls", "team_cards": "kartki",
}
# strzały NIECELNE i ZABLOKOWANE liczymy CAŁKOWICIE OSOBNO — nie wchodzą do
# zbiorczej skuteczności modelu (podsumowanie trafień/ROI ani tabela per rynek).
# Rynek "shots" (strzały ogółem) zostaje bez zmian = wszystkie strzały, zgodnie
# z regulaminem bukmachera; osobność dotyczy tylko raportu skuteczności.
RYNKI_OSOBNE = {"shots_off_target", "shots_blocked"}

# --- Superzmiana (Superbet): gdy wytypowany zawodnik zostanie zmieniony,
# statystyki jego zmiennika doliczają się do zakładu. Objęte rynki wg
# regulaminu (potwierdzone przez usera). Stosujemy WYŁĄCZNIE na korzyść
# gracza: upgrade przegrany -> wygrany na stronie "powyżej". Dla "poniżej"
# dolewka zmiennika mogłaby typ pogrążyć — takich legów nie ruszamy.
SUPERZMIANA_RYNKI = {
    "shots", "sot", "shots_outside_box", "sot_outside_box",
    "tackles", "fouls_committed", "fouls_won",
}


# próbuj rozliczać już ~105 min po kickoffie (źródła i tak wymagają statusu
# "zakończony") — status kuponu odświeża się tuż po końcowym gwizdku
MECZ_KONIEC_PO_S = 105 * 60
OKNO_PAROWANIA_S = 36 * 3600
# po tym czasie bez danych źródłowych typ zamyka się jako "zwrot" (brak
# rozstrzygnięcia) — kupony nie mogą wisieć "w grze" w nieskończoność
TERMIN_BRAK_DANYCH_S = 48 * 3600


def _klucz(b: dict) -> str:
    # klucz po ZNORMALIZOWANYM NAZWISKU, nie player_id: syntetyczne id
    # (bank/365) może się różnić między źródłami, a w erze randomizowanego
    # hash() zmieniało się co cykl i dublowało typy w logu (do 25 kopii)
    podmiot = rotowire._norm(str(b["podmiot"]))
    return f"{b['mecz_id']}:{podmiot}:{b['rynek_kod']}:{b['linia']}:{b['strona']}"


_RANGA_WYNIKU = {"wygrany": 2, "przegrany": 2, "zwrot": 1, None: 0}


def _migruj_log(log: dict) -> dict:
    """Przeklucz stary log (klucze z player_id) na klucze po nazwisku,
    scalając duplikaty: kurs/p_model z PIERWSZEJ publikacji (zamrożone),
    wynik z któregokolwiek rozliczonego duplikatu."""
    nowy: dict = {}
    for r in log.values():
        k = _klucz(r)
        a = nowy.get(k)
        if a is None:
            nowy[k] = r
            continue
        if r.get("opublikowano_ts", 0) < a.get("opublikowano_ts", 0):
            a, r = r, a
            nowy[k] = a
        if _RANGA_WYNIKU.get(r.get("wynik"), 0) > _RANGA_WYNIKU.get(a.get("wynik"), 0):
            for f in ("wynik", "faktyczna", "rozliczono_ts", "powod"):
                if f in r:
                    a[f] = r[f]
    return nowy


def _kupon_leg_do_logu(l: dict) -> dict:
    """Rzutuje leg kuponu (kupony.py:_leg_dict) na rekord dla _dopisz_nowe.

    Leg kuponu jest CZĘSTO jedynym miejscem, w którym dany typ w ogóle
    trafia do typy_log — value_bets trzyma tylko best-per-side, a spora
    część legów z legi_pool nigdy nie zostaje osobno opublikowaną okazją.
    Musi więc przenosić WSZYSTKIE pola, które _dopisz_nowe zapisuje/aktualizuje
    (patrz tam), inaczej te legi są ślepą plamą dla diagnostyki per kategoria."""
    return {
        "mecz_id": l["mecz_id"], "mecz": l["mecz"],
        "kickoff_ts": l["kickoff_ts"],
        "podmiot_id": l.get("podmiot_id", 0),
        "podmiot": l["podmiot"], "rynek_kod": l.get("rynek_kod", ""),
        "rynek": l["rynek"], "linia": l["linia"], "strona": l["strona"],
        "kurs": l["kurs"], "bukmacher": l.get("bukmacher"),
        "kurs_ref": l.get("kurs_ref"),
        "p_model": l["p_model"], "pewnosc": l.get("pewnosc"),
        "sugestia": False,
        "matchup": l.get("matchup"), "rotacja": l.get("rotacja"),
        "matchup_styl": l.get("matchup_styl"),
        "wyzsza_linia": l.get("wyzsza_linia"),
        "miekka_linia": l.get("miekka_linia"),
        "xi_sygnal": l.get("xi_sygnal"),
    }


def _dopisz_nowe(log: dict, value_bets: list[dict]) -> None:
    for b in value_bets:
        k = _klucz(b)
        if k in log:
            # flagi kategorii potrafią pojawić się PO pierwszej publikacji
            # (miękka linia w dniu meczu, matchup gdy urośnie profil rywala,
            # świeży skład) — bez aktualizacji stare klucze byłyby na zawsze
            # "bezkategoriowe" i diagnostyka per kategoria nie miałaby danych.
            # Aktualizujemy OR-em wyłącznie wpisy jeszcze nierozliczone;
            # kurs/p_model zostają z pierwszej publikacji (dataset kalibracji).
            rec = log[k]
            if rec.get("wynik") is None:
                for f in ("matchup", "matchup_styl", "rotacja", "wyzsza_linia",
                          "pewniak", "miekka_linia"):
                    if b.get(f):
                        rec[f] = True
                if b.get("xi_sygnal") is not None:
                    rec["xi_sygnal"] = b["xi_sygnal"]  # najświeższy przed meczem
                # typ pomiarowy (odrzucony przy progu), który PÓŹNIEJ przeszedł
                # progi i został opublikowany — przestaje być pomiarowy (wraca
                # do kalibracji/skuteczności); w drugą stronę NIGDY nie
                # degradujemy opublikowanego typu do pomiarowego
                if rec.get("odrzucony") and not b.get("odrzucony"):
                    rec["odrzucony"] = False
                    rec.pop("odrzucenie_powod", None)
                # typ spoza publikacji (kwarantanna/limit meczu), który w
                # kolejnym cyklu WSZEDŁ do publikacji — awansuje; w drugą
                # stronę nigdy nie degradujemy opublikowanego typu
                if rec.get("poza_publikacja") and not b.get("poza_publikacja"):
                    rec.pop("poza_publikacja", None)
            continue
        log[k] = {
            "mecz_id": b["mecz_id"], "mecz": b["mecz"],
            "kickoff_ts": b["kickoff_ts"],
            "podmiot_id": b["podmiot_id"], "podmiot": b["podmiot"],
            "rynek_kod": b["rynek_kod"], "rynek": b["rynek"],
            "linia": b["linia"], "strona": b["strona"],
            "kurs": b.get("kurs"), "bukmacher": b.get("bukmacher"),
            # konsensus UK (mediana buków) — do KALIBRACJI marży UK z rozliczeń:
            # po zebraniu próby porównujemy 1/kurs_ref do realnej częstości trafień
            # i stąd wyliczamy prawdziwą UK_CONSENSUS_MARGIN (dziś założona 0.045)
            "kurs_ref": b.get("kurs_ref"),
            "p_model": b["p_model"], "pewnosc": b.get("pewnosc"),
            "sugestia": bool(b.get("sugestia")),
            # kategorie typu — do diagnostyki per kategoria (Brier/log-loss)
            "matchup": bool(b.get("matchup")),
            "matchup_styl": bool(b.get("matchup_styl")),
            "rotacja": bool(b.get("rotacja")),
            "wyzsza_linia": bool(b.get("wyzsza_linia")),
            "pewniak": bool(b.get("pewniak")),
            "miekka_linia": bool(b.get("miekka_linia")),
            # sygnał składu przy publikacji — do kalibracji p_start z rozliczeń
            "xi_sygnal": b.get("xi_sygnal"),
            # POMIAR PROGÓW: typ odrzucony tuż przy progu (betting.NEAR_*) —
            # rozlicza się w tle, POZA kalibracją/skutecznością/UI; diagnostyka
            # porównuje jego hit-rate z przepuszczonymi (kategoria
            # odrzucone_pomiar), zanim ktokolwiek ruszy same progi
            "odrzucony": bool(b.get("odrzucony")),
            "odrzucenie_powod": b.get("odrzucenie_powod"),
            # POZA PUBLIKACJĄ: "kwarantanna_rynku" (rynek trafia poniżej
            # deklaracji) albo "limit_meczu" (nadmiar typów z jednego meczu).
            # Rozlicza się i UCZY kalibrację, ale nie wchodzi do
            # skuteczności/kalendarza/UI — w odróżnieniu od `odrzucony`,
            # który jest też poza kalibracją.
            "poza_publikacja": b.get("poza_publikacja"),
            "opublikowano_ts": int(time.time()),
            "wynik": None, "faktyczna": None,
        }


def _gid_365(rec: dict, cache: dict) -> int | None:
    """Znajdź id zakończonego meczu w 365Scores (cache per mecz).

    Szuka w wynikach rozgrywek MŚ (endpoint /games/results — /games/current
    ignoruje filtr dat i nie zawiera wczorajszych meczów). Dopasowanie po
    znormalizowanych nazwach drużyn; awaryjnie po kickoffie + jednej nazwie
    (rozjazdy typu "USA" vs "United States").
    """
    mid = rec["mecz_id"]
    if mid in cache:
        return cache[mid]
    teams = [t.strip() for t in str(rec["mecz"]).replace("—", "–").split("–")]
    if len(teams) != 2:
        cache[mid] = None
        return None
    home, away = rotowire._norm(teams[0]), rotowire._norm(teams[1])
    if "_wyniki" not in cache:
        try:
            cache["_wyniki"] = scores365.finished_games_by_competition()
        except Exception:
            cache["_wyniki"] = []
    gid = None
    for g in cache["_wyniki"]:
        if {g["home"], g["away"]} == {home, away}:
            gid = g["id"]
            break
        if (
            abs(g["ts"] - rec["kickoff_ts"]) < 3 * 3600
            and {g["home"], g["away"]} & {home, away}
        ):
            gid = g["id"]
            break
    cache[mid] = gid
    return gid


def _minuty_z_banku(rec: dict, lib: dict) -> float | None:
    """Minuty zawodnika w rozliczanym meczu (z banku trendów, rynek shots)."""
    t = lib.get(f"{rec['podmiot_id']}:shots")
    if not t:
        return None
    for i, ts in enumerate(t.get("timestamps", [])):
        if abs(ts - rec["kickoff_ts"]) < OKNO_PAROWANIA_S:
            mins = t.get("minutes", [])
            return float(mins[i]) if i < len(mins) else None
    return None


def _wartosc_z_banku(rec: dict, lib: dict) -> float | None:
    t = lib.get(f"{rec['podmiot_id']}:{rec['rynek_kod']}")
    if not t:
        return None
    for i, ts in enumerate(t.get("timestamps", [])):
        if abs(ts - rec["kickoff_ts"]) < OKNO_PAROWANIA_S:
            cnts = t.get("counts", [])
            return float(cnts[i]) if i < len(cnts) else None
    return None


def _wartosc_zmiennika(
    nazwisko_norm: str, mk: str, gid: int | None, staty: dict | None,
    lib: dict, rec: dict,
) -> float | None:
    """Statystyka zmiennika w rozliczanym meczu (cały jego czas gry jest
    z definicji PO wejściu, więc pełnomeczowa wartość = wkład po zmianie)."""
    if mk in MARKETY_365 and gid is not None:
        try:
            gra = scores365.game_player_shots(gid)
        except Exception:
            gra = None
        if gra is not None:
            skey = scores365.resolve_player_key(set(gra), nazwisko_norm)
            if skey:
                return float(gra[skey].get(MARKETY_365[mk], 0))
            return 0.0  # wszedł, a nie ma go w mapie strzałów = 0 zdarzeń
    if (
        mk in MARKETY_365_STATY and staty
        and gid is not None and not scores365.after_extra_time(gid)
    ):
        skey = scores365.resolve_player_key(set(staty), nazwisko_norm)
        if skey:
            w = staty[skey].get(mk)
            if w is not None:
                return float(w)
    # bank trendów (jedyne źródło odbiorów) — zmiennika szukamy po nazwisku,
    # bo nie znamy jego statshubowego id
    kandydaci = {
        rotowire._norm(str(t.get("player_name", ""))): t
        for t in lib.values()
        if t.get("market_code") == mk
    }
    tkey = scores365.resolve_player_key(set(kandydaci), nazwisko_norm)
    if tkey:
        t = kandydaci[tkey]
        for i, ts in enumerate(t.get("timestamps", [])):
            if abs(ts - rec["kickoff_ts"]) < OKNO_PAROWANIA_S:
                cnts = t.get("counts", [])
                return float(cnts[i]) if i < len(cnts) else None
    return None


def _superzmiana(
    rec: dict, gid: int | None, staty: dict | None, lib: dict,
    wartosc: float | None,
) -> tuple[float, str] | None:
    """Superzmiana Superbetu: dolicz statystyki zmiennika, jeśli ratują lega.

    Zwraca (nowa_wartość, powód) tylko gdy suma przebija linię — nigdy nie
    pogarsza wyniku. None = nie dotyczy / brak danych / suma dalej za niska.
    """
    if (
        rec.get("strona") != "powyzej"
        or rec.get("rynek_kod") not in SUPERZMIANA_RYNKI
        or "superbet" not in str(rec.get("bukmacher") or "").lower()
        or gid is None
    ):
        return None
    try:
        subs = scores365.game_substitutions(gid)
    except Exception:
        return None
    klucz = scores365.resolve_player_key(set(subs), str(rec["podmiot"]))
    if not klucz:
        return None  # grał do końca albo brak danych o zmianie
    zmiennik = subs[klucz]["wszedl"]
    dodatek = _wartosc_zmiennika(
        zmiennik, rec["rynek_kod"], gid, staty, lib, rec
    )
    if not dodatek:
        return None
    suma = float(wartosc or 0.0) + dodatek
    if suma > rec["linia"]:
        return suma, (
            f"superzmiana: {zmiennik} dołożył {dodatek:g} po wejściu "
            f"za {rec['podmiot']} ({subs[klucz]['minuta']:.0f}')"
        )
    return None


MIN_N_KALIBRACJI = 25          # od tylu rozliczonych typów na rynek korygujemy
BIAS_CAP = (0.85, 1.15)        # (stary format mnożnikowy — compute_bias/raport)
# kalibracja w PRZESTRZENI LOGITÓW: p' = sigmoid(logit(p) + b) — mnożnik
# psuł ogony (p=95% ściągał za mocno, p=50% za słabo); delta logitowa
# koryguje równomiernie. Cap w dół poszerzony do −0.80 (2026-07-19): zmierzone
# błędy realnych rynków wymagały delty −0.58 (shots) i −1.1 (fouls_committed),
# a cap −0.40 ucinał korektę w połowie — model NIE MÓGŁ się skalibrować mimo
# danych. Przed przestrzeleniem chroni shrinkage (waga n/(n+25)), nie cap.
BIAS_CAP_LOGIT = (-0.80, 0.40)
# sugestie STS (bez kursu, bez bezpieczników rynkowych) kalibrują się OSOBNO
# i mylą się dużo mocniej niż typy z kursem — cap w dół musi być szerszy
SUGESTIA_BIAS_CAP_LOGIT = (-1.0, 0.40)
# kalibracja PRZEDZIAŁOWA: bias liczony osobno per przedział szansy (model
# może przeszacowywać longshoty, a pewniaki mieć dobrze)
# przedział 0.70-1.01 sklejał dobrze skalibrowane 0.75-0.85 (hit ~ p) z
# przeszacowanym 0.85+ (hit 70% vs p 89%) — korekta się uśredniała; osobny
# bin góry pozwala kalibracji dociskać tam, gdzie faktycznie przeszacowuje
BIAS_PRZEDZIALY = [(0.0, 0.55), (0.55, 0.70), (0.70, 0.85), (0.85, 1.01)]
MIN_N_PRZEDZIAL = 15
# WAŻENIE ŚWIEŻOŚCI kalibracji: rozliczenie sprzed 14 dni waży połowę
# najnowszego (półokres). Warunki gry zmieniają się (faza grupowa vs
# pucharowa, klub vs turniej) — bez wygaszania stara prawda przykrywa nową
# i korekta reaguje z tygodniowym opóźnieniem. Punktem "teraz" jest
# najnowsze rozliczenie w logu (nie zegar) — przerwa w cyklach nie
# wyzerowuje kalibracji.
KALIBRACJA_POLOWICZNY_DNI = 14.0
# pokrewne rynki dzielą błąd modelu (shots i sot mylą się razem) — shrinkage
# rodzinny: rynek z małą próbą jest ściągany do biasu swojej rodziny;
# mapa wspólna z kuponami (dywersyfikacja) — mieszka w model/betting.py
RODZINY_RYNKOW = betting.RODZINY_RYNKOW


def _bias_surowy(grp: list[dict]) -> float:
    """(trafienia + 2) / (suma zamrożonych p_model + 2): >1 = model
    niedoszacowuje, <1 = przeszacowuje (pseudozliczenia +2 stabilizują)."""
    traf = sum(1 for r in grp if r["wynik"] == "wygrany")
    return (traf + 2.0) / (sum(r["p_model"] for r in grp) + 2.0)


def _cap_bias(b: float, cap: tuple[float, float] = BIAS_CAP) -> float:
    return round(max(cap[0], min(cap[1], b)), 3)


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def _bias_logit(grp: list[dict], wagi: list[float] | None = None) -> float:
    """Delta logitowa b: rozwiązanie Σ w·sigmoid(logit(p_i)+b) = Σ w·trafienia.

    Pseudozliczenia stabilizujące jak w _bias_surowy: dwie wirtualne
    obserwacje p=0.5 (jedna trafiona, jedna nie, waga 1). Opcjonalne wagi =
    ważenie świeżości. Bisekcja — bez zależności.
    """
    ps = [min(max(float(r["p_model"]), 1e-6), 1 - 1e-6) for r in grp]
    w = list(wagi) if wagi is not None else [1.0] * len(grp)
    traf = sum(wi for r, wi in zip(grp, w) if r["wynik"] == "wygrany") + 1.0
    ps += [0.5, 0.5]
    w += [1.0, 1.0]

    def f(b: float) -> float:
        return sum(
            wi / (1.0 + math.exp(-(_logit(p) + b))) for p, wi in zip(ps, w)
        ) - traf

    lo, hi = -3.0, 3.0
    if f(lo) > 0:
        return lo
    if f(hi) < 0:
        return hi
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def compute_bias(log: dict, min_n: int = MIN_N_KALIBRACJI) -> dict[str, float]:
    """Płaski bias per rynek (stary format) — zachowany dla raportu i testów."""
    grupy: dict[str, list[dict]] = {}
    for r in log.values():
        if r.get("wynik") in ("wygrany", "przegrany") and not r.get("odrzucony"):
            grupy.setdefault(r["rynek_kod"], []).append(r)
    return {
        mk: _cap_bias(_bias_surowy(grp))
        for mk, grp in grupy.items()
        if len(grp) >= min_n
    }


def compute_bias_full(
    log: dict,
    min_n: int = MIN_N_KALIBRACJI,
    sugestie: bool = False,
    cap: tuple[float, float] = BIAS_CAP_LOGIT,
) -> dict[str, dict]:
    """Kalibracja przedziałowa z shrinkage: rodzina -> rynek -> przedział.

    Wartości to DELTY LOGITOWE (p' = sigmoid(logit(p) + b)) — równomierna
    korekta w całej skali szans, w przeciwieństwie do mnożnika.
    Trzy poziomy (każdy ściągany do nadrzędnego proporcjonalnie do próby):
      1. rodzina rynków (strzelanie/faule/defensywa) — od min_n rozliczeń,
      2. rynek — bias ściągany do rodziny wagą n/(n+min_n),
      3. przedział szansy — ściągany do biasu rynku wagą n/(n+MIN_N_PRZEDZIAL).

    Zwraca {rynek: {"logit": True, "global": b, "bins": [[lo, hi, b], ...]}}
    — format rozumiany przez engine (stary mnożnikowy dalej wspierany).
    """
    # sugestie STS trafiają fatalnie względem typów z kursem (inne progi, brak
    # bezpieczników) — mieszanie ich z typami zaniżało bias całych rodzin.
    # Typy POMIAROWE (odrzucone przy progu) też zostają poza kalibracją —
    # nie były publikowane i z definicji łamią któryś bezpiecznik.
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and bool(r.get("sugestia")) == sugestie
        and not r.get("odrzucony")
    ]
    # ważenie świeżości względem najnowszego rozliczenia w logu — świeże
    # błędy ważą więcej, stare wygasają (półokres KALIBRACJA_POLOWICZNY_DNI)
    ts_max = max(
        (float(r.get("kickoff_ts") or 0) for r in settled), default=0.0
    )

    def _w(r: dict) -> float:
        dni = max(ts_max - float(r.get("kickoff_ts") or 0), 0.0) / 86400.0
        return 0.5 ** (dni / KALIBRACJA_POLOWICZNY_DNI)

    rodziny: dict[str, list[dict]] = {}
    for r in settled:
        fam = RODZINY_RYNKOW.get(r["rynek_kod"])
        if fam:
            rodziny.setdefault(fam, []).append(r)
    fam_bias = {
        f: _bias_logit(g, [_w(r) for r in g])
        for f, g in rodziny.items() if len(g) >= min_n
    }
    grupy: dict[str, list[dict]] = {}
    for r in settled:
        grupy.setdefault(r["rynek_kod"], []).append(r)
    out: dict[str, dict] = {}
    for mk, grp in grupy.items():
        fb = fam_bias.get(RODZINY_RYNKOW.get(mk, ""))
        # shrink liczony na EFEKTYWNEJ próbie (suma wag świeżości): stare
        # rozliczenia nie tylko mniej znaczą w biasie, ale i słabiej
        # emancypują rynek od rodziny
        n_eff = sum(_w(r) for r in grp)
        raw = _bias_logit(grp, [_w(r) for r in grp])
        if fb is not None:
            g = fb + (n_eff / (n_eff + min_n)) * (raw - fb)
        elif len(grp) >= min_n:
            g = raw
        else:
            continue  # za mało danych i brak rozliczonej rodziny
        bins = []
        for lo, hi in BIAS_PRZEDZIALY:
            bgrp = [r for r in grp if lo <= r["p_model"] < hi]
            bb = g
            if len(bgrp) >= MIN_N_PRZEDZIAL:
                b_eff = sum(_w(r) for r in bgrp)
                k = b_eff / (b_eff + MIN_N_PRZEDZIAL)
                bb = g + k * (_bias_logit(bgrp, [_w(r) for r in bgrp]) - g)
            bins.append([lo, hi, _cap_bias(bb, cap)])
        out[mk] = {"logit": True, "global": _cap_bias(g, cap), "bins": bins}
    return out


# KWARANTANNA RYNKU: rynek, który w rozliczeniach trafia wyraźnie poniżej
# deklaracji modelu, wypada z PUBLIKACJI (pewniaki, pula kuponów), ale dalej
# jest scorowany i logowany (poza_publikacja="kwarantanna_rynku") — kalibracja
# mierzy go nadal i rynek wraca sam, gdy okno rozliczeń się poprawi.
KWARANTANNA_PROG_BIAS = 0.80   # wejście do kwarantanny poniżej tego biasu
KWARANTANNA_MIN_N = 15         # od tylu rozliczonych typów oceniamy rynek
KWARANTANNA_OKNO = 40          # okno kroczące: tylko ostatnie N rozliczeń


def rynki_kwarantanna(log: dict | None = None) -> dict[str, dict]:
    """Rynki chwilowo poza publikacją: bias (traf vs deklaracja) z okna
    ostatnich rozliczeń poniżej progu. Zwraca {rynek: {bias, n, hit, sr_p}}."""
    if log is None:
        log = _migruj_log(supa.get_key("typy_log") or {})
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
    ]
    out: dict[str, dict] = {}
    for mk in {r["rynek_kod"] for r in settled}:
        grp = sorted(
            (r for r in settled if r["rynek_kod"] == mk),
            key=lambda r: r.get("kickoff_ts") or 0,
        )[-KWARANTANNA_OKNO:]
        if len(grp) < KWARANTANNA_MIN_N:
            continue
        traf = sum(1 for r in grp if r["wynik"] == "wygrany")
        sr_p = sum(r["p_model"] for r in grp) / len(grp)
        bias = (traf + 2.0) / (sr_p * len(grp) + 2.0)
        if bias < KWARANTANNA_PROG_BIAS:
            out[mk] = {
                "bias": round(bias, 3), "n": len(grp),
                "hit": round(traf / len(grp), 3), "sr_p": round(sr_p, 3),
            }
    return out


def kwarantanna() -> dict[str, dict]:
    """Kwarantanna rynków z logu w Supabase (pusta, gdy brak danych/env)."""
    log = _migruj_log(supa.get_key("typy_log") or {})
    return rynki_kwarantanna(log)


def market_bias() -> dict[str, dict]:
    """Korekty kalibracyjne z logu w Supabase (puste, gdy brak danych/env)."""
    log = _migruj_log(supa.get_key("typy_log") or {})
    return compute_bias_full(log)


def market_bias_sugestie() -> dict[str, dict]:
    """Osobna kalibracja sugestii STS — liczona wyłącznie z rozliczonych
    sugestii, z szerszym capem w dół (przeszacowania rzędu 20 pp)."""
    log = _migruj_log(supa.get_key("typy_log") or {})
    return compute_bias_full(log, sugestie=True, cap=SUGESTIA_BIAS_CAP_LOGIT)


def compute_wagi_zaufania(log: dict) -> dict[str, dict]:
    """Pomiar zaufania do p_model per KUBEŁEK PEWNOŚCI (wysoka/średnia).

    Dla rozliczonych, publikowanych typów z kursem porównujemy: średnie
    p_model (deklarację modelu), średnią cenę rynku po devigu i realny
    hit-rate. Składanie kuponów miesza p_model z ceną rynku log-liniowo
    (kupony._p_skladania: p^w * r^(1-w)), więc DOCELOWĄ wagę w — taką, przy
    której mieszanka średnio trafiałaby w realny hit — wyznacza wprost:

        w* = (ln hit − ln r̄) / (ln p̄ − ln r̄)

    Zwraca surowy pomiar per kubełek {n, sr_p, sr_rynek, hit, w_cel};
    shrink do wag bazowych i cap stosuje kupony.wagi_zaufania_z_pomiaru
    (ten sam wzorzec co kary korelacji z diagnostyki).
    """
    out: dict[str, dict] = {}
    for kubelek in ("wysoka", "srednia"):
        grp = [
            r for r in log.values()
            if r.get("wynik") in ("wygrany", "przegrany")
            and not r.get("sugestia") and not r.get("odrzucony")
            and r.get("kurs") and float(r["kurs"]) > 1.0
            and (r.get("pewnosc") or "srednia") == kubelek
        ]
        n = len(grp)
        if n < 5:
            continue
        sr_p = sum(float(r["p_model"]) for r in grp) / n
        sr_rynek = sum(
            betting.implied_prob_one_sided(float(r["kurs"])) for r in grp
        ) / n
        hit = sum(1 for r in grp if r["wynik"] == "wygrany") / n
        rec = {
            "n": n, "sr_p": round(sr_p, 3),
            "sr_rynek": round(sr_rynek, 3), "hit": round(hit, 3),
        }
        mianownik = math.log(max(sr_p, 1e-6)) - math.log(max(sr_rynek, 1e-6))
        if abs(mianownik) > 1e-3 and 0.0 < hit < 1.0:
            w = (math.log(hit) - math.log(max(sr_rynek, 1e-6))) / mianownik
            # w>1 = model lepszy niż sam deklaruje (rzadkie), w<0 = gorszy
            # niż rynek; sensowny zakres ucinamy, resztę robi shrink+cap
            rec["w_cel"] = round(min(max(w, 0.0), 1.2), 3)
        out[kubelek] = rec
    return out


def compute_diagnostyka(log: dict) -> dict:
    """Samokontrola modelu z rozliczeń: Brier / log-loss per kategoria typów.

    Kategorie nie wykluczają się (typ bywa matchup i pewniak naraz);
    "zwykle" = bez żadnej flagi specjalnej. Dodatkowo skuteczność sygnałów
    składu — P(zagrał | sygnał XI) — do przyszłej kalibracji modelu minut
    (od n>=40 na sygnał można zastąpić ręczne wagi zmierzonymi).
    """
    # typy pomiarowe (odrzucone przy progu) NIE wchodzą do kategorii jakości
    # modelu — mają własną kategorię porównawczą niżej
    wszystkie_settled = [
        r for r in log.values() if r.get("wynik") in ("wygrany", "przegrany")
    ]
    settled = [r for r in wszystkie_settled if not r.get("odrzucony")]

    def _stats(grp: list[dict]) -> dict | None:
        n = len(grp)
        if not n:
            return None
        brier = ll = 0.0
        traf = 0
        for r in grp:
            p = min(max(float(r["p_model"]), 1e-6), 1.0 - 1e-6)
            y = 1.0 if r["wynik"] == "wygrany" else 0.0
            brier += (p - y) ** 2
            ll += -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))
            traf += int(y)
        sr_p = sum(float(r["p_model"]) for r in grp) / n
        return {
            "n": n, "trafione": traf, "hit": round(traf / n, 3),
            "sr_p": round(sr_p, 3),
            "brier": round(brier / n, 4), "logloss": round(ll / n, 4),
        }

    FLAGI = ("sugestia", "matchup", "matchup_styl", "rotacja",
             "wyzsza_linia", "miekka_linia")
    kategorie = {
        "wszystkie": settled,
        "zwykle": [r for r in settled if not any(r.get(f) for f in FLAGI)],
        "matchup": [r for r in settled if r.get("matchup")],
        # pełne matchupy STYLU (model/styl.py + matchup.py) — mierzone osobno
        # od "matchup" (profil koncesji rywala); wdrożone 2026-07-14, ocena
        # czy analogie stylu zarabiają możliwa dopiero od n>=~25
        "matchup_styl": [r for r in settled if r.get("matchup_styl")],
        "rotacja": [r for r in settled if r.get("rotacja")],
        "wyzsza_linia": [r for r in settled if r.get("wyzsza_linia")],
        "miekka_linia": [r for r in settled if r.get("miekka_linia")],
        "sugestie": [r for r in settled if r.get("sugestia")],
        # POMIAR PROGÓW: jak trafiają typy odrzucone tuż przy progu vs
        # przepuszczone — dopiero ta para liczb uzasadnia ruszanie progów
        "odrzucone_pomiar": [
            r for r in wszystkie_settled if r.get("odrzucony")
        ],
    }
    out: dict = {"kategorie": {}}
    for nazwa, grp in kategorie.items():
        s = _stats(grp)
        if s:
            out["kategorie"][nazwa] = s
    # pomiar wag zaufania per kubełek pewności — raport w typy_wyniki
    # (stosowanie: kupony.wagi_zaufania_z_pomiaru w build_wc_fast)
    out["wagi_zaufania"] = compute_wagi_zaufania(log)
    sklady: dict[str, list[int]] = {}
    for r in log.values():
        if r.get("zagral") is None:
            continue
        s = r.get("xi_sygnal") or "brak"
        d = sklady.setdefault(str(s), [0, 0])
        d[1] += 1
        d[0] += int(bool(r["zagral"]))
    out["sklady"] = {
        k: {"zagral": a, "n": b, "pct": round(a / b, 3)}
        for k, (a, b) in sklady.items()
    }
    # KALIBRACJA marży konsensusu UK (betting.UK_CONSENSUS_MARGIN, dziś założona):
    # dla rozliczonych okazji „powyżej" z kursem UK porównaj implikowane p rynku
    # (1/kurs_ref) do realnej częstości trafień. marża_est = 1 − hit/implied_sr.
    # Gdy marza_est zauważalnie różni się od używanej przy n>=~30 — podmień stałą.
    uk = [
        r for r in settled
        if r.get("kurs_ref") and float(r["kurs_ref"]) > 1.0
        and not r.get("sugestia") and r.get("strona") == "powyzej"
    ]
    if uk:
        n_uk = len(uk)
        hit_uk = sum(1 for r in uk if r["wynik"] == "wygrany") / n_uk
        implied_sr = sum(1.0 / float(r["kurs_ref"]) for r in uk) / n_uk
        marza_est = round(1.0 - hit_uk / implied_sr, 3) if implied_sr > 0 else None
        out["marza_uk"] = {
            "n": n_uk,
            "hit": round(hit_uk, 3),
            "implied_sr": round(implied_sr, 3),
            "marza_est": marza_est,
            "marza_uzywana": betting.UK_CONSENSUS_MARGIN,
        }
    return out


# pomin_powod TECHNICZNE: stary kupon żyje dalej jako NOWY rekord w tym samym
# slocie (wymiana lega) albo zostanie zastąpiony w tym samym cyklu (przebudowa
# po składach) — jego legi i tak trafią do nauki przez ten nowy wariant, więc
# licząc OBA (stary+nowy) podwójnie ważylibyśmy te same/prawie te same legi.
_POMIN_POWOD_TECHNICZNE = ("wymiana lega", "przebudowa po składach")


def _kupon_liczy_sie_do_nauki(k: dict) -> bool:
    """Czy kupon wchodzi do korelacji/kalibracji per-kupon (nauka).

    Kupony NIGDY nie pominięte oczywiście się liczą. Z pominiętych liczą się
    user-pominięte ("nie zagrałem") i WŁASNE (generator „ucz model") — obie
    mają realne, rozliczone wyniki i są PO TO, żeby zasilać ten mechanizm
    (patrz kupony_wlasne wyżej — user explicite godzi się uczyć model).
    NIE liczą się: stare sloty po zmianie konfiguracji (nie odzwierciedlają
    żadnej realnej decyzji) i techniczne pominięcia (patrz wyżej)."""
    if not k.get("pominiety"):
        return True
    if k.get("pominiety_przez") == "konfiguracja":
        return False
    if k.get("pomin_powod") in _POMIN_POWOD_TECHNICZNE:
        return False
    return True


def compute_kupony_diagnostyka(log_kuponow: dict) -> dict:
    """Uczenie KUPONÓW z rozliczeń (domyka pętlę, której nie zamyka kalibracja
    per-typ):

    1. KALIBRACJA — czy kupon o deklarowanej szansie X% trafia ~X% (per horyzont).
       Rozjazd hit << sr_p oznacza, że kara korelacji za słabo tnie szansę
       (kupony systematycznie przeszacowane) — i odwrotnie.
    2. Zmierzona KORELACJA legów z jednego meczu: czy padają razem CZĘŚCIEJ
       (wsp > 1) czy RZADZIEJ (wsp < 1) niż niezależność (iloczyn p_model).
       To dane pod zastąpienie ZGADYWANYCH kar (0.92 / 0.95 / 0.97) zmierzonymi:
       wsp < 1 potwierdza karę w dół, wsp > 1 mówi, że karzemy w złą stronę.

    Włącza user-pominięte i WŁASNE kupony (mają realne rozliczone wyniki —
    to one najbardziej cierpią na agresywne pomijanie, więc wykluczenie ich
    tu osłabiałoby dokładnie ten mechanizm, który ma naprawić przeszacowanie
    kuponów). Wyklucza tylko stare sloty po zmianie konfiguracji i techniczne
    pominięcia (wymiana lega / przebudowa po składach) — patrz
    _kupon_liczy_sie_do_nauki.
    """
    settled = [
        k for k in log_kuponow.values()
        if isinstance(k, dict) and _kupon_liczy_sie_do_nauki(k)
        and k.get("wynik") in ("wygrany", "przegrany")
    ]

    per_h: dict[str, dict] = {}
    for k in settled:
        h = k.get("horyzont") or "value"
        d = per_h.setdefault(h, {"n": 0, "traf": 0, "sp": 0.0, "brier": 0.0})
        y = 1.0 if k["wynik"] == "wygrany" else 0.0
        p = min(max(float(k.get("p_model") or 0.0), 1e-6), 1.0 - 1e-6)
        d["n"] += 1
        d["traf"] += int(y)
        d["sp"] += p
        d["brier"] += (p - y) ** 2
    kalibracja = {
        h: {
            "n": d["n"], "hit": round(d["traf"] / d["n"], 3),
            "sr_p": round(d["sp"] / d["n"], 3),
            "brier": round(d["brier"] / d["n"], 4),
        }
        for h, d in per_h.items() if d["n"]
    }

    # pary legów z tego samego meczu: [oba_wygrane, n_par, suma_iloczynu_p]
    grp = {"ta_sama": [0, 0, 0.0], "przeciwne": [0, 0, 0.0], "nieznane": [0, 0, 0.0]}
    kary = {
        "ta_sama": kupony_model.KARA_TA_SAMA_DRUZYNA,
        "przeciwne": kupony_model.KARA_PRZECIWNE_DRUZYNY,
        "nieznane": kupony_model.KARA_KORELACJI,
    }
    for k in settled:
        legi = [
            l for l in k.get("legi", [])
            if l.get("wynik") in ("wygrany", "przegrany")
        ]
        for i in range(len(legi)):
            for j in range(i + 1, len(legi)):
                a, b = legi[i], legi[j]
                if a.get("mecz_id") != b.get("mecz_id"):
                    continue
                da, db = str(a.get("druzyna") or ""), str(b.get("druzyna") or "")
                if da and db and da == db:
                    rel = "ta_sama"
                elif da and db and da != db:
                    rel = "przeciwne"
                else:
                    rel = "nieznane"
                g = grp[rel]
                g[0] += int(a["wynik"] == "wygrany" and b["wynik"] == "wygrany")
                g[1] += 1
                g[2] += float(a.get("p_model") or 0) * float(b.get("p_model") or 0)
    korelacja = {}
    for rel, (oba, n, sexp) in grp.items():
        if n < 1:
            continue
        obs = oba / n
        exp = sexp / n
        korelacja[rel] = {
            "n_par": n, "obs_oba": round(obs, 3), "exp_indep": round(exp, 3),
            "wsp": round(obs / exp, 3) if exp > 0 else None,
            "kara_uzywana": kary[rel],
        }
    return {"kalibracja": kalibracja, "korelacja": korelacja}


def _snapshot_zamkniecia(
    log: dict, value_bets: list[dict], kupony_list: list[dict], now: int
) -> None:
    """CLV: kurs zamknięcia = ostatni kurs widziany PRZED startem meczu.

    Cykl chodzi co ~30 min, więc nadpisujemy snapshot do kickoffu — po meczu
    zostaje ostatnia wycena rynku. Porównanie "kurs wzięty przy publikacji vs
    zamknięcie" to najszybszy miernik, czy typy biją rynek (dodatnie CLV
    wygrywa długoterminowo, nawet gdy krótka seria jest na minusie).
    """
    kursy_teraz: dict[str, float] = {}
    for b in value_bets:
        if b.get("kurs"):
            kursy_teraz[_klucz(b)] = float(b["kurs"])
    for k in kupony_list:
        for l in k["legi"]:
            if l.get("kurs"):
                kursy_teraz.setdefault(_klucz(l), float(l["kurs"]))
    for kk, rec in log.items():
        if not rec.get("wynik") and rec["kickoff_ts"] > now and kk in kursy_teraz:
            rec["kurs_zamkniecia"] = kursy_teraz[kk]


def _sloty_aktualne() -> set[str]:
    """Sloty wynikające z AKTUALNEJ konfiguracji przedziałów kursowych —
    na stronie wisi maks. jeden kupon na przedział (user: razem max 4
    dzienne i max 4 długoterminowe)."""
    return (
        {f"dzienny:{int(a)}–{int(b)}"
         for a, b in kupony_model.PRZEDZIALY_DZIENNE}
        | {f"dlugoterminowy:{int(a)}–{int(b)}"
           for a, b in kupony_model.PRZEDZIALY_DLUGOTERMINOWE}
        | {f"value:{int(a)}–{int(b)}"
           for a, b in kupony_model.PRZEDZIALY_VALUE}
    )


def _sygnatura_legow(legi: list[dict]) -> frozenset:
    return frozenset(
        (l["mecz_id"], l["podmiot"], l.get("rynek_kod", ""), l["linia"], l["strona"])
        for l in legi
    )


# capy wariantów kluczy per slot/dzień — bez nich seryjne pomijanie/wymiany
# rozdymały log (#2/#3/... bez końca) i koszt skanów Jaccard przy publikacji
MAX_WARIANTOW_DNIA = 10
MAX_WYMIAN_DNIA = 5


def _kupon_do_logu(
    log_kuponow: dict,
    kupony_list: list[dict],
    now: int,
    niedostepni: set[int] | None = None,
    pominiete: set[str] | None = None,
    powody: dict[str, str] | None = None,
    wymiany: set[str] | None = None,
    przebudowy: set[str] | None = None,
    conf_mids: set[int] | None = None,
    legi_pool: list[dict] | None = None,
) -> None:
    """Cykl życia kuponu — przemyślany raz, potem ZAMROŻONY.

    Zasady (decyzja usera):
      * kupon po pierwszej publikacji się NIE zmienia (koniec z typami
        znikającymi między cyklami),
      * jedyny powód unieważnienia: potwierdzone składy wywróciły lega
        (zawodnik poza XI, a jego mecz jeszcze się nie zaczął) -> stary kupon
        dostaje wynik "anulowany" z powodem, a slot się zwalnia,
      * nowy kupon w danym slocie (horyzont+przedział) powstaje TYLKO, gdy
        poprzedni jest rozliczony (wygrany/przegrany), anulowany albo
        POMINIĘTY przez usera (przycisk w UI — klucz w `kupony_pominiete`);
        pominięty kupon znika z aktywnych, ale rozlicza się dalej w tle,
        żeby model uczył się także z niezagranych kuponów,
      * do zwolnionego przez pominięcie slotu nie wraca IDENTYCZNY zestaw
        legów — czekamy, aż pula da inny kupon,
      * nie publikujemy kuponu, którego pierwszy mecz już trwa.
    """
    niedostepni = niedostepni or set()
    pominiete = pominiete or set()
    dzien = time.strftime("%Y-%m-%d", time.localtime(now))

    # migracja starych rekordów (klucz = "horyzont:przedział:data")
    for key, rec in log_kuponow.items():
        rec.setdefault("slot", ":".join(key.split(":")[:2]))
        rec.setdefault("klucz", key)

    # 1) unieważnij aktywne kupony, którym ogłoszone składy wywróciły lega
    for rec in log_kuponow.values():
        if rec.get("wynik"):
            continue
        poza = [
            l for l in rec["legi"]
            if l.get("podmiot_id") in niedostepni and l["kickoff_ts"] > now
        ]
        if poza:
            rec.update(
                wynik="anulowany", rozliczono_ts=now,
                powod="zmiana składu: " + ", ".join(l["podmiot"] for l in poza),
            )

    # 1b) kupony pominięte przez usera: zwalniają slot, ale wynik zostaje
    # pusty — legi i kupon rozliczą się normalnie (dane do nauki modelu)
    for rec in log_kuponow.values():
        if rec.get("klucz") in pominiete and not rec.get("pominiety"):
            rec["pominiety"] = True
            rec["pominieto_ts"] = now
            rec["pominiety_przez"] = "user"
            rec["pomin_powod"] = (powody or {}).get(rec.get("klucz"))

    # 1b2) PRZYWRACANIE: user cofnął pominięcie (klucz zniknął z
    # kupony_pominiete) — wraca, o ile slot nie został już zajęty nowszym
    zajete_teraz = {
        r["slot"] for r in log_kuponow.values()
        if not r.get("wynik") and not r.get("pominiety")
    }
    # kolejność DETERMINISTYCZNA: przy dwóch kandydatach do tego samego slotu
    # wraca najdawniej pominięty (potem tie-break po kluczu) — wcześniej
    # decydowała przypadkowa kolejność iteracji po dict
    do_przywrocenia = sorted(
        (
            rec for rec in log_kuponow.values()
            if rec.get("pominiety")
            and rec.get("pominiety_przez") == "user"
            and not rec.get("wynik")
            and rec.get("klucz") not in pominiete
            and rec.get("pomin_powod")
            not in ("wymiana lega", "przebudowa po składach")
        ),
        key=lambda r: (r.get("pominieto_ts") or 0, r.get("klucz") or ""),
    )
    for rec in do_przywrocenia:
        if rec.get("slot") in zajete_teraz:
            continue
        rec["pominiety"] = False
        rec.pop("pominieto_ts", None)
        rec.pop("pominiety_przez", None)
        rec.pop("pomin_powod", None)
        zajete_teraz.add(rec["slot"])

    # 1b3) WYMIANA LEGA jednym klikiem: pomiń bieżący kupon i opublikuj
    # w jego slocie wariant z alternatywą rentgena (kurs_po / p_po już
    # policzone z karą korelacyjną)
    for rec in list(log_kuponow.values()):
        kl = rec.get("klucz")
        if (
            kl not in (wymiany or set())
            or rec.get("wynik") or rec.get("pominiety")
            or not rec.get("alternatywa")
        ):
            continue
        alt = rec["alternatywa"]
        idx = int(alt.get("zamiast_idx") or 0)
        alt_leg = {
            k2: v for k2, v in alt.items()
            if k2 not in ("zamiast_idx", "kurs_po", "p_po")
        }
        kurs_po = float(alt.get("kurs_po") or 0) or None
        p_po = float(alt.get("p_po") or 0) or None
        # ŚWIEŻA wycena wymienianego lega z bieżącej puli — alternatywa była
        # liczona przy publikacji i jej kurs/p potrafią być nieaktualne.
        # Kara korelacji zależy tylko od zestawu, więc skalowanie zamrożonych
        # kurs_po/p_po ilorazem świeżych i zamrożonych wartości lega jest
        # dokładne. Gdy lega nie ma już w ofercie, wymiana jest niewykonalna
        # i kupon zostaje bez zmian (zamiast pominięcia w ciemno).
        if legi_pool is not None:
            fresh = next(
                (
                    b for b in legi_pool
                    if b.get("mecz_id") == alt_leg.get("mecz_id")
                    and b.get("podmiot_id") == alt_leg.get("podmiot_id")
                    and b.get("rynek_kod") == alt_leg.get("rynek_kod")
                    and abs(float(b.get("linia") or 0)
                            - float(alt_leg.get("linia") or 0)) < 1e-6
                    and b.get("strona") == alt_leg.get("strona")
                ),
                None,
            )
            if fresh is None:
                continue
            if kurs_po and float(alt_leg.get("kurs") or 0) > 0:
                kurs_po = kurs_po * float(fresh["kurs"]) / float(alt_leg["kurs"])
            if p_po and float(alt_leg.get("p_model") or 0) > 0:
                p_po = p_po * float(fresh["p_model"]) / float(alt_leg["p_model"])
            alt_leg = {**alt_leg, "kurs": fresh["kurs"],
                       "p_model": fresh["p_model"]}
        legi = [dict(l) for i, l in enumerate(rec["legi"]) if i != idx]
        legi.append(alt_leg)
        legi.sort(key=lambda l: (l["kickoff_ts"], l["mecz_id"], -l["p_model"]))
        if min(l["kickoff_ts"] for l in legi) <= now + 15 * 60:
            continue  # pierwszy mecz za chwilę — za późno na wymianę
        if not kurs_po or not p_po:
            continue  # bez wyceny nie publikujemy — kupon zostaje bez zmian
        klucz_n, n = f"{rec['slot']}:{dzien}#w", 2
        while klucz_n in log_kuponow:
            klucz_n, n = f"{rec['slot']}:{dzien}#w{n}", n + 1
        if n > MAX_WYMIAN_DNIA + 2:
            continue  # cap wariantów wymiany na slot/dzień — log nie puchnie
        rec.update(pominiety=True, pominieto_ts=now,
                   pominiety_przez="user", pomin_powod="wymiana lega")
        log_kuponow[klucz_n] = {
            **{k2: rec[k2] for k2 in ("cel", "cel_label", "styl", "horyzont")
               if k2 in rec},
            "kurs_laczny": round(kurs_po, 2), "p_model": round(p_po, 4),
            "fair_kurs": round(1.0 / max(p_po, 1e-9), 2),
            "ev_pct": round((p_po * kurs_po - 1.0) * 100.0, 1),
            "legi": legi, "slot": rec["slot"], "klucz": klucz_n,
            "dzien": dzien, "opublikowano_ts": now, "wynik": None,
            "z_wymiany": True,
        }

    # 1b4) PRZEBUDOWA PO SKŁADACH (opt-in): pomiń, gdy WSZYSTKIE mecze legów
    # mają potwierdzone XI — builder w tym samym cyklu złoży nowy kupon już
    # na pewnych składach
    for rec in log_kuponow.values():
        if (
            rec.get("klucz") in (przebudowy or set())
            and not rec.get("wynik") and not rec.get("pominiety")
        ):
            mids = {l["mecz_id"] for l in rec["legi"]}
            if mids and mids <= (conf_mids or set()):
                rec.update(pominiety=True, pominieto_ts=now,
                           pominiety_przez="user",
                           pomin_powod="przebudowa po składach")

    # 1c) sloty wycofane (zmiana konfiguracji przedziałów): aktywny kupon ze
    # starego przedziału schodzi z widoku jak pominięty i rozlicza się w tle
    # — na stronie zostaje maks. JEDEN kupon na każdy aktualny przedział
    aktualne_sloty = _sloty_aktualne()
    for rec in log_kuponow.values():
        if (
            not rec.get("wynik")
            and not rec.get("pominiety")
            and rec.get("slot") not in aktualne_sloty
        ):
            rec["pominiety"] = True
            rec["pominieto_ts"] = now
            rec["pominiety_przez"] = "konfiguracja"

    # 2) nowe kupony wyłącznie do wolnych slotów
    zajete = {
        r["slot"] for r in log_kuponow.values()
        if not r.get("wynik") and not r.get("pominiety")
    }
    # zestawy legów pominiętych, jeszcze nierozliczonych kuponów per slot —
    # user właśnie je odrzucił, nie publikujemy ich ponownie 1:1; pominięcia
    # TECHNICZNE (wymiana/przebudowa/zmiana konfiguracji) nie blokują puli
    odrzucone: dict[str, set[frozenset]] = {}
    for r in log_kuponow.values():
        if (
            r.get("pominiety") and not r.get("wynik")
            and r.get("pominiety_przez") != "konfiguracja"
            and r.get("pomin_powod")
            not in ("wymiana lega", "przebudowa po składach")
        ):
            odrzucone.setdefault(r["slot"], set()).add(_sygnatura_legow(r["legi"]))
    for k in kupony_list:
        if not k.get("legi"):
            continue
        slot = f"{k.get('horyzont', '?')}:{k.get('cel_label', k.get('cel'))}"
        if slot in zajete:
            continue  # poprzedni kupon wciąż w grze — nie podmieniamy go
        if min(l["kickoff_ts"] for l in k["legi"]) <= now + 15 * 60:
            continue  # pierwszy mecz trwa lub startuje za chwilę — za późno
        if any(l.get("podmiot_id") in niedostepni for l in k["legi"]):
            continue  # leg z zawodnikiem poza składem — czekaj na kolejny cykl
        sygn = _sygnatura_legow(k["legi"])
        # user właśnie pominął ten zestaw — nie wraca ani identyczny, ani
        # prawie identyczny (Jaccard >= 0.7, np. 7 legów z 1 zamianą)
        if any(
            len(sygn & odrz) / max(len(sygn | odrz), 1) >= 0.7
            for odrz in odrzucone.get(slot, set())
        ):
            continue
        klucz, n = f"{slot}:{dzien}", 2
        while klucz in log_kuponow:
            klucz, n = f"{slot}:{dzien}#{n}", n + 1
        if n > MAX_WARIANTOW_DNIA + 2:
            continue  # cap publikacji na slot/dzień — chroni log i skan Jaccard
        log_kuponow[klucz] = {
            **k, "slot": slot, "klucz": klucz, "dzien": dzien,
            "opublikowano_ts": now, "wynik": None,
        }
        zajete.add(slot)


def _rozlicz_kupony(log_kuponow: dict, typy_log: dict, now: int) -> list[dict]:
    """Wynik kuponu z wyników legów: przegrany od pierwszego pudła; wygrany,
    gdy wszystkie legi trafione (zwrot wyłącza lega z kursu, jak u buka)."""
    for rec in log_kuponow.values():
        statusy = []
        for l in rec["legi"]:
            tk = (f"{l['mecz_id']}:{rotowire._norm(str(l['podmiot']))}:"
                  f"{l.get('rynek_kod', '')}:{l['linia']}:{l['strona']}")
            s = (typy_log.get(tk) or {}).get("wynik")
            # status lega zapisany w kuponie — podgląd kuponu w historii
            # pokazuje, które legi siadły (także dla już rozliczonych)
            l["wynik"] = s
            statusy.append((l, s))
        rec["legi_trafione"] = sum(1 for _, s in statusy if s == "wygrany")
        rec["legi_rozliczone"] = sum(1 for _, s in statusy if s)
        # superzmiana potrafi odwrócić lega PO rozliczeniu kuponu: gdy po
        # rewizji wszystkie legi siadły, przegrany kupon wraca do wygranego
        if (
            rec.get("wynik") == "przegrany"
            and statusy
            and all(s in ("wygrany", "zwrot") for _, s in statusy)
        ):
            kurs = 1.0
            for l, s in statusy:
                if s == "wygrany" and l.get("kurs"):
                    kurs *= l["kurs"]
            rec.update(wynik="wygrany", kurs_rozliczony=round(kurs, 2),
                       rozliczono_ts=now,
                       powod="superzmiana odwróciła przegranego lega")
            continue
        if rec.get("wynik"):
            continue
        if any(s == "przegrany" for _, s in statusy):
            rec.update(wynik="przegrany", rozliczono_ts=now)
        elif all(s in ("wygrany", "zwrot") for _, s in statusy):
            kurs = 1.0
            for l, s in statusy:
                if s == "wygrany":
                    kurs *= l["kurs"]
            # same zwroty = stawka wraca (kurs 1.0), nie "wygrany"
            wynik = "wygrany" if any(s == "wygrany" for _, s in statusy) else "zwrot"
            rec.update(wynik=wynik, kurs_rozliczony=round(kurs, 2),
                       rozliczono_ts=now)
    return sorted(
        log_kuponow.values(),
        key=lambda r: (-(r.get("opublikowano_ts") or 0)),
    )[:40]


def _typ_dnia(r: dict) -> dict:
    """Odchudzony typ do listy dziennej (co siadło danego dnia)."""
    return {
        "mecz": r.get("mecz"), "kickoff_ts": r.get("kickoff_ts"),
        "podmiot": r.get("podmiot"), "rynek_kod": r.get("rynek_kod"),
        "rynek": r.get("rynek"), "linia": r.get("linia"),
        "strona": r.get("strona"), "kurs": r.get("kurs"),
        "p_model": r.get("p_model"), "wynik": r.get("wynik"),
        "faktyczna": r.get("faktyczna"), "clv_pct": r.get("clv_pct"),
        # typ poza publikacją (kwarantanna/limit meczu) — w liście dnia
        # widoczny z oznaczeniem, ale poza licznikami skuteczności
        "poza_publikacja": r.get("poza_publikacja"),
    }


def skutecznosc_per_dzien(
    settled: list[dict], dni: int = 21, poza: list[dict] | None = None,
) -> list[dict]:
    """Skuteczność realnych typów pogrupowana po DNIU meczu (kickoff).

    Zwraca ostatnie `dni` dni (od najnowszego): trafienia, ROI flat (stawka
    1 j./okazję), liczbę okazji ORAZ listę typów tego dnia (`typy` — realne
    typy, które siadły/nie siadły), żeby dzień można było rozwinąć. ROZLICZONE
    typy tylko — `settled` powinno być już bez rynków osobnych.

    `poza` = typy poza publikacją (kwarantanna rynku / limit meczu): trafiają
    do listy dnia z oznaczeniem i osobnych liczników (poza_n/poza_trafione),
    ale NIE wchodzą do trafień/ROI — user ich nie widział na liście typów.
    """
    dzienne: dict[str, dict] = {}

    def _agg(r: dict) -> dict:
        d = time.strftime("%Y-%m-%d", time.localtime(r.get("kickoff_ts") or 0))
        return dzienne.setdefault(d, {
            "dzien": d, "rozliczone": 0, "trafione": 0,
            "okazje": 0, "_zwrot_j": 0.0, "typy": [],
            "poza_n": 0, "poza_trafione": 0,
        })

    for r in settled:
        agg = _agg(r)
        agg["rozliczone"] += 1
        if r.get("wynik") == "wygrany":
            agg["trafione"] += 1
        if not r.get("sugestia") and r.get("kurs"):
            agg["okazje"] += 1
            agg["_zwrot_j"] += r["kurs"] if r.get("wynik") == "wygrany" else 0.0
        agg["typy"].append(_typ_dnia(r))
    for r in poza or []:
        agg = _agg(r)
        agg["poza_n"] += 1
        if r.get("wynik") == "wygrany":
            agg["poza_trafione"] += 1
        agg["typy"].append(_typ_dnia(r))
    out = []
    for d in sorted(dzienne, reverse=True)[:dni]:
        agg = dzienne[d]
        agg["roi_flat"] = round(agg.pop("_zwrot_j") - agg["okazje"], 2)
        # publikowane przed typami poza publikacją; w obrębie grupy trafione
        # na górze, potem po nazwie
        agg["typy"].sort(
            key=lambda t: (
                bool(t.get("poza_publikacja")),
                t.get("wynik") != "wygrany",
                str(t.get("podmiot")),
            )
        )
        out.append(agg)
    return out


def rozlicz(
    value_bets: list[dict],
    kupony_list: list[dict] | None = None,
    niedostepni: set[int] | None = None,
    conf_mids: set[int] | None = None,
    legi_pool: list[dict] | None = None,
) -> dict:
    """Dopisz nowe typy do logu, rozlicz zakończone, zwróć podsumowanie."""
    log = _migruj_log(supa.get_key("typy_log") or {})
    _dopisz_nowe(log, value_bets)
    # legi kuponów też muszą być w logu (pewniaki spoza publikowanych typów)
    for k in kupony_list or []:
        _dopisz_nowe(log, [_kupon_leg_do_logu(l) for l in k["legi"]])
    # WŁASNE kupony usera (generator „ucz model") — ich legi też do logu, żeby
    # się rozliczyły; sam kupon trafia do kupony_log jako pominięty (niżej)
    kupony_wlasne = supa.get_key("kupony_wlasne") or {}
    for wk in kupony_wlasne.values():
        _dopisz_nowe(log, [_kupon_leg_do_logu(l) for l in (wk.get("legi") or [])
                            if l.get("mecz_id") and l.get("podmiot")])
    lib = supa.get_key("trend_lib") or {}
    now = int(time.time())
    cache_365: dict = {}
    # mecze przełożone: jeśli mecz wciąż figuruje w nadchodzących typach,
    # deadline braku danych nie może zamknąć jego legów jako zwrot
    mecze_przyszle = {
        b["mecz"] for b in value_bets if (b.get("kickoff_ts") or 0) > now
    }
    for k in kupony_list or []:
        for l in k["legi"]:
            if (l.get("kickoff_ts") or 0) > now:
                mecze_przyszle.add(l["mecz"])

    _snapshot_zamkniecia(log, value_bets, kupony_list or [], now)

    for rec in log.values():
        if rec.get("wynik") or now - rec["kickoff_ts"] < MECZ_KONIEC_PO_S:
            continue
        mk = rec["rynek_kod"]

        # RYNKI DRUŻYNOWE — osobna, prosta ścieżka (statystyki drużynowe 365)
        if mk in MARKETY_DRUZYNOWE:
            gid_t = _gid_365(rec, cache_365)
            wartosc_t = None
            if gid_t is not None and not scores365.after_extra_time(gid_t):
                try:
                    st_t = scores365.game_team_stats(gid_t)
                except Exception:
                    st_t = None
                if st_t:
                    tk = rotowire._norm(str(rec["podmiot"]))
                    if tk in st_t:
                        w_t = st_t[tk].get(MARKETY_DRUZYNOWE[mk])
                        wartosc_t = float(w_t) if w_t is not None else None
            if wartosc_t is None:
                if (
                    now - rec["kickoff_ts"] > TERMIN_BRAK_DANYCH_S
                    and rec.get("mecz") not in mecze_przyszle
                ):
                    rec.update(wynik="zwrot", faktyczna=None,
                               rozliczono_ts=now, powod="brak danych źródła")
                continue
            traf_t = (
                wartosc_t > rec["linia"] if rec["strona"] == "powyzej"
                else wartosc_t < rec["linia"]
            )
            rec.update(
                wynik="wygrany" if traf_t else "przegrany",
                faktyczna=wartosc_t, rozliczono_ts=now, zagral=True,
            )
            if rec.get("kurs") and rec.get("kurs_zamkniecia"):
                rec["clv_pct"] = round(
                    (rec["kurs"] / rec["kurs_zamkniecia"] - 1.0) * 100.0, 1
                )
            continue

        # pełne statystyki meczu z 365 (minuty + faule/przechwyty) — dostępne
        # tuż po końcowym gwizdku, niezależnie od odświeżeń banku trendów
        gid = _gid_365(rec, cache_365)
        staty = None
        if gid is not None:
            try:
                staty = scores365.game_player_match_stats(gid)
            except Exception:
                staty = None
        pkey = scores365.resolve_player_key(set(staty), rec["podmiot"]) if staty else None

        # minuty: najpierw 365 (nieobecny w statystykach meczu = nie zagrał),
        # fallback bank trendów
        minuty = None
        if staty:
            minuty = float(staty[pkey].get("minutes", 0)) if pkey else 0.0
        if minuty is None:
            minuty = _minuty_z_banku(rec, lib)
        if minuty is not None and minuty <= 0:
            rec.update(wynik="zwrot", faktyczna=0.0, rozliczono_ts=now,
                       powod="nie zagrał", zagral=False)
            continue

        wartosc = None
        if mk in MARKETY_365:
            gra = None
            if gid is not None:
                try:
                    gra = scores365.game_player_shots(gid)
                except Exception:
                    gra = None
            if gra is not None:
                skey = scores365.resolve_player_key(set(gra), rec["podmiot"])
                if skey:
                    wartosc = float(gra[skey].get(MARKETY_365[mk], 0))
                elif minuty:
                    # zagrał (minuty > 0), a nie ma go w mapie = 0 zdarzeń
                    wartosc = 0.0
        elif mk in MARKETY_LIB:
            # staty lineups obejmują CAŁY mecz — przy dogrywce nie nadają się
            # do rozliczenia rynku regularnego czasu (bank trendów zostaje)
            if (
                mk in MARKETY_365_STATY and staty and pkey
                and not scores365.after_extra_time(gid)
            ):
                w = staty[pkey].get(mk)
                wartosc = float(w) if w is not None else None
            if wartosc is None:
                wartosc = _wartosc_z_banku(rec, lib)
        if wartosc is None:
            # źródło nie ma jeszcze meczu — spróbujemy w kolejnym cyklu;
            # po terminie zamykamy jako zwrot, żeby nic nie wisiało "w grze"
            if (
                now - rec["kickoff_ts"] > TERMIN_BRAK_DANYCH_S
                and rec.get("mecz") not in mecze_przyszle
            ):
                rec.update(wynik="zwrot", faktyczna=None, rozliczono_ts=now,
                           powod="brak danych źródła")
            continue
        trafiony = (
            wartosc > rec["linia"] if rec["strona"] == "powyzej" else wartosc < rec["linia"]
        )
        if not trafiony:
            sz = _superzmiana(rec, gid, staty, lib, wartosc)
            if sz:
                wartosc, rec["powod"] = sz
                rec["superzmiana"] = True
                trafiony = True
            if gid is not None:
                rec["superzmiana_spr"] = True  # sprawdzone — rewizja nie dubluje
        rec.update(
            wynik="wygrany" if trafiony else "przegrany",
            faktyczna=wartosc, rozliczono_ts=now, zagral=True,
        )
        if rec.get("kurs") and rec.get("kurs_zamkniecia"):
            rec["clv_pct"] = round(
                (rec["kurs"] / rec["kurs_zamkniecia"] - 1.0) * 100.0, 1
            )

    # rewizja WSTECZ: legi przegrane przed wdrożeniem superzmiany (albo gdy
    # danych o zmianie jeszcze nie było) — każdy rekord sprawdzamy raz
    for rec in log.values():
        if (
            rec.get("wynik") != "przegrany"
            or rec.get("superzmiana_spr")
            or rec.get("strona") != "powyzej"
            or rec.get("rynek_kod") not in SUPERZMIANA_RYNKI
            or "superbet" not in str(rec.get("bukmacher") or "").lower()
        ):
            continue
        gid = _gid_365(rec, cache_365)
        if gid is None:
            # dane 365 mogą dojść później — flagę "sprawdzone" wolno ustawić
            # dopiero, gdy mecz znaleziono (albo gdy szanse na dane minęły)
            if now - (rec.get("rozliczono_ts") or 0) > 72 * 3600:
                rec["superzmiana_spr"] = True
            continue
        rec["superzmiana_spr"] = True
        try:
            staty = scores365.game_player_match_stats(gid)
        except Exception:
            staty = None
        sz = _superzmiana(rec, gid, staty, lib, rec.get("faktyczna"))
        if sz:
            wartosc, powod = sz
            rec.update(wynik="wygrany", faktyczna=wartosc, rozliczono_ts=now,
                       superzmiana=True, powod=powod)

    # przycinanie: wpisy bez wyniku, których mecz był >30 dni temu, to śmieci
    # (nigdy się nie rozliczą); ROZLICZONE zostają — to dataset kalibracji
    log = {
        k: r for k, r in log.items()
        if r.get("wynik") or now - (r.get("kickoff_ts") or now) < 30 * 86400
    }
    supa.put_key("typy_log", log)

    # ---- historia kuponów ----
    log_kuponow = supa.get_key("kupony_log") or {}
    # wmerguj WŁASNE kupony (generator „ucz model") jako pominięte — rozliczą
    # się w tle i zasilą korelację/kalibrację (jak automatyczne pominięte)
    for wkey, wk in kupony_wlasne.items():
        klucz = f"wlasny:{wkey}"[:150]
        legi = wk.get("legi") or []
        if klucz in log_kuponow or len(legi) < 2:
            continue
        log_kuponow[klucz] = {
            "klucz": klucz, "slot": "wlasny", "horyzont": "wlasny", "styl": "wlasny",
            "cel": 0, "cel_label": "własny",
            "kurs_laczny": wk.get("kurs_laczny"), "p_model": wk.get("p_model"),
            "legi": legi, "pominiety": True, "pominiety_przez": "user",
            "opublikowano_ts": int(wk.get("zapisano_ts") or now), "wynik": None,
        }
    if kupony_wlasne:
        supa.put_key("kupony_wlasne", {})   # bufor przetworzony — czyścimy
    # kupony pominięte przyciskiem w UI (web zapisuje klucz -> ts albo
    # {ts, powod}); wpisy starsze niż 14 dni wypadają
    pominiete_raw = supa.get_key("kupony_pominiete") or {}

    def _pomin_ts(v) -> int:
        return int((v.get("ts") if isinstance(v, dict) else v) or 0)

    pominiete = {
        k: v for k, v in pominiete_raw.items()
        if now - _pomin_ts(v) < 14 * 86400
    }
    if len(pominiete) != len(pominiete_raw):
        supa.put_key("kupony_pominiete", pominiete)
    powody = {
        k: v.get("powod") for k, v in pominiete.items() if isinstance(v, dict)
    }
    # akcje z UI: wymiana lega (zastosuj alternatywę) i przebudowa po
    # składach (opt-in) — klucze z TTL 3 dni
    wymiany_raw = supa.get_key("kupony_wymiana") or {}
    wymiany = {
        k: ts for k, ts in wymiany_raw.items() if now - int(ts or 0) < 3 * 86400
    }
    if len(wymiany) != len(wymiany_raw):
        supa.put_key("kupony_wymiana", wymiany)
    przebudowy_raw = supa.get_key("kupony_przebudowa") or {}
    przebudowy = {
        k: ts for k, ts in przebudowy_raw.items()
        if now - int(ts or 0) < 3 * 86400
    }
    if len(przebudowy) != len(przebudowy_raw):
        supa.put_key("kupony_przebudowa", przebudowy)
    _kupon_do_logu(log_kuponow, kupony_list or [], now, niedostepni,
                   set(pominiete), powody=powody, wymiany=set(wymiany),
                   przebudowy=set(przebudowy), conf_mids=conf_mids,
                   legi_pool=legi_pool)
    kupony_hist = _rozlicz_kupony(log_kuponow, log, now)
    # ROI kuponów per horyzont (stawka 1 j./kupon; pominięte = niezagrane,
    # nie wchodzą) — liczone z PEŁNEGO logu przed przycinaniem
    kupony_roi: dict[str, dict] = {}
    for r in log_kuponow.values():
        if r.get("pominiety") or r.get("wynik") not in (
            "wygrany", "przegrany", "zwrot"
        ):
            continue
        h = r.get("horyzont") or "value"
        d = kupony_roi.setdefault(h, {"n": 0, "wygrane": 0, "zwrot_j": 0.0})
        d["n"] += 1
        if r["wynik"] == "wygrany":
            d["wygrane"] += 1
            d["zwrot_j"] += float(
                r.get("kurs_rozliczony") or r.get("kurs_laczny") or 0
            )
        elif r["wynik"] == "zwrot":
            d["zwrot_j"] += 1.0
    for d in kupony_roi.values():
        d["zwrot_j"] = round(d["zwrot_j"], 2)
        d["roi_j"] = round(d["zwrot_j"] - d["n"], 2)
    # WSZYSTKIE wygrane kupony — trwały log, który NIGDY nie znika (osobna
    # sekcja na Skuteczności). Zbierany z PEŁNEGO logu przed przycinaniem; raz
    # wygrany kupon zostaje na zawsze (superzmiana tylko dokłada wygrane).
    # Odchudzamy o pola doradcze aktywnego kuponu (rentgen), które w historii
    # są zbędne i tylko puchłyby payload.
    wygrane_log = supa.get_key("kupony_wygrane") or {}
    _POMIN_POLA = ("alternatywa", "wariant_b", "dolozenie", "najslabszy_idx")
    for r in log_kuponow.values():
        if r.get("wynik") != "wygrany" or not r.get("klucz"):
            continue
        wygrane_log[r["klucz"]] = {
            k: v for k, v in r.items() if k not in _POMIN_POLA
        }
    if wygrane_log:
        supa.put_key("kupony_wygrane", wygrane_log)
    kupony_wygrane = sorted(
        wygrane_log.values(),
        key=lambda r: -(r.get("rozliczono_ts") or r.get("opublikowano_ts") or 0),
    )
    # przycinanie: kupony rozliczone/anulowane starsze niż 21 dni wypadają
    # (UI i tak pokazuje top 40; payload nie może rosnąć bez końca)
    log_kuponow = {
        k: r for k, r in log_kuponow.items()
        if not r.get("wynik")
        or now - (r.get("rozliczono_ts") or now) < 21 * 86400
    }
    supa.put_key("kupony_log", log_kuponow)

    # ---- podsumowanie do UI ----
    # strzały niecelne/zablokowane (RYNKI_OSOBNE) NIE wchodzą do skuteczności
    # ani ROI — uczą się w tle (typy_log/kalibracja), ale nie są pokazywane.
    # Typy POMIAROWE (odrzucone przy progu) też zostają poza wszystkim —
    # nigdy nie były opublikowane, mierzy je tylko diagnostyka kategorii.
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and r.get("rynek_kod") not in RYNKI_OSOBNE
        and not r.get("odrzucony")
        # typy spoza publikacji uczą kalibrację, ale nie liczą się do
        # pokazywanej skuteczności — user ich nie widział, nie mógł zagrać
        and not r.get("poza_publikacja")
    ]
    okazje = [r for r in settled if not r["sugestia"] and r.get("kurs")]
    roi = sum(
        (r["kurs"] - 1.0) if r["wynik"] == "wygrany" else -1.0 for r in okazje
    )
    # typy poza publikacją (kwarantanna/limit meczu): w Skuteczności widoczne
    # z oznaczeniem (pełna transparentność), ale poza licznikami trafień/ROI
    poza_pub = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and r.get("rynek_kod") not in RYNKI_OSOBNE
        and not r.get("odrzucony")
        and r.get("poza_publikacja")
    ]

    def _po_rynku(recs: list[dict]) -> list[dict]:
        out = []
        for mk in sorted({r["rynek_kod"] for r in recs}):
            grp = [r for r in recs if r["rynek_kod"] == mk]
            traf = sum(1 for r in grp if r["wynik"] == "wygrany")
            sr_p = sum(r["p_model"] for r in grp) / len(grp)
            out.append({
                "rynek_kod": mk, "rynek": grp[0]["rynek"], "n": len(grp),
                "trafione": traf,
                "sr_p_model": round(sr_p, 3),
                "czestosc": round(traf / len(grp), 3),
                # bias > 1 = model niedoszacowuje, < 1 = przeszacowuje;
                # stosowany w modelu dopiero od n>=25 (na razie raport)
                "bias": round((traf + 2.0) / (sr_p * len(grp) + 2.0), 3),
            })
        return out

    po_rynku = _po_rynku(settled)

    # skuteczność DZIEŃ PO DNIU (realne typy, bez rynków osobnych) — z listą
    # typów danego dnia (co siadło); zasila przełącznik dnia na Skuteczności
    skutecznosc_dzienna = skutecznosc_per_dzien(settled, poza=poza_pub)

    ostatnie = sorted(
        settled + poza_pub + [
            r for r in log.values()
            if r.get("wynik") == "zwrot"
            and r.get("rynek_kod") not in RYNKI_OSOBNE
            and not r.get("odrzucony")
        ],
        key=lambda r: -(r.get("rozliczono_ts") or 0),
    )[:60]
    z_clv = [r for r in settled if r.get("clv_pct") is not None]
    diagnostyka = compute_diagnostyka(log)
    for nazwa, s in diagnostyka["kategorie"].items():
        print(
            f"Diag {nazwa}: n={s['n']} hit={s['hit']} śr.p={s['sr_p']} "
            f"Brier={s['brier']} logloss={s['logloss']}"
        )
    if diagnostyka["sklady"]:
        print("Sygnały XI: " + ", ".join(
            f"{k}: zagrał {v['zagral']}/{v['n']} ({v['pct']:.0%})"
            for k, v in diagnostyka["sklady"].items()
        ))
    kupony_diag = compute_kupony_diagnostyka(log_kuponow)
    for h, s in kupony_diag["kalibracja"].items():
        print(f"Kupony {h}: hit={s['hit']} vs śr.p={s['sr_p']} (n={s['n']}, Brier={s['brier']})")
    for rel, s in kupony_diag["korelacja"].items():
        print(
            f"Korelacja legów [{rel}]: obs={s['obs_oba']} vs indep={s['exp_indep']} "
            f"wsp={s['wsp']} (n_par={s['n_par']}, kara={s['kara_uzywana']})"
        )
    return {
        "diagnostyka": diagnostyka,
        "kupony_diag": kupony_diag,
        "podsumowanie": {
            # bez rynków osobnych (niecelne/zablokowane) — te są liczone osobno
            "opublikowane": sum(
                1 for r in log.values()
                if r.get("rynek_kod") not in RYNKI_OSOBNE
                and not r.get("odrzucony")
                and not r.get("poza_publikacja")
            ),
            "rozliczone": len(settled),
            "trafione": sum(1 for r in settled if r["wynik"] == "wygrany"),
            "roi_flat": round(roi, 2),
            "okazje_rozliczone": len(okazje),
            # CLV: dodatnie = braliśmy kursy lepsze niż zamknięcie rynku
            "clv_sr_pct": (
                round(sum(r["clv_pct"] for r in z_clv) / len(z_clv), 1)
                if z_clv else None
            ),
            "clv_n": len(z_clv),
        },
        "po_rynku": po_rynku,
        "ostatnie": ostatnie,
        # skuteczność dzień po dniu (realne typy) — do przełącznika w UI
        "skutecznosc_dzienna": skutecznosc_dzienna,
        "kupony": kupony_hist,
        "kupony_roi": kupony_roi,
        # WSZYSTKIE wygrane kupony (trwały log, nigdy nie znikają)
        "kupony_wygrane": kupony_wygrane,
    }
