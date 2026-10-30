# Etap 0 – mapowanie statshub → własny statshub (FotMob)

Źródła: pełny opis kształtów `sources/statshub.py` i konsumentów (raporty etapu 0, 30.10),
próbka FotMob `matchDetails` (Sunderland–Leeds 25.10), pomiar zgodności 30.10 (88 zapytań).

Legenda: **1:1** – to samo pole w FotMob · **liczone** – z bazy meczów (FotMob raz po meczu) ·
**lepiej** – FotMob daje więcej · **weryfikacja E1** – pole istnieje, kształt do sprawdzenia
na żywo w etapie 1 · **porzucamy** – zero albo kosmetyczny wpływ (decyzja właściciela).

## A. Krytyczne (bez nich nie ma typów albo rozliczeń)

| Dane statshub | Konsumenci | FotMob / nasza baza | Status |
|---|---|---|---|
| Terminarz `event/by-date`: id, start, drużyny id+nazwa, utid, status | build_league, silnik, parowanie Superbet | `api/data/matches?date=` – id, `status.utcTime`, `home/away.id/name`, liga id, `status.started/finished/cancelled` | 1:1 (id przez etap 3) |
| `slug` (nazwy dla 365) | rozliczanie 365 | nazwy drużyn z terminarza | liczone |
| `lineupConfirmed` | bramy składu, UI | `lineup.lineupType` / `lineup.source` | weryfikacja E1 |
| Historia zawodnika `player/performance` (minuty, 10 statystyk, pozycja, `teamId`, rywal, utid, `substitutedIn/Out`, mecze z 0 min) | trendy, ratunek historii, odkrywanie, rozliczenia, nauka | baza meczów: `playerStats` + `shotmap` + `lineup.starters/subs` + zdarzenia `Substitution` | liczone (zgodność 96–100%) |
| Kadra `team/players/performance` (stats per mecz, `wonContest`) | pełne kadry, krycie, występy | baza meczów (wszyscy zawodnicy drużyny z jej meczów); `wonContest` → `Successful dribbles` | liczone |
| `unavailability` (rodzaj, status out/dayToDay, daty) | niedostępni (brama), braki | `lineup.unavailable` (mecz) + strona drużyny | weryfikacja E1 |
| Historia drużyny `team/performance`: 15 pól `statistics`/`opponentStatistics`, wynik, `league.id`, dogrywka | magazyn `hd_*` = cały model drużynowy, profil, rozliczenia zapasowe | `content.stats.Periods.All` (strzały, celne, niecelne, zablokowane, zza pola, w polu, rożne, faule, żółte, czerwone, spalone, posiadanie, xG, odbiory, przechwyty, …) + `header` wynik | liczone; **lepiej** (połowy: `FirstHalf/SecondHalf`) |
| Wynik i status meczu (`*ScoreNormaltime`, dogrywka, odwołany) | rozliczenia, zwroty | `header.status` (`finished`, `cancelled`, `scoreStr`, `reason`) + gole z zdarzeń do 90' | weryfikacja E1 (flaga dogrywki) |
| Wyszukiwarka + profil zawodnika (`team_id`) | odkrywanie z oferty | nasza baza (zawodnik → drużyna z ostatniego meczu) | liczone |

## B. Ważne (są zapasy, ale chcemy pełną jakość)

| Dane statshub | FotMob / baza | Status |
|---|---|---|
| Rynki zza pola / głową / 1. połowa (`extra-stats`, shotmap) | `shotmap.shots`: `isFromInsideBox`, `shotType=Header`, `period`, `isOnTarget`, `isBlocked` | 1:1 (98–100%); brak mapy w części małych lig |
| Shotmap `x/y` (Sofascore 0–100), `situation` | `x/y` FotMob (inna geometria), `situation` | liczone – przeliczenie współrzędnych, mapa wartości `situation` |
| `league_average` (cecha modelu, prior) | średnia z bazy per rozgrywki × rynek | liczone |
| `opponent_average` | z bazy: ile rywal dopuszcza (ostatnie 6) | liczone |
| `opponent_rank`, `total_ranks` (opis UI) | z bazy | liczone (tanio) |
| Przewidywany / oficjalny XI (`predicted-teams-lineup`, `team-lineup`) | `lineup` przed meczem (`lineupType`) + obecne źródła składów | weryfikacja E1; właściciel: składy mogą iść z innych źródeł |
| `in_predicted_lineup`, `historia_pelna`, `z_kadry` | ustawiane przez naszą warstwę | liczone |
| Sędzia (`refereeId`, `matchRecords`) | `matchFacts.infoBox.Referee` (id, mecze, żółte/mecz, faule/mecz, karne) | **lepiej** |
| Wzrost, noga (`player meta`) | profil zawodnika FotMob (do sprawdzenia) | weryfikacja E1 / kosmetyczne |
| Nazwa rozgrywek po utid | terminarz FotMob | 1:1 |

## C. Porzucamy (zero albo kosmetyczny wpływ)

| Dane | Dlaczego |
|---|---|
| Feed `props/player-trends` jako źródło kandydatów | kod działa bez niego od 07.2026; kandydaci z oferty Superbet/Betclic + bank + kadry |
| `line`, `odds_type`, `ref_odds` (kursy UK) | **ZOSTAJĄ w strukturze (właściciel 30.10)** – na przyszłość do porównywania cen i szukania perełek na Superbecie; FotMob ich nie daje → puste do czasu podpięcia źródła kursów (np. Odds API statshub / Sportradar) |
| `last_game_with_team` | zero konsumentów |
| `fetch_team_trends` | zastępowane historią drużyny z magazynu |
| H2H z kadr 80 | wyłączone od 29.10; wróci z własnej bazy (bez dodatkowych zapytań) |
| `wc_auto`, tryb MŚ | poza produkcją |

## D. Tożsamość (decyzja do etapu 3) – propozycja

Pipeline trzyma numery Sofascore (statshub) w: `typy_log` (`mecz_id`, `podmiot_id`, klucz z nazwiskiem),
`trend_lib`, `hd_0..9`, `druzyny_profil`, `druzyny_forma`, `h2h_kadry`, `sedziowie_sh`, `pomiar_xi`,
`styl_bank_liga`, `player_sezon`, `zakres_meczow`, listy publikacji, `rozgrywki.PROFILE` (utid).

**ZATWIERDZONE (właściciel 30.10): numery Sofascore zostają kanoniczne – zero migracji historii.**
1. Mapa FotMob → Sofascore budowana na meczach sprzed 29.10, które mają oba źródła: mecz po dacie
   i drużynach (z `trend_lib` / `hd_*`), zawodnik po nazwisku w obrębie drużyny tego meczu,
   rozgrywki po drużynach.
2. Byty bez odpowiednika (nowi zawodnicy, nowe mecze po przełączeniu): numer zastępczy
   **4 000 000 000 + id FotMob** – nie zderza się z Sofascore (< 10⁸) ani z `PID_SYNTETYCZNY` (9·10⁸).
3. Nazwisko w kluczu księgi bierzemy z mapowanej tożsamości (nazwa statshub), żeby nie powstał dubel.
4. Typy sprzed przełączenia (numer meczu Sofascore) rozliczane przez mapę mecz Sofascore → FotMob.

## E. Pułapki kształtu (replika musi je zachować)
`events`/`player_statistics_event`/`homeTeam` jako dict · klucze `stats` w kadrze = id meczu jako tekst ·
`teamId` w każdym rekordzie · mecze z 0 min obecne · `totalShotsOnGoal` = wszystkie strzały, `shotsOnGoal` = celne ·
`homeScoreOvertime/Penalties` = null bez dogrywki · `recentGames` od najnowszego · `fetch_team_performance`
nie rzuca, `fetch_player_performance`/`fetch_event_shotmap` rzucają · dataclass z identycznymi polami
(`StatshubTrend(**rec)` po cichu gubi rekord o innych polach).

## F. Do sprawdzenia na żywo w etapie 1 (lista kontrolna)
1. `lineup.lineupType` / `source` przed meczem: przewidywany vs potwierdzony – od ilu godzin, w jakich ligach.
2. `lineup.unavailable`: pola (powód, kontuzja/kartki, przewidywany powrót).
3. Flaga dogrywki / karnych i wynik po 90' w `header` / zdarzeniach.
4. Zdarzenia `Substitution`: minuta, kto wszedł / zszedł (→ `substitutedIn/Out`, minuty).
5. Geometria `x/y` shotmapy FotMob → skala Sofascore; wartości `situation`.
6. Pokrycie: odsetek meczów z `playerStats` i `shotmap` w naszym zakresie lig (cel ≥ statshub).
7. Mecze odwołane/przełożone w terminarzu.
8. Strona drużyny / zawodnika FotMob (kadra, kontuzje, wzrost) – czy potrzebna, ile zapytań.
