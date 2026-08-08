"""Dwa cenniki, jeden typ — Superbet i Betclic jako równorzędne źródła ofert.

Decyzja usera 2026-08-08: „bierzemy pod uwagę i Betclic, i Superbet, tylko musi
być jasno napisane, jaki bukmacher" oraz „stawiać będziemy tam, gdzie wyższy
[kurs]". Powód jest w podaży: zmierzone tego dnia na żywej siatce Superbetu —
„zza pola" ma 2 zawodników, odbiory 73, przy 1756 na zwykłych strzałach.
Wzorcowe typy, które user wkleił (Igbekeme, Hellebrand, Lokilo, Yamal — „zza
pola"; Paredes, Anderson — odbiory), stoją właśnie na tych rynkach i wszystkie
u Betclica.
"""
from footstats.jobs import build_wc_fast as B
from footstats.model import betting


def test_scalanie_sumuje_rynki_obu_bukmacherow():
    """Rynek kwotowany tylko przez jednego z nich ma zostać w ofercie —
    inaczej odbiory i „zza pola" przepadają, bo Superbet ich nie wystawia."""
    sb = {"shots": {1.5: {"over": 1.80}}}
    bc = {"tackles": {1.5: {"over": 2.10}},
          "shots_outside_box": {0.5: {"over": 1.95}}}
    out = B._scal_oferty_zawodnika(sb, bc)
    assert set(out) == {"shots", "tackles", "shots_outside_box"}


def test_przy_wspolnej_linii_zostaje_wyzszy_kurs():
    """Ten sam zakład za więcej pieniędzy — decyzja usera."""
    sb = {"sot": {1.5: {"over": 1.72}}}
    bc = {"sot": {1.5: {"over": 2.05}}}
    assert B._scal_oferty_zawodnika(sb, bc)["sot"][1.5]["over"] == 2.05
    # i w drugą stronę — kolejność argumentów nie może decydować
    assert B._scal_oferty_zawodnika(bc, sb)["sot"][1.5]["over"] == 2.05


def test_scalanie_nie_psuje_zrodla():
    """Wejście ma zostać nietknięte — cache Superbetu jest współdzielony
    przez cały cykl (scoring, drabinki, tabela pokryć)."""
    sb = {"sot": {1.5: {"over": 1.72}}}
    B._scal_oferty_zawodnika(sb, {"sot": {1.5: {"over": 2.05}}})
    assert sb["sot"][1.5]["over"] == 1.72


def test_brak_drugiego_cennika_niczego_nie_zmienia():
    sb = {"shots": {1.5: {"over": 1.80}}}
    assert B._scal_oferty_zawodnika(sb, {}) == sb
    assert B._scal_oferty_zawodnika({}, sb) == sb


def test_kurs_nieliczbowy_nie_wywala_scalania():
    """Oferta bywa niepełna (None, pusty string) — to nie może zatrzymać cyklu."""
    sb = {"shots": {1.5: {"over": 1.80}}}
    bc = {"shots": {1.5: {"over": None}, 2.5: {"over": "—"}}}
    out = B._scal_oferty_zawodnika(sb, bc)
    assert out["shots"][1.5]["over"] == 1.80


def test_linia_jest_liczba_po_obu_stronach():
    """⚑ Wynik idzie prosto do `sorted()` w scoringu, a klucze dwóch typów
    naraz przewracają tam CAŁY przebieg (regresja 08.08 — patrz
    `test_linie_wracaja_z_pamieci_jako_liczby`). Druga brama, bo oferta
    Betclica dociera dwiema drogami: świeżo z sieci (float) i z pamięci
    Supabase, gdzie JSON zrobił z linii tekst."""
    sb = {"shots": {1.5: {"over": 1.80}}}
    bc = {"shots": {"0.5": {"over": 1.30}}, "tackles": {"1.5": {"over": 2.10}}}
    out = B._scal_oferty_zawodnika(sb, bc)
    assert sorted(out["shots"]) == [0.5, 1.5]
    assert list(out["tackles"]) == [1.5]


def test_sam_betclic_tez_wnosi_linie_liczbowe():
    """Zawodnik kwotowany WYŁĄCZNIE przez Betclica idzie krótszą gałęzią —
    i to właśnie ci zawodnicy są celem drugiego cennika (odbiory, „zza pola")."""
    bc = {"tackles": {"0.5": {"over": 1.09}, "1.5": {"over": 1.55}}}
    out = B._scal_oferty_zawodnika({}, bc)
    assert sorted(out["tackles"]) == [0.5, 1.5]


def test_obaj_bukmacherzy_maja_zapisany_tryb_podatku():
    """Bukmacher jedzie z kursem aż do księgi, bo od niego zależy rachunek
    netto — a ten musi być zamrożony przy typie, nie liczony po fakcie."""
    assert betting.tryb_podatku("Betclic") in betting.WSPOLCZYNNIK_PODATKU
    assert betting.tryb_podatku("Superbet") in betting.WSPOLCZYNNIK_PODATKU


# ---------------------------------------------------------------------------
# Kto daje tę cenę (2026-08-08, zgłoszenie usera)
# ---------------------------------------------------------------------------

def test_zrodlo_wskazuje_betclica_tylko_gdy_placi_wiecej():
    """Karta drabinki pisze w nagłówku „Kurs X u Superbetu". Siatka bierze
    WYŻSZĄ z dwóch cen, więc bez mapy źródeł karta podpisywała cenę Betclica
    cudzym nazwiskiem — i wysyłała usera do bukmachera, który jej nie ma."""
    sb = {"shots": {0.5: {"over": 1.80}, 1.5: {"over": 3.00}}}
    bc = {"shots": {"0.5": {"over": 1.70}, "1.5": {"over": 3.40}}}
    z = B.zrodla_kursow(sb, bc)
    # 0,5 zostaje u Superbetu (1,80 > 1,70) — nie zapisujemy nic
    assert "0.5" not in (z.get("shots") or {})
    # 1,5 przechodzi do Betclica (3,40 > 3,00)
    assert z["shots"]["1.5"] == "Betclic"


def test_rynek_ktorego_superbet_nie_kwotuje_jest_betclica():
    """Odbiory i „zza pola" Superbet kwotuje śladowo — cała drabinka jest
    wtedy z drugiego cennika i karta musi to napisać."""
    z = B.zrodla_kursow({}, {"tackles": {"0.5": {"over": 1.58}}})
    assert z["tackles"]["0.5"] == "Betclic"


def test_brak_drugiego_cennika_nie_daje_zadnych_zrodel():
    """Superbet jest domyślny — zapisujemy WYŁĄCZNIE wyjątki, żeby mapa nie
    puchła do rozmiaru całej siatki."""
    assert B.zrodla_kursow({"shots": {0.5: {"over": 1.8}}}, {}) == {}
