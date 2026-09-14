"""Źródło składów: SportsGambler — przewidywane i ogłoszone jedenastki z ławką.

Wpięte 2026-09-14. Powód: typy zawodnicze publikowane BEZ sygnału składu
kończą się zwrotem w 24% (zawodnik nie zagrał), z przewidywanym składem
w 17%, z ogłoszonym w 5% (księga, epoka ligowa). A skład mieliśmy dla garstki
meczów: Rotowire tylko Europa Zachodnia + MLS, statshub ~12 meczów na cykl,
Sofascore blokuje IP serwerowni. SportsGambler obejmuje ~60 rozgrywek
(Argentyna, Brazylia, Chile, Szwecja, Norwegia, Dania, Turcja, Portugalia,
Belgia, Holandia, Serie B, LaLiga 2, Championship…), pomiar z 16.08 na
zamrożonym snapshocie: 75,6% trafności pozycji składu (Belgia/Holandia/
Portugalia ~85%, Argentyna 63%, Turcja 57%) — `docs/pomiar-sklady-sportsgambler.md`.
Dostęp z GitHub Actions sprawdzony sondą 14.09 (`sonda.yml`): HTTP 200
zarówno lista, jak i endpoint składu. BEZ Ekstraklasy.

Jak strona działa (rozpracowane 14.09):
  * lista:  https://www.sportsgambler.com/lineups/football/
    nagłówki dni `<h3 class="date-headline">Monday 14 September</h3>`, pod nimi
    wiersze `lineup-row` z `fxs-time`, `fxs-league`, `fxs-team home`,
    `fxs-team`, a w przycisku `reply_click(<id>)` i etykieta
    „Predicted Lineups" / „Confirmed Lineups";
  * skład:  /lineups/lineups-load2.php?id=<id>  (to samo, co strona dociąga
    AJAX-em po kliknięciu) — dwa `<h3><span>Como Confirmed Lineup</span>`,
    XI jako `<span class="player-name">…</span>` w `lineups-home` /
    `lineups-away`, ławka jako `<li class="sub-player">` pod
    `<h3>Como Substitutes</h3>`.

⚑ NAZWY DRUŻYN: SportsGambler skraca („Newcastle", „Tottenham"), my mamy
„Newcastle United", „Tottenham Hotspur". Zmierzone 14.09: po samej
normalizacji 50 z naszych meczów w oknie 48 h zostawało bez pary. Dlatego
parujemy jak z Betcliciem — `betclic.paruj_mecze` (zbiory słów + zawieranie,
remis = brak pary) — i wynik kluczujemy NASZĄ nazwą drużyny, żeby cykl czytał
to tą samą parą funkcji, co Rotowire (`rotowire.predicted_status`,
`is_confirmed`). Dodatkowo niesiemy `bench` (ławka) i `zrodlo`.

Pamięć między cyklami (`sg_sklady` w Supabase): skład ogłoszony nie zmienia
się — nie pytamy drugi raz; przewidywany odświeżamy po `ODSWIEZ_PREDICTED_S`.
Pytamy WYŁĄCZNIE o mecze z naszego terminarza w oknie `OKNO_S`.
"""

from __future__ import annotations

import datetime as _dt
import re
import time

from curl_cffi import requests

from . import betclic
from .rotowire import _norm

LISTA_URL = "https://www.sportsgambler.com/lineups/football/"
SKLAD_URL = "https://www.sportsgambler.com/lineups/lineups-load2.php?id={id}"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124"

ODSWIEZ_PREDICTED_S = 3 * 3600     # przewidywany skład pytamy ponownie po 3 h
RETENCJA_S = 2 * 86400             # wpis w pamięci żyje 2 doby
BUDZET_S = 120.0                   # sufit czasu na dociąganie składów w cyklu
OKNO_S = 40 * 3600                 # mecze do 40 h przed gwizdkiem
# Godziny na liście są w czasie brytyjskim (strona z UK); do parowania
# używamy szerokiego okna, bo i tak rozstrzyga para nazw drużyn + doba.
OKNO_PAROWANIA_S = 8 * 3600
_UK_OFFSET_S = 3600                # BST (lato); zimą 0 — okno parowania to kryje

_MIESIACE = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}


def _data_z_naglowka(tekst: str, rok: int) -> _dt.date | None:
    """'Monday 14 September' -> date(rok, 9, 14)."""
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)", tekst or "")
    if not m:
        return None
    mies = _MIESIACE.get(m.group(2).lower())
    if not mies:
        return None
    try:
        return _dt.date(rok, mies, int(m.group(1)))
    except ValueError:
        return None


def _kickoff_ts(data: _dt.date | None, czas: str) -> int:
    if not data:
        return 0
    m = re.match(r"(\d{1,2}):(\d{2})", czas or "")
    hh, mm = (int(m.group(1)), int(m.group(2))) if m else (12, 0)
    dt = _dt.datetime(data.year, data.month, data.day, hh, mm,
                      tzinfo=_dt.timezone.utc)
    return int(dt.timestamp()) - _UK_OFFSET_S


def lista_meczow(html: str, dzis: _dt.date | None = None) -> list[dict]:
    """Wiersze listy: [{id, home, away, liga, czas, data, kickoff_ts, confirmed}].

    Rok bierzemy z `dzis` (strona go nie pisze); przełom roku obsługujemy tak,
    że data wcześniejsza o >300 dni od `dzis` dostaje rok+1.
    """
    dzis = dzis or _dt.date.today()
    out: list[dict] = []
    czesci = re.split(r'class="date-headline">', html)
    for czesc in czesci[1:]:
        naglowek = re.match(r"([^<]+)<", czesc)
        data = _data_z_naglowka(naglowek.group(1) if naglowek else "", dzis.year)
        if data and (data - dzis).days < -300:
            data = data.replace(year=dzis.year + 1)
        for row in re.findall(r'lineup-row">(.*?)<!--table row-->', czesc, re.S):
            mid = re.search(r"reply_click\((\d+)\)", row)
            home = re.search(r'fxs-team home">\s*([^<]+?)\s*<', row)
            away = re.search(r'fxs-team">\s*([^<]+?)\s*<', row)
            if not (mid and home and away):
                continue
            liga = re.search(r'fxs-league[^>]*>\s*([^<]+?)\s*<', row)
            czas = re.search(r'fxs-time">\s*([^<]+?)\s*<', row)
            out.append({
                "id": int(mid.group(1)),
                "home": home.group(1), "away": away.group(1),
                "liga": (liga.group(1) if liga else ""),
                "czas": (czas.group(1) if czas else ""),
                "data": data.isoformat() if data else None,
                "kickoff_ts": _kickoff_ts(data, czas.group(1) if czas else ""),
                "confirmed": "Confirmed Lineup" in row,
            })
    return out


def _nazwiska(fragment: str) -> set[str]:
    return {
        _norm(n) for n in re.findall(r'class="player-name">\s*([^<]+?)\s*<', fragment)
    }


def _lawka(html: str, druzyna: str) -> set[str]:
    m = re.search(
        r"<h3>\s*" + re.escape(druzyna) + r"\s+Substitutes\s*</h3>(.*?)</ul>",
        html, re.S,
    )
    if not m:
        return set()
    out = set()
    for li in re.findall(r'<li class="sub-player">(.*?)</li>', m.group(1), re.S):
        li = re.sub(r"<span[^>]*>.*?</span>", " ", li, flags=re.S)   # numer koszulki
        nazwa = re.sub(r"<[^>]+>", "", li).strip()
        if nazwa:
            out.add(_norm(nazwa))
    return out


def sklad_meczu(html: str) -> dict[str, dict]:
    """Z odpowiedzi `lineups-load2.php`: {home: {...}, away: {...}}.

    Każdy wpis: {"team", "xi": set, "bench": set, "confirmed": bool}.
    Pusty słownik, gdy strona nie ma jeszcze składów (obie XI puste).
    """
    naglowki = re.findall(
        r"<h3><span>\s*(.+?)\s+(Confirmed|Predicted)\s+Lineup\s*</span>", html
    )
    if len(naglowki) < 2:
        return {}
    i_home = html.find('class="lineups-home')
    i_away = html.find('class="lineups-away')
    if i_home < 0 or i_away < 0 or i_away < i_home:
        return {}
    i_koniec = html.find("<!--lineups-->", i_away)
    xi_home = _nazwiska(html[i_home:i_away])
    xi_away = _nazwiska(html[i_away:i_koniec if i_koniec > 0 else None])
    if not xi_home and not xi_away:
        return {}
    out = {}
    for strona, (team, etyk), xi in (("home", naglowki[0], xi_home),
                                      ("away", naglowki[1], xi_away)):
        out[strona] = {
            "team": team.strip(), "xi": xi, "bench": _lawka(html, team.strip()),
            "confirmed": etyk == "Confirmed",
        }
    return out


def _get(url: str, timeout: int = 20) -> str:
    r = requests.get(url, impersonate="chrome124", timeout=timeout,
                     headers={"User-Agent": _UA, "Referer": LISTA_URL})
    r.raise_for_status()
    return r.text


def paruj(nasze_mecze: list[dict], lista: list[dict]) -> dict:
    """{klucz naszego meczu: wiersz SG} — tą samą regułą, co z Betcliciem."""
    bc = [
        {"gospodarz": r["home"], "gosc": r["away"], "kickoff_ts": r["kickoff_ts"],
         "sg": r}
        for r in lista
    ]
    pary, _ = betclic.paruj_mecze(
        [{"klucz": m["klucz"], "home": m["home"], "away": m["away"],
          "kickoff_ts": m.get("kickoff_ts") or 0} for m in nasze_mecze],
        bc_mecze=bc, okno_s=OKNO_PAROWANIA_S,
    )
    return {k: v["sg"] for k, v in pary.items()}


def fetch_predicted_lineups(
    nasze_mecze: list[dict],
    pamiec: dict | None = None,
    teraz: int | None = None,
    budzet_s: float = BUDZET_S,
    pobierz=None,
    dzis: _dt.date | None = None,
) -> tuple[dict[str, dict], dict, dict]:
    """Składy SportsGamblera dla NASZYCH meczów, kluczowane NASZĄ nazwą drużyny.

    `nasze_mecze`: [{"klucz", "home", "away", "kickoff_ts"}] (nazwy jak
    w cyklu — `team_name`). `pamiec` — wpisy z poprzednich cykli, zwracana
    zaktualizowana. Zwraca (mapa jak Rotowire, pamięć, licznik do logu).
    """
    pobierz = pobierz or _get
    teraz = int(teraz or time.time())
    pamiec = dict(pamiec or {})
    licznik = {"lista": 0, "sparowane": 0, "pobrane": 0, "z_pamieci": 0,
               "ogloszone": 0, "puste": 0, "bledy": 0, "wyczerpany": ""}
    try:
        lista = lista_meczow(pobierz(LISTA_URL), dzis=dzis)
    except Exception as e:                                     # noqa: BLE001
        print(f"SportsGambler: lista niedostępna ({type(e).__name__}: {e})")
        return {}, pamiec, licznik
    licznik["lista"] = len(lista)
    w_oknie = [
        m for m in nasze_mecze
        if 0 < (int(m.get("kickoff_ts") or 0) - teraz) <= OKNO_S
    ]
    pary = paruj(w_oknie, lista)
    licznik["sparowane"] = len(pary)
    start = time.monotonic()
    mapa: dict[str, dict] = {}
    for m in sorted(w_oknie, key=lambda x: x.get("kickoff_ts") or 0):
        row = pary.get(m["klucz"])
        if not row:
            continue
        klucz = str(row["id"])
        wpis = pamiec.get(klucz)
        swiezy = bool(wpis) and (
            wpis.get("confirmed")
            or teraz - int(wpis.get("ts") or 0) <= ODSWIEZ_PREDICTED_S
        )
        if not swiezy:
            if time.monotonic() - start > budzet_s:
                licznik["wyczerpany"] = "czas"
            else:
                try:
                    sk = sklad_meczu(pobierz(SKLAD_URL.format(id=row["id"])))
                except Exception as e:                         # noqa: BLE001
                    licznik["bledy"] += 1
                    print(f"SportsGambler: mecz {row['home']}–{row['away']} "
                          f"pominięty ({type(e).__name__}: {e})")
                    sk = None
                if sk is None:
                    pass
                elif not sk:
                    licznik["puste"] += 1
                    wpis = {"ts": teraz, "confirmed": False, "puste": True}
                    pamiec[klucz] = wpis
                else:
                    licznik["pobrane"] += 1
                    wpis = {
                        "ts": teraz,
                        "confirmed": bool(sk["home"]["confirmed"] and sk["away"]["confirmed"]),
                        "xi_home": sorted(sk["home"]["xi"]),
                        "xi_away": sorted(sk["away"]["xi"]),
                        "bench_home": sorted(sk["home"]["bench"]),
                        "bench_away": sorted(sk["away"]["bench"]),
                        "conf_home": bool(sk["home"]["confirmed"]),
                        "conf_away": bool(sk["away"]["confirmed"]),
                    }
                    pamiec[klucz] = wpis
        else:
            licznik["z_pamieci"] += 1
        if not wpis or wpis.get("puste"):
            continue
        for strona, nasza in (("home", m["home"]), ("away", m["away"])):
            xi = set(wpis.get(f"xi_{strona}") or [])
            if not xi:
                continue
            conf = bool(wpis.get(f"conf_{strona}"))
            if conf:
                licznik["ogloszone"] += 1
            rec = {"xi": xi, "confirmed": conf,
                   "bench": set(wpis.get(f"bench_{strona}") or []), "zrodlo": "sg"}
            team = _norm(nasza)
            if team not in mapa or (conf and not mapa[team]["confirmed"]):
                mapa[team] = rec
    pamiec = {k: v for k, v in pamiec.items()
              if teraz - int(v.get("ts") or 0) <= RETENCJA_S}
    return mapa, pamiec, licznik


def dolacz_do_rotowire(roto: dict[str, dict], sg: dict[str, dict]) -> int:
    """Dołóż składy SG do mapy Rotowire IN PLACE. Zwraca, ile drużyn doszło.

    Rotowire zostaje, gdy ma drużynę; SG nadpisuje tylko wtedy, gdy SG ma
    skład OGŁOSZONY, a Rotowire jeszcze przewidywany.
    """
    n = 0
    for team, rec in sg.items():
        stary = roto.get(team)
        if stary is None:
            roto[team] = rec
            n += 1
        elif rec["confirmed"] and not stary.get("confirmed"):
            roto[team] = rec
    return n
