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


# --------------------------------------------------------------- rentgen

def test_rentgen_przezywa_do_meta():
    """⚑ 2026-08-21. Lejek drabinek istniał tylko jako `print` w logu Actions,
    który znika po kilku dniach, a `/actions/runs/{id}/logs` wymaga praw
    admina do repo (403 nawet dla repo publicznego). Sesja 21.08 nie mogła
    przez to odczytać produkcyjnych liczb i musiała liczyć je dry-runem, który
    widzi połowę meczów. Rozkład ma trafiać do meta, tak jak `ciche_bledy`."""
    from collections import Counter

    diagnostyka.reset()
    diagnostyka.zapisz_rentgen("drabinki_lejek", Counter({"par": 1457}))
    diagnostyka.zapisz_rentgen("budzet_odkrywania", {"wyczerpany": "czas"})
    r = diagnostyka.rentgen()
    assert r["drabinki_lejek"] == {"par": 1457}
    assert r["budzet_odkrywania"]["wyczerpany"] == "czas"


def test_rentgen_pomija_pusty_rozklad():
    """Pusty rozkład to brak pomiaru, nie pomiar równy zeru — w meta nie ma
    po co trzymać pustych kluczy."""
    diagnostyka.reset()
    diagnostyka.zapisz_rentgen("nic", {})
    assert diagnostyka.rentgen() == {}


def test_reset_czysci_takze_rentgen():
    """Cykl woła `reset` na starcie; rozkład z poprzedniego przebiegu nie może
    udawać bieżącego — to ta sama pułapka co przy licznikach cichych błędów."""
    diagnostyka.reset()
    diagnostyka.zapisz_rentgen("drabinki_lejek", {"par": 1})
    diagnostyka.reset()
    assert diagnostyka.rentgen() == {}
