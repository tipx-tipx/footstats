# Ile pieniędzy zdejmują bramy i czy kolejność listy jest odwrócona

**Pomiar 2026-08-14**, źródło: produkcyjna księga `typy_log` (4594 wpisy),
epoka ligowa, wyłącznie rozstrzygnięte typy. ROI brutto, bez podatku od stawki
(podatek nie zmienia porównań między segmentami — obniża wszystkie o tyle samo).

Powód pomiaru: kolejka po audycie zalecała dwie rzeczy — limit **1 typ na mecz**
i nowy ranking, bo „dzisiejsze sortowanie jest odwrócone". Obie tezy stały na
114 rozliczeniach. Sprawdzenie na pełnej księdze dało wynik częściowo
przeciwny, a przy okazji odsłoniło rzecz ważniejszą od obu.

---

## 1. Bramy publikacji wyrzucają materiał lepszy niż to, co zostaje

Typ zdjęty bramą nie znika — rozlicza się „w tle" i uczy model, więc znamy
jego wynik. Zestawienie wg powodu zdjęcia:

| co się z typem stało | n | deklaruje | trafia | luka | ROI |
|---|---|---|---|---|---|
| **pokazany klientowi** | 419 | 70,9% | 60,1% | −10,8 pp | **−3,5%** |
| odrzucony / sugestia | 409 | 55,9% | 39,1% | −16,8 pp | −3,1% |
| rozjazd z rynkiem (okno zgody) | 274 | 79,0% | 62,4% | −16,6 pp | −3,0% |
| kwarantanna strony | 190 | 79,5% | 63,2% | −16,3 pp | −1,3% |
| poza listą dnia | 149 | 71,6% | 62,4% | −9,2 pp | **+1,2%** |
| kwarantanna rynku | 34 | 86,7% | 79,4% | −7,3 pp | **+10,3%** |
| leg kuponu | 28 | 78,5% | 57,1% | −21,3 pp | −13,8% |
| stare dane | 5 | 73,3% | 20,0% | −53,3 pp | −62,6% |

**Żadna z dużych bram nie zarabia.** Razem zdejmują 647 typów — więcej, niż
publikujemy — a to, co zostaje na stronie, wypada gorzej niż to, co odrzuciły.

Wyjątki, które faktycznie działają i **zostają**: `stare_dane` (−62,6% na
5 typach), `leg_kuponu` (−13,8%), `ujemna_po_korekcie` i
`kwarantanna_kategorii` (n=1–2, bez wniosku, ale kierunek zgodny).

### Zastrzeżenie metodologiczne

Bramy wybierają **nielosowo**: wstrzymują dokładnie to, co przed chwilą
traciło. Część przewagi typów „w tle" to więc zwykły powrót do średniej po
serii pecha. To jednak nie jest obrona kwarantanny, tylko zarzut wobec niej:
brama patrzy na okno 40 rozliczeń i wstrzymuje segment w chwili, gdy ten i tak
wraca do normy — a wypuszcza go, gdy zdąży się poprawić.

Mocniejszy jest przypadek okna zgody (`rozjazd_z_rynkiem`): dotyczy wszystkich
rynków i stron, nie reaguje na wyniki, a mimo to zdjęte przez nie typy dają
−3,0% wobec −3,5% na tym, co przepuściło. Ta brama po prostu nie odróżnia.

---

## 2. Bogactwo materiału meczu — najsilniejszy zmierzony sygnał

Podział typów wg tego, **ile typów model w ogóle wystawił w danym meczu**
(bez drabinek, które mają własną ekonomikę):

| typów w meczu | n | deklaruje | trafia | luka | ROI |
|---|---|---|---|---|---|
| 1 | 33 | 71,6% | 60,6% | −10,9 pp | +6,4% |
| 2–4 | 176 | 73,5% | 60,2% | −13,3 pp | **−6,7%** |
| 5 i więcej | 157 | 74,0% | 68,8% | **−5,3 pp** | **+8,3%** |

Mecz, o którym model ma dużo do powiedzenia, jest **dwa razy lepiej
skalibrowany**. Kubełek „1 typ" ma za małą próbę, żeby cokolwiek z niego
wnioskować.

### Cztery kontrole, które ten efekt przeżył

**Pasmo kursu** (mogłoby być tak, że bogate mecze to po prostu tanie typy):

| pasmo | 1 typ | 2–4 | 5+ |
|---|---|---|---|
| < 1,50 | −25,0% | +2,6% | **+10,3%** |
| 1,50–1,99 | za mało | −12,2% | **−0,7%** |
| 2,00+ | −18,6% | −21,4% | **+15,2%** |

Monotonicznie w 9 z 9 komórek.

**Horyzont publikacji** (mogłoby być tak, że bogate mecze są bliżej gwizdka):
do 12 h: −26,2 / −2,4 / **+7,2**; 12–36 h: −15,2 / −15,6 / **+5,8**;
36 h+: −35,1 / −9,2 / **+11,1**. Znowu monotonicznie.

**Liga** (mogłoby być tak, że to po prostu Brazylia): Liga Profesional
2–4 typy −38,5% wobec 5+ **+11,8%**; Brasileirão Série A 5+ **+11,9%**.

**Drabinki**: mecze z jednym typem to w 35% drabinki (ROI −26,6%). Po ich
odsianiu efekt zostaje — to właśnie tabela wyżej.

---

## 3. Czy kolejność listy jest odwrócona — NIE

Tercje 419 publikowanych rozliczeń wg różnych kryteriów sortowania
(góra = to, co klient widzi pierwsze):

| sortowanie | góra | środek | dół |
|---|---|---|---|
| **dzisiejsze (p × √kurs + premie)** | **+0,6%** | +0,5% | −11,6% |
| sama deklarowana szansa | +8,4% | −5,9% | −13,0% |
| **przewaga nad kursem (EV)** | **−7,4%** | +2,1% | −5,3% |
| sam kurs, wysoki na górę | −9,2% | −9,3% | +7,8% |
| deklarowana pewność | +3,5% | −3,9% | −10,2% |

Odwrócone było sortowanie **po przewadze nad kursem** — i to jest to samo,
które zdjęliśmy 13.08 razem z werdyktem o przewadze (`04ff875`). Dzisiejsza
kolejność ma kierunek poprawny: góra +0,6%, dół −11,6%.

Teza audytu („górna tercja −4,2% / −41,2%") stała na 114 rozliczeniach i
dotyczyła stanu sprzed naprawy znaku kalibracji. **Nie potwierdza się.**

---

## 4. Limit typów na mecz — brama martwa i przeciwskuteczna

Zalecenie audytu: 1 typ na mecz (dziś stała mówi 4).

* **Brama i tak nie działała.** W całej księdze (4594 wpisy) powód
  `limit_meczu` wystąpił **raz** — stoi na końcu łańcucha, więc wcześniejsze
  bramy zdejmowały typy przed nią.
* **Gdyby działała, kosztowałaby.** Zostawienie jednego typu z meczu (wg
  dzisiejszego rankingu) daje 143 zakłady o ROI −11,7% zamiast 419 o ROI
  −3,5%. Limit obcina segment 5+, czyli jedyny zarabiający.

---

## Co z tego weszło do kodu (2026-08-14)

1. **Kwarantanna rynku / strony / kategorii nie zdejmuje typu z listy**
   (`build_wc_fast.KWARANTANNA_ZDEJMUJE_Z_LISTY = False`). Zostaje jako pomiar,
   jako etykieta na karcie („ostrożnie z tym zakładem") i jako brama **w puli
   kuponów** — tam błąd pojedynczego lega mnoży się przez cały kupon.
2. **Kategoria w kwarantannie znów produkuje kandydatów.** Wcześniej
   „ambitniejsza linia" w kwarantannie przestawała w ogóle powstawać, więc
   znikała także z pomiaru i brama nie miała jak się nigdy odwrócić.
3. **Limit ekspozycji na mecz zdjęty z listy** (zostaje w puli kuponów).
4. **Bogactwo materiału meczu weszło do kolejności listy** (`moc_listy`,
   premia 1,10 od 5 typów w meczu). Liczone przy dumpie, więc obejmuje typy
   wznowione; front bierze gotową liczbę zamiast liczyć własną kopię formuły.

**Czego NIE ruszono:** okna zgody (`rozjazd_z_rynkiem`, 274 typy) — mimo że
pomiar mówi to samo co o kwarantannach. To osobna decyzja i osobna skala:
brama zdejmuje dziś 174 typy przed gwizdkiem, więc zmiana powinna iść własnym
pomiarem przed i po, nie razem z tą.

---

## 5. Okno zgody z rynkiem — dopisane 14.08 wieczorem

Ostatnia nieruszona brama. Dziś: typ wchodzi, gdy `p_model − implied(kurs)`
mieści się w **[0; 16 pp)**. Wycina więc dwie różne rzeczy naraz: typy poniżej
ceny rynku (dziś praktycznie nie powstają — 11 rozliczeń) i typy 16+ pp nad nią.

**Pełna skala rozjazdu** (wszystkie rozliczone, epoka ligowa):

| rozjazd | n | deklaruje | trafia | luka | ROI |
|---|---|---|---|---|---|
| 0–4 pp | 38 | 35,4% | 31,6% | −3,8 pp | **−24,8%** |
| 4–8 pp | 49 | 51,1% | 40,8% | −10,3 pp | −14,2% |
| 8–12 pp | 144 | 62,8% | 52,1% | −10,7 pp | −6,9% |
| **12–16 pp** (przy granicy) | 482 | 71,1% | 60,6% | −10,5 pp | −1,4% |
| 16–20 pp | 359 | 74,2% | 58,5% | −15,7 pp | −4,1% |
| 20–30 pp | 371 | 74,9% | 59,3% | −15,6 pp | **+6,3%** |
| 30+ pp | 64 | 65,4% | 18,8% | **−46,7 pp** | −23,8% |

Zwrot **rośnie** z rozjazdem aż do 30 pp — odwrotnie, niż zakłada brama.
Najgorszy segment (0–4 pp) brama przepuszcza, bo mieści się w oknie.
Kontrola po paśmie kursu: w **każdym** paśmie typy 16+ pp mają lepszy zwrot
niż te w oknie (−1,8% wobec −6,3% przy kursie 2,00+ itd.).

**⚑ Ale progu NIE wolno stawiać na ROI.** Podział rozliczeń na starszą
i nowszą połowę:

```
przedział       starsze ROI    nowsze ROI     luka starsze / nowsze
0-16 pp             -6,7%         -2,6%           -10,8 / -9,5     stabilne
16-20 pp            +2,8%         -9,7%           -11,0 / -19,4    ZNAK SIĘ ZMIENIA
20-30 pp            +4,7%         +8,4%           -14,5 / -17,1    stabilne
30+ pp             -55,1%        +14,0%           -53,6 / -38,3    ZNAK SIĘ ZMIENIA
```

Zwrot w tych przedziałach jest w dużej części szumem. **Stabilna jest luka** —
rośnie z rozjazdem monotonicznie, a przy 30+ pp wybucha (−53 i −38 pp w obu
połowach: model deklaruje 65%, wchodzi 19%).

**Rekomendacja:** górna granica 16 → **30 pp**, czyli tam, gdzie luka faktycznie
wybucha, a nie tam, gdzie ROI akurat wygląda korzystnie. Dolna zostaje.
Symulacja: 274 typy wracają, zwrot całości −3,3% wobec −3,5% dziś — czyli
**efekt na wynik jest znikomy**. To zmiana o różnorodność i o zgodność z zasadą
„nic nie blokujemy", nie o zysk. Przy limicie 12 typów na dobę te typy są
materiałem dla kolejności, a nie zalewem listy.

### ⚑ REKOMENDACJA WYCOFANA — sprawdzenie 13.08 przed wdrożeniem

Powtórzenie pomiaru na próbie większej o ~500 rozliczeń (1951 typów modelu)
**odwróciło przesłankę**. Granica 16 pp zostaje, nic nie zmieniamy.

| rozjazd | n | luka | ROI | luka starsze / nowsze |
|---|---|---|---|---|
| 8–12 pp | 271 | −9,6 pp | −4,9% | |
| **12–16 pp** (koniec okna) | 651 | **−8,8 pp** | +1,6% | −12,3 / −6,1 |
| 16–20 pp | 486 | **−19,3 pp** | −11,2% | −19,3 / −19,4 |
| 20–30 pp | 421 | **−16,4 pp** | +1,5% | −12,4 / −19,7 |

Luka za granicą jest **dwa razy głębsza** i trzyma się w obu połowach próby.
Kontrola po paśmie kursu daje to samo w **każdym** paśmie (16–30 pp: −15,0 /
−17,5 / −20,4 pp wobec −8,4 / −8,6 / −13,8 pp w oknie) — 12.08 wychodziło
odwrotnie i to była główna podstawa rekomendacji. Na najczystszym cięciu
(typy opublikowane po naprawie znaku i priorze): 12–16 pp luka **+0,6 pp**
przy ROI +15,7%, 16–20 pp luka **−21,9 pp** przy −20,3%.

**Skąd wzięła się tamta rekomendacja — usterka pomiarowa w części 5.**
Tabela „co zdejmują bramy" porównywała każdą bramę z ROI **wszystkiego**, co
publikowane. W tym zbiorze siedzi 94 drabinki o ROI −25,5%, a żadna z tych
bram nie zdejmuje ani jednej drabinki (0% w każdej grupie — drabinki mają
własne progi). Odniesienie było zaniżone o 2,3 pp:

```
                      ROI     wobec całości (-4,2%)   wobec tego samego materiału
rozjazd_z_rynkiem    -2,4%    „lepsze niż strona"      -1,9%  -> zdejmuje GORSZE
kwarantanna_strony   -4,3%     ~równo                  -1,9%  -> zdejmuje GORSZE
poza_lista_dnia      +4,2%    lepsze                   -2,0%  -> nadal lepsze
kwarantanna_rynku    +3,4%    lepsze                   +1,0%  -> nadal lepsze
```

Naprawione 13.08: `audyt_uczenia._odniesienie_skladem` liczy odniesienie
ważone składem strumieni danej bramy, tabela pokazuje rozbicie publikowanych
per strumień, a `tests/test_audyt_bramy.py` pilnuje obu kierunków (brama
zdejmująca gorsze nie krzyczy, zdejmująca lepsze — krzyczy dalej).

⚑ **To dotyczy także decyzji z 14.08 o kwarantannach** (część 1 tego
dokumentu). Przy poprawnym odniesieniu `kwarantanna_strony` zdejmowała
materiał **gorszy** od publikowanego (−4,3% wobec −1,9%), a nie lepszy —
argument za zdjęciem jej z listy był słabszy, niż wyglądał. `kwarantanna_rynku`
broni się dalej (+3,4% wobec +1,0%). Decyzja zostaje na produkcji do rozstrzygnięcia
przez właściciela — zmiana ma dopiero jeden dzień rozliczeń, więc dziś nic
nie potwierdzi ani nie obali jej skutku.

---

## Jak to odtworzyć

Skrypty pomiarowe (jednorazowe, w katalogu roboczym sesji): tercje rankingu,
pozycja typu w meczu, powody zdjęcia z publikacji. Wszystkie czytają
`supa.get_key("typy_log")` i filtrują `epoka == "liga"` oraz rozstrzygnięty
`wynik`. Kluczowe filtry, bez których liczby kłamią:

* **`epoka == "liga"`** — mundial karał strzały trzy razy naraz i miesza wynik
  (patrz `epoka-produktu-mundial-liga`),
* **publikowane** = brak `poza_publikacja`, `odrzucony`, `sugestia`,
* **drabinki osobno** (`ekran == "drabinki"`) — mają własną ekonomikę (−26,6%)
  i przy 35% udziale w meczach jednotypowych potrafią odwrócić wniosek.
