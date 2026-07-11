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
from collections import defaultdict
from dataclasses import asdict

from scipy import stats as _stats

import numpy as np
from curl_cffi import requests

from dataclasses import replace as dc_replace

from .. import supa
from ..engine import (
    MatchContext, PlayerHistory, RARE_MARKETS, apply_bias, score_player_market,
)
from ..model import betting, context, counts, koncesje, kupony, matchup_lite, tempo
from ..sources import eloratings, rotowire, scores365, statshub, superbet
from . import rozliczanie
from .build_demo import MARKET_NAMES_PL, WEB_DATA_DIR, line_for_lambda

# KURSY GŁÓWNE: wyłącznie Superbet. STS blokuje IP serwerowni (chmura = źródło
# prawdy, cron GitHub Actions), więc kursy STS w line-shoppingu powodowały
# rozjazd danych między przebiegiem lokalnym a chmurowym (typy "znikały").
# STS zostaje tylko jako adresat SUGESTII bez kursu (niecelne/zablokowane).
# Wróci do kursów głównych, gdy pipeline pójdzie z domowego IP (telefon/Pi).

SH_BASE = "https://www.statshub.com/api"
SH_HEADERS = {"Accept": "application/json", "Referer": "https://www.statshub.com/"}


def _dump(name: str, obj) -> None:
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (WEB_DATA_DIR / name).write_text(
        json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _rozlicz_i_zapisz(
    value_bets: list[dict],
    kupony_list: list[dict],
    niedostepni: set[int] | None = None,
    conf_mids: set[int] | None = None,
) -> None:
    """Rozliczanie + zapis wyników. Wywoływane w KAŻDYM cyklu — także gdy
    statshub nie ma propsów (rozliczenia nie mogą czekać na nowe typy).

    kupony.json = AKTYWNE kupony z logu (zamrożone przy publikacji), a nie
    świeżo wygenerowana lista — dzięki temu strona /kupony pokazuje dokładnie
    to, co potem trafi do historii, i nic nie zmienia się między cyklami.
    Przy błędzie NIE nadpisujemy plików — zostają wyniki z poprzedniego cyklu.
    """
    try:
        wyniki = rozliczanie.rozlicz(
            value_bets, kupony_list, niedostepni, conf_mids=conf_mids
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
# nazwy reprezentacji EN -> PL (do dopasowania z Superbetem)
EN_PL = {v: k for k, v in superbet.TEAM_PL_EN.items()}


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


def past_wc_event_ids(days_back: int = 25) -> list[int]:
    """ID rozegranych meczów MŚ z ostatnich dni (do biblioteki historii)."""
    now = int(time.time())
    out: dict[int, bool] = {}
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
                out[ev["id"]] = True
    return list(out)


def group_prior_from_context(trend: statshub.StatshubTrend) -> counts.GroupPrior:
    """Prior grupowy z ligowej średniej statshub (fallback, gdy mała próba)."""
    la = trend.league_average
    # leagueAverage bywa w skali drużynowej dla części rynków — traktujemy
    # ostrożnie: prior o umiarkowanej sile, średnia z historii zawodnika.
    played = [c for c, m in zip(trend.counts, trend.minutes) if m > 0]
    base = float(np.mean(played)) if played else (la or 0.8)
    return counts.GroupPrior(mean_per90=max(base, 0.15), pseudo_matches=5.0)


def profil_sedziow(
    events: list[dict], team_name: dict[int, str]
) -> dict[int, dict]:
    """Profil sędziego per nadchodzący mecz: {mid: {sedzia, mnoznik, n}}.

    Źródło: 365Scores — officials (obsada znana 1-2 dni przed meczem) +
    suma fauli wszystkich zawodników z rozegranych meczów MŚ tego sędziego.
    Mnożnik = średnia z ilorazów (faule meczu / OCZEKIWANE faule tej pary
    drużyn) — oczekiwania z pozostałych meczów tych drużyn, żeby nie mylić
    stylu sędziego ze stylem drużyn (Maroko fauluje dużo u każdego arbitra).
    Mecze z dogrywką pomijane (staty obejmują 120 min i zawyżałyby profil).
    Wyniki per mecz cache'owane w Supabase (sedziowie_cache).
    """
    cache = supa.get_key("sedziowie_cache") or {}
    zmieniony = False
    for g in scores365.finished_games_by_competition():
        gid = str(g["id"])
        druzyny = [g.get("home") or "", g.get("away") or ""]
        if gid in cache:
            # starsze wpisy sprzed pola "druzyny" — uzupełnij przy okazji
            if not cache[gid].get("druzyny") and all(druzyny):
                cache[gid]["druzyny"] = druzyny
                zmieniony = True
            continue
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
        supa.put_key("sedziowie_cache", cache)

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
    sched = scores365.scheduled_games_by_competition()
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


# start MŚ 2026 (2026-06-08 UTC, kilka dni zapasu przed 1. meczem) — granica
# między "sezonem klubowym" (prior) a "turniejem" (aktualizacja posteriora)
WC_START_TS = 1_780_876_800
# wygaszanie historii przedturniejowej w priorze (sezon klubowy jest długi)
PRIOR_TAU_DNI = 240.0
# minimalna/maksymalna siła priora klubowego (w ekwiwalencie pełnych meczów)
PRIOR_MIN_MECZE, PRIOR_MAX_MECZE = 4.0, 12.0


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
    # próbie przedturniejowej — dotychczasowy słaby prior + cała historia
    kp = klub_prior(trend, now, opp_w)
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
    opp_n = 6 if trend.opponent_average else 0
    koncesja_opis = ""
    if opp_allowed is None and koncesje_tab is not None:
        kc = koncesje_tab.lookup(
            trend.opponent_name, trend.market_code, trend.position,
            elo_map=elo_map, team_name=trend.team_name,
        )
        if kc:
            opp_allowed, opp_avg, opp_n = kc
            kub = koncesje.kubelek_pozycji(trend.position) or "tej formacji"
            koncesja_opis = (
                f"Na tym turnieju zawodnicy z formacji „{kub}” notują przeciw "
                f"{trend.opponent_name} ~{opp_allowed:.2f} na 90 min przy "
                f"normie {opp_avg:.2f} (próba: {opp_n} meczów)"
            )
    ctx = MatchContext(
        is_home=trend.is_home,
        is_favourite=bool(spread_teamu is not None and spread_teamu > 0.15),
        neutral_venue=True,
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
        matchup_factor=matchup_factor,
        matchup_opis=matchup_opis,
    )
    return (prior, ctx), hist


def main():
    events = upcoming_wc_events()
    print(f"Nadchodzące mecze MŚ (statshub): {len(events)}")
    if not events:
        print("Brak nadchodzących meczów MŚ w statshub.")
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
    # sygnał przewidywanego/oficjalnego składu (in_predicted_lineup) jest
    # wiarygodny per (mecz, zawodnik) TYLKO dla trendów z żywego feedu —
    # dokładane niżej trendy z banku/365 mają tam zawsze False i bez tej
    # mapy wyglądałyby przy ogłoszonym składzie jak "wszyscy poza XI"
    xi_zywy: dict[tuple[int, int], bool] = {}
    for t in trends:
        if t.event_id and t.player_id:
            k_xi = (t.event_id, t.player_id)
            xi_zywy[k_xi] = xi_zywy.get(k_xi, False) or t.in_predicted_lineup
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
            past_ids = past_wc_event_ids()
            for i in range(0, len(past_ids), 8):
                for t in statshub.fetch_event_trends(past_ids[i:i + 8]):
                    _merge(t)
        for t in trends:
            _merge(t)
        bank_recs = {
            f"{t.player_id}:{t.market_code}": asdict(t) for t in lib.values()
        }
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

    # uczestnicy MŚ (znormalizowani) — do ważenia próby siłą rywala
    wc_names = {
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
            bank_recs, wc_names=None, min_ts=WC_START_TS,
        )
        n_prof = len({k[0] for k in koncesje_tab._obs})
        print(f"Profil rywali: {n_prof} drużyn, "
              f"{sum(len(v) for v in koncesje_tab._obs.values())} obserwacji")
    except Exception as e:
        koncesje_tab = None
        print(f"Profil rywali pominięty ({e})")

    # kursy Superbetu
    try:
        sb_events = superbet.list_events(days_ahead=8)
    except Exception as e:
        sb_events = []
        print(f"Superbet niedostępny: {e}")

    # Elo reprezentacji (eloratings.net, cache w Supabase) — ciągła waga
    # próby siłą rywala + syntetyczny spread, gdy brak kursów 1X2
    elo_map = eloratings.get_ratings()
    print(f"Elo: {len(elo_map)} reprezentacji" if elo_map
          else "Elo niedostępne — wagi próby z listy uczestników MŚ")

    # profil sędziów: obsada + średnia fauli/mecz vs średnia turnieju
    try:
        sedzia_by_mid = profil_sedziow(events, team_name)
        _ev_by = {e["id"]: e for e in events}
        for mid_s, s in sedzia_by_mid.items():
            _e = _ev_by.get(mid_s, {})
            lbl = (f"{team_name.get(_e.get('homeTeamId'), '?')} – "
                   f"{team_name.get(_e.get('awayTeamId'), '?')}")
            print(f"  sędzia {lbl}: {s['sedzia']}"
                  + (f" (faule ×{s['mnoznik']}, {s['n']} m.)"
                     if s.get("mnoznik") else " (bez historii MŚ)"))
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

    ev_by_id = {e["id"]: e for e in events}
    sb_cache: dict[int, dict] = {}
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
            # na karcie meczu pokazujemy mnożnik PO shrinkage (1-2 mecze
            # próby to za słaby dowód na "×1,26") — spójnie ze scoringiem
            matches_out[mid] = {
                "id": mid, "liga": "MŚ", "sezon": "2026",
                "kolejka": "Ćwierćfinał", "kickoff_ts": ts,
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
        )
        if built is None:
            continue
        prior, ctx = built
        mk = tr.market_code
        # trigger rotacyjny: zawodnik w (przewidywanym) XI bez ani jednego
        # występu na turnieju — rynek często nie zdążył dograć jego linii
        gral_na_turnieju = any(
            ts_g >= WC_START_TS and m_g > 0
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
                "info": {
                    "name": tr.player_name, "team": tr.team_name,
                    "opp": tr.opponent_name, "mid": mid, "ts": ts,
                    "match": match_label,
                },
            }

        # kursy Superbetu dla tego zawodnika/rynku (mecz pobrany wyżej)
        sb_lines = {}
        if sb_odds:
            sb_lines = sb_odds.get("players", {}).get(
                superbet.norm_name(tr.player_name), {}
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
        for l, slot in sorted(merged.items()):
            over_odd = slot.get("over", (None,))[0]
            under_odd = slot.get("under", (None,))[0]
            sm = score_player_market(mk, l, hist, prior, ctx,
                                     over_odd, under_odd,
                                     market_calibrated=True,
                                     market_bias=bias_map.get(mk, 1.0))
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
                if (
                    (pewny or perelka or niszowa)
                    and len(tr.counts) >= 5  # pewniak nie powstaje z 2 meczów
                    and (sm.ci_high - sm.ci_low) <= 0.35
                    and abs(p_side - implied) <= max_div
                    and (implied <= 0 or p_side / implied <= max_rel)
                ):
                    legi_pool.append({
                        "id": 0, "mecz_id": mid, "mecz": match_label,
                        "kickoff_ts": ts, "podmiot_id": tr.player_id,
                        "podmiot": tr.player_name, "druzyna": tr.team_name,
                        "przeciwnik": tr.opponent_name,
                        "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk], "linia": l,
                        "strona": side_pl, "kurs": odd,
                        "bukmacher": sv[1], "p_model": round(p_side, 4),
                        "matchup": matchup_typ, "rotacja": rotacja,
                        "xi_sygnal": xi_sygnal,
                        "swieze_sklady": mid in swieze_mids,
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
            kurs_ref = None
            if (
                tr.ref_odds
                and abs(l - tr.line) < 1e-6
                and (tr.odds_type == "over") == (a.side == "powyzej")
            ):
                kurs_ref = round(statistics.median(tr.ref_odds), 2)
            # OKAZJA Z KURSEM, gdy jest DOWÓD miękkiej linii: Superbet płaci
            # >= 0.10 ponad konsensus UK (gdy dostępny) LUB >= 12% ponad kurs
            # wynikający z JEGO WŁASNEJ siatki pozostałych linii (1a — line
            # shopping bez zewnętrznych źródeł). Bez dowodu — typ zostaje
            # w puli pewniaków.
            odstaje_zewn = kurs_ref is not None and kurs_wziety - kurs_ref >= 0.10
            fw_a = fair_wewn.get(l)
            oczek_a = (
                round(fw_a * (1.0 - betting.DEFAULT_ONE_SIDED_MARGIN), 2)
                if fw_a else None
            )
            miekka_a = oczek_a is not None and kurs_wziety >= oczek_a * 1.12
            if not odstaje_zewn and not miekka_a:
                continue
            value_bets.append({
                "id": vb_id, "mecz_id": mid, "mecz": match_label, "kickoff_ts": ts,
                "podmiot_typ": "zawodnik", "podmiot_id": tr.player_id,
                "podmiot": tr.player_name, "druzyna": tr.team_name,
                "przeciwnik": tr.opponent_name,
                "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk],
                "linia": l, "strona": a.side,
                "kurs": kurs_wziety,
                "bukmacher": book,
                "kurs_ref": kurs_ref,
                "p_model": a.model_prob, "p_rynku": a.implied_prob,
                "fair_kurs": a.fair_odds, "edge_pp": a.edge_pp, "ev_pct": a.ev_pct,
                "matchup": float(sm.factors.get("rywal", 1.0) or 1.0) >= 1.12,
                "rotacja": rotacja, "xi_sygnal": xi_sygnal,
                "miekka_linia": miekka_a,
                "kurs_oczekiwany": oczek_a if miekka_a else None,
                "pewnosc": a.confidence, "pewnosc_score": a.confidence_score,
                "ryzyko": a.risk, "rank_score": a.rank_score,
                "ci": [sm.ci_low, sm.ci_high],
                "oczekiwane_minuty": sm.expected_minutes, "lambda": sm.lam,
                "rozklad": dist, "czynniki": sm.factors, "uzasadnienie": sm.reasoning,
            })
            matches_out[mid]["okazje"].append(vb_id)

    # --- SUGESTIE bez kursów: niecelne / zablokowane (rynki STS, blokowany w chmurze) ---
    # WYŁĄCZNIE z prawdziwej historii per strzał z 365Scores (real_split —
    # pełny scoring modelu: prior, minuty, składy, matchup). Dawny fallback
    # "strzały − celne z podziałem ligowym" USUNIĘTY: rozliczenia pokazały
    # hit 23.5% przy śr. p 55.2% (real_split: 48.8% przy 58.1%) — szacunek
    # był czystym szumem i psuł kalibrację oraz zaufanie do sekcji.
    def _push_sugestia(pid, mk, info, lam, p_over, line, extra):
        nonlocal vb_id
        vb_id += 1
        value_bets.append({
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
        })
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
            })

    # --- PEWNIAKI: najlepszy typ KAŻDEGO rynku dla każdego meczu ---
    # Nie top-N po samej szansie (wygrywałyby zawsze zwykłe strzały 0.5) —
    # użytkownik chce widzieć pełne spektrum statystyk: strzały, celne,
    # zza pola, celne zza pola, faule, wywalczone, odbiory, przechwyty...
    # Kandydaci przeszli pełny scoring + bezpieczniki rozbieżności.
    juz_opublikowane = {
        (b["podmiot_id"], b["rynek_kod"], b["linia"], b["strona"])
        for b in value_bets
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
    for b in do_emisji:
        klucz = (b["podmiot_id"], b["rynek_kod"], b["linia"], b["strona"])
        if klucz in juz_opublikowane:
            continue
        juz_opublikowane.add(klucz)
        ci = b.get("ci") or [None, None]
        ci_w = (ci[1] - ci[0]) if ci[0] is not None else 1.0
        vb_id += 1
        value_bets.append({
            "id": vb_id, "mecz_id": b["mecz_id"], "mecz": b["mecz"],
            "kickoff_ts": b["kickoff_ts"], "podmiot_typ": "zawodnik",
            "podmiot_id": b["podmiot_id"], "podmiot": b["podmiot"],
            "druzyna": b.get("druzyna", ""), "przeciwnik": b.get("przeciwnik", ""),
            "rynek_kod": b["rynek_kod"], "rynek": b["rynek"],
            "linia": b["linia"], "strona": b["strona"],
            "pewniak": True,
            "wyzsza_linia": bool(b.get("wyzsza_linia")),
            "matchup": bool(b.get("matchup")),
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
        })
        matches_out.setdefault(b["mecz_id"], {}).setdefault("okazje", []).append(vb_id)

    value_bets.sort(key=lambda b: -b["rank_score"])

    # NIE degraduj aplikacji do pustej planszy: dopóki nie ma realnych okazji MŚ,
    # zostaw dotychczasowe dane (tryb pokazowy). Przełączamy na MŚ dopiero,
    # gdy propsy i kursy dają choć jedną okazję.
    if not value_bets:
        print(
            f"Na razie 0 okazji MŚ ({len(matches_out)} meczów, "
            f"{len(players_out)} zawodników ma propsy). Nie podmieniam danych "
            "aplikacji — czekam na pełne propsy/kursy ćwierćfinałów."
        )
        _rozlicz_i_zapisz([], [], niedostepni)
        return

    _dump("value_bets.json", value_bets)
    _dump("matches.json", list(matches_out.values()))
    _dump("players.json", list(players_out.values()))
    _dump("odds_superbet.json", odds_grid)   # siatka kursów do TOP POKRYCIA
    n_dzis = len({b["mecz_id"] for b in legi_pool
                  if b["kickoff_ts"] <= time.time() + kupony.OKNO_DZIS_S})
    print(f"Pula kuponów: {len(legi_pool)} legów, meczów w oknie dziennym: {n_dzis}")
    profil_kuponow = str(supa.get_key("kupony_profil") or "zbalansowany")
    if profil_kuponow not in ("bezpieczny", "zbalansowany", "agresywny"):
        profil_kuponow = "zbalansowany"
    if profil_kuponow != "zbalansowany":
        print(f"Profil kuponów: {profil_kuponow}")
    kupony_list = kupony.build_kupony(value_bets, legi_pool, profil=profil_kuponow)
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
    _rozlicz_i_zapisz(value_bets, kupony_list, niedostepni, conf_mids=conf_mids)
    _dump("meta.json", {
        "wygenerowano_ts": int(time.time()), "tryb": "ms2026",
        "liga": "Mistrzostwa Świata", "sezon": "2026",
        "zrodlo": "statshub (statystyki i historia) + Superbet (kursy)",
        "meczow_w_bazie": len(matches_out), "meczow_demo": len(matches_out),
        "meczow_kalibracja": 20, "okazji": len(value_bets),
    })
    print(f"OK: {len(matches_out)} meczów, {len(value_bets)} okazji, "
          f"{len(players_out)} zawodników.")


if __name__ == "__main__":
    main()
