"""Najwyżej DWIE poprzeczki na zakład (2026-08-02, decyzja usera).

Brama z 01.08 wybiera najlepszą poprzeczkę wg oceny modelu, ale widzi tylko
bieżące przeliczenie — poprzeczki dokładały się więc między cyklami i jeden
zakład potrafił urosnąć do czterech wierszy.

GRANICA WZIĘTA Z POMIARU, nie z gustu. Poprzeczki wg kolejności wystawienia:

    1. bazowa              449 typów   57% trafień   -0,219 j./typ
    2. pierwsza dołożona   135 typów   64% trafień   -0,147 j./typ  <-- najlepsza
    3. i dalsze             37 typów   49% trafień   -0,298 j./typ  <-- najgorsza

Druga bije bazową, dopiero trzecia się załamuje. Limit ucina ogon: 42 wiersze
z 809. Obie zostają na liście i obie liczą się w Skuteczności — to dwa różne
zakłady (łatwiejszy tańszy, ambitniejszy droższy), a zwijanie do jednego
wiersza robi UI, nie publikacja.
"""

from footstats.jobs.build_wc_fast import linie_opublikowane


def _rec(**kw):
    r = {
        "mecz_id": 1, "podmiot": "Boca Juniors", "rynek_kod": "team_goals",
        "linia": 0.5, "strona": "ponizej",
    }
    r.update(kw)
    return r


def test_zbiera_wystawione_poprzeczki_per_zaklad():
    log = {
        "a": _rec(linia=0.5),
        "b": _rec(linia=1.5),                       # ten sam zakład, inna linia
        "c": _rec(linia=2.5, strona="powyzej"),     # DRUGA STRONA = inny zakład
        "d": _rec(mecz_id=2),                       # inny mecz = inny zakład
    }
    m = linie_opublikowane(log)
    assert m[(1, "boca juniors", "team_goals", "ponizej")] == {0.5, 1.5}
    assert m[(1, "boca juniors", "team_goals", "powyzej")] == {2.5}
    assert m[(2, "boca juniors", "team_goals", "ponizej")] == {0.5}


def test_poprzeczka_nie_jest_czescia_tozsamosci_zakladu():
    """„poniżej 4,5" i „poniżej 5,5" to jeden pomysł wyceniony dwa razy —
    muszą wpaść pod TEN SAM klucz, inaczej brama nic nie zablokuje."""
    m = linie_opublikowane({"a": _rec(linia=4.5), "b": _rec(linia=5.5)})
    assert len(m) == 1 and next(iter(m.values())) == {4.5, 5.5}


def test_typy_ktorych_user_nie_widzial_nie_blokuja():
    """Odrzucony przy progu, spoza publikacji i sugestia bez kursu nie były
    na stronie — nie ma z czym kolidować (ta sama zasada co przy kierunkach).
    Inaczej typ policzony „na próbę" zabierałby miejsce prawdziwemu."""
    log = {
        "a": _rec(linia=1.5, odrzucony=True),
        "b": _rec(linia=2.5, poza_publikacja="kwarantanna_rynku"),
        "c": _rec(linia=3.5, sugestia=True),
    }
    assert linie_opublikowane(log) == {}


def test_nazwa_podmiotu_znormalizowana():
    """Klucz idzie po znormalizowanej nazwie — w księdze bywa „Boca Juniors"
    i „boca juniors" (patrz `rozliczanie._klucz`), a to jeden zakład."""
    m = linie_opublikowane({
        "a": _rec(podmiot="Boca Juniors", linia=0.5),
        "b": _rec(podmiot="boca juniors", linia=1.5),
    })
    assert len(m) == 1


def test_pusta_ksiega_nie_blokuje_niczego():
    """Nieudany odczyt księgi ma zostawić publikację nietkniętą, a nie
    zablokować cały cykl — pusty słownik wyłącza bramę."""
    assert linie_opublikowane({}) == {}
    assert linie_opublikowane(None) == {}


# --- SAMA BRAMA: ile poprzeczek przepuszcza ---------------------------------
#
# Odwzorowuje warunek z `build_wc_fast` (limit 2), żeby granica była przypięta
# testem, a nie tylko komentarzem. Najważniejszy jest przypadek DRUGIEJ
# poprzeczki: ona ma PRZECHODZIĆ — wypada najlepiej z całej trójki, więc
# zaostrzenie limitu do jednej byłoby cofnięciem się, nie porządkiem.

MAX_POPRZECZEK_ZAKLADU = 2


def _przepuszcza(juz: set, linia: float) -> bool:
    nowa = linia not in juz
    return not (nowa and len(juz) >= MAX_POPRZECZEK_ZAKLADU)


def test_pierwsza_i_druga_poprzeczka_przechodza():
    assert _przepuszcza(set(), 0.5)          # zakład bez historii
    assert _przepuszcza({0.5}, 1.5)          # DRUGA — najlepiej rozliczana


def test_trzecia_poprzeczka_odpada():
    assert not _przepuszcza({0.5, 1.5}, 2.5)
    assert not _przepuszcza({0.5, 1.5, 2.5}, 3.5)


def test_juz_wystawiona_poprzeczka_nie_blokuje_sama_siebie():
    """Typ wraca w kolejnym cyklu z tą samą poprzeczką — musi przejść, inaczej
    zniknąłby userowi ze strony mimo że nadal jest aktualny."""
    assert _przepuszcza({0.5, 1.5}, 0.5)
    assert _przepuszcza({0.5, 1.5}, 1.5)
