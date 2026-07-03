"""Jeden cykl automatycznego odświeżenia — uruchamiany przez Harmonogram zadań.

Wybiera właściwą robotę zależnie od trybu:
  * TRYB MŚ (domyślnie teraz): przelicza okazje z statshub + Superbet + STS.
  * TRYB LIGOWY (po starcie sezonu): odświeża dane ligowe.

Uruchamiany co ~30 min przez Windows Task Scheduler (patrz scripts/). Loguje
wynik z sygnaturą czasową; nie wymaga otwartej sesji ani terminala.
"""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

# lokalnie: wczytaj sekrety z pipeline/.env (gitignorowany). W GitHub Actions
# zmienne przychodzą ze środowiska — dotenv ich nie nadpisze.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except Exception:
    pass

MODE = "ms2026"  # przełączyć na "liga" po starcie sezonu 2026/27


def main():
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] START cyklu (tryb: {MODE})", flush=True)
    try:
        if MODE == "ms2026":
            from . import build_wc_fast
            build_wc_fast.main()
        else:
            from . import build_demo
            build_demo.main()
        # wypchnij wyniki do Supabase (jeśli skonfigurowane) — aplikacja na Vercel je czyta
        from . import push_supabase
        push_supabase.push()
        print(f"[{stamp}] OK", flush=True)
    except Exception:
        print(f"[{stamp}] BŁĄD:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
