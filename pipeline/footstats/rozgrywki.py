"""Profile rozgrywek — jedna konfiguracja trybu ligowego.

Zakres zatwierdzony 2026-07-20 (koniec MŚ), rozszerzony 2026-07-27:

* statystyki indywidualne (propsy zawodników): CAŁY ŚWIAT — każdy mecz,
  na który Superbet lub STS kwotuje propsy. Odkrywanie meczów idzie OD OFERTY
  bukmachera, więc lista profili NIE ogranicza propsów; profil precyzuje
  tylko dodatkowe źródła i zakres drużynowy.
* statystyki drużynowe: wyłącznie rozgrywki z flagą druzynowe=True
  (top 5 lig + Ekstraklasa + puchary europejskie razem z kwalifikacjami
  + Ameryka Płd. + Skandynawia — patrz niżej).

ROZSZERZENIE 2026-07-27 — dlaczego akurat te ligi. Rynki drużynowe to jedyna
część systemu z dodatnim wynikiem (w oknie zgody: 42 typy, 83,3% trafień,
+7,2u; zawodnicze w tym samym oknie −7,8u), a zakres ograniczał je do garstki
meczów. Sonda statshub na 129 meczach z kursami pokazała, KTÓRE rozgrywki
spoza rejestru mają komplet danych drużynowych — dołożone zostały te z realną
podażą: Ameryka Płd. (gra cały rok, ~30 meczów w oknie 4 dni) i Skandynawia
(trwający sezon letni, zapełnia lukę do startu top 5 w sierpniu).

Pary utid/comp365 dla nowych lig zweryfikowane 2026-07-27 przez porównanie
NAZW DRUŻYN z obu źródeł (statshub event/by-date vs 365Scores games/results):
każda para pokazuje te same kluby. Ta weryfikacja jest istotna, bo błędny
comp365 nie daje błędu — po prostu rynki drużynowe tej ligi nigdy się nie
rozliczą i po 48h zamkną jako zwrot.

Identyfikatory (zweryfikowane na żywo 2026-07-20):

* utid = uniqueTournamentId statshub (zgodny z numeracją Sofascore).
  Potwierdzone sondą event/by-date: Ekstraklasa=202, LM=7, LE=679, LK=17015.
  Top 5 lig nie grało jeszcze po przerwie letniej — wpisane standardowe
  wartości Sofascore, potwierdzic=True po pierwszej kolejce sezonu.
* comp365 = competitionId 365Scores (endpoint /search + kontrola fixtures).
  UWAGA na pułapkę: w 365Scores kwalifikacje LM i LE to OSOBNE rozgrywki
  (332 i 596), a Liga Konferencji (7685) zawiera kwalifikacje w sobie.
  Druga pułapka: comp365=7 to Premier League, a utid=7 to Liga Mistrzów —
  to dwie różne przestrzenie identyfikatorów.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProfilRozgrywek:
    utid: int                    # uniqueTournamentId statshub / Sofascore
    nazwa: str                   # nazwa do UI (prosty język)
    kraj: str                    # kraj/region do UI i logów
    druzynowe: bool = False      # czy liczymy rynki i dane drużynowe
    comp365: tuple[int, ...] = ()  # competitionId 365Scores (może być kilka)
    utid_potwierdzony: bool = True  # False = wpis z numeracji Sofascore,
    #                                 potwierdzić sondą po starcie sezonu


# Rejestr rozgrywek objętych statystykami drużynowymi. Propsy zawodników
# NIE wymagają wpisu tutaj — mecz spoza rejestru dostaje profil domyślny.
PROFILE: dict[int, ProfilRozgrywek] = {
    p.utid: p
    for p in (
        # top 5 lig (utid do potwierdzenia po starcie sezonu ~2026-08)
        ProfilRozgrywek(17, "Premier League", "Anglia", druzynowe=True,
                        comp365=(7,), utid_potwierdzony=False),
        ProfilRozgrywek(8, "LaLiga", "Hiszpania", druzynowe=True,
                        comp365=(11,), utid_potwierdzony=False),
        ProfilRozgrywek(23, "Serie A", "Włochy", druzynowe=True,
                        comp365=(17,), utid_potwierdzony=False),
        ProfilRozgrywek(35, "Bundesliga", "Niemcy", druzynowe=True,
                        comp365=(25,), utid_potwierdzony=False),
        ProfilRozgrywek(34, "Ligue 1", "Francja", druzynowe=True,
                        comp365=(35,), utid_potwierdzony=False),
        # liga polska (sezon 26/27 startuje 2026-07-24)
        ProfilRozgrywek(202, "Ekstraklasa", "Polska", druzynowe=True,
                        comp365=(153,)),
        # puchary europejskie — kwalifikacje dzielą utid z pucharem,
        # więc wchodzą w zakres automatycznie; po stronie 365Scores
        # kwalifikacje LM/LE mają osobne id (332/596)
        ProfilRozgrywek(7, "Liga Mistrzów", "Europa", druzynowe=True,
                        comp365=(572, 332)),
        ProfilRozgrywek(679, "Liga Europy", "Europa", druzynowe=True,
                        comp365=(573, 596)),
        ProfilRozgrywek(17015, "Liga Konferencji", "Europa", druzynowe=True,
                        comp365=(7685,)),
        # --- Ameryka Południowa (dodane 2026-07-27) — grają cały rok, więc
        # niosą podaż także wtedy, gdy Europa ma przerwę
        ProfilRozgrywek(155, "Liga Profesional", "Argentyna", druzynowe=True,
                        comp365=(72,)),
        ProfilRozgrywek(325, "Brasileirão Série A", "Brazylia", druzynowe=True,
                        comp365=(113,)),
        ProfilRozgrywek(390, "Brasileirão Série B", "Brazylia", druzynowe=True,
                        comp365=(116,)),
        ProfilRozgrywek(480, "CONMEBOL Sudamericana", "Ameryka Płd.",
                        druzynowe=True, comp365=(389,)),
        # --- Skandynawia (dodane 2026-07-27) — sezon letni, czyli dokładnie
        # ten okres, w którym top 5 lig jeszcze nie gra
        ProfilRozgrywek(40, "Allsvenskan", "Szwecja", druzynowe=True,
                        comp365=(122,)),
        ProfilRozgrywek(46, "Superettan", "Szwecja", druzynowe=True,
                        comp365=(123,)),
        ProfilRozgrywek(20, "Eliteserien", "Norwegia", druzynowe=True,
                        comp365=(131,)),
        ProfilRozgrywek(39, "Superliga", "Dania", druzynowe=True,
                        comp365=(119,)),
        # --- ROZSZERZENIE ZAKRESU (2026-08-11) ---
        #
        # Zmierzone tego dnia na terminarzu: 67 ze 160 nadchodzących meczów
        # było POZA rejestrem, więc nie liczyliśmy dla nich ani jednego rynku
        # drużynowego. Nie chodziło o egzotykę — odpadały Leagues Cup,
        # Libertadores, J1, Championship czy Eredivisie, czyli rozgrywki
        # z porządnym pokryciem danych.
        #
        # To była największa pojedyncza blokada podaży: cel „różne typy na
        # jak największej liczbie meczów" nie miał prawa się spełnić, dopóki
        # dwie piąte terminarza w ogóle nie wchodziło do liczenia.
        #
        # `utid` z endpointu `event/by-date`, sparowany z nazwą z `matches`.
        # `comp365` z wyszukiwarki 365Scores (`/search/?query=`) i SPRAWDZONY
        # na realnych meczach — bez tego rozgrywka daje typy, które nigdy się
        # nie rozliczą (rozliczanie szuka wyniku po `comp365`, brak id nie
        # rzuca błędu, typ po prostu wisi i zamyka się jako zwrot):
        #     Leagues Cup    comp365=7242   fixtures 18, results 18
        #     Libertadores   comp365=102    fixtures 15, results 33
        #
        # South African Premier Division (utid 358, 9 meczów) NIE WCHODZI:
        # wyszukiwarka 365 nie dała jednoznacznego dopasowania, a rozgrywka
        # bez pary identyfikatorów to cicha strata typów. Wraca, gdy id
        # zostanie potwierdzone — zapisane w `docs/kolejka-po-audycie.md`.
        ProfilRozgrywek(13783, "Leagues Cup", "Ameryka Płn.", druzynowe=True,
                        comp365=(7242,)),
        ProfilRozgrywek(384, "CONMEBOL Libertadores", "Ameryka Płd.",
                        druzynowe=True, comp365=(102,)),
        # --- HOLANDIA I MLS (2026-08-17) ---
        #
        # Obie były wymienione WYŻEJ, w uzasadnieniu rozszerzenia z 11.08,
        # jako rozgrywki „z porządnym pokryciem danych" — i obu wtedy nie
        # dopisano. Skutek widać w księdze: typy drużynowe na tych ligach
        # POWSTAJĄ (oferta idzie od bukmachera, nie od rejestru), ale nie mają
        # jak się rozliczyć, bo rozliczanie szuka meczu wyłącznie w `comp365`
        # rozgrywek z zakresu. Zmierzone 17.08 na wiszących: Ajax – Heerenveen,
        # Feyenoord – Go Ahead, Excelsior – PSV, Twente – PEC Zwolle,
        # Orlando – Cincinnati, CF Montréal – DC United, San Jose – St. Louis,
        # Atlanta United – NY Red Bulls.
        #
        # ⚑ PUŁAPKA PRZY WERYFIKACJI: wyszukiwarka 365 na „Eredivisie" oddaje
        # DWIE rozgrywki o tej samej nazwie — 57 to piłka nożna (Ajax,
        # Feyenoord, PSV), a 5765 to SIATKÓWKA (Orion Stars, Lycurgus,
        # Draisma Dynamo). Sama nazwa nie wystarcza, dlatego obie pary
        # sprawdzone nazwami drużyn na realnych meczach:
        #     Eredivisie  comp365=57   utid=37   4 nasze mecze odnalezione
        #     MLS         comp365=104  utid=242  4 nasze mecze odnalezione
        # `utid` odczytany z `uniqueTournamentId` w statshub `/event/{id}`,
        # ten sam dla wszystkich czterech meczów każdej ligi.
        #
        # Liga MX świadomie POZA zakresem (decyzja właściciela 17.08).
        ProfilRozgrywek(37, "Eredivisie", "Holandia", druzynowe=True,
                        comp365=(57,)),
        ProfilRozgrywek(242, "MLS", "Ameryka Płn.", druzynowe=True,
                        comp365=(104,)),
    )
}


def profil(utid: int | None) -> ProfilRozgrywek | None:
    """Profil rozgrywek albo None, gdy utid spoza rejestru."""
    if utid is None:
        return None
    return PROFILE.get(int(utid))


def profil_lub_domyslny(utid: int | None, nazwa: str = "", kraj: str = "") -> ProfilRozgrywek:
    """Profil z rejestru albo domyślny (propsy tak, drużynowe nie).

    nazwa/kraj pozwalają przenieść etykiety ze źródła (statshub podaje
    unique_tournaments.name i categories.name) do UI bez wpisu w rejestrze.
    """
    p = profil(utid)
    if p is not None:
        return p
    return ProfilRozgrywek(int(utid or 0), nazwa or "Inne rozgrywki",
                           kraj or "", druzynowe=False)


def czy_druzynowe(utid: int | None) -> bool:
    """Czy rozgrywki są w zakresie statystyk drużynowych."""
    p = profil(utid)
    return bool(p and p.druzynowe)


def comp365_druzynowe() -> list[int]:
    """Wszystkie competitionId 365Scores z zakresu drużynowego (bez dubli)."""
    out: list[int] = []
    for p in PROFILE.values():
        for cid in p.comp365:
            if cid not in out:
                out.append(cid)
    return out


def utidy_niepotwierdzone() -> list[int]:
    """utid-y czekające na potwierdzenie sondą po starcie sezonu."""
    return [p.utid for p in PROFILE.values() if not p.utid_potwierdzony]
