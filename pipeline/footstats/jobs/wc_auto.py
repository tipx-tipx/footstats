"""Strażnik trybu MŚ — czeka aż statshub wystawi propsy na ćwierćfinały, potem
scoruje szybką ścieżką (statshub + Superbet).

statshub to otwarte API (nie dławi jak bezpośredni Sofascore), więc pollujemy je
spokojnie co 20 minut. Propsy na mecz pojawiają się ~24-48 h przed kickoffem.
Gdy tylko się pojawią dla któregokolwiek ćwierćfinału — liczymy okazje i
przebudowujemy dane aplikacji. Kręci się dalej, dopóki są mecze w przyszłości.

Użycie: python -m footstats.jobs.wc_auto
"""

from __future__ import annotations

import sys
import time

from ..sources import statshub
from . import build_wc_fast

POLL_SECONDS = 1200          # 20 minut — statshub jest otwarte, nie ma pośpiechu
MAX_HOURS = 72.0             # ćwierćfinały rozłożone na kilka dni


def qf_props_live() -> int:
    """Ile nadchodzących meczów MŚ ma już wystawione propsy w statshub."""
    events = build_wc_fast.upcoming_wc_events()
    if not events:
        return 0
    trends = statshub.fetch_event_trends([e["id"] for e in events])
    return len({t.player_id for t in trends})


def main():
    start = time.time()
    last_players = -1
    while True:
        try:
            n = qf_props_live()
        except Exception as e:
            print(f"statshub chwilowo niedostępny ({e}) — ponawiam.", flush=True)
            n = 0

        if n > 0 and n != last_players:
            print(f"statshub: propsy dla {n} zawodników — liczę okazje.", flush=True)
            try:
                build_wc_fast.main()
            except Exception as e:
                print(f"Błąd scoringu: {e}", file=sys.stderr, flush=True)
            last_players = n

        if (time.time() - start) / 3600.0 > MAX_HOURS:
            print("Koniec okna MŚ — kończę strażnika.", flush=True)
            return

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
