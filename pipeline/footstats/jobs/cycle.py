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

# "liga" (tryb ligowy, produkcja od 2026-07-21) / "ms2026" (MŚ, zakończone
# 2026-07-19) / "demo". Fazy 1-3 roadmapy ligowej domknięte — silnik,
# brama jakości, rynki drużynowe, składy i rozliczanie multi-liga.
MODE = "liga"


def main():
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] START cyklu (tryb: {MODE})", flush=True)
    try:
        if MODE == "ms2026":
            from . import build_wc_fast
            build_wc_fast.main()
        elif MODE == "liga":
            from . import build_league
            build_league.main(publikuj=True)
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
