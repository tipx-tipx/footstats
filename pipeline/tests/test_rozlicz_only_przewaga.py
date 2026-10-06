"""Lekki job rozliczania nie gubi pomiaru „czy bijemy cenę” (2026-10-06).

Do 06.10 pomiar przewagi liczył tylko duży cykl, a `rozlicz_only` co 20 minut
nadpisywał `typy_wyniki` bez niego — sekcja „Model a kurs” w Kontroli przez
większość doby pisała „brak pomiaru w ostatnim cyklu”.
"""

from footstats.jobs import rozliczanie


def _uruchom(monkeypatch, przewaga_rynkow):
    from footstats.jobs import rozlicz_only

    monkeypatch.setenv("SUPABASE_URL", "https://test.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test")
    monkeypatch.setattr(rozliczanie, "rozlicz", lambda *a, **kw: {
        "kupony": [],
        "podsumowanie": {"rozliczone": 0, "opublikowane": 0, "trafione": 0,
                         "roi_flat": 0.0},
    })
    monkeypatch.setattr(rozliczanie, "szansa_pokazywana", lambda *a, **kw: {})
    monkeypatch.setattr(rozlicz_only.supa, "get_key", lambda key: {})
    monkeypatch.setattr(rozliczanie, "przewaga_rynkow", przewaga_rynkow)
    monkeypatch.setattr(rozliczanie, "przewaga_pasm", lambda *a, **kw: {
        "1.35-1.6": {"n": 300, "od": 1.35, "do": 1.6, "hit": 0.6, "przewaga": -0.003},
    })
    zapisane: dict[str, object] = {}

    def _put(key, payload):
        zapisane[key] = payload
        return True

    monkeypatch.setattr(rozlicz_only.supa, "put_key", _put)
    rozlicz_only.main()
    return zapisane


def test_lekki_job_zapisuje_przewage_w_typy_wyniki(monkeypatch):
    segment = {"n": 120, "se": 2.1, "strona": "ponizej", "przewaga": 0.01,
               "rynek_kod": "team_cards"}
    zapisane = _uruchom(monkeypatch, lambda *a, **kw: {"team_cards|ponizej": segment})
    wyniki = zapisane["typy_wyniki"]
    assert wyniki["przewaga_rynkow"] == {"team_cards|ponizej": segment}
    assert "1.35-1.6" in wyniki["przewaga_pasm"]


def test_awaria_pomiaru_nie_blokuje_zapisu(monkeypatch):
    def _pada(*a, **kw):
        raise RuntimeError("księga nieczytelna")

    zapisane = _uruchom(monkeypatch, _pada)
    assert "typy_wyniki" in zapisane
    assert "kupony" in zapisane
    assert "przewaga_rynkow" not in zapisane["typy_wyniki"]
