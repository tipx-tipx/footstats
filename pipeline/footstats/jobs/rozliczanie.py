"""Automatyczne rozliczanie publikowanych typów + baza pod uczenie modelu.

Przepływ (wywoływane na końcu każdego cyklu):
  1. każdy publikowany typ (okazja i sugestia) trafia do logu `typy_log`
     w Supabase — z ZAMROŻONYM p_model i kursem z chwili pierwszej publikacji,
  2. po zakończonym meczu (kickoff + 2,5 h) cykl szuka faktycznej wartości:
       * rynki strzałowe — z 365Scores (chartEvents, per strzał),
       * faule/odbiory/przechwyty — z banku trendów (świeży trend zawodnika
         w statshub zawiera rozegrany mecz; parowanie po timestampie),
       * zawodnik nie zagrał (0 minut wg statshub) -> "zwrot" (void),
  3. podsumowanie `typy_wyniki` (trafienia, ROI flat, per rynek) idzie na
     stronę Skuteczności. Odchylenie trafień od średniego p_model per rynek
     (bias) to surowiec do dokręcenia kalibracji — STOSUJEMY je w modelu
     dopiero od n>=25 rozliczonych typów na rynku (na razie tylko raport).
"""

from __future__ import annotations

import time

from .. import supa
from ..sources import rotowire, scores365

# rynek -> pole w agregacie 365Scores (classify_event)
MARKETY_365 = {
    "shots": "shots", "sot": "sot",
    "headed_shots": "headed", "headed_sot": "headed_sot",
    "shots_outside_box": "outside", "sot_outside_box": "sot_outside",
    "shots_blocked": "blocked", "shots_off_target": "off_target",
}
# rynki rozliczane z banku trendów statshub
MARKETY_LIB = {"fouls_committed", "tackles", "fouls_won", "interceptions"}

MECZ_KONIEC_PO_S = int(2.5 * 3600)
OKNO_PAROWANIA_S = 36 * 3600


def _klucz(b: dict) -> str:
    return f"{b['mecz_id']}:{b['podmiot_id']}:{b['rynek_kod']}:{b['linia']}:{b['strona']}"


def _dopisz_nowe(log: dict, value_bets: list[dict]) -> None:
    for b in value_bets:
        k = _klucz(b)
        if k in log:
            continue
        log[k] = {
            "mecz_id": b["mecz_id"], "mecz": b["mecz"],
            "kickoff_ts": b["kickoff_ts"],
            "podmiot_id": b["podmiot_id"], "podmiot": b["podmiot"],
            "rynek_kod": b["rynek_kod"], "rynek": b["rynek"],
            "linia": b["linia"], "strona": b["strona"],
            "kurs": b.get("kurs"), "bukmacher": b.get("bukmacher"),
            "p_model": b["p_model"], "pewnosc": b.get("pewnosc"),
            "sugestia": bool(b.get("sugestia")),
            "opublikowano_ts": int(time.time()),
            "wynik": None, "faktyczna": None,
        }


def _gra_365(rec: dict, cache: dict) -> dict | None:
    """Znajdź agregat strzałów 365Scores dla meczu z rekordu (cache per mecz)."""
    mid = rec["mecz_id"]
    if mid in cache:
        return cache[mid]
    teams = [t.strip() for t in str(rec["mecz"]).replace("—", "–").split("–")]
    if len(teams) != 2:
        cache[mid] = None
        return None
    home, away = rotowire._norm(teams[0]), rotowire._norm(teams[1])
    dzien = time.strftime("%d/%m/%Y", time.localtime(rec["kickoff_ts"]))
    nastepny = time.strftime("%d/%m/%Y", time.localtime(rec["kickoff_ts"] + 86400))
    wynik = None
    try:
        data = scores365._get(
            f"{scores365.BASE}/games/current/?{scores365.Q}&sports=1"
            f"&startDate={dzien}&endDate={nastepny}"
        )
        for g in data.get("games", []):
            gn = {
                rotowire._norm(str((g.get("homeCompetitor") or {}).get("name", ""))),
                rotowire._norm(str((g.get("awayCompetitor") or {}).get("name", ""))),
            }
            if gn == {home, away} and g.get("statusGroup") == 4:
                wynik = scores365.game_player_shots(int(g["id"]))
                break
    except Exception:
        wynik = None
    cache[mid] = wynik
    return wynik


def _minuty_z_banku(rec: dict, lib: dict) -> float | None:
    """Minuty zawodnika w rozliczanym meczu (z banku trendów, rynek shots)."""
    t = lib.get(f"{rec['podmiot_id']}:shots")
    if not t:
        return None
    for i, ts in enumerate(t.get("timestamps", [])):
        if abs(ts - rec["kickoff_ts"]) < OKNO_PAROWANIA_S:
            mins = t.get("minutes", [])
            return float(mins[i]) if i < len(mins) else None
    return None


def _wartosc_z_banku(rec: dict, lib: dict) -> float | None:
    t = lib.get(f"{rec['podmiot_id']}:{rec['rynek_kod']}")
    if not t:
        return None
    for i, ts in enumerate(t.get("timestamps", [])):
        if abs(ts - rec["kickoff_ts"]) < OKNO_PAROWANIA_S:
            cnts = t.get("counts", [])
            return float(cnts[i]) if i < len(cnts) else None
    return None


def rozlicz(value_bets: list[dict]) -> dict:
    """Dopisz nowe typy do logu, rozlicz zakończone, zwróć podsumowanie."""
    log = supa.get_key("typy_log") or {}
    _dopisz_nowe(log, value_bets)
    lib = supa.get_key("trend_lib") or {}
    now = int(time.time())
    cache_365: dict = {}

    for rec in log.values():
        if rec.get("wynik") or now - rec["kickoff_ts"] < MECZ_KONIEC_PO_S:
            continue
        mk = rec["rynek_kod"]
        wartosc = None
        if mk in MARKETY_365:
            gra = _gra_365(rec, cache_365)
            if gra is not None:
                pkey = scores365.resolve_player_key(set(gra), rec["podmiot"])
                wartosc = float(gra.get(pkey, {}).get(MARKETY_365[mk], 0)) if pkey else 0.0
        elif mk in MARKETY_LIB:
            wartosc = _wartosc_z_banku(rec, lib)
        if wartosc is None:
            continue  # źródło jeszcze nie ma meczu — spróbujemy w kolejnym cyklu
        minuty = _minuty_z_banku(rec, lib)
        if minuty is not None and minuty <= 0:
            rec.update(wynik="zwrot", faktyczna=0.0, rozliczono_ts=now)
            continue
        trafiony = (
            wartosc > rec["linia"] if rec["strona"] == "powyzej" else wartosc < rec["linia"]
        )
        rec.update(
            wynik="wygrany" if trafiony else "przegrany",
            faktyczna=wartosc, rozliczono_ts=now,
        )

    supa.put_key("typy_log", log)

    # ---- podsumowanie do UI ----
    settled = [r for r in log.values() if r.get("wynik") in ("wygrany", "przegrany")]
    okazje = [r for r in settled if not r["sugestia"] and r.get("kurs")]
    roi = sum(
        (r["kurs"] - 1.0) if r["wynik"] == "wygrany" else -1.0 for r in okazje
    )
    po_rynku = []
    for mk in sorted({r["rynek_kod"] for r in settled}):
        grp = [r for r in settled if r["rynek_kod"] == mk]
        traf = sum(1 for r in grp if r["wynik"] == "wygrany")
        sr_p = sum(r["p_model"] for r in grp) / len(grp)
        po_rynku.append({
            "rynek_kod": mk, "rynek": grp[0]["rynek"], "n": len(grp),
            "trafione": traf,
            "sr_p_model": round(sr_p, 3),
            "czestosc": round(traf / len(grp), 3),
            # bias > 1 = model niedoszacowuje, < 1 = przeszacowuje;
            # stosowany w modelu dopiero od n>=25 (na razie raport)
            "bias": round((traf + 2.0) / (sr_p * len(grp) + 2.0), 3),
        })
    ostatnie = sorted(
        settled + [r for r in log.values() if r.get("wynik") == "zwrot"],
        key=lambda r: -(r.get("rozliczono_ts") or 0),
    )[:60]
    return {
        "podsumowanie": {
            "opublikowane": len(log),
            "rozliczone": len(settled),
            "trafione": sum(1 for r in settled if r["wynik"] == "wygrany"),
            "roi_flat": round(roi, 2),
            "okazje_rozliczone": len(okazje),
        },
        "po_rynku": po_rynku,
        "ostatnie": ostatnie,
    }
