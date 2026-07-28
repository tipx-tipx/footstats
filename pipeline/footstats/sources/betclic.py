"""Źródło kursów: Betclic PL — DRUGI cennik, wyłącznie pod Drabinki.

Po co: karta Drabinki ma pokazywać ROZJAZD dwóch cenników. Wzorem są wpisy
typerów, gdzie niski kurs Superbetu jest DOWODEM, że zdarzenie jest pewne,
a gra się tam, gdzie za to samo płacą więcej. Betclic NIE wchodzi do modelu
(pewniaki/drużyny) — decyzja usera 2026-07-28.

Zweryfikowane 2026-07-28 (rozpoznanie Playwrightem + odtworzenie w Pythonie):
  * Betclic nie mówi JSON-em. Oferta idzie **gRPC-Web** (binarny protobuf):
    POST https://offering.begmedia.com/web/offering.access.api/
         offering.access.api.MatchService/{Metoda}
    ciało = ramka: bajt flagi 0x00 + 4 bajty długości BE + protobuf.
  * Metody (z bundla `main-*.js`):
      GetMatchesBySportWithNotifications   1=kod sportu, 3=język, 5=limit
      GetMatchesByCompetitionWithNotifications  1=id rozgrywek, 3=język
      GetMatchWithNotification             1=id meczu, 2=język,
                                           3=id kategorii (opcjonalne),
                                           4=obsługiwane funkcje (powt. enum)
  * To STRUMIEŃ serwerowy: pierwsza ramka to pełna oferta, potem połączenie
    wisi i dosyła zmiany kursów. Czytamy pierwszą ramkę i się rozłączamy —
    inaczej `requests` czeka do timeoutu.
  * Bez `supported_features` serwer przycina odpowiedź; wysyłamy
    MARKETS(1) + PLAYER_ODDS(5).
  * Kursy NIE leżą w jednym polu. Rynek trzyma zakłady w PIĘCIU miejscach:
    main_selections(16), selection_matrix(10), split_card_groups(11),
    group_markets(13), tabs(14), sliders(15) — a w matrixie i sliderach
    dodatkowo owinięte w NullableSelection. Czytanie tylko pola 16 pokazywało
    „0 zakładów" na rynkach, które na stronie mają kursy.
  * Id rozgrywek: Ekstraklasa = 221 (z adresu `…/ekstraklasa-c221`).

KIEDY SĄ RYNKI ZAWODNICZE (zmierzone 2026-07-28 na dwóch krańcach):
  * trzy dni przed meczem Ekstraklasy kategoria `ca_ftb_prp` („Statystyki")
    zawiera WYŁĄCZNIE rzuty rożne — i tak samo pusto jest wtedy u Superbetu
    i STS, więc to rytm rynku, nie brak w odczycie;
  * w dniu meczu (kwalifikacje LM) ta sama kategoria ma komplet: strzały,
    celne, spoza pola karnego, głową, faule, spalone, odbiory, kartki —
    44 zawodników z kursami w jednym meczu.
`raport_zawodniczy` sprawdza to jednym poleceniem.

GDZIE SIEDZI NAZWISKO: **w nazwie suwaka** (`Slider.name`), a NIE w
`player_ids` zakładu — te w rynkach zawodniczych są puste. Bez czytania
nazwy suwaka wszystkie linie zlewają się w bezimienną kupę.

Kursy zmieniają się w czasie → NIE cache'ujemy odpowiedzi z kursami.
"""

from __future__ import annotations

import re
import struct
from collections import defaultdict
from datetime import datetime, timezone

from curl_cffi import requests

from .scores365 import _tokeny_druzyny
from .superbet import TEAM_PL_EN, norm_name

HOST = "https://offering.begmedia.com/web/offering.access.api"
USLUGA_MECZE = "offering.access.api.MatchService"
USLUGA_MENU = "offering.access.api.SportMenuService"
BASE = f"{HOST}/{USLUGA_MECZE}"
HEADERS = {
    "content-type": "application/grpc-web+proto",
    "x-grpc-web": "1",
    "x-bg-regulation": "PL",
    "x-bg-ref-brand": "BETCLIC",
    "x-bg-ref-regulator-zone": "PL",
    "x-bg-ref-platform": "DESKTOP",
    "accept-language": "pl-PL",
    "origin": "https://www.betclic.pl",
    "referer": "https://www.betclic.pl/",
}

# MatchPageSupportedFeatures: MARKETS=1, TOP_MYCOMBI=2, HOT_BETS=3,
# BOOSTED_ODDS=4, PLAYER_ODDS=5
CECHY = (1, 5)

ID_EKSTRAKLASA = 221

# rynki zawodnicze -> nasze kody. Nazwy spisane z ŻYWEJ oferty 2026-07-28
# (kwalifikacje LM, Dinamo Zagrzeb–FC Thun): „Liczba strzałów zawodnika spoza
# pola karnego", „Liczba celnych strzałów zawodnika głową", „Liczba fauli
# zawodnika (OPTA)", „Liczba odbiorów zawodnika (OPTA)", „Liczba spalonych
# zawodnika (OPTA)", „Liczba kartek zawodnika". Dopasowujemy po SŁOWACH
# KLUCZOWYCH, bez względu na wielkość liter (lekcja z Superbetu).
# Kolejność ma znaczenie — bardziej szczegółowe wzorce najpierw.
WZORCE_RYNKOW: tuple[tuple[tuple[str, ...], str], ...] = (
    (("celn", "zza pola"), "sot_outside_box"),
    (("celn", "spoza pola"), "sot_outside_box"),
    (("zza pola",), "shots_outside_box"),
    (("spoza pola",), "shots_outside_box"),
    (("celn", "głow"), "headed_sot"),
    (("głow",), "headed_shots"),
    (("celn", "strza"), "sot"),
    (("nieceln", "strza"), "shots_off_target"),
    (("zablokowan", "strza"), "shots_blocked"),
    (("strza",), "shots"),
    (("faul", "na zawodniku"), "fouls_won"),
    (("wymuszon", "faul"), "fouls_won"),
    (("faul",), "fouls_committed"),
    (("odbi",), "tackles"),
    (("przechw",), "interceptions"),
    (("spalon",), "offsides"),
    (("kartk",), "yellow_card"),
)

# Rynki Betclica, które WYGLĄDAJĄ jak nasze, a nimi nie są — odrzucamy je
# zanim zadziałają wzorce, bo cicho zasiliłyby model cudzą statystyką:
#   * „- 1. połowa" i „(z dogrywką)" — my liczymy 90 minut,
#   * „z pola karnego" (bez „spoza") — to strzały Z POLA, osobna statystyka,
#   * „nogą" — strzały nogą, których w ogóle nie modelujemy,
#   * podania — nie mamy takiego rynku.
ODRZUCANE_WZORCE: tuple[str, ...] = (
    "połowa", "dogryw", "nogą", "podań", "podania", "asyst",
)

# nazwy rynków, których nie umiemy zaszufladkować — zbierane, nie gubione
NIEZNANE_RYNKI: set[str] = set()


# ---------------------------------------------------------------------------
# gRPC-Web: ramkowanie + minimalny protobuf (bez generowania klas z .proto)
# ---------------------------------------------------------------------------

def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _pole_varint(nr: int, wart: int) -> bytes:
    return _varint(nr << 3) + _varint(wart)


def _pole_str(nr: int, wart: str) -> bytes:
    b = wart.encode()
    return _varint(nr << 3 | 2) + _varint(len(b)) + b


def _pole_msg(nr: int, tresc: bytes) -> bytes:
    return _varint(nr << 3 | 2) + _varint(len(tresc)) + tresc


def _czytaj_varint(buf: bytes, i: int) -> tuple[int, int]:
    wynik = shift = 0
    while True:
        b = buf[i]
        i += 1
        wynik |= (b & 0x7F) << shift
        if not b & 0x80:
            return wynik, i
        shift += 7


def _dekoduj(buf: bytes, glebokosc: int = 0, maks: int = 16) -> list[tuple]:
    """Rozbiór protobufa po numerach pól (nazwy pól znamy z bundla)."""
    out: list[tuple] = []
    i = 0
    while i < len(buf):
        try:
            klucz, i = _czytaj_varint(buf, i)
        except IndexError:
            break
        nr, typ = klucz >> 3, klucz & 7
        if nr == 0:
            break
        try:
            if typ == 0:
                w, i = _czytaj_varint(buf, i)
                out.append((nr, "int", w))
            elif typ == 1:
                out.append((nr, "f64", struct.unpack("<d", buf[i:i + 8])[0]))
                i += 8
            elif typ == 5:
                out.append((nr, "f32", struct.unpack("<f", buf[i:i + 4])[0]))
                i += 4
            elif typ == 2:
                dl, i = _czytaj_varint(buf, i)
                sur = buf[i:i + dl]
                i += dl
                tekst = None
                try:
                    kand = sur.decode()
                    if sur and all(c.isprintable() or c in " \n" for c in kand):
                        tekst = kand
                except UnicodeDecodeError:
                    pass
                if tekst is not None:
                    out.append((nr, "str", tekst))
                elif glebokosc < maks:
                    out.append((nr, "msg", _dekoduj(sur, glebokosc + 1, maks)))
                else:
                    out.append((nr, "bin", sur))
            else:
                break
        except (struct.error, IndexError):
            break
    return out


def _we(pola: list[tuple], nr: int) -> list:
    """Wszystkie wartości pola `nr` (pola powtarzalne)."""
    return [w for n, _t, w in pola if n == nr]


def _wart(pola: list[tuple], nr: int, domysl=None):
    for n, _t, w in pola:
        if n == nr:
            return w
    return domysl


def _ramki(buf: bytes):
    i = 0
    while i + 5 <= len(buf):
        flaga = buf[i]
        dl = struct.unpack(">I", buf[i + 1:i + 5])[0]
        yield flaga, buf[i + 5:i + 5 + dl]
        i += 5 + dl


def _zapytaj(metoda: str, msg: bytes, timeout: int = 40,
             usluga: str = USLUGA_MECZE) -> list[tuple]:
    """POST gRPC-Web, pierwsza kompletna ramka, rozbita na pola.

    UWAGA: to strumień serwerowy. Czytamy do końca PIERWSZEJ ramki i
    zamykamy połączenie — czekanie na koniec odpowiedzi zawsze kończy się
    timeoutem (zmierzone: serwer trzyma je otwarte na dosyłanie kursów).
    """
    dane = b"\x00" + struct.pack(">I", len(msg)) + msg
    buf = bytearray()
    r = requests.post(f"{HOST}/{usluga}/{metoda}", data=dane, headers=HEADERS,
                      impersonate="chrome124", timeout=timeout, stream=True)
    try:
        if r.status_code != 200:
            raise RuntimeError(f"Betclic {metoda}: HTTP {r.status_code}")
        for chunk in r.iter_content():
            buf.extend(chunk)
            if len(buf) >= 5:
                dl = struct.unpack(">I", bytes(buf[1:5]))[0]
                if len(buf) >= 5 + dl:
                    break
    finally:
        r.close()
    for flaga, tresc in _ramki(bytes(buf)):
        if not flaga & 0x80 and tresc:
            return _dekoduj(tresc)
    return []


# ---------------------------------------------------------------------------
# Odczyt oferty
# ---------------------------------------------------------------------------

def _ts_utc(iso: str | None) -> int:
    """'2026-07-31T16:00:00.0000000Z' -> sekundy unix (0 gdy nie da się)."""
    if not iso:
        return 0
    try:
        czysty = re.sub(r"\.\d+Z?$", "", iso).rstrip("Z")
        return int(datetime.fromisoformat(czysty)
                   .replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return 0


def _mecz_z_pol(m: list[tuple]) -> dict:
    """Wiadomość Match -> nasz słownik (pola wg schematu z bundla)."""
    nazwa = _wart(m, 2, "") or ""
    strony = [s.strip() for s in nazwa.split(" - ")]
    rozgr = _wart(m, 8, []) or []
    druzyny = []
    for c in _we(m, 12):
        druzyny.append({
            "id": _wart(c, 2),
            "nazwa": _wart(c, 3),
            "skrot": _wart(c, 4),
            "gracze": [
                {"id": _wart(g, 1), "nazwa": _wart(g, 3),
                 "kurs": _wart(g, 2), "status": _wart(g, 4)}
                for g in _we(c, 5)
            ],
        })
    return {
        "id": _wart(m, 1),
        "nazwa": nazwa,
        "gospodarz": strony[0] if len(strony) == 2 else None,
        "gosc": strony[1] if len(strony) == 2 else None,
        "start_utc": _wart(m, 3),
        "kickoff_ts": _ts_utc(_wart(m, 3)),
        "rynkow_otwartych": _wart(m, 7),
        "rozgrywki": _wart(rozgr, 2),
        "rozgrywki_id": _wart(rozgr, 1),
        "kraj": _wart(rozgr, 5),
        "kategorie": [{"id": _wart(k, 2), "nazwa": _wart(k, 3)}
                      for k in _we(m, 10)],
        "druzyny": druzyny,
        "_pola": m,
    }


def _tekst(w) -> str:
    """Wartość pola jako tekst — dekoder czasem oddaje pustą wiadomość ([])
    zamiast pustego napisu, a wtedy `.lower()` wywala cały odczyt."""
    return w if isinstance(w, str) else ""


def _zaklady(rynek: list[tuple], sciezka: str = "",
             podmiot: str = "") -> list[dict]:
    """Wszystkie zakłady rynku — z każdego miejsca, gdzie Betclic je trzyma.

    `podmiot` to etykieta gałęzi, w której zakład siedzi. **W rynkach
    zawodniczych to NAZWISKO** — zmierzone 2026-07-28 na kwalifikacjach LM:
    „Liczba strzałów zawodnika spoza pola karnego" ma 88 zakładów w suwakach,
    a każdy suwak to jeden gracz (`Slider.name` = 'Miha Zajc'), zaś
    `player_ids` w samym zakładzie jest PUSTE. Bez czytania nazwy suwaka
    wszystkie linie zlewały się w jedną kupę bez właściciela.
    """
    out: list[dict] = []

    def dodaj(s: list[tuple], gdzie: str, kto: str) -> None:
        out.append({
            "nazwa": _wart(s, 10),
            "kurs": _wart(s, 12),
            "gracze": _we(s, 16),
            "sciezka": gdzie,
            "podmiot": kto,
        })

    for s in _we(rynek, 16):                       # main_selections
        dodaj(s, sciezka, podmiot)
    for m in _we(rynek, 10):                       # selection_matrix
        for ns in _we(m, 1):                       # NullableSelection
            for s in _we(ns, 1):
                dodaj(s, sciezka, podmiot)
    for sc in _we(rynek, 11):                      # split_card_groups
        etykieta = _tekst(_wart(sc, 1))
        for s in _we(sc, 2):
            dodaj(s, f"{sciezka}/{etykieta}", etykieta or podmiot)
    for g in _we(rynek, 13):                       # group_markets
        etykieta = _tekst(_wart(g, 2))
        out += _zaklady(g, f"{sciezka}/{etykieta}", etykieta or podmiot)
    for tab in _we(rynek, 14):                     # tabs
        etykieta = _tekst(_wart(tab, 1))
        for r in _we(tab, 2):
            out += _zaklady(r, f"{sciezka}/{etykieta}", etykieta or podmiot)
    for sl in _we(rynek, 15):                      # sliders (linie per gracz)
        etykieta = _tekst(_wart(sl, 1))
        for sv in _we(sl, 3):
            for ns in _we(sv, 2):
                for s in _we(ns, 1):
                    dodaj(s, f"{sciezka}/{etykieta}[{_wart(sv, 1)}]",
                          etykieta or podmiot)
    return out


def lista_meczow(sport: str = "football", limit: int = 200) -> list[dict]:
    """Nadchodzące mecze sportu (bez rynków — sam kalendarz + id)."""
    pola = _zapytaj("GetMatchesBySportWithNotifications",
                    _pole_str(1, sport) + _pole_str(3, "pl")
                    + _pole_varint(5, limit))
    return _zbierz_mecze(pola)


def lista_meczow_rozgrywek(id_rozgrywek: int = ID_EKSTRAKLASA) -> list[dict]:
    """Mecze jednych rozgrywek (Ekstraklasa = 221)."""
    pola = _zapytaj("GetMatchesByCompetitionWithNotifications",
                    _pole_varint(1, id_rozgrywek) + _pole_str(3, "pl"))
    return _zbierz_mecze(pola)


def kalendarz(sport: str = "football", ile: int = 1000,
              na_strone: int = 200) -> list[dict]:
    """CAŁY kalendarz nadchodzących meczów, stronicowany.

    To jest właściwe źródło do parowania: `lista_meczow` oddaje tylko to, co
    Betclic wrzuca na stronę główną (~46 meczów), a chodzenie po 132
    rozgrywkach z menu to 132 zapytania. Kalendarz daje wszystko po 200 na
    stronę (zmierzone 2026-07-28).
    """
    widziane: dict[int, dict] = {}
    for offset in range(0, max(ile, 1), na_strone):
        msg = (_pole_str(2, "pl")
               + _pole_msg(3, _pole_str(1, sport))
               + _pole_varint(6, offset)
               + _pole_varint(7, na_strone))
        pola = _zapytaj("GetMatchCalendarWithNotifications", msg)
        strona = _zbierz_mecze(pola)
        if not strona:
            break
        for m in strona:
            widziane.setdefault(m["id"], m)
        if len(strona) < na_strone:
            break
    return sorted(widziane.values(), key=lambda m: m["kickoff_ts"] or 0)


def lista_rozgrywek(sport: str = "football") -> list[dict]:
    """Wszystkie rozgrywki sportu z menu Betclica: [{id, nazwa, kraj}].

    `lista_meczow` daje tylko to, co Betclic wrzuca na stronę główną (~46
    meczów), więc do pełnego pokrycia trzeba chodzić po rozgrywkach. Menu
    siedzi w INNEJ usłudze niż mecze: `SportMenuService/GetSportMenu`,
    zapytanie ma jedno pole (język).
    """
    pola = _zapytaj("GetSportMenu", _pole_str(1, "pl"), usluga=USLUGA_MENU)
    znalezione: dict[int, dict] = {}

    def chodz(p: list[tuple], kraj: str | None = None) -> None:
        for _nr, typ, w in p:
            if typ != "msg":
                continue
            # CountryItem: 1 kod, 2 nazwa, 3 rozgrywki
            kod = _wart(w, 1)
            nazwa2 = _wart(w, 2)
            moj_kraj = kraj
            if isinstance(kod, str) and isinstance(nazwa2, str) and _we(w, 3):
                moj_kraj = nazwa2
            # CompetitionItem: 1 id(int), 2 nazwa(str), 3 kod sportu(str)
            cid, nazwa, kod_sportu = _wart(w, 1), _wart(w, 2), _wart(w, 3)
            if (isinstance(cid, int) and isinstance(nazwa, str)
                    and kod_sportu == sport):
                znalezione.setdefault(cid, {
                    "id": cid, "nazwa": nazwa, "kraj": _wart(w, 4) or moj_kraj,
                })
            chodz(w, moj_kraj)

    chodz(pola)
    return sorted(znalezione.values(), key=lambda r: r["nazwa"])


def dopasuj_rozgrywki(nasze_nazwy: list[str],
                      rozgrywki: list[dict] | None = None) -> dict[str, int]:
    """{nasza nazwa rozgrywek: id u Betclica} — tylko dopasowania jednoznaczne.

    Ta sama reguła co przy drużynach: zbiory słów, najpierw równość, potem
    zawieranie, remis = brak dopasowania. „Ekstraklasa" trafia w
    „Ekstraklasa", ale „Liga Konferencji" nie zgadnie się na „Liga Mistrzów".
    """
    if rozgrywki is None:
        rozgrywki = lista_rozgrywek()
    przygotowane = [(r["id"], _tokeny(r["nazwa"])) for r in rozgrywki]
    out: dict[str, int] = {}
    for nazwa in nasze_nazwy:
        tok = _tokeny(nazwa)
        if not tok:
            continue
        rowne = {cid for cid, t in przygotowane if t == tok}
        zawarte = {cid for cid, t in przygotowane if t and (t <= tok or tok <= t)}
        for kandydaci in (rowne, zawarte):
            if len(kandydaci) == 1:
                out[nazwa] = next(iter(kandydaci))
                break
    return out


def mecze_rozgrywek(ids: list[int]) -> list[dict]:
    """Mecze wielu rozgrywek w jednej liście (bez duplikatów)."""
    widziane: dict[int, dict] = {}
    for cid in ids:
        try:
            for m in lista_meczow_rozgrywek(cid):
                widziane.setdefault(m["id"], m)
        except (RuntimeError, OSError) as e:
            print(f"Betclic: rozgrywki {cid} nie odpowiedziały ({e})")
    return sorted(widziane.values(), key=lambda m: m["kickoff_ts"] or 0)


def _zbierz_mecze(pola: list[tuple]) -> list[dict]:
    """Wyłuskaj wiadomości Match z dowolnie zagnieżdżonej odpowiedzi.

    Kalendarz przychodzi w kilku opakowaniach (sekcje „popularne", „dziś"),
    więc nie chodzimy po sztywnej ścieżce, tylko rozpoznajemy Match po
    kształcie: id(int) + nazwa(str) + data(str 20..).
    """
    znalezione: dict[int, dict] = {}

    def chodz(p: list[tuple]) -> None:
        for _nr, typ, w in p:
            if typ != "msg":
                continue
            ma_id = any(n == 1 and t == "int" for n, t, _ in w)
            nazwa = _wart(w, 2)
            data = _wart(w, 3)
            if (ma_id and isinstance(nazwa, str) and isinstance(data, str)
                    and data.startswith("20") and " - " in nazwa):
                m = _mecz_z_pol(w)
                znalezione.setdefault(m["id"], m)
            chodz(w)

    chodz(pola)
    return sorted(znalezione.values(), key=lambda m: m["kickoff_ts"] or 0)


def oferta_meczu(id_meczu: int, kategoria: str | None = None) -> dict:
    """Oferta jednego meczu; `kategoria` to id z `mecz['kategorie']`.

    Bez kategorii dostajemy zakładkę „Top". Rynki drużynowe i zawodnicze
    siedzą w kategoriach — po nie trzeba zawołać osobno.
    """
    msg = _pole_varint(1, id_meczu) + _pole_str(2, "pl")
    if kategoria:
        msg += _pole_str(3, kategoria)
    msg += b"".join(_pole_varint(4, c) for c in CECHY)
    pola = _zapytaj("GetMatchWithNotification", msg)
    wiad = _we(pola, 1)
    if not wiad or not _we(wiad[0], 1):
        return {}
    mecz = _mecz_z_pol(_we(wiad[0], 1)[0])
    rynki = []
    for sk in _we(mecz["_pola"], 11):              # sub_categories
        for r in _we(sk, 3):
            rynki.append({
                "nazwa": _wart(r, 2),
                "podkategoria": _wart(sk, 2),
                "podkategoria_id": _wart(sk, 1),
                "zaklady": _zaklady(r),
            })
    for r in _we(mecz["_pola"], 25):               # markets (płasko)
        rynki.append({"nazwa": _wart(r, 2), "podkategoria": None,
                      "podkategoria_id": None, "zaklady": _zaklady(r)})
    mecz["rynki"] = rynki
    return mecz


def _czy_statystyczna(kat: dict) -> bool:
    """Czy kategoria to „Statystyki" — tam siedzą rynki zawodnicze."""
    return ("prp" in str(kat.get("id") or "").lower()
            or "statyst" in str(kat.get("nazwa") or "").lower())


def oferta_pelna(id_meczu: int, tylko_statystyki: bool = False) -> dict:
    """Wszystkie kategorie meczu w jednym słowniku (Top + reszta).

    `tylko_statystyki` ogranicza dociąganie do kategorii „Statystyki" — pięć
    zapytań na mecz schodzi do dwóch. Przy wpinaniu drugiej ceny w Drabinki
    reszta kategorii (dokładny wynik, handicapy) i tak jest nam niepotrzebna,
    a każde zapytanie to kilka sekund.
    """
    baza = oferta_meczu(id_meczu)
    if not baza:
        return {}
    widziane = {(_tekst(r["nazwa"]), _tekst(r["podkategoria_id"]))
                for r in baza["rynki"]}
    for kat in baza.get("kategorie") or []:
        if not kat.get("id"):
            continue
        if tylko_statystyki and not _czy_statystyczna(kat):
            continue
        czesc = oferta_meczu(id_meczu, kat["id"])
        for r in czesc.get("rynki") or []:
            klucz = (_tekst(r["nazwa"]), _tekst(r["podkategoria_id"]))
            if klucz in widziane:
                continue
            widziane.add(klucz)
            r["kategoria"] = kat["nazwa"]
            baza["rynki"].append(r)
    return baza


# ---------------------------------------------------------------------------
# Rynki zawodnicze -> nasze kody
# ---------------------------------------------------------------------------

def kod_rynku(nazwa: str | None, wymagaj_zawodnika: bool = True) -> str | None:
    """Kod naszego rynku dla nazwy Betclica (albo None).

    `wymagaj_zawodnika` odsiewa rynki drużynowe: Betclic pisze je tym samym
    słownikiem („Liczba fauli (OPTA) - FC Thun" vs „Liczba fauli zawodnika
    (OPTA)"), a bez tego warunku faule drużyny wjechałyby jako faule gracza.
    """
    n = _tekst(nazwa).lower()
    if not n:
        return None
    if wymagaj_zawodnika and "zawodnik" not in n:
        return None
    if any(s in n for s in ODRZUCANE_WZORCE):
        return None
    if "z pola karnego" in n and "spoza pola" not in n:
        return None            # strzały Z POLA to inna statystyka niż nasze
    for slowa, kod in WZORCE_RYNKOW:
        if all(s in n for s in slowa):
            return kod
    return None


def linia_i_strona(nazwa: str | None) -> tuple[float | None, str | None]:
    """'Powyżej 1,5' -> (1.5, 'over'). Przecinek dziesiętny jak w PL."""
    if not nazwa:
        return None, None
    n = nazwa.lower()
    strona = "over" if "powyżej" in n or "ponad" in n else (
        "under" if "poniżej" in n else None)
    m = re.search(r"(\d+(?:[.,]\d+)?)", n)
    if not m:
        return None, strona
    return float(m.group(1).replace(",", ".")), strona


def kursy_zawodnikow(id_meczu: int, tylko_statystyki: bool = True) -> dict:
    """Kursy zawodnicze Betclica w postaci gotowej do parowania.

    Zwraca {klucz_nazwiska: {kod_rynku: {linia: {'over': kurs}}}} —
    dokładnie taki kształt jak `superbet.normalized_players`, żeby Drabinki
    mogły porównać cennik bez tłumaczy w środku. Klucz nazwiska liczony
    `superbet.norm_name`, więc „Semedo, Lisandro" i „Lisandro Semedo" to
    to samo.

    Zawodnika rozpoznajemy po `player_ids` w zakładzie (pole 16 Selection),
    NIE po nazwie rynku — nazwa bywa drużynowa i po nazwie nie odróżnisz
    „liczby strzałów" drużyny od zawodnika.
    """
    oferta = oferta_pelna(id_meczu, tylko_statystyki=tylko_statystyki)
    if not oferta:
        return {}
    gracze_id: dict[int, str] = {}
    for d in oferta.get("druzyny") or []:
        for g in d.get("gracze") or []:
            if g.get("id") and g.get("nazwa"):
                gracze_id[int(g["id"])] = str(g["nazwa"])

    out: dict[str, dict] = defaultdict(lambda: defaultdict(dict))
    nazwy: dict[str, str] = {}
    for r in oferta.get("rynki") or []:
        kod = kod_rynku(r["nazwa"])
        if kod is None:
            if "zawodnik" in _tekst(r["nazwa"]).lower():
                NIEZNANE_RYNKI.add(_tekst(r["nazwa"]))
            continue
        for z in r["zaklady"]:
            if not z["kurs"]:
                continue
            # Kto obstawiany: najpierw etykieta gałęzi (suwak = nazwisko),
            # potem spis składu po `player_ids`. Zmierzone 2026-07-28: rynki
            # zawodnicze mają PUSTE `player_ids`, więc sam identyfikator by
            # nie wystarczył.
            osoba = _tekst(z.get("podmiot"))
            if not osoba and z["gracze"]:
                try:
                    osoba = gracze_id.get(int(z["gracze"][0]), "")
                except (TypeError, ValueError):
                    osoba = ""
            linia, strona = linia_i_strona(z["nazwa"])
            if linia is None or not osoba:
                continue
            klucz = norm_name(osoba)
            if not klucz:
                continue
            nazwy.setdefault(klucz, osoba)
            out[klucz][kod].setdefault(linia, {})[strona or "over"] = float(z["kurs"])
    return {"players": {k: {kod: dict(v) for kod, v in d.items()}
                        for k, d in out.items()},
            "player_names": nazwy,
            "match": {"id": oferta["id"], "nazwa": oferta["nazwa"],
                      "kickoff_ts": oferta["kickoff_ts"]}}


# ---------------------------------------------------------------------------
# Parowanie meczów: nasze dane <-> Betclic
# ---------------------------------------------------------------------------

# maksymalna różnica kickoffu, żeby uznać dwa wpisy za ten sam mecz
OKNO_CZASU_S = 3 * 3600


# Nazwa u Betclica -> nazwa w naszych danych. Betclic spolszcza ('Dinamo
# Zagrzeb', 'FC Kopenhaga') i skraca ('Kuopio' zamiast 'KuPS'), a wtedy zbiory
# słów nigdy nie trafią. Klucz: nazwa Betclica małymi literami, bez spacji na
# brzegach. DOPISYWAĆ, gdy `raport_parowania` pokaże parę, którą człowiek widzi
# na oko — dokładnie tak, jak robi to KLUB_ALIASY dla Superbetu.
KLUB_ALIASY: dict[str, str] = {
    "dinamo zagrzeb": "Dinamo Zagreb",
    "fc kopenhaga": "Kobenhavn",
    "zalgiris kaunas": "Kauno Zalgiris",
    "kuopio": "KuPS",
    "mikkelin palloilijat": "MP",
    "ucv fc": "Universidad Central",
    "klaksvik": "Klaksvikar",
    "rapid wiedeń": "Rapid Wien",
    "steaua": "FCSB",
    "malezja": "Malaysia",
    "ac d`escaldes": "Atletic Club Escaldes",
}


def _tokeny(nazwa: str | None) -> frozenset[str]:
    """Tokeny nazwy do porównania — z apostrofami zdjętymi PRZED podziałem.

    Bez tego „Hapoel Be'er Sheva" rozpada się na `be` i `er`, a Betclic pisze
    „Hapoel Beer Sheva" — jedno słowo. Zbiory nigdy się nie zejdą, choć to ta
    sama drużyna. Czyścimy obie strony tak samo.
    """
    czysta = re.sub(r"['’`]", "", str(nazwa or ""))
    return _tokeny_druzyny(czysta)


def _pl_en(nazwa: str | None) -> str:
    """Nazwa drużyny sprowadzona do postaci porównywalnej z naszymi danymi.

    Dwa źródła rozjazdu: reprezentacje Betclic zapisuje po polsku ('Malezja'
    vs 'Malaysia') — na to jest tablica wspólna z Superbetem — oraz kluby,
    które spolszcza albo skraca (`KLUB_ALIASY` wyżej).
    """
    s = str(nazwa or "").strip()
    return KLUB_ALIASY.get(s.lower(), TEAM_PL_EN.get(s, s))


def paruj_mecze(nasze: list[dict], bc_mecze: list[dict] | None = None,
                okno_s: int = OKNO_CZASU_S) -> tuple[dict, list[dict]]:
    """Dopasuj nasze mecze do meczów Betclica. Zwraca ({klucz: mecz_bc}, luka).

    `nasze` to lista słowników z kluczami: `klucz` (cokolwiek nas identyfikuje),
    `home`, `away`, `kickoff_ts`.

    **NIE po podobieństwie tekstu** — zmierzone 2026-07-27
    ([[parowanie-nazw-druzyn]]): dla „Deportivo Riestra" najbliższe tekstowo
    jest „Deportivo Recoleta" (0,80), czyli INNY klub, a taka podmiana nie
    zostawia śladu w logu. Dlatego zbiory słów i dwa stopnie: najpierw
    identyczne zbiory po obu stronach, potem zawieranie. Na każdym stopniu
    **remis = brak pary**, nie strzał. Czas jest twardą bramą, nie punktacją.
    """
    if bc_mecze is None:
        bc_mecze = kalendarz()
    przygotowane = [
        (i, _tokeny(_pl_en(m.get("gospodarz"))),
         _tokeny(_pl_en(m.get("gosc"))), m.get("kickoff_ts") or 0)
        for i, m in enumerate(bc_mecze)
    ]
    pary: dict = {}
    zajete: set[int] = set()
    for nasz in nasze:
        th = _tokeny(nasz.get("home"))
        ta = _tokeny(nasz.get("away"))
        ts = nasz.get("kickoff_ts") or 0
        if not th or not ta:
            continue
        w_oknie = [
            (i, bh, ba) for i, bh, ba, bts in przygotowane
            if i not in zajete and bh and ba
            and (not ts or not bts or abs(bts - ts) <= okno_s)
        ]
        rowne = [i for i, bh, ba in w_oknie if bh == th and ba == ta]
        zawarte = [i for i, bh, ba in w_oknie
                   if (bh <= th or th <= bh) and (ba <= ta or ta <= ba)]
        for kandydaci in (rowne, zawarte):
            if len(kandydaci) == 1:
                pary[nasz["klucz"]] = bc_mecze[kandydaci[0]]
                zajete.add(kandydaci[0])
                break
    luka = [m for i, m in enumerate(bc_mecze) if i not in zajete]
    return pary, luka


def raport_parowania(nasze: list[dict], bc_mecze: list[dict] | None = None,
                     ile: int = 15) -> dict:
    """Ile sparowaliśmy i CO nie trafiło — z podpowiedzią kandydata.

    Bez tego dopisywanie aliasów byłoby zgadywaniem: raport pokazuje mecze
    bez pary razem z wpisem Betclica, który leci o tej samej porze i dzieli
    choć jedno słowo. Jeśli człowiek widzi, że to ta sama drużyna, wpis idzie
    do `KLUB_ALIASY`.
    """
    if bc_mecze is None:
        bc_mecze = kalendarz()
    pary, luka = paruj_mecze(nasze, bc_mecze)
    bez_pary = [n for n in nasze if n["klucz"] not in pary]
    print(f"Betclic: sparowane {len(pary)}/{len(nasze)} "
          f"({100 * len(pary) / max(len(nasze), 1):.0f}%), "
          f"oferta Betclica bez pary: {len(luka)}")
    podpowiedzi = []
    for n in bez_pary[:ile]:
        th = _tokeny(n.get("home"))
        ta = _tokeny(n.get("away"))
        ts = n.get("kickoff_ts") or 0
        kand = [
            b for b in luka
            if b["kickoff_ts"] and ts and abs(b["kickoff_ts"] - ts) <= OKNO_CZASU_S
            and (_tokeny(_pl_en(b.get("gospodarz"))) & th
                 or _tokeny(_pl_en(b.get("gosc"))) & ta)
        ]
        etykieta = kand[0]["nazwa"] if kand else "— brak w ofercie"
        print(f"   {str(n.get('home'))[:22]:24}- {str(n.get('away'))[:22]:24} -> {etykieta}")
        podpowiedzi.append({"nasz": f"{n.get('home')} - {n.get('away')}",
                            "kandydat": kand[0]["nazwa"] if kand else None})
    return {"sparowane": len(pary), "razem": len(nasze),
            "podpowiedzi": podpowiedzi}


def znajdz_zawodnika(gracze_bc: dict, nazwa: str) -> dict:
    """Kursy zawodnika z paczki Betclica po nazwisku z innego źródła.

    Ta sama reguła co `superbet.znajdz_zawodnika`: klucz dokładny, a gdy go
    nie ma — zawieranie zbiorów tokenów w OBIE strony, przyjmowane tylko gdy
    JEDNOZNACZNE. Dwóch kandydatów = brak dopasowania. Szukamy zawsze
    W OBRĘBIE JEDNEGO MECZU, więc ryzyko trafienia w cudze nazwisko jest
    małe, ale reguła zostaje ta sama — imiennicy w jednej lidze istnieją.
    """
    klucz = norm_name(nazwa)
    if klucz in gracze_bc:
        return gracze_bc[klucz]
    tokeny = set(klucz.split())
    if not tokeny:
        return {}
    trafienia = [
        v for k, v in gracze_bc.items()
        if (tk := set(k.split())) and (tokeny <= tk or tk <= tokeny)
    ]
    return trafienia[0] if len(trafienia) == 1 else {}


# ---------------------------------------------------------------------------
# Rozjazd cenników: Superbet vs Betclic
# ---------------------------------------------------------------------------

# DWIE BRAMY, bo dwa różne zagrożenia — i uwaga: NIE WOLNO ich zacieśnić tak,
# żeby zabiły przypadek „u Superbetu 1,25 bo pewne, u Betclica 2,00". To jest
# NAJCENNIEJSZY rodzaj rozjazdu i sedno wszystkich czterech wpisów typera,
# które user pokazał (Superbet 1,20–1,37, gra po 1,90–1,95).
#
# 1) WSPÓLNE LINIE. Prawdziwym śmieciem nie była wielkość różnicy, tylko to,
#    że Betclic liczył CO INNEGO: „Valmir Matoshi powyżej 9,5 strzału za 1,60"
#    (sprawdzone wzrokiem na ich stronie — tak to u nich naprawdę wygląda).
#    Taki rynek ma z naszym najwyżej JEDNĄ wspólną linię, bo drabinki leżą
#    w zupełnie innych miejscach. Gdy oba cenniki dzielą co najmniej dwie
#    linie tego samego zawodnika i rynku, mówią o tej samej rzeczy — i wtedy
#    duża różnica na jednej z nich to okazja, nie błąd.
MIN_WSPOLNYCH_LINII = 2

# 2) BEZPIECZNIK OSTATECZNY na absurdy (28,00 vs 1,95 = +1336%). Wysoko,
#    żeby nie ruszać realnych okazji: 1,20 vs 2,60 (+117%) ma przechodzić.
#    UWAGA: układu „pewniak taniej" ten limit NIE dotyczy w ogóle — decyzja
#    usera 2026-07-28: „1,20 → 2,60, dokładnie tutaj nie powinno być limitu".
#    Rozsądku pilnuje wtedy zgoda całej drabinki (niżej), a nie procent.
MAX_ROZJAZD_PCT = 200.0

# Ile może wynosić TYPOWY rozjazd na drabince, żebyśmy uznali, że oba cenniki
# liczą to samo. Jedna linia potrafi się rozjechać mocno i to jest właśnie
# okazja; ale gdy rozjeżdża się CAŁA drabinka, to znak, że Betclic mierzy inną
# statystykę — wtedy nie pokazujemy nic. To jest ten „rozsądek" zamiast limitu.
PROG_ZGODY_DRABINKI_PCT = 60.0

# „Pewniak taniej": rynek u jednego bukmachera mówi „to niemal pewne"
# (kurs <= 1,45), a drugi płaci za to sensowne pieniądze (>= 1,75).
# Dokładnie ten układ typer opisuje zdaniem „Superbet wycenia to na zaledwie
# 1,20" — niska cena jest DOWODEM, a gra się tam, gdzie płacą więcej.
PEWNIAK_MAX_KURS = 1.45
PEWNIAK_MIN_LEPSZY = 1.75

# ile porównań odrzuciły bramy — do logu, żeby obcinka nie była cicha
ODRZUCONE_ROZJAZDY: dict[str, int] = {
    "za_duzy": 0, "za_malo_wspolnych": 0, "drabinka_niezgodna": 0,
}


def rozjazd(kurs_sb: float | None, kurs_bc: float | None,
            limit_pct: float | None = MAX_ROZJAZD_PCT) -> dict | None:
    """Porównanie dwóch cen tego samego zdarzenia.

    Wzorzec z wpisów typera ([[drabinki-wzorzec-typera]]): gra się tam, gdzie
    płacą WIĘCEJ, a niski kurs drugiego bukmachera jest dowodem, że zdarzenie
    jest pewne. Zwracamy więc lepszą cenę, gorszą i o ile procent lepsza jest
    lepsza — plus szansę wynikającą z TAŃSZEJ ceny, bo to ona jest ostrożniejszą
    oceną rynku. Różnice ponad `MAX_ROZJAZD_PCT` odrzucamy (patrz wyżej).
    """
    try:
        a = float(kurs_sb or 0)
        b = float(kurs_bc or 0)
    except (TypeError, ValueError):
        return None
    if a <= 1.0 or b <= 1.0:
        return None
    lepszy_, gorszy_ = max(a, b), min(a, b)
    pewniak = (gorszy_ <= PEWNIAK_MAX_KURS and lepszy_ >= PEWNIAK_MIN_LEPSZY)
    # układ „pewniak taniej" nie ma limitu procentowego (decyzja usera):
    # 1,20 -> 2,60 to najcenniejsza okazja, nie błąd danych
    if (limit_pct is not None and not pewniak
            and lepszy_ / gorszy_ - 1 > limit_pct / 100):
        ODRZUCONE_ROZJAZDY["za_duzy"] += 1
        return None
    lepszy, gorszy = (a, b) if a >= b else (b, a)
    return {
        "superbet": round(a, 2),
        "betclic": round(b, 2),
        "lepszy": round(lepszy, 2),
        "gdzie": "superbet" if a >= b else "betclic",
        "przewaga_pct": round((lepszy / gorszy - 1) * 100, 1),
        "p_rynku": round(1.0 / gorszy, 4),
        # nazwany układ, a nie sam procent — front ma to wyróżniać
        "typ": ("pewniak_taniej"
                if gorszy <= PEWNIAK_MAX_KURS and lepszy >= PEWNIAK_MIN_LEPSZY
                else "zwykly"),
    }


def porownaj_drabinke(linie_sb: dict, linie_bc: dict) -> dict:
    """Rozjazdy dla JEDNEGO zawodnika i rynku: {linia: rozjazd}.

    Tu mieszka brama wspólnych linii (patrz `MIN_WSPOLNYCH_LINII`): dopóki
    oba cenniki nie zejdą się na co najmniej dwóch liniach, nie wierzymy, że
    liczą to samo, i nie pokazujemy nic. Dzięki temu układ „1,25 u jednego,
    2,00 u drugiego" przechodzi (bo reszta drabinki się zgadza), a rynek
    liczący inną statystykę odpada w całości.
    """
    wspolne = sorted(set(linie_sb or {}) & set(linie_bc or {}))
    if len(wspolne) < MIN_WSPOLNYCH_LINII:
        if wspolne:
            ODRZUCONE_ROZJAZDY["za_malo_wspolnych"] += len(wspolne)
        return {}
    # NAJPIERW bez limitu: patrzymy, czy drabinki jako całość się zgadzają.
    # Jedna linia może się mocno rozjechać — to jest właśnie okazja. Ale gdy
    # rozjeżdża się CAŁA drabinka, oba cenniki liczą co innego.
    surowe = {
        linia: rozjazd((linie_sb[linia] or {}).get("over"),
                       (linie_bc[linia] or {}).get("over"), limit_pct=None)
        for linia in wspolne
    }
    gapy = sorted(r["przewaga_pct"] for r in surowe.values() if r)
    if not gapy:
        return {}
    mediana = gapy[len(gapy) // 2] if len(gapy) % 2 else (
        (gapy[len(gapy) // 2 - 1] + gapy[len(gapy) // 2]) / 2)
    if mediana > PROG_ZGODY_DRABINKI_PCT:
        ODRZUCONE_ROZJAZDY["drabinka_niezgodna"] += len(gapy)
        return {}
    # drabinka spójna -> ufamy jej także tam, gdzie jedna linia odjeżdża
    return {linia: r for linia, r in surowe.items() if r}


def porownaj_kursy(sb_players: dict, bc_players: dict) -> list[dict]:
    """Wspólne linie obu bukmacherów dla jednego meczu, z rozjazdem.

    Wejście w kształcie `{klucz_nazwiska: {kod_rynku: {linia: {'over': kurs}}}}`
    — czyli to, co zwracają `superbet.fetch_stat_odds` i `kursy_zawodnikow`.
    Wynik posortowany od największego rozjazdu.
    """
    out: list[dict] = []
    for klucz, rynki_sb in (sb_players or {}).items():
        rynki_bc = znajdz_zawodnika(bc_players or {}, klucz)
        if not rynki_bc:
            continue
        for kod, linie_sb in rynki_sb.items():
            for linia, r in porownaj_drabinke(
                linie_sb, rynki_bc.get(kod) or {}
            ).items():
                out.append({"gracz": klucz, "rynek": kod, "linia": linia, **r})
    out.sort(key=lambda x: -x["przewaga_pct"])
    return out


# ---------------------------------------------------------------------------
# Sonda: czy Betclic wystawił dziś rynki zawodnicze
# ---------------------------------------------------------------------------

def raport_zawodniczy(id_rozgrywek: int = ID_EKSTRAKLASA, ile: int = 4) -> dict:
    """Jednym poleceniem: czy w tych rozgrywkach są rynki zawodnicze.

    Wypisuje, co jest w ofercie i ile zakładów ma przypisanego gracza.
    Zmierzone 2026-07-28 na Ekstraklasie (3 dni przed kolejką): kategoria
    „Statystyki" to same rzuty rożne, zakładów z graczem ZERO.
    """
    mecze = lista_meczow_rozgrywek(id_rozgrywek)
    print(f"Betclic: {len(mecze)} meczów w rozgrywkach {id_rozgrywek}")
    wynik = []
    for m in mecze[:ile]:
        oferta = oferta_pelna(m["id"])
        rynki = oferta.get("rynki") or []
        zawodnicze = [r for r in rynki
                      if any(z["gracze"] for z in r["zaklady"])]
        zakladow = sum(len(r["zaklady"]) for r in rynki)
        print(f"  {m['start_utc'][:16]} {m['nazwa'][:38]:40} "
              f"rynków={len(rynki):3d} zakładów={zakladow:4d} "
              f"zawodniczych={len(zawodnicze)}")
        for r in zawodnicze:
            kod = kod_rynku(r["nazwa"])
            print(f"      {r['nazwa']}  -> {kod or 'NIEZNANY'}")
        wynik.append({"mecz": m["nazwa"], "rynkow": len(rynki),
                      "zakladow": zakladow,
                      "zawodniczych": [r["nazwa"] for r in zawodnicze]})
    if NIEZNANE_RYNKI:
        print("nierozpoznane nazwy rynków:", sorted(NIEZNANE_RYNKI)[:20])
    return {"mecze": wynik}


if __name__ == "__main__":  # sonda z ręki: python -m footstats.sources.betclic
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == "mecz":
        o = oferta_pelna(int(sys.argv[2]))
        print(o["nazwa"], "|", o["start_utc"])
        for r in o["rynki"]:
            print(f"  [{len(r['zaklady']):3d}] {r['podkategoria'] or '-':22} {r['nazwa']}")
            for z in r["zaklady"][:4]:
                print(f"        {str(z['nazwa'])[:44]:46} {z['kurs']} gracz={z['gracze']}")
    else:
        raport_zawodniczy(int(sys.argv[1]) if len(sys.argv) > 1 else ID_EKSTRAKLASA)
