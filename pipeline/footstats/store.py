"""Lokalny magazyn danych pipeline'u (JSON Lines).

Prosty odpowiednik tabel bazy — pozwala pracować bez skonfigurowanego Supabase
(backfill, walidacja modelu, dane demo). Po podpięciu Supabase te same
znormalizowane wiersze wysyłamy do Postgresa (jobs/push_supabase.py).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store"


class JsonlTable:
    def __init__(self, name: str):
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        self.path = STORE_DIR / f"{name}.jsonl"

    def append(self, row: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def append_many(self, rows: list[dict]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    # niedokończona linia (równoległy zapis backfillu) — pomiń
                    continue
        return out

    def iter_rows(self) -> Iterator[dict]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def existing_ids(self, key: str) -> set:
        return {r[key] for r in self.iter_rows() if key in r}


def matches_table() -> JsonlTable:
    return JsonlTable("matches")


def player_stats_table() -> JsonlTable:
    return JsonlTable("player_match_stats")


def team_stats_table() -> JsonlTable:
    return JsonlTable("team_match_stats")
