# -*- coding: utf-8 -*-
"""PRÓG TRANSFERU (2026-09-10, etap 6).

Licznik transferu istnieje od 25.08 i za każdym razem mówił prawdę — tyle że
nikt na niego nie patrzył, dopóki projekt nie padł. 04.09 straż odcięcia
kończyła joby ZIELONO, więc awaria stała pięć dni niezauważona.

Próg ma krzyczeć, ZANIM limit padnie: ostrzeżenie przy trzykrotności normy,
czerwony job przy czterokrotności.
"""
import pytest

from footstats import supa


@pytest.fixture(autouse=True)
def _czysty_licznik(monkeypatch):
    monkeypatch.setattr(supa, "_egress", {})
    yield


def _przeczytaj(mb: float, klucz: str = "jakis_klucz") -> None:
    supa._egress[klucz] = [1, int(mb * 1e6)]


def test_normalny_przebieg_nie_alarmuje(capsys):
    """Po etapie 3 pipeline czyta najwyżej ~9,6 MB — to ma być cisza."""
    _przeczytaj(9.6)
    assert supa.straz_budzetu("cykl") == pytest.approx(9.6, abs=0.1)
    assert "Uwaga" not in capsys.readouterr().err


def test_ostrzezenie_przy_podwyzszonym_transferze(capsys):
    _przeczytaj(20.0)
    supa.straz_budzetu("cykl")
    assert "Uwaga" in capsys.readouterr().err


def test_alarm_wywala_job(capsys):
    """Czterokrotność normy = regresja, którą trzeba naprawić w kodzie."""
    _przeczytaj(50.0)
    with pytest.raises(supa.PrzekroczonyBudzet) as ex:
        supa.straz_budzetu("cykl")
    assert "50.0 MB" in str(ex.value)


def test_alarm_bez_podnoszenia_tylko_drukuje(capsys):
    """W bloku `finally` wyjątek przesłoniłby PIERWOTNĄ przyczynę awarii."""
    _przeczytaj(50.0)
    assert supa.straz_budzetu("cykl", podnies=False) == pytest.approx(50.0)
    assert "TRANSFER POZA NORMĄ" in capsys.readouterr().err


def test_sumuje_wszystkie_klucze():
    """Regresja rzadko siedzi w jednym kluczu — 21 odczytów po 2 MB też boli.

    Tak właśnie wyglądało spalenie z 01.09: `typy_log` czytany 14 razy
    w jednym cyklu, każdy odczyt osobno niewinny.
    """
    for i in range(21):
        _przeczytaj(2.0, f"klucz_{i}")
    with pytest.raises(supa.PrzekroczonyBudzet):
        supa.straz_budzetu("cykl")


def test_progi_maja_sens_wobec_limitu():
    """Kontrola samych liczb: alarm musi być poniżej tempa, które pali limit.

    5 GB/mies. = ~170 MB/dobę przy ~40 przebiegach = ~4 MB na przebieg.
    """
    budzet_na_przebieg = 5000 / 30 / 40
    assert supa.OSTRZEZENIE_PRZEBIEGU_MB > budzet_na_przebieg
    assert supa.ALARM_PRZEBIEGU_MB > supa.OSTRZEZENIE_PRZEBIEGU_MB
    # alarm ma być wcześniej niż tempo palące miesięczny limit w jedną dobę
    assert supa.ALARM_PRZEBIEGU_MB * 40 < 5000
