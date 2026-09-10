# -*- coding: utf-8 -*-
"""ROUTER MAGAZYNÓW W `supa` (2026-09-10, etap 1 przeprowadzki).

Supabase był używany jako pamięć robocza pipeline'u: `typy_log`, `trend_lib`,
`styl_bank_liga`, `typy_log_kopia` i `hd_0..hd_9` czyta i pisze WYŁĄCZNIE
pipeline, a mimo to jechały przez sieć do 70 razy na dobę i dwukrotnie
wyczerpały limit transferu Free (25.08 i 04.09).

Przeprowadzka idzie przez podmianę TRANSPORTU wewnątrz `supa`, nie przez
przepisywanie 131 wywołań `get_key`/`put_key` w pipelinie. Ten plik pilnuje
trzech rzeczy, na których cała operacja stoi:

1. pusty `MAGAZYN` = zachowanie dokładnie jak przed zmianą,
2. klucz z wpisem NIE dotyka Supabase — ani przy odczycie, ani przy zapisie,
3. awaria magazynu to `(None, False)`, nigdy `(None, True)` — bo „pustka"
   pozwoliłaby wołającemu zapisać garść świeżych wpisów na miejsce historii.
"""
import pytest

from footstats import supa


class _Magazyn:
    """Zaślepka backendu: trzyma payloady w pamięci, liczy operacje."""

    def __init__(self, dane=None, ok=True):
        self.dane = dict(dane or {})
        self.ok = ok
        self.pobran = 0
        self.zapisow = 0

    def pobierz(self, key):
        self.pobran += 1
        if not self.ok:
            return None, False
        return self.dane.get(key), True

    def zapisz(self, key, payload):
        self.zapisow += 1
        if not self.ok:
            return False
        self.dane[key] = payload
        return True


@pytest.fixture(autouse=True)
def _czysty_stan(monkeypatch):
    """`MAGAZYN`, rejestr i pamięć procesu są globalne — testy ich nie dziedziczą."""
    monkeypatch.setattr(supa, "MAGAZYN", {})
    monkeypatch.setattr(supa, "_BACKENDY", {})
    monkeypatch.setattr(supa, "_ruch_poza", {})
    supa.wyczysc_pamiec()
    yield
    supa.wyczysc_pamiec()


@pytest.fixture
def _bez_supabase(monkeypatch):
    """Każde dotknięcie Supabase w teście to błąd — zaznaczmy to twardo."""
    def _stop():
        raise AssertionError("klucz z MAGAZYN nie może iść do Supabase")
    monkeypatch.setattr(supa, "_conn", _stop)


# ---------------------------------------------------------------------------
# 1. Bez konfiguracji nic się nie zmienia
# ---------------------------------------------------------------------------

def test_pusty_magazyn_idzie_do_supabase(monkeypatch):
    """Cofnięcie przeprowadzki = skasowanie wpisu. Musi wracać stare zachowanie."""
    monkeypatch.setattr(supa, "_conn", lambda: None)   # tryb lokalny
    assert supa.get_key_ok("typy_log") == (None, True)
    assert supa.put_key("typy_log", {"a": 1}) is False


# ---------------------------------------------------------------------------
# 2. Klucz z wpisem omija Supabase
# ---------------------------------------------------------------------------

def test_odczyt_idzie_do_magazynu(monkeypatch, _bez_supabase):
    mag = _Magazyn({"typy_log": {"x": 1}})
    supa.zarejestruj_backend("repo", mag)
    monkeypatch.setitem(supa.MAGAZYN, "typy_log", "repo")

    assert supa.get_key_ok("typy_log") == ({"x": 1}, True)
    assert mag.pobran == 1


def test_zapis_idzie_do_magazynu(monkeypatch, _bez_supabase):
    mag = _Magazyn()
    supa.zarejestruj_backend("repo", mag)
    monkeypatch.setitem(supa.MAGAZYN, "typy_log", "repo")

    assert supa.put_key("typy_log", {"x": 1}) is True
    assert mag.dane["typy_log"] == {"x": 1}


def test_inne_klucze_dalej_ida_do_supabase(monkeypatch):
    """Przeprowadzka jest PER KLUCZ — reszta nie może się przełączyć przy okazji."""
    mag = _Magazyn()
    supa.zarejestruj_backend("repo", mag)
    monkeypatch.setitem(supa.MAGAZYN, "typy_log", "repo")
    monkeypatch.setattr(supa, "_conn", lambda: None)

    assert supa.get_key_ok("players") == (None, True)
    assert mag.pobran == 0


def test_brak_klucza_w_magazynie_to_pustka_nie_awaria(monkeypatch, _bez_supabase):
    """Magazyn działa, klucza jeszcze nie ma — to `(None, True)`, jak w bazie."""
    mag = _Magazyn()
    supa.zarejestruj_backend("repo", mag)
    monkeypatch.setitem(supa.MAGAZYN, "typy_log", "repo")

    assert supa.get_key_ok("typy_log") == (None, True)


# ---------------------------------------------------------------------------
# 3. Awaria magazynu NIE MOŻE wyglądać jak pustka
# ---------------------------------------------------------------------------

def test_awaria_magazynu_to_none_false(monkeypatch, _bez_supabase):
    mag = _Magazyn({"typy_log": {"x": 1}}, ok=False)
    supa.zarejestruj_backend("repo", mag)
    monkeypatch.setitem(supa.MAGAZYN, "typy_log", "repo")

    assert supa.get_key_ok("typy_log") == (None, False)


def test_awaria_magazynu_nie_nadpisuje_historii(monkeypatch, _bez_supabase):
    """SEDNO CAŁEJ OPERACJI.

    `put_key_bezpiecznie` pomija zapis, gdy nie umie odczytać stanu sprzed
    zmian. Ta ochrona musi działać tak samo, gdy stan leży poza Supabase —
    inaczej jedno mrugnięcie magazynu zamieni tysiąc rozliczeń w garść
    świeżych wpisów.
    """
    mag = _Magazyn({"typy_log": {f"t{i}": i for i in range(5000)}}, ok=False)
    supa.zarejestruj_backend("repo", mag)
    monkeypatch.setitem(supa.MAGAZYN, "typy_log", "repo")

    assert supa.put_key_bezpiecznie("typy_log", {"t0": 0}) is False
    assert mag.zapisow == 0


def test_bezpiecznik_wagi_dziala_na_magazynie(monkeypatch, _bez_supabase):
    """Odczyt się udaje, ale nowy payload jest drastycznie lżejszy — nie zapisujemy."""
    mag = _Magazyn({"typy_log": {f"t{i}": {"duzy": "x" * 50} for i in range(500)}})
    supa.zarejestruj_backend("repo", mag)
    monkeypatch.setitem(supa.MAGAZYN, "typy_log", "repo")

    assert supa.put_key_bezpiecznie("typy_log", {"t0": {"duzy": "x"}}) is False
    assert mag.zapisow == 0


def test_niezarejestrowany_backend_nie_schodzi_na_supabase(monkeypatch, _bez_supabase):
    """Klucz przeniesiony, backendu brak: w bazie leży STARA wersja.

    Odczyt stamtąd cofnąłby produkt o kilka dni, a zapis zgubiłby wszystko,
    co przyszło po migracji. Awaria jest tu bezpieczniejsza niż cichy powrót.
    """
    monkeypatch.setitem(supa.MAGAZYN, "typy_log", "repo")   # nic nie zarejestrowane

    assert supa.get_key_ok("typy_log") == (None, False)
    assert supa.put_key("typy_log", {"x": 1}) is False


# ---------------------------------------------------------------------------
# 4. Pamięć procesu działa tak samo po obu stronach
# ---------------------------------------------------------------------------

def test_pamiec_procesu_obejmuje_magazyn(monkeypatch, _bez_supabase):
    """`get_key` czyta raz na proces — to ta sama oszczędność co przy Supabase."""
    mag = _Magazyn({"typy_log": {"x": 1}})
    supa.zarejestruj_backend("repo", mag)
    monkeypatch.setitem(supa.MAGAZYN, "typy_log", "repo")

    assert supa.get_key("typy_log") == {"x": 1}
    assert supa.get_key("typy_log") == {"x": 1}
    assert mag.pobran == 1, "drugi odczyt miał przyjść z pamięci procesu"


def test_zapis_odswieza_pamiec(monkeypatch, _bez_supabase):
    mag = _Magazyn({"typy_log": {"x": 1}})
    supa.zarejestruj_backend("repo", mag)
    monkeypatch.setitem(supa.MAGAZYN, "typy_log", "repo")

    supa.get_key("typy_log")
    supa.put_key("typy_log", {"x": 2})
    assert supa.get_key("typy_log") == {"x": 2}


def test_licznik_pokazuje_ruch_poza_supabase(monkeypatch, _bez_supabase):
    """Kryterium odbioru etapu 3 czyta się z tego licznika."""
    mag = _Magazyn({"typy_log": {"x": 1}})
    supa.zarejestruj_backend("repo", mag)
    monkeypatch.setitem(supa.MAGAZYN, "typy_log", "repo")

    supa.get_key_ok("typy_log")
    assert "poza Supabase" in supa.raport_poza_supabase()
