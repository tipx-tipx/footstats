"""Drugi szczebel drabinki ma być realny — i decyduje o rodzaju gry.

Zgłoszenie usera 2026-08-03: „ważne jest, aby realne było wejście też drugiego
szczebla; możemy podzielić drabinki na dwa typy — jedno z mniejszym kursem,
drugie value, np. 2+ kurs na pierwszy szczebel, ale realna szansa wejścia".

Pomiar, który to potwierdził (bieżący przebieg, 8 drugich szczebli):
0,08 · 0,13 · 0,15 · 0,17 · 0,17 · 0,27 · 0,28 · 0,40 — sześć z ośmiu poniżej
0,27. Powód był mechaniczny: MIN_P_SZCZEBLA obowiązuje dopiero OD TRZECIEGO
szczebla, więc pierwszy i drugi nie miały żadnej podłogi.
"""
import pytest

from footstats.jobs import radar as R


def _karta(rynek="shots", szczeble=()):
    drabinka = [{"linia": l, "kurs": k, "p_final": p} for l, k, p in szczeble]
    return {
        "hero": {"rynek_kod": rynek, "linia": drabinka[0]["linia"]},
        "rynki": [{"rynek_kod": rynek, "drabinka": drabinka}],
    }


def _kandydat(szczeble, traf=7, z=10, traf2=None):
    """Karta gotowa do `_oceń_karte`: bramy minut i startów przechodzą,
    pokrycie pierwszego szczebla nad progiem. Zmienną jest sama drabinka.

    `traf2` — ile razy wchodził DRUGI szczebel (domyślnie o dwa mniej niż
    pierwszy, czyli 5/10 przy wartościach domyślnych: dokładnie na progu
    MIN_POKRYCIE_DRUGIEGO)."""
    drabinka = []
    for i, (linia, kurs, p) in enumerate(szczeble):
        if i == 0:
            pok = traf
        elif i == 1:
            pok = traf2 if traf2 is not None else max(traf - 2, 0)
        else:
            pok = max(traf - 3, 0)
        drabinka.append({
            "linia": linia, "kurs": kurs,
            "pokrycie": {"traf": pok, "z": z},
            "p_bazowe": p, "korekta": 1.0, "p_final": p,
        })
    return {
        "minuty_sr6": 85, "udzial_startow": 0.9,
        "rynki": [{"rynek_kod": "shots", "rynek": "Strzały",
                   "drabinka": drabinka}],
    }


# --- rodzaj gry ---

def test_pewna_gdy_drugi_szczebel_realnie_wchodzi():
    w = _karta(szczeble=[(0.5, 1.45, 0.72), (1.5, 2.60, 0.44)])
    assert R._profil_gry(w) == "dwa_szczeble"


def test_value_gdy_kurs_od_2_a_szansa_bliska_polowie():
    """Bukmacher wycenia jak rzut monetą, my mamy wyraźnie lepiej."""
    # drugi szczebel 0,35 — nad podłogą z 08.08 (dawne 0,28 opisywało kartę,
    # która dziś w ogóle nie powstaje)
    w = _karta(szczeble=[(1.5, 2.30, 0.51), (2.5, 4.10, 0.35)])
    assert R._profil_gry(w) == "wyzszy_kurs"


def test_tani_pewniak_z_martwym_drugim_szczeblem_bez_etykiety():
    """Cała rzecz w tym, żeby OBA szczeble dały się zagrać — pierwszy sam
    nie wystarczy."""
    w = _karta(szczeble=[(0.5, 1.30, 0.78), (1.5, 6.70, 0.09)])
    assert R._profil_gry(w) is None


def test_karta_bez_drugiego_szczebla_bez_etykiety():
    w = _karta(szczeble=[(0.5, 1.40, 0.75)])
    assert R._profil_gry(w) is None


def test_szczebel_bez_policzonej_szansy_nie_daje_etykiety():
    """Brak liczby to brak wiedzy — nie obiecujemy po cichu."""
    w = _karta(szczeble=[(0.5, 1.40, None), (1.5, 2.50, 0.45)])
    assert R._profil_gry(w) is None


def test_value_wymaga_kursu_od_dwoch():
    """Ta sama szansa przy taniej cenie to nie value, tylko słaby pewniak."""
    # drugi szczebel nad podłogą, żeby test pytał wyłącznie o CENĘ pierwszego
    w = _karta(szczeble=[(1.5, 1.70, 0.51), (2.5, 3.00, 0.35)])
    assert R._profil_gry(w) is None


# --- DRABINKA MUSI BYĆ DRABINKĄ (2026-08-08) ---
#
# Zgłoszenie usera: „obecnie drabinki są bardziej wysoką szansą niż drabinkami
# — dajecie typy, gdzie pierwszy szczebel jest bardzo realny i kurs jest niski,
# a w drabinkach drugi szczebel bardzo często siada i jest głównym celem".
# Pomiar 20 żywych kart: 12 miało JEDEN szczebel, osiem dwa, trzeciego nie
# miała ani jedna.

def test_karta_z_jednym_szczeblem_nie_jest_drabinka():
    """Sedno zgłoszenia: pojedynczy typ nie ma prawa jechać jako drabinka."""
    score, hero = R._oceń_karte(_kandydat([(1.5, 1.75, 0.62)]))
    assert hero is None and score == 0.0


def test_karta_z_martwym_drugim_szczeblem_nie_powstaje():
    """Drugi szczebel na 20% to nie cel polowania, tylko ozdoba przy cenie."""
    score, hero = R._oceń_karte(
        _kandydat([(1.5, 1.75, 0.62), (2.5, 6.50, 0.20)])
    )
    assert hero is None and score == 0.0


def test_karta_z_realnym_drugim_szczeblem_przechodzi():
    kandydat = _kandydat([(1.5, 1.75, 0.62), (2.5, 3.20, 0.42)])
    score, hero = R._oceń_karte(kandydat)
    assert hero is not None
    assert hero["linia"] == 1.5
    # front ma z czego nazwać cel polowania po imieniu
    assert (hero["drugi_linia"], hero["drugi_p"]) == (2.5, 0.42)
    assert score > 0


def test_tania_linia_moze_stac_na_karcie_ale_nie_zostaje_naszym_typem():
    """⚑ Sedno rozwiązania z 08.08: życzenie „pierwszy szczebel od 1,60"
    pilnuje `MIN_KURS_SCORE` (wybór hero), a NIE próg startu drabinki.

    Podniesienie progu STARTU przesuwałoby całą drabinkę w górę i zabijało
    drugi szczebel — dry-run pokazał spadek z ~20 kart do jednej. Tu tania
    linia zostaje na karcie jako kontekst, ale nagłówkiem karty jest dopiero
    szczebel o grywalnej cenie.
    """
    # pokrycia 8/10, 7/10, 5/10 — trzeci szczebel nad progiem, żeby test pytał
    # wyłącznie o CENĘ hero, a nie o realność następnika
    score, hero = R._oceń_karte(
        _kandydat([(0.5, 1.40, 0.80), (1.5, 1.75, 0.62), (2.5, 3.20, 0.42)],
                  traf=8, traf2=7)
    )
    assert hero is not None
    assert hero["kurs"] >= R.MIN_KURS_SCORE
    assert hero["linia"] == 1.5           # nie 0,5 — mimo lepszej szansy
    assert hero["drugi_linia"] == 2.5
    assert score > 0


def test_drugi_szczebel_musi_realnie_wchodzic_a_nie_tylko_dobrze_wygladac():
    """⚑ Decyzja usera 08.08: „drugi szczebel musi być bardzo realny, nie
    zważając już nawet na nasze %, bo oni dają typy takie, że drugi szczebel
    też często wchodzi".

    Bramą jest POKRYCIE (ile razy wszedł), nie nasza wyliczona szansa —
    ta ostatnia po Wilsonie i korekcie strumienia potrafi spaść tak nisko,
    że wymagałaby od nas kłótni z ceną rynku.
    """
    # ta sama, przyzwoita szansa — różni się tylko historia drugiego szczebla
    _s, hero_rzadki = R._oceń_karte(
        _kandydat([(1.5, 1.75, 0.62), (2.5, 3.20, 0.42)], traf2=2)
    )
    _s2, hero_czesty = R._oceń_karte(
        _kandydat([(1.5, 1.75, 0.62), (2.5, 3.20, 0.42)], traf2=6)
    )
    assert hero_rzadki is None          # wchodził 2 razy na 10 — to nie cel
    assert hero_czesty is not None
    assert (hero_czesty["drugi_traf"], hero_czesty["drugi_z"]) == (6, 10)


def test_prog_pokrycia_drugiego_nie_zabija_pomiaru_progu():
    """Szczebel pomiarowy ma pokrycie 0,40–0,50, więc jego następnik NIGDY nie
    sięgnie 0,50. Gdyby brama pary obowiązywała i jego, pomiar progu pokrycia
    (NEAR_POKRYCIA) zbierałby zero próbek i cicho by umarł."""
    pomiar = []
    R._oceń_karte(
        _kandydat([(1.5, 2.25, 0.45), (2.5, 4.50, 0.22)], traf=4, traf2=1),
        pomiar_out=pomiar,
    )
    assert len(pomiar) == 1


def test_ranking_premiuje_karte_z_lepszym_drugim_szczeblem():
    """Ten sam pierwszy szczebel, inny drugi — wygrywa ta, którą da się
    dograć do końca. Dotąd obie miały identyczną ocenę, bo liczyła się
    wyłącznie najlepsza pojedyncza linia."""
    slaba, _ = R._oceń_karte(_kandydat([(1.5, 1.75, 0.62), (2.5, 3.20, 0.34)]))
    mocna, _ = R._oceń_karte(_kandydat([(1.5, 1.75, 0.62), (2.5, 3.20, 0.48)]))
    assert mocna > slaba


def test_premia_za_okno_ceny_nie_przebija_wyraznie_lepszej_karty():
    """Premia za cenę startu w oknie 1,60–1,90 ma przestawiać karty o zbliżonej
    jakości, a nie wynosić słabą nad wyraźnie lepszą."""
    w_oknie, _ = R._oceń_karte(_kandydat([(1.5, 1.75, 0.62), (2.5, 3.20, 0.36)]))
    # 0,49 przy kursie 2,30 to rozjazd 1,21 — jeszcze w granicy zgody z rynkiem
    # (MAX_ROZJAZD_KARTY); 0,52 dawałoby 1,29 i karta odpadłaby z innego powodu
    poza_oknem, hero = R._oceń_karte(
        _kandydat([(1.5, 2.30, 0.49), (2.5, 4.10, 0.44)])
    )
    assert hero is not None
    assert poza_oknem > w_oknie


# --- podłoga drugiego szczebla (progi, nie sama funkcja) ---

def test_progi_maja_sens_wzgledem_siebie():
    """Etykieta «pewna» nie może być łatwiejsza od samej podłogi drabinki —
    inaczej obiecywalibyśmy realny drugi szczebel tam, gdzie go ucięliśmy."""
    assert R.PEWNA_MIN_P_DRUGI >= R.MIN_P_DRUGIEGO_SZCZEBLA
    assert R.VALUE_MIN_P_DRUGI >= R.MIN_P_DRUGIEGO_SZCZEBLA
    assert R.MIN_P_DRUGIEGO_SZCZEBLA > R.MIN_P_SZCZEBLA


# progi liczone WZGLĘDEM stałej, nie wpisane na sztywno: podłoga drugiego
# szczebla ruszała się już dwa razy (0,25 w 08-03, 0,33 w 08-08) i za każdym
# razem test zgłaszał fałszywą awarię zamiast pilnować reguły
@pytest.mark.parametrize("p_drugiego,zostaje", [
    (R.MIN_P_DRUGIEGO_SZCZEBLA + 0.07, 2),   # realny — zostaje
    (R.MIN_P_DRUGIEGO_SZCZEBLA, 2),          # dokładnie na progu — zostaje
    (R.MIN_P_DRUGIEGO_SZCZEBLA - 0.01, 1),   # pod progiem — drabinka się kończy
    (0.08, 1),
])
def test_podloga_ucina_martwy_drugi_szczebel(p_drugiego, zostaje):
    """Odtworzenie reguły z `_rynki_wpisu`: ucinamy na pierwszym szczeblu
    (poza pierwszym), który nie sięga progu."""
    drabinka = [
        {"linia": 0.5, "kurs": 1.4, "p_final": 0.7},
        {"linia": 1.5, "kurs": 3.0, "p_final": p_drugiego},
        {"linia": 2.5, "kurs": 8.0, "p_final": 0.05},
    ]
    for i, s in enumerate(drabinka):
        p_f = s.get("p_final")
        if i >= 1 and p_f is not None and p_f < R.MIN_P_DRUGIEGO_SZCZEBLA:
            drabinka = drabinka[:i]
            break
    assert len(drabinka) == zostaje


# --- ta sama reguła zadana karcie GOTOWEJ (wznowionej z rejestru) ---
# Karta z rejestru nie przechodzi już budowy drabinki, więc bramę trzeba jej
# postawić na zapisanych liczbach — inaczej reguły wprowadzone po publikacji
# omijają cały wznowiony strumień (zmierzone 08.08: 23 z 23 kart na stronie
# pochodziły z rejestru).

def _gotowa(szczeble, hero_linia=0.5):
    return {"hero": {"rynek_kod": "shots", "linia": hero_linia},
            "rynki": [{"rynek_kod": "shots", "drabinka": list(szczeble)}]}


def _s(linia, p_final, traf, z=10, p_model=None):
    return {"linia": linia, "kurs": 2.0, "p_final": p_final,
            "p_model": p_final if p_model is None else p_model,
            "pokrycie": {"z": z, "traf": traf}}


def test_gotowa_karta_bez_nastepnika_to_nie_drabinka():
    assert R.karta_ma_realny_drugi_szczebel(_gotowa([_s(0.5, 0.66, 7)])) is False


def test_gotowa_karta_z_realnym_nastepnikiem_przechodzi():
    karta = _gotowa([_s(0.5, 0.66, 7), _s(1.5, 0.42, 6)])
    assert R.karta_ma_realny_drugi_szczebel(karta) is True


def test_gotowa_karta_odpada_na_pokryciu_nastepnika():
    """Pokrycie to ta sama liczba co przy budowie (MIN_POKRYCIE_DRUGIEGO)."""
    karta = _gotowa([_s(0.5, 0.66, 7), _s(1.5, 0.42, 2)])   # 2/10 < 0,50
    assert R.karta_ma_realny_drugi_szczebel(karta) is False


def test_gotowa_karta_odpada_gdy_nastepnik_jest_martwy():
    karta = _gotowa([_s(0.5, 0.66, 7),
                     _s(1.5, R.MIN_P_DRUGIEGO_SZCZEBLA - 0.05, 6)])
    assert R.karta_ma_realny_drugi_szczebel(karta) is False


def test_nastepnik_oceniany_po_strzyzeniu_tak_jak_hero():
    """Model niżej niż historia -> liczy się średnia z obu, jak w `_oceń_karte`.

    Bez tego brama przepuszczałaby szczeble, które na karcie pokazują już
    inną (niższą) szansę, niż ta, którą przeszły selekcję.
    """
    tuz_nad = R.MIN_P_DRUGIEGO_SZCZEBLA + 0.02
    karta = _gotowa([_s(0.5, 0.66, 7),
                     _s(1.5, tuz_nad, 6, p_model=tuz_nad - 0.10)])
    assert R.karta_ma_realny_drugi_szczebel(karta) is False


@pytest.mark.parametrize("karta", [
    {},                                             # nic
    {"hero": {"rynek_kod": "shots", "linia": 0.5}},  # hero bez drabinki
    {"hero": {"rynek_kod": "shots", "linia": 9.5},   # hero spoza drabinki
     "rynki": [{"rynek_kod": "shots", "drabinka": [_s(0.5, 0.66, 7)]}]},
])
def test_brak_danych_to_nie_odmowa(karta):
    """`None`, nie `False` — brak pola nie dowodzi braku szczebla, a karta
    zdjęta z niewiedzy to ciche odrzucenie z fałszywej przesłanki."""
    assert R.karta_ma_realny_drugi_szczebel(karta) is None
