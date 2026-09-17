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
from collections import Counter

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
    # historia_pelna: od 17.09 kalendarz orzeka „opuścił mecz" tylko przy
    # historii z performance (podejrzanych dociąga `dociagnij_pelne_wystepy`)
    n = len(grane_dni)
    return StatshubTrend(
        historia_pelna=True,
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


# --- 6. Connell i Senesi: kalendarz z feedu, nieobecność, wznowione karty ---

from footstats.jobs import magazyn_druzyn as MD


def _kolega(pid, grane_dni, rywale, team_id=23, minuty=90.0):
    return StatshubTrend(
        historia_pelna=True,
        player_id=pid, player_name=f"G{pid}", position="M", team_id=team_id,
        team_name="Barnsley", opponent_id=9, opponent_name="Peterborough",
        is_home=False, market_code="shots", line=0.5, in_predicted_lineup=False,
        league_average=None, opponent_average=None, opponent_rank=None,
        total_ranks=None, event_id=1, counts=[1.0] * len(grane_dni),
        minutes=[minuty] * len(grane_dni),
        timestamps=[TERAZ - d * DZIEN for d in grane_dni],
        started=[True] * len(grane_dni), game_opponent_ids=list(rywale),
    )


def test_kalendarz_z_feedu_zna_mecze_bez_zawodnika():
    """Connell grał do 22.08; koledzy grali dalej — te mecze są w feedzie."""
    koledzy = [_kolega(p, [3, 10, 17], [101, 102, 103]) for p in range(1, 6)]
    connell = _kolega(99, [24, 31], [104, 105])
    kal = MD.kalendarz_z_feedu(koledzy + [connell])
    assert len(kal[23]) == 3                       # 24 i 31 dni: tylko jeden gracz
    assert radar.nie_gral_ostatnio(connell, kal, TERAZ) is True
    assert radar.nie_gral_ostatnio(koledzy[0], kal, TERAZ) is False


def test_mecze_kadry_nie_udaja_meczu_klubu():
    """Ten sam dzień, różni rywale (różne reprezentacje) — to nie jest mecz klubu."""
    kadra = [_kolega(p, [5], [900 + p]) for p in range(1, 8)]
    klub = [_kolega(p, [2], [101]) for p in range(1, 8)]
    kal = MD.kalendarz_z_feedu(kadra + klub)
    assert kal[23] == [TERAZ - 2 * DZIEN]


def test_scal_kalendarze_dokłada_tylko_brakujace():
    out = MD.scal_kalendarze({23: [TERAZ - 40 * DZIEN]},
                             {23: [TERAZ - 3 * DZIEN, TERAZ - 40 * DZIEN + 3600]})
    assert out[23] == [TERAZ - 3 * DZIEN, TERAZ - 40 * DZIEN]


def test_karta_bez_gry_w_ostatnich_meczach_odpada_chyba_ze_w_skladzie():
    w = {"minuty_sr6": 88, "udzial_startow": 0.7, "nie_gral_ostatnio": True}
    powody = Counter()
    assert radar._oceń_karte(w, powody) == (0.0, None)
    assert powody["nie_gral_w_ostatnich_meczach"] == 1


def test_wznowiona_karta_zawodnika_ktory_nie_gra_schodzi(monkeypatch):
    kickoff = int(time.time()) + 7200
    karta = {"mecz_id": 1, "podmiot_id": 830659, "podmiot": "Marcos Senesi",
             "kickoff_ts": kickoff, "hero": {"rynek_kod": "fouls_won", "linia": 0.5}}
    magazyn = {B.PUBLIKACJE_KART_KLUCZ: {"k": {"wpis": karta, "kickoff_ts": kickoff,
                                                "opublikowano_ts": 1}}}
    _stub_supa(monkeypatch, magazyn)
    monkeypatch.setattr(radar, "karta_ma_realny_drugi_szczebel", lambda w: True)
    assert B.scal_karty_z_publikacjami([], wypadli={830659}) == []
    magazyn[B.PUBLIKACJE_KART_KLUCZ]["k"]["wpis"] = {**karta, "xi": True}
    assert len(B.scal_karty_z_publikacjami([], wypadli={830659})) == 1


def test_po_transferze_okno_od_pierwszego_meczu_w_klubie():
    """Trossard: pięć ostatnich meczów Beşiktaşu zagranych, wcześniejsze
    występy w innym klubie (daty spoza kalendarza drużyny)."""
    kal = {100: [TERAZ - d * DZIEN for d in (3, 10, 17, 24, 31, 38, 45, 52, 59, 66)]}
    tr = _trend([3, 10, 17, 24, 31, 70, 77, 84])     # 70+ dni: stary klub
    assert radar.udzial_startow(tr, kalendarz=kal, teraz=TERAZ) == 1.0
    # ten sam obraz BEZ występów gdzie indziej = rezerwowy, który wszedł do składu
    tr2 = _trend([3, 10, 17, 24, 31])
    assert radar.udzial_startow(tr2, kalendarz=kal, teraz=TERAZ) == 0.5
    # nowy zawodnik z jednym meczem na trzy dalej nie jest starterem
    tr3 = _trend([3, 70, 77, 84])
    kal3 = {100: [TERAZ - d * DZIEN for d in (3, 10, 17, 24)]}
    assert radar.udzial_startow(tr3, kalendarz=kal3, teraz=TERAZ) < 0.6


# --- 7. porównanie Superbet/Betclic na czystych cennikach ---

def _karta_sb_bc(linie_pelne):
    return {
        "mecz_id": 5, "podmiot": "Luca Connell",
        "rynki": [{"rynek_kod": "shots", "linie_pelne": linie_pelne,
                   "drabinka": [{"linia": 0.5, "kurs": 1.72},
                                {"linia": 1.5, "kurs": 4.25}]}],
    }


def test_rozjazd_liczony_z_czystego_superbetu_widzi_wyzszy_betclic():
    """Scalona siatka ma już wyższy kurs z obu — porównanie jej z Betclikiem
    dawało 0,0 pp, gdy tylko Betclic płacił więcej (15 z 20 porównań 15.09)."""
    w = _karta_sb_bc({"0.5": 1.72, "1.5": 4.25, "2.5": 9.0})
    sb = {5: {"players": {"connell luca": {"shots": {
        0.5: {"over": 1.40}, 1.5: {"over": 3.60}, 2.5: {"over": 8.0}}}}}}
    bc = {5: {"players": {"connell luca": {"shots": {
        0.5: {"over": 1.72}, 1.5: {"over": 4.25}, 2.5: {"over": 9.0}}}}}}
    radar._dopnij_betclic([w], {5: {"home": "A", "away": "B", "ts": TERAZ}},
                          paczki_bc=bc, podsumuj_karty=False, sb_cache=sb)
    s0 = w["rynki"][0]["drabinka"][0]
    assert s0["kurs_superbet"] == 1.40 and s0["kurs_betclic"] == 1.72
    assert s0["rozjazd"]["gdzie"] == "betclic" and s0["rozjazd"]["roznica_pp"] > 10
    # bez Superbetu nie ma porównania — zamiast fałszywego „rynek zgodny"
    w2 = _karta_sb_bc({"0.5": 1.72, "1.5": 4.25})
    radar._dopnij_betclic([w2], {5: {"home": "A", "away": "B", "ts": TERAZ}},
                          paczki_bc=bc, podsumuj_karty=False, sb_cache={5: {"players": {}}})
    assert "rozjazd" not in w2["rynki"][0]["drabinka"][0]


# --- 8. różnica kursów w rankingu drabinek, z głową ---

def _szczebel_roz(sb, bc, p_uczony=None):
    s = {"rozjazd": {"superbet": sb, "betclic": bc, "lepszy": max(sb, bc),
                     "gdzie": "superbet" if sb >= bc else "betclic"}}
    if p_uczony is not None:
        s["p_uczony"] = {"p": p_uczony}
    return s


def test_wartosc_rozjazdu_w_obie_strony():
    # Superbet 1,40 (ok. 66% po marży), Betclic płaci 1,72 (58%)
    w_bc = radar.wartosc_rozjazdu(_szczebel_roz(1.40, 1.72))
    w_sb = radar.wartosc_rozjazdu(_szczebel_roz(1.72, 1.40))
    assert w_bc == w_sb and w_bc > 0.07
    assert radar.wartosc_rozjazdu(_szczebel_roz(1.70, 1.72)) == 0.0   # marża zjada
    assert radar.wartosc_rozjazdu({}) == 0.0


def test_model_uczony_przeczacy_zeruje_wartosc_rozjazdu():
    # lepsza cena 1,72 = 58%; model widzi 50% -> to tańszy buk się myli
    assert radar.wartosc_rozjazdu(_szczebel_roz(1.40, 1.72, p_uczony=0.50)) == 0.0
    assert radar.wartosc_rozjazdu(_szczebel_roz(1.40, 1.72, p_uczony=0.60)) > 0.07


# --- 9. zawodnicy bez ściągania λ do linii ---

def test_wysoki_szczebel_zawodnika_bez_sztucznego_podbicia():
    """λ 1,5 strzału, linia 2,5 („3+"): ściąganie 0,6 podnosiło szansę."""
    from footstats.model import uczony as U
    zaw = U.wycena(1.5, 2.5, "powyzej", 12.0, sila=U.SCIAGANIE_LAMBDY_ZAW)
    druz = U.wycena(1.5, 2.5, "powyzej", 12.0)
    assert U.SCIAGANIE_LAMBDY_ZAW == 1.0 and zaw["sciag"] == 1.0
    assert zaw["p"] < druz["p"]
