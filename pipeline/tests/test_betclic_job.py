"""Osobny job pobierający ofertę Betclica — zakres i bezpieczniki.

Job powstał, bo w cyklu Betclic był nie do uratowania: 180 s budżetu starczało
na 3 mecze z 60, a pamięć wygasa po dobie, więc wpisy przepadały szybciej, niż
je dobieraliśmy. Tu sprawdzamy dwie rzeczy, które decydują o tym, czy job ma
sens: KOGO pyta i czego NIE robi, gdy coś padnie.
"""
import time

from footstats.jobs import betclic_oferty as J

TERAZ = 1_800_000_000
GODZINA = 3600


def _mecz(mid, kick, propsy=30, home="Gospodarz", away="Gosc"):
    return {"id": mid, "kickoff_ts": kick, "propsy_superbet": propsy,
            "gospodarz": home, "gosc": away}


def test_bierzemy_tylko_mecze_przed_gwizdkiem():
    matches = [_mecz(1, TERAZ + GODZINA), _mecz(2, TERAZ - GODZINA)]
    assert set(J._mecze_w_zakresie(matches, TERAZ)) == {1}


def test_mecze_bez_propsow_superbetu_tez_wchodza_ale_po_tych_z_propsami():
    """⚑ 2026-09-14: odsiew z 08.08 („Superbet 0 = Betclic 0") był fałszywy —
    zmierzone na żywo: Midtjylland–Brøndby SB 0 propsów, Betclic 49 zawodników.
    Mecze bez propsów SB wchodzą, ale pobieramy je PO tych z propsami."""
    matches = [_mecz(1, TERAZ + GODZINA, propsy=25),
               _mecz(2, TERAZ + GODZINA, propsy=0)]
    assert set(J._mecze_w_zakresie(matches, TERAZ)) == {1, 2}
    assert J._z_propsami_superbetu(matches) == {1}


def test_pomijamy_mecze_za_daleko_w_przod():
    """Dalekie mecze nie mają jeszcze pełnej oferty, a zajęłyby miejsce
    najbliższym."""
    matches = [_mecz(1, TERAZ + GODZINA),
               _mecz(2, TERAZ + J.HORYZONT_S + GODZINA)]
    assert set(J._mecze_w_zakresie(matches, TERAZ)) == {1}


def test_zakres_dziala_takze_dla_slownika_matches():
    """`matches` bywa listą albo słownikiem — zależnie od tego, czy przyszło
    z dumpu, czy z Supabase."""
    matches = {"1": _mecz(1, TERAZ + GODZINA)}
    assert set(J._mecze_w_zakresie(matches, TERAZ)) == {1}


def test_smieciowy_rekord_nie_wywala_zakresu():
    matches = [_mecz(1, TERAZ + GODZINA), {"id": "abc"}, {}, None]
    assert set(J._mecze_w_zakresie([m for m in matches if m], TERAZ)) == {1}


def test_padniety_odczyt_pamieci_konczy_bez_zapisu(monkeypatch):
    """⚑ Najważniejszy bezpiecznik: padnięty odczyt to NIE jest pusta pamięć.
    Zapis z takiego stanu skasowałby dorobek poprzednich przebiegów."""
    # `main` liczy zakres względem zegara, nie względem naszej stałej
    kick = int(time.time()) + GODZINA
    monkeypatch.setattr(J.supa, "get_key", lambda k: [_mecz(1, kick)])
    monkeypatch.setattr(J.supa, "get_key_ok", lambda k: (None, False))

    zapisy = []
    monkeypatch.setattr(J.supa, "put_key_bezpiecznie",
                        lambda k, v: zapisy.append((k, v)) or True)
    monkeypatch.setattr(J.betclic, "paruj_mecze",
                        lambda *a, **kw: ({}, []))
    assert J.main() == 1
    assert zapisy == []


def test_brak_meczow_konczy_sie_spokojnie(monkeypatch):
    monkeypatch.setattr(J.supa, "get_key", lambda k: [])
    zapisy = []
    monkeypatch.setattr(J.supa, "put_key_bezpiecznie",
                        lambda k, v: zapisy.append(k) or True)
    assert J.main() == 0
    assert zapisy == []


def test_jeden_zepsuty_mecz_nie_zabija_przebiegu(monkeypatch):
    """⚑ REGRESJA 2026-08-08: trzy przebiegi joba z rzędu na czerwono.

    `AttributeError` z JEDNEGO zakładu (dekoder oddał `[]` zamiast nazwy)
    przeleciał przez wąską listę wyjątków i zabił cały przebieg — razem
    z dwiema minutami parowania i szesnastoma meczami, które czekały
    w kolejce. Drugi mecz musi się pobrać mimo padniętego pierwszego.
    """
    kick = int(time.time()) + GODZINA
    matches = [_mecz(1, kick, home="A", away="B"),
               _mecz(2, kick + 60, home="C", away="D")]
    monkeypatch.setattr(J.supa, "get_key", lambda k: matches)
    monkeypatch.setattr(J.supa, "get_key_ok", lambda k: ({}, True))
    monkeypatch.setattr(J.betclic, "paruj_mecze", lambda *a, **kw: (
        {1: {"id": 11, "nazwa": "A - B"}, 2: {"id": 22, "nazwa": "C - D"}}, []))

    def _kursy(bc_id):
        if bc_id == 11:
            raise AttributeError("'list' object has no attribute 'lower'")
        return {"players": {"kowalski": {"shots": {1.5: {"over": 2.0}}}}}

    monkeypatch.setattr(J.betclic, "kursy_zawodnikow", _kursy)
    zapisy = {}
    monkeypatch.setattr(J.supa, "put_key_bezpiecznie",
                        lambda k, v: zapisy.update({k: v}) or True)

    assert J.main() == 0
    assert list(zapisy[J.BETCLIC_KLUCZ]) == ["2"]


def test_caly_zakres_5_dni_takze_bez_propsow_superbetu():
    """⚑ 18.09: okno 48 h dla meczów bez propsów SB i horyzont 4 dni stały na
    koszcie ~71 s/mecz (blokujące zamykanie strumienia). Teraz cały zakres
    analizy — tryb ligowy liczy 5 dni."""
    matches = [_mecz(1, TERAZ + 5 * 24 * GODZINA - GODZINA, propsy=0),
               _mecz(2, TERAZ + 3 * 24 * GODZINA, propsy=0)]
    assert set(J._mecze_w_zakresie(matches, TERAZ)) == {1, 2}


def test_kazdy_przebieg_odswieza_takze_mecze_z_pamieci_i_bierze_zakres_cyklu(monkeypatch):
    """Mecz już zapamiętany jest pobierany ponownie (nowe rynki, ruch kursu —
    Chery 17.09 dostał ofertę Betclica dopiero o 15:44), a zakres pochodzi
    z `zakres_meczow` (każdy analizowany mecz), nie z `matches`."""
    kick = int(time.time()) + GODZINA
    zakres = [_mecz(1, kick, home="A", away="B"), _mecz(2, kick + 60, home="C", away="D")]
    klucze_czytane = []

    def _get(k):
        klucze_czytane.append(k)
        return zakres if k == J.ZAKRES_MECZOW_KLUCZ else [_mecz(9, kick)]

    monkeypatch.setattr(J.supa, "get_key", _get)
    pamiec = {"1": {"ts": int(time.time()) - 60,
                    "players": {"stary": {"shots": {"1.5": {"over": 1.9}}}}}}
    monkeypatch.setattr(J.supa, "get_key_ok", lambda k: (pamiec, True))
    monkeypatch.setattr(J.betclic, "paruj_mecze", lambda *a, **kw: (
        {1: {"id": 11, "nazwa": "A - B"}, 2: {"id": 22, "nazwa": "C - D"}}, []))
    pytano = []

    def _kursy(bc_id):
        pytano.append(bc_id)
        return {"players": {"nowy": {"shots_outside_box": {1.5: {"over": 3.9}}}}}

    monkeypatch.setattr(J.betclic, "kursy_zawodnikow", _kursy)
    zapisy = {}
    monkeypatch.setattr(J.supa, "put_key_bezpiecznie",
                        lambda k, v: zapisy.update({k: v}) or True)
    assert J.main() == 0
    assert klucze_czytane[0] == J.ZAKRES_MECZOW_KLUCZ
    assert sorted(pytano) == [11, 22]
    assert "nowy" in zapisy[J.BETCLIC_KLUCZ]["1"]["players"]
