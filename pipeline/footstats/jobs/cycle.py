"""Jeden cykl automatycznego odświeżenia — orkiestrator crona w chmurze.

Wybiera właściwą robotę zależnie od trybu:
  * TRYB LIGOWY (produkcja): odświeża dane ligowe (`build_league`).
  * TRYB MŚ (zakończony 2026-07-19): okazje z statshub + Superbet + STS.

URUCHAMIANY W GITHUB ACTIONS (`.github/workflows/cycle.yml`), nie na żadnym
komputerze. Poprzednia wersja tego opisu mówiła o „Harmonogramie zadań Windows
co ~30 min" — to było nieprawdą od przeprowadzki do chmury i wysyłało każdego,
kto tu zajrzał, na poszukiwanie lokalnego crona, którego nie ma.

Realna częstotliwość NIE wynosi 15 minut mimo takiej deklaracji w cronie:
GitHub tworzy ~14% zadeklarowanych tyknięć, mediana odstępu to ~96 min.
Pomiar i wnioski — w nagłówku `cycle.yml`.
"""

from __future__ import annotations

import os
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
    # STOPER CAŁEGO CYKLU (2026-08-01). Cykl regularnie ginął na limicie 20 min
    # w GitHub Actions, a z logów nie dało się powiedzieć, co go zjada — job
    # kończył się w połowie i nie zostawiał ani jednej liczby o czasie.
    # Zabity przebieg nie wypycha nic, więc każda taka śmierć to godzina
    # nieświeżej strony; bez pomiaru podnoszenie limitu jest zgadywaniem.
    t0 = time.monotonic()
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
        t_model = time.monotonic() - t0
        print(f"[stoper] model policzony po {t_model / 60:.1f} min", flush=True)
        # wypchnij wyniki do Supabase (jeśli skonfigurowane) — aplikacja na Vercel je czyta
        from . import push_supabase
        wypchniete = push_supabase.push()
        print(f"[stoper] wysyłka do Supabase: {(time.monotonic() - t0 - t_model) / 60:.1f} min "
              f"| CAŁY CYKL {(time.monotonic() - t0) / 60:.1f} min", flush=True)
        # push() zwraca False też gdy Supabase NIE jest skonfigurowany (lokalny
        # run bez sekretów) — to nie błąd. Ale gdy sekrety SĄ ustawione (GitHub
        # Actions), False = realny błąd (HTTP/brak danych) i dane NIE trafiły do
        # bazy. Bez tego job zostawał zielony mimo cichego padu pushu, a front
        # pokazywał stare mecze (patrz incydent: zamrożenie po formacie 2026-07).
        if not wypchniete and os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"):
            raise RuntimeError(
                "push_supabase.push() zwrócił False mimo ustawionych sekretów — "
                "dane NIE trafiły do Supabase"
            )
        print(f"[{stamp}] OK", flush=True)
    except Exception:
        print(f"[{stamp}] BŁĄD:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
