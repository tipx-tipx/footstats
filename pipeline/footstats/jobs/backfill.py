"""Backfill historii meczów z Sofascore do lokalnego magazynu.

Użycie:
    python -m footstats.jobs.backfill --league EPL --season 25/26 --max-matches 60

Idempotentny: mecze już pobrane są pomijane (klucz: sofascore event id).
Rate limit ~2 s/request — pełny sezon (380 meczów x ~5 requestów) trwa ~60-90 min.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict

from ..sources.sofascore import TOURNAMENTS, SofascoreSource
from .. import store


def run(
    league: str,
    season_label: str,
    max_matches: int | None = None,
    src: SofascoreSource | None = None,
) -> None:
    tid = TOURNAMENTS[league]
    src = src or SofascoreSource()
    sid = src.find_season_id(tid, season_label)
    if sid is None:
        print(f"Nie znaleziono sezonu {season_label} dla ligi {league}", file=sys.stderr)
        sys.exit(1)

    matches_t = store.matches_table()
    players_t = store.player_stats_table()
    teams_t = store.team_stats_table()
    done_ids = matches_t.existing_ids("sofascore_id")

    count = 0
    for ev in src.season_events(tid, sid, finished_only=True):
        if max_matches is not None and count >= max_matches:
            break
        eid = ev["id"]
        if eid in done_ids:
            continue
        try:
            bundle = src.fetch_match(eid)
        except Exception as e:  # nie przerywaj backfillu jednym błędem
            print(f"  ! pominięto mecz {eid}: {e}", file=sys.stderr)
            continue

        full = bundle.event
        matches_t.append(
            {
                "sofascore_id": eid,
                "league": league,
                "season": season_label,
                "round": (full.get("roundInfo") or {}).get("round"),
                "kickoff_ts": full.get("startTimestamp"),
                "home_team": full["homeTeam"]["name"],
                "home_team_id": full["homeTeam"]["id"],
                "away_team": full["awayTeam"]["name"],
                "away_team_id": full["awayTeam"]["id"],
                "home_goals": (full.get("homeScore") or {}).get("current"),
                "away_goals": (full.get("awayScore") or {}).get("current"),
                "referee": (full.get("referee") or {}).get("name"),
                "referee_id": (full.get("referee") or {}).get("id"),
            }
        )
        players_t.append_many(
            [{"match_sofascore_id": eid, **asdict(r)} for r in bundle.player_rows]
        )
        teams_t.append_many(
            [
                {"match_sofascore_id": eid, "team_sofascore_id": tid_, **stats}
                for tid_, stats in bundle.team_stats.items()
            ]
        )
        count += 1
        print(f"[{count}] {full['homeTeam']['name']} - {full['awayTeam']['name']} OK", flush=True)

    print(f"Gotowe: pobrano {count} nowych meczów ({league} {season_label}).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", required=True, choices=list(TOURNAMENTS))
    ap.add_argument("--season", required=True, help="np. 25/26")
    ap.add_argument("--max-matches", type=int, default=None)
    args = ap.parse_args()
    run(args.league, args.season, args.max_matches)
