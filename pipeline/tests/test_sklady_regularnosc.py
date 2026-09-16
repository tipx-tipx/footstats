"""Regularność startów liczona względem MECZÓW DRUŻYNY i sygnał składu na liście dnia.

Zgłoszenie właściciela 2026-09-14: w drabinkach stanęła karta na zawodnika
Como, „który nigdy nie wychodzi w podstawowym składzie" (faule wywalczone).
Powód: feed zawodnika ma tylko mecze, w których ZAGRAŁ — trzy pełne występy
w sezonie wyglądały jak 3/3 startów. Naprawa liczy starty względem
kalendarza drużyny z magazynu (mecz bez występu = bez startu), a lista dnia
układa zawodników sygnałem składu i dokłada po domknięciu tych z ogłoszonym XI.
"""
import datetime as dt

from footstats import engine
from footstats.jobs import build_wc_fast as B
from footstats.jobs import radar, rozliczanie
from footstats.model import counts
from footstats.sources.statshub import StatshubTrend

TERAZ = 1_800_000_000
DZIEN = 86_400
KLUB = 100


def _trend(grane_dni, minuty=90, team_id=KLUB):
    """Zawodnik z występami `grane_dni` dni temu (tylko mecze, w których grał)."""
    n = len(grane_dni)
    return StatshubTrend(
        player_id=1, player_name="Rezerwowy", position="M", team_id=team_id,
        team_name="Como", opponent_id=200, opponent_name="Parma", is_home=True,
        market_code="fouls_won", line=1.5, in_predicted_lineup=False,
        league_average=None, opponent_average=None, opponent_rank=None,
        total_ranks=None, event_id=999,
        counts=[2.0] * n, minutes=[float(minuty)] * n,
        timestamps=[TERAZ - d * DZIEN for d in grane_dni],
        started=[minuty >= 60] * n,
    )


# drużyna grała co tydzień: 10 meczów, 1..64 dni temu (+ jeden za tydzień)
KALENDARZ = {KLUB: [TERAZ + 7 * DZIEN] + [TERAZ - (1 + 7 * i) * DZIEN for i in range(10)]}


def test_rezerwowy_z_trzema_pelnymi_meczami_nie_jest_starterem():
    tr = _trend([1, 22, 43])                       # 3 z 10 meczów drużyny
    assert radar.udzial_startow(tr) is None       # stara miara: za mało (<5)
    tr5 = _trend([1, 15, 22, 43, 57])
    assert radar.udzial_startow(tr5) == 1.0       # stara miara: „zawsze w XI"
    assert radar.udzial_startow(tr5, kalendarz=KALENDARZ, teraz=TERAZ) == 0.5
    assert radar.udzial_startow(tr, kalendarz=KALENDARZ, teraz=TERAZ) == 0.3


def test_dopelnienie_wstawia_zero_minut_za_opuszczone_mecze():
    st, mi, ts = radar.dopelnij_meczami_druzyny(_trend([1, 22]), KALENDARZ, TERAZ)
    assert len(ts) == 10 and ts[0] == TERAZ - DZIEN       # przyszły mecz pominięty
    assert st[0] and mi[0] == 90.0 and not st[1] and mi[1] == 0.0
    assert sum(st) == 2
    # przesunięcie znacznika o 2 h (inne źródło) dalej paruje ten sam mecz
    tr = _trend([1])
    tr.timestamps = [TERAZ - DZIEN + 2 * 3600]
    assert radar.dopelnij_meczami_druzyny(tr, KALENDARZ, TERAZ)[0][0]


def test_bez_kalendarza_zostaje_stara_miara_nie_zero():
    tr = _trend([1, 8, 15, 22, 29])
    assert radar.dopelnij_meczami_druzyny(tr, {}, TERAZ) is None
    assert radar.dopelnij_meczami_druzyny(tr, {7: [TERAZ - DZIEN]}, TERAZ) is None
    assert radar.udzial_startow(tr, kalendarz={}, teraz=TERAZ) == 1.0


def test_gral_w_ostatnim_meczu_druzyny():
    assert radar.gral_w_ostatnim_meczu(_trend([1, 22]), KALENDARZ, TERAZ) is True
    assert radar.gral_w_ostatnim_meczu(_trend([8, 22]), KALENDARZ, TERAZ) is False
    # bez kalendarza: ostatni mecz drużyny znany z feedu
    assert radar.gral_w_ostatnim_meczu(_trend([8]), {}, TERAZ) is None
    assert radar.gral_w_ostatnim_meczu(
        _trend([8]), {}, TERAZ, ostatni_ts=TERAZ - 8 * DZIEN) is True
    assert radar.gral_w_ostatnim_meczu(
        _trend([8]), {}, TERAZ, ostatni_ts=TERAZ - DZIEN) is False


def test_model_minut_dostaje_historie_druzyny():
    """Ten sam zawodnik: z dopełnioną historią spodziewamy się dużo mniej minut."""
    tr = _trend([1, 22, 43])
    prior = counts.GroupPrior(mean_per90=1.5, pseudo_matches=4.0)
    ctx = engine.MatchContext(is_home=True, is_favourite=False)

    def _hist(dop):
        h = engine.PlayerHistory(
            counts=tr.counts, minutes=tr.minutes,
            days_ago=[(TERAZ - t) / DZIEN for t in tr.timestamps],
            started=tr.started)
        if dop:
            st, mi, ts = radar.dopelnij_meczami_druzyny(tr, KALENDARZ, TERAZ)
            h.historia_druzyny = (st, mi, [(TERAZ - t) / DZIEN for t in ts])
        return h

    bez = engine.score_player_market("fouls_won", 1.5, _hist(False), prior, ctx)
    z = engine.score_player_market("fouls_won", 1.5, _hist(True), prior, ctx)
    assert bez.expected_minutes > 75
    assert z.expected_minutes < 0.5 * bez.expected_minutes


# ------------------------------------------------------------ lista dnia --

def _ts(dzien, godz):
    return int(dt.datetime.strptime(dzien, "%Y-%m-%d").replace(
        hour=godz, tzinfo=rozliczanie.STREFA).timestamp())


def _zaw(i, p=0.7, **kw):
    r = {"mecz_id": i, "podmiot_id": 1000 + i, "podmiot": f"Gracz {i}",
         "rynek_kod": "fouls_won", "strona": "powyzej", "linia": 1.5,
         "p_model": p, "kurs": 1.6, "podmiot_typ": "zawodnik",
         "kickoff_ts": _ts("2026-09-14", 20)}
    r.update(kw)
    return r


def _klucz(b):
    return (float(b.get("p_model") or 0.0), True)


def test_priorytet_skladu_szczeble():
    assert B.priorytet_skladu(_zaw(1, xi_sygnal="official")) == 3
    assert B.priorytet_skladu(_zaw(1, xi_sygnal="predicted")) == 2
    assert B.priorytet_skladu(_zaw(1, gral_w_ostatnim=True)) == 1
    assert B.priorytet_skladu(_zaw(1, gral_w_ostatnim=None)) == 0
    assert B.priorytet_skladu({"podmiot_typ": "druzyna"}) == 3


def test_sklad_przed_sila_przy_wejsciu_na_liste():
    """Silniejszy typ bez sygnału ustępuje słabszemu z ogłoszonym XI, gdy
    miejsc jest mniej niż kandydatów (limit na mecz = 3, wszyscy z meczu 1)."""
    kand = [
        _zaw(1, p=0.95, podmiot="A", gral_w_ostatnim=True),
        _zaw(1, p=0.90, podmiot="B", gral_w_ostatnim=True),
        _zaw(1, p=0.85, podmiot="C", gral_w_ostatnim=True),
        _zaw(1, p=0.60, podmiot="D", xi_sygnal="official"),
        _zaw(1, p=0.65, podmiot="E", xi_sygnal="predicted"),
    ]
    lista, zdjete, _ = B.wybierz_liste_publikowana(kand, _klucz)
    assert [b["podmiot"] for b in lista] == ["D", "E", "A"]
    assert zdjete[B._klucz_publikacji(kand[2])] == "poza_lista_dnia"


def test_zawodnik_bez_zadnego_sygnalu_nie_wchodzi_ale_nieznany_tak():
    bez = _zaw(1, podmiot="X", gral_w_ostatnim=False)
    nieznany = _zaw(2, podmiot="Y", gral_w_ostatnim=None)
    pokazany = _zaw(3, podmiot="Z", gral_w_ostatnim=False, pokazany_wczesniej=True)
    lista, zdjete, _ = B.wybierz_liste_publikowana([bez, nieznany, pokazany], _klucz)
    assert sorted(b["podmiot"] for b in lista) == ["Y", "Z"]
    assert zdjete[B._klucz_publikacji(bez)] == "bez_sygnalu_skladu"


def test_dzien_domkniety_doklada_zawodnika_z_ogloszonym_xi():
    stary = _zaw(1, podmiot="Stary", gral_w_ostatnim=True)
    xi = _zaw(2, podmiot="Nowy XI", xi_sygnal="official")
    przewid = _zaw(3, podmiot="Tylko przewidywany", xi_sygnal="predicted")
    druzyna = {**_zaw(4, podmiot="Klub"), "podmiot_typ": "druzyna", "kurs": 1.3}
    zamkniete = {"2026-09-14": {B._klucz_publikacji(stary)}}
    dolozone: dict = {}
    lista, zdjete, z_dnia = B.wybierz_liste_publikowana(
        [stary, xi, przewid, druzyna], _klucz, zamkniete=zamkniete,
        dolozone=dolozone)
    assert [b["podmiot"] for b in lista] == ["Nowy XI", "Stary"] or \
        [b["podmiot"] for b in lista] == ["Stary", "Nowy XI"]
    assert dolozone == {"2026-09-14": [B._klucz_publikacji(xi)]}
    assert xi.get("dolozony_po_domknieciu") is True
    assert zdjete[B._klucz_publikacji(przewid)] == "dzien_zamkniety"
    assert zdjete[B._klucz_publikacji(druzyna)] == "dzien_zamkniety"
    assert z_dnia["2026-09-14"] == 2
    # bez słownika wyjściowego (stare wywołania) dzień jest zamrożony jak dotąd
    lista2, zdjete2, _ = B.wybierz_liste_publikowana(
        [stary, _zaw(2, podmiot="Nowy XI", xi_sygnal="official")], _klucz,
        zamkniete=zamkniete)
    assert len(lista2) == 1 and len(zdjete2) == 1


def test_dokladanie_po_domknieciu_szanuje_limity_doby():
    """Ogłoszona doba ma komplet 21 zawodniczych — nowy z XI już nie wejdzie;
    limit na mecz (3) też obowiązuje."""
    komplet = [_zaw(i, podmiot=f"P{i}") for i in range(1, B.LISTA_CAP + 1)]
    zamkniete = {"2026-09-14": {B._klucz_publikacji(b) for b in komplet}}
    nowy = _zaw(50, podmiot="Nowy", xi_sygnal="official")
    dolozone: dict = {}
    lista, zdjete, _ = B.wybierz_liste_publikowana(
        komplet + [nowy], _klucz, zamkniete=zamkniete, dolozone=dolozone)
    assert len(lista) == B.LISTA_CAP and not dolozone
    assert zdjete[B._klucz_publikacji(nowy)] == "dzien_zamkniety"
    # 3 z meczu 1 już na liście → czwarty z meczu 1 nie wchodzi
    trzy = [_zaw(1, podmiot=f"M{i}") for i in range(3)]
    zamk2 = {"2026-09-14": {B._klucz_publikacji(b) for b in trzy}}
    czwarty = _zaw(1, podmiot="Czwarty", xi_sygnal="official")
    dolozone = {}
    lista, _, _ = B.wybierz_liste_publikowana(
        trzy + [czwarty], _klucz, zamkniete=zamk2, dolozone=dolozone)
    assert len(lista) == 3 and not dolozone


def test_dopisz_dolozone_tylko_do_domknietych_dob():
    manifest = {"2026-09-14": {"zamkniete_ts": 1, "klucze": ["a"]},
                "2026-09-15": {"klucze": ["z"]}}
    n = B.dopisz_dolozone(manifest, {"2026-09-14": ["b", "a"],
                                     "2026-09-15": ["y"], "2026-09-16": ["q"]})
    assert n == 1
    assert manifest["2026-09-14"]["klucze"] == ["a", "b"]
    assert manifest["2026-09-15"] == {"klucze": ["z"]}
    assert "2026-09-16" not in manifest


def _trend_rynku(mk, grane_dni, minuty=90):
    tr = _trend(grane_dni, minuty=minuty)
    tr.market_code = mk
    return tr


def test_udzial_startow_z_unii_rynkow_nie_z_jednego_feedu():
    """Dier 16.09: „celne" z feedu znały 2 mecze sezonu, „strzały" 6 —
    brama liczona na jednym rynku wyrzucała startera, który grał wszystko."""
    celne = _trend_rynku("sot", [1, 8])                       # feed UK: 2 kwotowane
    strzaly = _trend_rynku("shots", [1, 8, 15, 22, 29, 36])   # performance: komplet
    assert radar.udzial_startow(celne, kalendarz=KALENDARZ, teraz=TERAZ) == 0.2
    unia = radar.polacz_wystepy([celne, strzaly])
    assert radar.udzial_startow(unia, kalendarz=KALENDARZ, teraz=TERAZ) == 0.6
    # ten sam mecz w dwóch rynkach liczy się RAZ, a nie dwa razy
    assert len(unia.timestamps) == 6
    assert unia.market_code == "shots"            # baza = najdłuższa historia
    assert radar.nie_gral_ostatnio(unia, KALENDARZ, TERAZ) is False


def test_unia_wystepow_sklejona_po_zawodniku():
    a = _trend_rynku("sot", [1, 8]); b = _trend_rynku("shots", [1, 15])
    b.player_id = 2
    slownik = radar.wystepy_zawodnikow([a, b])
    assert set(slownik) == {1, 2}
    assert len(slownik[1].timestamps) == 2 and len(slownik[2].timestamps) == 2
    assert radar.polacz_wystepy([]) is None
