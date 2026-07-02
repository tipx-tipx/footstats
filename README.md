# FootStats — silnik okazji na statystyki piłkarskie

Osobiste narzędzie analityczne: model matematyczny szacuje prawdopodobieństwa
statystyk zawodników i drużyn (strzały, faule, odbiory, kartki…), porównuje je
z kursami bukmacherów (Superbet, Betclic, STS) i pokazuje zakłady, w których
kurs płaci lepiej, niż powinien.

**To nie jest przeglądarka statystyk.** Każda pozycja na liście ma: szansę wg
modelu, uczciwy kurs, przewagę nad bukmacherem, ocenę pewności i ryzyka oraz
uzasadnienie po polsku.

---

## Struktura projektu

```
footstats/
├── PLAN.md              ← pełny plan projektu, model matematyczny, architektura
├── web/                 ← aplikacja (Next.js) — to, co widzisz w przeglądarce
│   └── src/data/demo/   ← dane wygenerowane przez pipeline
├── pipeline/            ← silnik analityczny (Python)
│   ├── footstats/
│   │   ├── sources/     ← pobieranie danych (Sofascore)
│   │   ├── model/       ← matematyka: rozkłady, minuty, kontekst, kursy
│   │   ├── jobs/        ← zadania: backfill, budowa danych demo
│   │   └── engine.py    ← spina wszystko w scoring okazji
│   ├── tests/           ← 26 testów rdzenia matematycznego
│   └── data/            ← lokalny magazyn pobranych meczów (+ cache HTTP)
└── supabase/migrations/ ← schemat bazy danych (na etap z prawdziwymi kursami)
```

## Jak to uruchomić

### 1. Aplikacja (przeglądarka)

```
cd web
npm install
npm run dev
```

Otwórz http://localhost:3000. Aplikacja czyta dane z `web/src/data/demo/` —
działa od razu, bez żadnej konfiguracji.

### 2. Pipeline (odświeżanie danych)

Wymaga Pythona 3.12+. Jednorazowo:

```
cd pipeline
pip install -r requirements.txt
```

Pobranie historii meczów (tu: Premier League, do 250 meczów — trwa ok. godziny,
bo szanujemy limity źródła; można przerwać i wznowić, nic nie pobiera się dwa razy):

```
python -m footstats.jobs.backfill --league EPL --season 25/26 --max-matches 250
```

Przeliczenie modelu i wygenerowanie danych dla aplikacji:

```
python -m footstats.jobs.build_demo
```

**Ważne:** pipeline uruchamiaj tylko na swoim komputerze (domowe IP), nie na
serwerze w chmurze — źródło danych blokuje ruch z chmur.

### 3. Testy modelu

```
cd pipeline
python -m pytest tests/
```

## Tryb pokazowy vs sezon

Jest lipiec 2026 — przerwa między sezonami (trwa MŚ). Dlatego aplikacja działa
w **trybie pokazowym**: statystyki zawodników są prawdziwe (Premier League
2025/26), ale mecze „nadchodzące" to ostatnia kolejka sezonu, a kursy są
przykładowe. Wszystko jest wyraźnie oznaczone w aplikacji.

**Po starcie sezonu 2026/27 (sierpień):**

1. backfill zaciągnie nowe kolejki tą samą komendą,
2. kursy na nadchodzące mecze wpiszesz ręcznie (Superbet/Betclic/STS) — format
   i job scoringu przygotujemy wtedy; schemat bazy (`supabase/migrations/`)
   już na to czeka,
3. model przeliczy okazje na prawdziwych liniach.

## Wdrożenie na Vercel + Supabase (gdy będziesz gotowy)

1. **Supabase**: załóż projekt na supabase.com (darmowy plan wystarczy),
   w SQL Editor wklej zawartość `supabase/migrations/0001_init.sql`.
2. **Vercel**: `npm i -g vercel`, potem `cd web && vercel` (projekt jest na to
   gotowy; katalog główny aplikacji: `web`).
3. Pipeline zostaje na Twoim komputerze i wypycha wyniki do Supabase
   (job `push_supabase` dopiszemy przy podpinaniu bazy — aplikacja ma warstwę
   danych przygotowaną na podmianę źródła).

Darmowe plany Vercel (Hobby) i Supabase (Free) w zupełności wystarczą.

## Co oznaczają wskaźniki

| Wskaźnik | Znaczenie |
|---|---|
| **szansa wg modelu** | prawdopodobieństwo zdarzenia policzone z historii, minut, rywala i sędziego |
| **kurs mówi** | prawdopodobieństwo „wpisane" w kurs bukmachera, po zdjęciu jego marży |
| **uczciwy kurs** | kurs, jaki powinien być przy szansie modelu (odwrotność szansy) |
| **przewaga (p.p.)** | różnica: szansa modelu − szansa z kursu, w punktach procentowych |
| **wartość (+%)** | ile średnio zarabia ten zakład na 100 zł w długiej serii |
| **pewność** | ile danych i jak stabilnych stoi za predykcją |
| **ryzyko** | jak kapryśne jest samo zdarzenie (rzadkie = loteria) |
| **CLV** | czy Twój kurs był lepszy niż kurs tuż przed meczem (dodatni = wyprzedzasz rynek) |

## Bezpieczniki modelu (dlaczego okazji jest mało)

System celowo **odrzuca** typy, gdy: model drastycznie nie zgadza się z rynkiem
(to zwykle rynek wie więcej), widełki szansy są za szerokie (za mało danych),
kurs jest poniżej 1,30 lub powyżej 6,00, a dla rzadkich zdarzeń (strzały głową,
spalone) wymaga wyraźnie większej przewagi. Kilkadziesiąt solidnych okazji
tygodniowo to zdrowy wynik — setki „okazji" oznaczałyby zepsuty model.
