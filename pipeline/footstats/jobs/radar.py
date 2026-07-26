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

import math
from collections import Counter

import numpy as np

from ..model import context as context_mod
from ..model import counts as counts_mod
from ..model import kontekst_drabinki as kd
from ..model import tempo as tempo_mod
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
MAX_WYSZUKAN_CYKL = 90      # budżet zapytań /api/search na cykl (statshub to
                            # otwarte API bez limitów — próg jest grzeczności,
                            # nie technicznym wymogiem). Mecze iterowane od
                            # NAJBLIŻSZEGO kickoffu, najpierw te bez trendów.
MAX_DEBIUTANTOW_MECZU = 10  # ilu kandydatów IDENTYFIKUJEMY per mecz. Sufit
                            # kart trzyma round-robin, więc tu chodzi o
                            # szerokość lejka: przy 3 braliśmy pierwszych wg
                            # liczby rynków (rotacyjnych), a dobrzy gracze —
                            # np. Imaz z 2,8 strzału śr. — nie byli nawet
                            # sprawdzani (pomiar 2026-07-25)
MAX_RYNKOW_BEZ_HISTORII = 4  # karta bez historii to sama drabinka kursów —
                             # 9 rynków × kilka szczebli to ściana, nie analiza
# rynki pokazywane na kartach bez historii, w kolejności ważności
RYNKI_PODSTAWOWE = ("shots", "sot", "fouls_committed", "fouls_won",
                    "shots_outside_box", "offsides", "tackles")
MAX_WPISOW = 30             # dzienny TOP kart — ranking porządkuje resztę
                            # (decyzja usera 2026-07-26: więcej materiału, ale
                            # z jawnymi klasami jakości zamiast płaskiej listy)
MAX_WPISOW_MECZ = 2         # sufit kart na mecz (bez gwarancji slotu!)
MAX_SHOTMAP_CYKL = 160      # budżet zapytań o shotmapy historyczne na cykl
OSTATNIE_N = 10             # ile ostatnich występów pokazuje karta rynku
MAX_SEZONOW_WPISU = 3       # sekcja "sezony" na karcie (bieżący + poprzednie)
# przycinanie drabinki: nikt nie gra linii 8+ @23.00 z ~0% szans — szum
MAX_SZCZEBLI = 5            # tyle linii max na rynek
MIN_P_SZCZEBLA = 0.03       # od 3. szczebla w górę: p_model < 3% ucina resztę
MAX_KURS_SZCZEBLA = 12.0    # ...podobnie kurs powyżej tego progu
# pierwszy szczebel drabinki od 1.65 (decyzja usera 2026-07-25): linie po
# 1.2-1.5 to pewniaki bez value — drabinka ma zaczynać się od grywalnej ceny
MIN_KURS_PIERWSZEGO = 1.65
# --- TWARDE BRAMY JAKOŚCI (decyzja usera 2026-07-25: „tylko najlepsze
# drabinki, nie randomowe"). Sygnał (transfer/forma/debiutant) NIE jest już
# przepustką — zostaje plakietką, ale karta musi obronić się liczbami. ---
MIN_KURS_SCORE = 1.65       # linia liczy się dopiero od grywalnej ceny
MIN_PROBA_SCORE = 8         # min. występów w próbie (było 5 — za krótkie
                            # serie udawały pewniaki: 3/5 = "60%")
# Surowe pokrycie linii. ZEJŚCIE 0.6 -> 0.5 (decyzja usera 2026-07-26):
# próg 60% pochodził z czasów, gdy karta nie miała realnego
# prawdopodobieństwa i pokrycie musiało samo udawać jakość. Odkąd bramą jest
# przewaga nad kursem (MIN_EDGE_KARTY liczone z p_final), 60% wycinało akurat
# typy najbardziej wartościowe: „5/10 przy kursie 3,00" to 50% szansy wobec
# 33% w cenie. Pomiar cyklu 2026-07-26: 236 z ~346 kandydatów padało na tym
# progu, a na braku przewagi tylko 4 — czyli lista była krótka nie dlatego,
# że typy są słabe, tylko dlatego, że bramka pytała o złą rzecz.
PROG_POKRYCIA_KARTY = 0.5
MIN_MINUT_KARTY = 62        # zmiennik (52-55 min śr.) to ryzyko, nie typ
MIN_EDGE_KARTY = 0.03       # przewaga po korekcie próby, w pkt proc.
# poziom ufności korekty próby: 7/10 -> ~57% zamiast naiwnych 70%
WILSON_K = 0.674            # ~75% jednostronnie

# --- KOREKTA KONTEKSTOWA (przebudowa 2026-07-26) ---
# Pokrycie linii mówi, co zawodnik robił PRZECIW KOMU INNEMU. Żeby karta
# odpowiadała na „gra z najlepszą defensywą, czemu miałby oddać 2 strzały?",
# liczymy DWIE prawdopodobieństwa z tego samego rozkładu NB (model/counts.py):
#
#   p_ref — historia płasko (bez wygaszania), minuty jak w próbie, zero kontekstu
#   p_ctx — historia wygaszana w czasie (forma), minuty PROGNOZOWANE, pełny
#           kontekst meczu (rywal, sędzia, scenariusz, dom, sezony)
#
# Ich iloraz to czysta korekta: wszystko, co wspólne (poziom gracza, prior,
# rozrzut), skraca się i zostaje tylko to, czym NADCHODZĄCY mecz różni się od
# przeciętnego meczu z próby. Tym ilorazem mnożymy pokrycie Wilsona — baza
# zostaje empiryczna i zgodna z tym, co karta pokazuje („trafione 8/10").
RADAR_TAU_DNI = 60.0        # wygaszanie historii w p_ctx = czynnik formy
PSEUDO_MECZE_PRIOR = 3.0    # słaby prior z własnej średniej: dodaje rozrzut
                            # przy krótkiej historii, nie przesuwa poziomu
KOREKTA_WIDELKI = (0.55, 1.60)   # kontekst koryguje, nie rządzi
P_FINAL_WIDELKI = (0.02, 0.97)
CAP_SEZONU = (0.85, 1.15)   # ile może ruszyć średnia z całych sezonów
# klasy jakości po przewadze nad kursem (pkt proc.). Progi są ZAŁOŻENIEM do
# skalibrowania z rozliczeń drabinek — dopiero własny strumień skuteczności
# powie, czy „top" faktycznie trafia lepiej niż „solidny".
PROG_KLASY = ((0.10, "top"), (0.06, "mocny"))


def _wilson_low(traf: int, z: int, k: float = WILSON_K) -> float:
    """Dolna granica ufności odsetka trafień — kara za krótką próbę.

    Bez tego 5/5 (100%) bije 8/10 (80%), choć druga próba jest dwa razy
    pewniejsza. Wzór Wilsona: im mniej meczów, tym mocniej ściąga w dół.
    """
    if z <= 0:
        return 0.0
    p = traf / z
    mian = 1.0 + k * k / z
    licz = p + k * k / (2 * z) - k * math.sqrt(
        (p * (1.0 - p) + k * k / (4 * z)) / z
    )
    return max(0.0, licz / mian)


def _mnoznik_sezonu(
    sezony: list[dict], rynek_kod: str, okno90: float | None,
) -> tuple[float, dict]:
    """Średnie z CAŁYCH sezonów vs poziom z ostatnich meczów.

    Sezonowa próba (30+ meczów) jest znacznie mocniejsza niż okno 10 spotkań,
    więc kiedy okno mówi „2,4 strzału", a dwa sezony „1,5", to okno jest
    najpewniej szczytem formy, nie nowym poziomem. Mnożnik działa na lambdę
    (czyli tylko w p_ctx), więc nie skraca się w ilorazie korekty.
    """
    probki = [
        (s["na90"][rynek_kod], float(s.get("minuty") or 0))
        for s in (sezony or [])
        if (s.get("na90") or {}).get(rynek_kod) is not None
        and (s.get("mecze") or 0) >= 8
    ]
    minuty = sum(m for _v, m in probki)
    if not probki or minuty <= 0 or not okno90 or okno90 <= 0:
        return 1.0, {}
    sezon90 = sum(v * m for v, m in probki) / minuty
    m = float(np.clip(sezon90 / okno90, *CAP_SEZONU))
    return m, {
        "sezon90": round(sezon90, 2), "okno90": round(okno90, 2),
        "mnoznik": round(m, 3),
    }


def _posteriory(
    grane: list[tuple[float, float, int]], teraz: int,
) -> tuple[object, object, float] | None:
    """(posterior wygaszany, posterior płaski, średnie minuty próby).

    Prior jest celowo słaby i wzięty z własnej średniej zawodnika — jego rolą
    jest dorzucić naddyspersję przy krótkiej historii (NB zamiast Poissona),
    a nie przesunąć poziom. Poziom niosą obserwacje.
    """
    if not grane:
        return None
    c = np.array([x[0] for x in grane], dtype=float)
    m = np.array([x[1] for x in grane], dtype=float)
    dni = np.array(
        [max(0.0, (teraz - x[2]) / 86400.0) for x in grane], dtype=float
    )
    minuty_sum = float(m.sum())
    if minuty_sum <= 0:
        return None
    sr90 = float(c.sum()) / minuty_sum * 90.0
    prior = counts_mod.GroupPrior(
        mean_per90=max(sr90, 0.05), pseudo_matches=PSEUDO_MECZE_PRIOR
    )
    post_swiezy = counts_mod.fit_posterior(
        c, m, dni, prior, tau_days=RADAR_TAU_DNI
    )
    # płaski = te same dane bez wygaszania (tau tak duże, że wagi ~1)
    post_plaski = counts_mod.fit_posterior(
        c, m, np.zeros_like(dni), prior, tau_days=RADAR_TAU_DNI
    )
    return post_swiezy, post_plaski, minuty_sum / len(grane)
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
        if len(out) >= MAX_DEBIUTANTOW_MECZU:
            break  # komplet kart tego meczu — nie pal budżetu dalej
        surowa = (names.get(key) or key).strip()
        if "," in surowa:
            # Superbet formatuje "Nazwisko, Imię" — wyszukiwarka statshub
            # tego nie rozumie (zmierzone 2026-07-25: "Sylla, Youssuf"
            # -> 0 trafień; "Youssuf Sylla" -> trafia)
            czesci = [c.strip() for c in surowa.split(",") if c.strip()]
            surowa = " ".join(reversed(czesci))
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


def _korekta_linii(
    posty: tuple, minuty_proj: float, f_ctx: float, linia: float,
) -> tuple[float, float, float] | None:
    """(korekta, p_ctx, p_ref) dla jednej linii — patrz KOREKTA_WIDELKI."""
    post_swiezy, post_plaski, minuty_bazowe = posty
    p_ctx = counts_mod.predict_match(
        post_swiezy, minuty_proj, f_ctx
    ).p_over(linia)
    p_ref = counts_mod.predict_match(
        post_plaski, minuty_bazowe, 1.0
    ).p_over(linia)
    if p_ref <= 1e-6:
        return None
    return float(np.clip(p_ctx / p_ref, *KOREKTA_WIDELKI)), p_ctx, p_ref


def _rynki_wpisu(
    drabinki: dict[str, dict[str, float]],
    trendy_mk: dict[str, statshub.StatshubTrend],
    p_model_idx: dict[tuple[str, str, float], float],
    podmiot: str,
    nazwy_pl: dict[str, str],
    *,
    sedzia: dict | None = None,
    tempo: dict | None = None,
    is_home: bool | None = None,
    koncesje: kd.KoncesjeDruzyn | None = None,
    koncesje_nazw=None,
    nazwa_rywala: str | None = None,
    nazwa_druzyny: str | None = None,
    opp_id: int | None = None,
    minuty_proj: float | None = None,
    sezony: list[dict] | None = None,
    teraz: int = 0,
) -> list[dict]:
    """Sekcja `rynki` wpisu: przycięta drabinka kursów + pokrycie linii
    w ostatnich występach + forma i PEŁNY kontekst meczu per rynek.

    Każdy szczebel dostaje `p_final` — pokrycie Wilsona przemnożone przez
    korektę kontekstową (rywal na tym rynku, sędzia przy faulach, scenariusz
    meczu, dom/wyjazd, średnie sezonowe, forma i prognoza minut). To ta liczba,
    nie surowe „8/10", decyduje o wyborze i kolejności kart."""
    out = []
    for mk, linie in drabinki.items():
        if not linie:
            continue  # rynek bez kursów „powyżej" = pusta drabinka, bez sensu
        tr = trendy_mk.get(mk)
        grane = _grane(tr) if tr is not None else []
        okno = grane[:OSTATNIE_N]
        # --- KONTEKST MECZU dla tego rynku (mnożniki lambdy) ---
        posty = _posteriory(grane, teraz) if grane else None
        lacznie_min = sum(m for _c, m, _t in grane)
        srednia90 = (
            sum(c for c, _m, _t in grane) / lacznie_min * 90.0
            if lacznie_min > 0 else None
        )
        f_rywal, opis_rywal = kd.mnoznik_rywala(
            mk, tr, koncesje, opp_id,
            (tr.position if tr is not None else None), teraz,
            koncesje_nazw=koncesje_nazw,
            nazwa_rywala=nazwa_rywala,
            nazwa_druzyny=nazwa_druzyny,
        )
        f_sedzia, opis_sedzia = kd.mnoznik_sedziego(mk, sedzia)
        f_scen, opis_scen = kd.mnoznik_scenariusza(mk, tempo, is_home)
        f_dom, opis_dom = kd.mnoznik_domu(mk, is_home)
        f_sezon, opis_sezon = _mnoznik_sezonu(sezony or [], mk, srednia90)
        f_ctx = context_mod.cap(
            f_rywal * f_sedzia * f_scen * f_dom * f_sezon,
            context_mod.CAP_COMBINED,
        )
        drabinka = []
        for linia_s, kurs in sorted(linie.items(), key=lambda kv: float(kv[0])):
            if not drabinka and kurs < MIN_KURS_PIERWSZEGO:
                continue  # drabinka startuje od pierwszej grywalnej ceny
            if len(drabinka) >= MAX_SZCZEBLI:
                break
            linia = float(linia_s)
            p = p_model_idx.get((podmiot, mk, linia))
            # od 3. szczebla: linie z ~0% szans / kosmicznym kursem = szum;
            # wyższe linie będą tylko gorsze, więc ucinamy resztę drabinki
            if len(drabinka) >= 2 and (
                (p is not None and p < MIN_P_SZCZEBLA)
                or kurs > MAX_KURS_SZCZEBLA
            ):
                break
            szczebel = {
                "linia": linia, "kurs": kurs,
                "p_model": round(p, 3) if p is not None else None,
            }
            if okno:
                # POKRYCIE: ile z ostatnich występów przebiło tę linię —
                # rdzeń analizy tipsterskiej ("2+ trafione w 8/10")
                traf = sum(1 for c, _, _ in okno if c > linia)
                szczebel["pokrycie"] = {"traf": traf, "z": len(okno)}
                # SZANSA PO KONTEKŚCIE: pokrycie Wilsona × korekta meczowa.
                # Bez prognozy minut nie ma czego rzutować na mecz.
                kor = (
                    _korekta_linii(posty, minuty_proj, f_ctx, linia)
                    if posty and minuty_proj else None
                )
                if kor is not None:
                    p_baz = _wilson_low(traf, len(okno))
                    szczebel["p_bazowe"] = round(p_baz, 3)
                    szczebel["korekta"] = round(kor[0], 3)
                    szczebel["p_final"] = round(
                        float(np.clip(p_baz * kor[0], *P_FINAL_WIDELKI)), 3
                    )
            drabinka.append(szczebel)
        if not drabinka:
            continue
        rec: dict = {
            "rynek_kod": mk,
            "rynek": nazwy_pl.get(mk, mk),
            "drabinka": drabinka,
            # WODOSPAD KONTEKSTU — karta ma powiedzieć wprost, czemu ścinamy
            # albo podbijamy pokrycie. Puste sekcje (np. sędzia bez obsady)
            # zostają z etykietą źródła, żeby UI mogło napisać „nie wiemy".
            "kontekst": {
                "rywal": opis_rywal,
                "sedzia": opis_sedzia,
                "scenariusz": opis_scen,
                "dom": opis_dom,
                "sezony": opis_sezon,
                "lacznie": round(f_ctx, 3),
            },
        }
        if tr is not None:
            N = OSTATNIE_N
            rec["ostatnie"] = [int(c) for c, _, _ in grane[:N]]
            rec["minuty"] = [int(m) for _, m, _ in grane[:N]]
            rec["rywale"] = [
                str(o) for (o, m) in zip(tr.game_opponents, tr.minutes)
                if m and m >= MIN_MINUT_MECZU
            ][:N]
            if srednia90 is not None:
                rec["srednia90"] = round(srednia90, 2)
            # FORMA okno-vs-baza (informacyjnie, na KAŻDYM rynku z historią;
            # sygnal_formy zostaje osobno jako rzadka plakietka "seria")
            if len(grane) >= MIN_GIER_FORMA - 2:
                okno_f, baza = grane[:OKNO_FORMY], grane[OKNO_FORMY:]
                m_o = sum(m for _, m, _ in okno_f)
                m_b = sum(m for _, m, _ in baza)
                if m_o > 0 and m_b > 0:
                    rec["forma"] = {
                        "okno90": round(
                            sum(c for c, _, _ in okno_f) / m_o * 90.0, 2
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
    # rynki z historią przed rynkami „gołej drabinki"; gołe — w kolejności
    # ważności rynku (strzały przed spalonymi), nie alfabetycznie
    kolejnosc_rynku = {mk: i for i, mk in enumerate(RYNKI_PODSTAWOWE)}
    out.sort(key=lambda r: (
        "ostatnie" not in r,
        kolejnosc_rynku.get(r["rynek_kod"], len(RYNKI_PODSTAWOWE)),
        r["rynek_kod"],
    ))
    if not any("ostatnie" in r for r in out):
        out = out[:MAX_RYNKOW_BEZ_HISTORII]  # sama drabinka = bez ściany
    return out


def _oceń_karte(w: dict, powody: Counter | None = None) -> tuple[float, dict | None]:
    """Ocena karty: (score, najlepszy_szczebel) albo (0.0, None) gdy odpada.

    Score = REALNA PRZEWAGA nad kursem: `p_final − 1/kurs`, gdzie p_final to
    pokrycie Wilsona po korekcie kontekstowej (rywal na tym rynku, sędzia przy
    faulach, scenariusz meczu, forma, prognoza minut, średnie sezonowe).
    Mnożników „na wierzchu" już nie ma — cały kontekst siedzi w p_final, więc
    score jest w tych samych jednostkach co rzeczywistość i da się go rozliczyć.

    Dodatkowo p_model (pełny silnik, gdy policzył tę linię) działa jako
    STRZYŻENIE, nigdy jako podbicie: gdy model widzi mniej niż my, schodzimy
    w połowie drogi do niego. Dwie niezależne estymaty w rozjeździe to powód
    do ostrożności, a nie do wybierania wygodniejszej.

    Karta bez ani jednej linii przechodzącej bramy NIE powstaje: sygnały same
    z siebie nie wystarczają (koniec z „Lewandowski, bo transfer").
    """
    if (w.get("minuty_sr6") or 0) < MIN_MINUT_KARTY:
        if powody is not None:
            powody["za_malo_minut"] += 1
        return 0.0, None
    best_score, best_s = 0.0, None
    lokalne: Counter = Counter()
    for r in w.get("rynki", []):
        for s in r.get("drabinka", []):
            p = s.get("pokrycie")
            if not p or p["z"] < MIN_PROBA_SCORE:
                lokalne["krotka_proba"] += 1
                continue
            if s["kurs"] < MIN_KURS_SCORE:
                lokalne["kurs_ponizej_progu"] += 1
                continue
            if p["traf"] / p["z"] < PROG_POKRYCIA_KARTY:
                lokalne["slabe_pokrycie"] += 1
                continue
            p_final = s.get("p_final")
            if p_final is None:
                lokalne["brak_korekty"] += 1
                continue  # bez korekty kontekstowej nie oceniamy karty
            p_mod = s.get("p_model")
            if p_mod is not None and p_mod < p_final:
                p_final = round((p_final + float(p_mod)) / 2.0, 3)
                s["p_final"] = p_final
                s["strzyzenie_modelu"] = True
            edge = p_final - 1.0 / s["kurs"]
            if edge < MIN_EDGE_KARTY:
                lokalne["brak_przewagi"] += 1
                continue
            if edge > best_score:
                best_score, best_s = edge, {
                    "rynek_kod": r["rynek_kod"], "rynek": r.get("rynek"),
                    "linia": s["linia"], "kurs": s["kurs"],
                    "traf": p["traf"], "z": p["z"],
                    "edge": round(edge, 3),
                    "p_final": p_final,
                    "p_bazowe": s.get("p_bazowe"),
                    "korekta": s.get("korekta"),
                }
    if powody is not None and best_s is None:
        # najczęstszy powód odpadnięcia tej karty — bez tego nie wiadomo,
        # czy pusta lista to słaby dzień, czy zbyt ostry próg
        powody[
            lokalne.most_common(1)[0][0] if lokalne else "brak_drabinki"
        ] += 1
    return best_score, best_s


def _klasa_karty(edge: float, miejsce: int = 1, ile: int = 1) -> str:
    """Klasa jakości karty: próg bezwzględny ORAZ miejsce w stawce dnia.

    Sam próg bezwzględny nie wystarcza w obie strony: w dobry dzień „top"
    dostawałoby 25 kart naraz (etykieta przestaje cokolwiek znaczyć), a w słaby
    — żadna, mimo że któraś jest najlepsza z dostępnych. Dlatego „top" wymaga
    przewagi >= PROG_KLASY[0] I bycia w czubie stawki (max z 3 kart i górnego
    kwintyla). Progi bezwzględne są ZAŁOŻENIEM do skalibrowania z rozliczeń
    strumienia drabinek — patrz rozliczanie.skutecznosc_strumieni.
    """
    prog_top, nazwa_top = PROG_KLASY[0]
    if edge >= prog_top and miejsce <= max(3, round(0.2 * max(ile, 1))):
        return nazwa_top
    for prog, nazwa in PROG_KLASY[1:]:
        if edge >= prog:
            return nazwa
    return "solidny"


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
    sedzia_by_mid: dict[int, dict] | None = None,
    koncesje_tab=None,
) -> list[dict]:
    """Złóż wpisy radaru/drabinek ze zbiorów, które cykl i tak ma w pamięci.

    DRABINKI (przebudowa 2026-07-24, decyzja produktowa): wpis dostaje KAŻDY
    kwotowany przez Superbet gracz z historią statshub — drabina linii z
    kursami + pełna analiza (ostatnie występy, forma okno-vs-baza, kontekst
    rywala, średnie sezonowe z cache workera). Detektory transfer/forma/
    debiutant zostają jako PLAKIETKI i priorytet sortowania, nie bramy.

    KONTEKST MECZU (2026-07-26): każdy szczebel dostaje `p_final` — pokrycie
    Wilsona skorygowane o to, co czeka zawodnika W TYM meczu (koncesje rywala
    na tym konkretnym rynku, sędzia przy faulach, scenariusz meczu z kursów
    1X2, forma, prognoza minut, średnie sezonowe). Selekcja i kolejność kart
    idą po realnej przewadze nad kursem, nie po surowym „trafione 8/10".

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
    # KONCESJE RYWALI z historii całego feedu (fallback tam, gdzie statshub
    # nie podaje gotowych agregatów — cała ścieżka `performance`, m.in.
    # Ekstraklasa, oraz rynki spoza piątki rdzeniowej)
    koncesje = kd.zbuduj_koncesje(trendy_pm, teraz)
    # TEMPO MECZU z kursów 1X2/total Superbetu (scenariusz: otwarty mecz,
    # faworyt/underdog) — liczone raz na mecz, nie na kartę
    tempo_by_mid: dict[int, dict | None] = {}

    def _tempo(mid: int) -> dict | None:
        if mid not in tempo_by_mid:
            try:
                tempo_by_mid[mid] = tempo_mod.tempo_from_match_odds(
                    (sb_cache.get(mid) or {}).get("match")
                )
            except Exception:
                tempo_by_mid[mid] = None
        return tempo_by_mid[mid]
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
            info = players_out.get(pid) or {}
            # średnia minut z ostatnich 6 występów — "gra pełne mecze"
            # vs "wchodzi z ławki" to pierwsze pytanie każdej analizy.
            # Liczona PRZED drabinką, bo jest prognozą ekspozycji w p_final.
            gr_ref = _grane(tr_ref)[:6]
            minuty_sr6 = (
                round(sum(m for _, m, _ in gr_ref) / len(gr_ref))
                if gr_ref else None
            )
            sez = _sezony_wpisu(player_sezon, pid)
            # dom/wyjazd z meta meczu (tr.is_home bywa puste na ścieżce
            # performance, a meta ma id gospodarza zawsze)
            is_home = (
                bool(tr_ref.team_id == meta.get("hid"))
                if meta.get("hid") and tr_ref.team_id else None
            )
            opp_id = (
                (meta.get("aid") if is_home else meta.get("hid"))
                if is_home is not None else (tr_ref.opponent_id or None)
            )
            rynki = _rynki_wpisu(
                drabinki, trendy_mk, p_model_idx,
                tr_ref.player_name, nazwy_pl,
                sedzia=(sedzia_by_mid or {}).get(mid),
                tempo=_tempo(mid),
                is_home=is_home,
                koncesje=koncesje,
                koncesje_nazw=koncesje_tab,
                nazwa_rywala=tr_ref.opponent_name or meta.get(
                    "away" if is_home else "home"
                ),
                nazwa_druzyny=tr_ref.team_name,
                opp_id=opp_id,
                minuty_proj=minuty_sr6,
                sezony=sez,
                teraz=teraz,
            )
            if not rynki:
                continue  # same puste drabinki (kursy-szum) = nie ma karty
            wpis = {
                "minuty_sr6": minuty_sr6,
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
            if sez:
                wpis["sezony"] = sez
            wpisy.append(wpis)

    # debiutanci: Superbet kwotuje, statshub milczy. Priorytet budżetu
    # wyszukiwań: NAJPIERW mecze BEZ ŻADNYCH trendów (ligi poza feedem
    # propsów UK — Ekstraklasa! — żyją wyłącznie tą ścieżką), potem reszta;
    # wewnątrz po kickoffie. Bez tego budżet przepalał się na ławkach
    # meczów, które i tak mają karty z trendów (bug zmierzony 2026-07-25:
    # Superbet kwotował 41 graczy Lecha, kart nie było).
    budzet = [0]
    # shotmapy historycznych meczów — WSPÓLNE dla graczy tej samej drużyny
    # (ta sama historia), więc koszt ~10 zapytań na drużynę, nie na gracza
    sm_cache_cykl: dict[int, list] = {}
    budzet_shotmap = [MAX_SHOTMAP_CYKL]
    mids_z_trendami = {m for (m, _p) in trendy_pm}
    for mid, meta in sorted(
        events_meta.items(),
        key=lambda kv: (kv[0] in mids_z_trendami, kv[1].get("ts") or 0),
    ):
        if (meta.get("ts") or 0) <= teraz:
            continue  # mecz już trwa/był — szkoda budżetu
        sb = sb_cache.get(mid)
        if not sb or not (meta.get("hid") and meta.get("aid")):
            continue
        znane = sorted({
            t.player_name for (m, _), sl in trendy_pm.items() if m == mid
            for t in sl.values()
        })
        for d in debiutanci_meczu(
            sb, znane, (meta["hid"], meta["aid"]), budzet
        )[:MAX_DEBIUTANTOW_MECZU]:
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
            # UCZCIWA ETYKIETA (fix 2026-07-25): gdy mecz nie ma ŻADNYCH
            # trendów, to nie „debiutant bez historii", tylko CAŁA liga jest
            # poza feedem propsów UK (Ekstraklasa). Nazywanie Luisa Palmy
            # czy Nika Prelca „debiutantem, którego rynek wycenia w ciemno"
            # byłoby po prostu nieprawdą — historia istnieje, my jej tu
            # nie mamy. Średnie sezonowe dociąga worker (Sofascore).
            bez_feedu = mid not in mids_z_trendami
            # HISTORIA SPOZA FEEDU PROPSÓW (odkrycie 2026-07-25):
            # /player/{id}/performance daje 10 ostatnich meczów ze
            # statystykami dla KAŻDEJ ligi — Ekstraklasa dostaje pełną
            # drabinkę z pokryciem linii zamiast gołych kursów.
            trendy_perf: dict[str, statshub.StatshubTrend] = {}
            if profil.get("id"):
                try:
                    trendy_perf = statshub.trendy_z_performance(
                        int(profil["id"]), d["nazwa"], profil.get("team_id"),
                        statshub.fetch_player_performance(int(profil["id"])),
                        sm_cache=sm_cache_cykl, budzet=budzet_shotmap,
                    )
                except Exception:
                    trendy_perf = {}
            # prognoza minut z historii performance (ta sama rola co
            # minuty_sr6 na ścieżce trendów: ekspozycja w p_final)
            gr_deb = (
                _grane(max(trendy_perf.values(), key=lambda t: len(t.counts)))[:6]
                if trendy_perf else []
            )
            minuty_sr6_deb = (
                round(sum(m for _c, m, _t in gr_deb) / len(gr_deb))
                if gr_deb else None
            )
            is_home_deb = (
                bool(profil.get("team_id") == meta["hid"])
                if profil.get("team_id") else None
            )
            opp_id_deb = (
                (meta["aid"] if is_home_deb else meta["hid"])
                if is_home_deb is not None else None
            )
            wpisy.append({
                **({"sezony": sez_deb} if sez_deb else {}),
                # z historią z performance to pełnoprawna drabinka, nie
                # „same kursy" — etykieta idzie za realną zawartością karty
                "rodzaj": (
                    "drabinka" if (bez_feedu and trendy_perf)
                    else "bez_feedu" if bez_feedu else "debiutant"
                ),
                "mecz_id": mid, "mecz": meta["label"],
                "kickoff_ts": meta["ts"],
                "podmiot_id": profil.get("id"),
                "podmiot": d["nazwa"],
                "druzyna": druzyna or "",
                "przeciwnik": przeciwnik or "",
                "pozycja": (profil.get("position") or "?")[:1],
                "xi": None,
                **({"powod": "poza_feedem"} if bez_feedu and not trendy_perf
                   else {"powod": "brak_historii"} if not bez_feedu else {}),
                "minuty_sr6": minuty_sr6_deb,
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
                    trendy_perf, {}, d["nazwa"], nazwy_pl,
                    sedzia=(sedzia_by_mid or {}).get(mid),
                    tempo=_tempo(mid),
                    is_home=is_home_deb,
                    koncesje=koncesje,
                    koncesje_nazw=koncesje_tab,
                    nazwa_rywala=przeciwnik,
                    nazwa_druzyny=druzyna,
                    opp_id=opp_id_deb,
                    minuty_proj=minuty_sr6_deb,
                    sezony=sez_deb,
                    teraz=teraz,
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

    # SORTOWANIE (przebudowa 2026-07-24): po MECZACH chronologicznie,
    # w meczu po jakości (score) — sygnały wyróżnia plakietka na karcie,
    # nie kolejność listy (stary radar sortował rodzajami, co przy wielu
    # kartach rozrzucało jeden mecz po całej liście). Sufit per mecz
    # trzyma eksplozję: każdy kwotowany gracz = kandydat na kartę.
    # TWARDE BRAMY: karta bez ani jednej linii z realną przewagą odpada,
    # niezależnie od rodzaju. Sygnał to plakietka, nie przepustka.
    ocenione = []
    powody_odpadniecia: Counter = Counter()
    for w in wpisy:
        score, hero = _oceń_karte(w, powody_odpadniecia)
        if hero is None:
            continue
        w["_score"] = score
        w["hero"] = hero    # najlepsza linia karty — front pokazuje ją w nagłówku
        ocenione.append(w)

    # SELEKCJA: globalny TOP po jakości, max MAX_WPISOW_MECZ na mecz i BEZ
    # gwarantowanego slotu — słaby mecz nie dostaje nic (decyzja usera:
    # „tylko najlepsze, nie randomowe"). Wcześniejszy round-robin dawał
    # kartę każdemu meczowi, także takiemu z ujemną przewagą.
    if powody_odpadniecia:
        print("Drabinki — kandydaci odrzuceni: " + ", ".join(
            f"{k}={v}" for k, v in powody_odpadniecia.most_common()
        ) + f" (przeszło: {len(ocenione)})")
    per_mecz_n: dict[int, int] = {}
    wybrane: list[dict] = []
    for w in sorted(ocenione, key=lambda w: -w["_score"]):
        if len(wybrane) >= MAX_WPISOW:
            break
        if per_mecz_n.get(w["mecz_id"], 0) >= MAX_WPISOW_MECZ:
            continue
        per_mecz_n[w["mecz_id"]] = per_mecz_n.get(w["mecz_id"], 0) + 1
        wybrane.append(w)
    wpisy = wybrane
    # OCENA na karcie: miejsce w rankingu dnia + klasa jakości. Front sortuje
    # i oznacza WYŁĄCZNIE tym — nie ma drugiej definicji „najlepszego typu"
    # po stronie web (rozjazd backend/front byłby nie do wytłumaczenia userowi).
    for miejsce, w in enumerate(
        sorted(wpisy, key=lambda w: -w["_score"]), start=1
    ):
        hero = w.get("hero") or {}
        w["ocena"] = {
            "miejsce": miejsce,
            "klasa": _klasa_karty(w["_score"], miejsce, len(wpisy)),
            "edge": round(w["_score"], 3),
            "p_final": hero.get("p_final"),
            "p_bazowe": hero.get("p_bazowe"),
            "korekta": hero.get("korekta"),
            # wodospad z rynku, który wygrał kartę — front pokazuje go
            # w rozwinięciu jako „dlaczego"
            "kontekst": next(
                (r.get("kontekst") for r in w.get("rynki", [])
                 if r.get("rynek_kod") == hero.get("rynek_kod")),
                None,
            ),
        }
    wpisy.sort(key=lambda w: (w["kickoff_ts"], w["mecz_id"], -w["_score"]))
    for i, w in enumerate(wpisy, start=1):
        w.pop("_score", None)
        w["id"] = i
    return wpisy

