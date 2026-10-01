"""Lekkie klucze pod nową stronę (redesign, etap 7B, 2026-10-01).

Nowa strona czyta dokładnie to, co pokazuje – zamiast ciągnąć ciężkie klucze
i wycinać z nich u siebie (limit transferu Supabase, patrz nota przy
`push_supabase.KOSZYKI_PLAYERS`):

* `matches` dostaje numery drużyn i rozgrywek (herby z Sofascore dla KAŻDEJ
  drużyny, nie tylko z mapy w kodzie strony) i podsumowanie oferty meczu
  (ilu zawodników ma kurs, ile rynków, ile linii) – lista meczów nie musi
  pobierać całej siatki kursów, żeby to policzyć;
* `kursy_mNN` – kursy na zawodników per mecz, OSOBNO Superbet i Betclic.
  `odds_superbet` trzyma jedną liczbę (wyższą z dwóch) bez nazwy bukmachera,
  więc strona meczu podpisywała cenę Betclica jako Superbet;
* `zaw_kNN` + `zaw_indeks` – strona zawodnika: jeden koszyk po numerze
  zawodnika (10 ostatnich meczów na rynek + jego kursy) zamiast dwóch koszyków
  całych drużyn z 20 meczami, i lekki indeks do wyszukiwarki.

Same funkcje bez sieci i bez stanu cyklu – liczone z tego, co cykl i tak ma.
"""

from __future__ import annotations

from typing import Callable

KOSZYKI_KURSOW = 32
KOSZYKI_ZAWODNIKOW = 64
# okno historii na stronie zawodnika (kratki „X z 10”, dziennik mecz po meczu)
OKNO_ZAWODNIKA = 10


def _f(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def uzupelnij_mecze(mecze: dict, ev_by_id: dict, odds_grid: dict) -> None:
    """Dopisuje do rekordów `matches` numery drużyn/rozgrywek i podsumowanie
    oferty. Zmienia `mecze` w miejscu; brak danych = brak pola (strona ma
    wtedy zapas), nigdy wymyślona wartość."""
    for mid, rec in mecze.items():
        ev = ev_by_id.get(mid) or ev_by_id.get(rec.get("id")) or {}
        for pole, zrodlo in (("gospodarz_id", "homeTeamId"),
                             ("gosc_id", "awayTeamId"),
                             ("turniej_id", "uniqueTournamentId")):
            v = ev.get(zrodlo)
            if v is None and zrodlo == "uniqueTournamentId":
                v = (ev.get("tournament") or {}).get("uniqueTournamentId")
            if v:
                rec[pole] = int(v)
        siatka = odds_grid.get(mid) or odds_grid.get(str(mid)) or {}
        rynki: set = set()
        linie = 0
        for rynki_z in siatka.values():
            for mk, l in (rynki_z or {}).items():
                rynki.add(mk)
                linie += len(l or {})
        rec["oferta"] = {"zawodnicy": len(siatka), "rynki": len(rynki),
                         "linie": linie}


def siatka_dwoch_kursow(
    odds_grid: dict,
    zrodla_grid: dict,
    nazwy: dict,
    sb_cache: dict,
    bc_cache: dict,
    znajdz_sb: Callable[[dict, str], dict],
    znajdz_bc: Callable[[dict, str], dict],
) -> dict:
    """{mecz_id: {zawodnik_id: {rynek: {linia: [superbet, betclic]}}}} – kurs
    „powyżej” u każdego bukmachera osobno (None = nie kwotuje tej linii).

    Szkielet (które linie) bierzemy z `odds_grid`, czyli dokładnie z tego, co
    cykl pokazał. Ceny – z pełnych ofert obu bukmacherów, tą samą funkcją
    wyszukiwania zawodnika co scoring. Gdy oferty zawodnika nie da się
    odnaleźć (np. inna pisownia w odkrywaniu), zostaje cena z siatki u tego
    bukmachera, którego wskazuje `zrodla_grid` – wiadomo przynajmniej, czyja
    jest, a drugi kurs zostaje pusty zamiast zgadniętego.
    """
    wynik: dict = {}
    for mid, gracze in (odds_grid or {}).items():
        sb_gracze = ((sb_cache or {}).get(mid) or {}).get("players") or {}
        bc_gracze = ((bc_cache or {}).get(mid) or {}).get("players") or {}
        for pid, rynki in (gracze or {}).items():
            nazwa = nazwy.get(pid) or nazwy.get(str(pid)) or ""
            sb_z = (znajdz_sb(sb_gracze, nazwa) if sb_gracze and nazwa else {}) or {}
            bc_z = (znajdz_bc(bc_gracze, nazwa) if bc_gracze and nazwa else {}) or {}
            obce = ((zrodla_grid or {}).get(mid) or {}).get(pid) or {}
            for mk, linie in (rynki or {}).items():
                sb_l = {_f(l): (v or {}).get("over") for l, v in (sb_z.get(mk) or {}).items()}
                bc_l = {_f(l): (v or {}).get("over") for l, v in (bc_z.get(mk) or {}).items()}
                kto = obce.get(mk) or {}
                cele: dict = {}
                for l, najlepszy in (linie or {}).items():
                    sb = sb_l.get(_f(l))
                    bc = bc_l.get(_f(l))
                    if sb is None and bc is None:
                        # oferty nie znaleźliśmy – cena z siatki u jej właściciela
                        if kto.get(l) == "Betclic":
                            bc = najlepszy
                        else:
                            sb = najlepszy
                    cele[str(l)] = [round(float(sb), 2) if sb else None,
                                    round(float(bc), 2) if bc else None]
                if cele:
                    wynik.setdefault(int(mid), {}).setdefault(int(pid), {})[mk] = cele
    return wynik


def klucze_kursow_meczow(kursy_dwa: dict) -> dict:
    """`kursy_m00`..`kursy_m31` – mecz w koszyku `id % 32`. Wszystkie koszyki
    zawsze (także puste), żeby po meczu nie zostawała stara oferta."""
    koszyki: list[dict] = [{} for _ in range(KOSZYKI_KURSOW)]
    for mid, gracze in (kursy_dwa or {}).items():
        koszyki[int(mid) % KOSZYKI_KURSOW][str(mid)] = gracze
    return {f"kursy_m{i:02d}": k for i, k in enumerate(koszyki)}


def _forma_okna(forma: dict) -> dict:
    out = {}
    for mk, f in (forma or {}).items():
        f = f or {}
        out[mk] = {k: (v[:OKNO_ZAWODNIKA] if isinstance(v, list) else v)
                   for k, v in f.items()}
    return out


def klucze_zawodnikow(players: list, kursy_dwa: dict, value_bets: list,
                      mecze: list) -> dict:
    """`zaw_k00`..`zaw_k63` (zawodnik w koszyku `id % 64`) i `zaw_indeks`.

    Tylko zawodnicy, którzy mają kurs albo typ – reszta i tak nie ma strony.
    Najbliższy mecz zawodnika: ten z kursem/typem, który zaczyna się
    najwcześniej.
    """
    # z pliku JSON klucze są tekstem – w pamięci cyklu liczbami
    kursy_dwa = {int(m): {int(p): r for p, r in (g or {}).items()}
                 for m, g in (kursy_dwa or {}).items()}
    start = {int(m["id"]): int(m.get("kickoff_ts") or 0)
             for m in mecze or [] if m.get("id") is not None}
    mecz_zaw: dict[int, int] = {}

    def _dopisz(pid, mid):
        if pid is None or mid is None:
            return
        pid, mid = int(pid), int(mid)
        stary = mecz_zaw.get(pid)
        if stary is None or start.get(mid, 1 << 62) < start.get(stary, 1 << 62):
            mecz_zaw[pid] = mid

    for mid, gracze in (kursy_dwa or {}).items():
        for pid in gracze or {}:
            _dopisz(pid, mid)
    for b in value_bets or []:
        if (b.get("podmiot_typ") or "zawodnik") == "zawodnik" and not b.get("sugestia"):
            _dopisz(b.get("podmiot_id"), b.get("mecz_id"))

    koszyki: list[list] = [[] for _ in range(KOSZYKI_ZAWODNIKOW)]
    indeks = []
    for z in players or []:
        pid = z.get("id")
        if pid is None or int(pid) not in mecz_zaw:
            continue
        pid = int(pid)
        mid = mecz_zaw[pid]
        rec = {
            "id": pid, "nazwa": z.get("nazwa"), "pozycja": z.get("pozycja"),
            "druzyna": z.get("druzyna"), "xi": bool(z.get("xi")),
            "minuty_lacznie": z.get("minuty_lacznie"), "mecz_id": mid,
            "forma": _forma_okna(z.get("forma")),
            "kursy": ((kursy_dwa or {}).get(mid) or {}).get(pid) or {},
        }
        koszyki[pid % KOSZYKI_ZAWODNIKOW].append(rec)
        indeks.append({"id": pid, "n": z.get("nazwa"), "d": z.get("druzyna"),
                       "m": mid})
    out = {f"zaw_k{i:02d}": k for i, k in enumerate(koszyki)}
    out["zaw_indeks"] = indeks
    return out
