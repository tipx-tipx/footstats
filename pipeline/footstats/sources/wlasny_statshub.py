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
        for zapis in (baza or {}).values():
            self._dodaj_mecz_fm(baza_meczow.rozpakuj(zapis))

    # --- baza FotMob -----------------------------------------------------------
    def _dodaj_mecz_fm(self, r: dict) -> None:
        if r.get("status") != "finished":
            return
        h, a = self.t.id_druzyny(r["home"]["id"]), self.t.id_druzyny(r["away"]["id"])
        eid = self.t.id_meczu(r["id"])
        ev = {"id": eid, "timeStartTimestamp": int(r["ts"]), "homeTeamId": h, "awayTeamId": a,
              "uniqueTournamentId": self.t.utid(r.get("liga_id") or 0) or 0, "status": "finished"}
        dom = {"name": self.nazwy.get(h) or r["home"]["name"]}
        gosc = {"name": self.nazwy.get(a) or r["away"]["name"]}
        # ⚑ mecz BEZ SKŁADÓW (część krajowych pucharów w FotMob) nie wchodzi
        # do meczów drużyny: kadra bez wierszy w tym meczu znaczyłaby „nikt
        # nie zagrał”, a logika „opuścił mecz drużyny” – że zawodnik nie grał
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
        return {"events": mecze, "data": data, "unavailability": []}

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
