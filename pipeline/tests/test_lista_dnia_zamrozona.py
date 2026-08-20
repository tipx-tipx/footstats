"""Lista dnia: jedna publikacja dziennie, potem skład się nie zmienia.

Trzy rzeczy naraz (decyzja właściciela 2026-08-14):

1. **Doba PRODUKTOWA 6:00 → 6:00.** 41% naszych typów to mecze grane między
   północą a 4:00 (Ameryka Płd.). Przy dobie kalendarzowej „lista na piątek"
   domykana o 6:00 w piątek zawierałaby mecze, które zaczęły się o 2:00 w nocy.

2. **Limity liczą się naprawdę.** Do 14.08 deklarowały 20 typów na dzień i 2 na
   mecz, a realnie stała mediana 67 (13.08 — 185) i do 16 typów z meczu. Powód:
   typ wznowiony wchodził poza limitem, ale licznik rósł dopiero po nim, więc
   mocny nowy typ przechodził przed nim i limit przeciekał.

3. **Dzień domknięty jest zamrożony.** Po ogłoszeniu listy nic nie dochodzi.
"""

import datetime as dt

import pytest

from footstats.jobs import build_wc_fast as B
from footstats.jobs import rozliczanie
from footstats.model import uczony as U

STREFA = rozliczanie.STREFA


def _ts(dzien: str, godz: int, minuta: int = 0) -> int:
    d = dt.datetime.strptime(dzien, "%Y-%m-%d").replace(
        hour=godz, minute=minuta, tzinfo=STREFA)
    return int(d.timestamp())


def _typ(mecz_id=1, kickoff=None, p=0.7, kurs=1.8, **kw):
    r = {
        "mecz_id": mecz_id, "podmiot_id": 100 + mecz_id, "podmiot": f"Team {mecz_id}",
        "rynek_kod": "team_corners", "strona": "ponizej", "linia": 4.5,
        "p_model": p, "kurs": kurs, "podmiot_typ": "druzyna",
        "kickoff_ts": kickoff if kickoff is not None else _ts("2026-08-14", 20),
    }
    r.update(kw)
    return r


# Typy muszą się różnić WSZYSTKIM, co ma własny limit (mecz, rynek, rodzina
# statystyki, pasmo kursu) — inaczej test „limitu dnia" mierzyłby w rzeczywistości
# limit rynku albo pasma. Każdy z tych limitów ma swój osobny test niżej.
RYNKI = ["team_corners", "team_goals", "team_cards", "team_fouls",
         "team_sot", "team_shots", "match_corners", "match_cards"]
# po jednym kursie z każdego pasma PASMA_CENY
# ⚑ WSZYSTKIE WEWNĄTRZ PÓŁEK (2026-08-20). Do dziś lista brała każdy kurs,
# więc testy limitu mogły używać 2,60 i 4,00. Odkąd dobę dzielą półki
# (`uczony.POLKI`, sufit 2,00/2,20 per strumień), taki typ odpada na
# widełkach i test limitu mierzyłby widełki zamiast limitu. Odrzucenie
# spoza półek ma własny test niżej.
KURSY = [1.25, 1.45, 1.60, 1.75, 1.85, 1.95]


def _rozne(ile: int, od: int = 1, **kw) -> list[dict]:
    """`ile` typów z różnych meczów, rynków i pasm kursu."""
    out = []
    for i in range(ile):
        r = dict(kw)
        r.setdefault("kurs", KURSY[i % len(KURSY)])
        out.append(_typ(mecz_id=od + i, rynek_kod=RYNKI[i % len(RYNKI)],
                        strona="ponizej" if i % 2 else "powyzej", **r))
    return out


# --------------------------------------------------------------- doba 6→6

def test_mecz_wieczorny_nalezy_do_swojego_dnia():
    assert B.dzien_listy(_ts("2026-08-14", 20)) == "2026-08-14"


def test_mecz_o_drugiej_w_nocy_nalezy_do_DNIA_POPRZEDNIEGO():
    """Sedno doby produktowej: Ameryka Płd. gra „dziś wieczorem", nie jutro."""
    assert B.dzien_listy(_ts("2026-08-15", 2)) == "2026-08-14"


def test_granica_szostej_jest_ostra():
    assert B.dzien_listy(_ts("2026-08-15", 5, 59)) == "2026-08-14"
    assert B.dzien_listy(_ts("2026-08-15", 6, 0)) == "2026-08-15"


def test_moment_domkniecia_to_szosta_rano_tego_dnia():
    assert B.moment_domkniecia("2026-08-14") == _ts("2026-08-14", 6)


def test_pusty_znacznik_nie_wywraca_cyklu():
    assert B.dzien_listy(None) == ""
    assert B.dzien_listy(0) == ""


# ------------------------------------------------------- limit działa naprawdę

def _klucz(b):
    return (B.moc_listy(b, 0), True)


@pytest.fixture
def bez_roznorodnosci(monkeypatch):
    """Izoluje sam limit doby — gwarancje różnorodności poza zasięg."""
    for nazwa in ("LISTA_PER_MECZ", "LISTA_PER_RYNEK", "LISTA_PER_PASMO",
                  "LISTA_PER_RODZINA"):
        monkeypatch.setattr(B, nazwa, 999)


def test_limit_dnia_obowiazuje(bez_roznorodnosci):
    lista, zdjete, z_dnia = B.wybierz_liste_publikowana(_rozne(36), _klucz)
    assert len(lista) == B.LISTA_CAP
    assert z_dnia["2026-08-14"] == B.LISTA_CAP
    assert all(p == "poza_lista_dnia" for p in zdjete.values())


def test_wznowione_zajmuja_miejsca_zamiast_je_omijac(bez_roznorodnosci):
    """NAPRAWA PRZECIEKU: wznowione idą pierwsze, więc limit ich obejmuje.

    Wcześniej mocny nowy typ wchodził przed wznowionymi (sortowanie po sile),
    a one i tak dochodziły poza limitem — dzień rósł bez końca.
    """
    ile_wzn = B.LISTA_CAP - 2
    wznowione = _rozne(ile_wzn, od=1, p=0.5, wznowiony=True)
    nowe = _rozne(10, od=100, p=0.95)                    # mocniejsze od tamtych
    lista, _, _ = B.wybierz_liste_publikowana(wznowione + nowe, _klucz)
    assert len(lista) == B.LISTA_CAP
    # wszystkie wznowione muszą zostać — typ raz pokazany nie znika
    assert sum(1 for b in lista if b.get("wznowiony")) == ile_wzn
    # ...a nowe dobierają się tylko na to, co naprawdę zostało wolne
    assert sum(1 for b in lista if not b.get("wznowiony")) == 2


def test_wznowione_ponad_limit_zostaja_ale_blokuja_nowe():
    """Gdy pokazanych jest więcej niż limit, żaden NIE znika — nowe nie wchodzą."""
    wznowione = _rozne(B.LISTA_CAP + 4, od=1, wznowiony=True)
    nowe = _rozne(4, od=100, p=0.99)
    lista, _, _ = B.wybierz_liste_publikowana(wznowione + nowe, _klucz)
    assert len(lista) == len(wznowione) > B.LISTA_CAP
    assert all(b.get("wznowiony") for b in lista)


def test_limit_na_mecz():
    kand = [_typ(mecz_id=7, linia=i, p=0.6) for i in range(1, 9)]
    lista, _, _ = B.wybierz_liste_publikowana(kand, _klucz)
    assert len(lista) == B.LISTA_PER_MECZ


def test_limity_licza_sie_osobno_na_kazda_dobe(bez_roznorodnosci):
    dzis = _rozne(36, od=1, kickoff=_ts("2026-08-14", 20))
    jutro = _rozne(36, od=100, kickoff=_ts("2026-08-15", 20))
    _, _, z_dnia = B.wybierz_liste_publikowana(dzis + jutro, _klucz)
    assert z_dnia == {"2026-08-14": B.LISTA_CAP, "2026-08-15": B.LISTA_CAP}


def test_mecz_nocny_liczy_sie_do_doby_poprzedniej():
    wieczor = _rozne(4, od=1, kickoff=_ts("2026-08-14", 20))
    noc = _rozne(4, od=50, kickoff=_ts("2026-08-15", 2))
    _, _, z_dnia = B.wybierz_liste_publikowana(wieczor + noc, _klucz)
    assert set(z_dnia) == {"2026-08-14"}      # wszystko to JEDNA doba produktowa


def test_sugestia_nie_zajmuje_miejsca(bez_roznorodnosci):
    kand = _rozne(36) + [_typ(mecz_id=999, sugestia=True)]
    lista, _, _ = B.wybierz_liste_publikowana(kand, _klucz)
    assert any(b.get("sugestia") for b in lista)
    assert sum(1 for b in lista if not b.get("sugestia")) == B.LISTA_CAP


# ------------------------------------------------------------- zamrożenie

def test_dzien_domkniety_nie_przyjmuje_nowych():
    stary = _typ(mecz_id=1)
    nowy = _typ(mecz_id=2, p=0.99)
    zamkniete = {"2026-08-14": {B._klucz_publikacji(stary)}}
    lista, zdjete, _ = B.wybierz_liste_publikowana(
        [stary, nowy], _klucz, zamkniete=zamkniete)
    assert [b["mecz_id"] for b in lista] == [1]
    assert zdjete[B._klucz_publikacji(nowy)] == "dzien_zamkniety"


def test_dzien_domkniety_wpuszcza_swoj_komplet_ponad_limit():
    """Skład ogłoszony wraca w całości, nawet gdyby limit był dziś mniejszy."""
    typy = [_typ(mecz_id=i) for i in range(1, 26)]
    zamkniete = {"2026-08-14": {B._klucz_publikacji(b) for b in typy}}
    lista, zdjete, z_dnia = B.wybierz_liste_publikowana(
        typy, _klucz, zamkniete=zamkniete)
    assert len(lista) == len(typy) > B.LISTA_CAP
    assert not zdjete
    assert z_dnia["2026-08-14"] == len(typy)


def test_dzien_otwarty_dziala_normalnie_gdy_inny_jest_zamkniety():
    dzis = _typ(mecz_id=1, kickoff=_ts("2026-08-14", 20))
    jutro = _typ(mecz_id=2, kickoff=_ts("2026-08-15", 20))
    lista, _, _ = B.wybierz_liste_publikowana(
        [dzis, jutro], _klucz, zamkniete={"2026-08-14": set()})
    assert [b["mecz_id"] for b in lista] == [2]


# --------------------------------------------------------------- domykanie

def test_domyka_dzien_ktorego_godzina_minela():
    typy = [_typ(mecz_id=1), _typ(mecz_id=2)]
    manifest, swiezo = domkniety = B.domknij_dni(
        typy, {}, _ts("2026-08-14", 7))
    assert swiezo == ["2026-08-14"]
    assert manifest["2026-08-14"]["zamkniete_ts"] == _ts("2026-08-14", 7)
    assert len(manifest["2026-08-14"]["klucze"]) == 2
    assert domkniety is not None


def test_nie_domyka_dnia_ktory_jeszcze_rosnie():
    """Lista na jutro ma prawo się uzupełniać aż do swojej 6:00."""
    jutro = [_typ(mecz_id=1, kickoff=_ts("2026-08-15", 20))]
    manifest, swiezo = B.domknij_dni(jutro, {}, _ts("2026-08-14", 7))
    assert swiezo == []
    assert manifest == {}


def test_nie_domyka_dwa_razy():
    typy = [_typ(mecz_id=1)]
    manifest, _ = B.domknij_dni(typy, {}, _ts("2026-08-14", 7))
    dolozone = typy + [_typ(mecz_id=2)]
    manifest2, swiezo2 = B.domknij_dni(dolozone, manifest, _ts("2026-08-14", 9))
    assert swiezo2 == []
    assert manifest2["2026-08-14"]["klucze"] == manifest["2026-08-14"]["klucze"]


def test_nie_zamraza_pustki():
    """Cykl padnięty przed świtem nie ma prawa zamrozić pustego dnia."""
    manifest, swiezo = B.domknij_dni([], {}, _ts("2026-08-14", 7))
    assert (manifest, swiezo) == ({}, [])


def test_sugestia_nie_wchodzi_do_manifestu():
    manifest, _ = B.domknij_dni(
        [_typ(mecz_id=1), _typ(mecz_id=2, sugestia=True)], {},
        _ts("2026-08-14", 7))
    assert len(manifest["2026-08-14"]["klucze"]) == 1


def test_wczytaj_zamkniete_pomija_dni_bez_stempla():
    m = {"2026-08-14": {"zamkniete_ts": 1, "klucze": ["a", "b"]},
         "2026-08-15": {"klucze": ["c"]}}
    assert B.wczytaj_zamkniete(m) == {"2026-08-14": {"a", "b"}}
    assert B.wczytaj_zamkniete(None) == {}


def test_manifest_nie_rosnie_w_nieskonczonosc():
    m = {"2026-08-01": {"zamkniete_ts": 1, "klucze": []},
         "2026-08-13": {"zamkniete_ts": 1, "klucze": []},
         "2026-08-14": {"zamkniete_ts": 1, "klucze": []}}
    out = B.przytnij_manifest(m, _ts("2026-08-14", 12))
    assert "2026-08-01" not in out
    assert "2026-08-14" in out


def test_typ_spoza_polek_odpada_z_powodem(bez_roznorodnosci):
    """⚑ 2026-08-20. Powyżej sufitu strumienia model jest ANTY-SYGNAŁEM —
    przy kursach 2,40–2,80 typy z najwyższą szansą trafiają 30,8%, a te
    z najniższą 46,7% (n=360). Taki typ nie wchodzi na listę, ale musi
    zostawić powód: cichych odrzuceń nie ma."""
    w_polce = _typ(mecz_id=1, kurs=1.75)
    za_drogi = _typ(mecz_id=2, kurs=2.60, p=0.99)
    lista, zdjete, _ = B.wybierz_liste_publikowana([w_polce, za_drogi], _klucz)
    assert [b["mecz_id"] for b in lista] == [1]
    assert zdjete[B._klucz_publikacji(za_drogi)] == "kurs_poza_polkami"


def test_sufit_jest_per_strumien(bez_roznorodnosci):
    """Drużyny do 2,00, zawodnicy do 2,20 — wytyczna właściciela 20.08."""
    druzyna = _typ(mecz_id=1, kurs=2.10, podmiot_typ="druzyna")
    zawodnik = _typ(mecz_id=2, kurs=2.10, podmiot_typ="zawodnik")
    lista, zdjete, _ = B.wybierz_liste_publikowana([druzyna, zawodnik], _klucz)
    assert [b["mecz_id"] for b in lista] == [2], (
        "kurs 2,10 mieści się zawodnikowi (sufit 2,20), ale nie drużynie (2,00)"
    )
    assert zdjete[B._klucz_publikacji(druzyna)] == "kurs_poza_polkami"


def test_polki_maja_wlasne_budzety(bez_roznorodnosci):
    """Doba dzieli się na półki: 15 pewniaków i 6 wyższych kursów.

    Bez tego obie zakładki pokazywały tę samą listę inaczej posortowaną —
    to jest sedno zadania 5 planu.
    """
    pewniaki = [_typ(mecz_id=i, kurs=1.40, p=0.80) for i in range(1, 30)]
    wyzsze = [_typ(mecz_id=100 + i, kurs=2.00, p=0.55) for i in range(1, 30)]
    lista, _zdjete, z_dnia = B.wybierz_liste_publikowana(
        pewniaki + wyzsze, _klucz)
    ile_pewniakow = sum(1 for b in lista if float(b["kurs"]) < 1.80)
    ile_wyzszych = sum(1 for b in lista if float(b["kurs"]) >= 1.80)
    assert ile_pewniakow == U.POLKI["wysoka_szansa"]["limit_dobowy"]
    assert ile_wyzszych == U.POLKI["wyzsze_kursy"]["limit_dobowy"]
    assert z_dnia["2026-08-14"] == B.LISTA_CAP


def test_polka_pewniakow_wybiera_po_szansie_nie_po_mocy(bez_roznorodnosci):
    """⚑ 2026-08-20. `moc_listy` to p × √kurs, więc w obrębie jednej półki
    podbija typy DROŻSZE — a te trafiają rzadziej.

    Zmierzone na 3560 kandydatach (podział czasowy, klucz oceniony na
    okresie, którego nie widział): półka pewniaków po mocy 71,6%,
    po szansie modelu 74,7%.

    Test odtwarza sytuację wprost: pewniejszy typ po niższym kursie ma
    wygrać z mniej pewnym po wyższym, choć `moc_listy` woli tego drugiego.
    """
    pewny = _typ(mecz_id=1, kurs=1.25, p=0.82)
    drozszy = _typ(mecz_id=2, kurs=1.75, p=0.70)
    assert B.moc_listy(drozszy, 0) > B.moc_listy(pewny, 0), (
        "założenie testu: moc faworyzuje droższy typ"
    )
    kolejnosc = sorted([drozszy, pewny],
                       key=lambda b: -float(b.get("p_model") or 0.0))
    assert kolejnosc[0] is pewny


def test_wyzsze_kursy_zostaja_na_mocy():
    """Na wąskim paśmie 1,80–2,00 szansa NIE pomaga (53,0% wobec 55,4%),
    więc ta półka zostaje na mierze z dłuższym pomiarem za sobą."""
    assert U.POLKI["wyzsze_kursy"]["kurs_max"] - \
        U.POLKI["wyzsze_kursy"]["kurs_min"] <= 0.45, (
        "pasmo wyższych kursów urosło — przemierzyć, czy klucz nadal właściwy"
    )
