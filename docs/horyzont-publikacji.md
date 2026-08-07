# Horyzont publikacji — jak daleko przed meczem wolno typować

Pomiar z 2026-08-07, na żywej księdze (`typy_log`), 548 rozliczonych typów
drużynowych bieżącej epoki, tylko opublikowane (bez tła, bez sugestii).
Horyzont = liczba godzin między pokazaniem typu a gwizdkiem.

## 1. Wynik podstawowy

| horyzont | n | deklaruje | trafia | luka | ROI |
|---|---:|---:|---:|---:|---:|
| ≤24 h | 88 | 73,0% | 69,0% | −5,4 pp | **+7,8%** |
| 24–48 h | 109 | 73,8% | 65,4% | −8,4 pp | −2,6% |
| 48–72 h | 168 | 70,6% | 50,9% | −19,7 pp | **−19,4%** |
| 72 h+ | 183 | 66,6% | 56,0% | −10,6 pp | −1,4% |

W złotówkach, ostatnie 7 dni, stawka 10 zł na typ:

| okno | typów | wynik |
|---|---:|---:|
| ≤48 h | 132 | **+80,80 zł** (ROI +6,4%) |
| >48 h | 235 | **−274,00 zł** (ROI −12,0%) |

## 2. Cztery kontrole — efekt nie jest przebraniem czegoś innego

**Dzień meczu** (bo wiemy, że piątek i sobota grają w innym produkcie):

| grupa | n | luka | ROI |
|---|---:|---:|---:|
| piątek+sobota / ≤24 h | 26 | +3,1 | +17,1% |
| piątek+sobota / 24–48 h | 53 | −0,6 | +12,0% |
| piątek+sobota / >48 h | 102 | −4,7 | +10,3% |
| reszta tygodnia / ≤24 h | 62 | −4,3 | **+13,0%** |
| reszta tygodnia / 24–48 h | 56 | −16,0 | −16,9% |
| reszta tygodnia / >48 h | 249 | −18,9 | **−17,6%** |

Blisko meczu zarabiamy w OBU grupach dni. Część efektu „piątek+sobota"
to prawdopodobnie ten sam mechanizm w przebraniu — w weekend gramy bliżej.

**Rynek:** `team_corners` ≤24 h +33,0% wobec >48 h −23,1%; `match_corners`
+12,5% wobec −18,7%; `team_goals` najsłabiej (+5,2% wobec +0,4%).

**Pasmo deklarowanej szansy:** <70% → +14,9% (≤48 h) wobec −7,9% (>48 h);
≥70% → −1,2% wobec −12,0%. Czyli to nie jest znany problem pasma 55–70%.

**Pasmo kursu:** ≤48 h bije >48 h w każdym paśmie — <1,6 (−2,1 wobec −10,9),
1,6–2,3 (+8,8 wobec −24,9), 2,3+ (+24,1 wobec +0,5).

**Świeże 7 dni osobno:** ≤24 h +6,1% (n=55), 24–48 h +6,6% (n=77),
>48 h −12,0% (n=235).

## 3. Ta sama przyczyna, co migotanie listy

`superbet.list_events(days_ahead=8)` daje mecze na tydzień w przód, więc typ
powstaje nawet cztery dni przed gwizdkiem i przez cztery dni zajmuje miejsce na
liście, która ma 20 pozycji. Zmierzone 07.08: **45 żywych typów walczy o 20
miejsc, 35 z nich opublikowano dalej niż 48 h przed meczem**.

Selekcja listy (`build_wc_fast.py`, ~6275) sortuje typy wznowione razem ze
świeżymi i nie daje pierwszeństwa tym, które user już widział — w kluczu
sortowania jest `ma_rachunek`, a typ wznowiony z księgi jest „uproszczony",
więc systematycznie przegrywa. Efekt: z 45 kandydatów na stronie stoi 20
(17 świeżych, 3 wznowione), a **22 typy pokazane wcześniej są dziś poza
stroną** — 11 zdjął limit 6 na rynek, 7 limit dwudziestki, 4 limit 6 na pasmo
kursu. Do Skuteczności nadal się liczą, bo naprawdę były pokazane.

## 4. Podaż — czy przy oknie 48 h wystarczy typów

Gotowe typy dziennie (wszystkie / z meczem w oknie 48 h):

```
2026-08-04:  60 / 21      2026-08-06:  75 / 26
2026-08-05:  86 / 28      2026-08-07:  34 / 16
```

W chudych dniach sprzed poszerzenia okna zgody (01–03.08) było 9 / 9 / 3.
Dlatego okno musi mieć bezpiecznik podaży, a nie stać na sztywno.

## 5. MECHANIZMU NIE MA — okno 48 h ODRZUCONE (07.08 po południu)

Zarzut usera: „odległość meczu sama w sobie nic nie zmienia; pytanie, czy
analiza dalekiego meczu jest tak samo dopracowana". Sprawdzone i **zarzut jest
trafny** — korelacja z części 1 nie ma za sobą mechanizmu:

* **Nasza ocena się nie zmienia.** Dla 39 żywych typów porównano szansę
  zamrożoną przy publikacji ze świeżą wyceną tej samej linii z bieżącego cyklu:
  średnia zmiana **−0,5 pp** dla typów starszych niż 48 h (i +0,2 pp dla
  najświeższych). Model dzień przed meczem mówi to samo, co trzy dni wcześniej.
* **Kurs nie ucieka.** Średnia zmiana kursu od publikacji: **0,00**. Sześć
  z 45 typów zniknęło z oferty — to jedyny realny ubytek.
* **Rachunek dalekiego typu jest niewiele uboższy:** czynniki ≠ 1,00 średnio
  0,58 wobec 0,93 przy meczach do doby, matchup 17% wobec 27%, przedziały
  ufności tej samej szerokości (24–26 pp). Składów XI nie ma nigdzie (0%).
* **Pora meczu (region) nie tłumaczy:** mecze nocne −5,5%, dzienne −4,4%.
* **Pora publikacji nie tłumaczy:** cykl nocny −7,9%, dzienny −3,4%, a efekt
  horyzontu siedzi w obu.
* **Mecz rozegrany w międzyczasie** to jedyny znaleziony fizyczny mechanizm —
  i jest mały: 15 typów (4% dalekich), za to ROI **−41,0%**. Po ich odjęciu
  różnica zostaje (≤48 h +4,6%, >48 h −8,6%).

**Luka pomiarowa, którą trzeba zamknąć, zanim ktokolwiek wróci do tej tezy:**
typ awansowany z tła (kwarantanna, okno zgody) zachowuje `opublikowano_ts`
z czasu, gdy jeszcze nie był pokazany — więc w tym pomiarze wygląda na
„publikowany daleko", choć user zobaczył go tuż przed meczem. Z księgi nie da
się ich dziś odróżnić.

**Decyzja usera: nie skracamy horyzontu.** Trzy–cztery dni w przód zostają —
są potrzebne do kuponów długoterminowych i do szerszej perspektywy. Silna
korelacja bez mechanizmu i ze znaną luką pomiarową to za mało na blokadę
(zasada „nic nie blokujemy").

## 6. Co w zamian — WDROŻONE 07.08

1. **Limity listy liczą się per DZIEŃ MECZOWY** (`wybierz_liste_publikowana`).
   Typ na sobotę nie konkuruje z typem na poniedziałek.
2. **Typ raz pokazany wchodzi zawsze**, poza limitem — limity dotyczą wyłącznie
   nowych wejść, ale liczą też typy już stojące, żeby nowe nie dokładały
   przesytu.
3. Front dzielił listę na „dziś / jutro / dalsze dni" już wcześniej, więc
   dłuższa lista rozkłada się na sekcje (12 wierszy w dniu bieżącym i 3 na
   sekcję w dniach przyszłych, reszta pod „pokaż wszystkie").

Efekt na żywych danych (07.08, 45 kandydatów): lista **20 → 45 pozycji**,
wraca 25 typów, które user widział, **nie znika ani jeden**. Rozkład: piątek 5,
sobota 20, niedziela 18, poniedziałek 2. Skład: gole 17, rożne 12, kartki 10,
celne 5, strzały 1 — bez przesytu jednego rynku.

**Dry-run pełnego cyklu (07.08, 149 meczów) potwierdza:**

```
Lista publikowana: 59 z 86 kandydatów (na KAŻDY dzień meczowy max 20,
                   2/mecz, 6/rynek, 6/rodzinę)
Lista wg dnia meczu: 07.08 → 7, 08.08 → 21, 09.08 → 23, 10.08 → 3, 11.08 → 5
                   (w tym 30 pokazanych wcześniej — te wchodzą poza limitem)
Skład listy wg rodziny: goals 22, cards 14, corners 13, sot 6, shots 4
Do księgi jako 'poza publikacją': 27 świeżych typów (poza_lista_dnia)
```

Dni 08 i 09.08 mają po 21–23 pozycje, czyli ponad limit — to typy pokazane
wcześniej, które z założenia wchodzą poza limitem. Świeże wejścia dalej są
ograniczone do dwudziestki na dzień, a odcięte lądują w tle, nie w bilansie.

## 7. Co jeszcze warto zrobić z tym pomiarem

* **Zamknąć lukę stempla** — osobne pole „pierwszy raz pokazany", żeby awanse
  z tła nie udawały dalekich publikacji.
* **Cień wyceny dla wszystkich typów**, nie tylko przy potwierdzonym składzie
  (dziś 19 par, próg wiarygodności to 100). Wtedy pytanie „czy nasza świeższa
  ocena jest lepsza" rozstrzygnie się liczbą, a nie dyskusją.
* **Mecz w międzyczasie** — jedyny potwierdzony mechanizm; typ na mecz za trzy
  dni powinien być przeliczony po każdym meczu, który drużyna rozegra wcześniej.
