"""Terminarz pokazuje KAŻDY przeanalizowany mecz — i zna jego rozgrywki.

Regresja 2026-08-03 (zgłoszenie usera): „w Meczach i Drużynach brakuje
jutrzejszych kwalifikacji Ligi Mistrzów". Trzy niezależne przyczyny, każda
pilnowana tu osobno:

1. mecz bez ani jednego typu i bez propsów zawodniczych NIE trafiał do
   `matches` — czyli cała kolejka kwalifikacji pucharów znikała ze strony,
   mimo że model ją policzył (`domknij_terminarz`),
2. mecz wznowiony z księgi wracał z PUSTĄ nazwą rozgrywek, a zakładka Mecze
   filtruje domyślnie po „naszych ligach" — więc wracał tylko po to, żeby
   zostać odfiltrowanym (`scal_z_publikacjami(liga_by_mid=...)`),
3. rozjazd nazw statshub↔Superbet (patrz test_build_league) wycinał mecz już
   na parowaniu.
"""
import time

from footstats.jobs import build_wc_fast as B


def _stub_supa(monkeypatch, magazyn: dict):
    monkeypatch.setattr(B.supa, "get_key_ok", lambda k: (magazyn.get(k), True))
    monkeypatch.setattr(B.supa, "get_key", lambda k: magazyn.get(k))
    monkeypatch.setattr(B.supa, "put_key",
                        lambda k, v: magazyn.__setitem__(k, v) or True)
    monkeypatch.setattr(B, "_dry_run", lambda: False)


# --- 1. każdy mecz z zakresu ląduje w terminarzu ---

def _budowniczy(znane: set[int]):
    """Namiastka `_zapewnij_mecz`: zna tylko mecze z bieżącego kalendarza."""
    matches: dict[int, dict] = {}

    def rekord(mid: int):
        if mid not in znane:
            return None
        return matches.setdefault(mid, {"id": mid, "liga": "Liga Mistrzów",
                                        "okazje": []})
    return matches, rekord


def test_mecz_bez_typow_zostaje_w_terminarzu():
    """Sedno regresji: zero typów to nie powód, żeby ukryć mecz."""
    matches, rekord = _budowniczy({1, 2, 3})
    dolozone = B.domknij_terminarz(matches, {1, 2, 3}, rekord)
    assert dolozone == 3
    assert sorted(matches) == [1, 2, 3]
    # mecz bez pobranych kursów mówi wprost „zero propsów", zamiast milczeć
    assert matches[1]["propsy_superbet"] == 0


def test_liczba_propsow_z_pobranych_kursow_nie_jest_nadpisywana():
    matches, rekord = _budowniczy({1, 2})
    matches[1] = {"id": 1, "liga": "X", "okazje": [], "propsy_superbet": 14}
    B.domknij_terminarz(matches, {1, 2}, rekord, {1: 14, 2: 3})
    assert matches[1]["propsy_superbet"] == 14   # ustawione w pętli zawodniczej
    assert matches[2]["propsy_superbet"] == 3    # dołożone z cache kursów


def test_mecz_spoza_kalendarza_nie_wchodzi_na_sile():
    """Zakres bierzemy z terminarza; id bez eventu to błąd danych, nie mecz."""
    matches, rekord = _budowniczy({1})
    assert B.domknij_terminarz(matches, {1, 999}, rekord) == 1
    assert 999 not in matches


def test_istniejacy_rekord_nie_jest_deptany():
    matches, rekord = _budowniczy({1})
    matches[1] = {"id": 1, "liga": "Liga Europy", "okazje": [7]}
    assert B.domknij_terminarz(matches, {1}, rekord) == 0
    assert matches[1]["okazje"] == [7] and matches[1]["liga"] == "Liga Europy"


# --- 2. wznowiony mecz odzyskuje nazwę rozgrywek ---

def _bet(mecz_id=1, kickoff_ts=None):
    return {
        "mecz_id": mecz_id, "podmiot": "Fenerbahçe", "rynek_kod": "team_goals",
        "linia": 1.5, "strona": "powyzej", "kurs": 1.73,
        "kickoff_ts": kickoff_ts or (int(time.time()) + 7200),
        "mecz": "Fenerbahçe – SK Sturm Graz",
    }


def test_wznowiony_mecz_dostaje_lige_z_biezacego_terminarza(monkeypatch):
    """Typ opublikowany PRZED stemplem ligi (03.08) wraca bez rozgrywek —
    a pusta liga wypada z filtra „tylko nasze ligi" na zakładce Mecze."""
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    # cykl 1: rekord meczu z tamtej epoki, bez ligi
    B.scal_z_publikacjami([_bet()], {1: {"id": 1, "liga": ""}})

    # cykl 2: mecz nie policzył się na świeżo, ale JEST w terminarzu cyklu
    mecze2: dict = {}
    out, wzn = B.scal_z_publikacjami(
        [], mecze2,
        liga_by_mid={1: {"liga": "Liga Mistrzów", "sezon": "2026/27",
                         "kolejka": "qualification round 3"}},
    )
    assert wzn == 1 and out[0]["wznowiony"] is True
    assert mecze2[1]["liga"] == "Liga Mistrzów"
    assert mecze2[1]["kolejka"] == "qualification round 3"


def test_wznowienie_z_ksiegi_tez_dostaje_lige(monkeypatch):
    """Druga, niezależna ścieżka wznowienia (księga rozliczeń) — to ona
    zbudowała 17 kadłubków bez ligi zmierzonych na produkcji 03.08."""
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    kickoff = int(time.time()) + 7200
    log = {"k1": {
        "mecz_id": 1, "mecz": "Fenerbahçe – SK Sturm Graz",
        "podmiot": "SK Sturm Graz", "podmiot_id": 5, "rynek_kod": "team_goals",
        "linia": 1.5, "strona": "powyzej", "kurs": 1.73, "p_model": 0.62,
        "kickoff_ts": kickoff, "wynik": None,
    }}
    mecze: dict = {}
    out, _ = B.scal_z_publikacjami(
        [], mecze, typy_log=log,
        liga_by_mid={1: {"liga": "Liga Mistrzów", "sezon": "2026/27",
                         "kolejka": "qualification round 3"}},
    )
    assert len(out) == 1
    assert mecze[1]["liga"] == "Liga Mistrzów"


def test_liga_z_ksiegi_ma_pierwszenstwo_przed_terminarzem(monkeypatch):
    """Stempel przy publikacji jest prawdą o TAMTEJ chwili — terminarz tylko
    uzupełnia pustkę, nigdy nie poprawia zapisanej wartości."""
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    B.scal_z_publikacjami([_bet()], {1: {"id": 1, "liga": "Liga Europy"}})
    mecze2: dict = {}
    B.scal_z_publikacjami([], mecze2,
                          liga_by_mid={1: {"liga": "Liga Mistrzów"}})
    assert mecze2[1]["liga"] == "Liga Europy"


def test_brak_terminarza_nie_wywraca_wznowienia(monkeypatch):
    """Mecz spoza bieżącego zakresu wraca bez etykiety — ale wraca."""
    magazyn: dict = {}
    _stub_supa(monkeypatch, magazyn)
    B.scal_z_publikacjami([_bet()], {1: {"id": 1, "liga": ""}})
    mecze2: dict = {}
    out, wzn = B.scal_z_publikacjami([], mecze2, liga_by_mid={})
    assert wzn == 1 and mecze2[1]["liga"] == ""
