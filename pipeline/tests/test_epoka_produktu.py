"""Mundial to archiwum, nie nauczyciel.

POWÓD (2026-08-03, decyzja usera). Mistrzostwa były testem silnika; produktem
jest faza ligowa. Wszystkie warstwy uczące liczyły się jednak z CAŁEJ księgi,
a mundial to 27% jej rozliczeń — i mówił co innego niż liga:

    strzały zawodnicze   MUNDIAL  n=142  trafień 54%  deklaracja 69%  ROI −17,6%
    strzały zawodnicze   LIGA     n= 66  trafień 58%  deklaracja 58%  ROI  +9,7%

Mieszanka kazała ukarać ten rynek dwa razy — kalibracją (−0,604 zamiast −0,144
z samej ligi) i korektą strumienia „pewniaki" (−0,418, policzoną w 100% na
mundialu). Kary się dodają: przy szansie surowej 70% pokazywaliśmy 45,6%, czyli
poniżej progu publikacji 52%. Stąd „strumień zawodniczy stoi".

ZAKRES: wyłącznie uczenie. Rozliczenia, ROI i Skuteczność zostają nietknięte —
user te typy widział i wynik jest jego wynikiem.
"""

from footstats.jobs import rozliczanie as R


def _typ(mecz: str, **kw) -> dict:
    baza = {
        "mecz": mecz, "rynek_kod": "shots", "rynek": "Strzały",
        "podmiot": "X", "podmiot_id": 1, "linia": 1.5, "strona": "powyzej",
        "kurs": 2.0, "p_model": 0.7, "kickoff_ts": 1785000000,
        "wynik": "przegrany", "mecz_id": 1,
    }
    baza.update(kw)
    return baza


def test_mecz_dwoch_reprezentacji_to_mundial():
    assert R.epoka(_typ("Hiszpania – Francja")) == "ms"
    assert R.epoka(_typ("Spain – France")) == "ms"


def test_mecz_klubowy_to_liga():
    assert R.epoka(_typ("Djurgårdens IF – Västerås SK")) == "liga"
    # klub o nazwie mylącej z krajem po JEDNEJ stronie to nadal liga
    assert R.epoka(_typ("Brazylia – Djurgårdens IF")) == "liga"


def test_stempel_wygrywa_z_nazwami():
    """Gdyby rozpoznanie po nazwach kiedyś się myliło, zapis z chwili
    publikacji ma rację — historii nie przepisujemy pod nową regułę."""
    assert R.epoka(_typ("Hiszpania – Francja", epoka="liga")) == "liga"
    assert R.epoka(_typ("Realny Klub – Inny Klub", epoka="ms")) == "ms"


def test_publikacja_stempluje_epoke():
    log: dict = {}
    R._dopisz_nowe(log, [_typ("Hiszpania – Francja", wynik=None),
                         _typ("Lech – Legia", wynik=None, linia=2.5)])
    epoki = sorted(r.get("epoka") for r in log.values())
    assert epoki == ["liga", "ms"]


def _ksiega() -> dict:
    """Mundial mówi 'przeszacowujecie', liga mówi 'jest dobrze'."""
    log = {}
    for i in range(40):
        log[f"ms{i}"] = _typ("Hiszpania – Francja", p_model=0.70,
                             wynik="przegrany" if i % 2 else "wygrany",
                             kickoff_ts=1785000000 + i)
    for i in range(40):
        log[f"lg{i}"] = _typ("Lech – Legia", p_model=0.55,
                             wynik="wygrany" if i % 20 else "przegrany",
                             kickoff_ts=1785500000 + i)
    return log


def test_kalibracja_uczy_sie_tylko_z_ligi():
    log = _ksiega()
    tylko_liga = {k: v for k, v in log.items() if k.startswith("lg")}
    assert R.compute_bias_full(log) == R.compute_bias_full(tylko_liga)


def test_przewaga_rynkow_pomija_mundial():
    log = _ksiega()
    pelna = R.przewaga_rynkow(log)
    ligowa = R.przewaga_rynkow({k: v for k, v in log.items() if k.startswith("lg")})
    assert pelna == ligowa
    # a to jest ta liczba, na ktorej stoi decyzja o ukryciu rynku
    assert all(v["n"] == 40 for v in pelna.values())


def test_rynek_bez_wlasnej_epoki_dostaje_polowe_korekty_z_poprzedniej():
    """Twardy filtr epok wyrzucał informację zamiast ją ważyć. Strzały mają
    66 ligowych rozliczeń i własne zdanie; faule zostały z 15 — czyli bez
    kalibracji i bez osłony kwarantanny, przy 20% trafień na deklarowane 44%.
    Obie epoki wskazują ten sam KIERUNEK, różnią się siłą — stąd połowa."""
    log = {}
    for i in range(60):        # rynek TYLKO mundialowy: mocno przeszacowany
        log[f"ms{i}"] = _typ("Hiszpania – Francja", rynek_kod="fouls_committed",
                             p_model=0.75, wynik="przegrany" if i % 4 else "wygrany",
                             kickoff_ts=1785000000 + i)
    for i in range(60):        # rynek ligowy: trafia zgodnie z deklaracją
        log[f"lg{i}"] = _typ("Lech – Legia", p_model=0.55,
                             wynik="wygrany" if i % 2 else "przegrany",
                             kickoff_ts=1785500000 + i)
    bias = R.compute_bias_full(log)
    surowy = R.compute_bias_full(
        {k: v for k, v in log.items() if k.startswith("ms")}, _surowo=True,
    )
    assert "fouls_committed" in bias, "rynek bez ligowych danych ma zostać bez kary?"
    assert bias["fouls_committed"]["global"] == round(
        surowy["fouls_committed"]["global"] * R.KOREKTA_OBCEJ_EPOKI, 6
    ) or abs(bias["fouls_committed"]["global"]
             - surowy["fouls_committed"]["global"] * R.KOREKTA_OBCEJ_EPOKI) < 1e-6
    # rynek z WŁASNYMI danymi ligowymi nie widzi mundialu wcale
    assert bias["shots"]["global"] == R.compute_bias_full(
        {k: v for k, v in log.items() if k.startswith("lg")})["shots"]["global"]


def test_rozliczenia_i_skutecznosc_zostaja_nietkniete():
    """Zakres zmiany to UCZENIE. Wynik usera jest wynikiem usera."""
    log = _ksiega()
    dni = R.skutecznosc_per_dzien(list(log.values()))
    # oba produkty liczą się do wyniku usera — mundial znika z UCZENIA, nie
    # ze Skuteczności
    assert sum(d["rozliczone"] for d in dni) == 80
