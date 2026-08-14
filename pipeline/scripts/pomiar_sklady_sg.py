# -*- coding: utf-8 -*-
"""CZY PROGNOZA SKŁADU SPORTSGAMBLERA JEST DOŚĆ DOBRA, ŻEBY NA NIEJ STAĆ.

Pytanie, od którego zależy strumień zawodniczy i drabinki: dla Ameryki
Południowej i Skandynawii NIKT nie podaje nam składów, a bez wiedzy, kto
wyjdzie w pierwszej jedenastce, typ na zawodnika jest loterią
([[strumien-zawodniczy-martwy]]).

PRÓG DECYZYJNY: **wyraźnie powyżej 68,6%**. Tyle daje własna jedenastka
liczona z rotacji minut, którą zmierzyliśmy i ODRZUCILIŚMY
(`docs/pomiar-wlasna-jedenastka.md`) — źródło zewnętrzne ma sens tylko wtedy,
gdy bije to, co już umiemy sami.

⚑ PUŁAPKA, KTÓRA ZŁAPAŁA PIERWSZE PODEJŚCIE (13.08). Po meczu SportsGambler
podmienia etykietę na „Confirmed" i pokazuje skład FAKTYCZNY. Pomiar robiony
po fakcie wychodzi wtedy 92,5% i mówi wyłącznie o tym, czy umiemy sparować
nazwiska. Dlatego mierzymy WYŁĄCZNIE z zamrożonego snapshotu pobranego PRZED
meczami (`docs/pomiar/sg-prognozy-*.json`, wszystkie wpisy „Predicted").

Uruchomienie:

    cd pipeline
    PYTHONUTF8=1 python scripts/pomiar_sklady_sg.py

CZYTA TYLKO — do produkcji nie zapisuje nic. Postęp odkłada w pliku
`docs/pomiar/sg-wyniki-<data>.json`, więc przerwany przebieg wznawia się
w miejscu, w którym stanął (statshub ma budżet zapytań i oddaje HTTP 429).
"""

from __future__ import annotations

import json
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from footstats.jobs import build_league as BL          # noqa: E402
from footstats.sources import statshub                 # noqa: E402

PL = timezone(timedelta(hours=2))
KATALOG = Path(__file__).resolve().parent.parent.parent / "docs" / "pomiar"
PROG = 0.686        # własna jedenastka z rotacji minut — patrz docstring

# Ile zapytań do statshuba wolno wypuścić w jednym przebiegu. Budżet jest
# wspólny z cyklem, a 9 cichych błędów 429 w jednym przebiegu już się zdarzyło
# — dlatego pomiar chodzi partiami i wznawia się z pliku.
LIMIT_ZAPYTAN = 400
PAUZA_S = 0.35

# Czyste sufiksy prawne/organizacyjne. „atletico", „united", „city" NIE są
# szumem: to człony, które rozróżniają kluby.
SZUM = {"fc", "cf", "sc", "ac", "afc", "cd", "ca", "club", "de", "do", "da",
        "if", "ff", "sk", "bk", "ik", "fk", "cs", "ec", "se", "ss", "as",
        "aa", "the", "el", "los", "las"}


def _plask(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def slowa(s: str) -> list[str]:
    s = _plask(s)
    for z in "-/.,()'":
        s = s.replace(z, " ")
    return [w for w in s.split() if w and w not in SZUM]


# Jednoczłonowa nazwa krótsza niż to nie wystarcza, żeby uznać klub za ten
# sam. Powód jest konkretny: „Racing Club" (Argentyna) wobec „Racing
# Santander" (Hiszpania) — samo „racing" pasuje do obu, a to dwa różne kluby
# na dwóch kontynentach. „Bragantino" wobec „Red Bull Bragantino" ma tę samą
# budowę i JEST poprawne, więc rozstrzyga długość członu: rozpoznawalna nazwa
# klubu jest długa, wspólny przedrostek ligowy — krótki.
MIN_CZLON_JEDNOWYRAZOWY = 7

# Znaczniki zespołu rezerw. Bez nich „Real Sociedad B" (LaLiga 2) paruje się
# z „Real Sociedad" (LaLiga) — inna drużyna, inny skład, a mecze potrafią być
# tego samego dnia. Znacznik po jednej stronie i brak po drugiej = różne kluby.
ZNACZNIKI_REZERW = {"b", "ii", "u19", "u20", "u21", "u23", "sub21",
                    "reserves", "res"}


def _skrot_pasuje(skrot: str, slowo: str) -> bool:
    """Czy krótki człon jest skrótem słowa: „PR" od „Paranaense".

    Dwa warunki naraz, bo sam podciąg jest stanowczo za słaby: „al" z „Al-Nasr
    Dubai" jest podciągiem „Mallorca" (m-A-L-lorca) i tak właśnie hiszpański
    mecz parował się z emirackim. Dlatego skrót musi ZACZYNAĆ SIĘ tą samą
    literą, a reszta jego liter ma wystąpić w kolejności w reszcie słowa.

    „PR" od „Paranaense" przechodzi (p, potem r). „MG" od „Mineiro" NIE (brak
    „g"), więc „Atlético MG" zostanie niesparowane zamiast wpaść na „Atlético
    Madrid" — wolimy stracić mecz z pomiaru niż policzyć skład nie tej drużyny.
    """
    if not skrot or not slowo or skrot[0] != slowo[0]:
        return False
    it = iter(slowo[1:])
    return all(c in it for c in skrot[1:])


def ta_sama_druzyna(a: str, b: str) -> bool:
    """Czy dwie nazwy opisują ten sam klub.

    Trzy warunki, OR: zbiór słów jednej nazwy zawiera się w drugiej (z progiem
    długości wyżej), każde słowo krótszej ma prefiks w dłuższej, albo krótkie
    człony są skrótami („Athletico PR" ⊂ „Athletico Paranaense").
    Podobieństwa tekstu świadomie NIE używamy — wybiera zły klub
    ([[parowanie-nazw-druzyn]]). Zmierzone na snapshocie: 78% meczów paruje
    się jednoznacznie, reszta to skróty w rodzaju „Argentinos Jrs".
    """
    wa, wb = set(slowa(a)), set(slowa(b))
    if not wa or not wb:
        return False
    if (wa & ZNACZNIKI_REZERW) != (wb & ZNACZNIKI_REZERW):
        return False        # rezerwy to nie pierwszy zespół
    if wa == wb:
        return True
    if wa <= wb or wb <= wa:
        krotsza = wa if wa <= wb else wb
        if len(krotsza) > 1:
            return True
        czlon = next(iter(krotsza))
        dluzsza = wb if wa <= wb else wa
        # jedno słowo musi się samo obronić: albo jest długie, albo jest
        # najdłuższym członem tej drugiej nazwy (czyli jej rdzeniem)
        return (len(czlon) >= MIN_CZLON_JEDNOWYRAZOWY
                or czlon == max(dluzsza, key=len))
    krotsza, dluzsza = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    return all(
        any(x.startswith(w) or w.startswith(x)
            if min(len(x), len(w)) >= 3
            else (_skrot_pasuje(w, x) if len(w) < len(x)
                  else _skrot_pasuje(x, w))
            for x in dluzsza)
        for w in krotsza
    )


def klucz_zawodnika(nazwa: str) -> tuple[str, str]:
    """(inicjał imienia, ostatni człon nazwiska) — wspólny mianownik obu źródeł.

    SportsGambler pisze „Thiago Silva", statshub „T. Silva". Sam człon
    nazwiska nie wystarcza: w jednym składzie potrafi stać dwóch braci
    („R. Carmichael" i „K. Carmichael" — zmierzone na Forward Madison FC),
    więc inicjał imienia jest częścią klucza. Gdy imienia nie ma, zostaje
    pusty inicjał i porównanie schodzi do samego nazwiska.
    """
    czesci = [c for c in _plask(nazwa).replace(".", " ").split() if c]
    if not czesci:
        return ("", "")
    nazwisko = next((c for c in reversed(czesci) if len(c) > 1), czesci[-1])
    inicjal = czesci[0][0] if len(czesci) > 1 else ""
    return (inicjal, nazwisko)


def _zgodne(a: tuple[str, str], b: tuple[str, str]) -> bool:
    """Ten sam zawodnik: nazwisko musi się zgadzać, inicjał tylko gdy znany."""
    if a[1] != b[1]:
        return False
    return not (a[0] and b[0]) or a[0] == b[0]


def trafienia(prognoza: list[str], faktyczne: list[str]) -> int:
    """Ilu z przewidzianych naprawdę wyszło w pierwszym składzie."""
    zostalo = [klucz_zawodnika(n) for n in faktyczne]
    ile = 0
    for n in prognoza:
        k = klucz_zawodnika(n)
        for i, f in enumerate(zostalo):
            if _zgodne(k, f):
                ile += 1
                zostalo.pop(i)
                break
    return ile


def wczytaj_snapshot() -> dict:
    pliki = sorted(KATALOG.glob("sg-prognozy-*.json"))
    if not pliki:
        print(f"Brak snapshotu w {KATALOG} — nie ma czego mierzyć.")
        sys.exit(1)
    plik = pliki[-1]
    d = json.loads(plik.read_text(encoding="utf-8"))
    obce = {m.get("etykieta") for m in d["mecze"]} - {"Predicted"}
    if obce:
        print(f"UWAGA: snapshot zawiera etykiety {obce} — te wpisy to już "
              "składy potwierdzone, nie prognoza. Pomijam je.")
    print(f"Snapshot {plik.name}: {len(d['mecze'])} meczów, pobrany "
          f"{datetime.fromtimestamp(d['pobrano_ts'], PL):%d.%m %H:%M}")
    return d


def terminarz_statshub(dni: set) -> dict:
    """{data: [surowe eventy]} dla dni objętych snapshotem, plus margines."""
    out: dict = {}
    for dzien in sorted(dni):
        for delta in (-1, 0, 1):
            d2 = dzien + timedelta(days=delta)
            if d2 in out:
                continue
            start = int(datetime(d2.year, d2.month, d2.day,
                                 tzinfo=PL).timestamp())
            start -= start % 86400
            try:
                out[d2] = BL._sh(
                    f"{BL.SH_BASE}/event/by-date?startOfDay={start}"
                    f"&endOfDay={start + 86399}"
                ).get("data", [])
            except Exception as e:
                print(f"   dzień {d2}: statshub nie oddał terminarza ({e})")
                out[d2] = []
    return out


def sparuj(mecze_sg: list[dict], sh: dict) -> tuple[list[tuple], Counter]:
    """(mecz SG, event statshub) — tylko dopasowania JEDNOZNACZNE.

    Okno dnia to D−1..D+1, bo SportsGambler podaje dzień LOKALNY: mecz
    argentyński grany o 21:30 miejscowego to u nas 02:30 następnego dnia.
    Zmierzone: bez tego okna sufit parowania spadał z 78% do 69%, a tracona
    była dokładnie Ameryka Południowa (Argentyna 36 → 55 meczów).
    """
    out, licznik = [], Counter()
    for x in mecze_sg:
        if x.get("etykieta") != "Predicted":
            licznik["nie jest prognozą"] += 1
            continue
        dzien = datetime.fromtimestamp(x["kickoff_dzien_ts"], PL).date()
        # DEDUPLIKACJA PO ID: mecz grany na styku dób wraca z `by-date` dla
        # obu dni, a bez tego wyglądał jak dwa różne dopasowania i cała para
        # szła do kosza jako niejednoznaczna (zmierzone: 51 meczów).
        okno_map = {
            (e.get("events") or {}).get("id"): e
            for delta in (0, 1, -1)
            for e in (sh.get(dzien + timedelta(days=delta)) or [])
            if (e.get("events") or {}).get("id")
        }
        okno = list(okno_map.values())
        traf = [
            e for e in okno
            if ta_sama_druzyna(x["dom"], (e.get("homeTeam") or {}).get("name"))
            and ta_sama_druzyna(x["wyjazd"],
                                (e.get("awayTeam") or {}).get("name"))
        ]
        if len(traf) == 1:
            out.append((x, traf[0]))
            licznik["sparowane"] += 1
        elif traf:
            licznik["wiele dopasowań — odrzucone"] += 1
        else:
            licznik["brak dopasowania"] += 1
    return out, licznik


def _sklad_faktyczny(event_id: int, team_id: int) -> list[str]:
    """XI bez ławki, nazwiskami. [] gdy statshub jeszcze go nie ma."""
    surowe = statshub._get(
        f"{statshub.BASE}/event/{event_id}/team-lineup"
        f"?teamId={team_id}&heatmap=false"
    )
    d = surowe.get("data", surowe)
    if not isinstance(d, list):
        return []
    return [str(p.get("name") or "") for p in d
            if p.get("isSubstitute") is not True and p.get("name")]


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass

    snap = wczytaj_snapshot()
    mecze_sg = snap["mecze"]
    dni = {datetime.fromtimestamp(m["kickoff_dzien_ts"], PL).date()
           for m in mecze_sg}
    print(f"Dni objęte snapshotem: {min(dni)} – {max(dni)}")
    sh = terminarz_statshub(dni)
    pary, licznik = sparuj(mecze_sg, sh)
    print("\nPAROWANIE ZE STATSHUBEM:")
    for k, v in licznik.most_common():
        print(f"   {k:<32} {v:>4}")
    laczne = sum(licznik.values()) - licznik["nie jest prognozą"]
    if laczne:
        print(f"   => sufit pomiaru: {licznik['sparowane']/laczne:.0%}")

    wyniki_plik = KATALOG / f"sg-wyniki-{datetime.now(PL):%Y-%m-%d}.json"
    zrobione = (json.loads(wyniki_plik.read_text(encoding="utf-8"))
                if wyniki_plik.exists() else {})
    if zrobione:
        print(f"\nWznawiam: {len(zrobione)} meczów policzonych wcześniej")

    zapytan = 0
    nowe = 0
    pominiete = Counter()
    for x, e in pary:
        ev = e.get("events") or {}
        eid = ev.get("id")
        klucz = str(eid)
        if klucz in zrobione:
            continue
        if ev.get("status") != "finished":
            pominiete["mecz jeszcze nierozegrany"] += 1
            continue
        if zapytan + 2 > LIMIT_ZAPYTAN:
            pominiete["poza budżetem tego przebiegu"] += 1
            continue
        try:
            dom = _sklad_faktyczny(eid, (e.get("homeTeam") or {}).get("id"))
            time.sleep(PAUZA_S)
            wyj = _sklad_faktyczny(eid, (e.get("awayTeam") or {}).get("id"))
            time.sleep(PAUZA_S)
            zapytan += 2
        except Exception as err:
            pominiete[f"błąd statshuba: {type(err).__name__}"] += 1
            continue
        if len(dom) < 11 or len(wyj) < 11:
            pominiete["statshub nie ma pełnego XI"] += 1
            continue
        zrobione[klucz] = {
            "mecz": f"{x['dom']} – {x['wyjazd']}",
            "liga": ((e.get("unique_tournaments") or {}).get("name") or "?"),
            "kraj": ((e.get("categories") or {}).get("name") or ""),
            "dom_traf": trafienia(x.get("xi_dom") or [], dom),
            "wyj_traf": trafienia(x.get("xi_wyjazd") or [], wyj),
            "dom_prog": len(x.get("xi_dom") or []),
            "wyj_prog": len(x.get("xi_wyjazd") or []),
        }
        nowe += 1
    if nowe:
        wyniki_plik.write_text(json.dumps(zrobione, ensure_ascii=False,
                                          indent=1), encoding="utf-8")
    print(f"\nPOLICZONE W TYM PRZEBIEGU: {nowe} meczów "
          f"({zapytan} zapytań do statshuba)")
    for k, v in pominiete.most_common():
        print(f"   pominięte — {k}: {v}")

    if not zrobione:
        print("\nBrak rozegranych meczów ze snapshotu — pomiar czeka na mecze.")
        return

    print("\n" + "=" * 78)
    print("WYNIK: ILU PRZEWIDZIANYCH ZAWODNIKÓW NAPRAWDĘ WYSZŁO W PIERWSZYM SKŁADZIE")
    print("=" * 78)
    traf = sum(r["dom_traf"] + r["wyj_traf"] for r in zrobione.values())
    prog = sum(r["dom_prog"] + r["wyj_prog"] for r in zrobione.values())
    if not prog:
        print("Brak pozycji do porównania.")
        return
    skutecznosc = traf / prog
    n = len(zrobione)
    szum = (skutecznosc * (1 - skutecznosc) / prog) ** 0.5
    print(f"   meczów: {n}, pozycji składu: {prog}")
    print(f"   trafionych: {traf}  =  {skutecznosc:.1%}  (szum {szum*100:.1f} pp)")
    print(f"   próg decyzyjny (własna jedenastka z minut): {PROG:.1%}")
    roznica = (skutecznosc - PROG) * 100
    if skutecznosc - 2 * szum > PROG:
        print(f"   ⚑ BIJE PRÓG o {roznica:+.1f} pp, i to poza szumem — "
              "źródło ma sens, patrz kolejka (strumień zawodniczy, drabinki)")
    elif skutecznosc + 2 * szum < PROG:
        print(f"   ⚑ NIE BIJE PROGU ({roznica:+.1f} pp) — własna jedenastka "
              "z rotacji minut jest lepsza, a jej nie utrzymujemy")
    else:
        print(f"   RÓŻNICA W SZUMIE ({roznica:+.1f} pp) — pomiar NIE "
              "rozstrzyga, potrzeba więcej meczów")

    print("\n   PER ROZGRYWKI (min. 3 mecze):")
    per = defaultdict(lambda: [0, 0, 0])
    for r in zrobione.values():
        k = f"{r['liga']} ({r['kraj']})"
        per[k][0] += r["dom_traf"] + r["wyj_traf"]
        per[k][1] += r["dom_prog"] + r["wyj_prog"]
        per[k][2] += 1
    for k, (t, p, ile) in sorted(per.items(), key=lambda kv: -kv[1][2]):
        if ile < 3 or not p:
            continue
        print(f"      {k:<42} {ile:>3} mecz.  {t/p:>6.1%}")


if __name__ == "__main__":
    main()
