# Czy prognoza składu SportsGamblera jest dość dobra, żeby na niej stać

**Pomiar zamknięty 16.08.2026.** Narzędzie: `pipeline/scripts/pomiar_sklady_sg.py`.
Dane: zamrożony snapshot `docs/pomiar/sg-prognozy-2026-08-13.json` (730 meczów,
pobrany 13.08 o 12:16, **wyłącznie wpisy „Predicted"**), wyniki cząstkowe
w `docs/pomiar/sg-wyniki-2026-08-16.json`.

## Po co to było

Dla Ameryki Południowej i Skandynawii **nikt nie podaje nam składów**, a bez
wiedzy, kto wyjdzie w pierwszej jedenastce, typ na zawodnika jest loterią.
Zablokowany na tym jest cały strumień zawodniczy i drabinki.

Próg decyzyjny ustawiliśmy **wyraźnie powyżej 68,6%** — tyle daje własna
jedenastka liczona z rotacji minut, którą zmierzyliśmy i odrzuciliśmy
(`docs/pomiar-wlasna-jedenastka.md`). Źródło zewnętrzne ma sens tylko wtedy,
gdy bije to, co już umiemy sami.

## Wynik

```
meczów: 64,  pozycji składu: 1408
trafionych: 1065  =  75,6%   (szum 1,1 pp)
próg:                68,6%
                    ------
                     +7,0 pp,  czyli sześć razy własny szum
```

**Próg pobity.** Prognoza SportsGamblera jest wyraźnie lepsza od naszej własnej
jedenastki z minut i nadaje się jako podstawa dla strumienia zawodniczego.

## ⚑ Czego ta liczba NIE mówi — najsłabiej jest tam, gdzie najbardziej potrzeba

Rozbicie per rozgrywki (min. 3 mecze):

| rozgrywki | mecze | trafność |
|---|---:|---:|
| Pro League (Belgia) | 5 | 87,3% |
| Eredivisie (Holandia) | 5 | 85,5% |
| 2. Bundesliga (Niemcy) | 9 | 84,8% |
| Liga Portugal | 3 | 84,8% |
| Allsvenskan (Szwecja) | 5 | 81,8% |
| Championship (Anglia) | 4 | 79,5% |
| Brasileirão Série A | 3 | 75,8% |
| Russian Premier League | 4 | 70,5% |
| MLS (USA) | 6 | 69,7% |
| Liga MX (Meksyk) | 3 | 69,7% |
| **Liga Profesional (Argentyna)** | **5** | **62,7%** |
| LaLiga 2 (Hiszpania) | 4 | 60,2% |
| Trendyol Süper Lig (Turcja) | 4 | 56,8% |

**Argentyna wypada PONIŻEJ progu** — a to jest dokładnie ta liga, dla której
szukaliśmy źródła. Europa Zachodnia, gdzie wynik jest znakomity, ma składy
także z innych źródeł, więc tam SportsGambler niczego nie odblokowuje.

Próby per liga są jednak małe (3–9 meczów, szum rzędu 5–10 pp), więc **to jest
sygnał, nie wyrok**. Przed wpięciem w produkcję trzeba dobić próbę Ameryki
Południowej.

## Ograniczenia pomiaru

* **Sufit 77%** — tyle meczów paruje się ze statshubem jednoznacznie (565
  z 730). Reszta to skróty w rodzaju „Argentinos Jrs" czy „Newell's OB".
* **Zmierzono 64 mecze z 167 kandydatów**; 103 to mecze z 17–18.08, jeszcze
  nierozegrane w chwili pomiaru. Drugi przebieg tego samego dnia dołożył zero
  — narzędzie wznawia się z pliku wyników, więc **wystarczy uruchomić je
  ponownie po 18.08**, żeby próba urosła bez powtarzania pracy.
* **Mierzymy wyłącznie snapshot sprzed meczów.** Po meczu SportsGambler
  podmienia etykietę na „Confirmed" i pokazuje skład faktyczny — pomiar
  robiony po fakcie wychodzi 92,5% i mówi tylko o tym, czy umiemy parować
  nazwiska. Ta pułapka złapała pierwsze podejście 13.08.

## Co z tego wynika dla kolejki

1. **Źródło wchodzi** — próg jest pobity poza szumem, decyzja o wpięciu ma
   pokrycie w pomiarze.
2. **Najpierw dobić próbę Ameryki Południowej** (uruchomić narzędzie po 18.08).
   Jeśli Argentyna utrzyma się poniżej progu, wpinamy SportsGamblera
   z zastrzeżeniem na rozgrywki — a nie globalnie.
3. **Kontuzje z 365Scores dopiero PO tym** — obie zmiany dotykają tego samego
   miejsca i wdrożone razem nie dadzą się rozdzielić w pomiarze.
