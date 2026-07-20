"""Tryb MŚ — SZYBKA ŚCIEŻKA przez statshub (otwarte API) + kursy Superbet.

Dlaczego szybciej: statshub daje w jednym zapytaniu historię mecz-po-meczu,
przewidywany skład i średnią rywala dla 5 rynków rdzeniowych — bez dławionego
Sofascore i bez godzinnego backfillu. Kursy realne bierzemy z Superbetu.

Użycie:
    python -m footstats.jobs.build_wc_fast

Jeśli statshub nie ma jeszcze wystawionych propsów na ćwierćfinały (ładują się
~24-48 h przed meczem), job to zgłasza i kończy — wtedy działa tryb pokazowy,
a strażnik/kolejne uruchomienie dokończy, gdy propsy się pojawią.
"""

from __future__ import annotations

import json
import os
import statistics
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import asdict

from scipy import stats as _stats

import numpy as np
from curl_cffi import requests

from dataclasses import replace as dc_replace

from .. import rozgrywki, supa
from ..engine import (
    MatchContext, PlayerHistory, RARE_MARKETS, apply_bias, score_player_market,
)
from ..model import (
    betting, context, counts, koncesje, kupony, matchup_lite, styl, tempo,
)
from ..sources import eloratings, rotowire, scores365, sofascore, statshub, superbet
from . import rozliczanie
from .build_demo import MARKET_NAMES_PL, WEB_DATA_DIR, line_for_lambda

# KURSY GŁÓWNE: wyłącznie Superbet. STS blokuje IP serwerowni (chmura = źródło
# prawdy, cron GitHub Actions), więc kursy STS w line-shoppingu powodowały
# rozjazd danych między przebiegiem lokalnym a chmurowym (typy "znikały").
# STS zostaje tylko jako adresat SUGESTII bez kursu (niecelne/zablokowane).
# Wróci do kursów głównych, gdy pipeline pójdzie z domowego IP (telefon/Pi).

SH_BASE = "https://www.statshub.com/api"
SH_HEADERS = {"Accept": "application/json", "Referer": "https://www.statshub.com/"}


# Klucze faktycznie zapisane w BIEŻĄCYM uruchomieniu main() — manifest na końcu
# cyklu mówi push_supabase.py, które pliki wolno wypchnąć. Bez tego awaria w
# środku cyklu (np. statshub padnie) kończy się `return` PRZED dumpem części
# plików — zostają w wersji ze świeżego `git checkout` (stare/puste dane
# commitowane w repo), a push_supabase i tak by je wypchnął na produkcję,
# cicho nadpisując żywe dane w Supabase starymi.
_generated_this_run: set[str] = set()

# Adapter trybu ligowego (build_league.TrybLigowy) — None = klasyczny tryb MŚ.
# Ustawiany na czas JEDNEGO przebiegu przez main(tryb=...). W trybie ligowym
# bez publikacji (dry-run) dumpy idą do podkatalogu liga_dryrun, a rozliczenia
# i zapisy do Supabase są pomijane — produkcja zostaje nietknięta.
_tryb = None


def _dry_run() -> bool:
    return _tryb is not None and not _tryb.publikuj


def _dump(name: str, obj) -> None:
    katalog = WEB_DATA_DIR / "liga_dryrun" if _dry_run() else WEB_DATA_DIR
    katalog.mkdir(parents=True, exist_ok=True)
    (katalog / name).write_text(
        json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    if name.endswith(".json") and not _dry_run():
        _generated_this_run.add(name[:-5])


def _rozlicz_i_zapisz(
    value_bets: list[dict],
    kupony_list: list[dict],
    niedostepni: set[int] | None = None,
    conf_mids: set[int] | None = None,
    odrzucone_pomiar: list[dict] | None = None,
    poza_publikacja: list[dict] | None = None,
    legi_pool: list[dict] | None = None,
) -> None:
    """Rozliczanie + zapis wyników. Wywoływane w KAŻDYM cyklu — także gdy
    statshub nie ma propsów (rozliczenia nie mogą czekać na nowe typy).

    kupony.json = AKTYWNE kupony z logu (zamrożone przy publikacji), a nie
    świeżo wygenerowana lista — dzięki temu strona /kupony pokazuje dokładnie
    to, co potem trafi do historii, i nic nie zmienia się między cyklami.
    Przy błędzie NIE nadpisujemy plików — zostają wyniki z poprzedniego cyklu.
    """
    if _dry_run():
        print(f"[dry-run liga] rozliczanie i log typów POMINIĘTE "
              f"({len(value_bets)} typów, {len(kupony_list)} kuponów w pamięci)")
        return
    try:
        # typy pomiarowe (odrzucone przy progu) i typy poza publikacją
        # (kwarantanna/limit meczu) dokładamy WYŁĄCZNIE do logu rozliczeń —
        # value_bets.json (UI) idzie bez nich
        wyniki = rozliczanie.rozlicz(
            value_bets + (odrzucone_pomiar or []) + (poza_publikacja or []),
            kupony_list, niedostepni, conf_mids=conf_mids,
            legi_pool=legi_pool,
        )
    except Exception as ex:
        print(f"Rozliczanie pominięte ({ex}) — poprzednie wyniki bez zmian")
        return
    _dump("typy_wyniki.json", wyniki)
    _dump("kupony.json", [
        k for k in wyniki["kupony"]
        if k.get("wynik") is None and not k.get("pominiety")
    ])
    p = wyniki["podsumowanie"]
    print(f"Typy: {p['opublikowane']} w logu, {p['rozliczone']} rozliczonych, "
          f"{p['trafione']} trafionych, ROI flat {p['roi_flat']:+.2f} j.")
# uniqueTournamentId 16 = Mistrzostwa Świata (jak w Sofascore)
WC_UTID = 16

# --- BRAMA JAKOŚCI (tylko tryb ligowy): świeżość próby zawodnika ---
# fit_posterior waży starość meczu z tau=180 dni (skala CAŁEGO sezonu), więc
# historia sprzed przerwy letniej wciąż waży ~0.66 — model sam z siebie nie
# odróżni "gra co tydzień" od "ostatni mecz w maju". Świeżości pilnujemy
# osobno tutaj: historia bez świeżych występów to typ na nieaktualnym
# zawodniku (kontuzja, wypadł z rotacji, transfer, przerwa w lidze).
OKNO_SWIEZEJ_PROBY_S = 120 * 86400  # okno "żywej" historii (pokrywa przerwę letnią)
MIN_MECZE_W_OKNIE = 2               # mniej występów w oknie = historia martwa, typu nie ma
STARE_DANE_S = 45 * 86400           # ostatni występ dawniej -> typ tylko "w tle"
#   (liczy się, uczy kalibrację, widoczny w Skuteczności; wraca do publikacji
#    po 1-2 kolejkach, gdy zawodnik znów ma świeże mecze)


# --- PEŁNE SKŁADY (predicted/oficjalne) ---
# okno pobierania: przewidywane XI pojawiają się ~36 h przed meczem
OKNO_SKLADOW_S = 48 * 3600
# limit zapytań backupowych do Sofascore per cykl (nieoficjalne API, dławić)
LIMIT_SOFA_NA_CYKL = 40


def sklady_xi(events: list[dict]) -> dict[int, dict]:
    """Pełne XI nadchodzących meczów: mid -> {xi_by_team, confirmed, zrodlo}.

    xi_by_team: {teamId: set[playerId]} — sygnał składu jest wiarygodny
    per DRUŻYNA (bywa, że znamy XI tylko jednej strony; zawodnikom drugiej
    nie wolno wtedy wpisywać "poza składem").

    Hierarchia źródeł (id eventów/zawodników wspólne — statshub jest
    zbudowany na id Sofascore):
      1. statshub team-lineup (oficjalny, gdy event.lineupConfirmed),
      2. statshub predicted-teams-lineup (pełne 11/11 ~36 h przed meczem),
      3. Sofascore /event/{id}/lineups (backup; blokuje IP serwerowni,
         więc w chmurze cicho odpada — działa z domowego PC).
    Migotliwa flaga inPredictedLineup z player-trends zostaje ostatecznym
    fallbackiem w silniku (nic jej nie nadpisuje, gdy XI drużyny nie znamy).
    """
    now = int(time.time())
    out: dict[int, dict] = {}
    sofa_uzyte = 0
    for e in events:
        mid, ts = e.get("id"), e.get("timeStartTimestamp") or 0
        h_tid, a_tid = e.get("homeTeamId"), e.get("awayTeamId")
        if not (mid and h_tid and a_tid) or ts <= now or ts - now > OKNO_SKLADOW_S:
            continue
        xi_by_team: dict[int, set] = {}
        confirmed = bool(e.get("lineupConfirmed"))
        zrodlo = None
        if confirmed:
            for tid in (h_tid, a_tid):
                try:
                    xi_t = statshub.fetch_team_lineup(mid, tid)
                except Exception:
                    xi_t = []
                if len(xi_t) >= 10:
                    xi_by_team[tid] = set(xi_t)
            if xi_by_team:
                zrodlo = "statshub oficjalny"
        if not xi_by_team:
            try:
                pred = statshub.fetch_predicted_lineup(mid)
            except Exception:
                pred = {}
            for side, tid in (("home", h_tid), ("away", a_tid)):
                pids = pred.get(side) or []
                if len(pids) >= 10:
                    xi_by_team[tid] = set(pids)
            if xi_by_team:
                zrodlo = "statshub przewidywany"
                confirmed = confirmed or bool(pred.get("confirmed"))
        if not xi_by_team and sofa_uzyte < LIMIT_SOFA_NA_CYKL:
            sofa_uzyte += 1
            sofa = sofascore.fetch_lineups(mid)
            if sofa:
                for side, tid in (("home", h_tid), ("away", a_tid)):
                    if len(sofa[side]) >= 10:
                        xi_by_team[tid] = sofa[side]
                if xi_by_team:
                    zrodlo = "sofascore"
                    confirmed = confirmed or sofa["confirmed"]
        if xi_by_team:
            out[mid] = {
                "xi_by_team": xi_by_team,
                "confirmed": confirmed,
                "zrodlo": zrodlo,
            }
        time.sleep(0.15)
    return out


def swiezosc_proby(
    timestamps: list[int], minutes: list[float], now: int
) -> tuple[int, float]:
    """(ile występów w oknie świeżości, dni od ostatniego występu).

    Występ = mecz z minutami > 0. Brak jakiegokolwiek występu -> (0, inf).
    """
    grane = [ts for ts, m in zip(timestamps, minutes) if m > 0 and ts > 0]
    if not grane:
        return 0, float("inf")
    n_okno = sum(1 for ts in grane if ts >= now - OKNO_SWIEZEJ_PROBY_S)
    return n_okno, (now - max(grane)) / 86400.0
# nazwy reprezentacji EN -> PL (do dopasowania z Superbetem)
EN_PL = {v: k for k, v in superbet.TEAM_PL_EN.items()}
# MŚ 2026 to NIE jest w pełni neutralny turniej — USA/Meksyk/Kanada są
# współgospodarzami i grają większość swoich meczów u siebie. Nazwy w
# formacie statshub (angielski), zgodnym z wartościami TEAM_PL_EN wyżej.
WC26_HOST_NATIONS = {"USA", "Mexico", "Canada"}


def venue_context(team_name: str, opponent_name: str, is_home_raw: bool) -> tuple[bool, bool]:
    """(is_home, neutral_venue) dla MatchContext, z uwzględnieniem gospodarzy
    MŚ 2026. Gdy jedna z drużyn jest gospodarzem, mecz NIE jest neutralny —
    gospodarz gra u siebie niezależnie od tego, co statshub oznaczył jako
    "home team" w samej parze (to pole bywa administracyjne w turniejach).
    Gdy żadna drużyna nie jest gospodarzem, mecz jest na neutralnym terenie
    (kraj trzeci) i zostaje bez efektu dom/wyjazd, jak dotychczas."""
    host_team = team_name in WC26_HOST_NATIONS
    host_opp = opponent_name in WC26_HOST_NATIONS
    is_host_match = host_team or host_opp
    is_home = host_team if is_host_match else is_home_raw
    return is_home, not is_host_match


def _sh(url: str) -> dict:
    r = requests.get(url, impersonate="chrome124", timeout=30, headers=SH_HEADERS)
    r.raise_for_status()
    return r.json()


def upcoming_wc_events() -> list[dict]:
    """Nadchodzące mecze MŚ z statshub (przeszukaj najbliższe 8 dni)."""
    now = int(time.time())
    out = {}
    for d in range(8):
        start = now + d * 86400
        start -= start % 86400
        try:
            data = _sh(
                f"{SH_BASE}/event/by-date?startOfDay={start}&endOfDay={start + 86399}"
            ).get("data", [])
        except Exception:
            continue
        for e in data:
            ev = e.get("events", e)
            utid = ev.get("uniqueTournamentId") or (ev.get("tournament") or {}).get(
                "uniqueTournamentId"
            )
            if utid == WC_UTID and ev.get("status") == "notstarted":
                out[ev["id"]] = ev
    return list(out.values())


def load_trend_lib() -> dict:
    """Trwała biblioteka trendów (Supabase app_data.trend_lib).

    statshub KASUJE propsy po meczu — bez tej biblioteki tracimy historię
    zawodników, zanim pojawią się kursy na ich następny mecz.
    """
    return supa.get_key("trend_lib") or {}


def save_trend_lib(lib: dict) -> None:
    supa.put_key("trend_lib", lib)


def past_wc_events(days_back: int = 25) -> list[dict]:
    """Rozegrane mecze MŚ z ostatnich dni (pełne eventy: id, drużyny, kickoff)."""
    now = int(time.time())
    out: dict[int, dict] = {}
    for d in range(1, days_back + 1):
        start = now - d * 86400
        start -= start % 86400
        try:
            data = _sh(
                f"{SH_BASE}/event/by-date?startOfDay={start}&endOfDay={start + 86399}"
            ).get("data", [])
        except Exception:
            continue
        for e in data:
            ev = e.get("events", e)
            utid = ev.get("uniqueTournamentId") or (ev.get("tournament") or {}).get(
                "uniqueTournamentId"
            )
            if utid == WC_UTID and ev.get("status") != "notstarted":
                out[ev["id"]] = ev
    return list(out.values())


def past_wc_event_ids(days_back: int = 25) -> list[int]:
    """ID rozegranych meczów MŚ z ostatnich dni (do biblioteki historii)."""
    return [ev["id"] for ev in past_wc_events(days_back)]


def group_prior_from_context(trend: statshub.StatshubTrend) -> counts.GroupPrior:
    """Prior grupowy z ligowej średniej statshub (fallback, gdy mała próba)."""
    la = trend.league_average
    # leagueAverage bywa w skali drużynowej dla części rynków — traktujemy
    # ostrożnie: prior o umiarkowanej sile, średnia z historii zawodnika.
    played = [c for c, m in zip(trend.counts, trend.minutes) if m > 0]
    base = float(np.mean(played)) if played else (la or 0.8)
    return counts.GroupPrior(mean_per90=max(base, 0.15), pseudo_matches=5.0)


# nowe wpisy sędziowskie per cykl (game_referee + pełne staty per mecz) —
# na MŚ turniej miał kilka meczów dziennie, w sezonie ligowym dziesiątki;
# pierwszy cykl dogania porcjami jak bank stylu
LIMIT_NOWYCH_SEDZIOW = 40


def profil_sedziow(
    events: list[dict], team_name: dict[int, str],
    comp_ids: list[int] | None = None,
    cache_key: str = "sedziowie_cache",
) -> dict[int, dict]:
    """Profil sędziego per nadchodzący mecz: {mid: {sedzia, mnoznik, n}}.

    Źródło: 365Scores — officials (obsada znana 1-2 dni przed meczem) +
    suma fauli wszystkich zawodników z rozegranych meczów tego sędziego.
    Mnożnik = średnia z ilorazów (faule meczu / OCZEKIWANE faule tej pary
    drużyn) — oczekiwania z pozostałych meczów tych drużyn, żeby nie mylić
    stylu sędziego ze stylem drużyn (Maroko fauluje dużo u każdego arbitra).
    Mecze z dogrywką pomijane (staty obejmują 120 min i zawyżałyby profil).
    Wyniki per mecz cache'owane w Supabase (cache_key).

    Domyślnie MŚ; tryb ligowy podaje comp_ids (rozgrywki drużynowe) i osobny
    cache (sedziowie_cache_liga) — profile arbitrów klubowych osobno.
    """
    cache = supa.get_key(cache_key) or {}
    zmieniony = False
    rozegrane_365: list[dict] = []
    for c in (comp_ids or [None]):
        try:
            rozegrane_365 += (
                scores365.finished_games_by_competition(c)
                if c else scores365.finished_games_by_competition()
            )
        except Exception:
            continue
    nowych_sed = 0
    for g in rozegrane_365:
        gid = str(g["id"])
        druzyny = [g.get("home") or "", g.get("away") or ""]
        if gid in cache:
            # starsze wpisy sprzed pola "druzyny" — uzupełnij przy okazji
            if not cache[gid].get("druzyny") and all(druzyny):
                cache[gid]["druzyny"] = druzyny
                zmieniony = True
            continue
        if nowych_sed >= LIMIT_NOWYCH_SEDZIOW:
            break
        nowych_sed += 1
        rec = {
            "sedzia": scores365.game_referee(g["id"]), "faule": None,
            "druzyny": druzyny if all(druzyny) else None,
        }
        try:
            if not scores365.after_extra_time(g["id"]):
                staty = scores365.game_player_match_stats(g["id"])
                faule = sum(
                    float(s.get("fouls_committed") or 0) for s in staty.values()
                )
                rec["faule"] = round(faule, 1) if faule > 0 else None
        except Exception:
            pass
        cache[gid] = rec
        zmieniony = True
    if zmieniony:
        supa.put_key(cache_key, cache)

    per_sedzia: dict[str, list[tuple[float, list | None]]] = {}
    sr_druzyny: dict[str, list[float]] = {}
    for rec in cache.values():
        if not rec.get("faule"):
            continue
        if rec.get("sedzia"):
            per_sedzia.setdefault(rec["sedzia"], []).append(
                (float(rec["faule"]), rec.get("druzyny"))
            )
        for d in rec.get("druzyny") or []:
            sr_druzyny.setdefault(d, []).append(float(rec["faule"]))
    wszystkie = [f for fl in per_sedzia.values() for f, _ in fl]
    if not wszystkie:
        return {}
    turniej_sr = sum(wszystkie) / len(wszystkie)

    def _oczekiwane(druzyny: list | None, f_meczu: float) -> float:
        """Faule, jakich spodziewamy się po TEJ parze drużyn (styl drużyn);
        bieżący mecz wyłączony z oczekiwań (leave-one-out)."""
        srednie = []
        for d in druzyny or []:
            fl = list(sr_druzyny.get(d) or [])
            if f_meczu in fl:
                fl.remove(f_meczu)
            if len(fl) >= 2:
                srednie.append(sum(fl) / len(fl))
        return sum(srednie) / len(srednie) if len(srednie) == 2 else turniej_sr

    # obsady nadchodzących meczów: parowanie fixtures 365 z eventami statshub
    # po znormalizowanych nazwach drużyn (awaryjnie kickoff +-3h + jedna nazwa)
    sched: list[dict] = []
    for c in (comp_ids or [None]):
        try:
            sched += (
                scores365.scheduled_games_by_competition(c)
                if c else scores365.scheduled_games_by_competition()
            )
        except Exception:
            continue
    out: dict[int, dict] = {}
    for e in events:
        hn = rotowire._norm(team_name.get(e.get("homeTeamId"), ""))
        an = rotowire._norm(team_name.get(e.get("awayTeamId"), ""))
        ts = e.get("timeStartTimestamp") or 0
        g365 = next(
            (g for g in sched if {g["home"], g["away"]} == {hn, an}),
            None,
        ) or next(
            (g for g in sched
             if abs(g["ts"] - ts) < 3 * 3600 and {g["home"], g["away"]} & {hn, an}),
            None,
        )
        if g365 is None:
            continue
        ref = scores365.game_referee(g365["id"])
        if not ref:
            continue
        proby = per_sedzia.get(ref, [])
        ilorazy = [f / max(_oczekiwane(dr, f), 1e-6) for f, dr in proby]
        out[e["id"]] = {
            "sedzia": ref,
            "mnoznik": (
                round(sum(ilorazy) / len(ilorazy), 3) if ilorazy else None
            ),
            "n": len(proby),
        }
    return out


# --- BANK STYLU (pełne matchupy, model/styl.py) ---
# limity per cykl: pierwszy przebieg dogania cały turniej w 1-2 cyklach,
# kolejne dolewają po kilka meczów dziennie — bez zalewania API
LIMIT_NOWYCH_GIER_STYLU = 40
LIMIT_WZROSTOW_NA_CYKL = 30


def aktualizuj_bank_stylu(
    gracze_id_sh: set[int],
    comp_ids: list[int] | None = None,
    past_events: list[dict] | None = None,
    klucz: str = "styl_bank",
) -> dict:
    """Dolej do banku stylu (Supabase `klucz`) nowe rozegrane mecze:
    statystyki drużynowe i styl zawodników (365Scores), sytuacje strzałów
    (shotmapy statshub) oraz wzrosty zawodników (statshub /player).

    Bank jest trwały — 365/statshub trzymają dane meczu długo, ale wolimy
    nie zależeć od ich retencji, a shotmapy/staty pobierać RAZ per mecz.

    Domyślnie tryb MŚ (rozgrywki 5930, shotmapy z past_wc_events). Tryb
    LIGOWY podaje comp_ids (rozgrywki.comp365_druzynowe), rozegrane eventy
    statshub zakresu drużynowego i osobny klucz banku (styl_bank_liga) —
    style klubów i reprezentacji to dwa różne światy, nie mieszamy.
    """
    bank = supa.get_key(klucz) or {}
    gry = bank.setdefault("gry", {})
    zaw = bank.setdefault("zawodnicy", {})
    smapy = bank.setdefault("shotmap", {})
    wzrost = bank.setdefault("wzrost", {})
    zmienione = False

    # 1) mecze 365Scores: statystyki drużynowe + styl zawodników per mecz
    nowych = 0
    try:
        rozegrane_365: list[dict] = []
        for c in (comp_ids or [None]):
            try:
                rozegrane_365 += (
                    scores365.finished_games_by_competition(c)
                    if c else scores365.finished_games_by_competition()
                )
            except Exception:
                continue
        for g in rozegrane_365:
            gid = str(g["id"])
            if gid in gry:
                continue
            if nowych >= LIMIT_NOWYCH_GIER_STYLU:
                break
            try:
                druzyny = scores365.game_team_stats(g["id"])
                pelne = scores365.game_player_match_stats(g["id"])
            except Exception:
                continue
            if len(druzyny) != 2:
                continue
            gry[gid] = {"ts": g["ts"], "druzyny": druzyny}
            for pkey, rec in pelne.items():
                if not rec.get("minutes"):
                    continue
                z = zaw.setdefault(
                    pkey, {"druzyna": rec.get("druzyna", ""), "gry": {}}
                )
                if rec.get("druzyna"):
                    z["druzyna"] = rec["druzyna"]
                z["gry"][gid] = {
                    "ts": g["ts"], "min": rec.get("minutes", 0),
                    "dribbles_att": rec.get("dribbles_att", 0),
                    "dribbled_past": rec.get("dribbled_past", 0),
                    "aerial_won": rec.get("aerial_won", 0),
                    "aerial_att": rec.get("aerial_att", 0),
                    "ground_att": rec.get("ground_att", 0),
                    "key_passes": rec.get("key_passes", 0),
                    "crosses_att": rec.get("crosses_att", 0),
                }
                # przycinamy do ostatnich 10 meczów (profil i tak bierze 8)
                if len(z["gry"]) > 10:
                    najstarsze = sorted(
                        z["gry"], key=lambda k: z["gry"][k].get("ts", 0)
                    )[: len(z["gry"]) - 10]
                    for k in najstarsze:
                        del z["gry"][k]
            nowych += 1
            zmienione = True
            time.sleep(0.3)
    except Exception as e:
        print(f"Bank stylu: mecze 365 pominięte ({e})")

    # 2) shotmapy statshub (kontry per drużyna, stałe fragmenty per zawodnik)
    try:
        nowych_smap = 0
        for ev in (past_events if past_events is not None else past_wc_events()):
            eid = str(ev["id"])
            if eid in smapy:
                continue
            # w sezonie ligowym rozegranych meczów jest wielokrotnie więcej
            # niż na turnieju — pierwszy cykl dogania porcjami, nie zalewa API
            if nowych_smap >= LIMIT_NOWYCH_GIER_STYLU:
                break
            try:
                strzaly = statshub.fetch_event_shotmap(ev["id"])
            except Exception:
                continue
            if not strzaly:
                continue
            dr: dict[str, dict] = {}
            stale: dict[str, int] = {}
            for s in strzaly:
                tid = str(s.get("teamId") or "")
                if tid:
                    slot = dr.setdefault(tid, {"shots": 0, "kontra": 0})
                    slot["shots"] += 1
                    if s.get("situation") == "fast-break":
                        slot["kontra"] += 1
                if str(s.get("situation") or "") in (
                    "corner", "free-kick", "set-piece", "penalty"
                ):
                    pid = str(s.get("playerId") or "")
                    if pid:
                        stale[pid] = stale.get(pid, 0) + 1
            smapy[eid] = {
                "ts": ev.get("timeStartTimestamp") or 0,
                "druzyny": dr, "stale": stale,
            }
            nowych_smap += 1
            zmienione = True
            time.sleep(0.4)
    except Exception as e:
        print(f"Bank stylu: shotmapy pominięte ({e})")

    # 3) wzrosty zawodników (tylko prawdziwe id statshub; 0 = "pytaliśmy,
    # brak danych" — nie odpytujemy w kółko)
    brakujace = [
        pid for pid in gracze_id_sh
        if pid and pid < 900_000_000 and str(pid) not in wzrost
    ]
    for pid in brakujace[:LIMIT_WZROSTOW_NA_CYKL]:
        try:
            meta_p = statshub.fetch_player_meta(pid)
        except Exception:
            continue
        wzrost[str(pid)] = meta_p.get("height") or 0
        zmienione = True
        time.sleep(0.25)

    if zmienione:
        supa.put_key(klucz, bank)
    return bank


# start MŚ 2026 (2026-06-08 UTC, kilka dni zapasu przed 1. meczem) — granica
# między "sezonem klubowym" (prior) a "turniejem" (aktualizacja posteriora)
WC_START_TS = 1_780_876_800
# wygaszanie historii przedturniejowej w priorze (sezon klubowy jest długi)
PRIOR_TAU_DNI = 240.0
# minimalna/maksymalna siła priora klubowego (w ekwiwalencie pełnych meczów)
PRIOR_MIN_MECZE, PRIOR_MAX_MECZE = 4.0, 12.0
# minimalna WARTOŚĆ (%) Superbetu ponad no-vig UK, by uznać linię za miękką
# (dowód okazji z kursem). Skaluje się z kursem, w odróżnieniu od dawnej sztywnej
# różnicy 0.10 kursu. Strojony — kandydat do kalibracji z rozliczeń okazji.
PROG_EV_UK = 4.0
# limit ekspozycji: maks. tylu publikowanych pewniaków z JEDNEGO meczu —
# typy z tego samego meczu padają razem (korelacja), a czerwone dni
# kalendarza to głównie dni z wieloma typami z jednego zamulonego meczu.
# Nadmiar zostaje w puli generatora kuponów (decyzja usera: 4)
MAX_PEWNIAKOW_MECZ = 4


def klub_prior(
    trend: statshub.StatshubTrend,
    now: int,
    opp_w: list[float] | None,
) -> tuple[counts.GroupPrior, list[bool]] | None:
    """SILNY prior Gamma z historii SPRZED turnieju (sezon klubowy + kadra).

    Leczy chroniczną "za małą próbę": zamiast słabej średniej z 6-10 meczów
    turnieju, punktem wyjścia jest tempo per-90 z pełnej dostępnej historii
    przedturniejowej (ważonej świeżością i siłą rywala), a mecze turnieju
    tylko AKTUALIZUJĄ posterior (maska likelihood — bez podwójnego liczenia).

    Zwraca (prior, maska_likelihood) albo None, gdy próba sprzed turnieju
    jest za mała (wtedy zostaje dotychczasowy słaby prior + pełna historia).
    """
    w_sum, exp_sum, cnt_sum = 0.0, 0.0, 0.0
    mask = []
    for i, ts_g in enumerate(trend.timestamps):
        pre = ts_g < WC_START_TS
        mask.append(not pre)
        if not pre or i >= len(trend.counts):
            continue
        mins = trend.minutes[i] if i < len(trend.minutes) else 0.0
        if mins <= 0:
            continue
        dni = max((now - ts_g) / 86400.0, 0.0)
        w = float(np.exp(-dni / PRIOR_TAU_DNI))
        if opp_w and i < len(opp_w):
            w *= opp_w[i]
        exp_sum += w * mins / 90.0
        cnt_sum += w * trend.counts[i]
        w_sum += w
    if exp_sum < PRIOR_MIN_MECZE:
        return None
    rate = cnt_sum / exp_sum
    return (
        counts.GroupPrior(
            mean_per90=max(rate, 0.05),
            pseudo_matches=float(min(exp_sum, PRIOR_MAX_MECZE)),
            source="klub",
        ),
        mask,
    )


def score_from_trend(
    trend: statshub.StatshubTrend,
    opp_avg_ref: float | None,
    lineup_confirmed: bool = False,
    predicted_available: bool = False,
    roto_pred: bool | None = None,
    roto_confirmed: bool = False,
    matchup_factor: float | None = None,
    matchup_opis: str = "",
    wc_names: set | None = None,
    elo_map: dict[str, int] | None = None,
    tempo_meczu: dict | None = None,
    sedzia: dict | None = None,
    koncesje_tab: "koncesje.Koncesje | None" = None,
    player_style=None,
    opponent_style=None,
    liga: bool = False,
):
    """Zbuduj PlayerHistory z recentGames i policz predykcję (bez kursów).

    Składy — hierarchia sygnałów:
      1. lineupConfirmed (statshub) LUB skład potwierdzony na Rotowire
         -> official_started: twardy fakt (w XI / scenariusz ławki),
      2. przewidywane XI z DWÓCH źródeł (statshub + Rotowire):
         zgoda -> mocny sygnał miękki; spór -> wracamy do historii minut,
      3. tylko jedno źródło -> jego prognoza jako sygnał miękki,
      4. brak prognoz -> sama historia.

    elo_map — ratingi eloratings.net: ciągła waga próby siłą rywala
    (Botswana ≠ Francja) i syntetyczny spread, gdy brak kursów 1X2.
    tempo_meczu — {'spread','total',...} z model/tempo.py (kursy Superbetu).
    """
    now = int(time.time())
    elo_map = elo_map or {}
    # ważenie próby siłą rywala: ciągła waga z Elo (mecz z Francją liczy się
    # pełniej niż z Botswaną); rywal bez ratingu (klub) dostaje wagę bazową
    opp_w = None
    if trend.game_opponents:
        opp_w = [
            eloratings.sample_weight(
                elo_map.get(eloratings._norm(o)),
                is_wc_participant=bool(wc_names and rotowire._norm(o) in wc_names),
            )
            for o in trend.game_opponents[: len(trend.counts)]
        ]
        if len(opp_w) < len(trend.counts):
            opp_w += [0.8] * (len(trend.counts) - len(opp_w))
    hist = PlayerHistory(
        counts=trend.counts,
        minutes=trend.minutes,
        days_ago=[max((now - ts) / 86400.0, 0.0) for ts in trend.timestamps],
        started=trend.started,
        opp_weights=opp_w,
    )
    if sum(1 for m in trend.minutes if m > 0) < 3:
        return None, hist
    # PRIOR: pełna historia sprzed turnieju jako silny prior Gamma
    # ("sezon klubowy"), mecze turnieju aktualizują posterior; przy małej
    # próbie przedturniejowej — dotychczasowy słaby prior + cała historia.
    # W LIDZE podział klub/kadra nie istnieje — ciągła historia + prior grupowy.
    kp = None if liga else klub_prior(trend, now, opp_w)
    if kp is not None:
        prior, hist.likelihood_mask = kp
    else:
        prior = group_prior_from_context(trend)
    sh_pred = trend.in_predicted_lineup if predicted_available else None
    if lineup_confirmed:
        official, predicted = trend.in_predicted_lineup, None
    elif roto_confirmed and roto_pred is not None:
        official, predicted = roto_pred, None
    elif sh_pred is not None and roto_pred is not None:
        # dwa źródła: zgoda = sygnał, spór = nie wiemy -> historia
        official = None
        predicted = sh_pred if sh_pred == roto_pred else None
    else:
        official = None
        predicted = sh_pred if sh_pred is not None else roto_pred
    # tempo/scenariusz meczu: kursy 1X2+gole Superbetu; fallback różnica Elo
    spread_home, total = None, None
    if tempo_meczu:
        spread_home = tempo_meczu.get("spread")
        total = tempo_meczu.get("total")
    else:
        spread_home = eloratings.synthetic_spread(
            elo_map.get(eloratings._norm(trend.team_name if trend.is_home else trend.opponent_name)),
            elo_map.get(eloratings._norm(trend.opponent_name if trend.is_home else trend.team_name)),
        )
    # spread z perspektywy DRUŻYNY ZAWODNIKA (dodatni = jego zespół faworytem)
    spread_teamu = None
    if spread_home is not None:
        spread_teamu = spread_home if trend.is_home else -spread_home
    # kontekst: średnia rywala względem ligi (żywy feed statshub), a gdy jej
    # nie ma — profil koncesji rywala per rynek×pozycja z banku (koncesje.py)
    opp_allowed = trend.opponent_average
    opp_avg = trend.league_average
    # 6 = ZAŁOŻENIE, nie zmierzona wielkość próby: statshub NIE ujawnia w API
    # (props/player-trends), z ilu meczów liczy opponentAverage — sprawdzone
    # w StatshubTrend/fetch_event_trends, brak takiego pola. shrink_factor()
    # ściąga więc ZAWSZE tym samym k=6/(6+12)=0.33, niezależnie od realnej
    # (nieznanej) próby. Fallback niżej (koncesje.py, gdy statshub milczy) MA
    # prawdziwe n_meczy z własnego banku — nie ten przypadek. Nie zgadywać
    # innej stałej bez danych; ew. do zmierzenia jak marża UK (porównać
    # kalibrację rekordów z opp_n=6 vs rekordów z realnym n z koncesje.py).
    opp_n = 6 if trend.opponent_average else 0
    koncesja_opis = ""
    if opp_allowed is None and koncesje_tab is not None:
        kc = koncesje_tab.lookup(
            trend.opponent_name, trend.market_code, trend.position,
            elo_map=elo_map, team_name=trend.team_name, now=now,
        )
        if kc:
            opp_allowed, opp_avg, opp_n = kc
            kub = koncesje.kubelek_pozycji(trend.position) or "tej formacji"
            koncesja_opis = (
                f"Na tym turnieju zawodnicy z formacji „{kub}” notują przeciw "
                f"{trend.opponent_name} ~{opp_allowed:.2f} na 90 min przy "
                f"normie {opp_avg:.2f} (próba: {opp_n} meczów)"
            )
    if liga:
        # liga: realny gospodarz z feedu, neutralne boisko nie występuje
        # (finały pucharów na neutralnym — do obsłużenia przy okazji finałów)
        ctx_is_home, ctx_neutral_venue = trend.is_home, False
    else:
        ctx_is_home, ctx_neutral_venue = venue_context(
            trend.team_name, trend.opponent_name, trend.is_home
        )
    ctx = MatchContext(
        is_home=ctx_is_home,
        is_favourite=bool(spread_teamu is not None and spread_teamu > 0.15),
        neutral_venue=ctx_neutral_venue,
        implied_spread=spread_teamu,
        implied_total=total,
        opponent_allowed_per90=opp_allowed,
        league_avg_per90=opp_avg,
        opponent_sample_matches=opp_n,
        opponent_concession_opis=koncesja_opis,
        # profil sędziego (365Scores): mnożnik fauli vs średnia turnieju —
        # shrinkowany i capowany w context.referee_factor
        referee_fouls_multiplier=(sedzia or {}).get("mnoznik"),
        referee_sample_matches=(sedzia or {}).get("n", 0),
        referee_name=(sedzia or {}).get("sedzia") or "",
        official_started=official,
        predicted_started=predicted,
        opponent_name=trend.opponent_name,
        # PEŁNE matchupy stylu (model/styl.py -> model/matchup.py) — gdy
        # profile są, engine używa ich ZAMIAST matchup-lite (elif w engine)
        player_style=player_style,
        opponent_style=opponent_style,
        matchup_factor=matchup_factor,
        matchup_opis=matchup_opis,
    )
    return (prior, ctx), hist


def main(tryb=None) -> None:
    """Cienki wrapper: gwarantuje zapis manifestu (_manifest.json) na KAŻDYM
    wyjściu z _main_impl (sukces, wczesny return, wyjątek) — patrz komentarz
    przy _generated_this_run wyżej.

    tryb: build_league.TrybLigowy albo None (klasyczny przebieg MŚ)."""
    global _tryb
    _tryb = tryb
    _generated_this_run.clear()
    try:
        _main_impl(tryb)
    finally:
        _dump("_manifest.json", {"keys": sorted(_generated_this_run)})
        _tryb = None


def _main_impl(tryb=None):
    events = tryb.events if tryb else upcoming_wc_events()
    print(f"Nadchodzące mecze {'ligowe' if tryb else 'MŚ'} (statshub): {len(events)}")
    if not events:
        print("Brak nadchodzących meczów w statshub.")
        _rozlicz_i_zapisz([], [])  # rozliczenia lecą niezależnie od nowych typów
        return

    try:
        trends = statshub.fetch_event_trends([e["id"] for e in events])
    except Exception as e:
        print(f"statshub chwilowo niedostępny ({e}) — pomijam ten cykl, dane bez zmian.")
        _rozlicz_i_zapisz([], [])
        return
    print(f"Trendów propsów: {len(trends)} "
          f"({len(set(t.player_id for t in trends))} zawodników)")
    if not trends:
        # statshub schował feed propsów (2026-07-04: /api/props/* zwraca
        # pustkę anonimowo — prawdopodobnie za kontem). NIE przerywamy:
        # historia jest w banku trendów (Supabase) i w 365Scores, składy
        # daje Rotowire, kursy Superbet — jedziemy bez statshuba.
        print("statshub: 0 propsów w feedzie — buduję trendy z banku "
              "historii i pełnych statystyk 365Scores.")

    # --- BIBLIOTEKA HISTORII: mecze bez propsów statshub (np. ćwierćfinały) ---
    # statshub wystawia propsy ~24-48 h przed meczem, a Superbet kwotuje dużo
    # wcześniej (i wtedy kursy są najmiększe). Historia zawodnika nie zależy
    # od nadchodzącego meczu — bierzemy jego najświeższy trend z ROZEGRANYCH
    # meczów MŚ i przepinamy na nowy event (rywal/kontekst neutralne, składy
    # z Rotowire, kursy z Superbetu).
    covered = {t.event_id for t in trends}
    # PEŁNE SKŁADY (statshub predicted/team-lineup + backup Sofascore) —
    # gdzie znamy całą XI drużyny, nadpisujemy migotliwą flagę
    # inPredictedLineup z trendów pewniejszym źródłem (pid w XI / poza XI)
    xi_pelne = sklady_xi(events)
    if xi_pelne:
        n_conf_xi = sum(1 for v in xi_pelne.values() if v["confirmed"])
        zrodla_xi = Counter(v["zrodlo"] for v in xi_pelne.values())
        print(f"Składy: pełne XI dla {len(xi_pelne)} meczów "
              f"({n_conf_xi} potwierdzonych; "
              + ", ".join(f"{k}: {v}" for k, v in zrodla_xi.most_common()) + ")")
    for t in trends:
        xi_t = (xi_pelne.get(t.event_id) or {}).get("xi_by_team", {}).get(t.team_id)
        if xi_t is not None:
            t.in_predicted_lineup = t.player_id in xi_t
    # sygnał przewidywanego/oficjalnego składu (in_predicted_lineup) jest
    # wiarygodny per (mecz, zawodnik) TYLKO dla trendów z żywego feedu —
    # dokładane niżej trendy z banku/365 mają tam zawsze False i bez tej
    # mapy wyglądałyby przy ogłoszonym składzie jak "wszyscy poza XI"
    xi_zywy: dict[tuple[int, int], bool] = {}
    for t in trends:
        if t.event_id and t.player_id:
            k_xi = (t.event_id, t.player_id)
            xi_zywy[k_xi] = xi_zywy.get(k_xi, False) or t.in_predicted_lineup
    # zawodnicy z pełnych XI bez żywego trendu (dokładki z banku/365) też
    # mają wiarygodny sygnał składu — bank czyta go właśnie z tej mapy
    for mid_x, v in xi_pelne.items():
        for xi_set in v["xi_by_team"].values():
            for pid_x in xi_set:
                xi_zywy[(mid_x, pid_x)] = True
    uncovered = [
        e for e in events
        if e["id"] not in covered and e.get("homeTeamId") and e.get("awayTeamId")
    ]
    wszystkie_ev = [
        e for e in events if e.get("homeTeamId") and e.get("awayTeamId")
    ]
    # timestampy meczów reprezentacji per drużyna (z historii 365Scores) —
    # do oznaczania "kadra vs klub" w formie zawodnika
    nt_ts: dict[str, set] = {}
    bank_recs: dict = {}
    try:
        # 1) trwała biblioteka z Supabase (przeżywa kasowanie propsów przez statshub)
        stored = load_trend_lib()
        lib: dict[tuple[int, str], statshub.StatshubTrend] = {}
        for rec in stored.values():
            try:
                t = statshub.StatshubTrend(**rec)
                lib[(t.player_id, t.market_code)] = t
            except TypeError:
                continue  # stary format po zmianie pól — rekord wypada

        def _merge(t: statshub.StatshubTrend) -> None:
            key = (t.player_id, t.market_code)
            prev = lib.get(key)
            ts_new = t.timestamps[0] if t.timestamps else 0
            ts_old = prev.timestamps[0] if prev and prev.timestamps else -1
            if prev is None or ts_new >= ts_old:
                lib[key] = t

        # 2) dołóż co jeszcze zostało z rozegranych eventów + dzisiejsze trendy
        if uncovered:
            past_ids = list(tryb.past_event_ids) if tryb else past_wc_event_ids()
            for i in range(0, len(past_ids), 8):
                for t in statshub.fetch_event_trends(past_ids[i:i + 8]):
                    _merge(t)
        for t in trends:
            _merge(t)
        bank_recs = {
            f"{t.player_id}:{t.market_code}": asdict(t) for t in lib.values()
        }
        if not _dry_run():
            save_trend_lib(bank_recs)

        # 3) przepnij najświeższe trendy z biblioteki na KAŻDY nadchodzący
        #    mecz, którego żywy feed nie pokrywa w danym (zawodnik, rynek) —
        #    wcześniej robiliśmy to tylko dla meczów CAŁKIEM bez propsów,
        #    przez co 2-3 żywe trendy "zasłaniały" cały bank (odbiory,
        #    faule ról drugoplanowych) i pula pewniaków była samymi gwiazdami
        team_by_id: dict[int, str] = {}
        for t in lib.values():
            if t.team_id:
                team_by_id[t.team_id] = t.team_name
            if t.opponent_id:
                team_by_id[t.opponent_id] = t.opponent_name
        n_lib = 0
        juz_w_trendach = {
            (t.event_id, t.player_id, t.market_code) for t in trends
        }
        for e in wszystkie_ev:
            hid, aid = e["homeTeamId"], e["awayTeamId"]
            if not team_by_id.get(hid) or not team_by_id.get(aid):
                continue  # nieznana drużyna = brak historii i pusta karta meczu
            for (pid, mk), t in lib.items():
                if t.team_id not in (hid, aid):
                    continue
                if (e["id"], pid, mk) in juz_w_trendach:
                    continue  # żywy feed już to pokrywa
                juz_w_trendach.add((e["id"], pid, mk))
                opp_id = aid if t.team_id == hid else hid
                trends.append(dc_replace(
                    t,
                    event_id=e["id"],
                    opponent_id=opp_id,
                    opponent_name=team_by_id.get(opp_id, ""),
                    is_home=(t.team_id == hid),
                    opponent_average=None, opponent_rank=None,
                    in_predicted_lineup=xi_zywy.get((e["id"], pid), False),
                    ref_odds=[],
                ))
                n_lib += 1
        if n_lib:
            print(f"Biblioteka historii ({len(lib)} trendów w banku): "
                  f"+{n_lib} przepiętych na nadchodzące mecze")

        # 4) uzupełnij braki PER ZAWODNIK×RYNEK z pełnych statystyk meczowych
        #    365Scores (minuty, strzały, faule, faule na zawodniku, przechwyty,
        #    spalone; odbiory — brak w 365). Dla WSZYSTKICH meczów — nie tylko
        #    niepokrytych: bank rzadko ma całą kadrę, a to właśnie tu rodzą
        #    się typy kontekstowe na role drugoplanowe (nie same gwiazdy).
        MARKETY_365_FULL = ("shots", "sot", "fouls_committed", "fouls_won",
                            "interceptions", "offsides")
        pokryci = {
            (t.team_id, rotowire._norm(t.player_name), t.market_code)
            for t in trends
        }
        zespoly: list[tuple[dict, int, int, bool, str, str]] = []
        for e in wszystkie_ev:
            hid, aid = e["homeTeamId"], e["awayTeamId"]
            slug_parts = str(e.get("slug", "")).replace("-vs-", "|").split("|")
            if len(slug_parts) != 2:
                continue
            home_nm = slug_parts[0].replace("-", " ").title()
            away_nm = slug_parts[1].rsplit("-", 1)[0].replace("-", " ").title()
            zespoly.append((e, hid, aid, True, home_nm, away_nm))
            zespoly.append((e, aid, hid, False, away_nm, home_nm))
        if zespoly:
            cids365 = scores365.competitor_ids(
                sorted({z[4] for z in zespoly})
            )
            n_365 = 0
            hist_cache: dict[str, list] = {}
            for e, tid, opp_tid, is_home, team_nm, opp_nm in zespoly:
                cid = cids365.get(rotowire._norm(team_nm))
                if not cid:
                    continue
                if team_nm not in hist_cache:
                    hist_cache[team_nm] = scores365.team_match_history(cid, 6)
                    nt_ts.setdefault(team_nm, set()).update(
                        g_ts for g_ts, _ in hist_cache[team_nm]
                    )
                games = hist_cache[team_nm]
                if len(games) < 3:
                    continue
                gracze = sorted({p for _, st in games for p in st})
                for pkey in gracze:
                    wpisy = [(ts, st.get(pkey)) for ts, st in games]
                    zagrane = [w for w in wpisy if w[1] and w[1].get("minutes", 0) > 0]
                    if len(zagrane) < 3:
                        continue
                    # pozycja z formacji 365 (dominująca litera) — trafia do
                    # kubełka profilu rywala; wcześniejsze "M" na sztywno
                    # wrzucało obrońców i napastników do złego kubełka
                    poz_licznik: dict[str, int] = {}
                    for _, rec in zagrane:
                        p_l = str(rec.get("pos") or "")
                        if p_l:
                            poz_licznik[p_l] = poz_licznik.get(p_l, 0) + 1
                    poz_gl = max(poz_licznik, key=poz_licznik.get) \
                        if poz_licznik else "M"
                    if poz_gl == "G":
                        continue  # rynki zawodników z pola — bramkarz zbędny
                    pid_365 = (900_000_000
                               + zlib.crc32(pkey.encode("utf-8")) % 90_000_000)
                    for mk in MARKETY_365_FULL:
                        if (tid, pkey, mk) in pokryci:
                            continue  # jest już trend z banku/statshub
                        c_l, m_l, tss, st_l, poz_l = [], [], [], [], []
                        for ts_g, rec in wpisy:
                            if rec is None:
                                continue
                            c_l.append(float(rec.get(mk, 0)))
                            m_l.append(float(rec.get("minutes", 0)))
                            tss.append(int(ts_g))
                            st_l.append(bool(rec.get("started")))
                            poz_l.append(str(rec.get("pos") or ""))
                        trends.append(statshub.StatshubTrend(
                            # hash() jest randomizowany per proces — id musi
                            # być STABILNE między cyklami (log typów, kupony)
                            player_id=pid_365,
                            player_name=pkey.title(),
                            position=poz_gl,
                            team_id=tid, team_name=team_nm,
                            opponent_id=opp_tid, opponent_name=opp_nm,
                            is_home=is_home, market_code=mk, line=0.5,
                            in_predicted_lineup=xi_zywy.get(
                                (e["id"], pid_365), False),
                            league_average=None, opponent_average=None,
                            opponent_rank=None, total_ranks=None,
                            event_id=e["id"],
                            counts=c_l, minutes=m_l,
                            timestamps=tss, started=st_l,
                            game_positions=poz_l,
                        ))
                        n_365 += 1
            if n_365:
                print(f"365Scores pełne staty: +{n_365} trendów uzupełnionych "
                      f"({len(hist_cache)} drużyn)")
    except Exception as ex:
        print(f"Biblioteka historii pominięta ({ex})")

    # --- rynki z map strzałów (365Scores): głową / zza pola karnego ---
    # Syntetyczne trendy: liczby z chartEvents 365Scores (per typ strzału),
    # minuty/starty/pozycje ze statshubowego trendu "shots" tego zawodnika
    # (mecze parowane po timestampie). Dalej płyną przez ten sam scoring,
    # co rynki rdzeniowe (składy, matchup, kursy Superbetu, bezpieczniki).
    SHOT_SPLIT = {
        "headed_shots": "headed",
        "headed_sot": "headed_sot",
        "shots_outside_box": "outside",
        "sot_outside_box": "sot_outside",
        # rynki STS (bez kursu w chmurze) — prawdziwa historia zamiast szacunku
        "shots_blocked": "blocked",
        "shots_off_target": "off_target",
    }
    try:
        shots_trends = [t for t in trends if t.market_code == "shots"]
        team_names = sorted({t.team_name for t in shots_trends if t.team_name})
        cids = scores365.competitor_ids(team_names)
        hist365: dict[str, list] = {}
        for name in team_names:
            cid = cids.get(rotowire._norm(name))
            if cid:
                hist365[name] = scores365.team_shot_history(cid, n_games=6)
                nt_ts.setdefault(name, set()).update(
                    g_ts for g_ts, _ in hist365[name]
                )
        n_syn = 0
        for t in shots_trends:
            games365 = hist365.get(t.team_name) or []
            if not games365:
                continue
            all_keys = {k for _, pp in games365 for k in pp}
            pkey = scores365.resolve_player_key(all_keys, t.player_name)
            if pkey is None:
                continue  # zawodnik bez strzałów w historii 365 — nic do modelowania
            for mk2, f365 in SHOT_SPLIT.items():
                counts2, minutes2, ts2, started2, pos2 = [], [], [], [], []
                for i, ts in enumerate(t.timestamps):
                    rec = next(
                        (pp for g_ts, pp in games365 if abs(g_ts - ts) < 36 * 3600),
                        None,
                    )
                    if rec is None:
                        continue
                    counts2.append(float(rec.get(pkey, {}).get(f365, 0)))
                    minutes2.append(t.minutes[i])
                    ts2.append(ts)
                    started2.append(t.started[i])
                    pos2.append(t.game_positions[i] if i < len(t.game_positions) else "")
                if sum(1 for m in minutes2 if m > 0) < 3:
                    continue
                trends.append(dc_replace(
                    t, market_code=mk2, line=0.5,
                    counts=counts2, minutes=minutes2, timestamps=ts2,
                    started=started2, game_positions=pos2,
                    opponent_average=None, opponent_rank=None,
                    league_average=None, ref_odds=[],
                ))
                n_syn += 1
        if n_syn:
            print(f"365Scores: dołożono {n_syn} trendów map strzałów "
                  f"(drużyn z historią: {len(hist365)})")
    except Exception as e:
        print(f"365Scores pominięte ({e}) — rynki map strzałów bez zmian.")

    # nazwy drużyn są w trendach (event ma tylko ID) -> mapa id->nazwa
    team_name = {}
    for t in trends:
        if t.team_id:
            team_name[t.team_id] = t.team_name
        if t.opponent_id:
            team_name[t.opponent_id] = t.opponent_name
    if tryb:
        # w trybie ligowym nazwy z by-date (homeTeam/awayTeam) są pełniejsze
        # niż z trendów (drużyna bez propsów nie ma trendu) i nadpisują je
        team_name.update(tryb.team_name)

    # uczestnicy MŚ (znormalizowani) — do ważenia próby siłą rywala;
    # w lidze brak listy uczestników (waga bazowa dla wszystkich rywali)
    wc_names = set() if tryb else {
        rotowire._norm(n) for n in team_name.values() if n
    } | {
        rotowire._norm(x)
        for t in trends
        for x in (t.team_name, t.opponent_name)
        if x
    }

    # profil rywala per rynek×pozycja — ze WSZYSTKICH meczów turnieju w banku
    # (nie tylko przeciw aktualnym przeciwnikom: drużyny, które odpadły, też
    # budują normę i profile); filtr klubów załatwia min_ts (sezon skończony)
    try:
        koncesje_tab = koncesje.zbuduj_koncesje(
            bank_recs, wc_names=None,
            min_ts=tryb.koncesje_min_ts if tryb else WC_START_TS,
        )
        n_prof = len({k[0] for k in koncesje_tab._obs})
        print(f"Profil rywali: {n_prof} drużyn, "
              f"{sum(len(v) for v in koncesje_tab._obs.values())} obserwacji")
    except Exception as e:
        koncesje_tab = None
        print(f"Profil rywali pominięty ({e})")

    # PEŁNE MATCHUPY STYLU: bank (drużyny 365 + shotmapy statshub + wzrosty)
    # -> profile OpponentStyle/PlayerStyle -> engine (model/matchup.py).
    # Awaria któregokolwiek źródła = degradacja do matchup-lite, nie błąd.
    style_turnieju = None
    bank_stylu: dict = {}
    try:
        if tryb:
            # wersja ligowa: mecze 365 z rozgrywek drużynowych (comp365),
            # shotmapy z rozegranych meczów zakresu, OSOBNY klucz banku —
            # style klubów nie mieszają się z reprezentacjami MŚ
            bank_stylu = aktualizuj_bank_stylu(
                {t.player_id for t in trends},
                comp_ids=rozgrywki.comp365_druzynowe(),
                past_events=tryb.past_druzynowe_events,
                klucz="styl_bank_liga",
            )
        else:
            bank_stylu = aktualizuj_bank_stylu({t.player_id for t in trends})
        strony_zaw: dict[str, str] = {}
        for t in trends:
            k_st = rotowire._norm(t.player_name)
            if k_st not in strony_zaw:
                s_st = matchup_lite.dominant_side(t.game_positions[:8])
                if s_st != "C":
                    strony_zaw[k_st] = s_st
        tid_by_norm = {
            rotowire._norm(n): tid for tid, n in team_name.items() if n
        }
        style_turnieju = styl.StyleTurnieju(bank_stylu, strony_zaw, tid_by_norm)
        print(f"Bank stylu: {len(bank_stylu.get('gry', {}))} meczów 365, "
              f"{len(bank_stylu.get('shotmap', {}))} shotmap, "
              f"{len(bank_stylu.get('wzrost', {}))} wzrostów")
    except Exception as e:
        print(f"Bank stylu pominięty ({e}) — matchupy w trybie lite")

    # kursy Superbetu (w trybie ligowym lista przyjechała już z parownikiem)
    if tryb:
        sb_events = tryb.sb_events
    else:
        try:
            sb_events = superbet.list_events(days_ahead=8)
        except Exception as e:
            sb_events = []
            print(f"Superbet niedostępny: {e}")

    # Elo reprezentacji (eloratings.net, cache w Supabase) — ciągła waga
    # próby siłą rywala + syntetyczny spread, gdy brak kursów 1X2.
    # W lidze eloratings nie zna klubów — waga bazowa, spread z kursów 1X2.
    elo_map = {} if tryb else eloratings.get_ratings()
    if not tryb:
        print(f"Elo: {len(elo_map)} reprezentacji" if elo_map
              else "Elo niedostępne — wagi próby z listy uczestników MŚ")

    # profil sędziów: obsada + średnia fauli/mecz vs oczekiwania par drużyn
    try:
        if tryb:
            # wersja ligowa: tylko mecze zakresu drużynowego (tam liczymy
            # rynki dyscyplinarne), rozgrywki z profili, osobny cache
            sedzia_by_mid = profil_sedziow(
                [e for e in events if e["id"] in tryb.druzynowe_mids],
                team_name,
                comp_ids=rozgrywki.comp365_druzynowe(),
                cache_key="sedziowie_cache_liga",
            )
        else:
            sedzia_by_mid = profil_sedziow(events, team_name)
        _ev_by = {e["id"]: e for e in events}
        for mid_s, s in sedzia_by_mid.items():
            _e = _ev_by.get(mid_s, {})
            lbl = (f"{team_name.get(_e.get('homeTeamId'), '?')} – "
                   f"{team_name.get(_e.get('awayTeamId'), '?')}")
            print(f"  sędzia {lbl}: {s['sedzia']}"
                  + (f" (faule ×{s['mnoznik']}, {s['n']} m.)"
                     if s.get("mnoznik") else " (bez historii)"))
    except Exception as e:
        sedzia_by_mid = {}
        print(f"Profil sędziów pominięty ({e})")

    # samokalibracja: zmierzone odchylenia szans per rynek (od n>=25 rozliczonych)
    try:
        bias_map = rozliczanie.market_bias()
        if bias_map:
            print("Kalibracja z rozliczeń (Δlogit): " + ", ".join(
                f"{mk} {v['global']:+.2f}" for mk, v in bias_map.items()))
    except Exception:
        bias_map = {}
    # sugestie STS uczą się na własnych rozliczeniach (osobna pula błędu)
    try:
        bias_map_sug = rozliczanie.market_bias_sugestie()
        if bias_map_sug:
            print("Kalibracja sugestii (Δlogit): " + ", ".join(
                f"{mk} {v['global']:+.2f}" for mk, v in bias_map_sug.items()))
    except Exception:
        bias_map_sug = {}
    # BRAMA PUBLIKACJI: rynki trafiające wyraźnie poniżej deklaracji wypadają
    # z publikacji (pewniaki, pula kuponów), ale dalej są scorowane i logowane
    # (poza_publikacja) — kalibracja mierzy je nadal i rynek wraca sam
    try:
        kwarantanna_rynkow = rozliczanie.kwarantanna()
        if kwarantanna_rynkow:
            print("Kwarantanna rynków: " + ", ".join(
                f"{mk} (hit {v['hit']:.0%} vs p {v['sr_p']:.0%}, n={v['n']})"
                for mk, v in kwarantanna_rynkow.items()))
    except Exception as e:
        kwarantanna_rynkow = {}
        print(f"Kwarantanna rynków pominięta ({e})")

    ev_by_id = {e["id"]: e for e in events}
    sb_cache: dict[int, dict] = {}
    tempo.reset_fallback_stats()
    tempo_cache: dict[int, dict | None] = {}  # mid -> tempo z kursów 1X2/goli
    # pełna siatka kursów Superbet (over) do widoku TOP POKRYCIA na stronie
    # meczu: mecz_id -> player_id -> rynek -> "linia" -> kurs. Zbierana z tej
    # samej siatki co scoring (merged), tylko zapisywana na dysk (JSON).
    odds_grid: dict[int, dict[int, dict[str, dict[str, float]]]] = {}

    # przewidywane XI z Rotowire (drugie źródło, działa z chmury)
    try:
        roto = rotowire.fetch_predicted_lineups()
        print(f"Rotowire: przewidywane składy {len(roto)} drużyn")
    except Exception as e:
        roto = {}
        print(f"Rotowire niedostępny: {e}")

    # składy: potwierdzone (event.lineupConfirmed) i przewidywane (czy statshub
    # w ogóle wystawił przewidywany skład dla danego meczu)
    lineup_confirmed = {e["id"]: bool(e.get("lineupConfirmed")) for e in events}
    predicted_available: dict[int, bool] = {}
    for t in trends:
        if t.event_id:
            predicted_available[t.event_id] = (
                predicted_available.get(t.event_id, False) or t.in_predicted_lineup
            )
    # pełne XI (sklady_xi) wzmacniają oba sygnały: znany skład = przewidywany
    # dostępny; potwierdzenie z team-lineup/Sofascore = jak lineupConfirmed
    for mid_x, v in xi_pelne.items():
        predicted_available[mid_x] = True
        if v["confirmed"]:
            lineup_confirmed[mid_x] = True
    n_conf = sum(lineup_confirmed.values())
    if n_conf:
        print(f"Składy ogłoszone: {n_conf} z {len(events)} meczów")

    # okno "rynek nie zdążył": zapamiętujemy PIERWSZY moment potwierdzenia
    # składów per mecz — typy z meczu potwierdzonego <45 min temu dostają
    # bonus w rankingu (kursy często jeszcze nie zareagowały na ogłoszone XI)
    swieze_mids: set[int] = set()
    conf_mids: set[int] = set()
    try:
        potw = supa.get_key("sklady_potwierdzone_ts") or {}
        now_p = int(time.time())
        for e in events:
            mid_e = e["id"]
            conf_e = lineup_confirmed.get(mid_e, False) or (
                rotowire.is_confirmed(roto, team_name.get(e.get("homeTeamId"), ""))
                and rotowire.is_confirmed(roto, team_name.get(e.get("awayTeamId"), ""))
            )
            if conf_e:
                conf_mids.add(mid_e)
            if conf_e and str(mid_e) not in potw:
                potw[str(mid_e)] = now_p
        potw = {k: v for k, v in potw.items() if now_p - int(v) < 3 * 86400}
        if not _dry_run():
            supa.put_key("sklady_potwierdzone_ts", potw)
        swieze_mids = {
            int(k) for k, v in potw.items() if now_p - int(v) < 45 * 60
        }
        if swieze_mids:
            print(f"Świeżo potwierdzone składy (okno na stare linie): "
                  f"{len(swieze_mids)} meczów")
    except Exception:
        swieze_mids = set()

    # zawodnicy POZA ogłoszonym składem (twardy sygnał z statshub lub Rotowire)
    # — unieważniają zamrożone kupony z ich legami (patrz rozliczanie).
    # in_predicted_lineup jest wiarygodne TYLKO dla (mecz, zawodnik) z żywego
    # feedu statshub (xi_zywy) — trendy z banku/365 spoza niego mają False,
    # które znaczy "brak sygnału", nie "poza składem".
    niedostepni: set[int] = set()
    for t in trends:
        if not t.player_id or not t.event_id:
            continue
        rp = rotowire.predicted_status(roto, t.team_name, t.player_name)
        if (
            lineup_confirmed.get(t.event_id)
            and (t.event_id, t.player_id) in xi_zywy
            and not t.in_predicted_lineup
        ) or (rotowire.is_confirmed(roto, t.team_name) and rp is False):
            niedostepni.add(t.player_id)
    if niedostepni:
        print(f"Poza ogłoszonymi składami: {len(niedostepni)} zawodników")

    # matchup-lite: profil per90 zawodników każdej drużyny (pod strony boiska)
    opp_players_by_team: dict[tuple[int, int], list[matchup_lite.OppPlayer]] = {}
    for t in trends:
        tot_min = sum(t.minutes)
        if not t.event_id or not t.team_id or tot_min < 90:
            continue
        opp_players_by_team.setdefault((t.event_id, t.team_id), []).append(
            matchup_lite.OppPlayer(
                market_code=t.market_code,
                positions=tuple(t.game_positions[:6]),
                per90=float(sum(t.counts) / tot_min * 90.0),
            )
        )

    value_bets, matches_out, players_out = [], {}, {}
    vb_id = 0
    seen_player_market = set()  # (player_id, market) — statshub bywa zdublowany
    real_split = {}  # (player_id, mk) -> pełny scoring niecelnych/zablokowanych z 365
    legi_pool = []   # wszystkie kwotowane linie z wysoką szansą — pula pod kupony pewniaków
    # typy zdjęte z publikacji (kwarantanna / stare dane / limit meczu) —
    # rozliczają się i uczą kalibrację w tle; zasilane w KAŻDYM kanale
    # emisji: okazje z kursem, sugestie STS, pewniaki
    typy_poza_publikacja: list[dict] = []
    pstyle_cache: dict[int, object] = {}  # PlayerStyle per zawodnik (styl.py)

    # REJESTR ODRZUCEŃ: dla każdej pary (mecz, zawodnik, rynek), która weszła
    # do scoringu, a NIE dała typu — jeden wpis z powodem. Odpowiada na pytanie
    # "czemu nie ma typu na X" na stronie meczu; wcześniej odrzucenia były
    # cichymi `continue` i wymagały debugowania kodu.
    odrzucenia: dict[tuple, dict] = {}

    def _odrzuc(mid_o, tr_o, powod: str, szczegol: str = "") -> None:
        odrzucenia[(mid_o, tr_o.player_id, tr_o.market_code)] = {
            "mecz_id": mid_o, "podmiot": tr_o.player_name,
            "druzyna": tr_o.team_name,
            "rynek_kod": tr_o.market_code,
            "rynek": MARKET_NAMES_PL.get(tr_o.market_code, tr_o.market_code),
            "powod": powod, "szczegol": szczegol,
        }

    # POMIAR PROGÓW: typy odrzucone TUŻ przy progu (betting.NEAR_*) — trafiają
    # do typy_log jako `odrzucony=True` (rozliczą się w tle, POZA kalibracją,
    # skutecznością i UI). Diagnostyka porówna ich hit-rate z przepuszczonymi.
    odrzucone_pomiar: list[dict] = []
    ODRZUCONE_POMIAR_MAX = 80   # bezpiecznik objętości logu per cykl

    # PEŁNE POKRYCIE p_model per (zawodnik, rynek, linia) — dla scannera value
    # betów STS. Model „widzi" KAŻDĄ kwotowaną linię, nie tylko te, które weszły
    # do puli/okazji, więc STS może łączyć swój kurs z p_model dużo częściej.
    # Klucz sts_model jest backendowy (apka go nie czyta).
    model_pokrycie: list[dict] = []

    for tr in trends:
        if (tr.player_id, tr.market_code) in seen_player_market:
            continue
        seen_player_market.add((tr.player_id, tr.market_code))
        # mecz zawodnika: po jego drużynie i przeciwniku
        ev = next((e for e in events
                   if {e.get("homeTeamId"), e.get("awayTeamId")}
                   == {tr.team_id, tr.opponent_id}), None)
        if ev is None:
            continue
        mid = ev["id"]
        ts = ev.get("timeStartTimestamp") or int(time.time())
        home_name = team_name.get(ev.get("homeTeamId"), "")
        away_name = team_name.get(ev.get("awayTeamId"), "")
        match_label = f"{home_name} – {away_name}"

        if mid not in matches_out:
            sed = sedzia_by_mid.get(mid) or {}
            # etykiety rozgrywek: tryb ligowy niesie je per mecz (z profili
            # rozgrywek + rund statshub); MŚ zostaje po staremu
            et = (tryb.liga_by_mid.get(mid) if tryb else None) or {
                "liga": "MŚ", "sezon": "2026", "kolejka": "Ćwierćfinał",
            }
            # na karcie meczu pokazujemy mnożnik PO shrinkage (1-2 mecze
            # próby to za słaby dowód na "×1,26") — spójnie ze scoringiem
            matches_out[mid] = {
                "id": mid, "liga": et["liga"], "sezon": et["sezon"],
                "kolejka": et["kolejka"], "kickoff_ts": ts,
                "gospodarz": home_name, "gosc": away_name,
                "sedzia": sed.get("sedzia"),
                "sedzia_mnoznik_fauli": round(context.shrink_factor(
                    float(sed.get("mnoznik") or 1.0), sed.get("n", 0), 8.0
                ), 2),
                "okazje": [],
                "sklady_ogloszone": lineup_confirmed.get(mid, False)
                or (
                    rotowire.is_confirmed(roto, home_name)
                    and rotowire.is_confirmed(roto, away_name)
                ),
            }

        # kursy Superbetu dla meczu — POBIERANE PRZED scoringiem, bo tempo
        # meczu (1X2 + total goli) wchodzi do kontekstu predykcji
        sb_odds = sb_cache.get(mid)
        if sb_odds is None and sb_events:
            if tryb:
                # parowanie klubów zrobił build_league (nazwy + okno czasu)
                sb_ev = tryb.sb_ev_by_mid.get(mid)
            else:
                sb_ev = superbet.match_superbet_event(
                    sb_events, home_name, away_name, ts
                )
            if sb_ev:
                parts = [p.strip() for p in (sb_ev.get("matchName") or "·").split("·")]
                try:
                    sb_odds = superbet.fetch_stat_odds(sb_ev["eventId"], parts[0], parts[1])
                except Exception:
                    sb_odds = {"players": {}, "teams": {}}
            else:
                sb_odds = {"players": {}, "teams": {}}
            sb_cache[mid] = sb_odds
            tempo_m = tempo.tempo_from_match_odds(sb_odds.get("match"))
            tempo_cache[mid] = tempo_m
            if tempo_m:
                print(f"  tempo {match_label}: spread {tempo_m['spread']:+.2f}, "
                      f"gole {tempo_m['total']:.2f}")

        mf, mo = matchup_lite.matchup_lite_factor(
            tr.market_code,
            tr.game_positions[:6],
            opp_players_by_team.get((mid, tr.opponent_id), []),
        )
        # pełne profile stylu (cache per zawodnik — nie zależą od rynku)
        pstyle = ostyle = None
        if style_turnieju is not None:
            ostyle = style_turnieju.opponent(tr.opponent_name)
            if ostyle is not None:
                if tr.player_id not in pstyle_cache:
                    pstyle_cache[tr.player_id] = style_turnieju.player(
                        tr.player_name, tr.position or "M",
                        tr.game_positions[:8], player_id_sh=tr.player_id,
                    )
                pstyle = pstyle_cache[tr.player_id]
        built, hist = score_from_trend(
            tr, tr.opponent_average,
            # potwierdzony/przewidywany skład wolno czytać z in_predicted_lineup
            # tylko dla (mecz, zawodnik) z żywego feedu statshub — trendy
            # banku/365 spoza niego mają False = "brak sygnału"
            lineup_confirmed=lineup_confirmed.get(mid, False)
            and (mid, tr.player_id) in xi_zywy,
            predicted_available=predicted_available.get(mid, False)
            and (mid, tr.player_id) in xi_zywy,
            roto_pred=rotowire.predicted_status(roto, tr.team_name, tr.player_name),
            roto_confirmed=rotowire.is_confirmed(roto, tr.team_name),
            matchup_factor=mf if mf != 1.0 else None,
            matchup_opis=mo,
            wc_names=wc_names,
            elo_map=elo_map,
            tempo_meczu=tempo_cache.get(mid),
            sedzia=sedzia_by_mid.get(mid),
            koncesje_tab=koncesje_tab,
            player_style=pstyle,
            opponent_style=ostyle,
            liga=tryb is not None,
        )
        if built is None:
            _odrzuc(mid, tr, "za_malo_historii",
                    "mniej niż 3 mecze z minutami w historii")
            continue
        prior, ctx = built
        mk = tr.market_code
        # BRAMA JAKOŚCI (liga): typ tylko przy świeżej próbie. W MŚ nie ma
        # sensu (turniej sam jest oknem świeżości), w lidze historia bywa
        # w całości sprzed pauzy/kontuzji/transferu.
        stare_dane = False
        if tryb:
            n_swieze, dni_ostatni = swiezosc_proby(
                tr.timestamps, tr.minutes, int(time.time())
            )
            if n_swieze < MIN_MECZE_W_OKNIE:
                _odrzuc(mid, tr, "za_stara_historia",
                        f"tylko {n_swieze} występów w ostatnich 4 miesiącach, "
                        "dane o zawodniku są nieaktualne")
                continue
            stare_dane = dni_ostatni * 86400 > STARE_DANE_S
        # trigger rotacyjny: zawodnik w (przewidywanym) XI bez ani jednego
        # występu na turnieju (w lidze: w oknie świeżości z trybu) — rynek
        # często nie zdążył dograć jego linii
        prog_rotacji = tryb.rotacja_min_ts if tryb else WC_START_TS
        gral_na_turnieju = any(
            ts_g >= prog_rotacji and m_g > 0
            for ts_g, m_g in zip(tr.timestamps, tr.minutes)
        )
        rotacja = bool(
            (ctx.official_started or ctx.predicted_started)
            and not gral_na_turnieju
        )
        # sygnał składu przy publikacji — trafia do typy_log (kalibracja p_start)
        xi_sygnal = (
            "official" if ctx.official_started
            else "predicted" if ctx.predicted_started else None
        )

        probe = score_player_market(mk, 0.5, hist, prior, ctx, None, None,
                                    market_calibrated=True,
                                    market_bias=bias_map.get(mk, 1.0))
        if probe.lam < (0.35 if mk not in RARE_MARKETS else 0.2):
            _odrzuc(mid, tr, "za_malo_zdarzen",
                    f"model oczekuje ~{probe.lam:.2f} na mecz, za mało na typ")
            continue
        line = line_for_lambda(probe.lam)

        # niecelne/zablokowane z PRAWDZIWEJ historii 365Scores: pełny scoring
        # (Superbet nie kwotuje tych rynków — wynik trafi do sugestii STS)
        if mk in ("shots_blocked", "shots_off_target"):
            sm_r = score_player_market(mk, line, hist, prior, ctx, None, None,
                                       market_calibrated=True,
                                       market_bias=bias_map.get(mk, 1.0))
            dist_r = counts.predict_match(
                counts.fit_posterior(
                    np.array(hist.counts), np.array(hist.minutes),
                    np.array(hist.days_ago), prior),
                sm_r.expected_minutes, 1.0,
            ).distribution(8)
            real_split[(tr.player_id, mk)] = {
                "sm": sm_r, "line": line, "dist": dist_r,
                "stare_dane": stare_dane,
                "info": {
                    "name": tr.player_name, "team": tr.team_name,
                    "opp": tr.opponent_name, "mid": mid, "ts": ts,
                    "match": match_label,
                },
            }

        # kursy Superbetu dla tego zawodnika/rynku (mecz pobrany wyżej);
        # znajdz_zawodnika łata rozjazd pełne vs boiskowe nazwiska (kluby)
        sb_lines = {}
        if sb_odds:
            sb_lines = superbet.znajdz_zawodnika(
                sb_odds.get("players", {}), tr.player_name
            ).get(mk, {})

        # kursy: linia -> strona -> (kurs, bukmacher) — tylko Superbet (patrz nota u góry)
        merged: dict = {}
        for l, v in sb_lines.items():
            slot = merged.setdefault(l, {})
            for side in ("over", "under"):
                odd = v.get(side)
                if odd and (side not in slot or odd > slot[side][0]):
                    slot[side] = (odd, "Superbet")

        # siatka kursów Superbet (over) do TOP POKRYCIA — wszystkie linie danego
        # zawodnika/rynku, keyed po player_id (players.json nie ma mecz_id)
        over_linie = {
            str(l): round(slot["over"][0], 2)
            for l, slot in merged.items() if slot.get("over")
        }
        if over_linie:
            odds_grid.setdefault(mid, {}).setdefault(tr.player_id, {})[mk] = (
                over_linie
            )

        # zapisz formę zawodnika (dla UI)
        if tr.player_id not in players_out:
            players_out[tr.player_id] = {
                "id": tr.player_id, "nazwa": tr.player_name,
                "pozycja": tr.position or "?", "druzyna": tr.team_name,
                "minuty_lacznie": int(sum(tr.minutes)), "forma": {},
                # w przewidywanym/potwierdzonym pierwszym składzie (na górę TOP POKRYCIA)
                "xi": bool(tr.in_predicted_lineup),
            }
        elif tr.in_predicted_lineup:
            players_out[tr.player_id]["xi"] = True
        nt_zbior = nt_ts.get(tr.team_name, set())
        # statshub daje ~40 meczów historii — trzymamy 20, żeby na stronie meczu
        # dało się PREFEROWAĆ ostatnie 5 startów w KADRZE (a nie klubowe) i pokazać
        # datę ostatniego meczu (świeżość). Model i tak liczy z pełnego tr.counts.
        N = 20
        players_out[tr.player_id]["forma"][mk] = {
            "ostatnie": [int(c) for c in tr.counts[:N]],
            "minuty": [int(m) for m in tr.minutes[:N]],
            "rywale": [str(o) for o in tr.game_opponents[:N]],
            "kadra": [
                any(abs(ts_g - g) < 36 * 3600 for g in nt_zbior)
                for ts_g in tr.timestamps[:N]
            ],
            "ts": [int(t) for t in tr.timestamps[:N]],
            "srednia90": round(
                float(np.sum(tr.counts) / max(np.sum(tr.minutes), 1) * 90.0), 2
            ),
        }

        if not merged:
            _odrzuc(mid, tr, "brak_kursu",
                    "Superbet nie kwotuje tego rynku dla zawodnika")
            continue  # brak realnego kursu — nie tworzymy okazji

        # 1a: samospójność siatki linii Superbetu (line shopping bez
        # zewnętrznych kursów) — fair kurs każdej linii z fitu do POZOSTAŁYCH
        fair_wewn: dict[float, float] = {}
        if len(merged) >= 3:
            probs_w = {
                l0: betting.implied_prob_one_sided(s0["over"][0])
                for l0, s0 in merged.items() if s0.get("over")
            }
            if len(probs_w) >= 3:
                fair_wewn = betting.internal_fair_odds(probs_w)

        best_by_side, chosen = {}, {}
        # śledzenie powodu, gdy ŻADNA linia nie wejdzie do puli kuponów —
        # zasila rejestr odrzuceń precyzyjniejszym powodem niż "nie wyszło"
        n_pool_przed = len(legi_pool)
        prof_ok = ci_fail = div_fail = False
        hist_krotka = len(tr.counts) < 5
        for l, slot in sorted(merged.items()):
            over_odd = slot.get("over", (None,))[0]
            under_odd = slot.get("under", (None,))[0]
            sm = score_player_market(mk, l, hist, prior, ctx,
                                     over_odd, under_odd,
                                     market_calibrated=True,
                                     market_bias=bias_map.get(mk, 1.0))
            # POMIAR PROGÓW: odrzucenia tuż przy progu (betting.NEAR_*) —
            # rozliczą się w tle poza kalibracją/skutecznością/UI
            for od in sm.odrzucone:
                if (
                    od.get("side") != "powyzej"
                    or len(odrzucone_pomiar) >= ODRZUCONE_POMIAR_MAX
                ):
                    continue
                odrzucone_pomiar.append({
                    "id": 0, "mecz_id": mid, "mecz": match_label,
                    "kickoff_ts": ts, "podmiot_typ": "zawodnik",
                    "podmiot_id": tr.player_id, "podmiot": tr.player_name,
                    "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk],
                    "linia": l, "strona": "powyzej",
                    "kurs": od.get("odds"), "bukmacher": "Superbet",
                    "p_model": od.get("p_model"),
                    "pewnosc": "wysoka" if (sm.ci_high - sm.ci_low) <= 0.18
                    else "srednia",
                    "sugestia": False,
                    "odrzucony": True,
                    "odrzucenie_powod": od.get("powod"),
                })
            # pula pewniaków pod kupony: wysoka szansa + rozsądny kurs,
            # bez wymogu value, ale z TYMI SAMYMI bezpiecznikami rozbieżności
            # co okazje — model skrajnie niezgodny z rynkiem zwykle się myli
            # gramy wyłącznie "powyżej" (decyzja usera); under ma też wadę
            # modelową: P(nie zagra) wchodzi do dołu, a buk daje wtedy zwrot
            for side_key, side_pl in (("over", "powyzej"),):
                sv = slot.get(side_key)
                if not sv:
                    continue
                odd = sv[0]
                p_side = sm.p_over if side_key == "over" else 1.0 - sm.p_over
                implied = betting.implied_prob_one_sided(odd)
                # pełne pokrycie p_model (PRZED filtrami puli/okazji) — do STS
                model_pokrycie.append({
                    "podmiot": tr.player_name, "rynek_kod": mk, "linia": l,
                    "strona": side_pl, "p_model": round(p_side, 4),
                    "oczekiwane_minuty": sm.expected_minutes,
                })
                # miękka linia: płaci >=12% ponad kurs wynikający z RESZTY
                # siatki Superbetu na ten rynek (fair netto -> brutto z marżą)
                fw = fair_wewn.get(l)
                kurs_oczekiwany = (
                    round(fw * (1.0 - betting.DEFAULT_ONE_SIDED_MARGIN), 2)
                    if fw else None
                )
                miekka = (
                    kurs_oczekiwany is not None
                    and odd >= kurs_oczekiwany * 1.12
                )
                # dwa profile lega: PEWNIAK (niski kurs, wysoka szansa) oraz
                # PEREŁKA (kurs 2.0-3.6 przy wciąż solidnej szansie i
                # nieujemnej wartości — okazjonalne rodzynki na kupony)
                pewny = (
                    betting.MIN_ODDS <= odd <= 2.80   # user: kursy od 1.19
                    and p_side >= 0.52
                    and p_side * odd - 1.0 >= -0.12
                )
                perelka = (
                    1.90 <= odd <= 3.60
                    and p_side >= 0.42
                    and p_side * odd - 1.0 >= 0.0
                )
                # furtka kontekstowa: rynki niszowe (spalone / głową / celne
                # zza pola) prawie nigdy nie przechodzą zwykłych progów, a to
                # tam rynek myli się najbardziej — wpuszczamy je wyłącznie
                # przy wyraźnie sprzyjającym profilu rywala (matchup)
                czynnik_rywala = float(sm.factors.get("rywal", 1.0) or 1.0)
                matchup_typ = czynnik_rywala >= 1.12
                niszowa = (
                    mk in RARE_MARKETS
                    and matchup_typ
                    and 1.90 <= odd <= 3.60
                    and p_side >= 0.40
                    and p_side * odd - 1.0 >= -0.05
                )
                # typ kontekstowy (matchup): profil rywala wyraźnie sprzyja —
                # model może rozejść się z rynkiem mocniej niż zwykle, bo zna
                # kontekst, którego kurs mógł nie wycenić (weryfikują rozliczenia)
                max_div = 0.30 if matchup_typ else betting.MAX_MODEL_MARKET_DIVERGENCE
                max_rel = 2.3 if matchup_typ else betting.MAX_RELATIVE_DIVERGENCE
                if pewny or perelka or niszowa:
                    prof_ok = True
                    if (sm.ci_high - sm.ci_low) > 0.35:
                        ci_fail = True
                    if abs(p_side - implied) > max_div or (
                        implied > 0 and p_side / implied > max_rel
                    ):
                        div_fail = True
                if (
                    (pewny or perelka or niszowa)
                    and len(tr.counts) >= 5  # pewniak nie powstaje z 2 meczów
                    and (sm.ci_high - sm.ci_low) <= 0.35
                    and abs(p_side - implied) <= max_div
                    and (implied <= 0 or p_side / implied <= max_rel)
                ):
                    # wartość lega (do selekcji kuponów „ku przewadze”):
                    # EV vs Superbet zawsze; no-vig UK gdy jest konsensus na tej linii
                    ev_pct_leg = round((p_side * odd - 1.0) * 100.0, 1)
                    ev_uk_leg = None
                    kurs_ref_leg = None
                    if (
                        tr.ref_odds and abs(l - tr.line) < 1e-6
                        and tr.odds_type == "over" and side_key == "over"
                    ):
                        # mediana UK — do KALIBRACJI marży UK z rozliczeń (rozliczanie.py
                        # potrzebuje kurs_ref w typy_log; bez niego legi trafiające do
                        # logu WYŁĄCZNIE przez kupon są ślepą plamą dla tej diagnostyki)
                        kurs_ref_leg = round(statistics.median(tr.ref_odds), 2)
                        _nv = betting.no_vig_prob_uk(tr.ref_odds)
                        if _nv:
                            ev_uk_leg = round((_nv[0] * odd - 1.0) * 100.0, 1)
                    legi_pool.append({
                        "id": 0, "mecz_id": mid, "mecz": match_label,
                        "kickoff_ts": ts, "podmiot_id": tr.player_id,
                        "podmiot": tr.player_name, "druzyna": tr.team_name,
                        "przeciwnik": tr.opponent_name,
                        "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk], "linia": l,
                        "strona": side_pl, "kurs": odd,
                        "bukmacher": sv[1], "p_model": round(p_side, 4),
                        "ev_pct": ev_pct_leg, "ev_uk": ev_uk_leg, "kurs_ref": kurs_ref_leg,
                        # ta sama formuła co w value_bets (spójne z pewnosc_score
                        # backendu) — generator na żądanie (GeneratorKuponu) tego
                        # dotąd nie miał, więc nie mógł filtrować jak styl "value"
                        "pewnosc": "wysoka" if (sm.ci_high - sm.ci_low) <= 0.18 else "srednia",
                        "matchup": matchup_typ, "rotacja": rotacja,
                        # PEŁNY matchup stylu realnie ruszył predykcję — flaga
                        # do diagnostyki kategorii (czy analogie stylu trafiają)
                        "matchup_styl": bool(
                            pstyle is not None and ostyle is not None
                            and abs(float(sm.factors.get("matchup", 1.0) or 1.0) - 1.0) >= 0.05
                        ),
                        "xi_sygnal": xi_sygnal,
                        "swieze_sklady": mid in swieze_mids,
                        # brama jakości (liga): ostatni występ dawniej niż
                        # STARE_DANE_S -> typ nie wchodzi do publikacji ani
                        # do puli generatora, rozlicza się w tle
                        "stare_dane": stare_dane,
                        "miekka_linia": miekka,
                        "kurs_oczekiwany": kurs_oczekiwany if miekka else None,
                        "ci": [sm.ci_low, sm.ci_high],
                        "oczekiwane_minuty": sm.expected_minutes,
                        "ryzyko": betting.risk_level(
                            sm.lam, mk in RARE_MARKETS,
                            1.0 if (sm.expected_minutes or 0) >= 80
                            else 0.75 if (sm.expected_minutes or 0) >= 60
                            else 0.45,
                        ),
                        "czynniki": sm.factors, "uzasadnienie": sm.reasoning,
                        "lambda": sm.lam,
                        # rozkład przybliżony Poissonem z λ — pod drabinkę
                        # "szanse na inne linie" w rozwinięciu karty
                        "rozklad": [
                            float(_stats.poisson.pmf(k, sm.lam)) for k in range(7)
                        ] + [float(_stats.poisson.sf(6, sm.lam))],
                    })
            for a in sm.assessments:
                if a.side not in best_by_side or a.rank_score > best_by_side[a.side].rank_score:
                    best_by_side[a.side] = a
                    chosen[a.side] = (sm, l, slot)
        # żadna linia nie weszła do puli kuponów — zapisz precyzyjny powód
        if len(legi_pool) == n_pool_przed:
            if not prof_ok:
                _odrzuc(mid, tr, "kurs_lub_szansa_poza_widelkami",
                        "kwotowane linie nie łączą sensownego kursu z szansą")
            elif hist_krotka:
                _odrzuc(mid, tr, "krotka_historia",
                        f"tylko {len(tr.counts)} meczów w historii (potrzeba 5)")
            elif ci_fail and not div_fail:
                _odrzuc(mid, tr, "chwiejna_predykcja",
                        "za szerokie widełki szansy, model sam nie jest pewny")
            else:
                _odrzuc(mid, tr, "rozjazd_z_rynkiem",
                        "model za daleko od kursu, zwykle to my czegoś nie wiemy")
        for a in best_by_side.values():
            if a.side != "powyzej":
                continue  # underów nie gramy (decyzja usera)
            sm, l, slot = chosen[a.side]
            side_key = "over" if a.side == "powyzej" else "under"
            kurs_wziety, book = slot[side_key]
            vb_id += 1
            dist = counts.predict_match(
                counts.fit_posterior(
                    np.array(hist.counts), np.array(hist.minutes),
                    np.array(hist.days_ago), prior),
                sm.expected_minutes, 1.0,
            ).distribution(8)
            # konsensus bukmacherów UK (statshub) dla tej samej linii i strony
            kurs_ref = None       # surowa mediana UK (do UI: „UK płaci średnio X")
            kurs_novig = None     # uczciwy kurs UK po zdjęciu marży (no-vig benchmark)
            ev_uk = None          # wartość Superbetu vs no-vig UK, w %
            if (
                tr.ref_odds
                and abs(l - tr.line) < 1e-6
                and (tr.odds_type == "over") == (a.side == "powyzej")
            ):
                kurs_ref = round(statistics.median(tr.ref_odds), 2)
                novig = betting.no_vig_prob_uk(tr.ref_odds)
                if novig is not None:
                    p_uk, fair_uk = novig
                    kurs_novig = round(fair_uk, 2)
                    ev_uk = round((p_uk * kurs_wziety - 1.0) * 100.0, 1)
            # OKAZJA Z KURSEM, gdy jest DOWÓD miękkiej linii:
            #  (1) NO-VIG UK: Superbet daje realną WARTOŚĆ >= PROG_EV_UK ponad
            #      uczciwą cenę UK po zdjęciu marży (nie tylko wyższy surowy kurs —
            #      to porównanie w przestrzeni prawdopodobieństwa, skalujące się
            #      z kursem), LUB
            #  (2) >= 12% ponad kurs z JEGO WŁASNEJ siatki pozostałych linii (1a —
            #      line shopping bez zewnętrznych źródeł).
            # Bez dowodu — typ zostaje w puli pewniaków.
            odstaje_zewn = ev_uk is not None and ev_uk >= PROG_EV_UK
            fw_a = fair_wewn.get(l)
            oczek_a = (
                round(fw_a * (1.0 - betting.DEFAULT_ONE_SIDED_MARGIN), 2)
                if fw_a else None
            )
            miekka_a = oczek_a is not None and kurs_wziety >= oczek_a * 1.12
            if not odstaje_zewn and not miekka_a:
                continue
            rec_okazji = {
                "id": vb_id, "mecz_id": mid, "mecz": match_label, "kickoff_ts": ts,
                "podmiot_typ": "zawodnik", "podmiot_id": tr.player_id,
                "podmiot": tr.player_name, "druzyna": tr.team_name,
                "przeciwnik": tr.opponent_name,
                "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk],
                "linia": l, "strona": a.side,
                "kurs": kurs_wziety,
                "bukmacher": book,
                "kurs_ref": kurs_ref,
                "kurs_novig": kurs_novig, "ev_uk": ev_uk,
                "p_model": a.model_prob, "p_rynku": a.implied_prob,
                "fair_kurs": a.fair_odds, "edge_pp": a.edge_pp, "ev_pct": a.ev_pct,
                "matchup": float(sm.factors.get("rywal", 1.0) or 1.0) >= 1.12,
                "matchup_styl": bool(
                    pstyle is not None and ostyle is not None
                    and abs(float(sm.factors.get("matchup", 1.0) or 1.0) - 1.0) >= 0.05
                ),
                "rotacja": rotacja, "xi_sygnal": xi_sygnal,
                "miekka_linia": odstaje_zewn or miekka_a,
                "kurs_oczekiwany": (
                    kurs_novig if odstaje_zewn else (oczek_a if miekka_a else None)
                ),
                "pewnosc": a.confidence, "pewnosc_score": a.confidence_score,
                "ryzyko": a.risk, "rank_score": a.rank_score,
                "ci": [sm.ci_low, sm.ci_high],
                "oczekiwane_minuty": sm.expected_minutes, "lambda": sm.lam,
                "rozklad": dist, "czynniki": sm.factors, "uzasadnienie": sm.reasoning,
            }
            # brama jakości (liga): okazja na starych danych nie wchodzi do
            # publikacji, rozlicza się i uczy kalibrację w tle
            if stare_dane:
                rec_okazji["poza_publikacja"] = "stare_dane"
                typy_poza_publikacja.append(rec_okazji)
            else:
                value_bets.append(rec_okazji)
                matches_out[mid]["okazje"].append(vb_id)

    # --- SUGESTIE bez kursów: niecelne / zablokowane (rynki STS, blokowany w chmurze) ---
    # WYŁĄCZNIE z prawdziwej historii per strzał z 365Scores (real_split —
    # pełny scoring modelu: prior, minuty, składy, matchup). Dawny fallback
    # "strzały − celne z podziałem ligowym" USUNIĘTY: rozliczenia pokazały
    # hit 23.5% przy śr. p 55.2% (real_split: 48.8% przy 58.1%) — szacunek
    # był czystym szumem i psuł kalibrację oraz zaufanie do sekcji.
    def _push_sugestia(pid, mk, info, lam, p_over, line, extra, stare_dane=False):
        nonlocal vb_id
        vb_id += 1
        rec = {
            "id": vb_id, "mecz_id": info["mid"], "mecz": info["match"],
            "kickoff_ts": info["ts"], "podmiot_typ": "zawodnik",
            "podmiot_id": pid, "podmiot": info["name"], "druzyna": info["team"],
            "przeciwnik": info["opp"],
            "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk],
            "linia": line, "strona": "powyzej",
            "sugestia": True,                      # <-- brak kursu, sprawdź w STS
            "kurs": None, "bukmacher": "STS (sprawdź ręcznie)",
            "p_model": round(p_over, 4), "p_rynku": None,
            "fair_kurs": round(1.0 / max(p_over, 1e-6), 2),
            "edge_pp": None, "ev_pct": None,
            "rank_score": p_over,                  # sortowanie sugestii po szansie
            "lambda": round(lam, 3),
            **extra,
        }
        # brama jakości (liga): sugestia na starych danych tylko w tle
        if stare_dane:
            rec["poza_publikacja"] = "stare_dane"
            typy_poza_publikacja.append(rec)
            return
        value_bets.append(rec)
        matches_out.setdefault(info["mid"], {}).setdefault("okazje", []).append(vb_id)

    for (pid, mk), real in real_split.items():
        sm_r, dist_r = real["sm"], real["dist"]
        if sm_r.lam < 0.5:
            continue
        # STS wystawia kilka linii ("1 lub więcej", "2 lub więcej"...) —
        # emitujemy KAŻDĄ, przy której model daje >= 50% szans (z rozkładu)
        for linia_s in (0.5, 1.5, 2.5, 3.5):
            thr = int(linia_s) + 1  # "powyżej 1.5" = X >= 2
            p_over_l = float(sum(dist_r[thr:])) if thr < len(dist_r) else 0.0
            # kalibracja sugestii z ich własnych rozliczeń (rozkład jej nie ma)
            p_over_l = apply_bias(bias_map_sug.get(mk, 1.0), p_over_l)
            # progi PO kalibracji podniesione z 0.50/0.38: rozliczenia pokazały,
            # że sugestie p<0.60 trafiały 37.8%, a p>=0.70 — 100% (mała próba,
            # ale kierunek jasny) — mniej pozycji, za to grywalnych
            if p_over_l < (0.60 if linia_s == 0.5 else 0.45):
                break
            _push_sugestia(pid, mk, real["info"], sm_r.lam, p_over_l, linia_s, {
                "pewnosc": "srednia", "pewnosc_score": 45.0, "ryzyko": "wysokie",
                "ci": [sm_r.ci_low, sm_r.ci_high],
                "oczekiwane_minuty": sm_r.expected_minutes,
                "rozklad": dist_r, "czynniki": sm_r.factors,
                "uzasadnienie": sm_r.reasoning,
            }, stare_dane=real.get("stare_dane", False))

    # --- RYNKI DRUŻYNOWE: strzały / celne / kartki (historia: statshub
    # team-trends, ~20 meczów) + faule (bank stylu, mecze MŚ). Kursy Superbetu
    # (TEAM_MARKET_SUFFIX) są już w sb_cache. Legi drużynowe wchodzą do
    # legi_pool tymi samymi progami co zawodnicze i płyną dalej istniejącą
    # ścieżką pewniaków/kuponów; rozliczanie: scores365.game_team_stats.
    try:
        # zakres drużynowy: w lidze rynki drużynowe liczymy WYŁĄCZNIE dla
        # rozgrywek z profilem druzynowe=True (top 5 + Ekstraklasa + puchary,
        # decyzja zakresu 2026-07-20); w MŚ — wszystkie mecze jak dotąd
        ids_tt = [e["id"] for e in events]
        if tryb:
            ids_tt = [i for i in ids_tt if i in tryb.druzynowe_mids]
            print(f"Rynki drużynowe: {len(ids_tt)}/{len(events)} meczów "
                  "w zakresie drużynowym")
        try:
            team_trends = statshub.fetch_team_trends(ids_tt) if ids_tt else []
        except Exception as e:
            team_trends = []
            print(f"team-trends niedostępne ({e})")

        TEAM_POLE_BANKU = {
            "team_shots": "shots", "team_sot": "sot",
            "team_fouls": "fouls", "team_cards": "kartki",
            # rożne są w banku (game_team_stats id 8); goli bank nie ma —
            # nieistniejące pole daje None i uczciwe fallbacki (średnia
            # z historii trendu, czynnik rywala 1.0)
            "team_corners": "corners", "team_goals": "gole",
        }
        gry_banku = list((bank_stylu.get("gry") or {}).values())

        def _hist_z_banku(team_nm: str, pole: str) -> tuple[list, list]:
            tn = rotowire._norm(team_nm)
            pary = []
            for rec_g in gry_banku:
                dr = rec_g.get("druzyny") or {}
                if tn in dr and dr[tn].get(pole) is not None:
                    pary.append((int(rec_g.get("ts") or 0), float(dr[tn][pole])))
            pary.sort(key=lambda x: -x[0])
            return [c for _, c in pary], [t for t, _ in pary]

        def _srednia_turnieju(pole: str) -> tuple[float | None, int]:
            vals = [
                float(d[pole])
                for rec_g in gry_banku
                for d in (rec_g.get("druzyny") or {}).values()
                if d.get(pole) is not None
            ]
            return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

        def _koncesja_druzynowa(opp_nm: str, pole: str) -> tuple[float | None, int]:
            """Ile tej statystyki notują PRZECIW rywalowi jego przeciwnicy."""
            tn = rotowire._norm(opp_nm)
            vals = []
            for rec_g in gry_banku:
                dr = rec_g.get("druzyny") or {}
                if tn in dr and len(dr) == 2:
                    inny = next(k for k in dr if k != tn)
                    v = dr[inny].get(pole)
                    if v is not None:
                        vals.append(float(v))
            return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

        # faule drużyn: team-trends ich nie wystawia — syntetyczny trend z banku
        widziane_tt = {(t.event_id, t.team_id, t.market_code) for t in team_trends}
        for e in wszystkie_ev:
            if tryb and e["id"] not in tryb.druzynowe_mids:
                continue  # zakres drużynowy (jw.), gdy bank ligowy powstanie
            for tid_e, opp_e, is_home_e in (
                (e["homeTeamId"], e["awayTeamId"], True),
                (e["awayTeamId"], e["homeTeamId"], False),
            ):
                nm_e = team_name.get(tid_e, "")
                if not nm_e or (e["id"], tid_e, "team_fouls") in widziane_tt:
                    continue
                c_f, t_f = _hist_z_banku(nm_e, "fouls")
                if len(c_f) < 3:
                    continue
                team_trends.append(statshub.TeamTrend(
                    team_id=tid_e, team_name=nm_e,
                    opponent_name=team_name.get(opp_e, ""),
                    event_id=e["id"], is_home=is_home_e,
                    market_code="team_fouls", line=0.0,
                    counts=c_f, timestamps=t_f,
                ))

        n_team = 0
        seen_team = set()
        odpadki_t: Counter = Counter()  # diagnostyka: czemu legi drużynowe nie powstają
        for tt in team_trends:
            klucz_t = (tt.event_id, tt.team_id, tt.market_code)
            if klucz_t in seen_team or tt.event_id not in ev_by_id:
                continue
            seen_team.add(klucz_t)
            ev = ev_by_id[tt.event_id]
            mid = tt.event_id
            ts = ev.get("timeStartTimestamp") or int(time.time())
            home_name = team_name.get(ev.get("homeTeamId"), "")
            away_name = team_name.get(ev.get("awayTeamId"), "")
            match_label = f"{home_name} – {away_name}"
            sb_odds = sb_cache.get(mid)
            if sb_odds is None and sb_events:
                # mecz z trendami DRUŻYNOWYMI bez zawodniczych nie przeszedł
                # przez pętlę główną, więc nikt nie pobrał jego kursów —
                # typowy przypadek: kwalifikacje pucharów (propsów
                # zawodniczych brak, gole/rożne drużynowe są). Dociągamy.
                if tryb:
                    sb_ev = tryb.sb_ev_by_mid.get(mid)
                else:
                    sb_ev = superbet.match_superbet_event(
                        sb_events, home_name, away_name, ts
                    )
                if sb_ev:
                    parts = [p.strip()
                             for p in (sb_ev.get("matchName") or "·").split("·")]
                    try:
                        sb_odds = superbet.fetch_stat_odds(
                            sb_ev["eventId"], parts[0], parts[1]
                        )
                    except Exception:
                        sb_odds = {"players": {}, "teams": {}}
                else:
                    sb_odds = {"players": {}, "teams": {}}
                sb_cache[mid] = sb_odds
                # tempo z tych samych kursów — f_script niżej z niego korzysta
                tempo_cache[mid] = tempo.tempo_from_match_odds(sb_odds.get("match"))
            sb_odds = sb_odds or {}
            linie_t = (
                sb_odds.get("teams", {})
                .get("home" if tt.is_home else "away", {})
                .get(tt.market_code, {})
            )
            if not linie_t:
                odpadki_t["brak_kursu"] += 1
                continue
            if len(tt.counts) < 5:
                odpadki_t["krotka_historia"] += 1
                continue
            pole = TEAM_POLE_BANKU[tt.market_code]
            lg_mean, _lg_n = _srednia_turnieju(pole)
            if lg_mean is None:
                lg_mean = float(np.mean(tt.counts))
            prior_t = counts.GroupPrior(
                mean_per90=max(lg_mean, 0.5), pseudo_matches=4.0
            )
            n_h = min(len(tt.counts), 20)
            now_t = int(time.time())
            posterior_t = counts.fit_posterior(
                np.array(tt.counts[:n_h]),
                np.array([90.0] * n_h),
                np.array([
                    max((now_t - t) / 86400.0, 0.0)
                    for t in (tt.timestamps[:n_h] or [now_t] * n_h)
                ]),
                prior=prior_t,
            )
            sed_t = sedzia_by_mid.get(mid) or {}
            dyscyplinarny = tt.market_code in ("team_fouls", "team_cards")
            f_sedzia = context.referee_factor(
                sed_t.get("mnoznik"), sed_t.get("n", 0),
                market_is_disciplinary=dyscyplinarny,
            )
            tempo_m = tempo_cache.get(mid) or {}
            spread_home = tempo_m.get("spread")
            spread_teamu = (
                spread_home if tt.is_home else -spread_home
            ) if spread_home is not None else None
            f_script = context.game_script_factor(
                spread_teamu, tempo_m.get("total"), tt.market_code,
                bool(spread_teamu is not None and spread_teamu > 0.15),
            )
            konc, konc_n = _koncesja_druzynowa(tt.opponent_name, pole)
            f_opp = (
                context.opponent_factor(konc, lg_mean, konc_n)
                if konc is not None and lg_mean else 1.0
            )
            factor_t = f_sedzia * f_script * f_opp
            srednia_hist = float(np.mean(tt.counts[:n_h]))
            # brama jakości (liga) także dla drużyn: historia klubu sprzed
            # przerwy/awansu podlega tym samym progom co zawodnicza
            stare_t = False
            if tryb and tt.timestamps:
                n_sw_t, dni_ost_t = swiezosc_proby(
                    tt.timestamps, [90.0] * len(tt.timestamps), now_t
                )
                if n_sw_t < MIN_MECZE_W_OKNIE:
                    odpadki_t["za_stara_historia"] += 1
                    continue
                stare_t = dni_ost_t * 86400 > STARE_DANE_S
            for l_t, slot_t in sorted(linie_t.items()):
                odd_t = (slot_t or {}).get("over")
                if not odd_t:
                    continue
                pred_t = counts.predict_match(posterior_t, 90.0, factor_t)
                p_t = pred_t.p_over(l_t)
                lo_t, hi_t = counts.p_over_credible_interval(
                    posterior_t, 90.0, factor_t, l_t
                )
                implied_t = betting.implied_prob_one_sided(odd_t)
                pewny_t = (
                    betting.MIN_ODDS <= odd_t <= 2.80
                    and p_t >= 0.52 and p_t * odd_t - 1.0 >= -0.12
                )
                perelka_t = (
                    1.90 <= odd_t <= 3.60
                    and p_t >= 0.42 and p_t * odd_t - 1.0 >= 0.0
                )
                if not (pewny_t or perelka_t):
                    odpadki_t["kurs_lub_szansa_poza_widelkami"] += 1
                    continue
                if (hi_t - lo_t) > 0.35:
                    odpadki_t["chwiejna_predykcja"] += 1
                    continue
                if abs(p_t - implied_t) > betting.MAX_MODEL_MARKET_DIVERGENCE:
                    odpadki_t["rozjazd_z_rynkiem"] += 1
                    continue
                if implied_t > 0 and p_t / implied_t > betting.MAX_RELATIVE_DIVERGENCE:
                    odpadki_t["rozjazd_z_rynkiem"] += 1
                    continue
                ev_uk_t = kurs_ref_t = None
                if (
                    tt.ref_odds and abs(l_t - tt.line) < 1e-6
                    and tt.odds_type == "over"
                ):
                    kurs_ref_t = round(statistics.median(tt.ref_odds), 2)
                    nv_t = betting.no_vig_prob_uk(tt.ref_odds)
                    if nv_t:
                        ev_uk_t = round((nv_t[0] * odd_t - 1.0) * 100.0, 1)
                czynniki_t = []
                # liczby w opisach po polsku (przecinek) — teksty idą 1:1 do UI
                sr_t = f"{srednia_hist:.1f}".replace(".", ",")
                czynniki_t.append({
                    "nazwa": "Poziom bazowy",
                    "opis": f"Średnio {sr_t} na mecz "
                            f"(próba: {n_h} meczów)",
                    "mnoznik": None,
                })
                if abs(f_opp - 1.0) > 0.02:
                    konc_s = f"{konc:.1f}".replace(".", ",")
                    norma_s = f"{lg_mean:.1f}".replace(".", ",")
                    czynniki_t.append({
                        "nazwa": "Profil rywala",
                        "opis": f"Rywale notują przeciw {tt.opponent_name} "
                                f"~{konc_s} przy normie {norma_s} "
                                f"(próba: {konc_n} meczów)",
                        "mnoznik": round(f_opp, 2),
                    })
                if abs(f_sedzia - 1.0) > 0.02 and sed_t.get("sedzia"):
                    czynniki_t.append({
                        "nazwa": "Sędzia",
                        "opis": f"{sed_t['sedzia']}: "
                                f"{'surowy' if f_sedzia > 1 else 'pobłażliwy'}",
                        "mnoznik": round(f_sedzia, 2),
                    })
                if abs(f_script - 1.0) > 0.02:
                    czynniki_t.append({
                        "nazwa": "Scenariusz meczu",
                        "opis": "Z kursów meczowych: przewidywany przebieg "
                                + ("sprzyja" if f_script > 1 else "nie sprzyja"),
                        "mnoznik": round(f_script, 2),
                    })
                legi_pool.append({
                    "id": 0, "mecz_id": mid, "mecz": match_label,
                    "kickoff_ts": ts, "podmiot_id": tt.team_id,
                    "podmiot": tt.team_name, "druzyna": tt.team_name,
                    "przeciwnik": tt.opponent_name,
                    "podmiot_typ": "druzyna",
                    "rynek_kod": tt.market_code,
                    "rynek": MARKET_NAMES_PL[tt.market_code],
                    "linia": l_t, "strona": "powyzej", "kurs": odd_t,
                    "bukmacher": "Superbet", "p_model": round(p_t, 4),
                    "ev_pct": round((p_t * odd_t - 1.0) * 100.0, 1),
                    "ev_uk": ev_uk_t, "kurs_ref": kurs_ref_t,
                    "pewnosc": "wysoka" if (hi_t - lo_t) <= 0.18 else "srednia",
                    "matchup": bool(f_opp >= 1.12),
                    "matchup_styl": False,
                    "rotacja": False, "xi_sygnal": None,
                    "swieze_sklady": mid in swieze_mids,
                    "stare_dane": stare_t,
                    "miekka_linia": False, "kurs_oczekiwany": None,
                    "ci": [round(lo_t, 4), round(hi_t, 4)],
                    "oczekiwane_minuty": None,
                    "ryzyko": betting.risk_level(pred_t.lam, False, 1.0),
                    "czynniki": {
                        "rywal": round(f_opp, 3), "sedzia": round(f_sedzia, 3),
                        "dom_wyjazd": 1.0,
                        "scenariusz_meczu": round(f_script, 3),
                        "matchup": 1.0,
                        "lacznie": round(factor_t, 3), "opisy": {},
                    },
                    "uzasadnienie": {
                        "czynniki": czynniki_t,
                        "oczekiwana_liczba": round(float(pred_t.lam), 2),
                        "rynek_rzadki": False,
                    },
                    "lambda": round(float(pred_t.lam), 3),
                })
                n_team += 1
        if n_team or team_trends:
            print(f"Rynki drużynowe: +{n_team} legów w puli "
                  f"({len(team_trends)} trendów drużynowych)"
                  + (f"; odpadło: " + ", ".join(
                      f"{k}={v}" for k, v in odpadki_t.most_common())
                     if odpadki_t else ""))
    except Exception as e:
        print(f"Rynki drużynowe pominięte ({e})")

    # --- PEWNIAKI: najlepszy typ KAŻDEGO rynku dla każdego meczu ---
    # Nie top-N po samej szansie (wygrywałyby zawsze zwykłe strzały 0.5) —
    # użytkownik chce widzieć pełne spektrum statystyk: strzały, celne,
    # zza pola, celne zza pola, faule, wywalczone, odbiory, przechwyty...
    # Kandydaci przeszli pełny scoring + bezpieczniki rozbieżności.
    juz_opublikowane = {
        (b["podmiot_id"], b["rynek_kod"], b["linia"], b["strona"])
        for b in value_bets
    } | {
        # okazje/sugestie zdjęte przez bramę jakości — bez tego ten sam typ
        # trafiłby do logu drugi raz kanałem pewniaków
        (b["podmiot_id"], b["rynek_kod"], b["linia"], b["strona"])
        for b in typy_poza_publikacja
    }
    per_mecz_rynek: set[tuple[int, str]] = set()

    def _atrakcyjnosc(b: dict) -> float:
        """Ranking pewniaka: nie sama szansa (zawsze wygrywałaby linia 0,5),
        ale szansa × pierwiastek kursu, z bonusem za kontekst (profil rywala,
        wejście do XI) i karą za chwiejną predykcję (szerokie CI)."""
        ci = b.get("ci") or [None, None]
        ci_w = (ci[1] - ci[0]) if ci[0] is not None else 0.30
        r = b["p_model"] * (b["kurs"] ** 0.5)
        if b.get("matchup"):
            r *= 1.15
        if b.get("rotacja"):
            r *= 1.10
        if b.get("swieze_sklady"):
            r *= 1.12  # składy ogłoszone <45 min temu — kurs mógł nie zdążyć
        if b.get("miekka_linia"):
            r *= 1.10  # linia odstaje od własnej siatki buka (błąd tradera)
        if ci_w > 0.25:
            r *= 0.90
        return r

    # perełki: do 2 wpisów z wyższym kursem (>=2.0) per mecz, po wartości
    perelki_kandydaci = sorted(
        (b for b in legi_pool if b["kurs"] >= 1.90),
        key=lambda x: -(x["p_model"] * x["kurs"]),
    )
    perelki_per_mecz: dict[int, int] = {}
    do_emisji: list[dict] = []
    for b in sorted(legi_pool, key=lambda x: -_atrakcyjnosc(x)):
        if (b["mecz_id"], b["rynek_kod"]) in per_mecz_rynek:
            continue
        per_mecz_rynek.add((b["mecz_id"], b["rynek_kod"]))
        do_emisji.append(b)
    # WYŻSZE LINIE: ranking po samej szansie prawie zawsze wygrywa linia 0,5
    # — a w puli bywają perełki typu "strzały 1,5+" albo "odbiory 2,5+"
    # (kurs wyraźnie wyższy przy wciąż solidnej szansie). Per (mecz, rynek)
    # dokładamy najlepszego kandydata z linią >= 1,5 po jakości p×kurs.
    wyzsze: dict[tuple[int, str], dict] = {}
    for b in legi_pool:
        # przy kursie 1,9+ dopuszczamy "opcję ryzykowną" już od p>=40%
        # (format tipsterski: linia wyżej, kurs wyraźnie wyższy)
        prog_p = 0.40 if b["kurs"] >= 1.9 else 0.52
        if b["linia"] < 1.5 or b["p_model"] < prog_p:
            continue
        kw = (b["mecz_id"], b["rynek_kod"])
        w = wyzsze.get(kw)
        if w is None or b["p_model"] * b["kurs"] > w["p_model"] * w["kurs"]:
            wyzsze[kw] = b
    for b in wyzsze.values():
        b["wyzsza_linia"] = True
        do_emisji.append(b)
    for b in perelki_kandydaci:
        if perelki_per_mecz.get(b["mecz_id"], 0) >= 2:
            continue
        perelki_per_mecz[b["mecz_id"]] = perelki_per_mecz.get(b["mecz_id"], 0) + 1
        do_emisji.append(b)
    # LIMIT EKSPOZYCJI DZIENNEJ: do publikacji wchodzi maks. MAX_PEWNIAKOW_MECZ
    # pewniaków z jednego meczu (w kolejności atrakcyjności) — czerwone dni
    # kalendarza brały się z 5+ skorelowanych typów z jednego zamulonego
    # meczu. Nadmiar oraz rynki w kwarantannie dalej się rozliczają i UCZĄ
    # kalibrację (flaga poza_publikacja), ale nie wchodzą do apki/kalendarza.
    # (typy_poza_publikacja zainicjalizowane przed pętlą trendów — zbiera
    # też okazje z kursem i sugestie zdjęte przez bramę jakości)
    pewniaki_per_mecz: dict[int, int] = {}
    for b in do_emisji:
        klucz = (b["podmiot_id"], b["rynek_kod"], b["linia"], b["strona"])
        if klucz in juz_opublikowane:
            continue
        juz_opublikowane.add(klucz)
        ci = b.get("ci") or [None, None]
        ci_w = (ci[1] - ci[0]) if ci[0] is not None else 1.0
        vb_id += 1
        powod_poza = None
        if b["rynek_kod"] in kwarantanna_rynkow:
            powod_poza = "kwarantanna_rynku"
        elif b.get("stare_dane"):
            powod_poza = "stare_dane"
        elif pewniaki_per_mecz.get(b["mecz_id"], 0) >= MAX_PEWNIAKOW_MECZ:
            powod_poza = "limit_meczu"
        rec_pewniaka = {
            "id": vb_id, "mecz_id": b["mecz_id"], "mecz": b["mecz"],
            "kickoff_ts": b["kickoff_ts"],
            "podmiot_typ": b.get("podmiot_typ", "zawodnik"),
            "podmiot_id": b["podmiot_id"], "podmiot": b["podmiot"],
            "druzyna": b.get("druzyna", ""), "przeciwnik": b.get("przeciwnik", ""),
            "rynek_kod": b["rynek_kod"], "rynek": b["rynek"],
            "linia": b["linia"], "strona": b["strona"],
            "pewniak": True,
            "wyzsza_linia": bool(b.get("wyzsza_linia")),
            "matchup": bool(b.get("matchup")),
            "matchup_styl": bool(b.get("matchup_styl")),
            "rotacja": bool(b.get("rotacja")),
            "swieze_sklady": bool(b.get("swieze_sklady")),
            "miekka_linia": bool(b.get("miekka_linia")),
            "kurs_oczekiwany": b.get("kurs_oczekiwany"),
            "xi_sygnal": b.get("xi_sygnal"),
            "kurs": b["kurs"], "bukmacher": b["bukmacher"],
            "p_model": b["p_model"], "p_rynku": None,
            "fair_kurs": round(1.0 / max(b["p_model"], 1e-6), 2),
            "edge_pp": None,
            "ev_pct": round((b["p_model"] * b["kurs"] - 1.0) * 100.0, 1),
            "pewnosc": "wysoka" if ci_w <= 0.18 else "srednia",
            "pewnosc_score": 55.0,
            "ryzyko": b.get("ryzyko", "srednie"),
            "rank_score": round(_atrakcyjnosc(b), 4),
            "ci": ci, "oczekiwane_minuty": b.get("oczekiwane_minuty"),
            "lambda": round(b.get("lambda", 0.0), 3),
            "rozklad": b.get("rozklad"),
            "czynniki": b.get("czynniki", {}),
            "uzasadnienie": b.get("uzasadnienie", {"czynniki": []}),
        }
        if powod_poza:
            rec_pewniaka["poza_publikacja"] = powod_poza
            typy_poza_publikacja.append(rec_pewniaka)
            continue
        pewniaki_per_mecz[b["mecz_id"]] = pewniaki_per_mecz.get(b["mecz_id"], 0) + 1
        value_bets.append(rec_pewniaka)
        matches_out.setdefault(b["mecz_id"], {}).setdefault("okazje", []).append(vb_id)
    if typy_poza_publikacja:
        n_kw = sum(1 for t in typy_poza_publikacja
                   if t["poza_publikacja"] == "kwarantanna_rynku")
        n_st = sum(1 for t in typy_poza_publikacja
                   if t["poza_publikacja"] == "stare_dane")
        print(f"Poza publikacją: {n_kw} typów (kwarantanna rynku), "
              f"{n_st} (stare dane), "
              f"{len(typy_poza_publikacja) - n_kw - n_st} (limit na mecz) — "
              "rozliczą się i uczą kalibrację w tle")

    value_bets.sort(key=lambda b: -b["rank_score"])

    # rynki w kwarantannie wypadają też z puli kuponów (generator i kupony
    # automatyczne nie budują na rynku, który trafia poniżej deklaracji);
    # to samo legi na starych danych (brama jakości ligi)
    legi_pool_pub = [
        b for b in legi_pool
        if b["rynek_kod"] not in kwarantanna_rynkow and not b.get("stare_dane")
    ]

    # REJESTR ODRZUCEŃ — domknięcie: para (zawodnik, rynek) opublikowana
    # (typ/sugestia) wypada z rejestru; obecna w puli kuponów, ale nie na
    # karcie meczu, dostaje uczciwe "tylko_w_puli" (jest w generatorze)
    opublikowane_pary = {(b["podmiot_id"], b["rynek_kod"]) for b in value_bets}
    pary_puli = {(b["podmiot_id"], b["rynek_kod"]) for b in legi_pool_pub}
    odrzucenia_out = [
        r for (mid_o, pid_o, mk_o), r in odrzucenia.items()
        if (pid_o, mk_o) not in opublikowane_pary
        and (pid_o, mk_o) not in pary_puli
    ]
    w_puli_dodane = set()
    for b in legi_pool_pub:
        para = (b["podmiot_id"], b["rynek_kod"])
        if para in opublikowane_pary or para in w_puli_dodane:
            continue
        w_puli_dodane.add(para)
        odrzucenia_out.append({
            "mecz_id": b["mecz_id"], "podmiot": b["podmiot"],
            "druzyna": b.get("druzyna", ""),
            "rynek_kod": b["rynek_kod"], "rynek": b["rynek"],
            "powod": "tylko_w_puli",
            "szczegol": "typ dostępny w generatorze kuponów. Na karcie meczu "
                        "wygrał inny typ tego rynku",
        })
    # transparentność bramy: typy zdjęte z publikacji dostają uczciwy
    # wpis w rejestrze ("czemu nie ma typu"), zamiast znikać bez śladu
    for t in typy_poza_publikacja:
        if t["poza_publikacja"] == "limit_meczu":
            continue  # limit_meczu: typ i tak jest w generatorze (tylko_w_puli)
        para = (t["podmiot_id"], t["rynek_kod"])
        if para in opublikowane_pary or para in w_puli_dodane:
            continue
        w_puli_dodane.add(para)
        if t["poza_publikacja"] == "stare_dane":
            szczegol = (
                "ostatni mecz zawodnika był dawno temu, czekamy aż "
                "wróci do gry i da świeże dane"
            )
        else:
            kw = kwarantanna_rynkow.get(t["rynek_kod"], {})
            szczegol = (
                f"rynek chwilowo poza publikacją: ostatnie typy wchodziły w "
                f"{kw.get('hit', 0):.0%} przy deklarowanych {kw.get('sr_p', 0):.0%} "
                f"(próba: {kw.get('n', 0)}). Wróci, gdy kalibracja dogoni"
            )
        odrzucenia_out.append({
            "mecz_id": t["mecz_id"], "podmiot": t["podmiot"],
            "druzyna": t.get("druzyna", ""),
            "rynek_kod": t["rynek_kod"], "rynek": t["rynek"],
            "powod": t["poza_publikacja"],
            "szczegol": szczegol,
        })

    # pełne pokrycie p_model (backend-only, dla scannera STS) — emitujemy ZAWSZE,
    # także w trybie „0 okazji" niżej, bo model i tak policzył wszystkie linie
    _dump("sts_model.json", model_pokrycie)

    # RAPORT POKRYCIA (liga): parowanie z build_league + to, co dołożył
    # silnik — luka jest mierzona i zapisywana co cykl, nie ignorowana.
    # Jeden plik odpowiada na "czego nie gramy i dlaczego".
    def _dump_pokrycie() -> None:
        if not (tryb and tryb.pokrycie):
            return
        mecze_z_trendami = set(matches_out)
        pokrycie = {
            **tryb.pokrycie,
            "wygenerowano_ts": int(time.time()),
            # sparowane z Superbetem, ale statshub nie dał ani jednego trendu
            # (oferta propsów buków UK nie objęła meczu) — świadoma luka
            "mecze_bez_trendow": [
                f'{team_name.get(e.get("homeTeamId"), "?")} - '
                f'{team_name.get(e.get("awayTeamId"), "?")}'
                for e in events if e["id"] not in mecze_z_trendami
            ],
            "odrzucenia_per_powod": dict(sorted(
                Counter(o["powod"] for o in odrzucenia.values()).items(),
                key=lambda kv: -kv[1],
            )),
            "poza_publikacja_per_powod": dict(Counter(
                t["poza_publikacja"] for t in typy_poza_publikacja
            )),
            "typy": len(value_bets),
            "mecze_z_typami": len({b["mecz_id"] for b in value_bets}),
        }
        _dump("pokrycie_liga.json", pokrycie)
        print(f"Pokrycie ligi: {pokrycie['sparowane']}/{pokrycie['mecze_statshub']} "
              f"meczów sparowanych, {len(pokrycie['mecze_bez_trendow'])} bez trendów, "
              f"luka propsów Superbetu: {len(pokrycie['luka_superbet_propsy'])} meczów")

    # NIE degraduj aplikacji do pustej planszy: dopóki nie ma realnych okazji MŚ,
    # zostaw dotychczasowe dane (tryb pokazowy). Przełączamy na MŚ dopiero,
    # gdy propsy i kursy dają choć jedną okazję.
    if not value_bets:
        print(
            f"Na razie 0 okazji ({len(matches_out)} meczów, "
            f"{len(players_out)} zawodników ma propsy). Nie podmieniam danych "
            "aplikacji — czekam na pełne propsy/kursy."
        )
        # diagnoza "czemu 0": rozkład powodów odrzuceń zamiast ciszy
        powody: dict[str, int] = {}
        for o in odrzucenia.values():
            powody[o["powod"]] = powody.get(o["powod"], 0) + 1
        if powody:
            print("Powody odrzuceń: " + ", ".join(
                f"{k}={v}" for k, v in sorted(powody.items(), key=lambda x: -x[1])
            ))
        _dump("odrzucenia_zero_okazji.json", list(odrzucenia.values()))
        _dump_pokrycie()
        _rozlicz_i_zapisz([], [], niedostepni,
                          poza_publikacja=typy_poza_publikacja)
        return

    _dump_pokrycie()
    _dump("value_bets.json", value_bets)
    _dump("matches.json", list(matches_out.values()))
    _dump("players.json", list(players_out.values()))
    _dump("odds_superbet.json", odds_grid)   # siatka kursów do TOP POKRYCIA
    _dump("odrzucenia.json", odrzucenia_out)  # "czemu nie ma typu" per mecz
    print(f"Rejestr odrzuceń: {len(odrzucenia_out)} wpisów, "
          f"pomiar progów: {len(odrzucone_pomiar)} typów przy progu")
    # PULA LEGÓW pod generator kuponów NA ŻĄDANIE (frontend składa kupon w TS
    # z tej samej, przeanalizowanej puli — te same legi co automatyczne kupony).
    # Odchudzona o ciężkie pola (czynniki/uzasadnienie/rozkład) — zbędne do składania.
    _POLA_LEGA = (
        "mecz_id", "mecz", "kickoff_ts", "podmiot_id", "podmiot", "druzyna",
        "przeciwnik", "rynek_kod", "rynek", "linia", "strona", "kurs", "bukmacher",
        "p_model", "matchup", "rotacja", "miekka_linia", "swieze_sklady",
        "ev_pct", "ev_uk", "kurs_oczekiwany", "ryzyko", "oczekiwane_minuty",
        # wyzsza_linia/xi_sygnal/kurs_ref — muszą jechać aż do typy_log przez
        # kupony własne (generator na żądanie), inaczej te legi są ślepą
        # plamą w diagnostyce miękkich linii/sygnałów XI/marży UK (patrz
        # kupony.py:_leg_dict i rozliczanie.py:rozlicz, ten sam fix)
        "wyzsza_linia", "xi_sygnal", "kurs_ref",
        # pewnosc — do filtrowania w GeneratorKuponu jak backendowy styl "value"
        "pewnosc",
        # matchup_styl — flaga pełnych matchupów stylu; musi płynąć przez
        # kupony (własne i automatyczne) do typy_log, żeby diagnostyka
        # kategorii mierzyła skuteczność analogii stylu
        "matchup_styl",
        # ci — waga zaufania do p_model przy składaniu (kupony.py:_waga_modelu
        # / kuponBuilder.wagaModelu). BEZ tego generator na żądanie liczyłby
        # inne wagi (fallback z pewności) niż silnik automatyczny na tej
        # samej puli — cicha rozbieżność mimo parytetu algorytmów
        "ci",
    )
    _dump("legi_pool.json", [
        {**{k: b.get(k) for k in _POLA_LEGA}, "id": i}
        for i, b in enumerate(legi_pool_pub)
    ])
    n_dzis = len({b["mecz_id"] for b in legi_pool_pub
                  if b["kickoff_ts"] <= time.time() + kupony.OKNO_DZIS_S})
    print(f"Pula kuponów: {len(legi_pool_pub)} legów, meczów w oknie dziennym: {n_dzis}")
    fs = tempo.fallback_stats()
    n_total = fs["total_ok"] + fs["total_fallback"]
    n_spread = fs["spread_ok"] + fs["spread_fallback"]
    if fs["total_fallback"] or fs["spread_fallback"]:
        print(f"Tempo meczów: total zgadywany (2.6) {fs['total_fallback']}/{n_total}, "
              f"spread zgadywany (0.0) {fs['spread_fallback']}/{n_spread}")
    profil_kuponow = str(supa.get_key("kupony_profil") or "zbalansowany")
    if profil_kuponow not in ("bezpieczny", "zbalansowany", "agresywny"):
        profil_kuponow = "zbalansowany"
    if profil_kuponow != "zbalansowany":
        print(f"Profil kuponów: {profil_kuponow}")
    # ZMIERZONE kary korelacji legów z rozliczonych kuponów (zastępują zgadywane
    # 0.92/0.95/0.97; shrinkage do domyślnych przy małej próbie) — kupony dostają
    # uczciwsze szanse, bo legi z jednego meczu realnie nie padają niezależnie
    kary_kor = kupony.kary_korelacji_z_diagnostyki(
        rozliczanie.compute_kupony_diagnostyka(supa.get_key("kupony_log") or {})["korelacja"]
    )
    if kary_kor != kupony.KARY_DEFAULT:
        print(f"Kary korelacji (zmierzone): {kary_kor}")
    # ZMIERZONE wagi zaufania do p_model per kubełek pewności (z rozliczonych
    # typów) — składanie ufa modelowi dokładnie tyle, ile pokazały rozliczenia
    wagi_zauf: dict = {}
    try:
        pomiar_wag = rozliczanie.compute_wagi_zaufania(
            rozliczanie._migruj_log(supa.get_key("typy_log") or {})
        )
        wagi_zauf = kupony.wagi_zaufania_z_pomiaru(pomiar_wag)
        if wagi_zauf:
            print("Wagi zaufania (zmierzone): " + ", ".join(
                f"{k} {v:+.3f} (n={pomiar_wag[k]['n']}, "
                f"hit {pomiar_wag[k]['hit']:.0%} vs p {pomiar_wag[k]['sr_p']:.0%})"
                for k, v in wagi_zauf.items()
            ))
    except Exception as e:
        print(f"Wagi zaufania pominięte ({e})")
    kupony_list = kupony.build_kupony(
        value_bets, legi_pool_pub, profil=profil_kuponow, kary=kary_kor,
        wagi=wagi_zauf or None,
    )
    # znacznik: na ilu meczach kuponu składy były już POTWIERDZONE przy
    # budowie (mniejsze ryzyko anulowań/zwrotów niż na prognozach XI)
    for k in kupony_list:
        mids_k = {l["mecz_id"] for l in k["legi"]}
        k["mecze_lacznie"] = len(mids_k)
        k["mecze_ze_skladami"] = sum(1 for m in mids_k if m in conf_mids)
    if kupony_list:
        print("Kandydaci na kupony:", ", ".join(
            f"{k.get('horyzont', '?')[:5]} x{k.get('cel_label', k['cel'])} "
            f"(kurs {k['kurs_laczny']}, szansa {k['p_model']*100:.0f}%)"
            for k in kupony_list
        ))
    # publikacja kuponów idzie przez log (zamrożenie/anulowanie/rozliczenie)
    # wewnątrz _rozlicz_i_zapisz — kupony.json to aktywne kupony z logu
    _rozlicz_i_zapisz(value_bets, kupony_list, niedostepni,
                      conf_mids=conf_mids, odrzucone_pomiar=odrzucone_pomiar,
                      poza_publikacja=typy_poza_publikacja,
                      legi_pool=legi_pool_pub)
    _dump("meta.json", {
        "wygenerowano_ts": int(time.time()),
        "tryb": "liga" if tryb else "ms2026",
        "liga": tryb.liga_glowna if tryb else "Mistrzostwa Świata",
        "sezon": tryb.sezon if tryb else "2026",
        "zrodlo": "statshub (statystyki i historia) + Superbet (kursy)",
        "meczow_w_bazie": len(matches_out), "meczow_demo": len(matches_out),
        "meczow_kalibracja": 20, "okazji": len(value_bets),
        # zmierzone kary korelacji — generator kuponów na żądanie (frontend)
        # używa tych samych co automatyczne kupony w tym cyklu
        "kary_korelacji": kary_kor,
        # zmierzone delty wag zaufania per kubełek pewności — jw., frontend
        # stosuje te same co backend (kuponBuilder.wagaModelu)
        "wagi_zaufania": wagi_zauf,
    })
    print(f"OK: {len(matches_out)} meczów, {len(value_bets)} okazji, "
          f"{len(players_out)} zawodników.")


if __name__ == "__main__":
    main()
