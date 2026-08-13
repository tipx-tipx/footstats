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

**Jak zamknąć pomiar:** po rozegraniu tych meczów wziąć faktyczne XI ze
statshuba (`event/{id}/team-lineup?teamId=`) i porównać z zapisanym `xi_dom` /
`xi_wyjazd`. Parowanie po ostatnim członie nazwiska (SportsGambler pisze
„Thiago Silva", statshub „T. Silva"). Próg decyzyjny: **prognoza ma sens
dopiero wyraźnie powyżej 68,6%**, bo tyle daje własna jedenastka z rotacji
minut, która została odrzucona (`docs/pomiar-wlasna-jedenastka.md`).

**Kiedy skasować:** po zamknięciu pomiaru i zapisaniu wyniku w
`docs/pomiar-wlasna-jedenastka.md`. Plik nie jest częścią produktu i nic go
nie czyta.
