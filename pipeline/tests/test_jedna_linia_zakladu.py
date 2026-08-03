"""Najwyżej DWIE poprzeczki na zakład (2026-08-02, decyzja usera).

Brama z 01.08 wybiera najlepszą poprzeczkę wg oceny modelu, ale widzi tylko
bieżące przeliczenie — poprzeczki dokładały się więc między cyklami i jeden
zakład potrafił urosnąć do czterech wierszy.

GRANICA WZIĘTA Z POMIARU, nie z gustu. Poprzeczki wg kolejności wystawienia:

    1. bazowa              449 typów   57% trafień   -0,219 j./typ
    2. pierwsza dołożona   135 typów   64% trafień   -0,147 j./typ  <-- najlepsza
    3. i dalsze             37 typów   49% trafień   -0,298 j./typ  <-- najgorsza

Druga bije bazową, dopiero trzecia się załamuje. Limit ucina ogon: 42 wiersze
z 809. Obie zostają na liście i obie liczą się w Skuteczności — to dwa różne
zakłady (łatwiejszy tańszy, ambitniejszy droższy), a zwijanie do jednego
wiersza robi UI, nie publikacja.
"""

from footstats.jobs.build_wc_fast import linie_opublikowane


def _rec(**kw):
    r = {
        "mecz_id": 1, "podmiot": "Boca Juniors", "rynek_kod": "team_goals",
        "linia": 0.5, "strona": "ponizej",
    }
    r.update(kw)
    return r


def test_zbiera_wystawione_poprzeczki_per_zaklad():
    log = {
        "a": _rec(linia=0.5),
        "b": _rec(linia=1.5),                       # ten sam zakład, inna linia
        "c": _rec(linia=2.5, strona="powyzej"),     # DRUGA STRONA = inny zakład
        "d": _rec(mecz_id=2),                       # inny mecz = inny zakład
    }
    m = linie_opublikowane(log)
    assert m[(1, "boca juniors", "team_goals", "ponizej")] == {0.5, 1.5}
    assert m[(1, "boca juniors", "team_goals", "powyzej")] == {2.5}
    assert m[(2, "boca juniors", "team_goals", "ponizej")] == {0.5}


def test_poprzeczka_nie_jest_czescia_tozsamosci_zakladu():
    """„poniżej 4,5" i „poniżej 5,5" to jeden pomysł wyceniony dwa razy —
    muszą wpaść pod TEN SAM klucz, inaczej brama nic nie zablokuje."""
    m = linie_opublikowane({"a": _rec(linia=4.5), "b": _rec(linia=5.5)})
    assert len(m) == 1 and next(iter(m.values())) == {4.5, 5.5}


def test_typy_ktorych_user_nie_widzial_nie_blokuja():
    """Odrzucony przy progu, spoza publikacji i sugestia bez kursu nie były
    na stronie — nie ma z czym kolidować (ta sama zasada co przy kierunkach).
    Inaczej typ policzony „na próbę" zabierałby miejsce prawdziwemu."""
    log = {
        "a": _rec(linia=1.5, odrzucony=True),
        "b": _rec(linia=2.5, poza_publikacja="kwarantanna_rynku"),
        "c": _rec(linia=3.5, sugestia=True),
    }
    assert linie_opublikowane(log) == {}


def test_nazwa_podmiotu_znormalizowana():
    """Klucz idzie po znormalizowanej nazwie — w księdze bywa „Boca Juniors"
    i „boca juniors" (patrz `rozliczanie._klucz`), a to jeden zakład."""
    m = linie_opublikowane({
        "a": _rec(podmiot="Boca Juniors", linia=0.5),
        "b": _rec(podmiot="boca juniors", linia=1.5),
    })
    assert len(m) == 1


def test_pusta_ksiega_nie_blokuje_niczego():
    """Nieudany odczyt księgi ma zostawić publikację nietkniętą, a nie
    zablokować cały cykl — pusty słownik wyłącza bramę."""
    assert linie_opublikowane({}) == {}
    assert linie_opublikowane(None) == {}


# --- SAMA BRAMA: ile poprzeczek przepuszcza ---------------------------------
#
# Odwzorowuje warunek z `build_wc_fast` (limit 2), żeby granica była przypięta
# testem, a nie tylko komentarzem. Najważniejszy jest przypadek DRUGIEJ
# poprzeczki: ona ma PRZECHODZIĆ — wypada najlepiej z całej trójki, więc
# zaostrzenie limitu do jednej byłoby cofnięciem się, nie porządkiem.

MAX_POPRZECZEK_ZAKLADU = 2


def _przepuszcza(juz: set, linia: float) -> bool:
    nowa = linia not in juz
    return not (nowa and len(juz) >= MAX_POPRZECZEK_ZAKLADU)


def test_pierwsza_i_druga_poprzeczka_przechodza():
    assert _przepuszcza(set(), 0.5)          # zakład bez historii
    assert _przepuszcza({0.5}, 1.5)          # DRUGA — najlepiej rozliczana


def test_trzecia_poprzeczka_odpada():
    assert not _przepuszcza({0.5, 1.5}, 2.5)
    assert not _przepuszcza({0.5, 1.5, 2.5}, 3.5)


def test_juz_wystawiona_poprzeczka_nie_blokuje_sama_siebie():
    """Typ wraca w kolejnym cyklu z tą samą poprzeczką — musi przejść, inaczej
    zniknąłby userowi ze strony mimo że nadal jest aktualny."""
    assert _przepuszcza({0.5, 1.5}, 0.5)
    assert _przepuszcza({0.5, 1.5}, 1.5)


# --- FORMA DRUŻYN: dosypka zamiast budowania od zera (2026-08-02) ----------
#
# Forma była liczona wyłącznie z drużyn, dla których w danym cyklu przyszły
# świeże trendy. Drużyna bez trendu traciła 20 meczów historii, choć nic się
# z nią nie stało — a wtedy karta typu WZNOWIONEGO nie miała czym wypełnić
# kroków „skąd ta liczba" i „jak było ostatnio". Zmierzone: 11 z 16 typów
# na stronie bez formy.

def test_forma_dosypuje_brakujace_a_swieze_wygrywa(monkeypatch):
    from footstats.jobs import build_wc_fast as bwf
    monkeypatch.setattr(bwf, "_dry_run", lambda: False)
    monkeypatch.setattr(bwf.supa, "get_key", lambda k: [
        {"id": 1, "forma": {"team_goals": "stare"}},   # ma świeższą wersję niżej
        {"id": 2, "forma": {"team_goals": "x"}},       # tylko tu — do dosypania
        {"id": 9, "forma": {"team_goals": "x"}},       # nikt go dziś nie ogląda
    ])
    swieza = {1: {"id": 1, "forma": {"team_goals": "świeże"}}}
    bets = [{"podmiot_id": 1}, {"podmiot_id": 2}]
    out = {r["id"]: r for r in bwf.scal_forme_druzyn(swieza, bets)}
    assert out[1]["forma"]["team_goals"] == "świeże"   # świeże dane wygrywają
    assert 2 in out                                    # brakujące dosypane
    assert 9 not in out                                # bez typu na liście nie wchodzi


def test_forma_dosypuje_BRAKUJACY_RYNEK_istniejacej_druzyny(monkeypatch):
    """SEDNO poprawki z 03.08. Trendy przychodzą per rynek i rzadko komplet
    naraz, więc drużyna obecna w świeżym cyklu traciła rynki, których ten cykl
    nie policzył. Na karcie wyglądało to tak: Djurgårdens IF miał typ na rożne,
    a formę wyłącznie na gole — czyli krok „jak było ostatnio" był pusty mimo
    tego, że historia istniała."""
    from footstats.jobs import build_wc_fast as bwf
    monkeypatch.setattr(bwf, "_dry_run", lambda: False)
    monkeypatch.setattr(bwf.supa, "get_key", lambda k: [
        {"id": 1, "forma": {"team_goals": "stare", "team_corners": "ROŻNE"}},
    ])
    swieza = {1: {"id": 1, "forma": {"team_goals": "świeże"}}}
    out = {r["id"]: r for r in bwf.scal_forme_druzyn(swieza, [{"podmiot_id": 1}])}
    assert out[1]["forma"]["team_goals"] == "świeże"    # świeży rynek wygrywa
    assert out[1]["forma"]["team_corners"] == "ROŻNE"   # brakujący wraca


def test_forma_zostaje_druzynie_z_UJEMNYM_numerem(monkeypatch):
    """Ta lista decyduje, czyja forma ZOSTAJE w banku. Typ wznowiony z księgi
    przychodził z ujemnym numerem (patrz `rozliczanie._znak_podmiotu`), a
    snapshot trzyma drużynę pod dodatnim — więc bank wyrzucał formę dokładnie
    tych drużyn, które jej potrzebują najbardziej. Zmierzone 03.08: Sønderjyske
    i IFK Värnamo zniknęły z banku, mając typ na liście."""
    from footstats.jobs import build_wc_fast as bwf
    monkeypatch.setattr(bwf, "_dry_run", lambda: False)
    monkeypatch.setattr(bwf.supa, "get_key", lambda k: [
        {"id": 1295, "forma": {"team_goals": "20 meczów"}},
    ])
    out = {r["id"]: r for r in
           bwf.scal_forme_druzyn({}, [{"podmiot_id": -1295}])}
    assert out[1295]["forma"]["team_goals"] == "20 meczów"


def test_forma_przezywa_padniety_odczyt(monkeypatch):
    """Nieudany odczyt ma zostawić świeże dane, a nie wywalić cyklu."""
    from footstats.jobs import build_wc_fast as bwf
    monkeypatch.setattr(bwf, "_dry_run", lambda: False)

    def _padnij(_k):
        raise RuntimeError("supabase pada")

    monkeypatch.setattr(bwf.supa, "get_key", _padnij)
    out = bwf.scal_forme_druzyn({7: {"id": 7}}, [{"podmiot_id": 7}])
    assert [r["id"] for r in out] == [7]


# --- UZASADNIENIE DLA RYNKÓW Z OBU DRUŻYN (2026-08-03) ---------------------
#
# Suma meczowa i „kto więcej" były budowane z pustym `czynniki: []`, więc karta
# nie miała czym wypełnić kroku „skąd ta liczba" — a `skadTaLiczba` po stronie
# web zwraca null, gdy nie znajdzie „Poziomu bazowego". Pierwszy typ na liście
# (suma rożnych) otwierał się i nie tłumaczył NICZEGO.

class _Pred:
    def __init__(self, lam):
        self.lam = lam


def _pary():
    return (
        {"nazwa": "Aalesunds FK", "pred": _Pred(6.1)},
        {"nazwa": "Tromsø IL", "pred": _Pred(4.4)},
    )


def test_poziom_bazowy_jest_zawsze():
    """Bez „Poziomu bazowego" cały krok znika ze strony — to nie jest ozdoba,
    tylko warunek, żeby rozwinięcie w ogóle się pokazało."""
    from footstats.jobs.build_wc_fast import czynniki_pary
    h, a = _pary()
    cz = czynniki_pary(h, a, "Rzuty rożne", 0.0)
    assert cz[0]["nazwa"] == "Poziom bazowy"
    # obie liczby i ich suma muszą paść w zdaniu — to jest cały rachunek
    assert "6.1" in cz[0]["opis"] and "4.4" in cz[0]["opis"]
    assert "10.5" in cz[0]["opis"]


def test_korelacja_wchodzi_tylko_gdy_zmierzona():
    """Rynek bez pomiaru dostaje rho=0. Zdanie „bez wpływu" byłoby wtedy
    komunikatem o naszej kuchni, nie o meczu — więc milczymy."""
    from footstats.jobs.build_wc_fast import czynniki_pary
    h, a = _pary()
    assert len(czynniki_pary(h, a, "Rzuty rożne", 0.0)) == 1
    z_rho = czynniki_pary(h, a, "Rzuty rożne", -0.13)
    assert len(z_rho) == 2
    assert "mniej" in z_rho[1]["opis"]        # ujemna = jedna więcej, druga mniej
    assert "też" in czynniki_pary(h, a, "Kartki", 0.2)[1]["opis"]
