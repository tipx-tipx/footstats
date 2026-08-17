"""Źródło danych: 365Scores — mapy strzałów (alternatywa dla Sofascore).

Sofascore blokuje IP serwerowni, więc rynki wymagające danych per strzał
(głową, zza pola karnego, zablokowane, niecelne) nie działały w chmurze.
365Scores (webws.365scores.com) daje to samo i DZIAŁA z GitHub Actions
(potwierdzone). Każdy strzał w chartEvents ma:

  * bodyPart:  "Header" / "Left foot" / "Right Foot",
  * outcome.id: 0=Goal, 1=Missed (niecelny), 2=Saved (celny, obroniony),
                4=Blocked (zablokowany),
  * side: pozycja wzdłuż boiska w % (bramka=100; rzut karny ~88.5;
          linia pola karnego ~84 — strzał zza pola: side < 84),
  * xG / xGOT (bonus, nieużywane).

Przepływ: competitor_ids (z bieżących meczów) -> games/results per drużyna
-> game/?gameId= (members + chartEvents) -> agregacja per zawodnik per mecz.
Wyniki cache'owane w pamięci procesu (jeden cykl = jedno pobranie).
"""

from __future__ import annotations

import re
import time as _time

from curl_cffi import requests

from .. import diagnostyka
from .rotowire import _norm

BASE = "https://webws.365scores.com/web"
Q = "appTypeId=5&langId=1&timezoneName=Europe/Warsaw&userCountryId=1"

# linia pola karnego: 16.5 m z ~105 m boiska => ~84% (karny side~88.5 potwierdza skalę)
BOX_SIDE_THRESHOLD = 84.0

# competitionId Mistrzostw Świata 2026 (endpoint /search)
WC_COMPETITION_ID = 5930

# rynki liczone są w REGULARNYM czasie gry (90 min + doliczony): zdarzenia
# z bazową minutą > 90 ("104'", "120 + 5'") to dogrywka/karne — pomijamy
REGULARNY_CZAS_MIN = 90.0

_game_cache: dict[int, dict] = {}
# gameId -> mecz miał dogrywkę (gameTime > 90) — staty lineups obejmują wtedy
# całe 120 min i NIE nadają się do rozliczania rynków regularnego czasu
_et_cache: dict[int, bool] = {}


def _minuta(t) -> float | None:
    """Bazowa minuta zdarzenia: "90 + 2'" -> 90; "104'" -> 104; brak -> None."""
    s = str(t or "").replace("'", "").strip()
    if not s:
        return None
    try:
        return float(s.split("+")[0].strip())
    except ValueError:
        return None


# DOLICZONY CZAS TO NIE DOGRYWKA. Próg był `> 90,5` — a 365Scores podaje
# `gameTime` z doliczonym: Fluminense–Bahia (liga brazylijska, 30.07) miało
# 98,0 i przez to uchodziło za mecz po dogrywce. Skutek był drogi: rynki
# drużynowe takich meczów NIGDY się nie rozliczały (30.07: 89 typów wisiało
# po gwizdku), więc typ znikał ze strony po meczu i nie pojawiał się
# w Skuteczności — dokładnie to zgłosił user.
#
# Dogrywka to 2 × 15 minut PO 90, czyli realnie 120+; zawodnicy z doliczonym
# dobijają do ~100. Próg 110 minut rozdziela te dwa światy z zapasem, a
# słowa ze statusu łapią przypadki, w których 365 nie poda minut.
PROG_DOGRYWKI_MIN = 110.0
_SLOWA_DOGRYWKI = ("aet", "a.e.t", "after extra", "extra time",
                   "after penalties", "penalties", " et", "et ")

# ⚑ KARNE PO 90 MINUTACH TO NIE DOGRYWKA (2026-08-17). Ani `gameTime`, ani
# status tego NIE rozstrzygają: Leagues Cup bije karne OD RAZU po regulaminowym
# czasie, a 365Scores podaje wtedy `gameTime = 120,0` i „After Penalties"
# dokładnie tak samo jak puchary UEFA po prawdziwej dogrywce. Słowo
# „penalties" w `_SLOWA_DOGRYWKI` blokowało więc mecze rozegrane w 90 minutach.
#
# Zmierzone na 11 wiszących meczach: 5 z nich (78 typów, w tym 26 pokazanych
# klientowi) dogrywki NIE MIAŁO — potwierdzone niezależnie sumą połów
# w statystykach (1. połowa + 2. połowa = całość, czyli po 90. minucie nie
# doszło ani jedno zdarzenie).
#
# `game.stages` mówi to wprost i jest w każdej odpowiedzi (mecz ligowy ma
# 7 Halftime / 9 End of 90 Minutes / 1 Current):
#     karne po 90 min   ->  7 Halftime, 9 End of 90 Minutes, 11 Penalties
#     prawdziwa dogrywka->  7 Halftime, 9 End of 90 Minutes, 10 Extra Time, [11]
ETAP_DOGRYWKI_ID = 10


def _zapamietaj_et(game_id: int, game: dict) -> None:
    etapy = game.get("stages")
    if isinstance(etapy, list) and etapy:
        _et_cache[game_id] = any(
            e.get("id") == ETAP_DOGRYWKI_ID
            or "extra time" in str(e.get("name") or "").lower()
            for e in etapy
            if isinstance(e, dict)
        )
        return
    # ZAPAS — gdy 365 nie poda etapów. Zostaje stara, ostrożniejsza reguła:
    # przy braku wiedzy wolimy NIE rozliczyć (zwrot) niż rozliczyć rynek
    # 90-minutowy statystyką ze 120 minut, bo rozliczenie jest nieodwracalne.
    try:
        gt = float(game.get("gameTime") or 0)
    except (TypeError, ValueError):
        gt = 0.0
    status = f" {game.get('shortStatusText') or ''} {game.get('statusText') or ''} ".lower()
    _et_cache[game_id] = (
        gt > PROG_DOGRYWKI_MIN
        or any(s in status for s in _SLOWA_DOGRYWKI)
    )


def after_extra_time(game_id: int) -> bool:
    """Czy mecz miał dogrywkę (wg wcześniej pobranych danych meczu)."""
    if game_id not in _et_cache:
        try:
            game = _get(f"{BASE}/game/?{Q}&gameId={game_id}").get("game", {})
            _zapamietaj_et(game_id, game)
        except Exception:
            return False
    return _et_cache.get(game_id, False)


def _get(url: str, timeout: int = 25, retries: int = 2) -> dict:
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, impersonate="chrome124", timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            _time.sleep(2 * (attempt + 1))
    raise last


def competitor_ids(team_names: list[str]) -> dict[str, int]:
    """Mapa: znormalizowana nazwa drużyny -> competitorId.

    Szuka w bieżących meczach ORAZ w oknie najbliższych dni (drużyny grające
    za 2-3 dni nie występują w "current").
    """
    wanted = {_norm(n) for n in team_names}
    out: dict[str, int] = {}

    def _scan(games: list[dict]) -> None:
        for g in games:
            for side in ("homeCompetitor", "awayCompetitor"):
                c = g.get(side) or {}
                key = _norm(str(c.get("name", "")))
                if key in wanted and key not in out and c.get("id"):
                    out[key] = int(c["id"])

    wc_comp_id = None
    try:
        data = _get(f"{BASE}/games/current/?{Q}&sports=1")
        _scan(data.get("games", []))
        for g in data.get("games", []):
            if "World Cup" in str(g.get("competitionDisplayName", "")):
                wc_comp_id = g.get("competitionId")
                break
    except Exception:
        pass
    # terminarz i wyniki MŚ po znanym id rozgrywek — /games/current często
    # w ogóle nie zawiera meczów MŚ (ucina do ~100 bieżących wszystkich lig)
    if len(out) < len(wanted):
        for comp in {wc_comp_id, WC_COMPETITION_ID} - {None}:
            for endpoint in ("fixtures", "results"):
                try:
                    data = _get(f"{BASE}/games/{endpoint}/?{Q}&competitions={comp}")
                    _scan(data.get("games", []))
                except Exception:
                    pass
            if len(out) >= len(wanted):
                break
    return out


def competitor_ids_z_rozgrywek(comp_ids: list[int]) -> dict[str, int]:
    """Mapa znormalizowana nazwa -> competitorId z terminarza i wyników
    KONKRETNYCH rozgrywek.

    `competitor_ids` jest reliktem trybu MŚ: skanuje `/games/current` (ok. 100
    bieżących meczów całego świata) i rozgrywki mundialu, więc klubu, który nie
    gra akurat teraz, nie znajdzie. Beniaminka szukamy tam, gdzie na pewno
    jest — w terminarzu ligi, do której właśnie awansował (w wynikach może go
    jeszcze nie być, jeśli nie rozegrał pierwszej kolejki).
    """
    out: dict[str, int] = {}
    for comp in comp_ids:
        for endpoint in ("fixtures", "results"):
            try:
                data = _get(f"{BASE}/games/{endpoint}/?{Q}&competitions={comp}")
            except Exception as e:
                # całe ROZGRYWKI wypadają ze skanu bez śladu
                diagnostyka.cichy("365scores", "rozgrywki_skan", e)
                continue
            for g in data.get("games", []):
                for side in ("homeCompetitor", "awayCompetitor"):
                    c = g.get(side) or {}
                    nm = _norm(str(c.get("name") or ""))
                    if nm and c.get("id") and nm not in out:
                        out[nm] = int(c["id"])
    return out


# Skróty typu klubu — w nazwie są ozdobą, nie tożsamością. Lista celowo krótka:
# im więcej wyrzucimy, tym łatwiej o fałszywą zgodność (np. „cd leganes" i „ud
# leganes" po wycięciu obu skrótów to ta sama drużyna, a nie jest). Wszystko,
# co niesie znaczenie (atletico, real, sporting, dynamo, cska), ZOSTAJE.
_TOKENY_TYPU_KLUBU = frozenset({
    "fc", "fk", "fci", "afc", "cfr", "nk", "hnk", "gnk", "msk", "ofk",
    "sc", "rsc", "ssc", "ac", "sk", "bk", "if", "kf", "cf", "sv", "fs",
})


def _tokeny_druzyny(nazwa: str) -> frozenset[str]:
    """Słowa niosące TOŻSAMOŚĆ klubu: bez skrótów typu, roku i pojedynczych liter.

    Rok założenia w nazwie („KF Shkëndija 79", „FC Hradec Králové 1905") jest
    u jednego źródła, a u drugiego nie — dlatego liczby lecą. Pojedyncze litery
    lecą z tego samego powodu: „Caracas F.C." rozpada się na `f` i `c`.
    """
    surowe = re.split(r"[^0-9a-z]+", _norm(nazwa))
    return frozenset(
        t for t in surowe
        if len(t) > 1 and not t.isdigit() and t not in _TOKENY_TYPU_KLUBU
    )


def dopasuj_druzyne(mapa: dict[str, int], nazwa: str) -> int | None:
    """competitorId dla nazwy drużyny z innego źródła — albo None.

    POWÓD (zmierzone 2026-07-27): doganianie banku stylu prosiło o id dla 12
    drużyn i dostawało je dla JEDNEJ. Wszystkie pozostałe siedziały w mapie,
    tylko inaczej zapisane: „Caracas F.C." vs „Caracas FC", „Bodo/Glimt" vs
    „Bodo Glimt", „RSC Anderlecht" vs „Anderlecht", „KF Shkëndija" vs
    „KF Shkëndija 79", „FCI Levadia Tallinn" vs „Levadia Tallinn".

    DLACZEGO NIE PODOBIEŃSTWO TEKSTU. Wydaje się oczywiste i jest groźne.
    Dla „Deportivo Riestra" najbardziej podobne w mapie jest „Deportivo
    Recoleta" (0,80) — INNY KLUB. Dla „Riga FC" najbardziej podobne to
    „Rigas FS" (0,80) — też inny klub, drugi zespół z tej samej Rygi. Próg
    podobieństwa wpuściłby oba i zasilił bank historią cudzej drużyny: cicho,
    bez błędu i bez śladu w logu. Brak dopasowania widać, podmianę — nie.

    Dlatego ta sama reguła co przy zawodnikach (superbet.znajdz_zawodnika):
    porównujemy ZBIORY SŁÓW i przyjmujemy WYŁĄCZNIE dopasowanie jednoznaczne.
    Dwa stopnie, od ostrzejszego:

      1. identyczny zbiór słów (Riga FC -> riga, nie rigas fs),
      2. zawieranie się w którąkolwiek stronę (Deportivo Riestra -> riestra).

    Remis na którymkolwiek stopniu = brak dopasowania. Nie zgadujemy.
    """
    klucz = _norm(nazwa)
    if klucz in mapa:
        return mapa[klucz]
    tok = _tokeny_druzyny(nazwa)
    if not tok:
        return None
    # rozstrzygamy po ID, nie po kluczu: ta sama drużyna bywa w mapie pod
    # dwoma zapisami i dwa wpisy na jedno id to nadal jednoznaczność
    rowne: set[int] = set()
    zawarte: set[int] = set()
    for k, cid in mapa.items():
        kt = _tokeny_druzyny(k)
        if not kt:
            continue
        if kt == tok:
            rowne.add(int(cid))
        elif tok <= kt or kt <= tok:
            zawarte.add(int(cid))
    for kandydaci in (rowne, zawarte):
        if len(kandydaci) == 1:
            return next(iter(kandydaci))
    return None


def finished_games_by_competition(comp_id: int = WC_COMPETITION_ID) -> list[dict]:
    """Ostatnie zakończone mecze rozgrywek: [{id, ts, home, away, gole}, ...].

    /games/results per rozgrywki — pewniejsze do rozliczeń niż /games/current,
    który IGNORUJE parametry startDate/endDate i zwraca tylko ~100 bieżących
    meczów (wczorajszy mecz MŚ zwykle w ogóle się w nim nie pojawia).

    `gole` = {znormalizowana nazwa: gole} z TEJ SAMEJ odpowiedzi — competitor
    niesie `score` obok nazwy, więc bank stylu dostaje historię goli bez ani
    jednego dodatkowego zapytania (`game_scores` woła osobny endpoint i jest
    do rozliczania pojedynczego meczu, nie do zasilania banku). Brak wyniku
    365 sygnalizuje wartością −1, stąd ten sam filtr `>= 0` co tam.
    """
    from datetime import datetime

    data = _get(f"{BASE}/games/results/?{Q}&competitions={comp_id}")
    out = []
    for g in data.get("games", []):
        if g.get("statusGroup") != 4:
            continue
        try:
            ts = int(datetime.fromisoformat(str(g.get("startTime", ""))).timestamp())
        except Exception as e:
            # mecz bez czytelnej daty wypada z listy — jeśli to się mnoży,
            # źródło zmieniło format i tracimy całe kolejki
            diagnostyka.cichy("365scores", "data_meczu", e)
            continue
        gole: dict[str, float] = {}
        for side in ("homeCompetitor", "awayCompetitor"):
            c = g.get(side) or {}
            nm = _norm(str(c.get("name") or ""))
            sc = c.get("score")
            if nm and sc is not None and float(sc) >= 0:
                gole[nm] = float(sc)
        out.append({
            "id": int(g["id"]), "ts": ts,
            "home": _norm(str((g.get("homeCompetitor") or {}).get("name", ""))),
            "away": _norm(str((g.get("awayCompetitor") or {}).get("name", ""))),
            "gole": gole if len(gole) == 2 else {},
        })
    return out


def scheduled_games_by_competition(comp_id: int = WC_COMPETITION_ID) -> list[dict]:
    """Nadchodzące mecze rozgrywek: [{id, ts, home, away}, ...] (statusGroup 2)."""
    from datetime import datetime

    data = _get(f"{BASE}/games/fixtures/?{Q}&competitions={comp_id}")
    out = []
    for g in data.get("games", []):
        if g.get("statusGroup") != 2:
            continue
        try:
            ts = int(datetime.fromisoformat(str(g.get("startTime", ""))).timestamp())
        except Exception as e:
            # mecz bez czytelnej daty wypada z listy — jeśli to się mnoży,
            # źródło zmieniło format i tracimy całe kolejki
            diagnostyka.cichy("365scores", "data_meczu", e)
            continue
        out.append({
            "id": int(g["id"]), "ts": ts,
            "home": _norm(str((g.get("homeCompetitor") or {}).get("name", ""))),
            "away": _norm(str((g.get("awayCompetitor") or {}).get("name", ""))),
        })
    return out


_ref_cache: dict[int, str | None] = {}


def game_referee(game_id: int) -> str | None:
    """Sędzia główny meczu (officials[0]) — znany zwykle 1-2 dni przed meczem.

    365 dopisuje kraj w nawiasie ("Ismail Elfath (USA )") — ucinamy go.
    """
    if game_id in _ref_cache:
        return _ref_cache[game_id]
    import re as _re

    name = ""
    try:
        data = _get(f"{BASE}/game/?{Q}&gameId={game_id}")
        offs = (data.get("game") or {}).get("officials") or []
        if offs:
            name = _re.sub(r"\s*\(.*?\)\s*$", "", str(offs[0].get("name") or "")).strip()
    except Exception as e:
        # brak sędziego = brak mnożnika fauli i kartek dla całego meczu
        diagnostyka.cichy("365scores", "sedzia_meczu", e)
    _ref_cache[game_id] = name or None
    return _ref_cache[game_id]


def recent_finished_games_z_rozgrywkami(
    competitor_id: int, n: int = 6
) -> list[tuple[int, int, int]]:
    """Jak `recent_finished_games`, ale z ID ROZGRYWEK: [(gameId, ts, compId)].

    Rozgrywki są potrzebne, żeby odróżnić dwie zupełnie różne sytuacje, które
    ta sama ścieżka obsługuje (patrz build_wc_fast.dolej_historie_wlasna):

      * beniaminek — poprzedni sezon grał NIŻEJ, jego historia wymaga korekty
        poziomu przed użyciem,
      * drużyna z ligi świeżo dołożonej do zakresu — jej historia jest z tego
        samego poziomu, na którym gra teraz, i korekty NIE wymaga.

    Bez tego rozróżnienia dołożenie ośmiu lig naraz (2026-07-27) wrzuciłoby
    całą ich historię do worka „mecze z niższego poziomu" i skala poziomu
    liczyłaby stosunek Brazylii do Europy zamiast I ligi do Ekstraklasy.

    Ten endpoint (`/games/results?competitors=`) jako JEDYNY sięga w głąb
    sezonu: dla Remo oddał 36 meczów od 28.01, podczas gdy ten sam endpoint
    filtrowany po rozgrywkach zwraca wyłącznie ostatnią kolejkę.
    """
    data = _get(f"{BASE}/games/results/?{Q}&competitors={competitor_id}")
    rows = []
    for g in data.get("games", []):
        if g.get("statusGroup") != 4:
            continue
        st = str(g.get("startTime", ""))  # np. "2026-06-25T20:00:00+02:00"
        try:
            from datetime import datetime

            ts = int(datetime.fromisoformat(st).timestamp())
        except Exception as e:
            diagnostyka.cichy("365scores", "data_meczu", e)
            continue
        rows.append((int(g["id"]), ts, int(g.get("competitionId") or 0)))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:n]


def recent_finished_games(competitor_id: int, n: int = 6) -> list[tuple[int, int]]:
    """Ostatnie n zakończonych meczów drużyny: [(gameId, timestamp_unix), ...] od najnowszych."""
    return [(gid, ts) for gid, ts, _ in
            recent_finished_games_z_rozgrywkami(competitor_id, n)]


def classify_event(e: dict) -> dict[str, int] | None:
    """Zamień jedno zdarzenie chartEvents na liczniki rynków (None = pomiń)."""
    if e.get("type") not in (0, None):  # 0 = strzał
        return None
    out_id = (e.get("outcome") or {}).get("id")
    body = str(e.get("bodyPart") or "")
    side = e.get("side")
    headed = body == "Header"
    left = "left" in body.lower()
    right = "right" in body.lower()
    on_target = out_id in (0, 2)
    outside = side is not None and float(side) < BOX_SIDE_THRESHOLD
    return {
        "shots": 1,
        "sot": 1 if on_target else 0,
        "headed": 1 if headed else 0,
        "headed_sot": 1 if headed and on_target else 0,
        "outside": 1 if outside else 0,
        "sot_outside": 1 if outside and on_target else 0,
        "blocked": 1 if out_id == 4 else 0,
        "off_target": 1 if out_id == 1 else 0,
        "left_foot": 1 if left else 0,
        "left_foot_sot": 1 if left and on_target else 0,
        "right_foot": 1 if right else 0,
        "right_foot_sot": 1 if right and on_target else 0,
    }


# Słowa, które w nazwach klubów nic nie rozróżniają — bez ich odsiania
# „FC" albo „de" potrafi być jedynym wspólnym tokenem dwóch różnych klubów.
_SZUM_NAZWY_KLUBU = frozenset({
    "fc", "cf", "ac", "sc", "kf", "fk", "sk", "cd", "ca", "afc", "cfc",
    "club", "de", "del", "da", "do", "y", "e", "i", "the", "if", "ik",
    "sv", "vf", "vfb", "us", "as", "ss", "ssc", "cs", "rc", "sd",
    # ⚑ „DEPORTIVO" TO NIE TOŻSAMOŚĆ, TO „SPORTOWY" (dopięte 2026-08-17).
    # Docstring `resolve_team_key` od początku obiecuje, że „Deportivo Riestra"
    # nie zostanie rozliczone statystyką „Deportivo Recoleta" — a bez tego
    # wpisu obietnica nie miała pokrycia: wspólny token „deportivo" dawał
    # JEDNOZNACZNE maksimum, więc dopasowanie wychodziło i nie zostawiało
    # śladu. Rozliczenie jest nieodwracalne, więc to najgorsza możliwa klasa
    # cichego błędu ([[bledy-rozliczania]]). Klubów, których cała tożsamość
    # to samo „deportivo", nie ma.
    "deportivo", "dep", "depor",
})

# NAZWY, KTÓRYCH ŻADNA REGUŁA NIE POŁĄCZY — bo to po prostu inne słowa.
# „AGF" to skrót od Aarhus Gymnastikforening; wspólnego tokenu nie ma i nigdy
# nie będzie. Lista jest ostatnią deską ratunku i celowo krótka: każdy wpis
# to ręczna decyzja, że dwie nazwy oznaczają ten sam klub. Zmierzone koszty
# braku tej listy: 4 typy z „Lech Poznań – AGF" i 3 z „Lyngby – AGF"
# zamknięte jako „brak danych źródła", choć statystyki meczu były u źródła.
#
# ⚑ ROZSZERZONA 17.08 o cztery pary zmierzone na wiszących typach. Diagnoza
# 20 meczów z nierozliczonymi typami: 32 typy w 5 meczach ginęły WYŁĄCZNIE
# na nazwie, przy pełnych statystykach u źródła (mecz znaleziony, statystyki
# pobrane, dopasowanie drużyny puste):
#
#     FC København        u źródła „fc copenhagen"    9 typów (dwa mecze)
#     CD Guadalajara      u źródła „chivas"           8 typów
#     Olympique Lyonnais  u źródła „lyon"            11 typów
#     Pumas UNAM          u źródła „pumas"            — łapie już zbiór słów
#
# „Kopenhaga" to ten sam przypadek co AGF: København i Copenhagen nie mają
# wspólnego tokenu i mieć nie będą. „Chivas" to przydomek klubu.
_ALIASY_KLUBU: dict[str, frozenset[str]] = {
    "agf": frozenset({"aarhus"}),
    "aarhus": frozenset({"agf"}),
    "kobenhavn": frozenset({"copenhagen"}),
    "copenhagen": frozenset({"kobenhavn"}),
    "guadalajara": frozenset({"chivas"}),
    "chivas": frozenset({"guadalajara"}),
    "lyonnais": frozenset({"lyon"}),
    "lyon": frozenset({"lyonnais"}),
}


def _tokeny_tozsamosci(nazwa: str) -> frozenset[str]:
    """Słowa niosące tożsamość klubu — wspólna podstawa obu dopasowywaczy.

    `_tokeny_druzyny` dzieli po ZNAKACH NIEALFANUMERYCZNYCH, więc rozumie
    „Bodø/Glimt" jako dwa słowa; naiwne `.split()` widziało jedno („bodo/glimt")
    i nie miało jak trafić w „bodo glimt" u źródła. To gubiło komplet typów
    z każdego meczu tej drużyny (12 sztuk 31.07). Do tego odsiewamy szum nazw
    klubowych — obie listy, bo jedna zna „fc", a druga „de" i „club".
    """
    return frozenset(_tokeny_druzyny(nazwa) - _SZUM_NAZWY_KLUBU)


def _rdzen(token: str) -> str:
    """Token bez skandynawskiej końcówki liczby mnogiej/określonej.

    „Aalesunds FK" u nas, „Aalesund" u źródła — jedna litera różnicy kasowała
    11 typów. Ucinamy wyłącznie końcowe „s" i tylko w słowach dostatecznie
    długich, żeby nie skleić dwóch krótkich, różnych nazw.
    """
    return token[:-1] if len(token) > 5 and token.endswith("s") else token


def ta_sama_druzyna(a: str, b: str) -> bool:
    """Czy dwie nazwy z RÓŻNYCH źródeł oznaczają ten sam klub — ostro.

    `resolve_team_key` liczy NAJWIĘCEJ wspólnych słów i to jest bezpieczne
    tylko tam, gdzie kandydaci są dwaj: obie drużyny znanego już meczu. Do
    SZUKANIA meczu wśród setek to za mało — „Deportivo Riestra" i „Deportivo
    Recoleta" mają wspólne „deportivo", więc tamta reguła wskazałaby zupełnie
    inny klub, cicho i bez śladu ([[parowanie-nazw-druzyn]]).

    Tu obowiązuje reguła z `dopasuj_druzyne`: zbiory słów muszą być RÓWNE albo
    jeden musi zawierać się w drugim. Wtedy:

        lillestrom sk        == lillestrom          tak
        bodo/glimt           == bodo glimt          tak (ukośnik to separator)
        sandefjord fotball   >= sandefjord          tak
        aalesunds fk         ~= aalesund            tak (rdzeń)
        agf                  ~= aarhus              tak (alias)
        deportivo riestra    vs deportivo recoleta  NIE
        riga fc              vs rigas fs            NIE (rdzeń tnie od 6 liter)
        estudiantes la plata vs estudiantes rio cuarto  NIE
    """
    ta, tb = _tokeny_tozsamosci(a), _tokeny_tozsamosci(b)
    if not ta or not tb:
        return False
    for xa, xb in (
        (ta, tb),
        ({_rdzen(t) for t in ta}, {_rdzen(t) for t in tb}),
        (ta | {al for t in ta for al in _ALIASY_KLUBU.get(t, ())}, tb),
    ):
        if xa == xb or xa <= xb or xb <= xa:
            return True
    return False


def maja_wspolny_czlon(a: str, b: str) -> bool:
    """Czy nazwy mają choć jedno wspólne słowo tożsamości (albo jego rdzeń).

    ⚑ REGUŁA SŁABA — NIE WOLNO jej używać samodzielnie do szukania meczu.
    „Deportivo Riestra" i „Deportivo Recoleta" mają wspólne „deportivo", więc
    sama w sobie wskazałaby inny klub ([[parowanie-nazw-druzyn]]).

    Jedyne zastosowanie: POTWIERDZENIE drugiej strony meczu, którego pierwszą
    stronę dopasowała już ostra `ta_sama_druzyna` w oknie ±3 h — patrz
    `rozliczanie._gid_365`. Powód: „Red Bull Bragantino" u nas i „RB
    Bragantino" u źródła nie mają równych ani zawierających się zbiorów słów
    ({red, bull, bragantino} wobec {rb, bragantino}), a to ten sam klub.
    """
    ta, tb = _tokeny_tozsamosci(a), _tokeny_tozsamosci(b)
    if not ta or not tb:
        return False
    return bool(ta & tb) or bool({_rdzen(t) for t in ta} & {_rdzen(t) for t in tb})


def resolve_team_key(all_keys: set[str], team_name: str) -> str | None:
    """Klucz drużyny w statystykach meczu — po ZBIORACH SŁÓW, nie podobieństwie.

    PO CO (znalezione 2026-07-30): statystyki drużynowe rozliczały się tylko
    przy IDENTYCZNYM napisie, a 365Scores nazywa kluby inaczej niż my:

        qarabag              -> qarabag agdam
        sarmiento            -> sarmiento junin
        fci levadia tallinn  -> levadia tallinn
        deportivo riestra    -> riestra
        instituto de cordoba -> instituto ac cordoba

    Na 46 wiszących typów drużynowych 26 ginęło wyłącznie na tym. Typ znikał
    po meczu i nie pojawiał się w Skuteczności.

    ŚWIADOMIE BEZ PODOBIEŃSTWA TEKSTU ([[parowanie-nazw-druzyn]]): dla
    „Deportivo Riestra" najbliższe tekstowo jest „Deportivo Recoleta", czyli
    INNY klub, a taka podmiana nie zostawia śladu. Tu liczymy wspólne słowa
    (po odsianiu szumu typu „FC") i wymagamy JEDNOZNACZNEGO maksimum — remis
    oznacza brak dopasowania, nie strzał. To bezpieczne także dlatego, że
    kandydaci są tylko dwaj: obie drużyny tego meczu.

    TRZY PODEJŚCIA, OD NAJOSTRZEJSZEGO (rozszerzone 2026-08-02 — poprzednia
    wersja gubiła 45 typów w pięciu meczach, mimo że źródło miało komplet
    statystyk). Każde następne uruchamia się TYLKO wtedy, gdy poprzednie nic
    nie znalazło, i każde wymaga jednoznacznego maksimum:

      1. wspólne słowa           „lillestrom sk"  -> „lillestrom"
      2. wspólne rdzenie          „aalesunds fk"   -> „aalesund"
      3. alias z ręcznej listy    „agf"            -> „aarhus"
    """
    p = _norm(team_name)
    if p in all_keys:
        return p
    tokeny = _tokeny_tozsamosci(p)
    if not tokeny:
        return None
    # ⚑ TA SAMA NAZWA, INNY PODZIAŁ NA SŁOWA (2026-08-17). „HamKam" u nas,
    # „Ham-Kam" u źródła — zbiory słów nie mają nic wspólnego ({hamkam} wobec
    # {ham, kam}), rdzenie też nie, więc typ czekał na dane, które leżały
    # gotowe. Sklejamy tokeny w jeden napis (po sortowaniu, żeby kolejność nie
    # miała znaczenia) i wymagamy JEDNOZNACZNEGO trafienia — kandydatami są
    # tylko dwie drużyny tego meczu, więc zlepek nie ma jak trafić w obcy klub.
    zlep = "".join(sorted(tokeny))
    zgodne = [k for k in all_keys
              if "".join(sorted(_tokeny_tozsamosci(k))) == zlep]
    if len(zgodne) == 1:
        return zgodne[0]
    warianty = (
        (tokeny, lambda t: t),
        ({_rdzen(t) for t in tokeny}, _rdzen),
        (tokeny | {a for t in tokeny for a in _ALIASY_KLUBU.get(t, ())},
         lambda t: t),
    )
    for nasze, przeksztalc in warianty:
        wyniki: list[tuple[int, str]] = []
        for k in all_keys:
            ich = {przeksztalc(t) for t in _tokeny_tozsamosci(k)}
            wspolne = nasze & ich
            if wspolne:
                wyniki.append((len(wspolne), k))
        if not wyniki:
            continue
        naj = max(w[0] for w in wyniki)
        najlepsze = [k for n, k in wyniki if n == naj]
        if len(najlepsze) == 1:
            return najlepsze[0]
    return None


def resolve_player_key(all_keys: set[str], player_name: str) -> str | None:
    """Znajdź klucz zawodnika w historii 365 (dokładnie albo nazwisko+inicjał)."""
    p = _norm(player_name)
    if p in all_keys:
        return p
    pt = p.split()
    if not pt:
        return None
    for k in all_keys:
        kt = k.split()
        if kt and pt[-1] == kt[-1] and pt[0][:1] == kt[0][:1]:
            return k
    return None


def game_player_shots(game_id: int) -> dict[str, dict[str, int]]:
    """Agregat strzałów per zawodnik (znormalizowane nazwisko) dla meczu.

    Liczony WYŁĄCZNIE w regularnym czasie (90 min + doliczony) — tak rozlicza
    bukmacher; strzały z dogrywki i serii karnych nie wchodzą do agregatu.
    """
    if game_id in _game_cache:
        return _game_cache[game_id]
    data = _get(f"{BASE}/game/?{Q}&gameId={game_id}")
    game = data.get("game", {})
    _zapamietaj_et(game_id, game)
    names = {int(m["id"]): str(m.get("name", "")) for m in game.get("members", []) if m.get("id")}
    per_player: dict[str, dict[str, int]] = {}
    for e in (game.get("chartEvents") or {}).get("events", []):
        m_ev = _minuta(e.get("time"))
        if m_ev is not None and m_ev > REGULARNY_CZAS_MIN:
            continue  # dogrywka / seria karnych
        counts = classify_event(e)
        if counts is None:
            continue
        name = names.get(int(e.get("playerId") or 0))
        if not name:
            continue
        slot = per_player.setdefault(_norm(name), dict.fromkeys(counts, 0))
        for k, v in counts.items():
            slot[k] += v
    _game_cache[game_id] = per_player
    return per_player


_subs_cache: dict[int, dict[str, dict]] = {}


def game_substitutions(game_id: int) -> dict[str, dict]:
    """Zmiany w meczu: {znormalizowane nazwisko SCHODZĄCEGO: {"wszedl":
    znormalizowane nazwisko wchodzącego, "minuta": float}}.

    Z game.events (eventType.id == 1000): playerId = WCHODZĄCY,
    extraPlayers[0] = SCHODZĄCY — kierunek potwierdzony minutami i składem
    wyjściowym (wchodzący ma started=0 i minuty = 90 − minuta zmiany).
    Tylko regularny czas — zmiany w dogrywce nie dotyczą rynków 90 min.
    """
    if game_id in _subs_cache:
        return _subs_cache[game_id]
    data = _get(f"{BASE}/game/?{Q}&gameId={game_id}")
    game = data.get("game", {})
    _zapamietaj_et(game_id, game)
    names = {
        int(m["id"]): str(m.get("name", ""))
        for m in game.get("members", [])
        if m.get("id")
    }
    out: dict[str, dict] = {}
    for e in game.get("events") or []:
        if (e.get("eventType") or {}).get("id") != 1000:
            continue
        try:
            gt = float(e.get("gameTime") or 0)
        except (TypeError, ValueError) as e:
            diagnostyka.cichy("365scores", "minuta_zmiany", e)
            continue
        if gt > REGULARNY_CZAS_MIN:
            continue
        wszedl = names.get(int(e.get("playerId") or 0))
        zszedl = names.get(int((e.get("extraPlayers") or [0])[0] or 0))
        if wszedl and zszedl:
            out[_norm(zszedl)] = {"wszedl": _norm(wszedl), "minuta": gt}
    _subs_cache[game_id] = out
    return out


def team_shot_history(
    competitor_id: int, n_games: int = 6
) -> list[tuple[int, dict[str, dict[str, int]]]]:
    """Historia drużyny: [(timestamp, {zawodnik: liczniki}), ...] od najnowszych."""
    out = []
    for gid, ts in recent_finished_games(competitor_id, n_games):
        try:
            out.append((ts, game_player_shots(gid)))
        except Exception as e:
            # jeden mecz mniej w historii strzałów — przy próbie 5–10 meczów
            # to jest realna zmiana wyceny, a wyglądało jak „tyle było"
            diagnostyka.cichy("365scores", "historia_strzalow_meczu", e)
            continue
        _time.sleep(0.3)  # grzecznie dla API
    return out


# ---- pełne statystyki meczowe per zawodnik (lineups.members[].stats) ----
# nazwa statystyki 365 -> nasz kod rynku. UWAGA: wbrew wcześniejszej nocie
# "odbiory nie występują w 365" — istnieje "Tackles Won" ("8/17"), ale jako
# para udane/próby, NIE licznik zdarzeń jak w statshub, więc do ROZLICZANIA
# rynku tackles się nie nadaje (definicje bukmacherskie liczą próby odbioru
# wg Opta) — zostaje w banku STYLU niżej, nie tutaj.
STAT_NAME_MAP = {
    "Minutes": "minutes",
    "Total Shots": "shots",
    "Fouls Made": "fouls_committed",
    "Was Fouled": "fouls_won",
    "Interceptions": "interceptions",
    "Offsides": "offsides",
}

# statystyki STYLU zawodnika (pełne matchupy, model/styl.py):
# nazwa 365 -> (klucz licznika, klucz mianownika | None) — "12/16 (75%)"
# niesie i udane (12), i PRÓBY (16); dotychczasowy _stat_val gubił mianownik,
# a to właśnie próby (dryblingi, pojedynki) opisują styl gry
STAT_STYLE_MAP = {
    "Successful Dribbles": ("dribbles_succ", "dribbles_att"),
    "Was Dribbled Past": ("dribbled_past", None),
    "Aerial Duels Won": ("aerial_won", "aerial_att"),
    "Ground Duels Won": ("ground_won", "ground_att"),
    "Key Passes": ("key_passes", None),
    "Crosses Completed": ("crosses_succ", "crosses_att"),
    "Long Passes Completed": ("longballs_succ", "longballs_att"),
}

_full_cache: dict[int, dict] = {}


def _stat_val(v) -> float:
    """"90'" -> 90; "20/26 (77%)" -> 20; "2" -> 2."""
    s = str(v).strip().rstrip("'")
    s = s.split("/")[0].split("(")[0].strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _stat_pair(v) -> tuple[float, float | None]:
    """"20/26 (77%)" -> (20, 26); "59%" -> (59, None); "3" -> (3, None)."""
    s = str(v).strip().rstrip("'").split("(")[0].strip()
    parts = [p.strip().rstrip("%") for p in s.split("/")]
    try:
        num = float(parts[0])
    except (ValueError, IndexError):
        return 0.0, None
    if len(parts) >= 2:
        try:
            return num, float(parts[1])
        except ValueError:
            return num, None
    return num, None


def _poz_z_formacji(m: dict) -> str:
    """365 formation.name ("Centre Back", "Central Midfield") -> G/D/M/F."""
    nm = str(((m.get("formation") or {}).get("name")) or "").upper()
    if "GOALKEEPER" in nm:
        return "G"
    if "MIDFIELD" in nm:               # też Defensive/Attacking Midfield
        return "M"
    if "BACK" in nm or "DEFEN" in nm:  # też Left/Right Wing Back
        return "D"
    if "WING" in nm or "FORWARD" in nm or "STRIKER" in nm or "ATTACK" in nm:
        return "F"
    return ""


def game_player_match_stats(game_id: int) -> dict[str, dict[str, float]]:
    """Pełne staty meczu per zawodnik: minuty, strzały, faule, przechwyty...

    Zwraca {znormalizowane nazwisko: {"minutes": 90, "shots": 2, ...,
    "started": 1.0/0.0, "sot": ... (z chartEvents), "pos": "D"/"M"/"F"/"G"
    (litera formacji — pod kubełki profilu rywala)}}.
    """
    if game_id in _full_cache:
        return _full_cache[game_id]
    data = _get(f"{BASE}/game/?{Q}&gameId={game_id}")
    game = data.get("game", {})
    _zapamietaj_et(game_id, game)
    names = {int(m["id"]): str(m.get("name", "")) for m in game.get("members", []) if m.get("id")}
    out: dict[str, dict[str, float]] = {}
    for side in ("homeCompetitor", "awayCompetitor"):
        lu = (game.get(side) or {}).get("lineups") or {}
        druzyna = _norm(str((game.get(side) or {}).get("name", "")))
        for m in lu.get("members") or []:
            name = names.get(int(m.get("id") or 0))
            if not name:
                continue
            rec: dict = {
                "started": 1.0 if m.get("statusText") == "Starting" else 0.0,
                "pos": _poz_z_formacji(m),
                # drużyna zawodnika — bank stylu (model/styl.py) grupuje po niej
                "druzyna": druzyna,
            }
            for s in m.get("stats") or []:
                nazwa = str(s.get("name"))
                kod = STAT_NAME_MAP.get(nazwa)
                if kod:
                    rec[kod] = _stat_val(s.get("value"))
                para = STAT_STYLE_MAP.get(nazwa)
                if para:
                    num, den = _stat_pair(s.get("value"))
                    rec[para[0]] = num
                    if para[1] and den is not None:
                        rec[para[1]] = den
            if rec.get("minutes"):
                out[_norm(name)] = rec
    # celne strzały z mapy strzałów (nie ma ich w lineups)
    try:
        for pkey, cnts in game_player_shots(game_id).items():
            if pkey in out:
                out[pkey]["sot"] = float(cnts.get("sot", 0))
    except Exception as e:
        # ŚCIEŻKA ROZLICZANIA statystyk zawodników — cichy błąd zostawia typy
        # z tego meczu nierozliczone, a po siedmiu dniach idą na „zwrot"
        diagnostyka.cichy("365scores", "rozliczenie_statystyk", e)
    _full_cache[game_id] = out
    return out


def team_match_history(
    competitor_id: int, n_games: int = 6
) -> list[tuple[int, dict[str, dict[str, float]]]]:
    """Historia pełnych statystyk drużyny: [(timestamp, {zawodnik: staty}), ...]."""
    out = []
    for gid, ts in recent_finished_games(competitor_id, n_games):
        try:
            out.append((ts, game_player_match_stats(gid)))
        except Exception as e:
            diagnostyka.cichy("365scores", "historia_statystyk_meczu", e)
            continue
        _time.sleep(0.3)
    return out


# ---- statystyki DRUŻYNOWE per mecz (endpoint game/stats) — bank STYLU ----
# id statystyki 365 -> (nasz klucz, czy brać MIANOWNIK pary "x/y")
# Mianownik = PRÓBY (dośrodkowania, długie piłki, dryblingi) — to one opisują
# styl gry drużyny, nie skuteczność. Sprawdzone na żywym meczu MŚ 2026-07-14.
TEAM_STATS_MAP = {
    1: ("zolte", False), 2: ("czerwone", False),
    3: ("shots", False), 4: ("sot", False), 6: ("shots_blocked", False),
    8: ("corners", False), 9: ("offsides", False),
    10: ("possession", False), 12: ("fouls", False),
    52: ("crosses_att", True), 53: ("longballs_att", True),
    54: ("dribbles_att", True), 150: ("duels_won", False),
    56: ("aerial", None),          # para: won i attempts — oba potrzebne
    147: ("shots_outside", False),
}

_scores_cache: dict[int, dict] = {}


def game_scores(game_id: int) -> dict[str, float]:
    """Gole drużyn w meczu: {znormalizowana nazwa: gole} (endpoint game/).

    Do rozliczania rynku team_goals. Wynik obejmuje dogrywkę, ale rynki
    drużynowe z dogrywką i tak zamykają się jako zwrot (after_extra_time)
    ZANIM ktokolwiek zajrzy do tej funkcji.
    """
    if game_id in _scores_cache:
        return _scores_cache[game_id]
    game = _get(f"{BASE}/game/?{Q}&gameId={game_id}").get("game", {})
    out: dict[str, float] = {}
    for side in ("homeCompetitor", "awayCompetitor"):
        c = game.get(side) or {}
        nm = _norm(str(c.get("name") or ""))
        sc = c.get("score")
        if nm and sc is not None and float(sc) >= 0:
            out[nm] = float(sc)
    _zapamietaj_et(game_id, game)  # przy okazji: cache dogrywki bez 2. requestu
    _scores_cache[game_id] = out
    return out


_team_stats_cache: dict[int, dict] = {}


def game_team_stats(game_id: int) -> dict[str, dict[str, float]]:
    """Statystyki drużynowe meczu: {znormalizowana nazwa: {klucz: wartość}}.

    Endpoint `game/stats/?...&games=` (NIE `game/`) — płaska lista ~40
    statystyk per competitorId; nazwy drużyn z pola `competitors` tej samej
    odpowiedzi. `kartki` = żółte + czerwone (skala matchup.LG_TEAM_CARDS).
    """
    if game_id in _team_stats_cache:
        return _team_stats_cache[game_id]
    data = _get(f"{BASE}/game/stats/?{Q}&games={game_id}")
    nazwa_cid = {
        int(c["id"]): _norm(str(c.get("name", "")))
        for c in data.get("competitors") or []
        if c.get("id")
    }
    per_cid: dict[int, dict[str, float]] = {}
    for s in data.get("statistics") or []:
        mapowanie = TEAM_STATS_MAP.get(s.get("id"))
        cid = s.get("competitorId")
        if not mapowanie or cid is None:
            continue
        klucz, bierz_mianownik = mapowanie
        num, den = _stat_pair(s.get("value"))
        slot = per_cid.setdefault(int(cid), {})
        if klucz == "aerial":
            slot["aerial_won"] = num
            if den is not None:
                slot["aerial_att"] = den
        elif bierz_mianownik:
            if den is not None:
                slot[klucz] = den
        else:
            slot[klucz] = num
    out: dict[str, dict[str, float]] = {}
    for cid, st in per_cid.items():
        nm = nazwa_cid.get(cid)
        if not nm:
            continue
        st["kartki"] = st.pop("zolte", 0.0) + st.pop("czerwone", 0.0)
        out[nm] = st
    _team_stats_cache[game_id] = out
    return out
