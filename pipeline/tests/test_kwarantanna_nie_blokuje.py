"""Kwarantanna nie zdejmuje typu z listy — zostaje jako pomiar i etykieta.

DECYZJA WŁAŚCICIELA 2026-08-14, z pomiaru księgi (epoka ligowa, rozliczone):

    pokazane klientowi         n=419  luka -10,8 pp  ROI  -3,5%
    zdjęte: wstrzymany rynek   n= 34  luka  -7,3 pp  ROI +10,3%
    zdjęte: wstrzymana strona  n=190  luka -16,3 pp  ROI  -1,3%
    zdjęte: poza listą dnia    n=149  luka  -9,2 pp  ROI  +1,2%

Bramy wyrzucały materiał, który wypadał NIE GORZEJ niż to, co zostawało na
stronie — a kwarantanna patrzy na okno 40 rozliczeń, więc wstrzymuje segment
po serii pecha, czyli dokładnie wtedy, gdy ten i tak wraca do średniej.

Te testy pilnują trzech rzeczy naraz:
  1. brama umie nie blokować (i to jest jawny parametr, nie przypadek),
  2. ta sama brama dalej UMIE blokować — bo z niej żyje pula kuponów
     i etykieta „sami przestaliśmy ten rynek polecać",
  3. lista typów jest ustawiona na „nie blokuje" — zmiana tej stałej ma
     wywalić test, a nie po cichu zabrać klientowi 200 typów.
"""

from footstats.jobs import build_wc_fast as B
from footstats.jobs import rozliczanie

RYNKI = {"team_corners": {"roi": -0.19, "n": 118}}
STRONY = {"team_goals:powyzej": {"roi": -0.22, "n": 41}}


def _rec(mk: str, strona: str) -> dict:
    return {"rynek_kod": mk, "strona": strona}


def test_brama_bez_blokowania_przepuszcza_wstrzymany_rynek():
    brama = rozliczanie.brama_kwarantanny(
        RYNKI, STRONY, set(), blokuje=False)
    assert brama(_rec("team_corners", "ponizej")) is None
    assert brama(_rec("team_goals", "powyzej")) is None


def test_brama_blokujaca_dalej_dziala():
    """Pula kuponów i etykieta karty stoją na TEJ SAMEJ funkcji."""
    brama = rozliczanie.brama_kwarantanny(RYNKI, STRONY, set())
    assert brama(_rec("team_corners", "ponizej")) == "kwarantanna_rynku"
    assert brama(_rec("team_goals", "powyzej")) == "kwarantanna_strony"
    assert brama(_rec("team_goals", "ponizej")) is None


def test_rynek_nie_zdejmuje_strony_z_wlasnym_werdyktem():
    """Reguła z 30.07 zostaje nietknięta — sprawdzana przy blokuje=True."""
    brama = rozliczanie.brama_kwarantanny(
        RYNKI, STRONY, {"team_corners:powyzej"})
    assert brama(_rec("team_corners", "powyzej")) is None
    assert brama(_rec("team_corners", "ponizej")) == "kwarantanna_rynku"


def test_lista_typow_stoi_na_nie_blokuje():
    """Świadoma decyzja produktowa, nie domyślna wartość.

    Gdyby ktoś przestawił tę stałą, ze strony zniknie ~200 typów dziennie.
    Wtedy trzeba zmienić też ten test — razem z zapisaniem powodu w
    docs/kolejka-po-audycie.md.
    """
    assert B.KWARANTANNA_ZDEJMUJE_Z_LISTY is False
