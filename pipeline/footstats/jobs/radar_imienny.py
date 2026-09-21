# -*- coding: utf-8 -*-
"""IMIENNY RENTGEN DRABINEK (2026-09-21, decyzja właściciela).

PO CO. Rentgen radaru (`diagnostyka.zapisz_rentgen`) trzyma wyłącznie SUMY per
brama: „rzadko w pierwszym składzie: 352". Kiedy właściciel pyta „czemu radar
nie dał Mandragory zza pola?", nazwiska nie ma nigdzie — ani w `meta`, ani
w `odrzucenia` (to rejestr strumienia typów, nie radaru), ani w logu Actions.
Po meczu dane wypadają z Supabase i zostaje ręczne odtwarzanie ze statshuba
(sesja 21.09: sześć nazwisk, godzina pracy, jedno nierozstrzygnięte).

CO ROBI. Dla KAŻDEJ pary (mecz, zawodnik) z oferty zapisuje bramę, na której
radar ją zdjął, z jedną liczbą dowodową (minuty, udział startów, pokrycie
linii), albo „karta" z miejscem, gdy przeszła. Wiersz na parę, ~300 B.

DLACZEGO OSOBNA TABELA, NIE KLUCZ `app_data`. Klucz musiałby być czytany
i sklejany co cykl (70 razy na dobę), a odczyt to transfer — dokładnie to,
co 25.08 i 18.09 zatrzymało projekt (limit Free 5 GB/mies.). Tabela dostaje
upsert z `Prefer: return=minimal`: odpowiedź pusta, ZERO transferu
wychodzącego, bez odczytu poprzedniego stanu. Czyta ją tylko człowiek,
po nazwisku, kilka kB (`python -m footstats.jobs.radar_imienny Mandragora`).
Wiersze starsze niż `RETENCJA_DNI` kasuje ten sam cykl.

CZEGO NIE ROBI. Nie zmienia żadnej bramy ani kolejności kart — to wyłącznie
zapis tego, co radar i tak rozstrzygnął. Brak tabeli (niewklejona migracja
0009) = cichy licznik i cykl idzie dalej.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from collections import Counter

from .. import diagnostyka, supa

TABELA = "radar_imienny"
RETENCJA_DNI = 4
KLUCZ_KONFLIKTU = "mecz_id,podmiot_id"
# ile znaków szczegółu trzymamy — wiersz ma być tani, nie kompletny
MAX_SZCZEGOL = 600


def odnotuj(imienny: dict | None, mid: int, pid: int, brama: str,
            **szczegol) -> None:
    """Zapisz werdykt pary (mecz, zawodnik). Późniejszy werdykt NADPISUJE
    wcześniejszy (para przechodzi bramy po kolei — liczy się ostatnia)."""
    if imienny is None:
        return
    w = imienny.setdefault((int(mid), int(pid)), {})
    w["brama"] = brama
    for k, v in szczegol.items():
        if v is not None:
            w[k] = v


def opis_rynkow(rynki: list[dict] | None) -> dict[str, str]:
    """Skrót drabinek karty: {rynek: "0.5@1.62 6/10 f3/5 | 1.5@2.9 3/10 f1/5"}.

    Tyle wystarczy, żeby odpowiedzieć „6/10 na 1,5 — sito pokrycia", bez
    wożenia całej karty."""
    out: dict[str, str] = {}
    for r in rynki or []:
        czesci = []
        for s in (r.get("drabinka") or [])[:3]:
            p = s.get("pokrycie") or {}
            f = s.get("pokrycie5") or {}
            czesci.append(
                f"{s.get('linia')}@{s.get('kurs')} "
                f"{p.get('traf', '?')}/{p.get('z', '?')} "
                f"f{f.get('traf', '?')}/{f.get('z', '?')}"
            )
        if czesci:
            out[str(r.get("rynek_kod") or "?")] = " | ".join(czesci)
    return out


def _dzien(ts) -> str:
    if not ts:
        return ""
    return _dt.datetime.fromtimestamp(int(ts), _dt.timezone.utc).strftime("%Y-%m-%d")


def wiersze(imienny: dict, cykl_ts: int) -> list[dict]:
    """Słownik radaru → wiersze tabeli. Szczegół przycięty do MAX_SZCZEGOL."""
    out: list[dict] = []
    for (mid, pid), w in imienny.items():
        szczegol = {k: v for k, v in w.items()
                    if k not in ("brama", "mecz", "podmiot", "druzyna", "kickoff_ts")}
        tekst = json.dumps(szczegol, ensure_ascii=False, sort_keys=True)
        if len(tekst) > MAX_SZCZEGOL:
            tekst = tekst[:MAX_SZCZEGOL - 1] + "…"
        out.append({
            "mecz_id": int(mid),
            "podmiot_id": int(pid),
            "dzien": _dzien(w.get("kickoff_ts")) or _dzien(cykl_ts),
            "mecz": w.get("mecz"),
            "podmiot": w.get("podmiot"),
            "druzyna": w.get("druzyna"),
            "brama": str(w.get("brama") or "?"),
            "szczegol": tekst,
            "cykl_ts": int(cykl_ts),
        })
    return out


def zapisz(imienny: dict | None, cykl_ts: int) -> bool:
    """Upsert wszystkich par tego cyklu + sprzątanie starych dni.

    Nigdy nie rzuca — rentgen nie ma prawa położyć cyklu."""
    if not imienny:
        return False
    try:
        rows = wiersze(imienny, cykl_ts)
        ok = supa.upsert_wiersze(TABELA, rows, KLUCZ_KONFLIKTU)
        if ok:
            granica = _dzien(cykl_ts - RETENCJA_DNI * 86400)
            supa.usun_wiersze(TABELA, f"dzien=lt.{granica}")
            print(f"Radar — rentgen imienny: {len(rows)} par, bramy: "
                  + ", ".join(f"{k}={v}" for k, v in
                              Counter(r["brama"] for r in rows).most_common(8)),
                  flush=True)
        return ok
    except Exception as e:                                   # noqa: BLE001
        diagnostyka.cichy("radar", "rentgen_imienny", e)
        return False


def czytaj(nazwa: str, dni: int = RETENCJA_DNI) -> list[dict]:
    """Wiersze po fragmencie nazwiska (do ręcznego użytku, nie z cyklu)."""
    return supa.czytaj_wiersze(
        TABELA,
        f"podmiot=ilike.*{nazwa}*&dzien=gte."
        f"{_dzien(int(_dt.datetime.now(_dt.timezone.utc).timestamp()) - dni * 86400)}"
        "&order=dzien.desc,cykl_ts.desc",
    )


if __name__ == "__main__":                                   # pragma: no cover
    # python -m footstats.jobs.radar_imienny Mandragora
    # (SUPABASE_URL + SUPABASE_SERVICE_KEY lub klucz anon w środowisku)
    sys.stdout.reconfigure(encoding="utf-8")
    szukane = " ".join(sys.argv[1:]).strip()
    if not szukane:
        print("użycie: python -m footstats.jobs.radar_imienny <fragment nazwiska>")
        sys.exit(2)
    if not os.environ.get("SUPABASE_URL"):
        print("brak SUPABASE_URL w środowisku")
        sys.exit(2)
    for r in czytaj(szukane):
        print(f"{r.get('dzien')}  {r.get('mecz')}  {r.get('podmiot')} "
              f"({r.get('druzyna')})  →  {r.get('brama')}\n    {r.get('szczegol')}")
