# Czy to model, czy strzelanie — pomiar z 2026-08-07

Pytanie właściciela: „czy wybierany typ to przemyślana analiza, czy heurystyki
i strzelanie? czy model uczy się na tym, co mu nie wychodzi?".

Odpowiedź poniżej stoi na dwóch niezależnych nogach: **pomiarze na 1534
rozliczonych typach** bieżącej epoki i **przeglądzie kodu**. Obie mówią to samo.

## 1. Model NIE strzela — porządkuje typy

| prognoza | Brier ↓ | log-loss ↓ | AUC ↑ |
|---|---:|---:|---:|
| nasza (`p_model`) | 0,2257 | 0,6514 | **0,731** |
| sam kurs bukmachera | **0,2034** | **0,5934** | **0,749** |
| stała „nic nie wiemy" | 0,2489 | 0,6908 | 0,500 |

AUC 0,731 przy 0,500 dla rzutu monetą to twardy dowód, że nasza liczba niesie
informację. Widać to też w krzywej: im wyżej deklarujemy, tym częściej wchodzi.

| deklarujemy | n | trafia | luka |
|---|---:|---:|---:|
| 0–50% | 386 | 29,3% | −10,7 |
| 50–60% | 213 | 39,4% | −15,6 |
| 60–70% | 198 | 47,0% | −18,2 |
| 70–80% | 275 | 61,1% | −13,8 |
| 80–90% | 295 | 76,3% | −8,6 |
| 90%+ | 167 | 81,4% | −12,7 |

Kolejność jest zachowana bez wyjątku — ale **każdy wiersz jest przeszacowany**.
Średnio deklarujemy 66,1%, a trafiamy 53,4%.

## 2. Ale prawie cała ta wiedza pochodzi z kursu

Test rozstrzygający: bierzemy typy o **tej samej cenie** i pytamy, czy nasza
liczba odróżnia te, które wejdą, od tych, które nie wejdą.

| segment | n | AUC ponad kurs | ROI |
|---|---:|---:|---:|
| wszystko | 1534 | 0,530 | −7,5% |
| drużynowe | 1375 | 0,516 | −6,1% |
| zawodnicze | 159 | **0,476** | −19,9% |
| `team_corners` | 577 | **0,499** | −6,3% |
| `team_goals` | 507 | 0,515 | −7,2% |
| `shots` | 118 | **0,592** | −6,5% |
| `team_cards` | 63 | **0,596** | +1,9% |
| mecz w ciągu doby | 423 | 0,545 | −1,5% |
| mecz dalej niż doba | 952 | 0,500 | −8,1% |

0,5 znaczy „przy tej cenie nasza liczba nie wnosi nic". Na największym rynku
(rożne drużynowe, 577 typów) mamy **dokładnie zero**. Wyjątki, gdzie realnie coś
wiemy: kartki drużyny i strzały — obie na małej próbie, obie warte uwagi.

To pokrywa się z pomiarem, który system robi sam i **ignoruje**: optymalna waga
naszej liczby wobec kursu wychodzi `w* = 0,00` (`rozliczanie.py`,
`waga_rynku_pomiar`) — a mimo to publikujemy `p_model`, nie cenę.

## 3. Uczenie DZIAŁA, ale uczy się tylko jednej rzeczy

Na 1071 typach ze stemplem korekty da się odtworzyć liczbę sprzed uczenia:

| | Brier ↓ | log-loss ↓ | średnia deklaracja |
|---|---:|---:|---:|
| przed korektą | 0,2377 | 0,6871 | 72,3% |
| po korekcie | **0,2184** | **0,6326** | 66,2% |

(realna trafialność w tej grupie: 54,1%)

Czyli warstwa ucząca się **realnie poprawia prognozę** i ściąga przeszacowanie
o 6 punktów. To nie jest atrapa. Ale uczy się **wyłącznie przesunięcia**: jednej
liczby w górę lub w dół, per rynek, przedział szansy i strumień.

## 4. Czego model NIE robi (przegląd kodu)

* **Zero uczenia zależności.** W całym projekcie nie ma ani jednej regresji,
  dopasowania wag cech ani strojenia parametrów per liga. Brak `sklearn`,
  `scipy.optimize.minimize`, `xgboost` itd. — jedyne dopasowania to średnia
  drużyny i bisekcja licząca przesunięcie.
* **Cała warstwa kontekstu to ręczne mnożniki**, których nikt nigdy nie
  porównał z wynikiem: dom/wyjazd `1,06` / `0,94` (`context.py:175`), tempo
  `0,35 × odchylenie` (`context.py:227`), styl rywala `0,45 / 0,35 / 0,25`
  (`matchup.py:172-186`), mostki między rynkami (`build_wc_fast.py:4482`),
  wygaszanie koncesji 45 dni (`build_wc_fast.py:4472` — komentarz sam mówi
  „ZAŁOŻENIE… do kalibracji po rozliczeniach").
* **Sito, przez które przechodzi typ, jest w większości niezmierzone.**
  Najostrzejsze: widełki kurs/szansa (`betting.py:739`) — komentarz autora mówi
  wprost, że to założenie i że odrzuca ~1372 typy dziennie. „P ostrożne" to
  średnia arytmetyczna szansy i dolnego kwantyla (`build_wc_fast.py:4806`) —
  wygodna, ale bez uzasadnienia probabilistycznego.
* **Ranking i bonusy z palca**: `×1,15` za matchup, `×1,10` za rotację,
  `×1,12` za świeże składy (`build_wc_fast.py:5396-5415`). Zmierzone na
  rozliczeniach: typy z matchupem mają AUC ponad kurs **0,424** — czyli ten
  bonus działa w złą stronę.

## 5. Proporcje, uczciwie

Rdzeń probabilistyczny jest prawdziwy i dobrze napisany: rozkład Gamma-Poisson
z posteriorem ujemnym dwumianowym, wygaszanie czasowe, prior z poziomu ligi,
Skellam dla „kto więcej", dopasowanie momentów dla sum meczowych. To nie jest
zabawka.

Ale **struktura wyceny — co i o ile mnożymy — jest zamrożona w kodzie od dnia,
w którym ją wpisano, i żadne rozliczenie jej nie zmienia**. Uczy się tylko
poziom (średnia drużyny) i przesunięcie błędu. Stąd bierze się obraz z pomiaru:
kolejność typów jest sensowna, deklaracja jest zawyżona, a ponad cenę
bukmachera nie wnosimy prawie nic.

## 6. Co z tego wynika — trzy kierunki

1. **Zacząć strojić mnożniki kontekstu na rozliczeniach** zamiast trzymać je
   jako stałe. Najtańszy start: dom/wyjazd i sędzia — obie mają dość próby.
2. **Zastosować pomiar `w*`, który już liczymy** — mieszać naszą liczbę z ceną
   rynku zamiast publikować samą naszą. Dziś ten pomiar tylko się drukuje.
3. **Iść tam, gdzie mamy przewagę**: kartki drużyny (AUC ponad kurs 0,596,
   ROI +1,9%) i strzały (0,592). Rożne drużynowe, największy rynek, nie mają
   przewagi żadnej — i to one dają najwięcej strat.
