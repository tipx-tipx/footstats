"""WŁASNA BAZA MECZÓW — fundament „własnego statshub" (od 30.10.2026, docs/plan-fotmob.md).

Po co
-----
Statshub oddawał gotowe historie zawodników i drużyn. Od 29.10 nie odpowiada,
więc historie składamy SAMI: każdy zakończony mecz pobieramy z FotMob RAZ
(`fotmob.mecz_do_bazy`) i trzymamy tutaj na stałe. Gdyby kiedyś odmówiło
i to źródło, cała historia zostaje u nas – brakuje tylko nowych meczów.

Zgodność z danymi statshub (bramka etapu 2, 30.10): zawodnicy 237 meczów,
strzały 97,9%, celne 98,9%, faule 99,1%, faulowani 99,3%, głową 98,8–99,4%,
spalone 100%, kartki 99,3%; drużyny 272 mecze bez stałego przesunięcia żadnej
cechy (stosunek średnich 0,99–1,01), rożne 99,2%, faule 98,1%.

Zapis
-----
Jeden klucz na miesiąc startu meczu (`fm_baza_RRRRMM`, magazyn repo – patrz
`supa.MAGAZYN`), ~0,9 KB na mecz po kompresji. Zawodnik zapisany zwięźle
(lista zamiast słownika, statystyki bez zer); flagi meczu `staty_zawodnikow`
i `mapa_strzalow` mówią, czy brak pola znaczy 0, czy „brak danych" –
`rozpakuj` odtwarza dokładnie rekord z `mecz_do_bazy` (jest na to test).

⚑ Mecz rozegrany NIE jest nadpisywany – chyba że nowa wersja ma więcej danych
(FotMob potrafi dopisać statystyki zawodników albo mapę strzałów po czasie).
Ta sama zasada co w magazynie drużyn statshub: przepisanie dobrego rekordu
gorszym psuje historię po cichu.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from . import supa
from .sources import fotmob

KLUCZ_WZOR = "fm_baza_{}"

# kolejność pól zawodnika w zapisie zwięzłym
_POLA_ZAW = ("pid", "name", "team_id", "minuty", "start", "wszedl", "zszedl", "poz", "staty")
_KODY_STATYSTYK = (tuple(fotmob.POLA_ZAWODNIKA.values()) + tuple(fotmob.POLA_STRZALOW.values())
                   + fotmob.RYNKI_Z_MAPY + ("yellow_card", "red_card"))


def klucz_miesiaca(ts: int) -> str:
    return KLUCZ_WZOR.format(datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y%m"))


def spakuj(rek: dict) -> dict:
    """Rekord `mecz_do_bazy` → zapis zwięzły (statystyki zawodników bez zer i None)."""
    zaw = []
    for z in rek.get("zawodnicy") or []:
        s = z.get("staty")
        zaw.append([z["pid"], z["name"], z["team_id"], z["minuty"], 1 if z["start"] else 0,
                    z["wszedl"], z["zszedl"], z["poz"],
                    None if s is None else {k: v for k, v in s.items() if v}])
    return {**{k: v for k, v in rek.items() if k != "zawodnicy"}, "zawodnicy": zaw}


def rozpakuj(zapis: dict) -> dict:
    """Odwrotność `spakuj`: brakujące statystyki = 0, a rynki z mapy strzałów
    = None, gdy meczu nie było na mapie (brak danych to nie zero)."""
    mapa = bool(zapis.get("mapa_strzalow"))
    zaw = []
    for w in zapis.get("zawodnicy") or []:
        z = dict(zip(_POLA_ZAW, w))
        z["start"] = bool(z["start"])
        if z["staty"] is not None:
            pelne = {}
            for kod in _KODY_STATYSTYK:
                if kod in z["staty"]:
                    pelne[kod] = z["staty"][kod]
                elif kod in fotmob.RYNKI_Z_MAPY and not mapa:
                    pelne[kod] = None
                else:
                    pelne[kod] = 0.0
            z["staty"] = pelne
        zaw.append(z)
    return {**{k: v for k, v in zapis.items() if k != "zawodnicy"}, "zawodnicy": zaw}


def _bogatszy(nowy: dict, stary: dict) -> bool:
    """Czy nowa wersja meczu ma więcej danych niż zapisana."""
    def ile(r):
        return (int(bool(r.get("staty_zawodnikow"))) * 2 + int(bool(r.get("mapa_strzalow")))
                + int(bool(r.get("druzyny"))))
    return ile(nowy) > ile(stary)


# ------------------------------------------------------------- odczyt/zapis --
def wczytaj(miesiace: list[str]) -> tuple[dict[int, dict], list[str]]:
    """{id meczu FotMob: zapis zwięzły} z podanych kluczy miesięcy + lista
    kluczy, których NIE udało się odczytać (awaria ≠ pusty miesiąc –
    wołający nie może zapisać miesiąca, którego nie przeczytał)."""
    baza: dict[int, dict] = {}
    braki = []
    for k in miesiace:
        dane, ok = supa.get_key_ok(k)
        if not ok:
            braki.append(k)
            continue
        for mid, zapis in (dane or {}).items():
            baza[int(mid)] = zapis
    return baza, braki


def dopisz(baza: dict[int, dict], rekordy: list[dict]) -> set[str]:
    """Dopisz rekordy `mecz_do_bazy` (tylko zakończone). Zwraca klucze miesięcy,
    które się zmieniły (do zapisu)."""
    zmienione = set()
    for r in rekordy:
        if r.get("status") != "finished" or not r.get("id") or not r.get("ts"):
            continue
        stary = baza.get(r["id"])
        if stary is not None and not _bogatszy(r, stary):
            continue
        baza[r["id"]] = spakuj(r)
        zmienione.add(klucz_miesiaca(r["ts"]))
    return zmienione


def zapisz(baza: dict[int, dict], miesiace: set[str], nieprzeczytane: list[str]) -> dict[str, bool]:
    """Zapisz zmienione miesiące. Miesiąca, którego odczyt padł, NIE zapisujemy –
    nadpisalibyśmy jego historię garścią świeżych meczów."""
    wynik = {}
    for k in sorted(miesiace):
        if k in nieprzeczytane:
            wynik[k] = False
            continue
        czesc = {str(mid): z for mid, z in baza.items() if klucz_miesiaca(z["ts"]) == k}
        wynik[k] = bool(supa.put_key(k, czesc))
    return wynik


# --------------------------------------------------------------- indeksy ----
def historia_druzyn(baza: dict[int, dict]) -> dict[int, list[dict]]:
    """{team_id: [rekordy rozpakowane, od najnowszego]}."""
    out: dict[int, list[dict]] = defaultdict(list)
    for z in baza.values():
        r = rozpakuj(z)
        out[r["home"]["id"]].append(r)
        out[r["away"]["id"]].append(r)
    for lst in out.values():
        lst.sort(key=lambda r: r["ts"], reverse=True)
    return dict(out)


def historia_zawodnikow(baza: dict[int, dict]) -> dict[int, list[tuple[dict, dict]]]:
    """{pid: [(rekord meczu, wiersz zawodnika), od najnowszego]} – także mecze
    z 0 minut (ławka): na nich stoi „opuścił mecz" i `historia_pelna`."""
    out: dict[int, list[tuple[dict, dict]]] = defaultdict(list)
    for z in baza.values():
        r = rozpakuj(z)
        for w in r["zawodnicy"]:
            out[w["pid"]].append((r, w))
    for lst in out.values():
        lst.sort(key=lambda p: p[0]["ts"], reverse=True)
    return dict(out)
