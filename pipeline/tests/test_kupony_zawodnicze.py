"""Kupony z zawodnikami: „zawodnicy" i „hybryda" (2026-10-05).

Właściciel: „czemu w kuponach nie ma w ogóle kuponów z zawodniczymi typami?
Hybryd i też tylko dla zawodniczych". Do 05.10 kwarantanna w puli kuponów
zdejmowała każde zawodnicze „powyżej", a wszystkie przedziały składały się
z jednej puli, w której drużyny wygrywają szansą.
"""
import inspect

from footstats.jobs import build_wc_fast as B
from footstats.model import kupony

TERAZ = 1_800_000_000
KO = TERAZ + 6 * 3600          # dziś, z zapasem na margines startu


def _leg(mid, pid, kurs, p, rynek_kod="shots", typ=None, linia=0.5, ko=KO):
    l = {"id": pid, "mecz_id": mid, "mecz": f"M{mid}", "kickoff_ts": ko,
         "podmiot_id": pid, "podmiot": f"P{pid}", "druzyna": f"D{mid}",
         "rynek_kod": rynek_kod, "rynek": rynek_kod, "linia": linia,
         "strona": "powyzej", "kurs": kurs, "bukmacher": "Superbet",
         "p_model": p, "pewnosc": "wysoka"}
    if typ:
        l["podmiot_typ"] = typ
    return l


def _pula():
    # jak w życiu: drużynowe pewniejsze przy tej samej cenie
    druzyny = [_leg(m, 100 + m, 1.45, 0.86, "team_corners", "druzyna") for m in range(1, 6)]
    zawodnicy = [_leg(m, 200 + m, 1.45, 0.70, "shots", "zawodnik") for m in range(1, 6)]
    return druzyny + zawodnicy


def test_rodzaj_lega_po_stemplu_i_po_kodzie():
    assert kupony.rodzaj_lega({"podmiot_typ": "druzyna", "rynek_kod": "shots"}) == "druzyna"
    assert kupony.rodzaj_lega({"rynek_kod": "wiecej_shots"}) == "druzyna"
    assert kupony.rodzaj_lega({"rynek_kod": "match_cards"}) == "druzyna"
    assert kupony.rodzaj_lega({"rynek_kod": "fouls_won"}) == "zawodnik"


def test_powstaja_kupony_zawodnicze_i_hybrydowe_we_wlasnych_slotach():
    out = kupony.build_kupony([], _pula(), now_ts=TERAZ)
    po_h = {}
    for k in out:
        po_h.setdefault(k["horyzont"], []).append(k)
    zaw = po_h["zawodnicy"][0]
    assert {kupony.rodzaj_lega(l) for l in zaw["legi"]} == {"zawodnik"}
    assert 2.0 <= zaw["kurs_laczny"] <= 3.5
    hyb = po_h["hybryda"][0]
    assert {kupony.rodzaj_lega(l) for l in hyb["legi"]} == {"zawodnik", "druzyna"}
    assert 3.0 <= hyb["kurs_laczny"] <= 5.0
    # slot w rozliczaniu = horyzont:przedział — nowe rodzaje nie zajmują
    # miejsca kuponów drużynowych o tym samym przedziale
    sloty = [f"{k['horyzont']}:{k['cel_label']}" for k in out]
    assert len(sloty) == len(set(sloty))


def test_bez_zawodnikow_nie_ma_kuponow_zawodniczych_i_hybryd():
    pula = [l for l in _pula() if l["podmiot_typ"] == "druzyna"]
    out = kupony.build_kupony([], pula, now_ts=TERAZ)
    assert not [k for k in out if k["horyzont"] in ("zawodnicy", "hybryda")]
    # kupony drużynowe dalej się składają
    assert [k for k in out if k["horyzont"] == "dzienny"]


def test_kupon_identyczny_z_juz_zlozonym_nie_wchodzi_drugi_raz():
    """Gdy „na dziś" samo złożyło się z zawodników, kupon zawodniczy
    o tych samych nogach byłby duplikatem — nie publikujemy go dwa razy."""
    zawodnicy = [l for l in _pula() if l["podmiot_typ"] == "zawodnik"]
    out = kupony.build_kupony([], zawodnicy, now_ts=TERAZ)
    sygn = [kupony._sygnatura(k) for k in out]
    assert len(sygn) == len(set(sygn))


def test_wymog_rodzaju_w_builderze():
    pula = _pula()
    k = kupony._zloz_pewniaki(pula, 3.0, 5.0, min_legi=2, teraz=TERAZ,
                              wymagane=frozenset({"zawodnik", "druzyna"}))
    assert {kupony.rodzaj_lega(l) for l in k["legi"]} == {"zawodnik", "druzyna"}


def test_domyslny_builder_bez_zmian():
    """Parytet z kuponBuilder.ts: bez `wymagane` wynik jak dotąd."""
    pula = _pula()
    a = kupony._zloz_pewniaki(pula, 3.0, 5.0, min_legi=2, teraz=TERAZ)
    b = kupony._zloz_pewniaki(pula, 3.0, 5.0, min_legi=2, teraz=TERAZ, wymagane=None)
    assert a == b


def test_hybryda_podpowiada_zamiennik_tego_samego_rodzaju():
    out = kupony.build_kupony([], _pula(), now_ts=TERAZ)
    hyb = next(k for k in out if k["horyzont"] == "hybryda")
    alt = hyb.get("alternatywa")
    if alt:
        slaba = hyb["legi"][hyb["najslabszy_idx"]]
        assert kupony.rodzaj_lega(alt) == kupony.rodzaj_lega(slaba)
    assert "wariant_b" not in hyb


def test_luka_trafnosci_zatrzymuje_tylko_wyraznie_zawyzone_segmenty():
    # liczby z kwarantanny 05.10
    assert kupony.zawyzona_deklaracja({"n": 50, "hit": 0.40, "sr_p": 0.634})        # team_sot pon.
    assert kupony.zawyzona_deklaracja({"n": 91, "hit": 0.407, "sr_p": 0.558})       # zaniżony kurs
    assert not kupony.zawyzona_deklaracja({"n": 150, "hit": 0.453, "sr_p": 0.547})  # strzały zaw.
    assert not kupony.zawyzona_deklaracja({"n": 150, "hit": 0.553, "sr_p": 0.558})  # faule pop.
    assert not kupony.zawyzona_deklaracja({"n": 50, "hit": 0.60, "sr_p": 0.578})    # faule wyw.
    # dokładnie −10 pp to już za dużo; mała próba nie decyduje
    assert kupony.zawyzona_deklaracja({"n": 30, "hit": 0.50, "sr_p": 0.60})
    assert not kupony.zawyzona_deklaracja({"n": 18, "hit": 0.333, "sr_p": 0.618})
    assert not kupony.zawyzona_deklaracja(None)
    assert not kupony.zawyzona_deklaracja({"n": 50})


def test_kwarantanna_w_puli_kuponow_to_etykieta_poza_luka_trafnosci():
    """Strukturalnie: `_leg_dopuszczalny` odrzuca nogę z kwarantanny WYŁĄCZNIE
    przez `zawyzona_deklaracja`, w pozostałych przypadkach stempluje etykietę."""
    zrodlo = inspect.getsource(B)
    start = zrodlo.index("def _leg_dopuszczalny(")
    cialo = zrodlo[start:zrodlo.index("legi_pool_pub = [", start)]
    assert 'b["slabsza_seria"]' in cialo
    kw = cialo[cialo.index("_kw = _powod_kwarantanny"):cialo.index('if b.get("stare_dane")')]
    assert kw.count("return False") == 1
    assert "kupony.zawyzona_deklaracja(_stat)" in kw
