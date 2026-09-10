# PLAN: footstats działa codziennie, za zero złotych

Stan wyjściowy (10.09.2026): Supabase odcięty (402, `exceed_egress_quota`) od
04.09. Pipeline stoi. Blokada zejdzie sama ok. 30.09. Repo `tipx-tipx/footstats`
jest PUBLICZNE, Actions zużywa ~1500 min/dobę (na publicznym repo darmowe).

Cel: pipeline liczy i publikuje codziennie, bez zacinania, na darmowych planach,
i nie wraca do tego problemu za miesiąc.

Zasada nadrzędna: **jedna zmiana na raz, każda cofalna jedną stałą, kryterium
odbioru zapisane PRZED wykonaniem.**

---

## Diagnoza w trzech zdaniach

1. Supabase jest używany jako **pamięć robocza pipeline'u** (`typy_log` 25 MB,
   `trend_lib` 47 MB, `styl_bank_liga` 21 MB, `typy_log_kopia` 22 MB, `hd_0..9`),
   a te klucze jadą przez sieć do 70 razy na dobę. Front ich nie tyka ani razu.
2. `typy_log` **rośnie bez rotacji** ~1,3 MB/dobę (rozliczone wpisy zostają na
   zawsze – `rozliczanie.py:5959`). Za rok to ~500 MB JSON-a parsowanego przy
   każdym przebiegu. To ściana niezależna od tego, gdzie dane leżą.
3. Cykl trwa **39–44 min** przy timeoucie 50, a pinger puka co 10 min – więc
   z ~150 tyknięć na dobę startuje realnie 31–33 cykli, reszta odbija się od
   `concurrency`.

---

## ⚑⚑⚑⚑⚑ ETAP 0 – ODZYSKAĆ DANE. BLOKUJE WSZYSTKO POZOSTAŁE

**Jedyna kopia zapasowa księgi typów leży w tej samej odciętej bazie.**
`_kopia_zapasowa_logu` (`rozliczanie.py:1132`) zapisuje migawkę pod klucz
`typy_log_kopia` – czyli do Supabase. Poza Supabase nie ma NICZEGO: ani
w repo, ani w artefaktach Actions, ani na dysku.

To znaczy, że cała historia produktu – ~9300 rozliczeń, dataset kalibracji
i treningu, dorobek wielu tygodni – wisi dziś na jednym koncie, do którego
nie mamy dostępu, odciętym za przekroczenie limitu. **To jest ryzyko
egzystencjalne, nie niedogodność.** Dopóki nie ma kopii na dysku, każdy inny
etap jest przedwczesny.

### 0.1 Test: czy da się obejść 402 bezpośrednim połączeniem do Postgresa

Restrykcja `exceed_egress_quota` blokuje REST (PostgREST). Połączenie SQL idzie
inną drogą i **może działać mimo blokady** – to jest do sprawdzenia w 5 minut
i jeśli zadziała, cały plan rusza od dziś, bez czekania do 30.09.

Host `db.prqhkjkbpofajggquxjq.supabase.co` nie rozwiązuje się w DNS (sprawdzone),
więc droga wiedzie przez pooler, który odpowiada na porcie 6543:

```bash
# hasło bazy: panel Supabase → Project Settings → Database → Password
psql "postgresql://postgres.prqhkjkbpofajggquxjq:HASLO@aws-0-eu-central-1.pooler.supabase.com:6543/postgres" -c "select key, pg_column_size(payload) from app_data order by 2 desc limit 20;"
```

- **Działa** → od razu `pg_dump` całej bazy (69 MB) i przechodzimy do 0.3.
- **Nie działa** (402 też tutaj) → 0.2.

### 0.2 Jeśli SQL też jest odcięty – dwie drogi

| droga | efekt | ryzyko |
|---|---|---|
| transfer projektu do nowej organizacji Supabase | świeży licznik, dostęp w godzinę | transfer przy restrykcji bywa zablokowany; limit jest na organizację, więc drugi projekt (`tipx maile`) musi zostać w starej |
| czekać do ~30.09 | pewne, zero ruchu | 20 dni postoju, a po odblokowaniu spalimy się w 1–2 doby, jeśli etapy 1–4 nie są gotowe |

⚑ Postój jest w tej chwili **kosztem, ale nie stratą** – przebudowę i tak trzeba
zrobić, a robi się ją spokojniej przy zatrzymanym pipelinie. Czekanie do 30.09
jest akceptowalne WYŁĄCZNIE pod warunkiem, że etapy 1–4 są do tego czasu gotowe
i wchodzą w dniu odblokowania.

### 0.3 Kopia poza Supabase – pierwsza rzecz po odzyskaniu dostępu

`pg_dump` całej bazy + osobno `typy_log`, `typy_log_kopia`, `trend_lib`,
`styl_bank_liga`, `hd_*` jako pliki `.json.gz` na dysk i do prywatnego repo.

**ODBIÓR:** plik dumpa na dysku, `typy_log` odczytany, liczba wpisów zgadza się
z ostatnim znanym stanem księgi (~9300 rozliczonych).
**ODRZUCENIE:** jakikolwiek plik krótszy niż oczekiwany albo niedający się
sparsować – wtedy STOP i powtórka eksportu, nic dalej.

---

## ETAP 1 – Router kluczy wewnątrz `supa.py` (nie ruszamy 131 wywołań)

W pipelinie jest 131 wywołań `supa.get_key` / `supa.put_key`, z czego 74 w dwóch
plikach. **Nie dotykamy żadnego.** Testy mockują `supa._conn` i `supa.requests`
(`test_odciecie_projektu.py`), więc podmiana transportu WEWNĄTRZ `supa.py`
zachowuje i API, i cały zestaw 1340 testów.

```python
# supa.py
MAGAZYN = {              # klucz -> backend; brak wpisu = Supabase (domyślnie)
    "typy_log":        "repo",
    "typy_log_kopia":  "repo",
    "trend_lib":       "repo",
    "styl_bank_liga":  "repo",
    **{f"hd_{i}": "repo" for i in range(10)},
}
```

`get_key` / `get_key_ok` / `put_key` / `put_key_bezpiecznie` sprawdzają `MAGAZYN`
i kierują do właściwego backendu. Pamięć procesu, licznik egressu, bezpiecznik
wagi i straż 402 zostają wspólne dla obu dróg.

**ODBIÓR:** pełny pytest zielony BEZ zmian w plikach testów; pusty `MAGAZYN`
zachowuje się dokładnie jak dziś.
**ODRZUCENIE:** trzeba zmienić choć jeden test albo choć jedno wywołanie
w `rozliczanie.py` / `build_wc_fast.py` – wtedy projekt routera jest zły.

---

## ETAP 2 – Prywatne repo stanu + backend `repo.py`

Układ, który daje darmowe Actions ORAZ prywatne dane:

```
tipx-tipx/footstats        PUBLICZNE   kod + Actions (minuty darmowe, nielimitowane)
        │  fine-grained PAT w sekretach
        ▼
tipx-tipx/footstats-stan   PRYWATNE    dane pipeline'u, ZERO workflowów = 0 minut
```

Minuty Actions liczą się tam, gdzie workflow **biegnie**, nie tam, gdzie leżą
pliki – prywatne repo bez workflowów kosztuje dokładnie zero.

⚑ Uprywatnienie GŁÓWNEGO repo jest wykluczone: przy 1500 min/dobę limit
prywatnego Free (2000 min/**miesiąc**) padłby w 32 godziny.

### Trzy rzeczy, które backend musi robić dobrze

1. **gzip.** Zmierzone na naszych danych: `players.json` 16,3 MB → 1,36 MB (×12),
   `odrzucenia.json` 3,0 MB → 0,16 MB (×19). `typy_log` 25 MB to plik ~2 MB.
2. **Zapis bez okna nieatomowości.** `gh release upload --clobber` to `delete` +
   `upload`; między nimi pliku NIE MA. Kolejność musi być odwrotna:
   wgraj nowy asset pod nazwą z sygnaturą → przestaw wskaźnik → dopiero potem
   skasuj poprzedni. Czytelnik zawsze widzi kompletną wersję: starą albo nową.
3. **404 ≠ pustka.** Dokładnie ta sama pułapka, przed którą broni `get_key_ok`:
   nieudany odczyt musi zwrócić `(None, False)`, żeby wołający nie dopisał
   świeżych wpisów do niczego i nie zapisał tego jako całości historii.

Miejsca, gdzie to realnie zagraża (odczyt w innej grupie `concurrency` niż
zapis): `model.yml` czyta `trend_lib` pisany przez cykl; cykl czyta `hd_*`
pisane przez `magazyn.yml`.

**ODBIÓR:** test, w którym odczyt trafia w okno podmiany i zwraca `(None, False)`,
a wołający NIE nadpisuje historii. Dry-run lokalny czyta i pisze `typy_log`
z prywatnego repo.
**ODRZUCENIE:** jakikolwiek scenariusz, w którym czytelnik dostaje pusty lub
częściowy plik i traktuje go jak prawdę.

---

## ETAP 3 – Przeprowadzka pięciu ciężkich kluczy, po jednym

Kolejność od najcięższego i najmniej ryzykownego:
`trend_lib` → `styl_bank_liga` → `typy_log_kopia` → `hd_0..9` → `typy_log`.

Po każdym kluczu: jeden pełny cykl, odczyt licznika `raport_egress`, dopiero
potem następny. `typy_log` na końcu, bo jest najgorętszy (pisany z dwóch jobów).

⚑ `cycle.yml` i `rozlicz.yml` dzielą grupę `concurrency: footstats-cycle`, więc
nigdy nie chodzą równolegle – jedyny klucz pisany z dwóch miejsc jest już
serializowany przez GitHuba. Ta zależność **musi zostać**; gdyby ktoś kiedyś
rozdzielił te grupy, `typy_log` straci ochronę.

**ODBIÓR:** licznik egressu w cyklu spada z ~110 MB do **poniżej 15 MB**,
a `rozlicz_only` przestaje czytać `typy_log` z Supabase w ogóle.
**ODRZUCENIE:** cykl wydłuża się o więcej niż 3 min albo pojawia się choć jeden
`(None, False)` na kluczu, który wcześniej czytał się poprawnie.

---

## ETAP 4 – Rozbicie `typy_log` na okna (to naprawia przyczynę, nie objaw)

Dziś jeden plik rośnie 1,3 MB/dobę i jest czytany w całości przy każdym
przebiegu, choć cykl potrzebuje z niego prawie wyłącznie wpisów świeżych
i nierozliczonych.

```
typy_log_biezacy       nierozliczone + ostatnie 30 dni   ~1-2 MB   czyta cykl i rozliczanie
typy_log_2026-08       zamknięty miesiąc, tylko odczyt   ~35 MB    czyta trening
typy_log_2026-09       ...
```

Wpis wędruje z bieżącego do miesięcznego, gdy jest rozliczony i starszy niż
30 dni. Trening i pomiary sięgają po archiwum raz dziennie, nie 70 razy.

⚑ CZEGO NIE WOLNO: **skracać historii**. Rozliczone wpisy to dataset kalibracji
i treningu – zmieniamy tylko sposób przechowywania, nigdy zawartość. Podobnie
`BetCard.oknaFormy` liczy okno `all` z PEŁNEJ historii formy.

**ODBIÓR:** suma wpisów we wszystkich plikach = liczba wpisów przed rozbiciem,
co do jednego. Trening na rozbitej księdze daje ten sam wynik co na scalonej
(porównanie Briera na tej samej próbie). Cykl czyta poniżej 2 MB.
**ODRZUCENIE:** różnica choćby jednego wpisu albo inny wynik treningu.

---

## ETAP 5 – Żeby się nie zacinało: rytm i czas cyklu

Zmierzone: cykl 39–44 min przy timeoucie 50, pinger co 10 min, 150 tyknięć na
dobę wobec 31–33 realnych startów. Czyli **cykl jest wąskim gardłem świeżości**,
a nie cron.

| zmiana | dlaczego | ryzyko |
|---|---|---|
| `rozlicz.yml` 20 → 60 min | czytał `typy_log` 72×/dobę; po etapie 4 czyta mało, ale 72 przebiegi to nadal 72 starty | rozliczenie później o max 40 min – bez wpływu na produkt |
| pinger 10 → ~20 min | 2/3 dispatchy i tak odbija się od `concurrency` | żadne, to czysta strata dziś |
| zmierzyć, co zjada 40 min cyklu | dziś stoper pokazuje tylko „model" i „wysyłka" – za grubo, żeby cokolwiek wiedzieć | brak – to sam pomiar |

⚑ Trzeciego punktu NIE optymalizujemy w ciemno. Najpierw stoper na etapach
wewnątrz `build_league`, dopiero potem decyzja. Etap 4 sam z siebie skróci cykl
(mniej parsowania), więc pomiar robimy PO nim.

**ODBIÓR:** świeżość typów nie gorsza niż dziś przy mniejszej liczbie startów.
**ODRZUCENIE:** typy pojawiają się później niż przed zmianą.

---

## ETAP 6 – Czujniki, żeby to się nie powtórzyło trzeci raz

Dwa spalenia (25.08 i 04.09) miały wspólny mianownik: **nikt nie widział, że
licznik rośnie, dopóki nie było za późno.** Straż 402 z 28.08 kończyła joby
zielono, więc awaria stała pięć dni niezauważona.

1. **Próg egressu, nie tylko licznik.** `raport_egress` już jest; dokładamy
   budżet dobowy (5 GB/mies. ≈ 170 MB/dobę) i **czerwony job przy 50% progu**,
   zanim limit padnie.
2. **Kopia księgi POZA Supabase, raz na dobę.** Naprawia dziurę z etapu 0 na
   stałe – po etapie 3 dzieje się to samo z siebie, ale musi być świadomie
   sprawdzone testem.
3. **Rozstrzygnąć, czy Supabase liczy egress przed czy po kompresji.** Przed
   bazą stoi Cloudflare (`Server: cloudflare`), a nasz licznik mierzy
   `len(r.content)` PO dekompresji, więc zawyża ~12×. Arytmetyka to sugeruje:
   licznik dawałby ~350 GB/mies., a panel pokazał 31,79 GB (stosunek ~11×,
   dokładnie tyle, ile daje gzip na naszych danych). Jeśli tak jest, po
   przeprowadzce mamy 10× zapasu zamiast działania na styku. Weryfikacja: jedno
   spojrzenie w panel po pierwszej pełnej dobie i porównanie z licznikiem.
4. **Plakietka „dane sprzed N dni"** (już wdrożona 08.09) zostaje.

**ODBIÓR:** test, w którym przekroczenie progu dobowego kończy job czerwono.
Panel po dobie pokazuje egress zgodny z licznikiem w granicach ±20% (albo
wyjaśniony przez kompresję).

---

## ETAP 7 – Powrót na produkcję i doba obserwacji

1. Wdrożenie wszystkiego przy ZATRZYMANYM pipelinie (nic nie ryzykujemy).
2. Odblokowanie bazy (transfer organizacji albo 30.09).
3. Pierwsza doba pod obserwacją: licznik egressu po każdym cyklu, panel
   Supabase rano, liczba rozliczeń zgodna z liczbą typów.
4. Dopiero potem wracamy do modelu – czeka **pomiar kontrolny pokrycia**
   (`p` vs `p_bez_pokrycia` w `p_uczony`) i **drabinki** przy ~100 rozliczeniach.

**ODBIÓR całości:** siedem kolejnych dób bez odcięcia, egress poniżej 20%
limitu, cykle zielone, typy publikowane codziennie o 6:00.

---

## Budżet po zmianie (dlaczego to ma się zmieścić)

W Supabase zostaje **wyłącznie to, co czyta front**: bundle 1,4 MB
(`value_bets`, `matches`, `calibration`, `meta`, `kupony`, `odds_superbet`,
`legi_pool`, `sts_value`, `druzyny_forma`, `radar`, `pokrycie_liga`) plus trzy
leniwe – `players` 3,1 MB, `odrzucenia` 1,8 MB, `typy_wyniki` 1,1 MB – oraz
cztery małe `kupony_*` z tras API.

| pozycja | odświeżeń/dobę | waga | na dobę |
|---|---|---|---|
| bundle (okno 30 min) | 48 | 1,4 MB | 67 MB |
| `players` (1 h) | 24 | 3,1 MB | 74 MB |
| `odrzucenia` + `typy_wyniki` (3 h) | 8 | 2,9 MB | 23 MB |
| **razem bez kompresji** | | | **~165 MB = 5,0 GB/mies.** |
| **razem, jeśli liczone po kompresji** | | | **~14 MB = 0,4 GB/mies.** |

Zapis do Supabase nie liczy się do egressu (POST bez `return=representation`).
Jeśli okaże się, że jesteśmy na styku 5 GB, kolejna dźwignia to wydłużenie okna
`players` albo przeniesienie go za trasę API – ale `players` niesie `xi`
(pierwszy skład), potwierdzany ~godzinę przed meczem, więc **okna 1 h nie wolno
wydłużać** bez zgody na starsze składy.

---

## Czego w tym planie NIE robimy

* **Nie płacimy** – ani Supabase Pro, ani minut Actions.
* **Nie uprywatniamy głównego repo** – to kosztowałoby darmowe Actions.
* **Nie skracamy historii** księgi ani formy.
* **Nie dotykamy modelu** – żadnych zmian w wycenie, bramach, warstwach.
  Do modelu wracamy dopiero w etapie 7.
* **Nie optymalizujemy cyklu w ciemno** – najpierw stoper, potem decyzja.
* **Nie budujemy drugiego magazynu drużyn ani banku zawodników** – oba istnieją
  i są pełne.

---

## Punkt decyzyjny (jedyny otwarty)

Backend stanu: **prywatne repo GitHub** (zero kont, zero karty, ruszamy od razu;
kosztem PAT do rotacji i ręcznej atomowości zapisu) czy **Cloudflare R2**
(atomowy PUT, egress zawsze darmowy, droga do zdjęcia Supabase w całości;
kosztem konta i podpięcia karty mimo darmowego progu).

Plan jest napisany tak, że różnica dotyczy **wyłącznie etapu 2** – reszta
zostaje bez zmiany, bo router z etapu 1 traktuje backend jak wymienną wtyczkę.
