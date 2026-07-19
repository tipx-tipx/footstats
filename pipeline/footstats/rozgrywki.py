"""Profile rozgrywek — jedna konfiguracja trybu ligowego.

Zakres zatwierdzony 2026-07-20 (koniec MŚ):

* statystyki indywidualne (propsy zawodników): CAŁY ŚWIAT — każdy mecz,
  na który Superbet lub STS kwotuje propsy. Odkrywanie meczów idzie OD OFERTY
  bukmachera, więc lista profili NIE ogranicza propsów; profil precyzuje
  tylko dodatkowe źródła i zakres drużynowy.
* statystyki drużynowe: wyłącznie rozgrywki z flagą druzynowe=True
  (top 5 lig + Ekstraklasa + puchary europejskie razem z kwalifikacjami).

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
