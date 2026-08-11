"""Znak kalibracji: delta uczona tam, gdzie jest nakładana.

Błąd, który te testy zamykają (znaleziony 2026-08-11): `compute_bias_full`
i `korekta_strumienia` uczyły się na `p` WYBRANEGO ZAKŁADU, a silnik nakłada
wynik na `p_over`. Przy 93% typów „poniżej" na rynkach drużynowych delta
lądowała po przeciwnej stronie skali i pogłębiała błąd, zamiast go leczyć.
"""

from footstats.jobs import rozliczanie as R
from footstats.model import kupony


def _rek(strona, p, wynik, rynek="team_corners", **extra):
    return {
        "rynek_kod": rynek, "strona": strona, "p_model": p, "wynik": wynik,
        "kurs": 1.5, "kickoff_ts": 1786000000, "epoka": "liga",
        "podmiot_id": 1, "mecz_id": 1, "linia": 4.5, **extra,
    }


def test_transformacja_odbija_p_i_wynik_dla_ponizej():
    [out] = R.w_orientacji_over([_rek("ponizej", 0.75, "wygrany")])
    assert abs(out["p_model"] - 0.25) < 1e-9
    assert out["wynik"] == "przegrany"


def test_transformacja_nie_rusza_powyzej():
    wej = _rek("powyzej", 0.62, "wygrany")
    [out] = R.w_orientacji_over([wej])
    assert out["p_model"] == 0.62 and out["wynik"] == "wygrany"


def test_strumien_w_calosci_powyzej_jest_nietkniety():
    """Zawodnicy i drabinki są zawsze „powyżej" — transformacja to tożsamość."""
    grp = [_rek("powyzej", 0.4 + i / 50, "wygrany" if i % 3 else "przegrany",
                rynek="shots") for i in range(12)]
    assert R.w_orientacji_over(grp) == grp


def test_znak_delty_dla_przeszacowanego_ponizej():
    """Model deklaruje 80% na „poniżej", trafia 50% — delta MUSI ściągać.

    W skali `p_over` znaczy to deltę DODATNIĄ (podnosi p_over, czyli obniża
    p_under). Przed naprawą wychodziła ujemna, czyli podnosiła „poniżej".
    """
    grp = [_rek("ponizej", 0.8, "wygrany" if i % 2 else "przegrany")
           for i in range(40)]
    d_over = R._bias_logit(R.w_orientacji_over(grp))
    d_stary = R._bias_logit(grp)
    assert d_over > 0.3, "korekta ma podnosić p_over, czyli ściągać 'poniżej'"
    assert d_stary < 0, "stara orientacja dawała znak przeciwny"


def test_znak_delty_dla_przeszacowanego_powyzej():
    """Ta sama sytuacja po stronie „powyżej" — delta ujemna, bez odbicia."""
    grp = [_rek("powyzej", 0.8, "wygrany" if i % 2 else "przegrany",
                rynek="shots") for i in range(40)]
    assert R._bias_logit(R.w_orientacji_over(grp)) < -0.3


def test_obie_strony_tej_samej_linii_daja_zgodna_delte():
    """Ten sam materiał opisany raz jako over, raz jako under -> ta sama delta.

    To jest niezmiennik, którego złamanie było istotą błędu: opis zakładu nie
    może zmieniać tego, czego uczy się kalibracja.
    """
    over = [_rek("powyzej", 0.35, "wygrany" if i < 14 else "przegrany")
            for i in range(40)]
    under = [_rek("ponizej", 0.65, "przegrany" if i < 14 else "wygrany")
             for i in range(40)]
    d_o = R._bias_logit(R.w_orientacji_over(over))
    d_u = R._bias_logit(R.w_orientacji_over(under))
    assert abs(d_o - d_u) < 1e-6


def test_kupon_leg_ponizej_koryguje_sie_w_skali_over():
    """Leg „poniżej" z deltą +0,5 (w skali over) ma szansę SPAŚĆ."""
    leg = {"rynek_kod": "team_corners", "strona": "ponizej", "p_model": 0.75}
    p = kupony.urealnij_leg_wg_strony(leg, {"druzyny": 0.5})
    assert p < 0.75, "dodatnia delta w skali over musi ściągać 'poniżej'"
    # ta sama delta na legu „powyżej" — podnosi
    leg_o = {"rynek_kod": "team_corners", "strona": "powyzej", "p_model": 0.25}
    assert kupony.urealnij_leg_wg_strony(leg_o, {"druzyny": 0.5}) > 0.25


def test_kupon_leg_bez_korekty_zostaje_bez_zmian():
    leg = {"rynek_kod": "shots", "strona": "powyzej", "p_model": 0.6}
    assert kupony.urealnij_leg_wg_strony(leg, None) == 0.6
    assert kupony.urealnij_leg_wg_strony(leg, {}) == 0.6


def test_suma_obu_stron_po_korekcie_wynosi_jeden():
    """p_over + p_under = 1 po nałożeniu tej samej delty — wymóg audytu."""
    for p_over in (0.2, 0.5, 0.83):
        for d in (-0.9, 0.0, 0.45):
            o = {"rynek_kod": "team_goals", "strona": "powyzej",
                 "p_model": p_over}
            u = {"rynek_kod": "team_goals", "strona": "ponizej",
                 "p_model": 1.0 - p_over}
            suma = (kupony.urealnij_leg_wg_strony(o, {"druzyny": d})
                    + kupony.urealnij_leg_wg_strony(u, {"druzyny": d}))
            assert abs(suma - 1.0) < 1e-9


def test_p_surowe_odwraca_to_co_nalozono():
    """Stempel `kal_strumien` musi dać się odjąć dokładnie — inaczej kolejny
    pomiar uczy się z już skorygowanego `p` i regulator oscyluje."""
    for p_over, d in ((0.3, 0.4), (0.7, -0.55), (0.5, 0.9)):
        p_kor = kupony.urealnij_leg(p_over, d)
        rec = _rek("ponizej", 1.0 - p_kor, "wygrany", kal_strumien=d)
        assert abs(R._p_surowe(rec) - (1.0 - p_over)) < 1e-9
