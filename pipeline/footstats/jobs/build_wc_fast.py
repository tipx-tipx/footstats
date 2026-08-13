"""Tryb MŚ — SZYBKA ŚCIEŻKA przez statshub (otwarte API) + kursy Superbet.

Dlaczego szybciej: statshub daje w jednym zapytaniu historię mecz-po-meczu,
przewidywany skład i średnią rywala dla 5 rynków rdzeniowych — bez dławionego
Sofascore i bez godzinnego backfillu. Kursy realne bierzemy z Superbetu.

Użycie:
    python -m footstats.jobs.build_wc_fast

Jeśli statshub nie ma jeszcze wystawionych propsów na ćwierćfinały (ładują się
~24-48 h przed meczem), job to zgłasza i kończy — wtedy działa tryb pokazowy,
a strażnik/kolejne uruchomienie dokończy, gdy propsy się pojawią.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import statistics
import time
import traceback
import zlib
from collections import Counter, defaultdict
from dataclasses import asdict

from scipy import stats as _stats

import numpy as np
from curl_cffi import requests

from dataclasses import fields as dc_fields, replace as dc_replace

from .. import diagnostyka, rozgrywki, supa
from ..engine import (
    MatchContext, PlayerHistory, RARE_MARKETS, apply_bias, score_player_market,
)
from ..model import (
    betting, context, counts, koncesje, kupony, matchup, matchup_lite,
    profil_druzyn, styl, tempo,
)
from ..sources import (
    betclic, eloratings, rotowire, scores365, sofascore, statshub, superbet,
)
from . import radar, rozliczanie
from .build_demo import MARKET_NAMES_PL, WEB_DATA_DIR, line_for_lambda

# KURSY GŁÓWNE: Superbet i Betclic (drugi dołożony 2026-08-08, decyzja usera).
# STS blokuje IP serwerowni (chmura = źródło prawdy, cron GitHub Actions), więc
# kursy STS w line-shoppingu powodowały rozjazd danych między przebiegiem
# lokalnym a chmurowym (typy „znikały"). STS zostaje tylko jako adresat
# SUGESTII bez kursu (niecelne/zablokowane). Wróci do kursów głównych, gdy
# pipeline pójdzie z domowego IP (telefon/Pi).
#
# DWA CENNIKI, JEDEN TYP: ten sam zakład u dwóch bukmacherów to jedna pozycja
# na liście (klucz publikacji nie zna bukmachera), zagrana tam, gdzie płacą
# więcej. Bukmacher jest zapisywany PRZY TYPIE — razem z trybem podatkowym —
# więc historia wie, gdzie ten kurs był brany i da się to później rozliczyć
# osobno dla każdego z nich.
#
# Ile sekund wolno zużyć na pobranie oferty Betclica w jednym przebiegu.
#
# ZMIERZONE 08.08, bo pierwsza wersja tego budżetu stała na złej liczbie:
#   * `kursy_zawodnikow` meczu Z propsami:  ~71 s
#   * meczu bez propsów:                    30–40 s (i tak zwraca zero)
#   * `kalendarz()` do parowania:           ~150 s
# Przy 140 meczach pełne pokrycie kosztowałoby 2,2 godziny — czyli JEST
# NIEOSIĄGALNE w cyklu, który ma 8 minut zapasu. Zamiast tego trzy rzeczy:
#   1. pytamy WYŁĄCZNIE o mecze, w których Superbet kwotuje zawodników
#      (zmierzone: 70 ze 140, i rozkład jest zerojedynkowy — mecz ma albo 0
#      propsów, albo od razu 20+),
#   2. wynik zapisujemy między cyklami (patrz BETCLIC_KLUCZ), więc kolejne
#      przebiegi dobierają tylko brakujące mecze,
#   3. kolejność po godzinie rozpoczęcia — najbliższe mecze pierwsze.
# ⚑ OD 2026-08-08 CYKL SAM NIC NIE POBIERA — czyta gotowe.
#
# Pobieranie przeniesione do osobnego zadania (`jobs/betclic_oferty.py` +
# workflow „oferta Betclica"), bo w cyklu było nie do uratowania: 180 s budżetu
# starczało na 3 mecze z 60, a pamięć wygasa po dobie, więc wpisy przepadały
# szybciej, niż je dobieraliśmy. Osobny job ma własne 20 minut i domyka komplet
# po trzech–czterech uruchomieniach.
#
# Zero, nie mała liczba: gdyby cykl dobierał „przy okazji", wracalibyśmy do
# konkurowania o ten sam budżet, tylko ciszej. Zmienna środowiskowa zostaje
# jako awaryjne wejście (np. do dry-runu z sieci).
BUDZET_BETCLIC_TYPY_S = float(os.getenv("BETCLIC_BUDZET_CYKLU_S", "0"))
# Oferta Betclica pamiętana MIĘDZY CYKLAMI: mecz -> {ts, players}.
BETCLIC_KLUCZ = "betclic_oferty"
# ⚑ POBIERAMY RAZ NA MECZ (decyzja usera 08.08: „kurs pobierany jednorazowo na
# dany typ, nawet jak później się zmieni").
#
# Uzasadnienie jest mocniejsze, niż wygląda: cenę i tak ZAMRAŻAMY przy
# publikacji typu — po niej rozlicza księga i ją user widzi na karcie. Kolejne
# pobranie tego samego meczu nie poprawia więc ani jednego opublikowanego typu;
# służyłoby wyłącznie łapaniu nowych okazji po ruchu kursu. Przy 71 s na mecz
# ten sam budżet wydany na mecze JESZCZE NIEZNANE daje dużo więcej, a pełne
# pokrycie robi się po dwóch–trzech cyklach zamiast nigdy.
SWIEZOSC_BETCLIC_S = 24 * 3600
# ...z JEDNYM wyjątkiem: mecz tuż przed gwizdkiem odświeżamy raz, choćby
# oferta była zapamiętana. To okno, w którym user realnie stawia i w którym
# znane są składy — a pokazanie ceny, której już nie ma, boli bardziej niż
# brak typu. Meczów w takim oknie jest w cyklu kilka, więc kosztuje to 2–3
# zapytania, nie budżet.
OKNO_ODSWIEZENIA_BC_S = 6 * 3600
# Ile meczów maksymalnie trzymamy w pamięci między cyklami (bezpiecznik
# objętości klucza — jedna paczka to ~30 kB przy 60 kwotowanych zawodnikach).
MAX_MECZOW_W_PAMIECI_BC = 80

SH_BASE = "https://www.statshub.com/api"
SH_HEADERS = {"Accept": "application/json", "Referer": "https://www.statshub.com/"}


# Klucze faktycznie zapisane w BIEŻĄCYM uruchomieniu main() — manifest na końcu
# cyklu mówi push_supabase.py, które pliki wolno wypchnąć. Bez tego awaria w
# środku cyklu (np. statshub padnie) kończy się `return` PRZED dumpem części
# plików — zostają w wersji ze świeżego `git checkout` (stare/puste dane
# commitowane w repo), a push_supabase i tak by je wypchnął na produkcję,
# cicho nadpisując żywe dane w Supabase starymi.
_generated_this_run: set[str] = set()

# Adapter trybu ligowego (build_league.TrybLigowy) — None = klasyczny tryb MŚ.
# Ustawiany na czas JEDNEGO przebiegu przez main(tryb=...). W trybie ligowym
# bez publikacji (dry-run) dumpy idą do podkatalogu liga_dryrun, a rozliczenia
# i zapisy do Supabase są pomijane — produkcja zostaje nietknięta.
_tryb = None


def _dry_run() -> bool:
    return _tryb is not None and not _tryb.publikuj


def _dump(name: str, obj) -> None:
    katalog = WEB_DATA_DIR / "liga_dryrun" if _dry_run() else WEB_DATA_DIR
    katalog.mkdir(parents=True, exist_ok=True)
    (katalog / name).write_text(
        json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    if name.endswith(".json") and not _dry_run():
        _generated_this_run.add(name[:-5])


def _rozlicz_i_zapisz(
    value_bets: list[dict],
    kupony_list: list[dict],
    niedostepni: set[int] | None = None,
    conf_mids: set[int] | None = None,
    odrzucone_pomiar: list[dict] | None = None,
    poza_publikacja: list[dict] | None = None,
    legi_pool: list[dict] | None = None,
    drabinki: list[dict] | None = None,
    urealnienie: dict[str, float] | None = None,
    przewaga: dict[str, dict] | None = None,
    pasma: dict[str, dict] | None = None,
    sciaganie: tuple[float, float] | None = None,
) -> None:
    """Rozliczanie + zapis wyników. Wywoływane w KAŻDYM cyklu — także gdy
    statshub nie ma propsów (rozliczenia nie mogą czekać na nowe typy).

    kupony.json = AKTYWNE kupony z logu (zamrożone przy publikacji), a nie
    świeżo wygenerowana lista — dzięki temu strona /kupony pokazuje dokładnie
    to, co potem trafi do historii, i nic nie zmienia się między cyklami.
    Przy błędzie NIE nadpisujemy plików — zostają wyniki z poprzedniego cyklu.
    """
    if _dry_run():
        print(f"[dry-run liga] rozliczanie i log typów POMINIĘTE "
              f"({len(value_bets)} typów, {len(kupony_list)} kuponów w pamięci)")
        return
    try:
        # typy pomiarowe (odrzucone przy progu) i typy poza publikacją
        # (kwarantanna/limit meczu) dokładamy WYŁĄCZNIE do logu rozliczeń —
        # value_bets.json (UI) idzie bez nich
        wyniki = rozliczanie.rozlicz(
            value_bets + (odrzucone_pomiar or []) + (poza_publikacja or []),
            kupony_list, niedostepni, conf_mids=conf_mids,
            legi_pool=legi_pool, drabinki=drabinki,
        )
    except Exception as ex:
        print(f"Rozliczanie pominięte ({ex}) — poprzednie wyniki bez zmian")
        return
    # CZY BIJEMY CENĘ — per rynek i strona. To jest odpowiedź na jedyne
    # pytanie, które decyduje, czy rynek ma dla nas sens (patrz
    # rozliczanie.przewaga_rynkow). Idzie do widoku diagnostycznego, żeby dało
    # się śledzić, który rynek zbliża się do wejścia na listę, a który odjeżdża.
    if przewaga:
        wyniki["przewaga_rynkow"] = przewaga
    if pasma:
        wyniki["przewaga_pasm"] = pasma
    _dump("typy_wyniki.json", wyniki)

    # NORMALIZACJA KUPONU DO POKAZANIA MIESZKA W `rozliczanie` (2026-08-01).
    # Była tutaj jako funkcja zagnieżdżona i przez to obowiązywała tylko duży
    # cykl — a klucz `kupony` zapisuje też `rozlicz_only`, co 20 minut. Efekt
    # był taki, że naprawa wartości netto wracała do stanu sprzed naprawy przy
    # pierwszym lekkim rozliczeniu (patrz rozliczanie.kupon_do_pokazania).
    _dump("kupony.json", [
        rozliczanie.kupon_do_pokazania(k, urealnienie, sciaganie)
        for k in wyniki["kupony"]
        if k.get("wynik") is None and not k.get("pominiety")
    ])
    p = wyniki["podsumowanie"]
    print(f"Typy: {p['opublikowane']} w logu, {p['rozliczone']} rozliczonych, "
          f"{p['trafione']} trafionych, ROI flat {p['roi_flat']:+.2f} j.")
PUBLIKACJE_KLUCZ = "publikacje_typy"
# Profil drużyn (ile notują, ile dopuszczają) pamiętany między cyklami —
# patrz `model/profil_druzyn.py` i użycie przy czynniku rywala.
PROFIL_DRUZYN_KLUCZ = "druzyny_profil"


def _klucz_publikacji(b: dict) -> str:
    return (f"{b.get('mecz_id')}:{rotowire._norm(str(b.get('podmiot') or ''))}"
            f":{b.get('rynek_kod')}:{b.get('linia')}:{b.get('strona')}")


def _typ_z_logu(rec: dict) -> dict:
    """Karta typu odtworzona z KSIĘGI ROZLICZEŃ — uboższa, ale prawdziwa.

    Rejestr publikacji trzyma pełny rekord typu, ale sam bywa młodszy niż typy,
    które ma chronić (wpisy sprzed jego wdrożenia), i teoretycznie może się
    zgubić. Księga rozliczeń jest drugim, niezależnym źródłem: wie o KAŻDYM
    opublikowanym typie, z ceną i szansą zamrożonymi przy pierwszej publikacji.
    Nie ma za to rentgenu (czynniki, uzasadnienie, przedział, rozkład), więc
    karta jedzie oznaczona `uproszczony`, żeby front nie udawał pełnej analizy.
    """
    mecz = str(rec.get("mecz") or "")
    strony = [s.strip() for s in mecz.split("–")] if "–" in mecz else []
    podmiot = str(rec.get("podmiot") or "")
    # `match_`/`wiecej_` to też rynki DRUŻYNOWE — to miejsce znało tylko
    # `team_`, więc suma meczowa wznowiona z księgi wracała jako typ
    # ZAWODNICZY i lądowała na stronie głównej zamiast w Drużynach
    # (strona filtruje po `podmiot_typ`). Ta sama klasa pomyłki co
    # w rozliczaniu przed 01.08 — stąd wspólna stała.
    druzynowy = str(rec.get("rynek_kod") or "").startswith(
        betting.PRZEDROSTKI_DRUZYNOWE
    )
    przeciwnik = ""
    if druzynowy and len(strony) == 2:
        przeciwnik = strony[1] if strony[0] == podmiot else strony[0]
    kurs = rec.get("kurs")
    p = float(rec.get("p_model") or 0.0)
    return {
        "id": 0,   # nadawane przy scalaniu (patrz `scal_z_publikacjami`)
        "mecz_id": rec.get("mecz_id"), "mecz": mecz,
        "kickoff_ts": rec.get("kickoff_ts"),
        "podmiot_typ": "druzyna" if druzynowy else "zawodnik",
        # NUMER DRUŻYNY BEZ MINUSA (2026-08-03). Księga trzymała część klubów
        # pod ujemnym numerem (wyciek z pomiaru progów — patrz
        # `rozliczanie._znak_podmiotu`), a strona szuka po nim formy drużyny.
        # Rozliczanie prostuje to u źródła, ale karta ma być poprawna także
        # zanim tamten przebieg dotknie danego rekordu.
        "podmiot_id": (
            abs(rec["podmiot_id"])
            if druzynowy and isinstance(rec.get("podmiot_id"), int)
            else rec.get("podmiot_id")
        ),
        "podmiot": podmiot,
        "druzyna": podmiot if druzynowy else "", "przeciwnik": przeciwnik,
        "rynek_kod": rec.get("rynek_kod"), "rynek": rec.get("rynek"),
        "linia": rec.get("linia"), "strona": rec.get("strona"),
        "kurs": kurs, "bukmacher": rec.get("bukmacher") or "",
        "kurs_ref": rec.get("kurs_ref"),
        "p_model": p, "p_rynku": None,
        "fair_kurs": round(1.0 / max(p, 1e-6), 2),
        "edge_pp": None,
        "ev_pct": round(betting.ev_brutto_pct(p, kurs), 1) if kurs else None,
        "ev_netto": round(betting.ev_pct(p, kurs), 1) if kurs else None,
        "tryb_podatku": betting.tryb_podatku(rec.get("bukmacher")),
        "pewnosc": rec.get("pewnosc") or "srednia",
        "pewnosc_score": 55.0, "ryzyko": "srednie", "rank_score": 0.0,
        "ci": [None, None], "oczekiwane_minuty": None,
        "lambda": 0.0, "rozklad": None,
        "czynniki": {}, "uzasadnienie": {"czynniki": []},
        "pewniak": bool(rec.get("pewniak")),
        "wyzsza_linia": bool(rec.get("wyzsza_linia")),
        "matchup": bool(rec.get("matchup")),
        "rotacja": bool(rec.get("rotacja")),
        "miekka_linia": bool(rec.get("miekka_linia")),
        "opublikowano_ts": rec.get("opublikowano_ts"),
        "wznowiony": True, "uproszczony": True,
    }


def _mecz_z_logu(rec: dict) -> dict | None:
    """Minimalny rekord meczu dla typu odtworzonego z księgi — bez niego
    apka nie ma gdzie takiego typu pokazać."""
    strony = [s.strip() for s in str(rec.get("mecz") or "").split("–")]
    if len(strony) != 2 or not all(strony) or rec.get("mecz_id") is None:
        return None
    return {
        "id": rec["mecz_id"], "liga": rec.get("liga") or "", "sezon": "",
        "kolejka": None, "kickoff_ts": rec.get("kickoff_ts"),
        "gospodarz": strony[0], "gosc": strony[1],
        "sedzia": None, "sedzia_mnoznik_fauli": 1.0,
        "okazje": [], "sklady_ogloszone": False,
    }


def domknij_terminarz(
    matches_out: dict, mids_zakresu, rekord_meczu, propsy_by_mid: dict | None = None,
    mids_z_kursami: set | None = None,
) -> int:
    """Mecz z zakresu skanu, dla którego MAMY KURSY, ląduje w `matches` — także
    wtedy, gdy nie dał ani jednego typu.

    ZGŁOSZENIE USERA 2026-08-03: „w Meczach i Drużynach brakuje jutrzejszych
    kwalifikacji Ligi Mistrzów". Odkrywanie i parowanie działały bez zarzutu
    (48 z 54 kwalifikacji sparowanych z Superbetem), model je policzył — ale
    mecz trafiał do `matches` wyłącznie dwiema drogami: przez trend ZAWODNICZY
    albo przy dopisywaniu okazji. Kwalifikacje nie mają propsów (Superbet ich
    nie kwotuje), a wszystkie ich rynki drużynowe odpadły na bramach, więc mecz
    znikał ze strony bez śladu. Zmierzone: 94 mecze weszły do liczenia, 60 było
    na stronie.

    To ta sama klasa błędu, którą dla typów łata `scal_z_publikacjami` — tyle że
    tamto ratuje mecz, który KIEDYŚ dał typ. Mecz, który nie dał go nigdy, nie
    miał żadnej drogi na stronę.

    Zakładka Mecze to „terminarz skanu", więc jej zawartością ma być ZAKRES
    skanu, a nie jego wynik. Zero typów to informacja dla usera (razem
    z powodami z rejestru odrzuceń), a nie powód, żeby ukryć mecz.

    GRANICA TEGO ZAKRESU TO KURSY (`mids_z_kursami`, doprecyzowane 03.08 po
    uwadze usera: „w Meczach mają być tylko mecze, które mają pokrycia
    i kursy"). Pierwsza wersja przemiatała cały zakres drużynowy i dołożyła 40
    meczów, z czego 6 nie miało ANI JEDNEGO kwotowania — ani rynku drużynowego,
    ani propsa. Taki mecz nie jest „przeanalizowany bez wyniku", tylko
    nietknięty: nie ma na nim czego pokazać ani czego wyjaśnić, bo nie powstało
    nawet odrzucenie z powodem. Mecz z kursami, którego typy odpadły na bramach
    (kurs poza widełkami, za niska szansa), zostaje — tam user ma i liczby,
    i powód.

    Zwraca, ile meczów dołożono.
    """
    bylo = len(matches_out)
    for mid in sorted(mids_zakresu):
        if mids_z_kursami is not None and mid not in mids_z_kursami:
            continue
        rec = rekord_meczu(mid)
        if rec is None:
            continue
        # ile propsów kwotuje bukmacher — pętla zawodnicza ustawia to tylko dla
        # meczów, przez które przeszła; `setdefault` nie nadpisze jej liczby
        rec.setdefault("propsy_superbet", (propsy_by_mid or {}).get(mid, 0))
    return len(matches_out) - bylo


# ILE SZANSA MOŻE SIĘ ROZJECHAĆ, ŻEBY ŚWIEŻY RACHUNEK NADAL PASOWAŁ DO KARTY
# (2026-08-04). Karta wznowiona pokazuje szansę ZAMROŻONĄ przy publikacji, a
# rentgen dokładamy policzony dziś. Przy dużym rozjeździe te dwie rzeczy
# przestają być o tym samym — wtedy lepiej zostawić kartę uproszczoną niż
# tłumaczyć liczbę czynnikami, które prowadzą do innej liczby.
RENTGEN_MAX_ROZJAZD_P = 0.05


# =========================================================================
# LISTA DNIA — jedna publikacja dziennie, potem skład się nie zmienia
# =========================================================================
#
# ⚑ DOBA PRODUKTOWA 6:00 -> 6:00, NIE KALENDARZOWA. Rozkład godzin gwizdka
# (czas polski, 862 typy): 00:00-04:00 = 355 typów, czyli **41%** naszej
# listy to mecze grane nad ranem — Ameryka Płd. Przy dobie kalendarzowej
# „lista na piątek" domykana o 6:00 w piątek zawierałaby mecze, które
# zaczęły się o 2:00 w nocy, czyli cztery godziny wcześniej.
#
# Dzień listy D = mecze od 6:00 dnia D do 6:00 dnia D+1. Klient wchodzi rano
# i widzi komplet tego, co realnie może dziś obstawić: europejskie wieczory
# i południowoamerykańską noc.
#
# ⚑ CZEGO TO NIE ZMIENIA: `rozliczanie.dzien_pl` (doba kalendarzowa) zostaje
# definicją dla rozliczeń, Skuteczności i archiwum. Zmiana tamtej przestawiłaby
# całą historię — raz już mieliśmy 11% typów pod złą datą, gdy doba liczyła się
# strefą maszyny ([[doba-czasem-polskim]]). Konsekwencja do zaakceptowania:
# mecz o 2:00 w nocy z piątku na sobotę jest na liście PIĄTKOWEJ, a w
# Skuteczności pod datą SOBOTNIĄ. Dwie jednostki, każda poprawna u siebie.
GODZINA_DOMKNIECIA = 6


def _lokalnie(ts) -> _dt.datetime:
    """Czas polski. Bez bazy stref zostaje strefa maszyny — tak jak w rozliczaniu."""
    if rozliczanie.STREFA is None:                          # pragma: no cover
        return _dt.datetime.fromtimestamp(int(ts))
    return _dt.datetime.fromtimestamp(
        int(ts), _dt.timezone.utc).astimezone(rozliczanie.STREFA)


def dzien_listy(ts, godzina: int = GODZINA_DOMKNIECIA) -> str:
    """Doba PRODUKTOWA („YYYY-MM-DD") — mecz o 2:00 należy do dnia poprzedniego."""
    if not ts:
        return ""
    d = _lokalnie(ts)
    if d.hour < godzina:
        d -= _dt.timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def moment_domkniecia(dzien: str, godzina: int = GODZINA_DOMKNIECIA) -> int:
    """Kiedy (ts) domyka się lista dnia `dzien` — o `godzina`:00 czasu polskiego.

    Uwaga na zmianę czasu: godzina jest przypinana do daty W STREFIE, więc
    doba przestawiana z lata na zimę ma 25 godzin i to jest poprawne.
    """
    d = _dt.datetime.strptime(dzien, "%Y-%m-%d").replace(
        hour=godzina, minute=0, second=0, microsecond=0)
    if rozliczanie.STREFA is not None:
        d = d.replace(tzinfo=rozliczanie.STREFA)
    return int(d.timestamp())


def moc_listy(b: dict, kandydatow_w_meczu: int) -> float:
    """Kolejność „polecane" — JEDNA miara dla wszystkich kanałów listy.

    Podstawa: szansa × pierwiastek z kursu. Sama szansa wynosiłaby na górę
    wyłącznie linie 0,5, a sama wartość — najdłuższe strzały; pierwiastek
    tłumi kurs na tyle, żeby typ 87% po 1,21 wygrał z typem 43% po 3,55, ale
    nie na tyle, żeby kurs przestał się liczyć.

    Do tego jeden zmierzony czynnik: BOGACTWO MATERIAŁU MECZU, czyli ile
    typów model w tym meczu w ogóle wystawił (liczby i zastrzeżenia przy
    `PROG_BOGATEGO_MECZU`). Skrót: przy 10+ kandydatach luka deklaracji spada
    z około −20 pp do −9 pp i lepiej.

    ⚑ `kandydatow_w_meczu` liczy się z PULI PRZED SELEKCJĄ, nie z gotowej
    listy. Inaczej powstałoby błędne koło (kolejność zależy od listy, lista od
    kolejności), a przy pomiarze — zaglądanie w przyszłość, bo liczba typów,
    które przeżyły bramy, jest znana dopiero po fakcie.

    ⚑ To jest KOLEJNOŚĆ, nie brama i nie korekta szansy: żaden typ przez to
    nie znika z listy ani nie zmienia liczby na karcie.

    Front bierze gotową liczbę zamiast liczyć własną kopię formuły
    ([[kupony-przebudowa-domknieta]], lekcja o kopii konfiguracji backendu
    we froncie).
    """
    kurs = b.get("kurs") or b.get("fair_kurs") or 1.0
    moc = float(b.get("p_model") or 0.0) * (float(kurs) ** 0.5)
    if kandydatow_w_meczu >= PROG_BOGATEGO_MECZU:
        moc *= PREMIA_BOGATEGO_MECZU
    return round(moc, 4)


def scal_z_publikacjami(
    value_bets: list[dict], matches_out: dict, teraz: int | None = None,
    typy_log: dict | None = None, liga_by_mid: dict | None = None,
    policzone_w_cyklu: list[dict] | None = None,
) -> tuple[list[dict], int]:
    """Lista typów = wszystko, co OPUBLIKOWANE i czeka na gwizdek.

    Dotąd `value_bets.json` był wynikiem BIEŻĄCEGO przeliczenia, więc typ
    znikał userowi sprzed nosa, gdy tylko cykl przestawał go odtwarzać —
    mimo że dawno poszedł do `typy_log` i normalnie się rozliczy. Zmierzone
    2026-07-26 na Wiśle Kraków–GKS: o 13:31 trzy typy drużynowe, o 14:05
    zero, kursy Superbetu nietknięte. Powód nie leżał po stronie oceny —
    feed przestał zwracać trend dla GKS, a przy zerze typów mecz wypadał
    nawet z `matches`, więc w apce nie zostawał po nim ślad.

    `kupony.json` od dawna działa właśnie tak (aktywne kupony z logu,
    zamrożone przy publikacji) — to przeniesienie tej samej zasady na typy.
    Wpis wraca z ZAMROŻONYM kursem z chwili publikacji i flagą `wznowiony`,
    żeby front mógł powiedzieć wprost, że to typ z wcześniejszego cyklu.
    Razem z typem wraca jego rekord meczu — bez tego apka nie ma gdzie go
    pokazać.

    `liga_by_mid` = etykiety rozgrywek z BIEŻĄCEGO terminarza (tryb.liga_by_mid).
    Wznowiony mecz wraca z księgi albo rejestru, a te struktury dostały stempel
    rozgrywek dopiero 03.08 — starsze wpisy niosą pustą ligę. Pusta liga nie jest
    kosmetyką: zakładka Mecze filtruje domyślnie po „naszych ligach", więc mecz
    bez etykiety znikał userowi z terminarza, mimo że typ na niego stał na
    liście (zmierzone 03.08: 17 kwalifikacji pucharów). Skoro mecz jest w tym
    cyklu w terminarzu, znamy jego rozgrywki — i tu je dopisujemy.

    Zwraca (lista do publikacji, ile wpisów wznowiono). Mutuje `matches_out`.
    """
    teraz = teraz or int(time.time())
    ligi = liga_by_mid or {}

    def _z_terminarza(mecz: dict | None) -> dict | None:
        """Uzupełnij etykiety rozgrywek z bieżącego terminarza."""
        if not mecz:
            return mecz
        et = ligi.get(mecz.get("id"))
        if et and not mecz.get("liga"):
            mecz["liga"] = et.get("liga", "")
            mecz["sezon"] = mecz.get("sezon") or et.get("sezon", "")
            if not mecz.get("kolejka"):
                mecz["kolejka"] = et.get("kolejka", "")
        return mecz

    rej_raw, odczyt_ok = supa.get_key_ok(PUBLIKACJE_KLUCZ)
    # nieudany odczyt rejestru = pracujemy bez niego, ale NIE zapisujemy go
    # z powrotem (inaczej garstka typów z tego cyklu zastąpiłaby cały rejestr)
    rej = rej_raw or {}
    # LICZNIKI REJESTRU (2026-08-04). Rejestr jest JEDYNYM nośnikiem rentgenu
    # typu, a zmierzone tego dnia: 6 wpisów wobec 46 typów przed gwizdkiem
    # w księdze — czyli 40 kart wraca na stronę bez rachunku. Kod wygląda
    # poprawnie (wpis ginie dopiero po gwizdku), więc zanim cokolwiek w nim
    # ruszymy, cykl ma POWIEDZIEĆ, co się z wpisami dzieje: ile zastał, ile
    # skasował po gwizdku, ile dopisał i z czym został.
    _rej_na_wejsciu = len(rej)
    biezace = {_klucz_publikacji(b) for b in value_bets}
    _rej_nowych = sum(1 for k in biezace if k not in rej)

    for b in value_bets:
        k = _klucz_publikacji(b)
        rej[k] = {
            # STEMPEL WERSJI TRAFIA DO REJESTRU (2026-08-11). Dotąd `wersje`
            # nakładało dopiero `rozliczanie._dopisz_nowe`, więc rejestr
            # publikacji — jedyne miejsce, z którego typ WRACA na listę —
            # nie wiedział, którym rachunkiem policzono jego `p`. Bez tego
            # reguła „wznowienia między wersjami zabronione" (niżej) nie ma
            # czego sprawdzić.
            "bet": {
                **{kk: vv for kk, vv in b.items() if kk != "kal_tau"},
                "wersje": betting.wersje_publikacji(),
            },
            "mecz": matches_out.get(b.get("mecz_id")),
            "kickoff_ts": b.get("kickoff_ts"),
            # pierwsza publikacja wygrywa — to ona jest cena, ktora wzial user
            "opublikowano_ts": (rej.get(k) or {}).get("opublikowano_ts") or teraz,
        }

    # cena z księgi rozliczeń per typ — to ONA rozliczy typ i to ją musi
    # pokazywać wznowiona karta (patrz niżej)
    kurs_ksiegi = {
        _klucz_publikacji(r): r.get("kurs")
        for r in (typy_log or {}).values() if r.get("kurs")
    }

    out = list(value_bets)
    wznowione = 0
    odtworzone = set(biezace)
    _skasowane_po_gwizdku = 0
    _skasowane_bez_daty = 0
    _wznow_obca_wersja = 0   # patrz reguła wersji przy wznawianiu, niżej
    for k, rec in list(rej.items()):
        ts_k = int(rec.get("kickoff_ts") or 0)
        # brak kickoffu traktujemy jak po gwizdku: wpis bez daty nigdy by nie
        # wygasł i wracałby na listę w nieskończoność
        if ts_k <= teraz:
            # ROZDZIELONE, bo to dwie różne historie: wpis po gwizdku znika
            # zgodnie z projektem, a wpis BEZ DATY to podejrzenie, że rejestr
            # zjada typy przed czasem (patrz liczniki wyżej)
            _skasowane_bez_daty += not ts_k
            _skasowane_po_gwizdku += bool(ts_k)
            del rej[k]           # mecz się zaczął — typ żyje dalej w typy_log
            continue
        if k in biezace:
            continue
        bet = dict(rec.get("bet") or {})
        if not bet:
            continue
        # ⚑ WZNOWIENIA MIĘDZY WERSJAMI SĄ ZABRONIONE (2026-08-11, warunek
        # wdrożenia V2).
        #
        # Typ policzony poprzednią wersją kalibracji niesie ZAMROŻONE `p`
        # z tamtego rachunku — a przy naprawie orientacji kalibracji
        # (`rozliczanie.w_orientacji_over`) delty rynków drużynowych zmieniły
        # ZNAK. Wznawiając taki typ, pokazalibyśmy szansę, o której już wiemy,
        # że jest liczona odwrotnie, i to bez żadnego znaku dla użytkownika,
        # które liczby są z której wersji. Zmierzone przy wdrożeniu: 119 ze 133
        # typów na liście to byłyby wznowienia sprzed naprawy.
        #
        # Przeliczyć się ich NIE DA: surowego `p` sprzed kalibracji rynkowej
        # nie odzyskamy dla rekordów bez stempla `kal_rynek` (wprowadzony
        # razem z tą regułą, więc pierwsze mają go dopiero typy V2).
        #
        # Rekord zostaje w rejestrze i w księdze — rozliczy się i policzy jako
        # V1, tylko nie wraca na LISTĘ REKOMENDACJI. To jest różnica między
        # „usuwamy historię" a „przestajemy to polecać".
        _w_bet = (bet.get("wersje") or {}).get("kalibracja")
        if _w_bet != betting.WERSJA_KALIBRACJI:
            _wznow_obca_wersja += 1
            continue
        bet["wznowiony"] = True
        bet["opublikowano_ts"] = rec.get("opublikowano_ts")
        # CENA ZAMROŻONA, tak jak obiecuje karta. Rejestr odświeżał `bet`
        # w każdym cyklu, więc wznowiony typ pokazywał ostatnią widzianą cenę,
        # a księga rozliczy go po cenie z PIERWSZEJ publikacji — user widziałby
        # 1,28 i dostał ROI liczone z 1,23.
        if kurs_ksiegi.get(k) and bet.get("kurs") != kurs_ksiegi[k]:
            bet["kurs"] = kurs_ksiegi[k]
            p = float(bet.get("p_model") or 0.0)
            bet["ev_pct"] = round(betting.ev_brutto_pct(p, bet["kurs"]), 1)
            bet["ev_netto"] = round(
                betting.ev_pct(p, bet["kurs"], bet.get("tryb_podatku")), 1
            )
        # STEMPEL TRYBU PODATKOWEGO na typach WZNOWIONYCH (2026-07-31).
        # Typ raz pokazany zostaje na liście do gwizdka, więc wraca tu
        # z rejestru publikacji albo z księgi rozliczeń — a te struktury
        # powstały PRZED podatkiem i pola nie niosą. Zmierzone na produkcji
        # zaraz po wdrożeniu: 59 ze 153 typów na stronie było bez stempla.
        #
        # Dziś to nieszkodliwe, bo brak trybu = „standard" wszędzie, gdzie
        # się go czyta. Ale cały sens zapisywania trybu PRZY TYPIE polega na
        # tym, że historia pamięta, w czym była liczona — a rekord bez pola
        # dostanie tryb dopiero przy rozliczeniu, czyli już wg konfiguracji
        # z TAMTEJ chwili, nie z chwili publikacji.
        bet.setdefault(
            "tryb_podatku", betting.tryb_podatku(bet.get("bukmacher"))
        )
        out.append(bet)
        odtworzone.add(k)
        wznowione += 1
        mid = bet.get("mecz_id")
        if mid is not None and mid not in matches_out and rec.get("mecz"):
            matches_out[mid] = _z_terminarza(dict(rec["mecz"]))

    # DRUGIE ŹRÓDŁO: księga rozliczeń. Rejestr wyżej chroni tylko to, co przez
    # niego przeszło — typy opublikowane, zanim powstał (albo w cyklu, w którym
    # zapis do bazy padł), znikały userowi mimo że normalnie się rozliczą.
    # Zmierzone 2026-07-26 na Wiśle Kraków–GKS: pięć typów drużynowych w księdze,
    # zero na liście, bo rejestr wdrożyliśmy cztery godziny po ich publikacji.
    # RENTGEN Z BIEŻĄCEGO CYKLU (2026-08-04). Typ zdjęty bramą publikacji jest
    # liczony w KAŻDYM cyklu z pełnym rachunkiem — tylko trafia do worka
    # `typy_poza_publikacja` i tam ginie. Tymczasem ten sam typ wraca na listę
    # z księgi jako „uproszczony", bo księga rentgenu nie trzyma.
    #
    # Zmierzone tego dnia: 9 z 20 kart na stronie nie miało czym wypełnić
    # rozwinięcia, a rejestr publikacji — jedyny nośnik rentgenu — trzymał
    # 6 wpisów wobec 46 typów przed gwizdkiem w księdze.
    #
    # Bierzemy WYŁĄCZNIE wyjaśnienie (czynniki, przedział, lambda, rozkład).
    # Cena i szansa zostają zamrożone przy pierwszej publikacji — to po nich
    # typ się rozliczy i to je user widział, gdy typ brał.
    rentgen: dict[str, dict] = {}
    for b in (policzone_w_cyklu or []):
        if b.get("czynniki") or (b.get("uzasadnienie") or {}).get("czynniki"):
            rentgen.setdefault(_klucz_publikacji(b), b)
    _rentgen_dolozony = _rentgen_rozjazd = 0

    def _dolóż_rentgen(bet: dict, k: str) -> dict:
        swiezy = rentgen.get(k)
        if not swiezy:
            return bet
        nonlocal _rentgen_dolozony, _rentgen_rozjazd
        if abs(float(swiezy.get("p_model") or 0.0)
               - float(bet.get("p_model") or 0.0)) > RENTGEN_MAX_ROZJAZD_P:
            _rentgen_rozjazd += 1
            return bet
        bet.update({
            "czynniki": swiezy.get("czynniki") or {},
            "uzasadnienie": swiezy.get("uzasadnienie") or {"czynniki": []},
            "ci": swiezy.get("ci") or [None, None],
            "lambda": swiezy.get("lambda") or 0.0,
            "rozklad": swiezy.get("rozklad"),
            "oczekiwane_minuty": swiezy.get("oczekiwane_minuty"),
            "uproszczony": False,
        })
        _rentgen_dolozony += 1
        return bet

    z_logu = 0
    _rej_uzdrowione = 0
    for rec in (typy_log or {}).values():
        if rec.get("wynik") is not None or rec.get("sugestia"):
            continue                      # rozliczony albo bez kursu
        if rec.get("odrzucony") or rec.get("poza_publikacja"):
            continue                      # nigdy nie był na liście
        if rec.get("zrodlo"):
            continue                      # drabinki mają własną zakładkę i siatkę
        if int(rec.get("kickoff_ts") or 0) <= teraz:
            continue                      # po gwizdku
        # ta sama reguła wersji co przy rejestrze wyżej — księga jest DRUGIM
        # źródłem wznowień, więc bez tego typ V1 wracałby na listę tędy
        if (rec.get("wersje") or {}).get("kalibracja") \
                != betting.WERSJA_KALIBRACJI:
            _wznow_obca_wersja += 1
            continue
        k = _klucz_publikacji(rec)
        if k in odtworzone:
            continue
        bet = _dolóż_rentgen(_typ_z_logu(rec), k)
        if bet["mecz_id"] is None or not bet["kurs"]:
            continue
        out.append(bet)
        odtworzone.add(k)
        z_logu += 1
        mid = bet["mecz_id"]
        if mid not in matches_out:
            mecz = _z_terminarza(_mecz_z_logu(rec))
            if mecz:
                matches_out[mid] = mecz
        # SAMOLECZENIE REJESTRU (2026-08-06). Wpis rejestru powstaje tylko
        # w cyklu narodzin typu — jeśli tamten jeden zapis padł, karta wracała
        # z księgi bez rachunku już NA ZAWSZE, nawet gdy rentgen z bieżącego
        # cyklu właśnie jej ten rachunek przywrócił (Superbet zdejmuje linię
        # i rentgen znika razem z nią; zmierzone 06.08: pięć kart „gole
        # poniżej 0,5" bez analizy, wszystkie z nocnych cykli 04–05.08).
        # Odzyskany rachunek zapisujemy więc do rejestru — jednorazowa czkawka
        # zapisu przestaje być wyrokiem. Cena i szansa są już zamrożone
        # w `bet`, więc wpis niczego nie odświeży w złą stronę.
        if not bet.get("uproszczony") and k not in rej:
            rej[k] = {
                # stempel wersji jak w głównej pętli wyżej — tędy przechodzą
                # wyłącznie rekordy, które właśnie przeszły kontrolę wersji,
                # więc wpisujemy bieżącą (`_typ_z_logu` pola nie przenosi)
                "bet": {
                    **{kk: vv for kk, vv in bet.items() if kk != "kal_tau"},
                    "wersje": betting.wersje_publikacji(),
                },
                "mecz": matches_out.get(mid),
                "kickoff_ts": bet.get("kickoff_ts"),
                "opublikowano_ts": bet.get("opublikowano_ts") or teraz,
            }
            _rej_uzdrowione += 1

    # id typów są numerowane od zera w każdym cyklu, więc wpis wznowiony potrafi
    # trafić na cudzy numer — front używa ich jako kluczy i kotwic (#bet-N)
    uzyte = {b.get("id") for b in value_bets}
    nastepne = max([i for i in uzyte if isinstance(i, int)] or [0]) + 1
    for b in out[len(value_bets):]:
        if b.get("id") in uzyte or not isinstance(b.get("id"), int):
            b["id"] = nastepne
        uzyte.add(b["id"])
        nastepne = max(nastepne, b["id"]) + 1

    # ZAPIS REJESTRU MUSI BYĆ SŁYSZALNY (2026-08-03).
    #
    # Rejestr jest JEDYNYM miejscem, w którym przeżywa rentgen typu (czynniki,
    # przedział, lambda) — księga rozliczeń go nie trzyma, więc typ, który
    # z rejestru wypadnie, wraca na stronę jako „uproszczony" i nie ma czym
    # wypełnić rozwinięcia. Zmierzone 02.08: 12 z 16 typów na stronie było
    # uproszczonych, a w rejestrze siedziało tylko 5 z nich.
    #
    # Wpis powstaje TYLKO w tym cyklu, w którym typ policzono na świeżo. Jeśli
    # ten jeden zapis się nie uda, typ nie dostanie drugiej szansy — w kolejnym
    # cyklu nie ma go już w `value_bets`. Dlatego nieudany zapis musi krzyczeć,
    # a nie wracać cichym False.
    #
    # NIE `put_key_bezpiecznie`: ten rejestr kurczy się Z NATURY (wpisy giną po
    # gwizdku), więc bezpiecznik „nie nadpisuj mniejszym" blokowałby zapis
    # w każdy weekend z dużą liczbą gwizdków — patrz ostrzeżenie w docstringu
    # `supa.put_key_bezpiecznie`.
    print(f"Rejestr publikacji: zastano {_rej_na_wejsciu}, dopisano "
          f"{_rej_nowych} nowych z {len(value_bets)} świeżych, skasowano "
          f"{_skasowane_po_gwizdku} po gwizdku"
          + (f" + {_skasowane_bez_daty} BEZ DATY" if _skasowane_bez_daty else "")
          + f", zostaje {len(rej)}; wznowiono z niego {wznowione}, "
          f"z księgi {z_logu}")
    if z_logu:
        print(f"Rentgen z bieżącego cyklu: {_rentgen_dolozony} z {z_logu} kart "
              f"wznowionych z księgi odzyskało rozpisany rachunek"
              + (f" ({_rentgen_rozjazd} pominięte — szansa rozjechała się "
                 f"o ponad {RENTGEN_MAX_ROZJAZD_P*100:.0f} pp)"
                 if _rentgen_rozjazd else "")
              + (f"; {_rej_uzdrowione} z nich dopisane z powrotem do rejestru"
                 if _rej_uzdrowione else ""))
    # CICHE POMINIĘCIE ZAPISU (załatane 2026-08-04). Gdy odczyt rejestru padł,
    # ten `if` przechodził bokiem BEZ SŁOWA — a to znaczy, że typy policzone
    # w tym cyklu tracą rentgen na zawsze (wpis powstaje tylko raz, patrz
    # wyżej). Dokładnie ta klasa błędu, o którą chodzi w zasadzie „każde
    # miejsce, które coś odrzuca, ma licznik z powodem".
    if not _dry_run() and not odczyt_ok:
        print("UWAGA: odczyt rejestru publikacji PADŁ — zapis pominięty, żeby "
              f"nie nadpisać historii; {len(value_bets)} typów z tego cyklu "
              "wróci jutro jako uproszczone, bez rozpisanych czynników")
    if not _dry_run() and odczyt_ok:
        if not supa.put_key(PUBLIKACJE_KLUCZ, rej):
            print("UWAGA: zapis rejestru publikacji NIE POWIÓDŁ SIĘ — typy "
                  f"policzone w tym cyklu ({len(value_bets)}) wrócą jutro jako "
                  "uproszczone, bez rozpisanych czynników")
    # OSTATNIA SZANSA NA ETYKIETĘ: rekord meczu mógł wejść do `matches_out`
    # bez ligi także wcześniej (rejestr publikacji trzyma pełną kopię rekordu
    # z chwili publikacji, więc niesie ze sobą także ówczesną pustkę).
    bez_ligi = 0
    for mecz in matches_out.values():
        if not mecz.get("liga"):
            _z_terminarza(mecz)
            bez_ligi += not mecz.get("liga")
    if bez_ligi:
        print(f"Terminarz: {bez_ligi} meczów bez nazwy rozgrywek "
              "(spoza bieżącego zakresu — pokażą się bez etykiety)")

    if wznowione or z_logu:
        print(f"Publikacje: wznowiono {wznowione} typów z rejestru"
              + (f" + {z_logu} z księgi rozliczeń" if z_logu else "")
              + f" (bieżące przeliczenie dało {len(value_bets)})")
    if _wznow_obca_wersja:
        # NIE „zniknęły" — zostają w rejestrze i w księdze, rozliczą się
        # i policzą jako swoja wersja. Przestają tylko być rekomendacją.
        print(f"Wznowienia wstrzymane przez wersję: {_wznow_obca_wersja} typów "
              f"policzonych inną kalibracją niż {betting.WERSJA_KALIBRACJI} "
              "— zostają w księdze, nie wracają na listę")
    return out, wznowione + z_logu


def przytnij_rejestr_do_listy(lista_pub: list[dict], teraz: int) -> int:
    """Zdejmij z rejestru wpisy z TEGO cyklu, które nie weszły na listę.

    `scal_z_publikacjami` rejestruje całe bieżące przeliczenie, ZANIM selekcja
    (`wybierz_liste_publikowana`) ułoży listę dnia — więc rejestr
    trzymał też typy, których nikt nie widział, i co cykl wznawiał je jako
    „wznowione" z zamrożoną ceną, której nikt nie mógł wziąć (zmierzone
    2026-08-06: 141 wpisów wobec 20 typów na stronie). Rejestr ma trzymać
    wyłącznie to, co user naprawdę widział.

    Wpis świeżo dopisany w tym cyklu poznajemy po `opublikowano_ts == teraz`
    (pierwsza publikacja wygrywa, więc starszy wpis zachowuje starszy stempel).
    Wpisów z poprzednich cykli NIE tykamy: to typy naprawdę pokazane,
    chronione do gwizdka. Typ przycięty tutaj wróci do gry, gdy świeże
    przeliczenie znów go wystawi — wtedy zarejestruje się z datą i ceną
    z chwili PRAWDZIWEJ publikacji (patrz odrodzenie w `_dopisz_nowe`).
    """
    rej_raw, odczyt_ok = supa.get_key_ok(PUBLIKACJE_KLUCZ)
    if not odczyt_ok or not rej_raw:
        return 0
    lista_klucze = {_klucz_publikacji(b) for b in lista_pub}
    przyciety = {
        k: v for k, v in rej_raw.items()
        if k in lista_klucze or (v or {}).get("opublikowano_ts") != teraz
    }
    n = len(rej_raw) - len(przyciety)
    if n and not _dry_run():
        if not supa.put_key(PUBLIKACJE_KLUCZ, przyciety):
            print("UWAGA: przycięcie rejestru publikacji NIE POWIODŁO SIĘ — "
                  "wpisy spoza listy zostają do następnego cyklu")
            return 0
    return n


# NIC NIE BLOKUJEMY (zasada stała, user 2026-08-01: „my nie mamy blokować
# nic; mamy miesiąc, żeby nauczyć model na wszystkie typy i kursy").
# Limity poniżej NIE są bramami — żaden rynek, strona ani pasmo ceny nie jest
# wykluczone. To są GWARANCJE RÓŻNORODNOŚCI: pilnują, żeby lista nie zwyrodniała
# w dwadzieścia pozycji z jednego rynku albo z jednego przedziału kursowego.
# Pomiar przewagi układa kolejność, ale nikogo nie usuwa — co się nie zmieści,
# żyje dalej w puli kuponów.
#
# KAŻDY LIMIT LICZY SIĘ OSOBNO NA DZIEŃ (2026-08-07), a od 14.08 na DOBĘ
# PRODUKTOWĄ 6:00 -> 6:00 (`dzien_listy`).
#
# ⚑ ROZMIARY Z 14.08 — decyzja właściciela po pomiarze. Do tego dnia limity
# tylko UDAWAŁY, że działają: deklarowany cap 20 dawał realnie medianę 67
# typów na dzień (13.08 — 185), a „2 typy z meczu" pozwalało na 16. Powód
# i naprawa: nota o kolejności wznowionych w `wybierz_liste_publikowana`.
#
# Skąd 12: symulacja na 419 rozliczeniach pokazała, że przy budżecie 10–15
# typów dziennie i kolejności z premią za bogaty mecz zwrot brutto wychodzi
# dodatni (+1,7% / +1,2%) wobec −3,5% dziś, a przy 20 już nie (−0,7%).
# ⚑ UCZCIWIE: to jest SUFIT, nie obietnica — symulacja wybiera spośród typów,
# które dotrwały do rozliczenia, i zna ich siłę z góry. Netto dalej jesteśmy
# pod kreską (−10,5% przy 10/dzień wobec −15,1% dziś). Limit ma porządkować
# produkt; poprawa zwrotu jest hipotezą do sprawdzenia na nowych danych,
# nie deklaracją.
LISTA_CAP = 12
# 3, nie 2: mecze bogate w typy są naszym najlepszym materiałem (luka
# deklaracji −2,1 pp przy 20+ kandydatach wobec −21,7 pp przy kilku), ale
# przy budżecie 12 pięć typów z jednego meczu to 40% listy.
LISTA_PER_MECZ = 3
LISTA_PER_RYNEK = 4
# ...i tyle samo na przedział kursowy, żeby na liście były i tanie, i drogie
# typy. Bez tego sortowanie po zmierzonej przewadze wypełniłoby listę samym
# pasmem 3,0+ (dziś jedynym, które bije cenę), czyli tanie kursy zniknęłyby
# po cichu, a tego user nie chce.
LISTA_PER_PASMO = 4
# ...i na RODZINĘ STATYSTYKI (2026-08-05, zgłoszenie usera „bez przesytu").
#
# `LISTA_PER_RYNEK` liczy pary (kod, strona) OSOBNO, a kartki mają dwa osobne
# kody: `match_cards` i `team_cards`. Dla nas to różne rynki, dla patrzącego na
# listę to dwa razy to samo słowo — więc w najgorszym razie kartki mogły zająć
# 12 z 20 miejsc, nie łamiąc żadnego limitu. Zmierzone 05.08: 7 z 16 typów
# drużynowych to kartki (44%), przy 3 + 3 + 1 rozbitych na trzy pary.
#
# UWAGA NA DIAGNOZĘ: to NIE jest główna przyczyna przesytu. Pula tego samego
# cyklu ma 71% goli, a opublikowana lista 38% — limity dywersyfikują MOCNIEJ
# niż źródło, a prawdziwym ograniczeniem jest podaż. Ten limit domyka wyłącznie
# przypadek skrajny; zaostrzanie go skróciłoby listę, zamiast ją urozmaicić.
LISTA_PER_RODZINA = 4
# ...i JEDEN TYP NA ZAWODNIKA W DNIU (2026-08-08, przy wpięciu oferty do
# silnika; user: „żeby nie było kanibalizowania").
#
# Do tego dnia strumień zawodniczy jechał praktycznie na jednym rynku
# (41 z 46 typów to strzały), więc pytanie nie powstawało. Po wpięciu oferty
# ten sam zawodnik ma naraz strzały, celne, „zza pola", faule i odbiory —
# a to są rzeczy SKORELOWANE: kto dużo uderza, ten uderza też celnie. Trzy
# pozycje na Mbappé wyglądałyby jak trzy typy, a byłyby jednym zakładem
# w trzech opakowaniach; przy limicie 20 pozycji na dzień zjadłyby miejsce
# typom z innych meczów.
#
# DRUŻYN TO NIE DOTYCZY: „gole poniżej" i „rożne powyżej" tej samej drużyny
# to naprawdę różne zdarzenia, a limit meczu (2) i tak je ogranicza.
LISTA_PER_ZAWODNIKA = 1


def _rodzina_statystyki(kod) -> str:
    """Kartki to kartki, wszystko jedno czyje — `match_cards` i `team_cards`
    to dla użytkownika jedno i to samo."""
    k = str(kod or "")
    for r in ("cards", "corners", "goals", "shots", "sot", "fouls", "tackles"):
        if r in k:
            return r
    return k


def _pasmo_kursu(kurs) -> str:
    try:
        k = float(kurs or 0)
    except (TypeError, ValueError):
        return "?"
    for lo, hi in rozliczanie.PASMA_CENY:
        if lo <= k < hi:
            return f"{lo}-{hi}"
    return "?"


def wybierz_liste_publikowana(
    kandydaci: list[dict], klucz_sortowania, ukryte=frozenset(),
    zamkniete: dict[str, set] | None = None,
) -> tuple[list[dict], dict, dict]:
    """Które typy staną na stronie. Zwraca (lista, zdjęte, ile na dzień).

    TRZY ZASADY:

    1. **Limity liczą się per DZIEŃ.** Dwudziestka na całą listę robiła
       z niej ruchome schody — typ na sobotę konkurował z typem na poniedziałek,
       więc świeże wejście wypychało ze strony typ pokazany trzy dni wcześniej,
       z zamrożoną ceną, którą user mógł już zagrać. Zmierzone 07.08: 45
       żywych typów biło się o 20 miejsc, a 22 z nich (te, które user WIDZIAŁ)
       stały poza stroną. Dzień jest naturalną jednostką: listę czyta się jako
       „co gramy dziś, co jutro".
       ⚑ Od 14.08 to DOBA PRODUKTOWA 6:00 → 6:00 (`dzien_listy`), bo 41% typów
       to mecze grane nad ranem — patrz nota przy `GODZINA_DOMKNIECIA`.

    2. **Typ raz pokazany wchodzi zawsze.** Limity dotyczą wyłącznie NOWYCH
       wejść. Cena wznowionego typu jest zamrożona i po niej rozliczy go księga,
       więc zdjęcie go ze strony przed gwizdkiem znaczyłoby, że user nie ma
       gdzie sprawdzić zakładu, który wziął.
       ⚑ Od 14.08 wznowione są przetwarzane PIERWSZE, więc naprawdę zajmują
       swoje miejsca w limicie (wcześniej mocny nowy typ wchodził przed nimi
       i limit przeciekał — 67 typów dziennie zamiast 20).

    3. **Dzień domknięty się nie zmienia.** Gdy lista dnia została ogłoszona
       (`zamkniete[dzien]` = zbiór kluczy publikacji), wchodzi dokładnie to, co
       w niej stoi. Nowy typ na ten dzień dostaje `dzien_zamkniety` i żyje
       dalej w puli kuponów oraz w rozliczeniach w tle.

    Wyjątkiem zostaje rynek UKRYTY do dopracowania: schodzi ze strony także
    wtedy, gdy był pokazany, i dalej rozlicza się w księdze.
    """
    zamkniete = zamkniete or {}
    z_meczu: dict = {}
    z_rynku: dict = {}
    z_pasma: dict = {}
    z_rodziny: dict = {}
    z_dnia: dict = {}
    z_zawodnika: dict = {}
    lista_pub: list[dict] = []
    zdjete: dict = {}
    # ⚑ WZNOWIONE IDĄ PIERWSZE — NAPRAWA PRZECIEKU LIMITÓW (2026-08-14).
    #
    # Limity sprawdzają się tylko dla NOWYCH wejść, bo typ raz pokazany musi
    # zostać do gwizdka. Licznik rósł jednak dla wszystkich — a ponieważ
    # kandydaci szli wg siły, MOCNY NOWY typ był przetwarzany przed wznowionymi
    # i wchodził, zanim licznik zdążył urosnąć. Dzień zbierał typy przez
    # kilkanaście cykli i 3–4 dni horyzontu, więc rósł bez końca.
    #
    # Zmierzone przed naprawą: LISTA_CAP deklarował 20, a realnie na dzień
    # stała mediana 67 typów (13.08 — 185); LISTA_PER_MECZ deklarował 2, a
    # mecze miały do 16 typów. To ta sama klasa błędu co
    # [[wznowione-omijaly-bramy]], tylko od strony liczników.
    #
    # Naprawa jest jednym posortowaniem: najpierw typy już pokazane (zajmują
    # swoje miejsca), potem nowe wg siły. Nic nie znika ze strony — nowe po
    # prostu wchodzą na to, co realnie zostało wolne.
    # dwa przebiegi, bo `klucz_sortowania` bywa krotką (przewaga, kurs, …),
    # a sort w Pythonie jest stabilny: siła układa kolejność WEWNĄTRZ grup
    kolejnosc = sorted(kandydaci, key=klucz_sortowania, reverse=True)
    kolejnosc.sort(key=lambda b: 0 if b.get("wznowiony") else 1)
    for b in kolejnosc:
        if b.get("sugestia"):
            lista_pub.append(b)      # sugestia nie jest zakładem, nie liczy się
            continue
        # rynek ukryty do czasu dopracowania — zostaje w puli kuponów i dalej
        # rozlicza się w księdze, więc ma jak udowodnić poprawę; świeży typ
        # dostaje znacznik, żeby księga wiedziała, że NIE był na stronie
        if f'{b.get("rynek_kod")}|{b.get("strona")}' in ukryte:
            if not b.get("wznowiony"):
                zdjete.setdefault(_klucz_publikacji(b), "rynek_ukryty")
            continue
        # DOBA PRODUKTOWA (6:00 -> 6:00), nie kalendarzowa — patrz `dzien_listy`.
        # 41% typów to mecze grane nad ranem, a one należą do dnia, w którym
        # człowiek je obstawia, nie do daty w kalendarzu.
        dzien = dzien_listy(b.get("kickoff_ts"))
        if dzien in zamkniete:
            # dzień domknięty: skład jest już ogłoszony i się nie zmienia
            if _klucz_publikacji(b) not in zamkniete[dzien]:
                if not b.get("wznowiony"):
                    zdjete.setdefault(_klucz_publikacji(b), "dzien_zamkniety")
                continue
            lista_pub.append(b)
            z_dnia[dzien] = z_dnia.get(dzien, 0) + 1
            continue
        mecz = (dzien, b.get("mecz_id"))
        rynek = (dzien, b.get("rynek_kod"), b.get("strona"))
        pasmo = (dzien, _pasmo_kursu(b.get("kurs")))
        rodzina = (dzien, _rodzina_statystyki(b.get("rynek_kod")))
        # jeden typ na ZAWODNIKA w dniu (patrz LISTA_PER_ZAWODNIKA); drużyny
        # zostają poza tym licznikiem — u nich rynki nie są tak skorelowane
        zawodnik = (
            (dzien, rotowire._norm(str(b.get("podmiot") or "")))
            if b.get("podmiot_typ") == "zawodnik" else None
        )
        if not b.get("wznowiony"):
            if (z_dnia.get(dzien, 0) >= LISTA_CAP
                    or z_meczu.get(mecz, 0) >= LISTA_PER_MECZ
                    or z_rynku.get(rynek, 0) >= LISTA_PER_RYNEK
                    or z_pasma.get(pasmo, 0) >= LISTA_PER_PASMO
                    or z_rodziny.get(rodzina, 0) >= LISTA_PER_RODZINA
                    or (zawodnik is not None
                        and z_zawodnika.get(zawodnik, 0) >= LISTA_PER_ZAWODNIKA)):
                zdjete.setdefault(_klucz_publikacji(b), "poza_lista_dnia")
                continue
        z_dnia[dzien] = z_dnia.get(dzien, 0) + 1
        z_meczu[mecz] = z_meczu.get(mecz, 0) + 1
        z_rynku[rynek] = z_rynku.get(rynek, 0) + 1
        z_pasma[pasmo] = z_pasma.get(pasmo, 0) + 1
        z_rodziny[rodzina] = z_rodziny.get(rodzina, 0) + 1
        if zawodnik is not None:
            z_zawodnika[zawodnik] = z_zawodnika.get(zawodnik, 0) + 1
        lista_pub.append(b)
    return lista_pub, zdjete, z_dnia


LISTA_DNIA_KLUCZ = "lista_dnia"


def wczytaj_zamkniete(manifest: dict | None) -> dict[str, set]:
    """Manifest z Supabase -> {dzień: zbiór kluczy publikacji}."""
    out: dict[str, set] = {}
    for dzien, wpis in (manifest or {}).items():
        if isinstance(wpis, dict) and wpis.get("zamkniete_ts"):
            out[dzien] = set(wpis.get("klucze") or [])
    return out


def domknij_dni(
    lista_pub: list[dict], manifest: dict | None, teraz: int,
) -> tuple[dict, list[str]]:
    """Zamknij listy dni, których godzina domknięcia właśnie minęła.

    Zwraca (manifest, dni domknięte w tym przebiegu). Manifest jest zapisywany
    przez wywołującego — ta funkcja jest czysta, żeby dała się przetestować.

    ⚑ DOMKNIĘCIE JEST NIEODWRACALNE w obrębie dnia: raz zapisany skład wraca
    z manifestu przy każdym kolejnym cyklu, także wtedy, gdy model przestanie
    dany typ liczyć. To jest cel — klient ma raz zobaczyć listę i móc na niej
    polegać do wieczora.

    ⚑ CZEGO NIE ROBIMY: nie domykamy dnia, który jeszcze się nie zaczął
    (lista na jutro ma prawo rosnąć do swojej 6:00) ani dnia bez ani jednego
    typu — pusty manifest zamroziłby pustkę na cały dzień, gdyby cykl akurat
    padł przed świtem.

    Cron nie chodzi punktualnie (deklaruje 15 minut, realnie ~1–1,5 h), więc
    „o 6:00" znaczy „w pierwszym cyklu po 6:00", a faktyczny moment zapisujemy
    w `zamkniete_ts` — inaczej nie da się później odtworzyć, co i kiedy zostało
    zamrożone.
    """
    manifest = dict(manifest or {})
    dni: dict[str, list[str]] = {}
    for b in lista_pub:
        if b.get("sugestia"):
            continue                       # sugestia nie jest zakładem
        dzien = dzien_listy(b.get("kickoff_ts"))
        if dzien:
            dni.setdefault(dzien, []).append(_klucz_publikacji(b))
    swiezo: list[str] = []
    for dzien, klucze in sorted(dni.items()):
        wpis = manifest.get(dzien) or {}
        if wpis.get("zamkniete_ts"):
            continue                       # już domknięty
        if teraz < moment_domkniecia(dzien):
            continue                       # dzień jeszcze rośnie
        if not klucze:
            continue                       # pustki nie zamrażamy
        manifest[dzien] = {
            "zamkniete_ts": int(teraz),
            "klucze": sorted(set(klucze)),
        }
        swiezo.append(dzien)
    return manifest, swiezo


def przytnij_manifest(manifest: dict | None, teraz: int,
                      dni_wstecz: int = 4) -> dict:
    """Zostaw tylko dni, które jeszcze mogą być komuś potrzebne."""
    granica = dzien_listy(teraz - dni_wstecz * 86400)
    return {d: w for d, w in (manifest or {}).items() if d >= granica}


PUBLIKACJE_KART_KLUCZ = "publikacje_karty"


def scal_karty_z_publikacjami(
    wpisy: list[dict], teraz: int | None = None,
) -> list[dict]:
    """To samo co `scal_z_publikacjami`, ale dla kart drabinek.

    Karta nie jest nigdzie zamrażana: każdy cykl liczy ją od zera z BIEŻĄCYCH
    kursów, a przepustką jest `edge = p_final − 1/kurs ≥ 0,03`. Wystarczy więc,
    że kurs skróci się przez noc o dwa oczka i karta znika — także ta, którą
    user już obstawił. Zmierzone 2026-07-26: z 15 kart z poprzedniego zrzutu
    4 zniknęły z meczów NIEROZEGRANYCH (Bahia–Corinthians, Flamengo–São Paulo,
    Bragantino–Coritiba, Riestra–Boca), a sonda u źródła pokazała, że Superbet
    kwotował te mecze w komplecie (61–75 graczy) — to nasze bramy, nie oferta.

    Wznowiona karta wraca z ZAMROŻONYM `hero` (linia, kurs, przewaga z chwili
    publikacji) i flagą `wznowiony`. Sufit 30 kart obowiązuje tylko NOWE —
    przypięta karta nie może wypaść przez to, że model znalazł dziś coś
    lepszego, bo wtedy wracamy do punktu wyjścia.

    ⚑ ZAMROŻONA JEST CENA, NIE DEFINICJA DRABINKI (2026-08-08). Wznowienie
    chroni kartę przed WAHANIEM KURSU — po to powstało. Nie ma natomiast
    chronić jej przed zmianą reguł: wpis z rejestru wraca z treścią sprzed
    wdrożenia, więc każda nowa reguła omija cały wznowiony strumień.
    Zmierzone dzień po wymogu drugiego szczebla (commit 3338925): 23 z 23
    kart na stronie pochodziły z rejestru, 10 miało jeden szczebel — reguła
    nie zmieniła na stronie NICZEGO, a user zgłosił „nadal stare drabinki".
    Dlatego wznowiona karta przechodzi bramę struktury jeszcze raz, na
    zapisanych liczbach. To ten sam wniosek co przy typach
    ([[wznowione-omijaly-bramy]]): nowe progi wpinamy przy ODTWORZENIU.
    """
    teraz = teraz or int(time.time())
    # jak przy typach: nieudany odczyt = pracujemy bez rejestru, ale go nie
    # nadpisujemy zawartością jednego cyklu
    rej_raw, odczyt_ok = supa.get_key_ok(PUBLIKACJE_KART_KLUCZ)
    rej = rej_raw or {}
    klucz = lambda w: (f"{w.get('mecz_id')}:{w.get('podmiot_id')}"
                       f":{(w.get('hero') or {}).get('rynek_kod')}"
                       f":{(w.get('hero') or {}).get('linia')}")
    biezace = {klucz(w) for w in wpisy}
    for w in wpisy:
        k = klucz(w)
        rej[k] = {
            "wpis": w, "kickoff_ts": w.get("kickoff_ts"),
            "opublikowano_ts": (rej.get(k) or {}).get("opublikowano_ts") or teraz,
        }
    out = list(wpisy)
    wznowione = 0
    bez_drugiego = 0
    nierozstrzygniete = 0
    for k, rec in list(rej.items()):
        # jak przy typach: karta bez kickoffu wygasa od razu, zamiast wracać
        # na listę w nieskończoność
        ts_k = int(rec.get("kickoff_ts") or 0)
        if ts_k <= teraz:
            del rej[k]
            continue
        if k in biezace or not rec.get("wpis"):
            continue
        w = dict(rec["wpis"])
        # brama struktury na wznowieniu (patrz nota w docstringu). Wpis
        # ZOSTAJE w rejestrze — zdejmujemy go z listy, nie z historii; sam
        # wyleci rotacją po gwizdku.
        ma_drugi = radar.karta_ma_realny_drugi_szczebel(w)
        if ma_drugi is False:
            bez_drugiego += 1
            continue
        if ma_drugi is None:
            nierozstrzygniete += 1
        w["wznowiony"] = True
        w["opublikowano_ts"] = rec.get("opublikowano_ts")
        out.append(w)
        wznowione += 1
    if not _dry_run() and odczyt_ok:
        supa.put_key(PUBLIKACJE_KART_KLUCZ, rej)
    if wznowione or bez_drugiego:
        # licznik przy bramie, nie cisza ([[ciche-odrzucenia-zasada]])
        print(f"Publikacje kart: wznowiono {wznowione} "
              f"(bieżące przeliczenie dało {len(wpisy)}), "
              f"bez drugiego szczebla zdjęto {bez_drugiego}"
              + (f", bez zapisanej drabinki {nierozstrzygniete}"
                 if nierozstrzygniete else ""))
    out.sort(key=lambda w: (w.get("kickoff_ts") or 0, w.get("mecz_id") or 0))
    for i, w in enumerate(out, start=1):
        w["id"] = i
    return out


def scal_forme_druzyn(swieza: dict, value_bets: list[dict]) -> list[dict]:
    """Forma drużyn: bieżące przeliczenie DOSYPANE do poprzedniego snapshotu.

    PO CO (2026-08-02, przegląd zakładki Drużyny). `druzyny_forma` była
    budowana OD ZERA w każdym cyklu — wyłącznie z drużyn, dla których akurat
    przyszły świeże trendy. Drużyna bez trendu w danym cyklu traciła historię,
    choć te 20 meczów nigdzie się nie podziało. Skutek widać było na karcie:
    typ WZNOWIONY (a takich jest większość listy) nie miał kroków „skąd ta
    liczba" i „jak było ostatnio", więc rozwinięcie nie tłumaczyło niczego.
    Zmierzone: 11 z 16 typów bez formy, w tym 4 z 9 na półce ryzykownej.

    Świeże dane WYGRYWAJĄ — dosypka jest tylko dla drużyn, których w tym cyklu
    nie policzyliśmy. Historia nie może się cofnąć, ale i nie ma prawa zniknąć.

    Trzymamy wyłącznie drużyny, które mają dziś jakiś typ na liście. Inaczej
    plik puchłby w nieskończoność o kluby, których nikt już nie ogląda.
    """
    # NUMER BEZ ZNAKU (2026-08-03). Ta linia decyduje, KTÓRE drużyny zostają
    # w banku formy — a lista typów niesie też typy wznowione z księgi, które
    # do dziś przychodziły z ujemnym numerem (patrz `rozliczanie._znak_podmiotu`).
    # Snapshot trzyma drużynę pod dodatnim, więc porównanie nie trafiało i bank
    # WYRZUCAŁ formę dokładnie tych drużyn, które jej najbardziej potrzebują:
    # wznowionych. Potem karta nie miała czym pokazać kroku „jak było ostatnio",
    # a wyglądało to na brak danych ze źródła. Zmierzone 03.08: Sønderjyske
    # i IFK Värnamo zniknęły z banku mimo typów na liście.
    potrzebne = {abs(b["podmiot_id"]) for b in value_bets
                 if isinstance(b.get("podmiot_id"), int) and b["podmiot_id"]}
    out = dict(swieza)
    if _dry_run():
        return [v for k, v in out.items() if k in potrzebne or not potrzebne]
    try:
        poprzednia = supa.get_key("druzyny_forma") or []
    except Exception as e:
        print(f"Forma drużyn: poprzedni snapshot niedostępny ({e})")
        return list(out.values())
    # SCALAMY PER RYNEK, NIE PER DRUŻYNĘ (poprawka 2026-08-03).
    #
    # Pierwsza wersja dosypywała tylko BRAKUJĄCE DRUŻYNY, więc drużyna obecna
    # w świeżym cyklu zostawała wyłącznie z rynkami z tego cyklu — a trendy
    # przychodzą per rynek i rzadko komplet naraz. Efekt widać było wprost na
    # karcie: Djurgårdens IF miał typ na rożne, a formę tylko na gole;
    # Cracovia typ na gole, a formę tylko na rożne. Drużyna BYŁA, tylko nie
    # dla tego rynku, o który pytamy — czyli krok „jak było ostatnio" dalej
    # nie miał czego pokazać.
    dosypane_druzyny = dosypane_rynki = 0
    for rec in poprzednia:
        tid = rec.get("id")
        if not isinstance(tid, int) or abs(tid) not in potrzebne:
            continue
        biezacy = out.get(tid)
        if biezacy is None:
            out[tid] = rec
            dosypane_druzyny += 1
            continue
        # drużyna jest świeża, ale mogła stracić rynki, których ten cykl
        # nie policzył — świeży rynek WYGRYWA, brakujący wraca ze starego
        stara_forma = rec.get("forma") or {}
        nowa_forma = biezacy.setdefault("forma", {})
        for rynek, dane in stara_forma.items():
            if rynek not in nowa_forma:
                nowa_forma[rynek] = dane
                dosypane_rynki += 1
    if dosypane_druzyny or dosypane_rynki:
        print(f"Forma drużyn: {len(swieza)} świeżych, dosypano "
              f"{dosypane_druzyny} drużyn i {dosypane_rynki} rynków "
              f"z poprzedniego cyklu")
    return list(out.values())


def mnozniki_pary(h_n: dict, a_n: dict) -> dict:
    """Mnożniki rynku liczonego z DWÓCH drużyn — średnia geometryczna obu stron.

    Suma meczowa nie ma „swojego" rywala ani „swojego" miejsca gry: gospodarz
    gra u siebie, gość na wyjeździe, a każdy z nich ma innego przeciwnika.
    Średnia geometryczna jest tu jedyną uczciwą liczbą, bo λ meczu to suma
    dwóch λ, z których każda została już przemnożona przez własny zestaw.

    Po co w ogóle: pole `czynniki` było puste `{}`, przez co brama uzasadnień
    (`betting.ma_komplet_uzasadnienia`) traktowała te typy jak policzone bez
    rachunku i zdejmowała je z listy poniżej 70% szansy — choć rachunek
    istniał, tylko po stronie każdej drużyny osobno.
    """
    ha, aa = h_n.get("czynniki") or {}, a_n.get("czynniki") or {}
    if not ha or not aa:
        return {}
    out = {}
    for pole in ("rywal", "sedzia", "dom_wyjazd", "scenariusz_meczu",
                 "matchup", "lacznie"):
        h, a = float(ha.get(pole) or 1.0), float(aa.get(pole) or 1.0)
        out[pole] = round((h * a) ** 0.5, 3)
    out["opisy"] = {}
    return out


def czynniki_pary(h_n: dict, a_n: dict, nazwa_bazy: str, rho: float) -> list[dict]:
    """Uzasadnienie dla rynków liczonych z OBU drużyn (suma meczowa, „kto więcej").

    PO CO (2026-08-03). Te dwa rynki były budowane z pustym `czynniki: []`,
    więc karta nie miała czym wypełnić kroku „skąd ta liczba" — a `skadTaLiczba`
    po stronie web zwraca `null`, gdy nie znajdzie „Poziomu bazowego". Efekt:
    pierwszy typ na liście (suma rożnych) otwierał się i nie tłumaczył NICZEGO.

    To nie jest dorabianie uzasadnienia po fakcie: model liczy `lam` osobno dla
    każdej drużyny i mierzoną korelację między nimi — tylko nigdy tego nie
    zapisywał w formie do przeczytania.
    """
    kto = nazwa_bazy.lower()
    czynniki = [{
        "nazwa": "Poziom bazowy",
        "opis": (
            f"{h_n['nazwa']} notuje średnio {h_n['pred'].lam:.1f} "
            f"({kto}) na mecz, {a_n['nazwa']} {a_n['pred'].lam:.1f} — "
            f"razem {h_n['pred'].lam + a_n['pred'].lam:.1f}. Obie liczby są "
            f"już po korekcie na siłę rywala i miejsce gry"
        ),
        "mnoznik": None,
    }]
    # korelacja bywa zerowa (rynek bez pomiaru) — wtedy milczymy zamiast
    # pisać „bez wpływu", bo to zdanie o naszej kuchni, nie o meczu
    if abs(rho) > 0.02:
        czynniki.append({
            "nazwa": "Zależność między drużynami",
            "opis": (
                "Kiedy jedna drużyna notuje więcej, druga zwykle "
                + ("też" if rho > 0 else "mniej")
                + f" — zmierzone na historii ({rho:+.2f}). Bez tego suma "
                  "wychodziłaby zbyt równa"
            ),
            "mnoznik": None,
        })
    # CO PODNIOSŁO ALBO ŚCIĘŁO TĘ LICZBĘ. Do 05.08 karta sumy meczowej mówiła
    # tylko „tyle notują średnio" i kończyła — a model liczył dla obu drużyn
    # pełen zestaw poprawek, po prostu nigdzie ich nie opisywał.
    mn = mnozniki_pary(h_n, a_n)
    for pole, tytul, zdanie in (
        ("rywal", "Profil rywali",
         "przeciwnicy obu drużyn {kier} niż przeciętny zespół w tej lidze"),
        ("dom_wyjazd", "Dom i wyjazd",
         "miejsce gry {kier} liczbę względem neutralnego boiska"),
        ("scenariusz_meczu", "Scenariusz meczu",
         "kursy 1X2 zapowiadają mecz, który {kier} tę statystykę"),
        ("matchup", "Styl rywali",
         "styl przeciwników {kier} to, ile się tu dzieje"),
        ("sedzia", "Sędzia",
         "arbiter tego meczu {kier} liczbę względem przeciętnego"),
    ):
        m = float(mn.get(pole) or 1.0)
        if abs(m - 1.0) < 0.02:      # mnożnik ~1,00 nic nie robi, więc milczymy
            continue
        kier = "podnoszą" if m > 1 else "obniżają"
        if pole in ("dom_wyjazd", "scenariusz_meczu", "sedzia"):
            kier = "podnosi" if m > 1 else "obniża"
        czynniki.append({
            "nazwa": tytul,
            "opis": zdanie.format(kier=kier),
            "mnoznik": round(m, 3),
        })
    return czynniki


def wersje_w_ksiedze(log: dict) -> dict[str, str]:
    """Z ZAMROŻONEJ księgi: jaką wersją kalibracji policzono NIEROZLICZONY typ.

    ⚑ ROZJAZD KARTA–KSIĘGA (znaleziony audytem 2026-08-11, potwierdzony na
    danych). `rozliczanie._dopisz_nowe` przy istniejącym kluczu aktualizuje
    tylko flagi kategorii i robi `continue` — `p_model`, kurs i stempel wersji
    ZOSTAJĄ z pierwszej publikacji. To jest poprawne, dopóki rachunek się nie
    zmienia: cena i szansa mają być te, które user widział, biorąc typ.

    Ale po zmianie wersji kalibracji ten sam zakład policzony na nowo ma inne
    `p`. Karta pokazywałaby wtedy V2, a księga rozliczyłaby i NAUCZYŁA model
    na V1 — czyli mierzylibyśmy co innego, niż pokazaliśmy. Zmierzone na
    pierwszej liście V2: 7 z 20 typów miało w księdze rekord z poprzedniej
    wersji (Kairat Almaty: księga 0,869, strona 0,8325).

    Typ z takiej kolizji NIE WRACA na listę — schodzi jako `kolizja_wersji`.
    Świadomie nie „odradzamy" rekordu (skasuj i zapisz od nowa): rekord V1 ma
    zostać nietknięty i rozliczyć się jako historia tego, co naprawdę stało
    na stronie. Kolizja wygasa sama, gdy tamten typ przejdzie swój mecz.

    Zwraca {klucz_publikacji: wersja_kalibracji}; tylko typy NIEROZLICZONE
    i tylko te, które faktycznie były na liście (odrzucone i tło nie kolidują
    — user ich nie widział, ta sama zasada co w `linie_opublikowane`).
    """
    out: dict[str, str] = {}
    for r in (log or {}).values():
        if r.get("wynik") is not None or r.get("sugestia"):
            continue
        if r.get("odrzucony") or r.get("poza_publikacja"):
            continue
        w = (r.get("wersje") or {}).get("kalibracja")
        if w:
            out[_klucz_publikacji(r)] = w
    return out


def linie_opublikowane(log: dict) -> dict[tuple, set]:
    """Z ZAMROŻONEJ księgi: która linia zakładu jest już wystawiona.

    Zwraca {(mecz_id, podmiot, rynek_kod, strona): {linie}}. „Zakład" to
    mecz + drużyna/zawodnik + rynek + strona — POPRZECZKA nie jest częścią
    tożsamości, bo „poniżej 4,5" i „poniżej 5,5" to jeden pomysł wyceniony
    dwa razy, nie dwa zakłady.

    PO CO (2026-08-02). Brama „jedna linia na stronę" z 01.08 widzi wyłącznie
    BIEŻĄCE przeliczenie, więc łapie tylko połowę problemu. Zmierzone na
    księdze: ze 171 zakładów stojących w kilku poprzeczkach 94 dorobiły się
    drugiej w INNYM cyklu — o północy najlepsza była „poniżej 0,5", po
    południu kurs się przesunął i model dołożył „poniżej 1,5". Obie zostawały
    na stronie i obie się rozliczały.

    Typy odrzucone i spoza publikacji NIE blokują: user ich nie widział, więc
    nie ma z czym kolidować (ta sama zasada co w `kierunki_opublikowane`).
    """
    out: dict[tuple, set] = {}
    for r in (log or {}).values():
        if r.get("odrzucony") or r.get("poza_publikacja") or r.get("sugestia"):
            continue
        if r.get("linia") is None or not r.get("strona"):
            continue
        k = (r.get("mecz_id"), rotowire._norm(str(r.get("podmiot") or "")),
             r.get("rynek_kod"), r.get("strona"))
        out.setdefault(k, set()).add(float(r["linia"]))
    return out


def kierunki_opublikowane(log: dict) -> dict[tuple, dict]:
    """Z ZAMROŻONEGO logu: które strony linii są już opublikowane per mecz.

    Zwraca {(mecz_id, podmiot, rynek_kod): {"powyzej": max_linia,
    "ponizej": min_linia}}. Typy odrzucone i spoza publikacji nie blokują —
    user ich nie widział, więc nie ma z czym kolidować.
    """
    out: dict[tuple, dict] = {}
    for r in (log or {}).values():
        if r.get("odrzucony") or r.get("poza_publikacja"):
            continue
        linia = r.get("linia")
        strona = r.get("strona")
        if linia is None or strona not in ("powyzej", "ponizej"):
            continue
        k = (r.get("mecz_id"), rotowire._norm(str(r.get("podmiot") or "")),
             r.get("rynek_kod"))
        slot = out.setdefault(k, {})
        if strona == "powyzej":
            slot["powyzej"] = max(slot.get("powyzej", -9.0), float(linia))
        else:
            slot["ponizej"] = min(slot.get("ponizej", 99.0), float(linia))
    return out


def filtr_spojnosci_kierunku(
    legi: list[dict], opublikowane: dict[tuple, dict] | None = None,
) -> list[dict]:
    """Spójność kierunku per (mecz, podmiot, rynek) — decyzja usera 2026-07-25.

    Model potrafił opublikować OBIE strony tej samej linii (rożne Legii
    24.07: powyżej 4,5 @1.64 ORAZ poniżej 4,5 @2.12 przy p=49,6% — jedna
    z definicji przegrywa; cenowo +EV, produktowo bez sensu). Zasada:
    „poniżej" gra dopiero od linii NAJWYŻSZE-„powyżej" + 1. Korytarz
    (>3,5 + <5,5 = może wygrać oba) zostaje legalny, kolizja znika.
    Rynki zawodnicze (same „powyżej") przechodzą bez zmian.

    `opublikowane` (kierunki_opublikowane) domyka DZIURĘ MIĘDZY CYKLAMI
    zmierzoną 2026-07-26: filtr widział tylko bieżącą pulę, więc gdy „poniżej
    0,5" zamroziło się w logu 21.07, a model zmienił zdanie i 25.07 wystawił
    „powyżej 0,5" (strony „poniżej" nie było już w puli — nie było czego z czym
    porównać), obie strony siedziały w Skuteczności obok siebie. Typ raz
    opublikowany jest nieodwracalny, więc blokować musi TO, CO NOWE.
    """
    max_over: dict[tuple, float] = {}
    for b in legi:
        if b.get("strona") == "powyzej":
            k = (b.get("mecz_id"), b.get("podmiot"), b.get("rynek_kod"))
            max_over[k] = max(max_over.get(k, -9.0), float(b["linia"]))
    # krok 1: spójność WEWNĄTRZ puli (jak dotąd) — „poniżej" ustępuje „powyżej"
    wynik = [
        b for b in legi
        if b.get("strona") != "ponizej"
        or float(b["linia"]) >= max_over.get(
            (b.get("mecz_id"), b.get("podmiot"), b.get("rynek_kod")), -9.0
        ) + 1.0
    ]
    if not opublikowane:
        return wynik

    # krok 2: spójność z tym, co JUŻ zamrożone w logu — tu blokowana bywa
    # każda ze stron, bo przeciwnej nie da się już wycofać
    def _zgodny(b: dict) -> bool:
        slot = opublikowane.get((
            b.get("mecz_id"), rotowire._norm(str(b.get("podmiot") or "")),
            b.get("rynek_kod"),
        ))
        if not slot:
            return True
        linia = float(b["linia"])
        if b.get("strona") == "ponizej":
            return linia >= slot.get("powyzej", -9.0) + 1.0
        return linia <= slot.get("ponizej", 99.0) - 1.0

    return [b for b in wynik if _zgodny(b)]


# uniqueTournamentId 16 = Mistrzostwa Świata (jak w Sofascore)
WC_UTID = 16

# --- BRAMA JAKOŚCI (tylko tryb ligowy): świeżość próby zawodnika ---
# fit_posterior waży starość meczu z tau=180 dni (skala CAŁEGO sezonu), więc
# historia sprzed przerwy letniej wciąż waży ~0.66 — model sam z siebie nie
# odróżni "gra co tydzień" od "ostatni mecz w maju". Świeżości pilnujemy
# osobno tutaj: historia bez świeżych występów to typ na nieaktualnym
# zawodniku (kontuzja, wypadł z rotacji, transfer, przerwa w lidze).
OKNO_SWIEZEJ_PROBY_S = 120 * 86400  # okno "żywej" historii (pokrywa przerwę letnią)
MIN_MECZE_W_OKNIE = 2               # mniej występów w oknie = historia martwa, typu nie ma
# ⚑ Najstarszy mecz, który w ogóle wolno pokazać jako „ostatnie mecze" i wziąć
# do średniej opisowej drużyny (2026-08-11). Do prognozy i tak nie wchodził —
# wagi wykładniczne `counts.fit_posterior` ścinają go do zera — ale wchodził
# do KAŻDEJ liczby, którą widzi człowiek: uzasadnienia, karty, kontroli bazy.
# Osiemnaście miesięcy = dwa sezony rozgrywek; krócej zabrałoby historię
# drużynom grającym tylko w pucharach (sześć meczów na sezon).
MAX_WIEK_HISTORII_DRUZYNY_S = 548 * 86400
MIN_HISTORII_PO_PRZYCIECIU = 5      # tyle świeżych meczów musi zostać po suficie
STARE_DANE_S = 45 * 86400           # ostatni występ dawniej -> typ tylko "w tle"
#   (liczy się, uczy kalibrację, widoczny w Skuteczności; wraca do publikacji
#    po 1-2 kolejkach, gdy zawodnik znów ma świeże mecze)
# etykiety stron linii do czytelnych szczegółów w rejestrze odrzuceń
STRONA_PL = {"powyzej": "powyżej", "ponizej": "poniżej"}

# dokończenie zdania „szansa modelu X% ..." w rejestrze odrzuceń drużynowych.
# Trzy powody zamiast jednego — patrz betting.WIDELKI_DRUZYNOWE
POWODY_WIDELEK_PL = {
    "kurs_poza_widelkami": "przy kursie spoza widełek, w jakich gramy",
    "szansa_za_niska": "jest za niska jak na ten przedział kursów",
    "wartosc_ujemna": "nie daje dodatniej wartości przy ostrożnym liczeniu",
}

# --- BRAMA EKSPOZYCJI: ile minut model spodziewa się po zawodniku ---
# Typ na zawodnika, który przeciętnie gra pół meczu, jest zakładem o skład,
# nie o statystykę. Rozliczenia 2026-07-27: przy NIEZNANYM składzie zawodnik
# w ogóle zagrał w 85% typów (przy ogłoszonym — 95%), a te 15% to pudła bez
# szansy na trafienie. Drabinki mają taki próg od dawna (radar.MIN_MINUT_KARTY
# = 62) i to jedyny produkt, który nie tonie — model dostaje ten sam.
MIN_OCZEK_MINUT = 60.0

MAX_PERF_CYKL = 220                 # budżet zapytań /player/{id}/performance
#   na cykl (1 na zawodnika, nie na rynek) — ratowanie historii spoza
#   zasięgu feedu propsów; patrz odswiez_stare_trendy(). 120 ucinało 44 ze
#   164 zawodników z martwą próbą (dry-run 2026-07-26); koszt ~0,26 s na
#   zapytanie, więc pełne pokrycie to ~45 s w cyklu chodzącym co 30 min.

MAX_PERF_OFERTA = 900               # osobny budżet na dopełnianie OFERTY
#   bukmachera (patrz dopelnij_oferte_zawodnicza). Płacimy tylko za
#   zawodników z meczów, w których bukmacher realnie kwotuje zawodników —
#   dry-run 3.08: 10 z 60 meczów, 186 naszych zawodników w nich. Przy 260
#   budżet padał i 65 zawodników zostawało przy jednej statystyce.
#
#   420 -> 900 (2026-08-08). Drugi cennik podwoił lejek: 779 naszych zawodników
#   ma dziś kursy w meczach wspólnych z Betclikiem, a budżet 420 kończył się
#   co przebieg („budżet performance wyczerpany" w każdym logu). Skutek był
#   niewidoczny, bo kurs bez historii po prostu NIE WCHODZI do siatki —
#   wyglądało to jak brak oferty, a było brakiem zapytań. Koszt ~0,26 s na
#   zapytanie, czyli 900 to ~4 min w cyklu, który ma 50 min limitu i schodzi
#   dziś w 16.
MAX_SHOTMAP_OFERTA = 400            # ...i OSOBNY na mapy strzałów, bo to inna
#   cena: ~10 zapytań na drużynę zamiast 1 na zawodnika. Wspólny licznik
#   sprawiał, że mapy z pierwszych meczów zjadały historię wszystkim
#   pozostałym. Cache (`sm_cache`) jest wspólny dla graczy jednej drużyny,
#   więc realny koszt to liczba unikalnych meczów historycznych, nie graczy.


# --- PEŁNE SKŁADY (predicted/oficjalne) ---
# okno pobierania: przewidywane XI pojawiają się ~36 h przed meczem
OKNO_SKLADOW_S = 48 * 3600
# limit zapytań backupowych do Sofascore per cykl (nieoficjalne API, dławić)
LIMIT_SOFA_NA_CYKL = 40


def sklady_xi(events: list[dict]) -> dict[int, dict]:
    """Pełne XI nadchodzących meczów: mid -> {xi_by_team, confirmed, zrodlo}.

    xi_by_team: {teamId: set[playerId]} — sygnał składu jest wiarygodny
    per DRUŻYNA (bywa, że znamy XI tylko jednej strony; zawodnikom drugiej
    nie wolno wtedy wpisywać "poza składem").

    Hierarchia źródeł (id eventów/zawodników wspólne — statshub jest
    zbudowany na id Sofascore):
      1. statshub team-lineup (oficjalny, gdy event.lineupConfirmed),
      2. statshub predicted-teams-lineup (pełne 11/11 ~36 h przed meczem),
      3. Sofascore /event/{id}/lineups (backup; blokuje IP serwerowni,
         więc w chmurze cicho odpada — działa z domowego PC).
    Migotliwa flaga inPredictedLineup z player-trends zostaje ostatecznym
    fallbackiem w silniku (nic jej nie nadpisuje, gdy XI drużyny nie znamy).
    """
    now = int(time.time())
    out: dict[int, dict] = {}
    sofa_uzyte = 0
    for e in events:
        mid, ts = e.get("id"), e.get("timeStartTimestamp") or 0
        h_tid, a_tid = e.get("homeTeamId"), e.get("awayTeamId")
        if not (mid and h_tid and a_tid) or ts <= now or ts - now > OKNO_SKLADOW_S:
            continue
        xi_by_team: dict[int, set] = {}
        confirmed = bool(e.get("lineupConfirmed"))
        zrodlo = None
        if confirmed:
            for tid in (h_tid, a_tid):
                try:
                    xi_t = statshub.fetch_team_lineup(mid, tid)
                except Exception:
                    xi_t = []
                if len(xi_t) >= 10:
                    xi_by_team[tid] = set(xi_t)
            if xi_by_team:
                zrodlo = "statshub oficjalny"
        if not xi_by_team:
            try:
                pred = statshub.fetch_predicted_lineup(mid)
            except Exception:
                pred = {}
            for side, tid in (("home", h_tid), ("away", a_tid)):
                pids = pred.get(side) or []
                if len(pids) >= 10:
                    xi_by_team[tid] = set(pids)
            if xi_by_team:
                zrodlo = "statshub przewidywany"
                confirmed = confirmed or bool(pred.get("confirmed"))
        if not xi_by_team and sofa_uzyte < LIMIT_SOFA_NA_CYKL:
            sofa_uzyte += 1
            sofa = sofascore.fetch_lineups(mid)
            if sofa:
                for side, tid in (("home", h_tid), ("away", a_tid)):
                    if len(sofa[side]) >= 10:
                        xi_by_team[tid] = sofa[side]
                if xi_by_team:
                    zrodlo = "sofascore"
                    confirmed = confirmed or sofa["confirmed"]
        if xi_by_team:
            out[mid] = {
                "xi_by_team": xi_by_team,
                "confirmed": confirmed,
                "zrodlo": zrodlo,
            }
        time.sleep(0.15)
    return out


def swiezosc_proby(
    timestamps: list[int], minutes: list[float], now: int
) -> tuple[int, float]:
    """(ile występów w oknie świeżości, dni od ostatniego występu).

    Występ = mecz z minutami > 0. Brak jakiegokolwiek występu -> (0, inf).
    """
    grane = [ts for ts, m in zip(timestamps, minutes) if m > 0 and ts > 0]
    if not grane:
        return 0, float("inf")
    n_okno = sum(1 for ts in grane if ts >= now - OKNO_SWIEZEJ_PROBY_S)
    return n_okno, (now - max(grane)) / 86400.0


def odswiez_stare_trendy(
    trends: list, now: int, budzet: int = MAX_PERF_CYKL
) -> tuple[int, int]:
    """Dociągnij prawdziwą historię zawodnikom, których feed propsów ma martwą.

    `/api/props/player-trends` daje historię TYLKO z meczów, na które
    bukmacherzy UK wystawili linie. W Ameryce Południowej to garstka spotkań
    w sezonie, więc „ostatnie 40 meczów" zawodnika sięga dwóch lat wstecz,
    brama świeżości widzi zero występów w oknie i wyrzuca go jako
    `za_stara_historia` — mimo że gra co tydzień. Zmierzone 2026-07-26 na
    6 meczach Brasileirão/Ligi Profesional/MLS/Ligi MX: 58 z 360 trendów
    (16%), m.in. Igor Rabello z ostatnim meczem wg feedu 2025-09-20.

    `/api/player/{id}/performance` to własne dane meczowe statshuba —
    10 ostatnich występów z kompletem statystyk, niezależnie od tego, czy
    ktokolwiek je kwotował. Podmieniamy z nich SAMĄ HISTORIĘ; kontekst,
    którego performance nie zna (rywal, średnie ligi, linia z feedu, sygnał
    składu), zostaje z oryginalnego trendu nietknięty.

    Zwraca (ilu zawodników odświeżono, ile trendów podmieniono).
    """
    per_gracz: dict[int, list] = {}
    for t in trends:
        if t.player_id:
            per_gracz.setdefault(t.player_id, []).append(t)
    # ratujemy zawodnika, którego ŻADEN rynek nie ma świeżej próby — gdy choć
    # jeden ma, historia z feedu żyje i nie ma czego podmieniać
    stare = {
        pid: ich for pid, ich in per_gracz.items()
        if all(
            swiezosc_proby(t.timestamps, t.minutes, now)[0] < MIN_MECZE_W_OKNIE
            for t in ich
        )
    }
    if not stare:
        return 0, 0
    # najpierw zawodnicy z największą liczbą rynków — jedno zapytanie ratuje
    # tam najwięcej kandydatów naraz
    kolejka = sorted(stare.items(), key=lambda kv: -len(kv[1]))[:budzet]
    n_graczy = n_trendow = 0
    for pid, ich in kolejka:
        try:
            rows = statshub.fetch_player_performance(int(pid))
        except Exception as e:
            # zawodnik zostaje ze STARYM trendem — a odświeżenie było po to,
            # żeby nie liczyć z historii sprzed pół roku
            diagnostyka.cichy("cykl", "odswiezenie_trendu", e)
            continue
        if not rows:
            continue
        wzor = ich[0]
        swieze = statshub.trendy_z_performance(
            int(pid), wzor.player_name, wzor.team_id, rows
        )
        podmienione = 0
        for t in ich:
            s = swieze.get(t.market_code)
            if s is None:
                continue   # rynek pochodny (zza pola/głową) — potrzebuje shotmap
            if swiezosc_proby(s.timestamps, s.minutes, now)[0] < MIN_MECZE_W_OKNIE:
                continue   # performance też nie widzi świeżych występów: realnie nie gra
            t.counts = s.counts
            t.minutes = s.minutes
            t.timestamps = s.timestamps
            t.started = s.started
            t.game_positions = s.game_positions
            t.game_opponents = s.game_opponents
            t.game_opponent_ids = s.game_opponent_ids
            t.game_utids = s.game_utids
            podmienione += 1
        if podmienione:
            n_graczy += 1
            n_trendow += podmienione
    pominieto = max(0, len(stare) - len(kolejka))
    print(f"Historia spoza feedu propsów: {len(stare)} zawodników z martwą "
          f"próbą, odratowano {n_graczy} ({n_trendow} trendów)"
          + (f", budżet uciął {pominieto}" if pominieto else ""))
    return n_graczy, n_trendow


def _trend_z_kontekstem_meczu(swiezy, bazowy, mid: int):
    """Trend dociągnięty z historii + kontekst NADCHODZĄCEGO meczu.

    `/player/{id}/performance` zna tylko przeszłość zawodnika: kto był rywalem
    w każdym z minionych meczów, ile grał, ile notował. Nie wie natomiast nic
    o meczu, na który właśnie typujemy — a bez tego silnik nie policzy ani
    czynnika rywala, ani dom/wyjazd. Kontekst bierzemy więc z trendu bazowego
    tego samego zawodnika w tym samym spotkaniu (ten przyszedł z feedu propsów
    i kontekst niesie).

    Linia zostaje pusta: silnik dobiera ją sam z przewidywanej liczby zdarzeń,
    tak samo jak dla trendów, którym bukmacher UK nie podał swojej.

    Zwraca `None`, gdy kształt trendu nie pasuje — zamiast wywalać cykl.
    """
    try:
        pola = {f.name for f in dc_fields(type(swiezy))}
    except TypeError:
        return None
    kontekst = {
        "event_id": getattr(bazowy, "event_id", 0) or int(mid),
        "team_id": getattr(bazowy, "team_id", None),
        "team_name": getattr(bazowy, "team_name", None),
        "opponent_id": getattr(bazowy, "opponent_id", 0),
        "opponent_name": getattr(bazowy, "opponent_name", ""),
        "is_home": getattr(bazowy, "is_home", False),
        "in_predicted_lineup": getattr(bazowy, "in_predicted_lineup", False),
        "position": getattr(bazowy, "position", None),
        "line": 0.0,
    }
    zmiany = {k: v for k, v in kontekst.items() if k in pola and v is not None}
    try:
        return dc_replace(swiezy, **zmiany)
    except (TypeError, ValueError):
        return None


def bc_z_pamieci(
    kolejnosc: dict[int, int], pamiec: dict, teraz: int,
    swiezosc_s: int = SWIEZOSC_BETCLIC_S,
    okno_odswiezenia_s: int = OKNO_ODSWIEZENIA_BC_S,
) -> dict[int, dict]:
    """Oferty Betclica zapamiętane w poprzednich cyklach, wciąż ważne.

    Zasada: POBIERAMY RAZ NA MECZ (patrz SWIEZOSC_BETCLIC_S) — cena i tak jest
    zamrażana przy publikacji typu, więc ponowne pytanie o ten sam mecz niczego
    nie poprawia, a kosztuje 71 sekund, które lepiej wydać na mecz nieznany.

    Wyjątkiem jest mecz TUŻ PRZED GWIZDKIEM: tam odświeżamy raz, bo to okno,
    w którym user realnie stawia — a pokazanie ceny, której już nie ma, jest
    gorsze niż brak typu.

    Klucze pamięci są tekstowe (JSON), a mecze liczbowe — stąd konwersja
    w jednym miejscu zamiast w trzech.

    ⚑ DOTYCZY TO TAKŻE LINII, i to WYWRACAŁO CAŁY CYKL (2026-08-08).
    JSON nie zna kluczy liczbowych, więc oferta zapisana jako `{0.5: ...}`
    wraca z Supabase jako `{"0.5": ...}`. Po scaleniu z Superbetem (float)
    `merged` miał klucze dwóch typów naraz, a pierwsze `sorted()` po nich
    wywalało `TypeError: '<' not supported between 'str' and 'float'` —
    w `internal_fair_odds`, czyli w środku pętli scoringu, więc ginął CAŁY
    przebieg, nie jeden zawodnik. Objaw z produkcji: ostatni typ zapisany
    22:15, dokładnie wtedy, gdy osobny job zaczął napełniać `betclic_oferty`
    (22:08) — od tej chwili cykl nie dowiózł ani jednego typu.
    """
    out: dict[int, dict] = {}
    for mid, kickoff in kolejnosc.items():
        zap = (pamiec or {}).get(str(mid))
        if not zap or not zap.get("players"):
            continue
        zapisano = int(zap.get("ts") or 0)
        if teraz - zapisano > swiezosc_s:
            continue
        # mecz wszedł w okno przedmeczowe PO tym, jak zapamiętaliśmy ofertę
        do_gwizdka = int(kickoff or 0) - teraz
        if 0 < do_gwizdka <= okno_odswiezenia_s and zapisano < int(kickoff) - okno_odswiezenia_s:
            continue
        # `ts` jedzie razem z ofertą, bo typ z tej ceny musi zapisać, KIEDY ją
        # widzieliśmy — przy ofercie pamiętanej do doby „kurs_ts = teraz" byłby
        # po prostu nieprawdą (patrz `kurs_ts` w rozliczaniu)
        out[mid] = {"players": _linie_na_liczby(zap["players"]), "ts": zapisano}
    return out


def _linie_na_liczby(players: dict) -> dict:
    """`{"0.5": {...}}` z JSON-a z powrotem na `{0.5: {...}}` (patrz wyżej).

    Linia nieparsowalna WYPADA, zamiast jechać dalej jako tekst: jedna taka
    para przewraca `sorted()` w scoringu, a to kosztuje cały przebieg. Lepiej
    stracić linię niż cykl.
    """
    out: dict = {}
    for nazwisko, rynki in (players or {}).items():
        cel: dict = {}
        for mk, linie in (rynki or {}).items():
            slot: dict = {}
            for l, strony in (linie or {}).items():
                try:
                    slot[float(l)] = strony
                except (TypeError, ValueError):
                    continue
            if slot:
                cel[mk] = slot
        out[nazwisko] = cel
    return out


def bc_do_pobrania(
    kolejnosc: dict[int, int], juz_mamy: dict[int, dict], sb_cache: dict,
) -> list[tuple[int, int]]:
    """Mecze, o które WARTO zapytać Betclica — najbliższe pierwsze.

    Dwa odsiewy, oba zmierzone 08.08:
      * mecz już w pamięci nie potrzebuje zapytania,
      * mecz, w którym Superbet nie kwotuje ANI JEDNEGO zawodnika, prawie na
        pewno nie ma propsów też u Betclica (rozkład jest zerojedynkowy: 70 ze
        140 meczów ma 0, reszta od razu 20+). Takie zapytanie kosztuje 30–40 s
        i zwraca zero — to była połowa spalonego budżetu.
    """
    do_pobrania = [
        (mid, ts) for mid, ts in kolejnosc.items()
        if mid not in juz_mamy
        and len(((sb_cache or {}).get(mid) or {}).get("players") or {}) > 0
    ]
    do_pobrania.sort(key=lambda kv: kv[1])
    return do_pobrania


def bc_rotuj_pamiec(
    pamiec: dict, kolejnosc: dict[int, int], teraz: int,
    maks: int = MAX_MECZOW_W_PAMIECI_BC,
) -> dict:
    """Wyrzuć z pamięci mecze po gwizdku i wpisy starsze niż doba.

    Mecz spoza `kolejnosc` (czyli spoza bieżącego zakresu cyklu) ZOSTAJE,
    dopóki jest świeży — zakres bywa węższy w pojedynczym przebiegu, a
    kasowanie takich wpisów kazałoby pobierać je od nowa.
    """
    zywe = {
        k: v for k, v in (pamiec or {}).items()
        if teraz - int((v or {}).get("ts") or 0) < 86400
        and kolejnosc.get(_int_lub_zero(k), teraz + 1) > teraz
    }
    if len(zywe) <= maks:
        return zywe
    return dict(sorted(
        zywe.items(), key=lambda kv: -int((kv[1] or {}).get("ts") or 0)
    )[:maks])


def _int_lub_zero(x) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def _da_sie_na_liczbe(x) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def _scal_oferty_zawodnika(sb_rec: dict, bc_rec: dict) -> dict:
    """Oferty dwóch bukmacherów na jednego zawodnika w jeden słownik rynków.

    Kształt obu jest identyczny (`{rynek: {linia: {strona: kurs}}}`), więc
    scalanie jest sumą — z jednym wyjątkiem: gdy obaj kwotują TĘ SAMĄ linię,
    zostaje WYŻSZY kurs, bo to on jest do wzięcia (decyzja usera 08.08:
    „stawiać będziemy tam, gdzie wyższy").

    Uwaga na później: ta struktura nie niesie nazwy bukmachera, więc służy
    wyłącznie do ustalenia, JAKIE rynki i linie w ogóle istnieją (dociąganie
    historii, siatka pokryć). Typ dostaje bukmachera osobno, w pętli scoringu,
    gdzie kurs i jego źródło idą parą.

    LINIA JEST LICZBĄ, po obu stronach. Wynik trafia prosto do `sorted()`
    w scoringu, a klucze dwóch typów naraz przewracają tam cały przebieg
    (patrz `_linie_na_liczby`) — więc drugie źródło normalizujemy tutaj,
    niezależnie od tego, którędy przyszło.
    """
    if not bc_rec:
        return sb_rec or {}
    if not sb_rec:
        # też przez normalizację — zawodnik kwotowany WYŁĄCZNIE przez Betclica
        # idzie tą gałęzią i inaczej wniósłby do silnika tekstowe linie
        return {mk: {float(l): s for l, s in (linie or {}).items()
                     if _da_sie_na_liczbe(l)}
                for mk, linie in bc_rec.items()}
    out: dict = {mk: {l: dict(s) for l, s in linie.items()}
                 for mk, linie in sb_rec.items()}
    for mk, linie in bc_rec.items():
        cel = out.setdefault(mk, {})
        for l_raw, strony in (linie or {}).items():
            try:
                l = float(l_raw)
            except (TypeError, ValueError):
                continue
            slot = cel.setdefault(l, {})
            for strona, kurs in (strony or {}).items():
                try:
                    k = float(kurs)
                except (TypeError, ValueError):
                    continue
                if slot.get(strona) is None or k > float(slot[strona]):
                    slot[strona] = k
    return out


def zrodla_kursow(sb_rec: dict, bc_rec: dict) -> dict:
    """{rynek: {"linia": "Betclic"}} — gdzie cena po scaleniu pochodzi z Betclica.

    Ta sama reguła co w `_scal_oferty_zawodnika` (wygrywa wyższy kurs „over"),
    tylko zapisana osobno: sam scalony słownik nie niesie źródła, a karta
    drabinki musi wiedzieć, u KOGO ta cena była — inaczej pisze „u Superbetu"
    nad ceną, której tam nie ma (zgłoszenie usera 2026-08-08).

    Zwracamy WYŁĄCZNIE wyjątki. Superbet jest domyślnym cennikiem, więc mapa
    obcych cen jest o rząd wielkości mniejsza niż siatka i nie ma sensu
    powielać w niej całości.
    """
    out: dict = {}
    for mk, linie in (bc_rec or {}).items():
        sb_linie = (sb_rec or {}).get(mk) or {}
        for l_raw, strony in (linie or {}).items():
            try:
                l = float(l_raw)
            except (TypeError, ValueError):
                continue
            k_bc = (strony or {}).get("over")
            if k_bc is None:
                continue
            try:
                k_bc = float(k_bc)
            except (TypeError, ValueError):
                continue
            k_sb = ((sb_linie.get(l) or sb_linie.get(str(l)) or {})
                    .get("over"))
            try:
                lepszy = k_sb is None or k_bc > float(k_sb)
            except (TypeError, ValueError):
                lepszy = True
            if lepszy:
                out.setdefault(mk, {})[str(l)] = "Betclic"
    return out


def dopelnij_oferte_zawodnicza(
    gracze_meczu: dict[int, dict[int, object]],
    sb_cache: dict[int, dict],
    players_out: dict[int, dict],
    odds_grid: dict[int, dict],
    forma_z_trendu,
    budzet: int = MAX_PERF_OFERTA,
    budzet_shotmap: int = MAX_SHOTMAP_OFERTA,
    kolejnosc: dict[int, int] | None = None,
    fetch_performance=None,
    trendy_z_performance=None,
    trends_out: list | None = None,
    oferty_extra: dict[int, dict] | None = None,
    zrodla_grid: dict[int, dict] | None = None,
) -> tuple[int, int]:
    """Zakładka meczu ma pokazywać KURSY + wszystkie nasze statystyki
    indywidualne, które da się na ten mecz obstawić.

    Zgłoszenie usera 2026-08-03. Do dziś tabela pokazywała wyłącznie te
    statystyki, które wymienił feed propsów statshuba (`/props/player-trends`)
    — a on jest lustrem ofert bukmacherów UK, nie naszej oferty. Skutek
    zmierzony na Odense – Sønderjyske: feed dał 27 rekordów i WYŁĄCZNIE
    strzały, więc tabela znała jedną statystykę. W drugą stronę boli bardziej:
    Superbet kwotuje celne strzały najczęściej ze wszystkiego (547 par
    zawodnik–rynek w skanie 3.08), a formę na celne mieliśmy dla 15 zawodników
    z 1035 — te kursy leżały nietknięte.

    Dlatego kolejność odwracamy: punktem wyjścia jest OFERTA bukmachera na ten
    mecz, a brakującą historię dociągamy z `/player/{id}/performance` (własne
    dane meczowe statshuba, komplet statystyk, niezależne od tego, czy
    ktokolwiek je kwotował). Przy okazji do siatki kursów wpisujemy wszystkie
    kwotowane linie — dawniej trafiały tam tylko te, przy których silnik
    doszedł do końca scoringu, więc zawodnik odrzucony np. na „za mało zdarzeń"
    gubił kursy dla całej tabeli.

    DOŁĄCZAMY TE RYNKI DO SILNIKA TYPÓW (2026-08-07, decyzja usera).
    Do tego dnia dociągnięta historia szła wyłącznie do `players_out["forma"]`
    i do siatki kursów — czyli zasilała tabelę pokryć i drabinki, a typu z niej
    nigdy nie powstawało. Powód z 03.08 („nie mają kontekstu rywala ani
    kalibracji") przestał obowiązywać: kontekst rywala ma teraz kaskadę źródeł
    (`model/koncesje.py` + profil drużyn), a rynek bez własnej kalibracji jedzie
    na globalnej i jest o tym meldunek w logu (`rynki_bez_kalibracji`).
    Zmierzone 07.08, co tamta decyzja kosztowała: z 46 typów zawodniczych
    z trzech dni **41 to strzały**, a celnych, „zza pola", odbiorów i spalonych
    nie było ANI JEDNEGO — mimo że kursy i historia były w ręku.

    Trend z tej ścieżki niesie historię, ale nie zna kontekstu NADCHODZĄCEGO
    meczu (rywal, gdzie gramy, event_id) — bierzemy go z trendu bazowego tego
    samego zawodnika w tym samym meczu. Linia zostaje pusta: silnik dobiera ją
    sam z przewidywanej liczby zdarzeń (`line_for_lambda`), tak samo jak dla
    trendów z feedu, którym bukmacher UK nie podał swojej.

    `trends_out` jest opcjonalne — bez niego funkcja zachowuje się jak dawniej,
    co trzyma testy tabeli pokryć niezależne od tej zmiany.

    `kolejnosc` (mid -> kickoff_ts) decyduje, komu przypada budżet, gdy nie
    starcza dla wszystkich: najpierw mecze, które zaczynają się najwcześniej —
    to na nie ktoś dziś stawia.

    Zwraca (ile rynków dołożonych do formy, ile wpisów kursów w siatce).
    """
    fetch_performance = fetch_performance or statshub.fetch_player_performance
    trendy = trendy_z_performance or statshub.trendy_z_performance
    licznik = [budzet]
    # ⚑ DWA BUDŻETY, BO TO DWA RÓŻNE KOSZTY (2026-08-08). Do dziś jeden licznik
    # obsługiwał historię zawodnika (1 zapytanie na osobę) i mapy strzałów
    # (~10 na drużynę). Mapy zjadały go w pierwszych meczach, więc reszta
    # zawodników nie dostawała nawet TANIEJ historii — a bez niej kurs nie
    # wchodzi do siatki („if mk not in forma: continue" niżej).
    # Zmierzone tego dnia na 33 meczach wspólnych z ofertą Betclica:
    #     odbiory            466 zawodników ma kurs, NIE MA historii
    #     strzały zza pola   384 zawodników ma kurs, NIE MA historii
    #     gotowych par (kurs + historia): 78 z 779
    # To był najgrubszy przeciek w całym lejku drabinek — grubszy niż progi
    # i niż parowanie nazwisk (91 z 779).
    licznik_sm = [budzet_shotmap]
    sm_cache: dict[int, list] = {}
    n_rynkow = n_kursow = n_do_silnika = 0
    bez_pary: list[str] = []
    mecze = sorted(
        gracze_meczu.items(), key=lambda kv: (kolejnosc or {}).get(kv[0], 0)
    )
    for mid, gracze in mecze:
        sb_players = (sb_cache.get(mid) or {}).get("players") or {}
        bc_players = ((oferty_extra or {}).get(mid) or {}).get("players") or {}
        if not sb_players and not bc_players:
            continue   # bukmacher nie kwotuje zawodników — strona to mówi wprost
        for pid, tr in gracze.items():
            # OFERTA = SUMA OBU CENNIKÓW (2026-08-08). Rynki rozchodzą się
            # mocno: „zza pola" i odbiory Superbet kwotuje śladowo, a Betclic
            # normalnie — i to na nich stoją wzorcowe typy usera.
            _sb = superbet.znajdz_zawodnika(sb_players, tr.player_name)
            _bc = (betclic.znajdz_zawodnika(bc_players, tr.player_name)
                   if bc_players else {})
            rec = _scal_oferty_zawodnika(_sb, _bc)
            if not rec:
                bez_pary.append(tr.player_name)
                continue
            # kto daje cenę tam, gdzie NIE jest to Superbet (patrz `zrodla_kursow`)
            zrodla_gracza = zrodla_kursow(_sb, _bc) if _bc else {}
            forma = (players_out.get(pid) or {}).get("forma")
            if forma is None:
                continue
            braki = [mk for mk in rec if mk not in forma]
            if braki and licznik[0] > 0:
                licznik[0] -= 1
                try:
                    rows = fetch_performance(int(pid))
                except Exception:
                    rows = []
                if rows:
                    # shotmapy (rynki „zza pola" / „głową") kosztują ~10 zapytań
                    # na drużynę — pobieramy je TYLKO wtedy, gdy bukmacher
                    # rzeczywiście kwotuje któryś z tych rynków temu zawodnikowi
                    trzeba_shotmap = any(
                        mk in statshub.SHOTMAP_DERIVED for mk in braki
                    )
                    swieze = trendy(
                        int(pid), tr.player_name, tr.team_id, rows,
                        sm_cache=sm_cache if trzeba_shotmap else None,
                        budzet=licznik_sm,     # NIE `licznik` — patrz wyżej
                    )
                    for mk in braki:
                        s = swieze.get(mk)
                        if s is None or not s.counts:
                            continue
                        forma[mk] = forma_z_trendu(s, mk)
                        n_rynkow += 1
                        if trends_out is not None:
                            nowy = _trend_z_kontekstem_meczu(s, tr, mid)
                            if nowy is not None:
                                trends_out.append(nowy)
                                n_do_silnika += 1
            # KURSY: wszystkie kwotowane linie „powyżej" dla rynków, które
            # umiemy pokazać (mamy dla nich historię)
            for mk, linie in rec.items():
                if mk not in forma:
                    continue
                over = {
                    str(l): round(float(v["over"]), 2)
                    for l, v in (linie or {}).items() if (v or {}).get("over")
                }
                if over:
                    odds_grid.setdefault(mid, {}).setdefault(pid, {})[mk] = over
                    n_kursow += 1
                    obce = {l: kto for l, kto
                            in (zrodla_gracza.get(mk) or {}).items()
                            if l in over}
                    if obce and zrodla_grid is not None:
                        zrodla_grid.setdefault(mid, {}).setdefault(
                            pid, {})[mk] = obce
    if n_rynkow or n_kursow:
        # DWA BUDŻETY = DWIE RÓŻNE DIAGNOZY. „Wyczerpany" bez nazwy nie mówi,
        # czy zabrakło taniej historii, czy drogich map strzałów — a to zupełnie
        # inna decyzja ([[ciche-odrzucenia-zasada]]).
        print(f"Oferta zawodnicza: dołożono {n_rynkow} rynków do formy "
              f"i {n_kursow} wpisów kursów w siatce"
              + (f", z tego {n_do_silnika} poszło DO SILNIKA TYPÓW"
                 if n_do_silnika else "")
              + f"; historia {budzet - licznik[0]}/{budzet}"
              + (" WYCZERPANA" if licznik[0] <= 0 else "")
              + (f", mapy strzałów {budzet_shotmap - licznik_sm[0]}"
                 f"/{budzet_shotmap}" if budzet_shotmap != licznik_sm[0] else "")
              + (" WYCZERPANE" if licznik_sm[0] <= 0 else "")
              + (f", bez pary u bukmachera: {len(bez_pary)} zawodników"
                 if bez_pary else ""))
    return n_rynkow, n_kursow


# Odkrywanie zawodników WPROST Z OFERTY: budżety per cykl. Jedno odkrycie
# kosztuje do trzech zapytań (wyszukiwarka, profil, historia), więc bez sufitu
# jeden bogaty mecz zjadłby cały cykl — Sparta Praga – Lyon ma 66 kwotowanych
# zawodników, czyli ~200 zapytań na jedno spotkanie.
# Ile DRUŻYN pytamy o własną historię w jednym cyklu. Jedno zapytanie na
# drużynę (wynik jest cache'owany na cykl), więc przy ~70 meczach w zakresie
# drużynowym sufit 160 pokrywa komplet z zapasem.
MAX_TEAM_PERF_CYKL = 160

MAX_ODKRYC_CYKL = 220       # ilu zawodników odkrywamy na cykl (globalnie)
MAX_ODKRYC_MECZ = 6         # ...i ilu z jednego meczu W JEDNEJ RUNDZIE
MAX_WYSZUKAN_ODKRYC = 700   # sufit zapytań wyszukiwarki (statshub bez limitu,
#                             to próg grzeczności i czasu cyklu)
RUNDY_ODKRYWANIA = 3        # ile razy przemiatamy listę meczów


def odkryj_zawodnikow_z_oferty(
    mecze_do_odkrycia: list[tuple],
    sb_cache: dict[int, dict],
    players_out: dict[int, dict],
    odds_grid: dict[int, dict],
    forma_z_trendu,
    budzet: int = MAX_ODKRYC_CYKL,
    maks_na_mecz: int = MAX_ODKRYC_MECZ,
    budzet_wyszukan: int = MAX_WYSZUKAN_ODKRYC,
    rundy: int = RUNDY_ODKRYWANIA,
    debiutanci=None,
    fetch_performance=None,
    trendy_z_performance=None,
) -> tuple[int, int]:
    """Zawodnicy, o których wiemy WYŁĄCZNIE stąd, że bukmacher ich kwotuje.

    ZGŁOSZENIE USERA 2026-08-03: „w wielu meczach nie ma tabel pokryć ani
    kursów". `dopelnij_oferte_zawodnicza` odwróciło już kolejność (oferta →
    historia), ale wzbogaca WYŁĄCZNIE zawodników, których zna z feedu propsów
    statshuba. A ten feed jest lustrem ofert bukmacherów UK i na kwalifikacjach
    pucharów jest PUSTY — więc nie było kogo wzbogacać.

    Zmierzone: Sparta Praga – Lyon, 66 kwotowanych zawodników u Superbetu,
    ZERO w siatce pokryć; cała siatka stała na 13 z 95 meczów.

    Ścieżka identyfikacji jest ta sama, którą radar odkrywa debiutantów
    (`radar.debiutanci_meczu`): wyszukiwarka statshuba po nazwisku z oferty,
    a potem WERYFIKACJA klubu po `team_id` profilu. Weryfikacja jest tu
    najważniejsza — samo podobieństwo nazwiska wybiera cudzego zawodnika, a
    taka podmiana nie zostawia śladu w logu (patrz [[parowanie-nazw-druzyn]]).
    Nie potwierdziliśmy klubu = nie zgadujemy, zawodnik nie wchodzi.

    `mecze_do_odkrycia`: [(mid, team_ids, kickoff_ts, nazwy_druzyn)] — mecze
    obsługiwane od NAJBLIŻSZEGO kickoffu, bo na nie ktoś dziś stawia.

    Zwraca (ilu zawodników odkryto, ile wpisów kursów dopisano).
    """
    debiutanci = debiutanci or radar.debiutanci_meczu
    fetch_performance = fetch_performance or statshub.fetch_player_performance
    trendy = trendy_z_performance or statshub.trendy_z_performance
    licznik = [0]                 # budżet wyszukiwarki, wspólny dla meczów
    n_graczy = n_kursow = 0
    sm_cache: dict[int, list] = {}
    juz_odkryci: set[tuple[int, int]] = set()
    # RUNDAMI, NIE MECZ PO MECZU (2026-08-03). Pierwsza wersja szła listą do
    # wyczerpania budżetu i oddawała go kilku pierwszym meczom — 51 odkrytych
    # zawodników, a Sparta Praga – Lyon dalej z pustą tabelą, bo budżet skończył
    # się przed nią. Zgłoszenie brzmiało „w WIELU meczach nie ma tabel", więc
    # liczy się SZEROKOŚĆ: lepiej sześć wierszy w każdym meczu niż komplet
    # w trzech. Kolejność w rundzie: najpierw mecze z pustą tabelą, potem wg
    # kickoffu — bo pusty mecz jutro jest pilniejszy niż dopełnienie pełnego
    # dzisiaj.
    kolejka = sorted(
        mecze_do_odkrycia,
        key=lambda x: (len(odds_grid.get(x[0]) or {}) > 0, x[2]),
    )
    for mid, team_ids, _ts, nazwy_druzyn in [
        m for _runda in range(rundy) for m in kolejka
    ]:
        if n_graczy >= budzet or licznik[0] >= budzet_wyszukan:
            break
        sb_odds = sb_cache.get(mid) or {}
        if not (sb_odds.get("players") or {}):
            continue
        znane = [
            (players_out.get(pid) or {}).get("nazwa", "")
            for pid in (odds_grid.get(mid) or {})
        ]
        try:
            # min_rynkow=1: w tabeli pokryć jeden kwotowany rynek to
            # pełnoprawny wiersz (radar wymaga dwóch — inny cel, patrz
            # docstring debiutanci_meczu)
            znalezieni = debiutanci(sb_odds, znane, tuple(team_ids), licznik,
                                    min_rynkow=1, maks_kandydatow=maks_na_mecz,
                                    budzet_wyszukan=budzet_wyszukan)
        except Exception as e:
            print(f"Odkrywanie z oferty: mecz {mid} pominięty ({e})")
            continue
        for kand in znalezieni[:maks_na_mecz]:
            if n_graczy >= budzet:
                break
            profil = kand.get("profil") or {}
            pid = profil.get("id")
            rynki_sb = (sb_odds.get("players") or {}).get(kand["klucz_sb"]) or {}
            if not pid or not rynki_sb:
                continue
            # w kolejnej rundzie odkryty gracz wraca jako „znany" przez
            # odds_grid, ale bezpiecznik jest tani, a podwójne liczenie
            # zjadałoby budżet po cichu
            if (mid, int(pid)) in juz_odkryci:
                continue
            juz_odkryci.add((mid, int(pid)))
            try:
                rows = fetch_performance(int(pid))
            except Exception as e:
                # zawodnik z oferty bukmachera, któremu nie dociągnęliśmy
                # historii — wypada z typów, choć kurs na niego istnieje
                diagnostyka.cichy("cykl", "historia_z_oferty", e)
                continue
            if not rows:
                continue
            druzyna = nazwy_druzyn.get(profil.get("team_id"), "")
            swieze = trendy(int(pid), kand["nazwa"], profil.get("team_id"),
                            rows, sm_cache=sm_cache, budzet=[0])
            forma: dict[str, dict] = {}
            for mk in rynki_sb:
                s = swieze.get(mk)
                if s is not None and s.counts:
                    forma[mk] = forma_z_trendu(s, mk)
            if not forma:
                continue   # bukmacher kwotuje same rynki, których nie liczymy
            rec = players_out.setdefault(int(pid), {
                "id": int(pid), "nazwa": kand["nazwa"],
                "pozycja": profil.get("position") or "?",
                "druzyna": druzyna,
                "minuty_lacznie": 0, "forma": {}, "xi": False,
            })
            rec["forma"].update(forma)
            rec["minuty_lacznie"] = max(
                rec.get("minuty_lacznie") or 0,
                int(sum(next(iter(swieze.values())).minutes)) if swieze else 0,
            )
            n_graczy += 1
            for mk, linie in rynki_sb.items():
                if mk not in forma:
                    continue
                over = {
                    str(l): round(float(v["over"]), 2)
                    for l, v in (linie or {}).items() if (v or {}).get("over")
                }
                if over:
                    odds_grid.setdefault(mid, {}).setdefault(int(pid), {})[mk] = over
                    n_kursow += 1
    if n_graczy or licznik[0]:
        print(f"Odkrywanie z oferty: {n_graczy} zawodników spoza feedu propsów "
              f"({n_kursow} wpisów kursów, {licznik[0]} zapytań wyszukiwarki)"
              + (", budżet wyczerpany" if n_graczy >= budzet else ""))
    return n_graczy, n_kursow


# nazwy reprezentacji EN -> PL (do dopasowania z Superbetem)
EN_PL = {v: k for k, v in superbet.TEAM_PL_EN.items()}
# MŚ 2026 to NIE jest w pełni neutralny turniej — USA/Meksyk/Kanada są
# współgospodarzami i grają większość swoich meczów u siebie. Nazwy w
# formacie statshub (angielski), zgodnym z wartościami TEAM_PL_EN wyżej.
WC26_HOST_NATIONS = {"USA", "Mexico", "Canada"}


def venue_context(team_name: str, opponent_name: str, is_home_raw: bool) -> tuple[bool, bool]:
    """(is_home, neutral_venue) dla MatchContext, z uwzględnieniem gospodarzy
    MŚ 2026. Gdy jedna z drużyn jest gospodarzem, mecz NIE jest neutralny —
    gospodarz gra u siebie niezależnie od tego, co statshub oznaczył jako
    "home team" w samej parze (to pole bywa administracyjne w turniejach).
    Gdy żadna drużyna nie jest gospodarzem, mecz jest na neutralnym terenie
    (kraj trzeci) i zostaje bez efektu dom/wyjazd, jak dotychczas."""
    host_team = team_name in WC26_HOST_NATIONS
    host_opp = opponent_name in WC26_HOST_NATIONS
    is_host_match = host_team or host_opp
    is_home = host_team if is_host_match else is_home_raw
    return is_home, not is_host_match


def _sh(url: str) -> dict:
    r = requests.get(url, impersonate="chrome124", timeout=30, headers=SH_HEADERS)
    r.raise_for_status()
    return r.json()


def upcoming_wc_events() -> list[dict]:
    """Nadchodzące mecze MŚ z statshub (przeszukaj najbliższe 8 dni)."""
    now = int(time.time())
    out = {}
    for d in range(8):
        start = now + d * 86400
        start -= start % 86400
        try:
            data = _sh(
                f"{SH_BASE}/event/by-date?startOfDay={start}&endOfDay={start + 86399}"
            ).get("data", [])
        except Exception:
            continue
        for e in data:
            ev = e.get("events", e)
            utid = ev.get("uniqueTournamentId") or (ev.get("tournament") or {}).get(
                "uniqueTournamentId"
            )
            if utid == WC_UTID and ev.get("status") == "notstarted":
                out[ev["id"]] = ev
    return list(out.values())


# waga biblioteki trendów z chwili wczytania — zapis porównuje się do niej
# zamiast ciągnąć 8,6 MB drugi raz w tym samym cyklu (patrz save_trend_lib)
_TREND_LIB_WAGA: int | None = None


def load_trend_lib() -> dict:
    """Trwała biblioteka trendów (Supabase app_data.trend_lib).

    statshub KASUJE propsy po meczu — bez tej biblioteki tracimy historię
    zawodników, zanim pojawią się kursy na ich następny mecz.
    """
    global _TREND_LIB_WAGA
    lib, ok = supa.get_key_ok("trend_lib")
    # nieudany odczyt zostawia wagę pustą: zapis wykona wtedy własną kontrolę
    # (i sam się wstrzyma, jeśli baza dalej nie odpowiada)
    _TREND_LIB_WAGA = supa.waga(lib) if ok and lib is not None else None
    return lib or {}


def save_trend_lib(lib: dict) -> None:
    # biblioteka trendów tylko rośnie — nagły skurcz oznacza, że `load_trend_lib`
    # dostało pustkę po awarii odczytu, a nie że historia zniknęła
    supa.put_key_bezpiecznie("trend_lib", lib, waga_poprzednia=_TREND_LIB_WAGA)


def past_wc_events(days_back: int = 25) -> list[dict]:
    """Rozegrane mecze MŚ z ostatnich dni (pełne eventy: id, drużyny, kickoff)."""
    now = int(time.time())
    out: dict[int, dict] = {}
    for d in range(1, days_back + 1):
        start = now - d * 86400
        start -= start % 86400
        try:
            data = _sh(
                f"{SH_BASE}/event/by-date?startOfDay={start}&endOfDay={start + 86399}"
            ).get("data", [])
        except Exception:
            continue
        for e in data:
            ev = e.get("events", e)
            utid = ev.get("uniqueTournamentId") or (ev.get("tournament") or {}).get(
                "uniqueTournamentId"
            )
            if utid == WC_UTID and ev.get("status") != "notstarted":
                out[ev["id"]] = ev
    return list(out.values())


def past_wc_event_ids(days_back: int = 25) -> list[int]:
    """ID rozegranych meczów MŚ z ostatnich dni (do biblioteki historii)."""
    return [ev["id"] for ev in past_wc_events(days_back)]


def group_prior_from_context(trend: statshub.StatshubTrend) -> counts.GroupPrior:
    """Prior grupowy z ligowej średniej statshub (fallback, gdy mała próba).

    ⚑ JEDNOSTKI (naprawione 2026-08-13). Do dziś `base` była średnią liczbą
    zdarzeń NA MECZ, a trafiała do pola `mean_per90`, czyli „na 90 minut".
    Dla zawodnika grającego pełne mecze to jedno i to samo; dla rotacyjnego
    prior był zaniżony proporcjonalnie do brakujących minut.

    Zmierzone na siedmiu zawodnikach z realnymi typami (40 meczów każdy):
    prior zaniżał o 17% (0,83), a że waży `pseudo/(pseudo+ESS)` ≈ 14%, do
    posteriora przechodziło z tego 2,5%.

    ⚑ CZEMU TO ROBIMY, SKORO EFEKT JEST MAŁY, a kierunek PRZECIWNY do luki
    (prognozy są za wysokie, a ta poprawka je podnosi): bo to jest pomyłka
    jednostek, nie parametr do strojenia. Zostawiona w kodzie fałszuje każdy
    następny pomiar priora — a mierzyliśmy przy niej już dwa razy.
    Wielkość korekty jest zresztą w granicach szumu, więc nie zmienia
    selekcji; poprawia to, na czym stoją kolejne decyzje.
    """
    la = trend.league_average
    # leagueAverage bywa w skali drużynowej dla części rynków — traktujemy
    # ostrożnie: prior o umiarkowanej sile, średnia z historii zawodnika.
    zagrane = [(c, m) for c, m in zip(trend.counts, trend.minutes) if m > 0]
    ekspozycja = sum(m for _, m in zagrane) / 90.0
    if zagrane and ekspozycja > 0:
        base = float(sum(c for c, _ in zagrane)) / ekspozycja
    else:
        base = float(la or 0.8)
    return counts.GroupPrior(mean_per90=max(base, 0.15), pseudo_matches=5.0)


# nowe wpisy sędziowskie per cykl (game_referee + pełne staty per mecz) —
# na MŚ turniej miał kilka meczów dziennie, w sezonie ligowym dziesiątki;
# pierwszy cykl dogania porcjami jak bank stylu
LIMIT_NOWYCH_SEDZIOW = 40


def profil_sedziow(
    events: list[dict], team_name: dict[int, str],
    comp_ids: list[int] | None = None,
    cache_key: str = "sedziowie_cache",
    bank_gry: dict | None = None,
) -> dict[int, dict]:
    """Profil sędziego per nadchodzący mecz: {mid: {sedzia, mnoznik, n}}.

    Źródło: 365Scores — officials (obsada znana 1-2 dni przed meczem) +
    suma fauli wszystkich zawodników z rozegranych meczów tego sędziego.
    Mnożnik = średnia z ilorazów (faule meczu / OCZEKIWANE faule tej pary
    drużyn) — oczekiwania z pozostałych meczów tych drużyn, żeby nie mylić
    stylu sędziego ze stylem drużyn (Maroko fauluje dużo u każdego arbitra).
    Mecze z dogrywką pomijane (staty obejmują 120 min i zawyżałyby profil).
    Wyniki per mecz cache'owane w Supabase (cache_key).

    KARTKI MAJĄ WŁASNY MNOŻNIK (2026-08-03). Do dziś rynek `team_cards` jechał
    na profilu liczonym z FAULI — a to dwie różne cechy arbitra: przy tej samej
    liczbie fauli jeden sięga po kartkę, drugi upomina. Zgłoszenie usera:
    „do kartek ważni są sędziowie". Liczymy więc drugi mnożnik, tą samą metodą
    (iloraz do oczekiwań TEJ pary drużyn, leave-one-out), tylko na kartkach.

    Nie kosztuje ani jednego zapytania: kartki per mecz leżą już w banku stylu
    (`game_team_stats` -> `kartki` = żółte + czerwone), a bank i ten cache są
    kluczowane tym samym id meczu 365Scores. Wystarczy je złączyć — stąd
    `bank_gry`. Bez banku (albo przy chudej próbie) zostaje stary mnożnik
    z fauli, czyli zachowanie sprzed zmiany.

    Domyślnie MŚ; tryb ligowy podaje comp_ids (rozgrywki drużynowe) i osobny
    cache (sedziowie_cache_liga) — profile arbitrów klubowych osobno.
    """
    cache = supa.get_key(cache_key) or {}
    zmieniony = False
    rozegrane_365: list[dict] = []
    for c in (comp_ids or [None]):
        try:
            rozegrane_365 += (
                scores365.finished_games_by_competition(c)
                if c else scores365.finished_games_by_competition()
            )
        except Exception as e:
            diagnostyka.cichy("cykl", "rozegrane_z_rozgrywek", e)
            continue
    nowych_sed = 0
    for g in rozegrane_365:
        gid = str(g["id"])
        druzyny = [g.get("home") or "", g.get("away") or ""]
        if gid in cache:
            # starsze wpisy sprzed pola "druzyny" — uzupełnij przy okazji
            if not cache[gid].get("druzyny") and all(druzyny):
                cache[gid]["druzyny"] = druzyny
                zmieniony = True
            continue
        if nowych_sed >= LIMIT_NOWYCH_SEDZIOW:
            break
        nowych_sed += 1
        rec = {
            "sedzia": scores365.game_referee(g["id"]), "faule": None,
            "druzyny": druzyny if all(druzyny) else None,
        }
        try:
            if not scores365.after_extra_time(g["id"]):
                staty = scores365.game_player_match_stats(g["id"])
                faule = sum(
                    float(s.get("fouls_committed") or 0) for s in staty.values()
                )
                rec["faule"] = round(faule, 1) if faule > 0 else None
        except Exception as e:
            # sędzia bez profilu fauli = mnożnik 1,0 dla całego meczu, czyli
            # rynki kartek i fauli liczone bez jednego z mocniejszych czynników
            diagnostyka.cichy("cykl", "profil_sedziego", e)
        cache[gid] = rec
        zmieniony = True
    if zmieniony:
        supa.put_key_bezpiecznie(cache_key, cache)

    # kartki per mecz z banku stylu — złączenie po id meczu 365, zero zapytań
    kartki_meczu: dict[str, float] = {}
    for gid_b, rec_b in (bank_gry or {}).items():
        wart = [
            float(d["kartki"]) for d in (rec_b.get("druzyny") or {}).values()
            if d.get("kartki") is not None
        ]
        if len(wart) == 2:          # komplet obu drużyn albo nic
            kartki_meczu[str(gid_b)] = sum(wart)

    def _profil(pole: str) -> tuple[dict[str, list], float]:
        """(sędzia -> [(wartość meczu, drużyny)], średnia ogólna) dla cechy."""
        per: dict[str, list[tuple[float, list | None]]] = {}
        sr_dr: dict[str, list[float]] = {}
        for gid_c, rec in cache.items():
            wart = (float(rec["faule"]) if pole == "faule" and rec.get("faule")
                    else kartki_meczu.get(str(gid_c)) if pole == "kartki"
                    else None)
            if not wart:
                continue
            if rec.get("sedzia"):
                per.setdefault(rec["sedzia"], []).append(
                    (wart, rec.get("druzyny"))
                )
            for d in rec.get("druzyny") or []:
                sr_dr.setdefault(d, []).append(wart)
        wszystkie_p = [w for lista in per.values() for w, _ in lista]
        sr_ogolna = sum(wszystkie_p) / len(wszystkie_p) if wszystkie_p else 0.0
        _SREDNIE[pole] = sr_dr
        return per, sr_ogolna

    _SREDNIE: dict[str, dict[str, list[float]]] = {}
    per_sedzia, turniej_sr = _profil("faule")
    per_sedzia_k, turniej_sr_k = _profil("kartki")
    if not per_sedzia and not per_sedzia_k:
        return {}

    def _oczekiwane(druzyny: list | None, f_meczu: float,
                    pole: str = "faule") -> float:
        """Ile spodziewamy się po TEJ parze drużyn (styl drużyn, nie arbitra);
        bieżący mecz wyłączony z oczekiwań (leave-one-out)."""
        sr_dr = _SREDNIE.get(pole) or {}
        ogolna = turniej_sr if pole == "faule" else turniej_sr_k
        srednie = []
        for d in druzyny or []:
            fl = list(sr_dr.get(d) or [])
            if f_meczu in fl:
                fl.remove(f_meczu)
            if len(fl) >= 2:
                srednie.append(sum(fl) / len(fl))
        return sum(srednie) / len(srednie) if len(srednie) == 2 else ogolna

    # obsady nadchodzących meczów: parowanie fixtures 365 z eventami statshub
    # po znormalizowanych nazwach drużyn (awaryjnie kickoff +-3h + jedna nazwa)
    sched: list[dict] = []
    for c in (comp_ids or [None]):
        try:
            sched += (
                scores365.scheduled_games_by_competition(c)
                if c else scores365.scheduled_games_by_competition()
            )
        except Exception as e:
            diagnostyka.cichy("cykl", "terminarz_z_rozgrywek", e)
            continue
    out: dict[int, dict] = {}
    for e in events:
        hn = rotowire._norm(team_name.get(e.get("homeTeamId"), ""))
        an = rotowire._norm(team_name.get(e.get("awayTeamId"), ""))
        ts = e.get("timeStartTimestamp") or 0
        g365 = next(
            (g for g in sched if {g["home"], g["away"]} == {hn, an}),
            None,
        ) or next(
            (g for g in sched
             if abs(g["ts"] - ts) < 3 * 3600 and {g["home"], g["away"]} & {hn, an}),
            None,
        )
        if g365 is None:
            continue
        ref = scores365.game_referee(g365["id"])
        if not ref:
            continue
        proby = per_sedzia.get(ref, [])
        ilorazy = [f / max(_oczekiwane(dr, f), 1e-6) for f, dr in proby]
        proby_k = per_sedzia_k.get(ref, [])
        ilorazy_k = [
            k / max(_oczekiwane(dr, k, "kartki"), 1e-6) for k, dr in proby_k
        ]
        out[e["id"]] = {
            "sedzia": ref,
            "mnoznik": (
                round(sum(ilorazy) / len(ilorazy), 3) if ilorazy else None
            ),
            "n": len(proby),
            # osobna cecha arbitra: chętnie sięga po kartkę czy upomina
            "mnoznik_kartek": (
                round(sum(ilorazy_k) / len(ilorazy_k), 3) if ilorazy_k else None
            ),
            "n_kartek": len(proby_k),
        }
    return out


# wybór profilu arbitra (kartki mają własny) mieszka w `model/context.py`,
# bo korzystają z niego dwie ścieżki: typy drużynowe i drabinki
sedzia_dla_rynku = context.sedzia_dla_rynku

# Który powód odrzucenia zawodnika jest CIEKAWSZY, gdy kwotowanych linii jest
# kilka: im wyżej, tym bliżej publikacji był ten typ. Zawodnikowi, któremu
# zabrakło tylko wartości, warto się przyjrzeć; ten z kursem 8,0 nie mówi nic.
_KOLEJNOSC_PROFILU = {
    "kurs_poza_pasmem": 1,
    "szansa_za_niska": 2,
    "wartosc_ujemna_przy_ostroznym": 3,
}


# --- BANK STYLU (pełne matchupy, model/styl.py) ---
# limity per cykl: pierwszy przebieg dogania cały turniej w 1-2 cyklach,
# kolejne dolewają po kilka meczów dziennie — bez zalewania API
LIMIT_NOWYCH_GIER_STYLU = 40
LIMIT_WZROSTOW_NA_CYKL = 30


# Beniaminek: ile gier w banku uznajemy za "zna go" — poniżej dociągamy jego
# WŁASNĄ historię, także z niższej ligi.
#
# PODNIESIONE Z 4 NA 6 (2026-07-27). Cztery gry były progiem posteriora
# counts.py, ale brama `krotka_historia` w sekcji drużynowej wymaga PIĘCIU —
# więc drużyna doprowadzona dokładnie do czterech przestawała być "uboga",
# a typu i tak nie dawała. Sześć zostawia zapas na mecze, których 365 nie
# odda (brak statystyk, mecz przerwany).
MIN_GIER_BANKU = 6
# ile własnych meczów dociągamy takiej drużynie i ile drużyn na cykl
BENIAMINEK_GIER = 8
# PODNIESIONE Z 6 NA 12 (2026-07-27) — powód jest arytmetyczny. Po dołożeniu
# ośmiu lig do zakresu drużynowego bank stylu nie zna 141 z 214 drużyn
# najbliższych meczów (zmierzone: tylko 3% ma wymagane 5 gier). Zasilanie
# per rozgrywki tego nie nadrobi, bo `/games/results?competitions=` oddaje
# WYŁĄCZNIE ostatnią kolejkę — medianę jednego meczu na drużynę. Ta ścieżka,
# per drużyna, jest jedyną, która sięga w głąb sezonu. Przy 6 drużynach na
# cykl doganianie trwałoby ~24 cykle, przy 12 — połowę tego, czyli mniej
# więcej dobę. Koszt to ~minuta cyklu i tylko na czas doganiania: gdy bank
# już zna drużyny, lista "ubogich" jest pusta i pętla nie robi nic.
BENIAMINEK_DRUZYN_CYKL = 12


def zbuduj_aliasy_banku(
    bank: dict, nazwy_druzyn: set[str], comp_ids: list[int] | None = None,
) -> int:
    """Nazwa drużyny ze statshub -> klucz(e), pod którymi siedzi w banku stylu.

    POWÓD (zmierzone 2026-08-03). Bank zapisuje drużyny nazwami z 365Scores,
    a silnik szuka ich nazwami ze statshub — i szukał po DOKŁADNYM kluczu:

        statshub               bank (365Scores)
        sarmiento           -> sarmiento junin
        talleres            -> talleres cordoba
        sonderjyske fodbold -> sonderjyske
        viborg ff           -> viborg
        central cordoba     -> central cordoba sde

    Kosztowało to DWIE rzeczy naraz, obie widoczne na stronie:
      * `_hist_z_banku` nie znajdował historii, więc rynki budowane z banku
        (kartki, strzały, celne, faule) w ogóle nie były rozważane — Superbet
        je kwotował, a my ich nawet nie odrzucaliśmy, bo nie było czego liczyć.
        Zmierzone 03.08: połowa drużyn najbliższych meczów „nie istniała"
        w banku, choć siedziała w nim pod nazwą 365,
      * `dolej_historie_wlasna` liczy gry po tym samym kluczu, więc te drużyny
        BEZ KOŃCA wyglądały na ubogie: co cykl brały cały budżet doganiania,
        pobierały te same mecze, dopisywały zero (są już w banku) i lądowały
        w logu jako „nieudane". Budżet nie docierał do drużyn, które naprawdę
        historii nie mają.

    JAK PARUJEMY — NIE PODOBIEŃSTWEM TEKSTU ([[parowanie-nazw-druzyn]]).
    Idziemy przez id 365Scores: `dopasuj_druzyne` (zbiory słów + wymóg
    jednoznaczności) daje competitorId, a potem bierzemy WSZYSTKIE nazwy
    o tym id, które są w banku. Dla „Dundee FC" nie ma id Dundee United, więc
    podmiana klubu jest niemożliwa — a przy dopasowaniu po samych nazwach
    „dundee" zawiera się w „dundee united" i cicho wskazałoby cudzą historię.

    Alias jest LISTĄ, bo ta sama drużyna bywa w banku pod dwoma zapisami —
    wtedy historia jest rozbita i trzeba ją scalić, a nie wybrać jedną połowę.
    Zapisujemy w banku (`bank["alias"]`), więc kolejne cykle nie płacą za to
    ani jednym zapytaniem.
    """
    alias: dict = bank.setdefault("alias", {})
    klucze_banku: set[str] = set()
    for rec in (bank.get("gry") or {}).values():
        klucze_banku |= set((rec.get("druzyny") or {}).keys())
    brakujace = sorted(
        nm for nm in {rotowire._norm(n) for n in nazwy_druzyn if n}
        if nm and nm not in klucze_banku and nm not in alias
    )
    if not brakujace or not klucze_banku:
        return 0
    try:
        id_map = scores365.competitor_ids_z_rozgrywek(comp_ids or [])
    except Exception as e:
        print(f"Aliasy banku: mapa id 365 niedostępna ({e})")
        return 0
    # id -> nazwy 365, które SĄ w banku (tylko one mają jakąkolwiek historię)
    po_id: dict[int, list[str]] = {}
    for nazwa365, cid in id_map.items():
        if nazwa365 in klucze_banku:
            po_id.setdefault(int(cid), []).append(nazwa365)
    nowe = 0
    for nm in brakujace:
        cid = scores365.dopasuj_druzyne(id_map, nm)
        if not cid:
            continue
        pod_id = po_id.get(int(cid)) or []
        if pod_id:
            alias[nm] = sorted(pod_id)
            nowe += 1
    if nowe:
        print(f"Bank stylu: rozpoznano {nowe} drużyn zapisanych inną nazwą "
              f"(np. {', '.join(f'{k}->{v[0]}' for k, v in list(alias.items())[:3])})")
    return nowe


def dolej_historie_wlasna(
    bank: dict, nazwy_druzyn: set[str], comp_ids: list[int] | None = None,
    budzet: int = BENIAMINEK_DRUZYN_CYKL,
) -> int:
    """Dociągnij własne mecze drużynom, których bank prawie nie zna.

    Bank stylu jest zasilany PER ROZGRYWKI (`comp365` z rozgrywki.PROFILE), więc
    beniaminek nie istnieje w nim aż do kilku kolejek nowego sezonu — jego
    poprzedni rok rozegrał w rozgrywkach spoza rejestru. Zmierzone 2026-07-26:
    Wisła Kraków miała 0 gier w banku, bo cały sezon 25/26 grała w I lidze,
    i przez to wypadała z typów jako `za_stara_historia`.

    Historia z niższego poziomu NIE jest tym samym co z Ekstraklasy, dlatego
    zapisujemy przy grze `comp` (rozgrywki, z których pochodzi) — korekta
    poziomu dzieje się przy KONSUMPCJI (`_hist_z_banku`), nie tutaj: surowe
    liczby zostają surowe, a to, jak je przeliczyć, jest decyzją modelu.
    """
    gry = bank.setdefault("gry", {})
    alias = bank.get("alias") or {}
    ile_gier: dict[str, int] = {}
    for rec in gry.values():
        for nm in (rec.get("druzyny") or {}):
            ile_gier[nm] = ile_gier.get(nm, 0) + 1

    def _ile(nm: str) -> int:
        """Gry drużyny, licząc też te zapisane pod nazwą z 365Scores.

        Bez aliasu drużyna obecna w banku pod innym zapisem wyglądała na
        ubogą W KAŻDYM CYKLU: zabierała budżet doganiania, pobierała mecze,
        które już tam są, dopisywała zero i wracała na początek kolejki.
        Patrz `zbuduj_aliasy_banku`.
        """
        return ile_gier.get(nm, 0) + sum(
            ile_gier.get(a, 0) for a in (alias.get(nm) or ())
        )

    ubogie = sorted(
        (nm for nm in {rotowire._norm(n) for n in nazwy_druzyn if n}
         if _ile(nm) < MIN_GIER_BANKU),
        key=_ile,
    )[:budzet]
    if not ubogie:
        return 0
    id_map = scores365.competitor_ids_z_rozgrywek(comp_ids or [])
    dodane = 0
    udane: list[str] = []
    nieudane: list[str] = []
    for nm in ubogie:
        try:
            # dopasowanie po ZBIORACH SŁÓW, nie po dokładnym kluczu — 365Scores
            # i statshub zapisują te same kluby inaczej („RSC Anderlecht" vs
            # „Anderlecht", „Caracas F.C." vs „Caracas FC"). Zmierzone
            # 2026-07-27: na dokładnym kluczu z 12 drużyn cyklu id dostawała
            # JEDNA, przez co podniesiony budżet doganiania nie miał czego
            # doganiać. Reguła jednoznaczności siedzi w `dopasuj_druzyne` —
            # patrz tam, czemu NIE jest to próg podobieństwa tekstu.
            cid = scores365.dopasuj_druzyne(id_map, nm)
            if not cid:
                cid = scores365.dopasuj_druzyne(
                    scores365.competitor_ids([nm]), nm
                )
            if not cid:
                nieudane.append(nm)
                continue
            przed = dodane
            for gid_i, ts_i, comp_i in (
                scores365.recent_finished_games_z_rozgrywkami(
                    int(cid), BENIAMINEK_GIER
                )
            ):
                gid_s = str(gid_i)
                if gid_s in gry:
                    continue
                druzyny = scores365.game_team_stats(gid_i)
                if len(druzyny) != 2:
                    continue
                for nm_g, ile_g in (scores365.game_scores(gid_i) or {}).items():
                    if nm_g in druzyny:
                        druzyny[nm_g]["gole"] = float(ile_g)
                # `wlasna` = historia Z INNEGO POZIOMU, wymagająca skalowania
                # przy konsumpcji. Mecz rozegrany w rozgrywkach NASZEGO zakresu
                # jest zwykłą historią, choćby przyszedł tą samą ścieżką —
                # inaczej dołożenie ligi (2026-07-27: osiem naraz) oznaczałoby,
                # że cała jej historia udaje "niższy poziom" i psuje skalę
                # wszystkim pozostałym.
                w_zakresie = comp_i in set(comp_ids or [])
                gry[gid_s] = {
                    "ts": ts_i, "druzyny": druzyny,
                    **({} if w_zakresie else {"wlasna": True}),
                }
                dodane += 1
                time.sleep(0.3)
            (udane if dodane > przed else nieudane).append(nm)
        except Exception:
            nieudane.append(nm)
            continue
    if dodane or nieudane:
        # komunikat mówi o UDANYCH, nie o kandydatach: poprzednia wersja
        # raportowała "dociągnięto dla 6 drużyn", gdy udało się dla jednej
        print(f"Bank stylu: dociągnięto {dodane} własnych meczów dla "
              f"{len(udane)} drużyn ({', '.join(udane) or '—'})"
              + (f"; bez id 365: {', '.join(nieudane)}" if nieudane else ""))
    return dodane


def aktualizuj_bank_stylu(
    gracze_id_sh: set[int],
    comp_ids: list[int] | None = None,
    past_events: list[dict] | None = None,
    klucz: str = "styl_bank",
    nazwy_druzyn: set[str] | None = None,
) -> dict:
    """Dolej do banku stylu (Supabase `klucz`) nowe rozegrane mecze:
    statystyki drużynowe i styl zawodników (365Scores), sytuacje strzałów
    (shotmapy statshub) oraz wzrosty zawodników (statshub /player).

    Bank jest trwały — 365/statshub trzymają dane meczu długo, ale wolimy
    nie zależeć od ich retencji, a shotmapy/staty pobierać RAZ per mecz.

    Domyślnie tryb MŚ (rozgrywki 5930, shotmapy z past_wc_events). Tryb
    LIGOWY podaje comp_ids (rozgrywki.comp365_druzynowe), rozegrane eventy
    statshub zakresu drużynowego i osobny klucz banku (styl_bank_liga) —
    style klubów i reprezentacji to dwa różne światy, nie mieszamy.
    """
    bank = supa.get_key(klucz) or {}
    gry = bank.setdefault("gry", {})
    zaw = bank.setdefault("zawodnicy", {})
    smapy = bank.setdefault("shotmap", {})
    wzrost = bank.setdefault("wzrost", {})
    zmienione = False

    # 1) mecze 365Scores: statystyki drużynowe + styl zawodników per mecz
    nowych = 0
    try:
        rozegrane_365: list[dict] = []
        for c in (comp_ids or [None]):
            try:
                rozegrane_365 += (
                    scores365.finished_games_by_competition(c)
                    if c else scores365.finished_games_by_competition()
                )
            except Exception:
                continue
        for g in rozegrane_365:
            gid = str(g["id"])
            if gid in gry:
                # UZUPEŁNIENIE WSTECZ: gole doszły do banku 2026-07-26, a mecz
                # raz zapisany nigdy nie był odwiedzany ponownie — historia
                # team_goals budowałaby się po jednym meczu na cykl zamiast
                # istnieć od razu. Wynik jedzie w tej samej odpowiedzi, więc
                # dopełnienie starych wpisów nie kosztuje ani jednego zapytania.
                dr_stare = gry[gid].get("druzyny") or {}
                for nm_g, ile_g in (g.get("gole") or {}).items():
                    if nm_g in dr_stare and dr_stare[nm_g].get("gole") is None:
                        dr_stare[nm_g]["gole"] = float(ile_g)
                        zmienione = True
                continue
            if nowych >= LIMIT_NOWYCH_GIER_STYLU:
                break
            try:
                druzyny = scores365.game_team_stats(g["id"])
                pelne = scores365.game_player_match_stats(g["id"])
            except Exception as e:
                diagnostyka.cichy("cykl", "bank_stylu_mecz", e)
                continue
            if len(druzyny) != 2:
                continue
            # GOLE do banku (2026-07-26): `game_team_stats` ich nie zwraca —
            # 365 nie traktuje wyniku jako "statystyki" — więc bank nie miał
            # historii dla team_goals, jedynego rynku z dodatnim ROI. Wynik
            # jedzie w tej samej odpowiedzi co lista meczów, czyli za zero
            # dodatkowych zapytań. TEAM_POLE_BANKU już mapuje team_goals na
            # "gole", więc to wypełnienie samo aktywuje istniejące ścieżki:
            # _hist_z_banku, _srednia_turnieju i koncesje drużynowe.
            for nm_g, ile_g in (g.get("gole") or {}).items():
                if nm_g in druzyny:
                    druzyny[nm_g]["gole"] = float(ile_g)
            gry[gid] = {"ts": g["ts"], "druzyny": druzyny}
            for pkey, rec in pelne.items():
                if not rec.get("minutes"):
                    continue
                z = zaw.setdefault(
                    pkey, {"druzyna": rec.get("druzyna", ""), "gry": {}}
                )
                if rec.get("druzyna"):
                    z["druzyna"] = rec["druzyna"]
                z["gry"][gid] = {
                    "ts": g["ts"], "min": rec.get("minutes", 0),
                    "dribbles_att": rec.get("dribbles_att", 0),
                    "dribbled_past": rec.get("dribbled_past", 0),
                    "aerial_won": rec.get("aerial_won", 0),
                    "aerial_att": rec.get("aerial_att", 0),
                    "ground_att": rec.get("ground_att", 0),
                    "key_passes": rec.get("key_passes", 0),
                    "crosses_att": rec.get("crosses_att", 0),
                }
                # przycinamy do ostatnich 10 meczów (profil i tak bierze 8)
                if len(z["gry"]) > 10:
                    najstarsze = sorted(
                        z["gry"], key=lambda k: z["gry"][k].get("ts", 0)
                    )[: len(z["gry"]) - 10]
                    for k in najstarsze:
                        del z["gry"][k]
            nowych += 1
            zmienione = True
            time.sleep(0.3)
    except Exception as e:
        print(f"Bank stylu: mecze 365 pominięte ({e})")

    # 1b) beniaminkowie i wracający z niższych lig: bank zasilany per rozgrywki
    # nigdy ich nie zobaczy, dopóki nie rozegrają kilku kolejek nowego sezonu
    if nazwy_druzyn:
        # NAJPIERW aliasy: bez nich lista „ubogich" niżej jest zafałszowana
        # i budżet doganiania idzie na drużyny, które bank już zna pod nazwą
        # z 365Scores (patrz `zbuduj_aliasy_banku`)
        try:
            if zbuduj_aliasy_banku(bank, nazwy_druzyn, comp_ids):
                zmienione = True
        except Exception as e:
            print(f"Bank stylu: aliasy pominięte ({e})")
        try:
            if dolej_historie_wlasna(bank, nazwy_druzyn, comp_ids):
                zmienione = True
        except Exception as e:
            print(f"Bank stylu: własna historia pominięta ({e})")

    # 2) shotmapy statshub (kontry per drużyna, stałe fragmenty per zawodnik)
    try:
        nowych_smap = 0
        for ev in (past_events if past_events is not None else past_wc_events()):
            eid = str(ev["id"])
            if eid in smapy:
                continue
            # w sezonie ligowym rozegranych meczów jest wielokrotnie więcej
            # niż na turnieju — pierwszy cykl dogania porcjami, nie zalewa API
            if nowych_smap >= LIMIT_NOWYCH_GIER_STYLU:
                break
            try:
                strzaly = statshub.fetch_event_shotmap(ev["id"])
            except Exception as e:
                # mecz nie wchodzi do BANKU STYLU — a bank jest podstawą
                # profilu rywala i rynków drużynowych budowanych z historii
                diagnostyka.cichy("cykl", "bank_stylu_shotmapa", e)
                continue
            if not strzaly:
                continue
            dr: dict[str, dict] = {}
            stale: dict[str, int] = {}
            for s in strzaly:
                tid = str(s.get("teamId") or "")
                if tid:
                    slot = dr.setdefault(tid, {"shots": 0, "kontra": 0})
                    slot["shots"] += 1
                    if s.get("situation") == "fast-break":
                        slot["kontra"] += 1
                if str(s.get("situation") or "") in (
                    "corner", "free-kick", "set-piece", "penalty"
                ):
                    pid = str(s.get("playerId") or "")
                    if pid:
                        stale[pid] = stale.get(pid, 0) + 1
            smapy[eid] = {
                "ts": ev.get("timeStartTimestamp") or 0,
                "druzyny": dr, "stale": stale,
            }
            nowych_smap += 1
            zmienione = True
            time.sleep(0.4)
    except Exception as e:
        print(f"Bank stylu: shotmapy pominięte ({e})")

    # 3) wzrosty zawodników (tylko prawdziwe id statshub; 0 = "pytaliśmy,
    # brak danych" — nie odpytujemy w kółko)
    brakujace = [
        pid for pid in gracze_id_sh
        if pid and pid < 900_000_000 and str(pid) not in wzrost
    ]
    for pid in brakujace[:LIMIT_WZROSTOW_NA_CYKL]:
        try:
            meta_p = statshub.fetch_player_meta(pid)
        except Exception as e:
            diagnostyka.cichy("cykl", "wzrost_zawodnika", e)
            continue
        wzrost[str(pid)] = meta_p.get("height") or 0
        zmienione = True
        time.sleep(0.25)

    # dry-run ma CZYTAĆ produkcję (inaczej liczby są nieporównywalne), ale nie
    # zapisywać — docstring build_league.main obiecuje „Supabase nietknięte"
    # i to jedyne miejsce, które tej obietnicy nie dotrzymywało
    if zmienione and not _dry_run():
        supa.put_key_bezpiecznie(klucz, bank)
    return bank


# start MŚ 2026 (2026-06-08 UTC, kilka dni zapasu przed 1. meczem) — granica
# między "sezonem klubowym" (prior) a "turniejem" (aktualizacja posteriora)
WC_START_TS = 1_780_876_800
# wygaszanie historii przedturniejowej w priorze (sezon klubowy jest długi)
PRIOR_TAU_DNI = 240.0
# minimalna/maksymalna siła priora klubowego (w ekwiwalencie pełnych meczów)
PRIOR_MIN_MECZE, PRIOR_MAX_MECZE = 4.0, 12.0
# minimalna WARTOŚĆ (%) Superbetu ponad no-vig UK, by uznać linię za miękką
# (dowód okazji z kursem). Skaluje się z kursem, w odróżnieniu od dawnej sztywnej
# różnicy 0.10 kursu. Strojony — kandydat do kalibracji z rozliczeń okazji.
PROG_EV_UK = 4.0
# ⚑ LIMIT EKSPOZYCJI NA MECZ ZDJĘTY Z LISTY (decyzja właściciela 14.08).
#
# Powód nie jest kosmetyczny — zmierzony na 366 rozliczeniach epoki ligowej
# (bez drabinek), w podziale na to, ILE typów model wystawił w danym meczu:
#   1 typ w meczu    n= 33  luka -10,9 pp  ROI  +6,4%   (próba za mała)
#   2-4 typy         n=176  luka -13,3 pp  ROI  -6,7%
#   5 i więcej       n=157  luka  -5,3 pp  ROI  +8,3%
# Mecz, o którym model ma dużo do powiedzenia, jest DWA RAZY lepiej
# skalibrowany i jako jedyny zarabia. Efekt przeżył kontrolę na pasmo kursu
# (monotoniczny w 9 z 9 komórek), horyzont publikacji, ligę i drabinki.
# Limit obcinałby więc dokładnie najlepszy materiał.
#
# Przy okazji zmierzone: ta brama i tak była martwa — w całej księdze (4594
# wpisów) odpaliła RAZ, bo stała na końcu łańcucha i wcześniejsze bramy
# zdejmowały typy przed nią. Zostaje jako stała, bo używa jej pula kuponów
# (tam korelacja legów realnie boli), ale lista jej nie pyta.
#
# Bogactwo materiału meczu przeszło za to do RANKINGU — patrz `_atrakcyjnosc`.
MAX_PEWNIAKOW_MECZ = 4
# ⚑ Czy kwarantanna (rynku / strony / kategorii) ZDEJMUJE typ z listy.
# Od 14.08 nie — pełne uzasadnienie i liczby przy `_kwarantanna_zdejmuje`.
# W puli kuponów brama zostaje niezależnie od tej stałej.
KWARANTANNA_ZDEJMUJE_Z_LISTY = False
# ⚑ OD ILU KANDYDATÓW MECZ JEST „BOGATY" — próg wzięty z LUKI KALIBRACJI,
# nie z ROI. Rozkład na 419 rozliczeniach, wg liczby typów, które model
# wystawił w danym meczu (KANDYDACI, czyli razem z tłem — liczba znana PRZED
# selekcją, więc bez zaglądania w przyszłość):
#
#      1-4 kandydatów   n= 46  luka -21,7 pp   ROI -22,4%
#      5-9              n= 69  luka -18,9 pp   ROI -14,9%
#     10-19             n=216  luka  -9,4 pp   ROI  -3,5%
#     20+               n= 88  luka  -2,1 pp   ROI +15,1%
#
# Granica 10 dzieli „luka około −20 pp" od „luka −9 pp i lepiej". Wzięta
# z LUKI, bo ta jest stabilna: dobieranie progu i siły premii pod ROI dawało
# przy n=107 wyniki od −2,7% do +2,4%, czyli strojenie pod szum.
#
# ⚑ CZEGO TA LICZBA NIE MÓWI: kontroli per liga NIE DA SIĘ przeprowadzić —
# mecze z 20+ kandydatami to niemal wyłącznie Brasileirão i Liga Profesional,
# a te z kilkoma to egzotyka. Sygnał może więc znaczyć „mecz, o którym mamy
# dużo danych" albo po prostu „liga, którą dobrze pokrywamy". Obie
# interpretacje prowadzą do tej samej kolejności, ale gdyby doszło pokrycie
# nowych lig, trzeba to przemierzyć.
PROG_BOGATEGO_MECZU = 10
# Premia w kolejności listy, w skali pozostałych premii (matchup 1,15,
# rotacja 1,10). To jest KOLEJNOŚĆ, nie korekta szansy — i świadomie nie jest
# strojona pod ROI.
PREMIA_BOGATEGO_MECZU = 1.10


def klub_prior(
    trend: statshub.StatshubTrend,
    now: int,
    opp_w: list[float] | None,
) -> tuple[counts.GroupPrior, list[bool]] | None:
    """SILNY prior Gamma z historii SPRZED turnieju (sezon klubowy + kadra).

    Leczy chroniczną "za małą próbę": zamiast słabej średniej z 6-10 meczów
    turnieju, punktem wyjścia jest tempo per-90 z pełnej dostępnej historii
    przedturniejowej (ważonej świeżością i siłą rywala), a mecze turnieju
    tylko AKTUALIZUJĄ posterior (maska likelihood — bez podwójnego liczenia).

    Zwraca (prior, maska_likelihood) albo None, gdy próba sprzed turnieju
    jest za mała (wtedy zostaje dotychczasowy słaby prior + pełna historia).
    """
    w_sum, exp_sum, cnt_sum = 0.0, 0.0, 0.0
    mask = []
    for i, ts_g in enumerate(trend.timestamps):
        pre = ts_g < WC_START_TS
        mask.append(not pre)
        if not pre or i >= len(trend.counts):
            continue
        mins = trend.minutes[i] if i < len(trend.minutes) else 0.0
        if mins <= 0:
            continue
        dni = max((now - ts_g) / 86400.0, 0.0)
        w = float(np.exp(-dni / PRIOR_TAU_DNI))
        if opp_w and i < len(opp_w):
            w *= opp_w[i]
        exp_sum += w * mins / 90.0
        cnt_sum += w * trend.counts[i]
        w_sum += w
    if exp_sum < PRIOR_MIN_MECZE:
        return None
    rate = cnt_sum / exp_sum
    return (
        counts.GroupPrior(
            mean_per90=max(rate, 0.05),
            pseudo_matches=float(min(exp_sum, PRIOR_MAX_MECZE)),
            source="klub",
        ),
        mask,
    )


def score_from_trend(
    trend: statshub.StatshubTrend,
    opp_avg_ref: float | None,
    lineup_confirmed: bool = False,
    predicted_available: bool = False,
    roto_pred: bool | None = None,
    roto_confirmed: bool = False,
    matchup_factor: float | None = None,
    matchup_opis: str = "",
    wc_names: set | None = None,
    elo_map: dict[str, int] | None = None,
    tempo_meczu: dict | None = None,
    sedzia: dict | None = None,
    koncesje_tab: "koncesje.Koncesje | None" = None,
    player_style=None,
    opponent_style=None,
    liga: bool = False,
):
    """Zbuduj PlayerHistory z recentGames i policz predykcję (bez kursów).

    Składy — hierarchia sygnałów:
      1. lineupConfirmed (statshub) LUB skład potwierdzony na Rotowire
         -> official_started: twardy fakt (w XI / scenariusz ławki),
      2. przewidywane XI z DWÓCH źródeł (statshub + Rotowire):
         zgoda -> mocny sygnał miękki; spór -> wracamy do historii minut,
      3. tylko jedno źródło -> jego prognoza jako sygnał miękki,
      4. brak prognoz -> sama historia.

    elo_map — ratingi eloratings.net: ciągła waga próby siłą rywala
    (Botswana ≠ Francja) i syntetyczny spread, gdy brak kursów 1X2.
    tempo_meczu — {'spread','total',...} z model/tempo.py (kursy Superbetu).
    """
    now = int(time.time())
    elo_map = elo_map or {}
    # ważenie próby siłą rywala: ciągła waga z Elo (mecz z Francją liczy się
    # pełniej niż z Botswaną); rywal bez ratingu (klub) dostaje wagę bazową
    opp_w = None
    if trend.game_opponents:
        opp_w = [
            eloratings.sample_weight(
                elo_map.get(eloratings._norm(o)),
                is_wc_participant=bool(wc_names and rotowire._norm(o) in wc_names),
            )
            for o in trend.game_opponents[: len(trend.counts)]
        ]
        if len(opp_w) < len(trend.counts):
            opp_w += [0.8] * (len(trend.counts) - len(opp_w))
    hist = PlayerHistory(
        counts=trend.counts,
        minutes=trend.minutes,
        days_ago=[max((now - ts) / 86400.0, 0.0) for ts in trend.timestamps],
        started=trend.started,
        opp_weights=opp_w,
    )
    if sum(1 for m in trend.minutes if m > 0) < 3:
        return None, hist
    # PRIOR: pełna historia sprzed turnieju jako silny prior Gamma
    # ("sezon klubowy"), mecze turnieju aktualizują posterior; przy małej
    # próbie przedturniejowej — dotychczasowy słaby prior + cała historia.
    # W LIDZE podział klub/kadra nie istnieje — ciągła historia + prior grupowy.
    kp = None if liga else klub_prior(trend, now, opp_w)
    if kp is not None:
        prior, hist.likelihood_mask = kp
    else:
        prior = group_prior_from_context(trend)
    sh_pred = trend.in_predicted_lineup if predicted_available else None
    if lineup_confirmed:
        official, predicted = trend.in_predicted_lineup, None
    elif roto_confirmed and roto_pred is not None:
        official, predicted = roto_pred, None
    elif sh_pred is not None and roto_pred is not None:
        # dwa źródła: zgoda = sygnał, spór = nie wiemy -> historia
        official = None
        predicted = sh_pred if sh_pred == roto_pred else None
    else:
        official = None
        predicted = sh_pred if sh_pred is not None else roto_pred
    # tempo/scenariusz meczu: kursy 1X2+gole Superbetu; fallback różnica Elo
    spread_home, total = None, None
    if tempo_meczu:
        spread_home = tempo_meczu.get("spread")
        total = tempo_meczu.get("total")
    else:
        spread_home = eloratings.synthetic_spread(
            elo_map.get(eloratings._norm(trend.team_name if trend.is_home else trend.opponent_name)),
            elo_map.get(eloratings._norm(trend.opponent_name if trend.is_home else trend.team_name)),
        )
    # spread z perspektywy DRUŻYNY ZAWODNIKA (dodatni = jego zespół faworytem)
    spread_teamu = None
    if spread_home is not None:
        spread_teamu = spread_home if trend.is_home else -spread_home
    # kontekst: średnia rywala względem ligi (żywy feed statshub), a gdy jej
    # nie ma — profil koncesji rywala per rynek×pozycja z banku (koncesje.py)
    opp_allowed = trend.opponent_average
    opp_avg = trend.league_average
    # 6 = ZAŁOŻENIE, nie zmierzona wielkość próby: statshub NIE ujawnia w API
    # (props/player-trends), z ilu meczów liczy opponentAverage — sprawdzone
    # w StatshubTrend/fetch_event_trends, brak takiego pola. shrink_factor()
    # ściąga więc ZAWSZE tym samym k=6/(6+12)=0.33, niezależnie od realnej
    # (nieznanej) próby. Fallback niżej (koncesje.py, gdy statshub milczy) MA
    # prawdziwe n_meczy z własnego banku — nie ten przypadek. Nie zgadywać
    # innej stałej bez danych; ew. do zmierzenia jak marża UK (porównać
    # kalibrację rekordów z opp_n=6 vs rekordów z realnym n z koncesje.py).
    opp_n = 6 if trend.opponent_average else 0
    koncesja_opis = ""
    if opp_allowed is None and koncesje_tab is not None:
        kc = koncesje_tab.lookup(
            trend.opponent_name, trend.market_code, trend.position,
            elo_map=elo_map, team_name=trend.team_name, now=now,
        )
        if kc:
            opp_allowed, opp_avg, opp_n = kc
            kub = koncesje.kubelek_pozycji(trend.position) or "tej formacji"
            koncesja_opis = (
                f"Na tym turnieju zawodnicy z formacji „{kub}” notują przeciw "
                f"{trend.opponent_name} ~{opp_allowed:.2f} na 90 min przy "
                f"normie {opp_avg:.2f} (próba: {opp_n} meczów)"
            )
    if liga:
        # liga: realny gospodarz z feedu, neutralne boisko nie występuje
        # (finały pucharów na neutralnym — do obsłużenia przy okazji finałów)
        ctx_is_home, ctx_neutral_venue = trend.is_home, False
    else:
        ctx_is_home, ctx_neutral_venue = venue_context(
            trend.team_name, trend.opponent_name, trend.is_home
        )
    ctx = MatchContext(
        is_home=ctx_is_home,
        is_favourite=bool(spread_teamu is not None and spread_teamu > 0.15),
        neutral_venue=ctx_neutral_venue,
        implied_spread=spread_teamu,
        implied_total=total,
        opponent_allowed_per90=opp_allowed,
        league_avg_per90=opp_avg,
        opponent_sample_matches=opp_n,
        opponent_concession_opis=koncesja_opis,
        # profil sędziego (365Scores): mnożnik fauli vs średnia turnieju —
        # shrinkowany i capowany w context.referee_factor
        referee_fouls_multiplier=(sedzia or {}).get("mnoznik"),
        referee_sample_matches=(sedzia or {}).get("n", 0),
        referee_name=(sedzia or {}).get("sedzia") or "",
        official_started=official,
        predicted_started=predicted,
        opponent_name=trend.opponent_name,
        # PEŁNE matchupy stylu (model/styl.py -> model/matchup.py) — gdy
        # profile są, engine używa ich ZAMIAST matchup-lite (elif w engine)
        player_style=player_style,
        opponent_style=opponent_style,
        matchup_factor=matchup_factor,
        matchup_opis=matchup_opis,
    )
    return (prior, ctx), hist


def main(tryb=None) -> None:
    """Cienki wrapper: gwarantuje zapis manifestu (_manifest.json) na KAŻDYM
    wyjściu z _main_impl (sukces, wczesny return, wyjątek) — patrz komentarz
    przy _generated_this_run wyżej.

    tryb: build_league.TrybLigowy albo None (klasyczny przebieg MŚ)."""
    global _tryb
    _tryb = tryb
    _generated_this_run.clear()
    # Rejestr warstw uczenia jest globalny w module `rozliczanie`, a w jednym
    # procesie potrafią pójść dwa przebiegi (build_league woła main() per liga).
    # Bez zerowania drugi przebieg dziedziczyłby werdykt pierwszego.
    rozliczanie.reset_stanu_uczenia()
    try:
        _main_impl(tryb)
    finally:
        _dump("_manifest.json", {"keys": sorted(_generated_this_run)})
        _tryb = None


def _main_impl(tryb=None):
    events = tryb.events if tryb else upcoming_wc_events()
    print(f"Nadchodzące mecze {'ligowe' if tryb else 'MŚ'} (statshub): {len(events)}")
    if not events:
        print("Brak nadchodzących meczów w statshub.")
        _rozlicz_i_zapisz([], [])  # rozliczenia lecą niezależnie od nowych typów
        return

    try:
        trends = statshub.fetch_event_trends([e["id"] for e in events])
    except Exception as e:
        print(f"statshub chwilowo niedostępny ({e}) — pomijam ten cykl, dane bez zmian.")
        _rozlicz_i_zapisz([], [])
        return
    print(f"Trendów propsów: {len(trends)} "
          f"({len(set(t.player_id for t in trends))} zawodników)")
    # RATUNEK HISTORII (tylko liga): feed propsów pokrywa mecze wycenione
    # przez buków UK, więc poza Europą historia zawodnika bywa dwuletnia i
    # cały kandydat ginie na bramie świeżości. Robimy to TU, przed czymkolwiek
    # innym, żeby świeża próba weszła też do banku, minut i średnich drużyny.
    if tryb and trends:
        odswiez_stare_trendy(trends, int(time.time()))
    # ostatni mecz KAŻDEJ drużyny wg feedu — do rozróżnienia "zawodnik siedzi"
    # od "cała liga pauzowała" (przerwa letnia / mundialowa): flaga stare_dane
    # nie powinna chować typów za przerwę, na którą zawodnik nie miał wpływu
    ostatni_mecz_druzyny: dict[int, int] = {}
    for _t in trends:
        if _t.team_id is None:
            continue
        maks = max((ts for ts, m in zip(_t.timestamps, _t.minutes)
                    if ts > 0 and m is not None), default=0)
        if maks > ostatni_mecz_druzyny.get(_t.team_id, 0):
            ostatni_mecz_druzyny[_t.team_id] = maks
    if not trends:
        # statshub schował feed propsów (2026-07-04: /api/props/* zwraca
        # pustkę anonimowo — prawdopodobnie za kontem). NIE przerywamy:
        # historia jest w banku trendów (Supabase) i w 365Scores, składy
        # daje Rotowire, kursy Superbet — jedziemy bez statshuba.
        print("statshub: 0 propsów w feedzie — buduję trendy z banku "
              "historii i pełnych statystyk 365Scores.")

    # --- BIBLIOTEKA HISTORII: mecze bez propsów statshub (np. ćwierćfinały) ---
    # statshub wystawia propsy ~24-48 h przed meczem, a Superbet kwotuje dużo
    # wcześniej (i wtedy kursy są najmiększe). Historia zawodnika nie zależy
    # od nadchodzącego meczu — bierzemy jego najświeższy trend z ROZEGRANYCH
    # meczów MŚ i przepinamy na nowy event (rywal/kontekst neutralne, składy
    # z Rotowire, kursy z Superbetu).
    covered = {t.event_id for t in trends}
    # PEŁNE SKŁADY (statshub predicted/team-lineup + backup Sofascore) —
    # gdzie znamy całą XI drużyny, nadpisujemy migotliwą flagę
    # inPredictedLineup z trendów pewniejszym źródłem (pid w XI / poza XI)
    xi_pelne = sklady_xi(events)
    if xi_pelne:
        n_conf_xi = sum(1 for v in xi_pelne.values() if v["confirmed"])
        zrodla_xi = Counter(v["zrodlo"] for v in xi_pelne.values())
        print(f"Składy: pełne XI dla {len(xi_pelne)} meczów "
              f"({n_conf_xi} potwierdzonych; "
              + ", ".join(f"{k}: {v}" for k, v in zrodla_xi.most_common()) + ")")
    for t in trends:
        xi_t = (xi_pelne.get(t.event_id) or {}).get("xi_by_team", {}).get(t.team_id)
        if xi_t is not None:
            t.in_predicted_lineup = t.player_id in xi_t
    # sygnał przewidywanego/oficjalnego składu (in_predicted_lineup) jest
    # wiarygodny per (mecz, zawodnik) TYLKO dla trendów z żywego feedu —
    # dokładane niżej trendy z banku/365 mają tam zawsze False i bez tej
    # mapy wyglądałyby przy ogłoszonym składzie jak "wszyscy poza XI"
    xi_zywy: dict[tuple[int, int], bool] = {}
    for t in trends:
        if t.event_id and t.player_id:
            k_xi = (t.event_id, t.player_id)
            xi_zywy[k_xi] = xi_zywy.get(k_xi, False) or t.in_predicted_lineup
    # zawodnicy z pełnych XI bez żywego trendu (dokładki z banku/365) też
    # mają wiarygodny sygnał składu — bank czyta go właśnie z tej mapy
    for mid_x, v in xi_pelne.items():
        for xi_set in v["xi_by_team"].values():
            for pid_x in xi_set:
                xi_zywy[(mid_x, pid_x)] = True
    uncovered = [
        e for e in events
        if e["id"] not in covered and e.get("homeTeamId") and e.get("awayTeamId")
    ]
    wszystkie_ev = [
        e for e in events if e.get("homeTeamId") and e.get("awayTeamId")
    ]
    # timestampy meczów reprezentacji per drużyna (z historii 365Scores) —
    # do oznaczania "kadra vs klub" w formie zawodnika
    nt_ts: dict[str, set] = {}
    bank_recs: dict = {}
    try:
        # 1) trwała biblioteka z Supabase (przeżywa kasowanie propsów przez statshub)
        stored = load_trend_lib()
        lib: dict[tuple[int, str], statshub.StatshubTrend] = {}
        for rec in stored.values():
            try:
                t = statshub.StatshubTrend(**rec)
                lib[(t.player_id, t.market_code)] = t
            except TypeError:
                continue  # stary format po zmianie pól — rekord wypada

        def _merge(t: statshub.StatshubTrend) -> None:
            key = (t.player_id, t.market_code)
            prev = lib.get(key)
            ts_new = t.timestamps[0] if t.timestamps else 0
            ts_old = prev.timestamps[0] if prev and prev.timestamps else -1
            if prev is None or ts_new >= ts_old:
                lib[key] = t

        # 2) dołóż co jeszcze zostało z rozegranych eventów + dzisiejsze trendy
        if uncovered:
            past_ids = list(tryb.past_event_ids) if tryb else past_wc_event_ids()
            for i in range(0, len(past_ids), 8):
                for t in statshub.fetch_event_trends(past_ids[i:i + 8]):
                    _merge(t)
        for t in trends:
            _merge(t)
        bank_recs = {
            f"{t.player_id}:{t.market_code}": asdict(t) for t in lib.values()
        }
        if not _dry_run():
            save_trend_lib(bank_recs)

        # 3) przepnij najświeższe trendy z biblioteki na KAŻDY nadchodzący
        #    mecz, którego żywy feed nie pokrywa w danym (zawodnik, rynek) —
        #    wcześniej robiliśmy to tylko dla meczów CAŁKIEM bez propsów,
        #    przez co 2-3 żywe trendy "zasłaniały" cały bank (odbiory,
        #    faule ról drugoplanowych) i pula pewniaków była samymi gwiazdami
        team_by_id: dict[int, str] = {}
        for t in lib.values():
            if t.team_id:
                team_by_id[t.team_id] = t.team_name
            if t.opponent_id:
                team_by_id[t.opponent_id] = t.opponent_name
        n_lib = 0
        juz_w_trendach = {
            (t.event_id, t.player_id, t.market_code) for t in trends
        }
        for e in wszystkie_ev:
            hid, aid = e["homeTeamId"], e["awayTeamId"]
            if not team_by_id.get(hid) or not team_by_id.get(aid):
                continue  # nieznana drużyna = brak historii i pusta karta meczu
            for (pid, mk), t in lib.items():
                if t.team_id not in (hid, aid):
                    continue
                if (e["id"], pid, mk) in juz_w_trendach:
                    continue  # żywy feed już to pokrywa
                juz_w_trendach.add((e["id"], pid, mk))
                opp_id = aid if t.team_id == hid else hid
                trends.append(dc_replace(
                    t,
                    event_id=e["id"],
                    opponent_id=opp_id,
                    opponent_name=team_by_id.get(opp_id, ""),
                    is_home=(t.team_id == hid),
                    opponent_average=None, opponent_rank=None,
                    in_predicted_lineup=xi_zywy.get((e["id"], pid), False),
                    ref_odds=[],
                ))
                n_lib += 1
        if n_lib:
            print(f"Biblioteka historii ({len(lib)} trendów w banku): "
                  f"+{n_lib} przepiętych na nadchodzące mecze")

        # 4) uzupełnij braki PER ZAWODNIK×RYNEK z pełnych statystyk meczowych
        #    365Scores (minuty, strzały, faule, faule na zawodniku, przechwyty,
        #    spalone; odbiory — brak w 365). Dla WSZYSTKICH meczów — nie tylko
        #    niepokrytych: bank rzadko ma całą kadrę, a to właśnie tu rodzą
        #    się typy kontekstowe na role drugoplanowe (nie same gwiazdy).
        MARKETY_365_FULL = ("shots", "sot", "fouls_committed", "fouls_won",
                            "interceptions", "offsides")
        pokryci = {
            (t.team_id, rotowire._norm(t.player_name), t.market_code)
            for t in trends
        }
        zespoly: list[tuple[dict, int, int, bool, str, str]] = []
        for e in wszystkie_ev:
            hid, aid = e["homeTeamId"], e["awayTeamId"]
            slug_parts = str(e.get("slug", "")).replace("-vs-", "|").split("|")
            if len(slug_parts) != 2:
                continue
            home_nm = slug_parts[0].replace("-", " ").title()
            away_nm = slug_parts[1].rsplit("-", 1)[0].replace("-", " ").title()
            zespoly.append((e, hid, aid, True, home_nm, away_nm))
            zespoly.append((e, aid, hid, False, away_nm, home_nm))
        if zespoly:
            cids365 = scores365.competitor_ids(
                sorted({z[4] for z in zespoly})
            )
            n_365 = 0
            hist_cache: dict[str, list] = {}
            for e, tid, opp_tid, is_home, team_nm, opp_nm in zespoly:
                cid = cids365.get(rotowire._norm(team_nm))
                if not cid:
                    continue
                if team_nm not in hist_cache:
                    hist_cache[team_nm] = scores365.team_match_history(cid, 6)
                    nt_ts.setdefault(team_nm, set()).update(
                        g_ts for g_ts, _ in hist_cache[team_nm]
                    )
                games = hist_cache[team_nm]
                if len(games) < 3:
                    continue
                gracze = sorted({p for _, st in games for p in st})
                for pkey in gracze:
                    wpisy = [(ts, st.get(pkey)) for ts, st in games]
                    zagrane = [w for w in wpisy if w[1] and w[1].get("minutes", 0) > 0]
                    if len(zagrane) < 3:
                        continue
                    # pozycja z formacji 365 (dominująca litera) — trafia do
                    # kubełka profilu rywala; wcześniejsze "M" na sztywno
                    # wrzucało obrońców i napastników do złego kubełka
                    poz_licznik: dict[str, int] = {}
                    for _, rec in zagrane:
                        p_l = str(rec.get("pos") or "")
                        if p_l:
                            poz_licznik[p_l] = poz_licznik.get(p_l, 0) + 1
                    poz_gl = max(poz_licznik, key=poz_licznik.get) \
                        if poz_licznik else "M"
                    if poz_gl == "G":
                        continue  # rynki zawodników z pola — bramkarz zbędny
                    pid_365 = (900_000_000
                               + zlib.crc32(pkey.encode("utf-8")) % 90_000_000)
                    for mk in MARKETY_365_FULL:
                        if (tid, pkey, mk) in pokryci:
                            continue  # jest już trend z banku/statshub
                        c_l, m_l, tss, st_l, poz_l = [], [], [], [], []
                        for ts_g, rec in wpisy:
                            if rec is None:
                                continue
                            c_l.append(float(rec.get(mk, 0)))
                            m_l.append(float(rec.get("minutes", 0)))
                            tss.append(int(ts_g))
                            st_l.append(bool(rec.get("started")))
                            poz_l.append(str(rec.get("pos") or ""))
                        trends.append(statshub.StatshubTrend(
                            # hash() jest randomizowany per proces — id musi
                            # być STABILNE między cyklami (log typów, kupony)
                            player_id=pid_365,
                            player_name=pkey.title(),
                            position=poz_gl,
                            team_id=tid, team_name=team_nm,
                            opponent_id=opp_tid, opponent_name=opp_nm,
                            is_home=is_home, market_code=mk, line=0.5,
                            in_predicted_lineup=xi_zywy.get(
                                (e["id"], pid_365), False),
                            league_average=None, opponent_average=None,
                            opponent_rank=None, total_ranks=None,
                            event_id=e["id"],
                            counts=c_l, minutes=m_l,
                            timestamps=tss, started=st_l,
                            game_positions=poz_l,
                        ))
                        n_365 += 1
            if n_365:
                print(f"365Scores pełne staty: +{n_365} trendów uzupełnionych "
                      f"({len(hist_cache)} drużyn)")
    except Exception as ex:
        print(f"Biblioteka historii pominięta ({ex})")

    # --- rynki z map strzałów (365Scores): głową / zza pola karnego ---
    # Syntetyczne trendy: liczby z chartEvents 365Scores (per typ strzału),
    # minuty/starty/pozycje ze statshubowego trendu "shots" tego zawodnika
    # (mecze parowane po timestampie). Dalej płyną przez ten sam scoring,
    # co rynki rdzeniowe (składy, matchup, kursy Superbetu, bezpieczniki).
    SHOT_SPLIT = {
        "headed_shots": "headed",
        "headed_sot": "headed_sot",
        "shots_outside_box": "outside",
        "sot_outside_box": "sot_outside",
        # rynki STS (bez kursu w chmurze) — prawdziwa historia zamiast szacunku
        "shots_blocked": "blocked",
        "shots_off_target": "off_target",
    }
    try:
        shots_trends = [t for t in trends if t.market_code == "shots"]
        team_names = sorted({t.team_name for t in shots_trends if t.team_name})
        cids = scores365.competitor_ids(team_names)
        hist365: dict[str, list] = {}
        for name in team_names:
            cid = cids.get(rotowire._norm(name))
            if cid:
                hist365[name] = scores365.team_shot_history(cid, n_games=6)
                nt_ts.setdefault(name, set()).update(
                    g_ts for g_ts, _ in hist365[name]
                )
        n_syn = 0
        for t in shots_trends:
            games365 = hist365.get(t.team_name) or []
            if not games365:
                continue
            all_keys = {k for _, pp in games365 for k in pp}
            pkey = scores365.resolve_player_key(all_keys, t.player_name)
            if pkey is None:
                continue  # zawodnik bez strzałów w historii 365 — nic do modelowania
            for mk2, f365 in SHOT_SPLIT.items():
                counts2, minutes2, ts2, started2, pos2 = [], [], [], [], []
                for i, ts in enumerate(t.timestamps):
                    rec = next(
                        (pp for g_ts, pp in games365 if abs(g_ts - ts) < 36 * 3600),
                        None,
                    )
                    if rec is None:
                        continue
                    counts2.append(float(rec.get(pkey, {}).get(f365, 0)))
                    minutes2.append(t.minutes[i])
                    ts2.append(ts)
                    started2.append(t.started[i])
                    pos2.append(t.game_positions[i] if i < len(t.game_positions) else "")
                if sum(1 for m in minutes2 if m > 0) < 3:
                    continue
                trends.append(dc_replace(
                    t, market_code=mk2, line=0.5,
                    counts=counts2, minutes=minutes2, timestamps=ts2,
                    started=started2, game_positions=pos2,
                    opponent_average=None, opponent_rank=None,
                    league_average=None, ref_odds=[],
                ))
                n_syn += 1
        if n_syn:
            print(f"365Scores: dołożono {n_syn} trendów map strzałów "
                  f"(drużyn z historią: {len(hist365)})")
    except Exception as e:
        print(f"365Scores pominięte ({e}) — rynki map strzałów bez zmian.")

    # nazwy drużyn są w trendach (event ma tylko ID) -> mapa id->nazwa
    team_name = {}
    for t in trends:
        if t.team_id:
            team_name[t.team_id] = t.team_name
        if t.opponent_id:
            team_name[t.opponent_id] = t.opponent_name
    if tryb:
        # w trybie ligowym nazwy z by-date (homeTeam/awayTeam) są pełniejsze
        # niż z trendów (drużyna bez propsów nie ma trendu) i nadpisują je
        team_name.update(tryb.team_name)

    # uczestnicy MŚ (znormalizowani) — do ważenia próby siłą rywala;
    # w lidze brak listy uczestników (waga bazowa dla wszystkich rywali)
    wc_names = set() if tryb else {
        rotowire._norm(n) for n in team_name.values() if n
    } | {
        rotowire._norm(x)
        for t in trends
        for x in (t.team_name, t.opponent_name)
        if x
    }

    # profil rywala per rynek×pozycja — ze WSZYSTKICH meczów turnieju w banku
    # (nie tylko przeciw aktualnym przeciwnikom: drużyny, które odpadły, też
    # budują normę i profile); filtr klubów załatwia min_ts (sezon skończony)
    try:
        koncesje_tab = koncesje.zbuduj_koncesje(
            bank_recs, wc_names=None,
            min_ts=tryb.koncesje_min_ts if tryb else WC_START_TS,
        )
        n_prof = len({k[0] for k in koncesje_tab._obs})
        print(f"Profil rywali: {n_prof} drużyn, "
              f"{sum(len(v) for v in koncesje_tab._obs.values())} obserwacji")
    except Exception as e:
        koncesje_tab = None
        print(f"Profil rywali pominięty ({e})")

    # PEŁNE MATCHUPY STYLU: bank (drużyny 365 + shotmapy statshub + wzrosty)
    # -> profile OpponentStyle/PlayerStyle -> engine (model/matchup.py).
    # Awaria któregokolwiek źródła = degradacja do matchup-lite, nie błąd.
    style_turnieju = None
    bank_stylu: dict = {}
    try:
        if tryb:
            # wersja ligowa: mecze 365 z rozgrywek drużynowych (comp365),
            # shotmapy z rozegranych meczów zakresu, OSOBNY klucz banku —
            # style klubów nie mieszają się z reprezentacjami MŚ
            bank_stylu = aktualizuj_bank_stylu(
                {t.player_id for t in trends},
                comp_ids=rozgrywki.comp365_druzynowe(),
                past_events=tryb.past_druzynowe_events,
                klucz="styl_bank_liga",
                # tylko drużyny z meczów objętych zakresem DRUŻYNOWYM: bank
                # stylu służy rynkom drużynowym, a id 365 potrafimy rozwiązać
                # wyłącznie z terminarzy tych rozgrywek. Dla Cruzeiro czy
                # Hammarby (poza zakresem) i tak nie liczymy rynków drużynowych,
                # więc dociąganie im historii to spalone zapytania i szum
                # w logu ("nie rozwiązano id 365" dla 5 z 6 drużyn).
                nazwy_druzyn={
                    tryb.team_name[t] for e in tryb.events
                    if e.get("id") in tryb.druzynowe_mids
                    for t in (e.get("homeTeamId"), e.get("awayTeamId"))
                    if t in tryb.team_name
                },
            )
        else:
            bank_stylu = aktualizuj_bank_stylu({t.player_id for t in trends})
        strony_zaw: dict[str, str] = {}
        for t in trends:
            k_st = rotowire._norm(t.player_name)
            if k_st not in strony_zaw:
                s_st = matchup_lite.dominant_side(t.game_positions[:8])
                if s_st != "C":
                    strony_zaw[k_st] = s_st
        tid_by_norm = {
            rotowire._norm(n): tid for tid, n in team_name.items() if n
        }
        style_turnieju = styl.StyleTurnieju(bank_stylu, strony_zaw, tid_by_norm)
        print(f"Bank stylu: {len(bank_stylu.get('gry', {}))} meczów 365, "
              f"{len(bank_stylu.get('shotmap', {}))} shotmap, "
              f"{len(bank_stylu.get('wzrost', {}))} wzrostów")
    except Exception as e:
        print(f"Bank stylu pominięty ({e}) — matchupy w trybie lite")

    # kursy Superbetu (w trybie ligowym lista przyjechała już z parownikiem)
    if tryb:
        sb_events = tryb.sb_events
    else:
        try:
            sb_events = superbet.list_events(days_ahead=8)
        except Exception as e:
            sb_events = []
            print(f"Superbet niedostępny: {e}")

    # Elo reprezentacji (eloratings.net, cache w Supabase) — ciągła waga
    # próby siłą rywala + syntetyczny spread, gdy brak kursów 1X2.
    # W lidze eloratings nie zna klubów — waga bazowa, spread z kursów 1X2.
    elo_map = {} if tryb else eloratings.get_ratings()
    if not tryb:
        print(f"Elo: {len(elo_map)} reprezentacji" if elo_map
              else "Elo niedostępne — wagi próby z listy uczestników MŚ")

    # profil sędziów: obsada + średnia fauli/mecz vs oczekiwania par drużyn
    try:
        if tryb:
            # wersja ligowa: tylko mecze zakresu drużynowego (tam liczymy
            # rynki dyscyplinarne), rozgrywki z profili, osobny cache
            sedzia_by_mid = profil_sedziow(
                [e for e in events if e["id"] in tryb.druzynowe_mids],
                team_name,
                comp_ids=rozgrywki.comp365_druzynowe(),
                cache_key="sedziowie_cache_liga",
                # kartki per mecz leżą już w banku — złączenie po id meczu
                # daje drugi profil arbitra za darmo (patrz `profil_sedziow`)
                bank_gry=(bank_stylu or {}).get("gry"),
            )
        else:
            sedzia_by_mid = profil_sedziow(
                events, team_name, bank_gry=(bank_stylu or {}).get("gry"),
            )
        _ev_by = {e["id"]: e for e in events}
        for mid_s, s in sedzia_by_mid.items():
            _e = _ev_by.get(mid_s, {})
            lbl = (f"{team_name.get(_e.get('homeTeamId'), '?')} – "
                   f"{team_name.get(_e.get('awayTeamId'), '?')}")
            print(f"  sędzia {lbl}: {s['sedzia']}"
                  + (f" (faule ×{s['mnoznik']}, {s['n']} m.)"
                     if s.get("mnoznik") else " (bez historii)"))
    except Exception as e:
        sedzia_by_mid = {}
        print(f"Profil sędziów pominięty ({e})")

    # samokalibracja: zmierzone odchylenia szans per rynek (od n>=25 rozliczonych)
    try:
        bias_map = rozliczanie.market_bias()
        if bias_map:
            print("Kalibracja z rozliczeń (Δlogit): " + ", ".join(
                f"{mk} {v['global']:+.2f}" for mk, v in bias_map.items()))
    except Exception:
        bias_map = {}
    # sugestie STS uczą się na własnych rozliczeniach (osobna pula błędu)
    try:
        bias_map_sug = rozliczanie.market_bias_sugestie()
        if bias_map_sug:
            print("Kalibracja sugestii (Δlogit): " + ", ".join(
                f"{mk} {v['global']:+.2f}" for mk, v in bias_map_sug.items()))
    except Exception:
        bias_map_sug = {}
    # KOREKTA STRUMIENIA — druga warstwa uczenia, nad kalibracją rynkową.
    # Kalibracja rynkowa poprawia LICZBY, ale nie poprawia WYBORÓW: ściąga
    # szanse wszystkich kandydatów, a brama i tak bierze czub rozkładu, więc
    # opublikowany zbiór od miesiąca deklaruje ~71% i trafia 58%. Ta korekta
    # mierzy resztę błędu NA OPUBLIKOWANYCH typach i dokłada ją do każdego
    # rynku danego strumienia (patrz rozliczanie.korekta_strumienia).
    # WYPIS NIE MOŻE WYWRACAĆ UCZENIA (naprawa 2026-08-01). Od wprowadzenia
    # przedziałów (31.07) korekta bywa słownikiem, a ta linia formatowała ją
    # przez `:+.2f` — czyli SAM WYDRUK rzucał TypeError, wyjątek leciał w to
    # `except` i `korekta_strumieni` wracało puste. Skutek: druga warstwa
    # uczenia była wyłączona przez półtorej doby, mimo że liczyła się
    # poprawnie, a typy dostawały stempel, że ją zastosowano. Model wchodził
    # więc na bramę zgody z rynkiem NIESKORYGOWANY — a ta brama odrzuca
    # wszystko, co jest 12 pp nad kursem (zmierzona mediana odrzuceń: +17,5 pp).
    # Dlatego wypis jest teraz odporny na oba kształty i stoi PO ustawieniu
    # korekty, a nie przed jej użyciem.
    korekta_strumieni, _proby = {}, {}
    with rozliczanie.warstwa_uczenia("korekta_strumienia") as _w:
        # księgę czytamy RAZ i podajemy obu funkcjom — inaczej ten sam klucz
        # (ponad dwa tysiące wpisów) leciałby z Supabase dwukrotnie
        _ksiega = rozliczanie._migruj_log(supa.get_key("typy_log") or {})
        korekta_strumieni = rozliczanie.korekta_strumienia(_ksiega)
        rozliczanie.ustaw_korekte_strumienia(korekta_strumieni)
        # `n` warstwy to LICZBA ROZLICZEŃ, nie liczba strumieni z korektą —
        # inaczej strumień, który spadł pod próg, wyglądałby na „warstwa działa,
        # policzyła dwa zamiast trzech", czyli dokładnie na sukces.
        _proby = rozliczanie.proby_strumieni(_ksiega)
        _w.opisz(n=sum(p["n"] for p in _proby.values()),
                 opis=", ".join(f"{s} {p['n']}/{p['prog']}"
                                for s, p in sorted(_proby.items())))
    # OSTRZEŻENIE O PROGU: strumień pod progiem albo tuż nad nim znika
    # z korekty BEZ BŁĘDU — audyt z 05.08 złapał zawodników na 41 rozliczeniach
    # przy progu 40. Ten wypis odbiera zniknięciu efekt zaskoczenia.
    for _zdanie in rozliczanie.ostrzezenia_prob(_proby):
        print(f"[uczenie] próba strumienia — {_zdanie}")
    if korekta_strumieni:
        print("Korekta strumienia (Δlogit): " + ", ".join(
            f"{s} {betting.delta_globalna(d):+.2f}"
            + (f" (biny: {len(d.get('bins') or [])})" if isinstance(d, dict) else "")
            for s, d in korekta_strumieni.items()))
    # NA CZYM STOI TA KOREKTA — ile z jej okna to BIEŻĄCA wersja produktu.
    # Audyt zalecał twardy filtr wersji; pomiar z 12.08 pokazał, że filtr
    # skasowałby warstwę zawodnikom i drabinkom, nie zmieniając nic drużynom
    # (okno 120 już je izoluje). Zamiast filtra — licznik. Patrz
    # `rozliczanie.sklad_wersji_okna`.
    try:
        print("[uczenie] " + rozliczanie.zdanie_skladu_wersji(
            rozliczanie.sklad_wersji_okna(_ksiega)))
    except Exception as e:
        diagnostyka.cichy("cykl", "sklad_wersji_okna", e)

    # ILE PRZEDZIAŁÓW TO POMIAR, A ILE PRZYBLIŻENIE (2026-08-05).
    # Przedział bez własnej próby dostaje wartość globalną rynku i do dziś
    # wyglądał w raporcie identycznie jak zmierzony — cztery liczby w rzędzie
    # czytało się jak cztery pomiary. Ta linia mówi wprost, ile z nich to
    # wiedza. Sam licznik, żadnej zmiany w rachunku.
    try:
        print("[uczenie] " + rozliczanie.zdanie_pokrycia(
            rozliczanie.pokrycie_przedzialow(bias_map, korekta_strumieni)))
    except Exception as e:
        diagnostyka.cichy("cykl", "pokrycie_przedzialow", e)

    # SZANSA POKAZYWANA — ostatnia warstwa, wyłącznie na wyjściu.
    # Kalibracja i korekta strumienia działają PRZED bramą publikacji, więc
    # zjada je efekt selekcji: opublikowany zbiór i tak deklaruje ~71%, a
    # trafia 58%. Ta delta nie wraca do modelu — poprawia liczbę, którą user
    # czyta na stronie, i nic poza nią (patrz rozliczanie.szansa_pokazywana).
    korekta_pokazywana = {}
    with rozliczanie.warstwa_uczenia("szansa_pokazywana") as _w:
        # korektę przed bramą PODAJEMY jawnie — inaczej funkcja policzyłaby ją
        # sobie drugi raz z księgi i mogłaby odjąć inną liczbę niż ta, z którą
        # typy faktycznie wychodzą w tym cyklu
        korekta_pokazywana = rozliczanie.szansa_pokazywana(
            korekta_przed_brama=korekta_strumieni
        )
        _w.opisz(n=len(korekta_pokazywana),
                 opis=", ".join(sorted(korekta_pokazywana)))
        if korekta_pokazywana:
            print("Szansa pokazywana (Δlogit): " + ", ".join(
                f"{s} {d:+.2f}" for s, d in korekta_pokazywana.items()))

    # TWARDY STOP NA WARSTWACH KRYTYCZNYCH (2026-08-05).
    #
    # Obie warstwy wyżej decydują o liczbie, którą user czyta przy typie.
    # Publikacja bez nich jest GORSZA niż brak przeliczenia: strona pokazałaby
    # szanse, o których wiemy, że są zawyżone, a brama zgody z rynkiem
    # odrzuciłaby prawie wszystko (incydent 01.08 — 26 typów zamiast 99).
    # Dry-run leci dalej, żeby dało się diagnozować lokalnie bez sekretów.
    _padniete = rozliczanie.krytyczne_padniete()
    if _padniete and not _dry_run():
        raise RuntimeError(
            "krytyczne warstwy uczenia padły: " + ", ".join(_padniete)
            + " — cykl przerwany, żeby nie opublikować typów z niepoprawioną "
              "szansą (patrz rozliczanie.WARSTWY_KRYTYCZNE)"
        )

    def _urealnij_do_pokazania(b: dict) -> dict:
        """Kopia typu z szansą taką, jaka wychodzi z rozliczeń — do payloadu.

        Przeliczamy TAKŻE liczby pochodne (uczciwy kurs, przewaga, wartość),
        bo inaczej karta mówiłaby „szansa 58%, kurs 1,70, wartość +21%",
        czyli trzy liczby, z których dwie zaprzeczają trzeciej.
        """
        d = korekta_pokazywana.get(rozliczanie._strumien(b), 0.0)
        if not d or b.get("sugestia") or not b.get("p_model"):
            return b
        p = rozliczanie.urealnij_p(float(b["p_model"]), d)
        out = {**b, "p_model": round(p, 4), "p_urealnione": True,
               "fair_kurs": round(1.0 / max(p, 1e-6), 3)}
        # ...i dopisz do stempla liczbę, którą realnie zobaczy klient. Bez tego
        # rachunek kończył się na `p_over_final`, a karta pokazywała co innego
        # — patrz nota przy `p_pokazane` w betting.stempel_rachunku.
        if isinstance(b.get("rachunek"), dict) and b["rachunek"]:
            out["rachunek"] = {**b["rachunek"],
                               "p_pokazane": round(p, 4),
                               "kal_pokazywana": round(float(d), 4)}
        if b.get("p_rynku") is not None:
            out["edge_pp"] = round((p - float(b["p_rynku"])) * 100.0, 2)
        if b.get("kurs"):
            out["ev_pct"] = round(betting.ev_brutto_pct(p, b["kurs"]), 2)
            out["ev_netto"] = round(
                betting.ev_pct(p, b["kurs"], b.get("tryb_podatku")), 2
            )
        return out

    # ŚCIĄGNIĘCIE LICZBY NA KARCIE DO CENY — ostatni krok, już za bramami.
    # Waga liczona z rozliczeń raz na cykl; brak próby = karta bez zmian.
    _waga_karty = None
    _marza_karty = rozliczanie.MARZA_SCIAGANIA_DOMYSLNA
    with rozliczanie.warstwa_uczenia("sciaganie_karty") as _w:
        # NAJPIERW CENA, POTEM WAGA. Do jakiej ceny ściągamy, wynika z
        # rozliczeń (`marza_sciagania`) — dopóki brała się ze stałej 7%,
        # karta ściągała się do jednej ceny, a wartość liczyła wobec innej
        # i wychodziła ujemna przy KAŻDYM typie.
        _marza_karty = rozliczanie.marza_sciagania(_ksiega)
        _waga_karty = rozliczanie.waga_sciagania(_ksiega, _marza_karty)
        _w.opisz(n=(1 if _waga_karty else 0),
                 opis=(f"w={_waga_karty:.2f} (nasza liczba) / "
                       f"{1 - _waga_karty:.2f} (cena minus {_marza_karty:.1%})"
                       if _waga_karty else "za mała próba — karta bez zmian"))
    if _waga_karty:
        print(f"Szansa na karcie ściągana do ceny: w={_waga_karty:.2f} "
              f"naszej liczby, reszta z kursu po zdjęciu zmierzonej marży "
              f"{_marza_karty:.1%} (domyślna "
              f"{rozliczanie.MARZA_SCIAGANIA_DOMYSLNA:.0%}) — poprawia "
              f"kalibrację o ~10% (Brier), NIE poprawia ROI; selekcja bez zmian")

    def _sciagnij_karte_do_ceny(u: dict) -> dict:
        """Liczba POKAZYWANA klientowi, ściągnięta do ceny. Tylko karta.

        Przeliczamy też liczby pochodne, żeby karta nie mówiła „szansa 57%,
        kurs 1,70, wartość +21%" — trzech liczb, z których dwie zaprzeczają
        trzeciej, pilnujemy w całym produkcie.
        """
        if (not _waga_karty or u.get("sugestia") or not u.get("kurs")
                or not u.get("p_model")):
            return u
        p = rozliczanie.sciagnij_do_ceny(float(u["p_model"]), float(u["kurs"]),
                                         _waga_karty, _marza_karty)
        out = {**u, "p_model": round(p, 4), "p_sciagniete": True,
               "fair_kurs": round(1.0 / max(p, 1e-6), 3)}
        if u.get("p_rynku") is not None:
            out["edge_pp"] = round((p - float(u["p_rynku"])) * 100.0, 2)
        out["ev_pct"] = round(betting.ev_brutto_pct(p, u["kurs"]), 2)
        out["ev_netto"] = round(
            betting.ev_pct(p, u["kurs"], u.get("tryb_podatku")), 2
        )
        if isinstance(u.get("rachunek"), dict) and u["rachunek"]:
            # marża idzie do stempla razem z wagą — bez niej rachunku karty
            # nie da się odtworzyć, bo `p_pokazane` zależy od OBU liczb
            out["rachunek"] = {**u["rachunek"], "p_pokazane": round(p, 4),
                               "waga_sciagania": round(float(_waga_karty), 2),
                               "marza_sciagania": round(float(_marza_karty), 4)}
        return out

    # Korekta strumienia drużynowego NIE jest już stosowana po wyborze strony
    # zakładu — wchodzi do kalibracji „powyżej" razem z biasem rynku
    # (patrz pętla linii drużynowych i pomiar z 2026-07-30).

    def _dodaj_delte(v, d):
        """Kalibracja rynku + delta logitowa, w jednej korekcie.

        Rynek BEZ własnej kalibracji (za mało rozliczeń) też dostaje deltę —
        inaczej nowy rynek startowałby z pełnym przeszacowaniem strumienia.
        Stary format mnożnikowy zostawiamy nietknięty: mieszanie mnożnika
        z deltą logitową dałoby liczbę, której nikt później nie odtworzy.
        """
        if not d:
            return v if v is not None else 1.0
        # KOREKTA STRUMIENIA BYWA BINOWANA (2026-07-31). Oba zestawy binów
        # chodzą po TYCH SAMYCH przedziałach `p_over` (rozliczanie.
        # BIAS_PRZEDZIALY), więc sumują się bin po binie. Gdyby kiedyś
        # przestały być te same, `_delta_dla` niżej i tak dobierze wartość
        # po zakresie, a nie po pozycji na liście.
        d_glob = rozliczanie.betting.delta_globalna(d)

        def _delta_dla(lo, hi):
            return rozliczanie.betting.delta_dla_p(d, (lo + hi) / 2.0)

        if isinstance(v, dict) and v.get("logit"):
            biny = [[lo, hi, round(float(b) + _delta_dla(lo, hi), 3)]
                    for lo, hi, b in (v.get("bins") or [])]
            # ETYKIETY PO ZSUMOWANIU. Bin jest sumą dwóch korekt, więc niesie
            # pomiar, jeśli miała go KTÓRAKOLWIEK z nich — inaczej przedział
            # zmierzony przez strumień znikałby pod „globalna" z rynku.
            zr_rynku = list(v.get("zrodla") or [])
            zr_strum = list(d.get("zrodla") or []) if isinstance(d, dict) else []
            zrodla = [
                rozliczanie.ZRODLO_WLASNA
                if rozliczanie.ZRODLO_WLASNA in (
                    zr_rynku[i:i + 1] + zr_strum[i:i + 1])
                else (zr_rynku[i] if i < len(zr_rynku)
                      else rozliczanie.ZRODLO_GLOBALNA)
                for i in range(len(biny))
            ]
            return {
                **v,
                "global": round(float(v.get("global", 0.0)) + d_glob, 3),
                "bins": biny,
                **({"zrodla": zrodla} if zrodla else {}),
            }
        if v is None or v == 1.0:
            # rynek bez własnej kalibracji dostaje samą korektę strumienia —
            # razem z jej przedziałami, jeśli je ma
            if isinstance(d, dict):
                # etykiety źródeł jadą razem z binami — inaczej rynek bez
                # własnej kalibracji wyglądałby w liczniku pokrycia na wpis
                # sprzed wprowadzenia etykiet (patrz rozliczanie.ZRODLO_WLASNA)
                return {"logit": True, "global": round(d_glob, 3),
                        "bins": [[lo, hi, round(float(b), 3)]
                                 for lo, hi, b in (d.get("bins") or [])],
                        "zrodla": list(d.get("zrodla") or [])}
            return {"logit": True, "global": round(d_glob, 3), "bins": []}
        return v

    def _bias_z_korekta(mk: str, strumien: str):
        """Kalibracja rynku danego kodu + korekta jego strumienia."""
        return _dodaj_delte(bias_map.get(mk),
                            korekta_strumieni.get(strumien, 0.0))

    # BRAMA PUBLIKACJI: rynki tracące pieniądze w oknie ostatnich rozliczeń
    # wypadają z publikacji (pewniaki, pula kuponów), ale dalej są scorowane
    # i logowane (poza_publikacja) — kalibracja mierzy je nadal i rynek wraca sam
    kwarantanna_rynkow = {}
    with rozliczanie.warstwa_uczenia("kwarantanna_rynkow") as _w:
        kwarantanna_rynkow = rozliczanie.kwarantanna()
        _w.opisz(n=len(kwarantanna_rynkow),
                 opis=", ".join(sorted(kwarantanna_rynkow)) or "nic wstrzymane")
        if kwarantanna_rynkow:
            print("Kwarantanna rynków: " + ", ".join(
                f"{mk} (ROI {v['roi']:+.0%}, hit {v['hit']:.0%} "
                f"vs p {v['sr_p']:.0%}, n={v['n']})"
                for mk, v in kwarantanna_rynkow.items()))
    # TA SAMA BRAMA, ale po POWODZIE wejścia typu na listę, nie po rynku.
    # Rozliczenia pokazują, że model zarabia, gdy typuje nudno, a traci na
    # każdej ścieżce "znaleźliśmy coś więcej niż rynek" (ambitniejsza linia,
    # profil rywala, analogia stylu, rzekomy błąd tradera). Bez tej bramy
    # wystarczyło przekleić stratny typ na inny rynek, żeby przeszedł.
    kwarantanna_kategorii = {}
    with rozliczanie.warstwa_uczenia("kwarantanna_kategorii") as _w:
        kwarantanna_kategorii = rozliczanie.kategorie_kwarantanna()
        _w.opisz(n=len(kwarantanna_kategorii),
                 opis=", ".join(sorted(kwarantanna_kategorii)) or "nic wstrzymane")
        if kwarantanna_kategorii:
            print("Kwarantanna kategorii: " + ", ".join(
                f"{v['nazwa']} (ROI {v['roi']:+.0%}, hit {v['hit']:.0%} "
                f"vs p {v['sr_p']:.0%}, n={v['n']})"
                for v in kwarantanna_kategorii.values()))
    # TA SAMA BRAMA, ale po STRONIE LINII. Kwarantanna rynkowa miesza „powyżej"
    # z „poniżej" w jeden licznik i wychodzi jej średnia, a pomiar 30.07 mówi,
    # że to dwa różne światy: na tych samych rynkach „powyżej" ma ROI od −12%
    # do −32%, a „poniżej" nie wypada nigdzie. Bez tego wymiaru rynek albo
    # wypadał cały (razem z dobrą stroną), albo zostawał cały (razem ze złą).
    kwarantanna_stron = {}
    with rozliczanie.warstwa_uczenia("kwarantanna_stron") as _w:
        kwarantanna_stron = rozliczanie.strony_kwarantanna()
        _w.opisz(n=len(kwarantanna_stron),
                 opis=", ".join(sorted(kwarantanna_stron)) or "nic wstrzymane")
        if kwarantanna_stron:
            print("Kwarantanna strony linii: " + ", ".join(
                f"{v['rynek']} {v['strona']} (ROI {v['roi']:+.0%}, "
                f"hit {v['hit']:.0%} vs p {v['sr_p']:.0%}, n={v['n']})"
                for v in kwarantanna_stron.values()))
    # PIERWSZEŃSTWO DROBNIEJSZEGO POMIARU (2026-08-04). Strona z własną próbą
    # odpowiada za siebie — brama rynkowa jej nie dotyczy. Bez tego licznik
    # rynku (średnia obu stron) zamykał `team_corners` w komplecie, choć jego
    # strona „powyżej" zarabia +9,4% na 34 rozliczeniach i bije cenę
    # bukmachera. Szczegóły i liczby: `rozliczanie.strony_ocenione`.
    try:
        strony_z_werdyktem = rozliczanie.strony_ocenione()
        # LICZNIK PRZY BRAMIE, NIE PO ZGŁOSZENIU. Bez tej linii ułaskawienie
        # jest niewidoczne: w logu cyklu wyglądałoby to jak kwarantanna, która
        # nagle przestała działać na część typów.
        _darowane = sorted(
            k for k in strony_z_werdyktem
            if k.split(":")[0] in kwarantanna_rynkow and k not in kwarantanna_stron
        )
        if _darowane:
            print("Rynek w kwarantannie NIE zdejmuje stron z własnym "
                  f"werdyktem: {', '.join(_darowane)}")
    except Exception as e:
        strony_z_werdyktem = set()
        print(f"Werdykty stron pominięte ({e})")

    # OBIE BRAMY STOJĄ TU, PRZED WSZYSTKIMI ŚCIEŻKAMI PUBLIKACJI (2026-08-04).
    # Wcześniej były definiowane dopiero przy układaniu listy pewniaków, więc
    # sumy meczowe i „kto więcej" — które dopisują się do `value_bets` WPROST,
    # z pominięciem tamtej pętli — nie widziały ich w ogóle. Dziura była
    # niewidoczna, dopóki okno zgody stało na +12 pp i zdejmowało te typy
    # wcześniej; po rozszerzeniu okna na +16 pp od razu weszły na listę trzy
    # świeże „rożne w meczu poniżej" z rynku, który stoi w kwarantannie
    # (ROI −24%). To ta sama klasa błędu co bramy stawiane przy narodzinach
    # typu zamiast przy dumpie ([[wznowione-omijaly-bramy]]).
    _powod_kwarantanny = rozliczanie.brama_kwarantanny(
        kwarantanna_rynkow, kwarantanna_stron, strony_z_werdyktem)

    # ⚑ CZY KWARANTANNA ZDEJMUJE TYP Z LISTY — od 14.08 NIE.
    #
    # Decyzja właściciela, poparta pomiarem księgi (epoka ligowa, rozliczone,
    # ROI brutto):
    #
    #     pokazane klientowi         n=419  luka -10,8 pp  ROI  -3,5%
    #     zdjęte: wstrzymany rynek   n= 34  luka  -7,3 pp  ROI +10,3%
    #     zdjęte: wstrzymana strona  n=190  luka -16,3 pp  ROI  -1,3%
    #
    # Kwarantanna wyrzucała materiał, który wypada NIE GORZEJ niż to, co
    # zostawało na stronie. Mechanizm jest zrozumiały: brama patrzy na okno
    # 40 rozliczeń, więc wstrzymuje segment po serii pecha — czyli dokładnie
    # wtedy, gdy ten i tak wraca do średniej. Zasada właściciela z 05.08
    # („nic nie blokujemy, model ma się nauczyć wszystkiego") dostaje tu
    # pokrycie w kodzie.
    #
    # Co ZOSTAJE: `_powod_kwarantanny` wyżej dalej liczy to samo i dalej daje
    # typowi etykietę `rynek_wstrzymany` przy dumpie (typ schodzi na koniec
    # kolejności „polecane" i mówi o tym na karcie). Brama zostaje też w PULI
    # KUPONÓW (`_leg_dopuszczalny`) — tam błąd jednego lega mnoży się przez
    # cały kupon, więc to osobna decyzja i osobny pomiar.
    _kwarantanna_zdejmuje = rozliczanie.brama_kwarantanny(
        kwarantanna_rynkow, kwarantanna_stron, strony_z_werdyktem,
        blokuje=KWARANTANNA_ZDEJMUJE_Z_LISTY)

    def _strona_wstrzymana(b: dict) -> bool:
        """Czy ta STRONA tego rynku stoi w kwarantannie (patrz 30.07)."""
        return f"{b.get('rynek_kod')}:{b.get('strona')}" in kwarantanna_stron

    def _rynek_wstrzymany(b: dict) -> bool:
        """Czy typ zdejmuje BRAMA RYNKOWA — czyli średnia z obu stron linii."""
        return _powod_kwarantanny(b) == "kwarantanna_rynku"

    ev_by_id = {e["id"]: e for e in events}
    sb_cache: dict[int, dict] = {}
    tempo.reset_fallback_stats()
    # licznik cichych błędów zerujemy razem z resztą liczników przebiegu —
    # patrz `footstats/diagnostyka.py` (79 miejsc bez logu, przegląd 04.08)
    diagnostyka.reset()
    tempo_cache: dict[int, dict | None] = {}  # mid -> tempo z kursów 1X2/goli
    # pełna siatka kursów Superbet (over) do widoku TOP POKRYCIA na stronie
    # meczu: mecz_id -> player_id -> rynek -> "linia" -> kurs. Zbierana z tej
    # samej siatki co scoring (merged), tylko zapisywana na dysk (JSON).
    odds_grid: dict[int, dict[int, dict[str, dict[str, float]]]] = {}
    # ...i kto daje tę cenę, gdy NIE jest to Superbet: mecz -> gracz -> rynek ->
    # "linia" -> nazwa bukmachera. Tylko wyjątki (patrz nota przy zapisie).
    zrodla_grid: dict[int, dict[int, dict[str, dict[str, str]]]] = {}
    # zawodnicy przypisani do meczu (mid -> pid -> trend) — z tego wychodzi
    # dopelnij_oferte_zawodnicza(), która dokłada rynki z oferty bukmachera
    gracze_meczu: dict[int, dict[int, object]] = {}

    def _forma_z_trendu(tr, mk: str) -> dict:
        """Forma jednego rynku do players.json (UI: sparkline, TOP POKRYCIA).

        statshub daje ~40 meczów historii — trzymamy 20, żeby na stronie meczu
        dało się PREFEROWAĆ ostatnie 5 startów w KADRZE (a nie klubowe) i pokazać
        datę ostatniego meczu (świeżość). Model i tak liczy z pełnego tr.counts.
        """
        nt_zbior = nt_ts.get(tr.team_name, set())
        N = 20
        return {
            "ostatnie": [int(c) for c in tr.counts[:N]],
            "minuty": [int(m) for m in tr.minutes[:N]],
            "rywale": [str(o) for o in tr.game_opponents[:N]],
            "kadra": [
                any(abs(ts_g - g) < 36 * 3600 for g in nt_zbior)
                for ts_g in tr.timestamps[:N]
            ],
            "ts": [int(t) for t in tr.timestamps[:N]],
            "srednia90": round(
                float(np.sum(tr.counts) / max(np.sum(tr.minutes), 1) * 90.0), 2
            ),
        }

    # przewidywane XI z Rotowire (drugie źródło, działa z chmury)
    try:
        roto = rotowire.fetch_predicted_lineups()
        print(f"Rotowire: przewidywane składy {len(roto)} drużyn")
    except Exception as e:
        roto = {}
        print(f"Rotowire niedostępny: {e}")

    # składy: potwierdzone (event.lineupConfirmed) i przewidywane (czy statshub
    # w ogóle wystawił przewidywany skład dla danego meczu)
    lineup_confirmed = {e["id"]: bool(e.get("lineupConfirmed")) for e in events}
    predicted_available: dict[int, bool] = {}
    for t in trends:
        if t.event_id:
            predicted_available[t.event_id] = (
                predicted_available.get(t.event_id, False) or t.in_predicted_lineup
            )
    # pełne XI (sklady_xi) wzmacniają oba sygnały: znany skład = przewidywany
    # dostępny; potwierdzenie z team-lineup/Sofascore = jak lineupConfirmed
    for mid_x, v in xi_pelne.items():
        predicted_available[mid_x] = True
        if v["confirmed"]:
            lineup_confirmed[mid_x] = True
    n_conf = sum(lineup_confirmed.values())
    if n_conf:
        print(f"Składy ogłoszone: {n_conf} z {len(events)} meczów")

    # okno "rynek nie zdążył": zapamiętujemy PIERWSZY moment potwierdzenia
    # składów per mecz — typy z meczu potwierdzonego <45 min temu dostają
    # bonus w rankingu (kursy często jeszcze nie zareagowały na ogłoszone XI)
    swieze_mids: set[int] = set()
    conf_mids: set[int] = set()
    try:
        potw = supa.get_key("sklady_potwierdzone_ts") or {}
        now_p = int(time.time())
        for e in events:
            mid_e = e["id"]
            conf_e = lineup_confirmed.get(mid_e, False) or (
                rotowire.is_confirmed(roto, team_name.get(e.get("homeTeamId"), ""))
                and rotowire.is_confirmed(roto, team_name.get(e.get("awayTeamId"), ""))
            )
            if conf_e:
                conf_mids.add(mid_e)
            if conf_e and str(mid_e) not in potw:
                potw[str(mid_e)] = now_p
        potw = {k: v for k, v in potw.items() if now_p - int(v) < 3 * 86400}
        if not _dry_run():
            supa.put_key("sklady_potwierdzone_ts", potw)
        swieze_mids = {
            int(k) for k, v in potw.items() if now_p - int(v) < 45 * 60
        }
        if swieze_mids:
            print(f"Świeżo potwierdzone składy (okno na stare linie): "
                  f"{len(swieze_mids)} meczów")
    except Exception:
        swieze_mids = set()

    # zawodnicy POZA ogłoszonym składem (twardy sygnał z statshub lub Rotowire)
    # — unieważniają zamrożone kupony z ich legami (patrz rozliczanie).
    # in_predicted_lineup jest wiarygodne TYLKO dla (mecz, zawodnik) z żywego
    # feedu statshub (xi_zywy) — trendy z banku/365 spoza niego mają False,
    # które znaczy "brak sygnału", nie "poza składem".
    niedostepni: set[int] = set()
    for t in trends:
        if not t.player_id or not t.event_id:
            continue
        rp = rotowire.predicted_status(roto, t.team_name, t.player_name)
        if (
            lineup_confirmed.get(t.event_id)
            and (t.event_id, t.player_id) in xi_zywy
            and not t.in_predicted_lineup
        ) or (rotowire.is_confirmed(roto, t.team_name) and rp is False):
            niedostepni.add(t.player_id)
    if niedostepni:
        print(f"Poza ogłoszonymi składami: {len(niedostepni)} zawodników")

    # --- POZA SKŁADEM: twarda brama publikacji (zgłoszenie 2026-07-27) ---
    # `niedostepni` wyżej unieważnia ZAMROŻONE kupony, ale nigdy nie blokował
    # tworzenia NOWYCH typów i kart. Efekt: zawodnik, o którym sami wiemy, że
    # nie ma go w jedenastce, i tak wchodził do Pewniaków i do Drabinek —
    # wystarczyło, że jego HISTORIA wyglądała dobrze (Fabio Fehr, FC Thun).
    #
    # Dlaczego to nie to samo co `players.json.xi`: tam False znaczy dwie
    # zupełnie różne rzeczy — „wiemy, że go nie ma" i „nie znamy jeszcze
    # składu". Karać wolno tylko za pierwsze, więc liczymy je osobno:
    # skład drużyny musi być ZNANY (pełne XI z statshub/Sofascore albo
    # potwierdzenie Rotowire), a zawodnika w nim nie ma.
    poza_skladem: set[tuple[int, int]] = set()
    for mid_x, v in xi_pelne.items():
        for tid_x, xi_set in v["xi_by_team"].items():
            for t in trends:
                if (
                    t.event_id == mid_x and t.team_id == tid_x
                    and t.player_id and t.player_id not in xi_set
                ):
                    poza_skladem.add((mid_x, t.player_id))
    for t in trends:
        if not (t.player_id and t.event_id):
            continue
        if (
            rotowire.is_confirmed(roto, t.team_name)
            and rotowire.predicted_status(roto, t.team_name, t.player_name)
            is False
        ):
            poza_skladem.add((t.event_id, t.player_id))
    # tri-state dla UI: True = w składzie, False = poza składem, None = nie
    # wiemy. Bez tego karta nie umie odróżnić „ławka" od „skład nieznany".
    xi_znany: dict[tuple[int, int], bool] = {}
    for mid_x, v in xi_pelne.items():
        for tid_x, xi_set in v["xi_by_team"].items():
            for pid_x in xi_set:
                xi_znany[(mid_x, pid_x)] = True
    for k_ps in poza_skladem:
        xi_znany.setdefault(k_ps, False)
    if poza_skladem:
        print(f"Poza znanym składem: {len(poza_skladem)} par (mecz, zawodnik) "
              "— typy i karty tych zawodników nie powstają")

    # matchup-lite: profil per90 zawodników każdej drużyny (pod strony boiska)
    opp_players_by_team: dict[tuple[int, int], list[matchup_lite.OppPlayer]] = {}
    for t in trends:
        tot_min = sum(t.minutes)
        if not t.event_id or not t.team_id or tot_min < 90:
            continue
        opp_players_by_team.setdefault((t.event_id, t.team_id), []).append(
            matchup_lite.OppPlayer(
                market_code=t.market_code,
                positions=tuple(t.game_positions[:6]),
                per90=float(sum(t.counts) / tot_min * 90.0),
            )
        )

    value_bets, matches_out, players_out = [], {}, {}

    def _zapewnij_mecz(mid: int) -> dict:
        """Pełny rekord meczu w matches_out — także dla meczów, które mają
        WYŁĄCZNIE typy drużynowe lub sugestie (kwalifikacje pucharów: propsów
        zawodniczych brak, gole/rożne drużynowe są). Dotąd setdefault tworzył
        tam kadłubek {"okazje": [...]} bez id/ligi/nazw — web nie umiał
        przypisać rozgrywek i pokazywał "Inne rozgrywki" zamiast np. Ligi
        Konferencji, a tylkoNadchodzace wycinało mecz z /mecze (kickoff=None).
        """
        rec = matches_out.get(mid)
        if rec and rec.get("id"):
            return rec
        ev = ev_by_id.get(mid) or {}
        sed = sedzia_by_mid.get(mid) or {}
        et = (tryb.liga_by_mid.get(mid) if tryb else None) or (
            {"liga": "", "sezon": tryb.sezon, "kolejka": ""} if tryb
            else {"liga": "MŚ", "sezon": "2026", "kolejka": ""}
        )
        matches_out[mid] = {
            "id": mid, "liga": et["liga"], "sezon": et["sezon"],
            "kolejka": et["kolejka"],
            "kickoff_ts": ev.get("timeStartTimestamp") or int(time.time()),
            "gospodarz": team_name.get(ev.get("homeTeamId"), ""),
            "gosc": team_name.get(ev.get("awayTeamId"), ""),
            "sedzia": sed.get("sedzia"),
            "sedzia_mnoznik_fauli": round(context.shrink_factor(
                float(sed.get("mnoznik") or 1.0), sed.get("n", 0), 8.0
            ), 2),
            "okazje": (rec or {}).get("okazje", []),
            "sklady_ogloszone": lineup_confirmed.get(mid, False),
        }
        return matches_out[mid]

    vb_id = 0
    seen_player_market = set()  # (player_id, market) — statshub bywa zdublowany
    real_split = {}  # (player_id, mk) -> pełny scoring niecelnych/zablokowanych z 365
    legi_pool = []   # wszystkie kwotowane linie z wysoką szansą — pula pod kupony pewniaków
    # typy zdjęte z publikacji (kwarantanna / stare dane / limit meczu) —
    # rozliczają się i uczą kalibrację w tle; zasilane w KAŻDYM kanale
    # emisji: okazje z kursem, sugestie STS, pewniaki
    typy_poza_publikacja: list[dict] = []
    pstyle_cache: dict[int, object] = {}  # PlayerStyle per zawodnik (styl.py)

    # REJESTR ODRZUCEŃ: dla każdej pary (mecz, zawodnik, rynek), która weszła
    # do scoringu, a NIE dała typu — jeden wpis z powodem. Odpowiada na pytanie
    # "czemu nie ma typu na X" na stronie meczu; wcześniej odrzucenia były
    # cichymi `continue` i wymagały debugowania kodu.
    odrzucenia: dict[tuple, dict] = {}

    def _odrzuc(mid_o, tr_o, powod: str, szczegol: str = "") -> None:
        odrzucenia[(mid_o, tr_o.player_id, tr_o.market_code)] = {
            "mecz_id": mid_o, "podmiot": tr_o.player_name,
            "druzyna": tr_o.team_name,
            "rynek_kod": tr_o.market_code,
            "rynek": MARKET_NAMES_PL.get(tr_o.market_code, tr_o.market_code),
            "powod": powod, "szczegol": szczegol,
        }

    def _odrzuc_druzyne(mid_o, tt_o, powod: str, szczegol: str = "") -> None:
        """To samo dla rynków DRUŻYNOWYCH.

        Dotąd miały wyłącznie zbiorczy licznik drukowany na stdout, więc gdy
        mecz przestawał dawać typy, powód znikał razem z logiem przebiegu —
        a mecz bez ani jednego typu nie trafia nawet do `matches`, więc w apce
        nie zostawał po nim ślad. Zmierzone 2026-07-26 na Wiśle Kraków–GKS:
        o 13:31 trzy typy, o 14:05 zero, kursy nietknięte, powód nie do
        odtworzenia. Ujemne id odróżnia drużynę od zawodnika w kluczu.
        """
        odrzucenia[(mid_o, -abs(int(tt_o.team_id or 0)), tt_o.market_code)] = {
            "mecz_id": mid_o, "podmiot": tt_o.team_name,
            "druzyna": tt_o.team_name,
            "rynek_kod": tt_o.market_code,
            "rynek": MARKET_NAMES_PL.get(tt_o.market_code, tt_o.market_code),
            "powod": powod, "szczegol": szczegol,
            "podmiot_typ": "druzyna",
        }

    # POMIAR PROGÓW: typy odrzucone TUŻ przy progu (betting.NEAR_*) — trafiają
    # do typy_log jako `odrzucony=True` (rozliczą się w tle, POZA kalibracją,
    # skutecznością i UI). Diagnostyka porówna ich hit-rate z przepuszczonymi.
    odrzucone_pomiar: list[dict] = []
    ODRZUCONE_POMIAR_MAX = 80   # bezpiecznik objętości logu per cykl
    # OSOBNY budżet dla rynków DRUŻYNOWYCH (2026-07-27). Pętla zawodnicza idzie
    # pierwsza i przy ruchliwym dniu wypełniłaby wspólny limit do zera, a wtedy
    # pomiar bramy kurs×szansa — ten, po który go w ogóle dokładamy — nie
    # zebrałby ani jednej próbki. Dwa liczniki, żeby jedno nie głodziło drugiego.
    ODRZUCONE_POMIAR_DRUZYN_MAX = 60

    # PEŁNE POKRYCIE p_model per (zawodnik, rynek, linia) — dla scannera value
    # betów STS. Model „widzi" KAŻDĄ kwotowaną linię, nie tylko te, które weszły
    # do puli/okazji, więc STS może łączyć swój kurs z p_model dużo częściej.
    # Klucz sts_model jest backendowy (apka go nie czyta).
    model_pokrycie: list[dict] = []

    # --- OFERTA BUKMACHERA JAKO PUNKT WYJŚCIA DLA SILNIKA (2026-08-08) ---
    #
    # Do dziś historia dociągana pod ofertę Superbetu szła WYŁĄCZNIE do
    # `players_out["forma"]` i do siatki kursów, czyli zasilała tabelę pokryć
    # i drabinki, a typu z niej nie powstawało nigdy. Skutek zmierzony 07.08:
    # z 46 typów zawodniczych z trzech dni **41 to zwykłe strzały**, a odbiorów,
    # celnych, „zza pola" i spalonych nie było ANI JEDNEGO — mimo że kursy
    # i historia leżały w ręku ([[strumien-zawodniczy-martwy]]).
    #
    # Powód był czysto techniczny: silnik iteruje po `trends`, a dociągnięte
    # rynki lądowały w innym worku. Dlatego dopełnienie musi wykonać się TU —
    # przed pętlą scoringu — żeby jego trendy przeszły przez te same bramy,
    # kalibrację i kwarantanny co reszta. Wymaga to wcześniejszego pobrania
    # oferty (`sb_cache`), która dotąd powstawała w trakcie pętli.
    # znacznik czasu tego przebiegu — wiek ceny liczymy od niego, a nie od
    # `time.time()` w środku pętli, żeby wszystkie typy jednego cyklu miały
    # spójny stempel (patrz `kurs_ts` przy okazji)
    ts_cyklu = int(time.time())
    ev_by_para = {
        frozenset({e.get("homeTeamId"), e.get("awayTeamId")}): e
        for e in events
    }

    def _mecz_trendu(tr_x):
        """Mecz zawodnika po jego drużynie i przeciwniku (indeks zamiast
        skanowania listy `events` dla każdego trendu z osobna)."""
        return ev_by_para.get(frozenset({tr_x.team_id, tr_x.opponent_id}))

    def _oferta_meczu(mid_o: int, home_o: str, away_o: str, ts_o: int) -> dict:
        """Kursy Superbetu dla meczu, z cache i pomiarem tempa.

        Wyjęte z pętli scoringu bez zmiany zachowania: to ten sam kod, który
        wcześniej stał przy pierwszym trendzie danego meczu.
        """
        sb_o = sb_cache.get(mid_o)
        if sb_o is not None or not sb_events:
            return sb_o or {"players": {}, "teams": {}}
        if tryb:
            sb_ev = tryb.sb_ev_by_mid.get(mid_o)
        else:
            sb_ev = superbet.match_superbet_event(
                sb_events, home_o, away_o, ts_o
            )
        if sb_ev:
            parts = [p.strip() for p in (sb_ev.get("matchName") or "·").split("·")]
            try:
                sb_o = superbet.fetch_stat_odds(
                    sb_ev["eventId"], parts[0], parts[1]
                )
            except Exception:
                sb_o = {"players": {}, "teams": {}}
        else:
            sb_o = {"players": {}, "teams": {}}
        sb_cache[mid_o] = sb_o
        tempo_m = tempo.tempo_from_match_odds(sb_o.get("match"))
        tempo_cache[mid_o] = tempo_m
        return sb_o

    _kolejnosc_meczow: dict[int, int] = {}
    for _tr in trends:
        _ev = _mecz_trendu(_tr)
        if _ev is None:
            continue
        _mid = _ev["id"]
        _ts = _ev.get("timeStartTimestamp") or int(time.time())
        _kolejnosc_meczow[_mid] = _ts
        # zawodnicy meczu: pierwszy trend danego gracza niesie kontekst
        # (rywal, dom/wyjazd) — z niego korzysta `_trend_z_kontekstem_meczu`
        gracze_meczu.setdefault(_mid, {}).setdefault(_tr.player_id, _tr)
        # rekord zawodnika z formą rynków, które przyszły z feedu propsów —
        # `dopelnij_oferte_zawodnicza` dokłada do niego BRAKUJĄCE rynki oferty
        rec_p = players_out.setdefault(_tr.player_id, {
            "id": _tr.player_id, "nazwa": _tr.player_name,
            "pozycja": _tr.position or "?", "druzyna": _tr.team_name,
            "minuty_lacznie": int(sum(_tr.minutes)), "forma": {},
            "xi": bool(_tr.in_predicted_lineup),
        })
        if _tr.in_predicted_lineup:
            rec_p["xi"] = True
        rec_p["forma"].setdefault(_tr.market_code, _forma_z_trendu(_tr, _tr.market_code))
    for _mid, _ts in sorted(_kolejnosc_meczow.items(), key=lambda kv: kv[1]):
        _ev = ev_by_id.get(_mid) or {}
        _oferta_meczu(
            _mid,
            team_name.get(_ev.get("homeTeamId"), ""),
            team_name.get(_ev.get("awayTeamId"), ""),
            _ts,
        )
    # --- DRUGI BUKMACHER JAKO ŹRÓDŁO OFERT (2026-08-08, decyzja usera) ---
    #
    # Do dziś Betclic dawał WYŁĄCZNIE drugą cenę na kartach drabinek. A oferty
    # obu bukmacherów nie pokrywają się ani trochę: zmierzone 08.08 na żywej
    # siatce Superbetu — „zza pola" ma 2 zawodników, odbiory 73, przy 1756 na
    # zwykłych strzałach. Tymczasem wzorcowe typy, które user wkleił (Igbekeme,
    # Hellebrand, Lokilo, Yamal — wszystko „zza pola"; Paredes i Anderson —
    # odbiory), stoją właśnie na tych rynkach i wszystkie u Betclica.
    #
    # ZASADA (user): model ocenia, czy zdarzenie wejdzie; bukmacher to miejsce,
    # gdzie stawiamy, więc wybieramy tego, który płaci więcej. Jeden typ, przy
    # nim napisane, u kogo grać — `merged` w pętli scoringu bierze wyższy kurs
    # i zapamiętuje jego źródło.
    bc_cache: dict[int, dict] = {}
    if not _dry_run() or os.getenv("BETCLIC_W_DRYRUN"):
        try:
            _teraz_bc = int(time.time())
            # PAMIĘĆ MIĘDZY CYKLAMI — bez niej pełne pokrycie jest nieosiągalne
            # (patrz nota przy BUDZET_BETCLIC_TYPY_S). Padnięty odczyt traktujemy
            # jak pustą pamięć, ale wtedy NIE zapisujemy z powrotem — inaczej
            # jeden timeout Supabase kasowałby dorobek kilku cykli
            # ([[supabase-read-modify-write]]).
            _pamiec_raw, _odczyt_ok = supa.get_key_ok(BETCLIC_KLUCZ)
            _pamiec = dict(_pamiec_raw or {}) if _odczyt_ok else {}
            bc_cache = bc_z_pamieci(_kolejnosc_meczow, _pamiec, _teraz_bc)
            _z_pamieci = len(bc_cache)
            # przy budżecie 0 (domyślnie) cykl nie pobiera nic — oferta pochodzi
            # w całości z osobnego joba, a ta lista służy już tylko do logu
            _do_pobrania = (
                bc_do_pobrania(_kolejnosc_meczow, bc_cache, sb_cache)
                if BUDZET_BETCLIC_TYPY_S > 0 else []
            )
            _n_bc = 0
            if _do_pobrania:
                _pary_bc, _ = betclic.paruj_mecze([
                    {"klucz": _mid,
                     "home": team_name.get((ev_by_id.get(_mid) or {}).get("homeTeamId"), ""),
                     "away": team_name.get((ev_by_id.get(_mid) or {}).get("awayTeamId"), ""),
                     "kickoff_ts": _ts}
                    for _mid, _ts in _do_pobrania
                ])
                _start_bc = time.time()
                for _mid, _ts in _do_pobrania:
                    _bc = _pary_bc.get(_mid)
                    if not _bc:
                        continue
                    if time.time() - _start_bc > BUDZET_BETCLIC_TYPY_S:
                        print(f"Betclic: budżet czasu wyczerpany po {_n_bc} "
                              f"meczach (zostaje {len(_do_pobrania) - _n_bc} "
                              "na następny cykl)")
                        break
                    try:
                        _paczka = betclic.kursy_zawodnikow(int(_bc["id"]))
                    except Exception as e:
                        # szeroko z tego samego powodu co w `betclic_oferty`:
                        # tu wyjątek spoza listy nie kładł cyklu (jest szerszy
                        # `except` niżej), ale ucinał pobieranie WSZYSTKIM
                        # kolejnym meczom w tym przebiegu
                        diagnostyka.cichy("betclic", "kursy_zawodnikow", e)
                        continue
                    _n_bc += 1
                    if _paczka.get("players"):
                        bc_cache[_mid] = {
                            "players": _paczka["players"], "ts": _teraz_bc,
                        }
                        _pamiec[str(_mid)] = {
                            "ts": _teraz_bc, "players": _paczka["players"],
                        }
            _pamiec = bc_rotuj_pamiec(_pamiec, _kolejnosc_meczow, _teraz_bc)
            if bc_cache:
                print(f"Betclic jako źródło ofert: {len(bc_cache)} meczów "
                      f"(z pamięci {_z_pamieci}, pobrane {_n_bc}), "
                      f"{sum(len(p.get('players') or {}) for p in bc_cache.values())} "
                      "kwotowanych zawodników")
            if _odczyt_ok and _pamiec and not _dry_run():
                supa.put_key_bezpiecznie(BETCLIC_KLUCZ, _pamiec)
        except Exception as e:
            bc_cache = {}
            print(f"Betclic niedostępny jako źródło ofert ({e})")

    trendy_z_oferty: list = []
    try:
        dopelnij_oferte_zawodnicza(
            gracze_meczu, sb_cache, players_out, odds_grid, _forma_z_trendu,
            kolejnosc=_kolejnosc_meczow,
            trends_out=trendy_z_oferty,
            oferty_extra=bc_cache,
            zrodla_grid=zrodla_grid,
        )
    except Exception as e:
        # oferta to DODATEK do feedu propsów — jej awaria nie ma prawa
        # zatrzymać cyklu, który i tak policzy typy ze zwykłych trendów
        trendy_z_oferty = []
        print(f"Oferta zawodnicza — dopełnienie padło ({e})")
    if trendy_z_oferty:
        trends = list(trends) + trendy_z_oferty

    for tr in trends:
        if (tr.player_id, tr.market_code) in seen_player_market:
            continue
        seen_player_market.add((tr.player_id, tr.market_code))
        # mecz zawodnika: po jego drużynie i przeciwniku
        ev = next((e for e in events
                   if {e.get("homeTeamId"), e.get("awayTeamId")}
                   == {tr.team_id, tr.opponent_id}), None)
        if ev is None:
            continue
        mid = ev["id"]
        ts = ev.get("timeStartTimestamp") or int(time.time())
        home_name = team_name.get(ev.get("homeTeamId"), "")
        away_name = team_name.get(ev.get("awayTeamId"), "")
        match_label = f"{home_name} – {away_name}"

        # POZA SKŁADEM — koniec pętli dla tego zawodnika. Znamy jedenastkę
        # jego drużyny i jego w niej nie ma, więc typ na niego jest zakładem
        # o to, że wejdzie z ławki i zdąży. Rozliczenia mówią, ile to kosztuje:
        # przy nieznanym składzie zawodnik zagrał w 85% przypadków, przy
        # ogłoszonym — w 95%. Te 10 pp to czyste pudła bez żadnej szansy.
        if (mid, tr.player_id) in poza_skladem:
            _odrzuc(mid, tr, "poza_skladem",
                    "nie ma go w składzie na ten mecz")
            continue

        if mid not in matches_out:
            sed = sedzia_by_mid.get(mid) or {}
            # etykiety rozgrywek: tryb ligowy niesie je per mecz (z profili
            # rozgrywek + rund statshub); MŚ zostaje po staremu
            et = (tryb.liga_by_mid.get(mid) if tryb else None) or {
                "liga": "MŚ", "sezon": "2026", "kolejka": "Ćwierćfinał",
            }
            # na karcie meczu pokazujemy mnożnik PO shrinkage (1-2 mecze
            # próby to za słaby dowód na "×1,26") — spójnie ze scoringiem
            matches_out[mid] = {
                "id": mid, "liga": et["liga"], "sezon": et["sezon"],
                "kolejka": et["kolejka"], "kickoff_ts": ts,
                "gospodarz": home_name, "gosc": away_name,
                "sedzia": sed.get("sedzia"),
                "sedzia_mnoznik_fauli": round(context.shrink_factor(
                    float(sed.get("mnoznik") or 1.0), sed.get("n", 0), 8.0
                ), 2),
                "okazje": [],
                "sklady_ogloszone": lineup_confirmed.get(mid, False)
                or (
                    rotowire.is_confirmed(roto, home_name)
                    and rotowire.is_confirmed(roto, away_name)
                ),
            }

        # kursy Superbetu dla meczu — pobrane PRZED pętlą (patrz pre-pass oferty
        # wyżej), bo z nich powstają trendy dokładane do silnika. Tu już tylko
        # odczyt z cache; `_oferta_meczu` dociąga wyłącznie mecz, który z jakiegoś
        # powodu ominął pre-pass.
        sb_odds = _oferta_meczu(mid, home_name, away_name, ts)

        # ILU ZAWODNIKÓW TEGO MECZU SUPERBET W OGÓLE KWOTUJE.
        # Strona meczu musi odróżnić "bukmacher nie wystawia propsów" (Leagues
        # Cup, Copa do Brasil, puchary — zmierzone 3.08: 25 z 26 meczów bez
        # ani jednego propsa) od "wystawia, a my nic nie znaleźliśmy" (błąd
        # parsera — taki już nas kosztował tydzień). Bez tej liczby TOP POKRYCIA
        # zgadywało przyczynę pustej kolumny kursu.
        if mid in matches_out:
            matches_out[mid]["propsy_superbet"] = len(
                (sb_odds or {}).get("players") or {}
            )

        mf, mo = matchup_lite.matchup_lite_factor(
            tr.market_code,
            tr.game_positions[:6],
            opp_players_by_team.get((mid, tr.opponent_id), []),
        )
        # pełne profile stylu (cache per zawodnik — nie zależą od rynku)
        pstyle = ostyle = None
        if style_turnieju is not None:
            ostyle = style_turnieju.opponent(tr.opponent_name)
            if ostyle is not None:
                if tr.player_id not in pstyle_cache:
                    pstyle_cache[tr.player_id] = style_turnieju.player(
                        tr.player_name, tr.position or "M",
                        tr.game_positions[:8], player_id_sh=tr.player_id,
                    )
                pstyle = pstyle_cache[tr.player_id]
        built, hist = score_from_trend(
            tr, tr.opponent_average,
            # potwierdzony/przewidywany skład wolno czytać z in_predicted_lineup
            # tylko dla (mecz, zawodnik) z żywego feedu statshub — trendy
            # banku/365 spoza niego mają False = "brak sygnału"
            lineup_confirmed=lineup_confirmed.get(mid, False)
            and (mid, tr.player_id) in xi_zywy,
            predicted_available=predicted_available.get(mid, False)
            and (mid, tr.player_id) in xi_zywy,
            roto_pred=rotowire.predicted_status(roto, tr.team_name, tr.player_name),
            roto_confirmed=rotowire.is_confirmed(roto, tr.team_name),
            matchup_factor=mf if mf != 1.0 else None,
            matchup_opis=mo,
            wc_names=wc_names,
            elo_map=elo_map,
            tempo_meczu=tempo_cache.get(mid),
            sedzia=sedzia_by_mid.get(mid),
            koncesje_tab=koncesje_tab,
            player_style=pstyle,
            opponent_style=ostyle,
            liga=tryb is not None,
        )
        if built is None:
            _odrzuc(mid, tr, "za_malo_historii",
                    "mniej niż 3 mecze z minutami w historii")
            continue
        prior, ctx = built
        mk = tr.market_code
        # BRAMA JAKOŚCI (liga): typ tylko przy świeżej próbie. W MŚ nie ma
        # sensu (turniej sam jest oknem świeżości), w lidze historia bywa
        # w całości sprzed pauzy/kontuzji/transferu.
        stare_dane = False
        if tryb:
            n_swieze, dni_ostatni = swiezosc_proby(
                tr.timestamps, tr.minutes, int(time.time())
            )
            if n_swieze < MIN_MECZE_W_OKNIE:
                _odrzuc(mid, tr, "za_stara_historia",
                        f"tylko {n_swieze} występów w ostatnich 4 miesiącach, "
                        "dane o zawodniku są nieaktualne")
                continue
            stare_dane = dni_ostatni * 86400 > STARE_DANE_S
            if stare_dane:
                # przerwa CAŁEJ ligi (mundialowa/letnia), nie zawodnika:
                # jeśli grał w okresie ostatnich meczów swojej drużyny
                # (różnica do 14 dni), jego dane są tak świeże, jak kalendarz
                # pozwala — typ wraca do publikacji zamiast wisieć "w tle"
                # (2026-07: cała MLS po pauzie mundialowej łapała flagę)
                ost_dr = ostatni_mecz_druzyny.get(tr.team_id or -1, 0)
                if ost_dr > 0:
                    dni_druzyny = (int(time.time()) - ost_dr) / 86400.0
                    if dni_ostatni - dni_druzyny <= 14.0:
                        stare_dane = False
        # trigger rotacyjny: zawodnik w (przewidywanym) XI bez ani jednego
        # występu na turnieju (w lidze: w oknie świeżości z trybu) — rynek
        # często nie zdążył dograć jego linii
        prog_rotacji = tryb.rotacja_min_ts if tryb else WC_START_TS
        gral_na_turnieju = any(
            ts_g >= prog_rotacji and m_g > 0
            for ts_g, m_g in zip(tr.timestamps, tr.minutes)
        )
        rotacja = bool(
            (ctx.official_started or ctx.predicted_started)
            and not gral_na_turnieju
        )
        # sygnał składu przy publikacji — trafia do typy_log (kalibracja p_start)
        xi_sygnal = (
            "official" if ctx.official_started
            else "predicted" if ctx.predicted_started else None
        )

        probe = score_player_market(mk, 0.5, hist, prior, ctx, None, None,
                                    market_calibrated=True,
                                    market_bias=_bias_z_korekta(mk, "pewniaki"))
        if probe.lam < (0.35 if mk not in RARE_MARKETS else 0.2):
            _odrzuc(mid, tr, "za_malo_zdarzen",
                    f"model oczekuje ~{probe.lam:.2f} na mecz, za mało na typ")
            continue
        # ile minut spodziewamy się po zawodniku (patrz MIN_OCZEK_MINUT):
        # rezerwowy z 25 minutami to loteria składu, nie typ statystyczny
        if (probe.expected_minutes or 0.0) < MIN_OCZEK_MINUT:
            _odrzuc(mid, tr, "za_malo_minut",
                    f"spodziewamy się ~{probe.expected_minutes:.0f} minut, "
                    "za mało jak na typ")
            continue
        line = line_for_lambda(probe.lam)

        # niecelne/zablokowane z PRAWDZIWEJ historii 365Scores: pełny scoring
        # (Superbet nie kwotuje tych rynków — wynik trafi do sugestii STS)
        if mk in ("shots_blocked", "shots_off_target"):
            sm_r = score_player_market(mk, line, hist, prior, ctx, None, None,
                                       market_calibrated=True,
                                       market_bias=_bias_z_korekta(mk, "pewniaki"))
            dist_r = counts.predict_match(
                counts.fit_posterior(
                    np.array(hist.counts), np.array(hist.minutes),
                    np.array(hist.days_ago), prior),
                sm_r.expected_minutes, 1.0,
            ).distribution(8)
            real_split[(tr.player_id, mk)] = {
                "sm": sm_r, "line": line, "dist": dist_r,
                "stare_dane": stare_dane,
                "info": {
                    "name": tr.player_name, "team": tr.team_name,
                    "opp": tr.opponent_name, "mid": mid, "ts": ts,
                    "match": match_label,
                },
            }

        # kursy Superbetu dla tego zawodnika/rynku (mecz pobrany wyżej);
        # znajdz_zawodnika łata rozjazd pełne vs boiskowe nazwiska (kluby)
        sb_lines = {}
        if sb_odds:
            sb_lines = superbet.znajdz_zawodnika(
                sb_odds.get("players", {}), tr.player_name
            ).get(mk, {})

        # kursy Betclica dla tego samego zawodnika i rynku (drugie źródło ofert
        # od 2026-08-08 — patrz nota u góry pliku)
        bc_lines = {}
        bc_odds = bc_cache.get(mid) or {}
        if bc_odds:
            bc_lines = betclic.znajdz_zawodnika(
                bc_odds.get("players") or {}, tr.player_name
            ).get(mk, {})

        # kursy: linia -> strona -> (kurs, bukmacher). Gdy obaj kwotują tę samą
        # linię, zostaje WYŻSZY — ten sam zakład za więcej pieniędzy. Nazwa
        # bukmachera jedzie razem z kursem, więc typ zawsze wie (i pokazuje),
        # gdzie ta cena była do wzięcia.
        merged: dict = {}
        for zrodlo, linie_z in (("Superbet", sb_lines), ("Betclic", bc_lines)):
            for l, v in (linie_z or {}).items():
                slot = merged.setdefault(l, {})
                for side in ("over", "under"):
                    odd = (v or {}).get(side)
                    if odd and (side not in slot or odd > slot[side][0]):
                        slot[side] = (odd, zrodlo)

        # siatka kursów (over) do TOP POKRYCIA i do drabinek — wszystkie linie
        # danego zawodnika/rynku, keyed po player_id (players.json nie ma mecz_id)
        over_linie = {
            str(l): round(slot["over"][0], 2)
            for l, slot in merged.items() if slot.get("over")
        }
        if over_linie:
            odds_grid.setdefault(mid, {}).setdefault(tr.player_id, {})[mk] = (
                over_linie
            )
            # ⚑ ŹRÓDŁO JEDZIE RAZEM Z CENĄ (2026-08-08, zgłoszenie usera:
            # „czy przy typie jest napisane jaki bukmacher w drabinkach").
            # `merged` wybiera WYŻSZY kurs z dwóch cenników, więc od 08.08 do
            # siatki trafiają też ceny Betclica — ale sama liczba, bez nazwy.
            # Karta drabinki pisała wtedy „Kurs 1,82 u Superbetu" nad ceną,
            # której u Superbetu nie ma. Typy miały to dobrze od początku
            # (pole `bukmacher`), drabinki czytają siatkę i nie miały skąd wziąć.
            # Zapisujemy TYLKO wyjątki, bo Superbet jest domyślny i mapa
            # obcych cen jest o rząd wielkości mniejsza niż cała siatka.
            obce = {
                str(l): slot["over"][1]
                for l, slot in merged.items()
                if slot.get("over") and slot["over"][1] != "Superbet"
            }
            if obce:
                zrodla_grid.setdefault(mid, {}).setdefault(
                    tr.player_id, {})[mk] = obce

        # zapisz formę zawodnika (dla UI)
        if tr.player_id not in players_out:
            players_out[tr.player_id] = {
                "id": tr.player_id, "nazwa": tr.player_name,
                "pozycja": tr.position or "?", "druzyna": tr.team_name,
                "minuty_lacznie": int(sum(tr.minutes)), "forma": {},
                # w przewidywanym/potwierdzonym pierwszym składzie (na górę TOP POKRYCIA)
                "xi": bool(tr.in_predicted_lineup),
            }
        elif tr.in_predicted_lineup:
            players_out[tr.player_id]["xi"] = True
        players_out[tr.player_id]["forma"][mk] = _forma_z_trendu(tr, mk)
        # zawodnicy per mecz — punkt wejścia dla dopelnij_oferte_zawodnicza()
        # (tam odwracamy kolejność: oferta bukmachera → nasza historia)
        gracze_meczu.setdefault(mid, {})[tr.player_id] = tr

        if not merged:
            _odrzuc(mid, tr, "brak_kursu",
                    "Superbet nie kwotuje tego rynku dla zawodnika")
            continue  # brak realnego kursu — nie tworzymy okazji

        # 1a: samospójność siatki linii Superbetu (line shopping bez
        # zewnętrznych kursów) — fair kurs każdej linii z fitu do POZOSTAŁYCH
        fair_wewn: dict[float, float] = {}
        if len(merged) >= 3:
            probs_w = {
                l0: betting.implied_prob_one_sided(s0["over"][0])
                for l0, s0 in merged.items() if s0.get("over")
            }
            if len(probs_w) >= 3:
                fair_wewn = betting.internal_fair_odds(probs_w)

        best_by_side, chosen = {}, {}
        # śledzenie powodu, gdy ŻADNA linia nie wejdzie do puli kuponów —
        # zasila rejestr odrzuceń precyzyjniejszym powodem niż "nie wyszło"
        n_pool_przed = len(legi_pool)
        prof_ok = ci_fail = div_fail = False
        powod_profilu: str | None = None   # patrz `_KOLEJNOSC_PROFILU`
        hist_krotka = len(tr.counts) < 5
        for l, slot in sorted(merged.items()):
            over_odd = slot.get("over", (None,))[0]
            under_odd = slot.get("under", (None,))[0]
            sm = score_player_market(mk, l, hist, prior, ctx,
                                     over_odd, under_odd,
                                     market_calibrated=True,
                                     market_bias=_bias_z_korekta(mk, "pewniaki"))
            # POMIAR PROGÓW: odrzucenia tuż przy progu (betting.NEAR_*) —
            # rozliczą się w tle poza kalibracją/skutecznością/UI
            for od in sm.odrzucone:
                if (
                    od.get("side") != "powyzej"
                    or len(odrzucone_pomiar) >= ODRZUCONE_POMIAR_MAX
                ):
                    continue
                odrzucone_pomiar.append({
                    "id": 0, "mecz_id": mid, "mecz": match_label,
                    "kickoff_ts": ts, "podmiot_typ": "zawodnik",
                    "podmiot_id": tr.player_id, "podmiot": tr.player_name,
                    "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk],
                    "linia": l, "strona": "powyzej",
                    "kurs": od.get("odds"), "bukmacher": "Superbet",
                    "p_model": od.get("p_model"),
                    "pewnosc": "wysoka" if (sm.ci_high - sm.ci_low) <= 0.18
                    else "srednia",
                    "sugestia": False,
                    "odrzucony": True,
                    "odrzucenie_powod": od.get("powod"),
                })
            # pula pewniaków pod kupony: wysoka szansa + rozsądny kurs,
            # bez wymogu value, ale z TYMI SAMYMI bezpiecznikami rozbieżności
            # co okazje — model skrajnie niezgodny z rynkiem zwykle się myli
            # gramy wyłącznie "powyżej" (decyzja usera); under ma też wadę
            # modelową: P(nie zagra) wchodzi do dołu, a buk daje wtedy zwrot
            for side_key, side_pl in (("over", "powyzej"),):
                sv = slot.get(side_key)
                if not sv:
                    continue
                odd = sv[0]
                p_side = sm.p_over if side_key == "over" else 1.0 - sm.p_over
                implied = betting.implied_prob_one_sided(odd)
                # pełne pokrycie p_model (PRZED filtrami puli/okazji) — do STS
                model_pokrycie.append({
                    "podmiot": tr.player_name, "rynek_kod": mk, "linia": l,
                    "strona": side_pl, "p_model": round(p_side, 4),
                    "oczekiwane_minuty": sm.expected_minutes,
                })
                # miękka linia: płaci >=12% ponad kurs wynikający z RESZTY
                # siatki Superbetu na ten rynek (fair netto -> brutto z marżą)
                fw = fair_wewn.get(l)
                kurs_oczekiwany = (
                    round(fw * (1.0 - betting.DEFAULT_ONE_SIDED_MARGIN), 2)
                    if fw else None
                )
                miekka = (
                    kurs_oczekiwany is not None
                    and odd >= kurs_oczekiwany * 1.12
                )
                # dwa profile lega: PEWNIAK (niski kurs, wysoka szansa) oraz
                # PEREŁKA (kurs 2.0-3.6 przy wciąż solidnej szansie i
                # nieujemnej wartości — okazjonalne rodzynki na kupony)
                # O PUBLIKACJI decyduje p OSTROŻNE: średnia punktowego p
                # i dolnej granicy przedziału wiarygodności. Powód nie jest
                # kosmetyczny — zmierzone 2026-07-26 na 324 rozliczeniach:
                # luka deklaracja−trafienia trzyma się −7 do −22 pp NIEZALEŻNIE
                # od okresu, mimo dużych korekt kalibracyjnych (−0,25..−0,73
                # w logitach, tylko 1 przedział z 44 przy suficie). To nie jest
                # błąd średniej, tylko EFEKT SELEKCJI: liczymy p dla tysięcy
                # kandydatów i publikujemy te z najwyższym, a najwyższe
                # oszacowania to systematycznie te, które przestrzeliły w górę.
                # Kalibracja ściąga wszystkie p, brama wybiera nowy czub i
                # korekta goni własny ogon. Dolna granica karze wprost to,
                # co selekcja premiuje: szerokie, niepewne oszacowania.
                p_dec = (p_side + sm.ci_low) / 2.0 if sm.ci_low is not None else p_side
                pewny = (
                    betting.MIN_ODDS <= odd <= betting.PROFIL_PEWNY_MAX_ODDS
                    and p_side >= betting.PROFIL_PEWNY_MIN_P
                    and p_dec * odd - 1.0 >= 0.0
                )
                perelka = (
                    betting.PROFIL_PERELKA_ODDS[0] <= odd
                    <= betting.PROFIL_PERELKA_ODDS[1]
                    and p_side >= betting.PROFIL_PERELKA_MIN_P
                    and p_dec * odd - 1.0 >= 0.0
                )
                # furtka kontekstowa: rynki niszowe (spalone / głową / celne
                # zza pola) prawie nigdy nie przechodzą zwykłych progów, a to
                # tam rynek myli się najbardziej — wpuszczamy je wyłącznie
                # przy wyraźnie sprzyjającym profilu rywala (matchup)
                czynnik_rywala = float(sm.factors.get("rywal", 1.0) or 1.0)
                matchup_typ = czynnik_rywala >= 1.12
                niszowa = (
                    mk in RARE_MARKETS
                    and matchup_typ
                    and betting.PROFIL_PERELKA_ODDS[0] <= odd
                    <= betting.PROFIL_PERELKA_ODDS[1]
                    and p_side >= betting.PROFIL_NISZOWA_MIN_P
                    and p_dec * odd - 1.0 >= 0.0
                )
                if not (pewny or perelka or niszowa):
                    # KTÓRY warunek uciął — patrz `powod_profilu_zawodnika`.
                    # Trzymamy powód NAJBLIŻSZY publikacji spośród wszystkich
                    # kwotowanych linii tego zawodnika: „zabrakło wartości"
                    # mówi co innego niż „kurs w ogóle nie z tej półki".
                    _p = betting.powod_profilu_zawodnika(
                        odd, p_side, p_dec,
                        rzadki=mk in RARE_MARKETS, matchup=matchup_typ,
                    )
                    if _KOLEJNOSC_PROFILU.get(_p, 0) > _KOLEJNOSC_PROFILU.get(
                        powod_profilu or "", 0
                    ):
                        powod_profilu = _p
                # typ kontekstowy (matchup): profil rywala wyraźnie sprzyja —
                # model może rozejść się z rynkiem mocniej niż zwykle, bo zna
                # kontekst, którego kurs mógł nie wycenić (weryfikują rozliczenia)
                max_div = 0.30 if matchup_typ else betting.MAX_MODEL_MARKET_DIVERGENCE
                max_rel = 2.3 if matchup_typ else betting.MAX_RELATIVE_DIVERGENCE
                if pewny or perelka or niszowa:
                    prof_ok = True
                    if (sm.ci_high - sm.ci_low) > 0.35:
                        ci_fail = True
                    if abs(p_side - implied) > max_div or (
                        implied > 0 and p_side / implied > max_rel
                    ):
                        div_fail = True
                if (
                    (pewny or perelka or niszowa)
                    and len(tr.counts) >= 5  # pewniak nie powstaje z 2 meczów
                    and (sm.ci_high - sm.ci_low) <= 0.35
                    and abs(p_side - implied) <= max_div
                    and (implied <= 0 or p_side / implied <= max_rel)
                ):
                    # wartość lega (do selekcji kuponów „ku przewadze”):
                    # EV vs Superbet zawsze; no-vig UK gdy jest konsensus na tej linii
                    ev_pct_leg = round(betting.ev_brutto_pct(p_side, odd), 1)
                    ev_netto_leg = round(betting.ev_pct(p_side, odd), 1)
                    ev_uk_leg = None
                    kurs_ref_leg = None
                    if (
                        tr.ref_odds and abs(l - tr.line) < 1e-6
                        and tr.odds_type == "over" and side_key == "over"
                    ):
                        # mediana UK — do KALIBRACJI marży UK z rozliczeń (rozliczanie.py
                        # potrzebuje kurs_ref w typy_log; bez niego legi trafiające do
                        # logu WYŁĄCZNIE przez kupon są ślepą plamą dla tej diagnostyki)
                        kurs_ref_leg = round(statistics.median(tr.ref_odds), 2)
                        _nv = betting.no_vig_prob_uk(tr.ref_odds)
                        if _nv:
                            ev_uk_leg = round((_nv[0] * odd - 1.0) * 100.0, 1)
                    legi_pool.append({
                        "id": 0, "mecz_id": mid, "mecz": match_label,
                        "kickoff_ts": ts, "podmiot_id": tr.player_id,
                        "podmiot": tr.player_name, "druzyna": tr.team_name,
                        "przeciwnik": tr.opponent_name,
                        "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk], "linia": l,
                        "strona": side_pl, "kurs": odd,
                        "bukmacher": sv[1], "p_model": round(p_side, 4),
                        "ev_pct": ev_pct_leg, "ev_netto": ev_netto_leg,
                        "ev_uk": ev_uk_leg, "kurs_ref": kurs_ref_leg,
                        # ta sama formuła co w value_bets (spójne z pewnosc_score
                        # backendu) — generator na żądanie (GeneratorKuponu) tego
                        # dotąd nie miał, więc nie mógł filtrować jak styl "value"
                        "pewnosc": "wysoka" if (sm.ci_high - sm.ci_low) <= 0.18 else "srednia",
                        "matchup": matchup_typ, "rotacja": rotacja,
                        # PEŁNY matchup stylu realnie ruszył predykcję — flaga
                        # do diagnostyki kategorii (czy analogie stylu trafiają)
                        "matchup_styl": bool(
                            pstyle is not None and ostyle is not None
                            and abs(float(sm.factors.get("matchup", 1.0) or 1.0) - 1.0) >= 0.05
                        ),
                        "xi_sygnal": xi_sygnal,
                        "swieze_sklady": mid in swieze_mids,
                        # brama jakości (liga): ostatni występ dawniej niż
                        # STARE_DANE_S -> typ nie wchodzi do publikacji ani
                        # do puli generatora, rozlicza się w tle
                        "stare_dane": stare_dane,
                        "miekka_linia": miekka,
                        "kurs_oczekiwany": kurs_oczekiwany if miekka else None,
                        "ci": [sm.ci_low, sm.ci_high],
                        "oczekiwane_minuty": sm.expected_minutes,
                        "ryzyko": betting.risk_level(
                            sm.lam, mk in RARE_MARKETS,
                            1.0 if (sm.expected_minutes or 0) >= 80
                            else 0.75 if (sm.expected_minutes or 0) >= 60
                            else 0.45,
                        ),
                        "czynniki": sm.factors, "uzasadnienie": sm.reasoning,
                        "lambda": sm.lam,
                        # rozkład przybliżony Poissonem z λ — pod drabinkę
                        # "szanse na inne linie" w rozwinięciu karty
                        "rozklad": [
                            float(_stats.poisson.pmf(k, sm.lam)) for k in range(7)
                        ] + [float(_stats.poisson.sf(6, sm.lam))],
                        # NA CZYM STOI TA LICZBA — patrz betting.stempel_rachunku.
                        # Silnik dostał deltę ŁĄCZNĄ (`_bias_z_korekta`), więc
                        # składowe liczymy tutaj, gdzie znamy obie z osobna.
                        "rachunek": betting.stempel_rachunku(
                            p_over_raw=sm.p_over_raw,
                            kal_rynek=betting.delta_dla_p(
                                bias_map.get(mk), sm.p_over_raw
                            ) if sm.p_over_raw is not None else None,
                            kal_strumien=betting.delta_dla_p(
                                korekta_strumieni.get("pewniaki", 0.0),
                                sm.p_over_raw,
                            ) if sm.p_over_raw is not None else None,
                            p_over_final=sm.p_over,
                        ),
                    })
            for a in sm.assessments:
                if a.side not in best_by_side or a.rank_score > best_by_side[a.side].rank_score:
                    best_by_side[a.side] = a
                    chosen[a.side] = (sm, l, slot)
        # żadna linia nie weszła do puli kuponów — zapisz precyzyjny powód
        if len(legi_pool) == n_pool_przed:
            if not prof_ok:
                # POWÓD, NIE ZBIORCZA ETYKIETA (2026-08-03). Do dziś wszystkie
                # trzy warunki profilu miały jeden komunikat, więc 137 odrzuceń
                # dziennie nie mówiło, co właściwie tnie — i tym samym nie dało
                # się zdecydować, czy problem jest w progach, w cenie, czy
                # w tym, że korekta strumienia ściąga szansę pod próg.
                _odrzuc(mid, tr,
                        powod_profilu or "kurs_lub_szansa_poza_widelkami",
                        betting.POWODY_PROFILU_PL.get(
                            powod_profilu or "",
                            "kwotowane linie nie łączą sensownego kursu z szansą",
                        ))
            elif hist_krotka:
                _odrzuc(mid, tr, "krotka_historia",
                        f"tylko {len(tr.counts)} meczów w historii (potrzeba 5)")
            elif ci_fail and not div_fail:
                _odrzuc(mid, tr, "chwiejna_predykcja",
                        "za szerokie widełki szansy, model sam nie jest pewny")
            else:
                _odrzuc(mid, tr, "rozjazd_z_rynkiem",
                        "model za daleko od kursu, zwykle to my czegoś nie wiemy")
        for a in best_by_side.values():
            if a.side != "powyzej":
                continue  # underów nie gramy (decyzja usera)
            sm, l, slot = chosen[a.side]
            side_key = "over" if a.side == "powyzej" else "under"
            kurs_wziety, book = slot[side_key]
            vb_id += 1
            dist = counts.predict_match(
                counts.fit_posterior(
                    np.array(hist.counts), np.array(hist.minutes),
                    np.array(hist.days_ago), prior),
                sm.expected_minutes, 1.0,
            ).distribution(8)
            # konsensus bukmacherów UK (statshub) dla tej samej linii i strony
            kurs_ref = None       # surowa mediana UK (do UI: „UK płaci średnio X")
            kurs_novig = None     # uczciwy kurs UK po zdjęciu marży (no-vig benchmark)
            ev_uk = None          # wartość Superbetu vs no-vig UK, w %
            if (
                tr.ref_odds
                and abs(l - tr.line) < 1e-6
                and (tr.odds_type == "over") == (a.side == "powyzej")
            ):
                kurs_ref = round(statistics.median(tr.ref_odds), 2)
                novig = betting.no_vig_prob_uk(tr.ref_odds)
                if novig is not None:
                    p_uk, fair_uk = novig
                    kurs_novig = round(fair_uk, 2)
                    ev_uk = round((p_uk * kurs_wziety - 1.0) * 100.0, 1)
            # OKAZJA Z KURSEM, gdy jest DOWÓD miękkiej linii:
            #  (1) NO-VIG UK: Superbet daje realną WARTOŚĆ >= PROG_EV_UK ponad
            #      uczciwą cenę UK po zdjęciu marży (nie tylko wyższy surowy kurs —
            #      to porównanie w przestrzeni prawdopodobieństwa, skalujące się
            #      z kursem), LUB
            #  (2) >= 12% ponad kurs z JEGO WŁASNEJ siatki pozostałych linii (1a —
            #      line shopping bez zewnętrznych źródeł).
            # Bez dowodu — typ zostaje w puli pewniaków.
            odstaje_zewn = ev_uk is not None and ev_uk >= PROG_EV_UK
            fw_a = fair_wewn.get(l)
            oczek_a = (
                round(fw_a * (1.0 - betting.DEFAULT_ONE_SIDED_MARGIN), 2)
                if fw_a else None
            )
            miekka_a = oczek_a is not None and kurs_wziety >= oczek_a * 1.12
            if not odstaje_zewn and not miekka_a:
                continue
            rec_okazji = {
                "id": vb_id, "mecz_id": mid, "mecz": match_label, "kickoff_ts": ts,
                "podmiot_typ": "zawodnik", "podmiot_id": tr.player_id,
                "podmiot": tr.player_name, "druzyna": tr.team_name,
                "przeciwnik": tr.opponent_name,
                "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk],
                "linia": l, "strona": a.side,
                "kurs": kurs_wziety,
                "bukmacher": book,
                # KIEDY TĘ CENĘ WIDZIELIŚMY. Superbet pobieramy co cykl, więc
                # jego kurs jest sprzed minut; oferta Betclica jest pamiętana
                # (patrz SWIEZOSC_BETCLIC_S) i bywa sprzed godzin. Bez tego
                # stempla front nie miałby jak uczciwie powiedzieć, że cena
                # mogła się od tego czasu ruszyć.
                "kurs_ts": (
                    int((bc_odds or {}).get("ts") or ts_cyklu)
                    if book == "Betclic" else ts_cyklu
                ),
                "kurs_ref": kurs_ref,
                "kurs_novig": kurs_novig, "ev_uk": ev_uk,
                "p_model": a.model_prob, "p_rynku": a.implied_prob,
                "fair_kurs": a.fair_odds, "edge_pp": a.edge_pp, "ev_pct": a.ev_pct,
                "ev_netto": a.ev_netto, "tryb_podatku": a.tryb_podatku,
                "matchup": float(sm.factors.get("rywal", 1.0) or 1.0) >= 1.12,
                "matchup_styl": bool(
                    pstyle is not None and ostyle is not None
                    and abs(float(sm.factors.get("matchup", 1.0) or 1.0) - 1.0) >= 0.05
                ),
                "rotacja": rotacja, "xi_sygnal": xi_sygnal,
                "miekka_linia": odstaje_zewn or miekka_a,
                "kurs_oczekiwany": (
                    kurs_novig if odstaje_zewn else (oczek_a if miekka_a else None)
                ),
                "pewnosc": a.confidence, "pewnosc_score": a.confidence_score,
                "ryzyko": a.risk, "rank_score": a.rank_score,
                "ci": [sm.ci_low, sm.ci_high],
                "oczekiwane_minuty": sm.expected_minutes, "lambda": sm.lam,
                "rozklad": dist, "czynniki": sm.factors, "uzasadnienie": sm.reasoning,
            }
            # brama jakości (liga): okazja na starych danych nie wchodzi do
            # publikacji, rozlicza się i uczy kalibrację w tle. To samo dotyczy
            # okazji, która powstałaby tuż przed gwizdkiem (zapas na obstawienie)
            # ta sama brama co wszędzie indziej: strona traci pieniądze
            # w oknie rozliczeń (rynek jako całość może być w porządku —
            # pomiar 30.07), albo rynek stoi i strona nie ma własnej próby
            _kw_z = _kwarantanna_zdejmuje({"rynek_kod": mk, "strona": a.side})
            if _kw_z:
                rec_okazji["poza_publikacja"] = _kw_z
                typy_poza_publikacja.append(rec_okazji)
            elif not betting.w_oknie_zgody(a.model_prob, kurs_wziety):
                rec_okazji["poza_publikacja"] = "rozjazd_z_rynkiem"
                typy_poza_publikacja.append(rec_okazji)
            elif stare_dane:
                rec_okazji["poza_publikacja"] = "stare_dane"
                typy_poza_publikacja.append(rec_okazji)
            elif ts <= int(time.time()) + kupony.MARGINES_STARTU_S:
                rec_okazji["poza_publikacja"] = "za_pozno"
                typy_poza_publikacja.append(rec_okazji)
            else:
                value_bets.append(rec_okazji)
                matches_out[mid]["okazje"].append(vb_id)

    # --- OFERTA ZAWODNICZA MECZU: wykonana PRZED pętlą scoringu (2026-08-08).
    # Dawniej stała tutaj i przez to jej rynki mogły zasilić tabelę pokryć oraz
    # drabinki, ale nigdy nie stawały się typem — pętla, która robi typy, była
    # już za nami. Drugiego wywołania NIE MA celowo: budżet zapytań do
    # `/player/{id}/performance` jest wspólny na cykl, a powtórka kosztowałaby
    # go dwa razy przy zerowym zysku (forma jest już uzupełniona).

    # --- SUGESTIE bez kursów: niecelne / zablokowane (rynki STS, blokowany w chmurze) ---
    # WYŁĄCZNIE z prawdziwej historii per strzał z 365Scores (real_split —
    # pełny scoring modelu: prior, minuty, składy, matchup). Dawny fallback
    # "strzały − celne z podziałem ligowym" USUNIĘTY: rozliczenia pokazały
    # hit 23.5% przy śr. p 55.2% (real_split: 48.8% przy 58.1%) — szacunek
    # był czystym szumem i psuł kalibrację oraz zaufanie do sekcji.
    # DECYZJA PRODUKTOWA 2026-07-21: sugestii STS nie publikujemy. Samotny
    # typ "sprawdź kurs ręcznie w STS" mylił sekcję Zawodnicy (rodzynek bez
    # kursu chował zakładki pewniaki/value), a wartość STS niesie skaner
    # Value Betów (sts_value + sts_model), nie sugestie. Przełącznik zamiast
    # kasowania kodu — łatwy powrót, gdyby decyzja się zmieniła.
    SUGESTIE_STS_WLACZONE = False

    def _push_sugestia(pid, mk, info, lam, p_over, line, extra, stare_dane=False):
        nonlocal vb_id
        if not SUGESTIE_STS_WLACZONE:
            return
        vb_id += 1
        rec = {
            "id": vb_id, "mecz_id": info["mid"], "mecz": info["match"],
            "kickoff_ts": info["ts"], "podmiot_typ": "zawodnik",
            "podmiot_id": pid, "podmiot": info["name"], "druzyna": info["team"],
            "przeciwnik": info["opp"],
            "rynek_kod": mk, "rynek": MARKET_NAMES_PL[mk],
            "linia": line, "strona": "powyzej",
            "sugestia": True,                      # <-- brak kursu, sprawdź w STS
            "kurs": None, "bukmacher": "STS (sprawdź ręcznie)",
            "p_model": round(p_over, 4), "p_rynku": None,
            "fair_kurs": round(1.0 / max(p_over, 1e-6), 2),
            "edge_pp": None, "ev_pct": None,
            "rank_score": p_over,                  # sortowanie sugestii po szansie
            "lambda": round(lam, 3),
            **extra,
        }
        # brama jakości (liga): sugestia na starych danych tylko w tle
        if stare_dane:
            rec["poza_publikacja"] = "stare_dane"
            typy_poza_publikacja.append(rec)
            return
        value_bets.append(rec)
        _zapewnij_mecz(info["mid"])["okazje"].append(vb_id)

    for (pid, mk), real in real_split.items():
        sm_r, dist_r = real["sm"], real["dist"]
        if sm_r.lam < 0.5:
            continue
        # STS wystawia kilka linii ("1 lub więcej", "2 lub więcej"...) —
        # emitujemy KAŻDĄ, przy której model daje >= 50% szans (z rozkładu)
        for linia_s in (0.5, 1.5, 2.5, 3.5):
            thr = int(linia_s) + 1  # "powyżej 1.5" = X >= 2
            p_over_l = float(sum(dist_r[thr:])) if thr < len(dist_r) else 0.0
            # kalibracja sugestii z ich własnych rozliczeń (rozkład jej nie ma)
            p_over_l = apply_bias(bias_map_sug.get(mk, 1.0), p_over_l)
            # progi PO kalibracji podniesione z 0.50/0.38: rozliczenia pokazały,
            # że sugestie p<0.60 trafiały 37.8%, a p>=0.70 — 100% (mała próba,
            # ale kierunek jasny) — mniej pozycji, za to grywalnych
            if p_over_l < (0.60 if linia_s == 0.5 else 0.45):
                break
            _push_sugestia(pid, mk, real["info"], sm_r.lam, p_over_l, linia_s, {
                "pewnosc": "srednia", "pewnosc_score": 45.0, "ryzyko": "wysokie",
                "ci": [sm_r.ci_low, sm_r.ci_high],
                "oczekiwane_minuty": sm_r.expected_minutes,
                "rozklad": dist_r, "czynniki": sm_r.factors,
                "uzasadnienie": sm_r.reasoning,
            }, stare_dane=real.get("stare_dane", False))

    # --- RYNKI DRUŻYNOWE: strzały / celne / kartki (historia: statshub
    # team-trends, ~20 meczów) + faule (bank stylu, mecze MŚ). Kursy Superbetu
    # (TEAM_MARKET_SUFFIX) są już w sb_cache. Legi drużynowe wchodzą do
    # legi_pool tymi samymi progami co zawodnicze i płyną dalej istniejącą
    # ścieżką pewniaków/kuponów; rozliczanie: scores365.game_team_stats.
    druzyny_forma: dict[int, dict] = {}  # forma drużyn z legami (dla UI)
    try:
        # zakres drużynowy: w lidze rynki drużynowe liczymy WYŁĄCZNIE dla
        # rozgrywek z profilem druzynowe=True (top 5 + Ekstraklasa + puchary,
        # decyzja zakresu 2026-07-20); w MŚ — wszystkie mecze jak dotąd
        ids_tt = [e["id"] for e in events]
        if tryb:
            ids_tt = [i for i in ids_tt if i in tryb.druzynowe_mids]
            print(f"Rynki drużynowe: {len(ids_tt)}/{len(events)} meczów "
                  "w zakresie drużynowym")
        try:
            team_trends = statshub.fetch_team_trends(ids_tt) if ids_tt else []
        except Exception as e:
            team_trends = []
            print(f"team-trends niedostępne ({e})")

        TEAM_POLE_BANKU = {
            "team_shots": "shots", "team_sot": "sot",
            "team_fouls": "fouls", "team_cards": "kartki",
            # rożne są w banku (game_team_stats id 8); goli bank nie ma —
            # nieistniejące pole daje None i uczciwe fallbacki (średnia
            # z historii trendu, czynnik rywala 1.0)
            "team_corners": "corners", "team_goals": "gole",
        }
        gry_banku = list((bank_stylu.get("gry") or {}).values())
        # skala poziomu zależy WYŁĄCZNIE od rynku, a `_hist_z_banku` woła ją
        # dla każdej drużyny osobno — bez pamięci przemiatałaby cały bank
        # (kilka tysięcy meczów) raz na drużynę i rynek
        _skala_cache: dict[str, float] = {}

        def _skala_poziomu(pole: str) -> float:
            """Ile razy ten sam wskaźnik jest wyższy w rozgrywkach zakresu niż
            w meczach dociągniętych własną ścieżką (niższe ligi beniaminków).

            Bierzemy stosunek średnich, nie różnicę — jest bezwymiarowy, więc
            odporny na to, czy mowa o rożnych, faulach czy strzałach. Przy
            chudej próbce ściągamy go w stronę 1,0 wagą n/(n+8): beniaminek
            zwykle słabnie po awansie, ale jednego meczu nie wolno brać za
            dowód poziomu ligi.
            """
            if pole in _skala_cache:
                return _skala_cache[pole]
            zakres, wlasne = [], []
            for rec_g in gry_banku:
                cel = wlasne if rec_g.get("wlasna") else zakres
                for d in (rec_g.get("druzyny") or {}).values():
                    if d.get(pole) is not None:
                        cel.append(float(d[pole]))
            skala = 1.0
            if len(wlasne) >= 2 and zakres:
                sr_w = sum(wlasne) / len(wlasne)
                if sr_w > 0:
                    raw = (sum(zakres) / len(zakres)) / sr_w
                    waga_w = len(wlasne) / (len(wlasne) + 8.0)
                    skala = float(np.clip(1.0 + (raw - 1.0) * waga_w, 0.70, 1.40))
            _skala_cache[pole] = skala
            return skala

        # nazwa ze statshub -> klucze w banku (365Scores); patrz
        # `zbuduj_aliasy_banku` — bez tego połowa drużyn „nie istniała"
        aliasy_banku: dict = (bank_stylu.get("alias") or {})

        def _klucze_banku(team_nm: str) -> list[str]:
            tn = rotowire._norm(team_nm)
            return [tn, *(aliasy_banku.get(tn) or ())]

        def _hist_z_banku(team_nm: str, pole: str) -> tuple[list, list]:
            klucze = _klucze_banku(team_nm)
            skala = _skala_poziomu(pole)
            pary = []
            for rec_g in gry_banku:
                dr = rec_g.get("druzyny") or {}
                # historia bywa ROZBITA na dwa zapisy tej samej drużyny —
                # bierzemy pierwszy klucz obecny w tym meczu, nigdy dwa naraz
                tn = next((k for k in klucze if k in dr), None)
                if tn is not None and dr[tn].get(pole) is not None:
                    # mecz z niższej ligi liczy się, ale przeliczony na poziom
                    # rozgrywek, w których drużyna gra TERAZ
                    mnoznik = skala if rec_g.get("wlasna") else 1.0
                    pary.append((int(rec_g.get("ts") or 0),
                                 float(dr[tn][pole]) * mnoznik))
            pary.sort(key=lambda x: -x[0])
            return [c for _, c in pary], [t for t, _ in pary]

        def _srednia_turnieju(pole: str) -> tuple[float | None, int]:
            vals = [
                float(d[pole])
                for rec_g in gry_banku
                for d in (rec_g.get("druzyny") or {}).values()
                if d.get(pole) is not None
            ]
            return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

        def _koncesja_druzynowa(opp_nm: str, pole: str) -> tuple[float | None, int]:
            """Ile tej statystyki notują PRZECIW rywalowi jego przeciwnicy."""
            klucze = _klucze_banku(opp_nm)
            vals = []
            for rec_g in gry_banku:
                dr = rec_g.get("druzyny") or {}
                tn = next((k for k in klucze if k in dr), None)
                if tn is not None and len(dr) == 2:
                    inny = next(k for k in dr if k != tn)
                    v = dr[inny].get(pole)
                    if v is not None:
                        vals.append(float(v))
            return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

        # --- RYNKI DRUŻYNOWE Z WŁASNEGO BANKU (rozszerzone 2026-07-27) ---
        # Sonda statshub na 129 meczach (1590 rekordów team-trends): feed niesie
        # WYŁĄCZNIE `goals` i `cornerKicks`. Kartek, strzałów, celnych i fauli
        # drużynowych nie ma tam wcale — czyli tą drogą nowy rynek nie przyjdzie.
        #
        # Ale obie brakujące połówki mamy u siebie:
        #   * LINIA I KURS — Superbet kwotuje je CZYSTO (sonda 8 meczów klubowych
        #     2026-07-27: kartki 8/8 meczów po ~6,6 linii, celne 8/8 po ~4,4,
        #     strzały 6/8 po ~4, faule 4/8 po jednej linii),
        #   * HISTORIA — bank stylu ligowego (475 meczów, 950 rekordów
        #     drużyna-mecz): kartki 86,7% pokrycia, strzały 97,6%, celne 94,3%,
        #     faule 71,4%.
        # Reszta ścieżki (kalibracja, czynnik rywala, sędzia, matchup, mostki,
        # rozliczanie z game_team_stats) już te kody rynków zna — brakowało
        # jedynie samego trendu. Budujemy go tu, dokładnie tak jak dotąd dla
        # fauli, i dalej wszystko płynie istniejącą ścieżką.
        #
        # UWAGA: nowy rynek startuje BEZ historii rozliczeń, więc przez pierwsze
        # ~2 tygodnie nie chroni go ani kwarantanna rynku (KWARANTANNA_MIN_N=15),
        # ani kalibracja (bias=1.0). Leci na surowym modelu — dlatego dokładamy
        # je świadomie i patrzymy na pierwsze rozliczenia.
        RYNKI_Z_BANKU = (
            ("team_cards", "kartki"),
            ("team_sot", "sot"),
            ("team_shots", "shots"),
            ("team_fouls", "fouls"),
        )
        # próg zgodny z bramą głównej pętli (`len(tt.counts) < 5`) — budowanie
        # trendu z 3 meczów tylko po to, żeby odpaść oczko dalej, zaciemniało
        # diagnostykę licznikiem `krotka_historia`
        MIN_HIST_BANKU = 5
        widziane_tt = {(t.event_id, t.team_id, t.market_code) for t in team_trends}
        syntetyczne_tt: Counter = Counter()
        for e in wszystkie_ev:
            if tryb and e["id"] not in tryb.druzynowe_mids:
                continue  # zakres drużynowy (jw.), gdy bank ligowy powstanie
            lid_e = int(e.get("uniqueTournamentId") or 0)
            for tid_e, opp_e, is_home_e in (
                (e["homeTeamId"], e["awayTeamId"], True),
                (e["awayTeamId"], e["homeTeamId"], False),
            ):
                nm_e = team_name.get(tid_e, "")
                if not nm_e:
                    continue
                for mk_e, pole_e in RYNKI_Z_BANKU:
                    # feed ma pierwszeństwo: jego historia niesie id rywali
                    # i miejsce gry, więc jest bogatsza niż nasza z banku
                    if (e["id"], tid_e, mk_e) in widziane_tt:
                        continue
                    c_f, t_f = _hist_z_banku(nm_e, pole_e)
                    if len(c_f) < MIN_HIST_BANKU:
                        continue
                    team_trends.append(statshub.TeamTrend(
                        team_id=tid_e, team_name=nm_e,
                        opponent_name=team_name.get(opp_e, ""),
                        opponent_id=int(opp_e or 0),
                        event_id=e["id"], is_home=is_home_e,
                        league_id=lid_e,
                        market_code=mk_e, line=0.0,
                        counts=c_f, timestamps=t_f,
                    ))
                    syntetyczne_tt[mk_e] += 1
        if syntetyczne_tt:
            print("Trendy drużynowe z własnego banku: "
                  + ", ".join(f"{k}={v}" for k, v in sorted(syntetyczne_tt.items())))

        # --- TRZECIE ŹRÓDŁO: HISTORIA DRUŻYNY WPROST ZE STATSHUBA (2026-08-04)
        #
        # Dwa poprzednie mają tę samą dziurę: feed `props/team-trends` jest
        # lustrem ofert bukmacherów UK, a bank stylu rośnie z meczów, które
        # sami przeskanowaliśmy. W PRZERWIE LETNIEJ ligi oba stoją puste.
        #
        # Zmierzone na Sparcie Praga – Lyonie (kwalifikacje LM, komplet kursów,
        # ZERO typów): model widział dla Sparty 0 meczów w oknie czterech
        # miesięcy i odrzucał ją jako `za_stara_historia`. `/team/{id}/
        # performance` ma dla niej 9 w tym oknie i 40 w ogóle — komplet sześciu
        # rynków, razem z golami i rożnymi, których bank nie zna.
        #
        # Kolejność źródeł zostaje: feed pierwszy (niesie linie i kursy
        # referencyjne), bank drugi, to trzecie. Dokładamy WYŁĄCZNIE brakujące
        # pary (mecz, drużyna, rynek), więc nic nie nadpisujemy.
        z_performance: Counter = Counter()
        cache_hist: dict[int, dict] = {}
        _perf_rekordy: dict[int, list] = {}
        budzet_tp = [MAX_TEAM_PERF_CYKL]

        def _perf(tid: int) -> list:
            """Surowa historia drużyny, pobrana RAZ na cykl i dzielona przez
            oba zastosowania: własne statystyki i profil rywala."""
            tid = int(tid)
            if tid not in _perf_rekordy:
                if budzet_tp[0] <= 0:
                    return []
                budzet_tp[0] -= 1
                _perf_rekordy[tid] = statshub.fetch_team_performance(tid)
            return _perf_rekordy[tid]

        # PROFIL DRUŻYNY PAMIĘTANY MIĘDZY CYKLAMI (2026-08-07).
        #
        # Ile drużyna NOTUJE i ile DOPUSZCZA — z `opponentStatistics`, które
        # feed niesie w każdym rekordzie historii. To domyka dziurę: czynnik
        # rywala braliśmy z `recentGames` feedu propsów, czyli z lustra oferty
        # bukmacherów UK, więc dla Ekstraklasy, kwalifikacji i części Ameryki
        # Południowej wychodził 1,00 (zmierzone 07.08: komplet czynników miało
        # 18 ze 134 kandydatów).
        #
        # DLACZEGO PAMIĘTANY, A NIE LICZONY CO CYKL: pierwsza wersja pytała
        # o historię przy każdym przebiegu i wydłużyła dry-run z ~15 do ~23
        # minut przy twardym limicie 35. Profil starzeje się wolno (drużyny
        # grają co 3–7 dni), więc odświeżamy najwyżej raz na dobę — to ścina
        # ~95% zapytań wobec pytania w każdym cyklu, a cykl czyta gotowe liczby.
        _profil_raw, _profil_ok = supa.get_key_ok(PROFIL_DRUZYN_KLUCZ)
        _profil_mag = [_profil_raw or {}]
        _profil_licz = Counter()

        def _profil_druzyny(tid) -> dict | None:
            """Profil drużyny: z pamięci, a gdy stary — odświeżony z feedu."""
            if not tid:
                return None
            p = profil_druzyn.pobierz(_profil_mag[0], tid)
            if not profil_druzyn.wymaga_odswiezenia(p, now_t):
                _profil_licz["z_pamieci"] += 1
                return p
            rek = _perf(abs(int(tid)))
            if not rek:
                # budżet wyczerpany albo feed milczy — stary profil jest lepszy
                # niż brak profilu, bo alternatywą jest czynnik rywala 1,00
                _profil_licz["bez_odswiezenia"] += 1
                return p
            nowy = profil_druzyn.zbuduj(
                abs(int(tid)), rek, now_t, statshub.TEAM_PERF_MAP
            )
            if not nowy:
                _profil_licz["za_chuda_historia"] += 1
                return p
            _profil_mag[0] = profil_druzyn.scal(_profil_mag[0], tid, nowy)
            _profil_licz["odswiezone"] += 1
            return nowy
        for e in wszystkie_ev:
            if tryb and e["id"] not in tryb.druzynowe_mids:
                continue
            lid_e = int(e.get("uniqueTournamentId") or 0)
            for tid_e, opp_e, is_home_e in (
                (e["homeTeamId"], e["awayTeamId"], True),
                (e["awayTeamId"], e["homeTeamId"], False),
            ):
                nm_e = team_name.get(tid_e, "")
                if not nm_e or not tid_e:
                    continue
                braki = [
                    mk for mk in statshub.TEAM_PERF_MAP.values()
                    if (e["id"], tid_e, mk) not in widziane_tt
                ] + ([] if (e["id"], tid_e, "team_goals") in widziane_tt
                     else ["team_goals"])
                if not braki:
                    continue
                if tid_e not in cache_hist:
                    rek_e = _perf(tid_e)
                    if not rek_e:
                        continue
                    cache_hist[tid_e] = statshub.historia_druzyny(
                        int(tid_e), rek_e
                    )
                hist_e = cache_hist.get(tid_e) or {}
                for mk_e in braki:
                    dane = hist_e.get(mk_e)
                    if not dane or len(dane[0]) < MIN_HIST_BANKU:
                        continue
                    c_p, t_p, opp_p, oppid_p, dom_p = dane
                    team_trends.append(statshub.TeamTrend(
                        team_id=tid_e, team_name=nm_e,
                        opponent_name=team_name.get(opp_e, ""),
                        opponent_id=int(opp_e or 0),
                        event_id=e["id"], is_home=is_home_e,
                        league_id=lid_e,
                        market_code=mk_e, line=0.0,
                        counts=c_p, timestamps=t_p,
                        game_opponents=opp_p, game_opponent_ids=oppid_p,
                        game_is_home=dom_p,
                    ))
                    widziane_tt.add((e["id"], tid_e, mk_e))
                    z_performance[mk_e] += 1
        if z_performance:
            print("Trendy drużynowe z historii statshuba: "
                  + ", ".join(f"{k}={v}" for k, v in sorted(z_performance.items()))
                  + f" ({len(cache_hist)} drużyn"
                  + (", budżet wyczerpany" if budzet_tp[0] <= 0 else "") + ")")

        # KONTEKST Z FEEDU — w lidze bank stylu bywa młody/pusty, a recentGames
        # CAŁEGO feedu team-trends to duża próbka: liczymy z niej średnią ligi
        # (norma rynku) i koncesje rywala (co drużyny notują PRZECIW niemu).
        # Dedup po (drużyna, rynek, timestamp) — ten sam mecz nie liczy się 2x.
        liga_probki: dict[tuple[int, str], list[float]] = {}
        # (rywal_id, rynek) -> [(wartość, ts)] — ts do wagi świeżości koncesji
        koncesje_feed: dict[tuple[int, str], list[tuple[float, int]]] = {}
        # (drużyna_id, rynek) -> własne wartości (mostek: atak rywala -> kartki)
        wlasne_feed: dict[tuple[int, str], list[float]] = {}
        seen_gra: set = set()
        for tt in team_trends:
            # NIE ZIPUJEMY PO `game_opponent_ids` (naprawa 2026-08-03).
            #
            # Trend zbudowany z NASZEGO banku (kartki, strzały, celne, faule —
            # feed ich dla klubów nie wystawia) nie zna id rywali, więc ta lista
            # jest pusta. `zip` ucina po najkrótszej, czyli te trendy wnosiły
            # do normy ligowej DOKŁADNIE ZERO próbek — cicho, bez śladu.
            #
            # Skutek był konkretny: `lg_feed` nigdy nie zbierał wymaganych 30
            # obserwacji, więc poziom bazowy dla kartek spadał na ŚREDNIĄ
            # CAŁEGO BANKU, mieszając ligi. Zmierzone 03.08 na drużynach
            # najbliższych meczów: Superliga duńska 1,05 kartki na drużynę-mecz,
            # Brasileirão B 2,56, a wspólny prior 1,93 — czyli duński zespół
            # startował z liczbą prawie dwukrotnie zawyżoną, i to przy rynku,
            # na którym i tak zawyżamy ([[lambda-per-rynek]]).
            #
            # Koncesje rywala zostają warunkowe: bez id rywala nie ma czego
            # przypisać, ale norma ligi i własne próbki są policzalne zawsze.
            for i_g, (v_g, ts_g) in enumerate(zip(tt.counts, tt.timestamps)):
                opp_g = (
                    tt.game_opponent_ids[i_g]
                    if i_g < len(tt.game_opponent_ids) else 0
                )
                k_g = (tt.team_id, tt.market_code, ts_g)
                if k_g in seen_gra:
                    continue
                seen_gra.add(k_g)
                liga_probki.setdefault(
                    (tt.league_id, tt.market_code), []
                ).append(v_g)
                wlasne_feed.setdefault(
                    (tt.team_id, tt.market_code), []
                ).append(v_g)
                if opp_g:
                    koncesje_feed.setdefault(
                        (opp_g, tt.market_code), []
                    ).append((v_g, ts_g))

        # świeżość koncesji z feedu: tau 45 dni — ZAŁOŻENIE (rytm ligowy to
        # mecz co ~tydzień; 14 dni z koncesje.py jest strojone pod turniej
        # i zabiłoby próbę), do kalibracji po rozliczeniach cykli jak marża UK
        KONCESJE_FEED_TAU_DNI = 45.0

        # ILE TYPÓW DOSTAŁO PROFIL RYWALA Z POMIARU, a nie z przybliżenia —
        # licznik, bo do 07.08 brak kontekstu rywala wyglądał identycznie jak
        # „rywal przeciętny" (czynnik 1,00) i nie zostawiał śladu.
        _konc_zmierzone: Counter = Counter()

        def _konc_feed_srednia(kf: list[tuple[float, int]]) -> float:
            """Płaska średnia koncesji (do korekty historii — bez świeżości)."""
            return float(np.mean([v for v, _ in kf]))

        # MOSTKI MIĘDZY STATYSTYKAMI: skorelowany rynek jako miękki sygnał —
        # rywal dopuszczający dużo strzałów zwykle dopuszcza i rożne, a mocno
        # strzelający rywal wymusza faule i kartki. Tłumienie pierwiastkiem +
        # shrink + ciasny cap: mostek dopycha obraz, nigdy go nie maluje.
        MOSTKI = {
            # rynek typu -> (rynek pokrewny, źródło: koncesje rywala / jego gra)
            "team_corners": ("team_shots", "koncesje"),
            "team_goals": ("team_sot", "koncesje"),
            "team_cards": ("team_shots", "wlasne"),
            "team_fouls": ("team_shots", "wlasne"),
        }

        def _mostek(mk_t: str, opp_id: int, lid: int) -> float:
            para = MOSTKI.get(mk_t)
            if not para or not opp_id:
                return 1.0
            mk_zr, zrodlo = para
            if zrodlo == "koncesje":
                probki = [v for v, _ in (koncesje_feed.get((opp_id, mk_zr)) or [])]
            else:
                probki = wlasne_feed.get((opp_id, mk_zr)) or []
            lg_zr = liga_probki.get((lid, mk_zr)) or []
            if len(probki) < 4 or len(lg_zr) < 30:
                return 1.0
            norma_zr = float(np.mean(lg_zr))
            if norma_zr <= 0:
                return 1.0
            raw = float(np.sqrt(float(np.mean(probki)) / norma_zr))
            return float(np.clip(
                context.shrink_factor(raw, len(probki), 10.0), 0.92, 1.10
            ))

        # ostatni mecz drużyn per liga (mediana) — jak u zawodników:
        # rozróżnienie "ta drużyna nie gra" od "cała liga pauzowała"
        liga_teamy: dict[int, dict[int, int]] = {}
        for tt0 in team_trends:
            maks0 = max((t for t in tt0.timestamps if t > 0), default=0)
            if maks0:
                slot0 = liga_teamy.setdefault(tt0.league_id, {})
                if maks0 > slot0.get(tt0.team_id, 0):
                    slot0[tt0.team_id] = maks0
        mediana_ligi_ts = {
            lid: sorted(m.values())[len(m) // 2]
            for lid, m in liga_teamy.items() if m
        }

        n_team = 0
        pomiar_druzyn = 0   # własny budżet typów pomiarowych, patrz wyżej
        seen_team = set()
        odpadki_t: Counter = Counter()  # diagnostyka: czemu legi drużynowe nie powstają
        # (mecz, rynek) -> {"home": {...}, "away": {...}} pod „kto więcej"
        # i sumy meczowe; wypełniane w pętli niżej
        predykcje_druzyn: dict[tuple[int, str], dict] = {}
        for tt in team_trends:
            klucz_t = (tt.event_id, tt.team_id, tt.market_code)
            if klucz_t in seen_team or tt.event_id not in ev_by_id:
                continue
            seen_team.add(klucz_t)
            ev = ev_by_id[tt.event_id]
            mid = tt.event_id
            ts = ev.get("timeStartTimestamp") or int(time.time())
            home_name = team_name.get(ev.get("homeTeamId"), "")
            away_name = team_name.get(ev.get("awayTeamId"), "")
            match_label = f"{home_name} – {away_name}"
            sb_odds = sb_cache.get(mid)
            if sb_odds is None and sb_events:
                # mecz z trendami DRUŻYNOWYMI bez zawodniczych nie przeszedł
                # przez pętlę główną, więc nikt nie pobrał jego kursów —
                # typowy przypadek: kwalifikacje pucharów (propsów
                # zawodniczych brak, gole/rożne drużynowe są). Dociągamy.
                if tryb:
                    sb_ev = tryb.sb_ev_by_mid.get(mid)
                else:
                    sb_ev = superbet.match_superbet_event(
                        sb_events, home_name, away_name, ts
                    )
                if sb_ev:
                    parts = [p.strip()
                             for p in (sb_ev.get("matchName") or "·").split("·")]
                    try:
                        sb_odds = superbet.fetch_stat_odds(
                            sb_ev["eventId"], parts[0], parts[1]
                        )
                    except Exception:
                        sb_odds = {"players": {}, "teams": {}}
                else:
                    sb_odds = {"players": {}, "teams": {}}
                sb_cache[mid] = sb_odds
                # tempo z tych samych kursów — f_script niżej z niego korzysta
                tempo_cache[mid] = tempo.tempo_from_match_odds(sb_odds.get("match"))
            sb_odds = sb_odds or {}
            linie_t = (
                sb_odds.get("teams", {})
                .get("home" if tt.is_home else "away", {})
                .get(tt.market_code, {})
            )
            if not linie_t:
                odpadki_t["brak_kursu"] += 1
                _odrzuc_druzyne(mid, tt, "brak_kursu",
                                "Superbet nie kwotuje tego rynku dla drużyny")
                continue
            if len(tt.counts) < 5:
                odpadki_t["krotka_historia"] += 1
                _odrzuc_druzyne(mid, tt, "krotka_historia",
                                f"tylko {len(tt.counts)} meczów w historii "
                                "(potrzeba 5)")
                continue
            pole = TEAM_POLE_BANKU[tt.market_code]
            lg_mean, _lg_n = _srednia_turnieju(pole)
            # liga: norma rynku z feedu (bank turniejowy tu nie istnieje)
            lg_feed = liga_probki.get((tt.league_id, tt.market_code)) or []
            if len(lg_feed) >= 30:
                lg_mean = float(np.mean(lg_feed))
            if lg_mean is None:
                lg_mean = float(np.mean(tt.counts))
            prior_t = counts.GroupPrior(
                mean_per90=max(lg_mean, 0.5), pseudo_matches=4.0
            )
            now_t = int(time.time())
            # ⚑ TWARDY SUFIT WIEKU HISTORII (2026-08-11).
            #
            # `fit_posterior` waży mecze wykładniczo (tau 180 dni), więc do
            # SAMEJ PROGNOZY mecz sprzed czterech lat i tak wnosi ułamek
            # promila — to nie tam był problem. Problem jest wszędzie indziej,
            # bo `tt.counts[:20]` bierze dwadzieścia ostatnich REKORDÓW, nie
            # dwadzieścia ostatnich meczów: średnia w uzasadnieniu, historia
            # rozpisana na karcie („ostatnie mecze"), kontrola rozjazdu bazy
            # i pomiar `srednia_hist` liczyły się z archiwum. Zmierzone tego
            # dnia na dumpie dry-runu: Bolívar miał w próbie rzuty rożne
            # z października 2020, Raków gole od sierpnia 2022 — 186 z ~960
            # meczów historii goli było starszych niż 400 dni.
            #
            # Klient czytał więc na karcie „w ostatnich meczach", patrząc na
            # spotkania sprzed pięciu lat, w zupełnie innym składzie.
            #
            # Sufit, a NIE okno o stałej długości: drużyna z pucharów gra
            # sześć razy w sezonie i okno „ostatnie 180 dni" zabrałoby jej
            # historię w całości. Osiemnaście miesięcy przepuszcza dwa pełne
            # sezony rozgrywek i odcina to, co i tak waży zero.
            _sufit_ts = now_t - MAX_WIEK_HISTORII_DRUZYNY_S
            # MASKA, NIE PREFIKS — i to nie jest nadgorliwość. `historia_druzyny`
            # sortuje malejąco jawnie (statshub.py), ale GŁÓWNE źródło trendów
            # to `fetch_team_trends`, gdzie kolejność `recentGames` jest taka,
            # jaką odda feed, i nic w naszym kodzie jej nie porządkuje.
            # Zmierzone przy wprowadzaniu: 86 z 86 serii przyszło posortowanych,
            # więc prefiks DZIŚ dawał ten sam wynik — ale opierałby całą maskę
            # wieku na obietnicy cudzego API. Przy odwróconej serii prefiks
            # wpuściłby dokładnie te mecze, które ma odciąć.
            _idx = [
                i for i in range(min(len(tt.counts), 20))
                if i >= len(tt.timestamps) or tt.timestamps[i] >= _sufit_ts
            ]
            if len(_idx) < min(len(tt.counts), 20):
                odpadki_t["historia_przycieta_wiekiem"] += 1
            n_h = len(_idx)
            if n_h < MIN_HISTORII_PO_PRZYCIECIU:
                # Nie „ten rynek jest zły" — po prostu nie mamy czym liczyć.
                # Rekord odrzucenia trafia do rejestru, więc za tydzień widać,
                # ilu meczów nam brakuje i gdzie dociągnąć dane, zamiast tylko
                # tego, że typów jest mało (patrz zasada: żadnych cichych
                # odrzuceń).
                odpadki_t["historia_za_stara"] += 1
                _odrzuc_druzyne(
                    mid, tt, "historia_za_stara",
                    f"tylko {n_h} meczów z ostatnich 18 miesięcy "
                    f"(w feedzie {len(tt.counts)}, reszta starsza)"
                )
                continue
            # KOREKTA KALENDARZA: każdy mecz historii sprowadzamy do warunków
            # neutralnych — dzielimy przez to, co tamten rywal przeciętnie
            # dopuszcza (koncesje feedu, ten sam shrink+cap co czynnik rywala)
            # i przez stały efekt miejsca gry (game_is_home z feedu). Baza
            # przestaje dziedziczyć łatwy/trudny terminarz i nadmiar meczów
            # u siebie; kontekst NADCHODZĄCEGO meczu nakłada potem f_opp
            # i f_venue — bez podwójnego liczenia, bo historia jest już czysta.
            hist_t: list[float] = []
            for i_g in _idx:
                mnoznik_gry = 1.0
                oid_g = (
                    tt.game_opponent_ids[i_g]
                    if i_g < len(tt.game_opponent_ids) else 0
                )
                kf_g = (
                    koncesje_feed.get((oid_g, tt.market_code)) if oid_g else None
                )
                if kf_g and len(kf_g) >= 4 and lg_mean:
                    mnoznik_gry *= context.cap(
                        context.shrink_factor(
                            _konc_feed_srednia(kf_g) / lg_mean, len(kf_g), 12.0
                        ),
                        context.CAP_OPPONENT,
                    )
                if i_g < len(tt.game_is_home):
                    mnoznik_gry *= context.home_away_factor(
                        tt.game_is_home[i_g], tt.market_code
                    )
                hist_t.append(float(tt.counts[i_g]) / max(mnoznik_gry, 0.5))
            _ts_h = [
                tt.timestamps[i] if i < len(tt.timestamps) else now_t
                for i in _idx
            ]
            posterior_t = counts.fit_posterior(
                np.array(hist_t),
                np.array([90.0] * n_h),
                np.array([
                    max((now_t - t) / 86400.0, 0.0) for t in _ts_h
                ]),
                prior=prior_t,
            )
            sed_t = sedzia_by_mid.get(mid) or {}
            dyscyplinarny = tt.market_code in ("team_fouls", "team_cards")
            # kartki mają WŁASNY profil arbitra (nie ten z fauli) — patrz
            # `sedzia_dla_rynku`; przy chudej próbie wraca stary mnożnik
            mn_sed, n_sed = sedzia_dla_rynku(sed_t, tt.market_code)
            f_sedzia = context.referee_factor(
                mn_sed, n_sed, market_is_disciplinary=dyscyplinarny,
            )
            tempo_m = tempo_cache.get(mid) or {}
            spread_home = tempo_m.get("spread")
            spread_teamu = (
                spread_home if tt.is_home else -spread_home
            ) if spread_home is not None else None
            f_script = context.game_script_factor(
                spread_teamu, tempo_m.get("total"), tt.market_code,
                bool(spread_teamu is not None and spread_teamu > 0.15),
            )
            konc, konc_n = _koncesja_druzynowa(tt.opponent_name, pole)
            # KONCESJE ZMIERZONE U ŹRÓDŁA (2026-08-07) — drugie w kolejności,
            # przed feedem. Bank stylu zostaje pierwszy, bo jest zbudowany
            # z meczów, które sami przeskanowaliśmy; ale tam, gdzie go nie ma,
            # dotąd schodziliśmy na `recentGames` z feedu propsów, czyli na
            # lustro oferty bukmacherów UK. Dla Ekstraklasy, kwalifikacji
            # pucharów i części Ameryki Południowej tego lustra nie ma wcale
            # i czynnik rywala wychodził 1,00 — zmierzone 07.08: komplet
            # czynników miało 18 ze 134 kandydatów.
            #
            # `opponentStatistics` przychodzi w KAŻDYM rekordzie historii
            # drużyny, w każdej lidze, i jest pomiarem, nie przybliżeniem.
            # Zmierzone na 3018 obserwacjach: „ile rywal dopuszcza" to
            # najsilniejsza pojedyncza zależność w każdym z pięciu rynków
            # drużynowych, a dołożenie jej zmniejsza błąd o 5–15%.
            if konc is None and tt.opponent_id:
                km, km_n = profil_druzyn.wartosc(
                    _profil_druzyny(tt.opponent_id), tt.market_code, "dopuszcza"
                )
                if km is not None:
                    konc, konc_n = km, km_n
                    _konc_zmierzone[tt.market_code] += 1
            if konc is None:
                # koncesje z feedu: co drużyny notują przeciw temu rywalowi,
                # ważone świeżością (mecz sprzed tygodnia > sprzed 3 miesięcy)
                # — spójnie z koncesje.py dla zawodników
                kf = koncesje_feed.get((tt.opponent_id, tt.market_code)) or []
                if len(kf) >= 4:
                    wagi_kf = np.exp(
                        -np.maximum(
                            now_t - np.array([t for _, t in kf], dtype=float),
                            0.0,
                        ) / 86400.0 / KONCESJE_FEED_TAU_DNI
                    )
                    # feed miewa eventTimestamp=0 -> waga ~0; przy zdegenerowanych
                    # wagach wracamy do płaskiej średniej zamiast NaN
                    konc = (
                        float(np.average([v for v, _ in kf], weights=wagi_kf))
                        if float(np.sum(wagi_kf)) > 1e-9
                        else _konc_feed_srednia(kf)
                    )
                    konc_n = len(kf)
            f_opp = (
                context.opponent_factor(konc, lg_mean, konc_n)
                if konc is not None and lg_mean else 1.0
            )
            # dom/wyjazd: gospodarze wykonują więcej rożnych/strzałów/goli,
            # goście łapią więcej kartek — dotąd sekcja drużynowa to gubiła
            f_venue = context.home_away_factor(tt.is_home, tt.market_code)
            # matchup drużynowy: styl rywala z banku shotmap (głęboki blok,
            # pressing, kontry) + mostek ze skorelowanej statystyki feedu
            ostyle_t = None
            try:
                ostyle_t = style_turnieju.opponent(tt.opponent_name)
            except Exception:
                ostyle_t = None  # bank stylu pusty/pominięty -> neutralnie
            f_matchup_t, opis_matchup_t = (1.0, None)
            if ostyle_t is not None:
                f_matchup_t, opis_matchup_t = matchup.matchup_factor_druzyny(
                    tt.market_code, ostyle_t,
                    is_favourite=bool(
                        spread_teamu is not None and spread_teamu > 0.15
                    ),
                )
            f_mostek_t = _mostek(tt.market_code, tt.opponent_id, tt.league_id)
            f_styl_t = float(np.clip(f_matchup_t * f_mostek_t, 0.85, 1.20))
            factor_t = f_sedzia * f_script * f_opp * f_venue * f_styl_t
            srednia_hist = float(np.mean([tt.counts[i] for i in _idx]))
            # brama jakości (liga) także dla drużyn: historia klubu sprzed
            # przerwy/awansu podlega tym samym progom co zawodnicza
            stare_t = False
            if tryb and tt.timestamps:
                n_sw_t, dni_ost_t = swiezosc_proby(
                    tt.timestamps, [90.0] * len(tt.timestamps), now_t
                )
                if n_sw_t < MIN_MECZE_W_OKNIE:
                    odpadki_t["za_stara_historia"] += 1
                    _odrzuc_druzyne(mid, tt, "za_stara_historia",
                                    f"tylko {n_sw_t} meczów w ostatnich "
                                    "4 miesiącach")
                    continue
                stare_t = dni_ost_t * 86400 > STARE_DANE_S
                if stare_t:
                    med = mediana_ligi_ts.get(tt.league_id, 0)
                    if med and (now_t - med) / 86400.0 >= dni_ost_t - 14.0:
                        stare_t = False  # pauzowała cała liga, nie ta drużyna
            pred_t = counts.predict_match(posterior_t, 90.0, factor_t)
            # PREDYKCJE OBU DRUŻYN POD NOWE RYNKI (2026-07-30). „Kto więcej"
            # i suma meczowa potrzebują rozkładów OBU drużyn naraz, a ta pętla
            # widzi je osobno (jeden obrót = jedna drużyna). Odkładamy więc
            # rozkłady i przetwarzamy je PO pętli, gdy komplet jest pewny.
            _slot_t = "home" if tt.team_id == ev.get("homeTeamId") else "away"
            predykcje_druzyn.setdefault((mid, tt.market_code), {})[_slot_t] = {
                "pred": pred_t, "nazwa": tt.team_name, "team_id": tt.team_id,
                "mecz": match_label, "ts": ts, "stare": stare_t,
                "home_name": home_name, "away_name": away_name,
                # posterior potrzebny do PRZEDZIAŁU nowych rynków (2026-07-31):
                # brama drużynowa decyduje o „p ostrożnym", a bez posteriora
                # nie było czym go policzyć — patrz counts.przedzial_sumy
                "posterior": posterior_t,
                # MNOŻNIKI TEJ DRUŻYNY — bez nich suma meczowa i „kto więcej"
                # wychodziły z `czynniki: {}`, czyli formalnie BEZ rachunku.
                # To nie było kosmetyczne: brama uzasadnień
                # (`betting.ma_komplet_uzasadnienia`) patrzy właśnie na to pole,
                # więc każdy typ na sumie poniżej 70% szansy wypadał z listy jako
                # „bez uzasadnienia" — mimo że model policzył wszystko, tylko
                # nigdzie tego nie zapisał (audyt 05.08, znalezisko nr 7).
                "czynniki": {
                    "rywal": round(f_opp, 3), "sedzia": round(f_sedzia, 3),
                    "dom_wyjazd": round(f_venue, 3),
                    "scenariusz_meczu": round(f_script, 3),
                    "matchup": round(f_styl_t, 3),
                    "lacznie": round(factor_t, 3),
                },
            }
            # KALIBRACJA rynków drużynowych: bias był dla nich LICZONY
            # (team_corners −0,466, team_goals −0,254), ale nigdy nie
            # docierał do p — ścieżka drużynowa jako jedyna nie przekazywała
            # go dalej. Stosujemy go tu, na p_over, żeby strona "poniżej"
            # pozostała jego dokładnym dopełnieniem.
            # sama kalibracja rynku; korekta strumienia leci NIŻEJ, na stronie
            # którą faktycznie typujemy (patrz `_korekta_strony`)
            bias_t = bias_map.get(tt.market_code, 1.0)
            for l_t, slot_t in sorted(linie_t.items()):
                # KOREKTA ZAWSZE NA „POWYŻEJ", NIGDY NA WYBRANEJ STRONIE
                # (poprawka 2026-07-30). Model ma pełny rozkład, więc szansa
                # „poniżej" jest z definicji lustrem: p_under = 1 − p_over.
                # Dokładanie korekty do strony, którą typujemy, łamało tę
                # tożsamość — obie strony tej samej linii dostawały liczby,
                # które się nie sumują do jedynki.
                #
                # POMIAR, KTÓRY TO ROZSTRZYGNĄŁ (30.07, 108 rozliczonych
                # typów drużynowych):
                #     „powyżej"  mówiliśmy 74%, weszło 59%  ROI −15%
                #     „poniżej"  mówiliśmy 72%, weszło 69%  ROI  +8%
                # Błąd NIE jest symetryczny: strona „poniżej" jest prawie
                # dokładna. Poprzednie założenie („przeszacowujemy to, co
                # publikujemy, niezależnie od strony") jest tym obalone —
                # symetryczna korekta psuła dobrą stronę i za słabo ruszała
                # złą. Źródłem jest zawyżona przewidywana liczba zdarzeń,
                # a ona podbija „powyżej" i zaniża „poniżej" jednym ruchem,
                # więc jedna korekta na „powyżej" naprawia obie strony.
                _bias_t_pelny = _dodaj_delte(
                    bias_t, korekta_strumieni.get("druzyny", 0.0)
                )
                _p_over_sur_t = pred_t.p_over(l_t)
                p_over_t = apply_bias(_bias_t_pelny, _p_over_sur_t)
                # DELTA KALIBRACJI RYNKU FAKTYCZNIE UŻYTA DLA TEGO TYPU
                # (2026-08-11, warunek wdrożenia V2). `kal_strumien` zapisuje
                # tylko część strumieniową; części rynkowej nie zapisywał NIKT,
                # więc `_p_surowe` potrafiło odwrócić jedną z dwóch nałożonych
                # korekt, a `compute_bias_full` uczyło się na `p`, z którego nie
                # dało się zdjąć własnej poprzedniej delty. Stempel zamyka tę
                # lukę OD PIERWSZEGO REKORDU V2 — bez niego przebudowa pętli
                # regulatora znów nie miałaby na czym się oprzeć.
                _kal_rynek_t = betting.delta_dla_p(bias_t, _p_over_sur_t)
                lo_o, hi_o = counts.p_over_credible_interval(
                    posterior_t, 90.0, factor_t, l_t
                )
                # PRZEDZIAŁ W TEJ SAMEJ SKALI CO p (2026-07-27). Bramą
                # publikacji jest `p_dec_t = (p + lo)/2`, więc korygowanie
                # samego `p` przy surowym `lo` rozjeżdżało obie liczby:
                # im mocniejsza korekta, tym bardziej brama ją rozwadniała.
                # Ścieżka zawodnicza kalibruje CI od dawna (engine._kalibruj).
                lo_o = apply_bias(_bias_t_pelny, lo_o)
                hi_o = apply_bias(_bias_t_pelny, hi_o)
                # obie strony linii: Superbet kwotuje over i under, a model ma
                # pełny rozkład — "poniżej" to lustro szansy "powyżej"
                for strona_t, klucz_odds in (
                    ("powyzej", "over"), ("ponizej", "under")
                ):
                    odd_t = (slot_t or {}).get(klucz_odds)
                    if not odd_t:
                        continue
                    if strona_t == "powyzej":
                        p_t, lo_t, hi_t = p_over_t, lo_o, hi_o
                    else:
                        p_t, lo_t, hi_t = 1.0 - p_over_t, 1.0 - hi_o, 1.0 - lo_o
                    # KOREKTA STRUMIENIA — patrz `_p_over_t_kor` wyżej.
                    # Od 2026-07-30 stosowana do „powyżej", a „poniżej" jest
                    # jej LUSTREM; nie dokładamy jej drugi raz do wybranej
                    # strony, bo to łamało tożsamość p_under = 1 − p_over.
                    implied_t = betting.implied_prob_one_sided(odd_t)
                    # jak po stronie zawodniczej: decyduje p ostrożne
                    p_dec_t = (p_t + lo_t) / 2.0
                    if not betting.widelki_druzynowe_ok(odd_t, p_t, p_dec_t):
                        # ROZDZIELONA DIAGNOSTYKA (2026-07-27): trzy warunki
                        # miały dotąd jeden licznik, więc te 1372 odrzucenia
                        # nie mówiły, CO właściwie tnie. Patrz betting.
                        # WIDELKI_DRUZYNOWE — to najbardziej kosztowna brama
                        # w systemie i jedyna nigdy niezweryfikowana.
                        powod_w = betting.powod_widelek(odd_t, p_t, p_dec_t)
                        odpadki_t[powod_w] += 1
                        _odrzuc_druzyne(
                            mid, tt, powod_w,
                            f"{STRONA_PL.get(strona_t, strona_t)} {l_t} "
                            f"@{odd_t}: szansa modelu {p_t:.0%} "
                            + POWODY_WIDELEK_PL[powod_w],
                        )
                        # POMIAR PROGU: typ, który minął się z bramą niewiele,
                        # rozlicza się w tle jako `odrzucony` — poza kalibracją,
                        # skutecznością i UI. Za miesiąc porównamy jego wynik
                        # z przepuszczonymi i dopiero wtedy ruszymy liczby.
                        if (
                            betting.widelki_druzynowe_blisko(odd_t, p_t, p_dec_t)
                            and pomiar_druzyn < ODRZUCONE_POMIAR_DRUZYN_MAX
                        ):
                            pomiar_druzyn += 1
                            odrzucone_pomiar.append({
                                "id": 0, "mecz_id": mid, "mecz": match_label,
                                "kickoff_ts": ts, "podmiot_typ": "druzyna",
                                # DODATNI, mimo że klucz diagnostyczny wyżej
                                # (`_odrzuc_druzyne`) używa minusa: ten rekord
                                # idzie do KSIĘGI, a stamtąd numer wracał na
                                # stronę i rozjeżdżał tożsamość klubu — patrz
                                # `rozliczanie._znak_podmiotu`.
                                "podmiot_id": abs(int(tt.team_id or 0)),
                                "podmiot": tt.team_name,
                                "rynek_kod": tt.market_code,
                                "rynek": MARKET_NAMES_PL.get(
                                    tt.market_code, tt.market_code
                                ),
                                "linia": l_t, "strona": strona_t,
                                "kurs": odd_t, "bukmacher": "Superbet",
                                "p_model": round(p_t, 4),
                                "pewnosc": "srednia",
                                "sugestia": False,
                                "odrzucony": True,
                                "odrzucenie_powod": powod_w,
                            })
                        continue
                    if (hi_t - lo_t) > 0.35:
                        odpadki_t["chwiejna_predykcja"] += 1
                        _odrzuc_druzyne(
                            mid, tt, "chwiejna_predykcja",
                            f"{STRONA_PL.get(strona_t, strona_t)} {l_t}: "
                            f"przedział szansy {lo_t:.0%}–{hi_t:.0%} za szeroki",
                        )
                        continue
                    if abs(p_t - implied_t) > betting.MAX_MODEL_MARKET_DIVERGENCE:
                        odpadki_t["rozjazd_z_rynkiem"] += 1
                        _odrzuc_druzyne(
                            mid, tt, "rozjazd_z_rynkiem",
                            f"{STRONA_PL.get(strona_t, strona_t)} {l_t}: model "
                            f"{p_t:.0%} vs rynek {implied_t:.0%}",
                        )
                        continue
                    if implied_t > 0 and p_t / implied_t > betting.MAX_RELATIVE_DIVERGENCE:
                        odpadki_t["rozjazd_z_rynkiem"] += 1
                        _odrzuc_druzyne(
                            mid, tt, "rozjazd_z_rynkiem",
                            f"{STRONA_PL.get(strona_t, strona_t)} {l_t}: model "
                            f"{p_t:.0%} to {p_t / implied_t:.1f}× wycena rynku",
                        )
                        continue
                    ev_uk_t = kurs_ref_t = None
                    if (
                        tt.ref_odds and abs(l_t - tt.line) < 1e-6
                        and tt.odds_type == klucz_odds
                    ):
                        kurs_ref_t = round(statistics.median(tt.ref_odds), 2)
                        nv_t = betting.no_vig_prob_uk(tt.ref_odds)
                        if nv_t:
                            ev_uk_t = round((nv_t[0] * odd_t - 1.0) * 100.0, 1)
                    czynniki_t = []
                    # liczby w opisach po polsku (przecinek) — teksty idą 1:1 do UI
                    sr_t = f"{srednia_hist:.1f}".replace(".", ",")
                    sr5_txt = ""
                    if len(tt.counts) >= 5:
                        sr5 = float(np.mean(tt.counts[:5]))
                        sr5_txt = f", ostatnie 5 meczów: {sr5:.1f}".replace(".", ",")
                    # korekta kalendarza/prior widocznie ruszyły bazę ->
                    # mówimy to wprost. Liczba = baza, od której model
                    # REALNIE startuje (posterior per-90 = lambda/czynniki),
                    # nie surowa średnia po korekcie — inaczej proza "liczy
                    # od 1,1 … zostaje 1,7" kłóciła się sama ze sobą, bo
                    # gubiła krok "krótka próba ściągana do normy ligi"
                    # (karta Larne, 2026-07-21)
                    kor_txt = ""
                    baza_start = (
                        float(pred_t.lam) / factor_t if factor_t else srednia_hist
                    )
                    if abs(baza_start - srednia_hist) > 0.03 * max(srednia_hist, 0.1):
                        kor_txt = (
                            f"; po korekcie na siłę rywali i miejsce gry oraz "
                            f"zderzeniu krótkiej próby z normą ligi model "
                            f"startuje od {baza_start:.1f}"
                        ).replace(".", ",")
                    czynniki_t.append({
                        "nazwa": "Poziom bazowy",
                        "opis": f"Średnio {sr_t} na mecz "
                                f"(próba: {n_h} meczów{sr5_txt}){kor_txt}",
                        "mnoznik": None,
                    })
                    if abs(f_opp - 1.0) > 0.02:
                        konc_s = f"{konc:.1f}".replace(".", ",")
                        norma_s = f"{lg_mean:.1f}".replace(".", ",")
                        czynniki_t.append({
                            "nazwa": "Profil rywala",
                            "opis": f"Drużyny notują przeciw {tt.opponent_name} "
                                    f"średnio {konc_s} przy normie ligi {norma_s} "
                                    f"(próba: {konc_n} meczów)",
                            "mnoznik": round(f_opp, 2),
                        })
                    if abs(f_venue - 1.0) > 0.02:
                        czynniki_t.append({
                            "nazwa": "Dom i wyjazd",
                            "opis": ("Gra u siebie" if tt.is_home
                                     else "Gra na wyjeździe")
                            + (", to zwykle pomaga w tej statystyce"
                               if f_venue > 1
                               else ", to zwykle obniża tę statystykę"),
                            "mnoznik": round(f_venue, 2),
                        })
                    if abs(f_styl_t - 1.0) > 0.02:
                        czynniki_t.append({
                            "nazwa": "Styl rywala",
                            "opis": opis_matchup_t or (
                                "Skorelowane statystyki rywala "
                                + ("sprzyjają temu rynkowi" if f_styl_t > 1
                                   else "nie sprzyjają temu rynkowi")
                            ),
                            "mnoznik": round(f_styl_t, 2),
                        })
                    if abs(f_sedzia - 1.0) > 0.02 and sed_t.get("sedzia"):
                        czynniki_t.append({
                            "nazwa": "Sędzia",
                            "opis": f"{sed_t['sedzia']}: "
                                    f"{'surowy' if f_sedzia > 1 else 'pobłażliwy'}",
                            "mnoznik": round(f_sedzia, 2),
                        })
                    if abs(f_script - 1.0) > 0.02:
                        czynniki_t.append({
                            "nazwa": "Scenariusz meczu",
                            "opis": "Z kursów meczowych: przewidywany przebieg "
                                    + ("sprzyja" if f_script > 1 else "nie sprzyja"),
                            "mnoznik": round(f_script, 2),
                        })
                    legi_pool.append({
                        "id": 0, "mecz_id": mid, "mecz": match_label,
                        "kickoff_ts": ts, "podmiot_id": tt.team_id,
                        "podmiot": tt.team_name, "druzyna": tt.team_name,
                        "przeciwnik": tt.opponent_name,
                        "podmiot_typ": "druzyna",
                        "rynek_kod": tt.market_code,
                        "rynek": MARKET_NAMES_PL[tt.market_code],
                        "linia": l_t, "strona": strona_t, "kurs": odd_t,
                        "bukmacher": "Superbet", "p_model": round(p_t, 4),
                        "ev_pct": round(betting.ev_brutto_pct(p_t, odd_t), 1),
                        "ev_netto": round(betting.ev_pct(p_t, odd_t), 1),
                        "tryb_podatku": betting.tryb_podatku("Superbet"),
                        "ev_uk": ev_uk_t, "kurs_ref": kurs_ref_t,
                        "pewnosc": "wysoka" if (hi_t - lo_t) <= 0.18 else "srednia",
                        "matchup": bool(f_opp >= 1.12),
                        "matchup_styl": bool(f_styl_t >= 1.08),
                        "rotacja": False, "xi_sygnal": None,
                        "swieze_sklady": mid in swieze_mids,
                        "stare_dane": stare_t,
                        "miekka_linia": False, "kurs_oczekiwany": None,
                        "ci": [round(lo_t, 4), round(hi_t, 4)],
                        "oczekiwane_minuty": None,
                        # ILE Z TEJ PROGNOZY JEST NASZE (2026-08-11).
                        # `fit_posterior` waży mecze wykładniczo (tau 180 dni),
                        # więc archiwum sprzed lat prawie nie wchodzi — ale
                        # zamiast niego wchodzi PRIOR, czyli średnia ligi.
                        # Zmierzone tego dnia na dumpie dry-runu: Boca Juniors
                        # ma efektywną próbę 1,97 z dwunastu meczów, więc 67%
                        # jego prognozy to zdanie „przeciętna drużyna w tej
                        # lidze notuje tyle" — a nic w rekordzie tego nie
                        # mówiło. `counts.MIN_EFFECTIVE_MATCHES` istnieje od
                        # początku i NIE JEST NIGDZIE UŻYWANY.
                        #
                        # Stempel, nie brama: dopiero rozliczenia pokażą, czy
                        # typy stojące na priorze wypadają gorzej. Bez zapisu
                        # to pytanie jest niemierzalne wstecz (ta sama lekcja
                        # co przy `lambda` — patrz rozliczanie._dopisz_nowe).
                        # delta kalibracji RYNKU użyta dla tego typu — patrz
                        # `_kal_rynek_t`. Razem z `kal_strumien` daje komplet
                        # tego, co nałożono na surowe `p_over`.
                        "kal_rynek": round(float(_kal_rynek_t), 4),
                        # ...i to samo w jednym słowniku, wspólnym formacie dla
                        # WSZYSTKICH strumieni (betting.stempel_rachunku).
                        # `kal_rynek` wyżej zostaje dla zgodności z rekordami
                        # zapisanymi między 11 a 12.08.
                        "rachunek": betting.stempel_rachunku(
                            p_over_raw=_p_over_sur_t,
                            kal_rynek=_kal_rynek_t,
                            kal_strumien=betting.delta_dla_p(
                                korekta_strumieni.get("druzyny", 0.0),
                                _p_over_sur_t,
                            ),
                            p_over_final=p_over_t,
                        ),
                        "ess": round(float(posterior_t.effective_matches), 2),
                        "udzial_priora": round(
                            prior_t.pseudo_matches
                            / (prior_t.pseudo_matches
                               + max(float(posterior_t.effective_matches), 0.0)),
                            3,
                        ),
                        "ryzyko": betting.risk_level(pred_t.lam, False, 1.0),
                        "czynniki": {
                            "rywal": round(f_opp, 3), "sedzia": round(f_sedzia, 3),
                            "dom_wyjazd": round(f_venue, 3),
                            "scenariusz_meczu": round(f_script, 3),
                            "matchup": round(f_styl_t, 3),
                            "lacznie": round(factor_t, 3), "opisy": {},
                        },
                        "uzasadnienie": {
                            "czynniki": czynniki_t,
                            "oczekiwana_liczba": round(float(pred_t.lam), 2),
                            "rynek_rzadki": False,
                        },
                        "lambda": round(float(pred_t.lam), 3),
                        # surowa historia predykcji — do kalibracji tau
                        # (pamięci formy drużyn) z własnych rozliczeń:
                        # jobs/kalibracja_tau.py odtwarza z tego posterior
                        # przy różnych tau i mierzy Briera na wynikach
                        "kal_tau": {
                            "hist": [round(h, 2) for h in hist_t],
                            "ts": [int(x) for x in _ts_h],
                            "factor": round(factor_t, 4),
                            "prior": round(float(lg_mean), 3),
                        },
                    })
                    n_team += 1
                    # forma drużyny do UI (karta typu: ostatnie mecze tego rynku)
                    f_slot = druzyny_forma.setdefault(tt.team_id, {
                        "id": tt.team_id, "nazwa": tt.team_name,
                        "druzyna": tt.team_name, "podmiot_typ": "druzyna",
                        "forma": {},
                    })
                    if tt.market_code not in f_slot["forma"]:
                        # TYLE, ILE ZOSTAŁO PO SUFICIE WIEKU (patrz `n_h`).
                        # To jest karta, którą czyta człowiek: „ostatnie mecze"
                        # muszą być ostatnimi meczami, a nie ostatnimi
                        # rekordami w feedzie. Przed tą zmianą karta Bolívara
                        # pokazywała rzuty rożne z 2020 roku pod nagłówkiem
                        # „ostatnio".
                        # te same indeksy co likelihood — jedna maska wieku
                        # na cały rekord, bez drugiego, rozjeżdżającego się
                        # przycięcia dla UI
                        n_f = len(_idx)

                        def _po_idx(seq, dom=None):
                            return [
                                seq[i] for i in _idx if i < len(seq)
                            ] if seq else ([] if dom is None else dom)

                        f_slot["forma"][tt.market_code] = {
                            "ostatnie": [int(c) for c in _po_idx(tt.counts)],
                            # mecz drużyny = zawsze pełne 90 (okna formy w UI
                            # filtrują po minutach > 0)
                            "minuty": [90] * n_f,
                            "rywale": [
                                str(o) for o in _po_idx(tt.game_opponents)
                            ],
                            "ts": [int(t) for t in _ts_h],
                            "dom": [
                                bool(h) for h in _po_idx(tt.game_is_home)
                            ],
                            "srednia90": round(
                                float(np.mean([tt.counts[i] for i in _idx])), 2
                            ) if n_f else 0.0,
                        }
        # === NOWE RYNKI: „KTO WIĘCEJ" I SUMA MECZOWA (2026-07-30) ===
        # Wchodzą PO pętli, bo potrzebują rozkładów OBU drużyn naraz, a pętla
        # widzi je osobno. Rozliczanie tych rynków powstało WCZEŚNIEJ niż
        # publikacja (rozliczanie.MARKETY_SUMY / MARKETY_WIECEJ) — nie
        # wystawiamy niczego, czego nie umiemy zamknąć.
        n_wiecej = n_sumy = 0
        odpadki_nowe: Counter = Counter()

        def _do_puli_nowych(rec: dict) -> None:
            """Sumy meczowe i „kto więcej" też są legami kuponu (2026-08-04).

            ZMIERZONE tego dnia — pula kuponów i lista typów rozjechały się
            całkowicie:

                lista:  20 typów, średnia szansa 71,2%
                pula:   24 legi,  średnia szansa 59,0%
                wspólnych: 4

            Na liście stało 12 typów o szansie 74–91% przy kursach 1,26–1,65
            (kartki meczowe, gole drużyny) — czyli DOKŁADNIE materiał, którego
            kupon dzienny potrzebuje. Żaden nie był dostępny dla kuponów, bo te
            dwa rynki dopisują się do listy własną ścieżką i nigdy nie trafiały
            do `legi_pool`.

            Skutek widoczny dla użytkownika: zakładka „Kupony → na dziś"
            świeciła zerem, bo w oknie dziennym zostawało 6 legów, z czego
            5 „ryzykownych" (szansa < 55%), a profil zbalansowany dopuszcza
            jeden taki. Trzy kartki meczowe z listy złożyłyby się na kurs 2,20
            przy szansie ~71%.

            To ta sama klasa błędu co kwarantanny omijane przez te rynki
            (naprawione tego samego dnia): nowa ścieżka publikacji dopisana
            obok głównej nie widzi mechanizmów, które główna ma.
            """
            legi_pool.append({**rec, "id": 0})
        for (mid_n, mk_n), strony_n in predykcje_druzyn.items():
            if "home" not in strony_n or "away" not in strony_n:
                odpadki_nowe["tylko jedna druzyna"] += 1
                continue
            h_n, a_n = strony_n["home"], strony_n["away"]
            if h_n["stare"] or a_n["stare"]:
                odpadki_nowe["stare dane"] += 1
                continue
            oferta_n = sb_cache.get(mid_n) or {}
            ts_n = h_n["ts"]
            if ts_n <= int(time.time()) + kupony.MARGINES_STARTU_S:
                odpadki_nowe["za pozno"] += 1
                continue
            baza_n = mk_n.replace("team_", "")
            # „Rzuty rożne drużyny" -> „Rzuty rożne": przy sumie meczowej
            # i przy „kto więcej" słowo „drużyny" jest zbędne i czyta się źle
            # („Rzuty rożne drużyny w meczu")
            nazwa_bazy = MARKET_NAMES_PL.get(mk_n, mk_n)
            for _ogon in (" drużyny", " drużyn"):
                if nazwa_bazy.endswith(_ogon):
                    nazwa_bazy = nazwa_bazy[: -len(_ogon)]
                    break

            # --- „KTO WIĘCEJ": trzy wyniki, gramy TYLKO strony drużynowe ---
            # Remisu nie publikujemy (decyzja usera), ale jest policzony i
            # odjęty — bez tego szansa drużyny wyszłaby zawyżona nawet o 19 pp
            # (kartki). Patrz rozliczanie.STRONY_WIECEJ.
            # ZMIERZONA KORELACJA MIĘDZY DRUŻYNAMI (2026-08-01) — jedna liczba
            # na rynek, ta sama dla porównania i dla sumy, bo to ta sama para
            # liczb w tym samym meczu. Rynek bez pomiaru dostaje 0, czyli
            # liczy się dokładnie jak dotąd. Patrz counts.KORELACJA_DRUZYN.
            rho_n = counts.korelacja_rynku(mk_n)
            kursy_w = (oferta_n.get("porownania") or {}).get(mk_n) or {}
            kod_w = "wiecej_" + baza_n
            if kursy_w and kod_w in rozliczanie.MARKETY_WIECEJ:
                p_h, p_remis, p_a = counts.porownanie_druzyn(
                    h_n["pred"], a_n["pred"], rho=rho_n
                )
                # PRZEDZIAŁ na P(kto więcej) — liczony RAZ na mecz+rynek,
                # osobno dla każdej strony (remis zjada masę po obu stronach,
                # więc strona gościa NIE jest dopełnieniem strony gospodarza)
                ci_w = {}
                try:
                    ci_w["gospodarz"] = counts.przedzial_porownania(
                        h_n["posterior"], h_n["pred"].exposure,
                        a_n["posterior"], a_n["pred"].exposure,
                        rho=rho_n,
                    )
                    ci_w["gosc"] = counts.przedzial_porownania(
                        a_n["posterior"], a_n["pred"].exposure,
                        h_n["posterior"], h_n["pred"].exposure,
                        rho=rho_n,
                    )
                except Exception:
                    ci_w = {}
                for strona_w, p_w, kurs_w, kto_w, rywal_w in (
                    ("gospodarz", p_h, kursy_w.get("home"),
                     h_n["nazwa"], a_n["nazwa"]),
                    ("gosc", p_a, kursy_w.get("away"),
                     a_n["nazwa"], h_n["nazwa"]),
                ):
                    if not kurs_w or float(kurs_w) <= 1.0:
                        continue
                    kurs_w = float(kurs_w)
                    ev_w = betting.ev_brutto_pct(p_w, kurs_w)
                    if ev_w < betting.MIN_EV_PCT:
                        odpadki_nowe["kto wiecej: brak wartosci"] += 1
                        continue
                    # === BRAMY JAKOŚCI (dopięte 2026-07-31) ===
                    # Do tej pory ten rynek przechodził WYŁĄCZNIE przez EV
                    # powyżej — bez widełek kursu, bez progu szansy, bez
                    # przedziału i bez okna zgody z rynkiem. Reszta systemu
                    # przechodzi przez komplet tych bram, a rozjazd był
                    # niezamierzony: rynek dopisano 30.07 osobną ścieżką.
                    lo_w, hi_w = ci_w.get(strona_w, (None, None))
                    if lo_w is None:
                        odpadki_nowe["kto wiecej: brak przedzialu"] += 1
                        continue
                    if hi_w - lo_w > betting.MAX_CI_WIDTH:
                        odpadki_nowe["kto wiecej: szeroki przedzial"] += 1
                        continue
                    p_dec_w = (p_w + lo_w) / 2.0
                    if not betting.widelki_druzynowe_ok(kurs_w, p_w, p_dec_w):
                        odpadki_nowe[
                            "kto wiecej: " + betting.powod_widelek(
                                kurs_w, p_w, p_dec_w)
                        ] += 1
                        continue
                    if not betting.w_oknie_zgody(p_w, kurs_w):
                        odpadki_nowe["kto wiecej: rozjazd z rynkiem"] += 1
                        continue
                    _kw_w = _kwarantanna_zdejmuje(
                        {"rynek_kod": kod_w, "strona": strona_w})
                    if _kw_w:
                        odpadki_nowe[f"kto wiecej: {_kw_w}"] += 1
                        continue
                    vb_id += 1
                    n_wiecej += 1
                    _rec_w = {
                        "id": vb_id, "mecz_id": mid_n, "mecz": h_n["mecz"],
                        "kickoff_ts": ts_n,
                        # podmiot ZAWSZE gospodarz — tak to rozlicza
                        # rozliczanie.MARKETY_WIECEJ
                        "podmiot_id": h_n["team_id"],
                        "podmiot": h_n["home_name"],
                        "podmiot_typ": "druzyna",
                        "druzyna": kto_w, "przeciwnik": rywal_w,
                        "rynek_kod": kod_w,
                        "rynek": "Więcej: " + nazwa_bazy.lower(),
                        "linia": 0, "strona": strona_w,
                        "kurs": float(kurs_w), "bukmacher": "Superbet",
                        "p_model": round(p_w, 4),
                        "p_rynku": betting.implied_prob_one_sided(
                            float(kurs_w)),
                        "fair_kurs": round(1.0 / max(p_w, 1e-6), 3),
                        "edge_pp": None,
                        "ev_pct": round(ev_w, 2),
                        "ev_netto": round(betting.ev_pct(p_w, kurs_w), 2),
                        "tryb_podatku": betting.tryb_podatku("Superbet"),
                        # PEWNOŚĆ Z PRZEDZIAŁU, nie z sufitu (2026-07-31).
                        # Wcześniej stało tu na sztywno „średnia / 50 pkt" —
                        # rynek podawał liczbę, której nie policzył, i to
                        # dokładnie w polu, po którym user filtruje listę.
                        # Próg 0,18 jak w rynkach drużynowych (linia 3616).
                        "pewnosc": "wysoka" if (hi_w - lo_w) <= 0.18
                                   else "srednia",
                        "pewnosc_score": round(
                            100.0 * max(0.0, 1.0 - (hi_w - lo_w) / 0.30), 1
                        ),
                        "ryzyko": betting.risk_level(
                            p_w, False, 1.0, is_prob_market=True
                        ),
                        "rank_score": round(ev_w, 3),
                        "ci": [round(lo_w, 4), round(hi_w, 4)],
                        "oczekiwane_minuty": None,
                        "lambda": round(h_n["pred"].lam, 3),
                        "rozklad": None, "sugestia": False,
                        "czynniki": mnozniki_pary(h_n, a_n),
                        # ⚑ „KTO WIĘCEJ" ZOSTAJE BEZ WARSTW UCZENIA — ŚWIADOMIE
                        # (rozstrzygnięte 12.08, przy wpinaniu ich do sum).
                        #
                        # To jest TRÓJMIAN: gospodarz / remis / gość, a
                        # `p_h + p_remis + p_a = 1`. Delta logitowa z naszych
                        # warstw jest zdefiniowana na `p_over` dwustronnego
                        # rynku — nałożona na jedną nogę trójmianu rozerwałaby
                        # tę sumę, czyli dokładnie ten błąd, dla którego cała
                        # kalibracja jedzie w orientacji „powyżej" (awaria
                        # odwróconego znaku, 11.08). `wiecej_*` nie ma zresztą
                        # wpisu w mapie kalibracji, bo nie ma czego tam liczyć.
                        #
                        # Zera są więc pomiarem, nie zaokrągleniem: mówią
                        # wprost, że ten rynek idzie bez warstw — i to zostaje
                        # do czasu, aż ktoś policzy korektę dla trójmianu.
                        # Dotyczy 17 rozliczeń bieżącej epoki.
                        "rachunek": betting.stempel_rachunku(
                            p_over_raw=p_w, kal_rynek=0.0, kal_strumien=0.0,
                            p_over_final=p_w,
                        ),
                        # ile zabiera remis — user ma to widzieć, bo przy
                        # kartkach to co piąty zakład
                        "p_remis": round(p_remis, 4),
                        "uzasadnienie": {
                            "czynniki": czynniki_pary(
                                h_n, a_n, nazwa_bazy, rho_n),
                            "oczekiwana_liczba": round(h_n["pred"].lam, 2),
                        },
                    }
                    value_bets.append(_rec_w)
                    _do_puli_nowych(_rec_w)

            # --- SUMA MECZOWA: linia i strony jak przy jednej drużynie ---
            kod_s = "match_" + baza_n
            linie_s = (oferta_n.get("sumy") or {}).get(kod_s) or {}
            if linie_s and kod_s in rozliczanie.MARKETY_SUMY:
                # JEDNA LINIA NA STRONĘ (2026-08-01). Ten rynek wystawiał
                # KAŻDĄ kwotowaną linię, więc jeden mecz potrafił dać pięć
                # wierszy „rożne w meczu poniżej" (6,5 / 7,5 / 13,5 / 14,5 /
                # 15,5) — a to jeden wynik meczu w pięciu przebraniach.
                # Zbieramy kandydatów i wystawiamy najlepszego po wartości;
                # patrz bliźniacza brama przy pewniakach niżej.
                kandydaci_s: dict[str, dict] = {}
                # ⚑ SUMA MECZOWA PRZECHODZI PRZEZ TE SAME WARSTWY CO DRUŻYNY
                # (2026-08-12). Do dziś ten rynek liczył `p` z SUROWYCH
                # rozkładów obu drużyn i szedł prosto do `p_model` — omijał
                # i kalibrację rynku, i korektę strumienia, bo
                # `korekta_strumieni` była wołana tylko w ścieżce zawodniczej,
                # drużynowej i drabinek. `match_corners` ma przy tym własną
                # kalibrację ze WSZYSTKICH czterech przedziałów, policzoną z
                # jego rozliczeń, i nigdy jej nie używał.
                #
                # ZMIERZONE na 95 rozliczeniach match_*/wiecej_* bieżącej epoki
                # (skala `p_over`):
                #     dziś                 Brier 0,1718   luka -7,9 pp
                #     + korekta strumienia Brier 0,1617   luka +1,2 pp
                #     + obie warstwy       Brier 0,1625   luka +1,2 pp
                # Sama kalibracja rynku wypadła neutralnie (-0,5%, czyli szum
                # przy tej próbie), ale wchodzi razem z drugą: różnica między
                # „samą korektą" a „obiema" jest w szumie, a JEDNOLITOŚĆ
                # ścieżek to realna wartość — dziś właśnie zapłaciliśmy za to,
                # że jedna ścieżka miała inny zestaw warstw niż reszta.
                #
                # Korekta leci na `p_over`, nie na wybraną stronę, żeby
                # „poniżej" zostało dokładnym dopełnieniem „powyżej" (patrz
                # pętla drużynowa i awaria odwróconego znaku z 11.08).
                _bias_s_pelny = _dodaj_delte(
                    bias_map.get(kod_s), korekta_strumieni.get("druzyny", 0.0)
                )
                for linia_s, slot_s in sorted(linie_s.items()):
                    _p_over_s_sur = counts.p_over_sumy(
                        h_n["pred"], a_n["pred"], float(linia_s), rho=rho_n
                    )
                    p_over_s = apply_bias(_bias_s_pelny, _p_over_s_sur)
                    _kal_rynek_s = betting.delta_dla_p(
                        bias_map.get(kod_s), _p_over_s_sur)
                    _kal_strum_s = betting.delta_dla_p(
                        korekta_strumieni.get("druzyny", 0.0), _p_over_s_sur)
                    # PRZEDZIAŁ liczony RAZ na linię, dla strony „powyżej";
                    # „poniżej" jest jego lustrem — tak samo jak w rynkach
                    # drużynowych (p_under = 1 − p_over, więc granice się
                    # zamieniają miejscami)
                    try:
                        lo_o_s, hi_o_s = counts.przedzial_sumy(
                            h_n["posterior"], h_n["pred"].exposure,
                            a_n["posterior"], a_n["pred"].exposure,
                            float(linia_s), rho=rho_n,
                        )
                        # ...i w TEJ SAMEJ skali co `p`, inaczej brama
                        # „p ostrożne" rozwadnia korektę (ta sama poprawka co
                        # w pętli drużynowej, 2026-07-27)
                        lo_o_s = apply_bias(_bias_s_pelny, lo_o_s)
                        hi_o_s = apply_bias(_bias_s_pelny, hi_o_s)
                    except Exception:
                        lo_o_s = hi_o_s = None
                    for strona_s, p_s, kurs_s in (
                        ("powyzej", p_over_s, slot_s.get("over")),
                        ("ponizej", 1.0 - p_over_s, slot_s.get("under")),
                    ):
                        if not kurs_s or float(kurs_s) <= 1.0:
                            continue
                        kurs_s = float(kurs_s)
                        ev_s = betting.ev_brutto_pct(p_s, kurs_s)
                        if ev_s < betting.MIN_EV_PCT:
                            continue
                        # === BRAMY JAKOŚCI (dopięte 2026-07-31) ===
                        # Ten rynek szedł na stronę na samym EV. Skutek
                        # zmierzony 31.07 na produkcji: 39 typów, kursy od
                        # 1,04, z czego 28 poniżej 1,136 — czyli poniżej
                        # granicy, za którą zakład traci NAWET przy pewności
                        # stuprocentowej (po podatku od stawki). Widełki
                        # kurs×szansa odcinają to jednym warunkiem.
                        if lo_o_s is None:
                            odpadki_nowe["suma: brak przedzialu"] += 1
                            continue
                        if strona_s == "powyzej":
                            lo_s, hi_s = lo_o_s, hi_o_s
                        else:
                            lo_s, hi_s = 1.0 - hi_o_s, 1.0 - lo_o_s
                        if hi_s - lo_s > betting.MAX_CI_WIDTH:
                            odpadki_nowe["suma: szeroki przedzial"] += 1
                            continue
                        p_dec_s = (p_s + lo_s) / 2.0
                        if not betting.widelki_druzynowe_ok(
                            kurs_s, p_s, p_dec_s
                        ):
                            odpadki_nowe[
                                "suma: " + betting.powod_widelek(
                                    kurs_s, p_s, p_dec_s)
                            ] += 1
                            continue
                        # ta sama brama co przy typach: poza oknem zgody
                        # z rynkiem nie publikujemy
                        if not betting.w_oknie_zgody(p_s, kurs_s):
                            odpadki_nowe["suma: rozjazd z rynkiem"] += 1
                            continue
                        _kw_s = _kwarantanna_zdejmuje(
                            {"rynek_kod": kod_s, "strona": strona_s})
                        if _kw_s:
                            odpadki_nowe[f"suma: {_kw_s}"] += 1
                            continue
                        poprzedni = kandydaci_s.get(strona_s)
                        if poprzedni is not None and poprzedni["ev_pct"] >= ev_s:
                            continue
                        kandydaci_s[strona_s] = ({
                            "id": 0, "mecz_id": mid_n, "mecz": h_n["mecz"],
                            "kickoff_ts": ts_n,
                            "podmiot_id": h_n["team_id"],
                            "podmiot": h_n["home_name"],
                            "podmiot_typ": "druzyna",
                            "druzyna": h_n["mecz"], "przeciwnik": "",
                            "rynek_kod": kod_s,
                            "rynek": nazwa_bazy + " w meczu",
                            "linia": float(linia_s), "strona": strona_s,
                            "kurs": float(kurs_s), "bukmacher": "Superbet",
                            "p_model": round(p_s, 4),
                            "p_rynku": betting.implied_prob_one_sided(
                                float(kurs_s)),
                            "fair_kurs": round(1.0 / max(p_s, 1e-6), 3),
                            "edge_pp": None,
                            "ev_pct": round(ev_s, 2),
                            "ev_netto": round(betting.ev_pct(p_s, kurs_s), 2),
                            "tryb_podatku": betting.tryb_podatku("Superbet"),
                            # pewność z przedziału, nie z sufitu — patrz
                            # bliźniaczy komentarz przy „kto więcej"
                            "pewnosc": "wysoka" if (hi_s - lo_s) <= 0.18
                                       else "srednia",
                            "pewnosc_score": round(
                                100.0 * max(0.0, 1.0 - (hi_s - lo_s) / 0.30), 1
                            ),
                            "ryzyko": betting.risk_level(
                                h_n["pred"].lam + a_n["pred"].lam, False, 1.0
                            ),
                            "rank_score": round(ev_s, 3),
                            "ci": [round(lo_s, 4), round(hi_s, 4)],
                            "oczekiwane_minuty": None,
                            "lambda": round(
                                h_n["pred"].lam + a_n["pred"].lam, 3),
                            "rozklad": None, "sugestia": False,
                            "czynniki": mnozniki_pary(h_n, a_n),
                            # od 12.08 ta ścieżka ma komplet warstw — patrz
                            # nota przy `_bias_s_pelny` wyżej
                            "rachunek": betting.stempel_rachunku(
                                p_over_raw=_p_over_s_sur,
                                kal_rynek=_kal_rynek_s,
                                kal_strumien=_kal_strum_s,
                                p_over_final=p_over_s,
                            ),
                            "uzasadnienie": {
                                "czynniki": czynniki_pary(
                                    h_n, a_n, nazwa_bazy, rho_n),
                                "oczekiwana_liczba": round(
                                    h_n["pred"].lam + a_n["pred"].lam, 2),
                            },
                        })
                # …i dopiero teraz wystawiamy po jednym na stronę
                for rec_s in kandydaci_s.values():
                    vb_id += 1
                    n_sumy += 1
                    rec_s["id"] = vb_id
                    value_bets.append(rec_s)
                    _do_puli_nowych(rec_s)
        if n_wiecej or n_sumy or odpadki_nowe:
            szczegoly = ", ".join(
                str(k) + "=" + str(v) for k, v in odpadki_nowe.most_common()
            )
            print("Nowe rynki: kto wiecej " + str(n_wiecej)
                  + ", sumy meczowe " + str(n_sumy)
                  + ("; odpadlo: " + szczegoly if odpadki_nowe else ""))

        if n_team or team_trends:
            print(f"Rynki drużynowe: +{n_team} legów w puli "
                  f"({len(team_trends)} trendów drużynowych)"
                  + (f"; odpadło: " + ", ".join(
                      f"{k}={v}" for k, v in odpadki_t.most_common())
                     if odpadki_t else ""))
            # NA CZYM STOJĄ TE LEGI — własna historia czy średnia ligi.
            # Bez tej linii nie da się odróżnić „model policzył tę drużynę"
            # od „model podstawił średnią rozgrywek i nazwał to prognozą".
            _ess = [
                float(l["ess"]) for l in legi_pool
                if l.get("podmiot_typ") == "druzyna" and l.get("ess") is not None
            ]
            if _ess:
                _ess_s = sorted(_ess)
                _chude = sum(
                    1 for e in _ess if e < counts.MIN_EFFECTIVE_MATCHES
                )
                print(
                    "Rynki drużynowe — na czym stoi prognoza: efektywna próba "
                    f"mediana {_ess_s[len(_ess_s) // 2]:.1f} meczów "
                    f"(min {_ess_s[0]:.1f}, max {_ess_s[-1]:.1f}); "
                    f"{_chude} z {len(_ess)} legów poniżej progu "
                    f"{counts.MIN_EFFECTIVE_MATCHES:.0f} — tam ponad połowę "
                    "prognozy wnosi średnia rozgrywek, nie ta drużyna"
                )
        if _konc_zmierzone:
            print("Profil rywala ZMIERZONY (z historii, nie z przybliżenia): "
                  + ", ".join(f"{k}={v}" for k, v
                              in _konc_zmierzone.most_common()))
        # ZAPIS PROFILU — te same zasady, co przy rejestrze publikacji:
        # nieudany odczyt oznacza „nie zapisuj", bo garstka drużyn z tego cyklu
        # nadpisałaby pamięć zbieraną tygodniami (patrz `supa.get_key_ok`).
        # `put_key_bezpiecznie` byłoby tu złym narzędziem: przycinanie martwych
        # drużyn z natury zmniejsza payload i bezpiecznik blokowałby zapis.
        if _profil_licz:
            print("Profil drużyn: "
                  + ", ".join(f"{k}={v}" for k, v in _profil_licz.most_common())
                  + f"; w pamięci {len((_profil_mag[0].get('druzyny') or {}))}")
        if not _profil_ok:
            print("UWAGA: odczyt profilu drużyn PADŁ — zapis pominięty, żeby "
                  "nie nadpisać pamięci; czynnik rywala jedzie w tym cyklu "
                  "ze źródeł zapasowych")
        elif _profil_licz.get("odswiezone") and not _dry_run():
            _profil_mag[0], _zeszlo_pd = profil_druzyn.przytnij(
                _profil_mag[0], now_t
            )
            if _zeszlo_pd:
                print(f"Profil drużyn: {_zeszlo_pd} drużyn zeszło z pamięci "
                      f"(brak meczu od {profil_druzyn.ROTACJA_DNI:.0f} dni)")
            if not supa.put_key(PROFIL_DRUZYN_KLUCZ, _profil_mag[0]):
                print("UWAGA: zapis profilu drużyn NIE POWIÓDŁ SIĘ — następny "
                      "cykl policzy te drużyny od nowa (koszt: zapytania, "
                      "nie dane)")
    except Exception as e:
        print(f"Rynki drużynowe pominięte ({e})")

    # --- SPÓJNOŚĆ KIERUNKU (decyzja usera 2026-07-25) ---
    # filtr na CAŁEJ puli, zanim rozejdzie się do pewniaków/kuponów/dumpów
    n_przed_sp = len(legi_pool)
    # kierunki już zamrożone w logu — bez nich filtr widzi tylko bieżący cykl
    # i przepuszcza kolizję rozłożoną na kilka dni (pomiar 2026-07-26)
    try:
        _log_publikacji = supa.get_key("typy_log") or {}
        kierunki_log = kierunki_opublikowane(_log_publikacji)
        # ...z tego samego odczytu: która LINIA zakładu jest już wystawiona
        # (patrz `linie_opublikowane` i brama niżej) — drugi odczyt księgi
        # kosztowałby kilkanaście megabajtów na cykl
        linie_log = linie_opublikowane(_log_publikacji)
        # ...i z tego samego odczytu: którą wersją policzono typ, który już
        # stoi w księdze (patrz `wersje_w_ksiedze` i brama kolizji niżej)
        wersje_log = wersje_w_ksiedze(_log_publikacji)
    except Exception as e:
        kierunki_log = {}
        linie_log = {}
        wersje_log = {}
        print(f"Spójność kierunku: log niedostępny ({e}) — tylko bieżąca pula")
    legi_pool = filtr_spojnosci_kierunku(legi_pool, kierunki_log)
    if len(legi_pool) < n_przed_sp:
        print(f"Spójność kierunku: usunięto {n_przed_sp - len(legi_pool)} "
              f"legów kolidujących z przeciwną stroną linii "
              f"(pula + {len(kierunki_log)} zamrożonych kierunków z logu)")

    # --- PEWNIAKI: najlepszy typ KAŻDEGO rynku dla każdego meczu ---
    # Nie top-N po samej szansie (wygrywałyby zawsze zwykłe strzały 0.5) —
    # użytkownik chce widzieć pełne spektrum statystyk: strzały, celne,
    # zza pola, celne zza pola, faule, wywalczone, odbiory, przechwyty...
    # Kandydaci przeszli pełny scoring + bezpieczniki rozbieżności.
    juz_opublikowane = {
        (b["podmiot_id"], b["rynek_kod"], b["linia"], b["strona"])
        for b in value_bets
    } | {
        # okazje/sugestie zdjęte przez bramę jakości — bez tego ten sam typ
        # trafiłby do logu drugi raz kanałem pewniaków
        (b["podmiot_id"], b["rynek_kod"], b["linia"], b["strona"])
        for b in typy_poza_publikacja
    }
    per_mecz_rynek: set[tuple[int, str]] = set()

    def _atrakcyjnosc(b: dict) -> float:
        """Ranking pewniaka: nie sama szansa (zawsze wygrywałaby linia 0,5),
        ale szansa × pierwiastek kursu, z bonusem za kontekst (profil rywala,
        wejście do XI) i karą za chwiejną predykcję (szerokie CI)."""
        ci = b.get("ci") or [None, None]
        ci_w = (ci[1] - ci[0]) if ci[0] is not None else 0.30
        r = b["p_model"] * (b["kurs"] ** 0.5)
        # premie tylko za kategorie, które NIE stoją w kwarantannie — inaczej
        # windujemy w rankingu dokładnie te typy, które udowodniły, że tracą
        if b.get("matchup") and "matchup" not in kwarantanna_kategorii:
            r *= 1.15
        if b.get("rotacja") and "rotacja" not in kwarantanna_kategorii:
            r *= 1.10
        if b.get("swieze_sklady"):
            r *= 1.12  # składy ogłoszone <45 min temu — kurs mógł nie zdążyć
        if b.get("miekka_linia") and "miekka_linia" not in kwarantanna_kategorii:
            r *= 1.10  # linia odstaje od własnej siatki buka (błąd tradera)
        if ci_w > 0.25:
            r *= 0.90
        return r

    def _kategoria_wstrzymana(b: dict) -> str | None:
        """Pierwsza flaga typu, która stoi w kwarantannie (albo None).

        POMIAR — mówi, z jakiej kategorii typ pochodzi. Czy to go zdejmuje
        z listy, decyduje `_kategoria_zdejmuje` niżej.
        """
        return next(
            (f for f in rozliczanie.KATEGORIE_KWARANTANNY
             if b.get(f) and f in kwarantanna_kategorii),
            None,
        )

    def _kategoria_zdejmuje(b: dict) -> str | None:
        """Czy kwarantanna KATEGORII zdejmuje typ z listy. Od 14.08: nie.

        Ta sama decyzja i ten sam pomiar co przy `_kwarantanna_zdejmuje`.
        Kategoria dalej jest liczona i dalej odbiera typowi premię
        w rankingu (patrz `_atrakcyjnosc`) — po prostu nie kasuje go z listy.
        """
        return _kategoria_wstrzymana(b) if KWARANTANNA_ZDEJMUJE_Z_LISTY else None

    # perełki: do 2 wpisów z wyższym kursem (>=2.0) per mecz, po wartości
    perelki_kandydaci = sorted(
        (b for b in legi_pool if b["kurs"] >= 1.90),
        key=lambda x: -(x["p_model"] * x["kurs"]),
    )
    perelki_per_mecz: dict[int, int] = {}
    do_emisji: list[dict] = []
    for b in sorted(legi_pool, key=lambda x: -_atrakcyjnosc(x)):
        if (b["mecz_id"], b["rynek_kod"]) in per_mecz_rynek:
            continue
        per_mecz_rynek.add((b["mecz_id"], b["rynek_kod"]))
        do_emisji.append(b)
    # WYŻSZE LINIE: ranking po samej szansie prawie zawsze wygrywa linia 0,5
    # — a w puli bywają perełki typu "strzały 1,5+" albo "odbiory 2,5+"
    # (kurs wyraźnie wyższy przy wciąż solidnej szansie). Per (mecz, rynek)
    # dokładamy najlepszego kandydata z linią >= 1,5 po jakości p×kurs.
    # ⚑ 14.08: kategoria w kwarantannie DALEJ dokłada kandydatów. Wcześniej
    # „ambitniejsza linia" w kwarantannie przestawała w ogóle powstawać —
    # czyli znikała nie tylko ze strony, ale i z pomiaru, więc brama nie miała
    # jak się nigdy odwrócić (typów brak → próba nie rośnie → kwarantanna
    # trwa). To był jedyny cichy samopodtrzymujący się wycinek w tym pliku,
    # ta sama pułapka co samozagładzanie kwarantanny w [[roznorodnosc-typow]].
    # Kategoria zostaje jako pomiar i odbiera premię w rankingu.
    wyzsze: dict[tuple[int, str], dict] = {}
    for b in ([] if (KWARANTANNA_ZDEJMUJE_Z_LISTY
                     and "wyzsza_linia" in kwarantanna_kategorii)
              else legi_pool):
        # przy kursie 1,9+ dopuszczamy "opcję ryzykowną" już od p>=40%
        # (format tipsterski: linia wyżej, kurs wyraźnie wyższy)
        prog_p = 0.40 if b["kurs"] >= 1.9 else 0.52
        # koncept dotyczy WYŁĄCZNIE strony "powyżej": dla undersów linia 3,5
        # to nie "ambitniejszy wariant", a werdykt "wyższa linia za lepszy
        # kurs" na karcie "poniżej 3,5" był bez sensu (Larne, 2026-07-21)
        if b.get("strona") == "ponizej" or b["linia"] < 1.5 or b["p_model"] < prog_p:
            continue
        kw = (b["mecz_id"], b["rynek_kod"])
        w = wyzsze.get(kw)
        if w is None or b["p_model"] * b["kurs"] > w["p_model"] * w["kurs"]:
            wyzsze[kw] = b
    for b in wyzsze.values():
        b["wyzsza_linia"] = True
        do_emisji.append(b)
    for b in perelki_kandydaci:
        if perelki_per_mecz.get(b["mecz_id"], 0) >= 2:
            continue
        perelki_per_mecz[b["mecz_id"]] = perelki_per_mecz.get(b["mecz_id"], 0) + 1
        do_emisji.append(b)
    # === JEDNA LINIA NA (mecz, rynek, podmiot, stronę) — 2026-08-01 ===
    #
    # Zgłoszenie usera: „czemu tu jest miliard typów?". Trzy kanały wyżej
    # (najlepszy per rynek, „wyższa linia", perełki) potrafiły wystawić tę samą
    # drużynę na tym samym rynku i tej samej stronie w kilku liniach naraz:
    #
    #   Motor Lublin  rożne drużyny poniżej  3,5 / 4,5 / 6,5
    #   Wisła Płock   rożne w meczu poniżej  6,5 / 7,5 / 13,5 / 14,5 / 15,5
    #
    # To NIE są osobne zakłady. Padło 6 rożnych — „poniżej 14,5", „poniżej 15,5"
    # i „poniżej 16,5" wchodzą razem, zawsze. Zmierzone na całej księdze:
    # 65% takich skupisk kończy się jednolitym wynikiem, a Skuteczność liczona
    # per wiersz pokazuje 57,1% trafień tam, gdzie per zdarzenie jest 53,0%
    # (zagnieżdżone „poniżej" dokładają tanie pewniaki).
    #
    # Rynki zawodnicze mają tę bramę od zawsze (`best_by_side`). Tu jej nie było.
    # Zostaje NAJATRAKCYJNIEJSZA linia — czyli „wyższa linia" i perełka nadal
    # wygrywają, gdy naprawdę są lepsze, ale nie DOKŁADAJĄ się do bazowej.
    najlepsza_na_strone: dict[tuple, dict] = {}
    for b in do_emisji:
        k_str = (b["mecz_id"], b["rynek_kod"], b.get("podmiot_id"), b["strona"])
        w = najlepsza_na_strone.get(k_str)
        if w is None or _atrakcyjnosc(b) > _atrakcyjnosc(w):
            najlepsza_na_strone[k_str] = b
    if len(najlepsza_na_strone) < len(do_emisji):
        print(f"Jedna linia na stronę: {len(do_emisji)} kandydatów -> "
              f"{len(najlepsza_na_strone)} (zdjęte zagnieżdżone linie tego "
              f"samego zakładu)")
    do_emisji = list(najlepsza_na_strone.values())
    # LIMIT EKSPOZYCJI NA MECZ ZDJĘTY Z LISTY 14.08 — liczby i powód przy
    # `MAX_PEWNIAKOW_MECZ`. Skrót: mecz z 5+ typami jest naszym NAJLEPSZYM
    # materiałem (ROI +8,3%, luka −5,3 pp), a sama brama i tak odpaliła raz
    # w całej księdze. Licznik zostaje, bo mówi, ile typów mecz już dostał —
    # z tego liczy się premia bogactwa w kolejności listy.
    # Typy zdjęte innymi bramami dalej się rozliczają i UCZĄ kalibrację
    # (flaga poza_publikacja), ale nie wchodzą do apki/kalendarza.
    # (typy_poza_publikacja zainicjalizowane przed pętlą trendów — zbiera
    # też okazje z kursem i sugestie zdjęte przez bramę jakości)
    pewniaki_per_mecz: dict[int, int] = {}
    # zapas na obstawienie — NOWY typ nie pojawia się kwadrans przed gwizdkiem
    # (typ już opublikowany wraca z rejestru publikacji i zostaje do końca)
    teraz_pub = int(time.time())
    for b in do_emisji:
        klucz = (b["podmiot_id"], b["rynek_kod"], b["linia"], b["strona"])
        if klucz in juz_opublikowane:
            continue
        juz_opublikowane.add(klucz)
        ci = b.get("ci") or [None, None]
        ci_w = (ci[1] - ci[0]) if ci[0] is not None else 1.0
        vb_id += 1
        # kwarantanny idą przez wspólną funkcję — tę samą, której używają
        # sumy meczowe i „kto więcej" (patrz `_kwarantanna_zdejmuje`)
        powod_poza = _kwarantanna_zdejmuje(b)
        if powod_poza is None:
            if not betting.w_oknie_zgody(b["p_model"], b["kurs"]):
                # najostrzejsza brama, zmierzona na 336 rozliczeniach — patrz
                # betting.OKNO_ZGODY_*. Typ dalej się liczy i uczy w tle.
                powod_poza = "rozjazd_z_rynkiem"
            elif _kategoria_zdejmuje(b):
                powod_poza = "kwarantanna_kategorii"
            elif b.get("stare_dane"):
                powod_poza = "stare_dane"
            elif b["kickoff_ts"] <= teraz_pub + kupony.MARGINES_STARTU_S:
                powod_poza = "za_pozno"
            elif (betting.wymaga_uzasadnienia(b.get("kurs"))
                  and not betting.ma_komplet_uzasadnienia(b)):
                # BRAMA UZASADNIEŃ — patrz betting.PROG_KURSU_POLEK.
                #
                # DOTYCZY WYŁĄCZNIE NOWYCH PUBLIKACJI i to jest zamierzone,
                # mimo lekcji z [[wznowione-omijaly-bramy]] (bramy stawiać przy
                # dumpie, nie przy narodzinach typu). Tutaj wyjątek jest
                # świadomy: typ RAZ POKAZANY zostaje do gwizdka nawet bez
                # materiału, bo cena jest zamrożona, user mógł go zagrać,
                # a znikanie typów spod ręki naprawialiśmy osobno. Stąd to
                # miejsce w kodzie — pętla po świeżych kandydatach, przed
                # `scal_z_publikacjami`, które wznawia typy z księgi.
                powod_poza = "bez_uzasadnienia"
        rec_pewniaka = {
            "id": vb_id, "mecz_id": b["mecz_id"], "mecz": b["mecz"],
            "kickoff_ts": b["kickoff_ts"],
            "podmiot_typ": b.get("podmiot_typ", "zawodnik"),
            "podmiot_id": b["podmiot_id"], "podmiot": b["podmiot"],
            "druzyna": b.get("druzyna", ""), "przeciwnik": b.get("przeciwnik", ""),
            "rynek_kod": b["rynek_kod"], "rynek": b["rynek"],
            "linia": b["linia"], "strona": b["strona"],
            "pewniak": True,
            "wyzsza_linia": bool(b.get("wyzsza_linia")),
            "matchup": bool(b.get("matchup")),
            "matchup_styl": bool(b.get("matchup_styl")),
            "rotacja": bool(b.get("rotacja")),
            "swieze_sklady": bool(b.get("swieze_sklady")),
            "miekka_linia": bool(b.get("miekka_linia")),
            "kurs_oczekiwany": b.get("kurs_oczekiwany"),
            "xi_sygnal": b.get("xi_sygnal"),
            "kurs": b["kurs"], "bukmacher": b["bukmacher"],
            "p_model": b["p_model"], "p_rynku": None,
            "fair_kurs": round(1.0 / max(b["p_model"], 1e-6), 2),
            "edge_pp": None,
            "ev_pct": round(betting.ev_brutto_pct(b["p_model"], b["kurs"]), 1),
            "ev_netto": round(
                betting.ev_pct(b["p_model"], b["kurs"], b.get("tryb_podatku")), 1
            ),
            "tryb_podatku": b.get("tryb_podatku")
                            or betting.tryb_podatku(b.get("bukmacher")),
            "pewnosc": "wysoka" if ci_w <= 0.18 else "srednia",
            "pewnosc_score": 55.0,
            "ryzyko": b.get("ryzyko", "srednie"),
            "rank_score": round(_atrakcyjnosc(b), 4),
            "ci": ci, "oczekiwane_minuty": b.get("oczekiwane_minuty"),
            "lambda": round(b.get("lambda", 0.0), 3),
            "rozklad": b.get("rozklad"),
            # NA CZYM STOI TA PROGNOZA — stempel z pętli drużynowej. To jest
            # BIAŁA LISTA PÓL: co nie zostanie tu wymienione, ginie w drodze
            # z puli na stronę i do księgi, choć w legu było (ta sama pułapka
            # co przy `kal_tau` i `swieze_sklady` wyżej).
            **({"ess": b["ess"]} if b.get("ess") is not None else {}),
            **({"udzial_priora": b["udzial_priora"]}
               if b.get("udzial_priora") is not None else {}),
            **({"kal_rynek": b["kal_rynek"]}
               if b.get("kal_rynek") is not None else {}),
            **({"rachunek": b["rachunek"]} if b.get("rachunek") else {}),
            **({"kal_tau": b["kal_tau"]} if b.get("kal_tau") else {}),
            "czynniki": b.get("czynniki", {}),
            "uzasadnienie": b.get("uzasadnienie", {"czynniki": []}),
        }
        if powod_poza:
            rec_pewniaka["poza_publikacja"] = powod_poza
            typy_poza_publikacja.append(rec_pewniaka)
            continue
        pewniaki_per_mecz[b["mecz_id"]] = pewniaki_per_mecz.get(b["mecz_id"], 0) + 1
        value_bets.append(rec_pewniaka)
        _zapewnij_mecz(b["mecz_id"])["okazje"].append(vb_id)
    # OSTATNIA BRAMA: typ, który po UREALNIENIU szansy przestaje mieć wartość.
    #
    # Decyzja usera 2026-07-29. Skoro strona pokazuje szansę ściągniętą
    # o zmierzony rozjazd deklaracji z wynikami, to ta sama liczba musi
    # decydować, czy typ w ogóle jest okazją. Inaczej karta mówiłaby wprost
    # „szansa 70%, kurs 1,27, wartość −11%" — czyli polecalibyśmy zakład,
    # który sami wyceniamy na minus.
    #
    # Brama stoi PO wszystkich innych i NIE jest kolejną warstwą uczenia:
    # to samo przeliczenie, które trafia na stronę (`_urealnij_do_pokazania`).
    # Typ nie znika bez śladu — idzie do księgi jako `poza_publikacja`, więc
    # rozlicza się i uczy kalibrację, tak jak typy z kwarantanny.
    if korekta_pokazywana:
        odpadle = []
        for b in value_bets:
            if b.get("sugestia") or not b.get("kurs"):
                continue
            if (_urealnij_do_pokazania(b).get("ev_pct") or 0.0) < 0.0:
                odpadle.append(b)
        if odpadle:
            odrzucone_id = {id(b) for b in odpadle}
            value_bets[:] = [b for b in value_bets if id(b) not in odrzucone_id]
            for b in odpadle:
                typy_poza_publikacja.append(
                    {**b, "poza_publikacja": "ujemna_po_korekcie"}
                )

    # === NAJWYŻEJ DWIE POPRZECZKI NA ZAKŁAD (2026-08-02, decyzja usera) ===
    #
    # Brama z 01.08 wybiera najlepszą poprzeczkę wg oceny modelu, ale widzi
    # tylko BIEŻĄCE przeliczenie. Poprzeczki dokładały się więc MIĘDZY cyklami:
    # o północy najlepsza była „poniżej 0,5", po południu kurs się przesunął
    # i model dołożył „poniżej 1,5". Jeden zakład potrafił urosnąć do czterech
    # wierszy.
    #
    # CZEMU DWIE, A NIE JEDNA — to nie jest kompromis, tylko pomiar. Poprzeczki
    # ustawione wg kolejności wystawienia dają (cała księga, rozliczone):
    #
    #     1. bazowa              449 typów   57% trafień   -0,219 j./typ
    #     2. pierwsza dołożona   135 typów   64% trafień   -0,147 j./typ  <-- NAJLEPSZA
    #     3. i dalsze             37 typów   49% trafień   -0,298 j./typ  <-- najgorsza
    #
    # Druga poprzeczka bije bazową. Dopiero trzecia się załamuje — i tam leży
    # granica. Rozkład to potwierdza: 419 zakładów ma jedną poprzeczkę, 139
    # dwie, a tylko 35 trzy lub cztery. Limit ucina ogon (42 wiersze z 809),
    # nie połowę listy.
    #
    # Zostają OBIE i obie liczą się w Skuteczności: to naprawdę dwa różne
    # zakłady (łatwiejszy przy niższym kursie i ambitniejszy przy wyższym),
    # a nie ten sam wyceniony dwa razy. Na liście stoją jako jeden wiersz
    # z drabinką — zwijanie robi UI, nie publikacja.
    #
    # WYGRYWAJĄ WYSTAWIONE WCZEŚNIEJ. Typ raz pokazany wisi do gwizdka
    # z zamrożonym kursem, user mógł go już zagrać, a księga rozliczy go po
    # tamtej cenie — podmiana poprzeczki pod nim byłaby przepisywaniem historii.
    #
    # Stoi PO wszystkich bramach jakości, żeby liczyć tylko to, co naprawdę
    # weszłoby na stronę. Typ nie znika bez śladu — jak każdy odsiew idzie do
    # księgi i dalej uczy kalibrację.
    MAX_POPRZECZEK_ZAKLADU = 2
    if linie_log:
        _zostaja, _nadmiar = [], []
        for b in value_bets:
            k = (b["mecz_id"], rotowire._norm(str(b.get("podmiot") or "")),
                 b["rynek_kod"], b.get("strona"))
            juz = linie_log.get(k) or set()
            nowa = b.get("linia") is not None and float(b["linia"]) not in juz
            if nowa and len(juz) >= MAX_POPRZECZEK_ZAKLADU:
                _nadmiar.append({**b, "poza_publikacja": "trzecia_poprzeczka"})
            else:
                _zostaja.append(b)
        if _nadmiar:
            value_bets[:] = _zostaja
            typy_poza_publikacja.extend(_nadmiar)

    # ⚑ KOLIZJA WERSJI: karta pokazywałaby inną liczbę, niż rozliczy księga.
    # Patrz `wersje_w_ksiedze` — pełny opis i pomiar. Brama stoi TU, obok
    # pozostałych filtrów korzystających z zamrożonej księgi, i przed
    # `_urealnij_do_pokazania`, więc typ nie zdąży trafić na listę.
    if wersje_log:
        _zostaja, _kolizje = [], []
        for b in value_bets:
            w_ksiegi = wersje_log.get(_klucz_publikacji(b))
            if w_ksiegi and w_ksiegi != betting.WERSJA_KALIBRACJI:
                _kolizje.append({**b, "poza_publikacja": "kolizja_wersji"})
            else:
                _zostaja.append(b)
        if _kolizje:
            value_bets[:] = _zostaja
            typy_poza_publikacja.extend(_kolizje)
            print(f"Kolizja wersji: {len(_kolizje)} typów ma w księdze rekord "
                  f"policzony inną kalibracją niż {betting.WERSJA_KALIBRACJI} "
                  "— nie wracają na listę, bo karta i rozliczenie mówiłyby co "
                  "innego (rekord w księdze zostaje nietknięty)")
            print(f"Limit poprzeczek zakładu: zdjęto {len(_nadmiar)} "
                  f"(zakład ma już {MAX_POPRZECZEK_ZAKLADU} wystawione)")

    if typy_poza_publikacja:
        licz_poza = Counter(t["poza_publikacja"] for t in typy_poza_publikacja)
        print("Poza publikacją: " + ", ".join(
            f"{v} ({k})" for k, v in licz_poza.most_common()
        ) + " — rozliczą się i uczą kalibrację w tle")

    # CO SPRZEDAJEMY vs CZEGO SIĘ UCZYMY — jedna linia, w każdym cyklu.
    # Rosnąca lista znaczy, że wypuszczamy nowe rynki szybciej, niż je mierzymy;
    # dokładnie to stało się z sumami meczowymi 30.07 (patrz notatka
    # „nowe rynki bez bram"). Nie jest to brama, tylko czujnik.
    try:
        _bez_kal = rozliczanie.rynki_bez_kalibracji(value_bets)
        if _bez_kal:
            print("Rynki publikowane bez własnej kalibracji (próg "
                  f"{rozliczanie.MIN_N_KALIBRACJI}): " + ", ".join(
                      f"{d['rynek']} — "
                      + rozliczanie.odmien(d['publikacji'], "typ", "typy", "typów")
                      + ", "
                      + rozliczanie.odmien(d['rozliczen'], "rozliczenie",
                                           "rozliczenia", "rozliczeń")
                      for d in _bez_kal))
    except Exception as e:
        print(f"Raport rynków bez kalibracji pominięty ({e})")

    value_bets.sort(key=lambda b: -b["rank_score"])

    # rynki w kwarantannie wypadają też z puli kuponów (generator i kupony
    # automatyczne nie budują na rynku, który trafia poniżej deklaracji);
    # to samo legi na starych danych (brama jakości ligi)
    # POMIAR BRAM PULI (2026-08-03). Pusta zakładka Kuponów wraca jako
    # zgłoszenie co kilka dni, a log mówił tylko, ILE legów zostało — nigdy,
    # co je zabrało. Bez tego każda diagnoza zaczyna się od zgadywania, która
    # z pięciu bram zjadła pulę (zmierzone 03.08: z ~52 legów drużynowych
    # zostało 5, wszystkie „gole drużyny poniżej").
    odpadki_legow: Counter = Counter()

    def _leg_dopuszczalny(b: dict) -> bool:
        if not b.get("kurs"):
            odpadki_legow["brak_kursu"] += 1
            return False
        # ta sama podłoga co na stronie — bez niej pula kuponów brała
        # tanie legi wznowione sprzed zmian bram (2026-08-01: 28 legów
        # „rożne w meczu" po 1,05–1,17, przy MIN_ODDS 1,19)
        if not betting.kurs_w_widelkach(b["kurs"]):
            odpadki_legow["kurs_poza_widelkami"] += 1
            return False
        # BRAMA STRONY, KTÓREJ TU NIE BYŁO (2026-08-04). Do dziś pulę chronił
        # wyłącznie licznik rynku — a on miesza obie strony linii. Odkąd rynek
        # przestał zdejmować stronę z własnym werdyktem (`_rynek_wstrzymany`),
        # bez niej do kuponów wchodziłoby dokładnie to, co brama stron
        # wcześniej wstrzymała: `team_corners:ponizej` (ROI −19%, n=118).
        _kw = _powod_kwarantanny(b)
        if _kw:
            odpadki_legow[
                f"{_kw}:{b['rynek_kod']}:{b.get('strona')}"] += 1
            return False
        if b.get("stare_dane"):
            odpadki_legow["stare_dane"] += 1
            return False
        if _kategoria_wstrzymana(b):
            odpadki_legow["kwarantanna_kategorii"] += 1
            return False
        # ta sama brama co przy typach: leg poza oknem zgody z rynkiem nie
        # wchodzi do kuponów. Błąd pojedynczego lega MNOŻY się przez kupon,
        # więc to tu boli najbardziej (patrz kupony 0/18 w stylu
        # „z przewagą")
        if not betting.w_oknie_zgody(b["p_model"], b["kurs"]):
            odpadki_legow["poza_oknem_zgody"] += 1
            return False
        return True

    legi_pool_pub = [b for b in legi_pool if _leg_dopuszczalny(b)]
    if odpadki_legow:
        print(f"Pula kuponów — bramy zdjęły {sum(odpadki_legow.values())} "
              f"z {len(legi_pool)} legów: " + ", ".join(
                  f"{k}={v}" for k, v in odpadki_legow.most_common()))

    # REJESTR ODRZUCEŃ — domknięcie: para (zawodnik, rynek) opublikowana
    # (typ/sugestia) wypada z rejestru; obecna w puli kuponów, ale nie na
    # karcie meczu, dostaje uczciwe "tylko_w_puli" (jest w generatorze)
    opublikowane_pary = {(b["podmiot_id"], b["rynek_kod"]) for b in value_bets}
    pary_puli = {(b["podmiot_id"], b["rynek_kod"]) for b in legi_pool_pub}
    odrzucenia_out = [
        r for (mid_o, pid_o, mk_o), r in odrzucenia.items()
        if (pid_o, mk_o) not in opublikowane_pary
        and (pid_o, mk_o) not in pary_puli
    ]
    w_puli_dodane = set()
    for b in legi_pool_pub:
        para = (b["podmiot_id"], b["rynek_kod"])
        if para in opublikowane_pary or para in w_puli_dodane:
            continue
        w_puli_dodane.add(para)
        odrzucenia_out.append({
            "mecz_id": b["mecz_id"], "podmiot": b["podmiot"],
            "druzyna": b.get("druzyna", ""),
            "rynek_kod": b["rynek_kod"], "rynek": b["rynek"],
            "powod": "tylko_w_puli",
            "szczegol": "typ dostępny w generatorze kuponów. Na karcie meczu "
                        "wygrał inny typ tego rynku",
        })
    # transparentność bramy: typy zdjęte z publikacji dostają uczciwy
    # wpis w rejestrze ("czemu nie ma typu"), zamiast znikać bez śladu
    for t in typy_poza_publikacja:
        if t["poza_publikacja"] == "limit_meczu":
            continue  # limit_meczu: typ i tak jest w generatorze (tylko_w_puli)
        para = (t["podmiot_id"], t["rynek_kod"])
        if para in opublikowane_pary or para in w_puli_dodane:
            continue
        w_puli_dodane.add(para)
        if t["poza_publikacja"] == "stare_dane":
            szczegol = (
                "ostatni mecz zawodnika był dawno temu, czekamy aż "
                "wróci do gry i da świeże dane"
            )
        elif t["poza_publikacja"] == "za_pozno":
            szczegol = (
                "za mało czasu do pierwszego gwizdka — nowych typów nie "
                "dodajemy na ostatnią chwilę, żebyś zdążył je obstawić"
            )
        elif t["poza_publikacja"] == "rozjazd_z_rynkiem":
            szczegol = (
                "nasza szansa za mocno rozjeżdża się z kursem. Rozliczenia "
                "mówią jasno: im dalej jesteśmy od bukmachera, tym rzadziej "
                "mamy rację — zwykle on wie coś, czego my nie wiemy"
            )
        elif t["poza_publikacja"] == "trzecia_poprzeczka":
            szczegol = (
                "ten zakład ma już dwie poprzeczki na liście — łatwiejszą "
                "i ambitniejszą. Trzeciej nie dokładamy: rozliczenia mówią, "
                "że druga poprzeczka wypada NAJLEPIEJ ze wszystkich, a trzecia "
                "i dalsze najgorzej"
            )
        elif t["poza_publikacja"] == "kwarantanna_kategorii":
            flaga = next(
                (f for f in rozliczanie.KATEGORIE_KWARANTANNY
                 if t.get(f) and f in kwarantanna_kategorii),
                None,
            )
            kk = kwarantanna_kategorii.get(flaga or "", {})
            szczegol = (
                f"typy z powodu „{kk.get('nazwa', flaga)}” ostatnio traciły "
                f"{abs(kk.get('roi', 0)):.0%} na złotówce stawki "
                f"(trafienia {kk.get('hit', 0):.0%}, próba: {kk.get('n', 0)}). "
                f"Wstrzymane, aż przestaną tracić"
            )
        elif t["poza_publikacja"] == "kwarantanna_strony":
            # WŁASNE LICZBY STRONY, NIE RYNKU (2026-08-04). Wcześniej ta gałąź
            # wpadała do `else` i tłumaczyła zdjęcie strony wynikiem CAŁEGO
            # rynku — a to dwie różne liczby, często o przeciwnym znaku
            # (`team_corners`: poniżej −19%, powyżej +9%).
            ks = kwarantanna_stron.get(
                f"{t['rynek_kod']}:{t.get('strona')}", {})
            szczegol = (
                f"ta strona zakładu jest chwilowo poza publikacją: ostatnie "
                f"typy traciły {abs(ks.get('roi', 0)):.0%} na złotówce stawki "
                f"(trafienia {ks.get('hit', 0):.0%}, próba: {ks.get('n', 0)}). "
                f"Druga strona tego rynku może być dalej typowana"
            )
        else:
            kw = kwarantanna_rynkow.get(t["rynek_kod"], {})
            szczegol = (
                f"rynek chwilowo poza publikacją: ostatnie typy traciły "
                f"{abs(kw.get('roi', 0)):.0%} na złotówce stawki "
                f"(trafienia {kw.get('hit', 0):.0%}, próba: {kw.get('n', 0)}). "
                f"Wróci, gdy przestanie tracić"
            )
        odrzucenia_out.append({
            "mecz_id": t["mecz_id"], "podmiot": t["podmiot"],
            "druzyna": t.get("druzyna", ""),
            "rynek_kod": t["rynek_kod"], "rynek": t["rynek"],
            "powod": t["poza_publikacja"],
            "szczegol": szczegol,
        })

    # pełne pokrycie p_model (backend-only, dla scannera STS) — emitujemy ZAWSZE,
    # także w trybie „0 okazji" niżej, bo model i tak policzył wszystkie linie
    _dump("sts_model.json", model_pokrycie)

    # RADAR okazji kontekstowych (nowi w drużynie / serie formy / debiutanci
    # kwotowani przez Superbet bez historii) — celowo POZA bramami publikacji
    # modelu (transfery model zwykle odrzuca jako rozjazd_z_rynkiem, bo liczy
    # ze starej ligi). Warstwa informacyjna z drabinką kursów, patrz radar.py.
    # Pusty wynik NIE nadpisuje poprzedniego pliku (jak filozofia „0 okazji").
    # DOCIĄG KURSÓW dla meczów BEZ trendów statshub (bug zmierzony 2026-07-25):
    # sb_cache wypełnia się tylko w pętli po trendach, więc mecz z zerem
    # trendów (cała Ekstraklasa — feed propsów UK jej nie kwotuje) nigdy nie
    # miał kursów w systemie i ścieżka debiutantów nie mogła odpalić — mimo
    # że Superbet kursy MA. Dociągamy dla najbliższych sparowanych meczów.
    try:
        DOCIAG_OKNO_S = 36 * 3600   # mecze w tym oknie przed kickoffem
        DOCIAG_MAX = 20             # limit grzecznościowy zapytań na cykl
        dociagniete = 0
        teraz_d = int(time.time())
        for e in sorted(wszystkie_ev,
                        key=lambda e: int(e.get("timeStartTimestamp") or 0)):
            mid_d = e["id"]
            ts_d = int(e.get("timeStartTimestamp") or 0)
            if mid_d in sb_cache:
                continue
            if not (0 <= ts_d - teraz_d <= DOCIAG_OKNO_S):
                continue
            if dociagniete >= DOCIAG_MAX:
                break
            if tryb:
                sb_ev = tryb.sb_ev_by_mid.get(mid_d)
            elif sb_events:
                sb_ev = superbet.match_superbet_event(
                    sb_events,
                    team_name.get(e.get("homeTeamId"), ""),
                    team_name.get(e.get("awayTeamId"), ""), ts_d,
                )
            else:
                sb_ev = None
            if not sb_ev:
                continue
            parts = [p.strip()
                     for p in (sb_ev.get("matchName") or "·").split("·")]
            try:
                sb_cache[mid_d] = superbet.fetch_stat_odds(
                    sb_ev["eventId"], parts[0], parts[1]
                )
                dociagniete += 1
            except Exception as e:
                # dociągnięcie kursów do puli kuponów — bez niego leg wypada
                diagnostyka.cichy("cykl", "dociagniecie_kursow", e)
                continue
        if dociagniete:
            print(f"Kursy Superbet dociągnięte dla {dociagniete} meczów "
                  f"bez trendów (ścieżka debiutantów)")
    except Exception as ex:
        print(f"Dociąg kursów pominięty ({ex})")
    pomiar_drabinek: list[dict] = []
    try:
        events_meta_radar = {
            e["id"]: {
                "label": f'{team_name.get(e["homeTeamId"], "?")} – '
                         f'{team_name.get(e["awayTeamId"], "?")}',
                "ts": int(e.get("timeStartTimestamp") or 0),
                "hid": e["homeTeamId"], "aid": e["awayTeamId"],
                "home": team_name.get(e["homeTeamId"], ""),
                "away": team_name.get(e["awayTeamId"], ""),
            }
            for e in wszystkie_ev
        }
        radar_wpisy = radar.zbuduj(
            trends, events_meta_radar, odds_grid, sb_cache,
            model_pokrycie, players_out, MARKET_NAMES_PL, int(time.time()),
            player_sezon=supa.get_key("player_sezon") or {},
            # profil arbitra (365Scores) — drabinki korygują nim rynki faulowe;
            # mecz bez obsady dostaje neutralne 1.0 i notatkę na karcie
            sedzia_by_mid=sedzia_by_mid,
            # tabela koncesji modelu (bank trendów + dopełnienie 365Scores) —
            # dla lig spoza feedu propsów, gdzie statshub nie daje gotowych
            # agregatów rywala, to JEDYNE źródło kontekstu (m.in. Ekstraklasa)
            koncesje_tab=koncesje_tab,
            # brama składu: karta nie powstaje dla zawodnika, o którym WIEMY,
            # że go w jedenastce nie ma (zgłoszenie 2026-07-27: Fabio Fehr)
            poza_skladem=poza_skladem,
            xi_znany=xi_znany,
            # zapas na obstawienie — nowa karta nie wskakuje tuż przed meczem
            margines_startu_s=kupony.MARGINES_STARTU_S,
            # WŁASNE UCZENIE DRABINEK: delta z ICH rozliczeń (nie modelu) —
            # ściąga szanse kart o tyle, o ile strumień przeszacowywał
            # SKALAR, nie biny: `p` drabinek pochodzi z pokrycia linii,
            # a nie z p_over silnika, więc przedziały modelu nic tam nie
            # znaczą (patrz rozliczanie._biny_korekty — drabinki celowo
            # zostają jedną liczbą; `delta_globalna` jest bezpiecznikiem)
            korekta_logit=rozliczanie.betting.delta_globalna(
                korekta_strumieni.get("drabinki")
            ),
            # ...i pomiar progu pokrycia: szczeble tuż pod nim, do rozliczenia
            # oferta drugiego bukmachera, pobrana raz w tym cyklu — pozwala
            # dopiąć drugą cenę PRZED selekcją kart (różnica jako przepustka)
            # i oszczędza powtórne zapytania
            bc_cache=bc_cache,
            # kto daje cenę tam, gdzie nie Superbet — karta musi to napisać
            zrodla_grid=zrodla_grid,
            # w tle (patrz radar.NEAR_POKRYCIA)
            pomiar_out=pomiar_drabinek,
        )
        radar_padl = False
    except Exception as ex:
        radar_wpisy = []
        radar_padl = True
        # pełny traceback, nie sam komunikat: pusty radar NIE nadpisuje
        # poprzedniego pliku, więc bez tego awaria drabinek wygląda w logu
        # identycznie jak „dziś nic nie przeszło bram"
        print(f"Radar pominięty w tym cyklu ({ex})\n{traceback.format_exc()}")
    # ⚑ „AWARIA" i „BRAMY ZDJĘŁY WSZYSTKO" TO DWIE RÓŻNE RZECZY (2026-08-08).
    # Dotąd rozstrzygał je jeden warunek `if radar_wpisy`, więc przy zerze
    # kandydatów cykl w ogóle nie wołał `scal_karty_z_publikacjami` i nie
    # zapisywał pliku — a wtedy na stronie zostawał POPRZEDNI radar, nietknięty
    # przez żadną nową regułę. Zmierzone tego dnia: cykl #657 zielony, świeżych
    # kart 0, a w Supabase dalej wisiały 23 karty z 07.08 22:09, z czego 10
    # jednoszczeblowych — czyli wymóg drugiego szczebla drugi dzień z rzędu nie
    # zmieniał niczego, mimo dwóch wdrożeń. Przy awarii zachowanie ZOSTAJE
    # (nie kasujemy strony z powodu wyjątku), przy zerze po bramach wznowione
    # przechodzą przez bramę i zapisujemy wynik, choćby był pusty.
    if not radar_padl:
        # karta raz pokazana zostaje do gwizdka — ta sama zasada co przy typach
        radar_wpisy = scal_karty_z_publikacjami(radar_wpisy)
        _dump("radar.json", {
            "wygenerowano_ts": int(time.time()),
            "wpisy": radar_wpisy,
        })
        rodzaje = Counter(w["rodzaj"] for w in radar_wpisy)
        print("Radar: " + (", ".join(
            f"{k}={v}" for k, v in sorted(rodzaje.items())
        ) if radar_wpisy else
            "pusto — żadna karta nie przeszła bram, poprzednie schodzą ze strony"))
        # KANDYDACI do średnich sezonowych: worker domowy (sofa_worker,
        # Sofascore blokuje chmurę) czyta tę listę i wypełnia player_sezon —
        # następny cykl dolewa sekcję "sezony" do kart drabinek
        kandydaci = []
        widziani_pid: set[int] = set()
        for w in radar_wpisy:
            pid = w.get("podmiot_id")
            if pid and pid not in widziani_pid:
                widziani_pid.add(pid)
                kandydaci.append({"id": int(pid), "nazwa": w.get("podmiot"),
                                  "druzyna": w.get("druzyna"),
                                  "mecz_id": w.get("mecz_id")})
        if kandydaci:
            supa.put_key("sezon_kandydaci", kandydaci[:250])

    # TYPY DRABINEK DO ROZLICZENIA: z każdej opublikowanej karty bierzemy
    # dokładnie ten szczebel, który zdecydował o jej wyborze (`hero`) — czyli
    # to, co user widzi w nagłówku. Rozliczają się jak typy modelu, ale
    # w osobnym strumieniu skuteczności (rozliczanie._strumien), bo ich
    # prawdopodobieństwo pochodzi z innego estymatora niż silnik.
    drabinki_typy = []
    for w in radar_wpisy:
        h = w.get("hero") or {}
        if not h.get("rynek_kod") or not h.get("kurs"):
            continue
        ocena = w.get("ocena") or {}
        drabinki_typy.append({
            "mecz_id": w["mecz_id"], "mecz": w["mecz"],
            "kickoff_ts": w["kickoff_ts"],
            "podmiot_id": w.get("podmiot_id") or 0,
            "podmiot": w["podmiot"],
            "rynek_kod": h["rynek_kod"],
            "rynek": h.get("rynek") or h["rynek_kod"],
            "linia": h["linia"], "strona": "powyzej",
            "kurs": h["kurs"], "bukmacher": "Superbet",
            # p_model w tym rekordzie to p_final drabinki (pokrycie + kontekst
            # meczu), NIE wyjście silnika — stąd flaga zrodlo niżej
            "p_model": h.get("p_final") or 0.0,
            "pewnosc": None, "sugestia": False,
            "zrodlo": rozliczanie.ZRODLO_DRABINKA,
            # RACHUNEK DRABINKI (2026-08-12). Inny niż w reszcie produktu i tak
            # ma zostać: `p` bierze się z pokrycia linii (Wilson) przemnożonego
            # przez kontekst meczu, a nie z p_over silnika. Kalibracji RYNKU
            # więc tu nie ma i nie jest to usterka — patrz `_biny_korekty`,
            # drabinki celowo uczą się własną, skalarną korektą.
            # `kal_rynek` zostaje pusty, bo `None` znaczy „ta ścieżka tego nie
            # liczy", a zero znaczyłoby „policzone i wyszło zero".
            "rachunek": betting.stempel_rachunku(
                p_over_raw=(
                    round(float(h["p_bazowe"]) * float(h["korekta"]), 4)
                    if h.get("p_bazowe") is not None
                    and h.get("korekta") is not None else None
                ),
                kal_strumien=rozliczanie.betting.delta_globalna(
                    korekta_strumieni.get("drabinki")
                ),
                p_over_final=h.get("p_final"),
            ),
            "klasa": ocena.get("klasa"),
            "edge": ocena.get("edge"),
        })

    # TYPY POMIAROWE DRABINEK: szczeble odrzucone WYŁĄCZNIE progiem pokrycia
    # (0,40–0,50). Idą do tej samej księgi z flagą `odrzucony`, więc rozliczą
    # się w tle, ale nie zobaczy ich ani user, ani skuteczność, ani korekta
    # strumienia. Po kilku tygodniach `rozliczanie.pomiar_progu_drabinek`
    # powie, czy próg 0,5 zarabia, czy tylko obcina kandydatów.
    for p in pomiar_drabinek:
        drabinki_typy.append({
            "mecz_id": p["mecz_id"], "mecz": p["mecz"],
            "kickoff_ts": p["kickoff_ts"],
            "podmiot_id": p.get("podmiot_id") or 0,
            "podmiot": p["podmiot"],
            "rynek_kod": p["rynek_kod"],
            "rynek": p.get("rynek") or p["rynek_kod"],
            "linia": p["linia"], "strona": "powyzej",
            "kurs": p["kurs"], "bukmacher": "Superbet",
            "p_model": p.get("p_final") or 0.0,
            "pewnosc": None, "sugestia": False,
            "zrodlo": rozliczanie.ZRODLO_DRABINKA,
            "edge": p.get("edge"),
            "odrzucony": True,
            "odrzucenie_powod": rozliczanie.POWOD_POMIARU_POKRYCIA,
        })

    # RAPORT POKRYCIA (liga): parowanie z build_league + to, co dołożył
    # silnik — luka jest mierzona i zapisywana co cykl, nie ignorowana.
    # Jeden plik odpowiada na "czego nie gramy i dlaczego".
    def _pokrycie_rynkow() -> dict:
        """W ilu meczach UMIEMY policzyć każdą naszą statystykę.

        Zgłoszenie usera 2026-07-27: „w Meczach miały być tabele pokryć
        wszystkich naszych statystyk, a obecnie jest nic". Do dziś wiedzieliśmy
        tylko, ile meczów sparowaliśmy — nie, których rynków w nich brakuje.
        A to właśnie ta tabela wyłapałaby dwa błędy parsera Superbetu
        z tego samego dnia w pierwszym cyklu, zamiast po tygodniu.

        Liczymy z tego samego `sb_cache`, z którego korzysta silnik, więc
        tabela pokazuje ofertę TAK, JAK MY JĄ WIDZIMY — łącznie z naszymi
        ślepotami. To jest zaleta, nie wada: rozjazd z rzeczywistością ma być
        widoczny na stronie.
        """
        mids_druz = (
            {m for m in sb_cache if not tryb or m in tryb.druzynowe_mids}
            if tryb else set(sb_cache)
        )
        druzynowe: Counter = Counter()
        for mid_p in mids_druz:
            teams_p = (sb_cache.get(mid_p) or {}).get("teams") or {}
            kody = set()
            for strona in ("home", "away"):
                kody |= set((teams_p.get(strona) or {}).keys())
            for k in kody:
                druzynowe[k] += 1
        # zawodnicy: ile PAR (zawodnik, rynek) ma kwotowanie w tym cyklu
        zawodnicze: Counter = Counter()
        for mid_p, sb_p in sb_cache.items():
            for _nazwa, rynki_p in (sb_p.get("players") or {}).items():
                for k in rynki_p:
                    zawodnicze[k] += 1
        return {
            "meczow_druzynowych": len(mids_druz),
            "druzynowe": dict(druzynowe.most_common()),
            "zawodnicze": dict(zawodnicze.most_common()),
        }

    # mecze, które weszły do `matches` Z DANYCH (trend zawodniczy albo
    # drużynowy), a nie z przemiatania terminarza niżej. Diagnostyka pokrycia
    # musi liczyć jedno i drugie osobno: po dołożeniu przemiatania `matches_out`
    # zawiera KAŻDY mecz w zakresie, więc "mecze bez trendów" wyszłoby zawsze
    # zerem i cicho straciłoby sens.
    # None = przemiatanie jeszcze nie przeszło (dziś nie zdarza się na żadnej
    # ścieżce, ale pusty ZBIÓR to prawdziwa odpowiedź „żaden mecz nie miał
    # trendów" i nie wolno jej mylić z brakiem pomiaru)
    mids_z_danymi: set[int] | None = None

    def _dump_pokrycie() -> None:
        if not (tryb and tryb.pokrycie):
            return
        mecze_z_trendami = (
            mids_z_danymi if mids_z_danymi is not None else set(matches_out)
        )
        pokrycie = {
            **tryb.pokrycie,
            "wygenerowano_ts": int(time.time()),
            # sparowane z Superbetem, ale statshub nie dał ani jednego trendu
            # (oferta propsów buków UK nie objęła meczu) — świadoma luka
            "mecze_bez_trendow": [
                f'{team_name.get(e.get("homeTeamId"), "?")} - '
                f'{team_name.get(e.get("awayTeamId"), "?")}'
                for e in events if e["id"] not in mecze_z_trendami
            ],
            "odrzucenia_per_powod": dict(sorted(
                Counter(o["powod"] for o in odrzucenia.values()).items(),
                key=lambda kv: -kv[1],
            )),
            "poza_publikacja_per_powod": dict(Counter(
                t["poza_publikacja"] for t in typy_poza_publikacja
            )),
            "typy": len(value_bets),
            "mecze_z_typami": len({b["mecz_id"] for b in value_bets}),
            "rynki": _pokrycie_rynkow(),
        }
        _dump("pokrycie_liga.json", pokrycie)
        print(f"Pokrycie ligi: {pokrycie['sparowane']}/{pokrycie['mecze_statshub']} "
              f"meczów sparowanych, {len(pokrycie['mecze_bez_trendow'])} bez trendów, "
              f"luka propsów Superbetu: {len(pokrycie['luka_superbet_propsy'])} meczów")

    # TERMINARZ POKAZUJE KAŻDY PRZEANALIZOWANY MECZ — patrz `domknij_terminarz`.
    # Przemiatamy zakres DRUŻYNOWY, czyli dokładnie ten, który zakładka Mecze
    # i tak pokazuje domyślnie.
    # ...a teraz mecze, w których feed propsów milczy CAŁKOWICIE — tam nie ma
    # kogo wzbogacać, więc zawodników trzeba odkryć wprost z oferty bukmachera
    # (patrz odkryj_zawodnikow_z_oferty). To domyka tabelę pokryć na
    # kwalifikacjach pucharów, gdzie kursy są, a feedu nie ma.
    _do_odkrycia = []
    for _mid, _sb in sb_cache.items():
        if not (_sb or {}).get("players"):
            continue
        _ev = ev_by_id.get(_mid) or {}
        _h, _a = _ev.get("homeTeamId"), _ev.get("awayTeamId")
        if not (_h and _a):
            continue
        _do_odkrycia.append((
            _mid, (int(_h), int(_a)),
            int(_ev.get("timeStartTimestamp") or 0),
            {int(_h): team_name.get(_h, ""), int(_a): team_name.get(_a, "")},
        ))
    if _do_odkrycia:
        odkryj_zawodnikow_z_oferty(
            _do_odkrycia, sb_cache, players_out, odds_grid, _forma_z_trendu,
        )

    mids_z_danymi = set(matches_out)
    # „mamy kursy" = bukmacher kwotuje na ten mecz cokolwiek, co umiemy wycenić:
    # rynek drużynowy albo propsy zawodnicze. Mecz spoza `sb_cache` to mecz,
    # któremu nawet nie pobraliśmy oferty — nie mamy o nim nic do powiedzenia.
    mids_z_kursami = {
        mid for mid, sb in sb_cache.items()
        if (sb or {}).get("players") or any(((sb or {}).get("teams") or {}).values())
    }
    _dolozone = domknij_terminarz(
        matches_out,
        (set(tryb.druzynowe_mids) if tryb else {e["id"] for e in events}),
        lambda mid: _zapewnij_mecz(mid) if mid in ev_by_id else None,
        {mid: len((sb or {}).get("players") or {}) for mid, sb in sb_cache.items()},
        mids_z_kursami=mids_z_kursami,
    )
    if _dolozone:
        print(f"Terminarz: {_dolozone} meczów w zakresie bez własnych danych "
              f"(dołożone do listy), {len(mids_z_danymi)} z trendami")

    # typ raz opublikowany zostaje na liście do gwizdka — patrz scal_z_publikacjami.
    # Księga rozliczeń jedzie jako DRUGIE źródło siatki (rejestr publikacji bywa
    # młodszy niż typy, które ma chronić); nieudany odczyt = pracujemy bez niej.
    # Siatka MUSI być przed bramką „0 okazji" niżej: cykl, w którym feed zamilkł
    # na całej linii, to dokładnie ten, w którym typy sprzed gwizdka mają wrócić.
    log_do_siatki, _ok_log = supa.get_key_ok("typy_log")
    # jeden zegar na scalenie i przycięcie rejestru — po `opublikowano_ts ==
    # _teraz_publikacji` poznajemy wpisy dopisane w TYM cyklu (patrz
    # `przytnij_rejestr_do_listy`)
    _teraz_publikacji = int(time.time())
    value_bets_pub, _wzn = scal_z_publikacjami(
        value_bets, matches_out, teraz=_teraz_publikacji,
        typy_log=rozliczanie._migruj_log(log_do_siatki or {}),
        liga_by_mid=(tryb.liga_by_mid if tryb else None),
        # typy zdjęte bramami są policzone z pełnym rachunkiem — karta
        # wznowiona z księgi może z niego skorzystać (patrz `_dolóż_rentgen`)
        policzone_w_cyklu=typy_poza_publikacja,
    )

    # TYP WZNOWIONY TEŻ JEST LEGIEM (naprawa 2026-07-30, zgłoszenie usera:
    # „jak to możliwe, że pula ma jednego lega, jak jest dużo więcej").
    #
    # Pula kuponów budowała się WYŁĄCZNIE z bieżącego przeliczenia, a lista
    # typów w 86% składa się z typów WZNOWIONYCH z rejestru publikacji
    # (pomiar 30.07: 63 typy drużynowe na liście, z tego 54 wznowione — pula
    # widziała 9). Strona pokazywała więc 63 pozycje, a generator kuponów
    # dziewięć: kupon dzienny nie miał z czego powstać, mimo że typy były.
    #
    # Wznowiony typ ma wszystko, czego leg potrzebuje: zamrożony kurs, szansę
    # i przedział z chwili publikacji — a przy publikacji przeszedł te same
    # bramy. Brakowało tylko podpięcia.
    _klucze_puli = {
        (b.get("mecz_id"), str(b.get("podmiot")), b.get("rynek_kod"),
         b.get("linia"), b.get("strona"))
        for b in legi_pool_pub
    }
    _dolozone_legi = 0
    for b in value_bets_pub:
        if b.get("sugestia") or not b.get("wznowiony"):
            continue
        k = (b.get("mecz_id"), str(b.get("podmiot")), b.get("rynek_kod"),
             b.get("linia"), b.get("strona"))
        if k in _klucze_puli or not _leg_dopuszczalny(b):
            continue
        _klucze_puli.add(k)
        legi_pool_pub.append(b)
        _dolozone_legi += 1
    if _dolozone_legi:
        print(f"Pula kuponów: dołożono {_dolozone_legi} legów z typów "
              f"wznowionych (wcześniej pula widziała tylko bieżące przeliczenie)")

    # NIE degraduj aplikacji do pustej planszy: dopóki nie ma realnych okazji MŚ,
    # zostaw dotychczasowe dane (tryb pokazowy). Przełączamy na MŚ dopiero,
    # gdy propsy i kursy dają choć jedną okazję.
    #
    # Sama siatka NIE wystarczy, żeby podmienić dane: wznowione typy niosą swoje
    # mecze, ale nie zawodników, formy ani kursów. Cykl, w którym feed padł na
    # całej linii (zero typów I zero zawodników), zostawia więc poprzedni zrzut —
    # inaczej ratując 20 typów wyzerowalibyśmy resztę aplikacji.
    if not value_bets_pub or not (value_bets or players_out):
        print(
            f"Na razie 0 okazji ({len(matches_out)} meczów, "
            f"{len(players_out)} zawodników ma propsy). Nie podmieniam danych "
            "aplikacji — czekam na pełne propsy/kursy."
        )
        # diagnoza "czemu 0": rozkład powodów odrzuceń zamiast ciszy
        powody: dict[str, int] = {}
        for o in odrzucenia.values():
            powody[o["powod"]] = powody.get(o["powod"], 0) + 1
        if powody:
            print("Powody odrzuceń: " + ", ".join(
                f"{k}={v}" for k, v in sorted(powody.items(), key=lambda x: -x[1])
            ))
        _dump("odrzucenia_zero_okazji.json", list(odrzucenia.values()))
        _dump_pokrycie()
        # drabinki żyją własnym życiem — dzień bez typów modelu (np. cały
        # rynek w kwarantannie) nadal ma karty do rozliczenia.
        # Typy POMIAROWE też muszą tędy przejść: cykl bez ani jednej okazji to
        # dokładnie ten, w którym progi wycięły wszystko — czyli najciekawszy
        # dla pomiaru, a dotąd jedyny, który go gubił.
        _rozlicz_i_zapisz([], [], niedostepni,
                          odrzucone_pomiar=odrzucone_pomiar,
                          poza_publikacja=typy_poza_publikacja,
                          drabinki=drabinki_typy,
                          urealnienie=korekta_pokazywana)
        return

    _dump_pokrycie()
    # UWAGA NA KOLEJNOŚĆ: urealnienie dotyczy WYŁĄCZNIE tego dumpu.
    # `value_bets` (surowe) idą niżej do `_rozlicz_i_zapisz`, czyli do księgi —
    # gdyby trafiła tam liczba już poprawiona, następny pomiar liczyłby się
    # z niej i korekta zjadałaby własny ogon.
    #
    # Brama „ujemna po korekcie" MUSI stać także tutaj, nie tylko przy świeżych
    # typach. Prawie cała lista to typy WZNOWIONE z rejestru publikacji
    # (dry-run 2026-07-29: 49 pozycji na liście, z czego świeżych 1) — brama
    # przy narodzinach typu przepuszczałaby więc praktycznie wszystko, a user
    # dalej widziałby karty z ujemną wartością. Wyjątek robimy dla sugestii
    # (nie mają kursu, więc nie ma czego liczyć).
    #
    # PODŁOGA KURSU stoi w tym samym miejscu i z tego samego powodu (zgłoszenie
    # usera 2026-08-01: „zaczęły się pojawiać kursy 1,03, a miało być minimum
    # 1,19"). Typ raz opublikowany wracał tu z księgi BEZ ŻADNEJ bramy, więc
    # kursy sprzed naprawy nowych rynków (1,05–1,09) trzymały się listy do
    # gwizdka. Decyzja usera: typ, który nie przechodzi DZISIEJSZYCH progów,
    # schodzi z listy — w księdze zostaje i normalnie się rozliczy.
    do_pokazania = []
    zdjete = 0
    poza_kursem = 0
    # POWÓD ZDJĘCIA PER TYP — księga musi wiedzieć, że tego typu user NIE
    # widział (2026-08-01). Do dziś `_rozlicz_i_zapisz` dostawał surowe
    # `value_bets`, czyli listę SPRZED bram wyświetlania, więc typ zdjęty tutaj
    # liczył się w Skuteczności jako opublikowany. Przy podłodze kursu ta luka
    # od razu urosła: typ po 1,05 nie trafia na stronę, a wpadał do statystyki.
    zdjete_klucze: dict[str, str] = {}
    for b in value_bets_pub:
        if not b.get("sugestia") and not betting.kurs_w_widelkach(b.get("kurs")):
            poza_kursem += 1
            zdjete_klucze[_klucz_publikacji(b)] = "kurs_poza_widelkami"
            continue
        u = _urealnij_do_pokazania(b)
        if not u.get("sugestia") and u.get("kurs") and (u.get("ev_pct") or 0.0) < 0.0:
            zdjete += 1
            zdjete_klucze[_klucz_publikacji(b)] = "ujemna_po_korekcie"
            continue
        # ⚑ ŚCIĄGNIĘCIE DO CENY DOPIERO TUTAJ — ZA BRAMĄ (2026-08-12).
        # Kolejność jest treścią decyzji właściciela, nie szczegółem: gdyby
        # ściągnięta liczba trafiła WYŻEJ, brama „ujemna po korekcie" zdjęłaby
        # z listy setki typów (zmierzone: 967 -> 64 przy w=0,10). Selekcja
        # zostaje więc na naszej liczbie, a klient widzi liczbę uczciwą.
        # Patrz `rozliczanie.waga_sciagania`.
        u = _sciagnij_karte_do_ceny(u)
        do_pokazania.append({k: v for k, v in u.items() if k != "kal_tau"})
    if poza_kursem:
        print(f"Zdjęte przez podłogę kursu: {poza_kursem} typów poza "
              f"{betting.MIN_ODDS}–{betting.MAX_ODDS} (głównie wznowione "
              f"sprzed zmian bram)")
    if zdjete:
        print(f"Zdjęte po urealnieniu szansy: {zdjete} typów miało ujemną "
              f"wartość przy pokazywanej liczbie (zostaje {len(do_pokazania)})")
    # --- CO TRAFIA NA LISTĘ I W JAKIEJ KOLEJNOŚCI (decyzja usera 2026-08-01) ---
    #
    # Zgłoszenie: „nie może być tak, że będziemy wrzucać milion typów; w
    # zakładkach mają być najlepsze". Zmierzone tego dnia: 102 typy na 29
    # meczach, po 3-5 linii z jednego spotkania, kolejność przypadkowa.
    #
    # CZYM SORTUJEMY — i czym NIE. Wszystkie sygnały, które model produkuje
    # sam o sobie, okazały się ODWRÓCONE (pomiar na 114 rozliczeniach profilu
    # „poniżej, kurs 1,6+", podział na tercyle):
    #     wg deklarowanej pewności   górna 1/3 −4,2%   dolna 1/3 +26,6%
    #     wg deklarowanej przewagi   górna 1/3 −41,2%  dolna 1/3 +32,5%
    #     wg wysokości kursu         górna 1/3 +18,9%  dolna 1/3 −10,2%
    # Dlatego NIE sortujemy po pewności ani po przewadze — to przepis na
    # wybranie najgorszych. Zostają sygnały strukturalne: udowodniona przewaga
    # RYNKU nad ceną (rozliczanie.przewaga_rynkow) i wysokość kursu.
    #
    # LIMIT RÓŻNORODNOŚCI JEST KONIECZNY, nie kosmetyczny: bez `PER_RYNEK`
    # jedyny rynek z dodatnią przewagą zajmował 20 miejsc na 20 (zmierzone),
    # czyli sortowanie po cichu robiło się amputacją pozostałych rynków —
    # dokładnie tego, czego user nie chce. Rynek ma czekać niżej, aż model się
    # go nauczy, a nie znikać.
    # Same limity i selekcja siedzą na poziomie modułu
    # (`wybierz_liste_publikowana`) — tam też jest opis, dlaczego liczą się
    # per dzień meczowy i czemu typ raz pokazany wchodzi poza limitem.
    _ukryte: set[str] = set()
    _przewaga, _pasma, _log_przewagi = {}, {}, {}
    with rozliczanie.warstwa_uczenia("przewaga_rynkow") as _w:
        _log_przewagi = rozliczanie._migruj_log(
            supa.get_key("typy_log") or {}
        )
        _przewaga = rozliczanie.przewaga_rynkow(_log_przewagi)
        _pasma = rozliczanie.przewaga_pasm(_log_przewagi)
        # RYNEK, KTÓRY „TRAGICZNIE NIE WCHODZI", schodzi ze strony do czasu
        # dopracowania (decyzja usera 2026-08-01). Kryterium jest statystyczne,
        # nie uznaniowe — patrz rozliczanie.rynki_do_ukrycia. Zła seria NIE
        # wystarcza: rynek musi być istotnie gorszy od ceny bukmachera, na
        # próbie co najmniej 60 rozliczeń, przez trzy dni z rzędu.
        _hist_przewagi = rozliczanie.get_key_ok_przewagi()[0] or {}
        _wczoraj = sorted(_hist_przewagi)[-1] if _hist_przewagi else None
        _ukryte = rozliczanie.rynki_do_ukrycia(
            _przewaga, _hist_przewagi,
            set((_hist_przewagi.get(_wczoraj) or {}).get("ukryte") or ())
            if _wczoraj else set(),
        )
        _w.opisz(n=len(_przewaga),
                 opis=f"bije cenę {sum(1 for v in _przewaga.values() if v['przewaga'] > 0)}"
                      f" z {len(_przewaga)}, ukryte: {', '.join(sorted(_ukryte)) or 'brak'}")

    # ILE TYPÓW MODEL WYSTAWIŁ W TYM MECZU — liczone z PULI PRZED SELEKCJĄ
    # (kandydaci z listy + te zdjęte bramami, bo jedno i drugie świadczy o tym,
    # ile o meczu wiemy). Wchodzi do `moc_listy`; szczegóły i zastrzeżenia przy
    # `PROG_BOGATEGO_MECZU`.
    _kandydatow_w_meczu: Counter = Counter(
        b.get("mecz_id") for b in (do_pokazania + typy_poza_publikacja)
        if not b.get("sugestia")
    )

    def _klucz_listy(b: dict):
        # ⚑ JEDNA MIARA DLA WEJŚCIA I DLA KOLEJNOŚCI (2026-08-14).
        #
        # Do 14.08 o wejściu na listę decydowała zmierzona PRZEWAGA RYNKU
        # I PASMA (czy bijemy cenę), a o kolejności na ekranie — zupełnie inna
        # liczba (p × √kurs, liczona dodatkowo we froncie). Produkt miał więc
        # dwie różne definicje „najlepszego typu", a klient widział skutek obu
        # naraz, nie znając żadnej.
        #
        # Teraz decyduje `moc_listy` — ta sama liczba, którą pokazujemy jako
        # kolejność „polecane". Za nią stoi pomiar (tercje 419 rozliczeń: góra
        # +0,6%, dół −11,6%) i premia za bogactwo materiału meczu.
        #
        # Przewaga rynku NIE znika z produktu: dalej decyduje o UKRYCIU rynku
        # „tragicznie niewchodzącego" (`_ukryte` wyżej) i dalej jest raportowana
        # w logu cyklu. Zmienił się jej zakres: z układania kolejności na
        # wskazywanie, czego model jeszcze nie umie.
        ma_rachunek = bool(b.get("czynniki")) and (b.get("ci") or [None])[0] is not None
        return (moc_listy(b, _kandydatow_w_meczu.get(b.get("mecz_id"), 0)),
                ma_rachunek)

    # KSIĘGA MA WIEDZIEĆ, ŻE ODCIĘTY SELEKCJĄ TYP NIE BYŁ NA STRONIE
    # (2026-08-06, decyzja usera: „w Skuteczności tylko typy ukazane na
    # liście, reszta niech uczy się w tle"). Selekcja weszła 01.08 jako trzecia
    # brama wyświetlania, ale jako JEDYNA nie meldowała księdze zdjęć — świeży
    # typ wycięty z dwudziestki szedł do `typy_log` jako opublikowany
    # i Skuteczność liczyła go do bilansu dnia. Zmierzone 06.08: 22 z 26 wpisów
    # „opublikowanych" w oknie ostatniego cyklu nie było na stronie, a księga
    # trzymała 154 typy „na liście" wobec 20 w `value_bets`. Typów WZNOWIONYCH
    # `wybierz_liste_publikowana` nie zdejmuje w ogóle (patrz tam).
    # LISTA DNIA: raz ogłoszona, do końca dnia się nie zmienia. Manifest
    # trzyma skład każdej domkniętej doby produktowej — nieudany odczyt
    # traktujemy jak „brak domknięć" i NIE zapisujemy go z powrotem, żeby
    # jeden timeout nie skasował dnia (ta sama zasada co przy rejestrze
    # publikacji, [[supabase-read-modify-write]]).
    _manifest_raw, _manifest_ok = supa.get_key_ok(LISTA_DNIA_KLUCZ)
    _zamkniete = wczytaj_zamkniete(_manifest_raw if _manifest_ok else None)
    if _zamkniete:
        print("Lista dnia — domknięte: " + ", ".join(
            f"{d} ({len(k)} typów)" for d, k in sorted(_zamkniete.items())))
    elif not _manifest_ok:
        print("UWAGA: nie udało się odczytać manifestu listy dnia — ten cykl "
              "pracuje bez domknięć (nie nadpisujemy go)")
    lista_pub, _zdjete_selekcja, _z_dnia = wybierz_liste_publikowana(
        do_pokazania, _klucz_listy, _ukryte, zamkniete=_zamkniete,
    )
    for _k, _powod in _zdjete_selekcja.items():
        zdjete_klucze.setdefault(_k, _powod)
    _pokazane_wracaja = sum(1 for b in lista_pub if b.get("wznowiony"))
    if len(do_pokazania) > len(lista_pub):
        print(f"Lista publikowana: {len(lista_pub)} z {len(do_pokazania)} "
              f"kandydatów (na KAŻDĄ dobę produktową max {LISTA_CAP}, "
              f"{LISTA_PER_MECZ}/mecz, {LISTA_PER_RYNEK}/rynek, "
              f"{LISTA_PER_RODZINA}/rodzinę); reszta zostaje w puli kuponów")
    if _z_dnia:
        print("Lista wg doby produktowej (6:00→6:00): " + ", ".join(
            f"{d} {n}" for d, n in sorted(_z_dnia.items()))
            + (f" (w tym {_pokazane_wracaja} pokazanych wcześniej — te wchodzą "
               f"poza limitem)" if _pokazane_wracaja else ""))
    # DOMKNIĘCIE — po selekcji, bo zamrażamy dokładnie to, co idzie na stronę
    _swiezo_domkniete: list[str] = []
    _zamkniete_meta: dict = dict(_manifest_raw or {}) if _manifest_ok else {}
    if _manifest_ok:
        _manifest_out, _swiezo_domkniete = domknij_dni(
            lista_pub, _manifest_raw, _teraz_publikacji)
        if _swiezo_domkniete:
            _manifest_out = przytnij_manifest(_manifest_out, _teraz_publikacji)
            _zamkniete_meta = _manifest_out
            if _dry_run():
                print(f"[dry-run] domknęłoby listę dnia: "
                      f"{', '.join(_swiezo_domkniete)}")
            elif supa.put_key(LISTA_DNIA_KLUCZ, _manifest_out):
                print("Lista dnia DOMKNIĘTA: " + ", ".join(
                    f"{d} — {len(_manifest_out[d]['klucze'])} typów"
                    for d in _swiezo_domkniete)
                    + " (od teraz skład się nie zmienia)")
            else:
                print("UWAGA: domknięcia listy dnia NIE UDAŁO SIĘ zapisać — "
                      "lista pozostaje otwarta do następnego cyklu")
                _zamkniete_meta = dict(_manifest_raw or {})
    _przyciete_rej = przytnij_rejestr_do_listy(lista_pub, _teraz_publikacji)
    if _przyciete_rej:
        print(f"Rejestr publikacji: przycięto {_przyciete_rej} wpisów z tego "
              f"cyklu, które nie weszły na listę (rejestr trzyma tylko to, "
              f"co user widział)")
    # SKŁAD LISTY, NIE TYLKO DŁUGOŚĆ — po każdej zmianie bram trzeba widzieć,
    # CO weszło (lekcja z rozszerzenia okna zgody 04.08: dry-run pokazał 20
    # typów zamiast 18 i wyglądało dobrze, dopóki nikt nie spojrzał, że trzy
    # z nich są z rynku w kwarantannie). Limity liczą się per dzień, ale
    # o przesycie decyduje to, co user widzi na CAŁEJ liście.
    _rodziny_razem: dict = {}
    for _b in lista_pub:
        if not _b.get("sugestia"):
            _r = _rodzina_statystyki(_b.get("rynek_kod"))
            _rodziny_razem[_r] = _rodziny_razem.get(_r, 0) + 1
    if _rodziny_razem:
        print("Skład listy wg rodziny: " + ", ".join(
            f"{k} {v}" for k, v in sorted(
                _rodziny_razem.items(), key=lambda x: -x[1])))
    if _przewaga:
        _bija = [k for k, v in _przewaga.items() if v["przewaga"] > 0]
        print(f"Przewaga nad ceną: {len(_bija)} z {len(_przewaga)} rynków "
              f"bije kurs" + (f" ({', '.join(_bija)})" if _bija else ""))
    # ILE NASZEJ LICZBY WARTO MIESZAĆ Z CENĄ — pomiar, nie brama (2026-08-03).
    # Pierwszy odczyt był niewygodny (całość w*=0,00, czyli sama cena
    # przewiduje lepiej), więc ma być widoczny w KAŻDYM cyklu, a nie raz
    # w notatce. Patrz `rozliczanie.waga_rynku_pomiar`.
    with rozliczanie.warstwa_uczenia("waga_rynku") as _w:
        _wagi = rozliczanie.waga_rynku_pomiar(_log_przewagi)
        _w.opisz(n=len(_wagi), opis=", ".join(
            f"{k} w={v['w']:.2f}" for k, v in
            sorted(_wagi.items(), key=lambda kv: -kv[1]["n"])[:4]) or "brak segmentów")
        if _wagi:
            print("Waga naszej liczby vs cena (w=0 cena wie lepiej, w=1 my): "
                  + ", ".join(
                      f"{k} w={v['w']:.2f} (n={v['n']}, ROI {v['roi']:+.0%})"
                      for k, v in sorted(_wagi.items(), key=lambda kv: -kv[1]["n"])
                  ))
    if _pasma:
        print("Przewaga wg pasma ceny: " + ", ".join(
            f"{k} {v['przewaga']:+.4f} (weszło {100*v['hit']:.0f}%, n={v['n']})"
            for k, v in _pasma.items()))
    # DZIENNY STEMPEL POMIARU — bez historii etap 3 jest zgadywanką: po
    # dołożeniu potwierdzonych składów nie dałoby się powiedzieć, czy rynek
    # drgnął, bo nie byłoby z czym porównać (patrz rozliczanie.zapisz_przewage).
    if _ukryte:
        print("Ukryte do czasu dopracowania (istotnie gorsze od ceny, "
              f"{rozliczanie.UKRYCIE_DNI} dni z rzedu): {', '.join(sorted(_ukryte))}")
    if not _dry_run() and (_przewaga or _pasma):
        try:
            if rozliczanie.zapisz_przewage(_przewaga, _pasma, ukryte=_ukryte):
                print("Historia przewagi: stempel dnia zapisany")
        except Exception as e:
            print(f"Historia przewagi pominięta ({e})")
    # RYNEK WSTRZYMANY — MÓWIMY O TYM, ZAMIAST MILCZEĆ (2026-08-03).
    #
    # Kwarantanna blokuje NOWE zobowiązania z rynku, ale typu raz pokazanego nie
    # wycofujemy: cena jest zamrożona, user mógł go zagrać. Logika jest spójna
    # (sprawdzone: wszystkie 8 takich typów na stronie to typy WZNOWIONE,
    # wystawione zanim rynek wpadł do kwarantanny; świeżych zero) — ale strona
    # nie mówiła o tym ani słowa, a generator kuponów po cichu je pomijał.
    # Człowiek widział typ i nie miał jak wiedzieć, że sami przestaliśmy ten
    # rynek polecać. To jest informacja o ZAKŁADZIE, nie o naszej kuchni.
    for b in lista_pub:
        # ETYKIETA MA MÓWIĆ PRAWDĘ O TYM ZAKŁADZIE (2026-08-04). Do dziś brała
        # sam kod rynku, więc typ ze strony, którą dalej polecamy, dostawał
        # ostrzeżenie „sami przestaliśmy ten rynek polecać" — nieprawdziwe
        # odkąd rynek nie zdejmuje strony z własnym werdyktem.
        if _rynek_wstrzymany(b) or _strona_wstrzymana(b):
            b["rynek_wstrzymany"] = True

    # ⚑ KOLEJNOŚĆ NA LIŚCIE — JEDNA MIARA, LICZONA PRZY DUMPIE (2026-08-14).
    #
    # Dotąd kolejność „polecane" liczył FRONT (`moc` w DruzynyTablica), bo
    # `rank_score` z backendu znaczy co innego w każdym kanale i jest zerem
    # przy typach wznowionych — czyli przy większości listy. Front liczył
    # p × √kurs i tyle; nie miał jak uwzględnić niczego, czego nie widzi.
    #
    # Teraz backend podaje gotową liczbę `moc_listy`, a front tylko z niej
    # korzysta (z fallbackiem na starą formułę dla starszych danych). Liczona
    # jest TU, przy dumpie — więc obejmuje typy wznowione z rejestru, które
    # przechodzą obok całej pętli scoringu ([[wznowione-omijaly-bramy]]).
    #
    # Poza p × √kurs wchodzi jeden zmierzony czynnik: BOGACTWO MATERIAŁU
    # MECZU (ile typów model w tym meczu wystawił). Liczby i zastrzeżenia przy
    # `PROG_BOGATEGO_MECZU`. To zmienia WYŁĄCZNIE kolejność — żaden typ przez
    # to nie znika z listy ani nie zmienia swojej szansy.
    #
    # ⚑ Ta sama liczba co przy selekcji (`_kandydatow_w_meczu`, pula PRZED
    # bramami). Gdyby liczyć ją z gotowej listy, kolejność zależałaby od
    # wyniku selekcji, a selekcja od kolejności — i przy okazji sam limit
    # dzienny odbierałby premię meczom, którym się ona należy.
    for b in lista_pub:
        _ile = _kandydatow_w_meczu.get(b.get("mecz_id"), 0)
        if _ile >= PROG_BOGATEGO_MECZU:
            b["mecz_bogaty"] = True
        b["moc_listy"] = moc_listy(b, _ile)
    _bogate = sum(1 for b in lista_pub if b.get("mecz_bogaty"))
    if _bogate:
        print(f"Kolejność listy: {_bogate} typów z meczów, o których model ma "
              f"dużo do powiedzenia ({PROG_BOGATEGO_MECZU}+ kandydatów w "
              f"meczu) — premia {PREMIA_BOGATEGO_MECZU:.2f} w „polecanych”")
    _wstrzymane = sum(1 for b in lista_pub if b.get("rynek_wstrzymany"))
    if _wstrzymane:
        print(f"Rynki wstrzymane: {_wstrzymane} typów na liście pochodzi "
              f"z rynków/stron ze słabszą serią — od 14.08 wchodzą normalnie, "
              f"z etykietą na karcie i na końcu kolejności; do kuponów nie")
    _dump("value_bets.json", lista_pub)
    _dump("matches.json", list(matches_out.values()))
    _dump("players.json", list(players_out.values()))
    _dump("druzyny_forma.json", scal_forme_druzyn(druzyny_forma, lista_pub))
    _dump("odds_superbet.json", odds_grid)   # siatka kursów do TOP POKRYCIA
    _dump("odrzucenia.json", odrzucenia_out)  # "czemu nie ma typu" per mecz
    print(f"Rejestr odrzuceń: {len(odrzucenia_out)} wpisów, "
          f"pomiar progów: {len(odrzucone_pomiar)} typów przy progu")
    # PULA LEGÓW pod generator kuponów NA ŻĄDANIE (frontend składa kupon w TS
    # z tej samej, przeanalizowanej puli — te same legi co automatyczne kupony).
    # Odchudzona o ciężkie pola (czynniki/uzasadnienie/rozkład) — zbędne do składania.
    _POLA_LEGA = (
        "mecz_id", "mecz", "kickoff_ts", "podmiot_id", "podmiot", "druzyna",
        "przeciwnik", "rynek_kod", "rynek", "linia", "strona", "kurs", "bukmacher",
        "p_model", "matchup", "rotacja", "miekka_linia", "swieze_sklady",
        "ev_pct", "ev_uk", "kurs_oczekiwany", "ryzyko", "oczekiwane_minuty",
        # PODATEK (2026-07-31): `ev_pct` jest brutto i tym decydują bramy,
        # `ev_netto` to liczba pokazywana userowi. Oba muszą jechać aż do
        # typy_log, bo inaczej kupony z generatora na żądanie byłyby jedynym
        # miejscem w systemie bez informacji, w jakim trybie je liczono.
        "ev_netto", "tryb_podatku",
        # wyzsza_linia/xi_sygnal/kurs_ref — muszą jechać aż do typy_log przez
        # kupony własne (generator na żądanie), inaczej te legi są ślepą
        # plamą w diagnostyce miękkich linii/sygnałów XI/marży UK (patrz
        # kupony.py:_leg_dict i rozliczanie.py:rozlicz, ten sam fix)
        "wyzsza_linia", "xi_sygnal", "kurs_ref",
        # pewnosc — do filtrowania w GeneratorKuponu jak backendowy styl "value"
        "pewnosc",
        # podmiot_typ — generator oznacza legi DRUŻYNOWE (gole/rożne/kartki
        # drużyn) odróżnialnie od propsów zawodniczych
        "podmiot_typ",
        # matchup_styl — flaga pełnych matchupów stylu; musi płynąć przez
        # kupony (własne i automatyczne) do typy_log, żeby diagnostyka
        # kategorii mierzyła skuteczność analogii stylu
        "matchup_styl",
        # ci — waga zaufania do p_model przy składaniu (kupony.py:_waga_modelu
        # / kuponBuilder.wagaModelu). BEZ tego generator na żądanie liczyłby
        # inne wagi (fallback z pewności) niż silnik automatyczny na tej
        # samej puli — cicha rozbieżność mimo parytetu algorytmów
        "ci",
        # rachunek — „skąd wzięła się ta liczba" (betting.stempel_rachunku).
        # To CZWARTA biała lista na drodze stempla, obok `rec_pewniaka`,
        # `_dopisz_nowe` i `_kupon_leg_do_logu`. Od 12.08 endpoint kuponów
        # własnych odtwarza parametry modelowe WŁAŚNIE z tej puli (zamiast
        # ufać przeglądarce), więc leg bez rachunku wchodziłby do księgi
        # uboższy niż ten sam typ opublikowany normalnie.
        "rachunek",
    )
    # ⚑ JEDEN ZAKŁAD — JEDNA SZANSA NA EKRANIE (2026-08-13).
    #
    # Pula jedzie do generatora kuponów na żądanie i do niej ZAGLĄDA user.
    # Do dziś dumpowaliśmy ją z surowym `p_model`, a lista typów pokazywała
    # tę samą pozycję po urealnieniu i po ściągnięciu do ceny. Zmierzone tego
    # dnia: 32 z 32 typów listy jest też w puli, mediana różnicy +10,5 pp,
    # maksymalnie +13,8 (Pafos FC, kartki poniżej 2,5: 61,6% na liście, 74,8%
    # w generatorze). Ten sam zakład pokazywał więc dwie różne szanse dwa
    # kliknięcia od siebie.
    #
    # `p_model` ZOSTAJE SUROWE, bo na nim składa się kupon — i tak samo robi
    # backend (`build_kupony` dostaje surowe `value_bets`). Parytet front-backend
    # jest tu warunkiem, a nie ozdobą: generator na żądanie ma dawać ten sam
    # kupon co cykl. Do POKAZANIA dochodzi osobne pole.
    _pokaz_lega = {}
    for _b in legi_pool_pub:
        try:
            _pokaz_lega[id(_b)] = _sciagnij_karte_do_ceny(
                _urealnij_do_pokazania(_b)
            ).get("p_model")
        except Exception as e:
            diagnostyka.cichy("cykl", "p_pokaz_lega", e)
    _dump("legi_pool.json", [
        {**{k: b.get(k) for k in _POLA_LEGA}, "id": i,
         "p_pokaz": _pokaz_lega.get(id(b))}
        for i, b in enumerate(legi_pool_pub)
    ])
    n_dzis = len({b["mecz_id"] for b in legi_pool_pub
                  if b["kickoff_ts"] <= time.time() + kupony.OKNO_DZIS_S})
    print(f"Pula kuponów: {len(legi_pool_pub)} legów, meczów w oknie dziennym: {n_dzis}")
    # CZY PULA W OGÓLE SIĘGA PRZEDZIAŁÓW KURSU (2026-08-03). Drugi, całkiem
    # osobny powód pustej zakładki, i taki, którego liczba legów nie zdradza:
    # kupon musi trafić w zadany przedział kursu, a iloczyn CAŁEJ puli bywa
    # niższy niż dolna granica najtańszego z nich. Zmierzone 03.08: cztery legi
    # przed gwizdkiem dawały maksymalnie 6,78, przy długoterminowych
    # przedziałach od 9,0 — żaden kupon nie mógł powstać, choć pula „była".
    _teraz_p = time.time() + kupony.MARGINES_STARTU_S
    for _etykieta, _okno, _przedzialy in (
        ("dzienny", kupony.OKNO_DZIS_S, kupony.PRZEDZIALY_DZIENNE),
        ("długoterminowy", kupony.OKNO_DLUGO_S, kupony.PRZEDZIALY_DLUGOTERMINOWE),
    ):
        _legi = [b for b in legi_pool_pub
                 if _teraz_p < b["kickoff_ts"] <= time.time() + _okno]
        _max = 1.0
        for _b in _legi:
            _max *= float(_b.get("kurs") or 1.0)
        _dolna = min(c[0] for c in _przedzialy)
        if _legi and _max < _dolna:
            print(f"  UWAGA: {_etykieta} — iloczyn WSZYSTKICH {len(_legi)} legów "
                  f"to {_max:.2f}, a najniższy przedział zaczyna się od "
                  f"{_dolna:.1f}. Żaden kupon nie ma z czego powstać.")
    fs = tempo.fallback_stats()
    n_total = fs["total_ok"] + fs["total_fallback"]
    n_spread = fs["spread_ok"] + fs["spread_fallback"]
    if fs["total_fallback"] or fs["spread_fallback"]:
        print(f"Tempo meczów: total zgadywany (2.6) {fs['total_fallback']}/{n_total}, "
              f"spread zgadywany (0.0) {fs['spread_fallback']}/{n_spread}")
    profil_kuponow = str(supa.get_key("kupony_profil") or "zbalansowany")
    if profil_kuponow not in ("bezpieczny", "zbalansowany", "agresywny"):
        profil_kuponow = "zbalansowany"
    if profil_kuponow != "zbalansowany":
        print(f"Profil kuponów: {profil_kuponow}")
    # ZMIERZONE kary korelacji legów z rozliczonych kuponów (zastępują zgadywane
    # 0.92/0.95/0.97; shrinkage do domyślnych przy małej próbie) — kupony dostają
    # uczciwsze szanse, bo legi z jednego meczu realnie nie padają niezależnie
    diag_kuponow = rozliczanie.compute_kupony_diagnostyka(
        supa.get_key("kupony_log") or {}
    )
    kary_kor = kupony.kary_korelacji_z_diagnostyki(diag_kuponow["korelacja"])
    if kary_kor != kupony.KARY_DEFAULT:
        print(f"Kary korelacji (zmierzone): {kary_kor}")
    # UCZCIWA SZANSA KUPONU: zmierzone „ile z deklarowanej szansy naprawdę
    # wchodzi" per horyzont. Bez tego kupon obiecywał 17%, a wchodził w 10%
    # (a styl „z przewagą" — 34% deklaracji przy zerze na osiemnaście).
    kal_kuponow = {}
    with rozliczanie.warstwa_uczenia("kalibracja_kuponow") as _w:
        kal_kuponow = kupony.kalibracja_kuponow_z_pomiaru(
            diag_kuponow.get("kalibracja") or {}
        )
        _w.opisz(n=len(kal_kuponow), opis=", ".join(
            f"{h} x{w}" for h, w in sorted(kal_kuponow.items())) or "brak pomiaru")
    if kal_kuponow:
        print("Urealnienie szansy kuponów (zmierzone): " + ", ".join(
            f"{h} x{w}" for h, w in sorted(kal_kuponow.items())))
    # ZMIERZONE wagi zaufania do p_model per kubełek pewności (z rozliczonych
    # typów) — składanie ufa modelowi dokładnie tyle, ile pokazały rozliczenia
    wagi_zauf: dict = {}
    with rozliczanie.warstwa_uczenia("wagi_zaufania") as _w:
        pomiar_wag = rozliczanie.compute_wagi_zaufania(
            rozliczanie._migruj_log(supa.get_key("typy_log") or {})
        )
        wagi_zauf = kupony.wagi_zaufania_z_pomiaru(pomiar_wag)
        _w.opisz(n=len(wagi_zauf), opis=", ".join(
            f"{k} {v:+.3f}" for k, v in wagi_zauf.items()) or "brak kubełków")
        if wagi_zauf:
            print("Wagi zaufania (zmierzone): " + ", ".join(
                f"{k} {v:+.3f} (n={pomiar_wag[k]['n']}, "
                f"hit {pomiar_wag[k]['hit']:.0%} vs p {pomiar_wag[k]['sr_p']:.0%})"
                for k, v in wagi_zauf.items()
            ))
    kupony_list = kupony.build_kupony(
        value_bets, legi_pool_pub, profil=profil_kuponow, kary=kary_kor,
        wagi=wagi_zauf or None, kal_szansy=kal_kuponow or None,
        # ⚑ KOREKTA STRUMIENIA JUŻ SIEDZI W `p_model` LEGA (audyt 2026-08-11).
        #
        # Leg drużynowy powstaje z `p_over_t = apply_bias(_bias_t_pelny, …)`,
        # a `_bias_t_pelny` to kalibracja rynku PLUS korekta strumienia —
        # czyli szansa w puli jest już skorygowana. Przekazanie tych samych
        # delt do `build_kupony` nakładało je DRUGI RAZ: raz w silniku, raz
        # w `szansa_z_legow`/`legi_z_wartoscia`. Przy sześciu legach ta sama
        # poprawka wchodziła do iloczynu szóstą potęgą.
        #
        # Komentarz, który tu stał, ostrzegał przed podwójnym liczeniem, ale
        # w innej parze: `kal_szansy` (stary współczynnik na gotowy kupon)
        # kontra `korekty_legow`. Tamten konflikt jest obsłużony w
        # `build_kupony`; ten — nie był widziany w ogóle.
        #
        # `kal_szansy` zostaje: on działa na szansę CAŁEGO kuponu i mierzy
        # coś innego niż korekta pojedynczego typu (zależność między legami
        # i przeszacowanie iloczynu).
        korekty_legow=None,
    )
    # znacznik: na ilu meczach kuponu składy były już POTWIERDZONE przy
    # budowie (mniejsze ryzyko anulowań/zwrotów niż na prognozach XI)
    for k in kupony_list:
        mids_k = {l["mecz_id"] for l in k["legi"]}
        k["mecze_lacznie"] = len(mids_k)
        k["mecze_ze_skladami"] = sum(1 for m in mids_k if m in conf_mids)
    if kupony_list:
        print("Kandydaci na kupony:", ", ".join(
            f"{k.get('horyzont', '?')[:5]} x{k.get('cel_label', k['cel'])} "
            f"(kurs {k['kurs_laczny']}, szansa {k['p_model']*100:.0f}%)"
            for k in kupony_list
        ))
    # BRAMA WARTOŚCI KUPONU (2026-08-05) — patrz kupony.MIN_WARTOSC_KUPONU.
    # Nie publikujemy zakładu, o którym NASZA WŁASNA liczba mówi, że traci.
    # Licznik jest obowiązkowy: żadna brama w tym projekcie nie ma prawa
    # odrzucać po cichu (zasada z 2026-08-01).
    _bez_wartosci = [k for k in kupony_list if not kupony.kupon_oplacalny(k)]
    if _bez_wartosci:
        kupony_list = [k for k in kupony_list if kupony.kupon_oplacalny(k)]
        print("Kupony zdjęte na wartości: " + ", ".join(
            f"{k.get('horyzont', '?')[:5]} x{k.get('cel_label', k['cel'])} "
            f"(kurs {k['kurs_laczny']}, szansa {k['p_model']*100:.0f}%, "
            f"z 1 zł zostaje {kupony.wartosc_brutto(k):.2f} zł)"
            for k in _bez_wartosci
        ) + f" — zostaje {len(kupony_list)}")
    # KSIĘGA DOSTAJE TO, CO NAPRAWDĘ POSZŁO NA STRONĘ (2026-08-01).
    # Typ ŚWIEŻY, zdjęty przez bramę wyświetlania (podłoga kursu albo ujemna
    # wartość po korekcie), idzie do logu z `poza_publikacja` — rozlicza się
    # i uczy kalibrację, ale nie liczy się do Skuteczności. Typów WZNOWIONYCH
    # to nie dotyczy: one były pokazane wcześniej i ich rekord w księdze jest
    # uczciwy taki, jaki jest — historii nie przepisujemy.
    if zdjete_klucze:
        _zostaja, _zdjete_swieze = [], []
        for b in value_bets:
            powod_zdjecia = zdjete_klucze.get(_klucz_publikacji(b))
            if powod_zdjecia and not b.get("wznowiony"):
                _zdjete_swieze.append({**b, "poza_publikacja": powod_zdjecia})
            else:
                _zostaja.append(b)
        if _zdjete_swieze:
            value_bets = _zostaja
            typy_poza_publikacja.extend(_zdjete_swieze)
            _pp: dict[str, int] = {}
            for _z in _zdjete_swieze:
                _pp[_z["poza_publikacja"]] = _pp.get(_z["poza_publikacja"], 0) + 1
            print(f"Do księgi jako 'poza publikacją': {len(_zdjete_swieze)} "
                  f"świeżych typów zdjętych bramą wyświetlania ("
                  + ", ".join(f"{k} {v}" for k, v in
                              sorted(_pp.items(), key=lambda x: -x[1])) + ")")
    # CIEŃ WYCENY — ile naprawdę dają potwierdzone składy (patrz
    # rozliczanie.ustaw_cienie_skladow). Bierzemy ŚWIEŻO policzone `p` dla
    # typów z meczów, gdzie skład jest już potwierdzony, a gwizdek jest blisko.
    # Typ na liście się NIE zmienia — cena i szansa zostają zamrożone z chwili
    # publikacji. To wyłącznie druga liczba obok, do porównania po rozliczeniu.
    #
    # Okno dwóch godzin, bo tyle mniej więcej przed meczem składy są pewne,
    # a jednocześnie to garstka typów na cykl — nie chcemy dokładać roboty
    # cyklowi, który i tak ledwo mieści się w limicie czasu.
    _CIEN_OKNO_S = 2 * 3600
    try:
        _teraz_cien = int(time.time())
        _cienie: dict[str, float] = {}
        for b in (list(value_bets) + list(odrzucone_pomiar or [])
                  + list(typy_poza_publikacja or [])):
            if b.get("mecz_id") not in (conf_mids or set()):
                continue
            do_gwizdka = int(b.get("kickoff_ts") or 0) - _teraz_cien
            if not 0 < do_gwizdka <= _CIEN_OKNO_S or not b.get("p_model"):
                continue
            _cienie[rozliczanie._klucz(b)] = float(b["p_model"])
        rozliczanie.ustaw_cienie_skladow(_cienie)
        if _cienie:
            print(f"Cień wyceny: {len(_cienie)} typów przeliczonych przy "
                  "potwierdzonym składzie (pomiar, nie publikacja)")
    except Exception as e:
        rozliczanie.ustaw_cienie_skladow({})
        print(f"Cień wyceny pominięty ({e})")

    # STEMPEL ROZGRYWEK NA TYPIE (2026-08-03). Księga nie zapisywała, z jakich
    # rozgrywek był typ, więc KAŻDY pomiar — kalibracja, kwarantanna, przewaga
    # nad ceną — leciał wyłącznie po rynku. A poziom bywa zupełnie inny: kartki
    # to 1,05 na drużynę-mecz w duńskiej Superlidze i 2,56 w Brasileirão B
    # (pomiar 03.08). Jedna liczba na „team_cards" opisuje więc dwa różne
    # produkty i uśrednia je do kształtu, którego nie ma żaden.
    #
    # Stempel stawiamy PRZY PUBLIKACJI, nie odtwarzamy później — dokładnie z tego
    # powodu co `ekran` ([[stempel-ekranu]]): rekord rozliczony jest zamrożony,
    # a przypisanie po fakcie zgaduje wg dzisiejszego stanu terminarza.
    for _b in value_bets:
        if not _b.get("liga"):
            _b["liga"] = (matches_out.get(_b.get("mecz_id")) or {}).get("liga", "")

    # publikacja kuponów idzie przez log (zamrożenie/anulowanie/rozliczenie)
    # wewnątrz _rozlicz_i_zapisz — kupony.json to aktywne kupony z logu
    _rozlicz_i_zapisz(value_bets, kupony_list, niedostepni,
                      conf_mids=conf_mids, odrzucone_pomiar=odrzucone_pomiar,
                      poza_publikacja=typy_poza_publikacja,
                      legi_pool=legi_pool_pub, drabinki=drabinki_typy,
                      urealnienie=korekta_pokazywana,
                      # legi kuponów mają pokazywać tę samą szansę co lista
                      # typów — patrz `rozliczanie.kupon_do_pokazania`
                      sciaganie=((_waga_karty, _marza_karty)
                                 if _waga_karty else None),
                      # policzone wyżej przy układaniu listy — nie liczymy
                      # drugi raz, bo to kolejny odczyt księgi z Supabase
                      przewaga=_przewaga, pasma=_pasma)
    _dump("meta.json", {
        "wygenerowano_ts": int(time.time()),
        "tryb": "liga" if tryb else "ms2026",
        "liga": tryb.liga_glowna if tryb else "Mistrzostwa Świata",
        "sezon": tryb.sezon if tryb else "2026",
        "zrodlo": "statshub (statystyki i historia) + Superbet (kursy)",
        "meczow_w_bazie": len(matches_out), "meczow_demo": len(matches_out),
        "meczow_kalibracja": 20, "okazji": len(value_bets),
        # zmierzone kary korelacji — generator kuponów na żądanie (frontend)
        # używa tych samych co automatyczne kupony w tym cyklu
        "kary_korelacji": kary_kor,
        # zmierzone delty wag zaufania per kubełek pewności — jw., frontend
        # stosuje te same co backend (kuponBuilder.wagaModelu)
        "wagi_zaufania": wagi_zauf,
        # RYNKI WSTRZYMANE: bez tego pusta zakładka Pewniaków wygląda na
        # awarię, a to zadziałało zabezpieczenie (rynek tracił pieniądze
        # w oknie ostatnich rozliczeń). Front tłumaczy to użytkownikowi
        # zamiast pokazywać gołą pustkę.
        "kwarantanna": {
            mk: {"roi": v["roi"], "hit": v["hit"], "sr_p": v["sr_p"],
                 "n": v["n"], "nazwa": MARKET_NAMES_PL.get(mk, mk)}
            for mk, v in (kwarantanna_rynkow or {}).items()
        },
        # STRONY WSTRZYMANE: od 2026-08-04 wstrzymanie bywa WĘŻSZE niż rynek —
        # zdejmujemy samą stronę linii, a druga strona tego samego rynku jest
        # dalej typowana. Bez tego wpisu `kwarantanna` (rynki) opowiadałaby
        # o zakładach, których nikt nie wstrzymał, i odwrotnie: strona zdjęta
        # własnym wynikiem nie miałaby w meta żadnego śladu.
        "kwarantanna_stron": {
            k: {"roi": v["roi"], "hit": v["hit"], "sr_p": v["sr_p"],
                "n": v["n"], "nazwa": v["rynek"], "strona": v["strona"]}
            for k, v in (kwarantanna_stron or {}).items()
        },
        # POWODY WSTRZYMANE: to samo co wyżej, tylko po powodzie wejścia typu
        # na listę („ambitniejsza linia", „słaby rywal"...). Front tłumaczy
        # nimi, czemu typów jest mniej niż wczoraj.
        "kwarantanna_powodow": kwarantanna_kategorii or {},
        # zapas na obstawienie w minutach — front pisze go wprost, zamiast
        # trzymać własną kopię liczby (rozjazd byłby nie do wytłumaczenia)
        "margines_startu_min": kupony.MARGINES_STARTU_S // 60,
        # LISTA DNIA — front ma powiedzieć wprost, czy dzień jest już
        # domknięty („to jest komplet na dziś"), czy jeszcze rośnie
        # („zapowiedź, dojdą kolejne"). Bez tego zamrożenie jest niewidoczne
        # i wygląda jak zwykły dzień, w którym nic nowego nie przyszło.
        "lista_dnia": {
            "godzina_domkniecia": GODZINA_DOMKNIECIA,
            "limit": LISTA_CAP,
            "dni": {
                d: {"ile": n,
                    "zamkniete_ts": (_zamkniete_meta.get(d) or {}).get(
                        "zamkniete_ts")}
                for d, n in sorted(_z_dnia.items())
            },
        },
        # zmierzone urealnienie szansy kuponu per horyzont — generator na
        # żądanie pokazuje te same liczby co kupony automatyczne
        "kalibracja_kuponow": kal_kuponow or {},
        # PRZEDZIAŁY KURSOWE KUPONÓW — jedno źródło prawdy (kupony.py).
        # Strona miała je wpisane na sztywno i po przebudowie z 30.07 nie
        # zgadzała się ani jedna etykieta: zakładka Kupony pokazywała pustkę
        # przez dwa dni, choć kupony istniały. Patrz kupony.przedzialy_publiczne.
        "przedzialy_kuponow": kupony.przedzialy_publiczne(),
        # STAN WARSTW UCZENIA tego przebiegu {"korekta_strumienia": {...}}.
        # Warstwa, która padła, do 05.08 wyglądała identycznie jak warstwa,
        # która policzyła zero — obie kończyły się pustym słownikiem i cichym
        # printem w logu Actions. Raz kosztowało to półtorej doby uczenia
        # (patrz `rozliczanie.warstwa_uczenia`). Tu jest jedyny ślad, który
        # przeżywa czyszczenie logów Actions.
        "uczenie_stan": rozliczanie.stan_uczenia(),
        # CICHE BŁĘDY tego przebiegu {"statshub:historia_druzyny": 3, ...}.
        # W meta, a nie tylko w logu, bo log GitHub Actions znika po kilku
        # dniach, a to jest jedyny ślad po danych, które przepadły.
        "ciche_bledy": diagnostyka.raport(),
    })
    # CO PRZEPADŁO PO CICHU — jedna linia na koniec przebiegu. Do 04.08 nie
    # było tego widać w ogóle: 79 miejsc łapało wyjątek i szło dalej, więc
    # ubytek danych wyglądał identycznie jak ich brak u źródła.
    diagnostyka.wypisz()
    print(rozliczanie.raport_stanu_uczenia())
    print(f"OK: {len(matches_out)} meczów, {len(value_bets)} okazji, "
          f"{len(players_out)} zawodników.")


if __name__ == "__main__":
    main()
