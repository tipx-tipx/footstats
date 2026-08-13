# Własny skład przewidywany z rotacji minut — zmierzony i ODRZUCONY

**Pomiar 2026-08-13**, na żywym feedzie statshub. Powód: kolejka po audycie
stawiała tę pozycję jako następny duży krok („dla Ameryki Płd. i Skandynawii
nikt nam składów nie poda"), a diagnoza z 11.08 mówiła, że to jedyna droga
do odblokowania strumienia zawodniczego i drabinek.

**Wynik: własna jedenastka nie poprawia modelu, a wpięta jako twardy sygnał
POGARSZA go o 20%.** Poniżej komplet liczb, żeby nikt nie zaczynał tego
drugi raz bez nowego powodu.

---

## 1. Skala problemu — 94% meczów bez składu

Mecze w oknie składów (48 h przed gwizdkiem), źródła sprawdzone po kolei:

| źródło | pokrycie | uwaga |
|---|---|---|
| statshub `team-lineup` (oficjalny) | **0 ze 119** | pojawia się dopiero po gwizdku |
| statshub `predicted-teams-lineup` | **2 ze 119** | działa (Ilves 11/11), ale nie dla naszych lig |
| Rotowire | 50 drużyn, **+5 meczów** | po naprawie kodów lig; Europa Zach. + MLS |
| Sofascore | 2 z 12 lokalnie | **w chmurze wypada** — blokuje IP serwerowni |
| 365Scores | **brak składu przed meczem** | pole `lineups` nie istnieje do gwizdka |

**112 ze 119 meczów (94%) jedzie na samej historii występów.** Diagnoza
z 11.08 się potwierdza, i to na większej próbie.

## 2. Materiał JEST — `team-lineup` działa na meczach rozegranych

Sonda odsłoniła to, czego nie wiedzieliśmy: dla meczu **po gwizdku** endpoint
oddaje komplet 15–16 rekordów z `playerId`, `minutesPlayed`, `isSubstitute`,
`position` i zmianami. Do tego `team/{id}/events` (nieudokumentowany, działa)
daje mecze drużyny. Czyli kadrę i historię startów da się odtworzyć:

```
team/{id}/events -> ostatnie mecze -> team-lineup(mecz, tid) -> kto zaczął
```

Koszt zmierzony: **1,7 s na drużynę**, ok. 7 min na całe okno (238 drużyn),
a z pamięcią między cyklami — tylko przyrost. Wykonalne.

Kadra z 6 meczów: **mediana 22 zawodników**, składy dostępne dla 60% meczów.

## 3. Ale sygnał jest za słaby — walidacja wsteczna

Dla meczu N budujemy XI **wyłącznie z meczów wcześniejszych** (N−1…N−6)
i porównujemy z faktycznym składem. Żaden mecz nie widzi swojej przyszłości.

**Europa (54 testy, głównie eliminacje pucharowe):**

| metoda | trafia | z 11 |
|---|---|---|
| skład z ostatniego meczu | 62,8% | 6,9 |
| 11 najczęściej startujących | 58,8% | 6,5 |
| ważone świeżością (tau 60 d) | 62,0% | 6,8 |

**Ameryka Płd. i Płn. (112 testów — tam, gdzie ta funkcja miała działać):**

| metoda | trafia | mediana | z 11 |
|---|---|---|---|
| **skład z ostatniego meczu** | **68,6%** | 72,7% | 7,5 |
| 11 najczęściej startujących | 65,4% | 63,6% | 7,2 |
| ważone świeżością (tau 60 d) | 67,7% | 72,7% | 7,5 |

Ameryka wypada lepiej niż Europa (mecze co 7 dni zamiast co 3), ale **wciąż
daleko od 85–90% prognoz medialnych** — a to na nich stoi `p_start = 0,93`
dla `predicted_started` w `model/minutes.py`.

⚑ **Żadna metoda nie bije najprostszego baseline'u** — „skład z ostatniego
meczu". Cała konstrukcja z ważeniem i rankingiem nie wnosi nic ponad niego.

## 4. Właściwa miara: czy to poprawia `p_start`

Model nie potrzebuje jedenastki — potrzebuje dobrego `p_start` per zawodnik,
i **już go liczy** z historii (ważona średnia startów). Pytanie brzmi więc, czy
ograniczenie „startuje dokładnie 11" tę liczbę poprawia. Brier na zdarzeniu
„zawodnik zaczął mecz", 2915 obserwacji zawodnik×mecz (Ameryka):

```
p_start z historii (DZIŚ)            0,1994
p_start skalowane do 11 miejsc       0,1994   bez zmiany (0,0%)
twarde 0,93/0,07 z własnej XI        0,2394   GORZEJ o 20,1%
```

Europa (1351 obserwacji) daje **identyczny** obraz: 0,2434 / 0,2434 / 0,2926
(gorzej o 20,2%).

**Wniosek: model wyciska z historii wszystko, co w niej jest.** Normalizacja
do 11 miejsc nie wnosi nic, a twardy sygnał niszczy informację o niepewności —
mieszanka scenariuszy (start / zmiana / ławka / DNP) jest lepsza niż zerojedynkowe
„zagra albo nie", gdy trafność wynosi 68%.

---

## 5. Co z tego rozpoznania jest WARTE ZROBIENIA

### ⚑ Kontuzje i zawieszenia z 365Scores — dziura wskazana przez audyt

`injured_or_suspended` (`engine.py`) zeruje minuty w modelu (`p_start = 0`),
jest konsumowane przez `model/minutes.py` — i **w produkcji nikt go nigdy nie
ustawia**; jedyne przypisanie `True` jest w teście. Audyt zewnętrzny wskazał to
jako dziurę w danych.

Sonda znalazła źródło: `game/?gameId=` **przed meczem** nie ma składu, ale ma
`lineups.members` ze statusami i powodem:

```
Sprawdzonych meczów: 40
Meczów z listą nieobecnych: 22 (55%)
Statusy: Missing 57, Doubtful 9, Management 6, Starting 66
Rekord niesie: {"statusText": "Missing", "position": …,
                "injury": {"categoryId": 1, "reason": "Thigh…"}}
```

**365Scores działa w chmurze** — używamy go do sędziów i statystyk meczowych,
w odróżnieniu od Sofascore. Parowanie zawodników po nazwisku już istnieje
(`scores365.resolve_player_key`).

To jest sygnał **twardy** (kontuzjowany nie zagra), w przeciwieństwie do
przewidywanej jedenastki — więc dokładnie ten rodzaj, którego model potrzebuje.

### Drobiazg z tego samego pomiaru

`Starting` pojawia się na ~3 z 40 meczów, czyli 365Scores oddaje **oficjalny**
skład tuż przed gwizdkiem. Dla `official_started` to trzecie źródło, ale nasze
typy publikujemy wcześniej, więc wartość jest mała.

---

---

## 6. Kompleksowy przegląd źródeł — dopisane 13.08

Sprawdzone **tym samym klientem, którym chodzi pipeline** (`curl_cffi`), bo
liczy się nie to, czy strona istnieje, tylko czy odpowie naszemu botowi
w chmurze. Sofascore jest tu przestrogą: działa z domowego PC, w chmurze nie.

| źródło | dostęp | składy | kontuzje | nasze ligi |
|---|---|---|---|---|
| **SportsGambler** | **HTTP 200, bez klucza** | **przewidywane, 3–10 dni przed** | osobna sekcja | **wszystkie** |
| statshub (mamy) | mamy | 2 ze 119 przed meczem | brak endpointu | — |
| 365Scores (mamy) | mamy | brak przed meczem | **Missing/Doubtful, 55% meczów** | tak |
| Rotowire (mamy) | mamy | 50 drużyn | odcięte świadomie | Europa Zach. + MLS |
| Sofascore (mamy) | **blokuje IP serwerowni** | tak, ale w chmurze wypada | nie | tak |
| TheSportsDB | HTTP 200, klucz „3" | `lookuplineup` zwraca pustkę | nie | — |
| BSD / bzzoiro | HTTP 401, klucz darmowy | oficjalne 1 h przed | `unavailable_players` | tylko top Europa |
| API-Football | HTTP 403, klucz płatny/free 100/dzień | 20–40 min przed | `/injuries` | tak |
| Sportmonks | płatne od €29/mc | **expected lineups** (algorytmiczne) | tak | 2200+ lig |

### SportsGambler — endpoint i pokrycie

Składy nie są w HTML listy: siedzą za `reply_click(ID)`, które dociąga je
z **`/lineups/lineups-load2.php?id=<ID>`** (zwykły GET, ~13 kB HTML,
22 nazwiska w `class="…name…"`, formacja, etykieta `Predicted`/`Confirmed`).

Pokrycie policzone 13.08 — **1206 meczów ze składem**:

```
Brasileirão A  50   Liga Profesional 55   MLS         100   Liga MX      100
Brasileirão B  40   Libertadores    100   Sudamericana 100  Kolumbia     100
Ekstraklasa    24   Allsvenskan      48   Eliteserien   47  Superliga     22
Chile          40   Urugwaj         100   Veikkausliiga 100  LM/LE/LK  40/40/100
```

To jest **dokładnie ta luka**, której nie zamykało żadne z naszych źródeł:
Ameryka Płd., Skandynawia i Ekstraklasa.

### ⚑ Czego jeszcze NIE wiemy — i czemu to jest teraz najważniejsze

**Trafność prognozy SportsGambler nie jest zmierzona.** Pierwsze podejście
dało 92,5% (10,2 z 11) na 28 przypadkach, ale **wszystkie miały etykietę
`Confirmed`** — czyli mierzyliśmy, czy umiemy sparować nazwiska z już
ogłoszonym składem, a nie czy prognoza była trafna. Po meczu serwis podmienia
etykietę i pokazuje skład faktyczny, więc wstecz tego policzyć się NIE DA.

Pierwsze podejście dało też 68,8% przy parowaniu meczów wyłącznie po nazwie
drużyny — to była pomyłka: porównywało prognozę na jeden mecz ze składem
z innego. Dopasowanie po dacie (±36 h) podniosło wynik do 92,5%.

Snapshot 730 prognoz zapisany w `docs/pomiar/` — pomiar zamyka się po
rozegraniu tych meczów. **Próg decyzyjny: wyraźnie powyżej 68,6%**, bo tyle
daje własna jedenastka, którą odrzuciliśmy.

## Czego NIE robić

* **Nie budować własnej przewidywanej jedenastki** — zmierzone na dwóch
  niezależnych zbiorach (54 i 112 testów), oba dają ten sam wynik.
* **Nie wpinać jej jako `predicted_started`** — to ścieżka, która pogarsza
  Brier o 20%.
* **Nie stroić `tau_days`** w nadziei, że to uratuje ranking: baseline bez
  żadnego ważenia (sam ostatni mecz) i tak wypada najlepiej.
* Wracać do tematu wyłącznie z **nowym źródłem składów**, nie z nowym
  sposobem liczenia rotacji.

## Jak to odtworzyć

Skrypty pomiarowe (jednorazowe, w katalogu roboczym sesji): sonda źródeł
składów, test łańcucha kadry, walidacja wsteczna XI (Europa i Ameryka),
pomiar kontuzji 365. Wszystkie czytają żywy feed i nic nie zapisują.
Kluczowe filtry, bez których liczby kłamią:

* **anomalia „mecz rezerw"** — jeśli mniej niż 3 z 11 wystąpiło w całej
  historii, mecz nie mówi nic o rotacji, a jako błąd prognozy liczy się
  podwójnie (1 przypadek na 54 w Europie),
* **9 ≤ |XI| ≤ 13** — rekordy spoza tego zakresu to błędy feedu,
* **rozdzielić Europę od Ameryki** — różnica 6 pp bierze się z odstępu między
  meczami, nie z jakości danych.
