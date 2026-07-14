"""Style drużyn i zawodników (tryb MŚ) — paliwo dla PEŁNEGO silnika matchupów.

model/matchup.py („pressing vs budowanie", „target man vs słabość w powietrzu",
~20 analogii) był nieaktywny w trybie MŚ z adnotacją „statshub nie dostarcza
danych stylu". Sonda 2026-07-14 pokazała, że to nieaktualne — wszystkie pola
OpponentStyle/PlayerStyle da się policzyć z DARMOWYCH, już zintegrowanych
źródeł:

  * 365Scores `game/stats`  — statystyki DRUŻYNOWE per mecz (posiadanie,
    dośrodkowania i długie piłki z PRÓBAMI, pojedynki górne/dolne, dryblingi,
    strzały zza pola, bloki, spalone) — scores365.game_team_stats,
  * 365Scores lineups        — statystyki STYLU zawodnika per mecz (dryblingi,
    dribbled past, pojedynki, kluczowe podania, dośrodkowania)
    — scores365.game_player_match_stats (STAT_STYLE_MAP),
  * statshub shotmap         — sytuacje strzałów: udział KONTR per drużyna,
    strzały ze STAŁYCH fragmentów per zawodnik,
  * statshub /player/{id}    — wzrost (matchup.is_target_man).

Ten moduł jest CZYSTĄ kalkulacją nad bankiem (dict z Supabase `styl_bank`);
całe IO (pobieranie, limity per cykl) mieszka w build_wc_fast.
aktualizuj_bank_stylu. Zasada jak w matchup.py: efekt z danych, shrink przy
małej próbie (matchup._ratio), cap. Mianowniki LG_* w matchup.py są z top-5
lig — na MŚ tempo bywa inne, ale przy próbie 3-6 meczów shrink i tak trzyma
mnożniki blisko 1.0; normy z samego turnieju to kandydat na później.

Struktura banku (klucz Supabase `styl_bank`):
  gry:       {gid365: {ts, druzyny: {norm_nazwa: staty drużynowe}}}
  zawodnicy: {pkey:   {druzyna: norm_nazwa, gry: {gid365: {ts, min, ...styl}}}}
  shotmap:   {event_sh: {ts, druzyny: {teamId: {shots, kontra}},
                         stale: {playerId: n_strzalow_ze_stalych}}}
  wzrost:    {player_id_sh: cm}
"""

from __future__ import annotations

from . import matchup

# ile ostatnich meczów turnieju buduje profil (MŚ: 3 grupowe + faza pucharowa)
MAX_GIER_STYLU = 8
# minimum meczów drużyny w banku, żeby profil w ogóle powstał — poniżej tego
# shrink w matchup._ratio i tak spycha wszystko do 1.0, a półpuste profile
# tylko udają wiedzę
MIN_GIER_DRUZYNY = 2
# minimum minut zawodnika w banku na sensowne per-90 stylu
MIN_MINUT_ZAWODNIKA = 90.0


def _srednia(rekordy: list[dict], klucz: str) -> float | None:
    v = [float(r[klucz]) for r in rekordy if r.get(klucz) is not None]
    return sum(v) / len(v) if v else None


class StyleTurnieju:
    """Profile stylu policzone raz na cykl z banku.

    strony_zawodnikow — {pkey: 'L'/'R'/'C'} z pozycji statshub per mecz
    (dominant_side); zasila left/right_threat_pm rywala.
    team_id_by_norm — {norm_nazwa: statshub team_id}; spina bank 365
    (klucz: nazwa) z shotmapami statshub (klucz: teamId).
    """

    def __init__(
        self,
        bank: dict,
        strony_zawodnikow: dict[str, str] | None = None,
        team_id_by_norm: dict[str, int] | None = None,
    ) -> None:
        self._gry: dict = bank.get("gry") or {}
        self._zawodnicy: dict = bank.get("zawodnicy") or {}
        self._shotmap: dict = bank.get("shotmap") or {}
        self._wzrost: dict = bank.get("wzrost") or {}
        self._strony = strony_zawodnikow or {}
        self._tid = team_id_by_norm or {}
        self._opp_cache: dict[str, matchup.OpponentStyle | None] = {}
        # stałe fragmenty per zawodnik: suma strzałów ze stałych w shotmapach
        self._stale: dict[str, float] = {}
        self._n_shotmap_gier: dict[str, int] = {}
        for ev in self._shotmap.values():
            for pid, n in (ev.get("stale") or {}).items():
                self._stale[str(pid)] = self._stale.get(str(pid), 0.0) + float(n)

    # ---------- profil DRUŻYNY (rywala) ----------

    def _gry_druzyny(self, team_norm: str) -> list[tuple[dict, dict]]:
        """[(staty_drużyny, staty_rywala_w_tym_meczu), ...] od najnowszych."""
        pary = []
        for rec in self._gry.values():
            druzyny = rec.get("druzyny") or {}
            if team_norm not in druzyny or len(druzyny) != 2:
                continue
            opp_norm = next(k for k in druzyny if k != team_norm)
            pary.append((int(rec.get("ts") or 0), druzyny[team_norm], druzyny[opp_norm]))
        pary.sort(key=lambda x: -x[0])
        return [(a, b) for _, a, b in pary[:MAX_GIER_STYLU]]

    def _fastbreak_share(self, team_norm: str) -> float | None:
        tid = self._tid.get(team_norm)
        if tid is None:
            return None
        shots = kontry = 0.0
        for ev in self._shotmap.values():
            d = (ev.get("druzyny") or {}).get(str(tid))
            if d:
                shots += float(d.get("shots") or 0)
                kontry += float(d.get("kontra") or 0)
        return kontry / shots if shots >= 10 else None

    def _threat_flanki(self, team_norm: str, n_gier: int) -> tuple[float | None, float | None]:
        """Zagrożenie flankami rywala: (dryblingi + dośrodkowania) per mecz,
        rozbite na stronę L/P zawodnika (pozycje statshub)."""
        suma = {"L": 0.0, "R": 0.0}
        licznik = {"L": 0, "R": 0}
        for pkey, rec in self._zawodnicy.items():
            if rec.get("druzyna") != team_norm:
                continue
            side = self._strony.get(pkey)
            if side not in ("L", "R"):
                continue
            for g in (rec.get("gry") or {}).values():
                suma[side] += float(g.get("dribbles_att") or 0) + float(
                    g.get("crosses_att") or 0
                )
                licznik[side] += 1
        if n_gier <= 0:
            return None, None
        left = suma["L"] / n_gier if licznik["L"] else None
        right = suma["R"] / n_gier if licznik["R"] else None
        return left, right

    def opponent(self, team_name: str) -> matchup.OpponentStyle | None:
        team_norm = _norm(team_name)
        if team_norm in self._opp_cache:
            return self._opp_cache[team_norm]
        gry = self._gry_druzyny(team_norm)
        if len(gry) < MIN_GIER_DRUZYNY:
            self._opp_cache[team_norm] = None
            return None
        wlasne = [a for a, _ in gry]
        rywali = [b for _, b in gry]
        # weak_aerial = przegrane pojedynki górne / mecz (wygrane rywala górą
        # bywają niepełne w banku — liczymy z własnej pary won/att)
        przegrane_gora = [
            r["aerial_att"] - r["aerial_won"]
            for r in wlasne
            if r.get("aerial_att") is not None and r.get("aerial_won") is not None
        ]
        # deep-block: udział strzałów rywali oddawanych zza pola (sumarycznie,
        # nie średnia udziałów — mecze z 3 strzałami nie ważą tyle co z 20)
        strzaly_ryw = sum(float(r.get("shots") or 0) for r in rywali)
        zza_pola_ryw = sum(float(r.get("shots_outside") or 0) for r in rywali)
        left, right = self._threat_flanki(team_norm, len(gry))
        st = matchup.OpponentStyle(
            sample=len(gry),
            contests_pm=_srednia(wlasne, "dribbles_att"),
            duels_pm=_srednia(wlasne, "duels_won"),
            fouls_pm=_srednia(wlasne, "fouls"),
            crosses_pm=_srednia(wlasne, "crosses_att"),
            long_balls_pm=_srednia(wlasne, "longballs_att"),
            possession=_srednia(wlasne, "possession"),
            corners_pm=_srednia(wlasne, "corners"),
            # wysokość linii: ilu rywali ta drużyna łapie na spalonym
            offsides_forced=_srednia(rywali, "offsides"),
            # bloki tej drużyny = zablokowane strzały jej rywali
            blocks_made_pm=_srednia(rywali, "shots_blocked"),
            outside_share_conceded=(
                zza_pola_ryw / strzaly_ryw if strzaly_ryw >= 10 else None
            ),
            fastbreak_share=self._fastbreak_share(team_norm),
            cards_pm=_srednia(wlasne, "kartki"),
            weak_aerial=(
                sum(przegrane_gora) / len(przegrane_gora) if przegrane_gora else None
            ),
            left_threat_pm=left,
            right_threat_pm=right,
        )
        self._opp_cache[team_norm] = st
        return st

    # ---------- profil ZAWODNIKA ----------

    def player(
        self,
        player_name: str,
        position: str,
        game_positions: list[str] | tuple[str, ...],
        player_id_sh: int = 0,
        team_games: int = 0,
    ) -> matchup.PlayerStyle | None:
        """PlayerStyle z per-90 banku + wzrost statshub + stałe z shotmap.

        Zwraca None, gdy zawodnika nie ma w banku stylu (matchup wtedy nie
        rusza — engine spada na matchup_lite). Profil częściowy (mało minut)
        wraca z samą pozycją/stroną — flagi domyślnie False są bezpieczne.
        """
        klucze = set(self._zawodnicy.keys())
        pkey = _resolve(klucze, player_name)
        detailed = _dominujaca_pozycja(game_positions)
        wzrost = int(self._wzrost.get(str(player_id_sh)) or 0)
        if pkey is None:
            return None
        gry = [
            g for g in (self._zawodnicy[pkey].get("gry") or {}).values()
            if float(g.get("min") or 0) > 0
        ]
        minuty = sum(float(g.get("min") or 0) for g in gry)
        st = matchup.PlayerStyle(
            position=(position or "M")[:1],
            detailed_position=detailed,
            height=wzrost,
        )
        if minuty < MIN_MINUT_ZAWODNIKA:
            return st

        def per90(klucz: str) -> float:
            return sum(float(g.get(klucz) or 0) for g in gry) / minuty * 90.0

        st.is_dribbler = matchup.is_dribbler(per90("dribbles_att"))
        st.is_weak_1v1 = matchup.is_weak_1v1(per90("dribbled_past"))
        st.is_target_man = matchup.is_target_man(wzrost, per90("aerial_won"))
        st.is_holdup = matchup.is_holdup(per90("ground_att") + per90("aerial_att"))
        st.is_playmaker = matchup.is_playmaker(per90("key_passes"), st.position)
        # stałe fragmenty: strzały ze stałych / mecz drużyny (przybliżenie
        # per-90 dla grających od deski do deski)
        stale = self._stale.get(str(player_id_sh), 0.0)
        n_gier = max(team_games, len(gry))
        st.takes_setpieces = matchup.takes_setpieces(
            stale / n_gier if n_gier else 0.0
        )
        return st


def _dominujaca_pozycja(game_positions) -> str:
    """Najczęstszy pełny zapis pozycji z ostatnich meczów (np. 'RW', 'LB')."""
    licznik: dict[str, int] = {}
    for p in game_positions or []:
        p = str(p or "").strip().upper()
        if p:
            licznik[p] = licznik.get(p, 0) + 1
    if not licznik:
        return ""
    return max(licznik, key=lambda k: licznik[k])


def _norm(name: str) -> str:
    from ..sources.rotowire import _norm as rn

    return rn(name)


def _resolve(all_keys: set[str], player_name: str) -> str | None:
    from ..sources.scores365 import resolve_player_key

    return resolve_player_key(all_keys, player_name)
