# Rekomendacje po audycie uczenia — 2026-08-05

**Zasada tego dokumentu:** każda naprawa ma **czujnik**. Nie „poprawimy i zobaczymy",
tylko „poprawimy, a jeśli to samo zepsuje się za dwa tygodnie, dowiemy się tego
z cyklu, a nie od użytkownika". Naprawa bez czujnika nie wchodzi na tę listę.

Pomiary: `pipeline/scripts/audyt_uczenia.py` + sondy ad hoc opisane niżej.
Stan wyjściowy: `docs/audyt-uczenia.md`.

---

# ✅ ZNALEZISKO NR 1: dziewięć warstw uczenia może umrzeć po cichu

> **WDROŻONE 2026-08-05.** Rejestr `rozliczanie.warstwa_uczenia` zastąpił
> dwanaście bloków `try/except`. Stan idzie do `meta.uczenie_stan`, tabela
> drukuje się w każdym cyklu, a padnięcie `korekta_strumienia` albo
> `szansa_pokazywana` przerywa cykl (`build_wc_fast`) i wstrzymuje nadpisanie
> kuponów (`rozlicz_only`). Czujnik: `tests/test_stan_uczenia.py` (8 testów) —
> nowa warstwa bez wpięcia do rejestru wywala test. Panel dla admina:
> `components/skutecznosc/StanWarstw.tsx`, zakładka „Postęp".

**To jest najpilniejsza rzecz w całym audycie i odpowiedź na pytanie
„czy coś się znowu wyjebie".** Odpowiedź brzmi: tak, i już się zdarzyło.

Każde wywołanie warstwy uczenia w `build_wc_fast.py` wygląda tak:

```python
try:
    korekta_strumieni = rozliczanie.korekta_strumienia()
except Exception as e:
    korekta_strumieni = {}
    print(f"Korekta strumienia pominięta ({e})")
```

**Dwanaście takich miejsc, dziewięć różnych warstw:**

```
korekta_strumienia        szansa_pokazywana         kwarantanna rynków
kwarantanna kategorii     kwarantanna stron         przewaga_rynkow / pasm
rynki_do_ukrycia          waga_rynku_pomiar         wagi_zaufania
```

Skutek awarii: **cykl kończy się na ZIELONO**, strona działa, typy się publikują,
a model przestaje się uczyć. Jedyny ślad to linijka w logu GitHub Actions, do
którego nikt nie zagląda. To nie jest hipoteza — 2026-08-01 cała warstwa uczenia
leżała **półtora doby** przez `print` z polskim znakiem w `except` (patrz notatka
„uczenie padało przez print"). Wykryliśmy to przypadkiem.

## Naprawa

Nie usuwać `try/except` — cykl ma prawo dokończyć pracę, gdy jedna warstwa padnie.
Zamiast tego **podnieść awarię do danych**, tak jak zrobiliśmy z cichymi błędami
źródeł (`diagnostyka.cichy` → `meta.ciche_bledy`).

1. `rozliczanie.stan_uczenia()` — słownik `{warstwa: {"ok": bool, "n": int,
   "wartosc": …, "blad": str|None}}`, wypełniany przy każdym wywołaniu.
2. Wynik ląduje w `meta.uczenie_stan` i jest **drukowany w cyklu jedną tabelą**,
   niezależnie od tego, czy coś padło.
3. **Cykl kończy się BŁĘDEM, gdy padnie warstwa krytyczna** — `korekta_strumienia`
   albo `szansa_pokazywana`. Te dwie decydują o liczbie pokazywanej użytkownikowi;
   praca bez nich jest gorsza niż brak przeliczenia. Reszta (kwarantanny,
   przewaga, wagi) degraduje się łagodnie i wystarczy jej licznik.

## Czujnik

* **W cyklu:** tabela stanu w każdym logu — widać, że warstwa żyje, a nie tylko
  że nie krzyczy.
* **Na stronie:** kafelek w zakładce Skuteczność (widok admina) — „warstwy
  uczenia: 9/9". Spadek na 8/9 widać bez czytania logów.
* **W CI:** `test_stan_uczenia.py` — każda warstwa z listy MUSI raportować
  status; dopisanie nowej warstwy bez wpięcia do rejestru wywala test.

## Jak sprawdzić, że działa

Podmienić w teście jedną warstwę na taką, która rzuca wyjątek, i sprawdzić, że
(a) `meta.uczenie_stan` pokazuje ją jako padniętą, (b) cykl kończy się błędem,
gdy to warstwa krytyczna.

---

# ✅ ZNALEZISKO NR 2: uczymy się na rynku, którego nie sprzedajemy

> **CZUJNIK WDROŻONY 2026-08-05.** `rozliczanie.rynki_bez_kalibracji` +
> linia w każdym cyklu: „Rynki publikowane bez własnej kalibracji (próg 25):
> match_cards — 3 typy, 1 rozliczeń". Punkt 2 (karta typu mówi o mniejszej
> próbie) ZOSTAJE otwarty — to zmiana w treści karty, więc idzie z przejściem
> strona po stronie.

```
rynek              rozliczeń   na stronie   stan
team_corners            287            0    uczy się   <-- W KWARANTANNIE
team_goals              253            6    uczy się
shots                    63            4    uczy się
team_cards               16            3    poniżej progu (25)
team_sot                  9            2    poniżej progu
team_fouls                3            1    poniżej progu
match_cards               1            3    poniżej progu
match_corners             1            1    poniżej progu
```

**Rynek z największą próbą — 287 rozliczeń — ma dziś ZERO typów na stronie**,
bo siedzi w kwarantannie. Jednocześnie rynki, które realnie sprzedajemy
(`match_cards` 3 typy, `team_cards` 3, `team_sot` 2) mają od 1 do 16 rozliczeń,
czyli **poniżej progu kalibracji** i jadą na korekcie z poprzedniej epoki.

Czyli: 78% materiału do uczenia pochodzi z dwóch rynków, z których jeden jest
wyłączony ze sprzedaży. Model doskonali się w czymś, czego nie pokazujemy.

## Naprawa

To NIE jest wołanie o wyłączenie kwarantanny — ona ma powód (ROI). To wołanie
o **świadomość rozjazdu**: dziś nikt nie widzi, że rynek, na którym stoi
kalibracja, nie jest tym, który sprzedajemy.

1. Raport `rynek → (rozliczeń, opublikowanych, w kwarantannie)` w każdym cyklu.
2. Przy rynku publikowanym **poniżej progu kalibracji** karta typu ma prawo
   powiedzieć, że korekta jest z mniejszej próby — dziś udaje, że wie tyle samo
   o `match_cards` (1 rozliczenie) co o `team_goals` (253).

## Czujnik

Jedna linia w cyklu: `Rynki publikowane bez własnej kalibracji: match_cards (1),
team_cards (16), team_sot (9)…`. Gdy lista rośnie, znaczy że wypuszczamy
nowe rynki szybciej, niż je mierzymy — i to jest dokładnie to, co stało się
z sumami meczowymi 30.07.

---

# ✅ ZNALEZISKO NR 3: strumień zawodniczy stoi JEDEN rekord nad progiem

> **CZUJNIK WDROŻONY 2026-08-05.** `rozliczanie.proby_strumieni` +
> `ostrzezenia_prob`: cykl pisze „pewniaki: 41 rozliczeń przy progu 40 —
> NA STYK, 2 rozliczeń od zniknięcia korekty", a `n` warstwy to teraz liczba
> ROZLICZEŃ, nie liczba strumieni z korektą. Czujnik: `tests/test_proby_uczenia.py`.
> Punkt 2 (decyzja o podaży typów zawodniczych) ZOSTAJE otwarty.

```
ZAWODNICY   41 rozliczeń    próg korekty strumienia = 40
```

Jedno rozliczenie mniej i `korekta_strumienia` **przestaje zwracać wartość dla
tego strumienia** — po cichu, bez błędu, spadając do wartości globalnej. Nikt
by tego nie zauważył, bo warstwa nadal „działa".

Przyczyna jest po stronie podaży, nie kodu:

```
świeżych typów   drużyny   zawodnicy   drabinki
ostatnie  24 h       132          17         22
ostatnie 168 h      1077          50         84
```

Siedem typów zawodniczych dziennie. Przy oknie 120 rozliczeń ten strumień nigdy
nie zbierze pełnej próby.

## Naprawa

Dwie osobne rzeczy, nie mieszać:

1. **Natychmiast — czujnik.** Warstwa raportuje `n` obok wartości; gdy strumień
   jest w promieniu 20% od swojego progu, cykl pisze ostrzeżenie. To nie naprawia
   podaży, ale odbiera efekt zaskoczenia.
2. **Docelowo — decyzja o podaży.** Albo zwiększamy podaż typów zawodniczych
   (wąskie gardło: Superbet kwotuje prawie wyłącznie „powyżej" — patrz
   `docs/audyt-uczenia.md`), albo **świadomie przyjmujemy, że korekta tego
   strumienia jest oparta na szumie** i mówimy to wprost w dokumentacji.
   Czego nie robić: udawać, że 41 rozliczeń to pomiar.

## Czujnik

`n` przy każdej korekcie w logu i w `meta.uczenie_stan`. Ostrzeżenie przy
zbliżeniu do progu. Test: warstwa MUSI zwracać `n`, nie samą liczbę.

---

# ZNALEZISKO NR 4: drużyny się psują, i to jest główny strumień

```
strumień     połowa próby   deklaruje   trafia    luka
ZAWODNICY    starsza (20)      72,9%     60,0%   −12,9 pp
ZAWODNICY    nowsza  (21)      71,8%     66,7%   − 5,1 pp    poprawa
DRUŻYNY      starsza (289)     70,6%     60,9%   − 9,7 pp
DRUŻYNY      nowsza  (290)     70,4%     55,9%   −14,5 pp    POGORSZENIE
DRABINKI     starsza (23)      53,3%     39,1%   −14,1 pp
DRABINKI     nowsza  (24)      49,5%     41,7%   − 7,9 pp    poprawa
```

Strumień, który daje 93% materiału, **pogarsza się**: trafienia spadły z 60,9%
na 55,9% przy niezmienionej deklaracji. Zawodnicy i drabinki idą w dobrą stronę,
ale ich próby są dziesięć razy mniejsze.

To nie jest wada kalibracji — to model, który **traci trafność szybciej, niż
korekta zdąża obniżyć deklarację**. Najbardziej prawdopodobna przyczyna
(hipoteza, NIE potwierdzona): rozszerzenie zakresu lig 27.07. Od 03.08 każdy typ
niesie stempel rozgrywek, więc **za tydzień jedno zapytanie odpowie**, czy
tracimy równo wszędzie, czy w konkretnych ligach.

## Naprawa

**Nie ruszać teraz.** Zmiana korekty pod pogarszający się model to gonienie
własnego ogona. Zamiast tego:

1. Poczekać na próbę ze stemplem ligi (≈ 12.08) i rozbić lukę per rozgrywki.
2. Dopiero wtedy decyzja: zawęzić ligi czy uczyć per liga.

## Czujnik

**Trend luki per strumień, liczony w każdym cyklu** i pokazywany w zakładce
„Czy się uczymy". Dziś ta zakładka pokazuje paczki po 40 rozliczeń, ale
**nie pokazuje kierunku** — a kierunek jest jedyną rzeczą, która mówi, czy
model się uczy, czy psuje. Alarm, gdy nowsza połowa jest o ponad 3 pp gorsza
od starszej przy n ≥ 100.

---

# ZNALEZISKO NR 5: bramy nie wybierają lepszych typów

```
                    n     deklaruje   trafia    luka
opublikowane      444        65,9%    53,8%   −12,0 pp
poza publikacją   223        76,0%    64,6%   −11,4 pp
```

Typy, których **nie** publikujemy, trafiają o 11 pp częściej niż te, które
publikujemy. **Luka kalibracji jest w obu grupach praktycznie identyczna**
(−12,0 vs −11,4) — czyli bramy w ogóle nie selekcjonują pod jakość predykcji.

## Czego to NIE dowodzi

Trafność ≠ zysk. Grupa „poza publikacją" to w większości rynki w kwarantannie —
tanie „poniżej" o wysokiej trafności i ujemnym ROI. Odrzucamy je właśnie dlatego,
że tracą pieniądze mimo wysokiej trafności. **Ten wynik nie znaczy, że bramy są
odwrotnie skuteczne.**

## Co to jednak znaczy

Bramy optymalizują ROI, a **kalibracja nie jest przez nie w ogóle brana pod
uwagę** — publikujemy typy tak samo źle skalibrowane jak te, które odrzucamy.
To jest dokładnie ta „kalibracja publikacyjna", która wisi na liście od tygodni:
uczyć osobną korektę WYŁĄCZNIE na zbiorze, który przeszedł regułę publikacji.

## Naprawa

Osobna korekta liczona na `poza_publikacja is None`. To zmiana na kilkadziesiąt
linii — mechanizm istnieje, zmienia się tylko zbiór wejściowy.

**Warunek wstępny, którego nie wolno pominąć:** reguła publikacji musi stać
nieruchomo przez cały okres zbierania próby. W ciągu ostatnich dwóch dni
ruszaliśmy ją trzy razy (okno zgody, brama uzasadnień, limit rodziny). Zbiór
uczący byłby mieszanką trzech różnych reguł — czyli dokładnie ten błąd, który
kazał odwoływać wnioski dwa razy w tygodniu.

**Kolejność:** zamrozić bramy → tydzień rozliczeń → dopiero wtedy kalibracja
publikacyjna.

## Czujnik

Stempel `wersje` przy typie już istnieje i niesie wersję polityki selekcji.
Kalibracja publikacyjna **musi filtrować po tym stemplu** i odmówić liczenia,
gdy w próbie jest więcej niż jedna wersja polityki. Bez tego pierwsza zmiana
bramy po cichu zatruje pomiar.

---

# ZNALEZISKO NR 6: przedziały korekty w większości nie mają danych

```
rynek            0,0–0,55   0,55–0,70   0,70–0,85   0,85–1,01
team_corners           78          49          51         109
team_goals             65          52          97          39
shots                 19*          22          20          2*
                                       (* poniżej progu 20)
```

Tylko dwa rynki mają wszystkie cztery przedziały z własnymi danymi. `shots` ma
dwa z czterech poniżej progu — te spadają do wartości globalnej **po cichu**.
Wszystkie pozostałe rynki mają jedną wartość powielaną na cztery przedziały,
co w raporcie wygląda jak pomiar per przedział, a jest jego brakiem.

## Naprawa

Nie obniżać progu — 20 rozliczeń to i tak mało. Zamiast tego **przestać
udawać**: gdy przedział spada do globalnej, oznaczyć to w danych
(`"zrodlo": "globalna"`) i nie rysować go w raporcie uczenia jako osobnego
pomiaru.

## Czujnik

Licznik w cyklu: `Przedziały korekty: 8 z 56 na własnych danych, reszta globalna`.
Gdy ten stosunek spada, znaczy, że rozszerzamy rynki szybciej, niż zbieramy
próbę.

---

# ✅ ZNALEZISKO NR 7: czynniki modelu — dwie dziury

> **OBIE WDROŻONE 2026-08-05.**
>
> **Sumy meczowe:** `build_wc_fast.mnozniki_pary` składa mnożniki obu drużyn
> średnią geometryczną i wypełnia `czynniki`, a `czynniki_pary` dopisuje zdania
> („Profil rywali", „Dom i wyjazd", „Scenariusz meczu", „Styl rywali", „Sędzia").
> To NIE była kosmetyka: brama uzasadnień patrzy dokładnie na pole `czynniki`,
> więc każdy typ na sumie poniżej 70% szansy wypadał z listy jako „bez
> uzasadnienia" — mimo że model policzył wszystko. Czujnik: `tests/test_czynniki_sum.py`.
>
> **Sędzia:** `context.MIN_MECZE_SEDZIA = 4` — poniżej mnożnik jest DOKŁADNIE
> 1,00, a karta mówi „mamy za mało jego meczów, żeby cokolwiek o nim twierdzić"
> zamiast „gwiżdże mniej niż przeciętny arbiter (1 jego meczów w danych)".
> Czujnik: cztery testy w `tests/test_sedzia_kartki.py`.

## 7a. Sumy meczowe bez rachunku

`match_cards` i `match_corners` mają **puste `czynniki`** — dziś 4 z 20 typów na
liście. Powód: te rynki dopisują się do listy własną ścieżką (`value_bets.append`
wprost) i nigdy nie dostały rachunku. To ta sama ścieżka, która 04.08 omijała
kwarantanny.

**Naprawa:** mają `lambda` obu drużyn, więc da się z tego zbudować minimum
„poziom bazowy" + „co go zmienia". Bez tego brama uzasadnień (wdrożona dziś)
będzie je zdejmować w komplecie, gdy tylko trafią na półkę „więcej płacą".

**Czujnik:** test, który dla KAŻDEGO rynku w `MARKET_NAMES_PL` sprawdza, że
typ tego rynku wychodzi z niepustymi `czynniki`. Nowy rynek bez rachunku
nie przejdzie CI.

## 7b. Sędzia to głód danych, nie zepsuty kod

```
855 rozegranych meczów z obsadą, 444 różnych sędziów
   210 sędziów ma 1 mecz w profilu
   137 sędziów ma 2 mecze
    53 sędziów ma 3 mecze
   najlepiej pokryty ma 7
46% meczów w bazie NIE MA przypisanego arbitra
```

Przy 1–2 meczach na arbitra każdy sensowny shrink ściąga mnożnik do 1,00 —
i tak jest: zakres realnych mnożników to 0,95–1,11, a na dzisiejszych typach
kartkowych sędzia jest neutralny w 100% przypadków.

**Naprawa — wybrać JEDNO:**

* **A (uczciwe, tanie):** próg minimum N meczów na arbitra. Poniżej progu
  mnożnik = 1,00 **i karta nie wspomina o sędzim**. Dziś karta potrafi
  napisać „sędzia: surowy" na podstawie jednego meczu.
* **B (drogie):** dociągnąć historię arbitrów wstecz, żeby profile miały
  po 10+ meczów. To zapytania do 365Scores i czas cyklu, którego nie mamy.

Rekomendacja: **A teraz, B nigdy** — chyba że pomiar pokaże, że sędzia realnie
ruszałby typy przy pełnej próbie.

**Czujnik:** licznik w cyklu `sędziowie: N profili, mediana M meczów, K% meczów
bez obsady`. Gdy pokrycie rośnie, próg można obniżyć — świadomie, nie przypadkiem.

---

# KOLEJNOŚĆ PRAC

Uszeregowane po tym, co się stanie, jeśli tego NIE zrobimy.

| # | Co | Jeśli nie zrobimy | Koszt |
|---|---|---|---|
| 1 | **Stan warstw uczenia + twardy błąd na krytycznych** | Warstwa pada po cichu, dowiadujemy się po tygodniach — już się zdarzyło | pół dnia |
| 2 | **`n` i trend przy każdej korekcie** | Strumień zawodniczy wyłączy się bez śladu przy 40 rozliczeniach | godziny |
| 3 | **Czynniki dla sum meczowych** | Brama uzasadnień zdejmie 4 z 20 typów, gdy trafią na ryzykowną półkę | pół dnia |
| 4 | **Próg pokrycia sędziego** | Karta twierdzi rzeczy o arbitrze na podstawie jednego meczu | godziny |
| 5 | **Raport rynek: rozliczenia vs publikacje** | Kolejny nowy rynek wyjdzie bez kalibracji i nikt nie zauważy | godziny |
| 6 | **Rozbicie luki per liga** (po 12.08) | Nie dowiemy się, czemu drużyny się psują | czeka na dane |
| 7 | **Kalibracja publikacyjna** | Największa rzecz modelowa — ale wymaga tygodnia nieruszania bram | dni |

**Punkty 1–5 to jeden dzień pracy i wszystkie są czujnikami.** Dopiero po nich
ma sens 6 i 7 — bo bez czujników nie będziemy wiedzieć, czy zadziałały.

---

# CZEGO ŚWIADOMIE NIE REKOMENDUJĘ

* **Nie zmieniać korekty strumienia drużynowego teraz.** Model się psuje;
  dostrajanie korekty pod ruchomy cel to gonienie ogona.
* **Nie obniżać progów kalibracji.** 25 rozliczeń na rynek to i tak mało;
  obniżenie da szybciej liczby, które nic nie znaczą.
* **Nie wyłączać kwarantanny `team_corners`**, mimo że to nasza największa próba.
  Ma ujemne ROI i pomiar 04.08 pokazał, że ranking przewagi działa tam ODWROTNIE.
* **Nie usuwać `try/except` wokół warstw uczenia.** Cykl ma prawo dokończyć pracę.
  Naprawą jest widoczność, nie twardy pad wszystkiego.
