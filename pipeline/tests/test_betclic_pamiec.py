"""Pamięć oferty Betclica między cyklami — bez niej pokrycie jest nieosiągalne.

Zmierzone 2026-08-08: pobranie oferty jednego meczu Z propsami trwa ~71 s,
meczu bez propsów 30–40 s (i zwraca zero), a `kalendarz()` do parowania ~150 s.
Pełne pokrycie 140 meczów kosztowałoby 2,2 godziny — w cyklu, który ma osiem
minut zapasu. Stąd trzy reguły, których pilnują te testy:
  1. mecz raz pobrany nie jest pobierany ponownie, dopóki oferta jest świeża,
  2. pytamy wyłącznie o mecze, w których Superbet kwotuje zawodników,
  3. pamięć nie puchnie — mecze po gwizdku i stare wpisy wypadają.
"""
import time

from footstats.jobs import build_wc_fast as B

TERAZ = 1_800_000_000
GODZINA = 3600


def _pamiec(mid, ts, gracze=("kowalski",)):
    return {str(mid): {"ts": ts, "players": {g: {"shots": {}} for g in gracze}}}


# --- 1. czytanie z pamięci ---

def test_swieza_oferta_wraca_z_pamieci():
    kol = {101: TERAZ + 3 * GODZINA}
    out = B.bc_z_pamieci(kol, _pamiec(101, TERAZ - 600), TERAZ)
    assert set(out) == {101}
    assert out[101]["players"]


def test_przeterminowana_oferta_nie_wraca():
    kol = {101: TERAZ + 3 * GODZINA}
    stara = _pamiec(101, TERAZ - B.SWIEZOSC_BETCLIC_S - 1)
    assert B.bc_z_pamieci(kol, stara, TERAZ) == {}


def test_wpis_bez_zawodnikow_nie_liczy_sie_jako_pokrycie():
    """Mecz, w którym Betclic nie kwotował nikogo, ma być pytany ponownie —
    inaczej pusty strzał zamroziłby go na godzinę."""
    kol = {101: TERAZ + 3 * GODZINA}
    pusty = {"101": {"ts": TERAZ - 60, "players": {}}}
    assert B.bc_z_pamieci(kol, pusty, TERAZ) == {}


def test_pamiec_z_innego_cyklu_nie_wywraca_sie_na_kluczach_tekstowych():
    """JSON zamienia klucze liczbowe na tekst — to najczęstszy sposób, w jaki
    cache po cichu przestaje działać."""
    kol = {101: TERAZ + GODZINA}
    assert B.bc_z_pamieci(kol, _pamiec("101", TERAZ - 10), TERAZ)


def test_oferta_sprzed_doby_wciaz_wazna_bo_pobieramy_raz():
    """Decyzja usera: „kurs pobierany jednorazowo na dany typ, nawet jak
    później się zmieni". Cena i tak jest zamrażana przy publikacji, więc
    ponowne pytanie o ten sam mecz nie poprawia ani jednego typu — a kosztuje
    71 sekund, które lepiej wydać na mecz jeszcze nieznany."""
    kol = {101: TERAZ + 20 * GODZINA}
    stara = _pamiec(101, TERAZ - 10 * GODZINA)
    assert B.bc_z_pamieci(kol, stara, TERAZ)


def test_mecz_tuz_przed_gwizdkiem_odswiezamy_raz():
    """Jedyny wyjątek od „pobieramy raz": w oknie przedmeczowym user realnie
    stawia, a pokazanie ceny, której już nie ma, boli bardziej niż brak typu."""
    kickoff = TERAZ + 2 * GODZINA           # mecz w oknie 6 h
    kol = {101: kickoff}
    # ofertę zapamiętaliśmy DAWNO, jeszcze przed wejściem w okno
    stara = _pamiec(101, kickoff - 20 * GODZINA)
    assert B.bc_z_pamieci(kol, stara, TERAZ) == {}


def test_w_oknie_przedmeczowym_odswiezamy_tylko_raz():
    """Oferta pobrana JUŻ w oknie nie jest pobierana w kółko co cykl."""
    kickoff = TERAZ + 2 * GODZINA
    kol = {101: kickoff}
    swieza = _pamiec(101, TERAZ - 15 * 60)   # pobrana kwadrans temu, w oknie
    assert B.bc_z_pamieci(kol, swieza, TERAZ)


# --- 2. kogo w ogóle pytamy ---

def test_pytamy_tylko_o_mecze_z_propsami_superbetu():
    kol = {1: TERAZ + GODZINA, 2: TERAZ + 2 * GODZINA}
    sb = {1: {"players": {"a": {}}}, 2: {"players": {}}}
    assert B.bc_do_pobrania(kol, {}, sb) == [(1, TERAZ + GODZINA)]


def test_mecz_juz_w_pamieci_nie_jest_pobierany_ponownie():
    kol = {1: TERAZ + GODZINA, 2: TERAZ + 2 * GODZINA}
    sb = {1: {"players": {"a": {}}}, 2: {"players": {"b": {}}}}
    out = B.bc_do_pobrania(kol, {1: {"players": {}}}, sb)
    assert [m for m, _ in out] == [2]


def test_najblizsze_mecze_pierwsze():
    kol = {1: TERAZ + 5 * GODZINA, 2: TERAZ + GODZINA, 3: TERAZ + 3 * GODZINA}
    sb = {m: {"players": {"a": {}}} for m in kol}
    assert [m for m, _ in B.bc_do_pobrania(kol, {}, sb)] == [2, 3, 1]


# --- 3. rotacja pamięci ---

def test_mecz_po_gwizdku_wypada_z_pamieci():
    kol = {101: TERAZ - 60}          # już się zaczął
    out = B.bc_rotuj_pamiec(_pamiec(101, TERAZ - 10), kol, TERAZ)
    assert out == {}


def test_wpis_starszy_niz_doba_wypada():
    kol = {101: TERAZ + GODZINA}
    out = B.bc_rotuj_pamiec(_pamiec(101, TERAZ - 86401), kol, TERAZ)
    assert out == {}


def test_mecz_spoza_biezacego_zakresu_zostaje():
    """Zakres cyklu bywa węższy niż pamięć — kasowanie takich wpisów kazałoby
    pobierać je od nowa przy następnym przebiegu."""
    out = B.bc_rotuj_pamiec(_pamiec(999, TERAZ - 60), {}, TERAZ)
    assert set(out) == {"999"}


def test_pamiec_nie_puchnie_ponad_sufit():
    kol = {i: TERAZ + GODZINA for i in range(200)}
    duza = {}
    for i in range(200):
        duza.update(_pamiec(i, TERAZ - i))
    out = B.bc_rotuj_pamiec(duza, kol, TERAZ)
    assert len(out) == B.MAX_MECZOW_W_PAMIECI_BC
    # zostają NAJŚWIEŻSZE
    assert "0" in out and "199" not in out
