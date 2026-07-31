# FootStats — pełny przegląd projektu

Stan na 31 lipca 2026. Wszystkie liczby są z produkcji (Supabase), nie z przykładów.

---

## 1. Wizja produktu

**„To jest model, który typuje za mnie — i pokazuje, ile razy się pomylił."**

Po 30 sekundach użytkownik ma pomyśleć: *tu ktoś liczy, a nie zgaduje, i nie ukrywa
wpadek*. Trzy rzeczy widać od razu na pierwszym ekranie: gotowe typy na dziś, gotowy
kupon do skopiowania i licznik trafień z pełną historią, której nie da się poprawić
ręcznie.

Czym FootStats **nie** jest:
* nie jest przeglądarką statystyk (od tego jest Sofascore),
* nie jest serwisem tipsterskim (nikt tu nic nie „czuje"),
* nie jest wyrocznią — na stronie jest dosłownie napisane, że w tej chwili jesteśmy
  pod kreską.

---

## 2. Obecny stan projektu

### Co działa (produkcja, codziennie, bez udziału człowieka)

| Element | Stan |
|---|---|
| Zbieranie danych z 6 źródeł | działa, w całości z chmury |
| Model probabilistyczny (rynki zawodnicze) | działa, ale **w kwarantannie** — patrz niżej |
| Model rynków drużynowych | działa, to dziś główny produkt (98 typów na stronie) |
| Kupony (AKO) składane automatycznie | działa |
| Generator kuponów na życzenie | działa |
| Automatyczne rozliczanie typów i kuponów | działa |
| Samouczenie (kalibracja, kwarantanna, korekty) | działa |
| Strona na Vercel + logowanie | działa |
| Dwie role: admin / klient zewnętrzny | działa |

### Co jest ukończone i zamknięte
* Silnik matematyczny (Gamma-Poisson → rozkład ujemny dwumianowy) + 466 testów.
* Model minut (scenariusze: pełny mecz / zmiana / ławka / nie zagra).
* Warstwa kontekstu (rywal, sędzia, dom-wyjazd, scenariusz meczu, matchup).
* Czytniki kursów: Superbet (HTTP), STS (WebSocket), Betclic (gRPC-Web).
* Rozliczanie z trzech niezależnych źródeł wyniku + zwrot po 48 h, gdy brak danych.
* Warstwa uczenia: kalibracja logitowa per rynek, kwarantanna rynków/stron/kategorii,
  korekta strumienia, szansa pokazywana użytkownikowi.
* Drabinki (analiza zawodnika z porównaniem dwóch cenników).
* Nowe rynki: „kto więcej" i sumy meczowe (wdrożone 30 lipca).

### Co jest w trakcie
* **Przebudowa kuponów** — plik `pipeline/footstats/model/kupony.py` ma
  niescommitowane zmiany. Powód: 81 rozliczonych kuponów, 4 wygrane, ROI −56%.
  Nowe, krótsze przedziały kursu są już wpisane, brakuje podpięcia korekt per typ.
* **Zawyżone λ** — model systematycznie przewiduje za dużo zdarzeń. To jedna
  przyczyna trzyma dziś rynki zawodnicze w kwarantannie.
* **Drabinki: za mało kart** — 3–5 dziennie, powinno być kilkanaście.

### Co jest tylko pomysłem
* Korelacja między drużynami w sumach meczowych (dziś zakładamy niezależność, co
  zawyża wysokie linie).
* Suwak kursu 2–25 w generatorze ręcznym.
* Alerty (Telegram/push), panel admina, cokolwiek płatnego.
* Systemy (kupony blokowe) — **user odrzucił wprost**, nie robimy.

### Jedna liczba, która opisuje stan projektu

```
429 rozliczonych typów
trafia          58%   (250/429)
próg wyjścia na zero  60%   (przy realnym średnim kursie)
model obiecywał 71%
bilans        −49,41u  (= −494 zł przy 10 zł na typ)
CLV            +0,9%  (bierzemy kursy lepsze niż zamknięcie rynku)
```

Cała strata siedzi w typach zawodniczych; rynki drużynowe są blisko zera,
a bywały na plusie.

> ⚠️ **WDROŻONE 31 lipca: podatek od stawki.** Powyższe liczby były brutto.
> Po przeliczeniu (policzone na pełnym logu rozliczeń):
> **bilans −94,96u = −950 zł, próg wyjścia na zero 69%, brakuje ~11 pp,
> nie 2 pp.** Pełny rachunek w sekcji 4a.

### Jednostki — jedna definicja na cały projekt

Żeby nigdy nie było dwóch różnych liczb o tej samej rzeczy:

| Pojęcie | Definicja |
|---|---|
| **1 jednostka (1u)** | jedna płaska stawka na jeden typ |
| **domyślna stawka** | 10 zł (`useStawka`, zapamiętywana w przeglądarce) |
| **bilans jednostkowy** | `suma kursów typów wygranych − liczba postawionych typów` |
| **bilans w złotówkach** | `bilans jednostkowy × stawka`; dla 10 zł: −94,96u = **−950 zł** |
| **zwrot** | zawodnik nie zagrał albo brak danych po 48 h → stawka wraca w całości (razem z podatkiem), kurs 1,0 |
| **podatek** | 12% od stawki; tryb (`standard` / `bez_podatku` / `zwrot`) zapisany przy każdym typie |
| **`ev_pct`** | wartość BRUTTO — **tym decydują bramy publikacji** |
| **`ev_netto`** | wartość PO PODATKU — **to widzi użytkownik**; jedyna liczba na stronie |

Admin czyta bilans w jednostkach (porównuje okresy i produkty), klient
w złotówkach. Jedno źródło formatowania: `web/src/components/useBilans.ts`.

---

## 3. Technologie — dokładnie

**Frontend**
* Next.js **16.2.10** (App Router, React Server Components, ISR)
* React **19.2.4**, TypeScript 5
* Tailwind CSS 4 (`@tailwindcss/postcss`)
* framer-motion 12 (animacje, przejścia nawigacji)
* Zero bibliotek do wykresów — wszystkie wykresy to własne SVG
* Playwright 1.62 — wyłącznie do zrzutów ekranu i audytu mobilnego (nie do testów)

**Backend**
* Nie ma osobnego backendu. Serwerem jest Next.js na Vercelu:
  * komponenty serwerowe czytają dane wprost z Supabase (PostgREST, klucz anon),
  * dwa route handlery: `/api/login` (logowanie/wylogowanie) i `/api/kupon-pomin`
    (pominięcie/wymiana/przebudowa kuponu, zmiana profilu),
  * `proxy.ts` — bramka logowania przed całą aplikacją.

**Python**
* 3.12. Zależności — całe: `numpy`, `scipy`, `curl_cffi`, `python-dotenv`, `pytest`.
* **Nie ma** pandas, scikit-learn, PyTorch, TensorFlow, XGBoost. Świadomie.
* `curl_cffi` zamiast `requests`, bo podszywa się pod odcisk TLS Chrome — bez tego
  część źródeł odrzuca ruch.

**Baza**
* Supabase (Postgres), plan darmowy.
* W praktyce używana jest **jedna tabela**: `app_data (key text primary key,
  payload jsonb, updated_at)`. Pipeline wypycha ~14 kluczy, strona je czyta.
* Pełny znormalizowany schemat (ligi, drużyny, zawodnicy, snapshoty kursów,
  predykcje, sędziowie) leży w `supabase/migrations/0001_init.sql` i **nie jest
  używany** — czeka na moment, gdy analityka historyczna tego wymusi.
* RLS włączone: publiczny odczyt kluczem anon, zapis tylko kluczem service.

**Hosting**
* Vercel (projekt `footstats`, katalog główny `web/`), plan Hobby.
* Supabase Free.
* Koszt infrastruktury: **0 zł**.

**Autoryzacja**
* Hasło z env, bez kont i bez rejestracji.
* Po zalogowaniu ciasteczko HttpOnly `fs_sesja` = `<wygasa>.<rola>.<podpis HMAC-SHA256>`.
  Podpis liczony z obu pól, więc podmiana roli w ciasteczku unieważnia podpis.
* Dwie role: `APP_PASSWORD` → admin (pełny wgląd), `KLIENT_PASSWORD` → klient
  (sam produkt). Druga jest opcjonalna.
* Ważność sesji: 30 dni. Serwer nie pamięta niczego (brak sesji w bazie).

**API**
* Własnego publicznego API nie ma.
* Konsumujemy wewnętrzne (nieudokumentowane) endpointy: statshub, 365Scores,
  Superbet, STS (WebSocket), Betclic (gRPC-Web), Rotowire, eloratings.

**Crony**
* GitHub Actions, dwa workflow, wspólna grupa `concurrency` (nie mogą biec naraz):
  * `cycle.yml` — pełny cykl (dane → model → typy → kupony → Supabase), deklaruje
    co 15 min,
  * `rozlicz.yml` — samo rozliczanie zakończonych meczów, deklaruje co 20 min.
* **Uwaga praktyczna:** GitHub realizuje cron „best effort" — realnie odpala co
  ~1–1,5 h. Strona bywa godzinę nieświeża i to jest znany, nienaprawiony problem.
* Trzecia ścieżka: pominięcie kuponu na stronie odpala workflow od razu przez
  `workflow_dispatch` (token `GH_DISPATCH_TOKEN`), żeby nowy kupon był w ~2–3 min.

**Cache**
* Cache bundla w pamięci instancji Vercela, TTL 60 s — bez niego każdy getter
  pobierał całe ~14 MB od nowa (strona zawodników robiła to 6 razy na wejście).
* ISR: `revalidate: 60` na zapytaniu do Supabase.
* Lokalnie: cache HTTP na dysku (`pipeline/data/http_cache`) dla danych, które się
  nie zmieniają. Kursów **nigdy** nie cache'ujemy.

**Docker** — nie ma i nie jest potrzebny.

**GitHub** — tak, `tipx-tipx/footstats`, repo publiczne (dzięki temu minuty Actions
są nielimitowane). 186 commitów, gałąź `master`.

**CI/CD**
* Deploy: `git push` do `master` → Vercel buduje sam. Nie ma innej ścieżki wdrożenia.
* **CI testów NIE MA.** 466 testów pytest istnieje, ale nikt ich nie uruchamia
  automatycznie — tylko lokalnie, ręcznie. To realna dziura (patrz sekcja 19).

---

## 4. Model — jak to naprawdę liczy

### Skąd pobieramy dane i jak często

| Źródło | Co daje | Jak często |
|---|---|---|
| **statshub.com** | historia mecz po meczu każdego zawodnika, średnie rywala, przewidywane składy, kursy bukmacherów UK | co cykl (~1 h) |
| **365Scores** | mapy strzałów (strzał po strzale), statystyki drużynowe, statystyki stylu zawodnika, wyniki | co cykl |
| **Superbet** | kursy — główne źródło cen | co cykl, bez cache |
| **STS** | kursy — rynki, których nie ma Superbet (strzały niecelne, zablokowane) | na klik użytkownika |
| **Betclic** | kursy — drugi cennik, **tylko** do Drabinek | co cykl |
| **Rotowire** | przewidywane składy — drugi, niezależny głos | co cykl |
| **eloratings.net** | siła reprezentacji (ważenie próby) | raz na 3 dni |
| **Sofascore** | pełne dane meczowe | **tylko lokalnie** — blokuje IP serwerowni |

### Jakie ligi

Dwa różne zakresy, i to jest ważne rozróżnienie:

* **Statystyki zawodników — cały świat.** Nie mamy listy lig. Odkrywanie idzie
  od oferty bukmachera: jeśli Superbet kwotuje propsy na mecz, liczymy go.
* **Statystyki drużynowe — 17 wybranych rozgrywek**, bo tylko dla nich mamy
  komplet danych: top 5 lig Europy, Ekstraklasa, Liga Mistrzów / Europy /
  Konferencji (z kwalifikacjami), Argentyna, Brazylia (A i B), Sudamericana,
  Szwecja (Allsvenskan, Superettan), Norwegia, Dania.

Ameryka Południowa i Skandynawia doszły 27 lipca celowo: grają latem, czyli
dokładnie wtedy, gdy Europa ma przerwę.

### Jakie statystyki i rynki

**Zawodnicze (13 rynków):** strzały, celne strzały, strzały zza pola karnego,
celne zza pola, strzały głową, celne głową, strzały niecelne, strzały zablokowane,
faule popełnione, faule wywalczone, odbiory, przechwyty, spalone.

**Drużynowe (7 rynków):** gole, rzuty rożne, kartki, faule, strzały, celne strzały —
każdy w trzech wariantach:
* linia dla jednej drużyny („powyżej 4,5 rożnego"),
* **„kto więcej"** — porównanie dwóch drużyn, trzy wyniki z remisem,
* **suma meczowa** — obie drużyny razem.

Rynki połówkowe i minutowe świadomie pomijamy — model liczy pełny mecz.

### Jak model liczy — krok po kroku

**Krok 1. Prawdziwy poziom zawodnika (bayesowski).**
Intensywność zdarzeń na 90 minut opisujemy rozkładem Gamma. Prior bierzemy
z grupy porównawczej (pozycja × rola × liga) metodą **empirycznego Bayesa** —
zawodnik z trzema meczami jest ściągany do średniej grupy, zawodnik z trzydziestoma
prawie nie. Obserwacje wygaszamy wykładniczo w czasie (`waga = exp(−dni/180)`),
a dodatkowo ważymy siłą rywala.

**Krok 2. Rozkład liczby zdarzeń w meczu.**
Poisson z losową intensywnością Gamma daje **rozkład ujemny dwumianowy**:

```
X | λ ~ Poisson(λ · e),  λ ~ Gamma(α, β)   ⟹   X ~ NB(r=α, p=β/(β+e))
```

gdzie `e` = minuty/90 × iloczyn czynników kontekstu. Zaleta: naddyspersja
„za darmo" — im mniejsza próba, tym grubsze ogony, czyli model sam wie, że
mało wie.

**Krok 3. Minuty jako mieszanka scenariuszy.**
Nie jedna liczba minut, tylko cztery scenariusze z wagami: pełny mecz / start
i zejście / wejście z ławki / nie zagra. Po ogłoszeniu oficjalnego składu
scenariusze się upraszczają i pewność skacze.

**Krok 4. Kontekst — mnożniki, nigdy nie rządzą.**
Pięć czynników: rywal, sędzia (tylko faule i kartki), dom/wyjazd, scenariusz meczu
(z kursów 1X2 i totalu), matchup („kto na kogo gra", ~20 analogii typu „target man
kontra słaba gra głową" albo „driblujący skrzydłowy kontra słaby w 1:1 bocznik").
Każdy czynnik jest **ściągany do 1,0 przy małej próbie** i **capowany** do widełek.
Dodatkowo iloczyn wszystkich ma osobny sufit (0,60–1,80).

**Krok 5. Kursy → uczciwa cena.**
* Dwustronne kwotowanie: devig **metodą potęgową** (szukamy `k`, że
  `(1/over)^k + (1/under)^k = 1`) — lepiej niż proporcjonalny oddaje to, że
  bukmacherzy zawyżają marżę na wysokich kursach.
* Jednostronne: odejmujemy szacowaną marżę (7% dla PL, 4,5% dla konsensusu UK).
* Osobny sygnał: **samospójność siatki linii** — wszystkie linie jednego rynku
  (0,5 / 1,5 / 2,5…) opisują ten sam rozkład, więc dopasowujemy Poissona do
  pozostałych i sprawdzamy, czy któraś linia płaci wyraźnie więcej. To wyłapuje
  pomyłkę tradera we własnej ofercie buka, bez zewnętrznych kursów.

**Krok 6. Liczby, które widzi użytkownik.**

```
uczciwy kurs   = 1 / szansa modelu
przewaga (pp)  = szansa modelu − szansa z kursu po zdjęciu marży
wartość (EV%)  = (szansa modelu × kurs − 1) × 100
```

**Uwaga: ten wzór nie uwzględnia podatku od stawki — patrz sekcja 4a.**

**Pewność (0–100)** to ważona suma czterech składowych:
próba (35%), pewność minut (30%), szerokość przedziału ufności (35%),
minus kara, gdy przewaga stoi głównie na kontekście, a nie na bazie,
×0,85 gdy rynek nie ma potwierdzonej kalibracji, ×0,75 gdy zdarzenie jest rzadkie.

**Ryzyko** to osobna oś — nie „czy model wie", tylko „jak kapryśne jest samo
zdarzenie". Strzały głową to loteria nawet przy świetnym modelu.

**Ranking** sortuje po `przewaga × pewność^1,5`, celowo **nie** po EV — inaczej
longshoty wypychałyby solidne okazje.

### Czy używamy ML / regresji / Bayesa / Monte Carlo / Poissona / XGBoost / LSTM / ensemble

Uczciwa odpowiedź, punkt po punkcie:

| Technika | Używamy? |
|---|---|
| **Bayes** | **Tak, to rdzeń.** Gamma-Poisson, empiryczny Bayes, shrinkage. |
| **Poisson** | **Tak** — w rozkładzie predykcyjnym, w dopasowaniu siatki linii, w przedziałach ufności. |
| **Monte Carlo** | **Tak, w jednym miejscu** — przedział wiarygodności na szansę liczymy z 4000 losowań z posteriora. |
| **Splot rozkładów** | **Tak** — sumy meczowe i „kto więcej" liczone dokładnie, nie symulacją. |
| **Regresja** | Nie w klasycznej postaci. Kalibracja działa na skali logitowej (delta logitowa per rynek i per przedział szansy), co jest bliskie regresji logistycznej z jednym parametrem. |
| **ML „z biblioteki"** | **Nie.** Ani sklearn, ani XGBoost, ani sieci. |
| **XGBoost** | Nie. |
| **LSTM / sieci neuronowe** | Nie. |
| **Ensemble** | Nie w sensie ML. Jest coś innego: kilka niezależnych źródeł prawdy (dwa źródła składów, trzy źródła wyniku, dwa cenniki) i głosowanie między nimi. |

**Dlaczego nie ML.** Rynek player props to małe próby (10–30 meczów na zawodnika)
i silny szum. Model bayesowski daje **kalibrowane prawdopodobieństwo z uczciwym
przedziałem niepewności**, a to jest dokładnie ta liczba, której potrzebuje
zakład. Gradient boosting dałby lepsze dopasowanie punktowe i gorszą kalibrację —
a nam wolno mylić się co do wyniku, nie wolno kłamać co do pewności.

Warto dodać: mimo tego wyboru model **i tak** przeszacowuje (obiecuje 71%,
trafia 58%). To argument, że problem nie leży w klasie modelu, tylko w selekcji
i w danych.

### Czy model sam odrzuca typy

Tak, i to jest najgęstsza część systemu. Typ musi przejść **wszystkie** bramy:

1. **Szerokość przedziału ufności ≤ 0,30** — jeśli model sam nie wie, ile wynosi
   szansa, nie stawiamy.
2. **EV ≥ +1%** (rzadkie rynki: +5%).
3. **Pewność ≥ 25/100.**
4. **Kurs 1,19–6,00** (dla rynków drużynowych osobne widełki: 1,19–3,60 z progiem
   szansy).
5. **Okno zgody z rynkiem: 0 do +12 punktów procentowych.** To najciekawsza brama
   w projekcie. Pomiar na 408 rozliczonych typach pokazał zależność monotoniczną:
   ```
   poniżej ceny rynku   trafia 58%   ROI −22%
   +0 do +2 pp                81%        +7%
   +2 do +5 pp                73%        +4%
   +5 do +8 pp                69%        −7%
   +8 do +12 pp               62%        −6%
   +12 do +14 pp              62%         0%
   +14 do +18 pp              38%       −39%   ← klif
   ponad +18 pp               46%       −29%
   ```
   Im mocniej rozjeżdżamy się z bukmacherem, tym gorzej trafiamy. To klasyczna
   selekcja negatywna: buk odjeżdża od nas tam, gdzie wie coś, czego my nie wiemy
   (kontuzja, rotacja, waga meczu). Samo to okno poprawiło ROI z −13,9% na −1,3%.
6. **Kwarantanna rynków** — co cykl liczymy ROI każdego rynku w oknie kroczącym.
   Rynek, który traci, znika ze strony i wraca sam, gdy przestanie tracić.
   Histereza chroni przed migotaniem. **Dziś w kwarantannie jest sześć rynków
   zawodniczych**, dlatego zakładka Zawodnicy potrafi być pusta — to nie bug.
7. **Kwarantanna strony linii** — osobno „powyżej" i „poniżej". Najmocniejszy
   zmierzony sygnał w całym projekcie: „poniżej" ma +8%, „powyżej" −15%.
   Problem: rynki zawodnicze mają praktycznie tylko „powyżej".
8. **Kwarantanna kategorii** — po powodzie, dla którego typ trafił na listę.
9. **Zapas na obstawienie 90 minut** — nic nowego nie pojawia się później.
10. **Skład** — typ nie powstaje, jeśli wiemy, że zawodnika nie ma, albo
    spodziewamy się po nim mniej niż godziny gry.

**Typy odrzucone tuż pod progiem są mimo wszystko zapisywane i rozliczane w tle**
(poza stroną, poza statystykami, poza kalibracją). Dzięki temu za miesiąc da się
porównać ich realny wynik z przepuszczonymi i ruszyć próg **na dowodzie, a nie na
przeczucie**. Tak właśnie powstało okno zgody z rynkiem.

### Czy wszystko zapisujemy

Tak, i to jest zasada nienegocjowalna:

* Każdy opublikowany typ trafia do `typy_log` z **zamrożonym** `p_model` i kursem
  z chwili pierwszej publikacji. Rozliczony rekord jest zamrożony na zawsze —
  błąd rozliczenia zostaje w statystyce (dlatego rozliczanie ma osobne testy).
* Każdy kupon — tak samo, z podpisem zestawu typów.
* Typy, których nigdy nie pokazaliśmy (pomiarowe), rozliczają się w tle.
* Snapshot kursu zamknięcia → liczymy **CLV** (czy braliśmy kurs lepszy niż tuż
  przed meczem). Dziś: +0,9% na 364 typach.
* Zapis do Supabase idzie wyłącznie przez `get_key_ok` / `put_key_bezpiecznie` —
  jeden timeout przy odczyt-modyfikacja-zapis skasowałby całą historię.

### Jak model się uczy (cztery warstwy, wszystkie automatyczne)

1. **Kalibracja per rynek** — porównuje deklarowaną szansę z realną częstością
   i przesuwa `p` na skali logitowej, osobno w przedziałach szansy. Wchodzi od
   25 rozliczeń na rynku.
2. **Kwarantanna** — wyłącza to, co traci pieniądze (opisana wyżej).
3. **Korekta strumienia** — łapie to, czego kalibracja rynkowa nie widzi
   (osobno dla pewniaków, drużyn, drabinek). Stempel czasowy chroni regulator
   przed oscylacją.
4. **Szansa pokazywana** — po wszystkich bramach strona pokazuje liczbę już
   urealnioną, a typ, który po korekcie ma ujemną wartość, sam schodzi z listy.

Do tego mierzone z rozliczeń, nie założone: kary korelacji między typami z jednego
meczu (`ta sama drużyna 0,703`, `przeciwne 0,804`) i wagi zaufania w kuponach.

**Uczciwie o skuteczności tego uczenia:** kalibracja co cykl ściąga `p` w dół, ale
**deklaracja opublikowanych typów nie drgnęła od miesiąca** i stoi na ~71%. Powód
to efekt selekcji: korekta obniża wszystkie szanse, a brama publikacji natychmiast
wybiera nowy czub rozkładu. Z perspektywy użytkownika model mówi to samo i myli
się tak samo. To jest **główny nierozwiązany problem projektu**.

---

## 4a. Podatek od stawki — znaleziony i wdrożony 31 lipca

Do 31 lipca podatku **nie było nigdzie** — wyszukanie „podatek", „tax", „0,88"
w całym repozytorium zwracało zero trafień. Poniżej stan sprzed naprawy
i to, co zostało zrobione.

### Czego brakowało (stan sprzed 31 lipca)

| Pytanie | Odpowiedź |
|---|---|
| Czy kursy z Superbetu to zwykłe kursy brutto? | **Tak.** `sources/superbet.py` czyta pole `price` z oferty i nie przelicza go w żaden sposób. |
| Czy pipeline zakłada promocję „bez podatku"? | **Nie zakłada niczego.** Nie ma pojęcia podatku ani flagi trybu. |
| Jak liczona jest wypłata „z 10 zł robi się"? | `Math.round(kurs_łączny × 10)` — czysty iloczyn, brutto. |
| Czy historia używa faktycznych zwrotów? | **Nie.** `rozliczanie.py`: `zwrot += kurs` przy wygranej, potem `roi = zwrot − liczba_typów`. To stawka × kurs, brutto. |
| Czy próg wyjścia na zero uwzględnia podatek? | **Nie.** `SkutecznoscScena.progOplacalnosci` to dosłownie `1 / średni_kurs`. |

### Wzór, który jest, i wzór, który powinien być

```
dziś:          EV = p × kurs − 1
przy 12% od stawki:   EV = p × kurs × 0,88 − 1
```

Twój przykład się zgadza co do grosza: 92% przy kursie 1,13 to **+3,96% brutto**
i **−8,52% po podatku**. Zakład z „przewagą" staje się zakładem stratnym.

### Ile to realnie zmienia — policzone na żywych danych

**Historia (429 rozliczonych typów):**

```
                        brutto (było)    po 12% od stawki (jest)
bilans                    −49,41u              −94,96u
w złotówkach (10 zł)       −494 zł              −950 zł
próg wyjścia na zero        60,8%                 69,1%
realna trafialność           58%                   58%
brakuje do zera             2 pp                  11 pp
```

(policzone na 429 rozliczonych okazjach ze średnim kursem 1,645 —
odtworzenie zgadza się z liczbą na stronie co do grosza, więc nie jest
to szacunek)

Czyli teza „brakuje 2 punktów procentowych, to zasięg samej kalibracji" —
**upada**. Po podatku brakuje ~10 pp, a to już jest inna klasa problemu:
wymaga innej selekcji, nie dostrojenia.

**Typy wystawione dziś (138 pozycji, pobrane wprost z produkcji):**

```
stare rynki drużynowe   n=99   kursy 1,19–3,45
    średnie EV: +9,0% brutto  →  −4,1% po podatku
    typów z dodatnim EV po podatku:  19 z 99

sumy meczowe (rynek wdrożony 30 lipca)   n=39   kursy 1,04–3,05
    średnie EV: +1,7% brutto  →  −10,5% po podatku
    typów z dodatnim EV po podatku:   0 z 39
```

**Po podatku przeżywa 19 ze 138 dzisiejszych typów (14%).**

### Drugie odkrycie, przy okazji: nowe rynki omijają prawie wszystkie bramy

Przy sprawdzaniu podatku wyszła rzecz niezależna i pilniejsza.

Rynki wdrożone 30 lipca — **sumy meczowe** (`match_*`) i **„kto więcej"**
(`wiecej_*`) — przechodzą przez **jeden warunek: EV ≥ +1%**. Nie mają:

* `MIN_ODDS` / `MAX_ODDS` (reszta systemu: 1,19–6,00),
* widełek kurs × szansa (obowiązkowych dla starych rynków drużynowych),
* progu pewności ani limitu szerokości przedziału ufności,
* okna zgody z rynkiem — **„kto więcej" go nie ma wcale** (sumy mają).

Efekt widać gołym okiem: **28 z 39 sum meczowych ma kurs poniżej 1,136**.
Przy 12% od stawki kurs 1,136 to matematyczna granica opłacalności **przy
stuprocentowej pewności** — zakład po 1,04 traci 8,5% nawet wtedy, gdy zawsze
wchodzi. Publikujemy dziś 28 takich pozycji.

To jest naprawa na jeden wieczór (dopiąć nowe rynki do tych samych bram, co
resztę) i powinna wyprzedzić wszystko inne z kolejki.

### Co zostało wdrożone 31 lipca

Rozdzielone są **dwie liczby**, i to jest sedno rozwiązania:

* **`ev_pct` (brutto)** — tym decydują bramy publikacji. Zostaje nietknięte.
* **`ev_netto` (po podatku)** — to widzi użytkownik i tym liczą się bilanse.

Powód rozdziału jest pomiarowy, nie kosmetyczny. Gdyby podatek wszedł od razu
do bram, selekcja zmieniłaby się w tej samej chwili co rachunek i w kolejnych
rozliczeniach **nie dałoby się rozdzielić skutku jednego od drugiego**.

Sprawdzone przed decyzją: podatek w bramach ściąłby dzisiejszą listę
ze **138 typów do 6** — bo model gra medianą kursu 1,25, a po podatku sens
mają dopiero kursy od ~1,96.

**Co konkretnie się zmieniło:**

* `betting.py` — jedno miejsce na cały rachunek podatku (`kurs_netto`,
  `ev_pct`, `ev_brutto_pct`, `prog_oplacalnosci`) plus tryb per bukmacher,
* każdy publikowany typ dostaje `ev_netto` i `tryb_podatku`,
* rozliczenia liczą bilans po podatku — dzienny, per strumień, per epoka
  i kupony (przy kuponie podatek liczy się **raz od stawki**, nie od legu),
* zwrot (zakład anulowany) zostaje bez potrącenia — stawka wraca w całości,
* front pokazuje wyłącznie wartość netto: karta typu, hero, sortowanie,
  próg opłacalności, kwota „z 10 zł robi się", zysk zagranego kuponu,
* kwarantanny (rynków, stron, kategorii) **celowo zostają na brutto** — to
  bramy, a ich progi były kalibrowane na brutto.

**Czego NIE ruszono i dlaczego:** progi widełek drużynowych (0,52 i 0,42) były
zdefiniowane jako próg opłacalności przy kursach 1,92 i 2,38. Po podatku te
same definicje dają 0,59 i 0,48, czyli przeliczenie **zaostrzyłoby** bramę.
Do tego wracamy z pomiarem, tak jak przy oknie zgody z rynkiem.

### Czego jeszcze nie wiemy i co trzeba rozstrzygnąć

Nie przesądzam, że „12% od stawki" to właściwy tryb dla tego produktu —
to jest decyzja, nie fakt techniczny:

* **Superbet i STS** — standardowo podatek jest pobierany od stawki,
* **Betclic** reklamuje ofertę „bez podatku", ale zasady bywają warunkowe
  (limit stawki, wybrane rynki, czas trwania promocji),
* część operatorów prowadzi „zwrot podatku" jako bonus, co jest jeszcze
  innym rachunkiem.

Dlatego **nie wpisywałbym na sztywno mnożnika 0,88**, tylko `tax_mode`
per typ i per bukmacher (`standard` / `bez_podatku` / `zwrot`), zapisywany
razem z typem — żeby historia wiedziała, w jakim trybie zakład był liczony,
i żeby zmiana trybu nie unieważniła całej przeszłości.

**Do decyzji przed dotknięciem kodu:** który tryb jest domyślny, czy pokazujemy
obie liczby (brutto i netto), i czy typy niemożliwe do wygrania po podatku mają
w ogóle wchodzić na listę.

---

## 5. Dane

**Źródło:** patrz tabela w sekcji 4.

**Czy to API?** Formalnie tak — ale wewnętrzne, nieudokumentowane endpointy,
które zasilają strony tych serwisów. Nie ma kluczy, umów ani gwarancji.

**Czy scraping?** Tak, w praktyce to jest scraping API. Trzy protokoły:
zwykły HTTP/JSON (statshub, 365Scores, Superbet), WebSocket (STS),
gRPC-Web z binarnym protobufem (Betclic — protokół rozgryziony ręcznie,
z bundla JavaScript ich strony). Plus jeden klasyczny scraping HTML (Rotowire).

**Czy legalne?** Szara strefa regulaminów. Dane są publiczne i dostępne bez
logowania, nie obchodzimy zabezpieczeń, nie odsprzedajemy surowych danych i
trzymamy niskie tempo zapytań. Ale regulaminy tych serwisów zwykle zabraniają
automatycznego pobierania, więc **przy komercjalizacji to jest ryzyko prawne
i biznesowe do rozstrzygnięcia**, nie techniczne.

**Czy płatne?** Nie. Cały koszt danych to 0 zł. Alternatywa komercyjna
(API-Football itp.) to ~40–60 USD miesięcznie i była świadomie odrzucona.

**Jakie opóźnienie?**
* Kursy: świeże w chwili pobrania, nigdy nie cache'owane.
* Propsy zawodnicze pojawiają się w feedzie **24–48 h przed meczem** — wcześniej
  nie da się nic policzyć.
* Cykl deklaruje 15 minut, realnie odpala co ~1–1,5 h (ograniczenie GitHub Actions).
* Rozliczenie: mecz + ~105 minut, a jeśli po 48 h brak danych — automatyczny zwrot.

---

## 6. Panel użytkownika — wszystkie zakładki

Nawigacja jest w trzech grupach, celowo:

```
codzienna praca:    Zawodnicy  →  Drużyny  →  Kupony  →  Mecze
twoje rzeczy:       Moje zakłady
zaufanie:           Skuteczność  →  Jak to działa
```

Do tego ekran logowania i podstrona pojedynczego meczu.

**Nie ma** zakładek: Profil, Subskrypcja, Ustawienia, Panel admina. Nie ma kont
użytkowników — jest hasło.

---

## 7. Każda zakładka — co dokładnie robi

### Zawodnicy (`/`) — strona główna

Pierwszy ekran to hero z nagłówkiem „Model, który typuje za Ciebie", kaflem
„stan rynku" (żywe podsumowanie: czy dziś w ogóle jest co grać) i tickerem
najlepszych pozycji.

Pod spodem **tablica typów** z czterema zakładkami:
* **Pewniaki** — typy o najwyższej szansie,
* **Lepszy kurs w STS** — te same zdarzenia, gdzie drugi bukmacher płaci więcej,
* **Drabinki** — pełne analizy zawodnika (opis niżej),
* **Wszystko**.

**Filtry:** rynek, pewność (każda / wysoka / średnia), mecz, plus sortowanie
(polecane przez model / szansa / kurs / godzina). Filtry są w adresie URL, więc
link do konkretnego widoku da się wysłać.

**Wyszukiwania po nazwisku nie ma** — świadomie, bo lista jest krótka.
**Zapisywania typów nie ma** — od tego jest zakładka Moje zakłady.

Pojedynczy typ (`BetCard`) rozwija się w miejscu i pokazuje: formę zawodnika w tym
rynku mecz po meczu, rozkład prawdopodobieństwa (ile szans na 0, 1, 2, 3 zdarzenia),
wodospad czynników (baza → minuty → rywal → sędzia → dom/wyjazd → scenariusz)
i uzasadnienie po polsku.

**Drabinka** to osobny format: bierzemy jednego zawodnika i pokazujemy **całą
drabinkę kursów Superbetu** (1+, 2+, 3+…) z naszą szansą przy każdym szczeblu,
historią ostatnich 10 występów, rozbiciem na sezony i porównaniem z drugim
cennikiem (Betclic). Karty mają klasę jakości (TOP / mocny / solidny) i kategorię
mówiącą, **na jakim dowodzie stoją** (przewaga nad kursem / rozjazd cenników /
seria formy / transfer / debiutant).

### Drużyny (`/druzyny`)

Osobny produkt, nie ta sama lista. Gole, rożne, kartki, faule, strzały **całych
drużyn**, plus rynki „kto więcej" i sumy meczowe.

Układ zaprojektowany pod pełny sezon (dziesiątki meczów dziennie): trzy
najmocniejsze typy doby w formie dużych kart z paskiem szansy, potem reszta dnia
listą, potem kolejne dni zwijane per rozgrywki. Filtry: rynek i rozgrywki;
sortowanie: najmocniejsze / szansa / kurs / godzina.

Dziś: **98 typów, 35 meczów, 6 rozgrywek.**

### Kupony (`/kupony`)

Nagłówek mówi wszystko: „Wybierz, ile chcesz wygrać".

Trzy horyzonty (na dziś / na kilka dni / z przewagą), w każdym suwak celu
kursowego. Model **sam składa** kupon: dobiera typy zachłannie po jakości
`ln(szansa)/ln(kurs)` z przeszukiwaniem wiązką, z karą za typy z jednego meczu
i z dywersyfikacją rodzin rynków.

Karta kuponu pokazuje: kurs łączny, szansę modelu na komplet, ile z 10 zł robi się
złotówek, każdy typ z jego szansą, oznaczenie **najsłabszego ogniwa** oraz — to
ważne — ile z meczów miało już ogłoszone składy w chwili budowy.

Trzy akcje: **gram ten kupon** (ląduje w Moich zakładach), **pomiń, pokaż inny**
(odpala pipeline od razu, nowy kupon w 2–3 min; pominięty rozlicza się w tle, żeby
model się uczył), **przebuduj po składach**.

Po publikacji kupon jest **zamrożony** — nie zmienia się, chyba że ogłoszone składy
wywrócą któryś typ.

Niżej: kronika trafionych kuponów (wszystko, co kiedykolwiek weszło, zostaje na
stałe) i **generator własnego kuponu** — ta sama przeanalizowana pula, te same
bezpieczniki, ale wybierasz mecze, kurs docelowy i charakter (bezpieczny /
zbalansowany / agresywny). Można usunąć typ (model dobierze inny) albo przypiąć.

### Mecze (`/mecze`)

Terminarz przeskanowanych meczów z licznikami (ile okazji, jaka najlepsza wartość),
domyślnie zawężony do rozgrywek w zakresie drużynowym.

Pod spodem **tabela pokrycia skanu** — uczciwy raport: ile meczów widzi nasze
źródło statystyk, ile kwotuje Superbet, ile udało się sparować, i **które mecze
z bogatą ofertą propsów wypadły** (zmierzona luka pokrycia, nie ukryta).

Wejście w mecz → zawodnicy z najlepszym pokryciem linii, wszystkie okazje tego
meczu i rejestr odrzuceń („czemu ten zawodnik nie dostał typu").

### Moje zakłady (`/zaklady`)

Dziennik gracza. Kupony zagrane przyciskiem „gram ten kupon" **rozliczają się same**
(po kluczu, z historii pipeline'u) — nie trzeba wpisywać wyniku.

Do tego ręczny tracker pojedynczych zakładów: wpisujesz kurs wzięty i kurs tuż
przed meczem, a strona liczy CLV. Jeśli w długiej serii bierzesz lepsze kursy niż
zamknięcie rynku, to najmocniejszy dowód, że system faktycznie coś znajduje.

Dane trackera siedzą w przeglądarce (localStorage), nie na serwerze.

### Skuteczność (`/model`)

Najważniejsza zakładka projektu i jedyna, która ma dwa różne widoki.

**Werdykt na górze**, dziś brzmi: *„Na razie jesteśmy pod kreską"* — z pełnym
rachunkiem: 429 typów, bilans −49,41u, trafia 58%, próg 60%, obiecywał 71%,
CLV +0,9%, 7 z 21 dni na plusie. Plus akapit „co z tym robimy" pisany po ludzku.

Niżej filtr strumienia (Wszystko 429 / Zawodnicy 263 / Drużyny 166 / Drabinki 16),
**krzywa wyniku** narastająco, **kalendarz miesięczny** z bilansem dnia po dniu,
i lista każdego typu z wynikiem.

Zakładki dowodów:
* **Czy się uczymy** — paczki po 40 rozliczeń: „weszło / obiecywał / różnica".
  Dziś mówi wprost: *„Model NIE robi postępów — jest gorzej."*
* **Rynki** — tabela „obiecywał vs weszło" per rynek.
* **Kupony** — bilans per horyzont, ostatnie 12, kronika trafień.
* **Test na danych z przeszłości** — egzamin na meczach spoza nauki, z wykresem
  kalibracji i wynikiem Briera.

**Widok klienta** (`?widok=klient`) wycina kuchnię — i wycina ją **z danych na
serwerze**, nie z interfejsu. Ukrycie w UI nie jest ukryciem: komponent jest
kliencki, więc wszystko, co dostanie w propsach, ląduje w źródle strony.

### Jak to działa (`/jak-to-dziala`)

Dziesięć kroków metody bez żargonu, od „zbieramy historię" do „sprawdzamy sami
siebie", plus ramka **„Uczciwe zastrzeżenie"**: model nie zna kontuzji sprzed
godziny ani planów trenera, dlatego nie pokazujemy typów, w których drastycznie
nie zgadzamy się z rynkiem.

### Logowanie (`/login`)

Jedno pole na hasło. Hasło decyduje o roli.

---

## 8. Dashboard — co widzi użytkownik po zalogowaniu

Wchodzi na `/` (Zawodnicy) i w pierwszym ekranie ma:

1. **Nagłówek** — „Model, który typuje za Ciebie" + jedno zdanie, co system robi.
2. **Kafel stanu rynku** — żywa ocena, np. *„Rynek wycenia blisko modelu — w tej
   chwili bukmacher nie przepłaca za żadne zdarzenie."*
3. **Dwa przyciski** — „Zobacz dzisiejsze typy" i „Jak to działa?".
4. Po zjechaniu: **tablica typów** z filtrami.
5. Na dole dwa bliźniacze kafle: **kupon dnia** (gotowy do skopiowania, z kursem
   łącznym i kwotą z 10 zł) i **jak trafia model** (ostatni dzień, licznik łączny,
   trafialność, słupki dzień po dniu, ostatnie rozliczone typy zielono-czerwoną
   kreską).

Zamysł: obietnica → dowód → produkt, wszystko na jednym ekranie, bez klikania.

Ciekawostka o dzisiejszym stanie: ponieważ sześć rynków zawodniczych siedzi
w kwarantannie, strona główna zamiast listy pokazuje **wytłumaczenie po ludzku**,
które rynki są wstrzymane, ile straciły i że wrócą same — plus przyciski do
Drabinek i rynków drużynowych.

---

## 9. Free vs Premium

**Nie istnieje.** Dziś to narzędzie osobiste, nie produkt komercyjny:
brak kont, brak rejestracji, brak płatności, brak limitów.

Jest za to **przygotowany podział treści**, który jest naturalną granicą free/premium,
gdyby przyszła monetyzacja:

| | admin (`APP_PASSWORD`) | klient (`KLIENT_PASSWORD`) |
|---|---|---|
| Typy, kupony, drużyny, drabinki | tak | tak |
| Skuteczność: werdykt, krzywa, kalendarz | tak | tak |
| Tabela „obiecywał vs weszło" per rynek | tak | **nie** |
| Raport „czy się uczymy" | tak | **nie** |
| Typy liczone na próbę (pomiarowe) | tak | **nie** |
| Diagnostyka modelu, epoki per rynek | tak | **nie** |
| Bilans i historia kuponów | tak | **nie** |
| Test na danych z przeszłości | tak | **nie** |

Admin może podejrzeć własny produkt oczami klienta przełącznikiem, bez wylogowania.

---

## 10. Admin

**Panelu admina nie ma i na razie nie jest planowany.** Zamiast panelu jest zasada:
wszystko liczy się samo, a człowiek nie może dopisać ani skasować wyniku.

To nie jest brak funkcji, tylko decyzja produktowa — na stronie Skuteczności jest
napisane wprost: *„Nic nie da się stąd usunąć ani dopisać ręcznie."* Panel admina
z ręczną edycją zniszczyłby jedyny prawdziwy dowód, jaki ma ten produkt.

**Co da się dziś zrobić ręcznie (i to jest cała lista):**
* pominąć kupon / wymienić typ / przebudować po składach — z poziomu strony,
* zmienić charakter buildera (bezpieczny / zbalansowany / agresywny),
* kliknąć odświeżenie kursów STS,
* uruchomić cykl ręcznie z zakładki Actions na GitHubie,
* zmienić progi i zakres lig — **w kodzie**, przez commit.

**Co jest w pełni automatyczne:** zbieranie danych, liczenie, publikacja, wycofywanie
typów, rozliczanie, kalibracja, kwarantanna, składanie kuponów, wypychanie na stronę.

---

## 11. Automatyzacja — kto co robi

**Python (pipeline)** — cała robota merytoryczna:
odkrywa mecze → paruje je z ofertą bukmachera → pobiera historię i statystyki →
liczy rozkłady → nakłada kontekst → zdejmuje marżę z kursów → liczy przewagę,
pewność i ryzyko → przepuszcza przez bramy → składa kupony → rozlicza zakończone
mecze → przelicza kalibrację i kwarantannę → wypycha ~14 snapshotów JSON do Supabase.

**„Backend" (Next.js na Vercelu)** — czyta Supabase, cachuje w pamięci na 60 s,
odcina mecze, które już się zaczęły, pilnuje logowania i ról, wycina kuchnię dla
klienta, przyjmuje trzy akcje na kuponach i odpala pipeline po pominięciu.

**Frontend** — filtruje, sortuje, animuje, rysuje wykresy i trzyma ręczny tracker
w przeglądarce. **Nie liczy modelu.** Jedyny wyjątek: generator kuponów na życzenie
ma bliźniaczą implementację w TypeScript (`kuponBuilder.ts`), pilnowaną testem
parytetu z Pythonem — żeby ręczny kupon składał się dokładnie tak samo jak
automatyczny.

**Człowiek** — decyduje o progach i zakresie, ocenia zmiany wzrokiem na zrzutach,
raz na kilka dni odpala lokalnie doczytanie egzotycznych rozliczeń z Sofascore
(bo chmura ma tam zablokowane IP).

---

## 15. Roadmapa

### MVP — **zrobione**
Top 5 lig, 5 rynków zawodniczych, rynki drużynowe, kursy z prawdziwego źródła,
value board z przewagą, pewnością i uzasadnieniem, zapis predykcji od dnia pierwszego.

### v1 — **zrobione, i to z nawiązką**
Ponad plan: cały świat na propsach zamiast top 5 lig, 13 rynków zawodniczych
zamiast 5, trzech bukmacherów zamiast jednego, automatyczne rozliczanie i
samouczenie (tego w planie nie było wcale), kupony i drabinki (też nie było),
CLV, kalibracja i backtest w UI.

### v2 — **to, co robimy teraz** (kolejność ustalona przez użytkownika)

0. **ZROBIONE 31 lipca:** bramy dla nowych rynków (sumy, „kto więcej") oraz
   podatek od stawki w całym rachunku pokazywanym i rozliczanym.
1. **Dokończyć przebudowę kuponów** — krótsze kupony, wymóg dodatniej wartości
   każdego typu po korekcie, jedna spójna szansa pokazywana. Do tego suwak kursu
   2–25 w generatorze.
2. **Naprawić zawyżanie λ** — to trzyma rynki zawodnicze w kwarantannie.
3. **Zmierzyć korelację między drużynami** w sumach meczowych (dziś zakładamy
   niezależność, przez co wysokie linie są zawyżone).
4. **Więcej kart w Drabinkach** — z 3–5 do kilkunastu dziennie.
5. **Ocenić nowe rynki** („kto więcej", sumy) po pierwszych ~15 rozliczeniach
   na stronę.

### v3 — dalej
* Wyjście na plus na typach zawodniczych albo świadoma decyzja, że produktem są
  wyłącznie rynki drużynowe i drabinki.
* Alerty (Telegram / push) na typy, które wchodzą i schodzą.
* Automatyczna reakcja na ogłoszenie oficjalnych składów (dziś jest przebudowa
  na żądanie).
* CI z testami przed deployem.
* Ewentualna komercjalizacja: konta, płatności, limity — dziś **nie ma
  ani jednego z tych klocków**.

**Poza stołem** (odrzucone przez użytkownika): systemy/kupony blokowe,
kwarantanna w drabinkach.

---

## 19. Problemy — czego się boję

### Technicznie

0. **Po podatku produkt prawie nie ma czego pokazać — i to jest teraz problem
   numer jeden.** Podatek jest już policzony i widoczny (sekcja 4a), ale
   odsłonił rzecz strukturalną: model gra medianą kursu 1,25, a po 12% od
   stawki sens mają dopiero kursy od ~1,96. Gdyby podatek wpiąć w bramy,
   z dzisiejszych 138 typów zostałoby **6**. Bramy stoją więc na razie na
   brutto — świadomie, jako decyzja, nie przeoczenie. Dopóki model nie zacznie
   wygrywać na kursach ~2,0 (gdzie dziś trafia 28–40% przy deklarowanych
   58–64%), produkt nie ma dodatniej wartości do sprzedania.

1. **Model przeszacowuje i nie przestaje.** Obiecuje 71%, trafia 58%. Kalibracja
   ściąga szanse w dół co cykl, ale brama publikacji natychmiast wybiera nowy czub
   rozkładu, więc deklaracja opublikowanych typów stoi w miejscu od miesiąca. To
   jest problem numer jeden i nie jest rozwiązany.

2. **Żaden wycinek typów zawodniczych nie jest zyskowny.** Sprawdzone na 259
   typach: nawet najlepszy możliwy filtr (tylko kursy poniżej 1,6, bez
   kwarantannowanych kategorii, bez flagi „pewniak") dalej traci 8 groszy na
   złotówce. **Nie da się z tego wyjść samym filtrowaniem** — cały strumień jest
   pod kreską.

3. **Cron jest kłamcą.** Deklaruje 15 minut, realnie odpala co ~1–1,5 h. Strona
   bywa godzinę nieświeża, a typy potrafią pojawić się późno.

4. **Brak CI.** 466 testów, zero automatycznych uruchomień. Deploy idzie na
   `master` bez żadnej bramki. Jeden nieuważny commit trafia na produkcję.

5. **Kruchość źródeł.** Sześć nieudokumentowanych API. Zmiana pola w Superbecie
   albo w statshubie wywraca cykl — i już się to zdarzało (pułapka `matchTimestamp`,
   wielkie litery w „Poniżej"/„poniżej", dwie konwencje nazw rynków drużynowych).
   Betclic to binarny protobuf odczytany z bundla JS — przetrwa dokładnie do ich
   najbliższego refaktoru.

6. **Sofascore blokuje chmurę.** Ogon egzotycznych rozliczeń wymaga dwukliku na
   domowym komputerze. To jedyny element, który nie jest w pełni online.

7. **Rozliczony rekord jest zamrożony na zawsze.** Błąd rozliczenia zostaje
   w statystyce już na stałe. Trzy takie błędy znaleziono 30 lipca i naprawiono,
   ale skrzywione rekordy zostają.

8. **Jedna tabela zamiast schematu.** `app_data` z blobami JSON działa świetnie do
   ~14 MB, ale każda analiza historyczna wymaga wczytania całości. Znormalizowany
   schemat czeka od miesiąca nieużywany.

### Biznesowo

1. **Produkt nie zarabia.** Trudno sprzedawać narzędzie, którego własna zakładka
   Skuteczności mówi „jesteśmy pod kreską" — a ukryć tego nie chcemy, bo uczciwość
   jest jedyną przewagą tego produktu nad tipsterami z Telegrama.
2. **Zyskowna jest tylko część.** Rynki drużynowe bywają na plusie, zawodnicze nie.
   To sugeruje, że produktem powinny być drużyny i drabinki, a propsy zawodnicze
   zostają jako pole badawcze. Trudna decyzja, bo propsy były pierwotną wizją.
3. **Podaż typów.** Przy włączonej kwarantannie zakładka Zawodnicy potrafi być
   pusta. Użytkownik powiedział wprost: „nie może być tak, żeby było 6 typów".
   Naprawa podaży i naprawa jakości ciągną w przeciwne strony.
4. **Ryzyko prawne przy komercjalizacji.** Scraping wewnętrznych API jest do
   przyjęcia dla narzędzia osobistego; przy płatnym produkcie to inna rozmowa.
5. **Limitowanie kont.** Nawet gdy model zacznie zarabiać, polscy bukmacherzy
   szybko limitują wygrywające konta. To ogranicza wartość produktu dla klienta,
   niezależnie od jakości modelu.
6. **Zero infrastruktury sprzedażowej.** Brak kont, płatności, limitów, regulaminu.
   To tygodnie pracy, których nikt jeszcze nie zaczął.

### Marketingowo

1. **Nie ma czego pokazać jako dowód.** Jedyny szczery dowód to krzywa wyniku,
   a ona idzie w dół. Kronika trafionych kuponów (×20,30, ×10,79) ratuje wrażenie,
   ale to selekcja i my o tym wiemy.
2. **CLV to jedyna dobra wiadomość** (+0,9%): bierzemy lepsze kursy niż rynek na
   zamknięciu. Problem: nikt poza garstką ludzi nie wie, co to znaczy.
3. **Kategoria jest zatruta.** „Typy z AI" to fraza spalona przez oszustów.
   Wyróżnikiem musi być radykalna przejrzystość — pokazywanie porażek — a to jest
   przekaz trudny do sprzedania.
4. **Brak jakiejkolwiek obecności.** Nie ma domeny publicznej, landing page'a,
   nazwy zarezerwowanej, żadnego kanału. Produkt istnieje tylko za hasłem.

---

## 20. Screeny

Zrzuty świeże (31 lipca, produkcyjny build, prawdziwe dane), w dwóch szerokościach:
laptop 1440 px i telefon 390 px. Katalog: **`web/zrzuty/`**

> **Poprawka narzędzia (31 lipca).** Wcześniejsze zrzuty pokazywały puste pole
> pod pierwszym ekranem i tylko część treści (np. 4 kroki z 10 na „Jak to
> działa"). To **nie była wada strony, tylko skryptu**: komponent `Reveal`
> startuje z `opacity: 0` i pojawia się dopiero przy wejściu w widok, a
> `fullPage: true` w Playwrighcie renderuje wysoką klatkę **bez przewijania**.
> `zrzuty.mjs` przewija teraz całą stronę przed zrzutem. Ponieważ zrzuty są
> jedynym sposobem, w jaki oglądamy własne UI, narzędzie kłamało nam do oczu
> przy każdej ocenie układu.

```
start--laptop.png / start--telefon.png                  strona główna (Zawodnicy)
druzyny--laptop.png / --telefon.png                     typy drużynowe
kupony--laptop.png / --telefon.png                      gotowe kupony + generator
mecze--laptop.png / --telefon.png                       terminarz + pokrycie skanu
zaklady--laptop.png / --telefon.png                     dziennik gracza
model--laptop.png / --telefon.png                       Skuteczność (widok admina)
model-widok-klient--laptop.png / --telefon.png          Skuteczność (widok klienta)
jak-to-dziala--laptop.png / --telefon.png               metoda w 10 krokach
```

**Figmy nie ma.** Nigdy nie było — interfejs powstawał od razu w kodzie, a jedynym
narzędziem kontroli są zrzuty Playwrightem (`npm run zrzuty`) i audyt mobilny
(`npm run audyt`, wykrywa strony uciekające w bok na telefonie).

**Mockupów nie ma.** Design system siedzi w `web/src/app/globals.css` (zmienne
kolorów, promienie, cienie) i w `docs/frontend-design-skill.md`.

### Flow — jak dane płyną przez system

```
    ┌─────────── ŹRÓDŁA (6, wszystkie darmowe) ───────────┐
    statshub · 365Scores · Superbet · STS · Betclic · Rotowire
                            │
                            ▼
              PYTHON — cykl w GitHub Actions
    odkryj mecze → sparuj z ofertą buka → pobierz historię
    → policz rozkłady → nałóż kontekst → zdejmij marżę
    → przewaga / pewność / ryzyko → BRAMY → złóż kupony
    → rozlicz zakończone → przelicz kalibrację i kwarantannę
                            │
                            ▼
                SUPABASE — app_data (klucz → JSON)
                            │
                            ▼
             VERCEL — Next.js, cache 60 s, role
                            │
                            ▼
                      PRZEGLĄDARKA
```

### Kod — mapa dla kogoś, kto wchodzi pierwszy raz

```
pipeline/footstats/
  model/counts.py       ← SERCE: Gamma-Poisson → rozkład ujemny dwumianowy
  model/betting.py      ← devig, przewaga, EV, pewność, BRAMY PUBLIKACJI
  model/minutes.py      ← scenariusze minutowe
  model/context.py      ← mnożniki kontekstu (shrink + cap)
  model/matchup.py      ← „kto na kogo gra", ~20 analogii
  model/kupony.py       ← składanie kuponów (w trakcie przebudowy)
  engine.py             ← spina wszystko w jeden scoring
  jobs/build_wc_fast.py ← główny cykl (największy plik w projekcie)
  jobs/rozliczanie.py   ← rozliczanie + CAŁA warstwa uczenia
  jobs/radar.py         ← drabinki
  sources/              ← sześć czytników danych
  rozgrywki.py          ← rejestr lig w zakresie drużynowym

web/src/
  app/(app)/            ← siedem stron
  components/           ← ~45 komponentów
  lib/data.ts           ← warstwa danych (Supabase albo pliki lokalne)
  lib/okrojDlaKlienta.ts← wycinanie kuchni NA SERWERZE
  lib/auth.ts           ← podpisane ciasteczko sesji
```

**Repozytorium:** `github.com/tipx-tipx/footstats` (publiczne).
Cały kod, komentarze i nazwy zmiennych są po polsku — łącznie z uzasadnieniami
decyzji i zapisem pomiarów, na których je oparto.
