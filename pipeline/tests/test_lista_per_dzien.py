"""Lista typów: limity per DZIEŃ MECZOWY, typ raz pokazany nie znika (2026-08-07).

Zgłoszenie usera: „żeby typy nie pojawiały się i nie znikały". Dwudziestka
liczona na całą listę robiła z niej ruchome schody — typ na sobotę konkurował
z typem na poniedziałek, więc świeże wejście wypychało ze strony typ pokazany
trzy dni wcześniej, z ceną, którą user mógł już zagrać.
"""
import time

import pytest

from footstats.jobs import build_wc_fast as B
from footstats.model import uczony as U
from footstats.jobs import rozliczanie as R

DZIEN = 86400
JUTRO = int(time.time()) + DZIEN
POJUTRZE = JUTRO + DZIEN


def _typ(kickoff=JUTRO, mecz_id=1, rynek="team_corners", strona="ponizej",
         kurs=1.5, linia=6.5, **kw) -> dict:
    b = {
        "mecz_id": mecz_id, "mecz": "A – B", "kickoff_ts": kickoff,
        "podmiot_id": 100 + mecz_id, "podmiot": f"Drużyna {mecz_id}",
        "rynek_kod": rynek, "rynek": "Rzuty rożne", "linia": linia,
        "strona": strona, "kurs": kurs, "p_model": 0.8,
    }
    b.update(kw)
    return b


def _klucz(b):
    """Kolejność jak w produkcji, tylko bez pomiaru przewagi: droższy wyżej."""
    return (float(b.get("kurs") or 0.0),)


@pytest.fixture
def bez_roznorodnosci(monkeypatch):
    """Izoluje sam limit dnia — gwarancje różnorodności podniesione poza zasięg."""
    for nazwa in ("LISTA_PER_MECZ", "LISTA_PER_RYNEK", "LISTA_PER_PASMO",
                  "LISTA_PER_RODZINA"):
        monkeypatch.setattr(B, nazwa, 999)


# --- limit na dzień, nie na całą listę ---

def test_kazdy_dzien_ma_wlasna_dwudziestke(bez_roznorodnosci):
    # mecz_id unikalny w obrębie dnia — jeden mecz nie gra dwa razy
    # ⚑ kursy 1,20–1,49 to JEDNA półka (pewniaki), więc limitem doby jest jej
    # budżet, nie sufit globalny — patrz `uczony.POLKI` (wpięte 2026-08-20)
    kand = [_typ(kickoff=k, mecz_id=1000 * d + i, kurs=1.2 + i / 100)
            for d, k in enumerate((JUTRO, POJUTRZE)) for i in range(30)]
    limit = U.POLKI["wysoka_szansa"]["limit_dobowy"]
    lista, zdjete, per_dzien = B.wybierz_liste_publikowana(kand, _klucz)
    assert len(lista) == 2 * limit
    assert sorted(per_dzien.values()) == [limit, limit]
    assert len(zdjete) == 2 * (30 - limit)
    assert set(zdjete.values()) == {"poza_lista_dnia"}


def test_limit_rynku_liczy_sie_osobno_w_kazdym_dniu():
    """Sześć rożnych na jutro nie zabiera miejsca rożnym na pojutrze."""
    kand = [_typ(kickoff=k, mecz_id=i, kurs=1.2 + i / 100)
            for k in (JUTRO, POJUTRZE) for i in range(8)]
    lista, _zdjete, _per = B.wybierz_liste_publikowana(kand, _klucz)
    assert len(lista) == 2 * B.LISTA_PER_RYNEK


def test_limit_meczu_takze_per_dzien():
    kand = [_typ(kickoff=k, mecz_id=7, linia=float(i), kurs=1.2 + i / 100)
            for k in (JUTRO, POJUTRZE) for i in range(5)]
    lista, _z, _p = B.wybierz_liste_publikowana(kand, _klucz)
    assert len(lista) == 2 * B.LISTA_PER_MECZ


def test_dzien_liczony_doba_polska():
    """Ta sama definicja doby, co w Skuteczności — mecz o 00:30 należy do
    swojego dnia polskiego, nie do wczoraj wg strefy serwera."""
    kand = [_typ(kickoff=JUTRO, mecz_id=1),
            _typ(kickoff=POJUTRZE, mecz_id=2, rynek="team_goals")]
    _lista, _zdjete, per_dzien = B.wybierz_liste_publikowana(kand, _klucz)
    assert set(per_dzien) == {R.dzien_pl(JUTRO), R.dzien_pl(POJUTRZE)}


# --- jeden typ na zawodnika (2026-08-08, wpięcie oferty do silnika) ---

def _typ_zawodnika(nazwa="K. Mbappe", rynek="shots", mecz_id=1, kurs=1.8,
                   **kw) -> dict:
    return _typ(mecz_id=mecz_id, rynek=rynek, kurs=kurs,
                podmiot=nazwa, podmiot_typ="zawodnik", podmiot_id=555, **kw)


def test_jeden_zawodnik_nie_zajmuje_listy_kilkoma_rynkami():
    """User: „żeby nie było kanibalizowania". Strzały, celne i „zza pola" tego
    samego gracza to jeden zakład w trzech opakowaniach."""
    kand = [
        _typ_zawodnika(rynek="shots", kurs=1.90),
        _typ_zawodnika(rynek="sot", kurs=1.80),
        _typ_zawodnika(rynek="shots_outside_box", kurs=1.70),
    ]
    lista, zdjete, _p = B.wybierz_liste_publikowana(kand, _klucz)
    assert len(lista) == B.LISTA_PER_ZAWODNIKA == 1
    assert lista[0]["rynek_kod"] == "shots"      # najlepszy wg klucza
    assert set(zdjete.values()) == {"poza_lista_dnia"}


def test_limit_zawodnika_nie_dotyczy_druzyn():
    """„Gole poniżej" i „rożne powyżej" tej samej drużyny to różne zdarzenia —
    ogranicza je limit meczu, nie ten licznik."""
    kand = [
        _typ(mecz_id=1, rynek="team_goals", kurs=1.9),
        _typ(mecz_id=1, rynek="team_corners", kurs=1.8),
    ]
    lista, _zdjete, _p = B.wybierz_liste_publikowana(kand, _klucz)
    assert len(lista) == 2


def test_ten_sam_zawodnik_w_dwoch_dniach_dostaje_dwa_typy():
    """Limit jest DZIENNY, jak wszystkie pozostałe."""
    kand = [
        _typ_zawodnika(kickoff=JUTRO, mecz_id=1),
        _typ_zawodnika(kickoff=POJUTRZE, mecz_id=2),
    ]
    lista, _zdjete, _p = B.wybierz_liste_publikowana(kand, _klucz)
    assert len(lista) == 2


def test_pokazany_typ_zawodnika_zostaje_i_zajmuje_swoje_miejsce():
    """Typ raz pokazany zostaje do gwizdka — i LICZY SIĘ do limitu.

    ⚑ ZMIANA SEMANTYKI 2026-08-14. Do tego dnia test wymagał, żeby weszły OBA
    typy: wznowiony (bo raz pokazany) i nowy (bo licznik zdążył urosnąć
    dopiero po nim). To był właśnie przeciek — przy limicie „1 typ na
    zawodnika" na liście lądowały dwa, a w skali dnia deklarowane 20 typów
    zamieniało się w medianę 67.

    Teraz wznowione są przetwarzane pierwsze, więc zajmują swoje miejsca:
    pokazany typ zostaje (to się NIE zmieniło i nie ma prawa się zmienić),
    a nowy czeka na wolne miejsce.
    """
    kand = [
        _typ_zawodnika(rynek="shots", kurs=1.90),
        _typ_zawodnika(rynek="sot", kurs=1.80, wznowiony=True),
    ]
    lista, zdjete, _p = B.wybierz_liste_publikowana(kand, _klucz)
    assert [b["rynek_kod"] for b in lista] == ["sot"]      # pokazany zostaje
    assert len(zdjete) == 1                                # nowy czeka


# --- typ raz pokazany zostaje do gwizdka ---

def test_pokazany_typ_wchodzi_ponad_limit_dnia():
    """25 typów pokazanych wcześniej na jeden dzień — wszystkie zostają."""
    kand = [_typ(mecz_id=i, kurs=1.2 + i / 100, wznowiony=True)
            for i in range(25)]
    lista, zdjete, per_dzien = B.wybierz_liste_publikowana(kand, _klucz)
    assert len(lista) == 25 > B.LISTA_CAP
    assert not zdjete
    assert per_dzien[R.dzien_pl(JUTRO)] == 25


def test_pokazany_typ_nie_odpada_na_limicie_rynku():
    kand = [_typ(mecz_id=i, kurs=1.2 + i / 100, wznowiony=True)
            for i in range(10)]
    lista, zdjete, _p = B.wybierz_liste_publikowana(kand, _klucz)
    assert len(lista) == 10 and not zdjete


def test_swiezy_typ_ustepuje_pokazanym_ale_ich_nie_wypycha(bez_roznorodnosci):
    """Dzień pełen typów pokazanych: świeży czeka, ale nikogo nie zdejmuje."""
    pokazane = [_typ(mecz_id=i, kurs=2.5, wznowiony=True)
                for i in range(B.LISTA_CAP)]
    swiezy = _typ(mecz_id=99, kurs=1.9, rynek="team_goals")
    lista, zdjete, _p = B.wybierz_liste_publikowana(
        pokazane + [swiezy], _klucz)
    assert len(lista) == B.LISTA_CAP
    assert all(b.get("wznowiony") for b in lista)
    assert zdjete[B._klucz_publikacji(swiezy)] == "poza_lista_dnia"


def test_pokazane_licza_sie_do_limitu_swiezych():
    """Sześć pokazanych rożnych wypełnia limit rynku — świeży rożny czeka,
    ale typ z innego rynku wchodzi."""
    pokazane = [_typ(mecz_id=i, kurs=2.5, wznowiony=True)
                for i in range(B.LISTA_PER_RYNEK)]
    swiezy_rozne = _typ(mecz_id=50, kurs=1.95)
    swiezy_gole = _typ(mecz_id=51, kurs=1.95, rynek="team_goals")
    lista, zdjete, _p = B.wybierz_liste_publikowana(
        pokazane + [swiezy_rozne, swiezy_gole], _klucz)
    assert swiezy_gole in lista
    assert swiezy_rozne not in lista
    assert zdjete[B._klucz_publikacji(swiezy_rozne)] == "poza_lista_dnia"


def test_pokazany_z_wczoraj_nie_wypada_przez_dzisiejsza_fale(bez_roznorodnosci):
    """Regresja wprost ze zgłoszenia: 25 świeżych typów na ten sam dzień nie
    może zdjąć ze strony typu, który user widział wczoraj."""
    wczorajszy = _typ(mecz_id=1, kurs=1.25, wznowiony=True)
    fala = [_typ(mecz_id=200 + i, kurs=3.0, rynek="team_goals")
            for i in range(25)]
    lista, _zdjete, _p = B.wybierz_liste_publikowana(
        fala + [wczorajszy], _klucz)
    assert wczorajszy in lista


# --- rynek ukryty i sugestie ---

def test_rynek_ukryty_schodzi_takze_pokazanemu_ale_bez_znacznika():
    """Rynek w kwarantannie schodzi ze strony (decyzja 01.08), ale wznowionemu
    typowi nie dopisujemy znacznika — on JUŻ był policzony jako pokazany."""
    swiezy = _typ(mecz_id=1)
    pokazany = _typ(mecz_id=2, wznowiony=True)
    lista, zdjete, _p = B.wybierz_liste_publikowana(
        [swiezy, pokazany], _klucz, ukryte={"team_corners|ponizej"})
    assert lista == []
    assert zdjete == {B._klucz_publikacji(swiezy): "rynek_ukryty"}


def test_sugestia_nie_liczy_sie_do_limitu(bez_roznorodnosci):
    limit = U.POLKI["wysoka_szansa"]["limit_dobowy"]
    kand = [_typ(mecz_id=i, kurs=1.2 + i / 100) for i in range(limit)]
    sugestia = _typ(mecz_id=99, rynek="team_goals", sugestia=True)
    lista, _z, per_dzien = B.wybierz_liste_publikowana(
        kand + [sugestia], _klucz)
    assert sugestia in lista
    assert per_dzien[R.dzien_pl(JUTRO)] == limit


def test_pusta_lista_nie_wybucha():
    assert B.wybierz_liste_publikowana([], _klucz) == ([], {}, {})
