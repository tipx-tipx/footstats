# -*- coding: utf-8 -*-
"""Stempel ŹRÓDŁA SZANSY ma dojechać na stronę i do księgi wszystkimi drogami.

⚑ PO CO OSOBNY PLIK (2026-08-20). `test_stempel_przechodzi_do_ksiegi`
wymienia w opisie trzy białe listy, ale sprawdza tylko dwie — te, które da
się zawołać jako funkcję. Trzecia, `build_wc_fast.rec_pewniaka`, jest
słownikiem wewnątrz pętli w funkcji na kilka tysięcy linii i testu nie
miała. Tędy właśnie uciekł stempel `zrodlo_p` przy przełączeniu 18.08.

Koszt przeoczenia, zmierzony 20.08 na produkcji:

  * 1187 z 1511 typów opublikowanych po przełączeniu weszło do księgi bez
    stempla, choć liczbę modelu miały — czujnik przełączenia liczył lukę
    na 200 z 688 rozliczeń, i to na niereprezentatywnym wycinku (rynki
    meczowe zamiast drużynowych): pokazywał −4,7 pp zamiast −7,1 pp
    i margines +0,1 pp zamiast −1,4 pp,
  * warstwy karty (`_urealnij_do_pokazania`, `_sciagnij_karte_do_ceny`)
    rozpoznają typ modelu WYŁĄCZNIE po tym polu, więc bez niego ściągały
    liczbę modelu deltą policzoną dla starego rachunku.

Test jest STRUKTURALNY — czyta źródło. To jedyny sposób, żeby sprawdzić
białą listę, której nie da się wywołać, a przeoczenie w niej jest ciche:
nic nie pada, pole po prostu nie dojeżdża.
"""
import re
from pathlib import Path

from footstats.jobs import rozliczanie as R
from footstats.model import uczony


ZRODLO = Path(__file__).resolve().parent.parent / "footstats" / "jobs" / \
    "build_wc_fast.py"

# pola, które produkuje `uczony.stempel_zrodla` — komplet, nie wybór
POLA_STEMPLA = sorted(uczony.stempel_zrodla(
    0.55, {"p": 0.61, "lam": 4.2}, "uczony",
).keys())


def _blok(nazwa: str) -> str:
    """Treść słownika `nazwa = {...}` ze źródła silnika."""
    tekst = ZRODLO.read_text(encoding="utf-8")
    start = tekst.index(f"{nazwa} = {{")
    koniec = tekst.index("\n        }\n", start)
    return tekst[start:koniec]


def test_stempel_zrodla_ma_komplet_pol():
    """Gdy stempel urośnie o nowe pole, białe listy trzeba dopisać ręcznie."""
    assert POLA_STEMPLA == ["p_stary", "p_uczony", "zrodlo_p"], (
        "stempel źródła zmienił skład pól — sprawdź WSZYSTKIE białe listy: "
        "build_wc_fast.rec_pewniaka, rozliczanie._dopisz_nowe, "
        "rozliczanie._kupon_leg_do_logu oraz legi_pool w pętli zawodniczej"
    )


def test_rec_pewniaka_przepuszcza_stempel_zrodla():
    """⚑ Tędy idzie 79% typów — ta lista była przeoczona do 20.08."""
    blok = _blok("rec_pewniaka")
    for pole in POLA_STEMPLA:
        assert re.search(rf'"{pole}":\s*(round\(float\()?b\[', blok), (
            f"`{pole}` nie jest przepisywane w `rec_pewniaka` — pole zginie "
            "w drodze z puli na stronę i do księgi, a warstwy karty przestaną "
            "rozpoznawać typ modelu (patrz nota w tym pliku)"
        )


def test_stempel_zrodla_dojezdza_do_ksiegi():
    """Druga biała lista: value_bets -> księga."""
    log: dict = {}
    R._dopisz_nowe(log, [{
        "id": 1, "mecz_id": 100, "mecz": "A – B", "kickoff_ts": 1787100000,
        "podmiot_id": 5, "podmiot": "A", "podmiot_typ": "druzyna",
        "rynek_kod": "team_corners", "rynek": "Rzuty rożne drużyny",
        "linia": 4.5, "strona": "powyzej", "kurs": 1.85,
        "bukmacher": "Superbet", "p_model": 0.61, "pewnosc": "wysoka",
        **uczony.stempel_zrodla(0.55, {"p": 0.61, "lam": 4.2}, "uczony"),
    }])
    rec = next(iter(log.values()))
    assert rec.get("zrodlo_p") == "uczony"
    assert rec.get("p_stary") == 0.55
    assert (rec.get("p_uczony") or {}).get("p") == 0.61


def test_typ_bez_pokrycia_modelu_ma_wlasny_stempel():
    """Cichy fallback jest tu najgorszy z możliwych — strona pokazywałaby
    mieszankę dwóch rachunków, a pomiar przypisywał wszystko modelowi."""
    p, zrodlo = uczony.wybierz_szanse("druzyny", 0.55, None)
    assert (p, zrodlo) == (0.55, "stary_bez_pokrycia")
    assert uczony.stempel_zrodla(0.55, None, zrodlo) == {
        "zrodlo_p": "stary_bez_pokrycia", "p_stary": 0.55,
    }
