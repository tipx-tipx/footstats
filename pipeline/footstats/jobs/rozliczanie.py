"""Automatyczne rozliczanie publikowanych typów + baza pod uczenie modelu.

Przepływ (wywoływane na końcu każdego cyklu):
  1. każdy publikowany typ (okazja i sugestia) trafia do logu `typy_log`
     w Supabase — z ZAMROŻONYM p_model i kursem z chwili pierwszej publikacji,
  2. po zakończonym meczu (kickoff + ~105 min) cykl szuka faktycznej wartości
     — wszystko liczone w REGULARNYM czasie gry (bez dogrywki, jak u buka):
       * rynki strzałowe — z 365Scores (chartEvents per strzał, minuta <= 90),
       * faule/wywalczone/przechwyty — z pełnych statystyk meczu 365Scores
         (od razu po meczu; przy dogrywce NIE używamy — obejmują 120 min),
         fallback: bank trendów statshub (parowanie po timestampie),
       * odbiory — tylko bank trendów (365 ich nie podaje),
       * zawodnik nie zagrał (brak w statystykach meczu / 0 minut) -> "zwrot",
       * brak danych źródłowych po 48 h -> "zwrot" (nic nie wisi "w grze"),
       * SUPERZMIANA (Superbet): gdy zawodnik zszedł, a jego zmiennik dołożył
         brakującą statystykę, leg "powyżej" rozliczamy z sumy (patrz
         SUPERZMIANA_RYNKI); rewizja wsteczna naprawia też stare przegrane,

  3. podsumowanie `typy_wyniki` (trafienia, ROI flat, per rynek) idzie na
     stronę Skuteczności. Odchylenie trafień od średniego p_model per rynek
     (bias) to surowiec do dokręcenia kalibracji — STOSUJEMY je w modelu
     dopiero od n>=25 rozliczonych typów na rynku (na razie tylko raport).
"""

from __future__ import annotations

import math
import time

from .. import rozgrywki, supa
from ..model import betting
from ..model import kupony as kupony_model
from ..sources import rotowire, scores365, statshub

# rynek -> pole w agregacie 365Scores (classify_event)
MARKETY_365 = {
    "shots": "shots", "sot": "sot",
    "headed_shots": "headed", "headed_sot": "headed_sot",
    "shots_outside_box": "outside", "sot_outside_box": "sot_outside",
    "shots_blocked": "blocked", "shots_off_target": "off_target",
}
# rynki z pełnych statystyk meczowych 365Scores (lineups.members[].stats) —
# dostępne od razu po meczu, bez czekania na odświeżenie banku trendów
MARKETY_365_STATY = {"fouls_committed", "fouls_won", "interceptions", "offsides"}
# rynki rozliczane z banku trendów statshub (odbiory nie występują w 365)
MARKETY_LIB = {"fouls_committed", "tackles", "fouls_won", "interceptions",
               "offsides"}
# rynki DRUŻYNOWE -> pole w statystykach drużynowych 365 (game_team_stats).
# Rozliczane osobną, prostszą ścieżką: bez modelu minut, bez superzmiany;
# mecz z dogrywką NIE rozlicza się z tych statystyk (obejmują 120 min,
# a rynek dotyczy 90) — po terminie zamyka się jako zwrot
MARKETY_DRUZYNOWE = {
    "team_shots": "shots", "team_sot": "sot",
    "team_fouls": "fouls", "team_cards": "kartki",
    "team_corners": "corners",
    # gole nie występują w game_team_stats — rozliczane z wyniku meczu
    # (scores365.game_scores), pole tu tylko znacznikiem przynależności
    "team_goals": "gole",
}

# --- DWA NOWE RODZAJE ZAKŁADU (2026-07-30): NAJPIERW ROZLICZANIE ---
#
# Kolejność jest celowa. Cała ta sesja to były błędy rozliczeń — typy, których
# nie umieliśmy zamknąć, znikały userowi ze strony i nie trafiały do
# Skuteczności. Wystawienie rynku, którego nie potrafimy rozliczyć, dołożyłoby
# czwarty rodzaj tego samego problemu. Zasada: NIE PUBLIKUJEMY RYNKU, KTÓREGO
# NIE POTRAFIMY ZAMKNĄĆ.
#
# SUMA MECZOWA: obie drużyny razem, linia i strony jak przy pojedynczej
# drużynie (powyżej/poniżej).
MARKETY_SUMY = {
    "match_shots": "shots", "match_sot": "sot",
    "match_fouls": "fouls", "match_cards": "kartki",
    "match_corners": "corners",
}
# „KTO WIĘCEJ": trzy wyniki zamiast dwóch stron linii. `podmiot` trzyma ZAWSZE
# gospodarza (żeby dało się odtworzyć, która drużyna jest która), a `strona`
# mówi, na co postawiliśmy.
MARKETY_WIECEJ = {
    "wiecej_shots": "shots", "wiecej_sot": "sot",
    "wiecej_fouls": "fouls", "wiecej_cards": "kartki",
    "wiecej_corners": "corners",
}
# REMISU NIE GRAMY — decyzja usera 2026-07-30. Publikujemy wyłącznie „ta
# drużyna więcej", nigdy remisu.
#
# ALE MUSIMY GO LICZYĆ, i to nie jest sprzeczność. Remis zabiera część
# prawdopodobieństwa naszej stronie: przy kartkach aż 18,8% meczów kończy się
# tym samym wynikiem obu drużyn, przy strzałach 5,3%. Gdyby pominąć remis
# w rachunku, szansa gospodarza wyszłaby zawyżona nawet o 19 punktów, a kurs
# fair z 2,28 zrobiłby się 1,85 — i cała „przewaga" byłaby zmyślona.
#
# I DRUGA KONSEKWENCJA: remis to dla naszego typu PRZEGRANA, nie zwrot.
# Obstawiamy „gospodarz więcej", mecz kończy się 11:11 — zakład przepada.
# Dlatego rozliczanie niżej porównuje `strona` ze zwycięzcą, a nie sprawdza
# samej różnicy.
#
# GDZIE TEN RYNEK MA SENS: strzały (remis 5%) i faule (5%) są czyste,
# kartki (19%) to inna gra — tam remis zabiera co piąty zakład.
STRONY_WIECEJ = ("gospodarz", "gosc")
STRONA_REMIS = "remis"          # tylko jako wynik rozliczenia, nie do gry
# strzały NIECELNE i ZABLOKOWANE liczymy CAŁKOWICIE OSOBNO — nie wchodzą do
# zbiorczej skuteczności modelu (podsumowanie trafień/ROI ani tabela per rynek).
# Rynek "shots" (strzały ogółem) zostaje bez zmian = wszystkie strzały, zgodnie
# z regulaminem bukmachera; osobność dotyczy tylko raportu skuteczności.
RYNKI_OSOBNE = {"shots_off_target", "shots_blocked"}

# --- Superzmiana (Superbet): gdy wytypowany zawodnik zostanie zmieniony,
# statystyki jego zmiennika doliczają się do zakładu. Objęte rynki wg
# regulaminu (potwierdzone przez usera). Stosujemy WYŁĄCZNIE na korzyść
# gracza: upgrade przegrany -> wygrany na stronie "powyżej". Dla "poniżej"
# dolewka zmiennika mogłaby typ pogrążyć — takich legów nie ruszamy.
SUPERZMIANA_RYNKI = {
    "shots", "sot", "shots_outside_box", "sot_outside_box",
    "tackles", "fouls_committed", "fouls_won",
}


# próbuj rozliczać już ~105 min po kickoffie (źródła i tak wymagają statusu
# "zakończony") — status kuponu odświeża się tuż po końcowym gwizdku
# Kiedy NAJWCZEŚNIEJ wolno próbować rozliczyć mecz. Było 105 minut — a mecz
# trwa 90 minut gry, 15 minut przerwy i doliczony czas obu połów, czyli kończy
# się zwykle po 115–125 minutach od pierwszego gwizdka (Górnik–Fenerbahçe
# 29.07: doliczone 10 + 4, koniec po ~119 minutach). Przy 105 minutach cykl
# pytał źródła w trakcie gry. Pierwszą linią obrony jest status meczu
# u źródła (`statshub.fetch_event_result`), to jest druga: nie zawracamy
# głowy API, dopóki mecz na pewno się nie skończył.
MECZ_KONIEC_PO_S = 130 * 60
OKNO_PAROWANIA_S = 36 * 3600
# po tym czasie bez danych źródłowych typ zamyka się jako "zwrot" (brak
# rozstrzygnięcia) — kupony nie mogą wisieć "w grze" w nieskończoność
TERMIN_BRAK_DANYCH_S = 48 * 3600


# --- STRUMIENIE TYPÓW W LOGU ---
# Log trzyma typy o RÓŻNYM rodowodzie, z różnym znaczeniem pola p_model:
#   * typy modelu (brak `zrodlo`) — p z silnika NB; uczą kalibrację, bias
#     i kwarantannę rynków,
#   * DRABINKI (`zrodlo="drabinka"`) — p z pokrycia linii skorygowanego
#     kontekstem meczu, liczone CAŁKIEM poza silnikiem (jobs/radar.py).
# To dwa różne estymatory tej samej rzeczy, więc muszą się rozliczać osobno:
# wpuszczenie drabinek do kalibracji modelu zatruwałoby ją cudzymi błędami,
# a modelu do skuteczności drabinek — odwrotnie. Rozdziela je ten predykat.
ZRODLO_DRABINKA = "drabinka"


def _zwrot_typu(r: dict) -> float:
    """Ile realnie wraca z 1 j. postawionej na ten typ — PO PODATKU.

    Jedno miejsce dla wszystkich rachunków bilansu (dzień, strumień,
    podsumowanie), żeby nie dało się policzyć raz tak, a raz inaczej.

    TRYB PODATKOWY z rekordu; brak pola = „standard". Rekordy sprzed
    2026-07-31 nie mają go wcale, a wszystkie szły z Superbetu i STS, więc
    domyślny standard odtwarza ich prawdziwy wynik — historia liczy się od
    teraz NETTO (decyzja usera 2026-07-31). To nie jest poprawianie
    przeszłości: zamrożone są `p_model` i kurs, a nie sposób liczenia zysku.
    """
    if r.get("wynik") != "wygrany":
        return 0.0
    return betting.kurs_netto(float(r.get("kurs") or 0.0), r.get("tryb_podatku"))


def _z_modelu(r: dict) -> bool:
    """Typ policzony przez silnik — tylko takie uczą kalibrację i kwarantannę."""
    return not r.get("zrodlo")


def _strumien(r: dict) -> str:
    """Strumień skuteczności typu: pewniaki / druzyny / drabinki.

    Lista przedrostków drużynowych siedzi w `betting` — patrz komentarz przy
    `betting.PRZEDROSTKI_DRUZYNOWE`; do 2026-08-01 to miejsce znało tylko
    `team_`, a kupony znały wszystkie trzy.
    """
    if r.get("zrodlo") == ZRODLO_DRABINKA:
        return "drabinki"
    if str(r.get("rynek_kod") or "").startswith(betting.PRZEDROSTKI_DRUZYNOWE):
        return "druzyny"
    return "pewniaki"


def _klucz(b: dict) -> str:
    # klucz po ZNORMALIZOWANYM NAZWISKU, nie player_id: syntetyczne id
    # (bank/365) może się różnić między źródłami, a w erze randomizowanego
    # hash() zmieniało się co cykl i dublowało typy w logu (do 25 kopii)
    podmiot = rotowire._norm(str(b["podmiot"]))
    k = f"{b['mecz_id']}:{podmiot}:{b['rynek_kod']}:{b['linia']}:{b['strona']}"
    # drabinka trafia w tę samą linię co typ modelu zaskakująco często —
    # bez sufiksu jeden rekord obsługiwałby oba strumienie i pierwszy z brzegu
    # decydowałby, do którego licznika trafi wynik. Stare klucze (bez `zrodlo`)
    # zostają nietknięte, więc log nie wymaga migracji.
    return f"{k}:{b['zrodlo']}" if b.get("zrodlo") else k


_RANGA_WYNIKU = {"wygrany": 2, "przegrany": 2, "zwrot": 1, None: 0}


def _migruj_log(log: dict) -> dict:
    """Przeklucz stary log (klucze z player_id) na klucze po nazwisku,
    scalając duplikaty: kurs/p_model z PIERWSZEJ publikacji (zamrożone),
    wynik z któregokolwiek rozliczonego duplikatu."""
    nowy: dict = {}
    for r in log.values():
        k = _klucz(r)
        a = nowy.get(k)
        if a is None:
            nowy[k] = r
            continue
        if r.get("opublikowano_ts", 0) < a.get("opublikowano_ts", 0):
            a, r = r, a
            nowy[k] = a
        if _RANGA_WYNIKU.get(r.get("wynik"), 0) > _RANGA_WYNIKU.get(a.get("wynik"), 0):
            for f in ("wynik", "faktyczna", "rozliczono_ts", "powod"):
                if f in r:
                    a[f] = r[f]
    return nowy


def _kupon_leg_do_logu(l: dict) -> dict:
    """Rzutuje leg kuponu (kupony.py:_leg_dict) na rekord dla _dopisz_nowe.

    Leg kuponu jest CZĘSTO jedynym miejscem, w którym dany typ w ogóle
    trafia do typy_log — value_bets trzyma tylko best-per-side, a spora
    część legów z legi_pool nigdy nie zostaje osobno opublikowaną okazją.
    Musi więc przenosić WSZYSTKIE pola, które _dopisz_nowe zapisuje/aktualizuje
    (patrz tam), inaczej te legi są ślepą plamą dla diagnostyki per kategoria."""
    return {
        "mecz_id": l["mecz_id"], "mecz": l["mecz"],
        "kickoff_ts": l["kickoff_ts"],
        "podmiot_id": l.get("podmiot_id", 0),
        "podmiot": l["podmiot"], "rynek_kod": l.get("rynek_kod", ""),
        "rynek": l["rynek"], "linia": l["linia"], "strona": l["strona"],
        "kurs": l["kurs"], "bukmacher": l.get("bukmacher"),
        "kurs_ref": l.get("kurs_ref"),
        "p_model": l["p_model"], "pewnosc": l.get("pewnosc"),
        "sugestia": False,
        "matchup": l.get("matchup"), "rotacja": l.get("rotacja"),
        "matchup_styl": l.get("matchup_styl"),
        "wyzsza_linia": l.get("wyzsza_linia"),
        "miekka_linia": l.get("miekka_linia"),
        "xi_sygnal": l.get("xi_sygnal"),
        "kal_tau": l.get("kal_tau"),
    }


def _delta_stempla(b: dict) -> float:
    """Delta korekty strumienia UŻYTA dla tego typu — jako liczba.

    Korekta bywa skalarem albo rozkładem po przedziałach `p`. Do księgi ma
    trafić jedna liczba: ta, o którą faktycznie przesunięto ten typ. Bin
    rozwiązujemy na `p_over`, bo tam korekta jest nakładana i stamtąd lustrzy
    się na „poniżej" (patrz `_p_surowe`).

    ZASTRZEŻENIE, świadome: bin czytamy z `p` JUŻ skorygowanego, a nakładano
    go na surowym. Przedziały są szerokie (0,55 / 0,70 / 0,85), a korekta
    przesuwa `p` o kilka pp, więc pokrywają się prawie zawsze — ale typ tuż
    przy granicy binu może dostać stempel z sąsiedniego. Silnik może podać
    deltę wprost (pole `kal_strumien` na typie) i wtedy bierzemy ją bez
    zgadywania.
    """
    d = b.get("kal_strumien")
    if isinstance(d, (int, float)):
        return round(float(d), 4)
    p = float(b.get("p_model") or 0.0)
    p_over = p if b.get("strona") != "ponizej" else 1.0 - p
    return round(betting.delta_dla_p(_KOREKTA_CYKLU.get(_strumien(b)), p_over), 4)


def _dopisz_nowe(log: dict, value_bets: list[dict]) -> None:
    for b in value_bets:
        k = _klucz(b)
        if k in log:
            # flagi kategorii potrafią pojawić się PO pierwszej publikacji
            # (miękka linia w dniu meczu, matchup gdy urośnie profil rywala,
            # świeży skład) — bez aktualizacji stare klucze byłyby na zawsze
            # "bezkategoriowe" i diagnostyka per kategoria nie miałaby danych.
            # Aktualizujemy OR-em wyłącznie wpisy jeszcze nierozliczone;
            # kurs/p_model zostają z pierwszej publikacji (dataset kalibracji).
            rec = log[k]
            if rec.get("wynik") is None:
                for f in ("matchup", "matchup_styl", "rotacja", "wyzsza_linia",
                          "pewniak", "miekka_linia"):
                    if b.get(f):
                        rec[f] = True
                if b.get("xi_sygnal") is not None:
                    rec["xi_sygnal"] = b["xi_sygnal"]  # najświeższy przed meczem
                # typ pomiarowy (odrzucony przy progu), który PÓŹNIEJ przeszedł
                # progi i został opublikowany — przestaje być pomiarowy (wraca
                # do kalibracji/skuteczności); w drugą stronę NIGDY nie
                # degradujemy opublikowanego typu do pomiarowego
                if rec.get("odrzucony") and not b.get("odrzucony"):
                    rec["odrzucony"] = False
                    rec.pop("odrzucenie_powod", None)
                # typ spoza publikacji (kwarantanna/limit meczu), który w
                # kolejnym cyklu WSZEDŁ do publikacji — awansuje; w drugą
                # stronę nigdy nie degradujemy opublikowanego typu
                if rec.get("poza_publikacja") and not b.get("poza_publikacja"):
                    rec.pop("poza_publikacja", None)
            continue
        log[k] = {
            "mecz_id": b["mecz_id"], "mecz": b["mecz"],
            "kickoff_ts": b["kickoff_ts"],
            "podmiot_id": b["podmiot_id"], "podmiot": b["podmiot"],
            "rynek_kod": b["rynek_kod"], "rynek": b["rynek"],
            "linia": b["linia"], "strona": b["strona"],
            "kurs": b.get("kurs"), "bukmacher": b.get("bukmacher"),
            # konsensus UK (mediana buków) — do KALIBRACJI marży UK z rozliczeń:
            # po zebraniu próby porównujemy 1/kurs_ref do realnej częstości trafień
            # i stąd wyliczamy prawdziwą UK_CONSENSUS_MARGIN (dziś założona 0.045)
            "kurs_ref": b.get("kurs_ref"),
            "p_model": b["p_model"], "pewnosc": b.get("pewnosc"),
            "sugestia": bool(b.get("sugestia")),
            # historia predykcji typów DRUŻYNOWYCH — patrz kalibracja_tau.py
            **({"kal_tau": b["kal_tau"]} if b.get("kal_tau") else {}),
            # KOREKTA STRUMIENIA użyta przy publikacji — bez tego stempla
            # następny pomiar liczyłby się z już skorygowanego p i regulator
            # by oscylował (patrz `korekta_strumienia`)
            #
            # STEMPLUJEMY LICZBĘ, NIE CAŁY OBIEKT KOREKTY (2026-08-01).
            # Od wprowadzenia przedziałów (31.07) korekta bywa słownikiem
            # `{"global":…, "bins":[…]}`, a tu leciał on do księgi w całości —
            # więc stempel mówił „skorygowano o CAŁY rozkład" zamiast „o tyle".
            # `_p_surowe` odwraca stempel odejmowaniem, co na słowniku wywala
            # się TypeError-em i kładzie `korekta_strumienia` oraz
            # `szansa_pokazywana` (obie są w cyklu w try/except, więc uczenie
            # cicho przestawało działać zamiast krzyczeć). Zapisujemy deltę
            # rozwiązaną dla `p` TEGO typu — dokładnie tę, którą nałożono.
            **({"kal_strumien": _delta_stempla(b)}
               if _KOREKTA_CYKLU.get(_strumien(b)) else {}),
            # kategorie typu — do diagnostyki per kategoria (Brier/log-loss)
            "matchup": bool(b.get("matchup")),
            "matchup_styl": bool(b.get("matchup_styl")),
            "rotacja": bool(b.get("rotacja")),
            "wyzsza_linia": bool(b.get("wyzsza_linia")),
            "pewniak": bool(b.get("pewniak")),
            "miekka_linia": bool(b.get("miekka_linia")),
            # sygnał składu przy publikacji — do kalibracji p_start z rozliczeń
            "xi_sygnal": b.get("xi_sygnal"),
            # POMIAR PROGÓW: typ odrzucony tuż przy progu (betting.NEAR_*) —
            # rozlicza się w tle, POZA kalibracją/skutecznością/UI; diagnostyka
            # porównuje jego hit-rate z przepuszczonymi (kategoria
            # odrzucone_pomiar), zanim ktokolwiek ruszy same progi
            "odrzucony": bool(b.get("odrzucony")),
            "odrzucenie_powod": b.get("odrzucenie_powod"),
            # POZA PUBLIKACJĄ: "kwarantanna_rynku" (rynek trafia poniżej
            # deklaracji) albo "limit_meczu" (nadmiar typów z jednego meczu).
            # Rozlicza się i UCZY kalibrację, ale nie wchodzi do
            # skuteczności/kalendarza/UI — w odróżnieniu od `odrzucony`,
            # który jest też poza kalibracją.
            "poza_publikacja": b.get("poza_publikacja"),
            # STRUMIEŃ: brak = typ modelu. "drabinka" = karta z zakładki
            # Drabinki; `klasa` i `edge` zamrożone przy publikacji, żeby dało
            # się potem sprawdzić, czy klasa „top" faktycznie trafia lepiej
            # niż „solidny" (inaczej progi PROG_KLASY zostaną na zawsze
            # nieweryfikowalnym założeniem)
            **({"zrodlo": b["zrodlo"]} if b.get("zrodlo") else {}),
            **({"klasa": b["klasa"]} if b.get("klasa") else {}),
            **({"edge": b["edge"]} if b.get("edge") is not None else {}),
            "opublikowano_ts": int(time.time()),
            # WERSJE ZAMROŻONE PRZY TYPIE (2026-08-01) — model / kalibracja /
            # polityka selekcji / dane. Bez tego każdy pomiar na tym logu
            # miesza epoki i wychodzą z niego wnioski, które trzeba odwoływać
            # (zdarzyło się dwa razy w tygodniu — patrz betting.WERSJA_*).
            # Historia typów NIE jest przepisywana wstecz: rekord bez pola
            # znaczy „sprzed wersjonowania" i tak ma zostać.
            "wersje": betting.wersje_publikacji(),
            # CZAS ODCZYTU KURSU — osobno od czasu publikacji. Kurs bywa
            # czytany raz na cykl i użyty do kilku typów, a typ wznowiony
            # niesie cenę sprzed godzin; bez tego pola nie da się zmierzyć,
            # jak stara była cena, którą pokazaliśmy (punkt 10 z listy usera:
            # wskaźnik świeżości).
            "kurs_ts": b.get("kurs_ts") or int(time.time()),
            # TRYB PODATKOWY ZAMROŻONY PRZY TYPIE (2026-07-31). Bez tego pola
            # `_zwrot_typu` zawsze czytałby None i rozliczał wszystko jako
            # „standard" — czyli zamrożenie trybu byłoby pozorne, a przyszły
            # typ z oferty „bez podatku" policzyłby się źle. Kurs i p_model są
            # zamrażane z tego samego powodu: rekord ma pamiętać, w czym był
            # liczony, a nie zależeć od dzisiejszej konfiguracji.
            "tryb_podatku": b.get("tryb_podatku")
                            or betting.tryb_podatku(b.get("bukmacher")),
            "wynik": None, "faktyczna": None,
        }


KOPIA_LOGU_KLUCZ = "typy_log_kopia"
KOPIA_LOGU_CO_S = 24 * 3600


def _kopia_zapasowa_logu(log: dict, now: int) -> None:
    """Raz na dobę odkładamy migawkę księgi typów pod osobny klucz.

    Bezpieczniki przy zapisie bronią przed skasowaniem historii przez własny
    kod, ale nie przed pomyłką po stronie bazy ani ręcznym błędem. Doba to
    kompromis: kopia kosztuje jeden zapis dziennie, a najgorszy przypadek to
    utrata jednego dnia rozliczeń zamiast wszystkiego.
    """
    kopia, ok = supa.get_key_ok(KOPIA_LOGU_KLUCZ)
    if not ok:
        return
    if kopia and now - int((kopia or {}).get("ts") or 0) < KOPIA_LOGU_CO_S:
        return
    if supa.put_key(KOPIA_LOGU_KLUCZ, {"ts": now, "log": log}):
        print(f"Kopia zapasowa księgi typów: {len(log)} wpisów")


def _gid_365(rec: dict, cache: dict) -> int | None:
    """Znajdź id zakończonego meczu w 365Scores (cache per mecz).

    Multi-liga: wyniki z rozgrywek ZAKRESU DRUŻYNOWEGO (rozgrywki.comp365)
    plus MŚ (stare typy w logu). Mecze spoza tych rozgrywek (globalne propsy)
    nie mają gid — rozliczają się z banku/feedu trendów statshub.
    Endpoint /games/results per rozgrywki — /games/current ignoruje filtr
    dat i nie zawiera wczorajszych meczów. Dopasowanie po znormalizowanych
    nazwach drużyn; awaryjnie po kickoffie + jednej nazwie.
    """
    mid = rec["mecz_id"]
    if mid in cache:
        return cache[mid]
    teams = [t.strip() for t in str(rec["mecz"]).replace("—", "–").split("–")]
    if len(teams) != 2:
        cache[mid] = None
        return None
    home, away = rotowire._norm(teams[0]), rotowire._norm(teams[1])
    if "_wyniki" not in cache:
        wyniki: list[dict] = []
        for c in [None] + rozgrywki.comp365_druzynowe():
            try:
                wyniki += (
                    scores365.finished_games_by_competition(c)
                    if c else scores365.finished_games_by_competition()
                )
            except Exception:
                continue
        cache["_wyniki"] = wyniki
    gid = None
    for g in cache["_wyniki"]:
        if {g["home"], g["away"]} == {home, away}:
            gid = g["id"]
            break
        if (
            abs(g["ts"] - rec["kickoff_ts"]) < 3 * 3600
            and {g["home"], g["away"]} & {home, away}
        ):
            gid = g["id"]
            break
    cache[mid] = gid
    return gid


def _dolej_swieze_trendy(log: dict, lib: dict, now: int) -> None:
    """Multi-liga: dolej do banku (IN-MEMORY) trendy rozegranych meczów
    z nierozliczonych typów zawodniczych.

    mecz_id w logu to event id statshub, a props/player-trends dla
    ROZEGRANEGO meczu zwraca historię z tym meczem w recentGames — jeden
    batchowy request rozlicza strzały/celne/faule/odbiory w KAŻDEJ lidze
    świata, także tam, gdzie 365Scores nie zna rozgrywek (brak comp365).
    Nie zapisujemy trend_lib (to robi cykl budowy) — dolewka żyje tylko
    na czas tego rozliczenia.
    """
    mids = sorted({
        r["mecz_id"] for r in log.values()
        if not r.get("wynik")
        and str(r.get("podmiot_typ", "zawodnik")) == "zawodnik"
        and MECZ_KONIEC_PO_S < now - r["kickoff_ts"] < TERMIN_BRAK_DANYCH_S
        and r.get("mecz_id")
    })
    if not mids:
        return
    try:
        trendy = statshub.fetch_event_trends(mids[:60])
    except Exception:
        return
    n_dolane = 0
    for t in trendy:
        key = f"{t.player_id}:{t.market_code}"
        prev = lib.get(key)
        ts_new = t.timestamps[0] if t.timestamps else 0
        ts_old = (prev.get("timestamps") or [0])[0] if prev else -1
        if ts_new >= ts_old:
            lib[key] = {
                "timestamps": list(t.timestamps),
                "counts": list(t.counts),
                "minutes": list(t.minutes),
            }
            n_dolane += 1
    if n_dolane:
        print(f"Rozliczanie: dolano świeże trendy {len(mids[:60])} meczów "
              f"({n_dolane} rekordów) do rozliczeń spoza 365")


def _minuty_z_banku(rec: dict, lib: dict) -> float | None:
    """Minuty zawodnika w rozliczanym meczu (z banku trendów, rynek shots)."""
    t = lib.get(f"{rec['podmiot_id']}:shots")
    if not t:
        return None
    for i, ts in enumerate(t.get("timestamps", [])):
        if abs(ts - rec["kickoff_ts"]) < OKNO_PAROWANIA_S:
            mins = t.get("minutes", [])
            return float(mins[i]) if i < len(mins) else None
    return None


def _wartosc_z_banku(rec: dict, lib: dict) -> float | None:
    t = lib.get(f"{rec['podmiot_id']}:{rec['rynek_kod']}")
    if not t:
        return None
    for i, ts in enumerate(t.get("timestamps", [])):
        if abs(ts - rec["kickoff_ts"]) < OKNO_PAROWANIA_S:
            cnts = t.get("counts", [])
            return float(cnts[i]) if i < len(cnts) else None
    return None


def _wartosc_zmiennika(
    nazwisko_norm: str, mk: str, gid: int | None, staty: dict | None,
    lib: dict, rec: dict,
) -> float | None:
    """Statystyka zmiennika w rozliczanym meczu (cały jego czas gry jest
    z definicji PO wejściu, więc pełnomeczowa wartość = wkład po zmianie)."""
    if mk in MARKETY_365 and gid is not None:
        try:
            gra = scores365.game_player_shots(gid)
        except Exception:
            gra = None
        if gra is not None:
            skey = scores365.resolve_player_key(set(gra), nazwisko_norm)
            if skey:
                return float(gra[skey].get(MARKETY_365[mk], 0))
            return 0.0  # wszedł, a nie ma go w mapie strzałów = 0 zdarzeń
    if (
        mk in MARKETY_365_STATY and staty
        and gid is not None and not scores365.after_extra_time(gid)
    ):
        skey = scores365.resolve_player_key(set(staty), nazwisko_norm)
        if skey:
            w = staty[skey].get(mk)
            if w is not None:
                return float(w)
    # bank trendów (jedyne źródło odbiorów) — zmiennika szukamy po nazwisku,
    # bo nie znamy jego statshubowego id
    kandydaci = {
        rotowire._norm(str(t.get("player_name", ""))): t
        for t in lib.values()
        if t.get("market_code") == mk
    }
    tkey = scores365.resolve_player_key(set(kandydaci), nazwisko_norm)
    if tkey:
        t = kandydaci[tkey]
        for i, ts in enumerate(t.get("timestamps", [])):
            if abs(ts - rec["kickoff_ts"]) < OKNO_PAROWANIA_S:
                cnts = t.get("counts", [])
                return float(cnts[i]) if i < len(cnts) else None
    return None


def _superzmiana(
    rec: dict, gid: int | None, staty: dict | None, lib: dict,
    wartosc: float | None,
) -> tuple[float, str] | None:
    """Superzmiana Superbetu: dolicz statystyki zmiennika, jeśli ratują lega.

    Zwraca (nowa_wartość, powód) tylko gdy suma przebija linię — nigdy nie
    pogarsza wyniku. None = nie dotyczy / brak danych / suma dalej za niska.
    """
    if (
        rec.get("strona") != "powyzej"
        or rec.get("rynek_kod") not in SUPERZMIANA_RYNKI
        or "superbet" not in str(rec.get("bukmacher") or "").lower()
        or gid is None
    ):
        return None
    try:
        subs = scores365.game_substitutions(gid)
    except Exception:
        return None
    klucz = scores365.resolve_player_key(set(subs), str(rec["podmiot"]))
    if not klucz:
        return None  # grał do końca albo brak danych o zmianie
    zmiennik = subs[klucz]["wszedl"]
    dodatek = _wartosc_zmiennika(
        zmiennik, rec["rynek_kod"], gid, staty, lib, rec
    )
    if not dodatek:
        return None
    suma = float(wartosc or 0.0) + dodatek
    if suma > rec["linia"]:
        return suma, (
            f"superzmiana: {zmiennik} dołożył {dodatek:g} po wejściu "
            f"za {rec['podmiot']} ({subs[klucz]['minuta']:.0f}')"
        )
    return None


MIN_N_KALIBRACJI = 25          # od tylu rozliczonych typów na rynek korygujemy
BIAS_CAP = (0.85, 1.15)        # (stary format mnożnikowy — compute_bias/raport)
# kalibracja w PRZESTRZENI LOGITÓW: p' = sigmoid(logit(p) + b) — mnożnik
# psuł ogony (p=95% ściągał za mocno, p=50% za słabo); delta logitowa
# koryguje równomiernie. Cap w dół poszerzony do −0.80 (2026-07-19): zmierzone
# błędy realnych rynków wymagały delty −0.58 (shots) i −1.1 (fouls_committed),
# a cap −0.40 ucinał korektę w połowie — model NIE MÓGŁ się skalibrować mimo
# danych. Przed przestrzeleniem chroni shrinkage (waga n/(n+25)), nie cap.
BIAS_CAP_LOGIT = (-0.80, 0.40)
# sugestie STS (bez kursu, bez bezpieczników rynkowych) kalibrują się OSOBNO
# i mylą się dużo mocniej niż typy z kursem — cap w dół musi być szerszy
SUGESTIA_BIAS_CAP_LOGIT = (-1.0, 0.40)
# kalibracja PRZEDZIAŁOWA: bias liczony osobno per przedział szansy (model
# może przeszacowywać longshoty, a pewniaki mieć dobrze)
# przedział 0.70-1.01 sklejał dobrze skalibrowane 0.75-0.85 (hit ~ p) z
# przeszacowanym 0.85+ (hit 70% vs p 89%) — korekta się uśredniała; osobny
# bin góry pozwala kalibracji dociskać tam, gdzie faktycznie przeszacowuje
BIAS_PRZEDZIALY = [(0.0, 0.55), (0.55, 0.70), (0.70, 0.85), (0.85, 1.01)]
MIN_N_PRZEDZIAL = 15
# WAŻENIE ŚWIEŻOŚCI kalibracji: rozliczenie sprzed 14 dni waży połowę
# najnowszego (półokres). Warunki gry zmieniają się (faza grupowa vs
# pucharowa, klub vs turniej) — bez wygaszania stara prawda przykrywa nową
# i korekta reaguje z tygodniowym opóźnieniem. Punktem "teraz" jest
# najnowsze rozliczenie w logu (nie zegar) — przerwa w cyklach nie
# wyzerowuje kalibracji.
KALIBRACJA_POLOWICZNY_DNI = 14.0
# pokrewne rynki dzielą błąd modelu (shots i sot mylą się razem) — shrinkage
# rodzinny: rynek z małą próbą jest ściągany do biasu swojej rodziny;
# mapa wspólna z kuponami (dywersyfikacja) — mieszka w model/betting.py
RODZINY_RYNKOW = betting.RODZINY_RYNKOW


def _bias_surowy(grp: list[dict]) -> float:
    """(trafienia + 2) / (suma zamrożonych p_model + 2): >1 = model
    niedoszacowuje, <1 = przeszacowuje (pseudozliczenia +2 stabilizują)."""
    traf = sum(1 for r in grp if r["wynik"] == "wygrany")
    return (traf + 2.0) / (sum(r["p_model"] for r in grp) + 2.0)


def _cap_bias(b: float, cap: tuple[float, float] = BIAS_CAP) -> float:
    return round(max(cap[0], min(cap[1], b)), 3)


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def _bias_logit(grp: list[dict], wagi: list[float] | None = None) -> float:
    """Delta logitowa b: rozwiązanie Σ w·sigmoid(logit(p_i)+b) = Σ w·trafienia.

    Pseudozliczenia stabilizujące jak w _bias_surowy: dwie wirtualne
    obserwacje p=0.5 (jedna trafiona, jedna nie, waga 1). Opcjonalne wagi =
    ważenie świeżości. Bisekcja — bez zależności.
    """
    ps = [min(max(float(r["p_model"]), 1e-6), 1 - 1e-6) for r in grp]
    w = list(wagi) if wagi is not None else [1.0] * len(grp)
    traf = sum(wi for r, wi in zip(grp, w) if r["wynik"] == "wygrany") + 1.0
    ps += [0.5, 0.5]
    w += [1.0, 1.0]

    def f(b: float) -> float:
        return sum(
            wi / (1.0 + math.exp(-(_logit(p) + b))) for p, wi in zip(ps, w)
        ) - traf

    lo, hi = -3.0, 3.0
    if f(lo) > 0:
        return lo
    if f(hi) < 0:
        return hi
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def compute_bias(log: dict, min_n: int = MIN_N_KALIBRACJI) -> dict[str, float]:
    """Płaski bias per rynek (stary format) — zachowany dla raportu i testów."""
    grupy: dict[str, list[dict]] = {}
    for r in log.values():
        if (r.get("wynik") in ("wygrany", "przegrany")
                and not r.get("odrzucony") and _z_modelu(r)):
            grupy.setdefault(r["rynek_kod"], []).append(r)
    return {
        mk: _cap_bias(_bias_surowy(grp))
        for mk, grp in grupy.items()
        if len(grp) >= min_n
    }


def compute_bias_full(
    log: dict,
    min_n: int = MIN_N_KALIBRACJI,
    sugestie: bool = False,
    cap: tuple[float, float] = BIAS_CAP_LOGIT,
) -> dict[str, dict]:
    """Kalibracja przedziałowa z shrinkage: rodzina -> rynek -> przedział.

    Wartości to DELTY LOGITOWE (p' = sigmoid(logit(p) + b)) — równomierna
    korekta w całej skali szans, w przeciwieństwie do mnożnika.
    Trzy poziomy (każdy ściągany do nadrzędnego proporcjonalnie do próby):
      1. rodzina rynków (strzelanie/faule/defensywa) — od min_n rozliczeń,
      2. rynek — bias ściągany do rodziny wagą n/(n+min_n),
      3. przedział szansy — ściągany do biasu rynku wagą n/(n+MIN_N_PRZEDZIAL).

    Zwraca {rynek: {"logit": True, "global": b, "bins": [[lo, hi, b], ...]}}
    — format rozumiany przez engine (stary mnożnikowy dalej wspierany).
    """
    # sugestie STS trafiają fatalnie względem typów z kursem (inne progi, brak
    # bezpieczników) — mieszanie ich z typami zaniżało bias całych rodzin.
    # Typy POMIAROWE (odrzucone przy progu) też zostają poza kalibracją —
    # nie były publikowane i z definicji łamią któryś bezpiecznik.
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and bool(r.get("sugestia")) == sugestie
        and not r.get("odrzucony")
        # drabinki mają własne p (pokrycie + kontekst), nie p silnika —
        # kalibracja modelu musi je pomijać, inaczej uczy się cudzych błędów
        and _z_modelu(r)
    ]
    # ważenie świeżości względem najnowszego rozliczenia w logu — świeże
    # błędy ważą więcej, stare wygasają (półokres KALIBRACJA_POLOWICZNY_DNI)
    ts_max = max(
        (float(r.get("kickoff_ts") or 0) for r in settled), default=0.0
    )

    def _w(r: dict) -> float:
        dni = max(ts_max - float(r.get("kickoff_ts") or 0), 0.0) / 86400.0
        return 0.5 ** (dni / KALIBRACJA_POLOWICZNY_DNI)

    rodziny: dict[str, list[dict]] = {}
    for r in settled:
        fam = RODZINY_RYNKOW.get(r["rynek_kod"])
        if fam:
            rodziny.setdefault(fam, []).append(r)
    fam_bias = {
        f: _bias_logit(g, [_w(r) for r in g])
        for f, g in rodziny.items() if len(g) >= min_n
    }
    grupy: dict[str, list[dict]] = {}
    for r in settled:
        grupy.setdefault(r["rynek_kod"], []).append(r)
    out: dict[str, dict] = {}
    for mk, grp in grupy.items():
        fb = fam_bias.get(RODZINY_RYNKOW.get(mk, ""))
        # shrink liczony na EFEKTYWNEJ próbie (suma wag świeżości): stare
        # rozliczenia nie tylko mniej znaczą w biasie, ale i słabiej
        # emancypują rynek od rodziny
        n_eff = sum(_w(r) for r in grp)
        raw = _bias_logit(grp, [_w(r) for r in grp])
        if fb is not None:
            g = fb + (n_eff / (n_eff + min_n)) * (raw - fb)
        elif len(grp) >= min_n:
            g = raw
        else:
            continue  # za mało danych i brak rozliczonej rodziny
        bins = []
        for lo, hi in BIAS_PRZEDZIALY:
            # po `p_over`, nie po `p` typu — patrz `_p_over_rekordu`
            bgrp = [r for r in grp if lo <= _p_over_rekordu(r) < hi]
            bb = g
            if len(bgrp) >= MIN_N_PRZEDZIAL:
                b_eff = sum(_w(r) for r in bgrp)
                k = b_eff / (b_eff + MIN_N_PRZEDZIAL)
                bb = g + k * (_bias_logit(bgrp, [_w(r) for r in bgrp]) - g)
            bins.append([lo, hi, _cap_bias(bb, cap)])
        out[mk] = {"logit": True, "global": _cap_bias(g, cap), "bins": bins}
    return out


# KWARANTANNA RYNKU: rynek, który w oknie ostatnich rozliczeń TRACI PIENIĄDZE,
# wypada z PUBLIKACJI (pewniaki, pula kuponów), ale dalej jest scorowany
# i logowany (poza_publikacja="kwarantanna_rynku") — kalibracja mierzy go nadal
# i rynek wraca sam, gdy okno rozliczeń się poprawi.
#
# KRYTERIUM TO ROI, NIE KALIBRACJA. Wcześniej bramą był bias (trafienia vs
# deklaracja) — mierzyliśmy jedno, a karaliśmy czym innym: rynek źle
# skalibrowany bywa dochodowy (wysokie kursy niosą pudła) i odwrotnie, rynek
# trafiający zgodnie z deklaracją potrafi tracić przy kursach poniżej fair.
# Skoro karą jest zdjęcie z publikacji, mierzyć trzeba to, co publikacja
# realnie kosztuje: zwrot z jednostkowej stawki.
KWARANTANNA_ROI_WEJSCIE = -0.10   # wejście: strata > 10 gr na złotówce stawki
KWARANTANNA_ROI_WYJSCIE = -0.02   # wyjście: dopiero gdy strata prawie znika
KWARANTANNA_MIN_N = 15            # od tylu rozliczonych typów oceniamy rynek
KWARANTANNA_OKNO = 40             # okno kroczące: tylko ostatnie N rozliczeń
# ile ostatnich rozliczeń oglądamy w poszukiwaniu flagi z poprzedniego cyklu
# (patrz `_byl_w_kwarantannie`)
KWARANTANNA_HISTEREZA_OKNO = 5


def _byl_w_kwarantannie(grp: list[dict]) -> bool:
    """Czy rynek stał w kwarantannie w poprzednim cyklu — odczytane z logu.

    Rynek w kwarantannie oznacza flagą WSZYSTKIE swoje typy, więc wystarczy
    zajrzeć w najświeższe rozliczenia. Patrzymy na kilka ostatnich, a nie na
    jedno, bo typy wystawione po wejściu do kwarantanny rozliczą się dopiero
    za dzień–dwa i przez ten czas najświeższy rekord jest jeszcze sprzed
    wstrzymania.
    """
    return any(
        r.get("poza_publikacja") == "kwarantanna_rynku"
        for r in grp[-KWARANTANNA_HISTEREZA_OKNO:]
    )


def rynki_kwarantanna(log: dict | None = None) -> dict[str, dict]:
    """Rynki chwilowo poza publikacją: ROI flat z okna ostatnich rozliczeń
    poniżej progu, z histerezą (wejście −10%, wyjście −2%) żeby rynek nie
    migotał na granicy. Zwraca {rynek: {roi, n, hit, sr_p, bias}}."""
    if log is None:
        log = _migruj_log(supa.get_key("typy_log") or {})
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and _z_modelu(r)   # kwarantanna dotyczy DEKLARACJI MODELU, nie drabinek
        # bez kursu nie ma ROI — typ jest wtedy niemierzalny tą bramą
        and r.get("kurs") and float(r["kurs"]) > 1.0
    ]
    out: dict[str, dict] = {}
    for mk in {r["rynek_kod"] for r in settled}:
        grp = sorted(
            (r for r in settled if r["rynek_kod"] == mk),
            key=lambda r: r.get("kickoff_ts") or 0,
        )[-KWARANTANNA_OKNO:]
        if len(grp) < KWARANTANNA_MIN_N:
            continue
        traf = sum(1 for r in grp if r["wynik"] == "wygrany")
        sr_p = sum(r["p_model"] for r in grp) / len(grp)
        bias = (traf + 2.0) / (sr_p * len(grp) + 2.0)
        # ROI BRUTTO, ŚWIADOMIE (2026-07-31): kwarantanna to BRAMA, a bramy
        # zostają na brutto do czasu pomiaru — inaczej podatek przestawiłby
        # naraz i rachunek, i selekcję, i w rozliczeniach nie dałoby się
        # rozdzielić jednego od drugiego. Progi KWARANTANNA_ROI_* były
        # kalibrowane na brutto; ich przeliczenie to osobna decyzja.
        roi = sum(
            (float(r["kurs"]) - 1.0) if r["wynik"] == "wygrany" else -1.0
            for r in grp
        ) / len(grp)
        if roi < KWARANTANNA_ROI_WEJSCIE:
            wstrzymany = True
        elif roi > KWARANTANNA_ROI_WYJSCIE:
            wstrzymany = False
        else:
            wstrzymany = _byl_w_kwarantannie(grp)   # strefa histerezy: bez ruchu
        if wstrzymany:
            out[mk] = {
                "roi": round(roi, 3), "bias": round(bias, 3), "n": len(grp),
                "hit": round(traf / len(grp), 3), "sr_p": round(sr_p, 3),
            }
    return out


# KWARANTANNA STRONY LINII (2026-07-30). Ta sama mechanika co przy rynkach,
# ale bramą jest STRONA zakładu na danym rynku: „gole drużyny powyżej" osobno
# od „gole drużyny poniżej".
#
# POWÓD — pomiar na 108 rozliczonych typach drużynowych:
#     „powyżej"  mówiliśmy 74%, weszło 59%  ROI −15%
#     „poniżej"  mówiliśmy 72%, weszło 69%  ROI  +8%
# Różnica 23 punktów ROI na tym samym rynku. Kwarantanna rynkowa tego nie
# widziała, bo miesza obie strony w jeden licznik i wychodzi jej średnia —
# rynek albo wypada cały (razem z dobrą stroną), albo zostaje cały (razem
# ze złą). Żadna z tych dwóch odpowiedzi nie jest prawdziwa.
#
# Świadomie NIE wpisujemy na sztywno „gramy tylko poniżej": 108 rozliczeń to
# za mało na taką decyzję, a mechanizm z histerezą sam to wybierze z danych
# i sam odkręci, gdy strona się poprawi.
STRONA_MIN_N = 15
STRONA_OKNO = 50


def _byla_wstrzymana_strona(grp: list[dict]) -> bool:
    return any(
        r.get("poza_publikacja") == "kwarantanna_strony"
        for r in grp[-KWARANTANNA_HISTEREZA_OKNO:]
    )


def strony_kwarantanna(log: dict | None = None) -> dict[str, dict]:
    """Strony linii chwilowo poza publikacją: {"team_goals:powyzej": {...}}.

    ROI z okna ostatnich rozliczeń danej pary (rynek, strona), z tą samą
    histerezą wejścia/wyjścia co kwarantanna rynków.
    """
    if log is None:
        log = _migruj_log(supa.get_key("typy_log") or {})
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and _z_modelu(r)
        and r.get("kurs") and float(r["kurs"]) > 1.0
        # STRONY, KTORE ZNAMY: linia ma dwie („powyzej"/„ponizej"), a rynek
        # „kto wiecej" — dwie druzynowe („gospodarz"/„gosc"). Bez dopisania
        # tych drugich nowy rynek wchodzilby BEZ zabezpieczenia, ktore
        # 2026-07-30 okazalo sie najskuteczniejsze: to ono pokazalo, ze
        # wszystkie tracace strony to „powyzej".
        and r.get("strona") in ("powyzej", "ponizej", *STRONY_WIECEJ)
    ]
    out: dict[str, dict] = {}
    pary = {(r["rynek_kod"], r["strona"]) for r in settled}
    for mk, strona in pary:
        grp = sorted(
            (r for r in settled
             if r["rynek_kod"] == mk and r["strona"] == strona),
            key=lambda r: r.get("kickoff_ts") or 0,
        )[-STRONA_OKNO:]
        if len(grp) < STRONA_MIN_N:
            continue
        traf = sum(1 for r in grp if r["wynik"] == "wygrany")
        # ROI BRUTTO, ŚWIADOMIE (2026-07-31): kwarantanna to BRAMA, a bramy
        # zostają na brutto do czasu pomiaru — inaczej podatek przestawiłby
        # naraz i rachunek, i selekcję, i w rozliczeniach nie dałoby się
        # rozdzielić jednego od drugiego. Progi KWARANTANNA_ROI_* były
        # kalibrowane na brutto; ich przeliczenie to osobna decyzja.
        roi = sum(
            (float(r["kurs"]) - 1.0) if r["wynik"] == "wygrany" else -1.0
            for r in grp
        ) / len(grp)
        if roi < KWARANTANNA_ROI_WEJSCIE:
            wstrzymana = True
        elif roi > KWARANTANNA_ROI_WYJSCIE:
            wstrzymana = False
        else:
            wstrzymana = _byla_wstrzymana_strona(grp)
        if wstrzymana:
            out[f"{mk}:{strona}"] = {
                "roi": round(roi, 3), "n": len(grp),
                "hit": round(traf / len(grp), 3),
                "sr_p": round(
                    sum(float(r["p_model"]) for r in grp) / len(grp), 3),
                "rynek": grp[0].get("rynek") or mk,
                "strona": strona,
            }
    return out


def kwarantanna() -> dict[str, dict]:
    """Kwarantanna rynków z logu w Supabase (pusta, gdy brak danych/env)."""
    log = _migruj_log(supa.get_key("typy_log") or {})
    return rynki_kwarantanna(log)


# KWARANTANNA KATEGORII — ta sama mechanika co przy rynkach, ale bramą jest
# POWÓD, dla którego typ w ogóle wszedł na listę, a nie rynek, na którym stoi.
#
# Pomiar 2026-07-27 na 296 rozliczonych typach (próg opłacalności 62,9%):
#   zwykłe        65,6%  (n=183)  -> nad kreską
#   matchup       54,3%  (n=35)
#   matchup_styl  45,7%  (n=46)
#   wyższa linia  47,0%  (n=66)
#   miękka linia  41,2%  (n=17)
# Czyli: model zarabia dokładnie wtedy, gdy typuje "nudno". Każda ścieżka
# dołożona po to, żeby znaleźć COŚ WIĘCEJ niż rynek (profil rywala, analogia
# stylu, ambitniejsza linia, rzekomy błąd tradera), oddaje pieniądze. Skoro
# rynki mają za to karę, kategorie muszą mieć taką samą — inaczej wystarczy
# przekleić stratny typ na inny rynek i brama go przepuszcza.
#
# Typ z kategorii w kwarantannie NIE znika: liczy się, uczy kalibrację
# i widać go w Skuteczności "w tle" (poza_publikacja="kwarantanna_kategorii").
#
# DZIURA ZAŁATANA 2026-07-29: brakowało tu `pewniak` — a to NAJWIĘKSZA
# kategoria ze wszystkich. Pomiar na 259 rozliczonych typach zawodniczych:
#   pewniak        n=136  weszło 51%  deklarował 71%  ROI −22%
#   z tego bez żadnej innej flagi  n=46  weszło 57%   ROI −21%
# Czyli ponad połowa typów stała poza bramą, która miała pilnować dokładnie
# tego: „każda ścieżka dołożona po to, żeby znaleźć COŚ WIĘCEJ niż rynek,
# oddaje pieniądze". `pewniak` jest taką ścieżką — wpuszcza typ na listę BEZ
# wymogu wartości, na samej wysokiej szansie.
#
# Powód, dla którego to widać dopiero teraz: raport uczenia pokazał, że model
# przestał typować „nudno". Udział typów bez żadnej flagi spadł ze 100%
# w pierwszej paczce do 5% w ostatniej, a liczba flag na typ urosła z 0,00
# do 1,89 — i dokładnie tym torem szła luka (−6 pp -> −20 pp).
KATEGORIE_KWARANTANNY = (
    "wyzsza_linia", "matchup_styl", "matchup", "miekka_linia", "rotacja",
    "pewniak",
)
KATEGORIE_NAZWY_PL = {
    "wyzsza_linia": "Ambitniejsza linia",
    "matchup_styl": "Podobny rywal w przeszłości",
    "matchup": "Słaby rywal na tym rynku",
    "miekka_linia": "Zaniżony kurs bukmachera",
    "rotacja": "Wraca do składu",
    "pewniak": "Najwyższa szansa w meczu",
}
# progi jak przy rynkach, tylko próba mniejsza: kategoria zbiera typy ze
# WSZYSTKICH rynków naraz, więc 12 rozliczeń mówi tu tyle, co 15 na rynku
KATEGORIA_MIN_N = 12
KATEGORIA_OKNO = 60


def _byla_w_kwarantannie(grp: list[dict]) -> bool:
    """Czy kategoria stała w kwarantannie w poprzednim cyklu (histereza)."""
    return any(
        r.get("poza_publikacja") == "kwarantanna_kategorii"
        for r in grp[-KWARANTANNA_HISTEREZA_OKNO:]
    )


def kategorie_kwarantanna(log: dict | None = None) -> dict[str, dict]:
    """Kategorie typów chwilowo poza publikacją (ROI okna poniżej progu).

    Zwraca {flaga: {roi, n, hit, sr_p, nazwa}} — dokładnie jak
    `rynki_kwarantanna`, z tą samą histerezą wejścia/wyjścia.
    """
    if log is None:
        log = _migruj_log(supa.get_key("typy_log") or {})
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and _z_modelu(r)
        and r.get("kurs") and float(r["kurs"]) > 1.0
    ]
    out: dict[str, dict] = {}
    for flaga in KATEGORIE_KWARANTANNY:
        grp = sorted(
            (r for r in settled if r.get(flaga)),
            key=lambda r: r.get("kickoff_ts") or 0,
        )[-KATEGORIA_OKNO:]
        if len(grp) < KATEGORIA_MIN_N:
            continue
        traf = sum(1 for r in grp if r["wynik"] == "wygrany")
        sr_p = sum(float(r["p_model"]) for r in grp) / len(grp)
        # ROI BRUTTO, ŚWIADOMIE (2026-07-31): kwarantanna to BRAMA, a bramy
        # zostają na brutto do czasu pomiaru — inaczej podatek przestawiłby
        # naraz i rachunek, i selekcję, i w rozliczeniach nie dałoby się
        # rozdzielić jednego od drugiego. Progi KWARANTANNA_ROI_* były
        # kalibrowane na brutto; ich przeliczenie to osobna decyzja.
        roi = sum(
            (float(r["kurs"]) - 1.0) if r["wynik"] == "wygrany" else -1.0
            for r in grp
        ) / len(grp)
        if roi < KWARANTANNA_ROI_WEJSCIE:
            wstrzymana = True
        elif roi > KWARANTANNA_ROI_WYJSCIE:
            wstrzymana = False
        else:
            wstrzymana = _byla_w_kwarantannie(grp)
        if wstrzymana:
            out[flaga] = {
                "roi": round(roi, 3), "n": len(grp),
                "hit": round(traf / len(grp), 3), "sr_p": round(sr_p, 3),
                "nazwa": KATEGORIE_NAZWY_PL.get(flaga, flaga),
            }
    return out


# --- KOREKTA STRUMIENIA: uczenie tego, czego kalibracja rynkowa NIE łapie ---
#
# Pomiar 2026-07-27 (patrz notatka „czy model robi postępy"): przez cały
# miesiąc opublikowane typy DEKLAROWAŁY 68–75% i trafiały 58%, a luka ani
# drgnęła — mimo że kalibracja rynkowa co cykl ściągała `p` mocno w dół
# (strzały −0,71 w logitach). Powód nie jest błędem średniej, tylko EFEKTEM
# SELEKCJI: korekta obniża szanse WSZYSTKICH kandydatów, po czym brama
# publikacji wybiera czub nowego rozkładu — czyli znowu najbardziej
# optymistyczne oszacowania. Kalibracja goni własny ogon.
#
# Ta korekta mierzy to, co ZOSTAJE PO całej kalibracji, na tym, co faktycznie
# opublikowaliśmy, i domyka pętlę: gdy strumień przeszacowuje, wszystkie jego
# szanse jadą w dół, więc przez bramę przechodzi mniej typów — i to tych
# naprawdę mocnych.
#
# STABILNOŚĆ PĘTLI: gdyby liczyć korektę z p_model już skorygowanego, po
# jednym cyklu luka zniknęłaby i korekta wyzerowałaby się, wracając do
# przeszacowania (klasyczne oscylowanie regulatora). Dlatego przy publikacji
# stemplujemy typ polem `kal_strumien` (użyta delta), a tutaj ODEJMUJEMY ją,
# żeby zawsze mierzyć na SUROWYM p.
KOREKTA_STRUMIENIA_OKNO = 120     # ostatnie N rozliczeń strumienia
KOREKTA_STRUMIENIA_MIN_N = 40     # poniżej tego nie ruszamy niczego
# CAP PODNIESIONY -0,80 -> -1,05 (2026-07-30). Pomiar na 120 ostatnich
# rozliczeniach: pełna potrzebna korekta pewniaków to −0,955, czyli STARY CAP
# BYŁ WIĄŻĄCY — świadomie publikowaliśmy typy zawyżone o kilka punktów, bo
# bezpiecznik nie pozwalał korekcie dojść tam, gdzie wskazują dane.
#
# Cap miał chronić przed wyzerowaniem listy i to była słuszna obawa w chwili,
# gdy powstawał. Dziś tę rolę pełnią dwie inne rzeczy, których wtedy nie było:
# osobna szansa pokazywana (`szansa_pokazywana`, liczona PO selekcji) oraz
# brama „ujemna po korekcie", która zdejmuje typ, gdy przestaje mieć wartość.
# Cap nie musi już udawać obu naraz — zostaje tylko bezpiecznikiem na absurdy.
#
# CO TO ZMIENIA W PRAKTYCE: typ, któremu model daje 70%, po pełnej korekcie
# pokazuje 47%. Przy kursie 1,50 to nie jest zakład i wypadnie; przy 2,30 —
# jest. Typy zawodnicze przesuwają się więc z niskich kursów na wyższe.
# To nie jest zawężenie produktu, tylko przeniesienie go tam, gdzie liczby
# się bronią.
KOREKTA_STRUMIENIA_CAP = (-1.05, 0.20)
# TŁUMIENIE: stosujemy POŁOWĘ zmierzonej reszty błędu, nie całość.
# Pomiar na żywym logu 2026-07-27 dał od razu −0,80 dla pewniaków (szansa 70%
# spada na 51%), co w jednym cyklu wyzerowałoby listę typów zawodniczych —
# a user postawił sprawę jasno: „nie może być tak, żeby było 6 typów".
# Ze stemplem `kal_strumien` korekta i tak dochodzi do pełnej wartości, tylko
# przez kilka cykli: każdy dokłada połowę tego, co ZOSTAŁO. Dzięki temu widać
# po drodze, ile typów kosztuje uczciwość, i można się zatrzymać.
KOREKTA_STRUMIENIA_TLUMIENIE = 0.5

# PRZEDZIAŁY SZANSY W KOREKCIE STRUMIENIA (2026-07-31).
#
# Do dziś korekta była JEDNĄ liczbą na strumień. Pomiar na 536 rozliczeniach
# pokazał, że to za mało, bo błąd modelu ZMIENIA ZNAK:
#
#   segment (w oknie zgody)        n    weszło  obiecywał     luka
#   powyżej zawodnicze  <1,9     118    68,6%    74,3%      −5,6 pp
#   powyżej drużynowe   <1,9      30    63,3%    74,3%     −11,0 pp
#   poniżej drużynowe   <1,9      43    81,4%    80,4%      +1,0 pp
#   poniżej drużynowe   >=1,9     24    62,5%    45,8%     +16,7 pp  <- w drugą stronę
#
# Jedna delta na strumień uśrednia przeszacowanie z niedoszacowaniem i psuje
# oba naraz. Przedziały liczone są po `p` modelu — tych samych, których używa
# kalibracja rynkowa (BIAS_PRZEDZIALY), żeby dało się je zsumować bin po binie
# (patrz build_wc_fast._dodaj_delte).
#
# Próg jest WYŻSZY niż przy kalibracji rynkowej (MIN_N_PRZEDZIAL=15), bo
# przedział strumienia dzieli i tak niewielką próbę na cztery. Poniżej progu
# przedział dostaje wartość globalną — czyli zachowuje się dokładnie jak
# dotąd. Dzięki temu zmiana rusza WYŁĄCZNIE tam, gdzie naprawdę zmierzyliśmy.
KOREKTA_PRZEDZIAL_MIN_N = 20

# DRABINKI mają własne, ostrzejsze warunki — z dwóch powodów:
#
# 1. PRÓBA. Strumień wystawia kilka kart dziennie, nie kilkadziesiąt typów:
#    na 29.07 miał 12 rozliczeń wobec 276 pewniaków. Przy wspólnym progu 40
#    „drabinki nie uczą się w ogóle" ([[czy-model-robi-postepy]]) byłoby
#    prawdą jeszcze przez wiele tygodni.
# 2. SKUTEK. Korekta wchodzi do `p_final`, a `p_final` jest jedyną bramą
#    karty (MIN_EDGE_KARTY). Pomiar z 29.07 (deklaracja 50%, trafienia 17%)
#    dałby po stłumieniu −0,80 logita, czyli szansę 50% -> 31% — przy takich
#    liczbach NIC nie przeszłoby przez bramę i zakładka Drabinki zgasłaby na
#    dobre. Przy n=12 przedział ufności trafień sięga jednak 48%, więc
#    zerowanie strumienia byłoby wnioskiem mocniejszym niż dane.
#
# Dlatego: niższy próg wejścia i węższy cap. Korekta i tak dochodzi do niego
# przez kilka cykli (tłumienie), więc widać po drodze, ile kart kosztuje.
# DO REWIZJI, gdy strumień uzbiera ~60 rozliczeń: wtedy cap ma iść w stronę
# tego, co mają typy modelu (−0,80).
KOREKTA_DRABINEK_MIN_N = 25
KOREKTA_DRABINEK_CAP = (-0.40, 0.20)

# ustawiane raz na cykl przez build_wc_fast (patrz `ustaw_korekte_strumienia`)
# — potrzebne, żeby zapisać przy typie deltę, z jaką został opublikowany
_KOREKTA_CYKLU: dict[str, float] = {}


def ustaw_korekte_strumienia(korekta: dict[str, float]) -> None:
    """Zapamiętaj korektę użytą w TYM cyklu (stempel na publikowanych typach)."""
    global _KOREKTA_CYKLU
    _KOREKTA_CYKLU = dict(korekta or {})


def _p_over_rekordu(r: dict) -> float:
    """`p_over` linii, na której stał ten typ — a NIE `p` samego typu.

    PO CO TO ISTNIEJE (błąd znaleziony 2026-07-31): przedziały kalibracji są
    WYSZUKIWANE po `p_over` (engine._select_bias dostaje `p_over`, ścieżka
    drużynowa woła `apply_bias(..., pred.p_over(linia))`), a MIERZONE były po
    `p` typu. Dla typu „poniżej" te dwie liczby są swoimi lustrami, więc
    rekord lądował w binie po przeciwnej stronie skali niż ten, do którego
    zostanie potem przyłożony.

    Czemu nikt tego nie zauważył: typy zawodnicze to w 100% strona „powyżej",
    gdzie `p` typu JEST `p_over` — więc na propsach błąd nie istnieje. Wychodzi
    dopiero na rynkach drużynowych, gdzie 76% typów to „poniżej" — czyli
    dokładnie tam, gdzie siedzi jedyny zyskowny segment.
    """
    p = _p_surowe(r)
    return 1.0 - p if r.get("strona") == "ponizej" else p


def _delta_zapisana(r: dict) -> float:
    """Stempel `kal_strumien` rekordu ZAWSZE jako liczba.

    NAPRAWA 2026-08-01. Od 31.07 korekta bywa rozkładem po przedziałach, a do
    księgi trafiał CAŁY ten słownik (patrz `_delta_stempla`). Każde miejsce,
    które robiło na stempu `float(...)`, wywalało się wtedy TypeError-em —
    a że `korekta_strumienia` i `szansa_pokazywana` stoją w cyklu w
    `try/except`, uczenie CICHO się wyłączało zamiast krzyczeć. W księdze
    zostało 87 takich rekordów, więc tolerancja dla starego kształtu musi
    zostać na stałe, nie „do czasu migracji".
    """
    d = r.get("kal_strumien")
    if isinstance(d, dict):
        p = float(r.get("p_model") or 0.0)
        p_over = p if r.get("strona") != "ponizej" else 1.0 - p
        d = betting.delta_dla_p(d, p_over)
    try:
        return float(d or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _p_surowe(r: dict) -> float:
    """p_model sprzed korekty strumienia — na tym mierzymy, żeby nie oscylować.

    ODWRACAMY TAM, GDZIE NAŁOŻONO (poprawka 2026-07-31). Korekta idzie na
    `p_over` i dopiero stamtąd lustrzy się na „poniżej" (p_under = 1 − p_over).
    Odejmowanie delty wprost od `p` typu „poniżej" NIE jest odwrotnością tej
    operacji — przesunięcie w logicie nie zachowuje się symetrycznie przy
    odbiciu. Skutek: dla rynków drużynowych, gdzie 76% typów to „poniżej",
    surowe `p` wychodziło błędne, a że to na nim mierzymy kolejną korektę,
    błąd wracał do modelu przy każdym cyklu.
    """
    p = float(r.get("p_model") or 0.0)
    d = _delta_zapisana(r)
    if not d:
        return p
    over = r.get("strona") != "ponizej"
    p_over = p if over else 1.0 - p
    p_over_sur = 1.0 / (1.0 + math.exp(-(_logit(p_over) - d)))
    return p_over_sur if over else 1.0 - p_over_sur


# --- ODCIĘCIE MARTWEJ EPOKI (2026-08-01) ---
#
# Nowe rynki (`match_`, `wiecej_`) były publikowane od 30.07 przez JEDNĄ bramę
# (EV ≥ 1%) — bez widełek kursu, bez progu pewności, bez przedziału i bez okna
# zgody z rynkiem. Bramy dopięto 31.07 o 15:37. Rekordy sprzed tej chwili
# opisują więc politykę, której już nie ma.
#
# Czemu to nie jest kosmetyka: te 18 rozliczeń trafiło 83,3% przy deklarowanych
# 57,6% (mediana kursu 1,87). Wpuszczone do korekty strumienia drużynowego
# przesuwają ją z −0,324 na −0,179 — czyli podnoszą szansę POKAZYWANĄ userowi
# przy każdym typie drużynowym, na podstawie osiemnastu rekordów z martwej
# reguły. Dokładnie ten błąd (mieszanie epok) kazał odwołać wniosek z 31.07.
#
# ROZPOZNANIE PO STEMPLU, nie po dacie: od 2026-08-01 każdy publikowany typ
# niesie `wersje` (patrz betting.wersje_publikacji). Nowy rynek BEZ stempla
# jest z martwej epoki. Reguła wygasa sama — gdy nowe rynki uzbierają własne
# rozliczenia pod dzisiejszymi bramami, wszystkie będą ostemplowane i warunek
# przestanie cokolwiek odrzucać.
#
# ZAKRES: wyłącznie warstwy UCZENIA, które sterują liczbą pokazywaną userowi
# (korekta strumienia i szansa pokazywana). Rozliczenie, ROI i skuteczność
# ZOSTAJĄ nietknięte — user te typy widział i wynik jest jego wynikiem.
def _z_martwej_epoki(r: dict) -> bool:
    """Nowy rynek opublikowany, zanim dopięto mu bramy jakości."""
    return (
        str(r.get("rynek_kod") or "").startswith(("match_", "wiecej_"))
        and not r.get("wersje")
    )


def korekta_strumienia(log: dict | None = None) -> dict[str, float]:
    """Delta logitowa per strumień: o ile ściągnąć szanse, żeby deklaracja
    zgadzała się z trafieniami. Zwraca {"pewniaki": -0.42, "druzyny": -0.11}.

    DRABINKI liczą się tą samą maszynerią, ale z własnym progiem i capem
    (patrz KOREKTA_DRABINEK_*) — mimo że stoją poza kalibracją modelu
    (`_z_modelu`). To jedyne sprzężenie zwrotne, jakie ten strumień ma:
    ich `p` pochodzi z pokrycia linii, a nie z silnika, więc kalibracja
    rynkowa nie ma czego w nich poprawiać.
    """
    if log is None:
        log = _migruj_log(supa.get_key("typy_log") or {})
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and r.get("p_model")
        and not _z_martwej_epoki(r)   # patrz komentarz przy `_z_martwej_epoki`
        # typy modelu ORAZ drabinki — każdy mierzony na SWOICH rozliczeniach,
        # nigdy wymieszany (pętla niżej rozdziela je po strumieniu)
        and (_z_modelu(r) or r.get("zrodlo") == ZRODLO_DRABINKA)
    ]
    out: dict[str, float] = {}
    for strumien in STRUMIENIE:
        drabinki = strumien == "drabinki"
        min_n = (
            KOREKTA_DRABINEK_MIN_N if drabinki else KOREKTA_STRUMIENIA_MIN_N
        )
        cap = KOREKTA_DRABINEK_CAP if drabinki else KOREKTA_STRUMIENIA_CAP
        grp = sorted(
            (r for r in settled if _strumien(r) == strumien),
            key=lambda r: r.get("kickoff_ts") or 0,
        )[-KOREKTA_STRUMIENIA_OKNO:]
        if len(grp) < min_n:
            continue
        b = _bias_logit([{**r, "p_model": _p_surowe(r)} for r in grp])
        # dochodzimy do pełnej korekty przez kilka cykli, nie w jednym skoku
        juz = [_delta_zapisana(r) for r in grp]
        srednia_juz = sum(juz) / len(juz)
        b = srednia_juz + KOREKTA_STRUMIENIA_TLUMIENIE * (b - srednia_juz)
        b = max(cap[0], min(cap[1], b))
        # DRABINKI zostają skalarem: ich `p` pochodzi z pokrycia linii, a nie
        # z silnika, więc przedziały `p` modelu nic tam nie znaczą — a próba
        # jest najmniejsza ze wszystkich strumieni.
        biny = [] if drabinki else _biny_korekty(grp, b, cap)
        # PRÓG SZUMU OBEJMUJE CAŁĄ STRUKTURĘ: strumień idealnie skalibrowany
        # ma MILCZEĆ, a nie zwracać słownik zer. Delty 0,0 byłyby nieszkodliwe
        # w rachunku, ale znaczą co innego niż brak wpisu — a na braku wpisu
        # opiera się „cisza, gdy model trafia".
        istotna = abs(b) >= 0.02 or any(abs(x) >= 0.02 for _, _, x in biny)
        if not istotna:
            continue
        if biny:
            out[strumien] = {"logit": True, "global": round(b, 3), "bins": biny}
        else:
            out[strumien] = round(b, 3)
    return out


# --- TEST W PRZÓD: drużynowe „poniżej", kurs 1,9+ (zarejestrowany 2026-08-01) ---
#
# PRE-REJESTRACJA LEŻY W REPO: docs/forward-test-druzynowe-ponizej.md.
# Tam są kryteria, reguła stopu i to, czego do zamknięcia testu nie wolno
# ruszać. Tutaj jest tylko licznik — celowo, żeby zmiana zasad wymagała
# edycji dokumentu, a nie cichej poprawki w kodzie.
#
# Krótko, po co to jest: segment „poniżej / drużynowe / kurs ≥1,9" jako jedyny
# w całym pomiarze 31.07 wyszedł na plus (n=24, ROI +48,8%, luka +16,7 pp).
# Dwie rzeczy nie pozwalają zrobić z tego zasady: próba jest mała ORAZ jedna
# warstwa modelu już się na niej uczyła (bin korekty `drużyny 0,00–0,55` to
# dokładnie ten segment). Dlatego liczymy WYŁĄCZNIE rekordy ze stemplem
# `wersje`, czyli opublikowane po 2026-08-01 — na tych model już się nie uczył.
FORWARD_TEST_CEL_N = 40
FORWARD_TEST_MIN_KURS = 1.90


def forward_test(log: dict | None = None) -> dict:
    """Licznik pre-zarejestrowanego testu w przód (patrz docs/ i komentarz).

    Zwraca kształt gotowy dla zakładki „Czy się uczymy": ile już mamy, ile
    trzeba, trafienia vs deklaracja i ROI po podatku. `gotowy=False` znaczy
    „za wcześnie na wnioski" — i tak ma być raportowane na stronie.
    """
    if log is None:
        log = _migruj_log(supa.get_key("typy_log") or {})
    grp = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and not r.get("poza_publikacja")
        and r.get("wersje")                      # tylko epoka po pre-rejestracji
        and _strumien(r) == "druzyny"
        and r.get("strona") == "ponizej"
        and float(r.get("kurs") or 0.0) >= FORWARD_TEST_MIN_KURS
        and r.get("p_model")
        and betting.w_oknie_zgody(
            float(r["p_model"]), float(r.get("kurs") or 0.0)
        )
    ]
    n = len(grp)
    if not n:
        return {"n": 0, "cel": FORWARD_TEST_CEL_N, "gotowy": False,
                "dokument": "docs/forward-test-druzynowe-ponizej.md"}
    trafione = sum(1 for r in grp if r["wynik"] == "wygrany")
    deklaracja = sum(float(r["p_model"]) for r in grp) / n
    zwrot = sum(_zwrot_typu(r) for r in grp)
    return {
        "n": n,
        "cel": FORWARD_TEST_CEL_N,
        "gotowy": n >= FORWARD_TEST_CEL_N,
        "trafione": trafione,
        "hit": round(trafione / n, 4),
        "deklaracja": round(deklaracja, 4),
        "luka_pp": round((trafione / n - deklaracja) * 100.0, 1),
        "roi": round(zwrot / n - 1.0, 4),
        "bilans_j": round(zwrot - n, 2),
        "dokument": "docs/forward-test-druzynowe-ponizej.md",
    }


# --- SKUTECZNOŚĆ PER ZDARZENIE, NIE PER WIERSZ (2026-08-01) ---
#
# Zgłoszenie usera: „czemu tu jest miliard typów?". Odpowiedź: bo ta sama
# rzecz siedziała w kilku liniach naraz.
#
#   Wisła Płock  rożne w meczu poniżej   6,5 / 7,5 / 13,5 / 14,5 / 15,5
#
# Padło 11 rożnych — „poniżej 13,5", „poniżej 14,5" i „poniżej 15,5" wchodzą
# RAZEM. To jeden wynik meczu, nie trzy zakłady. Publikacja została naprawiona
# (build_wc_fast: jedna linia na stronę), ale KSIĘGA ma już takie skupiska
# i będzie je miała zawsze — więc statystyka musi umieć je policzyć uczciwie.
#
# Zmierzone na 471 opublikowanych rozliczeniach:
#   per wiersz     n=471   trafia 57,1%   bilans −106,79u
#   per zdarzenie  n=349   trafia 53,0%   bilans  −86,07u
# Czyli zakładka pokazywała skuteczność ZAWYŻONĄ o 4 pp (zagnieżdżone
# „poniżej" dokładają tanie pewniaki) i jednocześnie bilans zaniżony, bo
# liczyła stawkę kilka razy tam, gdzie ryzyko było jedno.
#
# METODA: nie wybieramy „reprezentanta" (każdy wybór byłby arbitralny), tylko
# dzielimy JEDNĄ STAWKĘ na wszystkie linie zdarzenia — rekord ze skupiska
# o k liniach waży 1/k. Zdarzenie zawsze waży dokładnie jedną jednostkę,
# a informacja ze wszystkich linii zostaje wykorzystana.
def _zdarzenie(r: dict) -> tuple:
    """Ta sama rzecz: mecz + rynek + podmiot + strona. Różne tylko linie."""
    return (r.get("mecz_id"), r.get("rynek_kod"),
            rotowire._norm(str(r.get("podmiot") or "")), r.get("strona"))


def skutecznosc_zdarzen(recs: list[dict]) -> dict:
    """Trafienia i bilans liczone RAZ NA ZDARZENIE (patrz komentarz wyżej)."""
    grupy: dict[tuple, list[dict]] = {}
    for r in recs:
        grupy.setdefault(_zdarzenie(r), []).append(r)
    if not grupy:
        return {"n": 0, "wierszy": len(recs), "trafione": 0.0, "hit": None,
                "bilans_j": 0.0, "roi": None, "skupisk": 0}
    trafione = zwrot = 0.0
    for czlony in grupy.values():
        w = 1.0 / len(czlony)
        trafione += w * sum(1 for r in czlony if r.get("wynik") == "wygrany")
        zwrot += w * sum(_zwrot_typu(r) for r in czlony)
    n = len(grupy)
    return {
        "n": n,
        "wierszy": len(recs),
        "trafione": round(trafione, 2),
        "hit": round(trafione / n, 4),
        "bilans_j": round(zwrot - n, 2),
        "roi": round(zwrot / n - 1.0, 4),
        "skupisk": sum(1 for v in grupy.values() if len(v) > 1),
    }


def _biny_korekty(grp: list[dict], globalna: float, cap: tuple) -> list:
    """Delty per przedział szansy, ściągane do globalnej przy małej próbie.

    Zwraca [] gdy ŻADEN przedział nie ma własnego pomiaru — wtedy wołający
    zostaje przy jednej liczbie i nic się nie zmienia względem poprzedniej
    wersji. To jest celowe: przedziały mają włączać się same, gdy danych
    przybędzie, a nie od razu udawać wiedzę.
    """
    biny = []
    wlasne = 0
    for lo, hi in BIAS_PRZEDZIALY:
        bgrp = [r for r in grp if lo <= _p_over_rekordu(r) < hi]
        bb = globalna
        if len(bgrp) >= KOREKTA_PRZEDZIAL_MIN_N:
            k = len(bgrp) / (len(bgrp) + KOREKTA_PRZEDZIAL_MIN_N)
            surowy = _bias_logit(
                [{**r, "p_model": _p_surowe(r)} for r in bgrp]
            )
            bb = globalna + k * (surowy - globalna)
            wlasne += 1
        biny.append([lo, hi, round(max(cap[0], min(cap[1], bb)), 3)])
    return biny if wlasne else []


# --- SZANSA POKAZYWANA: co piszemy userowi na stronie (2026-07-29) ---
#
# Zgłoszenie usera: „skoro przy deklarowanych 71% trafiamy 58%, pokazywanie
# 71% jest nieuczciwe". Racja — i żadna z warstw uczenia tego nie naprawia,
# bo wszystkie działają PRZED bramą publikacji: obniżamy szanse wszystkich
# kandydatów, a brama i tak wybiera czub nowego rozkładu, więc opublikowany
# zbiór wraca do ~71% (efekt selekcji, patrz `korekta_strumienia`).
#
# Ta korekta jest inna w jednym kluczowym punkcie: działa PO selekcji i NIE
# WRACA do modelu. Mierzy dokładnie to, co user widzi — deklarację przy
# opublikowanych typach — i porównuje z tym, co weszło. Ponieważ nie zamyka
# pętli, nie ma czym oscylować: żadnego tłumienia i żadnego stempla nie
# potrzebuje (w odróżnieniu od korekty strumienia, gdzie jedno i drugie jest
# konieczne).
#
# Czego NIE dotyka:
#   * księgi typów — `p_model` w logu zostaje surowe, inaczej następny pomiar
#     liczyłby się z już poprawionej liczby i korekta zjadłaby własny ogon,
#   * puli legów kuponów — to WEJŚCIE do beam-searcha z progami bezwzględnymi
#     (kupony.py), więc przesunięcie szans zmieniłoby SKŁAD kuponów, a nie
#     tylko wyświetlaną liczbę; kupony mają zresztą własne urealnienie,
#     zmierzone na rozliczonych kuponach,
#   * kart Drabinek — te uczą się u źródła (radar `korekta_logit`), a karta
#     pokazuje jawnie rachunek „pokrycie × kontekst = szansa"; przesunięcie
#     samego wyniku rozjechałoby go z jego własnym uzasadnieniem.
SZANSA_POKAZ_MIN_N = 40      # poniżej tego nie ruszamy pokazywanej liczby
SZANSA_POKAZ_OKNO = 200      # okno kroczące rozliczeń
SZANSA_POKAZ_CAP = (-1.0, 0.30)


def szansa_pokazywana(
    log: dict | None = None,
    korekta_przed_brama: dict[str, float] | None = None,
) -> dict[str, float]:
    """Delta logitowa: o ile jeszcze ściągnąć liczbę pokazywaną na stronie.

    Liczona na OPUBLIKOWANYCH, rozliczonych typach — ale na `p` SUROWYM
    (sprzed korekty strumienia, patrz `_p_surowe`), a od wyniku odejmujemy to,
    co korekta strumienia robi JUŻ TERAZ, przed bramą publikacji.
    Bez tego odjęcia liczylibyśmy jedną rzecz dwa razy.

    Pomiar 2026-07-29 pokazuje, dlaczego to nie jest teoretyczna ostrożność:
    w księdze nie ma ANI JEDNEGO rozliczonego pewniaka ze stemplem
    `kal_strumien` (korekta ruszyła 27.07, a rynki zawodnicze stoją od tego
    czasu w kwarantannie). Surowy pomiar dawał −0,80, korekta przed bramą
    stoi na −0,48 — złożone naiwnie zrobiłyby −1,28 i z typu na 70% zostałoby
    39%. Po odjęciu wychodzi −0,33, czyli 70% -> 62%.

    Zwraca {"pewniaki": -0.33, "druzyny": -0.20}.
    """
    if log is None:
        log = _migruj_log(supa.get_key("typy_log") or {})
    if korekta_przed_brama is None:
        korekta_przed_brama = korekta_strumienia(log)
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and not r.get("poza_publikacja")     # user ich nie widział
        and r.get("rynek_kod") not in RYNKI_OSOBNE
        and r.get("p_model")
        and not _z_martwej_epoki(r)   # patrz komentarz przy `_z_martwej_epoki`
    ]
    out: dict[str, float] = {}
    for strumien in STRUMIENIE:
        grp = sorted(
            (r for r in settled if _strumien(r) == strumien),
            key=lambda r: r.get("kickoff_ts") or 0,
        )[-SZANSA_POKAZ_OKNO:]
        if len(grp) < SZANSA_POKAZ_MIN_N:
            continue
        # cały rozjazd względem SUROWEGO wyjścia modelu...
        b = _bias_logit([{**r, "p_model": _p_surowe(r)} for r in grp])
        # ...minus ta jego część, którą przed bramą załatwia już korekta
        # strumienia (dla typów w oknie bywała inna — stąd pomiar na surowym)
        # korekta bywa binowana (2026-07-31); tu nie znamy `p` konkretnego
        # typu, bo liczymy jedną liczbę na cały strumień — bierzemy część
        # globalną, czyli dokładnie to, czym była ta korekta wcześniej
        b -= betting.delta_globalna(korekta_przed_brama.get(strumien))
        b = max(SZANSA_POKAZ_CAP[0], min(SZANSA_POKAZ_CAP[1], b))
        if abs(b) >= 0.02:
            out[strumien] = round(b, 3)
    return out


# --- CZY BIJEMY CENĘ BUKMACHERA (2026-08-01) -------------------------------
#
# JEDYNE PYTANIE, KTÓRE NAPRAWDĘ DECYDUJE o tym, czy rynek ma dla nas sens:
# czy nasza liczba jest lepszą prognozą niż liczba wyciągnięta z samego kursu.
# Zysk bierze się z przewagi informacyjnej, nie z ustawienia progów — pomiar
# 2026-08-01 na 576 rozliczeniach pokazał, że oba fakty idą w parze:
#
#   team_goals/poniżej   nasz Brier 0,2169  vs  z kursu 0,2308   -> ROI  +8,5%
#   shots/powyżej        nasz Brier 0,2498  vs  z kursu 0,2149   -> ROI −26,3%
#   ŁĄCZNIE (n=576)      nasz 0,2441        vs  z kursu 0,2237
#
# Bijemy cenę w 2 rynkach na 9 — i zarabiamy dokładnie w tym, w którym bijemy
# ją wyraźnie. Wszystkie inne objawy (odwrócona pewność, anty-predykcyjna
# przewaga, brama zgody odrzucająca wszystko) to skutki tego jednego faktu.
#
# CZEMU BRIER, A NIE ROI: ROI ma ogromną wariancję (jeden kurs 3,5 przewraca
# bilans dziesiątek zakładów), więc kwarantanna po ROI miota się po dwóch
# pechowych weekendach. Brier mierzy jakość prognozy, nie szczęście, i
# rozstrzyga na kilkukrotnie mniejszej próbie.
#
# TO NIE JEST BRAMA. Wynik służy do UKŁADANIA KOLEJNOŚCI listy — rynek nie
# znika, tylko czeka niżej, aż model się go nauczy, i wraca sam.
PRZEWAGA_MIN_N = 25      # poniżej tego nie orzekamy nic (przewaga = 0)


def przewaga_rynkow(log: dict | None = None) -> dict[str, dict]:
    """Per (rynek, strona): o ile nasza prognoza bije prognozę z kursu.

    Zwraca `{"team_goals|ponizej": {"n":.., "brier_model":.., "brier_kurs":..,
    "przewaga":..}}`. `przewaga` dodatnia = wiemy więcej niż bukmacher.

    Wynik jest TŁUMIONY wielkością próby (`n/(n+MIN_N)`), żeby rynek z 26
    rozliczeniami nie przeskakiwał rynku ze 130 na jednym dobrym tygodniu.
    Rynki poniżej progu nie trafiają do wyniku wcale — czyli w sortowaniu
    dostają zero i lądują MIĘDZY tymi, które biją cenę, a tymi, które
    przegrywają. Brak danych nie jest winą.
    """
    if log is None:
        log = _migruj_log(supa.get_key("typy_log") or {})
    grupy: dict[tuple, list] = {}
    for r in log.values():
        if r.get("wynik") not in ("wygrany", "przegrany"):
            continue
        if r.get("sugestia") or r.get("odrzucony") or r.get("zrodlo"):
            continue
        if not r.get("kurs") or not r.get("p_model"):
            continue
        if _z_martwej_epoki(r):
            continue
        try:
            kurs = float(r["kurs"])
        except (TypeError, ValueError):
            continue
        if kurs <= 1.0:
            continue
        grupy.setdefault((r.get("rynek_kod"), r.get("strona")), []).append(r)

    out: dict[str, dict] = {}
    for (rynek, strona), v in grupy.items():
        if len(v) < PRZEWAGA_MIN_N:
            continue
        b_model = b_kurs = 0.0
        for r in v:
            trafil = 1.0 if r["wynik"] == "wygrany" else 0.0
            b_model += (float(r["p_model"]) - trafil) ** 2
            b_kurs += (
                betting.implied_prob_one_sided(float(r["kurs"])) - trafil
            ) ** 2
        n = len(v)
        b_model /= n
        b_kurs /= n
        out[f"{rynek}|{strona}"] = {
            "rynek_kod": rynek, "strona": strona, "n": n,
            "brier_model": round(b_model, 4),
            "brier_kurs": round(b_kurs, 4),
            # dodatnia = nasza prognoza lepsza; tłumiona próbą
            "przewaga": round((b_kurs - b_model) * (n / (n + PRZEWAGA_MIN_N)), 4),
        }
    return out


# PASMA CENY — drugi wymiar tego samego pytania (2026-08-01, zgłoszenie usera:
# „model ma znajdować pewne typy przy kursach 1,3 / 1,5 / 1,9 / 2,5 / 3").
#
# Zmierzone na 570 rozliczeniach: przewaga NIE rozkłada się równo po cenie.
#     1,19-1,35   cena mówi 74,1%, wchodzi 73,5%  -> bukmacher trafia CO DO
#                 PUNKTU; my mówimy 82,4% i tylko dokładamy szum
#     3,00-6,00   cena mówi 28,7%, wchodzi 44,8%  -> TU bijemy cenę (+25,6% ROI)
# Na drużynowych w paśmie 3,0+ cena mówi 29%, a wchodzi 52,6%.
#
# Stąd zasada: pasmo ceny wchodzi na listę wtedy, gdy UDOWODNI, że jesteśmy
# w nim lepsi od bukmachera — dokładnie tak samo jak rynek. Dziś to 3,0+;
# gdy model się poprawi, dojdą niższe. Nic nie jest zamknięte na stałe.
#
# CZEMU OSOBNO, A NIE JAKO TRZECI WYMIAR OBOK RYNKU I STRONY: rynek × strona
# × pasmo to ~54 komórki na 570 rozliczeń, czyli prawie wszystkie poniżej progu
# istotności. Mierzymy więc dwa sygnały niezależnie i sumujemy je przy
# układaniu listy.
PASMA_CENY = ((1.19, 1.35), (1.35, 1.60), (1.60, 1.90),
              (1.90, 2.30), (2.30, 3.00), (3.00, 6.01))


def przewaga_pasm(log: dict | None = None) -> dict[str, dict]:
    """To samo co `przewaga_rynkow`, ale w przekroju PASM CENY.

    Klucz to `"1.9-2.3"`. Dodatnia `przewaga` = w tym przedziale kursowym
    nasza liczba jest lepsza od ceny bukmachera.
    """
    if log is None:
        log = _migruj_log(supa.get_key("typy_log") or {})
    rek = []
    for r in log.values():
        if r.get("wynik") not in ("wygrany", "przegrany"):
            continue
        if r.get("sugestia") or r.get("odrzucony") or r.get("zrodlo"):
            continue
        if not r.get("kurs") or not r.get("p_model") or _z_martwej_epoki(r):
            continue
        try:
            kurs = float(r["kurs"])
        except (TypeError, ValueError):
            continue
        if kurs > 1.0:
            rek.append((r, kurs))

    out: dict[str, dict] = {}
    for lo, hi in PASMA_CENY:
        v = [r for r, k in rek if lo <= k < hi]
        if len(v) < PRZEWAGA_MIN_N:
            continue
        b_model = b_kurs = 0.0
        trafione = 0
        for r in v:
            trafil = 1.0 if r["wynik"] == "wygrany" else 0.0
            trafione += int(trafil)
            b_model += (float(r["p_model"]) - trafil) ** 2
            b_kurs += (
                betting.implied_prob_one_sided(float(r["kurs"])) - trafil
            ) ** 2
        n = len(v)
        b_model /= n
        b_kurs /= n
        out[f"{lo}-{hi}"] = {
            "od": lo, "do": hi, "n": n,
            "hit": round(trafione / n, 4),
            "brier_model": round(b_model, 4),
            "brier_kurs": round(b_kurs, 4),
            "przewaga": round((b_kurs - b_model) * (n / (n + PRZEWAGA_MIN_N)), 4),
        }
    return out


def przewaga_pasma_dla(kurs, pasma: dict[str, dict] | None) -> float:
    """Przewaga pasma, w którym leży ten kurs (0.0 = nie wiemy)."""
    if not pasma or not kurs:
        return 0.0
    try:
        k = float(kurs)
    except (TypeError, ValueError):
        return 0.0
    for v in pasma.values():
        if float(v["od"]) <= k < float(v["do"]):
            return float(v.get("przewaga") or 0.0)
    return 0.0


def urealnij_p(p: float, delta: float) -> float:
    """Szansa po korekcie pokazywanej (delta w skali logitowej)."""
    if not delta:
        return float(p)
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return 1.0 / (1.0 + math.exp(-(_logit(p) + delta)))


def kupon_do_pokazania(k: dict, urealnienie: dict[str, float] | None = None) -> dict:
    """Kupon z logu przygotowany do POKAZANIA — wartość przeliczona od nowa.

    JEDNA FUNKCJA DLA WSZYSTKICH PISARZY KLUCZA `kupony` (2026-08-01).
    Wcześniej mieszkała jako funkcja zagnieżdżona w `build_wc_fast`, więc
    stosował ją WYŁĄCZNIE duży cykl — a klucz `kupony` zapisuje też lekki job
    rozliczeniowy (`rozlicz_only`), co 20 minut, prosto z logu. Skutek zmierzony
    na produkcji: naprawa wartości netto z `d6df2d8` żyła na stronie około
    półtorej godziny, po czym lekki job przywracał kłamiące liczby (kupon 18–25
    znów pokazywał netto **+72,8%** przy wartości brutto −10,6%).

    Reguła, która z tego wynika: klucz widoku ma jedną funkcję normalizującą,
    nie jedną na job. Kto zapisuje `kupony`, woła to.

    Co robi:
    * WARTOŚĆ OD NOWA Z ZAMROŻONYCH LICZB. Kupony żyją w logu tygodniami, więc
      obok siebie leżą rekordy zamrożone przez różne wersje kodu. Jedna z nich
      korygowała `ev_pct`, ale zostawiała `ev_netto` policzone ze surowej
      szansy. Przeliczenie z `p_model` i `kurs_laczny` gwarantuje, że trzy
      liczby na karcie (szansa, kurs, wartość) zawsze się zgadzają.
    * SZANSA LEGÓW jak na liście typów — żeby ten sam typ nie pokazywał dwóch
      różnych szans dwa kliknięcia od siebie. Sam kupon ma WŁASNE urealnienie
      (`kupony._urealnij_szanse`), więc jego `p_model` zostaje nietknięte.

    Dotyczy WYŁĄCZNIE tego, co pokazujemy — log kuponów zostaje surowy.
    """
    p_k = k.get("p_model")
    kurs_k = k.get("kurs_laczny")
    if p_k and kurs_k:
        k = {
            **k,
            "ev_pct": round((float(p_k) * float(kurs_k) - 1.0) * 100.0, 1),
            "ev_netto": round(betting.ev_pct(
                float(p_k), float(kurs_k), k.get("tryb_podatku")), 1),
        }
    if not urealnienie:
        return k
    return {**k, "legi": [
        {**l, "p_model": round(urealnij_p(
            float(l["p_model"]), urealnienie.get(_strumien(l), 0.0),
        ), 4)} if l.get("p_model") else l
        for l in k.get("legi", [])
    ]}


def market_bias() -> dict[str, dict]:
    """Korekty kalibracyjne z logu w Supabase (puste, gdy brak danych/env)."""
    log = _migruj_log(supa.get_key("typy_log") or {})
    return compute_bias_full(log)


def market_bias_sugestie() -> dict[str, dict]:
    """Osobna kalibracja sugestii STS — liczona wyłącznie z rozliczonych
    sugestii, z szerszym capem w dół (przeszacowania rzędu 20 pp)."""
    log = _migruj_log(supa.get_key("typy_log") or {})
    return compute_bias_full(log, sugestie=True, cap=SUGESTIA_BIAS_CAP_LOGIT)


def compute_wagi_zaufania(log: dict) -> dict[str, dict]:
    """Pomiar zaufania do p_model per KUBEŁEK PEWNOŚCI (wysoka/średnia).

    Dla rozliczonych, publikowanych typów z kursem porównujemy: średnie
    p_model (deklarację modelu), średnią cenę rynku po devigu i realny
    hit-rate. Składanie kuponów miesza p_model z ceną rynku log-liniowo
    (kupony._p_skladania: p^w * r^(1-w)), więc DOCELOWĄ wagę w — taką, przy
    której mieszanka średnio trafiałaby w realny hit — wyznacza wprost:

        w* = (ln hit − ln r̄) / (ln p̄ − ln r̄)

    Zwraca surowy pomiar per kubełek {n, sr_p, sr_rynek, hit, w_cel};
    shrink do wag bazowych i cap stosuje kupony.wagi_zaufania_z_pomiaru
    (ten sam wzorzec co kary korelacji z diagnostyki).
    """
    out: dict[str, dict] = {}
    for kubelek in ("wysoka", "srednia"):
        grp = [
            r for r in log.values()
            if r.get("wynik") in ("wygrany", "przegrany")
            and not r.get("sugestia") and not r.get("odrzucony")
            and _z_modelu(r)   # waga zaufania dotyczy p_model, nie drabinek
            and r.get("kurs") and float(r["kurs"]) > 1.0
            and (r.get("pewnosc") or "srednia") == kubelek
        ]
        n = len(grp)
        if n < 5:
            continue
        sr_p = sum(float(r["p_model"]) for r in grp) / n
        sr_rynek = sum(
            betting.implied_prob_one_sided(float(r["kurs"])) for r in grp
        ) / n
        hit = sum(1 for r in grp if r["wynik"] == "wygrany") / n
        rec = {
            "n": n, "sr_p": round(sr_p, 3),
            "sr_rynek": round(sr_rynek, 3), "hit": round(hit, 3),
        }
        mianownik = math.log(max(sr_p, 1e-6)) - math.log(max(sr_rynek, 1e-6))
        if abs(mianownik) > 1e-3 and 0.0 < hit < 1.0:
            w = (math.log(hit) - math.log(max(sr_rynek, 1e-6))) / mianownik
            # w>1 = model lepszy niż sam deklaruje (rzadkie), w<0 = gorszy
            # niż rynek; sensowny zakres ucinamy, resztę robi shrink+cap
            rec["w_cel"] = round(min(max(w, 0.0), 1.2), 3)
        out[kubelek] = rec
    return out


def compute_diagnostyka(log: dict) -> dict:
    """Samokontrola modelu z rozliczeń: Brier / log-loss per kategoria typów.

    Kategorie nie wykluczają się (typ bywa matchup i pewniak naraz);
    "zwykle" = bez żadnej flagi specjalnej. Dodatkowo skuteczność sygnałów
    składu — P(zagrał | sygnał XI) — do przyszłej kalibracji modelu minut
    (od n>=40 na sygnał można zastąpić ręczne wagi zmierzonymi).
    """
    # typy pomiarowe (odrzucone przy progu) NIE wchodzą do kategorii jakości
    # modelu — mają własną kategorię porównawczą niżej
    wszystkie_settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany") and _z_modelu(r)
    ]
    settled = [r for r in wszystkie_settled if not r.get("odrzucony")]

    def _stats(grp: list[dict]) -> dict | None:
        n = len(grp)
        if not n:
            return None
        brier = ll = 0.0
        traf = 0
        for r in grp:
            p = min(max(float(r["p_model"]), 1e-6), 1.0 - 1e-6)
            y = 1.0 if r["wynik"] == "wygrany" else 0.0
            brier += (p - y) ** 2
            ll += -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))
            traf += int(y)
        sr_p = sum(float(r["p_model"]) for r in grp) / n
        return {
            "n": n, "trafione": traf, "hit": round(traf / n, 3),
            "sr_p": round(sr_p, 3),
            "brier": round(brier / n, 4), "logloss": round(ll / n, 4),
        }

    FLAGI = ("sugestia", "matchup", "matchup_styl", "rotacja",
             "wyzsza_linia", "miekka_linia")
    kategorie = {
        "wszystkie": settled,
        "zwykle": [r for r in settled if not any(r.get(f) for f in FLAGI)],
        "matchup": [r for r in settled if r.get("matchup")],
        # pełne matchupy STYLU (model/styl.py + matchup.py) — mierzone osobno
        # od "matchup" (profil koncesji rywala); wdrożone 2026-07-14, ocena
        # czy analogie stylu zarabiają możliwa dopiero od n>=~25
        "matchup_styl": [r for r in settled if r.get("matchup_styl")],
        "rotacja": [r for r in settled if r.get("rotacja")],
        "wyzsza_linia": [r for r in settled if r.get("wyzsza_linia")],
        "miekka_linia": [r for r in settled if r.get("miekka_linia")],
        "sugestie": [r for r in settled if r.get("sugestia")],
        # POMIAR PROGÓW: jak trafiają typy odrzucone tuż przy progu vs
        # przepuszczone — dopiero ta para liczb uzasadnia ruszanie progów
        "odrzucone_pomiar": [
            r for r in wszystkie_settled if r.get("odrzucony")
        ],
    }
    out: dict = {"kategorie": {}}
    for nazwa, grp in kategorie.items():
        s = _stats(grp)
        if s:
            out["kategorie"][nazwa] = s
    # pomiar wag zaufania per kubełek pewności — raport w typy_wyniki
    # (stosowanie: kupony.wagi_zaufania_z_pomiaru w build_wc_fast)
    out["wagi_zaufania"] = compute_wagi_zaufania(log)
    sklady: dict[str, list[int]] = {}
    for r in log.values():
        if r.get("zagral") is None:
            continue
        s = r.get("xi_sygnal") or "brak"
        d = sklady.setdefault(str(s), [0, 0])
        d[1] += 1
        d[0] += int(bool(r["zagral"]))
    out["sklady"] = {
        k: {"zagral": a, "n": b, "pct": round(a / b, 3)}
        for k, (a, b) in sklady.items()
    }
    # KALIBRACJA marży konsensusu UK (betting.UK_CONSENSUS_MARGIN, dziś założona):
    # dla rozliczonych okazji „powyżej" z kursem UK porównaj implikowane p rynku
    # (1/kurs_ref) do realnej częstości trafień. marża_est = 1 − hit/implied_sr.
    # Gdy marza_est zauważalnie różni się od używanej przy n>=~30 — podmień stałą.
    uk = [
        r for r in settled
        if r.get("kurs_ref") and float(r["kurs_ref"]) > 1.0
        and not r.get("sugestia") and r.get("strona") == "powyzej"
    ]
    if uk:
        n_uk = len(uk)
        hit_uk = sum(1 for r in uk if r["wynik"] == "wygrany") / n_uk
        implied_sr = sum(1.0 / float(r["kurs_ref"]) for r in uk) / n_uk
        marza_est = round(1.0 - hit_uk / implied_sr, 3) if implied_sr > 0 else None
        out["marza_uk"] = {
            "n": n_uk,
            "hit": round(hit_uk, 3),
            "implied_sr": round(implied_sr, 3),
            "marza_est": marza_est,
            "marza_uzywana": betting.UK_CONSENSUS_MARGIN,
        }
    return out


# pomin_powod TECHNICZNE: stary kupon żyje dalej jako NOWY rekord w tym samym
# slocie (wymiana lega) albo zostanie zastąpiony w tym samym cyklu (przebudowa
# po składach) — jego legi i tak trafią do nauki przez ten nowy wariant, więc
# licząc OBA (stary+nowy) podwójnie ważylibyśmy te same/prawie te same legi.
_POMIN_POWOD_TECHNICZNE = ("wymiana lega", "przebudowa po składach")


def _kupon_liczy_sie_do_nauki(k: dict) -> bool:
    """Czy kupon wchodzi do korelacji/kalibracji per-kupon (nauka).

    Kupony NIGDY nie pominięte oczywiście się liczą. Z pominiętych liczą się
    user-pominięte ("nie zagrałem") i WŁASNE (generator „ucz model") — obie
    mają realne, rozliczone wyniki i są PO TO, żeby zasilać ten mechanizm
    (patrz kupony_wlasne wyżej — user explicite godzi się uczyć model).
    NIE liczą się: stare sloty po zmianie konfiguracji (nie odzwierciedlają
    żadnej realnej decyzji) i techniczne pominięcia (patrz wyżej)."""
    if not k.get("pominiety"):
        return True
    if k.get("pominiety_przez") == "konfiguracja":
        return False
    if k.get("pomin_powod") in _POMIN_POWOD_TECHNICZNE:
        return False
    return True


def compute_kupony_diagnostyka(log_kuponow: dict) -> dict:
    """Uczenie KUPONÓW z rozliczeń (domyka pętlę, której nie zamyka kalibracja
    per-typ):

    1. KALIBRACJA — czy kupon o deklarowanej szansie X% trafia ~X% (per horyzont).
       Rozjazd hit << sr_p oznacza, że kara korelacji za słabo tnie szansę
       (kupony systematycznie przeszacowane) — i odwrotnie.
    2. Zmierzona KORELACJA legów z jednego meczu: czy padają razem CZĘŚCIEJ
       (wsp > 1) czy RZADZIEJ (wsp < 1) niż niezależność (iloczyn p_model).
       To dane pod zastąpienie ZGADYWANYCH kar (0.92 / 0.95 / 0.97) zmierzonymi:
       wsp < 1 potwierdza karę w dół, wsp > 1 mówi, że karzemy w złą stronę.

    Włącza user-pominięte i WŁASNE kupony (mają realne rozliczone wyniki —
    to one najbardziej cierpią na agresywne pomijanie, więc wykluczenie ich
    tu osłabiałoby dokładnie ten mechanizm, który ma naprawić przeszacowanie
    kuponów). Wyklucza tylko stare sloty po zmianie konfiguracji i techniczne
    pominięcia (wymiana lega / przebudowa po składach) — patrz
    _kupon_liczy_sie_do_nauki.
    """
    settled = [
        k for k in log_kuponow.values()
        if isinstance(k, dict) and _kupon_liczy_sie_do_nauki(k)
        and k.get("wynik") in ("wygrany", "przegrany")
    ]

    per_h: dict[str, dict] = {}
    for k in settled:
        h = k.get("horyzont") or "value"
        d = per_h.setdefault(h, {"n": 0, "traf": 0, "sp": 0.0, "brier": 0.0})
        y = 1.0 if k["wynik"] == "wygrany" else 0.0
        p = min(max(float(k.get("p_model") or 0.0), 1e-6), 1.0 - 1e-6)
        d["n"] += 1
        d["traf"] += int(y)
        d["sp"] += p
        d["brier"] += (p - y) ** 2
    kalibracja = {
        h: {
            "n": d["n"], "hit": round(d["traf"] / d["n"], 3),
            "sr_p": round(d["sp"] / d["n"], 3),
            "brier": round(d["brier"] / d["n"], 4),
        }
        for h, d in per_h.items() if d["n"]
    }

    # pary legów z tego samego meczu: [oba_wygrane, n_par, suma_iloczynu_p]
    grp = {"ta_sama": [0, 0, 0.0], "przeciwne": [0, 0, 0.0], "nieznane": [0, 0, 0.0]}
    kary = {
        "ta_sama": kupony_model.KARA_TA_SAMA_DRUZYNA,
        "przeciwne": kupony_model.KARA_PRZECIWNE_DRUZYNY,
        "nieznane": kupony_model.KARA_KORELACJI,
    }
    for k in settled:
        legi = [
            l for l in k.get("legi", [])
            if l.get("wynik") in ("wygrany", "przegrany")
        ]
        for i in range(len(legi)):
            for j in range(i + 1, len(legi)):
                a, b = legi[i], legi[j]
                if a.get("mecz_id") != b.get("mecz_id"):
                    continue
                da, db = str(a.get("druzyna") or ""), str(b.get("druzyna") or "")
                if da and db and da == db:
                    rel = "ta_sama"
                elif da and db and da != db:
                    rel = "przeciwne"
                else:
                    rel = "nieznane"
                g = grp[rel]
                g[0] += int(a["wynik"] == "wygrany" and b["wynik"] == "wygrany")
                g[1] += 1
                g[2] += float(a.get("p_model") or 0) * float(b.get("p_model") or 0)
    korelacja = {}
    for rel, (oba, n, sexp) in grp.items():
        if n < 1:
            continue
        obs = oba / n
        exp = sexp / n
        korelacja[rel] = {
            "n_par": n, "obs_oba": round(obs, 3), "exp_indep": round(exp, 3),
            "wsp": round(obs / exp, 3) if exp > 0 else None,
            "kara_uzywana": kary[rel],
        }
    return {"kalibracja": kalibracja, "korelacja": korelacja}


def _snapshot_zamkniecia(
    log: dict, value_bets: list[dict], kupony_list: list[dict], now: int
) -> None:
    """CLV: kurs zamknięcia = ostatni kurs widziany PRZED startem meczu.

    Cykl chodzi co ~30 min, więc nadpisujemy snapshot do kickoffu — po meczu
    zostaje ostatnia wycena rynku. Porównanie "kurs wzięty przy publikacji vs
    zamknięcie" to najszybszy miernik, czy typy biją rynek (dodatnie CLV
    wygrywa długoterminowo, nawet gdy krótka seria jest na minusie).
    """
    kursy_teraz: dict[str, float] = {}
    for b in value_bets:
        if b.get("kurs"):
            kursy_teraz[_klucz(b)] = float(b["kurs"])
    for k in kupony_list:
        for l in k["legi"]:
            if l.get("kurs"):
                kursy_teraz.setdefault(_klucz(l), float(l["kurs"]))
    for kk, rec in log.items():
        if not rec.get("wynik") and rec["kickoff_ts"] > now and kk in kursy_teraz:
            rec["kurs_zamkniecia"] = kursy_teraz[kk]


def _sloty_aktualne() -> set[str]:
    """Sloty wynikające z AKTUALNEJ konfiguracji przedziałów kursowych —
    na stronie wisi maks. jeden kupon na przedział (user: razem max 4
    dzienne i max 4 długoterminowe)."""
    et = kupony_model.etykieta_celu
    return (
        {f"dzienny:{et(a, b)}" for a, b in kupony_model.PRZEDZIALY_DZIENNE}
        | {f"dlugoterminowy:{et(a, b)}"
           for a, b in kupony_model.PRZEDZIALY_DLUGOTERMINOWE}
        | {f"value:{et(a, b)}" for a, b in kupony_model.PRZEDZIALY_VALUE}
    )


def _sygnatura_legow(legi: list[dict]) -> frozenset:
    return frozenset(
        (l["mecz_id"], l["podmiot"], l.get("rynek_kod", ""), l["linia"], l["strona"])
        for l in legi
    )


# capy wariantów kluczy per slot/dzień — bez nich seryjne pomijanie/wymiany
# rozdymały log (#2/#3/... bez końca) i koszt skanów Jaccard przy publikacji
MAX_WARIANTOW_DNIA = 10
# zapas na obstawienie — jedno źródło prawdy (model/kupony.py)
MARGINES_STARTU_S = kupony_model.MARGINES_STARTU_S
MAX_WYMIAN_DNIA = 5


def _kupon_do_logu(
    log_kuponow: dict,
    kupony_list: list[dict],
    now: int,
    niedostepni: set[int] | None = None,
    pominiete: set[str] | None = None,
    powody: dict[str, str] | None = None,
    wymiany: set[str] | None = None,
    przebudowy: set[str] | None = None,
    conf_mids: set[int] | None = None,
    legi_pool: list[dict] | None = None,
) -> None:
    """Cykl życia kuponu — przemyślany raz, potem ZAMROŻONY.

    Zasady (decyzja usera):
      * kupon po pierwszej publikacji się NIE zmienia (koniec z typami
        znikającymi między cyklami),
      * jedyny powód unieważnienia: potwierdzone składy wywróciły lega
        (zawodnik poza XI, a jego mecz jeszcze się nie zaczął) -> stary kupon
        dostaje wynik "anulowany" z powodem, a slot się zwalnia,
      * nowy kupon w danym slocie (horyzont+przedział) powstaje TYLKO, gdy
        poprzedni jest rozliczony (wygrany/przegrany), anulowany albo
        POMINIĘTY przez usera (przycisk w UI — klucz w `kupony_pominiete`);
        pominięty kupon znika z aktywnych, ale rozlicza się dalej w tle,
        żeby model uczył się także z niezagranych kuponów,
      * do zwolnionego przez pominięcie slotu nie wraca IDENTYCZNY zestaw
        legów — czekamy, aż pula da inny kupon,
      * nie publikujemy kuponu, którego pierwszy mecz już trwa.
    """
    niedostepni = niedostepni or set()
    pominiete = pominiete or set()
    dzien = time.strftime("%Y-%m-%d", time.localtime(now))

    # migracja starych rekordów (klucz = "horyzont:przedział:data")
    for key, rec in log_kuponow.items():
        rec.setdefault("slot", ":".join(key.split(":")[:2]))
        rec.setdefault("klucz", key)

    # 1) unieważnij aktywne kupony, którym ogłoszone składy wywróciły lega
    for rec in log_kuponow.values():
        if rec.get("wynik"):
            continue
        poza = [
            l for l in rec["legi"]
            if l.get("podmiot_id") in niedostepni and l["kickoff_ts"] > now
        ]
        if poza:
            rec.update(
                wynik="anulowany", rozliczono_ts=now,
                powod="zmiana składu: " + ", ".join(l["podmiot"] for l in poza),
            )

    # 1b) kupony pominięte przez usera: zwalniają slot, ale wynik zostaje
    # pusty — legi i kupon rozliczą się normalnie (dane do nauki modelu)
    for rec in log_kuponow.values():
        if rec.get("klucz") in pominiete and not rec.get("pominiety"):
            rec["pominiety"] = True
            rec["pominieto_ts"] = now
            rec["pominiety_przez"] = "user"
            rec["pomin_powod"] = (powody or {}).get(rec.get("klucz"))

    # 1b2) PRZYWRACANIE: user cofnął pominięcie (klucz zniknął z
    # kupony_pominiete) — wraca, o ile slot nie został już zajęty nowszym
    zajete_teraz = {
        r["slot"] for r in log_kuponow.values()
        if not r.get("wynik") and not r.get("pominiety")
    }
    # kolejność DETERMINISTYCZNA: przy dwóch kandydatach do tego samego slotu
    # wraca najdawniej pominięty (potem tie-break po kluczu) — wcześniej
    # decydowała przypadkowa kolejność iteracji po dict
    do_przywrocenia = sorted(
        (
            rec for rec in log_kuponow.values()
            if rec.get("pominiety")
            and rec.get("pominiety_przez") == "user"
            and not rec.get("wynik")
            and rec.get("klucz") not in pominiete
            and rec.get("pomin_powod")
            not in ("wymiana lega", "przebudowa po składach")
        ),
        key=lambda r: (r.get("pominieto_ts") or 0, r.get("klucz") or ""),
    )
    for rec in do_przywrocenia:
        if rec.get("slot") in zajete_teraz:
            continue
        rec["pominiety"] = False
        rec.pop("pominieto_ts", None)
        rec.pop("pominiety_przez", None)
        rec.pop("pomin_powod", None)
        zajete_teraz.add(rec["slot"])

    # 1b3) WYMIANA LEGA jednym klikiem: pomiń bieżący kupon i opublikuj
    # w jego slocie wariant z alternatywą rentgena (kurs_po / p_po już
    # policzone z karą korelacyjną)
    for rec in list(log_kuponow.values()):
        kl = rec.get("klucz")
        if (
            kl not in (wymiany or set())
            or rec.get("wynik") or rec.get("pominiety")
            or not rec.get("alternatywa")
        ):
            continue
        alt = rec["alternatywa"]
        idx = int(alt.get("zamiast_idx") or 0)
        alt_leg = {
            k2: v for k2, v in alt.items()
            if k2 not in ("zamiast_idx", "kurs_po", "p_po")
        }
        kurs_po = float(alt.get("kurs_po") or 0) or None
        p_po = float(alt.get("p_po") or 0) or None
        # ŚWIEŻA wycena wymienianego lega z bieżącej puli — alternatywa była
        # liczona przy publikacji i jej kurs/p potrafią być nieaktualne.
        # Kara korelacji zależy tylko od zestawu, więc skalowanie zamrożonych
        # kurs_po/p_po ilorazem świeżych i zamrożonych wartości lega jest
        # dokładne. Gdy lega nie ma już w ofercie, wymiana jest niewykonalna
        # i kupon zostaje bez zmian (zamiast pominięcia w ciemno).
        if legi_pool is not None:
            fresh = next(
                (
                    b for b in legi_pool
                    if b.get("mecz_id") == alt_leg.get("mecz_id")
                    and b.get("podmiot_id") == alt_leg.get("podmiot_id")
                    and b.get("rynek_kod") == alt_leg.get("rynek_kod")
                    and abs(float(b.get("linia") or 0)
                            - float(alt_leg.get("linia") or 0)) < 1e-6
                    and b.get("strona") == alt_leg.get("strona")
                ),
                None,
            )
            if fresh is None:
                continue
            if kurs_po and float(alt_leg.get("kurs") or 0) > 0:
                kurs_po = kurs_po * float(fresh["kurs"]) / float(alt_leg["kurs"])
            if p_po and float(alt_leg.get("p_model") or 0) > 0:
                p_po = p_po * float(fresh["p_model"]) / float(alt_leg["p_model"])
            alt_leg = {**alt_leg, "kurs": fresh["kurs"],
                       "p_model": fresh["p_model"]}
        legi = [dict(l) for i, l in enumerate(rec["legi"]) if i != idx]
        legi.append(alt_leg)
        legi.sort(key=lambda l: (l["kickoff_ts"], l["mecz_id"], -l["p_model"]))
        if min(l["kickoff_ts"] for l in legi) <= now + MARGINES_STARTU_S:
            continue  # pierwszy mecz za chwilę — za późno na wymianę
        if not kurs_po or not p_po:
            continue  # bez wyceny nie publikujemy — kupon zostaje bez zmian
        klucz_n, n = f"{rec['slot']}:{dzien}#w", 2
        while klucz_n in log_kuponow:
            klucz_n, n = f"{rec['slot']}:{dzien}#w{n}", n + 1
        if n > MAX_WYMIAN_DNIA + 2:
            continue  # cap wariantów wymiany na slot/dzień — log nie puchnie
        rec.update(pominiety=True, pominieto_ts=now,
                   pominiety_przez="user", pomin_powod="wymiana lega")
        log_kuponow[klucz_n] = {
            **{k2: rec[k2] for k2 in ("cel", "cel_label", "styl", "horyzont")
               if k2 in rec},
            "kurs_laczny": round(kurs_po, 2), "p_model": round(p_po, 4),
            "fair_kurs": round(1.0 / max(p_po, 1e-9), 2),
            "ev_pct": round((p_po * kurs_po - 1.0) * 100.0, 1),
            # wariant po wymianie lega musi nieść to samo, co kupon oryginalny
            # — inaczej jedyny kupon w logu bez trybu rozliczyłby się inaczej
            "ev_netto": round(betting.ev_pct(p_po, kurs_po), 1),
            "tryb_podatku": rec.get("tryb_podatku")
                            or betting.TRYB_PODATKU_DOMYSLNY,
            "legi": legi, "slot": rec["slot"], "klucz": klucz_n,
            "dzien": dzien, "opublikowano_ts": now, "wynik": None,
            "z_wymiany": True,
        }

    # 1b4) PRZEBUDOWA PO SKŁADACH (opt-in): pomiń, gdy WSZYSTKIE mecze legów
    # mają potwierdzone XI — builder w tym samym cyklu złoży nowy kupon już
    # na pewnych składach
    for rec in log_kuponow.values():
        if (
            rec.get("klucz") in (przebudowy or set())
            and not rec.get("wynik") and not rec.get("pominiety")
        ):
            mids = {l["mecz_id"] for l in rec["legi"]}
            if mids and mids <= (conf_mids or set()):
                rec.update(pominiety=True, pominieto_ts=now,
                           pominiety_przez="user",
                           pomin_powod="przebudowa po składach")

    # 1c) sloty wycofane (zmiana konfiguracji przedziałów): aktywny kupon ze
    # starego przedziału schodzi z widoku jak pominięty i rozlicza się w tle
    # — na stronie zostaje maks. JEDEN kupon na każdy aktualny przedział
    aktualne_sloty = _sloty_aktualne()
    for rec in log_kuponow.values():
        if (
            not rec.get("wynik")
            and not rec.get("pominiety")
            and rec.get("slot") not in aktualne_sloty
        ):
            rec["pominiety"] = True
            rec["pominieto_ts"] = now
            rec["pominiety_przez"] = "konfiguracja"

    # 2) nowe kupony wyłącznie do wolnych slotów
    zajete = {
        r["slot"] for r in log_kuponow.values()
        if not r.get("wynik") and not r.get("pominiety")
    }
    # zestawy legów pominiętych, jeszcze nierozliczonych kuponów per slot —
    # user właśnie je odrzucił, nie publikujemy ich ponownie 1:1; pominięcia
    # TECHNICZNE (wymiana/przebudowa/zmiana konfiguracji) nie blokują puli
    odrzucone: dict[str, set[frozenset]] = {}
    for r in log_kuponow.values():
        if (
            r.get("pominiety") and not r.get("wynik")
            and r.get("pominiety_przez") != "konfiguracja"
            and r.get("pomin_powod")
            not in ("wymiana lega", "przebudowa po składach")
        ):
            odrzucone.setdefault(r["slot"], set()).add(_sygnatura_legow(r["legi"]))
    for k in kupony_list:
        if not k.get("legi"):
            continue
        slot = f"{k.get('horyzont', '?')}:{k.get('cel_label', k.get('cel'))}"
        if slot in zajete:
            continue  # poprzedni kupon wciąż w grze — nie podmieniamy go
        if min(l["kickoff_ts"] for l in k["legi"]) <= now + MARGINES_STARTU_S:
            continue  # pierwszy mecz startuje za mało czasu na obstawienie
        if any(l.get("podmiot_id") in niedostepni for l in k["legi"]):
            continue  # leg z zawodnikiem poza składem — czekaj na kolejny cykl
        sygn = _sygnatura_legow(k["legi"])
        # user właśnie pominął ten zestaw — nie wraca ani identyczny, ani
        # prawie identyczny (Jaccard >= 0.7, np. 7 legów z 1 zamianą)
        if any(
            len(sygn & odrz) / max(len(sygn | odrz), 1) >= 0.7
            for odrz in odrzucone.get(slot, set())
        ):
            continue
        klucz, n = f"{slot}:{dzien}", 2
        while klucz in log_kuponow:
            klucz, n = f"{slot}:{dzien}#{n}", n + 1
        if n > MAX_WARIANTOW_DNIA + 2:
            continue  # cap publikacji na slot/dzień — chroni log i skan Jaccard
        log_kuponow[klucz] = {
            **k, "slot": slot, "klucz": klucz, "dzien": dzien,
            "opublikowano_ts": now, "wynik": None,
        }
        zajete.add(slot)


def _rozlicz_kupony(log_kuponow: dict, typy_log: dict, now: int) -> list[dict]:
    """Wynik kuponu z wyników legów: przegrany od pierwszego pudła; wygrany,
    gdy wszystkie legi trafione (zwrot wyłącza lega z kursu, jak u buka)."""
    for rec in log_kuponow.values():
        statusy = []
        for l in rec["legi"]:
            tk = (f"{l['mecz_id']}:{rotowire._norm(str(l['podmiot']))}:"
                  f"{l.get('rynek_kod', '')}:{l['linia']}:{l['strona']}")
            s = (typy_log.get(tk) or {}).get("wynik")
            # status lega zapisany w kuponie — podgląd kuponu w historii
            # pokazuje, które legi siadły (także dla już rozliczonych)
            l["wynik"] = s
            statusy.append((l, s))
        rec["legi_trafione"] = sum(1 for _, s in statusy if s == "wygrany")
        rec["legi_rozliczone"] = sum(1 for _, s in statusy if s)
        # superzmiana potrafi odwrócić lega PO rozliczeniu kuponu: gdy po
        # rewizji wszystkie legi siadły, przegrany kupon wraca do wygranego
        if (
            rec.get("wynik") == "przegrany"
            and statusy
            and all(s in ("wygrany", "zwrot") for _, s in statusy)
        ):
            kurs = 1.0
            for l, s in statusy:
                if s == "wygrany" and l.get("kurs"):
                    kurs *= l["kurs"]
            rec.update(wynik="wygrany", kurs_rozliczony=round(kurs, 2),
                       rozliczono_ts=now,
                       powod="superzmiana odwróciła przegranego lega")
            continue
        if rec.get("wynik"):
            continue
        if any(s == "przegrany" for _, s in statusy):
            rec.update(wynik="przegrany", rozliczono_ts=now)
        elif all(s in ("wygrany", "zwrot") for _, s in statusy):
            kurs = 1.0
            for l, s in statusy:
                if s == "wygrany":
                    kurs *= l["kurs"]
            # same zwroty = stawka wraca (kurs 1.0), nie "wygrany"
            wynik = "wygrany" if any(s == "wygrany" for _, s in statusy) else "zwrot"
            rec.update(wynik=wynik, kurs_rozliczony=round(kurs, 2),
                       rozliczono_ts=now)
    return sorted(
        log_kuponow.values(),
        key=lambda r: (-(r.get("opublikowano_ts") or 0)),
    )[:40]


def _typ_dnia(r: dict) -> dict:
    """Odchudzony typ do listy dziennej (co siadło danego dnia)."""
    return {
        "mecz": r.get("mecz"), "kickoff_ts": r.get("kickoff_ts"),
        "podmiot": r.get("podmiot"), "rynek_kod": r.get("rynek_kod"),
        "rynek": r.get("rynek"), "linia": r.get("linia"),
        "strona": r.get("strona"), "kurs": r.get("kurs"),
        "p_model": r.get("p_model"), "wynik": r.get("wynik"),
        "faktyczna": r.get("faktyczna"), "clv_pct": r.get("clv_pct"),
        # klasa karty drabinki zamrożona przy publikacji (top/mocny/solidny) —
        # bez niej lista rozliczonych kart nie mówi, czy przegrała karta
        # oznaczona jako najlepsza, czy ta z końca rankingu. Typy modelu
        # klasy nie mają, więc pole zostaje puste
        "klasa": r.get("klasa"),
        # typ poza publikacją (kwarantanna/limit meczu) — w liście dnia
        # widoczny z oznaczeniem, ale poza licznikami skuteczności
        "poza_publikacja": r.get("poza_publikacja"),
    }


def skutecznosc_per_dzien(
    settled: list[dict], dni: int = 21, poza: list[dict] | None = None,
) -> list[dict]:
    """Skuteczność realnych typów pogrupowana po DNIU meczu (kickoff).

    Zwraca ostatnie `dni` dni (od najnowszego): trafienia, ROI flat (stawka
    1 j./okazję), liczbę okazji ORAZ listę typów tego dnia (`typy` — realne
    typy, które siadły/nie siadły), żeby dzień można było rozwinąć. ROZLICZONE
    typy tylko — `settled` powinno być już bez rynków osobnych.

    `poza` = typy poza publikacją (kwarantanna rynku / limit meczu): trafiają
    do listy dnia z oznaczeniem i osobnych liczników (poza_n/poza_trafione),
    ale NIE wchodzą do trafień/ROI — user ich nie widział na liście typów.
    """
    dzienne: dict[str, dict] = {}

    def _agg(r: dict) -> dict:
        d = time.strftime("%Y-%m-%d", time.localtime(r.get("kickoff_ts") or 0))
        return dzienne.setdefault(d, {
            "dzien": d, "rozliczone": 0, "trafione": 0,
            "okazje": 0, "_zwrot_j": 0.0, "typy": [],
            "poza_n": 0, "poza_trafione": 0,
        })

    for r in settled:
        agg = _agg(r)
        agg["rozliczone"] += 1
        if r.get("wynik") == "wygrany":
            agg["trafione"] += 1
        if not r.get("sugestia") and r.get("kurs"):
            agg["okazje"] += 1
            agg["_zwrot_j"] += _zwrot_typu(r)
        agg["typy"].append(_typ_dnia(r))
    for r in poza or []:
        agg = _agg(r)
        agg["poza_n"] += 1
        if r.get("wynik") == "wygrany":
            agg["poza_trafione"] += 1
        agg["typy"].append(_typ_dnia(r))
    out = []
    for d in sorted(dzienne, reverse=True)[:dni]:
        agg = dzienne[d]
        agg["roi_flat"] = round(agg.pop("_zwrot_j") - agg["okazje"], 2)
        # publikowane przed typami poza publikacją; w obrębie grupy trafione
        # na górze, potem po nazwie
        agg["typy"].sort(
            key=lambda t: (
                bool(t.get("poza_publikacja")),
                t.get("wynik") != "wygrany",
                str(t.get("podmiot")),
            )
        )
        out.append(agg)
    return out


STRUMIENIE = ("pewniaki", "druzyny", "drabinki")


def skutecznosc_strumieni(log: dict, dni: int = 21) -> dict[str, dict]:
    """Skuteczność rozbita na strumienie: pewniaki / drużyny / drabinki.

    Jeden wspólny licznik mówił o wszystkim naraz i o niczym konkretnie:
    typ zawodniczy z silnika, rynek drużynowy i karta z drabinki to trzy
    różne produkty, o różnym ryzyku i różnym pochodzeniu prawdopodobieństwa.
    Dopiero osobne liczniki odpowiadają na pytanie „czy TO działa".

    Każdy strumień dostaje ten sam kształt co `skutecznosc_dzienna`
    (dni + lista typów) plus własne podsumowanie, a drabinki dodatkowo
    rozbicie po KLASIE karty — to jedyny sposób sprawdzić, czy „top"
    naprawdę trafia lepiej niż „solidny", zamiast wierzyć progom.
    """
    out: dict[str, dict] = {}
    for nazwa in STRUMIENIE:
        w_strumieniu = [
            r for r in log.values()
            if r.get("wynik") in ("wygrany", "przegrany")
            and r.get("rynek_kod") not in RYNKI_OSOBNE
            and not r.get("odrzucony")
            and _strumien(r) == nazwa
        ]
        settled = [r for r in w_strumieniu if not r.get("poza_publikacja")]
        poza = [r for r in w_strumieniu if r.get("poza_publikacja")]
        okazje = [r for r in settled if not r.get("sugestia") and r.get("kurs")]
        trafione = sum(1 for r in settled if r["wynik"] == "wygrany")
        roi = sum(_zwrot_typu(r) - 1.0 for r in okazje)
        rec: dict = {
            "dni": skutecznosc_per_dzien(settled, dni=dni, poza=poza),
            "podsumowanie": {
                "rozliczone": len(settled),
                "trafione": trafione,
                "skutecznosc": (
                    round(trafione / len(settled), 3) if settled else None
                ),
                "okazje_rozliczone": len(okazje),
                "roi_flat": round(roi, 2),
                # typy rozliczone POZA publikacją (kwarantanna rynku / limit
                # meczu): nie wchodzą do trafień ani ROI wyżej, bo user ich
                # nie widział na liście — ale muszą mieć swoją liczbę.
                # Bez tego wygrana w kwarantannie nie istnieje w UI nigdzie
                # poza rozwinięciem konkretnego dnia i wygląda na zgubioną.
                "poza_n": len(poza),
                "poza_trafione": sum(1 for r in poza if r["wynik"] == "wygrany"),
            },
        }
        klasy: dict[str, dict] = {}
        for r in settled:
            if not r.get("klasa"):
                continue
            k = klasy.setdefault(r["klasa"], {"n": 0, "trafione": 0})
            k["n"] += 1
            if r["wynik"] == "wygrany":
                k["trafione"] += 1
        if klasy:
            for k in klasy.values():
                k["skutecznosc"] = round(k["trafione"] / k["n"], 3)
            rec["klasy"] = klasy
        out[nazwa] = rec
    return out


# --- RAPORT UCZENIA: czy model robi postępy (2026-07-29) ---
#
# Zamówienie usera z 27.07: „user ma widzieć postęp sam, bez pytania mnie".
# Do dziś odpowiedź na „czy to się poprawia" wymagała ode mnie ręcznej sondy
# po księdze — a odpowiedź brzmiała NIE ([[czy-model-robi-postepy]]:
# deklaracja stała na 68–75% przez siedem paczek z rzędu, trafienia na 58%).
#
# CZEMU PACZKI PO N ROZLICZEŃ, A NIE TYGODNIE. Tydzień to od 3 do 90 typów
# zależnie od kalendarza, więc „ostatni tydzień gorszy" mówiłoby głównie
# o tym, ile było meczów. Paczka stałej wielkości ma ten sam ciężar
# statystyczny w każdym wierszu — i dopiero wtedy porównanie wiersz do
# wiersza cokolwiek znaczy.
#
# GRANICE PACZEK LICZYMY OD NAJSTARSZEJ. Dzięki temu raz pokazany wiersz już
# się nie zmienia, a rośnie tylko ostatni (oznaczony `pelna: False`). Gdyby
# ciąć od końca, każde nowe rozliczenie przesuwałoby wszystkie granice i
# tabela wyglądałaby co dzień inaczej, mimo że historia jest ta sama.
PACZKA_UCZENIA = 40         # rozliczeń na wiersz raportu
PACZKA_UCZENIA_MIN = 10     # krótszy ogon nie jest osobnym wierszem
PACZEK_W_RAPORCIE = 10      # ile ostatnich wierszy trzymamy w payloadzie
TREND_PACZEK = 3            # po tylu pierwszych/ostatnich liczymy kierunek


def raport_uczenia(
    log: dict, rozmiar: int = PACZKA_UCZENIA,
) -> dict[str, dict]:
    """Postęp modelu w paczkach po `rozmiar` rozliczeń, per strumień.

    Każdy wiersz: od–do (daty meczów), ile weszło, ile model DEKLAROWAŁ,
    luka między jednym a drugim i ROI. Plus `trend`: średnia luka z trzech
    pierwszych paczek wobec trzech ostatnich — czyli jednozdaniowa odpowiedź
    na „czy się uczymy".

    Liczone na tych samych typach, co pokazywana skuteczność: bez sugestii,
    bez typów pomiarowych, bez typów spoza publikacji i bez rynków osobnych.
    """
    out: dict[str, dict] = {}
    for nazwa in STRUMIENIE:
        settled = sorted(
            (
                r for r in log.values()
                if r.get("wynik") in ("wygrany", "przegrany")
                and r.get("rynek_kod") not in RYNKI_OSOBNE
                and not r.get("odrzucony") and not r.get("poza_publikacja")
                and not r.get("sugestia") and r.get("p_model")
                and _strumien(r) == nazwa
            ),
            key=lambda r: r.get("kickoff_ts") or 0,
        )
        if not settled:
            continue
        paczki: list[dict] = []
        for i in range(0, len(settled), rozmiar):
            grp = settled[i:i + rozmiar]
            if len(grp) < PACZKA_UCZENIA_MIN and paczki:
                # ogon krótszy niż minimum doklejamy do poprzedniego wiersza,
                # zamiast pokazywać paczkę „3 typy, 33%" jako pełnoprawną
                paczki.pop()
                grp = settled[max(0, i - rozmiar):i + rozmiar]
            z_kursem = [r for r in grp if r.get("kurs") and float(r["kurs"]) > 1.0]
            traf = sum(1 for r in grp if r["wynik"] == "wygrany")
            hit = traf / len(grp)
            sr_p = sum(float(r["p_model"]) for r in grp) / len(grp)
            paczki.append({
                "od": time.strftime(
                    "%Y-%m-%d", time.localtime(grp[0].get("kickoff_ts") or 0)
                ),
                "do": time.strftime(
                    "%Y-%m-%d", time.localtime(grp[-1].get("kickoff_ts") or 0)
                ),
                "n": len(grp), "trafione": traf,
                "hit": round(hit, 3),
                "deklaracja": round(sr_p, 3),
                "luka": round(hit - sr_p, 3),
                "roi": (
                    round(sum(
                        (float(r["kurs"]) - 1.0) if r["wynik"] == "wygrany"
                        else -1.0 for r in z_kursem
                    ) / len(z_kursem), 3) if z_kursem else None
                ),
                "pelna": len(grp) >= rozmiar,
            })
        rec: dict = {"paczki": paczki[-PACZEK_W_RAPORCIE:]}
        # KIERUNEK liczymy z PEŁNEJ historii, nie z przyciętej listy — inaczej
        # „od początku" znaczyłoby „od dziesiątej paczki wstecz" i trend
        # zmieniałby sens w miarę, jak rośnie księga. I tylko z paczek PEŁNYCH:
        # ostatni, niedokończony wiersz potrafi mieć 12 typów i skakać o 30 pp
        # z dnia na dzień — wpuszczony do trendu robiłby z niego alarm.
        pelne = [p for p in paczki if p["pelna"]]
        if len(pelne) >= 2 * TREND_PACZEK:
            start = pelne[:TREND_PACZEK]
            teraz = pelne[-TREND_PACZEK:]
            l_start = sum(p["luka"] for p in start) / len(start)
            l_teraz = sum(p["luka"] for p in teraz) / len(teraz)
            rec["trend"] = {
                "luka_start": round(l_start, 3),
                "luka_teraz": round(l_teraz, 3),
                "zmiana": round(l_teraz - l_start, 3),
                "paczek": len(pelne),
            }
        out[nazwa] = rec
    return out


# POMIAR PROGU POKRYCIA DRABINEK (2026-07-29). Próg 0,5 (radar.
# PROG_POKRYCIA_KARTY) był od początku ZAŁOŻENIEM: raz zszedł z 0,6, raz go
# nie podnieśliśmy, ale nigdy nie zmierzyliśmy, czy szczeble tuż pod nim
# faktycznie trafiają gorzej. Od tej wersji radar dopisuje najlepszy szczebel
# z pokryciem 0,40–0,50 do księgi jako typ POMIAROWY (`odrzucony`), czyli poza
# publikacją, poza Skutecznością i poza korektą strumienia. Ta funkcja
# zestawia obie grupy — dopiero ona odpowiada, czy próg jest w dobrym miejscu.
POWOD_POMIARU_POKRYCIA = "pokrycie_pod_progiem"


def pomiar_progu_drabinek(log: dict) -> dict:
    """Opublikowane drabinki vs szczeble tuż pod progiem pokrycia.

    Zwraca {"opublikowane": {...}, "pod_progiem": {...}} z n / trafione /
    hit / sr_p / roi.

    JAK TO CZYTAĆ — i czego to NIE mówi. Grupy nie są bliźniacze: szczebel
    spod progu ma z definicji niższe `p_final` (bo p rośnie z pokryciem),
    więc wpuszczamy go do pomiaru już przy przewadze >= 0, a nie +3 pp
    (radar.MIN_EDGE_POMIARU — inaczej grupa byłaby pusta). Dlatego:
      * porównujemy przede wszystkim ROI, nie sam hit-rate — ROI uwzględnia
        cenę, a to właśnie ceną te grupy się różnią;
      * gdy „pod progiem" wychodzi PODOBNIE albo LEPIEJ, wniosek jest mocny:
        próg 0,5 nie zarabia, mimo że gra słabszą ręką;
      * gdy wychodzi gorzej, wniosek jest słabszy — część różnicy może
        pochodzić z luźniejszej bramy przewagi, nie z samego pokrycia.
    """
    def _stat(grp: list[dict]) -> dict:
        n = len(grp)
        z_kursem = [r for r in grp if r.get("kurs") and float(r["kurs"]) > 1.0]
        traf = sum(1 for r in grp if r["wynik"] == "wygrany")
        return {
            "n": n,
            "trafione": traf,
            "hit": round(traf / n, 3) if n else None,
            "sr_p": (
                round(sum(float(r["p_model"] or 0) for r in grp) / n, 3)
                if n else None
            ),
            "roi": (
                round(sum(
                    (float(r["kurs"]) - 1.0) if r["wynik"] == "wygrany"
                    else -1.0 for r in z_kursem
                ) / len(z_kursem), 3) if z_kursem else None
            ),
        }

    dr = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and r.get("zrodlo") == ZRODLO_DRABINKA
    ]
    return {
        "opublikowane": _stat([r for r in dr if not r.get("odrzucony")]),
        "pod_progiem": _stat([
            r for r in dr
            if r.get("odrzucony")
            and r.get("odrzucenie_powod") == POWOD_POMIARU_POKRYCIA
        ]),
    }


# --- MUNDIAL vs LIGI: rozbicie epok per rynek ---
# Powód (pomiar 2026-07-27, 408 rozliczonych typów): sezon ligowy wystartował,
# ale kwarantanna rynków patrzy na OKNO 40 OSTATNICH ROZLICZEŃ, a nie na
# kalendarz — dla rynków o dużym wolumenie połowa tego okna to wciąż mecze
# reprezentacji. Naturalne pytanie „może w ligach jest już lepiej?" sprawdziliśmy
# i odpowiedź brzmi NIE:
#
#   mundial (mecz < 21.07)         292 typy   57,4% trafień   ROI −13,5%
#   ligi    (mecz >= 21.07)        116 typów  65,7% trafień   ROI  −4,8%
#     z tego drużynowe              84        66,2%           ROI  −2,4%
#     z tego ZAWODNICZE             32        64,0%           ROI −11,2%
#
# Cała poprawa siedzi w rynkach drużynowych, których na mundialu w ogóle nie
# było; typy zawodnicze w ligach tracą praktycznie tyle samo co na turnieju.
# Sprawdzone też ważenie świeżością (półzanik 14 i 7 dni): ŻADEN wstrzymany
# rynek się nie odblokowuje, a strzały wychodzą wtedy nawet gorzej
# (−10,7% -> −12,6%). Wycięcie mundialu zwolniłoby odbiory (0 rozliczeń z lig),
# faule popełnione (1) i wywalczone (4) — czyli na BRAKU DANYCH, nie na dowodzie
# poprawy. Dlatego kwarantanny nie ruszamy; zamiast tego pokazujemy rozbicie,
# żeby moment przełomu dało się zobaczyć, a nie zgadywać.
KONIEC_MUNDIALU_TS = 1784592000   # 2026-07-21 00:00 UTC


def epoki_per_rynek(log: dict) -> dict:
    """Trafienia i ROI per rynek w rozbiciu mundial / ligi.

    Liczone na tej samej próbie co kwarantanna (typy modelu z kursem), żeby
    liczby dało się zestawić z jej progiem wprost.
    """
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and _z_modelu(r) and r.get("kurs") and float(r["kurs"]) > 1.0
    ]

    def _blok(grp: list[dict]) -> dict | None:
        if not grp:
            return None
        traf = sum(1 for r in grp if r["wynik"] == "wygrany")
        roi = sum(_zwrot_typu(r) - 1.0 for r in grp) / len(grp)
        return {"n": len(grp), "trafione": traf,
                "skutecznosc": round(traf / len(grp), 3), "roi": round(roi, 3)}

    out: dict = {}
    for mk in sorted({r["rynek_kod"] for r in settled}):
        grp = [r for r in settled if r["rynek_kod"] == mk]
        mundial = [r for r in grp
                   if int(r.get("kickoff_ts") or 0) < KONIEC_MUNDIALU_TS]
        ligi = [r for r in grp
                if int(r.get("kickoff_ts") or 0) >= KONIEC_MUNDIALU_TS]
        # etykieta z samego rekordu — rozliczanie nie zna map z build_demo,
        # a każdy typ i tak nosi swoją polską nazwę rynku
        out[mk] = {"mundial": _blok(mundial), "ligi": _blok(ligi),
                   "nazwa": next((r.get("rynek") for r in grp if r.get("rynek")), mk)}
    return out


def _statshub_wynik(event_id: int, cache: dict) -> dict | None:
    """Wynik meczu z otwartego API statshub; cache per przebieg rozliczania."""
    if event_id in cache:
        return cache[event_id]
    try:
        r = statshub.fetch_event_result(event_id)
    except Exception:
        r = None
    cache[event_id] = r
    return r


def _statshub_strzaly(event_id: int, cache: dict) -> dict | None:
    """Strzały/celne per zawodnik z shotmapy statshub; cache per przebieg."""
    if event_id in cache:
        return cache[event_id]
    try:
        r = statshub.player_shots_from_shotmap(event_id)
    except Exception:
        r = None
    cache[event_id] = r
    return r


def _sofa_gracz(sofa: dict, rec: dict) -> tuple[dict | None, dict | None]:
    """Staty zawodnika z cache Sofascore (`sofa_results`, worker domowy) —
    dopasowanie po nazwisku. Zwraca (staty_lub_None, wpis_meczu_lub_None)."""
    e = sofa.get(str(rec["mecz_id"]))
    if not e:
        return None, None
    players = e.get("players") or {}
    normed = {scores365._norm(n): v for n, v in players.items()}
    skey = scores365.resolve_player_key(set(normed), rec["podmiot"])
    return (normed.get(skey) if skey else None), e


def _sofa_druzyna(sofa: dict, rec: dict) -> tuple[dict | None, dict | None]:
    """Staty drużyny z cache Sofascore — po znormalizowanej nazwie."""
    e = sofa.get(str(rec["mecz_id"]))
    if not e:
        return None, None
    teams = e.get("teams") or {}
    normed = {rotowire._norm(n): v for n, v in teams.items()}
    return normed.get(rotowire._norm(str(rec["podmiot"]))), e


def rozlicz(
    value_bets: list[dict],
    kupony_list: list[dict] | None = None,
    niedostepni: set[int] | None = None,
    conf_mids: set[int] | None = None,
    legi_pool: list[dict] | None = None,
    drabinki: list[dict] | None = None,
) -> dict:
    """Dopisz nowe typy do logu, rozlicz zakończone, zwróć podsumowanie.

    `drabinki` — typy „hero" z kart zakładki Drabinki (jobs/radar.py). Idą do
    tego samego logu i rozliczają się tą samą maszynerią, ale z flagą
    `zrodlo="drabinka"`, która trzyma je poza kalibracją, biasem i kwarantanną
    modelu (patrz `_z_modelu`). Bez tego „najlepsze typy" byłyby deklaracją
    bez pokrycia — nikt by nie wiedział, czy trafiają.
    """
    # ODCZYT KSIĘGI JEST WARUNKIEM CAŁEGO ROZLICZANIA. Gdy zapytanie padnie,
    # `get_key` zwróciłby None nie do odróżnienia od pustej księgi — dopisalibyśmy
    # świeże typy i nadpisali nimi całą historię (dataset kalibracji, kwarantanny
    # i Skuteczności). Wyjątek łapie `_rozlicz_i_zapisz` i zostawia poprzednie
    # wyniki nietknięte.
    log_raw, odczyt_ok = supa.get_key_ok("typy_log")
    if not odczyt_ok:
        raise RuntimeError(
            "nie udało się odczytać typy_log — rozliczanie pominięte, "
            "żeby nie nadpisać historii"
        )
    log = _migruj_log(log_raw or {})
    _dopisz_nowe(log, value_bets)
    _dopisz_nowe(log, drabinki or [])
    # legi kuponów też muszą być w logu (pewniaki spoza publikowanych typów)
    for k in kupony_list or []:
        _dopisz_nowe(log, [_kupon_leg_do_logu(l) for l in k["legi"]])
    # WŁASNE kupony usera (generator „ucz model") — ich legi też do logu, żeby
    # się rozliczyły; sam kupon trafia do kupony_log jako pominięty (niżej)
    kupony_wlasne = supa.get_key("kupony_wlasne") or {}
    for wk in kupony_wlasne.values():
        _dopisz_nowe(log, [_kupon_leg_do_logu(l) for l in (wk.get("legi") or [])
                            if l.get("mecz_id") and l.get("podmiot")])
    lib = supa.get_key("trend_lib") or {}
    sofa = supa.get_key("sofa_results") or {}   # cache Sofascore (worker domowy)
    now = int(time.time())
    # multi-liga: świeże trendy rozegranych meczów prosto z feedu statshub —
    # rozliczają mecze, których 365Scores nie zna (globalne propsy)
    try:
        _dolej_swieze_trendy(log, lib, now)
    except Exception as e:
        print(f"Dolewka trendów pominięta ({e})")
    cache_365: dict = {}
    cache_sh: dict = {}      # wyniki meczów statshub (fallback egzotyki)
    cache_sh_sm: dict = {}   # shotmapy statshub (fallback strzałów egzotyki)
    # mecze przełożone: jeśli mecz wciąż figuruje w nadchodzących typach,
    # deadline braku danych nie może zamknąć jego legów jako zwrot
    mecze_przyszle = {
        b["mecz"] for b in value_bets if (b.get("kickoff_ts") or 0) > now
    }
    for k in kupony_list or []:
        for l in k["legi"]:
            if (l.get("kickoff_ts") or 0) > now:
                mecze_przyszle.add(l["mecz"])

    _snapshot_zamkniecia(log, value_bets, kupony_list or [], now)

    for rec in log.values():
        if rec.get("wynik") or now - rec["kickoff_ts"] < MECZ_KONIEC_PO_S:
            continue
        mk = rec["rynek_kod"]

        # SUMA MECZOWA i „KTO WIĘCEJ" — obie potrzebują statystyk OBU drużyn
        if mk in MARKETY_SUMY or mk in MARKETY_WIECEJ:
            gid_n = _gid_365(rec, cache_365)
            wartosci = None
            if gid_n is not None and not scores365.after_extra_time(gid_n):
                try:
                    st_n = scores365.game_team_stats(gid_n)
                except Exception:
                    st_n = None
                klucz_staty = MARKETY_SUMY.get(mk) or MARKETY_WIECEJ[mk]
                if st_n and len(st_n) == 2:
                    # gospodarz z `podmiot`, gość = ta druga drużyna meczu.
                    # Nazwy dopasowujemy tolerancyjnie (patrz resolve_team_key)
                    kh = scores365.resolve_team_key(
                        set(st_n), str(rec["podmiot"])
                    )
                    if kh:
                        ka = next(k for k in st_n if k != kh)
                        wh = (st_n[kh] or {}).get(klucz_staty)
                        wa = (st_n[ka] or {}).get(klucz_staty)
                        if wh is not None and wa is not None:
                            wartosci = (float(wh), float(wa))
            if wartosci is None:
                if (
                    now - rec["kickoff_ts"] > TERMIN_BRAK_DANYCH_S
                    and rec.get("mecz") not in mecze_przyszle
                ):
                    rec.update(wynik="zwrot", faktyczna=None,
                               rozliczono_ts=now, powod="brak danych źródła")
                continue
            wh, wa = wartosci
            if mk in MARKETY_SUMY:
                suma = wh + wa
                traf_n = (suma > rec["linia"] if rec["strona"] == "powyzej"
                          else suma < rec["linia"])
                faktyczna_n = suma
            else:
                zwyciezca = ("gospodarz" if wh > wa
                             else "gosc" if wa > wh else "remis")
                traf_n = rec["strona"] == zwyciezca
                # zapisujemy OBIE liczby — bez nich nie da się później
                # sprawdzić, czy rozliczenie było słuszne
                faktyczna_n = f"{wh:g}:{wa:g}"
            rec.update(
                wynik="wygrany" if traf_n else "przegrany",
                faktyczna=faktyczna_n, rozliczono_ts=now, zagral=True,
            )
            continue

        # RYNKI DRUŻYNOWE — osobna, prosta ścieżka (statystyki drużynowe 365)
        if mk in MARKETY_DRUZYNOWE:
            gid_t = _gid_365(rec, cache_365)
            wartosc_t = None
            if gid_t is not None and not scores365.after_extra_time(gid_t):
                # DOPASOWANIE NAZWY DRUŻYNY PO ZBIORACH SŁÓW, nie po
                # identycznym napisie (poprawka 2026-07-30). 365Scores nazywa
                # kluby inaczej niż my („qarabag" / „qarabag agdam",
                # „sarmiento" / „sarmiento junin"), przez co 26 z 46 wiszących
                # typów drużynowych nie rozliczało się nigdy — patrz
                # `scores365.resolve_team_key`.
                if mk == "team_goals":
                    # goli nie ma w game/stats — bierzemy wynik meczu
                    try:
                        wyniki_t = scores365.game_scores(gid_t)
                    except Exception:
                        wyniki_t = None
                    if wyniki_t:
                        kt = scores365.resolve_team_key(
                            set(wyniki_t), str(rec["podmiot"])
                        )
                        wartosc_t = wyniki_t.get(kt) if kt else None
                else:
                    try:
                        st_t = scores365.game_team_stats(gid_t)
                    except Exception:
                        st_t = None
                    kt = (scores365.resolve_team_key(
                        set(st_t), str(rec["podmiot"])) if st_t else None)
                    if kt:
                        w_t = st_t[kt].get(MARKETY_DRUZYNOWE[mk])
                        wartosc_t = float(w_t) if w_t is not None else None
            if wartosc_t is None and mk == "team_goals":
                # FALLBACK egzotyki: wynik z otwartego API statshub (dowolna
                # liga, także spoza comp365 — Kosowo/Islandia/niższe). mecz_id
                # = event_id statshub, więc adresujemy wprost, bez mapowania.
                sr = _statshub_wynik(rec["mecz_id"], cache_sh)
                if sr is not None and not sr["extra_time"]:
                    pid = rec.get("podmiot_id")
                    if pid and pid == sr.get("home_id"):
                        wartosc_t = sr["home_goals"]
                    elif pid and pid == sr.get("away_id"):
                        wartosc_t = sr["away_goals"]
                    else:  # brak/niepewne id — awaryjnie po nazwie
                        tkn = rotowire._norm(str(rec["podmiot"]))
                        if sr.get("home_name") and rotowire._norm(sr["home_name"]) == tkn:
                            wartosc_t = sr["home_goals"]
                        elif sr.get("away_name") and rotowire._norm(sr["away_name"]) == tkn:
                            wartosc_t = sr["away_goals"]
            if wartosc_t is None:
                # FALLBACK egzotyki (Warstwa 2): staty drużynowe z cache
                # Sofascore (worker domowy) — rożne/kartki/faule/strzały drużyny.
                tg, e_sofa = _sofa_druzyna(sofa, rec)
                if tg is not None and e_sofa and not e_sofa.get("extra_time"):
                    v = tg.get(mk)
                    if v is not None:
                        wartosc_t = float(v)
            if wartosc_t is None:
                if (
                    now - rec["kickoff_ts"] > TERMIN_BRAK_DANYCH_S
                    and rec.get("mecz") not in mecze_przyszle
                ):
                    rec.update(wynik="zwrot", faktyczna=None,
                               rozliczono_ts=now, powod="brak danych źródła")
                continue
            traf_t = (
                wartosc_t > rec["linia"] if rec["strona"] == "powyzej"
                else wartosc_t < rec["linia"]
            )
            rec.update(
                wynik="wygrany" if traf_t else "przegrany",
                faktyczna=wartosc_t, rozliczono_ts=now, zagral=True,
            )
            if rec.get("kurs") and rec.get("kurs_zamkniecia"):
                rec["clv_pct"] = round(
                    (rec["kurs"] / rec["kurs_zamkniecia"] - 1.0) * 100.0, 1
                )
            continue

        # pełne statystyki meczu z 365 (minuty + faule/przechwyty) — dostępne
        # tuż po końcowym gwizdku, niezależnie od odświeżeń banku trendów
        gid = _gid_365(rec, cache_365)
        staty = None
        if gid is not None:
            try:
                staty = scores365.game_player_match_stats(gid)
            except Exception:
                staty = None
        pkey = scores365.resolve_player_key(set(staty), rec["podmiot"]) if staty else None

        # minuty: najpierw 365 (nieobecny w statystykach meczu = nie zagrał),
        # fallback bank trendów
        minuty = None
        if staty:
            minuty = float(staty[pkey].get("minutes", 0)) if pkey else 0.0
        if minuty is None:
            minuty = _minuty_z_banku(rec, lib)
        if minuty is None:
            # FALLBACK egzotyki (Warstwa 2): minuty z cache Sofascore
            pg, _e = _sofa_gracz(sofa, rec)
            if pg is not None and pg.get("minutes") is not None:
                minuty = float(pg["minutes"])
        if minuty is not None and minuty <= 0:
            rec.update(wynik="zwrot", faktyczna=0.0, rozliczono_ts=now,
                       powod="nie zagrał", zagral=False)
            continue

        wartosc = None
        if mk in MARKETY_365:
            # PUSTA MAPA TO NIE ZERO ZDARZEŃ — najdroższy błąd rozliczania,
            # znaleziony 2026-07-30 na zgłoszeniu usera („Marcel Reguła
            # niezaliczony, a miał 6 strzałów").
            #
            # 365Scores dla części meczów oddaje mapę strzałów PUSTĄ ({}), a
            # jednocześnie w statystykach meczu pokazuje, że zawodnik zagrał
            # 90 minut. Stary kod czytał to jako „zagrał, nie ma go w mapie,
            # czyli oddał 0 strzałów", zapisywał `faktyczna=0` i NIE PYTAŁ już
            # żadnego innego źródła — bo `wartosc` przestawała być pusta.
            # Statshub miał wtedy komplet (Reguła: 6 strzałów, 1 celny).
            # Skutek: typ „powyżej" przegrywał z automatu, a księga uczyła
            # kalibrację na zmyślonych zerach.
            #
            # Teraz „zagrał, a nie ma go w mapie" jest OSTATNIM wnioskiem, po
            # przepytaniu wszystkich źródeł — i tylko wtedy, gdy mapa w ogóle
            # kogoś zawiera (patrz `mapa_pusta` niżej).
            gra = None
            if gid is not None:
                try:
                    gra = scores365.game_player_shots(gid)
                except Exception:
                    gra = None
            mapy_puste = True       # czy ŻADNE źródło nie miało danych o meczu
            if gra:                 # pusty słownik = brak danych, nie zero
                mapy_puste = False
                skey = scores365.resolve_player_key(set(gra), rec["podmiot"])
                if skey:
                    wartosc = float(gra[skey].get(MARKETY_365[mk], 0))
            if wartosc is None and mk in ("shots", "sot"):
                # multi-liga: mecz spoza rozgrywek z comp365 nie ma gid —
                # strzały/celne rozliczamy z banku trendów statshub
                # (te same dane Opta, na których stoi scoring)
                wartosc = _wartosc_z_banku(rec, lib)
            if wartosc is None and mk in ("shots", "sot"):
                # shotmapa z otwartego API statshub. Tylko mecze bez dogrywki —
                # shotmapa nie oddziela regularnego czasu.
                sr = _statshub_wynik(rec["mecz_id"], cache_sh)
                if sr is not None and not sr["extra_time"]:
                    counts = _statshub_strzaly(rec["mecz_id"], cache_sh_sm)
                    if counts:
                        mapy_puste = False
                        # id zawodników bywają w innej przestrzeni niż shotmapa
                        # — dopasowujemy po nazwisku, jak ścieżka 365
                        normed = {scores365._norm(n): v for n, v in counts.items()}
                        skey = scores365.resolve_player_key(set(normed), rec["podmiot"])
                        if skey is not None:
                            wartosc = float(normed[skey][mk])
            if wartosc is None and mk in ("shots", "sot"):
                # FALLBACK egzotyki (Warstwa 2): strzały z cache Sofascore
                # (worker domowy) — np. liga bez shotmapy statshub.
                pg, e_sofa = _sofa_gracz(sofa, rec)
                if pg is not None and e_sofa and not e_sofa.get("extra_time"):
                    v = pg.get(mk)
                    if v is not None:
                        wartosc = float(v)
            if wartosc is None and minuty and not mapy_puste:
                # dopiero TERAZ: zagrał, źródła mecz znają i w żadnym go nie ma
                # przy tym rynku — czyli faktycznie zero zdarzeń
                wartosc = 0.0
        elif mk in MARKETY_LIB:
            # staty lineups obejmują CAŁY mecz — przy dogrywce nie nadają się
            # do rozliczenia rynku regularnego czasu (bank trendów zostaje)
            if (
                mk in MARKETY_365_STATY and staty and pkey
                and not scores365.after_extra_time(gid)
            ):
                w = staty[pkey].get(mk)
                wartosc = float(w) if w is not None else None
            if wartosc is None:
                wartosc = _wartosc_z_banku(rec, lib)
            if wartosc is None:
                # FALLBACK egzotyki (Warstwa 2): faule/odbiory/przechwyty z
                # cache Sofascore (worker domowy) — jedyne źródło tych rynków
                # w egzotyce (statshub/365 ich nie mają).
                pg, e_sofa = _sofa_gracz(sofa, rec)
                if pg is not None and e_sofa and not e_sofa.get("extra_time"):
                    v = pg.get(mk)
                    if v is not None:
                        wartosc = float(v)
        if wartosc is None:
            # źródło nie ma jeszcze meczu — spróbujemy w kolejnym cyklu;
            # po terminie zamykamy jako zwrot, żeby nic nie wisiało "w grze"
            if (
                now - rec["kickoff_ts"] > TERMIN_BRAK_DANYCH_S
                and rec.get("mecz") not in mecze_przyszle
            ):
                rec.update(wynik="zwrot", faktyczna=None, rozliczono_ts=now,
                           powod="brak danych źródła")
            continue
        trafiony = (
            wartosc > rec["linia"] if rec["strona"] == "powyzej" else wartosc < rec["linia"]
        )
        if not trafiony:
            sz = _superzmiana(rec, gid, staty, lib, wartosc)
            if sz:
                wartosc, rec["powod"] = sz
                rec["superzmiana"] = True
                trafiony = True
            if gid is not None:
                rec["superzmiana_spr"] = True  # sprawdzone — rewizja nie dubluje
        rec.update(
            wynik="wygrany" if trafiony else "przegrany",
            faktyczna=wartosc, rozliczono_ts=now, zagral=True,
        )
        if rec.get("kurs") and rec.get("kurs_zamkniecia"):
            rec["clv_pct"] = round(
                (rec["kurs"] / rec["kurs_zamkniecia"] - 1.0) * 100.0, 1
            )

    # rewizja WSTECZ: legi przegrane przed wdrożeniem superzmiany (albo gdy
    # danych o zmianie jeszcze nie było) — każdy rekord sprawdzamy raz
    for rec in log.values():
        if (
            rec.get("wynik") != "przegrany"
            or rec.get("superzmiana_spr")
            or rec.get("strona") != "powyzej"
            or rec.get("rynek_kod") not in SUPERZMIANA_RYNKI
            or "superbet" not in str(rec.get("bukmacher") or "").lower()
        ):
            continue
        gid = _gid_365(rec, cache_365)
        if gid is None:
            # dane 365 mogą dojść później — flagę "sprawdzone" wolno ustawić
            # dopiero, gdy mecz znaleziono (albo gdy szanse na dane minęły)
            if now - (rec.get("rozliczono_ts") or 0) > 72 * 3600:
                rec["superzmiana_spr"] = True
            continue
        rec["superzmiana_spr"] = True
        try:
            staty = scores365.game_player_match_stats(gid)
        except Exception:
            staty = None
        sz = _superzmiana(rec, gid, staty, lib, rec.get("faktyczna"))
        if sz:
            wartosc, powod = sz
            rec.update(wynik="wygrany", faktyczna=wartosc, rozliczono_ts=now,
                       superzmiana=True, powod=powod)

    # przycinanie: wpisy bez wyniku, których mecz był >30 dni temu, to śmieci
    # (nigdy się nie rozliczą); ROZLICZONE zostają — to dataset kalibracji
    log = {
        k: r for k, r in log.items()
        if r.get("wynik") or now - (r.get("kickoff_ts") or now) < 30 * 86400
    }
    if supa.put_key_bezpiecznie("typy_log", log):
        _kopia_zapasowa_logu(log, now)

    # ---- historia kuponów ----
    # ten sam bezpiecznik co przy księdze typów: nieudany odczyt = pomijamy
    # całą sekcję kuponów zamiast nadpisać historię bieżącym cyklem
    log_kuponow_raw, kupony_odczyt_ok = supa.get_key_ok("kupony_log")
    if not kupony_odczyt_ok:
        raise RuntimeError(
            "nie udało się odczytać kupony_log — rozliczanie pominięte, "
            "żeby nie nadpisać historii kuponów"
        )
    log_kuponow = log_kuponow_raw or {}
    # wmerguj WŁASNE kupony (generator „ucz model") jako pominięte — rozliczą
    # się w tle i zasilą korelację/kalibrację (jak automatyczne pominięte)
    for wkey, wk in kupony_wlasne.items():
        klucz = f"wlasny:{wkey}"[:150]
        legi = wk.get("legi") or []
        if klucz in log_kuponow or len(legi) < 2:
            continue
        log_kuponow[klucz] = {
            "klucz": klucz, "slot": "wlasny", "horyzont": "wlasny", "styl": "wlasny",
            "cel": 0, "cel_label": "własny",
            "kurs_laczny": wk.get("kurs_laczny"), "p_model": wk.get("p_model"),
            "legi": legi, "pominiety": True, "pominiety_przez": "user",
            "opublikowano_ts": int(wk.get("zapisano_ts") or now), "wynik": None,
        }
    if kupony_wlasne:
        supa.put_key("kupony_wlasne", {})   # bufor przetworzony — czyścimy
    # kupony pominięte przyciskiem w UI (web zapisuje klucz -> ts albo
    # {ts, powod}); wpisy starsze niż 14 dni wypadają
    pominiete_raw = supa.get_key("kupony_pominiete") or {}

    def _pomin_ts(v) -> int:
        return int((v.get("ts") if isinstance(v, dict) else v) or 0)

    pominiete = {
        k: v for k, v in pominiete_raw.items()
        if now - _pomin_ts(v) < 14 * 86400
    }
    if len(pominiete) != len(pominiete_raw):
        supa.put_key("kupony_pominiete", pominiete)
    powody = {
        k: v.get("powod") for k, v in pominiete.items() if isinstance(v, dict)
    }
    # akcje z UI: wymiana lega (zastosuj alternatywę) i przebudowa po
    # składach (opt-in) — klucze z TTL 3 dni
    wymiany_raw = supa.get_key("kupony_wymiana") or {}
    wymiany = {
        k: ts for k, ts in wymiany_raw.items() if now - int(ts or 0) < 3 * 86400
    }
    if len(wymiany) != len(wymiany_raw):
        supa.put_key("kupony_wymiana", wymiany)
    przebudowy_raw = supa.get_key("kupony_przebudowa") or {}
    przebudowy = {
        k: ts for k, ts in przebudowy_raw.items()
        if now - int(ts or 0) < 3 * 86400
    }
    if len(przebudowy) != len(przebudowy_raw):
        supa.put_key("kupony_przebudowa", przebudowy)
    _kupon_do_logu(log_kuponow, kupony_list or [], now, niedostepni,
                   set(pominiete), powody=powody, wymiany=set(wymiany),
                   przebudowy=set(przebudowy), conf_mids=conf_mids,
                   legi_pool=legi_pool)
    kupony_hist = _rozlicz_kupony(log_kuponow, log, now)
    # ROI kuponów per horyzont (stawka 1 j./kupon; pominięte = niezagrane,
    # nie wchodzą) — liczone z PEŁNEGO logu przed przycinaniem
    kupony_roi: dict[str, dict] = {}
    for r in log_kuponow.values():
        if r.get("pominiety") or r.get("wynik") not in (
            "wygrany", "przegrany", "zwrot"
        ):
            continue
        h = r.get("horyzont") or "value"
        d = kupony_roi.setdefault(h, {"n": 0, "wygrane": 0, "zwrot_j": 0.0})
        d["n"] += 1
        if r["wynik"] == "wygrany":
            d["wygrane"] += 1
            # PODATEK OD STAWKI liczy się RAZ na kupon, nie od każdego typu —
            # kupon to jeden zakład o kursie łącznym (2026-07-31)
            d["zwrot_j"] += betting.kurs_netto(
                float(r.get("kurs_rozliczony") or r.get("kurs_laczny") or 0),
                r.get("tryb_podatku"),
            )
        elif r["wynik"] == "zwrot":
            # zakład anulowany: stawka wraca W CAŁOŚCI, razem z podatkiem
            d["zwrot_j"] += 1.0
    for d in kupony_roi.values():
        d["zwrot_j"] = round(d["zwrot_j"], 2)
        d["roi_j"] = round(d["zwrot_j"] - d["n"], 2)
    # WSZYSTKIE wygrane kupony — trwały log, który NIGDY nie znika (osobna
    # sekcja na Skuteczności). Zbierany z PEŁNEGO logu przed przycinaniem; raz
    # wygrany kupon zostaje na zawsze (superzmiana tylko dokłada wygrane).
    # Odchudzamy o pola doradcze aktywnego kuponu (rentgen), które w historii
    # są zbędne i tylko puchłyby payload.
    wygrane_log = supa.get_key("kupony_wygrane") or {}
    _POMIN_POLA = ("alternatywa", "wariant_b", "dolozenie", "najslabszy_idx")
    for r in log_kuponow.values():
        if r.get("wynik") != "wygrany" or not r.get("klucz"):
            continue
        wygrane_log[r["klucz"]] = {
            k: v for k, v in r.items() if k not in _POMIN_POLA
        }
    if wygrane_log:
        # log wygranych NIGDY nie maleje — nagły skurcz to znak, że odczyt
        # wyżej zwrócił pustkę po awarii, a nie że kupony zniknęły
        supa.put_key_bezpiecznie("kupony_wygrane", wygrane_log)
    kupony_wygrane = sorted(
        wygrane_log.values(),
        key=lambda r: -(r.get("rozliczono_ts") or r.get("opublikowano_ts") or 0),
    )
    # przycinanie: kupony rozliczone/anulowane starsze niż 21 dni wypadają
    # (UI i tak pokazuje top 40; payload nie może rosnąć bez końca)
    log_kuponow = {
        k: r for k, r in log_kuponow.items()
        if not r.get("wynik")
        or now - (r.get("rozliczono_ts") or now) < 21 * 86400
    }
    supa.put_key_bezpiecznie("kupony_log", log_kuponow)

    # ---- podsumowanie do UI ----
    # strzały niecelne/zablokowane (RYNKI_OSOBNE) NIE wchodzą do skuteczności
    # ani ROI — uczą się w tle (typy_log/kalibracja), ale nie są pokazywane.
    # Typy POMIAROWE (odrzucone przy progu) też zostają poza wszystkim —
    # nigdy nie były opublikowane, mierzy je tylko diagnostyka kategorii.
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and r.get("rynek_kod") not in RYNKI_OSOBNE
        and not r.get("odrzucony")
        # typy spoza publikacji uczą kalibrację, ale nie liczą się do
        # pokazywanej skuteczności — user ich nie widział, nie mógł zagrać
        and not r.get("poza_publikacja")
        # drabinki mają WŁASNY strumień (skutecznosc_strumienie) — doliczenie
        # ich tutaj zmieniłoby wstecz znaczenie liczb modelu, na których stoi
        # kalibracja, kalendarz i wykresy
        and _z_modelu(r)
    ]
    okazje = [r for r in settled if not r["sugestia"] and r.get("kurs")]
    roi = sum(_zwrot_typu(r) - 1.0 for r in okazje)
    # typy poza publikacją (kwarantanna/limit meczu): w Skuteczności widoczne
    # z oznaczeniem (pełna transparentność), ale poza licznikami trafień/ROI
    poza_pub = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and r.get("rynek_kod") not in RYNKI_OSOBNE
        and not r.get("odrzucony")
        and r.get("poza_publikacja")
        and _z_modelu(r)
    ]

    def _po_rynku(recs: list[dict]) -> list[dict]:
        out = []
        for mk in sorted({r["rynek_kod"] for r in recs}):
            grp = [r for r in recs if r["rynek_kod"] == mk]
            traf = sum(1 for r in grp if r["wynik"] == "wygrany")
            sr_p = sum(r["p_model"] for r in grp) / len(grp)
            out.append({
                "rynek_kod": mk, "rynek": grp[0]["rynek"], "n": len(grp),
                "trafione": traf,
                "sr_p_model": round(sr_p, 3),
                "czestosc": round(traf / len(grp), 3),
                # bias > 1 = model niedoszacowuje, < 1 = przeszacowuje;
                # stosowany w modelu dopiero od n>=25 (na razie raport)
                "bias": round((traf + 2.0) / (sr_p * len(grp) + 2.0), 3),
            })
        return out

    po_rynku = _po_rynku(settled)

    # skuteczność DZIEŃ PO DNIU (realne typy, bez rynków osobnych) — z listą
    # typów danego dnia (co siadło); zasila przełącznik dnia na Skuteczności
    skutecznosc_dzienna = skutecznosc_per_dzien(settled, poza=poza_pub)
    # ...i to samo rozbite na strumienie (pewniaki / drużyny / drabinki),
    # bo „skuteczność" bez podziału mieszała trzy różne produkty
    strumienie = skutecznosc_strumieni(log)
    for nazwa, s in strumienie.items():
        p_s = s["podsumowanie"]
        if p_s["rozliczone"]:
            print(
                f"Skuteczność [{nazwa}]: {p_s['trafione']}/{p_s['rozliczone']}"
                f" ({(p_s['skutecznosc'] or 0):.0%}), ROI flat"
                f" {p_s['roi_flat']:+.2f} j."
                + (
                    " | " + ", ".join(
                        f"{k}: {v['trafione']}/{v['n']}"
                        for k, v in sorted(s.get("klasy", {}).items())
                    ) if s.get("klasy") else ""
                )
            )

    # CZY MODEL ROBI POSTĘPY — paczki po 40 rozliczeń, automatycznie
    uczenie = raport_uczenia(log)
    for nazwa, rec in uczenie.items():
        t = rec.get("trend")
        if t:
            print(
                f"Uczenie [{nazwa}]: luka na starcie {t['luka_start']:+.3f}"
                f" -> teraz {t['luka_teraz']:+.3f}"
                f" (zmiana {t['zmiana']:+.3f}, paczek {t['paczek']})"
            )

    # czy próg pokrycia drabinek (0,5) stoi w dobrym miejscu — pomiar w tle
    prog_drabinek = pomiar_progu_drabinek(log)
    if prog_drabinek["pod_progiem"]["n"]:
        o, pp = prog_drabinek["opublikowane"], prog_drabinek["pod_progiem"]
        print(
            f"Drabinki — próg pokrycia: opublikowane {o['trafione']}/{o['n']}"
            f" (ROI {o['roi']}), pod progiem {pp['trafione']}/{pp['n']}"
            f" (ROI {pp['roi']})"
        )

    ostatnie = sorted(
        settled + poza_pub + [
            r for r in log.values()
            if r.get("wynik") == "zwrot"
            and r.get("rynek_kod") not in RYNKI_OSOBNE
            and not r.get("odrzucony")
        ],
        key=lambda r: -(r.get("rozliczono_ts") or 0),
    )[:60]
    z_clv = [r for r in settled if r.get("clv_pct") is not None]
    diagnostyka = compute_diagnostyka(log)
    for nazwa, s in diagnostyka["kategorie"].items():
        print(
            f"Diag {nazwa}: n={s['n']} hit={s['hit']} śr.p={s['sr_p']} "
            f"Brier={s['brier']} logloss={s['logloss']}"
        )
    if diagnostyka["sklady"]:
        print("Sygnały XI: " + ", ".join(
            f"{k}: zagrał {v['zagral']}/{v['n']} ({v['pct']:.0%})"
            for k, v in diagnostyka["sklady"].items()
        ))
    kupony_diag = compute_kupony_diagnostyka(log_kuponow)
    for h, s in kupony_diag["kalibracja"].items():
        print(f"Kupony {h}: hit={s['hit']} vs śr.p={s['sr_p']} (n={s['n']}, Brier={s['brier']})")
    for rel, s in kupony_diag["korelacja"].items():
        print(
            f"Korelacja legów [{rel}]: obs={s['obs_oba']} vs indep={s['exp_indep']} "
            f"wsp={s['wsp']} (n_par={s['n_par']}, kara={s['kara_uzywana']})"
        )
    return {
        "diagnostyka": diagnostyka,
        "kupony_diag": kupony_diag,
        "podsumowanie": {
            # bez rynków osobnych (niecelne/zablokowane) — te są liczone osobno
            "opublikowane": sum(
                1 for r in log.values()
                if r.get("rynek_kod") not in RYNKI_OSOBNE
                and not r.get("odrzucony")
                and not r.get("poza_publikacja")
            ),
            "rozliczone": len(settled),
            "trafione": sum(1 for r in settled if r["wynik"] == "wygrany"),
            "roi_flat": round(roi, 2),
            "okazje_rozliczone": len(okazje),
            # CLV: dodatnie = braliśmy kursy lepsze niż zamknięcie rynku
            "clv_sr_pct": (
                round(sum(r["clv_pct"] for r in z_clv) / len(z_clv), 1)
                if z_clv else None
            ),
            "clv_n": len(z_clv),
            # TO SAMO POLICZONE RAZ NA ZDARZENIE — bo zagnieżdżone linie tego
            # samego zakładu („poniżej 13,5 / 14,5 / 15,5") wchodzą razem
            # i liczone osobno zawyżają trafienia. Patrz `skutecznosc_zdarzen`.
            "zdarzenia": skutecznosc_zdarzen(settled),
        },
        "po_rynku": po_rynku,
        "ostatnie": ostatnie,
        # skuteczność dzień po dniu (realne typy) — do przełącznika w UI
        "skutecznosc_dzienna": skutecznosc_dzienna,
        # ta sama skuteczność rozbita na strumienie: pewniaki / drużyny /
        # drabinki (każdy z własnym ROI i listą dni)
        "skutecznosc_strumienie": strumienie,
        # pomiar progu pokrycia drabinek (opublikowane vs tuż pod progiem) —
        # jedyna droga do odpowiedzi, czy 0,5 to dobra liczba
        "prog_drabinek": prog_drabinek,
        # postęp modelu w paczkach po 40 rozliczeń (deklaracja vs trafienia
        # vs ROI) — user ma to widzieć sam, bez pytania mnie
        "raport_uczenia": uczenie,
        # TEST W PRZÓD (pre-rejestracja w docs/forward-test-druzynowe-ponizej.md)
        # — jedyny zyskowny segment pomiaru 31.07, liczony od nowa na epoce,
        # na której model się jeszcze nie uczył. Do 40 rozliczeń CZYTAMY, ale
        # nie wyciągamy wniosków.
        "forward_test": forward_test(log),
        # mundial vs ligi per rynek — czy sezon klubowy zmienił obraz
        # (patrz `epoki_per_rynek`: na 27.07 NIE zmienił, poza drużynowymi)
        "epoki_per_rynek": epoki_per_rynek(log),
        "kupony": kupony_hist,
        "kupony_roi": kupony_roi,
        # WSZYSTKIE wygrane kupony (trwały log, nigdy nie znikają)
        "kupony_wygrane": kupony_wygrane,
    }
