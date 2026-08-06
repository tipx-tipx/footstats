"""Typ odcięty selekcją listy nie liczy się do Skuteczności (2026-08-06).

Zgłoszenie usera: „w Skuteczności 75 typów drużynowych z dnia, a na zakładce
było najwyżej 10–15". Selekcja listy (LISTA_CAP i limity różnorodności,
2026-08-01) była jedyną bramą wyświetlania, która nie meldowała księdze
zdjęć — świeży typ wycięty z dwudziestki szedł do `typy_log` jako
opublikowany. Zmierzone 06.08: 22 z 26 wpisów „opublikowanych" w oknie
ostatniego cyklu nie było na stronie; rejestr publikacji trzymał 141 wpisów
wobec 20 typów w `value_bets`.

Decyzja usera: w Skuteczności tylko typy ukazane na liście, reszta liczy się
i uczy W TLE — jak kwarantanna.
"""
import time

from footstats.jobs import build_wc_fast as B
from footstats.jobs import rozliczanie as R


def _typ(**kw) -> dict:
    b = {
        "mecz_id": 1, "mecz": "Wisła Kraków – GKS Katowice",
        "kickoff_ts": int(time.time()) + 7200,
        "podmiot_id": 500, "podmiot": "GKS Katowice",
        "rynek_kod": "team_corners", "rynek": "Rzuty rożne drużyny",
        "linia": 6.5, "strona": "ponizej", "kurs": 1.23, "p_model": 0.88,
    }
    b.update(kw)
    return b


# --- KSIĘGA: odrodzenie rekordu przy prawdziwej publikacji ---

def test_typ_poza_lista_odradza_sie_z_cena_prawdziwej_publikacji():
    """Rekord spod `poza_lista_dnia` niesie cenę z cyklu, w którym NIKT typu
    nie widział. Gdy typ naprawdę wchodzi na listę, rekord rodzi się od nowa."""
    log: dict = {}
    R._dopisz_nowe(log, [_typ(kurs=1.23, p_model=0.88,
                              poza_publikacja="poza_lista_dnia")])
    rec = next(iter(log.values()))
    assert rec["poza_publikacja"] == "poza_lista_dnia"

    R._dopisz_nowe(log, [_typ(kurs=1.31, p_model=0.84)])
    rec = next(iter(log.values()))
    assert not rec.get("poza_publikacja")
    assert rec["kurs"] == 1.31 and rec["p_model"] == 0.84


def test_rynek_ukryty_tez_sie_odradza():
    log: dict = {}
    R._dopisz_nowe(log, [_typ(kurs=1.23, poza_publikacja="rynek_ukryty")])
    R._dopisz_nowe(log, [_typ(kurs=1.31)])
    rec = next(iter(log.values()))
    assert not rec.get("poza_publikacja") and rec["kurs"] == 1.31


def test_typ_pokazany_nie_degraduje_sie_gdy_wypadnie_z_listy():
    """Raz pokazany zostaje w bilansie z ceną z PIERWSZEJ publikacji — selekcja
    następnego cyklu może go wyprzeć ze strony, ale nie z historii."""
    log: dict = {}
    R._dopisz_nowe(log, [_typ(kurs=1.23)])
    R._dopisz_nowe(log, [_typ(kurs=1.31, poza_publikacja="poza_lista_dnia")])
    rec = next(iter(log.values()))
    assert not rec.get("poza_publikacja")
    assert rec["kurs"] == 1.23


def test_rekord_rozliczony_jest_zamrozony():
    log: dict = {}
    R._dopisz_nowe(log, [_typ(kurs=1.23, poza_publikacja="poza_lista_dnia")])
    rec = next(iter(log.values()))
    rec["wynik"] = "wygrany"
    R._dopisz_nowe(log, [_typ(kurs=1.31)])
    rec = next(iter(log.values()))
    assert rec["poza_publikacja"] == "poza_lista_dnia" and rec["kurs"] == 1.23


def test_kwarantanna_awansuje_po_staremu_bez_przepisania_ceny():
    """Odrodzenie dotyczy WYŁĄCZNIE powodów selekcji listy — awans
    z kwarantanny działa jak od 01.08: flaga schodzi, cena zostaje."""
    log: dict = {}
    R._dopisz_nowe(log, [_typ(kurs=1.23, poza_publikacja="kwarantanna_rynku")])
    R._dopisz_nowe(log, [_typ(kurs=1.31)])
    rec = next(iter(log.values()))
    assert not rec.get("poza_publikacja")
    assert rec["kurs"] == 1.23             # dataset kalibracji nietknięty


# --- REJESTR: trzyma tylko to, co weszło na listę ---

def _stub_supa(monkeypatch, magazyn: dict, odczyt_ok: bool = True):
    monkeypatch.setattr(
        B.supa, "get_key_ok",
        lambda k: ((magazyn.get(k), True) if odczyt_ok else (None, False)),
    )
    monkeypatch.setattr(B.supa, "get_key",
                        lambda k: magazyn.get(k) if odczyt_ok else None)
    monkeypatch.setattr(B.supa, "put_key",
                        lambda k, v: magazyn.__setitem__(k, v) or True)
    monkeypatch.setattr(B, "_dry_run", lambda: False)


def test_rejestr_przyciety_do_listy_dnia(monkeypatch):
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    na_liste, odciety = _typ(linia=6.5), _typ(linia=8.5)
    B.scal_z_publikacjami([na_liste, odciety], {1: {"id": 1}}, teraz=1000)
    assert len(magazyn[B.PUBLIKACJE_KLUCZ]) == 2

    n = B.przytnij_rejestr_do_listy([na_liste], teraz=1000)
    assert n == 1
    zostal = list(magazyn[B.PUBLIKACJE_KLUCZ].values())
    assert len(zostal) == 1 and zostal[0]["bet"]["linia"] == 6.5


def test_przyciecie_nie_tyka_typow_pokazanych_wczesniej(monkeypatch):
    """Typ z listy poprzedniego cyklu ma starszy `opublikowano_ts` — selekcja
    może go dziś wyprzeć ze strony, ale wpis (rentgen, zamrożona cena)
    zostaje do gwizdka."""
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    wczorajszy = _typ(linia=6.5)
    B.scal_z_publikacjami([wczorajszy], {1: {"id": 1}}, teraz=1000)
    B.przytnij_rejestr_do_listy([wczorajszy], teraz=1000)

    # cykl 2: nowy kandydat nie wchodzi na listę, wczorajszy też nie
    B.scal_z_publikacjami([_typ(linia=8.5)], {1: {"id": 1}}, teraz=2000)
    n = B.przytnij_rejestr_do_listy([], teraz=2000)
    assert n == 1
    zostal = list(magazyn[B.PUBLIKACJE_KLUCZ].values())
    assert len(zostal) == 1 and zostal[0]["bet"]["linia"] == 6.5


def test_przyciecie_nie_rusza_rejestru_przy_padnietym_odczycie(monkeypatch):
    magazyn: dict = {"publikacje_typy": {"stary": {"bet": {}}}}
    _stub_supa(monkeypatch, magazyn, odczyt_ok=False)
    assert B.przytnij_rejestr_do_listy([], teraz=1000) == 0
    assert magazyn["publikacje_typy"] == {"stary": {"bet": {}}}
