# -*- coding: utf-8 -*-
"""PRODUKCYJNA LISTA PRZENIESIONYCH KLUCZY (`supa.MAGAZYN`).

Reszta testów dostaje `MAGAZYN` pusty (patrz `conftest._magazyny_domyslnie_
wylaczone`), żeby mechanika Supabase nie zależała od tego, co akurat
przeprowadziliśmy. Ten plik jest wyjątkiem: patrzy na PRAWDZIWĄ listę
i pilnuje, żeby nie znalazło się na niej nic, co czyta front.
"""
import json
import re
from pathlib import Path

import pytest

from footstats import supa

REPO = Path(__file__).resolve().parents[2]
DATA_TS = REPO / "web" / "src" / "lib" / "data.ts"

pytestmark = pytest.mark.magazyn_produkcyjny


def _klucze_frontu() -> set[str]:
    """Klucze, po które front chodzi do Supabase — z `data.ts`, nie z pamięci."""
    tekst = DATA_TS.read_text(encoding="utf-8")
    bundle = re.search(r"const BUNDLE_KEYS = \[(.*?)\] as const", tekst, re.S)
    klucze = set(re.findall(r'"([a-z_0-9]+)"', bundle.group(1)))
    # trzy leniwe, pobierane osobno przez `fetchKlucz`
    klucze |= set(re.findall(r'fetchKlucz<[^>]+>\(\s*"([a-z_0-9]+)"', tekst))
    return klucze


def test_zaden_przeniesiony_klucz_nie_jest_czytany_przez_front():
    """⚑ SEDNO BEZPIECZEŃSTWA PRZEPROWADZKI.

    Front czyta Supabase anonimowym kluczem i NIE MA dostępu do prywatnego
    repo. Przeniesienie klucza, po który chodzi strona, oznacza, że strona
    cicho spada na lokalne dane demo — awarię widać dopiero po tym, jak
    klient zobaczy nieprawdziwe typy.
    """
    kolizje = set(supa.MAGAZYN) & _klucze_frontu()
    assert not kolizje, (
        f"klucze {sorted(kolizje)} czyta FRONT — nie wolno ich przenosić "
        "poza Supabase, bo strona pokaże dane demo"
    )


def test_front_ma_komplet_swoich_kluczy():
    """Kontrola samej metody: gdyby `data.ts` zmienił format, test wyżej
    przestałby cokolwiek sprawdzać, milcząco przechodząc."""
    klucze = _klucze_frontu()
    assert {"value_bets", "matches", "kupony", "players",
            "odrzucenia", "typy_wyniki"} <= klucze, (
        f"nie umiem odczytać kluczy frontu z data.ts (znalazłem: {sorted(klucze)})"
    )


def test_przeniesione_klucze_maja_znany_backend():
    for klucz, backend in supa.MAGAZYN.items():
        assert backend in supa._AUTO_MAGAZYNY, (
            f"'{klucz}' wskazuje na magazyn '{backend}', którego nikt nie "
            "podepnie automatycznie — job padnie na braku backendu"
        )


def test_magazyn_druzyn_przeniesiony_w_calosci():
    """`hd_*` to jeden magazyn w dziesięciu szardach — połowa tu, połowa tam
    znaczyłaby profil drużyny sklejony z dwóch epok."""
    szardy = {f"hd_{i}" for i in range(10)}
    w_magazynie = szardy & set(supa.MAGAZYN)
    assert w_magazynie in (set(), szardy), (
        f"przeniesiono tylko część szardów: {sorted(w_magazynie)}"
    )
