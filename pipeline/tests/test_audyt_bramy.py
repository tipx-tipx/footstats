# -*- coding: utf-8 -*-
"""Alarm „brama zdejmuje lepszy materiał" musi porównywać JAK ZA JAK.

Ta tabela (część 5 kontroli startowej) raz już zmieniła produkt: na jej
podstawie kwarantanny przestały zdejmować typy ze strony. Do 13.08 liczyła
odniesienie ze WSZYSTKIEGO, co publikowane — razem z drabinkami, których żadna
z tych bram nie dotyczy, a które mają ROI −25%. Odniesienie było przez to
zaniżone o ~2 pp i brama zdejmująca materiał GORSZY od publikowanego
wychodziła w alarmie jako zdejmująca lepszy.

Dokładnie tak wyglądało okno zgody (`rozjazd_z_rynkiem`): −2,4% wobec −4,2%
„na stronie", ale −1,9% na tym samym materiale, z którego brama wybiera.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from footstats.jobs import rozliczanie as R

_SCIEZKA = Path(__file__).resolve().parent.parent / "scripts" / "audyt_uczenia.py"


def _audyt():
    spec = importlib.util.spec_from_file_location("audyt_uczenia", _SCIEZKA)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _typ(wynik: str, kurs: float = 2.0, ekran: str = "druzyny",
         poza: str | None = None) -> dict:
    r = {
        "wynik": wynik, "kurs": kurs, "p_model": 0.6,
        "ekran": ekran, "rynek_kod": "team_goals", "wersje": {},
    }
    if poza:
        r["poza_publikacja"] = poza
    return r


def test_odniesienie_liczy_sie_na_skladzie_bramy():
    """Brama bez drabinek nie może być porównywana ze zbiorem z drabinkami."""
    audyt = _audyt()
    # publikowane: drużyny na zero (kurs 2,0 pół na pół) i drabinki na minus
    pub = ([_typ("wygrany"), _typ("przegrany")] * 10
           + [_typ("przegrany", ekran="drabinki")] * 10)
    pub_wg = {}
    for r in pub:
        pub_wg.setdefault(R._strumien(r), []).append(r)

    # brama zdejmuje WYŁĄCZNIE typy drużynowe
    zdjete = [_typ("przegrany", poza="brama")] * 5

    odn = audyt._odniesienie_skladem(zdjete, pub_wg, R)
    roi_calosci = audyt._roi(pub)

    assert roi_calosci < -0.3, "kontrola założenia: drabinki ciągną całość w dół"
    assert odn == pytest.approx(0.0, abs=1e-9), (
        "odniesieniem dla bramy drużynowej są typy drużynowe, nie całość"
    )


def test_brama_zdejmujaca_gorsze_nie_trafia_do_alarmu(capsys):
    """Regresja wprost: −2,4% wobec −1,9% to NIE jest 'lepszy materiał'."""
    audyt = _audyt()
    # 20 drużynowych pół na pół (ROI 0%) + 10 drabinek na minus (ROI −100%)
    pub = ([_typ("wygrany"), _typ("przegrany")] * 10
           + [_typ("przegrany", ekran="drabinki")] * 10)
    # brama zdejmuje 30 typów drużynowych o ROI −20% — gorszych niż te 0%,
    # ale lepszych niż całość publikowana razem z drabinkami
    zdjete = ([_typ("wygrany", kurs=1.6, poza="rozjazd_z_rynkiem")] * 15
              + [_typ("przegrany", kurs=1.6, poza="rozjazd_z_rynkiem")] * 15)
    assert audyt._roi(zdjete) == pytest.approx(-0.2)

    audyt.czesc5_bramy(pub + zdjete, R)
    out = capsys.readouterr().out

    assert "rozjazd_z_rynkiem" in out, (
        "brama ma być w tabeli i mieć czytelną nazwę — przy węższej kolumnie "
        "ucinało ją do 'rozjazd_z_ryn'"
    )
    assert "BRAMY, KTÓRE ZDEJMUJĄ MATERIAŁ LEPSZY" not in out, (
        "brama zdejmująca materiał gorszy od swojego odniesienia nie może "
        "trafić do alarmu — to był błąd sprzed 13.08"
    )


def test_brama_zdejmujaca_lepsze_dalej_krzyczy(capsys):
    """Naprawa nie może uciszyć alarmu tam, gdzie jest zasadny."""
    audyt = _audyt()
    pub = [_typ("przegrany", kurs=1.6)] * 30          # ROI −100%
    zdjete = [_typ("wygrany", kurs=1.6, poza="kwarantanna_rynku")] * 30

    audyt.czesc5_bramy(pub + zdjete, R)
    out = capsys.readouterr().out

    assert "BRAMY, KTÓRE ZDEJMUJĄ MATERIAŁ LEPSZY" in out
    assert "kwarantanna_rynku" in out


def test_strumien_bez_publikowanych_nie_wywraca_odniesienia():
    """Gdy strumień bramy nie ma ANI JEDNEGO publikowanego — pomijamy go,
    zamiast liczyć zero i zaniżać odniesienie."""
    audyt = _audyt()
    pub = [_typ("wygrany", kurs=2.0)] * 10            # same drużyny, ROI 0%
    pub_wg = {}
    for r in pub:
        pub_wg.setdefault(R._strumien(r), []).append(r)

    mieszane = ([_typ("przegrany", poza="brama")] * 5
                + [_typ("przegrany", ekran="drabinki", poza="brama")] * 5)
    odn = audyt._odniesienie_skladem(mieszane, pub_wg, R)

    assert odn == pytest.approx(audyt._roi(pub)), (
        "drabinki bez publikowanego odpowiednika nie mają wnosić zera"
    )
