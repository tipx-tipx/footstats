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
from collections import defaultdict
from dataclasses import asdict

import numpy as np
from curl_cffi import requests

from dataclasses import replace as dc_replace

from .. import supa
from ..engine import MatchContext, PlayerHistory, RARE_MARKETS, score_player_market
from ..model import betting, counts, kupony, matchup_lite
from ..sources import rotowire, scores365, statshub, superbet
from . import rozliczanie
from .build_demo import MARKET_NAMES_PL, WEB_DATA_DIR, line_for_lambda

# KURSY GŁÓWNE: wyłącznie Superbet. STS blokuje IP serwerowni (chmura = źródło
# prawdy, cron GitHub Actions), więc kursy STS w line-shoppingu powodowały
# rozjazd danych między przebiegiem lokalnym a chmurowym (typy "znikały").
# STS zostaje tylko jako adresat SUGESTII bez kursu (niecelne/zablokowane).
# Wróci do kursów głównych, gdy pipeline pójdzie z domowego IP (telefon/Pi).

SH_BASE = "https://www.statshub.com/api"
SH_HEADERS = {"Accept": "application/json", "Referer": "https://www.statshub.com/"}
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


def score_from_trend(
    trend: statshub.StatshubTrend,
    opp_avg_ref: float | None,
    lineup_confirmed: bool = False,
    predicted_available: bool = False,
    roto_pred: bool | None = None,
    roto_confirmed: bool = False,
    matchup_factor: float | None = None,
    matchup_opis: str = "",
):
    """Zbuduj PlayerHistory z recentGames i policz predykcję (bez kursów).

    Składy — hierarchia sygnałów:
      1. lineupConfirmed (statshub) LUB skład potwierdzony na Rotowire
         -> official_started: twardy fakt (w XI / scenariusz ławki),
      2. przewidywane XI z DWÓCH źródeł (statshub + Rotowire):
         zgoda -> mocny sygnał miękki; spór -> wracamy do historii minut,
      3. tylko jedno źródło -> jego prognoza jako sygnał miękki,
      4. brak prognoz -> sama historia.
    """
    now = int(time.time())
    hist = PlayerHistory(
        counts=trend.counts,
        minutes=trend.minutes,
        days_ago=[max((now - ts) / 86400.0, 0.0) for ts in trend.timestamps],
        started=trend.started,
    )
    if sum(1 for m in trend.minutes if m > 0) < 3:
        return None, hist
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
    # kontekst: średnia rywala względem ligi (jeśli statshub podał)
    ctx = MatchContext(
        is_home=trend.is_home,
        is_favourite=False,
        neutral_venue=True,
        opponent_allowed_per90=trend.opponent_average,
        league_avg_per90=trend.league_average,
        opponent_sample_matches=6 if trend.opponent_average else 0,
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
        return

    try:
        trends = statshub.fetch_event_trends([e["id"] for e in events])
    except Exception as e:
        print(f"statshub chwilowo niedostępny ({e}) — pomijam ten cykl, dane bez zmian.")
        return
    print(f"Trendów propsów: {len(trends)} "
          f"({len(set(t.player_id for t in trends))} zawodników)")
    if not trends:
        print("statshub nie ma jeszcze propsów na te mecze (ładują się ~24-48 h "
              "przed). Uruchom ponownie bliżej meczu.")
        return

    # --- BIBLIOTEKA HISTORII: mecze bez propsów statshub (np. ćwierćfinały) ---
    # statshub wystawia propsy ~24-48 h przed meczem, a Superbet kwotuje dużo
    # wcześniej (i wtedy kursy są najmiększe). Historia zawodnika nie zależy
    # od nadchodzącego meczu — bierzemy jego najświeższy trend z ROZEGRANYCH
    # meczów MŚ i przepinamy na nowy event (rywal/kontekst neutralne, składy
    # z Rotowire, kursy z Superbetu).
    covered = {t.event_id for t in trends}
    uncovered = [
        e for e in events
        if e["id"] not in covered and e.get("homeTeamId") and e.get("awayTeamId")
    ]
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
        save_trend_lib({
            f"{t.player_id}:{t.market_code}": asdict(t) for t in lib.values()
        })

        # 3) mecze bez propsów statshub: przepnij najświeższe trendy z biblioteki
        team_by_id: dict[int, str] = {}
        for t in lib.values():
            if t.team_id:
                team_by_id[t.team_id] = t.team_name
            if t.opponent_id:
                team_by_id[t.opponent_id] = t.opponent_name
        n_lib = 0
        for e in uncovered:
            hid, aid = e["homeTeamId"], e["awayTeamId"]
            if not team_by_id.get(hid) or not team_by_id.get(aid):
                continue  # nieznana drużyna = brak historii i pusta karta meczu
            for (pid, mk), t in lib.items():
                if t.team_id not in (hid, aid):
                    continue
                opp_id = aid if t.team_id == hid else hid
                trends.append(dc_replace(
                    t,
                    event_id=e["id"],
                    opponent_id=opp_id,
                    opponent_name=team_by_id.get(opp_id, ""),
                    is_home=(t.team_id == hid),
                    opponent_average=None, opponent_rank=None,
                    in_predicted_lineup=False, ref_odds=[],
                ))
                n_lib += 1
        if n_lib:
            print(f"Biblioteka historii ({len(lib)} trendów w banku): "
                  f"+{n_lib} przepiętych na mecze bez propsów statshub")

        # 4) drużyny wciąż BEZ historii (statshub skasował przed powstaniem
        #    banku): pełne statystyki meczowe z 365Scores (minuty, strzały,
        #    faule, faule na zawodniku, przechwyty; odbiór — brak w 365)
        MARKETY_365_FULL = ("shots", "sot", "fouls_committed", "fouls_won",
                            "interceptions")
        pokryte_teamy = {t.team_id for t in trends}
        braki: list[tuple[dict, int, int, bool, str, str]] = []
        for e in uncovered:
            hid, aid = e["homeTeamId"], e["awayTeamId"]
            slug_parts = str(e.get("slug", "")).replace("-vs-", "|").split("|")
            if len(slug_parts) != 2:
                continue
            home_nm = slug_parts[0].replace("-", " ").title()
            away_nm = slug_parts[1].rsplit("-", 1)[0].replace("-", " ").title()
            if hid not in pokryte_teamy:
                braki.append((e, hid, aid, True, home_nm, away_nm))
            if aid not in pokryte_teamy:
                braki.append((e, aid, hid, False, away_nm, home_nm))
        if braki:
            cids365 = scores365.competitor_ids(
                sorted({b[4] for b in braki})
            )
            n_365 = 0
            hist_cache: dict[str, list] = {}
            for e, tid, opp_tid, is_home, team_nm, opp_nm in braki:
                cid = cids365.get(rotowire._norm(team_nm))
                if not cid:
                    continue
                if team_nm not in hist_cache:
                    hist_cache[team_nm] = scores365.team_match_history(cid, 6)
                games = hist_cache[team_nm]
                if len(games) < 3:
                    continue
                gracze = sorted({p for _, st in games for p in st})
                for pkey in gracze:
                    wpisy = [(ts, st.get(pkey)) for ts, st in games]
                    zagrane = [w for w in wpisy if w[1] and w[1].get("minutes", 0) > 0]
                    if len(zagrane) < 3:
                        continue
                    for mk in MARKETY_365_FULL:
                        c_l, m_l, tss, st_l = [], [], [], []
                        for ts_g, rec in wpisy:
                            if rec is None:
                                continue
                            c_l.append(float(rec.get(mk, 0)))
                            m_l.append(float(rec.get("minutes", 0)))
                            tss.append(int(ts_g))
                            st_l.append(bool(rec.get("started")))
                        trends.append(statshub.StatshubTrend(
                            player_id=900_000_000 + abs(hash(pkey)) % 90_000_000,
                            player_name=pkey.title(),
                            position="M",
                            team_id=tid, team_name=team_nm,
                            opponent_id=opp_tid, opponent_name=opp_nm,
                            is_home=is_home, market_code=mk, line=0.5,
                            in_predicted_lineup=False,
                            league_average=None, opponent_average=None,
                            opponent_rank=None, total_ranks=None,
                            event_id=e["id"],
                            counts=c_l, minutes=m_l,
                            timestamps=tss, started=st_l,
                            game_positions=[""] * len(c_l),
                        ))
                        n_365 += 1
            if n_365:
                print(f"365Scores pełne staty: +{n_365} trendów dla drużyn "
                      f"bez historii statshub ({len(hist_cache)} drużyn)")
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
    real_split_reserved: set = set()
    try:
        shots_trends = [t for t in trends if t.market_code == "shots"]
        team_names = sorted({t.team_name for t in shots_trends if t.team_name})
        cids = scores365.competitor_ids(team_names)
        hist365: dict[str, list] = {}
        for name in team_names:
            cid = cids.get(rotowire._norm(name))
            if cid:
                hist365[name] = scores365.team_shot_history(cid, n_games=6)
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
                if mk2 in ("shots_blocked", "shots_off_target"):
                    # rezerwacja: jest prawdziwa historia -> fallbackowy
                    # szacunek (strzały − celne) ma się NIE odzywać, nawet
                    # gdy scoring odrzuci rynek jako zbyt rzadki
                    real_split_reserved.add((t.player_id, mk2))
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

    # kursy Superbetu
    try:
        sb_events = superbet.list_events(days_ahead=8)
    except Exception as e:
        sb_events = []
        print(f"Superbet niedostępny: {e}")

    # samokalibracja: zmierzone odchylenia szans per rynek (od n>=25 rozliczonych)
    try:
        bias_map = rozliczanie.market_bias()
        if bias_map:
            print(f"Kalibracja z rozliczeń: {bias_map}")
    except Exception:
        bias_map = {}

    ev_by_id = {e["id"]: e for e in events}
    sb_cache: dict[int, dict] = {}

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
    shot_lam = {}  # player_id -> {'shots': λ, 'sot': λ, 'info': {...}} — pod sugestie STS
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
            matches_out[mid] = {
                "id": mid, "liga": "MŚ", "sezon": "2026",
                "kolejka": "Ćwierćfinał", "kickoff_ts": ts,
                "gospodarz": home_name, "gosc": away_name,
                "sedzia": None, "sedzia_mnoznik_fauli": 1.0, "okazje": [],
                "sklady_ogloszone": lineup_confirmed.get(mid, False)
                or (
                    rotowire.is_confirmed(roto, home_name)
                    and rotowire.is_confirmed(roto, away_name)
                ),
            }

        mf, mo = matchup_lite.matchup_lite_factor(
            tr.market_code,
            tr.game_positions[:6],
            opp_players_by_team.get((mid, tr.opponent_id), []),
        )
        built, hist = score_from_trend(
            tr, tr.opponent_average,
            lineup_confirmed=lineup_confirmed.get(mid, False),
            predicted_available=predicted_available.get(mid, False),
            roto_pred=rotowire.predicted_status(roto, tr.team_name, tr.player_name),
            roto_confirmed=rotowire.is_confirmed(roto, tr.team_name),
            matchup_factor=mf if mf != 1.0 else None,
            matchup_opis=mo,
        )
        if built is None:
            continue
        prior, ctx = built
        mk = tr.market_code

        probe = score_player_market(mk, 0.5, hist, prior, ctx, None, None,
                                    market_calibrated=True,
                                    market_bias=bias_map.get(mk, 1.0))
        if probe.lam < (0.35 if mk not in RARE_MARKETS else 0.2):
            continue
        line = line_for_lambda(probe.lam)

        # zapamiętaj λ strzałów/celnych — do sugestii niecelne/zablokowane (STS)
        if mk in ("shots", "sot"):
            slot = shot_lam.setdefault(tr.player_id, {})
            slot[mk] = probe.lam
            slot["info"] = {
                "name": tr.player_name, "team": tr.team_name,
                "opp": tr.opponent_name, "mid": mid, "ts": ts,
                "match": match_label, "minutes": int(sum(tr.minutes)),
                "position": tr.position or "?",
            }

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

        # kursy Superbetu dla tego zawodnika/rynku
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

        # zapisz formę zawodnika (dla UI)
        if tr.player_id not in players_out:
            players_out[tr.player_id] = {
                "id": tr.player_id, "nazwa": tr.player_name,
                "pozycja": tr.position or "?", "druzyna": tr.team_name,
                "minuty_lacznie": int(sum(tr.minutes)), "forma": {},
            }
        players_out[tr.player_id]["forma"][mk] = {
            "ostatnie": [int(c) for c in tr.counts[:10]],
            "minuty": [int(m) for m in tr.minutes[:10]],
            "srednia90": round(
                float(np.sum(tr.counts) / max(np.sum(tr.minutes), 1) * 90.0), 2
            ),
        }

        if not merged:
            continue  # brak realnego kursu — nie tworzymy okazji

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
            for side_key, side_pl in (("over", "powyzej"), ("under", "ponizej")):
                sv = slot.get(side_key)
                if not sv:
                    continue
                odd = sv[0]
                p_side = sm.p_over if side_key == "over" else 1.0 - sm.p_over
                implied = betting.implied_prob_one_sided(odd)
                if (
                    1.10 <= odd <= 2.60
                    and p_side >= 0.55
                    and p_side * odd - 1.0 >= -0.12
                    and (sm.ci_high - sm.ci_low) <= 0.35
                    and abs(p_side - implied) <= betting.MAX_MODEL_MARKET_DIVERGENCE
                    and (implied <= 0 or p_side / implied <= betting.MAX_RELATIVE_DIVERGENCE)
                ):
                    legi_pool.append({
                        "id": 0, "mecz_id": mid, "mecz": match_label,
                        "kickoff_ts": ts, "podmiot_id": tr.player_id,
                        "podmiot": tr.player_name, "druzyna": tr.team_name,
                        "przeciwnik": tr.opponent_name,
                        "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk], "linia": l,
                        "strona": side_pl, "kurs": odd,
                        "bukmacher": sv[1], "p_model": round(p_side, 4),
                        "ci": [sm.ci_low, sm.ci_high],
                        "oczekiwane_minuty": sm.expected_minutes,
                        "czynniki": sm.factors, "uzasadnienie": sm.reasoning,
                        "lambda": sm.lam,
                    })
            for a in sm.assessments:
                if a.side not in best_by_side or a.rank_score > best_by_side[a.side].rank_score:
                    best_by_side[a.side] = a
                    chosen[a.side] = (sm, l, slot)
        for a in best_by_side.values():
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
                "pewnosc": a.confidence, "pewnosc_score": a.confidence_score,
                "ryzyko": a.risk, "rank_score": a.rank_score,
                "ci": [sm.ci_low, sm.ci_high],
                "oczekiwane_minuty": sm.expected_minutes, "lambda": sm.lam,
                "rozklad": dist, "czynniki": sm.factors, "uzasadnienie": sm.reasoning,
            })
            matches_out[mid]["okazje"].append(vb_id)

    # --- SUGESTIE bez kursów: niecelne / zablokowane (rynki STS, blokowany w chmurze) ---
    # Preferujemy PRAWDZIWĄ historię per strzał z 365Scores (real_split — pełny
    # scoring modelu: prior, minuty, składy, matchup). Gdy 365 nie ma zawodnika,
    # fallback: szacunek "strzały − celne" z podziałem wg danych ligowych.
    OFF_SHARE, BLK_SHARE = 0.556, 0.444
    from scipy import stats as _st

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
            # linia bazowa musi być prawdopodobna; wyższe warianty pokazujemy
            # już od ~38% (fair ~2.6 — typowy zakres kursów STS)
            if p_over_l < (0.5 if linia_s == 0.5 else 0.38):
                break
            _push_sugestia(pid, mk, real["info"], sm_r.lam, p_over_l, linia_s, {
                "pewnosc": "srednia", "pewnosc_score": 45.0, "ryzyko": "wysokie",
                "ci": [sm_r.ci_low, sm_r.ci_high],
                "oczekiwane_minuty": sm_r.expected_minutes,
                "rozklad": dist_r, "czynniki": sm_r.factors,
                "uzasadnienie": sm_r.reasoning,
            })

    for pid, slot in shot_lam.items():
        lam_shots = slot.get("shots")
        info = slot.get("info")
        if not lam_shots or not info:
            continue
        lam_sot = slot.get("sot", lam_shots * 0.34)  # brak celnych → typowy udział 34%
        lam_not_on = max(lam_shots - lam_sot, 0.1)
        for mk, share in (("shots_off_target", OFF_SHARE), ("shots_blocked", BLK_SHARE)):
            if (pid, mk) in real_split_reserved or (pid, mk) in real_split:
                continue  # jest prawdziwa historia 365 — szacunek zbędny
            lam = lam_not_on * share
            if lam < 0.5:
                continue  # za rzadkie na sensowną sugestię
            for line in (0.5, 1.5, 2.5):
                thr = int(line)  # "powyżej line" = X > floor(line)
                p_over = float(_st.poisson.sf(thr, lam))
                if p_over < (0.5 if line == 0.5 else 0.38):
                    break
                _push_sugestia(pid, mk, info, lam, p_over, line, {
                "pewnosc": "niska", "pewnosc_score": 30.0, "ryzyko": "wysokie",
                "ci": [None, None], "oczekiwane_minuty": None,
                "rozklad": [float(_st.poisson.pmf(k, lam)) for k in range(6)]
                + [float(_st.poisson.sf(5, lam))],
                "czynniki": {}, "uzasadnienie": {
                    "czynniki": [{
                        "nazwa": "Szacunek z modelu",
                        "opis": f"Oczekiwane {lam:.2f} na mecz (z: strzały − celne, "
                        f"podział {int(share*100)}% wg danych ligowych)",
                        "mnoznik": None,
                    }],
                    "oczekiwana_liczba": round(lam, 2), "rynek_rzadki": True,
                },
            })

    # --- PEWNIAKI: top typy każdego meczu z pełnego skanu (bez wymogu value) ---
    # Żeby każdy mecz miał co pokazać, nawet gdy rynek dograł kursy i value
    # zniknęło. Kandydaci przeszli pełny scoring + bezpieczniki rozbieżności.
    juz_opublikowane = {
        (b["podmiot_id"], b["rynek_kod"], b["linia"], b["strona"])
        for b in value_bets
    }
    per_mecz: dict[int, int] = {}
    for b in sorted(legi_pool, key=lambda x: -x["p_model"]):
        if per_mecz.get(b["mecz_id"], 0) >= 3:
            continue
        klucz = (b["podmiot_id"], b["rynek_kod"], b["linia"], b["strona"])
        if klucz in juz_opublikowane:
            continue
        juz_opublikowane.add(klucz)
        per_mecz[b["mecz_id"]] = per_mecz.get(b["mecz_id"], 0) + 1
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
            "kurs": b["kurs"], "bukmacher": b["bukmacher"],
            "p_model": b["p_model"], "p_rynku": None,
            "fair_kurs": round(1.0 / max(b["p_model"], 1e-6), 2),
            "edge_pp": None,
            "ev_pct": round((b["p_model"] * b["kurs"] - 1.0) * 100.0, 1),
            "pewnosc": "wysoka" if ci_w <= 0.18 else "srednia",
            "pewnosc_score": 55.0, "ryzyko": "srednie",
            "rank_score": b["p_model"],
            "ci": ci, "oczekiwane_minuty": b.get("oczekiwane_minuty"),
            "lambda": round(b.get("lambda", 0.0), 3), "rozklad": None,
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
        return

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    def dump(name, obj):
        (WEB_DATA_DIR / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    dump("value_bets.json", value_bets)
    dump("matches.json", list(matches_out.values()))
    dump("players.json", list(players_out.values()))
    n_dzis = len({b["mecz_id"] for b in legi_pool
                  if b["kickoff_ts"] <= time.time() + kupony.OKNO_DZIS_S})
    print(f"Pula kuponów: {len(legi_pool)} legów, meczów w oknie dziennym: {n_dzis}")
    kupony_list = kupony.build_kupony(value_bets, legi_pool)
    dump("kupony.json", kupony_list)
    if kupony_list:
        print("Kupony:", ", ".join(
            f"{k.get('horyzont', '?')[:5]} x{k.get('cel_label', k['cel'])} "
            f"(kurs {k['kurs_laczny']}, szansa {k['p_model']*100:.0f}%)"
            for k in kupony_list
        ))
    try:
        wyniki = rozliczanie.rozlicz(value_bets)
        dump("typy_wyniki.json", wyniki)
        p = wyniki["podsumowanie"]
        print(f"Typy: {p['opublikowane']} w logu, {p['rozliczone']} rozliczonych, "
              f"{p['trafione']} trafionych, ROI flat {p['roi_flat']:+.2f} j.")
    except Exception as ex:
        print(f"Rozliczanie pominięte ({ex})")
        dump("typy_wyniki.json", {"podsumowanie": None, "po_rynku": [], "ostatnie": []})
    dump("meta.json", {
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
