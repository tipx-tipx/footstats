# Co konkurencja robi w SILNIKU, czego my nie robimy

**16.08.2026.** Druga część analizy — nie o sprzedaży, tylko o tym, jak
poprawić **trafność, tworzenie typów i backend**. Materiał: parametry modelu,
które PredictStats i SmartBet wystawiają wprost w filtrach (to zdradza, na
czym liczą), zestawione z naszym silnikiem i z tym, co dziś o nim wiemy.

## Punkt wyjścia — nasze zmierzone problemy

```
luka deklaracji            -13 pp na wszystkich strumieniach
strona „powyżej"           ROI -12,0% (drużyny), -15,1% (zawodnicy)
strona „poniżej"           ROI  -3,1%   <- jedyna, która prawie wychodzi
model bije kurs            w 4 z 18 rynków — WSZYSTKIE to „poniżej"
luka to SELEKCJA           bias 1,00 na całym rozkładzie, 1,46 na górnych 5%
```

Każdą rekomendację niżej oceniam po tym, czy adresuje **te** liczby, czy
tylko dokłada podaży.

---

# 1. ⚑⚑⚑ POŁOWY MECZU — największa dźwignia, zero nowej matematyki

PredictStats ma we **wszystkich** modułach przełącznik:
`Okres: Cały mecz · 1. połowa · 2. połowa`. SmartBet ma `/stats/goals-halves`
i „gole do przerwy" wśród prognoz dnia.

**My nie mamy ani jednego rynku połówkowego.**

## Dlaczego to jest dźwignia na SKUTECZNOŚĆ, a nie tylko na podaż

W połowie meczu oczekiwana liczba zdarzeń jest z grubsza **połową** meczowej.
Nasz rozkład Poissona/NegBin liczy się tak samo — zmienia się wyłącznie λ.
Ale konsekwencja dla selekcji jest zasadnicza:

* przy λ = 10,7 rożnych na mecz linia bukmachera stoi ~9,5–10,5, a my
  typujemy „powyżej" tam, gdzie model widzi więcej;
* przy λ ≈ 5 na połowę linie schodzą na 4,5–5,5, gdzie **rozkład jest bardziej
  skośny**, a strona „poniżej" — ta jedyna, która u nas zarabia — staje się
  naturalnym wyborem znacznie częściej.

⚑ **To jest kierowanie podaży tam, gdzie mamy przewagę**, a nie próba
naprawienia strony „powyżej", która nie wychodzi od miesiąca.

## Co trzeba sprawdzić PRZED wdrożeniem

1. Czy statshub oddaje statystyki połówkowe (rożne/kartki/strzały per połowa).
   `docs/pomiar-49-pol` mówi, że mamy 49 pól, z których używamy pięciu —
   sprawdzić, czy któreś jest połówkowe.
2. Czy Superbet kwotuje rynki połówkowe dla rożnych/kartek (dla goli
   z pewnością tak).
3. **Kalibracja liczy się OSOBNO dla połówek** — inny reżim, inna λ; wrzucenie
   ich do wspólnego wiadra z rynkami meczowymi powtórzyłoby błąd
   „liczba zmierzona w jednym reżimie stosowana w przeciwnym".

---

# 2. ⚑⚑⚑ RUCH KURSU JAKO SYGNAŁ (ich „MoneyFlow") — mamy dane, nie używamy

PredictStats ma osobny płatny moduł **MoneyFlow** i „**Insider**" —
analizę ruchów rynku. BetLab sprzedaje to samo słowami: „We analyze suspicious
market moves for you. Get bets with the best information requiring fast
action."

**My zapisujemy `kurs_ref`, `kurs_ts`, `kurs_zamkniecia` i `clv_pct` przy
każdym typie — i używamy ich WYŁĄCZNIE jako pomiaru po fakcie.** Ruch kursu
nie wchodzi do decyzji o typie ani do rankingu.

## Dlaczego to jest istotne akurat u nas

Zmierzone: **nasza liczba bije kurs w 4 z 18 rynków**, a model „uczy się
wyłącznie przesunięcia" i ponad sam kurs wnosi 0,530 AUC (czyli nic).
Skoro kurs jest lepszym predyktorem niż my, to **jego RUCH niesie informację,
której nasz model nie ma z definicji** — bo powstaje z pieniędzy, a nie
z historii drużyny.

Trzy rzeczy do zrobienia, w kolejności:

1. **Zapisywać kurs otwarcia** (pierwszy widziany dla danej linii). Mamy
   `kurs_ts` i cenę z chwili publikacji, ale nie ma osobnego „otwarcia", więc
   nie da się policzyć dryfu.
2. **Zmierzyć, czy dryf przewiduje wynik** — czy typy, w których kurs poszedł
   w NASZĄ stronę między publikacją a gwizdkiem, trafiają lepiej. To jest
   pomiar do zrobienia z tego, co już mamy w `kurs_zamkniecia` i `clv_pct`.
3. Dopiero jeśli wyjdzie — wpiąć jako czynnik rankingu (nie jako bramę).

⚑ To jest jedyny sygnał z tej analizy, który jest **niezależny od naszego
modelu**. Wszystko inne, co liczymy, pochodzi z tej samej historii meczów.

---

# 3. ⚑⚑ 93% NASZYCH TYPÓW JEDZIE NA JEDNYM BUKMACHERZE

Sprawdzone w kodzie: scalanie ofert („gdy obaj kwotują tę samą linię, zostaje
WYŻSZY") działa **tylko w ścieżce zawodniczej** — `betclic.znajdz_zawodnika`
czyta `bc_odds["players"]`. Pamięć Betclica trzyma wyłącznie klucz `players`.

**Rynki drużynowe — czyli 93% naszego materiału — mają cenę z samego
Superbeta, bez porównania.**

PredictStats ma w narzędziach „Porównywarkę kursów", SmartBet reklamuje
„porównasz kursy".

## Ile to warte

Nasza zmierzona marża ściągania to 3,5–5,1%. Różnica ceny między bukmacherami
na tym samym zakładzie bywa 2–4 pp. Przy ROI **−5,7%** na liście dnia to nie
jest kosmetyka — to potencjalnie **jedna trzecia luki do zera**, i to bez
dotykania modelu.

**Do sprawdzenia (jeden pomiar, nie wdrożenie):** czy protokół Betclica
w ogóle wystawia rynki drużynowe (rożne/kartki/strzały drużyny), czy tylko
propsy zawodnicze. Jeśli tak — scalanie ofert dla drużyn jest tą samą funkcją,
którą już mamy napisaną.

⚑ To NIE jest sprzeczne z decyzją „Betclic tylko w drabinkach" — tamta
dotyczyła wpuszczania **nowych typów zawodniczych** po stronie „over".
Tu chodzi o **lepszą cenę tego samego typu**, który i tak publikujemy.

---

# 4. ⚑⚑ OKNO HISTORII JAKO PARAMETR — u nich user wybiera, u nas jest sztywne

Moduł rożnych PredictStats wystawia wprost:

```
Mecze:       5 · 10 · 15 · 20 · 25 · 30
Obliczanie:  na drużynę · na mecz
Sortuj po:   ostatnie H2H
Kierunek:    ponad · poniżej
```

To zdradza, że ich model liczy **prostą średnią z ostatnich N meczów** —
prostszą od naszej (wagi wykładnicze, tau 180 dni, prior grupowy, sufit
18 miesięcy). **Nie jest to powód do dumy, tylko do sprawdzenia:**

Nasze `tau = 180 dni` nigdy nie było zmierzone przeciw alternatywom. Mamy
teraz stempel `ess` przy każdym typie i pełną księgę rozliczeń — czyli
narzędzia, żeby policzyć, **które okno daje najlepszą kalibrację per rynek**.
Może się okazać, że dla kartek (zdarzenia rzadkie, zmienne przez sędziego)
lepsze jest okno 10 meczów niż półroczne wygaszanie.

To jest pomiar na jeden wieczór, z gotowym wzorcem: `pomiar_okna_uczenia.py`
robi dokładnie to samo dla okna korekty strumienia.

---

# 5. ⚑ RYNKI, KTÓRYCH NIE MAMY — i czy warto

PredictStats: Gole · BTTS · Kartki · Rożne · **Strzały** · **Faule** ·
**Remisy** · HT/FT Łamaki · 1X2 · Podwójna szansa.
SmartBet: to samo plus `corners-team`, `cards-team`, `shots-on-target`.

| rynek | mamy? | ocena |
|---|---|---|
| rożne, kartki, strzały, celne, faule (drużyna) | **tak** | to nasz rdzeń |
| gole drużyny | tak | |
| **połowy (1./2.)** | **nie** | ⚑ patrz pkt 1 — największa dźwignia |
| BTTS | nie | prosty, ale to rynek efektywny — bukmacher go zna |
| 1X2, podwójna szansa | nie | ⚑ NIE ROBIĆ: najefektywniejszy rynek świata, tam nie mamy czego szukać |
| HT/FT „łamaki" | nie | ciekawe, ale to rynek o bardzo niskiej trafności |
| remisy | nie | jw. |

⚑ **Wniosek: z całej ich listy jedno warte jest naszego czasu — POŁOWY.**
Reszta to albo rynki, gdzie bukmacher jest mocniejszy (1X2, BTTS), albo
egzotyka o niskiej trafności (HT/FT, remisy). Nie kopiować listy modułów —
skopiować JEDEN, który pasuje do naszej przewagi.

---

# 6. CZEGO U NICH NIE MA, A U NAS JEST (nie zepsuć tego)

* **kalibracja mierzona wstecz per rynek i przedział szansy**, z etykietami
  źródła (`wlasna` / `bez_proby` / `obca_epoka`);
* **korekta strumienia** i ściąganie deklaracji do ceny;
* **prior grupowy** liczony na 90 minut, z sufitem wieku historii;
* **stempel rachunku** przy każdym typie — pełna odtwarzalność wstecz;
* **podatek 12% w rachunku**, tryb zamrożony przy typie;
* **pomiar bram** (co zdejmują i czy zdejmują lepsze niż publikowane).

Żaden z trzech serwisów nie pokazuje ani jednej liczby o własnej kalibracji.
To znaczy albo jej nie mają, albo nie wytrzymuje pokazania.

---

# 7. KOLEJNOŚĆ PRAC — co realnie ruszy skuteczność

```
1. RUCH KURSU: dopisać kurs otwarcia + zmierzyć, czy dryf przewiduje wynik
   -> jedyny sygnał NIEZALEŻNY od naszego modelu           [pomiar: 1 wieczór]

2. DRUGI BUKMACHER DLA DRUŻYN: sprawdzić, czy Betclic wystawia rynki
   drużynowe; jeśli tak — scalić oferty (funkcja już istnieje)
   -> nie dotyka modelu, a wprost podnosi ROI              [pomiar + wdrożenie]

3. POŁOWY MECZU: sprawdzić dostępność danych i kursów, potem wdrożyć
   jako OSOBNY rynek z OSOBNĄ kalibracją
   -> kieruje podaż na stronę „poniżej", gdzie zarabiamy   [tydzień]

4. OKNO HISTORII PER RYNEK: zmierzyć 5/10/15/20/30 meczów przeciw
   dzisiejszemu tau=180 dni, per rynek
   -> może poprawić kalibrację bez nowych danych           [pomiar: 1 wieczór]
```

⚑ Punkty 1, 2 i 4 to POMIARY — dokładnie ten rodzaj pracy, który dziś trzy
razy zawrócił nas z drogi i oszczędził tygodnie. Ale w odróżnieniu od
dzisiejszych, każdy z nich ma po drugiej stronie **konkretne wdrożenie**,
a nie tylko „wiemy więcej".
