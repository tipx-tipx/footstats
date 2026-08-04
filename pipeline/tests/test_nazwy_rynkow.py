"""Każdy rynek, który umiemy rozliczyć, MUSI mieć polską nazwę.

Powód (2026-08-04): sumy meczowe i „kto więcej" żyją od 30.07, ale nie miały
wpisów w `MARKET_NAMES_PL`. Fallback `.get(kod, kod)` oddawał wtedy surowy kod,
a ten trafiał wprost do zdań dla użytkownika — na zakładce Skuteczność stało
„Wstrzymane właśnie są: rzuty rożne drużyny, match_corners, najwyższa szansa
w meczu". Kod wyciekał do tekstu przez pięć dni i nikt tego nie łapał, bo
fallback z definicji nie wybucha.
"""

from footstats.jobs import rozliczanie
from footstats.jobs.build_demo import MARKET_NAMES_PL


def test_kazdy_rozliczalny_rynek_ma_polska_nazwe():
    rozliczalne = (
        set(rozliczanie.MARKETY_SUMY)
        | set(rozliczanie.MARKETY_WIECEJ)
        | set(rozliczanie.MARKETY_DRUZYNOWE)
    )
    brakujace = sorted(k for k in rozliczalne if k not in MARKET_NAMES_PL)
    assert not brakujace, (
        "rynki bez polskiej nazwy — ich KOD trafi do tekstu dla użytkownika: "
        + ", ".join(brakujace)
    )


def test_nazwa_nigdy_nie_jest_kodem():
    """Nazwa równa kodowi = ktoś dopisał wpis „na odczep się"."""
    podejrzane = sorted(k for k, v in MARKET_NAMES_PL.items() if k == v)
    assert not podejrzane, podejrzane


def test_nazwy_sa_po_polsku_i_czytelne():
    """Bez podkreśleń i bez samych małych liter — to ma iść do zdania."""
    zle = sorted(
        f"{k}={v}" for k, v in MARKET_NAMES_PL.items()
        if "_" in v or not v[:1].isupper()
    )
    assert not zle, zle
