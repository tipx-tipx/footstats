# Ustalenia z 11.08.2026 — pełny zapis sesji

Dokument do przeglądu przez audytora zewnętrznego. Zawiera: co zmierzono,
co postanowiono, co już weszło do kodu i co zostaje otwarte. Liczby pochodzą
z produkcyjnej księgi (`typy_log`, 3471 rekordów) i z dry-runów na żywych
danych — nie z testów.

---

## 0. Punkt wyjścia — stan produktu

Właściciel wrócił po dwóch dniach nieobecności. Pomiar zastanego stanu:

**Infrastruktura zdrowa.** Awarie cyklu skończyły się 09.08 rano; od tego czasu
112 przebiegów bez błędu. Betclic: 48 udanych z rzędu. Problemem są wyłącznie
przebiegi anulowane (23 w oknie) — skutek długiego cyklu i `concurrency`.

**Skuteczność (epoka ligowa od 21.07, typy widoczne na stronie):**

```
razem widoczne     n=835   trafienia 57,0%   deklaracja 68,9%   ROI brutto −6,4%
główny model       n=748   trafienia 59,5%   deklaracja 70,8%   ROI brutto −4,0%
drabinki           n= 87   trafienia 35,6%   deklaracja 52,4%   ROI brutto −27,0%
```

*(Uwaga metodologiczna: we wcześniejszym briefie te trzy liczby były podane jako
jedna populacja — błędnie. 59,4%/70,9% pochodziło z okna 09–11.08, nie z n=835.)*

**Jakość prognozy kontra sam kurs** (Brier, 2438 rozliczeń, niżej = lepiej):

```
RAZEM   model 0,2304   z kursu 0,2083   — kurs lepszy w 10 rynkach na 10
```

**Stan strumieni:** zakładka zawodnicza („wysokie szanse") bez typu od 05.08.
Drabinki: 0 świeżych kart, 3 wznowione. Lista: 117 typów, 93% „poniżej",
62% gole drużyny, 103 ze 117 to wznowienia, 44 starsze niż dwa dni.

**Kupony:** długoterminowe 50 kuponów / 5 wygranych / −61,6%; „value" 10/0/−100%;
dzienne pozornie +80%, ale cały plus to jeden dzień (30.07) i jeden kupon
(23.07) — bez nich −26,7 j. Log rotuje po 21 dniach zachowując wygrane, więc
bilans jest z założenia zawyżony (selekcja przeżywalności).

---

## 1. Trzy usterki znalezione w trakcie sesji

### ① Historia w opisach sięgała pięciu lat wstecz

**Diagnoza pierwotna była błędna i została skorygowana.** `counts.fit_posterior`
waży mecze wykładniczo (`w = exp(−dni/180)`), więc mecz sprzed czterech lat wnosi
do prognozy 0,03% — archiwum nigdy jej nie psuło.

Prawdziwy problem: `tt.counts[:20]` brało dwadzieścia ostatnich **rekordów**,
nie meczów. Do prognozy to nie wchodziło, ale wchodziło do wszystkiego, co czyta
człowiek: średniej w uzasadnieniu, „ostatnich meczów" na karcie, kontroli bazy.
Zmierzone: Bolívar miał w próbie rzuty rożne z 2020 roku, Raków gole od 2022;
186 z ~960 meczów historii goli starszych niż 400 dni.

Drugi, poważniejszy problem tej samej rodziny: **kiedy własnej historii brakuje,
model podstawia średnią rozgrywek i publikuje to jako prognozę drużyny.**

```
drużyna              efektywna próba (ESS)   udział średniej ligi w prognozie
Boca Juniors                1,97                        67%
Bolívar                     2,68                        60%
São Paulo                   3,47                        54%
mediana (48 drużyn)        10,3                         28%
```

`counts.MIN_EFFECTIVE_MATCHES = 4.0` istnieje w kodzie od początku
i **nigdzie nie jest używany**.

### ② Drabinki karane trzy razy za tę samą niepewność

`p_baz = _wilson_low(traf, z)` → `× korekta kontekstu` → `× korekta strumienia
(−0,40 logit)` → próg 0,25.

**Korekta strumienia była zmierzona na pierwszych szczeblach** (bo tylko one
trafiały na stronę i się rozliczały), a stosuje się do drugich.

*Korekta wcześniejszego oszacowania:* `WILSON_K = 0,674`, nie 1,96 — więc 5/8
daje 0,506, a nie 0,33 jak wstępnie podano. Przy kontekście 1,0 taki szczebel
wychodzi na 0,407 i **przechodzi**; wypada dopiero przy kontekście ~0,55.
Główną karą jest korekta strumienia i mnożnik kontekstu, nie Wilson.

Liczniki z dry-runu:
```
Drabinki — kandydaci odrzuceni: slabe_pokrycie=54,
  jednoszczeblowa_brak_kolejnej_linii=36, za_malo_minut=29,
  rzadko_w_pierwszym_skladzie=29, kurs_ponizej_progu=20 ... (przeszło: 0)
Gdzie ginie drugi szczebel: start_pominiety_przez_cene=438,
  nastepnik_ponizej_progu_szansy=320, nastepnik_ucialy_sufit_linii=65
Szansa drugiego szczebla: 00-10%=239, 10-20%=67, 20-25%=14,
  25-30%=12, 30-40%=6, 40%+=1
```

`start_pominiety_przez_cene=438` to **nie** jest ubytek — to normalne
przewijanie do pierwszej linii z ceną ≥ `MIN_KURS_PIERWSZEGO`. Realny killer
to `nastepnik_ponizej_progu_szansy=320`.

### ③ Składy pobierane dla nieistniejącego turnieju

`rotowire.py` odpytuje `league=WOC` — mistrzostwa świata, zakończone 19.07.
Trzy tygodnie pytania o turniej, którego nie ma.

```
Składy: pełne XI dla 13 z 307 sparowanych meczów (0 potwierdzonych; sofascore: 13)
Rotowire: przewidywane składy 0 drużyn
Poza znanym składem: 199 par (mecz, zawodnik) — typy i karty nie powstają
```

To jest bezpośrednia przyczyna martwych drabinek i pustej zakładki zawodniczej.

**Wniosek szerszy niż sama literówka: brakuje kontroli zdrowia źródeł.**
Źródło dające zero przez trzy tygodnie nie wywołało żadnego alarmu.

---

## 2. ⚑ Znalezisko główne: kalibracja miała odwrócony znak

Wskazane przez audyt zewnętrzny, zweryfikowane niezależnie na 1583
rozliczeniach epoki ligowej.

**Mechanizm.** `_bias_logit` uczy się na `r["p_model"]` — czyli na `p`
WYBRANEGO ZAKŁADU; dla „poniżej" to `p_under`. Wynikowa delta jest nakładana
na `p_over`: `apply_bias(bias, pred.p_over(linia))`. Ponieważ 89–97% typów
drużynowych to „poniżej", korekta uczyła się po jednej stronie skali
i lądowała po przeciwnej.

```
rynek            n    % poniżej   delta OBECNA   delta poprawna   znak
team_corners   554      93%         −0,904          +0,909      ODWROTNY
team_goals     485      89%         −0,607          +0,360      ODWROTNY
match_corners  150      47%         −0,519          +0,257      ODWROTNY
team_cards     121      97%         −0,552          +0,579      ODWROTNY
team_sot        97      96%         −0,336          +0,241      ODWROTNY
team_shots      74      82%         −0,831          +0,844      ODWROTNY
team_fouls      33      91%         −0,499          +0,177      ODWROTNY
match_cards     30      70%         −0,436          −0,393      zgodny
```

**Skutek na największym rynku** (team_corners, typ „poniżej" z p = 0,75):

```
obecny kod   podnosi do 0,881   (+13,1 pp)
poprawnie    ściąga  do 0,547   (−20,3 pp)
fakt na rynku: deklarujemy 76,2%, trafiamy 60,8%
```

Warstwa lecząca przeszacowanie **pogłębiała je o 13 punktów procentowych**.

To tłumaczy: rosnącą lukę mimo dziewięciu warstw uczenia (−10,2 → −12,4 pp),
przegrywanie z kursem we wszystkich rynkach, oraz dodatnią deltę
`szansa_pokazywana` dla drużyn (+0,104) — ta warstwa kompensowała bałagan
piętro niżej.

`_p_over_rekordu` (dodane 31.07) naprawia orientację **przy wyborze przedziału**,
ale nie przy uczeniu delty. Ten sam błąd był już raz zauważony i załatany
w jednym z dwóch miejsc.

---

## 3. Decyzje właściciela

### Kierunek produktu

- **Chce OBA**: typy pewne (trafiające) ORAZ wyszukane okazje z wyższymi kursami.
- **Struktura zakładek zostaje**: zawodnicy (wysoka szansa + drabinki),
  drużyny (wysoka szansa + value).
- **Cel nadrzędny**: model ma być samodzielny analitycznie, nie przepisywać
  kursu. Kurs służy do oceny opłacalności i szukania błędów rynku, nie do
  liczenia prognozy.

### Zasady, które obowiązują

1. **Nic nie blokujemy.** Żadnych czarnych list rynków, stron ani pasm kursu.
   Jeśli wycinek wypada źle — przyczyną jest model, nie wycinek. Kwarantanny
   traktujemy jak przyznanie się do porażki.
2. **Horyzont publikacji zostaje.** To, że typy odległe wypadają gorzej, jest
   objawem błędu modelu, nie argumentem za skróceniem horyzontu.
3. **Odrzucone: „nie zdejmować rynków przez rozjazd deklaracji"** — kontrola
   „czy bijemy cenę" ma być miernikiem, nie bramą.
4. **Odrzucone: trafienia zamiast ROI na wierzchu strony** — zostaje jak jest.
5. **Zaakceptowane: dowód historyczny na karcie** zamiast żargonu
   („nie przekroczyła tej linii w 9 z 10 meczów" zamiast „przewaga +9 pp").
6. **Zaakceptowane: pusta zakładka zostaje pusta**, nie ukrywamy jej.
7. **Zaakceptowane: nie pokazujemy przy sprzedaży tego, czego nie dowozimy.**
8. **Zaakceptowane: koniec z tym samym legiem w wielu kuponach naraz**
   (dziś jeden zakład siedzi w 4 z 5 kuponów).

### Lista dnia — nowa koncepcja (do wdrożenia)

Limit 15–20 typów na dzień, **lista zamrażana** i niezmienna w ciągu dnia:
żadnych nowych typów po domknięciu, żadnego znikania. Dopuszczalna jedyna
zmiana: adnotacja o ruchu ceny. Warunek wstępny: podaż musi urosnąć (dziś
wybieramy 118 ze 137 kandydatów, czyli praktycznie nie wybieramy).

### Drabinki — routing zamiast progu (do wdrożenia)

```
pierwszy szczebel < 1,45 I drugi < 2,20   →  to nie drabinka, to tani pewniak
pierwszy ≥ 1,45                            →  drabinka
pierwszy 1,20–1,45, ale drugi ≥ 2,20
    przy pokryciu drugiego ≥ 50%           →  drabinka (najciekawszy typ karty)
```

---

## 4. Wdrożenie V2 — naprawa znaku

**Wariant przyjęty: A+** — krótki replay offline, natychmiastowa publikacja V2,
V1 wyłącznie jako cień wewnętrzny. Wariant „równoległy pomiar przez 3–4 dni"
odrzucony: nie da wiarygodnej próby, a dopisze rekordy ze znanym błędem.

### Co weszło do kodu

**Naprawa objęła cztery miejsca, nie jedno** (`_bias_logit` celowo nietknięty,
bo system ma dwie różne semantyki):

| miejsce | uczy się na | ląduje na | zmiana |
|---|---|---|---|
| `compute_bias_full` (rodzina/rynek/biny) | p typu → **p_over** | p_over | naprawione |
| `korekta_strumienia` + `_biny_korekty` | p typu → **p_over** | p_over | naprawione |
| `kupony.urealnij_leg_wg_strony` | p lega → **p_over** | p lega | naprawione |
| `szansa_pokazywana` | p typu | p typu | **nietknięte** |

Kupony miały drugi wariant tego samego błędu: `delta_dla_p` wybierał
**przedział** po `p` lega, a przedziały są wyznaczone na `p_over`.

**Transformacja jest tożsamością dla strumieni w całości „powyżej"**
(zawodnicy, drabinki) — potwierdzone na danych: 568 rozliczonych typów
zawodniczych, wszystkie „powyżej", zero rynków ze zmienioną deltą.

**Cap zsymetryzowany**: `BIAS_CAP_LOGIT` z (−0,80; +0,40) na (−0,80; +0,80).
Asymetria była pozostałością po czasach, gdy każda delta szła w dół. Po
naprawie cztery rynki siedziały sztucznie na +0,400 przy pomiarze +0,909,
+0,844, +0,579. Delt na capie: 10 → 19 → **8 po symetryzacji**.

**Wersje podbite**: `WERSJA_MODELU` i `WERSJA_KALIBRACJI` na
`2026-08-11-orientacja-over`. Epoka produktu zostaje `liga` — zmienił się
rachunek, nie zakres rozgrywek.

### Trzy warunki wdrożenia (wszystkie spełnione)

1. **Wznowienia między wersjami zabronione.** Typ policzony poprzednią
   kalibracją nie wraca na listę rekomendacji — zostaje w rejestrze i księdze,
   rozlicza się jako V1. Reguła działa na obu ścieżkach wznawiania (rejestr
   publikacji i księga rozliczeń). Stempel `wersje` trafia teraz także do
   rejestru; dotąd nakładało go dopiero `rozliczanie._dopisz_nowe`.
2. **Stempel `kal_rynek`** — delta kalibracji rynku faktycznie użyta dla typu,
   zapisywana od pierwszego rekordu V2. Razem z `kal_strumien` daje pełny
   rachunek tego, co nałożono na surowe `p_over`.
3. **Mapa kalibracji zamrożona** w `pipeline/footstats/kalibracja_zamrozona.json`,
   flaga `KALIBRACJA_ZAMROZONA`. Cykl ją czyta, ale nie przelicza. Plik z innej
   wersji jest ignorowany.

### Wyniki replaya (zamrożona migawka księgi)

```
korekta strumienia
  druzyny     −0,360  →  +0,019      (regulator nie ma już czego poprawiać)
  pewniaki    −0,282  →  −0,282
  drabinki    −0,400  →  −0,400

kalibracja per rynek (globalna)
  team_corners −0,800 → +0,800      team_goals  −0,642 → +0,466
  team_shots   −0,800 → +0,800      team_sot    −0,342 → +0,269
  team_cards   −0,602 → +0,621      team_fouls  −0,439 → +0,109
  match_corners −0,539 → +0,216     match_cards −0,433 → −0,347
  zawodnicze (shots/sot/tackles/fouls_*) — bez zmian
```

`team_goals` ma w trzecim przedziale −0,26 przy globalnej +0,466 — czyli
w jednym paśmie szansy model faktycznie **niedoszacowuje**. Przy jednej
korekcie na cały strumień było to niewidoczne.

**Wpływ na typy** (dry-run, n=121→133):

```
rynek          strona     n   V1 śr p   V2 śr p   mediana Δ   max |Δ|
team_goals     poniżej   73     89,2%     60,4%    −24,1 pp   48,9 pp
team_corners   poniżej    8     88,9%     50,2%    −37,6 pp   49,4 pp
team_cards     poniżej   12     88,8%     58,2%    −31,4 pp   36,8 pp
match_corners  powyżej    4     78,3%     87,8%     +7,9 pp   17,5 pp
RAZEM: mediana −24,1 pp; w dół 112, w górę 9
```

Spadek **nie jest uniwersalny** — 9 typów rośnie, wszystkie po stronie „powyżej".

**Niezmienniki:** `p_over + p_under = 1` po korekcie — odchylenie 0,00e+00.

**Efekt na bramach** (dry-run V2 kontra V1):

```
                        V1     V2
legi w puli            156    152
kandydaci na liście    137    210      (+73)
lista publikowana      119    133      (+14)

rozjazd_z_rynkiem      332 →  135      (−197)
wartosc_ujemna         182 →  425      (+243)
```

Lista **urosła**, nie schudła. Nasza liczba jest bliżej rynku, więc brama
„rozjazd" przestaje kosić; typy wypadają teraz z powodu, który rozumiemy.

**Czego naprawa nie ukryła:** 112 ze 133 typów ma ujemną wartość po podatku
(V1: 35 ze 118), mediana EV netto −5,1% wobec +3,1%. To nie regresja — to
prawda maskowana dotąd przez odwrócony znak.

---

## 5. Zmiany wdrożone wcześniej tego dnia (przed naprawą znaku)

**Sufit wieku historii drużynowej: 18 miesięcy.** Maska działa na indeksach,
nie na prefiksie — sortowanie `recentGames` z feedu `fetch_team_trends` nie
jest gwarantowane naszym kodem (dziś trzyma się w 86 na 86 seriach, ale to
obietnica cudzego API). Jedna maska obsługuje likelihood, średnią opisową,
`kal_tau` i historię na karcie.

Wynik: mecze w historii kart 1455 → 1179, starsze niż 18 miesięcy 253 → 0,
najstarszy 5,8 lat → 1,5 roku. Koszt: 9 legów na 165.

**Stempel `ess` i `udzial_priora`** przy każdym typie drużynowym — na karcie
i w księdze. Świadomie stempel, nie brama: dopiero rozliczenia pokażą, czy
typy stojące na średniej ligi wypadają gorzej.

**Nowa linia w logu cyklu**: mediana efektywnej próby i liczba legów poniżej
progu (dziś: mediana 8,6; 28 ze 152 poniżej 4).

**Złapany przy okazji drugi błąd tej samej rodziny:** stempel liczył się
poprawnie, ale nie docierał na stronę — `rec_pewniaka` to biała lista pól,
a co nie jest tam wymienione jawnie, ginie w drodze z puli do publikacji
(ta sama pułapka gubiła wcześniej `kal_tau`).

---

## 6. Otwarte — do rozstrzygnięcia

### ⚑ Regulator `compute_bias_full` nie odejmuje własnej poprzedniej delty

Uczy się na `p_model` zamrożonym w księdze, a to `p` **już zawiera** kalibrację
z chwili publikacji — w odróżnieniu od `korekta_strumienia`, gdzie `_p_surowe`
tę deltę zdejmuje. Stempla `kal_rynek` do dziś nie było, więc nie dało się jej
odjąć nawet chcąc.

Objaw: przed naprawą znaku wszystkie duże rynki drużynowe siedziały **dokładnie
na dolnym capie** (team_corners −0,800, team_shots −0,800). Regulator piął się
do sufitu, bo mierzył błąd resztkowy po własnej korekcie i publikował go jako
korektę pełną.

Obejście na dziś: mapa zamrożona. **Docelowo wymaga przebudowy pętli** —
i to jest następna rzecz do zrobienia po składach.

### Pozostałe, w kolejności

1. **Składy** (③) — Sofascore jako główne źródło, 365Scores jako drugie,
   Rotowire z poprawnymi kodami lig, skład zastępczy z rotacji minut,
   monitor zdrowia źródeł z twardym progiem na cykl.
2. **Drabinki** (②) — zdjąć korektę strumienia z drugiego szczebla, Wilson
   tylko przy krótkiej próbie, pokrycie przed procentem, routing z §3.
3. **Dane** — budżet historii per rynek (dziś kartki i faule mają komplet,
   gole 18 ze 160 przy 62% udziale w liście), priorytet po terminarzu, pamięć
   między cyklami (zwolni 60–70% budżetu), backoff na 429, cache negatywny.
4. **Zakres drużynowy z danych, nie z listy lig** — dziś 94 z 307 meczów.
   Kryterium: ESS ≥ 5 w danym rynku.
5. **Widełki kursu jako routing, nie brama** — `kurs_poza_widelkami` to 909
   odrzuceń na cykl, największe pojedyncze cięcie.
6. **Kalibracja per (rynek, strona, liga)** — dziś „rożne poniżej" ma jedną
   wagę dla Brasileirão i Allsvenskan.
7. **RLS** — osobne wdrożenie. Produkcja zachowuje się tak, jakby 0004 była
   aktywna (anon dostaje dokładnie 14 kluczy z allowlisty), więc **nie wklejać
   jej ponownie w ciemno**. Problem jest na poziomie pól: `meta` i `typy_wyniki`
   idą w całości, a RLS nie filtruje wnętrza JSONB. Naprawa: allowlistowe
   `meta_public` / `typy_wyniki_public`, przełączenie frontendu, dopiero potem
   odebranie anonowi surowych kluczy. Potwierdzone odczytem: anon pobiera
   `typy_wyniki` (1,58 MB) z `diagnostyka`, `raport_uczenia`, `przewaga_pasm`;
   `typy_log` jest zamknięta.
8. **Endpoint `kupon-pomin`** nie sprawdza roli i ufa wartościom z przeglądarki.
9. **`TERMIN_BRAK_DANYCH_S` = 7 dni**, a dokumentacja w tym samym pliku mówi
   o 48 godzinach.
10. **Naddyspersja** — rożne (1,55) i strzały (1,88) są nad-dyspersyjne, ale
    gole (0,94) i kartki (0,86) **pod**-dyspersyjne. Jedna zmiana rozkładu na
    wszystkie rynki byłaby błędem.

---

## 7. Uwagi metodologiczne do zapamiętania

**Dwie diagnozy z tej sesji nie wytrzymały weryfikacji i obie przesadzały
w tę samą stronę:**

- „model liczy średnią z pięciu lat" — nieprawda co do prognozy, wagi
  wykładnicze ją chroniły; prawda tylko co do opisów,
- „Wilson ścina 5/8 do 33%" — nieprawda, `WILSON_K = 0,674` daje 0,506.

Wniosek praktyczny: **każdą liczbę o modelu weryfikować w kodzie i na danych
przed wyciąganiem wniosków**, nawet gdy mechanizm wygląda oczywiście.

**Ocena V2 dopiero po ~100 sparowanych rozliczeniach** (min. 30 „powyżej"
i 30 „poniżej"), przez paired Brier / log-loss. Nie po ROI z kilku dni.
Wycofanie tylko przy błędzie technicznym — wtedy neutralna korekta albo
czasowe zatrzymanie ścieżki, nigdy powrót do znanego złego znaku.

**Stan testów:** 943 zielone, w tym 11 nowych opisujących orientację
kalibracji (znak dla obu stron, tożsamość dla strumieni „powyżej", zgodność
delty przy zamianie opisu zakładu, suma stron = 1, odwracalność stempla,
zakaz wznawiania między wersjami).
