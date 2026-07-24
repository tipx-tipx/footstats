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
from ..sources import statshub
from ..sources.sofascore import SofascoreSource
from ..sources.superbet import norm_name

# ~105 min po pierwszym gwizdku = mecz zamknięty (jak MECZ_KONIEC_PO_S w
# rozliczaniu; nie importujemy go, żeby nie ciągnąć modelu/numpy do workera).
MECZ_KONIEC_PO_S = 6300
MAX_WIEK_S = 7 * 86400   # starsze wpisy cache prune'ujemy (payload mały)

# --- średnie sezonowe graczy (sekcja "sezony" na kartach drabinek) ---
SEZON_MAX_GRACZY = 20        # ilu graczy dociągamy na jeden przebieg (2 s/req
                             # rate-limit => ~2-3 min; kolejne przebiegi dolewają)
SEZON_ODSWIEZ_S = 7 * 86400  # sezon w toku rośnie — odświeżaj raz na tydzień
SEZON_NEG_ODSWIEZ_S = 2 * 86400  # pusty wynik ponawiamy szybciej (id mógł
                                 # dojść do Sofascore / poprawiliśmy resolver)
SEZON_MIN_MECZE = 4          # mniej występów = agregat-szum, pomijamy
SEZON_MAX_TURNIEJE = 2       # ligi gracza (Sofascore zwraca najistotniejsze 1.)
SEZON_MAX_SEZONY = 2         # bieżący + poprzedni sezon per liga

# pole agregatu Sofascore -> nasz kod rynku
MAP_SEZON = {
    "totalShots": "shots", "shotsOnTarget": "sot",
    "shotsFromOutsideTheBox": "shots_outside_box",
    "fouls": "fouls_committed", "wasFouled": "fouls_won",
    "offsides": "offsides", "tackles": "tackles",
    "interceptions": "interceptions", "blockedShots": "shots_blocked",
}

# rynki zawodnicze (odsiew team_* przy zbieraniu kandydatów z typy_log)
RYNKI_ZAWODNIKA = set(MAP_SEZON.values()) | {
    "headed_shots", "headed_sot", "sot_outside_box", "shots_off_target",
}


def _srednie_sezonu(st: dict) -> dict | None:
    """Agregat sezonu Sofascore -> {mecze, minuty, na_mecz, na90} | None."""
    mecze = st.get("appearances") or 0
    minuty = st.get("minutesPlayed") or 0
    if mecze < SEZON_MIN_MECZE:
        return None
    na_mecz: dict = {}
    na90: dict = {}
    for pole, mk in MAP_SEZON.items():
        v = st.get(pole)
        if v is None:
            continue
        na_mecz[mk] = round(float(v) / mecze, 2)
        if minuty:
            na90[mk] = round(float(v) / minuty * 90.0, 2)
    if not na_mecz:
        return None
    return {"mecze": int(mecze), "minuty": int(minuty),
            "na_mecz": na_mecz, "na90": na90}


def _kandydaci_sezonow(now: int) -> list[dict]:
    """Gracze do dociągnięcia: lista z chmury, awaryjnie z typy_log."""
    kand = supa.get_key("sezon_kandydaci") or []
    if kand:
        return kand
    # fallback (np. przed pierwszym cyklem z drabinkami): gracze z logu typów;
    # "mecz" (Home – Away) niesie drużyny do weryfikacji homonimów
    log = supa.get_key("typy_log") or {}
    widziani: set[int] = set()
    out = []
    for r in sorted(log.values(),
                    key=lambda r: -(r.get("kickoff_ts") or 0)):
        pid = r.get("podmiot_id")
        if (pid and pid not in widziani
                and r.get("rynek_kod") in RYNKI_ZAWODNIKA):
            widziani.add(pid)
            out.append({"id": int(pid), "nazwa": r.get("podmiot"),
                        "mecz": r.get("mecz"), "mecz_id": r.get("mecz_id")})
    return out


def _tok(s) -> set[str]:
    return set(norm_name(str(s or "")).split())


def _tok_pasuje(a: set[str], b: set[str]) -> bool:
    return bool(a and b and (a <= b or b <= a))


def _id_z_shotmapy(mecz_id, nazwa_tok: set[str], sm_cache: dict) -> int | None:
    """Kanoniczne id gracza z shotmapy JEGO meczu (statshub, otwarte API).

    Najpewniejszy kanał przy rozjeździe id: shotmapa niesie playerName +
    playerId Sofascore, a dopasowujemy w obrębie jednego, znanego meczu —
    zero ryzyka homonimów (wyszukiwarka np. nie znajduje "Mikael" z Ceará
    w top-10 trafień, shotmapa Ceará–CRB wskazuje go wprost)."""
    if not mecz_id or not nazwa_tok:
        return None
    if mecz_id not in sm_cache:
        try:
            sm_cache[mecz_id] = statshub.fetch_event_shotmap(int(mecz_id))
        except Exception:
            sm_cache[mecz_id] = []
    for s in sm_cache[mecz_id]:
        if s.get("playerId") and _tok_pasuje(_tok(s.get("playerName")),
                                             nazwa_tok):
            return int(s["playerId"])
    return None


def _sezony_gracza(
    src: SofascoreSource, pid: int, nazwa: str | None,
    druzyny_tok: list[set[str]],
    mecz_id=None, sm_cache: dict | None = None,
) -> tuple[int, list[dict]]:
    """Lista turniejów+sezonów gracza — po id wprost, awaryjnie po nazwisku.

    Dwie pułapki tożsamości (zmierzone 2026-07-24):
      * feed propsów statshub miewa WŁASNE id (Mikael 938421535 w typach vs
        kanoniczne 994017 w Sofascore) — id wprost daje 404 albo, gorzej,
        CUDZY profil (kolizja przestrzeni id). Dlatego id wprost bierzemy
        tylko po zgodności NAZWISKA z profilu Sofascore.
      * wyszukiwarka zwraca homonimy (3× "Bruno Gomes"; pierwszy z ligi
        indonezyjskiej, nasz gra w Internacionalu) — hit przyjmujemy dopiero
        po zgodności DRUŻYNY profilu z drużynami kandydata (druzyny_tok);
        bez informacji o drużynie nie zgadujemy, jak debiutanci w radar.py.

    Zwraca (rozwiązane_id, turnieje) — staty sezonu MUSZĄ iść po rozwiązanym
    id, nie po id feedu (bug 2026-07-24: staty szły po starym pid -> 404 ->
    ciche puste sezony u każdego gracza rozwiązanego fallbackiem).
    """
    n_tok = _tok(nazwa)
    prof = src.player_profile(pid)
    if prof is not None:
        p_tok = _tok(prof.get("name"))
        if not n_tok or _tok_pasuje(p_tok, n_tok):
            try:
                t = src.player_seasons(pid)
                if t:
                    return pid, t
            except Exception:
                pass
        # id istnieje, ale nazwisko się nie zgadza = kolizja -> szukaj dalej
    if not nazwa or not n_tok:
        return pid, []
    # kanał 2: shotmapa meczu kandydata (kanoniczne id bez homonimów)
    sid = _id_z_shotmapy(mecz_id, n_tok, sm_cache if sm_cache is not None
                         else {})
    if sid and sid != pid:
        try:
            seas = src.player_seasons(sid)
            if seas:
                return sid, seas
        except Exception:
            pass
    # kanał 3: wyszukiwarka + weryfikacja drużyny profilu
    try:
        trafienia = statshub.search_players(str(nazwa))
    except Exception:
        return pid, []
    for t in trafienia[:8]:
        tid = t.get("id")
        if not tid or int(tid) == pid:
            continue
        if not _tok_pasuje(_tok(t.get("name")), n_tok):
            continue
        if druzyny_tok:
            prof_t = src.player_profile(int(tid))
            team_tok = _tok((prof_t or {}).get("team"))
            if not any(_tok_pasuje(team_tok, d) for d in druzyny_tok):
                continue  # inny człowiek o tym samym nazwisku
        elif len(trafienia) > 1:
            continue  # homonimy bez drużyny do weryfikacji — nie zgadujemy
        try:
            seas = src.player_seasons(int(tid))
        except Exception:
            continue
        if seas:
            return int(tid), seas
    return pid, []


def _backfill_sezony(src: SofascoreSource, now: int) -> None:
    """Dociągnij średnie sezonowe brakujących/przeterminowanych graczy.

    Wynik do klucza `player_sezon` (pid -> {name, fetched_ts, sezony[]}) —
    czyta go radar/drabinki w chmurze. Gracz raz pobrany = cache na tydzień.
    """
    kandydaci = _kandydaci_sezonow(now)
    cache = supa.get_key("player_sezon") or {}

    def _stale(k: dict) -> bool:
        rec = cache.get(str(k.get("id"))) or {}
        ttl = SEZON_ODSWIEZ_S if rec.get("sezony") else SEZON_NEG_ODSWIEZ_S
        return bool(k.get("id")) and now - (rec.get("fetched_ts") or 0) > ttl

    przeterminowani = [k for k in kandydaci if _stale(k)]
    do_pobrania = przeterminowani[:SEZON_MAX_GRACZY]
    pominieto = len(przeterminowani) - len(do_pobrania)
    print(f"Sezony: kandydatów {len(kandydaci)}, do pobrania teraz "
          f"{len(do_pobrania)}" + (f" (+{pominieto} w kolejnych przebiegach)"
                                   if pominieto else ""), flush=True)
    if not do_pobrania:
        return
    zebrano = 0
    sm_shot_cache: dict = {}   # shotmapy meczów kandydatów (jedna na mecz)
    for k in do_pobrania:
        pid = int(k["id"])
        druzyny_tok = [_tok(k.get("druzyna"))] if k.get("druzyna") else []
        for strona in str(k.get("mecz") or "").split("–"):
            t = _tok(strona)
            if t:
                druzyny_tok.append(t)
        sofa_id, turnieje = _sezony_gracza(
            src, pid, k.get("nazwa"), druzyny_tok,
            mecz_id=k.get("mecz_id"), sm_cache=sm_shot_cache,
        )
        if not turnieje:
            print(f"  gracz {pid} ({k.get('nazwa')}): nie znaleziono w "
                  f"Sofascore (ani po id, ani po nazwisku)", flush=True)
            # negative-cache — nie młócimy nieznajdywalnych co przebieg
            cache[str(pid)] = {"name": k.get("nazwa"), "fetched_ts": now,
                               "sezony": []}
            continue
        sezony = []
        for ut in turnieje[:SEZON_MAX_TURNIEJE]:
            utid = (ut.get("uniqueTournament") or {}).get("id")
            utn = (ut.get("uniqueTournament") or {}).get("name") or "?"
            if not utid:
                continue
            for s in (ut.get("seasons") or [])[:SEZON_MAX_SEZONY]:
                try:
                    # UWAGA: po ROZWIĄZANYM sofa_id, nie po id feedu (pid)
                    st = src.player_season_stats(sofa_id, utid, s["id"])
                except Exception:
                    continue
                agg = _srednie_sezonu(st)
                if agg:
                    sezony.append({"turniej": utn,
                                   "rok": str(s.get("year") or "?"), **agg})
        if sezony:
            cache[str(pid)] = {"name": k.get("nazwa"), "sofa_id": sofa_id,
                               "fetched_ts": now, "sezony": sezony}
            zebrano += 1
        else:
            # negative-cache: brak danych też zapamiętujemy (nie młócimy
            # co przebieg gracza, którego Sofascore nie zna pod tym id)
            cache[str(pid)] = {"name": k.get("nazwa"), "fetched_ts": now,
                               "sezony": []}
    ok = supa.put_key("player_sezon", cache)
    print(f"Sezony: zebrano {zebrano}/{len(do_pobrania)} graczy; "
          f"cache: {len(cache)}; push={ok}", flush=True)

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

        # średnie sezonowe graczy pod karty drabinek (cache tygodniowy) —
        # osobny try: awaria sezonów nie może cofnąć rozliczeń egzotyki
        try:
            _backfill_sezony(src, now)
        except Exception:
            print("Sezony pominięte w tym przebiegu:\n"
                  f"{traceback.format_exc()}", file=sys.stderr, flush=True)

        print(f"[{stamp}] OK — chmura dorozliczy egzotykę w najbliższym cyklu.",
              flush=True)
    except Exception:
        print(f"[{stamp}] BŁĄD:\n{traceback.format_exc()}", file=sys.stderr,
              flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
