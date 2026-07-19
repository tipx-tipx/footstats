"""Scanner value betów STS na statystyki zawodnika (cross-book vs Superbet).

Po co: STS regularnie PRZESZACOWUJE niszowe rynki propsowe (faule, odbiory,
niecelne, przechwyty, celne). Tam gdzie Superbet wycenia „przynajmniej 2 faule"
na 1.53, STS potrafi dać 2.20 na to samo zdarzenie. To jest miękka linia = value.

Ten job zestawia ofertę STS z Superbetem dla WSPÓLNYCH meczów i wypisuje
VALUE ALERTY: selekcje „powyżej", gdzie kurs STS płaci istotnie więcej, niż
wynika z ceny Superbetu po zdjęciu marży (referencja „fair"). Gra tylko „powyżej"
(decyzja usera — patrz build_wc_fast).

Referencja fair:
  * pierwsza: devig kursu Superbetu na tę samą linię (betting.implied_prob_one_sided).
    EV wzięcia STS = p_superbet_fair * kurs_STS - 1.
  * druga (kontrola): samospójność SIATKI linii Superbetu (betting.internal_fair_odds)
    — łapie pomyłkę tradera „reszta siatki 1,55, a tu 2,20".

Uruchomienie WYŁĄCZNIE LOKALNE (domowe IP) — STS/Superbet z chmury bywają
blokowane (POTWIERDZONE 2026-07-18: GitHub Actions/Azure dostaje 403 z Cloudflare
STS). Dlatego model on-demand: user odpala z domowego IP, wynik ląduje w Supabase
(klucz `sts_value`), a apka na Vercelu czyta z bazy — nic nie chodzi w tle.

STS schodzi po WebSocket (~14 s nasłuchu/mecz), ale to CZEKANIE na sieć (~0 CPU),
więc mecze skanujemy RÓWNOLEGLE (--rownolegle). value bet STS (definicja
produktowa) = MODEL analizuje selekcję (p_model z legi_pool) ORAZ STS przepłaca
vs Superbet — dlatego dokładamy stronę modelu i flagę `value_potwierdzony`.

  python -m footstats.jobs.sts_value                        # wspólna oferta, 3 dni
  python -m footstats.jobs.sts_value --dni 5 --min-ev 8     # szerzej, wyższy próg
  python -m footstats.jobs.sts_value --druzyna argentyn     # tylko mecze z filtrem
  python -m footstats.jobs.sts_value --do-supabase --bez-pliku   # tryb produktowy (klik .bat)
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .. import supa
from ..model import betting
from ..sources import sts, superbet
from ..sources.superbet import norm_name

# nazwy rynków po polsku (podzbiór pokrywany przez STS + Superbet — propsy)
MARKET_NAMES_PL = {
    "shots": "Strzały", "sot": "Strzały celne",
    "shots_off_target": "Strzały niecelne", "shots_blocked": "Strzały zablokowane",
    "fouls_committed": "Faule popełnione", "fouls_won": "Faule wywalczone",
    "tackles": "Odbiory", "interceptions": "Przechwyty",
    "yellow_card": "Żółta kartka",
}

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "store" / "sts_value.json"


def _pair_key(home: str, away: str) -> frozenset:
    """Nieuporządkowana para znormalizowanych nazw drużyn.

    Nieuporządkowana, bo przy meczach na neutralnym terenie (MŚ) STS i Superbet
    mogą inaczej wyznaczyć gospodarza (STS: „Argentyna - Hiszpania", Superbet:
    „Hiszpania · Argentyna") — inaczej ten sam mecz by się nie sparował.
    """
    return frozenset({norm_name(home), norm_name(away)})


def _linia_opis(line: float) -> str:
    """0.5 -> 'przynajmniej 1', 1.5 -> 'przynajmniej 2' (STS: 'N lub więcej')."""
    return f"przynajmniej {math.floor(line) + 1}"


def _when(ts: int | None) -> str:
    if not ts:
        return "?"
    delta = ts - int(time.time())
    if delta < 0:
        return "trwa/po"
    h = delta / 3600.0
    if h < 24:
        return f"za {round(h)} h"
    return f"za {round(h / 24)} dni"


def build_common_matches(days_ahead: int, druzyna: str | None) -> list[dict]:
    """Przecięcie oferty STS i Superbetu po nieuporządkowanej parze drużyn.

    Zwraca listę {pair, fid, sb_event, home, away, ts} dla meczów obecnych
    w OBU bukmacherach (tylko takie da się porównać cross-book).
    """
    print("· pobieram katalog meczów STS (WebSocket i_pl)...")
    sts_index = sts.match_ids_by_teams()  # {(nh, na): fid}
    print(f"  STS: {len(sts_index)} meczów")

    print("· pobieram listę meczów Superbet...")
    sb_events = superbet.list_events(days_ahead=days_ahead)
    print(f"  Superbet: {len(sb_events)} meczów")

    # indeks STS po nieuporządkowanej parze (klucz frozenset)
    sts_by_pair: dict[frozenset, str] = {}
    for (nh, na), fid in sts_index.items():
        sts_by_pair[frozenset({nh, na})] = fid

    common: list[dict] = []
    seen: set[frozenset] = set()
    now = int(time.time())
    horizon = now + days_ahead * 86400
    for ev in sb_events:
        name = ev.get("matchName") or ""
        parts = [p.strip() for p in name.split("·")]
        if len(parts) != 2:
            continue
        home, away = parts
        pair = _pair_key(home, away)
        if pair in seen or pair not in sts_by_pair:
            continue
        if druzyna and druzyna.lower() not in norm_name(name):
            continue
        try:
            ts = int(ev.get("matchTimestamp") or 0)
            if ts > 1e11:
                ts //= 1000
        except (TypeError, ValueError):
            ts = 0
        if ts and ts > horizon:
            continue
        seen.add(pair)
        common.append({
            "pair": pair, "fid": sts_by_pair[pair], "sb_event": ev,
            "home": home, "away": away, "ts": ts,
        })
    common.sort(key=lambda m: m["ts"] or 1 << 62)
    return common


def _match_baseline(sts_norm: dict, sb_players: dict) -> float:
    """Mediana ilorazu kurs_STS/kurs_Superbet po wspólnych selekcjach meczu.

    STS bywa GLOBALNIE luźniejszy (wyższa marża na plusie) — wtedy każdy kurs
    jest ~x1.1 wyższy i to nie jest per-selekcja value. Baseline pozwala odjąć
    to tło i szukać selekcji odstających PONAD typową różnicę tego meczu.
    """
    ratios = []
    for pkey, bases in sts_norm.items():
        sbm = sb_players.get(pkey) or {}
        for base, lines in bases.items():
            sbl = sbm.get(base) or {}
            for line, (odd, _ot) in lines.items():
                sbo = (sbl.get(line) or {}).get("over")
                if sbo:
                    ratios.append(odd / sbo)
    return float(statistics.median(ratios)) if len(ratios) >= 4 else 1.0


def scan_match(m: dict, ws_seconds: float, min_ev: float, min_ratio: float) -> list[dict]:
    """Zwróć value alerty dla jednego meczu (selekcje 'powyżej', STS vs Superbet)."""
    ev = m["sb_event"]
    parts = [p.strip() for p in (ev.get("matchName") or "·").split("·")]
    try:
        sb = superbet.fetch_stat_odds(ev["eventId"], parts[0], parts[1])
    except Exception as e:
        print(f"    ! Superbet błąd: {e}")
        return []
    # include_overtime: przy pucharach odbiory/niecelne/przechwyty STS daje
    # WYŁĄCZNIE z dogrywką — a to sztandarowe rynki value (patrz sts.py)
    sts_odds = sts.fetch_stat_odds(m["fid"], seconds=ws_seconds, include_overtime=True)

    sb_players = sb.get("players", {})
    sts_norm = sts.normalized_players(sts_odds)
    baseline = _match_baseline(sts_norm, sb_players)
    label = f"{m['home']} - {m['away']}"

    alerts: list[dict] = []
    for pkey, bases in sts_norm.items():
        sb_markets = sb_players.get(pkey)
        if not sb_markets:
            continue  # brak referencji Superbet dla tego zawodnika
        for base, sts_lines in bases.items():
            sb_lines = sb_markets.get(base)
            if not sb_lines:
                continue
            # samospójność siatki Superbetu (kontrolna, niezależna referencja fair)
            probs_grid = {
                l: betting.implied_prob_one_sided(v["over"])
                for l, v in sb_lines.items() if v.get("over")
            }
            fair_grid = betting.internal_fair_odds(probs_grid) if len(probs_grid) >= 3 else {}
            ladder_depth = len(sts_lines)

            for line, (sts_over, is_ot) in sts_lines.items():
                sb_slot = sb_lines.get(line)
                if not sb_slot or not sb_slot.get("over"):
                    continue
                sb_over = sb_slot["over"]
                if not (betting.MIN_ODDS <= sts_over <= betting.MAX_ODDS):
                    continue
                if sts_over <= sb_over:
                    continue  # value tylko gdy STS płaci WIĘCEJ niż Superbet
                # referencja fair = devig Superbetu na tej linii. Dla rynków z
                # dogrywką to DOLNE oszacowanie EV (dogrywka podnosi P("over"))
                p_fair = betting.implied_prob_one_sided(sb_over)
                ev_pct = (p_fair * sts_over - 1.0) * 100.0
                ratio = sts_over / sb_over
                if ev_pct < min_ev or ratio < min_ratio:
                    continue
                fair_kurs = fair_grid.get(line)
                # --- warstwa PEWNOŚCI: liczba niezależnych potwierdzeń, że STS
                # przepłaca akurat TĘ selekcję (a nie że jest globalnie luźny) ---
                sygnaly = 0
                if fair_kurs and sts_over >= fair_kurs * 1.10:
                    sygnaly += 1  # własna siatka Superbetu też mówi „za drogo"
                nadwyzka = ratio / baseline if baseline else 1.0
                if nadwyzka >= 1.15:
                    sygnaly += 1  # odstaje ponad tło różnicy tego meczu
                if ladder_depth >= 3:
                    sygnaly += 1  # pełna drabinka linii = kurs świeży, nie osierocony
                pewnosc = "wysoka" if sygnaly >= 3 else "średnia" if sygnaly == 2 else "niska"
                alerts.append({
                    "mecz": label, "mecz_ts": m["ts"],
                    "zawodnik": pkey, "rynek_kod": base,
                    "rynek": MARKET_NAMES_PL.get(base, base),
                    "linia": line, "linia_opis": _linia_opis(line),
                    "z_dogrywka": is_ot,
                    # rynki z dogrywką na STS mają SuperSub ("SuperZmiana"): przy
                    # zejściu zawodnika zakład PRZENOSI SIĘ na zmiennika — znika
                    # ryzyko minut, więc "powyżej" jest jeszcze bardziej prawdopodobne
                    # niż fair 90-min pojedynczego zawodnika (dodatkowa wartość)
                    "superzmiana": is_ot,
                    "kurs_sts": round(sts_over, 2),
                    "kurs_superbet": round(sb_over, 2),
                    "ratio": round(ratio, 2),
                    "nadwyzka_vs_baseline": round(nadwyzka, 2),
                    "p_fair_superbet": round(p_fair, 4),
                    "ev_pct": round(ev_pct, 1),
                    "fair_kurs_siatka": round(fair_kurs, 2) if fair_kurs else None,
                    "sygnaly": sygnaly,
                    "pewnosc": pewnosc,
                })
    return alerts


def _load_model_index() -> dict:
    """Indeks p_model per (zawodnik_norm, rynek_kod, linia) — strona „powyzej".

    Preferuje `sts_model` (PEŁNE pokrycie: każda kwotowana linia, nie tylko pula
    kuponów), z fallbackiem na `legi_pool` (gdyby cykl nie wyemitował jeszcze
    sts_model). Klucz po znormalizowanej nazwie — ta sama norm_name, po której
    scan_match paruje STS↔Superbet, więc pasuje do `alert['zawodnik']`. Puste bez
    env Supabase (tryb lokalny) — wtedy alerty po prostu nie dostają p_model.
    """
    src = supa.get_key("sts_model")
    if not isinstance(src, list) or not src:
        src = supa.get_key("legi_pool")
    index: dict = {}
    if not isinstance(src, list):
        return index
    for e in src:
        if not isinstance(e, dict) or str(e.get("strona")) != "powyzej":
            continue
        try:
            key = (norm_name(e.get("podmiot") or ""), e.get("rynek_kod"), round(float(e["linia"]), 1))
        except (TypeError, ValueError, KeyError):
            continue
        if not key[0] or not key[1]:
            continue
        cur = index.get(key)  # przy duplikatach preferuj wyższy p_model
        if cur is None or float(e.get("p_model") or 0) > float(cur.get("p_model") or 0):
            index[key] = e
    return index


# powody z rejestru odrzuceń, które znaczą „model NIE ufa tej selekcji" — weto
# potwierdzenia. Pomijamy `tylko_w_puli` (typ jest, wygrał inny na karcie meczu),
# `brak_kursu` (to nie model) i `kurs_lub_szansa_poza_widelkami` (dotyczy kwotowania
# Superbetu, a STS ma inny kurs).
_POWOD_WETO = {
    "za_malo_historii": "za mało historii, by model policzył szansę",
    "za_malo_zdarzen": "za mało zdarzeń w historii na ten rynek",
    "krotka_historia": "za krótka historia (poniżej progu)",
    "chwiejna_predykcja": "chwiejna predykcja, model sam nie jest pewny",
    "rozjazd_z_rynkiem": "model mocno rozjeżdża się z rynkiem",
}


def _load_rejections() -> dict:
    """Mapa (zawodnik_norm, rynek_kod) -> powód po ludzku, z klucza `odrzucenia`.

    Tylko powody z `_POWOD_WETO` (brak zaufania modelu). Zamyka scenariusz, w
    którym „value potwierdzony" ląduje na selekcji, którą własne sito modelu
    by wyrzuciło. Granulacja (zawodnik, rynek) — bo model odrzuca całą parę,
    niezależnie od linii.
    """
    rej = supa.get_key("odrzucenia")
    out: dict = {}
    if not isinstance(rej, list):
        return out
    for r in rej:
        if not isinstance(r, dict):
            continue
        opis = _POWOD_WETO.get(str(r.get("powod")))
        if not opis:
            continue
        key = (norm_name(r.get("podmiot") or ""), r.get("rynek_kod"))
        if key[0] and key[1]:
            out[key] = opis
    return out


def _enrich_with_model(alerts: list[dict], model_index: dict, rejections: dict) -> None:
    """Dołącz stronę modelu do alertów STS (in place).

    value bet STS = MODEL analizuje selekcję ORAZ STS przepłaca vs Superbet.
    scan_match dał już drugą część (STS > Superbet, EV z devigu). Tu dokładamy
    p_model (pełne pokrycie z sts_model) i EV wg NIEZALEŻNEJ wyceny modelu
    (p_model * kurs_STS - 1). `value_potwierdzony` wymaga: model widzi dodatni EV
    ORAZ NIE odrzucił tej selekcji. `model_odrzucil` + `odrzucenie_powod` to weto
    z rejestru odrzuceń (własne sito modelu) — zamyka „potwierdzone" na typie,
    którego model sam by nie wystawił.
    """
    for a in alerts:
        powod_weto = rejections.get((a["zawodnik"], a["rynek_kod"]))
        key = (a["zawodnik"], a["rynek_kod"], round(float(a["linia"]), 1))
        e = model_index.get(key)
        if e is None:
            a.update(zawodnik_nazwa=None, p_model=None, ev_model_pct=None,
                     oczekiwane_minuty=None, druzyna=None, ma_model=False,
                     model_odrzucil=bool(powod_weto), odrzucenie_powod=powod_weto,
                     value_potwierdzony=False)
            continue
        p = float(e.get("p_model") or 0) or None
        ev_model = round((p * a["kurs_sts"] - 1.0) * 100.0, 1) if p else None
        a.update(
            zawodnik_nazwa=e.get("podmiot"),
            p_model=round(p, 4) if p else None,
            ev_model_pct=ev_model,
            oczekiwane_minuty=e.get("oczekiwane_minuty"),
            druzyna=e.get("druzyna"),
            ma_model=True,
            model_odrzucil=bool(powod_weto),
            odrzucenie_powod=powod_weto,
            # potwierdzony TYLKO gdy model widzi dodatni EV I NIE odrzucił selekcji
            value_potwierdzony=bool(ev_model is not None and ev_model > 0 and not powod_weto),
        )


def _scan_all(common: list[dict], workers: int, ws_seconds: float,
              min_ev: float, min_ratio: float) -> list[dict]:
    """Przeskanuj mecze (równolegle, bo to I/O-bound: nasłuch WS ≈ 0 CPU).

    workers=1 → sekwencyjnie. Kolejność wyników nieistotna (i tak sortujemy).
    """
    total = len(common)
    out: list[dict] = []
    done = 0

    def run(m: dict):
        return m, scan_match(m, ws_seconds, min_ev, min_ratio)

    if workers <= 1:
        it = (run(m) for m in common)
        results = ((m, r) for (m, r) in it)
        for m, alerts in results:
            done += 1
            print(f"[{done}/{total}] {m['home']} - {m['away']}  ({_when(m['ts'])})  value={len(alerts)}")
            out.extend(alerts)
        return out

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(run, m): m for m in common}
        for fut in as_completed(futs):
            m = futs[fut]
            done += 1
            try:
                _, alerts = fut.result()
            except Exception as e:  # noqa: BLE001
                print(f"[{done}/{total}] {m['home']} - {m['away']}  ! błąd: {e}")
                continue
            print(f"[{done}/{total}] {m['home']} - {m['away']}  ({_when(m['ts'])})  value={len(alerts)}")
            out.extend(alerts)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Scanner value betów STS vs Superbet (propsy zawodnicze)")
    ap.add_argument("--dni", type=int, default=3, help="horyzont meczów w przód (domyślnie 3)")
    ap.add_argument("--min-ev", type=float, default=6.0, help="minimalny EV%% (domyślnie 6)")
    ap.add_argument("--min-ratio", type=float, default=1.12, help="min. iloraz kurs_STS/kurs_Superbet (domyślnie 1.12)")
    ap.add_argument("--druzyna", type=str, default=None, help="filtr: fragment nazwy drużyny/meczu")
    ap.add_argument("--max-mecze", type=int, default=12, help="limit meczów do skanu")
    ap.add_argument("--ws-sekundy", type=float, default=14.0, help="czas nasłuchu STS na mecz")
    ap.add_argument("--rownolegle", type=int, default=8,
                    help="ile meczów skanować naraz (I/O-bound; 1 = sekwencyjnie)")
    ap.add_argument("--do-supabase", action="store_true",
                    help="zapisz wynik do Supabase (klucz sts_value) — tryb produktowy")
    ap.add_argument("--bez-pliku", action="store_true",
                    help="nie zapisuj lokalnego pliku sts_value.json")
    args = ap.parse_args()

    # konsola Windows domyślnie cp1252 — polskie znaki/emoji w print() by ją wywaliły
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # .env (Supabase) — wzorem cycle.py; potrzebne do p_model i zapisu do bazy
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
    except Exception:
        pass

    model_index = _load_model_index()
    rejections = _load_rejections()
    if model_index:
        print(f"· model: {len(model_index)} selekcji z p_model, {len(rejections)} odrzuceń (weto)")
    else:
        print("· model: brak p_model (brak env Supabase lub pusty sts_model/legi_pool) — alerty bez potwierdzenia modelu")

    common = build_common_matches(args.dni, args.druzyna)
    print(f"\n· wspólnych meczów STS∩Superbet (≤{args.dni} dni): {len(common)}")
    if args.max_mecze and len(common) > args.max_mecze:
        print(f"  (skanuję pierwsze {args.max_mecze}, bliższe czasowo)")
        common = common[: args.max_mecze]

    workers = max(1, min(args.rownolegle, len(common) or 1))
    print(f"· skanuję {len(common)} meczów po {workers} naraz (STS ~{args.ws_sekundy:.0f} s nasłuchu/mecz)...")
    all_alerts = _scan_all(common, workers, args.ws_sekundy, args.min_ev, args.min_ratio)

    _enrich_with_model(all_alerts, model_index, rejections)

    # sortowanie: najpierw POTWIERDZONE przez model (model + cross-book = pełny
    # value bet STS), potem PEWNOŚĆ cross-book, potem EV — bo sam duży EV bywa
    # nieostrą/osieroconą linią STS, nie realnym value
    all_alerts.sort(key=lambda a: (a.get("value_potwierdzony", False), a["sygnaly"], a["ev_pct"]), reverse=True)

    n_model = sum(1 for a in all_alerts if a.get("value_potwierdzony"))
    wys = sum(1 for a in all_alerts if a["pewnosc"] == "wysoka")
    print("\n" + "=" * 70)
    print(f"VALUE ALERTY (STS przepłaca vs Superbet): {len(all_alerts)}")
    print(f"  wysoka pewność cross-book (3/3): {wys}   ·   potwierdzone przez model: {n_model}")
    print("=" * 70)
    for a in all_alerts:
        kropki = "●" * a["sygnaly"] + "○" * (3 - a["sygnaly"])
        fair = f", fair-siatka {a['fair_kurs_siatka']}" if a["fair_kurs_siatka"] else ""
        tagi = "  ⏱ z dogrywką + SuperZmiana" if a["z_dogrywka"] else ""
        nazwa = a.get("zawodnik_nazwa") or a["zawodnik"]
        model_txt = ""
        if a.get("ma_model"):
            znak = "+" if (a["ev_model_pct"] or 0) >= 0 else ""
            ptw = "  ✓ potwierdzony przez model" if a.get("value_potwierdzony") else ""
            model_txt = f"\n   model: p={a['p_model']}, EV(model) {znak}{a['ev_model_pct']}%{ptw}"
        print(
            f"\n🔵 VALUE ALERT!  [{kropki} {a['pewnosc']}]  {a['mecz']}  ({_when(a['mecz_ts'])})\n"
            f"   {nazwa} – {a['rynek']}: {a['linia_opis']}{tagi}\n"
            f"   STS {a['kurs_sts']}  vs  Superbet {a['kurs_superbet']}  "
            f"(x{a['ratio']}, EV +{a['ev_pct']}%, ponad tło x{a['nadwyzka_vs_baseline']}{fair}){model_txt}"
        )

    payload = {
        "generated_ts": int(time.time()),
        "n_meczow": len(common),
        "n_alertow": len(all_alerts),
        "n_potwierdzonych": n_model,
        "alerty": all_alerts,
    }
    if not args.bez_pliku:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n· zapisano {len(all_alerts)} alertów do {OUT_PATH}")
    if args.do_supabase:
        ok = supa.put_key("sts_value", payload)
        print(f"· Supabase (klucz sts_value): {'zapisano' if ok else 'NIE zapisano (brak env SUPABASE_*?)'}")


if __name__ == "__main__":
    main()
