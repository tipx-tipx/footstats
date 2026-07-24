"""Radar okazji kontekstowych — sygnały, których model celowo nie gra.

Trzy detektory (pomysł z ręcznych typów tipsterskich, 2026-07-22):

1. TRANSFER („nowy w drużynie"): historia statshub podąża za ZAWODNIKIEM,
   nie klubem — gdy ostatnie mecze gracza są w innej lidze niż liga jego
   obecnej drużyny (konsensus lig z historii KOLEGÓW z zespołu), rynek
   często wycenia go w ciemno. Model liczy takie przypadki ze starej
   historii i zwykle odrzuca je jako „rozjazd z rynkiem" — dlatego radar
   działa POZA bramami publikacji: to warstwa informacyjna z drabinką
   kursów, nie typ modelu.

2. FORMA („seria"): model świadomie NIE ma czynnika formy (PLAN.md — tylko
   wygaszanie czasowe, podwójne liczenie psuje kalibrację). Radar pokazuje
   serię trafień nad linią Superbetu jako sygnał w UI, bez dotykania p_model.

3. DEBIUTANT („rynek zgaduje"): Superbet kwotuje zawodnika, którego NIE MA
   w feedzie propsów statshub (bukmacherzy UK nie wystawili mu linii — brak
   danych w nowym klubie). Zmierzone na Ba-Sy (Hearts) 2026-07-22: feed
   propsów Sturm–Hearts miał 42 graczy, nowego nabytku ani śladu, a Superbet
   dawał mu pełną drabinkę. Identyfikacja przez /api/search + weryfikację
   team_id profilu z drużynami meczu.

Wszystkie progi są celowo konserwatywne: radar ma pokazywać kilka soczystych
wpisów dziennie, nie ścianę szumu.
"""

from __future__ import annotations

from collections import Counter

from ..sources import statshub, superbet

# --- progi detektorów ---
OKNO_TRANSFER = 15          # ile ostatnich meczów historii patrzymy na ligi
MIN_HISTORIA_TRANSFER = 8   # mniej meczów = za mało, żeby orzekać o zmianie
MAX_MECZE_W_NOWEJ = 3       # tyle meczów w lidze drużyny to wciąż „nowy"
MIN_MECZE_W_STAREJ = 6      # tyle meczów w innej lidze potwierdza przeszłość
OKNO_GRAL_PRZECIW = 8       # mecz PRZECIW obecnej drużynie w tylu ostatnich
MAX_DNI_SWIEZOSC = 60       # ostatni występ dawniej = nieaktualna historia

OKNO_FORMY = 6              # seria liczona z tylu OSTATNICH rozegranych
MIN_GIER_FORMA = 12         # łącznie rozegranych, żeby była baza porównania
MIN_TRAFIEN_FORMA = 5       # tyle z OKNO_FORMY meczów nad linią = seria
MIN_BOOST_FORMY = 1.4       # średnia/90 w oknie >= tyle razy średnia bazy
                            # (1.25 dawało ~13% graczy na żywym feedzie —
                            # pomiar 2026-07-22; seria ma być rzadka)
MIN_MINUT_MECZU = 20        # krótsze występy nie liczą się do serii
MIN_KURS_FORMY = 1.35       # linia serii musi być grywalna (nie 1.05)

MIN_RYNKOW_DEBIUTANTA = 2   # Superbet kwotuje >= tyle rynków (odsiew szumu)
MAX_WYSZUKAN_CYKL = 12      # limit zapytań /api/search na cykl (grzeczność)
MAX_WPISOW = 120            # sufit wpisów (drabinki = każdy kwotowany gracz,
                            # sygnały zawsze przodem — patrz sortowanie)
OSTATNIE_N = 10             # ile ostatnich występów pokazuje karta rynku
MAX_SEZONOW_WPISU = 3       # sekcja "sezony" na karcie (bieżący + poprzednie)
MIN_KURS_DRABINKI = 1.10    # niższe kursy to szum, nie zakład (pomiar: 1.01)
UTID_MUNDIAL = 16           # MŚ nigdy nie jest „starą ligą" (lato 2026:
                            # każdy reprezentant wracał z mundialu)
# utid liczy się jako „rozgrywki drużyny" (nie stara liga zawodnika), gdy
# grało w nim >= tylu RÓŻNYCH kolegów z zespołu — łapie bieżącą fazę ligi
# (Apertura/Clausura), puchary klubu i mundial przy 2+ reprezentantach
MIN_KOLEGOW_WSPOLNY_UTID = 2

# minuty z historii bywają None/0 dla meczów bez występu
def _grane(tr: statshub.StatshubTrend) -> list[tuple[float, float, int]]:
    """(licznik, minuty, ts) wyłącznie z meczów faktycznie rozegranych."""
    return [
        (float(c), float(m), int(ts))
        for c, m, ts in zip(tr.counts, tr.minutes, tr.timestamps)
        if m and m >= MIN_MINUT_MECZU
    ]


def liga_konsensus(
    trends: list[statshub.StatshubTrend],
) -> dict[int, tuple[int, set[int]]]:
    """Per drużyna: (dominująca liga, utidy wspólne dla >= 2 kolegów).

    Dominanta = moda utid-ów wszystkich meczów wszystkich graczy drużyny —
    wskazuje ligę domową bez zewnętrznej mapy klub->liga (zmierzone:
    Hearts->36, Sturm->45, Lech->202 z feedu Sturm–Hearts / AGF–Lech).

    Zbiór wspólnych utid-ów to ROZGRYWKI DRUŻYNY (bieżąca faza ligi,
    puchary, mundial przy 2+ reprezentantach) — sygnal_transferu nie może
    brać ich za „starą ligę" zawodnika (pomiar 2026-07-22: Apertura vs
    Clausura w Liga MX i CONCACAF Champions Cup wychodziły jako transfery).
    """
    liczniki: dict[int, Counter] = {}
    gracze_utidu: dict[int, dict[int, set[int]]] = {}  # tid -> utid -> pids
    widziani: set[tuple[int, int]] = set()  # (team_id, player_id) raz
    for t in trends:
        if not t.team_id or not t.game_utids:
            continue
        klucz = (t.team_id, t.player_id)
        if klucz in widziani:
            continue  # jeden rynek wystarczy — historia gier ta sama
        widziani.add(klucz)
        liczniki.setdefault(t.team_id, Counter()).update(
            u for u in t.game_utids if u
        )
        slot = gracze_utidu.setdefault(t.team_id, {})
        for u in set(t.game_utids):
            if u:
                slot.setdefault(u, set()).add(t.player_id)
    out: dict[int, tuple[int, set[int]]] = {}
    for tid, c in liczniki.items():
        if not c:
            continue
        wspolne = {
            u for u, pids in gracze_utidu.get(tid, {}).items()
            if len(pids) >= MIN_KOLEGOW_WSPOLNY_UTID
        }
        out[tid] = (c.most_common(1)[0][0], wspolne)
    return out


def sygnal_transferu(
    tr: statshub.StatshubTrend,
    liga_druzyny: int | None,
    utidy_druzyny: set[int] | None,
    teraz: int,
) -> dict | None:
    """Wykryj „nowego w drużynie" z historii jednego zawodnika.

    Dwa warianty:
      * zmiana_ligi — ostatnie mecze w innej lidze niż liga drużyny,
      * gral_przeciw — w ostatnich meczach grał PRZECIW obecnej drużynie
        (transfer wewnątrz ligi; własnej drużyny nie ma się w rywalach).

    „Starą ligą" nie mogą być rozgrywki, w których gra sama drużyna
    (utidy_druzyny) ani mundial — inaczej sezonowa zmiana fazy ligi
    (Apertura/Clausura), puchar klubu albo powrót z MŚ wygląda jak transfer.
    """
    utids = [u for u in tr.game_utids[:OKNO_TRANSFER] if u]
    if len(utids) < MIN_HISTORIA_TRANSFER:
        return None
    ost_ts = max((ts for _, _, ts in _grane(tr)), default=0)
    if not ost_ts or teraz - ost_ts > MAX_DNI_SWIEZOSC * 86400:
        return None  # dawno nie grał — to nie „świeży nabytek w rytmie"
    gral_przeciw = bool(
        tr.team_id
        and tr.team_id in tr.game_opponent_ids[:OKNO_GRAL_PRZECIW]
    )
    if not liga_druzyny:
        return None
    wykluczone = (utidy_druzyny or set()) | {liga_druzyny, UTID_MUNDIAL}
    n_nowa = sum(1 for u in utids if u == liga_druzyny)
    inne = Counter(u for u in utids if u not in wykluczone)
    zmiana_ligi = False
    utid_stara, n_stara = (None, 0)
    if inne:
        utid_stara, n_stara = inne.most_common(1)[0]
        zmiana_ligi = (
            n_nowa <= MAX_MECZE_W_NOWEJ
            and n_stara >= MIN_MECZE_W_STAREJ
            and n_stara >= 2 * max(n_nowa, 1)
        )
    # gral_przeciw wystarcza sam: mecz PRZECIW obecnej drużynie w ostatnich
    # OKNO_GRAL_PRZECIW występach = transfer co najwyżej sprzed kilku kolejek
    # (licznik meczów w lidze nic tu nie mówi — stary klub grał w tej samej)
    if not zmiana_ligi and not gral_przeciw:
        return None
    return {
        "powod": "zmiana_ligi" if zmiana_ligi else "gral_przeciw",
        "stara_liga_utid": utid_stara if zmiana_ligi else None,
        "mecze_stara": n_stara if zmiana_ligi else None,
        "mecze_nowa": n_nowa,
    }


def sygnal_formy(
    tr: statshub.StatshubTrend, drabinka: dict[float, float], teraz: int
) -> dict | None:
    """Seria trafień nad linią Superbetu w ostatnich meczach.

    Linia serii = NAJWYŻSZA kwotowana linia, nad którą zawodnik przeszedł
    w >= MIN_TRAFIEN_FORMA z OKNO_FORMY ostatnich występów, o ile jej kurs
    jest grywalny. Do tego kontrola trendu: średnia/90 okna wyraźnie ponad
    średnią wcześniejszej bazy (inaczej „seria" to po prostu poziom gracza).
    """
    grane = _grane(tr)
    if len(grane) < MIN_GIER_FORMA:
        return None
    okno, baza = grane[:OKNO_FORMY], grane[OKNO_FORMY:]
    if teraz - okno[0][2] > MAX_DNI_SWIEZOSC * 86400:
        return None
    min_okno = sum(m for _, m, _ in okno)
    min_baza = sum(m for _, m, _ in baza)
    if min_okno <= 0 or min_baza <= 0:
        return None
    per90_okno = sum(c for c, _, _ in okno) / min_okno * 90.0
    per90_baza = sum(c for c, _, _ in baza) / min_baza * 90.0
    if per90_baza <= 0 or per90_okno < MIN_BOOST_FORMY * per90_baza:
        return None
    najlepsza = None
    for linia, kurs in sorted(drabinka.items()):
        if kurs < MIN_KURS_FORMY:
            continue
        trafienia = sum(1 for c, _, _ in okno if c > linia)
        if trafienia >= MIN_TRAFIEN_FORMA:
            najlepsza = (linia, kurs, trafienia)
    if najlepsza is None:
        return None
    linia, kurs, trafienia = najlepsza
    return {
        "linia": linia,
        "kurs": kurs,
        "trafienia": trafienia,
        "okno": min(OKNO_FORMY, len(okno)),
        "srednia90_okno": round(per90_okno, 2),
        "srednia90_baza": round(per90_baza, 2),
    }


def _ten_sam_cykl_ligi(a: str, b: str) -> bool:
    """'Liga MX, Apertura' i 'Liga MX, Clausura' to JEDNA liga w dwóch
    fazach pod osobnymi utid-ami — porównujemy część przed przecinkiem."""
    pa = a.split(",")[0].strip().lower()
    pb = b.split(",")[0].strip().lower()
    return bool(pa) and pa == pb


def _klucze_dopasowane(klucze: set[str], nazwa: str) -> set[str]:
    """Wszystkie klucze norm_name z oferty Superbetu pasujące do nazwiska.

    Celowo LIBERALNE (podzbiór tokenów w obie strony, jak
    superbet.znajdz_zawodnika, ale bez wymogu jednoznaczności): tu chodzi
    o WYKLUCZENIE znanych graczy — lepiej pominąć wątpliwego debiutanta,
    niż flagować gwiazdę o podobnym nazwisku."""
    key = superbet.norm_name(nazwa)
    out = {key} if key in klucze else set()
    tokeny = set(key.split())
    if not tokeny:
        return out
    for k in klucze:
        tk = set(k.split())
        if tokeny <= tk or tk <= tokeny:
            out.add(k)
    return out


def debiutanci_meczu(
    sb_odds: dict,
    znane_nazwiska: list[str],
    team_ids: tuple[int, int],
    licznik_wyszukan: list[int],
) -> list[dict]:
    """Zawodnicy kwotowani przez Superbet, nieobecni w feedzie statshub.

    licznik_wyszukan: jednoelementowa lista-mutowalny budżet zapytań
    /api/search współdzielony przez wszystkie mecze cyklu."""
    players = sb_odds.get("players") or {}
    names = sb_odds.get("player_names") or {}
    if not players:
        return []
    klucze = set(players.keys())
    znane: set[str] = set()
    for nazwa in znane_nazwiska:
        znane |= _klucze_dopasowane(klucze, nazwa)
    kandydaci = []
    for key, rynki in players.items():
        if key in znane:
            continue
        n_rynkow = sum(1 for mk, linie in rynki.items() if linie)
        if n_rynkow < MIN_RYNKOW_DEBIUTANTA:
            continue
        kandydaci.append((n_rynkow, key))
    out = []
    for n_rynkow, key in sorted(kandydaci, reverse=True):
        if licznik_wyszukan[0] >= MAX_WYSZUKAN_CYKL:
            break
        surowa = names.get(key) or key
        licznik_wyszukan[0] += 1
        trafienia = statshub.search_players(surowa)
        profil = None
        for t in trafienia[:3]:
            if not t.get("id"):
                continue
            # nazwa z wyszukiwarki musi się zgadzać tokenowo z ofertą
            t_tok = set(superbet.norm_name(str(t.get("name") or "")).split())
            k_tok = set(key.split())
            if not (t_tok and (t_tok <= k_tok or k_tok <= t_tok)):
                continue
            p = statshub.fetch_player_profile(int(t["id"]))
            if p.get("team_id") in team_ids:
                profil = p
                break
        if profil is None:
            continue  # nie potwierdziliśmy przynależności — nie zgadujemy
        out.append({"klucz_sb": key, "nazwa": profil.get("name") or surowa,
                    "profil": profil})
    return out


def _rynki_wpisu(
    drabinki: dict[str, dict[str, float]],
    trendy_mk: dict[str, statshub.StatshubTrend],
    p_model_idx: dict[tuple[str, str, float], float],
    podmiot: str,
    nazwy_pl: dict[str, str],
) -> list[dict]:
    """Sekcja `rynki` wpisu: drabinka kursów + ostatnie występy per rynek."""
    out = []
    for mk, linie in drabinki.items():
        if not linie:
            continue  # rynek bez kursów „powyżej" = pusta drabinka, bez sensu
        drabinka = []
        for linia_s, kurs in sorted(linie.items(), key=lambda kv: float(kv[0])):
            if kurs < MIN_KURS_DRABINKI:
                continue  # 1.01–1.09 to szum siatki, nie zakład
            linia = float(linia_s)
            p = p_model_idx.get((podmiot, mk, linia))
            drabinka.append({
                "linia": linia, "kurs": kurs,
                "p_model": round(p, 3) if p is not None else None,
            })
        if not drabinka:
            continue
        rec: dict = {
            "rynek_kod": mk,
            "rynek": nazwy_pl.get(mk, mk),
            "drabinka": drabinka,
        }
        tr = trendy_mk.get(mk)
        if tr is not None:
            grane = _grane(tr)
            N = OSTATNIE_N
            rec["ostatnie"] = [int(c) for c, _, _ in grane[:N]]
            rec["minuty"] = [int(m) for _, m, _ in grane[:N]]
            rec["rywale"] = [
                str(o) for (o, m) in zip(tr.game_opponents, tr.minutes)
                if m and m >= MIN_MINUT_MECZU
            ][:N]
            lacznie_min = sum(m for _, m, _ in grane)
            if lacznie_min > 0:
                rec["srednia90"] = round(
                    sum(c for c, _, _ in grane) / lacznie_min * 90.0, 2
                )
            # FORMA okno-vs-baza (informacyjnie, na KAŻDYM rynku z historią;
            # sygnal_formy zostaje osobno jako rzadka plakietka "seria")
            if len(grane) >= MIN_GIER_FORMA - 2:
                okno, baza = grane[:OKNO_FORMY], grane[OKNO_FORMY:]
                m_o = sum(m for _, m, _ in okno)
                m_b = sum(m for _, m, _ in baza)
                if m_o > 0 and m_b > 0:
                    rec["forma"] = {
                        "okno90": round(
                            sum(c for c, _, _ in okno) / m_o * 90.0, 2
                        ),
                        "baza90": round(
                            sum(c for c, _, _ in baza) / m_b * 90.0, 2
                        ),
                    }
            # KONTEKST RYWALA: ile rywal średnio ODDAJE na tym rynku i jak
            # wypada na tle ligi (gotowe agregaty z feedu statshub)
            if tr.opponent_average is not None or tr.opponent_rank is not None:
                rec["rywal"] = {
                    "srednia": tr.opponent_average,
                    "rank": tr.opponent_rank,
                    "z": tr.total_ranks,
                    "liga": tr.league_average,
                }
        out.append(rec)
    # rynki z historią przed rynkami „gołej drabinki", w środku po nazwie
    out.sort(key=lambda r: ("ostatnie" not in r, r["rynek_kod"]))
    return out


def _sezony_wpisu(player_sezon: dict | None, pid: int | None) -> list[dict]:
    """Sekcja `sezony` wpisu z cache Supabase `player_sezon` (worker domowy).

    Średnie CAŁYCH sezonów (bieżący + poprzednie) per rynek — /mecz i /90.
    Pusta lista, gdy worker jeszcze nie pobrał gracza."""
    if not player_sezon or not pid:
        return []
    rec = player_sezon.get(str(pid)) or player_sezon.get(int(pid)) or {}
    sez = rec.get("sezony") or []
    return sez[:MAX_SEZONOW_WPISU]


def zbuduj(
    trends: list[statshub.StatshubTrend],
    events_meta: dict[int, dict],
    odds_grid: dict[int, dict[int, dict[str, dict[str, float]]]],
    sb_cache: dict[int, dict],
    model_pokrycie: list[dict],
    players_out: dict[int, dict],
    nazwy_pl: dict[str, str],
    teraz: int,
    player_sezon: dict | None = None,
) -> list[dict]:
    """Złóż wpisy radaru/drabinek ze zbiorów, które cykl i tak ma w pamięci.

    DRABINKI (przebudowa 2026-07-24, decyzja produktowa): wpis dostaje KAŻDY
    kwotowany przez Superbet gracz z historią statshub — drabina linii z
    kursami + pełna analiza (ostatnie występy, forma okno-vs-baza, kontekst
    rywala, średnie sezonowe z cache workera). Detektory transfer/forma/
    debiutant zostają jako PLAKIETKI i priorytet sortowania, nie bramy.

    Zwraca listę do radar.json — posortowaną: transfery, debiutanci, serie
    formy, reszta drabinek; wewnątrz rodzaju po godzinie meczu. Kickoffem,
    który minął, zajmuje się web (tylkoNadchodzace), nie my."""
    konsensus = liga_konsensus(trends)
    trendy_pm: dict[tuple[int, int], dict[str, statshub.StatshubTrend]] = {}
    for t in trends:
        if t.event_id and t.player_id:
            slot = trendy_pm.setdefault((t.event_id, t.player_id), {})
            prev = slot.get(t.market_code)
            if prev is None or len(t.counts) > len(prev.counts):
                slot[t.market_code] = t
    p_model_idx: dict[tuple[str, str, float], float] = {}
    for r in model_pokrycie:
        if r.get("strona") == "powyzej":
            p_model_idx[(r["podmiot"], r["rynek_kod"], float(r["linia"]))] = (
                float(r["p_model"])
            )

    wpisy: list[dict] = []
    for mid, gracze in odds_grid.items():
        meta = events_meta.get(mid)
        if not meta:
            continue
        for pid, drabinki in gracze.items():
            trendy_mk = trendy_pm.get((mid, pid))
            if not trendy_mk:
                continue
            tr_ref = max(trendy_mk.values(), key=lambda t: len(t.counts))
            liga_dr, utidy_dr = konsensus.get(
                tr_ref.team_id or -1, (None, set())
            )
            transfer = sygnal_transferu(tr_ref, liga_dr, utidy_dr, teraz)
            forma = None
            forma_mk = None
            if transfer is None:
                for mk, tr in trendy_mk.items():
                    linie = {
                        float(l): k for l, k in (drabinki.get(mk) or {}).items()
                    }
                    if not linie:
                        continue
                    s = sygnal_formy(tr, linie, teraz)
                    if s and (
                        forma is None
                        or (s["trafienia"], s["kurs"])
                        > (forma["trafienia"], forma["kurs"])
                    ):
                        forma, forma_mk = s, mk
            rynki = _rynki_wpisu(
                drabinki, trendy_mk, p_model_idx,
                tr_ref.player_name, nazwy_pl,
            )
            if not rynki:
                continue  # same puste drabinki (kursy-szum) = nie ma karty
            info = players_out.get(pid) or {}
            wpis = {
                "rodzaj": (
                    "transfer" if transfer else
                    "forma" if forma else "drabinka"
                ),
                "mecz_id": mid, "mecz": meta["label"],
                "kickoff_ts": meta["ts"],
                "podmiot_id": pid,
                "podmiot": tr_ref.player_name,
                "druzyna": tr_ref.team_name,
                "przeciwnik": tr_ref.opponent_name,
                "pozycja": info.get("pozycja") or tr_ref.position or "?",
                "xi": info.get("xi"),
                "rynki": rynki,
            }
            if transfer:
                wpis.update(transfer)
                wpis["_liga_druzyny_utid"] = liga_dr
            elif forma:
                wpis["powod"] = "seria"
                wpis["forma_rynek"] = forma_mk
                wpis["forma"] = forma
            sez = _sezony_wpisu(player_sezon, pid)
            if sez:
                wpis["sezony"] = sez
            wpisy.append(wpis)

    # debiutanci: Superbet kwotuje, statshub milczy
    budzet = [0]
    for mid, meta in events_meta.items():
        sb = sb_cache.get(mid)
        if not sb or not (meta.get("hid") and meta.get("aid")):
            continue
        znane = sorted({
            t.player_name for (m, _), sl in trendy_pm.items() if m == mid
            for t in sl.values()
        })
        for d in debiutanci_meczu(
            sb, znane, (meta["hid"], meta["aid"]), budzet
        ):
            profil = d["profil"]
            druzyna = (
                meta.get("home") if profil.get("team_id") == meta["hid"]
                else meta.get("away")
            )
            przeciwnik = (
                meta.get("away") if profil.get("team_id") == meta["hid"]
                else meta.get("home")
            )
            wiek = None
            if profil.get("birth_ts"):
                wiek = int((teraz - int(profil["birth_ts"])) // (365.25 * 86400))
            sez_deb = _sezony_wpisu(player_sezon, profil.get("id"))
            wpisy.append({
                **({"sezony": sez_deb} if sez_deb else {}),
                "rodzaj": "debiutant",
                "mecz_id": mid, "mecz": meta["label"],
                "kickoff_ts": meta["ts"],
                "podmiot_id": profil.get("id"),
                "podmiot": d["nazwa"],
                "druzyna": druzyna or "",
                "przeciwnik": przeciwnik or "",
                "pozycja": (profil.get("position") or "?")[:1],
                "xi": None,
                "powod": "brak_historii",
                "profil": {
                    "wzrost": profil.get("height"),
                    "wiek": wiek,
                    "kraj": profil.get("country"),
                    "noga": profil.get("foot"),
                },
                "rynki": _rynki_wpisu(
                    {
                        mk: {
                            str(l): v["over"]
                            for l, v in linie.items() if v.get("over")
                        }
                        for mk, linie in (
                            (sb.get("players") or {}).get(d["klucz_sb"]) or {}
                        ).items()
                    },
                    {}, {}, d["nazwa"], nazwy_pl,
                ),
            })

    # etykiety starych lig (drobny koszt: kilka utid-ów z cache w statshub)
    # + siatka bezpieczeństwa na fazy jednej ligi pod różnymi utid-ami:
    # „Liga MX, Apertura" vs „Liga MX, Clausura" to nie transfer
    przefiltrowane = []
    for w in wpisy:
        liga_dr = w.pop("_liga_druzyny_utid", None)
        utid = w.get("stara_liga_utid")
        if utid:
            nazwa_starej = statshub.fetch_tournament_name(int(utid)) or None
            w["stara_liga"] = nazwa_starej
            if nazwa_starej and liga_dr:
                nazwa_nowej = statshub.fetch_tournament_name(int(liga_dr))
                if nazwa_nowej and _ten_sam_cykl_ligi(
                    nazwa_starej, nazwa_nowej
                ):
                    continue
        przefiltrowane.append(w)
    wpisy = przefiltrowane

    kolejnosc = {"transfer": 0, "debiutant": 1, "forma": 2, "drabinka": 3}
    wpisy.sort(key=lambda w: (kolejnosc[w["rodzaj"]], w["kickoff_ts"]))
    wpisy = wpisy[:MAX_WPISOW]
    for i, w in enumerate(wpisy, start=1):
        w["id"] = i
    return wpisy

