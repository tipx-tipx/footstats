"""Kontekst meczu dla DRABINEK — rywal per rynek, sędzia, scenariusz meczu.

Drabinki liczyły dotąd wyłącznie z historii zawodnika („trafił 8/10"), a cały
kontekst sprowadzał się do jednego mnożnika ±8% z miejsca rywala w tabeli.
To za mało, żeby odpowiedzieć na pytanie, które zadaje każdy typujący: „gra
z najlepszą defensywą ligi — czemu miałby oddać 2 strzały?".

Ten moduł dokłada trzy warstwy, wszystkie w tej samej konwencji co
model/context.py (mnożnik ekspozycji, shrinkowany do 1.0 przy małej próbie
i capowany, żeby kontekst korygował, a nie rządził):

1. RYWAL per rynek — ile przeciwnik DOPUSZCZA na danym rynku vs średnia ligi.
   Źródło główne: `opponent_average`/`league_average` z feedu statshub (pełny
   sezon, cała tabela). Fallback: własna tabela koncesji z historii trendów,
   kluczowana po id drużyny — działa też tam, gdzie feedu propsów nie ma
   (Ekstraklasa i reszta ścieżki `performance`).

   Kierunek wychodzi sam z semantyki rynku, bo agregujemy zawsze to samo:
   „co zawodnicy notowali PRZECIW tej drużynie". Dla strzałów to hojność
   defensywy, dla fauli popełnionych — jak bardzo ta drużyna jest faulowana,
   dla fauli wywalczonych — jak bardzo sama fauluje, dla odbiorów — ile pracy
   defensywnej wymusza u rywali.

2. SĘDZIA — tylko rynki faulowe/kartkowe. Profil arbitra liczy już
   build_wc_fast.profil_sedziow (faule meczu vs oczekiwane dla tej pary
   drużyn); tutaj go tylko konsumujemy. Brak obsady = neutralnie 1.0 wraz
   z notatką dla UI, nie kara (decyzja usera 2026-07-26).

3. SCENARIUSZ MECZU — z kursów 1X2/total Superbetu przez model/tempo.py:
   otwarty mecz = więcej strzałów, wyraźny faworyt = underdog broni się
   głęboko (więcej odbiorów u niego, więcej strzałów u faworyta).

PUŁAPKA ZMIERZONA 2026-07-26 (sonda na żywym feedzie Nashville–Orlando):
`opponent_rank` rośnie WRAZ z dopuszczaną wartością — rank 1 to drużyna
NAJSZCZELNIEJSZA, nie najhojniejsza (shots: opp=10.38 przy średniej ligi
12.89 i rank 4/30; fouls: opp=1.44 przy średniej 2.18 i rank 1/30). Stary
`radar._mnoznik_rywala` czytał to odwrotnie i premiował typy przeciw
najlepszym defensywom. Dlatego liczymy ze STOSUNKU średnich (bezwymiarowy,
odporny na to, czy statshub podaje wartość drużynową czy na zawodnika),
a rank służy już tylko do opisu w UI.
"""

from __future__ import annotations

import math
import time
from collections import Counter, defaultdict

from . import context
from .koncesje import kubelek_pozycji

# --- rodziny rynków (semantyka kierunku i tego, co w ogóle koryguje sędzia) ---
RYNKI_DYSCYPLINARNE = frozenset({"fouls_committed", "fouls_won", "yellow_card"})

# Rynki bez własnych koncesji (nikt nie liczy „ile drużyna dopuszcza strzałów
# głową") dziedziczą kontekst po rynku-rodzicu. To przybliżenie, nie pomiar —
# stąd osobny, węższy cap w `mnoznik_rywala`.
RYNEK_RODZIC = {
    "shots_outside_box": "shots",
    "sot_outside_box": "sot",
    "headed_shots": "shots",
    "headed_sot": "sot",
    "shots_off_target": "shots",
    "shots_blocked": "shots",
    "interceptions": "tackles",
    "offsides": "shots",       # spalone łapie wysoką linię rywala tylko z grubsza
}
# ile ważą rynki dziedziczone: 1.0 = pełny mnożnik rodzica, 0.5 = połowa siły
WAGA_RYNKU_DZIEDZICZONEGO = 0.5

# Efektywna próba przypisywana agregatom statshuba. Feed liczy z całego sezonu
# (rank 1..30 = pełna tabela ligi), więc próba jest realnie duża — ale nie znamy
# jej dokładnie, stąd wartość zachowawcza zamiast „ufamy w 100%".
N_STATSHUB = 20

# Sanity na agregat statshuba: stosunek poza tym zakresem znaczy NIESPÓJNE
# JEDNOSTKI w feedzie, a nie ekstremalnie hojną defensywę. Zmierzone
# 2026-07-26 na żywym cyklu: Boca Juniors miało `opponentAverage=172,0`
# przy `leagueAverage=25,18` na strzałach (suma sezonu vs średnia na mecz)
# — surowy stosunek 6,8 wchodził prosto w górny cap i dawał karcie fałszywy
# bonus. Wszystkie pozostałe rekordy cyklu mieściły się w 0,89–1,26.
# Odrzucony agregat spada do koncesji z historii, a nie do neutralności.
STATSHUB_SENSOWNY_STOSUNEK = (0.4, 2.5)

# Historia klubowa: obserwacja sprzed 6 tygodni waży ~37% świeżej. Krócej niż
# counts.DEFAULT_TAU_DAYS (180, cały sezon), dłużej niż koncesje.py (14, okno
# turnieju) — profil drużyny w lidze zmienia się przez transfery i zmianę
# trenera, ale nie z tygodnia na tydzień.
KONCESJA_TAU_DNI = 45.0

MIN_MINUT_OBSERWACJI = 20.0   # krótsze wejście nic nie mówi o rywalu
MIN_OBS_NORMY = 15            # tyle obserwacji, żeby norma rynku miała sens
MIN_MINUT_PROFILU = 120.0     # łącznie minut przeciw drużynie (~1.5 meczu)


def _waga_swiezosci(ts: float, teraz: float) -> float:
    return math.exp(-max(teraz - ts, 0.0) / 86400.0 / KONCESJA_TAU_DNI)


class KoncesjeDruzyn:
    """Ile zawodnicy notują PRZECIW danej drużynie, per rynek i formacja.

    Klucz to id drużyny (nie nazwa) — id statshub/Sofascore są spójne między
    ścieżkami danych, a nazwy klubów wymagają normalizacji i i tak się mylą.
    Norma liczona w obrębie ROZGRYWEK (utid), bo bank miesza ligi o zupełnie
    różnym poziomie faulowania; globalna norma tylko jako ostatnia deska.
    """

    def __init__(self) -> None:
        # (team_id, rynek, kubełek) -> [(licznik, minuty, ts, utid)]
        self._obs: dict[tuple, list] = defaultdict(list)
        # (utid, rynek, kubełek) -> [(licznik, minuty)]
        self._norma: dict[tuple, list] = defaultdict(list)
        # (rynek, kubełek) -> [(licznik, minuty)]
        self._norma_globalna: dict[tuple, list] = defaultdict(list)

    def dodaj(
        self, opp_id: int, rynek: str, pozycja: str | None,
        licznik: float, minuty: float, ts: float, utid: int,
    ) -> None:
        kub = kubelek_pozycji(pozycja)
        if not kub or minuty < MIN_MINUT_OBSERWACJI or not opp_id:
            return
        self._obs[(int(opp_id), rynek, kub)].append(
            (float(licznik), float(minuty), float(ts), int(utid or 0))
        )
        if utid:
            self._norma[(int(utid), rynek, kub)].append(
                (float(licznik), float(minuty))
            )
        self._norma_globalna[(rynek, kub)].append(
            (float(licznik), float(minuty))
        )

    def _per90(self, probki: list[tuple]) -> float | None:
        minuty = sum(m for _c, m, *_ in probki)
        if minuty <= 0:
            return None
        return sum(c for c, _m, *_ in probki) / minuty * 90.0

    def lookup(
        self, opp_id: int, rynek: str, pozycja: str | None,
        teraz: float | None = None,
    ) -> tuple[float, float, int] | None:
        """(dopuszczane_per90, norma_per90, liczba_meczów) albo None.

        Obserwacje ważone świeżością; norma z rozgrywek, w których te
        obserwacje faktycznie padły.
        """
        kub = kubelek_pozycji(pozycja)
        if not kub or not opp_id:
            return None
        obs = self._obs.get((int(opp_id), rynek, kub))
        if not obs:
            return None
        teraz_ts = teraz if teraz is not None else time.time()
        wagi = [_waga_swiezosci(ts, teraz_ts) for _c, _m, ts, _u in obs]
        minuty_w = sum(w * m for w, (_c, m, _t, _u) in zip(wagi, obs))
        if minuty_w < MIN_MINUT_PROFILU:
            return None
        allowed = sum(
            w * c for w, (c, _m, _t, _u) in zip(wagi, obs)
        ) / minuty_w * 90.0
        # norma z dominujących rozgrywek tych obserwacji; globalna awaryjnie
        utidy = Counter(u for _c, _m, _t, u in obs if u)
        norma_probki: list[tuple] = []
        if utidy:
            norma_probki = self._norma.get(
                (utidy.most_common(1)[0][0], rynek, kub), []
            )
        if len(norma_probki) < MIN_OBS_NORMY:
            norma_probki = self._norma_globalna.get((rynek, kub), [])
        if len(norma_probki) < MIN_OBS_NORMY:
            return None
        norma = self._per90(norma_probki)
        if not norma or norma <= 0:
            return None
        # próba w MECZACH, nie w obserwacjach: kilku zawodników z tej samej
        # formacji w jednym meczu to jeden mecz (inaczej shrink by nie działał)
        n_meczy = len({round(ts / 43200.0) for _c, _m, ts, _u in obs})
        return allowed, norma, n_meczy


def zbuduj_koncesje(trendy_per_gracz: dict, teraz: float | None = None) -> KoncesjeDruzyn:
    """Tabela koncesji z historii trendów.

    `trendy_per_gracz`: {(event_id, player_id): {rynek: StatshubTrend}} —
    ten sam indeks, który radar buduje sobie i tak. Wymaga DEDUPLIKACJI po
    (gracz, rynek): feed propsów zwraca osobny rekord na każdą LINIĘ, więc
    surowa lista trendów policzyłaby tę samą historię po kilka razy i zawyżyła
    próbę (a przez nią siłę shrinkage).
    """
    k = KoncesjeDruzyn()
    widziani: set[tuple[int, str]] = set()
    for slot in trendy_per_gracz.values():
        for rynek, tr in slot.items():
            klucz = (int(tr.player_id or 0), rynek)
            if klucz in widziani:
                continue
            widziani.add(klucz)
            n = min(
                len(tr.counts), len(tr.minutes), len(tr.timestamps),
                len(tr.game_opponent_ids),
            )
            for i in range(n):
                poz = (
                    tr.game_positions[i]
                    if i < len(tr.game_positions) and tr.game_positions[i]
                    else tr.position
                )
                k.dodaj(
                    opp_id=tr.game_opponent_ids[i],
                    rynek=rynek,
                    pozycja=poz,
                    licznik=tr.counts[i],
                    minuty=tr.minutes[i],
                    ts=tr.timestamps[i],
                    utid=tr.game_utids[i] if i < len(tr.game_utids) else 0,
                )
    return k


def mnoznik_rywala(
    rynek: str,
    trend,
    koncesje: KoncesjeDruzyn | None = None,
    opp_id: int | None = None,
    pozycja: str | None = None,
    teraz: float | None = None,
    koncesje_nazw=None,
    nazwa_rywala: str | None = None,
    nazwa_druzyny: str | None = None,
) -> tuple[float, dict]:
    """Ile rywal dopuszcza na tym rynku vs norma — (mnożnik, opis dla UI).

    Kolejność źródeł: agregat statshuba (pełny sezon) → własna tabela koncesji
    po id → tabela modelu po NAZWIE drużyny (`model/koncesje.py`, budowana
    z banku trendów wzbogaconego o 365Scores — jedyne źródło dla lig spoza
    feedu propsów, m.in. Ekstraklasy) → rynek-rodzic z połową siły →
    neutralnie.
    """
    opis: dict = {"rynek": rynek}

    # 1. agregat statshuba: stosunek średnich, NIE rank (patrz docstring modułu)
    srednia = getattr(trend, "opponent_average", None) if trend else None
    liga = getattr(trend, "league_average", None) if trend else None
    if srednia is not None and liga:
        surowy = float(srednia) / float(liga)
        if STATSHUB_SENSOWNY_STOSUNEK[0] <= surowy <= STATSHUB_SENSOWNY_STOSUNEK[1]:
            m = context.cap(
                context.shrink_factor(surowy, N_STATSHUB, prior_strength=10.0),
                context.CAP_OPPONENT,
            )
            opis.update({
                "zrodlo": "statshub", "srednia": round(float(srednia), 2),
                "norma": round(float(liga), 2), "surowy": round(surowy, 3),
                "rank": getattr(trend, "opponent_rank", None),
                "z": getattr(trend, "total_ranks", None),
                "mnoznik": round(m, 3),
            })
            return m, opis
        opis["odrzucony_agregat"] = round(surowy, 2)   # niespójne jednostki

    # 2. własna tabela koncesji (działa też poza feedem propsów)
    for kod, waga in ((rynek, 1.0),
                      (RYNEK_RODZIC.get(rynek), WAGA_RYNKU_DZIEDZICZONEGO)):
        if not kod or koncesje is None or not opp_id:
            continue
        trafienie = koncesje.lookup(opp_id, kod, pozycja, teraz=teraz)
        if trafienie is None:
            continue
        allowed, norma, n_meczy = trafienie
        surowy = allowed / norma
        # rynek dziedziczony: bierzemy tylko część odchylenia od neutralności
        surowy = 1.0 + waga * (surowy - 1.0)
        m = context.cap(
            context.shrink_factor(surowy, n_meczy, prior_strength=6.0),
            context.CAP_OPPONENT,
        )
        opis.update({
            "zrodlo": "historia" if waga == 1.0 else "historia_pokrewny",
            "rynek_zrodlowy": kod,
            "srednia": round(allowed, 2), "norma": round(norma, 2),
            "surowy": round(surowy, 3), "mecze": n_meczy,
            "mnoznik": round(m, 3),
        })
        return m, opis

    # 3. tabela koncesji MODELU po nazwie drużyny — jedyne źródło kontekstu
    # dla lig spoza feedu propsów (Ekstraklasa), bo bank trendów jest tam
    # dopełniany z 365Scores. Bez tego karty polskiej ligi szły z rywalem 1.0.
    if koncesje_nazw is not None and nazwa_rywala:
        for kod, waga in ((rynek, 1.0),
                          (RYNEK_RODZIC.get(rynek), WAGA_RYNKU_DZIEDZICZONEGO)):
            if not kod:
                continue
            try:
                trafienie = koncesje_nazw.lookup(
                    nazwa_rywala, kod, pozycja,
                    team_name=nazwa_druzyny, now=teraz,
                )
            except Exception:
                trafienie = None
            if trafienie is None:
                continue
            allowed, norma, n_meczy = trafienie
            if norma <= 0:
                continue
            surowy = 1.0 + waga * (allowed / norma - 1.0)
            m = context.cap(
                context.shrink_factor(surowy, n_meczy, prior_strength=6.0),
                context.CAP_OPPONENT,
            )
            opis.update({
                "zrodlo": "bank" if waga == 1.0 else "bank_pokrewny",
                "rynek_zrodlowy": kod,
                "srednia": round(allowed, 2), "norma": round(norma, 2),
                "surowy": round(surowy, 3), "mecze": n_meczy,
                "mnoznik": round(m, 3),
            })
            return m, opis

    opis.update({"zrodlo": "brak", "mnoznik": 1.0})
    return 1.0, opis


def mnoznik_sedziego(rynek: str, sedzia: dict | None) -> tuple[float, dict]:
    """Mnożnik arbitra dla rynków faulowych — (mnożnik, opis dla UI).

    `sedzia` = wpis z build_wc_fast.profil_sedziow: {sedzia, mnoznik, n}.
    Brak obsady albo rynek niedyscyplinarny = 1.0 (z notatką, żeby karta
    mogła uczciwie napisać „obsada nieznana" zamiast milczeć).
    """
    if rynek not in RYNKI_DYSCYPLINARNE:
        return 1.0, {}
    if not sedzia or not sedzia.get("sedzia"):
        return 1.0, {"zrodlo": "brak_obsady"}
    surowy = sedzia.get("mnoznik")
    n = int(sedzia.get("n") or 0)
    if not surowy:
        return 1.0, {"zrodlo": "brak_profilu", "sedzia": sedzia["sedzia"]}
    m = context.referee_factor(float(surowy), n, market_is_disciplinary=True)
    return m, {
        "zrodlo": "365", "sedzia": sedzia["sedzia"],
        "surowy": round(float(surowy), 3), "mecze": n,
        "mnoznik": round(m, 3),
    }


def mnoznik_scenariusza(
    rynek: str, tempo: dict | None, is_home: bool | None,
) -> tuple[float, dict]:
    """Scenariusz meczu z kursów 1X2/total — (mnożnik, opis dla UI).

    `tempo` = wynik model/tempo.tempo_from_match_odds. Spread jest liczony
    jako gole GOSPODARZ−GOŚĆ, więc dla zawodnika gościa trzeba go odwrócić,
    zanim trafi do context.game_script_factor.
    """
    if not tempo or is_home is None:
        return 1.0, {}
    spread = float(tempo.get("spread") or 0.0)
    total = tempo.get("total")
    spread_gracza = spread if is_home else -spread
    faworyt = spread_gracza > 0
    m = context.game_script_factor(
        implied_spread=spread_gracza,
        implied_total=float(total) if total else None,
        market_code=rynek,
        is_favourite=faworyt,
    )
    return m, {
        "spread": round(spread_gracza, 2),
        "total": round(float(total), 2) if total else None,
        "faworyt": faworyt,
        "mnoznik": round(m, 3),
    }


def mnoznik_domu(rynek: str, is_home: bool | None) -> tuple[float, dict]:
    """Efekt dom/wyjazd per rodzina rynków (context.home_away_factor)."""
    if is_home is None:
        return 1.0, {}
    m = context.home_away_factor(bool(is_home), rynek)
    return m, {"dom": bool(is_home), "mnoznik": round(m, 3)}
