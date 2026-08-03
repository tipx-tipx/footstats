"""Jeden klub – jeden numer (2026-08-03).

POWÓD. `build_wc_fast._odrzuc_druzyne` odróżnia drużynę od zawodnika MINUSEM
w swoim kluczu diagnostycznym, a rekord pomiarowy szedł z tym minusem do
księgi. Gdy taki typ w kolejnym cyklu przechodził progi, aktualizacja zdejmowała
`odrzucony`, ale numer zostawał ujemny — więc ten sam klub żył w księdze pod
dwoma numerami (AGF jako 1291 i −1291). Zmierzone na żywej bazie: 162 z 465
opublikowanych typów drużynowych (35%).

Kosztowało to dwie widoczne rzeczy:
  * strona szuka formy drużyny PO NUMERZE, więc typ wznowiony z księgi nie miał
    jak pokazać kroku „jak było ostatnio" — 0 z 18 typów na stronie 03.08,
  * kupon pilnuje „jeden leg na podmiot" też po numerze, więc ta sama drużyna
    mogła wejść do kuponu dwa razy.
"""

from footstats.jobs import build_wc_fast, rozliczanie


def test_minus_schodzi_tylko_rynkom_druzynowym():
    Z = rozliczanie._znak_podmiotu
    assert Z({"podmiot_id": -1291, "rynek_kod": "team_goals"}) == 1291
    assert Z({"podmiot_id": -3163, "rynek_kod": "wiecej_shots"}) == 3163
    assert Z({"podmiot_id": -2032, "rynek_kod": "match_corners"}) == 2032
    # zawodnicy ujemnych numerów nie mają i nie wolno ich „prostować"
    assert Z({"podmiot_id": -55, "rynek_kod": "shots"}) is None
    # dodatni numer i brak numeru zostają nietknięte
    assert Z({"podmiot_id": 1291, "rynek_kod": "team_goals"}) is None
    assert Z({"podmiot_id": None, "rynek_kod": "team_goals"}) is None


def test_ksiega_prostuje_sie_sama_i_idempotentnie():
    log = {
        "a": {"podmiot_id": -1291, "rynek_kod": "team_goals", "wynik": None},
        # rozliczony też — numer nie jest wynikiem rozliczenia, a bez tego
        # 162 zamrożone rekordy zostałyby kalekie na zawsze
        "b": {"podmiot_id": -3218, "rynek_kod": "team_sot", "wynik": "wygrany"},
        "c": {"podmiot_id": 2244, "rynek_kod": "team_goals", "wynik": None},
        "d": {"podmiot_id": 77, "rynek_kod": "shots", "wynik": None},
    }
    assert rozliczanie._uzupelnij_znak_id(log) == 2
    assert log["a"]["podmiot_id"] == 1291
    assert log["b"]["podmiot_id"] == 3218
    assert log["c"]["podmiot_id"] == 2244 and log["d"]["podmiot_id"] == 77
    # cykl chodzi w kółko — drugi przebieg nie ma już czego ruszać
    assert rozliczanie._uzupelnij_znak_id(log) == 0


def test_ten_sam_klub_nie_wchodzi_do_ksiegi_pod_dwoma_numerami():
    log: dict = {}
    wspolne = {
        "mecz_id": 7, "mecz": "AGF – Viborg", "kickoff_ts": 1785700000,
        "podmiot": "AGF", "rynek": "Gole drużyny", "p_model": 0.7,
    }
    rozliczanie._dopisz_nowe(log, [
        {**wspolne, "podmiot_id": -1291, "rynek_kod": "team_goals",
         "linia": 1.5, "strona": "ponizej", "kurs": 1.85},
        {**wspolne, "podmiot_id": 1291, "rynek_kod": "team_corners",
         "linia": 4.5, "strona": "ponizej", "kurs": 2.27},
    ])
    assert {r["podmiot_id"] for r in log.values()} == {1291}


def test_karta_wznowiona_z_ksiegi_ma_numer_do_dopasowania_formy():
    """Strona łączy typ z formą przez `podmiot_id` — z minusem nie trafi nigdy."""
    bet = build_wc_fast._typ_z_logu({
        "mecz_id": 7, "mecz": "AGF – Viborg", "kickoff_ts": 1785700000,
        "podmiot_id": -1291, "podmiot": "AGF", "rynek_kod": "team_goals",
        "rynek": "Gole drużyny", "linia": 1.5, "strona": "ponizej",
        "kurs": 1.85, "p_model": 0.7,
    })
    assert bet["podmiot_id"] == 1291
    assert bet["podmiot_typ"] == "druzyna"
    assert bet["przeciwnik"] == "Viborg"


def test_suma_meczowa_z_ksiegi_wraca_jako_typ_DRUZYNOWY():
    """`match_`/`wiecej_` nie zaczynają się od `team_`, a strona filtruje po
    `podmiot_typ` — taki typ lądował wśród zawodników na stronie głównej."""
    for kod in ("match_corners", "match_cards", "wiecej_shots"):
        bet = build_wc_fast._typ_z_logu({
            "mecz_id": 7, "mecz": "AGF – Viborg", "kickoff_ts": 1785700000,
            "podmiot_id": -1291, "podmiot": "AGF", "rynek_kod": kod,
            "rynek": "X", "linia": 8.5, "strona": "ponizej",
            "kurs": 1.9, "p_model": 0.6,
        })
        assert bet["podmiot_typ"] == "druzyna", kod
        assert bet["podmiot_id"] == 1291, kod
