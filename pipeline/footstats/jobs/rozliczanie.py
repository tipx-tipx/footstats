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


# próbuj rozliczać już ~105 min po kickoffie (źródła i tak wymagają statusu
# "zakończony") — status kuponu odświeża się tuż po końcowym gwizdku
MECZ_KONIEC_PO_S = 105 * 60
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


MIN_N_KALIBRACJI = 25          # od tylu rozliczonych typów na rynek korygujemy
BIAS_CAP = (0.85, 1.15)        # ostrożnie: maks. +-15% korekty szansy


def compute_bias(log: dict, min_n: int = MIN_N_KALIBRACJI) -> dict[str, float]:
    """Współczynniki korekty szansy per rynek z rozliczonych typów.

    bias = (trafienia + 2) / (suma zamrożonych p_model + 2) — czyli o ile
    rzeczywista częstość odbiega od tego, co model twierdził. >1 = model
    niedoszacowuje, <1 = przeszacowuje. Zwracamy tylko rynki z próbą >= min_n,
    z twardym capem — korekta ma dokręcać, nie rządzić.
    """
    grupy: dict[str, list[dict]] = {}
    for r in log.values():
        if r.get("wynik") in ("wygrany", "przegrany"):
            grupy.setdefault(r["rynek_kod"], []).append(r)
    out: dict[str, float] = {}
    for mk, grp in grupy.items():
        if len(grp) < min_n:
            continue
        traf = sum(1 for r in grp if r["wynik"] == "wygrany")
        suma_p = sum(r["p_model"] for r in grp)
        bias = (traf + 2.0) / (suma_p + 2.0)
        out[mk] = round(max(BIAS_CAP[0], min(BIAS_CAP[1], bias)), 3)
    return out


def market_bias() -> dict[str, float]:
    """Korekty kalibracyjne z logu w Supabase (puste, gdy brak danych/env)."""
    log = supa.get_key("typy_log") or {}
    return compute_bias(log)


def _kupon_do_logu(log_kuponow: dict, kupony_list: list[dict], now: int) -> None:
    """Kupon dnia (horyzont+przedział) aktualizuje się do startu pierwszego
    meczu — potem jest zamrożony i czeka na rozliczenie legów."""
    dzien = time.strftime("%Y-%m-%d", time.localtime(now))
    for k in kupony_list:
        if k.get("styl") == "value" and not k.get("legi"):
            continue
        klucz = f"{k.get('horyzont', '?')}:{k.get('cel_label', k.get('cel'))}:{dzien}"
        rec = log_kuponow.get(klucz)
        pierwszy = min(l["kickoff_ts"] for l in k["legi"])
        if rec is None:
            log_kuponow[klucz] = {
                **k, "dzien": dzien, "opublikowano_ts": now, "wynik": None,
            }
        elif rec.get("wynik") is None and now < min(
            l["kickoff_ts"] for l in rec["legi"]
        ) and now < pierwszy:
            log_kuponow[klucz] = {
                **k, "dzien": dzien,
                "opublikowano_ts": rec["opublikowano_ts"], "wynik": None,
            }


def _rozlicz_kupony(log_kuponow: dict, typy_log: dict, now: int) -> list[dict]:
    """Wynik kuponu z wyników legów: przegrany od pierwszego pudła; wygrany,
    gdy wszystkie legi trafione (zwrot wyłącza lega z kursu, jak u buka)."""
    for rec in log_kuponow.values():
        if rec.get("wynik"):
            continue
        statusy = []
        for l in rec["legi"]:
            tk = (f"{l['mecz_id']}:{l.get('podmiot_id', 0)}:"
                  f"{l.get('rynek_kod', '')}:{l['linia']}:{l['strona']}")
            statusy.append((l, (typy_log.get(tk) or {}).get("wynik")))
        if any(s == "przegrany" for _, s in statusy):
            rec.update(wynik="przegrany", rozliczono_ts=now)
        elif all(s in ("wygrany", "zwrot") for _, s in statusy):
            kurs = 1.0
            for l, s in statusy:
                if s == "wygrany":
                    kurs *= l["kurs"]
            rec.update(wynik="wygrany", kurs_rozliczony=round(kurs, 2),
                       rozliczono_ts=now)
        rec["legi_trafione"] = sum(1 for _, s in statusy if s == "wygrany")
        rec["legi_rozliczone"] = sum(1 for _, s in statusy if s)
    return sorted(
        log_kuponow.values(),
        key=lambda r: (-(r.get("opublikowano_ts") or 0)),
    )[:40]


def rozlicz(value_bets: list[dict], kupony_list: list[dict] | None = None) -> dict:
    """Dopisz nowe typy do logu, rozlicz zakończone, zwróć podsumowanie."""
    log = supa.get_key("typy_log") or {}
    _dopisz_nowe(log, value_bets)
    # legi kuponów też muszą być w logu (pewniaki spoza publikowanych typów)
    for k in kupony_list or []:
        _dopisz_nowe(log, [{
            "mecz_id": l["mecz_id"], "mecz": l["mecz"],
            "kickoff_ts": l["kickoff_ts"],
            "podmiot_id": l.get("podmiot_id", 0),
            "podmiot": l["podmiot"], "rynek_kod": l.get("rynek_kod", ""),
            "rynek": l["rynek"], "linia": l["linia"], "strona": l["strona"],
            "kurs": l["kurs"], "bukmacher": l.get("bukmacher"),
            "p_model": l["p_model"], "pewnosc": l.get("pewnosc"),
            "sugestia": False,
        } for l in k["legi"]])
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

    # ---- historia kuponów ----
    log_kuponow = supa.get_key("kupony_log") or {}
    _kupon_do_logu(log_kuponow, kupony_list or [], now)
    kupony_hist = _rozlicz_kupony(log_kuponow, log, now)
    supa.put_key("kupony_log", log_kuponow)

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
        "kupony": kupony_hist,
    }
