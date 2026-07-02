"""Tryb MŚ 2026 — realne predykcje na mecze play-off + obieg kursów przez CSV.

Przepływ:
  1. `python -m footstats.jobs.backfill --league WC --season 2026` (rozegrane mecze MŚ)
  2. `python -m footstats.jobs.build_wc`
     → generuje pipeline/odds/ms2026_szablon.csv z predykcjami i uczciwymi kursami
     → jeżeli istnieje pipeline/odds/ms2026_kursy.csv (skopiowany szablon z wpisanymi
       kursami Superbet/Betclic/STS), scoruje go: prawdziwe okazje trafiają do aplikacji,
       a pełna ocena każdego wpisanego kursu do pipeline/odds/ms2026_ocena.csv
  3. wpisujesz kursy → uruchamiasz build_wc jeszcze raz → odświeżasz aplikację

Format CSV: średniki jako separator, przecinki dziesiętne (polski Excel).

UWAGA o próbie: na MŚ zawodnik ma za sobą 4-6 meczów turnieju — model świadomie
mocno korzysta z priorów grupowych, a pewność będzie przeważnie niska/średnia.
To uczciwe: turnieje reprezentacji to najtrudniejszy teren dla każdego modelu.
"""

from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from .. import store
from ..engine import MatchContext, PlayerHistory, score_player_market, RARE_MARKETS
from ..model import counts
from ..sources.sofascore import SofascoreSource, TOURNAMENTS
from ..sources import superbet
from .build_demo import (
    BOOKMAKERS, MARKET_NAMES_PL, PLAYER_MARKETS, STAT_COLUMNS, TEAM_MARKETS,
    WEB_DATA_DIR, build_player_index, build_team_index, compute_group_priors,
    compute_league_and_concessions, compute_referee_multipliers,
    compute_team_league_and_concessions, history_for, line_for_lambda, score_one,
)

ODDS_DIR = Path(__file__).resolve().parent.parent.parent / "odds"
SZABLON = ODDS_DIR / "ms2026_szablon.csv"
KURSY = ODDS_DIR / "ms2026_kursy.csv"
OCENA = ODDS_DIR / "ms2026_ocena.csv"

CSV_COLS = [
    "mecz_id", "mecz", "data", "podmiot_id", "podmiot", "druzyna",
    "rynek_kod", "rynek", "linia", "szansa_modelu_proc", "fair_kurs",
    "kurs_powyzej", "kurs_ponizej", "bukmacher",
]


def _pl(x: float, nd=2) -> str:
    return f"{x:.{nd}f}".replace(".", ",")


def _parse_pl(s: str | None) -> float | None:
    if s is None:
        return None
    s = str(s).strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_wc_store():
    matches = sorted(
        (m for m in store.matches_table().read_all() if m.get("league") == "WC"),
        key=lambda m: m["kickoff_ts"] or 0,
        reverse=True,
    )
    mids = {m["sofascore_id"] for m in matches}
    by_match_players = defaultdict(list)
    for p in store.player_stats_table().read_all():
        if p["match_sofascore_id"] in mids:
            by_match_players[p["match_sofascore_id"]].append(p)
    by_match_teams = defaultdict(dict)
    for t in store.team_stats_table().read_all():
        if t["match_sofascore_id"] in mids:
            by_match_teams[t["match_sofascore_id"]][t["team_sofascore_id"]] = t
    return matches, by_match_players, by_match_teams


def read_filled_odds() -> dict:
    """(mecz_id, podmiot_id, rynek_kod) -> wiersz z kursami (tylko wypełnione)."""
    if not KURSY.exists():
        return {}
    out = {}
    with KURSY.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            over = _parse_pl(row.get("kurs_powyzej"))
            under = _parse_pl(row.get("kurs_ponizej"))
            if over is None and under is None:
                continue
            key = (
                int(row["mecz_id"]),
                int(row["podmiot_id"]),
                row["rynek_kod"].strip(),
            )
            out[key] = {
                "linia": _parse_pl(row.get("linia")),
                "over": over,
                "under": under,
                "bukmacher": (row.get("bukmacher") or "").strip() or "—",
            }
    return out


def main():
    matches, by_match_players, by_match_teams = load_wc_store()
    if len(matches) < 20:
        print(f"Za mało meczów MŚ w magazynie ({len(matches)}). Uruchom backfill WC.")
        return

    train_ids = {m["sofascore_id"] for m in matches}
    player_index = build_player_index(matches, by_match_players)
    team_index = build_team_index(matches, by_match_teams)
    priors = compute_group_priors(player_index, train_ids)
    league_avg, concession = compute_league_and_concessions(
        matches, by_match_players, by_match_teams, train_ids
    )
    team_league_avg, team_concession = compute_team_league_and_concessions(
        matches, by_match_teams, train_ids
    )
    team_priors = {
        mk: counts.GroupPrior(mean_per90=max(team_league_avg[mk], 0.5), pseudo_matches=6.0)
        for mk in TEAM_MARKETS
    }
    refs = compute_referee_multipliers(matches, by_match_teams, train_ids)

    # nadchodzące mecze MŚ
    src = SofascoreSource()
    sid = src.find_season_id(TOURNAMENTS["WC"], "2026") or src.find_season_id(
        TOURNAMENTS["WC"], "26"
    )
    upcoming = [
        ev for ev in src.upcoming_events(TOURNAMENTS["WC"], sid)
        if ev.get("status", {}).get("type") == "notstarted"
    ]
    print(f"Nadchodzące mecze MŚ: {len(upcoming)}")

    # kursy Superbetu — automatycznie z ich API ofertowego
    try:
        sb_events = superbet.list_events(days_ahead=8)
        print(f"Superbet: {len(sb_events)} meczów w ofercie")
    except Exception as e:
        sb_events = []
        print(f"Superbet niedostępny ({e}) — działam bez automatycznych kursów")

    # ostatni skład każdej drużyny (z ostatnich 2 meczów w magazynie)
    team_last_players: dict[int, list[dict]] = defaultdict(list)
    for m in matches:  # od najnowszych
        for p in by_match_players.get(m["sofascore_id"], []):
            tid = p["team_sofascore_id"]
            if len([x for x in team_last_players[tid] if x["_mid"] != m["sofascore_id"]]) >= 40:
                continue
            team_last_players[tid].append({**p, "_mid": m["sofascore_id"]})

    filled = read_filled_odds()
    template_rows = []
    value_bets, matches_out, players_out = [], [], {}
    ocena_rows = []
    vb_id = 0

    for ev in upcoming:
        mid = ev["id"]
        ts = ev.get("startTimestamp") or int(time.time())
        home, away = ev["homeTeam"], ev["awayTeam"]
        match_label = f'{home["name"]} – {away["name"]}'
        data_str = time.strftime("%d.%m %H:%M", time.localtime(ts))
        match_out = {
            "id": mid, "liga": "MŚ", "sezon": "2026",
            "kolejka": (ev.get("roundInfo") or {}).get("name")
            or (ev.get("roundInfo") or {}).get("round"),
            "kickoff_ts": ts, "gospodarz": home["name"], "gosc": away["name"],
            "sedzia": None, "sedzia_mnoznik_fauli": 1.0, "okazje": [],
        }

        # automatyczne kursy Superbetu dla tego meczu
        sb_odds = {"players": {}, "teams": {"home": {}, "away": {}}}
        sb_ev = superbet.match_superbet_event(sb_events, home["name"], away["name"], ts)
        if sb_ev:
            parts = [p.strip() for p in (sb_ev.get("matchName") or "·").split("·")]
            try:
                sb_odds = superbet.fetch_stat_odds(sb_ev["eventId"], parts[0], parts[1])
                print(f"  {match_label}: kursy Superbet OK "
                      f"({len(sb_odds['players'])} zawodników)")
            except Exception as e:
                print(f"  {match_label}: błąd kursów Superbet: {e}")
        else:
            print(f"  {match_label}: brak w ofercie Superbetu")

        def emit(entity_id, entity_name, own_team, opp_name, mk, sm, hist_forma, prior_used):
            nonlocal vb_id
            key = (mid, entity_id, mk)
            fill = filled.get(key)
            # automatyczne kursy Superbetu (CSV, jeśli wypełniony, ma pierwszeństwo)
            if fill is None:
                if entity_id < 0:
                    slot = "home" if own_team == home["name"] else "away"
                    sb_lines = sb_odds["teams"][slot].get(mk, {})
                else:
                    sb_lines = sb_odds["players"].get(
                        superbet.norm_name(entity_name), {}
                    ).get(mk, {})
                if sb_lines:
                    fill = {"sb_lines": sb_lines, "bukmacher": "Superbet"}
            # wiersz szablonu (zawsze)
            template_rows.append({
                "mecz_id": mid, "mecz": match_label, "data": data_str,
                "podmiot_id": entity_id, "podmiot": entity_name, "druzyna": own_team,
                "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk],
                "linia": _pl(sm.line, 1),
                "szansa_modelu_proc": _pl(sm.p_over * 100, 0),
                "fair_kurs": _pl(sm.fair_odds_over),
                "kurs_powyzej": "", "kurs_ponizej": "", "bukmacher": "",
            })
            if entity_id not in players_out:
                players_out[entity_id] = {
                    "id": entity_id, "nazwa": entity_name,
                    "pozycja": "T" if entity_id < 0 else "?",
                    "druzyna": own_team,
                    "minuty_lacznie": int(sum(hist_forma.minutes)), "forma": {},
                }
            players_out[entity_id]["forma"][mk] = {
                "ostatnie": [int(c) for c in hist_forma.counts[:10]],
                "minuty": [int(mn) for mn in hist_forma.minutes[:10]],
                "srednia90": round(
                    float(np.sum(hist_forma.counts) / max(np.sum(hist_forma.minutes), 1) * 90.0), 2
                ),
            }
            if not fill:
                return
            # zbierz kandydatów: (linia, over, under) — z CSV jedna linia,
            # z Superbetu wszystkie kwotowane linie tego rynku
            if "sb_lines" in fill:
                candidates = [
                    (line, v.get("over"), v.get("under"))
                    for line, v in sorted(fill["sb_lines"].items())
                ]
            else:
                candidates = [(
                    fill["linia"] if fill["linia"] is not None else sm.line,
                    fill["over"], fill["under"],
                )]
            best_by_side = {}
            scored_by_side = {}
            scored = None
            for linia, over_k, under_k in candidates:
                trial = sm._rescore(linia, over_k, under_k)
                scored = scored or trial
                for a in trial.assessments:
                    if (a.side not in best_by_side
                            or a.rank_score > best_by_side[a.side].rank_score):
                        best_by_side[a.side] = a
                        scored_by_side[a.side] = (trial, linia, over_k, under_k)
            for a in best_by_side.values():
                trial, linia, over_k, under_k = scored_by_side[a.side]
                scored = trial
                fill_kursy = {"over": over_k, "under": under_k}
                vb_id += 1
                value_bets.append({
                    "id": vb_id, "mecz_id": mid, "mecz": match_label,
                    "kickoff_ts": ts,
                    "podmiot_typ": "druzyna" if entity_id < 0 else "zawodnik",
                    "podmiot_id": entity_id, "podmiot": entity_name,
                    "druzyna": own_team, "przeciwnik": opp_name,
                    "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk],
                    "linia": linia, "strona": a.side,
                    "kurs": fill_kursy["over"] if a.side == "powyzej" else fill_kursy["under"],
                    "bukmacher": fill["bukmacher"],
                    "p_model": a.model_prob, "p_rynku": a.implied_prob,
                    "fair_kurs": a.fair_odds, "edge_pp": a.edge_pp,
                    "ev_pct": a.ev_pct, "pewnosc": a.confidence,
                    "pewnosc_score": a.confidence_score, "ryzyko": a.risk,
                    "rank_score": a.rank_score,
                    "ci": [scored.ci_low, scored.ci_high],
                    "oczekiwane_minuty": scored.expected_minutes,
                    "lambda": scored.lam, "rozklad": scored.rozklad,
                    "czynniki": scored.factors, "uzasadnienie": scored.reasoning,
                })
                match_out["okazje"].append(vb_id)
            # ocena każdego sprawdzonego kursu (też negatywna — do pliku CSV)
            for linia, over_k, under_k in candidates:
                trial = sm._rescore(linia, over_k, under_k)
                p = trial.p_over
                for side, kurs in (("powyzej", over_k), ("ponizej", under_k)):
                    if kurs is None:
                        continue
                    p_side = p if side == "powyzej" else 1.0 - p
                    ev_pct = (p_side * kurs - 1.0) * 100.0
                    w_okazjach = (
                        side in best_by_side and scored_by_side[side][1] == linia
                    )
                    ocena_rows.append({
                        "mecz": match_label, "podmiot": entity_name,
                        "rynek": MARKET_NAMES_PL[mk], "linia": _pl(linia, 1),
                        "strona": side, "kurs": _pl(kurs),
                        "szansa_modelu_proc": _pl(p_side * 100, 0),
                        "fair_kurs": _pl(1.0 / max(p_side, 1e-6)),
                        "wartosc_proc": _pl(ev_pct, 1),
                        "werdykt": "OKAZJA" if w_okazjach
                        else ("blisko" if ev_pct > 0 else "bez wartości"),
                    })

        # --- zawodnicy obu drużyn ---
        for team, opp in ((home, away), (away, home)):
            tid = team["id"]
            seen = set()
            for p in team_last_players.get(tid, []):
                pid = p["sofascore_player_id"]
                if pid in seen:
                    continue
                seen.add(pid)
                pos = (p.get("position") or "M")[0]
                if pos == "G":
                    continue
                rows_all = player_index[pid]
                total_min = sum(r["minutes"] for r in rows_all)
                if total_min < 120:
                    continue
                for mk in PLAYER_MARKETS:
                    col = STAT_COLUMNS[mk]
                    hist_col = "fouls_committed" if mk == "yellow_card" else col
                    hist = history_for(rows_all, ts, hist_col)
                    if len(hist.counts) < 3:
                        continue
                    prior = priors["fouls_committed" if mk == "yellow_card" else mk][pos]
                    card_conv = None
                    if mk == "yellow_card":
                        from ..model.cards import player_card_conversion
                        card_conv = player_card_conversion(
                            sum(r.get("yellow_cards") or 0 for r in rows_all),
                            sum(r.get("fouls_committed") or 0 for r in rows_all),
                        )
                    conc = concession[mk].get(opp["id"], {})
                    ctx = MatchContext(
                        is_home=False, is_favourite=False, neutral_venue=True,
                        opponent_allowed_per90=conc.get("allowed_per_match")
                        or league_avg[mk],
                        league_avg_per90=league_avg[mk],
                        opponent_sample_matches=conc.get("games", 0),
                        official_started=None,
                        opponent_name=opp["name"],
                    )
                    probe = score_one(mk, 0.5, hist, prior, ctx, None, None, card_conv)
                    if mk != "yellow_card" and probe.lam < (
                        0.35 if mk not in RARE_MARKETS else 0.20
                    ):
                        continue
                    line = 0.5 if mk == "yellow_card" else line_for_lambda(probe.lam)
                    base = score_one(mk, line, hist, prior, ctx, None, None, card_conv)
                    base.rozklad = None if mk == "yellow_card" else counts.predict_match(
                        counts.fit_posterior(
                            np.array(hist.counts), np.array(hist.minutes),
                            np.array(hist.days_ago), prior,
                        ),
                        base.expected_minutes, 1.0,
                    ).distribution(8)
                    base._rescore = lambda l, o, u, _mk=mk, _h=hist, _pr=prior, _ctx=ctx, _cc=card_conv, _dist=base.rozklad: _with_dist(
                        score_one(_mk, l, _h, _pr, _ctx, o, u, _cc), _dist
                    )
                    forma_hist = hist if mk != "yellow_card" else history_for(rows_all, ts, col)
                    emit(pid, p["player_name"], team["name"], opp["name"], mk, base, forma_hist, prior)

        # --- drużyny ---
        for team, opp in ((home, away), (away, home)):
            tid = team["id"]
            rows_t = [r for r in team_index.get(tid, []) if (r["_match"]["kickoff_ts"] or 0) < ts]
            if len(rows_t) < 3:
                continue
            for mk, stat_name in TEAM_MARKETS.items():
                cvals = [float(r["stats"].get(stat_name) or 0) for r in rows_t]
                hist = PlayerHistory(
                    counts=cvals, minutes=[90.0] * len(rows_t),
                    days_ago=[max((ts - (r["_match"]["kickoff_ts"] or ts)) / 86400.0, 0.0) for r in rows_t],
                    started=[True] * len(rows_t),
                )
                conc = team_concession[mk].get(opp["id"], {})
                ctx = MatchContext(
                    is_home=False, is_favourite=False, neutral_venue=True,
                    opponent_allowed_per90=conc.get("allowed_per_match")
                    or team_league_avg[mk],
                    league_avg_per90=team_league_avg[mk],
                    opponent_sample_matches=conc.get("games", 0),
                    official_started=True, opponent_name=opp["name"],
                )
                probe = score_one(mk, 0.5, hist, team_priors[mk], ctx, None, None)
                line = line_for_lambda(probe.lam)
                base = score_one(mk, line, hist, team_priors[mk], ctx, None, None)
                base.rozklad = counts.predict_match(
                    counts.fit_posterior(
                        np.array(hist.counts), np.array(hist.minutes),
                        np.array(hist.days_ago), team_priors[mk],
                    ),
                    90.0, 1.0,
                ).distribution(max(8, int(base.lam * 1.8) + 4))
                base._rescore = lambda l, o, u, _mk=mk, _h=hist, _pr=team_priors[mk], _ctx=ctx, _dist=base.rozklad: _with_dist(
                    score_one(_mk, l, _h, _pr, _ctx, o, u), _dist
                )
                emit(-tid, team["name"], team["name"], opp["name"], mk, base, hist, team_priors[mk])

        matches_out.append(match_out)

    value_bets.sort(key=lambda b: -b["rank_score"])

    # --- zapis szablonu i oceny ---
    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    with SZABLON.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, delimiter=";")
        w.writeheader()
        w.writerows(template_rows)
    if ocena_rows:
        with OCENA.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(ocena_rows[0].keys()), delimiter=";")
            w.writeheader()
            w.writerows(ocena_rows)

    # --- zapis danych dla aplikacji ---
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    def dump(name, obj):
        (WEB_DATA_DIR / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    dump("value_bets.json", value_bets)
    dump("matches.json", matches_out)
    dump("players.json", list(players_out.values()))
    dump("meta.json", {
        "wygenerowano_ts": int(time.time()),
        "tryb": "ms2026",
        "liga": "Mistrzostwa Świata",
        "sezon": "2026",
        "zrodlo": "Sofascore (realne statystyki MŚ) + kursy Superbet (automatycznie)",
        "meczow_w_bazie": len(matches),
        "meczow_demo": len(matches_out),
        # kalibracja pochodzi z Premier League (ten sam rdzeń modelu) —
        # plik calibration.json celowo nie jest nadpisywany
        "meczow_kalibracja": 20,
        "okazji": len(value_bets),
    })
    print(
        f"OK: {len(matches_out)} nadchodzących meczów, {len(template_rows)} predykcji "
        f"w szablonie, {len(filled)} wpisanych kursów -> {len(value_bets)} okazji."
    )
    if not filled:
        print(f"Szablon: {SZABLON}\nSkopiuj go jako {KURSY.name}, wpisz kursy i uruchom ponownie.")


def _with_dist(sm, dist):
    sm.rozklad = dist
    return sm


if __name__ == "__main__":
    main()
