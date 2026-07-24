"""Lekki job TYLKO-ROZLICZANIE — bez przeliczania modelu.

Po co osobno: pełny cykl (build_league) odkrywa mecze, paruje Superbet i liczy
model — ciężki i odpalany rzadko (cron chmury bywa dławiony do co 1-3h). A
rozliczenia nie mogą czekać: zakończony mecz powinien zamknąć kupon szybko.
`rozliczanie.rozlicz()` jest samowystarczalny — czyta typy_log / trend_lib /
kupony_log z Supabase, dolewa świeże trendy statshub, rozlicza i ZAPISUJE
z powrotem typy_log/kupony_log do Supabase. Tu odpalamy go z pustymi wejściami
(nic nowego nie publikujemy) i odświeżamy dwa klucze widoku, które czyta
aplikacja: `kupony` (aktywne) i `typy_wyniki` (skuteczność).

Można odpalać CZĘSTO (np. co ~20 min) niezależnie od dużego cyklu. Ten sam
mechanizm rozliczania korzysta teraz z fallbacków statshub (wynik + shotmapa),
więc rozlicza także egzotykę, której 365Scores nie zna — w całości z chmury.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

# lokalnie: sekrety z pipeline/.env (gitignorowany). W GitHub Actions zmienne
# przychodzą ze środowiska — dotenv ich nie nadpisze.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except Exception:
    pass

from .. import supa
from . import rozliczanie


def main() -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] START rozliczania (lekki job, bez przeliczania modelu)",
          flush=True)
    ma_supabase = bool(
        os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY")
    )
    if not ma_supabase:
        print(f"[{stamp}] Brak sekretów Supabase — nie ma czego rozliczać, koniec.",
              flush=True)
        return
    try:
        wyniki = rozliczanie.rozlicz([], [])
        aktywne = [
            k for k in wyniki["kupony"]
            if k.get("wynik") is None and not k.get("pominiety")
        ]
        ok_k = supa.put_key("kupony", aktywne)
        ok_t = supa.put_key("typy_wyniki", wyniki)
        p = wyniki["podsumowanie"]
        print(
            f"[{stamp}] Rozliczono: {p['rozliczone']}/{p['opublikowane']} typów, "
            f"{p['trafione']} trafionych, ROI flat {p['roi_flat']:+.2f} j.; "
            f"{len(aktywne)} aktywnych kuponów; "
            f"push kupony={ok_k} typy_wyniki={ok_t}",
            flush=True,
        )
        # cichy błąd pushu nie może udawać sukcesu (jak w cycle.py)
        if not (ok_k and ok_t):
            raise RuntimeError(
                "push kupony/typy_wyniki do Supabase nie powiódł się"
            )
        print(f"[{stamp}] OK", flush=True)
    except Exception:
        print(f"[{stamp}] BŁĄD:\n{traceback.format_exc()}", file=sys.stderr,
              flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
