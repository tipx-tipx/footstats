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
import time
from collections import defaultdict

import numpy as np
from curl_cffi import requests

from ..engine import MatchContext, PlayerHistory, RARE_MARKETS, score_player_market
from ..model import counts
from ..sources import statshub, sts, superbet
from .build_demo import MARKET_NAMES_PL, WEB_DATA_DIR, line_for_lambda


def _sts_match_id(catalog: dict, home_en: str, away_en: str) -> str | None:
    """Znajdź STS id meczu po nazwach (statshub EN -> STS PL)."""
    en_pl = {v: k for k, v in superbet.TEAM_PL_EN.items()}
    h = superbet.norm_name(en_pl.get(home_en, home_en))
    a = superbet.norm_name(en_pl.get(away_en, away_en))
    # dopasowanie w obu kolejnościach (STS może mieć odwróconą stronę)
    return catalog.get((h, a)) or catalog.get((a, h))

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
):
    """Zbuduj PlayerHistory z recentGames i policz predykcję (bez kursów).

    Składy dwustopniowo:
      * lineupConfirmed (event) = skład OGŁOSZONY -> inPredictedLineup to twardy
        fakt: w XI (True) albo poza XI (False, scenariusz ławki),
      * skład nieogłoszony, ale statshub ma przewidywany (ktokolwiek w meczu
        ma inPredictedLineup=True) -> sygnał miękki (predicted_started),
      * brak przewidywanego składu dla meczu -> ignorujemy pole (sama historia).
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
    if lineup_confirmed:
        official, predicted = trend.in_predicted_lineup, None
    elif predicted_available:
        official, predicted = None, trend.in_predicted_lineup
    else:
        official, predicted = None, None
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

    # katalog STS (id meczów po nazwach drużyn — bez przeglądarki)
    try:
        sts_catalog = sts.match_ids_by_teams()
        print(f"STS: {len(sts_catalog)} meczów w katalogu")
    except Exception as e:
        sts_catalog = {}
        print(f"STS niedostępny: {e}")

    ev_by_id = {e["id"]: e for e in events}
    sb_cache: dict[int, dict] = {}
    sts_cache: dict[int, dict] = {}

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

    value_bets, matches_out, players_out = [], {}, {}
    vb_id = 0
    seen_player_market = set()  # (player_id, market) — statshub bywa zdublowany
    shot_lam = {}  # player_id -> {'shots': λ, 'sot': λ, 'info': {...}} — pod sugestie STS

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
                "sklady_ogloszone": lineup_confirmed.get(mid, False),
            }

        built, hist = score_from_trend(
            tr, tr.opponent_average,
            lineup_confirmed=lineup_confirmed.get(mid, False),
            predicted_available=predicted_available.get(mid, False),
        )
        if built is None:
            continue
        prior, ctx = built
        mk = tr.market_code

        probe = score_player_market(mk, 0.5, hist, prior, ctx, None, None,
                                    market_calibrated=True)
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

        # kursy STS dla tego meczu (WebSocket, po id z katalogu)
        sts_odds = sts_cache.get(mid)
        if sts_odds is None:
            sts_id = _sts_match_id(sts_catalog, home_name, away_name)
            if sts_id:
                try:
                    sts_odds = sts.fetch_stat_odds(sts_id, seconds=14)
                except Exception:
                    sts_odds = {"players": {}}
            else:
                sts_odds = {"players": {}}
            sts_cache[mid] = sts_odds
        sts_lines = sts_odds.get("players", {}).get(
            superbet.norm_name(tr.player_name), {}
        ).get(mk, {})

        # SCAL kursy z obu bukmacherów: linia -> strona -> (kurs, bukmacher)
        merged: dict = {}
        for src_name, src in (("Superbet", sb_lines), ("STS", sts_lines)):
            for l, v in src.items():
                slot = merged.setdefault(l, {})
                for side in ("over", "under"):
                    odd = v.get(side)
                    if odd and (side not in slot or odd > slot[side][0]):
                        slot[side] = (odd, src_name)

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
                                     market_calibrated=True)
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
            value_bets.append({
                "id": vb_id, "mecz_id": mid, "mecz": match_label, "kickoff_ts": ts,
                "podmiot_typ": "zawodnik", "podmiot_id": tr.player_id,
                "podmiot": tr.player_name, "druzyna": tr.team_name,
                "przeciwnik": tr.opponent_name,
                "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk],
                "linia": l, "strona": a.side,
                "kurs": kurs_wziety,
                "bukmacher": book,
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
    # statshub nie ma tych rynków, ale daje "strzały" i "celne". Ich różnica to
    # "nietrafione w światło bramki" = niecelne + zablokowane. Podział wg realnych
    # danych ligowych. Pokazujemy jako SUGESTIE (bez kursu) — kurs sprawdzasz w STS.
    OFF_SHARE, BLK_SHARE = 0.556, 0.444
    from scipy import stats as _st
    for pid, slot in shot_lam.items():
        lam_shots = slot.get("shots")
        info = slot.get("info")
        if not lam_shots or not info:
            continue
        lam_sot = slot.get("sot", lam_shots * 0.34)  # brak celnych → typowy udział 34%
        lam_not_on = max(lam_shots - lam_sot, 0.1)
        for mk, share in (("shots_off_target", OFF_SHARE), ("shots_blocked", BLK_SHARE)):
            lam = lam_not_on * share
            if lam < 0.5:
                continue  # za rzadkie na sensowną sugestię
            line = line_for_lambda(lam)
            thr = int(line)  # "powyżej line" = X > floor(line)
            p_over = float(_st.poisson.sf(thr, lam))
            if p_over < 0.5:
                continue  # sugerujemy tylko, gdy model widzi realną szansę na "powyżej"
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
                "pewnosc": "niska", "pewnosc_score": 30.0, "ryzyko": "wysokie",
                "rank_score": p_over,                  # sortowanie sugestii po szansie
                "ci": [None, None], "oczekiwane_minuty": None,
                "lambda": round(lam, 3),
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
            matches_out.setdefault(info["mid"], {}).setdefault("okazje", []).append(vb_id)

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
