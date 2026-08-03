"""Bank stylu zna drużynę pod nazwą z 365Scores, silnik pyta nazwą ze statshub.

POWÓD (2026-08-03). Superbet kwotuje kartki, strzały, celne i faule drużynowe,
a my ich nawet nie odrzucaliśmy — bo `_hist_z_banku` szukał historii po
DOKŁADNYM kluczu i nie znajdował nic:

    statshub „sarmiento"  ->  bank „sarmiento junin"
    statshub „viborg ff"  ->  bank „viborg"

Zmierzone na żywym banku: połowa drużyn najbliższych meczów „nie istniała",
choć siedziała w nim pod nazwą 365. Ten sam klucz liczy „ubogie" drużyny
w doganianiu banku, więc te drużyny co cykl zabierały cały budżet, pobierały
mecze już obecne w banku i dopisywały zero.
"""

import pytest

from footstats.jobs import build_wc_fast as bwf


@pytest.fixture
def bank():
    return {
        "gry": {
            "1": {"ts": 100, "druzyny": {"sarmiento junin": {"kartki": 2.0},
                                         "rival a": {"kartki": 1.0}}},
            "2": {"ts": 200, "druzyny": {"sarmiento junin": {"kartki": 3.0},
                                         "rival b": {"kartki": 2.0}}},
        }
    }


def test_alias_idzie_przez_ID_a_nie_przez_podobienstwo_nazw(bank, monkeypatch):
    """Klucz sprawy: „dundee" zawiera się w „dundee united", więc dopasowanie
    po nazwach wskazałoby CUDZĄ historię. Id 365 na to nie pozwala."""
    bank["gry"]["3"] = {"ts": 300,
                        "druzyny": {"dundee united": {"kartki": 5.0},
                                    "rival c": {"kartki": 1.0}}}
    monkeypatch.setattr(bwf.scores365, "competitor_ids_z_rozgrywek",
                        lambda _c: {"sarmiento junin": 7117,
                                    "dundee united": 999})
    # `dopasuj_druzyne` rozstrzyga po ID i dla „dundee" nie ma jednoznacznego
    monkeypatch.setattr(bwf.scores365, "dopasuj_druzyne",
                        lambda mapa, nm: 7117 if "sarmiento" in nm else None)
    bwf.zbuduj_aliasy_banku(bank, {"Sarmiento", "Dundee FC"}, [72])
    assert bank["alias"] == {"sarmiento": ["sarmiento junin"]}
    assert "dundee fc" not in bank["alias"]


def test_alias_scala_dwa_zapisy_tej_samej_druzyny(bank, monkeypatch):
    """Ta sama drużyna bywa w banku pod dwoma nazwami — historia jest wtedy
    ROZBITA i trzeba ją scalić, a nie wybrać jednej połowy."""
    bank["gry"]["3"] = {"ts": 300, "druzyny": {"ca sarmiento": {"kartki": 4.0},
                                               "rival c": {"kartki": 1.0}}}
    monkeypatch.setattr(bwf.scores365, "competitor_ids_z_rozgrywek",
                        lambda _c: {"sarmiento junin": 7117, "ca sarmiento": 7117})
    monkeypatch.setattr(bwf.scores365, "dopasuj_druzyne", lambda mapa, nm: 7117)
    bwf.zbuduj_aliasy_banku(bank, {"Sarmiento"}, [72])
    assert bank["alias"]["sarmiento"] == ["ca sarmiento", "sarmiento junin"]


def test_druzyna_znana_pod_aliasem_przestaje_zabierac_budzet(bank, monkeypatch):
    """Bez tego lista „ubogich" zawierała ją w KAŻDYM cyklu: pobranie tych
    samych meczów, zero dopisanych, i tak w kółko."""
    bank["alias"] = {"sarmiento": ["sarmiento junin"]}
    for i in range(3, 9):                      # razem 8 gier pod nazwą 365
        bank["gry"][str(i)] = {"ts": i, "druzyny": {"sarmiento junin": {"kartki": 1.0},
                                                    "x": {"kartki": 1.0}}}
    wolane = []
    monkeypatch.setattr(bwf.scores365, "competitor_ids_z_rozgrywek",
                        lambda _c: wolane.append("id_map") or {})
    assert bwf.dolej_historie_wlasna(bank, {"Sarmiento"}, [72]) == 0
    # nie ruszyliśmy nawet po mapę id — nie ma dla kogo
    assert wolane == []


def test_alias_nie_powstaje_dla_druzyny_ktorej_bank_nie_zna(bank, monkeypatch):
    """Alias ma wskazywać istniejącą historię, nie tworzyć pustego wpisu —
    inaczej doganianie uznałoby drużynę za znaną i nigdy by jej nie pobrało."""
    monkeypatch.setattr(bwf.scores365, "competitor_ids_z_rozgrywek",
                        lambda _c: {"nowy klub fc": 555})
    monkeypatch.setattr(bwf.scores365, "dopasuj_druzyne", lambda mapa, nm: 555)
    bwf.zbuduj_aliasy_banku(bank, {"Nowy Klub"}, [72])
    assert bank.get("alias") == {}
