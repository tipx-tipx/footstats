# Lista dnia: jedna publikacja dziennie + realny limit

**WDROŻONE 2026-08-14** (decyzja właściciela: „akceptuję wszystko").
Wszystkie liczby z produkcyjnej księgi (`typy_log`, epoka ligowa).

Co weszło do kodu — skrót dla czytającego za miesiąc:

| rzecz | gdzie | wartość |
|---|---|---|
| doba produktowa 6:00 → 6:00 | `build_wc_fast.dzien_listy` + `kluczDnia` we froncie | `GODZINA_DOMKNIECIA = 6` |
| zamrożenie listy dnia | `domknij_dni`, manifest w Supabase (`lista_dnia`) | raz na dobę |
| limit dzienny | `LISTA_CAP` | 12 |
| limit z meczu / rynku / pasma / rodziny | `LISTA_PER_*` | 3 / 4 / 4 / 4 |
| naprawa przecieku limitów | kolejność w `wybierz_liste_publikowana` | wznowione pierwsze |
| jedna miara wejścia i kolejności | `_klucz_listy` → `moc_listy` | — |

⚑ **Jedna rzecz wyszła w trakcie wdrożenia i zmienia obietnicę z tego
dokumentu** — patrz „Czego ten dokument nie przewidział" na końcu.

---

## Punkt wyjścia: dziś oba mechanizmy tylko UDAJĄ, że działają

```
LISTA_CAP = 20          deklarowany limit typów na dzień
mediana realna    67    (ostatnie 12 dni; 13.08 doszło do 185)
LISTA_PER_MECZ = 2      deklarowany limit typów z jednego meczu
maksimum realne   16    (po wprowadzeniu limitu, nie przed)
```

**Dlaczego przecieka:** limity sprawdzają się tylko dla NOWYCH wejść, a typ raz
pokazany wchodzi zawsze i jedynie podbija licznik. Ponieważ kandydaci są
sortowani wg siły, mocny nowy typ jest przetwarzany PRZED wznowionymi i wchodzi,
zanim licznik urośnie. Dzień zbiera typy przez kilkanaście cykli i 3–4 dni
horyzontu, więc rośnie w nieskończoność.

To jest ta sama klasa błędu co wcześniejsze „wznowione omijały bramy": reguła
postawiona przy narodzinach typu zamiast przy dumpie.

---

## 1. Czym jest „dzień" — doba produktowa 6:00 → 6:00

⚑ **To musi być rozstrzygnięte pierwsze, bo wszystko inne od tego zależy.**

Rozkład godzin gwizdka (czas polski, 862 typy):

```
00:00–04:00   355 typów  (41,2%)   <- Ameryka Płd.
13:00–17:00   103 typy
18:00–23:00   404 typy
```

**41% naszych typów to mecze grane między północą a 4:00 rano.** Przy dobie
kalendarzowej „lista na piątek" domykana o 6:00 w piątek zawierałaby mecze,
które zaczęły się o 2:00 w nocy — czyli cztery godziny wcześniej.

**Propozycja:** dzień listy D = mecze od **6:00 dnia D do 6:00 dnia D+1**.
Klient wchodzi rano i widzi komplet tego, co realnie może dziś obstawić:
europejskie wieczory i południowoamerykańską noc.

**Czego NIE ruszamy:** `rozliczanie.dzien_pl` (doba kalendarzowa) zostaje
definicją dla rozliczeń, Skuteczności i archiwum. Zmiana tamtej definicji
przestawiłaby całą historię — a raz już mieliśmy 11% typów pod złą datą, gdy
doba liczyła się strefą maszyny.

**Konsekwencja do zaakceptowania:** mecz o 2:00 w nocy z piątku na sobotę jest
na liście **piątkowej**, a w Skuteczności pod datą **sobotnią**. Dwie różne
jednostki, każda poprawna w swoim miejscu — ale trzeba to nazwać w interfejsie,
bo inaczej wygląda jak błąd.

---

## 2. Zamrożenie: jedna publikacja dziennie

**Reguła:** o 6:00 (pierwszy cykl po tej godzinie) lista dnia D domyka się.
Od tej chwili **skład się nie zmienia** — nic nie dochodzi i nic nie znika.

**Co dalej wolno zmieniać po domknięciu** (bo to informacja o zakładzie, nie
zmiana listy):

* aktualny kurs obok zamrożonego („płaciło 1,85, teraz 1,62"),
* status meczu: odwołany, przełożony, zawieszony rynek,
* potwierdzona absencja zawodnika,
* rozliczenie po gwizdku.

**Ile to kosztuje** — typy, które powstałyby po domknięciu:

| godzina domknięcia | nie zdąży | jakie są te typy |
|---|---|---|
| **6:00** | 161 z 862 (18,7%) | ROI −6,5% |
| 10:00 | 138 (16,0%) | – |
| 14:00 | 109 (12,6%) | – |
| (dla porównania: te, które zdążyły) | 320 rozliczonych | ROI −2,6% |

**Zamrożenie jest neutralne dla wyniku, a nie kosztowne.** Typy powstające po
granicy wypadają nawet nieco gorzej niż te, które zdążyły (−6,5% wobec −2,6%),
choć przy n=99 ta różnica mieści się w szumie. Argumentem za zamrożeniem jest
więc produkt i uczciwość pomiaru, nie ROI — ale **nie płacimy za nie wynikiem**.

⚑ Uczciwa nota: mój pierwszy rachunek dawał 6% i twierdził, że przepadają
NAJLEPSZE typy (+7,8%). Był liczony granicą „6:00 dnia meczu" w dobie
kalendarzowej, która dla 41% typów (mecze nocne) wypada już PO gwizdku.
Po poprawieniu granicy wniosek się odwrócił.

**Dni przyszłe:** lista na jutro i pojutrze zostaje „zapowiedzią" — może się
uzupełniać aż do swojego domknięcia. Horyzont 3–4 dni zostaje bez zmian
(decyzja z 07.08), zmienia się tylko to, że dzień bieżący jest zamknięty.

---

## 3. Limit dzienny: ile typów naprawdę

Symulacja na 419 rozliczonych typach: dzień dostaje twardy budżet, wybór wg
kolejności „polecane" (`moc_listy`).

| wariant | n | trafia | luka | ROI brutto | ROI netto | wynik na 10 zł/typ |
|---|---|---|---|---|---|---|
| dziś (limit nie działa) | 419 | 60,1% | −10,8 pp | −3,5% | −15,1% | −633 zł |
| **10 typów/dzień** | 91 | 74,7% | −7,6 pp | **+1,7%** | −10,5% | −96 zł |
| **15 typów/dzień** | 128 | 73,4% | −7,1 pp | **+1,2%** | −10,9% | −140 zł |
| 20 typów/dzień | 162 | 71,6% | −7,7 pp | −0,7% | −12,6% | −204 zł |
| 30 typów/dzień | 222 | 68,0% | −10,3 pp | −3,4% | −15,0% | −333 zł |

**Kontrola, czy to nie jest zwykłe „mniej zakładów = mniej straty":** przy tym
samym n=91, ale wybranym z DOŁU kolejności, ROI to **−19,4%**. Rozpiętość
21 punktów przy identycznej liczbie zakładów — czyli kolejność realnie
odróżnia dobre typy od złych, a limit jest tym, co pozwala z tego skorzystać.

**Dwa uczciwe zastrzeżenia:**

1. To jest **sufit, nie obietnica**. Symulacja wybiera spośród typów, które
   dotrwały do rozliczenia, i zna ich siłę z góry. W realnym cyklu wybieramy
   z tego, co istnieje o 6:00, więc wynik będzie słabszy.
2. **Netto dalej jesteśmy pod kreską** (−10,5% przy limicie 10 wobec −15,1%
   dziś). Limit zabiera dwie trzecie straty, nie czyni produktu zyskownym.
   Do zera po podatku potrzeba zwrotu brutto powyżej +13,6%.

**Rekomendacja: 12 typów na dobę produktową.** Leży w obszarze, gdzie zwrot
brutto jest dodatni (10–15), a lista jest na tyle duża, że klient ma z czego
wybierać. Zaczynamy od 12 i korygujemy z pomiaru, nie z gustu.

---

## 4. Różnorodność w ramach limitu

Przy 12 miejscach dziennie proporcje z dzisiejszych limitów przestają pasować
(dziś: 6 na rynek przy deklarowanym 20). Propozycja:

| limit | dziś | proponowany | dlaczego |
|---|---|---|---|
| typów na dzień | 20 | **12** | patrz wyżej |
| z jednego meczu | 2 | **3** | mecze bogate w typy są naszym najlepszym materiałem (luka −5,3 pp wobec −13,3 pp), ale 5 typów z jednego meczu to 40% listy |
| z jednego rynku/strony | 6 | **4** | żeby 12 pozycji nie było dwunastoma „rożnymi poniżej" |
| z jednego pasma kursu | 6 | **4** | tanie i drogie typy mają zostać obok siebie |
| na zawodnika | 1 | **1** | bez zmian |

**Co z resztą:** wszystko, co nie zmieściło się w budżecie, idzie tam gdzie
dziś — do puli generatora kuponów i do rozliczeń w tle. Nic nie znika
z pomiaru i nic nie przestaje uczyć modelu.

---

## 5. Pułapki wdrożenia, które trzeba obsłużyć

1. **Cron nie chodzi punktualnie.** Deklaruje co 15 minut, realnie odpala co
   ~1–1,5 h. „O 6:00" musi znaczyć „pierwszy cykl po 6:00", a moment domknięcia
   zapisujemy w manifeście — inaczej nie da się później odtworzyć, co i kiedy
   zostało zamrożone.
2. **Manifest musi przeżyć padnięty odczyt Supabase.** Zapis przez
   `put_key_bezpiecznie`; nieudany odczyt = pracujemy bez zmian, nie
   nadpisujemy dnia garstką typów z jednego cyklu.
3. **Zamrożenie rozwiązuje problem znikania typów** — a ten sam mechanizm
   („typ raz pokazany zostaje") jest dziś powodem, dla którego limity
   przeciekają. Po wdrożeniu limit stosuje się RAZ, przy domknięciu, więc
   znikanie przestaje być możliwe bez dodatkowej reguły.
4. **Zmiana wersji modelu w środku dnia.** Dziś typ z poprzedniej wersji nie
   wznawia się (brama kolizji). Przy zamrożonej liście: lista bieżącego dnia
   zostaje nietknięta do końca dnia, nowa wersja obowiązuje od najbliższego
   domknięcia. Inaczej klient traci sprzed nosa typ, który mógł zagrać.
5. **Pusta lista dnia.** Gdyby o 6:00 kandydatów było mniej niż budżet, dzień
   zostaje krótszy — nie dobieramy później. To jest cena obietnicy i trzeba ją
   nazwać wprost w interfejsie.

---

## Decyzje właściciela (14.08)

1. **Doba produktowa 6:00 → 6:00** — tak.
2. **Godzina domknięcia: 6:00.**
3. **Rozmiar listy: 12.**
4. **Dni przyszłe: zapowiedź**, uzupełnia się do swojego domknięcia; front
   mówi to wprost („lista zamknięta" / „jeszcze się uzupełnia").

---

## ⚑ Czego ten dokument nie przewidział

Przy wdrażaniu wyszło coś, co **zmienia obietnicę z części 3**, i musi to tu
stać, bo inaczej za miesiąc ktoś zacytuje tamtą tabelę jako obietnicę zysku.

**Cały efekt „limit poprawia zwrot" pochodzi z KOLEJNOŚCI, nie z limitu.**
Symulacja powtórzona z tą samą liczbą typów, ale bez premii za bogaty mecz:

```
limit 10, bez premii   ROI brutto -4,9%      z premią  +1,7%
limit 12, bez premii   ROI brutto -3,2%      z premią  -0,2%
limit 15, bez premii   ROI brutto -3,5%      z premią  +1,2%
```

Sam limit nie daje nic (−3,2% wobec −3,5% dziś). Działa dopiero to, KTÓRE 12
typów wybierzemy.

**A premii nie da się wiarygodnie nastroić.** Przy n=107 wynik skacze od
−2,7% do +2,4% w zależności od arbitralnie wybranego progu i siły premii —
to jest dopasowanie do szumu. Dlatego:

* próg wzięty jest z **luki kalibracji**, nie z ROI (stabilna miara: przy 10+
  kandydatach luka spada z ~−20 pp do −9 pp i lepiej),
* premia została na 1,10, w skali pozostałych premii, i **nie jest strojona**,
* liczba kandydatów liczy się z puli **przed selekcją** — inaczej powstałoby
  błędne koło (kolejność zależy od listy, lista od kolejności) i przeciek
  informacji z przyszłości w samym pomiarze.

**Czego nie wiemy:** kontroli „bogaty mecz kontra liga" NIE DA SIĘ dziś
przeprowadzić — mecze z 20+ kandydatami to niemal wyłącznie Brasileirão
i Liga Profesional, a te z kilkoma to egzotyka. Sygnał może więc znaczyć
„mecz, o którym mamy dużo danych" albo po prostu „liga, którą dobrze
pokrywamy". Obie interpretacje prowadzą do tej samej kolejności, ale przy
zmianie pokrycia lig trzeba to przemierzyć.

**Wniosek do zapamiętania:** limit 12 wdrażamy dlatego, że produkt ma być
przewidywalny i zgodny z tym, co deklaruje (dziś: mediana 67 przy
deklarowanych 20), a nie dlatego, że podnosi zwrot. Poprawa zwrotu jest
hipotezą do sprawdzenia na nowych rozliczeniach — nie obietnicą.
