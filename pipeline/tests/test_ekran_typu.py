"""Stempel ekranu: na której zakładce typ się pokazał (2026-08-02).

POWÓD. Księga zapisywała, CZY typ poszedł na stronę, ale nigdy GDZIE, więc
Skuteczność zgadywała po kodzie rynku — i zgadywała źle: `match_corners` nie
zaczyna się od `team_`, więc rożne całych meczów lądowały w zakładce
„Zawodnicy". Zgłoszenie usera 2026-08-02: „są jakieś typy z niedzieli, mimo
że nic nie pokazywało". Na żywej księdze dotyczyło to 146 rekordów.
"""

from footstats.jobs import rozliczanie
from footstats.model import betting


def test_ekran_z_rekordu_swiezego():
    E = betting.ekran_typu
    assert E({"podmiot_typ": "zawodnik", "rynek_kod": "shots", "pewniak": True}) \
        == "wysokie_szanse"
    assert E({"podmiot_typ": "druzyna", "rynek_kod": "team_goals"}) == "druzyny"
    assert E({"zrodlo": "drabinka", "rynek_kod": "shots"}) == "drabinki"


def test_nowe_rynki_to_druzyny_a_nie_zawodnicy():
    """SEDNO zgłoszenia: sumy meczowe i „kto więcej" nie mają `team_`."""
    for kod in ("match_corners", "match_cards", "wiecej_shots", "wiecej_corners"):
        assert betting.ekran_typu({"rynek_kod": kod}) == "druzyny", kod
        # i to samo z perspektywy strumienia uczenia
        assert rozliczanie._strumien({"rynek_kod": kod, "ekran": "druzyny"}) \
            == "druzyny"


def test_typ_zawodniczy_bez_pewniaka_nie_stoi_na_zadnej_liscie():
    """Od 2026-08-01 („Wszystko" i „Okazje" usunięte) nie ma zakładki, która
    by go listowała — więc nie wolno go liczyć do wyniku „Wysokich szans"."""
    assert betting.ekran_typu(
        {"podmiot_typ": "zawodnik", "rynek_kod": "shots", "pewniak": False}
    ) == "poza_lista"
    # dla warstwy uczenia to nadal ten sam produkt co „wysokie szanse":
    # strumienie dzielą PRODUKTY, nie ekrany
    assert rozliczanie._strumien({"ekran": "poza_lista"}) == "pewniaki"


def test_odtworzenie_historii_jest_oznaczone_i_idempotentne():
    log = {
        "a": {"rynek_kod": "match_corners", "wynik": "wygrany"},
        "b": {"rynek_kod": "shots", "pewniak": True, "wynik": "przegrany"},
        "c": {"rynek_kod": "shots", "ekran": "poza_lista"},   # już ostemplowany
    }
    assert rozliczanie._uzupelnij_ekrany(log) == 2
    assert log["a"]["ekran"] == "druzyny" and log["a"]["ekran_odtworzony"]
    assert log["b"]["ekran"] == "wysokie_szanse"
    # rekord ze stemplem zostaje NIETKNIĘTY — także jego brak flagi odtworzenia
    assert "ekran_odtworzony" not in log["c"]
    # drugi przebieg nic już nie zmienia (cykl chodzi co 20 minut)
    assert rozliczanie._uzupelnij_ekrany(log) == 0


def test_stempel_wygrywa_z_kodem_rynku():
    """Gdyby reguła kiedyś się zmieniła, zapis z chwili publikacji ma rację —
    historii nie przepisujemy pod nową regułę."""
    rec = {"rynek_kod": "shots", "pewniak": True, "ekran": "drabinki"}
    assert rozliczanie._strumien(rec) == "drabinki"


# --- DOBA LICZONA PO POLSKU, NIE PO SERWEROWEMU (2026-08-03) ---------------
#
# Dni w Skuteczności grupował `time.localtime()`, czyli strefa maszyny — a cykl
# chodzi na GitHub Actions, gdzie jest UTC. Mecz o 00:30 czasu polskiego trafiał
# do rozliczeń DZIEŃ WCZEŚNIEJ. Zmierzone: 107 z 987 rozliczonych typów (11%)
# pod złą datą, głównie Ameryka Płd. i MLS. Zgłoszenie usera: „wczoraj było 10
# typów w drabinkach, a nie widzę dziś 10 w rozliczeniach".

def test_doba_konczy_sie_o_polnocy_CZASU_POLSKIEGO():
    # 2026-08-01 23:30 UTC = 2026-08-02 01:30 w Warszawie (lato, UTC+2)
    assert rozliczanie.dzien_pl(1785627000) == "2026-08-02"
    # 2026-08-02 21:00 UTC = 2026-08-02 23:00 w Warszawie — ten sam dzień
    assert rozliczanie.dzien_pl(1785704400) == "2026-08-02"


def test_mecz_nocny_trafia_do_dnia_ktory_widzi_user(monkeypatch):
    """Racing Club – Tigre, 2.08 o 01:30 czasu polskiego. Serwer w UTC widzi
    1 sierpnia; user, kalendarz i cała reszta UI widzą 2 sierpnia."""
    rec = {
        "kickoff_ts": 1785627000, "wynik": "wygrany", "kurs": 1.8,
        "p_model": 0.6, "rynek_kod": "shots", "rynek": "Strzały",
        "podmiot": "X", "linia": 1.5, "strona": "powyzej", "mecz": "A – B",
    }
    dni = rozliczanie.skutecznosc_per_dzien([rec])
    assert [d["dzien"] for d in dni] == ["2026-08-02"]
