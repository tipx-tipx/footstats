"""Strażnik: każdy powód odrzucenia z pipeline'u ma etykietę na froncie.

`web/src/lib/odrzucenia.ts` sam ostrzega: brakujący klucz nie rzuca błędem,
tylko drukuje surową nazwę zmiennej w polskim zdaniu — i tak przez tygodnie
wypisywały się „wartosc ujemna przy ostroznym" i „za malo minut". Nowy powód
w `_odrzuc(...)` bez etykiety ma paść TU, nie u klienta.
"""

import re
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1] / "footstats" / "jobs" / "build_wc_fast.py"
FRONT = Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "odrzucenia.ts"


def _powody_pipeline() -> set[str]:
    zrodlo = PIPELINE.read_text(encoding="utf-8")
    # `_odrzuc(mid, tr, "powod"` i `_odrzuc_druzyne(mid, tt, "powod"`
    z_wywolan = set(re.findall(r'_odrzuc(?:_druzyne)?\(\s*\w+,\s*\w+,\s*"([a-z_]+)"', zrodlo))
    # domknięcie rejestru: `"powod": "tylko_w_puli"`
    z_domkniecia = set(re.findall(r'"powod":\s*"([a-z_]+)"', zrodlo))
    # bramy wyświetlania dopisywane do rejestru dynamicznie — klucze słownika
    blok = zrodlo.split("OPISY_ZDJECIA_PL = {", 1)[1].split("}", 1)[0]
    z_bram = set(re.findall(r'^\s*"([a-z_]+)":', blok, flags=re.M))
    assert z_bram, "słownik OPISY_ZDJECIA_PL pusty albo przeniesiony"
    return z_wywolan | z_domkniecia | z_bram


def _etykiety_frontu() -> set[str]:
    zrodlo = FRONT.read_text(encoding="utf-8")
    blok = zrodlo.split("POWOD_LABEL", 1)[1].split("};", 1)[0]
    return set(re.findall(r"^\s*([a-z_]+):\s*\n?\s*\"", blok, flags=re.M))


def test_kazdy_powod_pipeline_ma_etykiete_na_froncie():
    powody = _powody_pipeline()
    assert "rzadko_w_pierwszym_skladzie" in powody
    etykiety = _etykiety_frontu()
    # powody z widełek drużynowych front zna pod tymi samymi kodami; powody
    # doklejane dynamicznie (kwarantanna_*) mają własne klucze w słowniku
    brak = sorted(powody - etykiety)
    assert not brak, f"powody bez etykiety na froncie: {brak}"
