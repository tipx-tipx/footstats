"""Podsumowanie cyklu próbnego (dry-run `build_league`): ile typów, kart
i zawodników per rynek i ekran – do porównania źródeł (etap 4e planu FotMob).

Czyta zrzuty z `web/src/data/demo/liga_dryrun/` (patrz `build_wc_fast._dump`)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

KATALOG = Path(__file__).resolve().parents[2] / "web" / "src" / "data" / "demo" / "liga_dryrun"


def _czytaj(nazwa):
    p = KATALOG / nazwa
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _lista(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for k in ("wpisy", "typy", "lista", "data"):
            if isinstance(obj.get(k), list):
                return obj[k]
    return []


def main() -> int:
    if not KATALOG.exists():
        print(f"Brak zrzutów w {KATALOG}")
        return 1
    print("Pliki:", ", ".join(f"{p.name} ({p.stat().st_size // 1024} KB)" for p in sorted(KATALOG.glob("*.json"))))
    vb = _lista(_czytaj("value_bets.json"))
    print(f"\nTYPY (value_bets): {len(vb)}")
    for pole in ("ekran", "rynek_kod", "strona", "zrodlo", "bukmacher"):
        c = Counter(str(t.get(pole)) for t in vb if isinstance(t, dict) and pole in t)
        if c:
            print(f"  {pole}: {dict(c.most_common(20))}")
    p = [t.get("p_model") or t.get("p") for t in vb if isinstance(t, dict)]
    p = sorted(x for x in p if isinstance(x, (int, float)))
    if p:
        print(f"  szansa modelu: min {p[0]:.2f}, mediana {p[len(p) // 2]:.2f}, max {p[-1]:.2f}")
    radar = _lista(_czytaj("radar.json"))
    print(f"\nRADAR / DRABINKI: {len(radar)}")
    c = Counter(str(w.get("rynek_kod") or w.get("rynek")) for w in radar if isinstance(w, dict))
    if c:
        print(f"  rynki: {dict(c.most_common(15))}")
    players = _lista(_czytaj("players.json"))
    print(f"\nZAWODNICY na stronie: {len(players)}")
    mecze = _lista(_czytaj("matches.json"))
    print(f"MECZE na stronie: {len(mecze)}")
    odrz = _czytaj("odrzucenia.json")
    if isinstance(odrz, dict):
        powody = Counter()
        for v in odrz.values():
            for w in (v if isinstance(v, list) else (v or {}).get("odrzucone", []) if isinstance(v, dict) else []):
                if isinstance(w, dict):
                    powody[str(w.get("powod") or w.get("odrzucenie_powod"))] += 1
        if powody:
            print(f"\nODRZUCENIA (powody): {dict(powody.most_common(15))}")
    pok = _czytaj("pokrycie_liga.json")
    if isinstance(pok, dict):
        print(f"\nPOKRYCIE: { {k: v for k, v in pok.items() if not isinstance(v, (list, dict))} }")
    return 0


if __name__ == "__main__":
    sys.exit(main())
