"""WŁASNY STATSHUB – odpowiedzi w kształcie statshub z NASZYCH danych (etap 4, docs/plan-fotmob.md).

Po co
-----
Reszta pipeline'u czyta statshub w ściśle określonym kształcie (wiersze
`player/{id}/performance`, kadry, historie drużyn). Zamiast przepisywać
kilkanaście konsumentów, oddajemy im ten sam kształt z dwóch własnych źródeł:

* **do 29.10 – nasze dane statshub**: bank `trend_lib` (historie zawodników)
  i magazyn `hd_*` (mecze drużyn, numery meczów). Zero zapytań do sieci.
* **od 29.10 – baza meczów FotMob** (`fm_baza_*`) z numerami przetłumaczonymi
  przez mapę tożsamości (`tozsamosc`) na numery Sofascore.

⚑ OBIE CZĘŚCI ZAWSZE RAZEM. Bank łączy historie regułą „nowszy ostatni mecz
wygrywa całość” (`build_wc_fast._merge`), a odświeżanie trendów podmienia
`counts` w całości. Gdyby ta warstwa oddała same 2–3 mecze z FotMob, wyparłyby
one 20 meczów historii zawodnika. Ten sam mecz w obu częściach (start ±3 h)
bierzemy RAZ – z banku, bo to dokładnie to, co statshub wtedy oddał.

Kształty jak w `sources/statshub.py` (docs/etap0-mapowanie.md, „Pułapki
kształtu”): wiersze to DICTY (rozliczanie czyta `events` bez `_pierwszy`),
od najnowszego, mecze z 0 minut obecne, `yellowCard` tylko gdy kartka padła.
"""

from __future__ import annotations

import zlib
from collections import defaultdict

from .. import baza_meczow
from .. import tozsamosc as T
from . import statshub

TOL_MECZU_S = 3 * 3600

# nasz kod rynku (baza FotMob) → pole wiersza statshub `player_statistics_event`
POLA_SH = {
    "shots": "shots", "sot": "onTargetScoringAttempt", "shots_off_target": "shotOffTarget",
    "shots_blocked": "blockedScoringAttempt", "fouls_committed": "fouls", "fouls_won": "wasFouled",
    "tackles": "totalTackle", "interceptions": "interceptionWon", "offsides": "totalOffside",
    "dribbles_won": "wonContest",
}
# rynki z mapy strzałów → pola `extra-stats-batch`
POLA_EXTRA = {v: k for k, v in statshub.EXTRA_STATS_MAP.items()}
# rynek banku → pole wiersza (odwrotność mapy, z której bank powstał)
RYNEK_NA_POLE = {v: k for k, v in statshub.PERF_STATTYPE_MAP.items()}

# numery meczów banku bez odpowiednika w `hd_*` (stary klub zawodnika, rozgrywki
# spoza magazynu): stały numer z czasu startu – nie zderza się z Sofascore
# (< 10⁸), z naszymi syntetycznymi (9·10⁸) ani z zastępczymi FotMob (4·10⁹)
MECZ_BANKU = 3_000_000_000


def _ev_banku(ts: int, druzyna: int, rywal: int) -> int:
    para = f"{min(druzyna, rywal)}:{max(druzyna, rywal)}:{int(ts) // 60}"
    return MECZ_BANKU + zlib.crc32(para.encode()) % 900_000_000


class Zrodlo:
    """Indeks naszych danych pod odpowiedzi w kształcie statshub.

    `baza` – {id meczu FotMob: zapis zwięzły} (`baza_meczow.wczytaj`),
    `trend_lib` – bank, `eventy` – `tozsamosc.eventy_z_magazynu(hd)`,
    `nazwy_druzyn` – {team_id Sofascore: nazwa} (`tozsamosc.nazwy_druzyn_sh`)."""

    def __init__(self, tozsamosc: T.Tozsamosc, baza: dict[int, dict], trend_lib: dict,
                 eventy: dict[int, dict], nazwy_druzyn: dict[int, str] | None = None):
        self.t = tozsamosc
        self.eventy = eventy
        self.nazwy = dict(nazwy_druzyn or {})
        self.licz: defaultdict[str, int] = defaultdict(int)
        # bank: klucze per zawodnik (wiersze budujemy dopiero na żądanie)
        self._bank = trend_lib or {}
        self._klucze_banku: dict[int, list[str]] = defaultdict(list)
        self._pelny_bank: set[int] = set()        # bank zna KAŻDY mecz zawodnika
        self.nazwy_zawodnikow: dict[int, str] = {}
        self._gracze_druzyny: dict[int, set[int]] = defaultdict(set)
        for k, rec in self._bank.items():
            try:
                pid = int(rec.get("player_id") or 0)
            except (TypeError, ValueError):
                continue
            self._klucze_banku[pid].append(k)
            if rec.get("historia_pelna"):
                self._pelny_bank.add(pid)
            self.nazwy_zawodnikow.setdefault(pid, rec.get("player_name") or "")
            if rec.get("team_id"):
                self._gracze_druzyny[int(rec["team_id"])].add(pid)
        # mecze magazynu po drużynie (szukanie numeru meczu banku)
        self._ev_druzyny: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for e, v in eventy.items():
            self._ev_druzyny[v["h"]].append((v["t"], e))
            self._ev_druzyny[v["a"]].append((v["t"], e))
        # baza FotMob: wiersze per zawodnik (numer Sofascore)
        self._fm: dict[int, list[tuple[int, dict, dict | None]]] = defaultdict(list)
        # mecze drużyny z bazy (tylko ZE SKŁADAMI – patrz `_dodaj_mecz_fm`)
        self._mecze_fm_druzyny: dict[int, list[dict]] = defaultdict(list)
        self._cache_bank: dict[int, list[tuple[int, dict, dict | None]]] = {}
        self._mecz: dict[int, dict] = {}                 # numer meczu → mecz bazy (bez zawodników)
        self._mecze_druz_fm: dict[int, list[int]] = defaultdict(list)   # drużyna → numery meczów bazy
        self._terminarz: dict[int, tuple[str, int]] = {}  # numer meczu → (status, start) z terminarza
        self._sedziowie: dict[int, dict] = {}            # numer sędziego → profil
        self._hd: dict = {}                              # magazyn drużyn (`ustaw_magazyn`)
        self._niedostepni: dict[int, list[dict]] = {}    # drużyna → z nadchodzącego meczu
        self._dni_fm: dict[str, list[dict] | None] = {}   # terminarze FotMob (raz na proces)
        self._fm_mecz_po_ev: dict[int, dict] = {}         # numer meczu → mecz z terminarza FotMob
        self._przed_meczem: dict[int, dict] = {}          # numer meczu → {sedzia, potwierdzony}
        self._sklady: dict[int, dict] = {}               # mecz → XI
        for zapis in (baza or {}).values():
            self._dodaj_mecz_fm(baza_meczow.rozpakuj(zapis))

    # --- baza FotMob -----------------------------------------------------------
    def _dodaj_mecz_fm(self, r: dict) -> None:
        if r.get("status") != "finished":
            return
        h, a = self.t.id_druzyny(r["home"]["id"]), self.t.id_druzyny(r["away"]["id"])
        eid = self.t.id_meczu(r["id"])
        ev = {"id": eid, "timeStartTimestamp": int(r["ts"]), "homeTeamId": h, "awayTeamId": a,
              "uniqueTournamentId": self.t.utid(r.get("liga_id") or 0, r.get("liga_grupa")) or 0,
              "status": "finished"}
        dom = {"name": self.nazwy.get(h) or r["home"]["name"]}
        gosc = {"name": self.nazwy.get(a) or r["away"]["name"]}
        # ⚑ mecz BEZ SKŁADÓW (część krajowych pucharów w FotMob) nie wchodzi
        # do meczów drużyny: kadra bez wierszy w tym meczu znaczyłaby „nikt
        # nie zagrał”, a logika „opuścił mecz drużyny” – że zawodnik nie grał
        f3 = defaultdict(float)
        for w in r.get("zawodnicy") or []:
            if w.get("staty") and w["staty"].get("passes_final_third"):
                f3[w["team_id"]] += float(w["staty"]["passes_final_third"])
        self._mecz[eid] = {**{k: v for k, v in r.items() if k != "zawodnicy"}, "h": h, "a": a, "ev": ev,
                           "dom": dom, "gosc": gosc, "f3": dict(f3), "ma_sklady": bool(r.get("zawodnicy"))}
        self._mecze_druz_fm[h].append(eid)
        self._mecze_druz_fm[a].append(eid)
        if r.get("sedzia") and r["sedzia"].get("id"):
            sid = T.zastepczy(int(r["sedzia"]["id"]))
            if int(r["ts"]) >= int((self._sedziowie.get(sid) or {}).get("ost") or 0):
                self._sedziowie[sid] = {**r["sedzia"], "ost": int(r["ts"])}
        if r.get("zawodnicy"):
            rec_ev = {"events": ev, "homeTeam": dom, "awayTeam": gosc}
            self._mecze_fm_druzyny[h].append(rec_ev)
            self._mecze_fm_druzyny[a].append(rec_ev)
        else:
            self.licz["mecz_bez_skladow"] += 1
        for w in r.get("zawodnicy") or []:
            if not self.t.wiersz_zgodny(w["pid"], w["name"]):
                self.licz["kolizja_numeru"] += 1     # inna osoba pod tym numerem FotMob
                continue
            pid = self.t.id_zawodnika(w["pid"])
            self._gracze_druzyny[self.t.id_druzyny(w["team_id"])].add(pid)
            self.nazwy_zawodnikow.setdefault(pid, w["name"])
            ps = {"eventId": eid, "teamId": self.t.id_druzyny(w["team_id"]),
                  "minutesPlayed": float(w["minuty"]), "position": w.get("poz") or ""}
            s = w.get("staty")
            extra = None
            if s is not None:
                for kod, pole in POLA_SH.items():
                    if s.get(kod) is not None:
                        ps[pole] = float(s[kod])
                if s.get("yellow_card"):
                    ps["yellowCard"] = float(s["yellow_card"])
                if r.get("mapa_strzalow"):
                    extra = {pole: float(s.get(kod) or 0) for kod, pole in POLA_EXTRA.items()}
            # statshub: zawodnik zmieniony ma w `substitutedIn` numer zmiennika,
            # zmiennik w `substitutedOut` numer zmienionego; brak pary w zapisie
            # sprzed 31.10 = -1 (wiemy, że była zmiana, nie wiemy z kim)
            if w.get("zszedl") is not None:
                ps["substitutedIn"] = self.t.id_zawodnika(w["zmiana_przez"]) if w.get("zmiana_przez") else -1
            if w.get("wszedl") is not None:
                ps["substitutedOut"] = self.t.id_zawodnika(w["zmiana_za"]) if w.get("zmiana_za") else -1
            self._fm[pid].append((int(r["ts"]), {"player_statistics_event": ps, "events": ev,
                                                 "homeTeam": dom, "awayTeam": gosc}, extra))

    # --- bank (do 29.10) -------------------------------------------------------
    def _numer_meczu_banku(self, druzyna: int, rywal: int, ts: int) -> tuple[int, int, int, int, int | None]:
        """(event id, drużyna zawodnika W TAMTYM meczu, gospodarz, gość, utid)
        z magazynu. Bank trzyma OBECNĄ drużynę zawodnika, więc mecz z poprzednim
        klubem szukamy też po rywalu. Bez trafienia – numer z czasu i pary,
        drużyna zawodnika jako gospodarz (strony nie znamy)."""
        def o_porze(d):
            return [e for t, e in self._ev_druzyny.get(d, ()) if abs(t - ts) <= TOL_MECZU_S]
        for e in o_porze(druzyna):
            v = self.eventy[e]
            if not rywal or rywal in (v["h"], v["a"]):
                return e, druzyna, v["h"], v["a"], v.get("l")
        if rywal:
            for e in o_porze(rywal):
                v = self.eventy[e]
                swoja = v["a"] if v["h"] == rywal else v["h"]
                return e, swoja, v["h"], v["a"], v.get("l")
        return _ev_banku(ts, druzyna, rywal), druzyna, druzyna, rywal, None

    def _wiersze_banku(self, pid: int) -> list[tuple[int, dict, dict | None]]:
        if pid in self._cache_bank:
            return self._cache_bank[pid]
        gry: dict[int, dict] = {}
        druzyna, nazwa_dr = 0, ""
        for k in self._klucze_banku.get(pid, ()):
            rec = self._bank[k]
            rynek = rec.get("market_code") or k.split(":", 1)[-1]
            druzyna = druzyna or int(rec.get("team_id") or 0)
            nazwa_dr = nazwa_dr or rec.get("team_name") or ""
            ts_l = rec.get("timestamps") or []
            for i, ts in enumerate(ts_l):
                def el(pole, d=None):
                    lst = rec.get(pole) or []
                    return lst[i] if i < len(lst) else d
                g = gry.setdefault(int(ts), {"min": 0.0, "staty": {}, "extra": {}, "poz": "", "ryw": 0,
                                             "ryw_n": "", "utid": 0})
                g["min"] = max(g["min"], float(el("minutes", 0) or 0))
                g["poz"] = g["poz"] or (el("game_positions") or "")
                g["ryw"] = g["ryw"] or int(el("game_opponent_ids", 0) or 0)
                g["ryw_n"] = g["ryw_n"] or (el("game_opponents") or "")
                g["utid"] = g["utid"] or int(el("game_utids", 0) or 0)
                c = el("counts")
                if c is None:
                    continue
                if rynek in RYNEK_NA_POLE:
                    g["staty"][RYNEK_NA_POLE[rynek]] = float(c)
                elif rynek in POLA_EXTRA:
                    g["extra"][POLA_EXTRA[rynek]] = float(c)
        out = []
        for ts, g in gry.items():
            eid, swoja, h, a, utid = self._numer_meczu_banku(druzyna, g["ryw"], ts)
            ps = {"eventId": eid, "teamId": swoja, "minutesPlayed": g["min"], "position": g["poz"],
                  **{p: v for p, v in g["staty"].items() if p != "yellowCard" or v}}
            if pid not in self._pelny_bank:
                ps["_niepelny"] = True        # bank zna część meczów (feed propsów)
            ryw = a if h == swoja else h
            n_ryw = g["ryw_n"] or self.nazwy.get(ryw, "")
            n_dr = self.nazwy.get(swoja) or (nazwa_dr if swoja == druzyna else "")
            ev = {"id": eid, "timeStartTimestamp": ts, "homeTeamId": h, "awayTeamId": a,
                  "uniqueTournamentId": g["utid"] or utid or 0, "status": "finished"}
            dom, gosc = ({"name": n_dr}, {"name": n_ryw}) if h == swoja else ({"name": n_ryw}, {"name": n_dr})
            out.append((ts, {"player_statistics_event": ps, "events": ev, "homeTeam": dom, "awayTeam": gosc},
                        g["extra"] or None))
        self._cache_bank[pid] = out
        return out

    # --- odpowiedzi w kształcie statshub ---------------------------------------
    def _historia(self, pid: int) -> list[tuple[int, dict, dict | None]]:
        bank = self._wiersze_banku(int(pid))
        ts_banku = [ts for ts, _, _ in bank]
        nowe = [w for w in self._fm.get(int(pid), ())
                if not any(abs(w[0] - t) <= TOL_MECZU_S for t in ts_banku)]
        self.licz["mecze_z_banku"] += len(bank)
        self.licz["mecze_z_fotmob"] += len(nowe)
        return sorted(bank + nowe, key=lambda w: -w[0])

    def fetch_player_performance(self, player_id: int, limit: int = statshub.PERF_LIMIT) -> list[dict]:
        """Jak `statshub.fetch_player_performance`: wiersze od najnowszego."""
        return [w for _, w, _ in self._historia(player_id)[: int(limit)]]

    def extra_zawodnika(self, player_id: int, limit: int = statshub.PERF_LIMIT) -> dict[int, dict]:
        """{event id: rekord extra-stats} meczów z rozbiciem strzałów – do
        `trendy_z_performance(extra_meczu=...)`. Mecz bez mapy strzałów nie
        wchodzi (brak danych, nie zero)."""
        out = {}
        for _, w, x in self._historia(player_id)[: int(limit)]:
            if x is not None:
                out[int(w["events"]["id"])] = x
        return out

    # --- kadra drużyny (etap 4c) -------------------------------------------------
    def _mecze_druzyny(self, team_id: int, teraz: int) -> list[dict]:
        """Rozegrane mecze drużyny w kształcie `events[]` kadry statshub, od
        najnowszego: magazyn `hd_*` + baza FotMob (tylko mecze ze składami),
        ten sam mecz raz – z magazynu, bo pod jego numerem stoją wiersze banku."""
        tid = int(team_id)
        out = []
        for t, e in self._ev_druzyny.get(tid, ()):
            if t > teraz - TOL_MECZU_S:
                continue                       # mecz przyszły / trwający
            v = self.eventy[e]
            out.append({"events": {"id": e, "timeStartTimestamp": t, "homeTeamId": v["h"],
                                   "awayTeamId": v["a"], "uniqueTournamentId": v.get("l") or 0,
                                   "status": "finished"},
                        "homeTeam": {"name": self.nazwy.get(v["h"], "")},
                        "awayTeam": {"name": self.nazwy.get(v["a"], "")}})
        ts_mag = [r["events"]["timeStartTimestamp"] for r in out]
        for r in self._mecze_fm_druzyny.get(tid, ()):
            ts = r["events"]["timeStartTimestamp"]
            if not any(abs(ts - t) <= TOL_MECZU_S for t in ts_mag):
                out.append(r)
        out.sort(key=lambda r: -r["events"]["timeStartTimestamp"])
        return out

    def fetch_team_players_performance(self, team_id: int, limit: int = statshub.KADRA_LIMIT,
                                       teraz: int | None = None) -> dict:
        """Jak `statshub.fetch_team_players_performance`: {"events", "data",
        "unavailability"}; `stats` kluczowane numerem meczu jako TEKSTEM.
        Zawodnik bez żadnego wiersza w tych meczach nie wchodzi."""
        import time
        teraz = int(teraz or time.time())
        tid = int(team_id)
        mecze = self._mecze_druzyny(tid, teraz)[: int(limit)]
        # wiersz łączymy z meczem kadry po STARCIE (±3 h), nie po numerze: mecz
        # spoza magazynu ma w banku numer zastępczy, a w kadrze numer z bazy
        starty = [(int(r["events"]["timeStartTimestamp"]), int(r["events"]["id"])) for r in mecze]
        data = []
        for pid in sorted(self._gracze_druzyny.get(tid, ())):
            stats, poz = {}, ""
            for ts, w, _ in self._historia(pid):
                ps = w["player_statistics_event"]
                if int(ps.get("teamId") or 0) != tid:
                    continue
                eid = next((e for t, e in starty if abs(t - ts) <= TOL_MECZU_S), None)
                if eid is not None and str(eid) not in stats:
                    stats[str(eid)] = ps if ps.get("eventId") == eid else {**ps, "eventId": eid}
                    poz = poz or str(ps.get("position") or "")[:1]
            if stats:
                nazwa = self.nazwy_zawodnikow.get(pid, "")
                data.append({"id": pid, "slug": statshub._klucz_slug(nazwa), "name": nazwa,
                             "position": poz or None, "stats": stats})
        return {"events": mecze, "data": data, "unavailability": list(self._niedostepni.get(tid, ()))}

    def fetch_extra_stats(self, event_ids) -> dict[int, list[dict]]:
        """Jak `statshub.fetch_extra_stats`: {mecz: [rekord zawodnika]} tylko
        dla meczów z rozbiciem strzałów (mecz bez danych NIE wchodzi – nie
        wiemy, nie zero). Rekord łączy się w `trendy_kadry` po slugu nazwiska."""
        szukane = {int(x) for x in event_ids or ()}
        meczu: dict[int, tuple[int, set[int]]] = {}       # mecz → (start, drużyny)
        for e in szukane:
            v = self.eventy.get(e)
            if v:
                meczu[e] = (v["t"], {v["h"], v["a"]})
        for lst in self._mecze_fm_druzyny.values():
            for r in lst:
                e = int(r["events"]["id"])
                if e in szukane and e not in meczu:
                    meczu[e] = (r["events"]["timeStartTimestamp"],
                                {r["events"]["homeTeamId"], r["events"]["awayTeamId"]})
        out: dict[int, list[dict]] = {}
        for e, (start, druzyny) in meczu.items():
            rek = []
            for d in druzyny:
                for pid in self._gracze_druzyny.get(d, ()):
                    for ts, w, x in self._historia(pid):
                        if (x is not None and abs(ts - start) <= TOL_MECZU_S
                                and int(w["player_statistics_event"].get("teamId") or 0) == d):
                            nazwa = self.nazwy_zawodnikow.get(pid, "")
                            rek.append({"playerId": pid, "playerSlug": statshub._klucz_slug(nazwa),
                                        "playerName": nazwa, **x})
                            break
            if rek:
                out[e] = rek
        return out

    # --- nadchodzący mecz: niedostępni i składy (etap 4c) -----------------------
    def _zawodnicy_banku(self):
        if not hasattr(self, "_zaw_banku"):
            zaw = T.zawodnicy_z_trend_lib(self._bank)
            self._zaw_banku = (zaw, T.kadry(zaw), T.indeks_nazw(zaw))
        return self._zaw_banku

    def mecz_nadchodzacy(self, dane: dict) -> dict:
        """Surowe `matchDetails` meczu PRZED gwizdkiem → niedostępni i składy
        w numerach Sofascore; zapamiętane pod drużyną (kadra) i meczem (XI).

        Nowych zawodników ze składu mapujemy po nazwisku (`Tozsamosc.dodaj_mecz`
        bez zamykania – stały numer zastępczy dostaje dopiero ten, kto zagra)."""
        general, c = dane.get("general") or {}, dane.get("content") or {}
        lu = c.get("lineup") or {}
        druz = (dane.get("header") or {}).get("teams") or [{}, {}]
        fm_h, fm_a = int((druz[0] or {}).get("id") or 0), int((druz[1] or {}).get("id") or 0)
        fm_mid = int(general.get("matchId") or 0)
        eid = self.t.id_meczu(fm_mid)
        utid = self.t.utid(int(general.get("parentLeagueId") or general.get("leagueId") or 0),
                           int(general.get("leagueId") or 0))
        sklad_fm = []
        for strona, tid in (("homeTeam", fm_h), ("awayTeam", fm_a)):
            t = lu.get(strona) or {}
            for grupa in ("starters", "subs", "unavailable"):
                for p in t.get(grupa) or []:
                    if int(p.get("id") or 0):
                        sklad_fm.append({"pid": int(p["id"]), "name": str(p.get("name") or ""), "team_id": tid,
                                         "minuty": 0.0, "poz": None})
        if sklad_fm:
            zaw, kad, idx = self._zawodnicy_banku()
            for k, v in self.t.dodaj_mecz(
                    {"id": 0, "ts": 0, "home": {"id": fm_h}, "away": {"id": fm_a}, "zawodnicy": sklad_fm},
                    zaw, kad, idx).items():
                self.licz[f"sklad_{k}"] += v
        typ = str(lu.get("lineupType") or "")
        potwierdzony = typ in TYPY_SKLADU_POTWIERDZONEGO
        przewidywany = typ in TYPY_SKLADU_PRZEWIDYWANEGO
        xi, niedostepni = {}, {}
        for strona, tid in (("homeTeam", fm_h), ("awayTeam", fm_a)):
            t = lu.get(strona) or {}
            sh_t = self.t.id_druzyny(tid)
            xi[sh_t] = [self.t.id_zawodnika(p["id"]) for p in t.get("starters") or [] if int(p.get("id") or 0)]
            niedostepni[sh_t] = [w for w in (niedostepny_statshub(u, self.t, utid) for u in t.get("unavailable") or [])
                                 if w]
            self._niedostepni[sh_t] = niedostepni[sh_t]
        h, a = self.t.id_druzyny(fm_h), self.t.id_druzyny(fm_a)
        sedzia = ((c.get("matchFacts") or {}).get("infoBox") or {}).get("Referee") or {}
        sid = None
        if sedzia.get("id"):
            from .fotmob import _staty_sedziego
            sid = T.zastepczy(int(sedzia["id"]))
            self._sedziowie[sid] = {"id": sedzia["id"], "nazwa": sedzia.get("text"), **_staty_sedziego(sedzia),
                                    "ost": (self._sedziowie.get(sid) or {}).get("ost")}
        self._przed_meczem[eid] = {"sedzia": sid, "potwierdzony": potwierdzony}
        self._sklady[eid] = {"home": xi.get(h, []), "away": xi.get(a, []), "confirmed": potwierdzony,
                             "przewidywany": przewidywany, "h": h, "a": a}
        return {"event_id": eid, "home_id": h, "away_id": a, "xi": xi, "potwierdzony": potwierdzony,
                "przewidywany": przewidywany, "niedostepni": niedostepni, "typ_skladu": typ}

    def fetch_predicted_lineup(self, event_id: int) -> dict:
        """Jak `statshub.fetch_predicted_lineup`: {"home", "away", "confirmed"}.
        Pusto, gdy FotMob nie ma ani przewidywanego, ani ogłoszonego składu."""
        s = self._sklady.get(int(event_id))
        if not s or not (s["confirmed"] or s["przewidywany"]):
            return {"home": [], "away": [], "confirmed": False}
        return {"home": list(s["home"]), "away": list(s["away"]), "confirmed": bool(s["confirmed"])}

    def fetch_team_lineup(self, event_id: int, team_id: int) -> list[int]:
        """Jak `statshub.fetch_team_lineup`: ogłoszony XI drużyny (≥ 10) albo []."""
        s = self._sklady.get(int(event_id))
        if not s or not s["confirmed"]:
            return []
        xi = s["home"] if int(team_id) == s["h"] else s["away"] if int(team_id) == s["a"] else []
        return list(xi) if len(xi) >= 10 else []


# `lineup.lineupType` FotMob (31.10, 634 mecze + próbki przed meczem): skład
# ogłoszony = standard / simple; przewidywany = predicted. `lastStarting11` to
# tylko ostatnia jedenastka – NIE przewidywanie, nie podajemy go jako XI
TYPY_SKLADU_POTWIERDZONEGO = frozenset({"standard", "simple"})
TYPY_SKLADU_PRZEWIDYWANEGO = frozenset({"predicted"})
# `unavailability.expectedReturn`, które znaczą „może zagrać” (statshub `dayToDay`);
# reszta (data powrotu, „About a week”, „Out for season”, „Unknown”) = pewny brak
POWROT_WATPLIWY = frozenset({"doubtful", "day to day", "back in training"})


def niedostepny_statshub(u: dict, tozsamosc: T.Tozsamosc, utid: int | None) -> dict | None:
    """Wpis `lineup.unavailable` FotMob → wpis `unavailability` statshub."""
    if not int(u.get("id") or 0):
        return None
    un = u.get("unavailability") or {}
    typ = str(un.get("type") or "")
    powrot = str(un.get("expectedReturn") or "")
    koniec = None
    if un.get("expectedReturnDate"):
        from datetime import datetime
        try:
            koniec = int(datetime.fromisoformat(str(un["expectedReturnDate"]).replace("Z", "+00:00")).timestamp())
        except ValueError:
            koniec = None
    if typ == "suspension":
        # FotMob podaje zawieszenie PRZY TYM meczu – obowiązuje w jego rozgrywkach
        status, kind = None, "suspension"
    else:
        status = "dayToDay" if powrot.lower() in POWROT_WATPLIWY else "out"
        kind = "injury" if typ == "injury" else (typ or "injury")
    return {"playerId": tozsamosc.id_zawodnika(int(u["id"])), "kind": kind, "status": status,
            "startDateTimestamp": None, "endDateTimestamp": koniec, "uniqueTournamentId": utid,
            "reason": powrot}


# ---------------------------------------------------------- drużyny (4d) ----
# kod magazynu `hd_*` → pole `statistics` statshub (`magazyn_druzyn.POLA`)
POLA_MAGAZYNU = {"cor": "cornerKicks", "sh": "totalShotsOnGoal", "sot": "shotsOnGoal", "crd": "cards",
                 "fol": "fouls", "pos": "ballPossession", "crs": "accurateCross", "f3": "finalThirdEntries",
                 "box": "touchesInOppBox", "ins": "totalShotsInsideBox", "out": "totalShotsOutsideBox",
                 "off": "offsides", "tck": "totalTackle", "int": "interceptionWon", "xg": "expectedGoals"}
# statystyka drużyny w bazie FotMob → pole statshub
POLA_DRUZYNY_FM = {"corners": "cornerKicks", "shots": "totalShotsOnGoal", "sot": "shotsOnGoal",
                   "fouls": "fouls", "possession": "ballPossession", "accurate_crosses": "accurateCross",
                   "touches_opp_box": "touchesInOppBox", "shots_inside_box": "totalShotsInsideBox",
                   "shots_outside_box": "totalShotsOutsideBox", "offsides": "offsides", "tackles": "totalTackle",
                   "interceptions": "interceptionWon", "xg": "expectedGoals", "yellow_cards": "yellowCards",
                   "red_cards": "redCards"}
# "Passes into final third" (suma zawodników) → `finalThirdEntries` statshub:
# korelacja 0,962, stosunek średnich 0,912 na 449 meczach (bramka etapu 2)
SKALA_F3 = 1 / 0.912
# sytuacja strzału FotMob → statshub/Sofascore (bank stylu czyta fast-break,
# corner, free-kick, set-piece, penalty)
SYTUACJE = {"RegularPlay": "regular", "IndividualPlay": "regular", "FastBreak": "fast-break",
            "FromCorner": "corner", "FreeKick": "free-kick", "SetPiece": "set-piece",
            "ThrowInSetPiece": "throw-in-set-piece", "Penalty": "penalty"}


def _staty_druzyny_fm(m: dict, fm_team: int) -> dict:
    a = ((m.get("druzyny") or {}).get(str(fm_team)) or {}).get("all") or {}
    out = {pole: a[kod] for kod, pole in POLA_DRUZYNY_FM.items() if a.get(kod) is not None}
    if "yellow_cards" in a or "red_cards" in a:
        out["cards"] = float(a.get("yellow_cards") or 0) + float(a.get("red_cards") or 0)
    if (m.get("f3") or {}).get(fm_team):
        out["finalThirdEntries"] = round(m["f3"][fm_team] * SKALA_F3)
    return out


def _wspolrzedne_sofascore(x: float, y: float, w_polu: bool) -> tuple[float, float]:
    """FotMob (metry, bramka rywala przy x = 105, szerokość 68) → skala
    Sofascore 0–100 (x = odległość od bramki rywala). Zgodność z flagą FotMob
    "z pola karnego" 99,6% (4710 strzałów); rozbieżne przyciągamy do flagi,
    bo `statshub._poza_polem` liczy z geometrii."""
    from .sofascore import is_outside_box
    sx, sy = round((105 - float(x)) / 105 * 100, 2), round(float(y) / 68 * 100, 2)
    if bool(is_outside_box(sx, sy)) == (not w_polu):
        return sx, sy
    if w_polu:
        return min(sx, 15.0), min(max(sy, 21.0), 79.0)
    return max(sx, 16.5), sy


def _rozszerz_zrodlo():
    """Metody drużyn i meczu (4d) dopinane do `Zrodlo` – część zawodników
    zostaje czytelna sama."""

    def ustaw_magazyn(self, hd: dict) -> None:
        """Magazyn drużyn `hd_*` (scalone szardy) – historia drużyn do 29.10."""
        self._hd = hd or {}

    def fetch_team_performance(self, team_id: int, limit: int = statshub.TEAM_PERF_LIMIT) -> list[dict]:
        """Jak `statshub.fetch_team_performance`: mecze od najnowszego, magazyn
        `hd_*` (do 29.10) + baza FotMob, ten sam mecz raz (z magazynu)."""
        tid = int(team_id)
        out = []
        for m in (self._hd.get(str(tid)) or self._hd.get(tid) or {}).get("m") or []:
            if not m.get("e") or not m.get("t"):
                continue
            dom = m.get("h") == 1
            h, a = (tid, int(m.get("o") or 0)) if dom else (int(m.get("o") or 0), tid)
            g, gp = m.get("g"), m.get("gp")
            out.append({
                "event": {"id": int(m["e"]), "timeStartTimestamp": int(m["t"]),
                          "score": ({"home": g if dom else gp, "away": gp if dom else g}
                                    if g is not None and gp is not None else {}),
                          "homeScoreOvertime": None, "homeScorePenalties": None},
                "statistics": {POLA_MAGAZYNU[k]: v for k, v in (m.get("s") or {}).items() if k in POLA_MAGAZYNU},
                "opponentStatistics": {POLA_MAGAZYNU[k]: v for k, v in (m.get("sp") or {}).items()
                                       if k in POLA_MAGAZYNU},
                "homeTeam": {"id": h, "name": self.nazwy.get(h, "")},
                "awayTeam": {"id": a, "name": self.nazwy.get(a, "")},
                "league": {"id": m.get("l"), "name": ""}})
        ts_mag = [int(r["event"]["timeStartTimestamp"]) for r in out]
        for eid in self._mecze_druz_fm.get(tid, ()):
            m = self._mecz[eid]
            if any(abs(int(m["ts"]) - t) <= TOL_MECZU_S for t in ts_mag):
                continue
            fm_my, fm_oni = ((m["home"]["id"], m["away"]["id"]) if m["h"] == tid
                             else (m["away"]["id"], m["home"]["id"]))
            g, g90 = m.get("gole") or [None, None], m.get("gole90") or [None, None]
            out.append({
                "event": {"id": eid, "timeStartTimestamp": int(m["ts"]),
                          "score": {"home": g90[0], "away": g90[1]},
                          # statshub: niepuste przy dogrywce / karnych (rozliczanie wtedy nie liczy)
                          "homeScoreOvertime": (g[0] - g90[0]) if m.get("dogrywka") else None,
                          "homeScorePenalties": 0 if m.get("karne") else None},
                "statistics": _staty_druzyny_fm(m, fm_my), "opponentStatistics": _staty_druzyny_fm(m, fm_oni),
                "homeTeam": {"id": m["h"], "name": m["dom"]["name"]},
                "awayTeam": {"id": m["a"], "name": m["gosc"]["name"]},
                "league": {"id": m["ev"]["uniqueTournamentId"], "name": m.get("liga") or ""}})
        out.sort(key=lambda r: -int(r["event"]["timeStartTimestamp"]))
        return out[: int(limit)]

    def fetch_event_result(self, event_id: int) -> dict | None:
        """Jak `statshub.fetch_event_result`: wynik po 90 min + flaga dogrywki."""
        m = self._mecz.get(int(event_id))
        if not m or m.get("status") != "finished" or not m.get("gole90"):
            return None
        return {"home_id": m["h"], "away_id": m["a"], "home_name": m["dom"]["name"],
                "away_name": m["gosc"]["name"], "home_goals": float(m["gole90"][0]),
                "away_goals": float(m["gole90"][1]), "extra_time": bool(m.get("dogrywka"))}

    def dodaj_terminarz(self, mecze_fm: list[dict]) -> None:
        """Statusy i starty z terminarza FotMob (`fotmob.mecze_dnia`) – mecze
        przełożone / odwołane i jeszcze nierozegrane."""
        for m in mecze_fm:
            self._terminarz[self.t.id_meczu(m["id"])] = (m.get("status") or "", int(m.get("start_ts") or 0))

    def status_i_start(self, event_id: int) -> tuple[str | None, int | None]:
        e = int(event_id)
        if e in self._terminarz:
            st, ts = self._terminarz[e]
            return st or None, ts or None
        m = self._mecz.get(e)
        return (m["status"], int(m["ts"])) if m else (None, None)

    def status_meczu(self, event_id: int) -> str | None:
        return self.status_i_start(event_id)[0]

    def fetch_event_shotmap(self, event_id: int) -> list[dict]:
        """Jak `statshub.fetch_event_shotmap` (pola czytane przez pipeline).
        Mecz bez zapisanej mapy (zapis sprzed 31.10, liga bez mapy) → []."""
        m = self._mecz.get(int(event_id))
        if not m:
            return []
        out = []
        for s in m.get("strzaly") or []:
            pid_fm, team_fm, x, y, syt, cialo, celny, zablok, w_polu, _okres, minuta, gol = s
            pid = self.t.id_zawodnika(pid_fm)
            sx, sy = _wspolrzedne_sofascore(x, y, bool(w_polu))
            out.append({"playerId": pid, "playerName": self.nazwy_zawodnikow.get(pid, ""),
                        "teamId": self.t.id_druzyny(team_fm), "x": sx, "y": sy, "isOnTarget": bool(celny),
                        "isHeaded": cialo == "Header", "bodyPart": "head" if cialo == "Header" else "foot",
                        "result": "goal" if gol else "save" if celny else "block" if zablok else "miss",
                        "situation": SYTUACJE.get(syt, "regular"), "minute": minuta})
        return out

    def fetch_referee(self, referee_id: int) -> dict | None:
        """Jak `statshub.fetch_referee`: {m, zk, ck (czerwone/mecz), k (karne/mecz), ost}.
        Numer sędziego = zastępczy z numeru FotMob (pamięć `sedziowie_sh`
        trzyma 3 dni, więc zmiana przestrzeni numerów sama się wymienia)."""
        r = self._sedziowie.get(int(referee_id))
        if not r or not r.get("m"):
            return None
        m = int(r["m"])
        return {"m": m, "zk": round(float(r.get("zk") or 0), 3), "ck": round(float(r.get("ck") or 0) / m, 3),
                "k": round(float(r.get("k") or 0) / m, 3), "ost": r.get("ost")}

    for f in (ustaw_magazyn, fetch_team_performance, fetch_event_result, dodaj_terminarz, status_i_start,
              status_meczu, fetch_event_shotmap, fetch_referee):
        setattr(Zrodlo, f.__name__, f)


_rozszerz_zrodlo()


# ------------------------------------------------- terminarz i metadane (4e) ----
STATUS_BY_DATE = {"notstarted": "notstarted", "inprogress": "inprogress", "finished": "finished",
                  "postponed": "postponed", "canceled": "canceled", "abandoned": "canceled"}


def _rozszerz_4e():

    def _fm_dzien(self, data: str) -> list[dict]:
        """Terminarz FotMob dnia `RRRRMMDD` – raz na proces (pamięć klienta)."""
        if data not in self._dni_fm:
            from . import fotmob
            try:
                self._dni_fm[data] = fotmob.mecze_dnia(data)
            except Exception as e:                       # noqa: BLE001
                self._dni_fm[data] = None
                self.licz["terminarz_blad"] += 1
                self._blad_terminarza = repr(e)[:200]
            if self._dni_fm[data]:
                self.dodaj_terminarz(self._dni_fm[data])
        return self._dni_fm[data] or []

    def by_date(self, start: int) -> dict:
        """Odpowiedź `event/by-date?startOfDay=start&endOfDay=start+86399`
        w kształcie statshub, z terminarza FotMob (numery z mapy tożsamości,
        zastępcze dla nowych). Doba UTC może zahaczać o dwa dni FotMob,
        więc bierzemy oba i filtrujemy po starcie."""
        from datetime import datetime, timedelta, timezone
        d = datetime.fromtimestamp(int(start), timezone.utc).date()
        mecze = {m["id"]: m for dzien in (d - timedelta(days=1), d)
                 for m in self._fm_dzien(dzien.strftime("%Y%m%d"))}
        if all(self._dni_fm.get(x.strftime("%Y%m%d")) is None for x in (d - timedelta(days=1), d)):
            raise RuntimeError(f"terminarz FotMob {d}: {getattr(self, '_blad_terminarza', 'brak odpowiedzi')}")
        out = []
        for m in mecze.values():
            if not (int(start) <= int(m["start_ts"]) <= int(start) + 86399):
                continue
            h, a = self.t.id_druzyny(m["home_id"]), self.t.id_druzyny(m["away_id"])
            utid = (self.t.utid(m.get("liga_id") or 0, m.get("liga_grupa"))
                    or T.zastepczy(m.get("liga_grupa") or m.get("liga_id") or 0))
            n_h, n_a = self.nazwy.get(h) or m["home"], self.nazwy.get(a) or m["away"]
            eid = self.t.id_meczu(m["id"])
            self._fm_mecz_po_ev[eid] = m
            prz = self._przed_meczem.get(eid) or {}
            ev = {"id": eid, "status": STATUS_BY_DATE.get(m.get("status"), "notstarted"),
                  "uniqueTournamentId": utid, "tournament": {"uniqueTournamentId": utid},
                  "timeStartTimestamp": int(m["start_ts"]), "homeTeamId": h, "awayTeamId": a,
                  "roundSlug": "", "roundInfo": None, "refereeId": prz.get("sedzia"),
                  "lineupConfirmed": bool(prz.get("potwierdzony")),
                  "slug": f"{statshub._klucz_slug(n_h)}-vs-{statshub._klucz_slug(n_a)}"}
            out.append({"events": ev, "homeTeam": {"id": h, "name": n_h}, "awayTeam": {"id": a, "name": n_a},
                        "unique_tournaments": {"id": utid, "name": m.get("liga") or ""},
                        "categories": {"name": m.get("kraj") or ""},
                        "tournaments": {"name": m.get("liga") or ""}, "hasOdd": True})
        return {"data": out}

    def search_players(self, nazwa: str) -> list[dict]:
        """Jak `statshub.search_players`: [{id, name, slug}] po zgodności nazwiska
        (bank + baza FotMob), najlepsze pierwsze, do 8."""
        oc = []
        for pid, n in self.nazwy_zawodnikow.items():
            p = T.podobienstwo_nazwisk(nazwa, n)
            if p >= T.PROG_NAZWISKA:
                oc.append((p, pid, n))
        oc.sort(key=lambda x: (-x[0], x[1]))
        return [{"id": pid, "name": n, "slug": statshub._klucz_slug(n)} for _, pid, n in oc[:8]]

    def fetch_player_profile(self, player_id: int) -> dict:
        """Jak `statshub.fetch_player_profile`; `team_id` = drużyna z ostatniego meczu."""
        pid = int(player_id)
        hist = self._historia(pid)
        if not hist and pid not in self.nazwy_zawodnikow:
            return {}
        team = int(hist[0][1]["player_statistics_event"].get("teamId") or 0) if hist else None
        poz = str(hist[0][1]["player_statistics_event"].get("position") or "")[:1] if hist else None
        return {"id": pid, "name": self.nazwy_zawodnikow.get(pid, ""), "position": poz or None,
                "height": None, "foot": None, "team_id": team or None, "country": None,
                "market_value": None, "birth_ts": None}

    def fetch_player_meta(self, player_id: int) -> dict:
        """Wzrost i noga – FotMob podaje je tylko w profilu zawodnika (osobne
        zapytanie); dla `matchup.is_target_man` brak = 0 (pytaliśmy, nie wiemy)."""
        return {"height": None, "foot": None}

    def fetch_tournament_name(self, utid: int) -> str:
        for m in self._mecz.values():
            if m["ev"]["uniqueTournamentId"] == int(utid):
                kraj = m.get("kraj") or ""
                return f"{m.get('liga') or ''} ({kraj})" if kraj and kraj not in (m.get("liga") or "") else (m.get("liga") or "")
        return ""

    for f in (_fm_dzien, by_date, search_players, fetch_player_profile, fetch_player_meta, fetch_tournament_name):
        setattr(Zrodlo, f.__name__, f)


_rozszerz_4e()


HORYZONT_PRZED_MECZEM_S = 48 * 3600
BUDZET_PRZED_MECZEM = 150      # zapytań o szczegóły nadchodzących meczów na przebieg


def _przed_meczami(self, events: list[dict], teraz: int | None = None,
                   horyzont_s: int = HORYZONT_PRZED_MECZEM_S, budzet: int = BUDZET_PRZED_MECZEM,
                   pierwsze: set[int] | None = None) -> dict:
    """Szczegóły meczów z najbliższych `horyzont_s` (składy, niedostępni,
    sędzia) – najpierw mecze z `pierwsze` (numery meczów: oferta zawodnicza
    Superbetu, rozgrywki drużynowe), w każdej grupie najbliższe najpierw, do
    `budzet` zapytań.

    ⚑ KOLEJNOŚĆ (cykl próbny 31.10): same „najbliższe” wydały 150 zapytań
    głównie na niższe ligi bez oferty zawodników – pewnych niedostępnych 112
    przy 713 w sobotnim cyklu statshub 24.10. Niedostępni idą do kadr
    (`fetch_team_players_performance`), a kadry liczą się tylko tam, gdzie
    jest oferta zawodnicza. Surowe eventy
    terminarza (`raw` silnika) dostają `lineupConfirmed` i `refereeId`, żeby
    silnik wiedział, po który skład sięgnąć. Odmowa FotMob = koniec pętli,
    cykl liczy dalej bez składów (jak przy statshub bez `predicted-lineup`)."""
    import time
    from . import fotmob
    teraz = int(teraz or time.time())
    licz = defaultdict(int)
    pierwsze = pierwsze or set()
    kolejka = sorted((e for e in events if 0 < int(e.get("timeStartTimestamp") or 0) - teraz <= horyzont_s),
                     key=lambda e: (int(e["id"]) not in pierwsze, int(e["timeStartTimestamp"])))
    for ev in kolejka:
        m = self._fm_mecz_po_ev.get(int(ev["id"]))
        if m is None:
            licz["bez_meczu_fotmob"] += 1
            continue
        if licz["pobrane"] >= budzet:
            licz["poza_budzetem"] += 1
            continue
        try:
            wyn = self.mecz_nadchodzacy(fotmob.szczegoly_meczu(m["id"]))
        except (fotmob.FotmobOdmowa, fotmob.FotmobLimit) as e:
            licz["odmowa"] += 1
            self._odmowa_przed_meczem = str(e)
            break
        except Exception:                                # noqa: BLE001
            licz["blad"] += 1
            continue
        licz["pobrane"] += 1
        if int(ev["id"]) in pierwsze:
            licz["pobrane_z_priorytetu"] += 1
        licz["sklad_potwierdzony" if wyn["potwierdzony"] else
             "sklad_przewidywany" if wyn["przewidywany"] else "bez_skladu"] += 1
        licz["niedostepni"] += sum(len(v) for v in wyn["niedostepni"].values())
        prz = self._przed_meczem.get(int(ev["id"])) or {}
        ev["lineupConfirmed"] = bool(prz.get("potwierdzony"))
        ev["refereeId"] = prz.get("sedzia")
    return dict(licz)


Zrodlo.przed_meczami = _przed_meczami


def zbuduj(miesiace: int = 4) -> Zrodlo:
    """Własny statshub ze stanu: mapa tożsamości, baza FotMob z `miesiace`
    ostatnich miesięcy, bank, magazyn drużyn, nazwy drużyn. Awaria odczytu
    któregokolwiek klucza = wyjątek (cykl na niepełnych danych liczyłby
    historie od zera – patrz build_league o dry-runie bez .env)."""
    import time
    from datetime import datetime, timezone
    from .. import supa

    def czytaj(k):
        d, ok = supa.get_key_ok(k)
        if not ok:
            raise RuntimeError(f"własny statshub: odczyt '{k}' padł")
        return d
    t, ok = T.wczytaj()
    if not ok or t is None or not t.druzyny:
        raise RuntimeError("własny statshub: mapa tożsamości pusta albo nieczytelna")
    teraz = datetime.now(timezone.utc)
    klucze = []
    r, m = teraz.year, teraz.month
    for _ in range(int(miesiace)):
        klucze.append(baza_meczow.KLUCZ_WZOR.format(f"{r}{m:02d}"))
        r, m = (r, m - 1) if m > 1 else (r - 1, 12)
    baza, braki = baza_meczow.wczytaj(klucze)
    if braki:
        raise RuntimeError(f"własny statshub: odczyt {braki} padł")
    hd = {}
    for i in range(10):
        hd.update(czytaj(f"hd_{i}") or {})
    bank = czytaj("trend_lib") or {}
    eventy = T.eventy_z_magazynu(hd)
    nazwy = T.nazwy_druzyn_sh(bank, czytaj("typy_log") or {}, czytaj("zakres_meczow") or [], eventy)
    t0 = time.time()
    z = Zrodlo(t, baza, bank, eventy, nazwy)
    z.ustaw_magazyn(hd)
    print(f"Własny statshub: baza {len(baza)} meczów, bank {len(bank)} serii, magazyn {len(hd)} drużyn, "
          f"mapa {len(t.druzyny)} drużyn / {sum(1 for v in t.zawodnicy.values() if v)} zawodników "
          f"({time.time() - t0:.0f} s)", flush=True)
    return z
