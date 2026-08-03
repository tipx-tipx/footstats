"""Kartki mają WŁASNY profil arbitra, nie ten liczony z fauli.

POWÓD (zgłoszenie usera 2026-08-03: „do kartek ważni są sędziowie"). Rynek
`team_cards` jechał na mnożniku z FAULI — a to dwie różne cechy: przy tej samej
liczbie fauli jeden arbiter sięga po kartkę, drugi upomina. Kartki per mecz
leżały już w banku stylu (`game_team_stats` -> żółte + czerwone), a bank i cache
sędziów są kluczowane tym samym id meczu 365, więc drugi profil kosztuje zero
zapytań.
"""

from footstats.jobs import build_wc_fast as bwf
from footstats.model import context, kontekst_drabinki


def test_kartkowy_profil_wypiera_faulowy_gdy_ma_probe():
    sed = {"sedzia": "X", "mnoznik": 1.05, "n": 20,
           "mnoznik_kartek": 1.40, "n_kartek": 9}
    assert context.sedzia_dla_rynku(sed, "team_cards") == (1.40, 9)
    # faule i reszta jadą jak dotąd
    assert context.sedzia_dla_rynku(sed, "team_fouls") == (1.05, 20)
    assert context.sedzia_dla_rynku(sed, "team_corners") == (1.05, 20)


def test_chuda_proba_kartek_wraca_do_starego_mnoznika():
    """Trzy mecze to szum; mnożnik z fauli mierzy inną cechę, ale skorelowaną
    i stoi na próbie — lepszy przybliżony sygnał niż dokładny z trzech meczów."""
    sed = {"sedzia": "X", "mnoznik": 1.05, "n": 20,
           "mnoznik_kartek": 1.90, "n_kartek": 3}
    assert context.sedzia_dla_rynku(sed, "team_cards") == (1.05, 20)


def test_brak_obsady_jest_neutralny():
    assert context.sedzia_dla_rynku(None, "team_cards") == (None, 0)
    assert context.referee_factor(None, 0, market_is_disciplinary=True) == 1.0


def test_kartka_zawodnika_w_drabinkach_tez_idzie_po_kartkach():
    sed = {"sedzia": "X", "mnoznik": 1.0, "n": 20,
           "mnoznik_kartek": 1.45, "n_kartek": 12}
    m, opis = kontekst_drabinki.mnoznik_sedziego("yellow_card", sed)
    assert m > 1.0 and opis["surowy"] == 1.45 and opis["mecze"] == 12
    # rynek niedyscyplinarny dalej bez arbitra
    assert kontekst_drabinki.mnoznik_sedziego("shots", sed) == (1.0, {})


def test_profil_liczy_kartki_z_banku_bez_dodatkowych_zapytan(monkeypatch):
    """Bank stylu i cache sędziów łączy id meczu 365 — nic nie dociągamy."""
    cache = {
        "1": {"sedzia": "Sroka", "faule": 20.0, "druzyny": ["a", "b"]},
        "2": {"sedzia": "Sroka", "faule": 20.0, "druzyny": ["a", "c"]},
        "3": {"sedzia": "Lagodny", "faule": 20.0, "druzyny": ["a", "b"]},
        "4": {"sedzia": "Lagodny", "faule": 20.0, "druzyny": ["a", "c"]},
    }
    # ta sama liczba fauli wszędzie, RÓŻNE kartki — dokładnie ten przypadek,
    # którego stary profil nie umiał odróżnić
    bank_gry = {
        "1": {"druzyny": {"a": {"kartki": 4.0}, "b": {"kartki": 4.0}}},
        "2": {"druzyny": {"a": {"kartki": 4.0}, "c": {"kartki": 4.0}}},
        "3": {"druzyny": {"a": {"kartki": 1.0}, "b": {"kartki": 1.0}}},
        "4": {"druzyny": {"a": {"kartki": 1.0}, "c": {"kartki": 1.0}}},
    }
    monkeypatch.setattr(bwf.supa, "get_key", lambda k: cache)
    monkeypatch.setattr(bwf.supa, "put_key_bezpiecznie", lambda k, v: True)
    monkeypatch.setattr(bwf.scores365, "finished_games_by_competition",
                        lambda *a, **k: [])
    monkeypatch.setattr(bwf.scores365, "scheduled_games_by_competition",
                        lambda *a, **k: [{"id": 99, "home": "a", "away": "b",
                                          "ts": 1000}])
    monkeypatch.setattr(bwf.scores365, "game_referee", lambda gid: "Sroka")
    ev = [{"id": 7, "homeTeamId": 1, "awayTeamId": 2,
           "timeStartTimestamp": 1000}]
    out = bwf.profil_sedziow(ev, {1: "a", 2: "b"}, bank_gry=bank_gry)
    prof = out[7]
    assert prof["n_kartek"] == 2
    # Sroka daje 4 kartki tam, gdzie średnia par to 2,5 -> mnożnik > 1
    assert prof["mnoznik_kartek"] > 1.3
    # faule miał identyczne jak Łagodny, więc stary mnożnik tego nie widział
    assert abs(prof["mnoznik"] - 1.0) < 0.01
