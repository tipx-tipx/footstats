"""POMIAR PRZEWIDYWANYCH SKŁADÓW PER ŹRÓDŁO (2026-10-06, właściciel: „mieliśmy
tak dopracować przewidywanie składów, że nie musimy czekać do składów").

Po co
-----
Od 01.10 prawie połowa typów zawodników z samym PRZEWIDYWANYM składem kończy
się zwrotem (nie wyszedł w podstawie), a rozliczone trafiają 41% wobec 52%
przy ogłoszonym składzie. Pierwszy przewidywany skład statshub (~42 h przed
meczem) trafia 65% jedenastki — ale mierzyliśmy TYLKO jego (`pomiar_xi`).
Rotowire i SportsGambler wchodzą do cyklu bez żadnego pomiaru, a po
`sportsgambler.dolacz_do_rotowire` nie da się już ich rozróżnić.

Co zapisujemy (klucz `pomiar_skladow` w repo stanu, 30 dni)
-----------------------------------------------------------
    {mecz_id: {"k": kickoff, "h": gospodarz, "a": gość,
               "statshub" | "rotowire" | "sportsgambler":
                   {"pierwszy": {"ts", "h": [...], "a": [...], "pot": bool},
                    "ostatni":  {...}},
               "ogloszony": {"ts", "h": [id...], "a": [id...], "zrodlo"}}}

statshub w numerach zawodników, Rotowire i SportsGambler w znormalizowanych
nazwiskach (tak je podają) — analiza łączy je bankiem trendów.

Zasady jak w `archiwum_ofert`: mecz po gwizdku zamrożony, zapis tylko przy
zmianie, padnięty odczyt = brak zapisu.
"""
from __future__ import annotations

import time

from .. import magazyn_repo

KLUCZ = "pomiar_skladow"
RETENCJA_S = 30 * 86400


def _sekundy(ts) -> int | None:
    try:
        t = int(ts)
    except (TypeError, ValueError):
        return None
    return t // 1000 if t > 10**11 else t


def _xi_nazw(mapa: dict, druzyna_norm: str) -> tuple[list[str], bool] | None:
    rec = (mapa or {}).get(druzyna_norm)
    if not rec or not rec.get("xi"):
        return None
    return sorted(str(x) for x in rec["xi"]), bool(rec.get("confirmed"))


def _wpisz(wpis: dict, zrodlo: str, h, a, pot: bool, teraz: int) -> bool:
    """Ustaw `pierwszy` (raz) i `ostatni` (gdy się zmienił). True = zmiana."""
    stan = {"h": h, "a": a, "pot": bool(pot)}
    z = wpis.setdefault(zrodlo, {})
    zmiana = False
    if "pierwszy" not in z:
        z["pierwszy"] = {"ts": teraz, **stan}
        zmiana = True
    ost = z.get("ostatni")
    if not ost or {k: ost.get(k) for k in stan} != stan:
        z["ostatni"] = {"ts": teraz, **stan}
        zmiana = True
    return zmiana


def scal(stan: dict, mecze: list[dict], xi_statshub: dict, rotowire: dict,
         sportsgambler: dict, norm, teraz: int) -> int:
    """Dopisuje do `stan` (w miejscu). `mecze`: [{id, k, h, a, h_id, a_id}].
    `norm` — normalizacja nazw drużyn (rotowire._norm). Zwraca liczbę zmian."""
    zmiany = 0
    for m in mecze:
        ko = _sekundy(m.get("k"))
        if not m.get("id") or not ko or ko <= teraz:
            continue                                    # po gwizdku: zamrożony
        mid = str(m["id"])
        wpis = stan.get(mid) or {"k": ko, "h": m.get("h"), "a": m.get("a")}
        przed = repr(wpis)
        # statshub: przewidywany albo oficjalny (numery zawodników)
        sh = (xi_statshub or {}).get(m["id"]) or (xi_statshub or {}).get(mid)
        if sh:
            xt = sh.get("xi_by_team") or {}
            h = sorted(int(x) for x in xt.get(m.get("h_id"), []) or [])
            a = sorted(int(x) for x in xt.get(m.get("a_id"), []) or [])
            if h or a:
                if sh.get("confirmed") and "ogloszony" not in wpis:
                    wpis["ogloszony"] = {"ts": teraz, "h": h, "a": a,
                                         "zrodlo": sh.get("zrodlo")}
                elif not sh.get("confirmed"):
                    _wpisz(wpis, "statshub", h, a, False, teraz)
        # Rotowire i SportsGambler osobno (nazwiska)
        for nazwa, mapa in (("rotowire", rotowire), ("sportsgambler", sportsgambler)):
            xh = _xi_nazw(mapa, norm(m.get("h") or ""))
            xa = _xi_nazw(mapa, norm(m.get("a") or ""))
            if xh or xa:
                _wpisz(wpis, nazwa, (xh or ([], False))[0], (xa or ([], False))[0],
                       bool((xh or ([], False))[1] or (xa or ([], False))[1]), teraz)
        if repr(wpis) != przed:
            stan[mid] = wpis
            zmiany += 1
    for k in [k for k, w in stan.items()
              if (_sekundy(w.get("k")) or teraz) < teraz - RETENCJA_S]:
        del stan[k]
        zmiany += 1
    return zmiany


def zapisz(mecze, xi_statshub, rotowire, sportsgambler, norm,
           teraz: int | None = None) -> str:
    teraz = int(teraz or time.time())
    stan, ok = magazyn_repo.pobierz(KLUCZ)
    if not ok:
        return "Pomiar składów (źródła): ODCZYT PADŁ — nie zapisuję"
    stan = stan if isinstance(stan, dict) else {}
    n = scal(stan, mecze, xi_statshub, rotowire, sportsgambler, norm, teraz)
    if not n:
        return f"Pomiar składów (źródła): bez zmian ({len(stan)} meczów)"
    if not magazyn_repo.zapisz(KLUCZ, stan):
        return f"Pomiar składów (źródła): ZAPIS PADŁ ({n} zmian do powtórki)"
    zr = {z: sum(1 for w in stan.values() if z in w)
          for z in ("statshub", "rotowire", "sportsgambler", "ogloszony")}
    return (f"Pomiar składów (źródła): {n} zmian, {len(stan)} meczów — "
            + ", ".join(f"{k} {v}" for k, v in zr.items()))
