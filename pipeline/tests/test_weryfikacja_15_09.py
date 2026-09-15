"""Usterki znalezione przy weryfikacji produkcji 15.09 (wdrożenia z 14.09).

1. Betclic w kartkach i spalonych podaje KLUB jako etykietę gałęzi, a zawodnika
   w nazwie zakładu — wszyscy gracze lądowali pod kluczem „genoa".
2. Pamięć ofert Betclica nie niosła nazwisk w oryginale, więc odkrywanie
   pytało wyszukiwarkę posortowanym kluczem („luongo massimo") — 10 odkrytych
   zawodników na cykl zamiast ~190.
3. Rotowire: encje HTML w nazwach drużyn („Atl&eacute;tico Madrid").
4. Brama składu liczyła starty względem kalendarza, którego magazyn nie
   odświeżał od 18.08 — etatowy starter wychodził „2 z 10".
5. Księga wznawiała typy, które nigdy nie stały na stronie, a wznowione
   omijają limity doby (24 typy zawodnicze przy limicie 21).
"""
import time

from footstats.jobs import build_wc_fast as B
from footstats.jobs import radar
from footstats.model import betting
from footstats.sources import betclic, rotowire
from footstats.sources.statshub import StatshubTrend

TERAZ = 1_800_000_000
DZIEN = 86_400


# --- 1. Betclic: klub jako etykieta gałęzi ---

def _oferta(zaklady_kartek):
    return {
        "id": 7, "nazwa": "Genoa - Sudtirol", "kickoff_ts": TERAZ,
        "gospodarz": "Genoa", "gosc": "Sudtirol",
        "druzyny": [{"nazwa": "Genoa", "gracze": []},
                    {"nazwa": "Sudtirol", "gracze": []}],
        "rynki": [
            {"nazwa": "Liczba kartek zawodnika", "zaklady": zaklady_kartek},
            {"nazwa": "Liczba strzałów zawodnika", "zaklady": [
                {"podmiot": "Lorenzo Colombo", "nazwa": "Powyżej 1,5",
                 "kurs": 1.9, "gracze": []},
            ]},
        ],
    }


def test_kartki_z_klubem_w_etykiecie_ida_do_zawodnikow(monkeypatch):
    monkeypatch.setattr(betclic, "oferta_pelna", lambda *a, **k: _oferta([
        {"podmiot": "Genoa", "nazwa": "Kingsley Ehizibue Powyżej 0,5",
         "kurs": 4.5, "gracze": []},
        {"podmiot": "Genoa", "nazwa": "Leo Östigard Powyżej 0,5",
         "kurs": 3.8, "gracze": []},
        {"podmiot": "Sudtirol", "nazwa": "Bez strony zakładu", "kurs": 2.0,
         "gracze": []},
    ]))
    p = betclic.kursy_zawodnikow(7)
    gracze = p["players"]
    assert "genoa" not in gracze and "sudtirol" not in gracze
    assert gracze["ehizibue kingsley"]["yellow_card"] == {0.5: {"over": 4.5}}
    assert gracze["leo ostigard"]["yellow_card"] == {0.5: {"over": 3.8}}
    assert p["player_names"]["ehizibue kingsley"] == "Kingsley Ehizibue"
    # zwykła etykieta z nazwiskiem działa jak dotąd
    assert gracze["colombo lorenzo"]["shots"] == {1.5: {"over": 1.9}}


def test_osoba_z_nazwy_zakladu():
    assert betclic._osoba_z_nazwy_zakladu("Álvaro García Rivera Poniżej 1,5") == (
        "Álvaro García Rivera", "Poniżej 1,5")
    assert betclic._osoba_z_nazwy_zakladu("Powyżej 0,5")[0] == ""


# --- 2. nazwiska w pamięci Betclica i kolejność odkrywania ---

def test_pamiec_betclica_oddaje_nazwiska_w_oryginale():
    pamiec = {"101": {"ts": TERAZ - 600,
                      "players": {"hidde avest ter": {"shots": {"0.5": {"over": 1.5}}}},
                      "player_names": {"hidde avest ter": "Hidde ter Avest"}}}
    out = B.bc_z_pamieci({101: TERAZ + 3 * 3600}, pamiec, TERAZ)
    assert out[101]["player_names"] == {"hidde avest ter": "Hidde ter Avest"}
    # wpis sprzed zmiany (bez mapy) dalej się czyta
    del pamiec["101"]["player_names"]
    assert "player_names" not in B.bc_z_pamieci({101: TERAZ + 3 * 3600}, pamiec, TERAZ)[101]


def test_odkrywanie_szuka_nazwiskiem_w_oryginale_i_najpierw_nazwanych(monkeypatch):
    pytania: list[str] = []
    monkeypatch.setattr(radar.statshub, "search_players",
                        lambda q: pytania.append(q) or [])
    sb = {
        "players": {
            # bez nazwiska w oryginale, ale z największą liczbą rynków
            "luongo massimo": {"shots": {0.5: {}}, "sot": {0.5: {}}, "fouls_committed": {1.5: {}}},
            "hidde avest ter": {"shots": {0.5: {}}},
        },
        "player_names": {"hidde avest ter": "Hidde ter Avest"},
    }
    radar.debiutanci_meczu(sb, [], (1, 2), [0], min_rynkow=1)
    assert pytania == ["Hidde ter Avest", "luongo massimo"]


# --- 3. Rotowire: encje HTML ---

def test_rotowire_rozkodowuje_encje(monkeypatch):
    blok = ('<div class="lineup is-soccer">'
            '<div class="lineup__mteam">Atl&eacute;tico Madrid</div>'
            '<div class="lineup__mteam">Osasuna</div>'
            '<ul class="lineup__list is-home">x<li title="Jan Oblak"></li>'
            '<li title="Pablo Barrios"></li></ul>'
            '<ul class="lineup__list is-visit">x<li title="Ante Budimir"></li></ul>'
            '</div>')

    class _R:
        text = blok

        def raise_for_status(self):
            return None

    monkeypatch.setattr(rotowire.requests, "get", lambda *a, **k: _R())
    r = rotowire.fetch_predicted_lineups(include_tomorrow=False)
    assert rotowire.predicted_status(r, "Atlético Madrid", "Jan Oblak") is True


# --- 4. nieaktualny kalendarz drużyny ---

def _trend(grane_dni):
    n = len(grane_dni)
    return StatshubTrend(
        player_id=1, player_name="Martin Tejon", position="M", team_id=100,
        team_name="Marítimo", opponent_id=200, opponent_name="Gil Vicente",
        is_home=False, market_code="shots", line=0.5, in_predicted_lineup=False,
        league_average=None, opponent_average=None, opponent_rank=None,
        total_ranks=None, event_id=999,
        counts=[1.0] * n, minutes=[90.0] * n,
        timestamps=[TERAZ - d * DZIEN for d in grane_dni], started=[True] * n,
    )


def test_kalendarz_starszy_niz_wystepy_nie_rozstrzyga():
    """Tejon: 6/6 startów w sezonie, magazyn z ostatnim meczem sprzed 37 dni."""
    tr = _trend([1, 10, 17, 24, 30, 38, 150, 178])
    kal = {100: [TERAZ - d * DZIEN for d in (38, 130, 136, 144, 150, 158, 165, 171, 178, 185)]}
    assert radar.dopelnij_meczami_druzyny(tr, kal, TERAZ) is None
    # wraca stara miara z samych występów — 8/8 startów
    assert radar.udzial_startow(tr, kalendarz=kal, teraz=TERAZ) == 1.0


def test_swiezy_kalendarz_dalej_liczy_opuszczone_mecze():
    tr = _trend([1, 15])
    kal = {100: [TERAZ - d * DZIEN for d in (1, 8, 15, 22, 29)]}
    assert radar.udzial_startow(tr, kalendarz=kal, teraz=TERAZ) == 0.4
    # mecz kadry 10 dni po ostatnim meczu klubu to jeszcze nie nieaktualny kalendarz
    kadra = _trend([1, 15])
    kal2 = {100: [TERAZ - d * DZIEN for d in (11, 18, 25)]}
    assert radar.dopelnij_meczami_druzyny(kadra, kal2, TERAZ) is not None


# --- 5. wznowienia z księgi tylko dla typów pokazanych ---

def _stub_supa(monkeypatch, magazyn: dict):
    monkeypatch.setattr(B.supa, "get_key_ok", lambda k: (magazyn.get(k), True))
    monkeypatch.setattr(B.supa, "get_key", lambda k: magazyn.get(k))
    monkeypatch.setattr(B.supa, "put_key", lambda k, v: magazyn.__setitem__(k, v) or True)
    monkeypatch.setattr(B, "_dry_run", lambda: False)


def _wpis(linia, kickoff):
    return {
        "mecz_id": 1, "mecz": "Platense – Fluminense", "kickoff_ts": kickoff,
        "podmiot_id": 5, "podmiot": "Hulk", "rynek_kod": "sot",
        "rynek": "Celne strzały", "linia": linia, "strona": "powyzej",
        "kurs": 2.87, "p_model": 0.5, "sugestia": False, "wynik": None,
        "opublikowano_ts": 1000, "wersje": betting.wersje_publikacji(),
    }


def test_ksiega_nie_wznawia_typu_ktorego_nie_bylo_na_stronie(monkeypatch):
    kickoff = int(time.time()) + 7200
    pokazany, niepokazany = _wpis(0.5, kickoff), _wpis(1.5, kickoff)
    magazyn = {"pokazane_na_stronie": {
        "od_ts": kickoff - 5 * DZIEN,
        "klucze": {B.rozliczanie._klucz(pokazany): kickoff},
    }}
    _stub_supa(monkeypatch, magazyn)
    out, wzn = B.scal_z_publikacjami(
        [], {}, typy_log={"a": pokazany, "b": niepokazany})
    assert wzn == 1 and [b["linia"] for b in out] == [0.5]


def test_ksiega_bez_zapisu_pokazanych_wznawia_jak_dotad(monkeypatch):
    kickoff = int(time.time()) + 7200
    _stub_supa(monkeypatch, {})
    out, wzn = B.scal_z_publikacjami(
        [], {}, typy_log={"a": _wpis(0.5, kickoff), "b": _wpis(1.5, kickoff)})
    assert wzn == 2
