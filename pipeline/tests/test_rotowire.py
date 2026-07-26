"""Testy parsera/dopasowań Rotowire (bez sieci)."""

from footstats.sources import rotowire


def test_norm_strips_accents_and_case():
    assert rotowire._norm("Julián Álvarez") == "julian alvarez"
    assert rotowire._norm("  Cape  Verde ") == "cape verde"


def test_in_xi_exact_and_fuzzy():
    xi = {"nico paz", "lionel messi", "emiliano martinez"}
    assert rotowire._in_xi(xi, "Lionel Messi")
    # wariant imienia: nazwisko + inicjał
    assert rotowire._in_xi(xi, "Nicolas Paz")
    assert not rotowire._in_xi(xi, "Julian Alvarez")
    # to samo nazwisko, inny inicjał imienia — nie może się dopasować
    assert not rotowire._in_xi(xi, "Lautaro Martinez")


def test_predicted_status_none_for_unknown_team():
    lineups = {"argentina": {"xi": {"lionel messi"}, "confirmed": False}}
    assert rotowire.predicted_status(lineups, "Argentina", "Lionel Messi") is True
    assert rotowire.predicted_status(lineups, "Argentina", "Kylian Mbappe") is False
    assert rotowire.predicted_status(lineups, "France", "Kylian Mbappe") is None


def test_is_confirmed():
    lineups = {"egypt": {"xi": set(), "confirmed": True}}
    assert rotowire.is_confirmed(lineups, "Egypt") is True
    assert rotowire.is_confirmed(lineups, "Ghana") is False


def test_norm_zwija_litery_ktorych_nfkd_nie_rozklada():
    """ł, ø, đ, þ, ß to OSOBNE znaki Unicode, nie "litera + diakryt" —
    rozkład NFKD ich nie tyka, a źródła trzymają nazwy zwinięte do ASCII.

    Regresja 2026-07-26: pół Ekstraklasy (Wisła, Widzew Łódź, Zagłębie,
    Jagiellonia Białystok, Śląsk Wrocław) nigdy nie trafiało w bank stylu,
    bo lookup szedł po "wisła krakow", a bank trzymał "wisla krakow".
    """
    assert rotowire._norm("Wisła Kraków") == "wisla krakow"
    assert rotowire._norm("Widzew Łódź") == "widzew lodz"
    assert rotowire._norm("Zagłębie Lubin") == "zaglebie lubin"
    assert rotowire._norm("Śląsk Wrocław") == "slask wroclaw"
    # te same pułapki w ligach spoza Polski, które też obsługujemy
    assert rotowire._norm("Bodø/Glimt") == "bodo/glimt"
    assert rotowire._norm("FK Čukarički") == "fk cukaricki"
    assert rotowire._norm("Malmö FF") == "malmo ff"
    # znaki rozkładalne mają działać jak dotąd
    assert rotowire._norm("Górnik Zabrze") == "gornik zabrze"
