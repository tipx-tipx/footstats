"""Oznaczenia typów na stronie (2026-10-18) — patrz `OZNACZENIA_TYPU`."""
from footstats.jobs import build_wc_fast as B

MARZE = {"druzyny": 0.05, "zawodnicy": 0.18}


def _typ(podmiot_typ="zawodnik", kurs=1.40, p=0.70, pkw=0.7, polka="wysoka_szansa", **kw):
    return {"podmiot_typ": podmiot_typ, "kurs": kurs, "p_model": p, "polka": polka,
            "p_uczony": {"p": p, "pkw": pkw}, **kw}


def test_perla_wyzsze_kursy_z_pokryciem_i_modelem_nad_cena():
    # drużyna 1,90: cena po marży 5% = 0,50
    assert B.oznaczenia_typu(_typ("druzyna", 1.90, 0.55, 0.8, "wyzsze_kursy"), MARZE) == ["perla"]
    # model poniżej ceny — nie perełka
    assert "perla" not in B.oznaczenia_typu(_typ("druzyna", 1.90, 0.45, 0.9, "wyzsze_kursy"), MARZE)
    # wysoka szansa — perełek tam nie ma
    assert "perla" not in B.oznaczenia_typu(_typ("druzyna", 1.30, 0.80, 0.9), MARZE)


def test_nad_kursem_tylko_zawodnicy():
    # zawodnik 1,60: cena po marży 18% = 0,5125 → próg 0,6625
    assert "nad_kursem" in B.oznaczenia_typu(_typ(kurs=1.60, p=0.67), MARZE)
    assert "nad_kursem" not in B.oznaczenia_typu(_typ(kurs=1.60, p=0.65), MARZE)
    # u drużyn ta reguła była ujemna — nie oznaczamy
    assert "nad_kursem" not in B.oznaczenia_typu(_typ("druzyna", 1.60, 0.90), MARZE)


def test_seria_od_dziewieciu_na_dziesiec():
    assert B.oznaczenia_typu(_typ(p=0.50, pkw=0.9), MARZE) == ["seria"]
    assert B.oznaczenia_typu(_typ(p=0.50, pkw=0.8), MARZE) == []


def test_perla_nie_dubluje_serii():
    ozn = B.oznaczenia_typu(_typ("druzyna", 1.90, 0.60, 1.0, "wyzsze_kursy"), MARZE)
    assert ozn == ["perla"]


def test_bez_danych_bez_oznaczen():
    assert B.oznaczenia_typu({"kurs": None}, MARZE) == []
    assert B.oznaczenia_typu(_typ(sugestia=True, pkw=1.0), MARZE) == []
    assert B.oznaczenia_typu({"podmiot_typ": "druzyna", "kurs": 1.9, "p_model": 0.6,
                              "polka": "wyzsze_kursy"}, MARZE) == []   # brak pokrycia


def test_bez_marz_bierze_domyslna():
    assert B.oznaczenia_typu(_typ(kurs=1.60, p=0.90), None) == ["nad_kursem"]
