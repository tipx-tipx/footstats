# Snapshoty pomiarowe — dane, nie kod

Pliki, których jedynym zadaniem jest **przetrwać do następnej sesji**, bo
mierzą coś, czego nie da się policzyć wstecz.

## `sg-prognozy-<data>.json`

Przewidywane składy SportsGambler, pobrane **przed** meczami, 730 meczów
z 15 rozgrywek (Brazylia, Argentyna, MLS, Liga MX, Kolumbia, Urugwaj,
Finlandia, Skandynawia, Libertadores, Sudamericana).

**Po co:** trafności prognozy składu nie da się zmierzyć po fakcie. Po meczu
SportsGambler podmienia etykietę na `Confirmed` i pokazuje skład faktyczny —
pomiar wychodzi wtedy 92,5% i mówi wyłącznie o tym, czy umiemy sparować
nazwiska, a nie o tym, czy prognoza była trafna. Ta pułapka złapała pierwsze
podejście 13.08.

**Jak zamknąć pomiar:** uruchomić narzędzie, które to robi:

```
cd pipeline
PYTHONUTF8=1 python scripts/pomiar_sklady_sg.py
```

Bierze faktyczne XI ze statshuba (`event/{id}/team-lineup?teamId=`), porównuje
z zapisanym `xi_dom` / `xi_wyjazd` i sam mówi, czy próg jest pobity. Chodzi
partiami (statshub ma budżet zapytań) i odkłada postęp w `sg-wyniki-<data>.json`,
więc przerwany przebieg wznawia się w miejscu, w którym stanął. Próg decyzyjny:
**prognoza ma sens dopiero wyraźnie powyżej 68,6%**, bo tyle daje własna
jedenastka z rotacji minut, która została odrzucona
(`docs/pomiar-wlasna-jedenastka.md`).

**Co już wiadomo o tym snapshocie (sprawdzone 14.08):**

* **Sufit pomiaru to 77%** — tyle meczów paruje się ze statshubem
  jednoznacznie (565 z 730). Reszta to skróty w rodzaju „Argentinos Jrs"
  czy „Newell's OB”.
* **Okno dnia musi być D−1..D+1.** SportsGambler podaje dzień LOKALNY, więc
  mecz argentyński grany o 21:30 miejscowego to u nas 02:30 następnego dnia.
  Bez tego okna sufit spada do 69%, a traci się dokładnie Amerykę Południową
  (Argentyna 36 → 55 meczów, MLS 7 → 28).
* **Pole `liga` w snapshocie jest połamane** — „FC Orenburg – Lok. Moscow”
  ma tam `mls`. Rozgrywki bierzemy ze statshuba po sparowaniu. Same SKŁADY są
  poprawne: dla czterech sprawdzonych drużyn 8–10 z 11 nazwisk zgadza się
  z kadrą z ostatniego meczu, więc etykieta rozjechała się sama.
* **Mecze zaczynają się dopiero 14.08 wieczorem**, więc pierwsze wyniki są do
  wzięcia 15.08 rano (94 mecze z doby 14.08), a największa porcja po 16.08.

**Kiedy skasować:** po zamknięciu pomiaru i zapisaniu wyniku w
`docs/pomiar-wlasna-jedenastka.md`. Plik nie jest częścią produktu i nic go
nie czyta.
