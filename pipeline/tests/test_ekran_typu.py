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
