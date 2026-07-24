"""Domowy worker Sofascore — domyka OGON egzotyki (Warstwa 2).

Uruchamiany RĘCZNIE z domowego IP (dwuklik scripts/rozlicz-egzotyke.cmd), bo
Sofascore blokuje IP chmury. LEKKI Z DEFINICJI: nie liczy modelu — dla
WISZĄCYCH, ZAKOŃCZONYCH meczów pobiera z Sofascore staty (per-zawodnik faule/
odbiory/przechwyty/minuty/strzały + drużynowe rożne/kartki/faule/strzały) i
zapisuje je do klucza `sofa_results` w Supabase.

Rozlicza z tego CHMURA (rozliczanie.py czyta `sofa_results`) — worker SAM
niczego nie rozlicza, więc nie wyściguje się z chmurą o typy_log. Miękka
degradacja: nie odpalisz przez 48 h → te nogi idą na zwrot, reszta działa.

Oszczędny: pomija mecze już zebrane, a `fetch_match` cache'uje na dysku
(zakończony mecz = pobrany raz na zawsze). Kilka egzotycznych meczów na przebieg.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except Exception:
    pass

from .. import supa
from ..sources.sofascore import SofascoreSource

# ~105 min po pierwszym gwizdku = mecz zamknięty (jak MECZ_KONIEC_PO_S w
# rozliczaniu; nie importujemy go, żeby nie ciągnąć modelu/numpy do workera).
MECZ_KONIEC_PO_S = 6300
MAX_WIEK_S = 7 * 86400   # starsze wpisy cache prune'ujemy (payload mały)

# etykieta staty drużynowej Sofascore (lowercase) -> nasz kod rynku
_TEAM_LABEL = {
    "corner kicks": "team_corners",
    "fouls": "team_fouls",
    "total shots": "team_shots",
    "shots on target": "team_sot",
}


def _staty_druzyny(raw: dict) -> dict:
    """Surowe staty drużynowe Sofascore (etykiety ang.) -> kody rynków."""
    low = {str(k).strip().lower(): v for k, v in (raw or {}).items()}
    out: dict = {}
    for label, mk in _TEAM_LABEL.items():
        v = low.get(label)
        if v is not None:
            try:
                out[mk] = float(v)
            except (TypeError, ValueError):
                pass
    y, r = low.get("yellow cards"), low.get("red cards")
    if y is not None or r is not None:
        try:
            out["team_cards"] = float(y or 0) + float(r or 0)
        except (TypeError, ValueError):
            pass
    return out


def _score(ev: dict, side: str) -> tuple:
    s = ev.get(side) or {}
    return s.get("current"), s.get("normaltime", s.get("current"))


def main() -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] START workera Sofascore (ogon egzotyki)", flush=True)
    if not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY")):
        print(f"[{stamp}] Brak sekretów Supabase — nie ma dokąd zapisać. Koniec.",
              flush=True)
        return
    try:
        log = supa.get_key("typy_log") or {}
        now = int(time.time())
        # eventy WISZĄCYCH, ZAKOŃCZONYCH nóg = ogon do domknięcia
        eventy = sorted({
            r["mecz_id"] for r in log.values()
            if r.get("wynik") is None and r.get("mecz_id")
            and now - (r.get("kickoff_ts") or 0) >= MECZ_KONIEC_PO_S
            and (r.get("kickoff_ts") or 0) > 0
        })
        sofa = supa.get_key("sofa_results") or {}
        # prune stare wpisy (zostawiamy świeże, dokładamy nowe)
        sofa = {
            k: v for k, v in sofa.items()
            if k != "_meta" and isinstance(v, dict)
            and now - (v.get("ts") or 0) < MAX_WIEK_S
        }
        # pomiń mecze już zebrane (z zawodnikami) — oszczędza pracę i sieć
        do_pobrania = [
            e for e in eventy
            if not (sofa.get(str(e)) or {}).get("players")
        ]
        print(f"[{stamp}] Wiszących meczów: {len(eventy)}; "
              f"nowych do pobrania: {len(do_pobrania)}", flush=True)

        src = SofascoreSource()
        dobite = 0
        for eid in do_pobrania:
            try:
                b = src.fetch_match(eid)
            except Exception as e:
                print(f"  event {eid}: pominięty ({type(e).__name__}: {e})",
                      flush=True)
                continue
            ev = b.event or {}
            hc, hn = _score(ev, "homeScore")
            ac, an = _score(ev, "awayScore")
            extra = hc is not None and hn is not None and (hc != hn or ac != an)
            players: dict = {}
            for p in b.player_rows:
                nm = getattr(p, "player_name", None)
                if not nm:
                    continue
                players[nm] = {
                    "minutes": getattr(p, "minutes", None),
                    "shots": getattr(p, "shots", None),
                    "sot": getattr(p, "shots_on_target", None),
                    "fouls_committed": getattr(p, "fouls_committed", None),
                    "fouls_won": getattr(p, "fouls_won", None),
                    "tackles": getattr(p, "tackles", None),
                    "interceptions": getattr(p, "interceptions", None),
                    "offsides": getattr(p, "offsides", None),
                }
            id2name = {}
            for side in ("homeTeam", "awayTeam"):
                t = ev.get(side) or {}
                if t.get("id") is not None:
                    id2name[t["id"]] = t.get("name")
            teams = {
                id2name[tid]: _staty_druzyny(raw)
                for tid, raw in (b.team_stats or {}).items()
                if id2name.get(tid)
            }
            sofa[str(eid)] = {
                "players": players, "teams": teams,
                "extra_time": bool(extra), "ts": now,
            }
            dobite += 1

        sofa["_meta"] = {
            "last_run": now, "pobrano": dobite,
            "wiszacych": len(eventy), "w_cache": len(sofa),
        }
        ok = supa.put_key("sofa_results", sofa)
        print(f"[{stamp}] Zebrano {dobite} nowych meczów; cache: {len(sofa) - 1}; "
              f"push={ok}", flush=True)
        if not ok:
            raise RuntimeError("put_key sofa_results nie powiódł się")
        print(f"[{stamp}] OK — chmura dorozliczy egzotykę w najbliższym cyklu.",
              flush=True)
    except Exception:
        print(f"[{stamp}] BŁĄD:\n{traceback.format_exc()}", file=sys.stderr,
              flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
