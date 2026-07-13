"""build_wc_fast.py orkiestruje cały cykl produkcyjny (statshub -> scoring ->
kupony -> Supabase) i nie miał ANI JEDNEGO testu jednostkowego — dokładnie ten
plik spowodował P0 tej sesji (rollback danych przy awarii statshub, patrz
test_push_supabase.py). Testy niżej pokrywają main()/_main_impl() bez sieci
(monkeypatch na granicy: statshub/rozliczanie), skupione na manifeście —
mechanizmie, który ma tę klasę błędów uniemożliwić na przyszłość."""
from __future__ import annotations

import json

from footstats.jobs import build_wc_fast


def _fake_wyniki():
    return {
        "kupony": [],
        "podsumowanie": {
            "opublikowane": 0, "rozliczone": 0, "trafione": 0, "roi_flat": 0.0,
        },
    }


def test_main_bez_meczow_pisze_manifest_tylko_z_rozliczania(tmp_path, monkeypatch):
    """Brak nadchodzących meczów -> main() kończy wcześnie, ale MUSI zostawić
    manifest mówiący, że value_bets/matches/players itp. NIE zostały w tym
    cyklu wygenerowane (inaczej push_supabase wypchnąłby stare dane z checkoutu
    — dokładnie ten P0 tej sesji)."""
    monkeypatch.setattr(build_wc_fast, "WEB_DATA_DIR", tmp_path)
    monkeypatch.setattr(build_wc_fast, "upcoming_wc_events", lambda: [])
    monkeypatch.setattr(build_wc_fast.rozliczanie, "rozlicz", lambda *a, **k: _fake_wyniki())

    build_wc_fast.main()

    manifest = json.loads((tmp_path / "_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["keys"]) == {"typy_wyniki", "kupony"}
    for stale_key in ("value_bets", "matches", "players", "odds_superbet", "legi_pool", "meta"):
        assert stale_key not in manifest["keys"]
    # a to co _rozlicz_i_zapisz faktycznie zapisał, jest na dysku
    assert (tmp_path / "typy_wyniki.json").exists()
    assert (tmp_path / "kupony.json").exists()


def test_main_statshub_pada_pisze_manifest_tylko_z_rozliczania(tmp_path, monkeypatch):
    """Ta sama gwarancja, gdy statshub.fetch_event_trends rzuci wyjątkiem
    (statshub chwilowo niedostępny) zamiast zwrócić pustą listę meczów."""
    monkeypatch.setattr(build_wc_fast, "WEB_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        build_wc_fast, "upcoming_wc_events",
        lambda: [{"id": 1, "homeTeamId": 1, "awayTeamId": 2}],
    )

    def _boom(_ids):
        raise RuntimeError("statshub timeout")

    monkeypatch.setattr(build_wc_fast.statshub, "fetch_event_trends", _boom)
    monkeypatch.setattr(build_wc_fast.rozliczanie, "rozlicz", lambda *a, **k: _fake_wyniki())

    build_wc_fast.main()

    manifest = json.loads((tmp_path / "_manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["keys"]) == {"typy_wyniki", "kupony"}
    assert "value_bets" not in manifest["keys"]


def test_main_manifest_pisany_nawet_gdy_main_impl_wybuchnie(tmp_path, monkeypatch):
    """finally w main() musi zapisać manifest (choćby pusty) NIEZALEŻNIE od
    tego, co pójdzie nie tak w _main_impl — inaczej ten konkretny cykl
    zostawiłby WCZEŚNIEJSZY manifest, myląc push_supabase co do tego, czy
    dane pochodzą z tego uruchomienia."""
    monkeypatch.setattr(build_wc_fast, "WEB_DATA_DIR", tmp_path)

    def _boom():
        raise RuntimeError("coś zupełnie nieoczekiwanego")

    monkeypatch.setattr(build_wc_fast, "upcoming_wc_events", _boom)

    try:
        build_wc_fast.main()
    except RuntimeError:
        pass
    else:
        raise AssertionError("main() powinien przepuścić wyjątek dalej")

    manifest = json.loads((tmp_path / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["keys"] == []
