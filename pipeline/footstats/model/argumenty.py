"""Argumenty typu „jak u typera" — za i przeciw, liczone ze stanu sprzed meczu.

⚑ SKĄD TO SIĘ WZIĘŁO (2026-10-18, właściciel po wzorcach typera: „do każdego
rodzaju typów zależności dopracować, jak trener piłkarski"). Typer nie liczy
jednej liczby — zbiera ARGUMENTY: rywal skrajny w lidze w tej statystyce,
mecze z tym samym rywalem, forma, rola zawodnika. Pomiar na 29,7 tys.
rozliczonych typów (księga 14.09–17.10, cechy odtworzone sprzed meczu,
efekt przy tym samym kursie, obie połowy okresu):

  zawodnicy  rywal w top 5% ligi w oddawaniu statystyki   62,5%  +6,9 pp
             mecze z rywalem (2+), wszystkie weszły        70,5%  +9,8 pp
             forma 0/5 −5,1 · rzadko w składzie −3,3
  drużyny    rywal w top 5% ligi +4,1 · dolne 20% −2,5
             mecze z rywalem: wszystkie weszły +2,7 · żaden −3,2
             wyraźnie słabsza drużyna + „poniżej" +6,3

Jeden wspólny wzór (regresja wszystkich cech) ROZMYWAŁ te efekty — działa
dopiero liczenie argumentów, dokładnie jak u typera. Lista dnia z limitami:
drużyny wyższe kursy 53,4% → 61,5%, drużyny wysoka szansa 78,0% → 80,0%,
drabinki 1,60–2,60 50,7% → 55,0%; zawodnicy wysoka szansa bez poprawy
(dzisiejszy wybór jest tam już dobry, więc ich nie ruszamy).

Progi poniżej są TE SAME, które mierzono — zmiana progu = nowy pomiar.
Skrypty pomiaru: scratchpad sesji 18.10 (zaleznosci.py, argumenty.py).

Konwencja kierunku: ranking rywala liczymy jako „ile ODDAJE" w lidze
(1 = najwięcej). Dla typu „poniżej" odwracamy, bo wtedy sprzyja rywal, który
oddaje mało.
"""
from __future__ import annotations

import bisect
from collections import Counter

# rynek drużynowy -> (pole naszej statystyki, pole tego, co oddaje rywal)
# w rekordzie magazynu (magazyn_druzyn.rekord_meczu: "s" my, "sp" rywal,
# "g"/"gp" gole)
POLE_DRUZYNY = {
    "team_shots": (("s", "sh"), ("sp", "sh")),
    "team_sot": (("s", "sot"), ("sp", "sot")),
    "team_corners": (("s", "cor"), ("sp", "cor")),
    "team_fouls": (("s", "fol"), ("sp", "fol")),
    "team_cards": (("s", "crd"), ("sp", "crd")),
    "team_goals": (("g", None), ("gp", None)),
}
# rynek zawodnika -> co w meczach RYWALA mówi, ile on „oddaje" tej statystyki
# (faule wywalczone: ile rywal sam fauluje; faule popełnione: ile fauli
# popełnia się przeciw rywalowi)
POLE_RYWALA_ZAWODNIKA = {
    "shots": ("sp", "sh"),
    "sot": ("sp", "sot"),
    "fouls_won": ("s", "fol"),
    "fouls_committed": ("sp", "fol"),
    "offsides": ("sp", "off"),
    "shots_outside_box": ("sp", "out"),
}

OKNO_MECZOW = 10            # średnia „ile oddaje" z ostatnich 10 meczów
MIN_MECZOW_RANKINGU = 5     # drużyna w rankingu ligi dopiero z 5 meczami
MIN_DRUZYN_LIGI = 8         # ranking ligi z mniej niż 8 drużyn nic nie mówi
ODSTEP_PRZED_MECZEM_S = 3 * 3600

PROG_RYWAL_ZA = 0.90        # rywal w top 10% ligi (po stronie typu)
PROG_RYWAL_PRZECIW = 0.20   # rywal w dolnych 20%
PROG_DRUZYNA_TOP = 0.80     # drużyna w top 20% ligi w swojej statystyce
PROG_POKRYCIA = 0.80
PROG_NA_90 = 1.20           # średnia na 90 min ≥ 1,2 × (linia + 0,5)
MIN_MINUT_WYSTEPU = 15

OPISY = {
    "rywal_top": "rywal w czołówce ligi pod ten typ",
    "rywal_slaby": "rywal pod ten typ nie sprzyja",
    "h2h_wszystkie": "z tym rywalem weszło za każdym razem",
    "h2h_wiekszosc": "z tym rywalem zwykle wchodziło",
    "h2h_nie": "z tym rywalem nie wchodziło",
    "pokrycie": "weszło w 8 z 10 ostatnich",
    "forma": "forma 4–5 z 5 ostatnich",
    "forma_slaba": "słaba forma (0–1 z 5)",
    "na_90": "na 90 minut wyraźnie nad linią",
    "rzadko_sklad": "rzadko w pierwszym składzie",
    "druzyna_top": "drużyna w czołówce ligi w tej statystyce",
    # bilans bramek z ostatnich 10 meczów, nie siła klubu — PSG z Barceloną
    # potrafi tu wyjść „słabszy" (podgląd 18.10), więc opis mówi, co liczymy
    "slabsza_ponizej": "rywal z wyraźnie lepszym bilansem bramek",
}


def _wart(m: dict, pole) -> float | None:
    a, b = pole
    v = m.get(a) if b is None else (m.get(a) or {}).get(b)
    return float(v) if isinstance(v, (int, float)) else None


class Indeks:
    """Magazyn historii drużyn przygotowany do pytań „przed meczem".

    `mag` w formacie magazyn_druzyn.wczytaj: {team_id: {"m": [rekordy]}}.
    """

    def __init__(self, mag: dict | None):
        self.mecze: dict[int, list[dict]] = {}
        for tid, rec in (mag or {}).items():
            try:
                t = int(tid)
            except (TypeError, ValueError):
                continue          # „_braki" i inne pola techniczne
            ms = [m for m in ((rec or {}).get("m") or []) if m.get("t")]
            if ms:
                self.mecze[t] = sorted(ms, key=lambda m: m["t"])
        self._ts = {t: [m["t"] for m in ms] for t, ms in self.mecze.items()}
        self.liga_druzyn: dict[int, set[int]] = {}
        for t, ms in self.mecze.items():
            for m in ms:
                if m.get("l"):
                    self.liga_druzyn.setdefault(int(m["l"]), set()).add(t)
        self._ranking: dict[tuple, dict[int, float]] = {}

    def przed(self, tid: int, ko: int, n: int = OKNO_MECZOW) -> list[dict]:
        """Ostatnie `n` meczów drużyny przed meczem, najnowszy pierwszy."""
        ms = self.mecze.get(int(tid)) or []
        i = bisect.bisect_left(self._ts.get(int(tid), []), ko - ODSTEP_PRZED_MECZEM_S)
        return ms[max(0, i - n):i][::-1]

    def srednia(self, tid: int, ko: int, pole) -> tuple[float | None, int]:
        v = [x for x in (_wart(m, pole) for m in self.przed(tid, ko)) if x is not None]
        return (sum(v) / len(v), len(v)) if v else (None, 0)

    def liga(self, tid: int, ko: int) -> int | None:
        """Liga domowa drużyny — najczęstsza w ostatnich meczach (puchar to
        nie liga: ranking „najwięcej oddaje w lidze" liczymy w lidze)."""
        c = Counter(m.get("l") for m in self.przed(tid, ko) if m.get("l"))
        return int(c.most_common(1)[0][0]) if c else None

    def ranga(self, tid: int, ko: int, pole) -> float | None:
        """Miejsce drużyny w swojej lidze wg średniej `pole` (0 = najmniej,
        1 = najwięcej). None, gdy liga za mała albo drużyna bez próby."""
        liga = self.liga(tid, ko)
        if liga is None:
            return None
        dzien = int(ko // 86400)
        klucz = (liga, dzien, pole)
        if klucz not in self._ranking:
            d = {}
            for t in self.liga_druzyn.get(liga, ()):
                s, n = self.srednia(t, ko, pole)
                if n >= MIN_MECZOW_RANKINGU:
                    d[t] = s
            self._ranking[klucz] = d
        d = self._ranking[klucz]
        if int(tid) not in d or len(d) < MIN_DRUZYN_LIGI:
            return None
        v = d[int(tid)]
        return sum(1 for x in d.values() if x < v) / (len(d) - 1)

    def miejsce(self, tid: int, ko: int, pole, od_najwiekszej: bool = True
                ) -> tuple[int, int] | None:
        """(miejsce, liczba drużyn) w lidze — do opisu „2. na 18". Liczone
        z tego samego rankingu co `ranga` (wywołać po niej)."""
        if self.ranga(tid, ko, pole) is None:
            return None
        liga = self.liga(tid, ko)
        d = self._ranking[(liga, int(ko // 86400), pole)]
        v = d[int(tid)]
        lepszych = sum(1 for x in d.values() if (x > v if od_najwiekszej else x < v))
        return lepszych + 1, len(d)

    def sila(self, tid: int, ko: int) -> float | None:
        """Średnia różnica bramek z ostatnich meczów (≥5)."""
        v = [m["g"] - m["gp"] for m in self.przed(tid, ko)
             if isinstance(m.get("g"), (int, float)) and isinstance(m.get("gp"), (int, float))]
        return sum(v) / len(v) if len(v) >= 5 else None

    def h2h(self, tid: int, opp: int, ko: int) -> list[dict]:
        ms = self.mecze.get(int(tid)) or []
        return [m for m in ms if m.get("o") == int(opp) and m["t"] < ko - ODSTEP_PRZED_MECZEM_S]


def _bez_pustych(d: dict) -> dict:
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items() if v is not None}


def _po_stronie(v: float | None, strona: str) -> float | None:
    if v is None:
        return None
    return v if strona != "ponizej" else 1.0 - v


def _h2h_argument(trafienia: list[bool], za: list, przeciw: list) -> None:
    n = len(trafienia)
    if n >= 2 and all(trafienia):
        za.append("h2h_wszystkie")
    elif n >= 3 and sum(trafienia) / n >= 0.66:
        za.append("h2h_wiekszosc")
    if n >= 2 and not any(trafienia):
        przeciw.append("h2h_nie")


def argumenty_druzyny(idx: Indeks, tid: int, opp: int, ko: int, rynek: str,
                      linia: float, strona: str, pkw: float | None = None
                      ) -> dict[str, list[str]] | None:
    """Argumenty typu drużynowego (rynki team_*, strona powyżej/poniżej)."""
    pola = POLE_DRUZYNY.get(rynek)
    if not pola or strona not in ("powyzej", "ponizej") or not tid or not opp:
        return None
    nasze, rywala = pola
    za: list[str] = []
    przeciw: list[str] = []
    dane: dict = {}
    ro = _po_stronie(idx.ranga(opp, ko, rywala), strona)
    if ro is not None and ro >= PROG_RYWAL_ZA:
        za.append("rywal_top")
    if ro is not None and ro < PROG_RYWAL_PRZECIW:
        przeciw.append("rywal_slaby")
    if ro is not None:
        # „powyżej": miejsce od rywala, który oddaje najwięcej; „poniżej" — najmniej
        dane["rywal_miejsce"] = idx.miejsce(opp, ko, rywala, strona == "powyzej")
    traf = []
    for m in idx.h2h(tid, opp, ko)[-5:]:
        v = _wart(m, nasze)
        if v is not None:
            traf.append(v > linia if strona == "powyzej" else v < linia)
    _h2h_argument(traf, za, przeciw)
    if traf:
        dane["h2h"] = [sum(traf), len(traf)]
    if isinstance(pkw, (int, float)):
        pk = pkw if strona == "powyzej" else 1.0 - pkw
        if pk >= PROG_POKRYCIA:
            za.append("pokrycie")
        dane["pokrycie"] = round(pk, 2)
    rn = _po_stronie(idx.ranga(tid, ko, nasze), strona)
    if rn is not None and rn >= PROG_DRUZYNA_TOP:
        za.append("druzyna_top")
        dane["druzyna_miejsce"] = idx.miejsce(tid, ko, nasze, strona == "powyzej")
    s1, s2 = idx.sila(tid, ko), idx.sila(opp, ko)
    if s1 is not None and s2 is not None and s1 - s2 < -1 and strona == "ponizej":
        za.append("slabsza_ponizej")
    return {"za": za, "przeciw": przeciw, "dane": _bez_pustych(dane)}


def argumenty_zawodnika(idx: Indeks, opp: int, ko: int, rynek: str, linia: float,
                        counts, minutes, timestamps, opp_ids=None
                        ) -> dict[str, list[str]] | None:
    """Argumenty linii zawodnika „powyżej". Historia jak w StatshubTrend
    (najnowszy mecz pierwszy): `counts`, `minutes`, `timestamps`,
    `opp_ids` (game_opponent_ids)."""
    pole = POLE_RYWALA_ZAWODNIKA.get(rynek)
    if not pole or not counts:
        return None
    ids = list(opp_ids or []) + [0] * max(0, len(counts) - len(opp_ids or []))
    hist = [(float(c), float(mi or 0), o) for c, mi, o, ts
            in zip(counts, minutes, ids, timestamps or [])
            if ts and ts < ko - ODSTEP_PRZED_MECZEM_S]
    gr = [h for h in hist if h[1] >= MIN_MINUT_WYSTEPU]
    if len(gr) < 6:
        return None
    za: list[str] = []
    przeciw: list[str] = []
    dane: dict = {}
    if opp:
        ro = idx.ranga(opp, ko, pole)
        if ro is not None and ro >= PROG_RYWAL_ZA:
            za.append("rywal_top")
        if ro is not None and ro < PROG_RYWAL_PRZECIW:
            przeciw.append("rywal_slaby")
        if ro is not None:
            dane["rywal_miejsce"] = idx.miejsce(opp, ko, pole)
        h2h = [c > linia for c, mi, o in gr if o == opp][:5]
        _h2h_argument(h2h, za, przeciw)
        if h2h:
            dane["h2h"] = [sum(h2h), len(h2h)]
    f5 = sum(c > linia for c, _, _ in gr[:5])
    dane["forma"] = [f5, min(5, len(gr))]
    if f5 >= 4:
        za.append("forma")
    if f5 <= 1:
        przeciw.append("forma_slaba")
    p10 = sum(c > linia for c, _, _ in gr[:10])
    dane["pokrycie"] = [p10, min(10, len(gr))]
    if p10 / min(10, len(gr)) >= PROG_POKRYCIA:
        za.append("pokrycie")
    minuty = sum(mi for _, mi, _ in gr[:10])
    if minuty:
        na90 = 90 * sum(c for c, _, _ in gr[:10]) / minuty
        dane["na_90"] = round(na90, 2)
        if na90 / (linia + 0.5) >= PROG_NA_90:
            za.append("na_90")
    if sum(mi >= 60 for _, mi, _ in hist[:10]) / min(10, len(hist)) < 0.5:
        przeciw.append("rzadko_sklad")
    return {"za": za, "przeciw": przeciw, "dane": _bez_pustych(dane)}


def bilans(arg: dict | None) -> int:
    return len((arg or {}).get("za") or []) - len((arg or {}).get("przeciw") or [])


def czysty_pakiet(arg: dict | None, min_za: int = 2) -> bool:
    """Co najmniej `min_za` argumentów za i żadnego przeciw."""
    return bool(arg) and len(arg.get("za") or []) >= min_za and not arg.get("przeciw")
