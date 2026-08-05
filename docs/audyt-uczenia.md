# Czy model uczy się na wszystkim — audyt 2026-08-05

**Pytanie:** czy model faktycznie uczy się na wszystkich rodzajach typów
i wszystkich funkcjach — zawodnicy, drużyny, drabinki. I czy analiza typu
naprawdę bierze pod uwagę to, co w piłce ma znaczenie.

**Metoda:** `pipeline/scripts/audyt_uczenia.py` na żywej księdze (2109 wpisów,
667 rozliczeń bieżącej epoki). Odpalać ponownie po każdej większej zmianie bram.

---

# 1. Uczy się na wszystkich trzech — ale skrajnie nierówno

```
strumień     rozliczeń  deklaruje  trafia    luka      ROI
ZAWODNICY           41     72,3%    63,4%   − 8,9 pp   − 7,8%
DRUŻYNY            579     70,5%    58,4%   −12,1 pp   − 3,0%
DRABINKI            47     51,4%    40,4%   −10,9 pp   −15,6%
```

**Wszystkie trzy strumienie mają policzoną korektę** (zawodnicy −0,201,
drużyny −0,430, drabinki −0,287), więc odpowiedź na pytanie brzmi: tak, uczy się
na każdym. Ale:

* **93% materiału to DRUŻYNY.** Model uczy się prawie wyłącznie na nich.
* **ZAWODNICY mają 41 rozliczeń przy progu 40.** Korekta tego strumienia stoi
  na JEDNYM rekordzie zapasu — jedno rozliczenie mniej i warstwa przestaje
  działać, po cichu, wracając do wartości globalnej.
* **DRABINKI mają korektę globalną, ale bez przedziałów** (drużyny i zawodnicy
  mają po 4). Czyli drabinka o szansie 40% i 80% dostaje tę samą poprawkę.
* Wszystkie trzy **przeszacowują o 9–12 pp**. To jest ta sama wada od miesiąca.

# 2. Siedem rynków publikujemy, ale się na nich NIE uczymy

Kalibracja rynkowa objęła 12 rynków, ale **7 z nich nie ma ani jednego
rozliczenia w bieżącej epoce** i jedzie na połowie korekty z epoki poprzedniej:

```
fouls_committed, fouls_won, headed_shots, interceptions,
shots_outside_box, sot_outside_box  (+ jeden)
```

Do tego u większości rynków **wszystkie cztery przedziały mają IDENTYCZNĄ
wartość** — czyli pomiar per przedział nie miał danych i spadł do globalnej.
Realnie zróżnicowane są tylko cztery: `match_corners`, `team_goals`,
`team_corners`, `shots`.

# 3. Czynniki modelu — co realnie rusza liczbę

Mnożnik równy 1,00 nie robi nic. Ile typów danego rynku ma czynnik ≠ 1,00:

```
rynek            n    rywal   dom/wyjazd  scenariusz  styl rywala  sędzia
team_goals       6     2/6       3/6         2/6         3/6         –
shots            4     3/4       3/4         3/4         2/4         –
team_sot         2     2/2       2/2         2/2          –          –
team_fouls       1     1/1       1/1         1/1         1/1         –
team_cards       3     1/3       1/3          –           –          –
match_cards      3      –         –           –           –          –
match_corners    1      –         –           –           –          –
```

**Co działa:** rywal, dom/wyjazd, scenariusz meczu (z kursów 1X2), styl rywala.
Na rynkach drużynowych i na strzałach zawodniczych te cztery realnie ruszają
liczbę — czyli analiza NIE jest samą średnią z historii.

**Dwie dziury:**

1. **`match_cards` i `match_corners` mają PUSTE czynniki.** To sumy meczowe —
   dopisują się do listy własną ścieżką i nigdy nie dostały rachunku. Skutek dla
   użytkownika: te typy nie mają jak się wytłumaczyć na karcie, a to dziś 4 z 20
   pozycji. Problem znany od 04.08, nadal otwarty.
2. **Sędzia nie ruszył ANI JEDNEGO typu** — i to nie jest zepsuty kod, tylko
   głód danych:

```
855 rozegranych meczów z obsadą, 444 różnych sędziów
   210 sędziów ma 1 mecz w profilu
   137 sędziów ma 2 mecze
    53 sędziów ma 3 mecze
   najlepiej pokryty (Szymon Marciniak) ma 7
```

Przy próbie 1–2 meczów każdy sensowny shrink ściąga mnożnik do 1,00. Realny
zakres mnożników to 0,95–1,11, a **46% meczów w bazie w ogóle nie ma
przypisanego sędziego**. Na kartkach — gdzie arbiter powinien znaczyć najwięcej
— dziś wszystkie typy mają sędziego neutralnego.

# 4. „Przewaga nad bukmacherem" — co to znaczy i czy jest udowodniona

Gdy piszemy „przewaga", mamy na myśli: **nasza szansa minus szansa wynikająca
z kursu**. To DEFINICJA, nie dowód. Osobne pytanie brzmi: czy nasza liczba
przewiduje lepiej niż sam kurs. Zmierzone:

```
rynek | strona              n     przewaga
team_corners | powyżej      34    +0,0012
shots        | powyżej      30    −0,0008
team_goals   | poniżej     208    −0,0018
team_corners | poniżej     253    −0,0288
team_goals   | powyżej      45    −0,0292
```

**Na żadnym rynku z sensowną próbą nasza liczba nie bije ceny.** Jedyna dodatnia
wartość to +0,0012 przy n=34, czyli zero w granicach szumu.

To NIE znaczy, że model jest bezwartościowy — porządkuje typy poprawnie
(krzywa 32→83% monotonicznie na 585 typach) i ma dobrą architekturę. Znaczy, że
**słowo „przewaga" na stronie opisuje różnicę dwóch liczb, a nie udowodnioną
umiejętność wygrywania z rynkiem.** Przy sprzedaży trzeba to mówić dokładnie
tak, bo inaczej obiecujemy coś, czego pomiar nie potwierdza.

---

# Co z tego wynika — kolejność prac

**Najpierw podaż materiału do uczenia, potem strona.** Sensu nie ma polerowanie
prezentacji typów, których model nie umie wytłumaczyć ani ocenić.

1. **Czynniki dla sum meczowych** (`match_*`, `wiecej_*`) — mają λ obu drużyn,
   więc da się z tego zrobić przynajmniej „poziom bazowy" i „co go zmienia".
   Bez tego 4 z 20 typów na liście to karty bez rachunku.
2. **Strumień zawodniczy ma 41 rozliczeń** — trzeba go albo zasilić (podaż
   typów), albo świadomie przyjąć, że jego korekta jest oparta na szumie.
3. **Sędzia: albo próg, albo cisza.** Przy 1–2 meczach na arbitra mnożnik jest
   zgadywaniem. Uczciwiej pokazywać go dopiero od N meczów, a poniżej nie
   wspominać o sędzim na karcie.
4. **Siedem rynków bez rozliczeń** — albo przestajemy je publikować, albo
   przyjmujemy, że jadą na korekcie z martwej epoki.

Dopiero po tym ma sens przejście strona po stronie pod kątem wyglądu i tekstu.
