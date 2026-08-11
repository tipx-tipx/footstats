# Audyt techniczny modelu predykcyjnego FootStats

## Kim jesteś w tym zadaniu

Jesteś audytorem technicznym z doświadczeniem w modelach probabilistycznych,
inżynierii danych i systemach produkcyjnych. Masz przejrzeć cały projekt i
znaleźć to, czego jego autorzy nie widzą — błędy metodologiczne, martwy kod,
sprzeczne mechanizmy, przecieki danych, luki w pomiarze. Nie masz zgadywać,
co autorzy chcieli zrobić: masz sprawdzić, co kod robi naprawdę.

## Czym jest ten produkt

FootStats to serwis typerski dla piłki nożnej. Silnik analityczny liczy
prawdopodobieństwa zdarzeń w nadchodzących meczach (gole drużyny, rzuty rożne,
kartki, strzały zawodnika, faule itd.), porównuje je z kursami bukmacherów
i publikuje typy na stronie internetowej.

Docelowy produkt ma trzy sekcje:

1. **„Duża szansa"** — typy o wysokiej trafialności, kursy ~1,15–1,60.
   Obietnica wobec klienta: „historia mówi jednoznacznie".
2. **„Wyszukane okazje"** — typy z kursami 1,80+, gdzie nasza liczba jest
   wyraźnie wyższa niż to, co wynika z ceny. Obietnica: „nie trafi za każdym
   razem, ale cena jest za wysoka".
3. **„Drabinki"** — karty pojedynczych zawodników z kilkoma szczeblami linii
   tego samego rynku (np. „1+ strzał @1,55 / 2+ strzały @2,60"), budowane
   na historii występów zawodnika.

Serwis ma być sprzedawany klientom, więc liczby pokazywane na stronie muszą
się bronić w konfrontacji z realnymi wynikami.

## Do czego dążę — cel, przez pryzmat którego oceniaj wszystko

**Chcę, żeby model był samodzielny analitycznie.** Dziś podejrzewam, że nasza
prognoza jest w praktyce przeskalowanym kursem bukmachera: bierzemy cenę,
dokładamy kilka mnożników i wychodzi coś, co z ceną koreluje, ale nie wnosi
ponad nią żadnej informacji. Chcę modelu, który patrzy na dane meczowe
(historia drużyny/zawodnika, forma, rywal, sędzia, tempo, kontekst) i wyciąga
wniosek NIEZALEŻNIE od tego, co wycenił bukmacher. Kurs ma służyć do dwóch
rzeczy: (a) sprawdzenia, czy zakład jest opłacalny, (b) znalezienia okazji,
gdzie rynek się myli. Nie ma być źródłem naszej prognozy.

**Chcę trafiać.** Produkt, który obiecuje 74% i trafia 62%, jest niesprzedawalny.
Priorytetem jest zgodność deklarowanej szansy z rzeczywistością.

**Chcę pełnego pokrycia.** Dziś na mecz wychodzi mediana 2 typy, a większość
meczów nie dostaje żadnego. Chcę, żeby model umiał policzyć wszystkie mecze,
dla których mamy dane, i wystawić na każdym tyle typów, ile faktycznie się
obroni analitycznie.

## Zasady, których audyt ma się trzymać

Właściciel projektu podjął już te decyzje — nie proponuj ich odwrócenia,
chyba że masz twardy dowód w danych, że są szkodliwe (wtedy pokaż dowód):

- **Nie blokujemy rynków, stron linii ani pasm kursu.** Jeśli jakiś wycinek
  wypada źle, przyczyną jest model, a nie to, że ten wycinek jest zły.
  Naprawiamy liczenie, nie wycinamy materiału. Kwarantanny i czarne listy są
  ostatecznością i traktujemy je jako przyznanie się do porażki modelu.
- **Horyzont publikacji zostaje** — typy mogą być wystawiane kilka dni przed
  meczem. To, że dalsze typy wypadają gorzej, jest objawem błędu modelu,
  a nie argumentem za skróceniem horyzontu.
- **Rozliczenia są nieodwracalne.** Rozliczony rekord jest zamrożony, więc
  błąd w rozliczaniu zostaje w danych na zawsze. Każda zmiana w module
  rozliczania wymaga pełnego zestawu testów przed wdrożeniem.
- **Cała produkcja działa w chmurze** (GitHub Actions + Supabase + Vercel).
  Nie proponuj rozwiązań wymagających stale włączonego komputera.

## Architektura

```
pipeline/                       Python 3.12, cały silnik
  footstats/
    jobs/
      cycle.py                  orkiestrator crona (GitHub Actions)
      build_wc_fast.py          GŁÓWNY SILNIK — ~7500 linii, liczy wszystkie typy
      build_league.py           wejście trybu ligowego
      radar.py                  drabinki (karty zawodników)
      rozliczanie.py            księga typów, rozliczenia, warstwy kalibracji
      kalibracja_tau.py         historia predykcji rynków drużynowych
      push_supabase.py          wypchnięcie wyników do bazy
      betclic_oferty.py         drugi bukmacher, osobny job
    model/
      betting.py                progi publikacji, widełki kursu, EV, ekrany
      counts.py                 rozkłady liczby zdarzeń
      matchup.py                mnożniki na styl rywala
      context.py, tempo.py, cards.py, koncesje.py, styl.py, minutes.py
      profil_druzyn.py          profil rywala z pomiaru
      kupony.py                 składanie kuponów wielozakładowych
      kontekst_drabinki.py      mnożniki kontekstu dla drabinek
    sources/
      statshub.py               główne źródło statystyk i historii
      superbet.py               kursy (główny bukmacher)
      betclic.py                kursy (drugi bukmacher, gRPC-Web)
      scores365.py              statystyki meczowe, bank stylu, rozliczenia
      sofascore.py              składy, statystyki
      rotowire.py               przewidywane składy
      eloratings.py, sts.py
    supa.py                     dostęp do Supabase (app_data: klucz -> JSONB)
    store.py                    lokalny magazyn JSONL
  tests/                        ~930 testów pytest
web/                            Next.js 16 + React 19 + Tailwind 4
  src/app/                      strony (App Router)
  src/components/               komponenty UI
  src/lib/                      typy, formatowanie, okrajanie danych dla klienta
.github/workflows/              cron: cycle.yml, rozlicz.yml, betclic.yml, testy.yml
docs/                           dokumentacja pomiarów i decyzji
```

Dane produkcyjne żyją w Supabase w tabeli `app_data` (klucz → JSONB).
Najważniejsze klucze:
- `typy_log` — księga wszystkich typów z zamrożoną ceną i szansą z chwili
  publikacji, plus wynik po meczu (~3500 rekordów)
- `value_bets` — to, co widzi użytkownik na stronie
- `typy_wyniki` — podsumowania skuteczności, raport uczenia
- `radar` — karty drabinek
- `kupony`, `kupony_log`, `legi_pool` — kupony wielozakładowe
- `meta` — stan cyklu, kwarantanny, warstwy uczenia
- `trend_lib`, `styl_bank_liga`, `druzyny_profil` — banki danych historycznych

Uruchomienie pełnego cyklu lokalnie na żywych danych, bez zapisu do produkcji
(dry-run, ~30–45 minut, wymaga `pipeline/.env` z kluczami Supabase):

```
cd pipeline
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python -m footstats.jobs.build_league
```

Dumpy dry-runu lądują w `web/src/data/demo/liga_dryrun/`.
Testy: `cd pipeline && python -m pytest` (~930 testów, ~45 s).

## Stan faktyczny — liczby, które zmierzyłem przed audytem

**Zweryfikuj je samodzielnie. Jeśli któraś jest błędna, to samo w sobie jest
znaleziskiem** (znaczy, że pomiar w projekcie kłamie).

Skuteczność (epoka ligowa, od 21.07.2026, typy widoczne na stronie):
```
835 rozstrzygniętych typów
trafienia            59,4%
deklarowana szansa   70,9%   (na stronie po korektach: ~74%)
zwrot z zakładu      -5,1%
```

Jakość prognozy — nasza liczba kontra liczba wyprost z kursu (Brier, niżej=lepiej):
```
rynek              n     model     z kursu   kto lepszy
match_corners     150    0,1876    0,1840    kurs
shots             143    0,2472    0,2379    kurs
team_sot          126    0,2286    0,2192    kurs
team_goals        740    0,2217    0,2050    kurs
team_cards        153    0,2295    0,2106    kurs
team_shots         92    0,2758    0,2440    kurs
team_corners      865    0,2417    0,2061    kurs
RAZEM            2438    0,2304    0,2083    kurs (0 z 10 rynków dla nas)
```

Dane wejściowe (z ostatniego dry-runu):
```
Składy: pełne XI dla 13 z 307 sparowanych meczów (0 potwierdzonych)
Rotowire: przewidywane składy 0 drużyn
Rynki drużynowe: 94/307 meczów w zakresie
Trendy z historii: team_goals=18, team_corners=53 (na 160 drużyn, budżet wyczerpany)
Historia drużyn sięga 5 lat wstecz (Bolívar: rożne z 2020, Raków: gole od 2022)
Drabinki: kandydaci odrzuceni ... (przeszło: 0), wznowiono 3 stare karty
Odrzucenia rynków drużynowych: kurs_poza_widelkami=1029, szansa_za_niska=719,
  brak_kursu=645, rozjazd_z_rynkiem=373, wartosc_ujemna=206
```

Podejrzenia, które już mam (potwierdź, obal albo pogłęb):
1. Średnia historyczna liczona z 20 ostatnich *rekordów* bez filtra daty
   (`build_wc_fast.py`, ~5291 i ~5415), a brama świeżości wymaga tylko
   2 meczów w 120 dniach (`MIN_MECZE_W_OKNIE = 2`).
2. Szansa szczebla drabinki ścinana trzy razy z rzędu: dolna granica Wilsona,
   mnożnik kontekstu i korekta strumienia — przez co zawodnik z pokryciem
   5/8 (62,5%) dostaje ~22% i wypada na progu 25% (`radar.py`, ~900).
   Korekta strumienia była zmierzona na pierwszych szczeblach, a stosuje się
   do drugich.
3. `rotowire.py` odpytuje `league=WOC` (mistrzostwa świata), które skończyły
   się 19.07.2026.
4. Kalibracja liczona globalnie na strumień, mimo że błędy poszczególnych
   rynków mają przeciwne znaki.

## Co masz zbadać

Dla każdego obszaru: sprawdź kod, sprawdź dane produkcyjne tam, gdzie się da,
i odpowiedz na pytanie „czy to działa tak, jak twierdzi dokumentacja".

### 1. Poprawność statystyczna
- Czy rozkłady użyte do liczenia liczby zdarzeń są właściwe dla tych zjawisk
  (Poisson vs ujemny dwumianowy — nadmierna dyspersja rzutów rożnych i strzałów)?
- Czy przedziały ufności i dolne granice (Wilson) są stosowane spójnie i we
  właściwych miejscach? Gdzie ostrożność jest zaletą, a gdzie systematycznym
  zaniżeniem?
- Czy mnożniki kontekstu (rywal, sędzia, dom/wyjazd, tempo, styl) są niezależne,
  czy liczą to samo kilka razy? Ile wynosi ich iloczyn w praktyce i czy
  ograniczenia (`cap`) nie maskują błędu?
- Czy prawdopodobieństwa obu stron tej samej linii sumują się do jedności?
- Czy korelacja między zdarzeniami w jednym meczu jest uwzględniona tam,
  gdzie ma znaczenie (kupony, dwa typy z tego samego spotkania)?

### 2. Przeciek informacji z kursu do prognozy
To jest najważniejszy punkt audytu. **Prześledź każdą ścieżkę, którą cena
bukmachera wpływa na naszą liczbę.** Szukaj:
- miejsc, gdzie kurs wchodzi do liczenia prawdopodobieństwa (bezpośrednio
  albo przez wybór linii, filtr kandydatów, mnożnik),
- mechanizmu „wagi" mieszającej naszą liczbę z ceną — gdzie jest stosowany
  i czy jego wynik nie wraca potem do kalibracji jako „nasza" prognoza,
- selekcji, która patrzy na kurs przed policzeniem szansy.
Wynik: mapa wszystkich takich miejsc plus ocena, ile z naszej prognozy jest
faktycznie nasze.

### 3. Jakość i kompletność danych wejściowych
- Świeżość historii: gdzie i jak filtrowany jest wiek meczów, gdzie brakuje filtra
- Kompletność: dlaczego dwie trzecie meczów nie ma danych, gdzie kończą się
  budżety zapytań, czy podział budżetów odpowiada temu, z czego typujemy
- Parowanie: mecze między źródłami, drużyny między bankami, zawodnicy między
  bukmacherem a statystykami — gdzie gubimy rekordy na niedopasowaniu nazw
- Buforowanie: co pobieramy wielokrotnie bez potrzeby
- Awarie źródeł: które źródła milczą i czy system to zauważa, czy przechodzi
  do przybliżenia bez ostrzeżenia

### 4. Warstwy uczenia
System ma dziewięć warstw korygujących (`meta.uczenie_stan`). Zbadaj:
- czy się nie kanibalizują — czy dwie warstwy nie korygują tego samego błędu
- czy kolejność ich nakładania jest poprawna
- czy sygnał, na którym się uczą, nie jest skażony selekcją (uczenie na typach,
  które przeszły bramę, o tym, jak ustawić bramę)
- czy zabezpieczenia przed oscylacją regulatora działają
- czy warstwa, która „padła", jest wykrywana, czy cicho przestaje działać

### 5. Selekcja i publikacja
- Kolejność bram i to, czy wcześniejsza brama nie zjada pomiaru późniejszej
- Czy typ odrzucony jest mierzony (czy wiemy, jak wypadłby, gdyby wszedł)
- Wznowienia: typ raz opublikowany wraca na listę — czy z aktualną ceną
  i czy przechodzi dzisiejsze progi
- Limity listy (na dzień, mecz, rynek) — czy nie wycinają lepszego materiału
  niż zostawiają
- Sortowanie: po czym ustawiamy kolejność i czy te sygnały mają wartość
  predykcyjną (podejrzenie: część z nich jest odwrócona)

### 6. Rozliczanie
- Czy wynik zdarzenia jest ustalany poprawnie dla każdego rynku (regularny
  czas gry, dogrywka, zmiany zawodników, zawodnik który nie zagrał)
- Strefy czasowe przy grupowaniu po dniach
- Typy, które nigdy się nie rozliczają — dlaczego wiszą i czy reguła
  „brak danych po 48 h → zwrot" faktycznie działa
- Czy błędne rozliczenie da się wykryć po fakcie

### 7. Drabinki
- Cały łańcuch od kandydata do karty: gdzie i ile odpada, jak liczona jest
  szansa każdego szczebla, dlaczego drugi szczebel praktycznie nigdy nie przechodzi
- Czy definicja drabinki (kilka linii tego samego rynku) jest jedyną sensowną —
  rozważ warianty (kilka rynków tego samego zawodnika)
- Zależność od składów i co się dzieje, gdy składów nie ma

### 8. Kupony
- Dobór legów, kara za korelację, urealnienie łącznej szansy
- Czy ten sam zakład nie trafia do wielu kuponów naraz
- Czy deklarowana wartość kuponu ma pokrycie w rozliczeniach

### 9. Pomiar i raportowanie
- Czy statystyki skuteczności liczą to, co twierdzą (typy widoczne na stronie
  vs typy mierzone w tle)
- Czy pomiary filtrują epoki produktu (dane z zakończonego turnieju nie
  powinny uczyć dzisiejszego modelu)
- Selekcja przeżywalności: gdzie rotujące logi zawyżają wyniki
- Czy dwa różne pomiary tej samej rzeczy w systemie dają ten sam wynik

### 10. Wydajność i niezawodność
- Cykl trwa 30–45 minut przy limicie 70; rośnie z zakresem danych. Gdzie idzie
  czas i co da się zrównoleglić lub zbuforować
- Odporność na padnięcie źródła w połowie cyklu
- Bezpieczeństwo zapisów do bazy (odczyt–modyfikacja–zapis, utrata historii)

### 11. Frontend (`web/`)
- Spójność liczb między stroną a księgą
- Czy dane przeznaczone tylko dla administratora nie trafiają do przeglądarki
  klienta (są dwa poziomy dostępu)
- Wydajność, dostępność, zachowanie na telefonie
- Czy komunikaty i etykiety mówią prawdę o tym, co system faktycznie robi

### 12. Kod
- Martwy kod, mechanizmy wyłączone flagą i nigdy nie włączone
- Sprzeczności między komentarzem a implementacją (dokumentacja w tym projekcie
  jest obszerna i miejscami nieaktualna — traktuj ją jako hipotezę, nie prawdę)
- Cicha obsługa wyjątków, która zamienia awarię w niezauważalne pogorszenie
- Pokrycie testami tam, gdzie błąd jest nieodwracalny

## Format odpowiedzi

**Część A — znaleziska.** Uporządkowane od najcięższego. Każde:
- jedno zdanie: co jest źle
- dowód: plik i linia, fragment kodu albo liczba z danych
- skutek: co to znaczy dla trafialności, pokrycia albo wiarygodności pomiaru
- naprawa: konkretnie, z oszacowaniem nakładu (godziny/dni)
- ryzyko naprawy: co może się zepsuć

**Część B — luki koncepcyjne.** Rzeczy, których w tym modelu nie ma, a powinny
być, żeby cel „samodzielna analiza zamiast przepisywania kursu" był osiągalny.
Tu chcę Twojego zdania jako kogoś z zewnątrz: jakich sygnałów nie używamy,
jakie podejście modelowe byłoby właściwsze, co robią serwisy, które to robią
dobrze.

**Część C — plan.** Kolejność prac z uzasadnieniem, co odblokowuje co.

**Czego nie chcę:** ogólników („dodać więcej testów", „rozważyć uczenie
maszynowe"), przepisywania architektury bez powodu, propozycji blokowania
rynków. Każde znalezisko ma być sprawdzalne w kodzie albo w danych.
