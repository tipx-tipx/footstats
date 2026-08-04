"""Licznik cichych błędów — jedyna rzecz, która pokazuje, że dane przepadły.

Powód istnienia: przegląd 2026-08-04 policzył 79 miejsc w backendzie, gdzie
wyjątek jest łapany i zamieniany na `pass`/`continue`/`return []` bez logu.
Wszystkie cztery błędy znalezione 03–04.08 miały dokładnie ten podpis.
"""

from footstats import diagnostyka


def test_liczy_i_zeruje():
    diagnostyka.reset()
    assert diagnostyka.raport() == {}
    diagnostyka.cichy("statshub", "historia_druzyny")
    diagnostyka.cichy("statshub", "historia_druzyny")
    diagnostyka.cichy("365scores", "rozliczenie_statystyk")
    assert diagnostyka.raport() == {
        "statshub:historia_druzyny": 2,
        "365scores:rozliczenie_statystyk": 1,
    }
    diagnostyka.reset()
    assert diagnostyka.raport() == {}


def test_trzyma_pierwszy_komunikat_bledu(capsys):
    """Treść wyjątku bywa jedyną wskazówką, co się stało — bez niej diagnoza
    zaczyna się od powtarzania całego przebiegu."""
    diagnostyka.reset()
    diagnostyka.cichy("superbet", "linia_zawodnicza", ValueError("could not convert"))
    diagnostyka.cichy("superbet", "linia_zawodnicza", ValueError("inny komunikat"))
    diagnostyka.wypisz()
    out = capsys.readouterr().out
    assert "superbet:linia_zawodnicza=2" in out
    # pierwszy komunikat zachowany, drugi już nie nadpisuje
    assert "could not convert" in out
    assert "inny komunikat" not in out


def test_cichy_nigdy_nie_wybucha():
    """Wołane w bloku `except` — samo w sobie nie może rzucić, bo zamieniłoby
    połknięty błąd na wywalony cykl."""
    diagnostyka.reset()

    class Zlosliwy(Exception):
        def __str__(self):
            raise RuntimeError("nawet str() pada")

    try:
        diagnostyka.cichy("test", "zlosliwy", Zlosliwy())
    except Exception as e:  # pragma: no cover - to jest właśnie test
        raise AssertionError(f"licznik nie ma prawa rzucać: {e}") from e


def test_czysty_przebieg_nic_nie_pisze(capsys):
    diagnostyka.reset()
    diagnostyka.wypisz()
    assert capsys.readouterr().out == ""
