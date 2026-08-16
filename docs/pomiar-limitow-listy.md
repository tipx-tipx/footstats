# Czy nadmiar ponad limit listy szkodzi — i czy naprawa limitów coś da

**Pomiar z 16.08.2026.** Narzędzie: `pipeline/scripts/pomiar_limitow_listy.py`.
Pytanie postawione po tym, jak kontrola startowa pokazała, że limity
różnorodności nie trzymają: doba zbudowana w całości pod limitami ma **8 typów
z jednego rynku przy limicie 4**, doba domknięta — 24. Log cyklu mówi to zresztą
wprost: „Lista wg doby produktowej … *(w tym 96 pokazanych wcześniej — te
wchodzą poza limitem)*", czyli 96 z 99 typów.

## ⚑ WNIOSEK: NAPRAWA NIE MA POKRYCIA W WYNIKU

Pierwsze przybliżenie wyglądało jednoznacznie i **było mylące**. Na całej
bieżącej epoce (865 rozliczeń z zamrożonych list):

```
limit dzienny 12     w limicie -3,6%   ponad -0,5%    w szumie
limit rynek 4        w limicie +3,1%   ponad -6,6%    nadmiar szkodzi
limit mecz 3         w limicie +1,5%   ponad -9,6%    nadmiar szkodzi
```

Kontrola segmentowa tego nie obaliła (w obrębie tego samego `rynek|strona`
nadmiar wypada o 19,2 pp gorzej), ale **kontrola epok — tak**.

## Dlaczego pierwsza liczba kłamała

Podział na połowy próby wypada **06.08**, czyli przed naprawą znaku kalibracji
(11.08) i przed naprawą priora (13.08). Pierwsza połowa opisuje produkt,
którego już nie ma. Znak się między połowami odwraca:

```
LIMIT NA RYNEK      wcześniejsza połowa  różnica luki  +3,4 pp
                    późniejsza połowa                 -12,1 pp
LIMIT NA MECZ       wcześniejsza połowa                -6,7 pp
                    późniejsza połowa                  +3,6 pp
```

To jest dokładnie ten test, który 12.08 obalił rekomendację „okno zgody
16 → 30 pp" (`docs/pomiar-bramy-i-kolejnosc.md`).

Rozbicie po EPOKACH produktu, a nie po połowie:

```
LIMIT NA RYNEK      < 11.08          331 / 370   różnica luki   -4,1 pp
                    11-13.08          59 /  38                 -15,4 pp
                    >= 13.08          59 /   8   za mała próba
LIMIT NA MECZ       < 11.08          490 / 211                  -2,5 pp
                    11-13.08          71 /  26                  -0,2 pp
                    >= 13.08          63 /   4   za mała próba
```

Limit meczowy w nowszej epoce daje **zero**. Limit rynkowy trzyma znak, ale
próba „ponad limitem" to 38 typów.

## Symulacja: co naprawa zrobiłaby z bilansem

Limit liczony skumulowanie na dobę (kto pierwszy, ten zostaje):

```
CAŁA EPOKA (zdominowana przez produkt sprzed napraw)
   dziś           865 typów   ROI  -1,6%    -136 zł
   po naprawie    398 typów   ROI  +3,7%    +146 zł     bilans +282 zł

TYLKO PO NAPRAWIE ZNAKU (mecze od 11.08) — czyli DZISIEJSZY produkt
   rynek + mecz:  dziś 164 / +8,8% / +145 zł
                  po naprawie 111 / +8,1% / +90 zł      bilans  -55 zł
                  odcięte      53 / +10,4%              <- LEPSZE od zostających
   sam rynek:     po naprawie 118 / +10,8% / +128 zł    bilans  -17 zł
                  odcięte      46 / +3,7%, luka -9,6    <- gorzej skalibrowane
```

**W dzisiejszym produkcie naprawa nie dokłada pieniędzy — odejmuje.** Lista ma
dziś dodatni zwrot, więc obcięcie 28–32% wolumenu obniża bilans, nawet gdy
odcięte typy są nieco gorsze. Różnice mieszczą się przy tym w szumie (±4,4 pp
przy 164 rozliczeniach).

## Co z tego zostaje

1. **Nie naprawiać limitów pod hasłem zysku.** Liczba, która to obiecywała
   (+282 zł), pochodzi z produktu sprzed naprawy znaku kalibracji.
2. **Limit MECZOWY nie ma pokrycia w ogóle** — w nowszej epoce odcinałby typy
   lepsze od zostających (ROI +10,4% wobec +8,1%).
3. **Limit RYNKOWY ma sens jakościowy, nie finansowy**: odcięte typy są gorzej
   skalibrowane (luka −9,6 pp wobec −3,9 pp), ale ich zwrot jest dodatni.
   To jest ta sama sytuacja co przy limicie dziennym 14.08 — „limit nie
   poprawia zwrotu, poprawia go kolejność".
4. **Sprawa pozostaje PRODUKTOWA:** kod deklaruje gwarancję różnorodności,
   której nie dotrzymuje (55% strony to dwa rynki). Naprawa dla porządku jest
   uzasadniona — ale trzeba wiedzieć, że skróci listę o ~30% bez zysku, i tak
   ją sprzedawać.
5. **Wrócić po ~100 rozliczeniach z epoki po 13.08.** Dziś jest ich 8 ponad
   limitem rynkowym — na tym nie da się rozstrzygnąć niczego.
