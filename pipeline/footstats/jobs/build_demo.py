"""Budowa danych DEMO dla aplikacji webowej.

Bierze realny wycinek danych z lokalnego magazynu (backfill Sofascore) i:
  1. liczy priory grupowe (pozycja x rynek) oraz średnie ligowe,
  2. liczy czynniki rywala ("ile dopuszcza") i mnożniki sędziów,
  3. wybiera najnowsze mecze jako "nadchodzące" (demo w przerwie ligowej),
  4. scoruje wszystkie rynki silnikiem modelu,
  5. generuje przykładowe kursy bukmacherskie (fair odds + marża + szum) —
     wyraźnie oznaczone w UI jako DEMO,
  6. robi uczciwą mini-kalibrację: predykcje na meczach holdout vs realne wyniki,
  7. zapisuje JSON-y do web/src/data/demo/.

Użycie:
    python -m footstats.jobs.build_demo
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from .. import store
from ..engine import MatchContext, PlayerHistory, score_player_market, RARE_MARKETS
from ..model import betting, counts, matchup

WEB_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "web" / "src" / "data" / "demo"

# Klucze zapisane w BIEŻĄCYM uruchomieniu — patrz komentarz przy tej samej
# zmiennej w build_wc_fast.py. Manifest chroni push_supabase.py przed
# wypchnięciem na produkcję plików ze świeżego `git checkout` (stare dane
# commitowane w repo), gdy main() przerwie się przed dumpem.
_generated_this_run: set[str] = set()

PLAYER_MARKETS = [
    "shots", "sot", "shots_outside_box", "sot_outside_box", "headed_shots",
    "headed_sot", "fh_shots", "fh_sot", "fouls_committed", "fouls_won",
    "tackles", "interceptions", "yellow_card", "offsides",
    "shots_blocked", "shots_off_target",
]
STAT_COLUMNS = {
    "shots": "shots", "sot": "shots_on_target", "shots_outside_box": "shots_outside_box",
    "sot_outside_box": "sot_outside_box", "headed_shots": "headed_shots",
    "headed_sot": "headed_sot", "fh_shots": "fh_shots", "fh_sot": "fh_sot",
    "fouls_committed": "fouls_committed", "fouls_won": "fouls_won",
    "tackles": "tackles", "interceptions": "interceptions",
    "yellow_card": "yellow_cards", "offsides": "offsides",
    "shots_blocked": "shots_blocked", "shots_off_target": "shots_off_target",
}
TEAM_MARKETS = {
    "team_fouls": "Fouls", "team_cards": "Yellow cards",
    "team_shots": "Total shots", "team_sot": "Shots on target",
}
MARKET_NAMES_PL = {
    "shots": "Strzały", "sot": "Strzały celne", "shots_outside_box": "Strzały zza pola karnego",
    "sot_outside_box": "Celne zza pola karnego", "headed_shots": "Strzały głową",
    "headed_sot": "Celne strzały głową", "fh_shots": "Strzały w 1. połowie",
    "fh_sot": "Celne w 1. połowie", "fouls_committed": "Faule popełnione",
    "fouls_won": "Faule wywalczone", "tackles": "Odbiory", "interceptions": "Przechwyty",
    "yellow_card": "Żółta kartka", "offsides": "Spalone",
    "shots_blocked": "Strzały zablokowane", "shots_off_target": "Strzały niecelne",
    "team_fouls": "Faule drużyny", "team_cards": "Kartki drużyny",
    "team_shots": "Strzały drużyny", "team_sot": "Strzały celne drużyny",
    "team_goals": "Gole drużyny", "team_corners": "Rzuty rożne drużyny",
}
BOOKMAKERS = ["Superbet", "Betclic", "STS"]

N_DEMO_MATCHES = 10       # najnowsze mecze udają "nadchodzące"
N_CALIB_MATCHES = 20      # kolejne mecze do mini-kalibracji
MIN_MINUTES_FOR_PROFILE = 250.0


def load_store():
    matches = sorted(
        store.matches_table().read_all(), key=lambda m: m["kickoff_ts"] or 0, reverse=True
    )
    players = store.player_stats_table().read_all()
    teams = store.team_stats_table().read_all()
    by_match_players = defaultdict(list)
    for p in players:
        by_match_players[p["match_sofascore_id"]].append(p)
    by_match_teams = defaultdict(dict)
    for t in teams:
        by_match_teams[t["match_sofascore_id"]][t["team_sofascore_id"]] = t
    return matches, by_match_players, by_match_teams


def build_player_index(matches, by_match_players):
    """player_id -> lista występów (od najnowszych), z timestampem meczu."""
    idx = defaultdict(list)
    for m in matches:  # matches już posortowane malejąco po czasie
        for p in by_match_players.get(m["sofascore_id"], []):
            idx[p["sofascore_player_id"]].append({**p, "_match": m})
    return idx


def build_team_index(matches, by_match_teams):
    """team_id -> lista meczów (od najnowszych) ze statystykami drużynowymi."""
    idx = defaultdict(list)
    for m in matches:
        for tid, stats in by_match_teams.get(m["sofascore_id"], {}).items():
            idx[tid].append({"stats": stats, "_match": m})
    return idx


def compute_team_league_and_concessions(matches, by_match_teams, train_ids):
    """Średnie ligowe rynków drużynowych + ile rywal 'wymusza' u przeciwników."""
    league_vals = defaultdict(list)
    forced = defaultdict(lambda: defaultdict(list))  # mk -> team -> [stat rywala]
    for m in matches:
        mid = m["sofascore_id"]
        if mid not in train_ids:
            continue
        stats = by_match_teams.get(mid, {})
        for tid, s in stats.items():
            opp = m["away_team_id"] if tid == m["home_team_id"] else m["home_team_id"]
            for mk, name in TEAM_MARKETS.items():
                v = s.get(name)
                if v is None:
                    continue
                league_vals[mk].append(float(v))
                forced[mk][opp].append(float(v))  # statystyka wykonana PRZECIW opp
    league_avg = {mk: (float(np.mean(v)) if v else 1.0) for mk, v in league_vals.items()}
    concession = {}
    for mk in TEAM_MARKETS:
        concession[mk] = {
            tid: {"allowed_per_match": float(np.mean(vals)), "games": len(vals)}
            for tid, vals in forced[mk].items()
            if vals
        }
    return league_avg, concession


def compute_group_priors(player_index, train_ids):
    """Priory (pozycja x rynek) z per-90 zawodników o sensownej próbie."""
    rates = defaultdict(lambda: defaultdict(list))  # market -> pos -> [per90]
    for pid, rows in player_index.items():
        rows_t = [r for r in rows if r["match_sofascore_id"] in train_ids]
        total_min = sum(r["minutes"] for r in rows_t)
        if total_min < MIN_MINUTES_FOR_PROFILE:
            continue
        pos = (rows_t[0].get("position") or "M")[0]
        for mk, col in STAT_COLUMNS.items():
            total = sum(r.get(col) or 0 for r in rows_t)
            rates[mk][pos].append(total / total_min * 90.0)
    priors = {}
    for mk in PLAYER_MARKETS:
        priors[mk] = {}
        for pos in ("G", "D", "M", "F"):
            arr = np.array(rates[mk].get(pos, []))
            priors[mk][pos] = counts.estimate_group_prior(arr) if len(arr) else counts.GroupPrior(0.2, 6.0)
    return priors


def compute_league_and_concessions(matches, by_match_players, by_match_teams, train_ids):
    """Średnie ligowe per rynek + czynniki 'ile rywal dopuszcza'."""
    train = [m for m in matches if m["sofascore_id"] in train_ids]
    # per-market: allowed[team_id] = suma statystyki wykonanej PRZECIWKO drużynie
    allowed = defaultdict(lambda: defaultdict(float))
    games = defaultdict(int)
    league_totals = defaultdict(float)
    for m in train:
        mid = m["sofascore_id"]
        for side_team, opp_team in (
            (m["home_team_id"], m["away_team_id"]),
            (m["away_team_id"], m["home_team_id"]),
        ):
            games[side_team] += 1
        for p in by_match_players.get(mid, []):
            # statystyka zawodnika liczy się "przeciwko" drużynie przeciwnej
            opp = m["away_team_id"] if p["team_sofascore_id"] == m["home_team_id"] else m["home_team_id"]
            for mk, col in STAT_COLUMNS.items():
                v = p.get(col) or 0
                allowed[mk][opp] += v
                league_totals[mk] += v
    n_matches = max(len(train), 1)
    league_avg = {mk: league_totals[mk] / (2.0 * n_matches) for mk in STAT_COLUMNS}
    concession = {}
    for mk in STAT_COLUMNS:
        concession[mk] = {}
        for team_id, total in allowed[mk].items():
            g = max(games[team_id], 1)
            per_match = total / g
            concession[mk][team_id] = {
                "allowed_per_match": per_match,
                "factor": per_match / league_avg[mk] if league_avg[mk] > 0 else 1.0,
                "games": g,
            }
    return league_avg, concession


def compute_team_style(matches, by_match_players, by_match_teams, train_ids):
    """Bogaty profil stylu drużyny (per mecz) — zasila silnik matchupów.

    Zbiera: drybling, pojedynki, faule, dośrodkowania, długie piłki, posiadanie,
    rożne, kartki, wysokość linii (spalone wymuszane), bloki, udział strzałów
    rywala z dystansu, słabość w powietrzu, zagrożenie flankami.
    """
    acc = defaultdict(lambda: defaultdict(list))  # tid -> metric -> [wartości per mecz]

    for m in matches:
        mid = m["sofascore_id"]
        if mid not in train_ids:
            continue
        players = by_match_players.get(mid, [])
        ts = by_match_teams.get(mid, {})
        home, away = m["home_team_id"], m["away_team_id"]

        # agregaty zawodnicze per drużyna
        agg = defaultdict(lambda: defaultdict(float))
        for p in players:
            t = p["team_sofascore_id"]
            agg[t]["contests"] += p.get("contests") or 0
            agg[t]["duels"] += p.get("duels_won") or 0
            agg[t]["crosses"] += p.get("crosses") or 0
            agg[t]["long_balls"] += p.get("long_balls") or 0
            agg[t]["aerial_lost"] += p.get("aerial_lost") or 0
            agg[t]["shots_blocked"] += p.get("shots_blocked") or 0
            agg[t]["shots_outside"] += p.get("shots_outside_box") or 0
            agg[t]["shots"] += p.get("shots") or 0
            # zagrożenie flankami: drybling+dośrodkowania graczy z danej strony
            dp = (p.get("detailed_position") or "").upper()
            threat = (p.get("contests") or 0) + (p.get("crosses") or 0)
            if any(dp.startswith(x) for x in ("L", "ML", "DL")):
                agg[t]["left_threat"] += threat
            elif any(dp.startswith(x) for x in ("R", "MR", "DR")):
                agg[t]["right_threat"] += threat

        for tid, opp in ((home, away), (away, home)):
            a, ao = agg[tid], agg[opp]
            acc[tid]["contests"].append(a["contests"])
            acc[tid]["duels"].append(a["duels"])
            acc[tid]["crosses"].append(a["crosses"])
            acc[tid]["long_balls"].append(a["long_balls"])
            acc[tid]["left_threat"].append(a["left_threat"])
            acc[tid]["right_threat"].append(a["right_threat"])
            # bloki WYKONANE przez tid = strzały rywala, które zostały zablokowane
            acc[tid]["blocks_made"].append(ao["shots_blocked"])
            # słabość w powietrzu tid = przegrane pojedynki górą jego zawodników
            acc[tid]["weak_aerial"].append(a["aerial_lost"])
            # udział strzałów rywala z dystansu (deep block tid)
            if ao["shots"] > 0:
                acc[tid]["outside_share"].append(ao["shots_outside"] / ao["shots"])
            s = ts.get(tid, {})
            if s.get("Fouls") is not None:
                acc[tid]["fouls"].append(float(s["Fouls"]))
            if s.get("Yellow cards") is not None:
                acc[tid]["cards"].append(float(s["Yellow cards"]))
            if s.get("Ball possession") is not None:
                try:
                    acc[tid]["possession"].append(float(str(s["Ball possession"]).replace("%", "")))
                except ValueError:
                    pass
            if s.get("Corner kicks") is not None:
                acc[tid]["corners"].append(float(s["Corner kicks"]))
            opp_off = ts.get(opp, {}).get("Offsides")
            if opp_off is not None:
                acc[tid]["offsides_forced"].append(float(opp_off))

    def summarize(tid_metrics):
        out = {}
        n = max((len(v) for v in tid_metrics.values()), default=0)
        for metric, vals in tid_metrics.items():
            if vals:
                out[metric] = float(np.mean(vals))
        out["_n"] = n
        return out

    return {tid: summarize(mets) for tid, mets in acc.items()}


def compute_referee_multipliers(matches, by_match_teams, train_ids):
    fouls = defaultdict(list)
    cards = defaultdict(list)
    for m in matches:
        if m["sofascore_id"] not in train_ids or not m.get("referee"):
            continue
        stats = by_match_teams.get(m["sofascore_id"], {})
        tot_fouls = sum(float(s.get("Fouls") or 0) for s in stats.values())
        tot_cards = sum(float(s.get("Yellow cards") or 0) for s in stats.values())
        if tot_fouls > 0:
            fouls[m["referee"]].append(tot_fouls)
        if tot_cards >= 0:
            cards[m["referee"]].append(tot_cards)
    all_f = [v for arr in fouls.values() for v in arr]
    all_c = [v for arr in cards.values() for v in arr]
    avg_f = np.mean(all_f) if all_f else 22.0
    avg_c = np.mean(all_c) if all_c else 4.0
    out = {}
    for ref in fouls:
        out[ref] = {
            "fouls_multiplier": float(np.mean(fouls[ref]) / avg_f),
            "cards_multiplier": float(np.mean(cards[ref]) / avg_c) if cards.get(ref) else 1.0,
            "games": len(fouls[ref]),
        }
    return out


def history_for(player_rows, ref_ts, market_col):
    """PlayerHistory względem czasu meczu referencyjnego (tylko wcześniejsze mecze)."""
    prior_rows = [r for r in player_rows if (r["_match"]["kickoff_ts"] or 0) < ref_ts]
    return PlayerHistory(
        counts=[float(r.get(market_col) or 0) for r in prior_rows],
        minutes=[float(r["minutes"]) for r in prior_rows],
        days_ago=[max((ref_ts - (r["_match"]["kickoff_ts"] or ref_ts)) / 86400.0, 0.0) for r in prior_rows],
        started=[bool(r.get("started")) for r in prior_rows],
    )


def demo_odds_book(rng, p_model_over: float):
    """Przykładowe kursy JEDNEGO bukmachera: szum w skali log-odds
    (realistyczny przy małych p), potem marża."""
    p = float(np.clip(p_model_over, 0.02, 0.98))
    logit = np.log(p / (1.0 - p)) + rng.normal(0.0, 0.22)
    p_book = float(np.clip(1.0 / (1.0 + np.exp(-logit)), 0.06, 0.94))
    margin = rng.uniform(0.05, 0.09)
    over = round(1.0 / (p_book * (1.0 + margin / 2.0) + 1e-9), 2)
    under = round(1.0 / ((1.0 - p_book) * (1.0 + margin / 2.0) + 1e-9), 2)
    over = float(np.clip(over, 1.05, 15.0))
    under = float(np.clip(under, 1.05, 15.0))
    one_sided = rng.random() < 0.25  # część linii tylko "powyżej" (jak STS)
    return over, (None if one_sided else under)


def line_for_lambda(lam: float) -> float:
    if lam < 0.75:
        return 0.5
    return float(np.floor(lam)) + 0.5


def score_one(mk, line, hist, prior, ctx, over_odds, under_odds, card_conv=None):
    return score_player_market(
        market_code=mk, line=line, history=hist, group_prior=prior, ctx=ctx,
        over_odds=over_odds, under_odds=under_odds,
        market_calibrated=mk in ("shots", "sot", "fouls_committed", "tackles", "fouls_won"),
        card_conversion=card_conv,
    )


# forma zawodnika w UI ma pokazywać FAKTYCZNĄ statystykę rynku (dla kartek: kartki)


def main() -> None:
    """Cienki wrapper: gwarantuje zapis manifestu (_manifest.json) na KAŻDYM
    wyjściu z _main_impl (sukces, wczesny return, wyjątek)."""
    _generated_this_run.clear()
    try:
        _main_impl()
    finally:
        WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
        (WEB_DATA_DIR / "_manifest.json").write_text(
            json.dumps({"keys": sorted(_generated_this_run)}, ensure_ascii=False),
            encoding="utf-8",
        )


def _main_impl():
    rng = np.random.default_rng(2026)
    matches, by_match_players, by_match_teams = load_store()
    if len(matches) < N_DEMO_MATCHES + N_CALIB_MATCHES + 10:
        print(f"Za mało meczów w magazynie ({len(matches)}). Uruchom najpierw backfill.")
        return

    demo_matches = matches[:N_DEMO_MATCHES]
    calib_matches = matches[N_DEMO_MATCHES : N_DEMO_MATCHES + N_CALIB_MATCHES]
    demo_ids = {m["sofascore_id"] for m in demo_matches}
    calib_ids = {m["sofascore_id"] for m in calib_matches}
    train_ids = {m["sofascore_id"] for m in matches} - demo_ids - calib_ids

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
    refs = compute_referee_multipliers(matches, by_match_teams, train_ids | calib_ids)
    team_style = compute_team_style(matches, by_match_players, by_match_teams, train_ids)

    def _per90(rows, col):
        c = sum(r.get(col) or 0 for r in rows)
        mn = sum(r["minutes"] for r in rows)
        return (c / mn * 90.0) if mn > 0 else 0.0

    def build_player_style(pid, pos):
        rows = player_index.get(pid, [])
        heights = [r.get("height") or 0 for r in rows if r.get("height")]
        dp = next((r.get("detailed_position") for r in rows if r.get("detailed_position")), "")
        return matchup.PlayerStyle(
            position=pos,
            detailed_position=dp,
            height=int(np.median(heights)) if heights else 0,
            is_dribbler=matchup.is_dribbler(_per90(rows, "contests")),
            is_target_man=matchup.is_target_man(
                int(np.median(heights)) if heights else 0, _per90(rows, "aerial_won")),
            is_weak_1v1=matchup.is_weak_1v1(_per90(rows, "dribbled_past")),
            is_holdup=matchup.is_holdup(_per90(rows, "duels_won")),
            is_playmaker=matchup.is_playmaker(_per90(rows, "key_passes"), pos),
            takes_setpieces=matchup.takes_setpieces(_per90(rows, "setpiece_shots")),
        )

    def build_opponent_style(opp_id):
        st = team_style.get(opp_id, {})
        return matchup.OpponentStyle(
            sample=st.get("_n", 0),
            contests_pm=st.get("contests"),
            duels_pm=st.get("duels"),
            fouls_pm=st.get("fouls"),
            crosses_pm=st.get("crosses"),
            long_balls_pm=st.get("long_balls"),
            possession=st.get("possession"),
            corners_pm=st.get("corners"),
            offsides_forced=st.get("offsides_forced"),
            blocks_made_pm=st.get("blocks_made"),
            outside_share_conceded=st.get("outside_share"),
            cards_pm=st.get("cards"),
            weak_aerial=st.get("weak_aerial"),
            left_threat_pm=st.get("left_threat"),
            right_threat_pm=st.get("right_threat"),
        )

    # ---------------- mini-kalibracja (holdout) ----------------
    calib_records = defaultdict(list)  # market -> [(p_over, wynik 0/1)]
    for m in calib_matches:
        mid = m["sofascore_id"]
        ts = m["kickoff_ts"] or 0
        for p in by_match_players.get(mid, []):
            if p["minutes"] < 30:
                continue
            pid = p["sofascore_player_id"]
            pos = (p.get("position") or "M")[0]
            if pos == "G":
                continue
            opp_id = m["away_team_id"] if p["team_sofascore_id"] == m["home_team_id"] else m["home_team_id"]
            is_home = p["team_sofascore_id"] == m["home_team_id"]
            for mk in ("shots", "sot", "fouls_committed", "fouls_won", "tackles", "interceptions"):
                col = STAT_COLUMNS[mk]
                hist = history_for(player_index[pid], ts, col)
                if len(hist.counts) < 4:
                    continue
                conc = concession[mk].get(opp_id, {})
                ctx = MatchContext(
                    is_home=is_home, is_favourite=is_home,
                    opponent_allowed_per90=(conc.get("allowed_per_match") or league_avg[mk]) / 1.0,
                    league_avg_per90=league_avg[mk],
                    opponent_sample_matches=conc.get("games", 0),
                    referee_fouls_multiplier=(refs.get(m.get("referee")) or {}).get("fouls_multiplier"),
                    referee_cards_multiplier=(refs.get(m.get("referee")) or {}).get("cards_multiplier"),
                    referee_sample_matches=(refs.get(m.get("referee")) or {}).get("games", 0),
                    official_started=bool(p.get("started")),
                )
                sm = score_one(mk, 0.5 if league_avg[mk] < 1.5 else 1.5, hist, priors[mk][pos], ctx, None, None)
                actual = (p.get(col) or 0) > sm.line
                calib_records[mk].append((sm.p_over, 1.0 if actual else 0.0))

    calibration = {"rynki": [], "razem": None}
    all_pairs = []
    for mk, pairs in calib_records.items():
        arr = np.array(pairs)
        if len(arr) < 20:
            continue
        all_pairs.extend(pairs)
        brier = float(np.mean((arr[:, 0] - arr[:, 1]) ** 2))
        bins = []
        for lo in np.arange(0.0, 1.0, 0.125):
            m_ = (arr[:, 0] >= lo) & (arr[:, 0] < lo + 0.125)
            if m_.sum() >= 5:
                bins.append({
                    "p_pred": float(np.mean(arr[m_, 0])),
                    "p_real": float(np.mean(arr[m_, 1])),
                    "n": int(m_.sum()),
                })
        calibration["rynki"].append({
            "kod": mk, "nazwa": MARKET_NAMES_PL[mk], "n": len(arr),
            "brier": round(brier, 4), "kubelki": bins,
        })
    if all_pairs:
        arr = np.array(all_pairs)
        calibration["razem"] = {
            "n": len(arr),
            "brier": round(float(np.mean((arr[:, 0] - arr[:, 1]) ** 2)), 4),
        }

    # ---------------- okazje demo ----------------
    value_bets = []
    matches_out = []
    players_out = {}
    vb_id = 0
    for m in demo_matches:
        mid = m["sofascore_id"]
        ts = m["kickoff_ts"] or 0
        match_out = {
            "id": mid,
            "liga": m["league"], "sezon": m["season"], "kolejka": m.get("round"),
            "kickoff_ts": ts,
            "gospodarz": m["home_team"], "gosc": m["away_team"],
            "sedzia": m.get("referee"),
            "sedzia_mnoznik_fauli": round((refs.get(m.get("referee")) or {}).get("fouls_multiplier", 1.0), 2),
            "okazje": [],
        }
        for p in by_match_players.get(mid, []):
            pid = p["sofascore_player_id"]
            pos = (p.get("position") or "M")[0]
            if pos == "G" or not p.get("started"):
                continue
            opp_id = m["away_team_id"] if p["team_sofascore_id"] == m["home_team_id"] else m["home_team_id"]
            opp_name = m["away_team"] if p["team_sofascore_id"] == m["home_team_id"] else m["home_team"]
            own_name = m["home_team"] if p["team_sofascore_id"] == m["home_team_id"] else m["away_team"]
            is_home = p["team_sofascore_id"] == m["home_team_id"]

            for mk in PLAYER_MARKETS:
                col = STAT_COLUMNS[mk]
                # Kartki modelujemy PRZEZ FAULE (za mało kartek na zawodnika,
                # żeby modelować je wprost) — patrz model/cards.py.
                hist_col = "fouls_committed" if mk == "yellow_card" else col
                hist = history_for(player_index[pid], ts, hist_col)
                if len(hist.counts) < 5:
                    continue
                prior = priors["fouls_committed" if mk == "yellow_card" else mk][pos]
                card_conv = None
                if mk == "yellow_card":
                    rows_all = player_index[pid]
                    tot_y = sum(r.get("yellow_cards") or 0 for r in rows_all)
                    tot_f = sum(r.get("fouls_committed") or 0 for r in rows_all)
                    from ..model.cards import player_card_conversion
                    card_conv = player_card_conversion(tot_y, tot_f)
                conc = concession[mk].get(opp_id, {})
                ref_info = refs.get(m.get("referee")) or {}
                ctx = MatchContext(
                    is_home=is_home, is_favourite=is_home,
                    implied_spread=0.4 if is_home else -0.4,
                    implied_total=2.7,
                    opponent_allowed_per90=conc.get("allowed_per_match") or league_avg[mk],
                    league_avg_per90=league_avg[mk],
                    opponent_sample_matches=conc.get("games", 0),
                    referee_fouls_multiplier=ref_info.get("fouls_multiplier"),
                    referee_cards_multiplier=ref_info.get("cards_multiplier"),
                    referee_sample_matches=ref_info.get("games", 0),
                    official_started=True,
                    opponent_name=opp_name,
                    referee_name=m.get("referee") or "",
                    player_style=build_player_style(pid, pos),
                    opponent_style=build_opponent_style(opp_id),
                )
                # najpierw scoring bez kursów — potrzebujemy lambdy do wyboru linii
                probe = score_one(mk, 0.5, hist, prior, ctx, None, None)
                if mk != "yellow_card" and probe.lam < (0.35 if mk not in RARE_MARKETS else 0.20):
                    continue  # rynek bez sensu dla tego zawodnika
                line = 0.5 if mk == "yellow_card" else line_for_lambda(probe.lam)
                base = score_one(mk, line, hist, prior, ctx, None, None, card_conv)
                # kursy u 3 bukmacherów niezależnie — system robi "line shopping"
                # i pokazuje najlepszy kurs dla każdej strony rynku
                best = {}
                book_used = {}
                for book in BOOKMAKERS:
                    over_o, under_o = demo_odds_book(rng, base.p_over)
                    if mk == "yellow_card":
                        under_o = None  # polscy bukmacherzy kwotują tylko "otrzyma kartkę"
                    trial = score_one(mk, line, hist, prior, ctx, over_o, under_o, card_conv)
                    for a in trial.assessments:
                        if a.side not in best or a.ev_pct > best[a.side].ev_pct:
                            best[a.side] = a
                            book_used[a.side] = (
                                book,
                                over_o if a.side == "powyzej" else under_o,
                            )
                sm = base
                sm.assessments = list(best.values())

                if pid not in players_out:
                    total_min = sum(r["minutes"] for r in player_index[pid])
                    players_out[pid] = {
                        "id": pid,
                        "nazwa": p["player_name"],
                        "pozycja": pos,
                        "druzyna": own_name,
                        "minuty_lacznie": total_min,
                        "forma": {},
                    }
                forma_hist = (
                    hist if mk != "yellow_card"
                    else history_for(player_index[pid], ts, col)
                )
                players_out[pid]["forma"][mk] = {
                    "ostatnie": [int(c) for c in forma_hist.counts[:10]],
                    "minuty": [int(mn) for mn in forma_hist.minutes[:10]],
                    "srednia90": round(float(np.sum(forma_hist.counts) / max(np.sum(forma_hist.minutes), 1) * 90.0), 2),
                }

                for a in sm.assessments:
                    vb_id += 1
                    book, kurs_wziety = book_used[a.side]
                    bet = {
                        "id": vb_id,
                        "mecz_id": mid,
                        "mecz": f'{m["home_team"]} – {m["away_team"]}',
                        "kickoff_ts": ts,
                        "podmiot_typ": "zawodnik",
                        "podmiot_id": pid,
                        "podmiot": p["player_name"],
                        "druzyna": own_name,
                        "przeciwnik": opp_name,
                        "rynek_kod": mk,
                        "rynek": MARKET_NAMES_PL[mk],
                        "linia": line,
                        "strona": a.side,
                        "kurs": kurs_wziety,
                        "bukmacher": book,
                        "p_model": a.model_prob,
                        "p_rynku": a.implied_prob,
                        "fair_kurs": a.fair_odds,
                        "edge_pp": a.edge_pp,
                        "ev_pct": a.ev_pct,
                        "pewnosc": a.confidence,
                        "pewnosc_score": a.confidence_score,
                        "ryzyko": a.risk,
                        "rank_score": a.rank_score,
                        "ci": [sm.ci_low, sm.ci_high],
                        "oczekiwane_minuty": sm.expected_minutes,
                        "lambda": sm.lam,
                        "rozklad": counts.predict_match(
                            counts.fit_posterior(
                                np.array(hist.counts), np.array(hist.minutes),
                                np.array(hist.days_ago), prior,
                            ),
                            sm.expected_minutes,
                            1.0,
                        ).distribution(8) if mk != "yellow_card" else None,
                        "czynniki": sm.factors,
                        "uzasadnienie": sm.reasoning,
                    }
                    value_bets.append(bet)
                    match_out["okazje"].append(vb_id)

        # ---------------- rynki drużynowe ----------------
        for team_id, team_name, opp_id, opp_name, is_home in (
            (m["home_team_id"], m["home_team"], m["away_team_id"], m["away_team"], True),
            (m["away_team_id"], m["away_team"], m["home_team_id"], m["home_team"], False),
        ):
            rows_t = [
                r for r in team_index[team_id]
                if (r["_match"]["kickoff_ts"] or 0) < ts
            ]
            if len(rows_t) < 6:
                continue
            ref_info = refs.get(m.get("referee")) or {}
            for mk, stat_name in TEAM_MARKETS.items():
                cvals = [float(r["stats"].get(stat_name) or 0) for r in rows_t]
                hist = PlayerHistory(
                    counts=cvals,
                    minutes=[90.0] * len(rows_t),
                    days_ago=[
                        max((ts - (r["_match"]["kickoff_ts"] or ts)) / 86400.0, 0.0)
                        for r in rows_t
                    ],
                    started=[True] * len(rows_t),
                )
                conc = team_concession[mk].get(opp_id, {})
                ctx = MatchContext(
                    is_home=is_home, is_favourite=is_home,
                    implied_spread=0.4 if is_home else -0.4, implied_total=2.7,
                    opponent_allowed_per90=conc.get("allowed_per_match")
                    or team_league_avg[mk],
                    league_avg_per90=team_league_avg[mk],
                    opponent_sample_matches=conc.get("games", 0),
                    referee_fouls_multiplier=ref_info.get("fouls_multiplier"),
                    referee_cards_multiplier=ref_info.get("cards_multiplier"),
                    referee_sample_matches=ref_info.get("games", 0),
                    official_started=True,
                    opponent_name=opp_name, referee_name=m.get("referee") or "",
                    player_style=matchup.PlayerStyle(position="T"),
                    opponent_style=build_opponent_style(opp_id),
                )
                probe = score_one(mk, 0.5, hist, team_priors[mk], ctx, None, None)
                line = line_for_lambda(probe.lam)
                base = score_one(mk, line, hist, team_priors[mk], ctx, None, None)
                best, book_used = {}, {}
                for book in BOOKMAKERS:
                    over_o, under_o = demo_odds_book(rng, base.p_over)
                    trial = score_one(mk, line, hist, team_priors[mk], ctx, over_o, under_o)
                    for a in trial.assessments:
                        if a.side not in best or a.ev_pct > best[a.side].ev_pct:
                            best[a.side] = a
                            book_used[a.side] = (
                                book, over_o if a.side == "powyzej" else under_o
                            )

                ent_id = -team_id  # ujemne id = drużyna (nie koliduje z zawodnikami)
                if best and ent_id not in players_out:
                    players_out[ent_id] = {
                        "id": ent_id, "nazwa": team_name, "pozycja": "T",
                        "druzyna": team_name,
                        "minuty_lacznie": len(rows_t) * 90, "forma": {},
                    }
                if best:
                    players_out[ent_id]["forma"][mk] = {
                        "ostatnie": [int(c) for c in cvals[:10]],
                        "minuty": [90] * min(len(cvals), 10),
                        "srednia90": round(float(np.mean(cvals)), 2),
                    }
                for a in best.values():
                    vb_id += 1
                    book, kurs_wziety = book_used[a.side]
                    pred_dist = counts.predict_match(
                        counts.fit_posterior(
                            np.array(hist.counts), np.array(hist.minutes),
                            np.array(hist.days_ago), team_priors[mk],
                        ),
                        90.0, 1.0,
                    ).distribution(max(8, int(base.lam * 1.8) + 4))
                    value_bets.append({
                        "id": vb_id, "mecz_id": mid,
                        "mecz": f'{m["home_team"]} – {m["away_team"]}',
                        "kickoff_ts": ts,
                        "podmiot_typ": "druzyna", "podmiot_id": ent_id,
                        "podmiot": team_name, "druzyna": team_name,
                        "przeciwnik": opp_name,
                        "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk],
                        "linia": line, "strona": a.side,
                        "kurs": kurs_wziety, "bukmacher": book,
                        "p_model": a.model_prob, "p_rynku": a.implied_prob,
                        "fair_kurs": a.fair_odds, "edge_pp": a.edge_pp,
                        "ev_pct": a.ev_pct, "pewnosc": a.confidence,
                        "pewnosc_score": a.confidence_score, "ryzyko": a.risk,
                        "rank_score": a.rank_score,
                        "ci": [base.ci_low, base.ci_high],
                        "oczekiwane_minuty": 90.0, "lambda": base.lam,
                        "rozklad": pred_dist,
                        "czynniki": base.factors,
                        "uzasadnienie": base.reasoning,
                    })
                    match_out["okazje"].append(vb_id)

        matches_out.append(match_out)

    value_bets.sort(key=lambda b: -b["rank_score"])

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    def dump(name, obj):
        (WEB_DATA_DIR / name).write_text(
            json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        if name.endswith(".json"):
            _generated_this_run.add(name[:-5])
    dump("value_bets.json", value_bets)
    dump("matches.json", matches_out)
    dump("players.json", list(players_out.values()))
    dump("calibration.json", calibration)
    dump("meta.json", {
        "wygenerowano_ts": int(time.time()),
        "tryb": "demo",
        "liga": "Premier League",
        "sezon": "2025/26",
        "zrodlo": "Sofascore (realne statystyki), kursy PRZYKŁADOWE",
        "meczow_w_bazie": len(matches),
        "meczow_demo": len(demo_matches),
        "meczow_kalibracja": len(calib_matches),
        "okazji": len(value_bets),
    })
    print(f"OK: {len(value_bets)} okazji, {len(matches_out)} meczów demo, "
          f"{len(players_out)} zawodników, kalibracja: {calibration.get('razem')}")


if __name__ == "__main__":
    main()
