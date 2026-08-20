"""Źródło danych: statshub.com — SZYBKA ŚCIEŻKA (otwarte API, bez limitów).

Odkrycie (2026-07-02): statshub jest zbudowany na tych samych ID co Sofascore,
ale jego API jest OTWARTE (nie dławi ruchu jak bezpośredni Sofascore) i zwraca
dane już zagregowane. Endpoint `/api/props/player-trends?games=...` daje dla
każdej pary (zawodnik, rynek, linia) w jednym zapytaniu:

  * recentGames — pełną historię mecz-po-meczu (statValue, minuty, rywal, u siebie),
  * leagueAverage / opponentAverage / opponentRank — gotowy kontekst rywala,
  * inPredictedLineup — przewidywany skład,
  * line + bookmakers — linie i kursy (bukmacherzy UK, orientacyjnie).

To zastępuje: backfill per-mecz z Sofascore, własne liczenie średnich rywala
i pobieranie składów — dla 5 rynków rdzeniowych.

OGRANICZENIA:
  * pokrywa tylko 5 rynków: strzały, celne, faule, odbiory, faule wywalczone
    (rynki z map strzałów — zza pola, głową, zablokowane, niecelne — dalej
    pochodzą z shotmap Sofascore),
  * propsy ładują się ~24-48 h przed meczem (wcześniej feed jest pusty).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from curl_cffi import requests

# geometria pola karnego współdzielona z Sofascore (te same współrzędne 0-100)
from .. import diagnostyka
from .sofascore import is_outside_box as sofa_is_outside_box

BASE = "https://www.statshub.com/api"
HEADERS = {"Accept": "application/json", "Referer": "https://www.statshub.com/"}

# statType statshub -> nasz kod rynku
STATTYPE_MAP = {
    "shots": "shots",
    "onTargetScoringAttempt": "sot",
    "fouls": "fouls_committed",
    "totalTackle": "tackles",
    "wasFouled": "fouls_won",
}


# Odstęp między ponowieniami (rośnie z próbą: 1× i 2×). Wyciągnięte do stałej
# 2026-08-17, żeby testy mogły wyzerować SAM CZAS, nie liczbę prób — dokładnie
# jak `supa.PRZERWY_S`. Bez tego zestaw płacił 9 s za każdy mecz, o którego
# status pytamy przez zaślepioną sieć (zapora z conftest rzuca wyjątkiem,
# a każdy wyjątek wygląda tu jak awaria źródła).
PAUZA_PONOWIENIA_S = 3
# ⚑⚑ ODCIĘCIE ZA NADMIAR ZAPYTAŃ TO NIE JEST „chwilowo wolny" (2026-08-20).
#
# Do dziś 429 leciał tą samą ścieżką co timeout i 5xx: pauza 3 s, potem 6 s,
# potem poddajemy się — a wtedy `_main_impl` łapie wyjątek i POMIJA CAŁY
# CYKL („statshub chwilowo niedostępny — dane bez zmian"). Czyli jedno
# odcięcie kosztuje komplet typów, drabinek i kuponów na godzinę.
#
# Źródło odblokowuje się po MINUTACH, nie sekundach, więc trzysekundowa pauza
# gwarantowała porażkę wszystkich trzech prób. Zmierzone tego dnia lokalnie
# po serii dry-runów: 429 i cykl pusty w 0,8 min.
#
# ⚑ To zabezpieczenie jest warunkiem podniesienia budżetów odkrywania
# (`MAX_WYSZUKAN_ODKRYC` 700 → 1400): większy budżet to większa szansa na
# odcięcie, więc najpierw musi istnieć droga wyjścia.
PAUZA_ODCIECIA_S = 25


def _get(url: str, timeout: int = 25, retries: int = 3) -> dict:
    """GET z retry — statshub bywa chwilowo wolny/niedostępny (zwłaszcza z chmury).

    Odcięcie (429/403) dostaje WŁASNY, dłuższy backoff i licznik — patrz nota
    przy `PAUZA_ODCIECIA_S`.
    """
    import time as _t

    last = None
    for attempt in range(retries):
        odciecie = False
        try:
            r = requests.get(url, impersonate="chrome124", timeout=timeout, headers=HEADERS)
            odciecie = getattr(r, "status_code", None) in (403, 429)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # timeout, 5xx, itp.
            last = e
            if odciecie:
                # licznik idzie do raportu cyklu — bez niego odcięcie widać
                # dopiero po tym, jak strona pół dnia pokazuje stare dane
                diagnostyka.cichy("statshub", "odciecie_429", e)
                _t.sleep(PAUZA_ODCIECIA_S * (attempt + 1))
            else:
                _t.sleep(PAUZA_PONOWIENIA_S * (attempt + 1))
    raise last


@dataclass
class StatshubTrend:
    """Jeden rekord trendu: (zawodnik, rynek, linia) z historią i kontekstem."""

    player_id: int
    player_name: str
    position: str | None
    team_id: int
    team_name: str
    opponent_id: int
    opponent_name: str
    is_home: bool
    market_code: str
    line: float
    in_predicted_lineup: bool
    league_average: float | None
    opponent_average: float | None
    opponent_rank: int | None
    total_ranks: int | None
    event_id: int = 0
    odds_type: str = "over"  # strona, której dotyczą line i ref_odds
    # historia: listy równoległe (od najnowszych)
    counts: list[float] = field(default_factory=list)
    minutes: list[float] = field(default_factory=list)
    timestamps: list[int] = field(default_factory=list)
    started: list[bool] = field(default_factory=list)
    # pozycje per mecz (RW, LB, RCB...) — pod matchup-lite stron boiska
    game_positions: list[str] = field(default_factory=list)
    # rywal per mecz — do formy w UI i ważenia próby siłą rywala
    game_opponents: list[str] = field(default_factory=list)
    # id rywala per mecz — radar: mecz PRZECIW obecnej drużynie w historii
    # = zawodnik grał wtedy gdzie indziej (transfer wewnątrz ligi)
    game_opponent_ids: list[int] = field(default_factory=list)
    # rozgrywki per mecz (uniqueTournamentId) — radar wykrywa z tego zmianę
    # ligi/klubu (historia podąża za ZAWODNIKIEM, nie klubem)
    game_utids: list[int] = field(default_factory=list)
    # ile meczów temu ostatni występ w OBECNEJ drużynie (activityInfo feedu;
    # None = feed nie podał). Semantyka niepewna (sonda 2026-07-22), radar
    # traktuje wyłącznie jako sygnał pomocniczy.
    last_game_with_team: int | None = None
    # kursy referencyjne bukmacherów UK dla linii `line` (Bet365, WH, ...)
    ref_odds: list[float] = field(default_factory=list)


def fetch_event_trends(event_ids: list[int]) -> list[StatshubTrend]:
    """Pobierz trendy propsów dla podanych meczów (Z PAGINACJĄ).

    PUŁAPKA zmierzona 2026-07-20: endpoint jest stronicowany z domyślnym
    pageSize=25 — bez iterowania po stronach feed jest CICHO ucinany do
    25 rekordów niezależnie od liczby meczów (a `limit=` jest ignorowany).
    Działa pageSize + page; bierzemy pageSize=100 i idziemy do wyczerpania.

    Zwraca pustą listę, jeśli propsy nie są jeszcze wystawione (za wcześnie).
    """
    if not event_ids:
        return []
    games = ",".join(str(e) for e in event_ids)
    data: list[dict] = []
    page = 1
    PAGE_SIZE = 100
    while True:
        czesc = _get(
            f"{BASE}/props/player-trends?games={games}"
            f"&pageSize={PAGE_SIZE}&page={page}"
        ).get("data", [])
        data += czesc
        # bezpiecznik 40 stron = 4000 rekordów; realnie kilkaset
        if len(czesc) < PAGE_SIZE or page >= 40:
            break
        page += 1
    out: list[StatshubTrend] = []
    for rec in data:
        mk = STATTYPE_MAP.get(rec.get("statType"))
        if mk is None:
            continue
        rg = rec.get("recentGames", [])
        # minutesPlayed>0 => zagrał; started przybliżamy przez minuty (>60 ~ start)
        out.append(
            StatshubTrend(
                player_id=rec["playerId"],
                player_name=rec["playerName"],
                position=(rec.get("position") or "M")[:1],
                team_id=rec.get("teamId"),
                team_name=rec.get("teamName", ""),
                opponent_id=rec.get("opponentTeamId"),
                opponent_name=rec.get("opponentTeamName", ""),
                is_home=rec.get("homeTeamId") == rec.get("teamId"),
                market_code=mk,
                line=float(rec.get("line", 0.5)),
                in_predicted_lineup=bool(rec.get("inPredictedLineup")),
                event_id=int(rec.get("eventId") or 0),
                odds_type=str(rec.get("oddsType") or "over"),
                league_average=rec.get("leagueAverage"),
                opponent_average=rec.get("opponentAverage"),
                opponent_rank=rec.get("opponentRank"),
                total_ranks=rec.get("totalRanks"),
                counts=[float(g.get("statValue") or 0) for g in rg],
                minutes=[float(g.get("minutesPlayed") or 0) for g in rg],
                timestamps=[int(g.get("eventTimestamp") or 0) for g in rg],
                started=[float(g.get("minutesPlayed") or 0) >= 60 for g in rg],
                game_positions=[str(g.get("position") or "") for g in rg],
                game_opponents=[str(g.get("opponentName") or "") for g in rg],
                game_opponent_ids=[int(g.get("opponentId") or 0) for g in rg],
                game_utids=[int(g.get("uniqueTournamentId") or 0) for g in rg],
                last_game_with_team=(rec.get("activityInfo") or {}).get(
                    "lastGameWithTeam"
                ),
                ref_odds=[
                    float(b["oddsValue"])
                    for b in rec.get("bookmakers", [])
                    if b.get("oddsValue")
                ],
            )
        )
    return out


# pole statystyk meczowych z /player/{id}/performance -> nasz kod rynku.
# TO JEST ŚCIEŻKA DLA LIG SPOZA FEEDU PROPSÓW (Ekstraklasa, część Europy):
# player-trends istnieje tylko tam, gdzie bukmacherzy UK wystawili linie,
# a performance działa dla KAŻDEGO gracza (odkryte 2026-07-25).
PERF_STATTYPE_MAP = {
    "shots": "shots",
    "onTargetScoringAttempt": "sot",
    "fouls": "fouls_committed",
    "wasFouled": "fouls_won",
    "totalTackle": "tackles",
    "interceptionWon": "interceptions",
    "totalOffside": "offsides",
    "shotOffTarget": "shots_off_target",
    "blockedScoringAttempt": "shots_blocked",
    # ŻÓŁTA KARTKA (dołożona 2026-08-03). Pole `yellowCard` siedziało
    # w performance od zawsze, tylko nikt go nie mapował — a to JEDYNA nasza
    # statystyka, którą Superbet kwotuje na kwalifikacjach pucharów (strzałów
    # i fauli tam nie wystawia). Bez tej linijki zakładka meczu zostawała
    # pusta mimo 66 kwotowanych zawodników na Sparcie Praga – Lyonie.
    #
    # UWAGA: ta historia służy POKRYCIU (co zawodnik realnie zbierał).
    # Wycena kartki idzie osobną drogą — przez faule, patrz model/cards.py.
    "yellowCard": "yellow_card",
}

# Pola, w których BRAK WPISU znaczy „zero", a nie „nie zmierzono".
#
# Statshub wysyła `yellowCard` TYLKO w meczach, w których kartka padła —
# w pozostałych pola nie ma w ogóle. Pomijanie takiego meczu (domyślne
# zachowanie, słuszne dla statystyk mierzonych zawsze) dawało historię
# złożoną z samych meczów z kartką: zmierzone na Palavecino 03.08 — 1 mecz
# w historii kartek wobec 10 w faulach, czyli pokrycie 1/1 = „100% meczów
# z kartką". To nie jest brak danych, tylko ich odwrotność.
#
# Warunek `minuty > 0` jest tu istotny: zero dopisujemy WYŁĄCZNIE zawodnikowi,
# który wyszedł na boisko. Mecz przesiedziany na ławce nie jest dowodem, że
# kartki nie zbiera.
PERF_BRAK_ZNACZY_ZERO = frozenset({"yellowCard"})


# rynki, których performance NIE rozbija, a shotmapa pozwala policzyć.
#
# UWAGA (zmierzone 2026-07-25): flaga `isOutsideBox` ze statshuba jest
# BEZUŻYTECZNA — w sondzie miała wartość True dla 35 z 35 strzałów meczu,
# czyli po prostu zawsze. Branie jej wprost robiło z "zza pola" kopię
# wszystkich strzałów, a że kursy na ten rynek są wyższe (rzadsze zdarzenie),
# generowało to FAŁSZYWĄ przewagę i wynosiło takie karty na szczyt.
# Dlatego liczymy z GEOMETRII (x, y w skali 0-100, jak w Sofascore).
# Flagi `isHeaded` i `isOnTarget` są sprawdzone i wiarygodne (zgadzają się
# odpowiednio z bodyPart='head' i z result goal/save).
def _poza_polem(s: dict) -> bool:
    """Strzał spoza pola karnego — z geometrii, bo flaga API kłamie.

    x/y przychodzą ze statshuba jako STRINGI, stąd konwersja."""
    try:
        return bool(sofa_is_outside_box(float(s.get("x")), float(s.get("y"))))
    except (TypeError, ValueError):
        return False


def _celny(s: dict) -> bool:
    return bool(s.get("isOnTarget"))


def _glowa(s: dict) -> bool:
    return bool(s.get("isHeaded")) or str(s.get("bodyPart") or "") == "head"


SHOTMAP_DERIVED = {
    "shots_outside_box": _poza_polem,
    "sot_outside_box": lambda s: _poza_polem(s) and _celny(s),
    "headed_shots": _glowa,
    "headed_sot": lambda s: _glowa(s) and _celny(s),
}


def _pierwszy(v):
    """Pole bywa dictem albo jednoelementową listą — bierz rekord."""
    if isinstance(v, list):
        return v[0] if v else {}
    return v or {}


# Ile meczów historii bierzemy z performance. BEZ PARAMETRU API ODDAJE 10 —
# i przez to była to najkrótsza historia w całym systemie (odkryte 2026-08-03).
#
# Dlaczego to bolało: gracz odkryty z oferty bukmachera nie ma nic poza tą
# ścieżką, a brama drabinek wymaga OŚMIU ROZEGRANYCH występów w oknie. Dziesięć
# rekordów to często pięć-sześć z minutami (reszta to ławka), więc karta
# odpadała na „krótkiej próbie" — 138 ze 189 odrzuconych kandydatów w przebiegu
# 03.08, przy dwóch przepuszczonych.
#
# 40 zamiast 10 sięga mniej więcej sezon wstecz. Głębiej NIE schodzimy domyślnie
# (choć API pozwala — limit=100 sięga 2022 roku): mecz sprzed dwóch lat nie jest
# dowodem o dzisiejszej formie, a model i tak wygasza próbę czasowo i ma bramę
# świeżości. Parametr zostaje jawny, żeby liczenie ŚREDNICH SEZONOWYCH mogło
# poprosić o więcej, nie ruszając ścieżki typów.
PERF_LIMIT = 40


def fetch_player_performance(player_id: int, limit: int = PERF_LIMIT) -> list[dict]:
    """Ostatnie mecze gracza ze statystykami — DZIAŁA W KAŻDEJ LIDZE.

    Zwraca surowe rekordy {player_statistics_event, events, homeTeam,
    awayTeam}. Statystyki obejmują komplet rynków propsowych: strzały,
    celne, niecelne, zablokowane, faule popełnione i wywalczone, odbiory,
    przechwyty, SPALONE, minuty, pozycję, rating i kartki.
    """
    d = _get(f"{BASE}/player/{player_id}/performance?limit={int(limit)}",
             timeout=25, retries=2)
    rows = d.get("data", d)
    return rows if isinstance(rows, list) else []


def trendy_z_performance(
    player_id: int,
    player_name: str,
    team_id: int | None,
    rows: list[dict],
    sm_cache: dict | None = None,
    budzet: list[int] | None = None,
) -> dict[str, StatshubTrend]:
    """Rekordy z `fetch_player_performance` -> trendy per rynek.

    Ten sam kształt co `fetch_event_trends`, więc konsumenci (radar,
    rozliczanie) nie muszą wiedzieć, z której ścieżki przyszła historia.
    Bez `line`/`ref_odds` (to nie feed propsów — linie bierzemy z kursów
    Superbetu) i bez kontekstu rywala (`opponent_average` = None).

    `sm_cache` (event_id -> shotmapa) dokłada rynki pochodne z shotmap:
    zza pola, celne zza pola, głową, celne głową. Cache jest WSPÓLNY dla
    graczy tej samej drużyny (mają tę samą historię meczów), więc koszt to
    ~10 zapytań na drużynę, nie na gracza. `budzet` = jednoelementowa lista
    z licznikiem zapytań na cykl (None = bez limitu).
    """
    zebrane: dict[str, list[tuple]] = {}
    meta: dict[str, str] = {}
    for rec in rows:
        ps = _pierwszy(rec.get("player_statistics_event"))
        ev = _pierwszy(rec.get("events"))
        if not ps or not ev:
            continue
        ts = int(ev.get("timeStartTimestamp") or 0)
        minuty = float(ps.get("minutesPlayed") or 0)
        tid = ps.get("teamId")
        # rywal = drużyna przeciwna wobec drużyny gracza W TAMTYM meczu
        home, away = _pierwszy(rec.get("homeTeam")), _pierwszy(rec.get("awayTeam"))
        if tid and ev.get("homeTeamId") == tid:
            rywal, rywal_id = away.get("name") or "", ev.get("awayTeamId") or 0
        else:
            rywal, rywal_id = home.get("name") or "", ev.get("homeTeamId") or 0
        meta.setdefault("team_name", (
            home.get("name") if tid and ev.get("homeTeamId") == tid
            else away.get("name")
        ) or "")
        utid = int(ev.get("uniqueTournamentId") or 0)
        poz = str(ps.get("position") or "")
        for pole, mk in PERF_STATTYPE_MAP.items():
            v = ps.get(pole)
            if v is None:
                if pole not in PERF_BRAK_ZNACZY_ZERO or minuty <= 0:
                    continue
                v = 0            # zagrał i nie dostał — to jest zero, nie luka
            zebrane.setdefault(mk, []).append(
                (ts, float(v), minuty, rywal, int(rywal_id or 0), utid, poz)
            )
        # rynki pochodne ze shotmapy (zza pola / głową) — tylko gdy mecz
        # w ogóle miał shotmapę; brak = pomijamy mecz w tych rynkach,
        # zamiast liczyć fałszywe zero
        if sm_cache is None or not ev.get("id"):
            continue
        eid = int(ev["id"])
        if eid not in sm_cache:
            if budzet is not None and budzet[0] <= 0:
                continue
            try:
                sm_cache[eid] = fetch_event_shotmap(eid)
            except Exception as e:
                # brak shotmapy = zawodnik traci rozbicie strzałów (głową,
                # zza pola, celne) — cicho wypadał z tych rynków
                diagnostyka.cichy("statshub", "shotmap_meczu", e)
                sm_cache[eid] = []
            if budzet is not None:
                budzet[0] -= 1
        sm = sm_cache.get(eid) or []
        if not sm:
            continue
        moje = [s for s in sm if s.get("playerId") == player_id]
        for mk, pasuje in SHOTMAP_DERIVED.items():
            zebrane.setdefault(mk, []).append((
                ts, float(sum(1 for s in moje if pasuje(s))),
                minuty, rywal, int(rywal_id or 0), utid, poz,
            ))
    out: dict[str, StatshubTrend] = {}
    for mk, lista in zebrane.items():
        lista.sort(key=lambda x: -x[0])  # od najnowszego, jak w feedzie
        out[mk] = StatshubTrend(
            player_id=int(player_id),
            player_name=player_name,
            position=(lista[0][6] or "M")[:1] if lista else "M",
            team_id=int(team_id or 0),
            team_name=meta.get("team_name", ""),
            opponent_id=0,
            opponent_name="",
            is_home=False,
            market_code=mk,
            line=0.5,
            in_predicted_lineup=False,
            league_average=None,
            opponent_average=None,
            opponent_rank=None,
            total_ranks=None,
            counts=[x[1] for x in lista],
            minutes=[x[2] for x in lista],
            timestamps=[x[0] for x in lista],
            started=[x[2] >= 60 for x in lista],
            game_positions=[x[6] for x in lista],
            game_opponents=[x[3] for x in lista],
            game_opponent_ids=[x[4] for x in lista],
            game_utids=[x[5] for x in lista],
        )
    return out


def fetch_predicted_lineup(event_id: int) -> dict:
    """Przewidywane XI OBU drużyn: {'home': [pid...], 'away': [...], 'confirmed': bool}.

    Endpoint NIEUDOKUMENTOWANY (podejrzany w XHR strony fixture 2026-07-20):
    pełne 11/11 już ~36 h przed meczem dla lig z pokryciem propsów
    (Brasileirão tak; egzotyka typu Finlandia/Bułgaria bywa pusta do końca).
    Dużo pewniejsze niż migotliwa flaga inPredictedLineup w player-trends.
    """
    d = _get(f"{BASE}/event/{event_id}/predicted-teams-lineup")
    d = d.get("data", d) or {}
    out: dict = {"home": [], "away": [], "confirmed": False}
    for side, key in (("home", "homeTeam"), ("away", "awayTeam")):
        for p in ((d.get(key) or {}).get("data")) or []:
            pid = p.get("playerId")
            if pid:
                out[side].append(int(pid))
            if str(p.get("predictionType") or "") == "confirmed":
                out["confirmed"] = True
    return out


def fetch_team_lineup(event_id: int, team_id: int) -> list[int]:
    """Oficjalny skład drużyny w meczu (XI bez ławki); [] przed ogłoszeniem.

    Ten sam nieudokumentowany zestaw co predicted-teams-lineup; para z flagą
    event.lineupConfirmed. eventId = events.id (NIE internalId).
    """
    d = _get(f"{BASE}/event/{event_id}/team-lineup?teamId={team_id}&heatmap=false")
    data = d.get("data", d)
    if not isinstance(data, list):
        return []
    return [
        int(p["playerId"]) for p in data
        if p.get("playerId") and p.get("isSubstitute") is not True
    ]


def props_available(event_id: int) -> bool:
    """Czy statshub ma już wystawione propsy dla meczu (feed niepusty)."""
    try:
        return len(fetch_event_trends([event_id])) > 0
    except Exception as e:
        # „brak propsów" i „nie udało się sprawdzić" wyglądały tak samo —
        # a to różnica między „bukmacher nie wystawił" a „nasz błąd"
        diagnostyka.cichy("statshub", "sprawdzenie_propsow", e)
        return False


# statType team-trends -> nasz kod rynku DRUŻYNOWEGO. UWAGA na nazwy statshub:
# "totalShotsOnGoal" to strzały OGÓŁEM (statDisplay "Shots"), "shotsOnGoal" —
# celne. Fauli drużynowych team-trends nie wystawia (historia z banku stylu).
# Sonda klubowa 2026-07-20: dla klubów feed niesie głównie "goals" (673/750
# rekordów) i "cornerKicks" (75) — a Superbet kwotuje czysto właśnie gole,
# rożne i kartki drużynowe, więc mapujemy i te.
TEAM_STATTYPE_MAP = {
    "totalShotsOnGoal": "team_shots",
    "shotsOnGoal": "team_sot",
    "cards": "team_cards",
    "goals": "team_goals",
    "cornerKicks": "team_corners",
}


# Pola `/team/{id}/performance` -> nasze kody rynków. Gole NIE są statystyką
# w tym feedzie — siedzą w `event.score`, więc dokładamy je osobno.
TEAM_PERF_MAP = {
    "totalShotsOnGoal": "team_shots",
    "shotsOnGoal": "team_sot",
    "cards": "team_cards",
    "cornerKicks": "team_corners",
    "fouls": "team_fouls",
}

# Ile meczów historii bierzemy dla DRUŻYNY. Bez parametru API oddaje 10 —
# ta sama pułapka co przy zawodnikach (patrz PERF_LIMIT).
#
# ⚑⚑ NIE PODNOSIĆ DO 80. SPRAWDZONE 19.08 I ZAMKNIĘTE — oba kryteria odbioru
# wypadły nie „trochę poniżej progu", tylko o rzędy wielkości.
#
# Hipoteza brzmiała: mamy ~1 sezon, więc model nie odróżnia „taka jest zawsze"
# od „jest w formie"; drugi sezon dałby bazę odniesienia. Zmierzone NAJPIERW
# na danych, które już mamy — magazyn trzyma 40 meczów na drużynę (89% drużyn
# ma 40-41), a najdłuższe okno modelu to `w12`, więc połowa historii i tak
# leżała nieużywana. Dewiancja OOS na 63 766 wierszach, split czasowy:
#
#     dziś (w6, w12, trend)          1,4033
#     + baza 24 mecze                1,4022   -0,07%
#     + baza 40 meczów               1,4043   +0,08%   (gorzej)
#     + 40 + trend sezonowy          1,4043   +0,08%
#
# Próg odbioru wynosił -2,0%. KONTROLA NEGATYWNA mówi, że pomiar nie jest
# ślepy: sama stała +11,80%, bez `opp12` +1,89%, bez `liga` +0,24%.
#
# Drugie kryterium („wraca >= 200 kandydatów odrzucanych na wieku historii")
# jest STRUKTURALNIE nieosiągalne, nie tylko niespełnione: brama bierze
# 20 najnowszych meczów i odcina starsze niż 548 dni, a feed oddaje najnowsze
# — więc mecz nr 41+ jest ZE STARSZEJ części osi i tym bardziej odpada.
# Policzone: z 1299 drużyn 54 pada na tej bramie, ratowalnych głębszym
# pobraniem 0.
#
# ⚑ PRZY OKAZJI, WAŻNIEJSZE NIŻ SAM WERDYKT: własna forma drużyny prawie nic
# nie wnosi (bez `w6` dewiancja rośnie o 0,00%), a najwięcej wnosi PROFIL
# RYWALA (`opp12`, +1,89%). Jeśli szukać rezerwy w cechach, to po stronie
# rywala i kontekstu meczu, nie w głębszej historii własnej.
TEAM_PERF_LIMIT = 40


def fetch_team_performance(team_id: int, limit: int = TEAM_PERF_LIMIT) -> list[dict]:
    """Historia meczowa DRUŻYNY — niezależna od tego, czy ktokolwiek ją kwotował.

    ODKRYTE 2026-08-04, gdy Sparta Praga – Lyon nie dała ani jednego typu mimo
    kompletu kursów. Historię drużyn braliśmy WYŁĄCZNIE z `/props/team-trends`,
    a ten feed jest lustrem ofert bukmacherów UK — w przerwie letniej ligi
    czeskiej i francuskiej stoi pusty. Zmierzone tego dnia: model widział dla
    Sparty ZERO meczów w oknie czterech miesięcy i odrzucał ją jako
    `za_stara_historia`, podczas gdy ten endpoint ma dla niej dziewięć
    (a dla Lyonu sześć).

    Zwraca surowe rekordy {event, statistics, opponentStatistics, homeTeam,
    awayTeam, league}. `statistics` niesie komplet: kartki, rożne, faule,
    strzały, celne, spalone, odbiory, xG. `opponentStatistics` to te same pola
    po stronie RYWALA w tamtym meczu — czyli koncesje zmierzone, a nie
    przybliżane. `league` mówi, z jakich rozgrywek jest każdy mecz historii.
    """
    try:
        d = _get(f"{BASE}/team/{int(team_id)}/performance?limit={int(limit)}",
                 timeout=25, retries=2)
    except Exception as e:
        # CICHY UBYTEK HISTORII DRUŻYNY — bez licznika wyglądał identycznie jak
        # „ta drużyna nie ma historii" i wypadała z typów bez śladu
        diagnostyka.cichy("statshub", "historia_druzyny", e)
        return []
    rows = d.get("data", d)
    return rows if isinstance(rows, list) else []


def historia_druzyny(team_id: int, rows: list[dict]) -> dict[str, tuple]:
    """Rekordy z `fetch_team_performance` -> {kod_rynku: (counts, timestamps,
    rywale, rywale_id, czy_u_siebie)}.

    Kształt celowo „surowy", a nie gotowy TeamTrend: trend niesie też kontekst
    NADCHODZĄCEGO meczu (linia, rywal, event_id), którego historia nie zna.
    Składa go konsument — tak samo jak przy trendach z banku stylu.
    """
    out: dict[str, list] = {}
    for rec in rows:
        ev = rec.get("event") or {}
        st = rec.get("statistics") or {}
        try:
            ts = int(ev.get("timeStartTimestamp") or 0)
        except (TypeError, ValueError):
            ts = 0
        if not ts:
            continue
        home, away = rec.get("homeTeam") or {}, rec.get("awayTeam") or {}
        u_siebie = int(home.get("id") or 0) == int(team_id)
        rywal = (away if u_siebie else home) or {}
        pary = dict(TEAM_PERF_MAP)
        for pole, mk in pary.items():
            v = st.get(pole)
            if v is None:
                continue
            out.setdefault(mk, []).append(
                (ts, float(v), str(rywal.get("name") or ""),
                 int(rywal.get("id") or 0), u_siebie)
            )
        # GOLE: nie ma ich w `statistics`, są w wyniku meczu
        wynik = ev.get("score") or {}
        gole = wynik.get("home" if u_siebie else "away")
        if gole is not None:
            out.setdefault("team_goals", []).append(
                (ts, float(gole), str(rywal.get("name") or ""),
                 int(rywal.get("id") or 0), u_siebie)
            )
    gotowe: dict[str, tuple] = {}
    for mk, pary in out.items():
        pary.sort(key=lambda x: -x[0])
        gotowe[mk] = (
            [c for _, c, _, _, _ in pary],
            [t for t, _, _, _, _ in pary],
            [o for _, _, o, _, _ in pary],
            [i for _, _, _, i, _ in pary],
            [h for _, _, _, _, h in pary],
        )
    return gotowe


def koncesje_druzyny(team_id: int, rows: list[dict]) -> dict[str, tuple]:
    """Ile ta drużyna DOPUSZCZA — z `opponentStatistics`, mecz po meczu.

    Bliźniak `historia_druzyny`, tylko z drugiej strony boiska: tam czytamy, co
    drużyna notowała, tu — co notowali przeciwko niej jej rywale. Feed niesie
    oba komplety w KAŻDYM rekordzie historii, więc to nie kosztuje ani jednego
    dodatkowego zapytania.

    PO CO (2026-08-07). Czynnik rywala miał dotąd dwa źródła: bank stylu
    (365Scores, po nazwach drużyn) i `recentGames` z feedu propsów. To drugie
    jest lustrem oferty bukmacherów UK, więc dla Ekstraklasy, kwalifikacji
    pucharów i części Ameryki Południowej po prostu nie istnieje — zmierzone
    07.08: komplet czynników miało 18 ze 134 kandydatów, reszta szła
    z czynnikiem rywala równym 1,00, czyli bez kontekstu przeciwnika.
    Ten endpoint działa dla KAŻDEJ ligi i ma 40 meczów wstecz (do 182 przy
    wyższym `limit`), więc domyka dziurę u źródła.

    Zmierzone na tych samych danych: „ile rywal dopuszcza" to NAJSILNIEJSZA
    pojedyncza zależność w każdym z pięciu rynków drużynowych — model uczony
    od zera na 3018 obserwacjach stawia ją na pierwszym miejscu z wagą dwa do
    czterech razy większą niż cokolwiek innego, a samo dołożenie jej do własnej
    średniej zmniejsza błąd przewidywania o 5–15% (najwięcej przy faulach).

    Kształt jak w `historia_druzyny`: {kod_rynku: (wartości, znaczniki czasu,
    nazwy rywali, id rywali, czy_u_siebie)}, od najnowszego.
    """
    out: dict[str, list] = {}
    for rec in rows:
        ev = rec.get("event") or {}
        opp_st = rec.get("opponentStatistics") or {}
        try:
            ts = int(ev.get("timeStartTimestamp") or 0)
        except (TypeError, ValueError):
            ts = 0
        if not ts:
            continue
        home, away = rec.get("homeTeam") or {}, rec.get("awayTeam") or {}
        u_siebie = int(home.get("id") or 0) == int(team_id)
        rywal = (away if u_siebie else home) or {}
        for pole, mk in TEAM_PERF_MAP.items():
            v = opp_st.get(pole)
            if v is None:
                continue
            out.setdefault(mk, []).append(
                (ts, float(v), str(rywal.get("name") or ""),
                 int(rywal.get("id") or 0), u_siebie)
            )
        # GOLE STRACONE — jak w `historia_druzyny`, tylko druga strona wyniku
        wynik = ev.get("score") or {}
        stracone = wynik.get("away" if u_siebie else "home")
        if stracone is not None:
            out.setdefault("team_goals", []).append(
                (ts, float(stracone), str(rywal.get("name") or ""),
                 int(rywal.get("id") or 0), u_siebie)
            )
    gotowe: dict[str, tuple] = {}
    for mk, pary in out.items():
        pary.sort(key=lambda x: -x[0])
        gotowe[mk] = (
            [c for _, c, _, _, _ in pary],
            [t for t, _, _, _, _ in pary],
            [o for _, _, o, _, _ in pary],
            [i for _, _, _, i, _ in pary],
            [h for _, _, _, _, h in pary],
        )
    return gotowe


@dataclass
class TeamTrend:
    """Trend DRUŻYNOWY: (drużyna, rynek) z historią ~20 meczów i linią."""

    team_id: int
    team_name: str
    opponent_name: str
    event_id: int
    is_home: bool
    market_code: str
    line: float
    odds_type: str = "over"
    # kontekst ligi (recentGames całego feedu = próbka ligi i koncesje rywali)
    opponent_id: int = 0
    league_id: int = 0
    league_name: str = ""
    counts: list[float] = field(default_factory=list)
    timestamps: list[int] = field(default_factory=list)
    game_opponents: list[str] = field(default_factory=list)
    # per mecz historii: id rywala i czy grali u siebie (isHome z feedu)
    game_opponent_ids: list[int] = field(default_factory=list)
    game_is_home: list[bool] = field(default_factory=list)
    ref_odds: list[float] = field(default_factory=list)


def fetch_team_trends(event_ids: list[int]) -> list[TeamTrend]:
    """Trendy drużynowe (`/api/props/team-trends`) dla podanych meczów.

    Zwraca gole / rożne / strzały / celne / kartki per drużyna z historią
    recentGames (statValue per mecz, ~20 wstecz) i kursami referencyjnymi.
    Z PAGINACJĄ — ta sama pułapka co player-trends (domyślne pageSize=25
    cicho ucina feed; zmierzone 2026-07-20: 750 rekordów w 8 stronach).
    """
    if not event_ids:
        return []
    games = ",".join(str(e) for e in event_ids)
    data: list[dict] = []
    page = 1
    PAGE_SIZE = 100
    while True:
        czesc = _get(
            f"{BASE}/props/team-trends?games={games}"
            f"&pageSize={PAGE_SIZE}&page={page}"
        ).get("data", [])
        data += czesc
        # bezpiecznik 40 stron, jak w fetch_event_trends
        if len(czesc) < PAGE_SIZE or page >= 40:
            break
        page += 1
    out: list[TeamTrend] = []
    for rec in data:
        mk = TEAM_STATTYPE_MAP.get(rec.get("statType"))
        if mk is None:
            continue
        rg = rec.get("recentGames", [])
        out.append(TeamTrend(
            team_id=int(rec.get("teamId") or 0),
            team_name=rec.get("teamName", ""),
            opponent_name=rec.get("opponentTeamName", ""),
            event_id=int(rec.get("eventId") or 0),
            is_home=rec.get("homeTeamId") == rec.get("teamId"),
            market_code=mk,
            line=float(rec.get("line", 0.5)),
            odds_type=str(rec.get("oddsType") or "over"),
            opponent_id=int(rec.get("opponentTeamId") or 0),
            league_id=int(rec.get("leagueId") or 0),
            league_name=str(rec.get("leagueName") or ""),
            counts=[float(g.get("statValue") or 0) for g in rg],
            timestamps=[int(g.get("eventTimestamp") or 0) for g in rg],
            game_opponents=[str(g.get("opponentName") or "") for g in rg],
            game_opponent_ids=[int(g.get("opponentId") or 0) for g in rg],
            game_is_home=[bool(g.get("isHome")) for g in rg],
            ref_odds=[
                float(b["oddsValue"])
                for b in rec.get("bookmakers", [])
                if b.get("oddsValue")
            ],
        ))
    return out


def fetch_event_shotmap(event_id: int) -> list[dict]:
    """Mapa strzałów meczu — lista strzałów z `playerId`, `teamId`, `minute`,
    `situation` (assisted/regular/fast-break/corner/free-kick/set-piece),
    `bodyPart`, `isBlockedShot`, `blockedByPlayerId`, `xG`.

    Dla banku STYLU (model/styl.py): udział strzałów z kontr per drużyna
    i strzały ze stałych fragmentów per zawodnik. Kształt sprawdzony na
    żywym meczu MŚ (2026-07-14)."""
    data = _get(f"{BASE}/event/{event_id}/shotmap").get("data", [])
    return data if isinstance(data, list) else []


# wynik strzału w shotmapie -> czy CELNY (on target). Gol i obroniony = celny;
# blok/niecelny/słupek = niecelny. Zgodne z definicją SoT bukmachera.
_SHOTMAP_CELNE = {"goal", "save", "saved"}


def fetch_event_result(event_id: int) -> dict | None:
    """Wynik meczu w REGULARNYM czasie dla DOWOLNEJ ligi (otwarte API, z chmury).

    Zwraca {home_id, away_id, home_name, away_name, home_goals, away_goals,
    extra_time} albo None, gdy mecz niezakończony / brak wyniku. Gole bierze z
    pól *ScoreNormaltime (bez dogrywki) — pod rynki 90-minutowe; extra_time=True
    gdy *Current != *Normaltime (była dogrywka/karne). To domyka rozliczanie
    goli drużynowych egzotyki, której 365Scores nie zna (te same id co statshub).
    """
    try:
        d = _get(f"{BASE}/event/{event_id}")
    except Exception as e:
        # wynik meczu — bez niego typ idzie na „zwrot" po siedmiu dniach
        diagnostyka.cichy("statshub", "wynik_meczu", e)
        return None
    root = d.get("data", d) or {}
    ev = root.get("events")
    ev = (ev[0] if isinstance(ev, list) and ev else ev) or {}
    if not isinstance(ev, dict):
        return None
    # MECZ MUSI BYĆ SKOŃCZONY. Docstring obiecywał to od początku, ale kod
    # tego nie sprawdzał: dla trwającego meczu `homeScoreCurrent` to wynik
    # BIEŻĄCY, więc rozliczenie w 80. minucie brało stan z tej minuty jako
    # ostateczny. Zgłoszenia usera 2026-07-30 (Górnik Zabrze, Remo) to
    # dokładnie ten przypadek — gole zapisane jako 0.
    if str(ev.get("status") or "").lower() != "finished":
        return None
    hn, an = ev.get("homeScoreNormaltime"), ev.get("awayScoreNormaltime")
    hc, ac = ev.get("homeScoreCurrent"), ev.get("awayScoreCurrent")
    hg = hn if hn is not None else hc
    ag = an if an is not None else ac
    if hg is None or ag is None:
        return None
    extra = hn is not None and hc is not None and (hn != hc or an != ac)

    def _nazwa(side: str) -> str | None:
        t = root.get(side) or {}
        t = (t[0] if isinstance(t, list) and t else t) or {}
        return t.get("name") if isinstance(t, dict) else None

    return {
        "home_id": ev.get("homeTeamId"),
        "away_id": ev.get("awayTeamId"),
        "home_name": _nazwa("homeTeam"),
        "away_name": _nazwa("awayTeam"),
        "home_goals": float(hg),
        "away_goals": float(ag),
        "extra_time": bool(extra),
    }


def status_meczu(event_id: int) -> str | None:
    """Status meczu u źródła: `finished`, `notstarted`, `postponed`, `canceled`.

    ⚑ PO CO OSOBNO OD `fetch_event_result` (2026-08-17). Tamta zwraca None
    ZARÓWNO dla meczu przełożonego, jak i dla meczu, którego statystyki po
    prostu jeszcze nie doszły — a to dwie zupełnie różne sytuacje. Druga mija
    sama w kolejnym cyklu, pierwsza NIE MINIE NIGDY: meczu nie było, więc typ
    czeka do siedmiodniowego terminu i dopiero wtedy zamyka się jako „brak
    danych źródła", choć od początku wiadomo było, że danych nie będzie.

    Zmierzone 17.08: 14 typów na dwóch przełożonych meczach (Celta Vigo –
    Osasuna, Independiente Santa Fe – River Plate), 5 z nich klient widział
    na stronie. Do tego dnia w całym kodzie nie było ani jednego miejsca,
    które rozpoznawałoby przełożenie.
    """
    try:
        d = _get(f"{BASE}/event/{event_id}")
    except Exception as e:
        # status meczu — bez niego typ czeka na dane, których może nie być
        diagnostyka.cichy("statshub", "status_meczu", e)
        return None
    root = d.get("data", d) or {}
    ev = root.get("events")
    ev = (ev[0] if isinstance(ev, list) and ev else ev) or {}
    if not isinstance(ev, dict):
        return None
    return str(ev.get("status") or "").lower() or None


def player_shots_from_shotmap(event_id: int) -> dict[str, dict] | None:
    """{nazwa_zawodnika: {"shots": n, "sot": n}} z shotmapy meczu (otwarte API).

    Kluczem jest NAZWISKO (nie playerId) — id zawodników statshub bywają w innej
    przestrzeni niż odbiorca (kupon), więc rozliczanie dopasowuje po nazwisku
    (jak ścieżka 365, resolve_player_key). None = brak shotmapy (egzotyka bez
    pokrycia — nie mylić z 0 strzałów). Liczy CAŁĄ shotmapę, więc używać tylko
    dla meczów bez dogrywki (patrz fetch_event_result.extra_time).
    """
    try:
        sm = fetch_event_shotmap(event_id)
    except Exception as e:
        # ścieżka ROZLICZANIA strzałów — cichy błąd tutaj zostawia typ
        # nierozliczony na zawsze (rekord zamrożony po siedmiu dniach)
        diagnostyka.cichy("statshub", "rozliczenie_strzalow", e)
        return None
    if not sm:
        return None
    out: dict[str, dict] = {}
    for s in sm:
        name = s.get("playerName")
        if not name:
            continue
        d = out.setdefault(str(name), {"shots": 0, "sot": 0})
        d["shots"] += 1
        if str(s.get("result") or "").lower() in _SHOTMAP_CELNE:
            d["sot"] += 1
    return out


_TOURNAMENT_NAME_CACHE: dict[int, str] = {}


def fetch_tournament_name(utid: int) -> str:
    """Nazwa rozgrywek po uniqueTournamentId (`/api/unique-tournament/{id}`).

    Radar etykietuje tym „starą ligę" transferu (np. 'Championnat National,
    Francja'). Cache w pamięci procesu — jeden cykl pyta o kilka utid-ów."""
    if utid in _TOURNAMENT_NAME_CACHE:
        return _TOURNAMENT_NAME_CACHE[utid]
    nazwa = ""
    try:
        d = _get(f"{BASE}/unique-tournament/{utid}", timeout=12, retries=1)
        rec = d.get("data") or {}
        nazwa = str(rec.get("name") or "")
        kraj = str(rec.get("categoryName") or "")
        if nazwa and kraj and kraj.lower() not in nazwa.lower():
            nazwa = f"{nazwa} ({kraj})"
    except Exception as e:
        # nazwa rozgrywek pusta = typ bez etykiety ligi (stempel rozgrywek
        # dołożony 03.08 właśnie po to, żeby dało się mierzyć per liga)
        diagnostyka.cichy("statshub", "nazwa_rozgrywek", e)
    _TOURNAMENT_NAME_CACHE[utid] = nazwa
    return nazwa


def search_players(nazwa: str) -> list[dict]:
    """Wyszukiwarka zawodników `/api/search?q=` (odkryta 2026-07-22).

    Zwraca listę {id, name, slug, countrySlug} — radar używa jej do
    zidentyfikowania debiutantów kwotowanych przez Superbet, których nie ma
    w feedzie propsów (bukmacherzy UK nie wystawili im linii)."""
    try:
        d = _get(f"{BASE}/search?q={nazwa}", timeout=15, retries=2)
    except Exception as e:
        diagnostyka.cichy("statshub", "szukanie_zawodnika", e)
        return []
    out = d.get("players") or []
    return out if isinstance(out, list) else []


def fetch_player_profile(player_id: int) -> dict:
    """Pełniejszy profil niż fetch_player_meta — pod kartę debiutanta radaru.

    KLUCZOWE pole: team_id (obecny klub wg statshub) — weryfikuje, że
    wyszukany po nazwisku gracz faktycznie należy do drużyny z meczu."""
    try:
        data = _get(f"{BASE}/player/{player_id}", timeout=15, retries=2).get(
            "data", {}
        )
    except Exception as e:
        diagnostyka.cichy("statshub", "profil_zawodnika", e)
        return {}
    rec = data.get("players")
    if isinstance(rec, list):
        rec = rec[0] if rec else {}
    if not isinstance(rec, dict):
        return {}
    h = rec.get("height")
    mv = rec.get("marketvalue")
    return {
        "id": rec.get("id"),
        "name": rec.get("name"),
        "position": rec.get("position"),
        "height": int(h) if isinstance(h, (int, float)) and h else None,
        "foot": rec.get("preferredfoot") or None,
        "team_id": int(rec.get("teamid") or 0) or None,
        "country": rec.get("countrySlug"),
        "market_value": float(mv) if mv else None,
        "birth_ts": rec.get("dateofbirth"),
    }


def fetch_player_meta(player_id: int) -> dict:
    """Metadane zawodnika: {"height": int|None, "foot": str|None}.

    `/api/player/{id}` zwraca {"data": {"players": [rekord]}} — m.in. height
    (cm) i preferredfoot. Wzrost zasila matchup.is_target_man."""
    data = _get(f"{BASE}/player/{player_id}").get("data", {})
    rec = data.get("players")
    if isinstance(rec, list):
        rec = rec[0] if rec else {}
    if not isinstance(rec, dict):
        rec = {}
    h = rec.get("height")
    return {
        "height": int(h) if isinstance(h, (int, float)) and h else None,
        "foot": rec.get("preferredfoot") or None,
    }
