# -*- coding: utf-8 -*-
"""RATUNEK DANYCH Z ODCIĘTEGO SUPABASE (etap 0 planu, 2026-09-10).

Po co to istnieje
-----------------
Gdy Supabase odetnie projekt za przekroczenie limitu transferu, REST oddaje 402
na KAŻDE zapytanie z kluczem — i odczyty, i zapisy. Ale restrykcja dotyczy
PostgREST, a połączenie SQL idzie inną drogą i MOŻE działać mimo blokady.
Ten skrypt to sprawdza i, jeśli droga jest otwarta, wyciąga dane na dysk.

⚑ DLACZEGO TO JEST PILNE. Jedyna kopia zapasowa księgi typów powstaje pod
kluczem `typy_log_kopia` (`rozliczanie.py:1132`) — czyli w TYM SAMYM Supabase.
Poza nim nie ma nic: ani w repo, ani w artefaktach Actions, ani na dysku.
Cała historia produktu (~9300 rozliczeń, dataset kalibracji i treningu) wisi
na jednym koncie, do którego przy odcięciu nie ma dostępu.

Jak uruchomić
-------------
1. Panel Supabase → Connect → Connection string → Transaction pooler.
   Skopiuj gotowy URI i wstaw w miejsce hasła swoje hasło bazy.
2. Podaj go przez ZMIENNĄ ŚRODOWISKOWĄ, nie argumentem — argument zostaje
   w historii powłoki:

       $env:SUPABASE_DB_URL = "postgresql://postgres.REF:HASLO@aws-0-REGION.pooler.supabase.com:6543/postgres"
       python pipeline/scripts/ratuj_baze.py              # sam test + inwentarz
       python pipeline/scripts/ratuj_baze.py --eksport    # test + zapis na dysk

Wymaga `psycopg` (NIE ma go w requirements i nie ma go tam być — cykl instaluje
zależności co przebieg i nie potrzebuje sterownika SQL):

       pip install "psycopg[binary]"
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ⚑ KOPIA NIE MOŻE WYLĄDOWAĆ W DRZEWIE REPO. `tipx-tipx/footstats` jest
# PUBLICZNE — dump księgi w repo oznaczałby opublikowanie całej kuchni
# produktu (typy, wyniki, wagi modelu). Domyślny katalog leży OBOK repo,
# a skrypt odmawia zapisu wewnątrz niego.
REPO = Path(__file__).resolve().parents[2]
DOMYSLNY_CEL = REPO.parent / "footstats-kopia"

# klucze, bez których produktu nie da się odtworzyć — te lecą zawsze
KRYTYCZNE = ("typy_log", "typy_log_kopia", "trend_lib", "styl_bank_liga",
             "kupony_log", "przewaga_historia", "model_wagi")

# sufiks kawałka (`supa.MARKER_CZESCI` to co innego — to marker W payloadzie)
supa_marker_czesci = "__cz"


# Druga droga podania URI: plik OBOK repo (nigdy w nim — repo jest publiczne).
# Wygodniejsza, bo hasło nie przechodzi ani przez historię powłoki, ani przez
# rozmowę z asystentem: wklejasz raz do pliku i kasujesz po eksporcie.
PLIK_DSN = REPO.parent / "db-url.txt"


def _polaczenie():
    dsn = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not dsn and PLIK_DSN.exists():
        dsn = PLIK_DSN.read_text(encoding="utf-8").strip()
        print(f"URI wzięty z {PLIK_DSN}")
    if not dsn:
        sys.exit(f"Brak URI. Ustaw SUPABASE_DB_URL albo wklej go do {PLIK_DSN} "
                 "(patrz nagłówek pliku).")
    try:
        import psycopg
    except ImportError:
        sys.exit('Brak sterownika. Zainstaluj: pip install "psycopg[binary]"')
    print("Łączę przez pooler (omijamy PostgREST, na którym siedzi blokada)…",
          flush=True)
    return psycopg.connect(dsn, connect_timeout=20)


def inwentarz(conn) -> list[tuple[str, int]]:
    """Co leży w app_data i ile waży — bez pobierania zawartości."""
    with conn.cursor() as cur:
        cur.execute(
            "select key, pg_column_size(payload) as bajty, "
            "       length(payload::text) as znaki "
            "from app_data order by bajty desc"
        )
        wiersze = cur.fetchall()
    print(f"\nKluczy w app_data: {len(wiersze)}\n")
    print(f"{'klucz':<34}{'w bazie':>12}{'jako JSON':>14}")
    print("-" * 60)
    suma_b = suma_j = 0
    for key, bajty, znaki in wiersze:
        suma_b += bajty or 0
        suma_j += znaki or 0
        print(f"{key:<34}{(bajty or 0) / 1e6:>10.2f} MB{(znaki or 0) / 1e6:>11.2f} MB")
    print("-" * 60)
    print(f"{'RAZEM':<34}{suma_b / 1e6:>10.2f} MB{suma_j / 1e6:>11.2f} MB\n")
    return [(k, b or 0) for k, b, _ in wiersze]


_NIEPELNY = object()


def _scal(conn, key: str, payload):
    """Klucz ciężki leży w bazie w kawałkach — pod główną nazwą jest sam marker.

    ⚑ Bez tego kopia `typy_log` czy `trend_lib` to plik z jedną liczbą.
    Sklejamy TĄ SAMĄ funkcją, której używa produkcja (`supa.sklej_czesci`),
    żeby kopia była bit w bit tym, co czyta pipeline.

    Brak choćby jednej części to `_NIEPELNY`, nigdy połowa danych: kopia
    z dziurą jest gorsza niż jej brak, bo wygląda na dobrą.
    """
    sys.path.insert(0, str(REPO / "pipeline"))
    from footstats import supa

    n = supa.ile_czesci(payload)
    if n is None:
        return payload
    with conn.cursor() as cur:
        cur.execute("select key, payload from app_data where key like %s",
                    (f"{key}\\_\\_cz%",))
        mapa = dict(cur.fetchall())
    czesci = [mapa.get(supa.klucz_czesci(key, i)) for i in range(n)]
    braki = [i for i, cz in enumerate(czesci) if cz is None]
    if braki:
        print(f"    marker mówi o {n} częściach, brakuje {len(braki)}: {braki[:5]}")
        return _NIEPELNY
    return supa.sklej_czesci(czesci)


def eksport(conn, cel: Path, klucze: list[str]) -> int:
    cel = cel.resolve()
    if REPO == cel or REPO in cel.parents:
        sys.exit(f"ODMOWA: {cel} leży w drzewie repo, a repo jest PUBLICZNE. "
                 "Wybierz katalog poza nim (--cel).")
    cel.mkdir(parents=True, exist_ok=True)
    stempel = datetime.now().strftime("%Y%m%d-%H%M")
    katalog = cel / f"app_data-{stempel}"
    katalog.mkdir(exist_ok=True)

    print(f"Zapisuję do {katalog}\n", flush=True)
    razem = 0
    for key in klucze:
        with conn.cursor() as cur:
            cur.execute("select payload from app_data where key = %s", (key,))
            wiersz = cur.fetchone()
        if wiersz is None:
            print(f"  {key:<34} BRAK KLUCZA")
            continue

        payload = _scal(conn, key, wiersz[0])
        if payload is _NIEPELNY:
            print(f"  {key:<34} ⚑ BRAKUJE CZĘŚCI — pomijam, to nie byłaby kopia")
            continue
        tekst = json.dumps(payload, ensure_ascii=False)
        plik = katalog / f"{key}.json.gz"
        with gzip.open(plik, "wt", encoding="utf-8") as f:
            f.write(tekst)
        waga = plik.stat().st_size
        razem += waga
        ile = len(wiersz[0]) if isinstance(wiersz[0], (dict, list)) else "—"
        print(f"  {key:<34}{len(tekst) / 1e6:>8.2f} MB → "
              f"{waga / 1e6:.2f} MB gz   ({ile} wpisów)")

    # kontrola: odczytujemy z powrotem to, co zapisaliśmy. Kopia, której nikt
    # nigdy nie otworzył, nie jest kopią.
    print("\nKontrola odczytu…", flush=True)
    bledy = 0
    for plik in sorted(katalog.glob("*.json.gz")):
        try:
            with gzip.open(plik, "rt", encoding="utf-8") as f:
                json.load(f)
        except Exception as ex:  # noqa: BLE001
            print(f"  ⚑ {plik.name}: NIE DA SIĘ ODCZYTAĆ — {ex!r}")
            bledy += 1
    if bledy:
        print(f"\n⚑⚑ {bledy} plików nie przeszło kontroli. To NIE jest kopia.")
        return 1
    print(f"  wszystkie {len(list(katalog.glob('*.json.gz')))} plików czytelne")
    print(f"\nGOTOWE: {razem / 1e6:.1f} MB w {katalog}")
    return 0


def main() -> int:
    cel = DOMYSLNY_CEL
    if "--cel" in sys.argv:
        cel = Path(sys.argv[sys.argv.index("--cel") + 1])

    try:
        conn = _polaczenie()
    except Exception as ex:  # noqa: BLE001
        print(f"\n⚑ POŁĄCZENIE NIE PRZESZŁO: {ex!r}\n", file=sys.stderr)
        print("Co to znaczy:\n"
              "  „Tenant or user not found”  → zły region w hoście albo zły REF;\n"
              "                                weź gotowy URI z panelu (Connect).\n"
              "  „password authentication”   → złe hasło bazy.\n"
              "  timeout / odmowa            → blokada obejmuje też SQL;\n"
              "                                zostaje transfer organizacji albo 30.09.",
              file=sys.stderr)
        return 2

    with conn:
        print("POŁĄCZENIE DZIAŁA — blokada 402 dotyczy tylko REST.\n")
        spis = inwentarz(conn)
        if "--eksport" not in sys.argv:
            print("To był sam rentgen. Eksport: dodaj --eksport")
            return 0
        # krytyczne najpierw, potem cała reszta wg wagi. Części (`__czNN`)
        # pomijamy — dociąga je `_scal` przy kluczu głównym.
        wszystkie = [k for k, _ in spis if supa_marker_czesci not in k]
        klucze = [k for k in KRYTYCZNE if k in set(wszystkie)]
        klucze += [k for k in wszystkie if k not in klucze]
        return eksport(conn, cel, klucze)


if __name__ == "__main__":
    raise SystemExit(main())
