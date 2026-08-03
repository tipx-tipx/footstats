"""Źródło kursów: Superbet (wewnętrzne API ofertowe ich strony).

Zweryfikowane 2026-07-02:
  * lista meczów:  /v2/pl-PL/events/by-date?...&sportId=5
  * pełna oferta:  /v2/pl-PL/events/{eventId}  (kilkaset rynków, w tym
    per-zawodnik: strzały, celne, zza pola, głową, faule, faule na zawodniku,
    odbiory, spalone — dokładnie nasze rynki)

Kursy zmieniają się w czasie → NIE cache'ujemy odpowiedzi z kursami.
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections import defaultdict

from curl_cffi import requests

BASE = "https://production-superbet-offer-pl.freetls.fastly.net/v2/pl-PL"
HEADERS = {
    "Accept": "application/json",
    "Origin": "https://superbet.pl",
    "Referer": "https://superbet.pl/",
}

# rynki zawodnicze Superbetu -> nasze kody
PLAYER_MARKET_MAP = {
    "Zawodnik - liczba strzałów": "shots",
    "Zawodnik - liczba celnych strzałów": "sot",
    "Zawodnik - liczba strzałów spoza pola karnego": "shots_outside_box",
    "Zawodnik - liczba celnych strzałów spoza pola karnego": "sot_outside_box",
    "Zawodnik - liczba strzałów głową": "headed_shots",
    "Zawodnik - liczba celnych strzałów głową": "headed_sot",
    "Zawodnik - liczba popełnionych fauli": "fouls_committed",
    "Zawodnik - liczba fauli na zawodniku": "fouls_won",
    "Zawodnik - liczba odbiorów": "tackles",
    "Zawodnik - liczba spalonych": "offsides",
    "Zawodnik - liczba niecelnych strzałów": "shots_off_target",
    "Zawodnik - liczba zablokowanych strzałów": "shots_blocked",
    "Zawodnik - liczba przechwytów": "interceptions",
}

# rynki drużynowe (nazwa zawiera nazwę drużyny, np. "Francja liczba fauli").
# Sonda klubowa 2026-07-20 (Atlético MG–Bahia, 287 rynków): czyste rynki
# drużynowe z total to "liczba goli", "liczba rzutów rożnych", "liczba
# kartek"; fauli/strzałów ogółem Superbet dla klubów często nie kwotuje
# czysto (tylko w combo), ale sufiksy zostają — łapią, gdy są.
#
# DWIE KONWENCJE NAZW (zmierzone 2026-07-27, patrz `_kod_rynku_druzyny`):
# ta sama oferta zapisuje rynek drużynowy raz z drużyną z przodu, raz z tyłu.
TEAM_MARKET_SUFFIX = {
    "liczba fauli": "team_fouls",
    "liczba strzałów": "team_shots",
    "liczba celnych strzałów": "team_sot",
    "liczba żółtych kartek": "team_cards",
    "liczba kartek": "team_cards",
    "liczba goli": "team_goals",
    "liczba rzutów rożnych": "team_corners",
}

# „KTO WIĘCEJ" — porównanie dwóch drużyn zamiast linii z dwiema stronami.
# Rynek ma TRZY wyniki (gospodarz / remis / gość), a nazwa wyniku bywa raz
# nazwą drużyny, raz „1"/„X"/„2" — obsługujemy oba zapisy.
#
# PO CO TO JEST WAŻNE: nasz zmierzony błąd to zawyżanie przewidywanej liczby
# zdarzeń. W zakładzie „kto więcej" ten błąd SIĘ SKRACA, bo zawyżamy obie
# drużyny naraz — to jedyny znany nam rynek odporny na naszą główną wadę.
POROWNANIA_DRUZYN = {
    "najwięcej strzałów": "team_shots",
    "najwięcej celnych strzałów": "team_sot",
    "najwięcej kartek": "team_cards",
    "najwięcej rzutów rożnych": "team_corners",
    "najwięcej fauli": "team_fouls",
}

# SUMA MECZOWA obu drużyn (dziś czytamy tylko gole — reszta leżała odłogiem:
# „Liczba rzutów rożnych" to 42 kwotowania na mecz, ignorowane w całości).
SUMY_MECZOWE = {
    "liczba rzutów rożnych": "match_corners",
    "liczba strzałów": "match_shots",
    "liczba celnych strzałów": "match_sot",
    "liczba kartek": "match_cards",
    "liczba żółtych kartek": "match_cards",
    "liczba fauli": "match_fouls",
}

# Rynki połówkowe i minutowe NIE są naszym zakładem — model liczy pełny mecz.
_FRAGMENTY_MECZU = ("połowa", "polowa", "minuty", "od 0:00", "przedział",
                    "przedzial", "h2h", "kto pierwszy", "ostatni")


def _fragment_meczu(mname_l: str) -> bool:
    """Czy nazwa dotyczy wycinka meczu (połowa, okno minutowe, przedział)."""
    return any(f in mname_l for f in _FRAGMENTY_MECZU)

# nazwy reprezentacji: Superbet (PL) -> Sofascore/statshub (EN)
TEAM_PL_EN = {
    "Hiszpania": "Spain", "Austria": "Austria", "USA": "USA",
    "Bośnia i Hercegowina": "Bosnia & Herzegovina", "Belgia": "Belgium",
    "Senegal": "Senegal", "Anglia": "England", "DR Konga": "DR Congo",
    "Meksyk": "Mexico", "Ekwador": "Ecuador", "Francja": "France",
    "Szwecja": "Sweden", "Norwegia": "Norway", "Maroko": "Morocco",
    "Holandia": "Netherlands", "Niemcy": "Germany", "Paragwaj": "Paraguay",
    "Brazylia": "Brazil", "Japonia": "Japan", "Kanada": "Canada",
    "Wybrzeże Kości Słoniowej": "Ivory Coast", "Portugalia": "Portugal",
    "Argentyna": "Argentina", "Włochy": "Italy", "Chorwacja": "Croatia",
    "Polska": "Poland", "Urugwaj": "Uruguay", "Kolumbia": "Colombia",
    # pozostałe reprezentacje MŚ 2026
    "Szwajcaria": "Switzerland", "Algieria": "Algeria", "Australia": "Australia",
    "Egipt": "Egypt", "Ghana": "Ghana",
    "Republika Zielonego Przylądka": "Cape Verde", "Zielony Przylądek": "Cape Verde",
    "Korea Południowa": "South Korea", "Iran": "Iran", "Arabia Saudyjska": "Saudi Arabia",
    "Katar": "Qatar", "Tunezja": "Tunisia", "Nigeria": "Nigeria",
    "Kamerun": "Cameroon", "RPA": "South Africa", "Ekwador ": "Ecuador",
    "Kostaryka": "Costa Rica", "Panama": "Panama", "Honduras": "Honduras",
    "Peru": "Peru", "Chile": "Chile", "Wenezuela": "Venezuela",
    "Nowa Zelandia": "New Zealand", "Turcja": "Türkiye", "Serbia": "Serbia",
    "Dania": "Denmark", "Szkocja": "Scotland", "Walia": "Wales",
    "Grecja": "Greece", "Ukraina": "Ukraine", "Czechy": "Czechia",
    "Węgry": "Hungary", "Rumunia": "Romania", "Słowacja": "Slovakia",
    "Mali": "Mali", "Burkina Faso": "Burkina Faso", "RD Konga": "DR Congo",
    "Jordania": "Jordan", "Irak": "Iraq", "Uzbekistan": "Uzbekistan",
}


def norm_name(name: str) -> str:
    """Normalizacja nazwiska do dopasowania między źródłami.

    'Mateta, Jean-Philippe' i 'Jean-Philippe Mateta' -> ten sam klucz.
    """
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    tokens = sorted(t for t in re.split(r"[^a-z]+", s) if len(t) > 1)
    return " ".join(tokens)


def znajdz_zawodnika(players: dict, nazwa: str) -> dict:
    """Rekord propsów zawodnika po nazwisku z innego źródła.

    W ofercie klubowej Superbet używa PEŁNYCH nazwisk ('Renan Augusto Lodi
    dos Santos'), a statshub boiskowych ('Renan Lodi') — dokładny klucz
    norm_name wtedy nie trafia (zmierzone 2026-07-20, Brasileirão). Fallback:
    dopasowanie podzbiorem tokenów w OBIE strony, przyjmowane tylko gdy
    JEDNOZNACZNE (dwóch kandydatów = brak dopasowania, nie zgadujemy).
    """
    key = norm_name(nazwa)
    rec = players.get(key)
    if rec is not None:
        return rec
    tokeny = set(key.split())
    if not tokeny:
        return {}
    trafienia = [
        k for k in players
        if tokeny <= set(k.split()) or set(k.split()) <= tokeny
    ]
    if len(trafienia) == 1:
        return players[trafienia[0]]
    return {}


def _get(url: str, min_interval: float = 1.5, retries: int = 3) -> dict:
    """GET z retry (jak statshub._get) — bez tego jeden nieudany request i
    dany mecz zostaje bez kursów Superbet do następnego cyklu (typy/kupony na
    ten mecz milkną). 429/403 (throttling) dostają znacznie dłuższe
    wychłodzenie niż timeout/5xx — jak http_client.RateLimitedClient — żeby
    kolejna próba w trakcie "chłodzenia" źródła nie eskalowała blokady."""
    last: Exception = RuntimeError(f"nie udało się pobrać: {url}")
    for attempt in range(retries):
        time.sleep(min_interval)
        try:
            r = requests.get(url, impersonate="chrome124", timeout=25, headers=HEADERS)
        except Exception as e:  # timeout, błąd sieci
            last = e
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r.json()
        last = RuntimeError(f"Superbet {r.status_code}: {url}")
        if attempt < retries - 1:
            time.sleep(60 * (attempt + 1) if r.status_code in (403, 429) else 3 * (attempt + 1))
    raise last


def list_events(days_ahead: int = 7, cofnij_h: int = 12) -> list[dict]:
    """Oferta prematch w oknie [teraz - cofnij_h, +days_ahead].

    `cofnij_h` NIE jest kosmetyką: `matchTimestamp` Superbetu bywa PRZESUNIĘTY
    względem realnego kickoffu (zmierzone 2026-07-25: Jagiellonia–Korona gra
    14:45, znacznik 13:04; Lech gra 20:15, znacznik 12:53). Przy starcie okna
    ustawionym na „teraz" mecz wypadał z listy, gdy tylko jego znacznik minął —
    czyli traciliśmy mecze TUŻ PRZED rozpoczęciem, a więc te najważniejsze
    (oferta żyła: fetch_stat_odds po eventId zwracał komplet 41 graczy).
    Kickoffem i tak filtrujemy dalej po stronie konsumentów.
    """
    start = time.strftime(
        "%Y-%m-%d+%H:%M:%S", time.localtime(time.time() - cofnij_h * 3600)
    )
    end = time.strftime(
        "%Y-%m-%d+23:59:00", time.localtime(time.time() + days_ahead * 86400)
    )
    url = (
        f"{BASE}/events/by-date?currentStatus=active&offerState=prematch"
        f"&startDate={start}&endDate={end}&sportId=5"
    )
    return _get(url).get("data", [])


def match_superbet_event(
    events: list[dict], home_en: str, away_en: str, kickoff_ts: int
) -> dict | None:
    """Znajdź mecz Superbetu odpowiadający meczowi Sofascore (nazwy + czas)."""
    # jedna nazwa EN może mieć KILKA polskich wariantów (np. Cape Verde =
    # "Republika Zielonego Przylądka" i "Zielony Przylądek") — zbierz wszystkie
    en_pl_multi: dict[str, set[str]] = {}
    for pl, en in TEAM_PL_EN.items():
        en_pl_multi.setdefault(en, set()).add(pl.strip())
    home_pl = en_pl_multi.get(home_en, set())
    away_pl = en_pl_multi.get(away_en, set())
    for ev in events:
        name = ev.get("matchName") or ""
        parts = [p.strip() for p in name.split("·")]
        if len(parts) != 2:
            continue
        # Dokładne dopasowanie nazw (PL) — w turnieju mecz jest jednoznaczny,
        # więc NIE bramkujemy czasem (matchTimestamp Superbetu bywa przesunięty).
        if parts[0] in home_pl and parts[1] in away_pl:
            return ev
        # awaryjnie: znormalizowane nazwy + luźne okno czasowe (±30 h)
        if norm_name(parts[0]) == norm_name(home_en) and norm_name(parts[1]) == norm_name(away_en):
            try:
                ev_ts = int(ev.get("matchTimestamp") or 0)
                if ev_ts > 1e11:
                    ev_ts //= 1000
            except (TypeError, ValueError):
                ev_ts = 0
            if not ev_ts or abs(ev_ts - kickoff_ts) < 30 * 3600:
                return ev
    return None


def _kod_rynku_druzyny(
    mname: str, home_pl: str, away_pl: str
) -> tuple[str, str | None]:
    """('home'/'away', kod rynku) dla nazwy rynku drużynowego — albo (_, None).

    Superbet zapisuje ten sam rodzaj rynku na DWA sposoby i do 2026-07-27
    czytaliśmy tylko pierwszy:

        'Racing Club - liczba goli'              drużyna z przodu
        'Liczba celnych strzałów - Racing Club'  drużyna z tyłu
        'Liczba strzałów Racing Club'            z tyłu i BEZ myślnika

    Strzały, celne i faule drużynowe stoją WYŁĄCZNIE w drugiej konwencji, więc
    cały ten kawałek oferty był dla nas niewidzialny: silnik budował trendy
    z banku stylu i tracił je na `brak_kursu` (zmierzone 2026-07-27: 100%
    odrzuceń dla team_shots/team_sot/team_fouls, 53 trendy na darmo).

    Dopasowanie jest ŚCISŁE — reszta nazwy po odcięciu drużyny musi być całym
    kluczem `TEAM_MARKET_SUFFIX`. Dzięki temu combo w rodzaju
    'Santos powyżej 4.5 celnych strzałów; Santos strzeli gola' (inny zakład,
    nie do użycia jako typ) odpada samo, bez osobnego filtra.

    Gdy nazwa jednej drużyny jest końcówką drugiej ('River Plate' w 'CA River
    Plate'), wygrywa DŁUŻSZE dopasowanie — inaczej kurs trafiłby do rywala.
    """
    trafienia: list[tuple[int, str, str]] = []
    for team_pl, slot in ((home_pl, "home"), (away_pl, "away")):
        if not team_pl:
            continue
        if mname.startswith(team_pl):
            reszta = mname[len(team_pl):]
        elif mname.endswith(team_pl):
            reszta = mname[: -len(team_pl)]
        else:
            continue
        code = TEAM_MARKET_SUFFIX.get(reszta.strip(" -").lower())
        if code:
            trafienia.append((len(team_pl), slot, code))
    if not trafienia:
        return "home", None
    _, slot, code = max(trafienia)
    return slot, code


# Nazwy rynku kartki, które NIE są naszym rynkiem — sprawdzać PRZED słowem
# „kartk", bo każda z nich je zawiera.
_KARTKA_ODRZUC = (
    "czerwon",      # czerwona kartka to inne zdarzenie
    "1. kartk", "pierwsz",   # kto dostanie pierwszą kartkę w meczu
    "połow", "dogryw",       # my liczymy 90 minut
    "liczba kartek",         # kartki DRUŻYNY, nie zawodnika
)


def _zawodnik_kartka(mname_l: str, spec: dict) -> str | None:
    """Nazwa zawodnika, jeśli to rynek „zawodnik otrzyma (żółtą) kartkę".

    GUBILIŚMY TEN RYNEK OD ZAWSZE (znalezione 2026-08-03) — przez dwa
    niezależne rozjazdy naraz:

    * nazwa w ofercie ma MYŚLNIK („Zawodnik - otrzyma kartkę"), a porównanie
      szło po dokładnym stringu bez myślnika,
    * zawodnik siedzi w `specifiers.player`, nie w `player_name` jak przy
      rynkach liczbowych (strzały, faule).

    Cena: 66 kwotowanych zawodników na Sparcie Praga – Lyonie i 38 na
    Olympiakosie – NEC, czytanych jako zero. To bolało najbardziej tam, gdzie
    bolało najbardziej: na kwalifikacjach pucharów Superbet NIE kwotuje
    strzałów ani fauli, więc kartka bywa JEDYNĄ naszą statystyką z kursem,
    a zakładka meczu zostawała pusta.

    Ta sama lekcja co przy „Poniżej"/„poniżej" w rynkach drużynowych:
    dopasowujemy po słowach kluczowych, nie po dokładnej nazwie.

    Kupony łączone („X strzeli gola; Y otrzyma kartkę") też zawierają słowo
    „kartkę", ale nie mają ani „zawodnik" w nazwie rynku, ani specyfikatora
    `player` — trzymają graczy pod `ss_player_*`. Odpadają na obu warunkach.
    """
    if "kartk" not in mname_l or "zawodnik" not in mname_l:
        return None
    if any(x in mname_l for x in _KARTKA_ODRZUC):
        return None
    gracz = spec.get("player") or spec.get("player_name")
    return str(gracz) if gracz else None


def fetch_stat_odds(event_id: int, home_pl: str, away_pl: str) -> dict:
    """Pobierz i znormalizuj kursy statystyczne meczu.

    Zwraca:
      players: norm_name -> market_code -> line -> {'over': kurs, 'under': kurs}
      player_names: norm_name -> surowa nazwa z oferty (radar: wyszukiwarka
                    statshub potrzebuje nazwiska w naturalnej kolejności,
                    norm_name sortuje tokeny alfabetycznie)
      teams:   'home'/'away' -> market_code -> line -> {'over': ..., 'under': ...}
    """
    d = _get(f"{BASE}/events/{event_id}")
    data = d.get("data")
    event = data[0] if isinstance(data, list) else data
    odds = event.get("odds", [])

    players: dict = defaultdict(lambda: defaultdict(dict))
    player_names: dict[str, str] = {}
    teams: dict = {"home": defaultdict(dict), "away": defaultdict(dict)}
    # kursy meczowe pod tempo/scenariusz meczu (model/tempo.py)
    match: dict = {"h": None, "x": None, "a": None, "totals": defaultdict(dict)}
    # „kto więcej": kod rynku -> {"home"/"remis"/"away": kurs}
    porownania: dict = defaultdict(dict)
    # sumy meczowe obu drużyn: kod rynku -> linia -> {"over"/"under": kurs}
    sumy: dict = defaultdict(lambda: defaultdict(dict))

    for o in odds:
        if o.get("status") == "block":
            continue
        price = o.get("price")
        if not price or price <= 1.0:
            continue
        mname = (o.get("marketName") or "").strip()
        oname = (o.get("name") or "").strip()
        spec = o.get("specifiers") or {}

        mname_l_pelna = mname.lower()

        # --- „KTO WIĘCEJ": trzy wyniki, bez linii ---
        if (mname_l_pelna in POROWNANIA_DRUZYN
                and not _fragment_meczu(mname_l_pelna)):
            kod = POROWNANIA_DRUZYN[mname_l_pelna]
            on_l = oname.lower()
            # nazwa wyniku: raz nazwa drużyny, raz „1"/„X"/„2"
            if on_l in ("x", "remis"):
                strona = "remis"
            elif oname == "1" or (home_pl and oname == home_pl):
                strona = "home"
            elif oname == "2" or (away_pl and oname == away_pl):
                strona = "away"
            else:
                strona = None
            if strona:
                porownania[kod][strona] = float(price)
            continue

        # --- SUMA MECZOWA obu drużyn (bez nazwy drużyny w nazwie rynku) ---
        if (mname_l_pelna in SUMY_MECZOWE and spec.get("total")
                and not _fragment_meczu(mname_l_pelna)):
            kod_s = SUMY_MECZOWE[mname_l_pelna]
            try:
                linia_s = float(spec["total"])
            except (TypeError, ValueError):
                linia_s = None
            on_l = oname.lower()
            strona_s = ("over" if "powyżej" in on_l
                        else "under" if "poniżej" in on_l else None)
            if linia_s is not None and strona_s:
                sumy[kod_s][linia_s][strona_s] = float(price)
            continue

        # --- 1X2 (rynek "Mecz") i total goli ("Liczba goli") ---
        if mname == "Mecz" and oname in ("1", "X", "2"):
            match[{"1": "h", "X": "x", "2": "a"}[oname]] = float(price)
            continue
        if mname == "Liczba goli" and spec.get("total"):
            try:
                line = float(spec["total"])
            except ValueError:
                line = None
            if line is not None:
                if "powyżej" in oname.lower():
                    match["totals"][line]["over"] = float(price)
                elif "poniżej" in oname.lower():
                    match["totals"][line]["under"] = float(price)
            continue

        # STRONA ZAKŁADU BEZ WZGLĘDU NA WIELKOŚĆ LITER (błąd znaleziony
        # 2026-07-27). Superbet zapisuje wynik raz małą, raz wielką literą —
        # 'Liczba celnych strzałów - Racing Club' ma 'poniżej 3.5', ale
        # 'Liczba strzałów Racing Club' ma już 'Poniżej 10.5'. Dopasowanie
        # wrażliwe na wielkość liter gubiło ten drugi wariant po cichu:
        # rynek istniał w ofercie, a u nas kończył się jako `brak_kursu`.
        oname_l, mname_l = oname.lower(), mname.lower()
        side = None
        if "powyżej" in oname_l or "powyżej" in mname_l:
            side = "over"
        elif "poniżej" in oname_l or "poniżej" in mname_l:
            side = "under"

        # --- zawodnicy ---
        code = PLAYER_MARKET_MAP.get(mname)
        if code and spec.get("player_name") and spec.get("total") and side:
            try:
                line = float(spec["total"])
            except ValueError:
                continue
            key = norm_name(spec["player_name"])
            player_names.setdefault(key, str(spec["player_name"]))
            players[key][code].setdefault(line, {})[side] = float(price)
            continue

        # --- kartka zawodnika ---
        kartkowy = _zawodnik_kartka(mname_l, spec)
        if kartkowy:
            key = norm_name(kartkowy)
            player_names.setdefault(key, kartkowy)
            players[key]["yellow_card"].setdefault(0.5, {})["over"] = float(price)
            continue

        # --- drużyny: pełny mecz, obie konwencje nazw ---
        if "połowa" in mname:
            continue
        total = spec.get("total")
        if total and side:
            slot, code = _kod_rynku_druzyny(mname, home_pl, away_pl)
            if code:
                try:
                    line = float(total)
                except ValueError:
                    continue
                teams[slot][code].setdefault(line, {})[side] = float(price)

    return {"players": {k: dict(v) for k, v in players.items()},
            "player_names": player_names,
            "teams": {k: dict(v) for k, v in teams.items()},
            # „kto więcej" i sumy meczowe — nowe rodzaje zakładu (2026-07-30)
            "porownania": {k: dict(v) for k, v in porownania.items()},
            "sumy": {k: {l: dict(v) for l, v in lin.items()}
                     for k, lin in sumy.items()},
            "match": {**match, "totals": {k: dict(v) for k, v in match["totals"].items()}}}
