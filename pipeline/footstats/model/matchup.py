"""Silnik matchupów — "kto na kogo gra".

STATUS: AKTYWNE także w trybie MŚ (od 2026-07-14). Profile PlayerStyle/
OpponentStyle buduje model/styl.py z banku stylu (Supabase `styl_bank`):
statystyki drużynowe i styl zawodników z 365Scores (game/stats + lineups,
scores365.STAT_STYLE_MAP), sytuacje strzałów z shotmap statshub i wzrosty
z /api/player — patrz build_wc_fast.aktualizuj_bank_stylu. Gdy zawodnika/
drużyny nie ma w banku, engine spada na matchup_lite.py (strony boiska).
Skuteczność mierzona osobno flagą `matchup_styl` w diagnostyce kategorii
(rozliczanie.compute_diagnostyka) — analogie mają zarabiać, nie tylko
istnieć. W trybie ligowym profile jak dotąd buduje build_demo.py.

Styl KONKRETNEGO rywala i profil zawodnika tworzą przewidywalne efekty na
statystyki. To osobna warstwa mnożników, obok czynnika "ile rywal dopuszcza".

Architektura: predykcja dostaje dwa profile —
  * PlayerStyle  — kim jest zawodnik (drybler? target man? egzekutor? słaby 1v1?),
  * OpponentStyle — jak gra rywal (drybluje? dośrodkowuje? długie piłki? wysoka linia?
    głęboki blok? agresywny?).
Funkcja matchup_factor łączy je per rynek i zwraca mnożnik + opis po polsku.

Zasady: każdy efekt wynika z DANYCH (nie domysłu), jest kierunkowy, shrinkowany
do 1.0 przy małej próbie i capowany do [0.78, 1.32].

Wdrożone analogie (numeracja jak w docs/matchup-analogie.md):
  1  faworyt vs głęboki blok -> strzały +, celne -, zablokowane +
  2  egzekutor stałych/karnych -> strzały, celne +
  3  strzelec z dystansu vs głęboki blok -> zza pola +
  4  strzelec vs dużo blokująca drużyna -> zablokowane +
  9  target man vs słaby w powietrzu stoper -> głową +
  10 drużyna dużo dośrodkowująca x wzrostowy napastnik -> głową +
  11 dużo rożnych x wysocy -> głową +
  16 obrońca często ogrywany 1v1 vs drybler -> faule +
  17 rywal grający kontry -> faule taktyczne +
  18 defensywny pomocnik vs gra środkiem -> faule +
  20 holdup striker vs fizyczny stoper -> wywalczone +
  21 rozgrywający w zatłoczonym środku -> faulowany +
  25 boczny obrońca vs skrzydło po jego stronie -> odbiory +   (świadomość L/P: A)
  28 obrońca vs długie piłki rywala -> przechwyty +
  29 głęboki obrońca vs wysokie posiadanie rywala -> przechwyty +
  34 faulujący x surowy sędzia x derby -> kartka +   (sędzia w context)
  35 boczny obrońca vs gwiazda-skrzydło -> kartka +
  36 ostatni obrońca / wysoka linia vs szybki napastnik -> kartka +
  37 faule drużyny vs dryblerzy rywala -> team_fouls +
  38 wysoki pressing -> własne faule +
  39 dwie agresywne drużyny -> team_cards +
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .context import cap, shrink_factor

CAP_MATCHUP = (0.78, 1.32)

# --- średnie ligowe (top 5 lig, przybliżone; służą jako mianowniki) ---
LG_TEAM_CONTESTS = 18.0        # próby dryblingu / drużyna / mecz
LG_TEAM_DUELS = 44.0           # wygrane pojedynki / drużyna / mecz
LG_TEAM_FOULS = 11.0
LG_TEAM_CROSSES = 16.0
LG_TEAM_LONGBALLS = 55.0
LG_TEAM_POSSESSION = 50.0
LG_TEAM_CORNERS = 5.0
LG_OFFSIDES_FORCED = 2.2
LG_BLOCKS_MADE = 3.6           # bloki obronne / drużyna / mecz
LG_OUTSIDE_SHARE = 0.42        # udział strzałów rywala oddawanych spoza pola
LG_FASTBREAK_SHARE = 0.08      # udział strzałów z szybkich kontr
LG_TEAM_CARDS = 1.9

DEF_POS = {"D", "M"}
ATT_POS = {"F", "M"}
LR_LEFT = {"L", "DL", "ML", "LB", "LWB", "LW", "LM", "LST"}
LR_RIGHT = {"R", "DR", "MR", "RB", "RWB", "RW", "RM", "RST"}


@dataclass
class PlayerStyle:
    """Profil zawodnika liczony z jego historii (per-90 / udziały)."""

    position: str = "M"                 # litera G/D/M/F
    detailed_position: str = ""         # np. 'LB','RW' gdy znane
    is_dribbler: bool = False           # dużo prób 1v1
    is_target_man: bool = False         # wzrost + gra w powietrzu
    is_weak_1v1: bool = False           # często ogrywany (dużo challengeLost)
    is_holdup: bool = False             # dużo pojedynków/dotknięć w ataku
    is_playmaker: bool = False          # dużo kluczowych podań, środek pola
    takes_setpieces: bool = False       # oddaje strzały ze stałych
    height: int = 0

    @property
    def side(self) -> str | None:
        dp = (self.detailed_position or "").upper()
        for tok in (dp, dp[:2], dp[:1]):
            if tok in LR_LEFT:
                return "L"
            if tok in LR_RIGHT:
                return "R"
        return None


@dataclass
class OpponentStyle:
    """Profil stylu rywala (per mecz) + wielkość próby do shrinkage."""

    sample: int = 0
    contests_pm: float | None = None       # ile drybluje
    duels_pm: float | None = None          # fizyczność
    fouls_pm: float | None = None          # skłonność do fauli
    crosses_pm: float | None = None        # dośrodkowania
    long_balls_pm: float | None = None     # gra długimi piłkami
    possession: float | None = None
    corners_pm: float | None = None
    offsides_forced: float | None = None   # wysokość linii (pułapki)
    blocks_made_pm: float | None = None    # ile blokuje strzałów
    outside_share_conceded: float | None = None  # deep-block: udział strzałów z dystansu
    fastbreak_share: float | None = None   # jak kontratakuje
    cards_pm: float | None = None          # agresja
    weak_aerial: float | None = None       # słabość w powietrzu (przegrane górą / mecz)
    # świadomość strony: drybling/dośrodkowania z lewej i prawej flanki rywala
    left_threat_pm: float | None = None
    right_threat_pm: float | None = None


def _ratio(value: float | None, league: float, sample: int, prior: float = 10.0) -> float:
    """Znormalizowany, shrinkowany stosunek do średniej ligi (1.0 = neutralnie)."""
    if value is None or league <= 0:
        return 1.0
    return shrink_factor(value / league, sample, prior)


def deep_block_signal(opp: OpponentStyle) -> float:
    """1.0 = przeciętnie; >1 = rywal broni głębiej (mniej posiadania, więcej
    dopuszczonych strzałów z dystansu, więcej bloków)."""
    parts = []
    if opp.outside_share_conceded is not None:
        parts.append(opp.outside_share_conceded / LG_OUTSIDE_SHARE)
    if opp.blocks_made_pm is not None:
        parts.append(opp.blocks_made_pm / LG_BLOCKS_MADE)
    if opp.possession is not None:
        parts.append(LG_TEAM_POSSESSION / max(opp.possession, 25.0))  # mniej pos = głębiej
    if not parts:
        return 1.0
    raw = float(np.mean(parts))
    return shrink_factor(raw, opp.sample, 8.0)


def matchup_factor_druzyny(
    market_code: str,
    opp: OpponentStyle,
    is_favourite: bool = False,
) -> tuple[float, str | None]:
    """Matchup DRUŻYNOWY: styl rywala vs rynek całej drużyny.

    Zespołowa wersja matchup_factor — te same sygnały banku stylu (głęboki
    blok, pressing dryblingiem, kontry), bez warstwy pozycji zawodnika.
    Widełki ciaśniejsze niż u zawodników (0.85–1.20): na poziomie drużyny
    styl rozmywa się między jedenastu wykonawców. Gole celowo neutralne —
    głęboki blok daje więcej strzałów, ale mniej goli na strzał, kierunek
    netto jest niejednoznaczny i lepiej nie udawać, że go znamy.
    """
    f = 1.0
    opis: str | None = None
    deep = deep_block_signal(opp)
    press = _ratio(opp.contests_pm, LG_TEAM_CONTESTS, opp.sample)
    fb = _ratio(opp.fastbreak_share, LG_FASTBREAK_SHARE, opp.sample, prior=8.0)

    if market_code == "team_corners":
        # głęboki blok = bloki strzałów i zamknięte pole karne -> rożne rosną
        f *= 1.0 + 0.45 * (deep - 1.0)
        if deep > 1.03:
            opis = "Rywal broni głęboko i blokuje strzały, to generuje rożne"
        elif deep < 0.97:
            opis = "Rywal gra wysoko i trzyma piłkę, o rożne trudniej"
    elif market_code in ("team_shots", "team_sot"):
        if is_favourite and deep > 1.03:
            if market_code == "team_shots":
                f *= 1.0 + 0.4 * (deep - 1.0)
                opis = "Faworyt przeciw głębokiemu blokowi, dużo prób strzeleckich"
            else:
                f *= 1.0 - 0.2 * (deep - 1.0)
                opis = "Głęboki blok rywala, trudniej o czysty celny strzał"
    elif market_code in ("team_cards", "team_fouls"):
        raw = 1.0 + 0.35 * (press - 1.0) + 0.25 * (fb - 1.0)
        f *= raw
        if raw > 1.03:
            opis = "Rywal drybluje i kontratakuje, to wymusza faule"
        elif raw < 0.97:
            opis = "Rywal gra statycznie, mniej okazji do fauli"
    return float(np.clip(f, 0.85, 1.20)), opis


def matchup_factor(
    market_code: str,
    player: PlayerStyle,
    opp: OpponentStyle,
    is_favourite: bool = False,
) -> tuple[float, str | None]:
    """Zwraca (mnożnik, opis_pl). 1.0 = brak wpływu matchupu."""
    pos = (player.position or "M")[:1]
    f = 1.0
    opis = None

    press = _ratio(opp.contests_pm, LG_TEAM_CONTESTS, opp.sample)
    deep = deep_block_signal(opp)

    # ---------- STRZAŁY / CELNE ----------
    if market_code in ("shots", "sot"):
        # 1: faworyt vs głęboki blok -> więcej strzałów, ale mniej celnych
        if is_favourite and deep > 1.03:
            if market_code == "shots":
                f *= 1.0 + 0.5 * (deep - 1.0)
                opis = "Faworyt przeciw głębokiemu blokowi, dużo prób z dystansu"
            else:  # sot
                f *= 1.0 - 0.25 * (deep - 1.0)
                opis = "Głęboki blok rywala, trudniej o celny strzał"
        # 2: egzekutor stałych/karnych
        if player.takes_setpieces:
            f *= 1.10
            opis = "Egzekutor stałych fragmentów, dodatkowe strzały"

    # ---------- STRZAŁY ZZA POLA ----------
    if market_code == "shots_outside_box":
        # 3: strzelec z dystansu vs głęboki blok
        if deep > 1.03:
            f *= 1.0 + 0.6 * (deep - 1.0)
            opis = "Rywal broni nisko: brak miejsca w polu, strzały z dystansu"
        if player.takes_setpieces:
            f *= 1.08

    # ---------- STRZAŁY ZABLOKOWANE ----------
    if market_code == "shots_blocked":
        # 4: strzelec vs dużo blokująca drużyna
        blk = _ratio(opp.blocks_made_pm, LG_BLOCKS_MADE, opp.sample)
        f *= 1.0 + 0.5 * (blk - 1.0) + 0.3 * (deep - 1.0)
        if blk > 1.08 or deep > 1.08:
            opis = "Rywal ustawia dużo ciał w polu, więcej zablokowanych strzałów"

    # ---------- STRZAŁY GŁOWĄ ----------
    if market_code in ("headed_shots", "headed_sot"):
        boost = 1.0
        why = []
        # 9: target man vs słaby w powietrzu stoper
        if player.is_target_man:
            boost *= 1.10
            why.append("wysoki napastnik grający głową")
        if opp.weak_aerial is not None:
            wa = _ratio(opp.weak_aerial, 9.0, opp.sample)  # ~9 przegranych górą/mecz
            boost *= 1.0 + 0.4 * (wa - 1.0)
            if wa > 1.1:
                why.append("rywal słaby w powietrzu")
        # 10: drużyna dużo dośrodkowująca (własna) — przybliżamy przez rożne rywala? nie;
        #     dośrodkowania to cecha WŁASNEJ drużyny -> podawane osobno w opp.crosses_pm
        #     tutaj używamy corners jako sygnału stałych fragmentów (11)
        if opp.corners_pm is not None:
            cor = _ratio(opp.corners_pm, LG_TEAM_CORNERS, opp.sample)
            # więcej rożnych w meczu (proxy: rywal oddaje dużo rożnych) -> więcej okazji głową
            boost *= 1.0 + 0.15 * (cor - 1.0)
        f *= boost
        if why:
            opis = "Gra głową sprzyja: " + ", ".join(why)

    # ---------- FAULE POPEŁNIONE ----------
    if market_code == "fouls_committed" and pos in DEF_POS:
        f *= 1.0 + 0.5 * (press - 1.0)                    # 14 (drybler rywala)
        if opp.duels_pm is not None:                       # 15 (fizyczność)
            f *= 1.0 + 0.25 * (_ratio(opp.duels_pm, LG_TEAM_DUELS, opp.sample) - 1.0)
        if player.is_weak_1v1 and press > 1.0:             # 16 (ogrywany 1v1)
            f *= 1.12
            opis = "Obrońca często ogrywany 1v1 przeciw dryblerom, faule ratunkowe"
        if opp.fastbreak_share is not None:                # 17 (kontry)
            fb = _ratio(opp.fastbreak_share, LG_FASTBREAK_SHARE, opp.sample)
            f *= 1.0 + 0.2 * (fb - 1.0)
            if fb > 1.15 and not opis:
                opis = "Rywal groźny z kontr, więcej fauli taktycznych"
        if pos == "M" and player.is_playmaker is False and opp.possession is not None:  # 18
            centralplay = _ratio(opp.possession, LG_TEAM_POSSESSION, opp.sample)
            f *= 1.0 + 0.1 * (centralplay - 1.0)
        if not opis and press > 1.06:
            opis = "Rywal dużo dryblinguje, więcej fauli w pojedynkach"

    # ---------- FAULE WYWALCZONE ----------
    if market_code == "fouls_won":
        if player.is_dribbler:                             # 19
            f *= 1.08 + 0.5 * max(_ratio(opp.fouls_pm, LG_TEAM_FOULS, opp.sample) - 1.0, 0)
            opis = "Dużo dryblinguje, często faulowany"
        if player.is_holdup:                               # 20
            phys = _ratio(opp.duels_pm, LG_TEAM_DUELS, opp.sample)
            f *= 1.06 + 0.3 * (phys - 1.0)
            opis = "Gra ciałem przeciw fizycznemu rywalowi, wymusza faule"
        if player.is_playmaker:                            # 21
            f *= 1.07
            if not opis:
                opis = "Rozgrywający w środku: faulowany, by zatrzymać akcję"

    # ---------- ODBIORY ----------
    if market_code == "tackles" and pos in DEF_POS:
        f *= 1.0 + 0.7 * (press - 1.0)                     # 23
        if opp.duels_pm is not None:                       # 24
            f *= 1.0 + 0.25 * (_ratio(opp.duels_pm, LG_TEAM_DUELS, opp.sample) - 1.0)
        # 25 świadomość strony (A): jeśli znamy stronę zawodnika i zagrożenie flanką
        side = player.side
        side_threat = None
        if side == "L" and opp.right_threat_pm is not None:
            side_threat = opp.right_threat_pm   # lewy obrońca ↔ prawa flanka rywala
        elif side == "R" and opp.left_threat_pm is not None:
            side_threat = opp.left_threat_pm
        if side_threat is not None:
            st = _ratio(side_threat, LG_TEAM_CONTESTS / 2.0, opp.sample)
            f *= 1.0 + 0.4 * (st - 1.0)
            if st > 1.12:
                opis = "Broni flanki, którą rywal mocno atakuje – dużo pojedynków"
        if not opis and press > 1.06:
            opis = "Rywal dużo dryblinguje i wchodzi w pojedynki, więcej odbiorów"

    # ---------- PRZECHWYTY ----------
    if market_code == "interceptions" and pos in DEF_POS:
        f *= 1.0 + 0.3 * (press - 1.0)                     # 27
        if opp.long_balls_pm is not None:                  # 28
            lb = _ratio(opp.long_balls_pm, LG_TEAM_LONGBALLS, opp.sample)
            f *= 1.0 + 0.35 * (lb - 1.0)
            if lb > 1.12:
                opis = "Rywal gra długimi piłkami, więcej okazji do przechwytu"
        if opp.possession is not None:                     # 29
            pos_ratio = _ratio(opp.possession, LG_TEAM_POSSESSION, opp.sample)
            f *= 1.0 + 0.2 * (pos_ratio - 1.0)
            if not opis and pos_ratio > 1.1:
                opis = "Rywal dużo gra piłką, więcej podań do przechwycenia"

    # ---------- SPALONE ----------
    if market_code == "offsides" and pos in ATT_POS and opp.offsides_forced is not None:
        line = _ratio(opp.offsides_forced, LG_OFFSIDES_FORCED, opp.sample)
        f *= 1.0 + 0.6 * (line - 1.0)
        if player.detailed_position in ("ST", "CF", "LST", "RST") or player.is_target_man:
            f *= 1.05  # 31 poacher grający na ramieniu obrońcy
        if line > 1.1:
            opis = "Rywal gra wysoką linią i łapie na spalone"

    # ---------- ŻÓŁTA KARTKA ----------
    if market_code == "yellow_card" and pos in DEF_POS:
        if press > 1.0:                                    # 33
            f *= 1.0 + 0.35 * (press - 1.0)
            opis = "Broni przeciw dryblerom, większe ryzyko kartki"
        side = player.side                                 # 35 gwiazda-skrzydło po stronie
        side_threat = opp.right_threat_pm if side == "L" else (
            opp.left_threat_pm if side == "R" else None)
        if side_threat is not None:
            st = _ratio(side_threat, LG_TEAM_CONTESTS / 2.0, opp.sample)
            if st > 1.1:
                f *= 1.0 + 0.25 * (st - 1.0)
                opis = "Kryje groźnego skrzydłowego, cyniczne faule i kartka"
        if player.is_weak_1v1 and opp.fastbreak_share is not None:  # 36
            fb = _ratio(opp.fastbreak_share, LG_FASTBREAK_SHARE, opp.sample)
            if fb > 1.1:
                f *= 1.0 + 0.2 * (fb - 1.0)

    # ---------- RYNKI DRUŻYNOWE ----------
    if market_code == "team_fouls":
        f *= 1.0 + 0.4 * (press - 1.0)                     # 37 vs dryblerzy rywala
        if opp.fastbreak_share is not None:                # kontry rywala
            f *= 1.0 + 0.15 * (_ratio(opp.fastbreak_share, LG_FASTBREAK_SHARE, opp.sample) - 1.0)
        if press > 1.06:
            opis = "Rywal ma dryblerów wymuszających faule"
    if market_code == "team_cards":
        # 39 dwie agresywne drużyny — sygnał: rywal dużo kartkowany
        if opp.cards_pm is not None:
            f *= 1.0 + 0.3 * (_ratio(opp.cards_pm, LG_TEAM_CARDS, opp.sample) - 1.0)
            if opp.cards_pm > LG_TEAM_CARDS * 1.15:
                opis = "Obie drużyny grają ostro, więcej kartek"

    return cap(f, CAP_MATCHUP), opis


# ---------- klasyfikatory profilu zawodnika (per-90 / udziały) ----------

def is_dribbler(contests_per90: float) -> bool:
    return contests_per90 >= 2.5


def is_target_man(height: int, aerial_won_per90: float) -> bool:
    return height >= 186 and aerial_won_per90 >= 1.5


def is_weak_1v1(dribbled_past_per90: float) -> bool:
    return dribbled_past_per90 >= 1.3


def is_holdup(duels_per90: float, touches_att_share: float = 0.0) -> bool:
    return duels_per90 >= 8.0


def is_playmaker(key_passes_per90: float, position: str) -> bool:
    return key_passes_per90 >= 1.5 and position in ("M", "F")


def takes_setpieces(setpiece_shots_per90: float) -> bool:
    return setpiece_shots_per90 >= 0.4
