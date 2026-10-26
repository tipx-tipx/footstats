# -*- coding: utf-8 -*-
"""ARCHIWUM DANYCH OPTA Z THE ANALYST — WYŁĄCZNIE DO POMIARU (2026-10-26).

Właściciel 26.10: „archiwizuj” (po przedstawieniu ryzyka). Czego to dotyczy
----------------------------------------------------------------------------
dataviz.theanalyst.com wystawia publicznie (bez logowania) pliki, z których
korzystają strony The Analyst:

* `opta-power-rankings/pr-reference.json` — siła ~14,5 tys. klubów (co tydzień),
* `opta-power-rankings/league-meta.json` — siła lig (puchary),
* `project-data/soccer/{tmcl}/team-stats.json` i `player-stats.json` — sezon
  od początku do dziś: xG, xG przeciw, PPDA, strzały z pola karnego, faule,
  kartki, odbiory… — tylko 7 męskich rozgrywek niżej (codziennie ~07:10 UTC).

Historii tych plików nie ma, więc test wsteczny jest niemożliwy — stąd
codzienna migawka. Po 4–6 tygodniach: połączenie z księgą (stan z dnia przed
meczem) i test, czy cecha dodaje coś ponad model (Brier walk-forward,
trafność półek przy tej samej liczbie typów). Do tego czasu NIC z tych danych
nie wchodzi do wyboru typów ani na stronę.

⚑ RYZYKO PRAWNE (przedstawione właścicielowi 26.10): dane Stats Perform,
regulamin zabrania pobierania automatycznego i użytku komercyjnego, w UE
chroni je prawo do baz danych. Dlatego: raz na dobę, tylko te pliki, nic
na stronie, nic z płatnego API (klucz w kodzie The Analyst NIE jest nasz).
Wyłączenie: usunąć workflow `opta.yml`.

Zapis: magazyn stanu (`magazyn_repo`), klucz `opta_arch_RRRRMMDD` — każdy dzień
osobno, więc retencja wersji klucza nie kasuje poprzednich dni.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

from .. import magazyn_repo

BAZA = "https://dataviz.theanalyst.com"
RANKINGI = ("opta-power-rankings/pr-reference.json",
            "opta-power-rankings/league-meta.json")
# numery sezonu (tmcl) 2026/27 ze stron theanalyst.com/competition/*/stats, 26.10
ROZGRYWKI = {
    "premier_league": "6pdwluctev9iebv00r4qqukno",
    "championship": "al48ooi8acoibema226051250",
    "bundesliga": "8h5xijv2u4mlf5028gso6kw7o",
    "la_liga": "830epggffy1nfkfyrtpqdwhlg",
    "serie_a": "60cryos85i4bp5ul34tt0brx0",
    "ligue_1": "bqnc4ccgnrp6pb3bktqet0yz8",
    "liga_mistrzow": "99jev9kv55deht65t6myggxlg",
}
PLIKI_ROZGRYWEK = ("team-stats", "player-stats")
PRZERWA_S = 2.0          # między zapytaniami — z umiarem
TIMEOUT_S = 60


def _pobierz_json(sciezka: str):
    req = urllib.request.Request(f"{BAZA}/{sciezka}",
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


def sciezki() -> dict[str, str]:
    """{nazwa w archiwum: ścieżka na dataviz}."""
    out = {s.rsplit("/", 1)[1].removesuffix(".json"): s for s in RANKINGI}
    for nazwa, tmcl in ROZGRYWKI.items():
        for plik in PLIKI_ROZGRYWEK:
            out[f"{nazwa}/{plik}"] = f"project-data/soccer/{tmcl}/{plik}.json"
    return out


def zbierz(pobierz=_pobierz_json, przerwa_s: float = PRZERWA_S) -> tuple[dict, dict]:
    """(pliki {nazwa: dane}, błędy {nazwa: opis}) — błąd jednego pliku nie
    przerywa reszty."""
    pliki, bledy = {}, {}
    for i, (nazwa, sciezka) in enumerate(sciezki().items()):
        if i and przerwa_s:
            time.sleep(przerwa_s)
        try:
            pliki[nazwa] = pobierz(sciezka)
        except Exception as e:                                  # noqa: BLE001
            bledy[nazwa] = f"{type(e).__name__}: {e}"[:200]
    return pliki, bledy


def klucz_dnia(ts: float | None = None) -> str:
    return "opta_arch_" + time.strftime("%Y%m%d", time.gmtime(ts or time.time()))


def main() -> int:
    t0 = time.time()
    pliki, bledy = zbierz()
    payload = {"ts": int(t0), "zrodlo": BAZA, "rozgrywki": ROZGRYWKI,
               "pliki": pliki, "bledy": bledy}
    print(f"Archiwum Opta: {len(pliki)} plików, błędy {len(bledy)}"
          + (f" ({', '.join(sorted(bledy))})" if bledy else ""))
    if not pliki:
        print("Archiwum Opta: nic nie pobrano — bez zapisu")
        return 1
    ok = magazyn_repo.zapisz(klucz_dnia(t0), payload)
    print(f"Archiwum Opta: zapis {klucz_dnia(t0)} {'OK' if ok else 'NIEUDANY'} "
          f"w {time.time() - t0:.0f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
