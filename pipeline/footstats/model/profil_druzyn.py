"""Profil drużyny: ile NOTUJE i ile DOPUSZCZA — pamiętany między cyklami.

PO CO TO POWSTAŁO (2026-08-07)
------------------------------
Czynnik rywala miał dotąd dwa źródła: bank stylu (mecze, które sami
przeskanowaliśmy) i `recentGames` z feedu propsów — a ten drugi jest lustrem
oferty bukmacherów UK. Dla Ekstraklasy, kwalifikacji pucharów i części Ameryki
Południowej po prostu nie istnieje, więc czynnik wychodził 1,00. Zmierzone
07.08: komplet czynników miało **18 ze 134 kandydatów**.

Historia drużyny (`/team/{id}/performance`) działa w KAŻDEJ lidze i niesie
w każdym meczu komplet statystyk obu stron — czyli koncesje zmierzone, a nie
przybliżane. Zmierzone na 3018 obserwacjach z banku: „ile rywal dopuszcza" to
NAJSILNIEJSZA pojedyncza zależność w każdym z pięciu rynków drużynowych,
a dołożenie jej zmniejsza błąd przewidywania o 5–15%.

Problem: pytanie o historię co cykl wydłużyło dry-run z ~15 do ~23 minut przy
twardym limicie 35. Dlatego profil jest PAMIĘTANY: cykl czyta gotowe liczby,
a odświeża tylko te drużyny, które od ostatniego razu zdążyły rozegrać mecz.

CO TU JEST, A CZEGO NIE MA
--------------------------
Trzymamy AGREGATY (średnia ważona świeżością + próba), nie surowe mecze —
241 drużyn × 6 rynków × 2 strony to ~70 kB, czyli rozmiar, który cykl może
czytać co przebieg. Surowa historia do uczenia wag mieszka osobno i czyta ją
wyłącznie skrypt uczący (patrz `scripts/backfill_historii.py`).

Moduł jest CZYSTY: żadnych zapytań do sieci ani do bazy. Wejście to rekordy
z `statshub.fetch_team_performance`, wyjście to słownik. Dzięki temu cała
logika (wygaszanie, scalanie, decyzja o odświeżeniu) ma testy bez zaślepek.
"""

from __future__ import annotations

import math

WERSJA = 1

# Półokres świeżości obserwacji: mecz sprzed 45 dni waży o połowę mniej niż
# wczorajszy. Ta sama liczba, co przy koncesjach z feedu (`build_wc_fast`):
# rytm ligowy to mecz co ~tydzień, więc 45 dni obejmuje ~6 spotkań.
# ZAŁOŻENIE, nie pomiar — do kalibracji, gdy uzbiera się próba rozliczeń
# typów liczonych z tego profilu.
TAU_DNI = 45.0

# Poniżej tylu meczów profil jest zbyt chudy, żeby cokolwiek nim korygować.
# Ta sama granica, co `MIN_HIST_BANKU` w build_wc_fast — profil, który zna
# trzy mecze, potrafi zrobić z przeciętnej obrony twierdzę.
MIN_MECZE = 5

# Jak długo profil jest „świeży". Drużyny grają co 3–7 dni, więc doba to
# odstęp, przy którym prawie nigdy nie przegapimy meczu, a i tak odpytujemy
# każdą drużynę najwyżej raz dziennie zamiast przy każdym cyklu (cykl chodzi
# co ~30–60 min, czyli oszczędzamy ~95% zapytań).
SWIEZOSC_H = 24.0

# Drużyna, która nie zagrała od trzech miesięcy, wypada z profilu — inaczej
# klucz puchłby w nieskończoność o kluby z zakończonych rozgrywek.
ROTACJA_DNI = 90.0


def _waga(ts: int, teraz: int) -> float:
    dni = max(teraz - int(ts or 0), 0) / 86400.0
    return math.exp(-dni / TAU_DNI)


def zbuduj(team_id: int, rekordy: list[dict], teraz: int,
           mapa_rynkow: dict[str, str]) -> dict:
    """Rekordy historii -> profil jednej drużyny.

    `mapa_rynkow` to `statshub.TEAM_PERF_MAP` (pole feedu -> kod rynku),
    wstrzykiwana, żeby ten moduł nie zależał od źródła danych.

    Zwraca `{}`, gdy historia jest pusta albo zbyt chuda — pusty profil jest
    uczciwszy niż profil zbudowany z dwóch meczów.
    """
    surowe: dict[str, dict[str, list]] = {}
    ostatni = 0
    mecze = 0
    for rec in rekordy or []:
        ev = rec.get("event") or {}
        try:
            ts = int(ev.get("timeStartTimestamp") or 0)
        except (TypeError, ValueError):
            ts = 0
        if not ts or ts > teraz:
            # mecz bez daty albo z przyszłości (feed miewa oba) — nie liczymy
            continue
        st = rec.get("statistics") or {}
        opp = rec.get("opponentStatistics") or {}
        home = rec.get("homeTeam") or {}
        u_siebie = int(home.get("id") or 0) == int(team_id)
        ostatni = max(ostatni, ts)
        mecze += 1
        for pole, rynek in mapa_rynkow.items():
            for strona, zrodlo in (("notuje", st), ("dopuszcza", opp)):
                v = zrodlo.get(pole)
                if v is None:
                    continue
                surowe.setdefault(rynek, {}).setdefault(strona, []).append(
                    (float(v), ts)
                )
        # GOLE: nie ma ich w `statistics` — są w wyniku meczu, a strona zależy
        # od tego, gdzie graliśmy (ta sama pułapka co w `historia_druzyny`).
        wynik = ev.get("score") or {}
        strzelone = wynik.get("home" if u_siebie else "away")
        stracone = wynik.get("away" if u_siebie else "home")
        for strona, v in (("notuje", strzelone), ("dopuszcza", stracone)):
            if v is not None:
                surowe.setdefault("team_goals", {}).setdefault(
                    strona, []
                ).append((float(v), ts))

    if mecze < MIN_MECZE:
        return {}

    rynki: dict[str, dict] = {}
    for rynek, strony in surowe.items():
        wpis: dict = {}
        for strona, pary in strony.items():
            if len(pary) < MIN_MECZE:
                continue
            wagi = [_waga(ts, teraz) for _v, ts in pary]
            suma_wag = sum(wagi)
            if suma_wag <= 1e-9:
                # wszystkie obserwacje tak stare, że wagi zeszły do zera —
                # płaska średnia jest uczciwsza niż dzielenie przez zero
                wpis[strona] = round(sum(v for v, _t in pary) / len(pary), 3)
            else:
                wpis[strona] = round(
                    sum(v * w for (v, _t), w in zip(pary, wagi)) / suma_wag, 3
                )
            wpis[f"n_{strona}"] = len(pary)
        if wpis:
            rynki[rynek] = wpis
    if not rynki:
        return {}
    return {"ts": int(teraz), "ostatni_mecz": int(ostatni), "n": mecze,
            "rynki": rynki}


def wymaga_odswiezenia(profil: dict | None, teraz: int,
                       swiezosc_h: float = SWIEZOSC_H) -> bool:
    """Czy warto wydać zapytanie na tę drużynę.

    Odświeżamy, gdy profilu nie ma albo gdy jest starszy niż `swiezosc_h`.
    Świadomie NIE patrzymy na terminarz („czy grała od ostatniego razu"):
    terminarz bywa niekompletny dla egzotyki, a pomyłka w tę stronę oznacza
    profil zamrożony na tygodnie. Doba to kompromis, który i tak ścina ~95%
    zapytań wobec pytania przy każdym cyklu.
    """
    if not profil or not profil.get("rynki"):
        return True
    wiek_h = (int(teraz) - int(profil.get("ts") or 0)) / 3600.0
    return wiek_h >= swiezosc_h


def wartosc(profil: dict | None, rynek: str, strona: str = "dopuszcza"
            ) -> tuple[float | None, int]:
    """(wartość, próba) dla rynku — albo (None, 0), gdy profil jej nie zna."""
    if not profil:
        return None, 0
    wpis = (profil.get("rynki") or {}).get(rynek) or {}
    v = wpis.get(strona)
    n = int(wpis.get(f"n_{strona}") or 0)
    if v is None or n < MIN_MECZE:
        return None, 0
    return float(v), n


def scal(magazyn: dict | None, team_id: int, profil: dict) -> dict:
    """Wstaw profil drużyny do magazynu (kopia, bez mutacji wejścia)."""
    out = dict(magazyn or {})
    out.setdefault("wersja", WERSJA)
    druzyny = dict(out.get("druzyny") or {})
    if profil:
        druzyny[str(int(team_id))] = profil
    out["druzyny"] = druzyny
    return out


def przytnij(magazyn: dict | None, teraz: int,
             rotacja_dni: float = ROTACJA_DNI) -> tuple[dict, int]:
    """Wyrzuć drużyny, które od dawna nie grały. Zwraca (magazyn, ile zeszło).

    Bez tego klucz rośnie w nieskończoność o kluby z zakończonych rozgrywek,
    a cykl czyta go przy każdym przebiegu.
    """
    out = dict(magazyn or {})
    druzyny = dict(out.get("druzyny") or {})
    granica = int(teraz) - int(rotacja_dni * 86400)
    zostaje = {
        k: v for k, v in druzyny.items()
        if int((v or {}).get("ostatni_mecz") or 0) >= granica
    }
    out["druzyny"] = zostaje
    out.setdefault("wersja", WERSJA)
    return out, len(druzyny) - len(zostaje)


def pobierz(magazyn: dict | None, team_id) -> dict | None:
    if not magazyn or team_id is None:
        return None
    try:
        klucz = str(abs(int(team_id)))
    except (TypeError, ValueError):
        return None
    return (magazyn.get("druzyny") or {}).get(klucz)
