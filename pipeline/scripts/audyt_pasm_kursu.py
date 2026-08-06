# -*- coding: utf-8 -*-
"""GDZIE DOKŁADNIE TRACIMY — kurs, rynek, strona, deklarowana szansa.

Pytanie postawione 2026-08-06, po pomiarze pasm kursu:

    kurs 1,00–2,00   n=498   ROI −6,6% ± 3,1%   <- jedyny ISTOTNY wynik
    kurs 2,00–3,00   n=177   ROI +0,8% ± 8,9%
    kurs 3,00–6,00   n= 54   ROI +15,6% ± 21,4%

Tanie typy to 68% wszystkiego, co publikujemy, i jako jedyne tracą w sposób
niedający się zwalić na szum. Ale „tanie typy tracą" to jeszcze nie diagnoza:

  * jeśli tracą we WSZYSTKICH rynkach — winny jest próg kursu i lekarstwem
    jest podniesienie podłogi,
  * jeśli tracą w JEDNYM rynku — próg kursu jest niewinny, a problemem jest
    ten rynek (albo jego jedna strona),
  * jeśli tracą tam, gdzie deklarujemy NAJWYŻSZE szanse — to nie kurs ani
    rynek, tylko przeszacowanie modelu w górnym końcu skali; wtedy lekarstwem
    jest kalibracja, a ruszanie progu kursu leczyłoby objaw.

Te trzy odpowiedzi prowadzą do trzech RÓŻNYCH decyzji, więc nie wolno ich
mylić. Skrypt liczy wszystkie trzy przekroje na tych samych rozliczeniach.

UWAGA NA WIELE PORÓWNAŃ NARAZ. Przy kilkudziesięciu wycinkach kilka wyjdzie
„istotnych" czystym przypadkiem — dlatego każdy wiersz niesie własny błąd
standardowy, a skrypt drukuje na końcu, ile wycinków w ogóle sprawdził.
Wycinek poniżej MIN_N nie jest pokazywany jako wynik, tylko sumowany
w wierszu „za mała próba" — inaczej ROI +80% na czterech typach wyglądałoby
jak odkrycie.

    cd pipeline
    PYTHONUTF8=1 python scripts/audyt_pasm_kursu.py

CZYTA TYLKO — nie zapisuje nic.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Poniżej tylu rozliczeń wycinek nie jest wynikiem, tylko ciekawostką.
MIN_N = 25

PASMA_KURSU = [(1.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 6.01)]
PASMA_SZANSY = [(0.0, 0.55), (0.55, 0.70), (0.70, 0.85), (0.85, 1.01)]


def staty(grp: list[dict]) -> tuple[int, float, float, float, float]:
    """n, deklaracja, trafienia, ROI i BŁĄD STANDARDOWY ROI.

    Błąd liczony z rozrzutu pojedynczych zwrotów, nie z liczby trafień:
    typ po kursie 3,55 wnosi do wariancji wielokrotnie więcej niż typ po 1,19,
    więc te same 30 typów daje zupełnie inną pewność wyniku w zależności od
    tego, jak drogie były.
    """
    n = len(grp)
    if n == 0:
        return 0, 0.0, 0.0, 0.0, 0.0
    dekl = sum(float(r["p_model"]) for r in grp) / n
    traf = sum(1 for r in grp if r["wynik"] == "wygrany") / n
    zwroty = [
        (float(r["kurs"]) - 1.0) if r["wynik"] == "wygrany" else -1.0
        for r in grp
    ]
    roi = sum(zwroty) / n
    war = sum((z - roi) ** 2 for z in zwroty) / n
    return n, dekl, traf, roi, (war / n) ** 0.5


def wiersz(nazwa: str, grp: list[dict], szer: int = 26) -> bool:
    """Drukuje wycinek; zwraca True, gdy wynik przekracza własny szum."""
    n, dekl, traf, roi, se = staty(grp)
    istotny = n >= MIN_N and abs(roi) > 2 * se
    znacznik = "  <-- ISTOTNE" if istotny else ""
    print(
        f"{nazwa[:szer]:<{szer}}{n:>6}{dekl:>10.1%}{traf:>9.1%}"
        f"{(traf - dekl) * 100:>+8.1f}{roi:>9.1%}{se:>9.1%}{znacznik}"
    )
    return istotny


def naglowek(pierwsza: str, szer: int = 26) -> None:
    print(
        f"{pierwsza:<{szer}}{'n':>6}{'deklaruje':>10}{'trafia':>9}"
        f"{'luka':>8}{'ROI':>9}{'szum':>9}"
    )


def w_pasmie(rekordy: list[dict], pole, lo: float, hi: float) -> list[dict]:
    return [r for r in rekordy if lo <= float(pole(r)) < hi]


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except Exception:
        pass
    from footstats import supa
    from footstats.jobs import rozliczanie as R

    if not os.environ.get("SUPABASE_URL"):
        print("Brak SUPABASE_URL — audyt potrzebuje księgi z chmury.")
        return

    log = R._migruj_log(supa.get_key("typy_log") or {})
    settled = [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and r.get("p_model") and r.get("kurs")
        and R._z_biezacej_epoki(r) and not R._z_martwej_epoki(r)
    ]
    print(f"Rozliczeń w bieżącej epoce: {len(settled)}\n")
    if not settled:
        return

    sprawdzonych = 0
    istotnych: list[str] = []

    # ---------------------------------------------------------------- 1
    print("=" * 84)
    print("1. PASMA KURSU — punkt wyjścia")
    print("=" * 84)
    naglowek("kurs")
    for lo, hi in PASMA_KURSU:
        grp = w_pasmie(settled, lambda r: r["kurs"], lo, hi)
        if grp:
            sprawdzonych += 1
            if wiersz(f"{lo:.2f} – {hi:.2f}", grp):
                istotnych.append(f"kurs {lo:.2f}–{hi:.2f}")

    # ---------------------------------------------------------------- 2
    print("\n" + "=" * 84)
    print("2. CZY TANIE TYPY TRACĄ WSZĘDZIE — pasmo 1,00–2,00 rynek po rynku")
    print("=" * 84)
    print("Jeśli strata jest wszędzie, winny jest PRÓG KURSU.")
    print("Jeśli siedzi w jednym rynku, próg jest niewinny.\n")
    tanie = w_pasmie(settled, lambda r: r["kurs"], 1.0, 2.0)
    wg_rynku: dict[str, list] = defaultdict(list)
    for r in tanie:
        wg_rynku[f"{r.get('rynek_kod')}|{r.get('strona')}"].append(r)
    naglowek("rynek | strona")
    male = 0
    for nazwa, grp in sorted(wg_rynku.items(), key=lambda x: -len(x[1])):
        if len(grp) < MIN_N:
            male += len(grp)
            continue
        sprawdzonych += 1
        if wiersz(nazwa, grp):
            istotnych.append(f"tanie: {nazwa}")
    if male:
        print(f"{'(wycinki poniżej progu)':<26}{male:>6}   — nie liczone")

    # ---------------------------------------------------------------- 3
    print("\n" + "=" * 84)
    print("3. CZY TO NA PEWNO KURS, A NIE DEKLAROWANA SZANSA")
    print("=" * 84)
    print("Kurs i szansa idą w parze, więc „tanie typy tracą” może naprawdę")
    print("znaczyć „przeszacowujemy górny koniec skali”. Ten sam zbiór,")
    print("pocięty po TYM, CO OBIECUJEMY:\n")
    naglowek("deklarowana szansa")
    for lo, hi in PASMA_SZANSY:
        grp = w_pasmie(settled, lambda r: r["p_model"], lo, hi)
        if grp:
            sprawdzonych += 1
            if wiersz(f"{lo:.0%} – {hi:.0%}", grp):
                istotnych.append(f"szansa {lo:.0%}–{hi:.0%}")

    # ---------------------------------------------------------------- 4
    print("\n" + "=" * 84)
    print("4. TE SAME TYPY, DWA KRYTERIA NARAZ (tanie ORAZ wysoko deklarowane)")
    print("=" * 84)
    naglowek("wycinek")
    for lo, hi in PASMA_SZANSY:
        grp = [r for r in tanie if lo <= float(r["p_model"]) < hi]
        if len(grp) >= MIN_N:
            sprawdzonych += 1
            if wiersz(f"kurs<2,00 i szansa {lo:.0%}+", grp):
                istotnych.append(f"tanie + szansa {lo:.0%}–{hi:.0%}")

    # ---------------------------------------------------------------- 5
    print("\n" + "=" * 84)
    print("5. PRZEDZIAŁ 55–70% POD LUPĄ — ile mu ścinamy, a ile powinniśmy")
    print("=" * 84)
    print("Korekta dzieli skalę na cztery przedziały i każdy ma własną wartość.")
    print("Jeśli akurat ten przedział dostaje korektę bliską zeru, to typy z")
    print("niego wychodzą na stronę nieurealnione — i luka bierze się STĄD,")
    print("a nie z rynku ani z kursu.\n")
    try:
        bias = R.compute_bias_full(log)
    except Exception as e:
        print(f"   nie dało się policzyć kalibracji: {e}")
        bias = {}

    # PRZEDZIAŁ WYBIERA `p_over`, NIE SZANSA TYPU — inaczej ta tabela kłamie.
    # Kalibracja binuje po szansie ZDARZENIA („ile goli padnie"), a nie po
    # szansie zakładu: typ „poniżej" z szansą 61% opisuje zdarzenie o szansie
    # 39% i trafia do przedziału 0–55%, nie 55–70%. Pierwsza wersja tej sekcji
    # patrzyła na `p_model` i przypisała `team_goals|poniżej` korektę +0,049
    # z przedziału, który tych typów w ogóle nie dotyczy.
    def bin_dla_rekordu(wpis: dict | None, r: dict):
        if not isinstance(wpis, dict):
            return None, None
        try:
            p_over = float(R._p_over_rekordu(r))
        except Exception:
            return None, None
        zrodla = wpis.get("zrodla") or []
        for i, b in enumerate(wpis.get("bins") or []):
            if len(b) >= 3 and float(b[0]) <= p_over < float(b[1]):
                return float(b[2]), (zrodla[i] if i < len(zrodla) else None)
        return wpis.get("global"), "global"

    print(f"{'rynek | strona':<26}{'n':>6}{'deklaruje':>10}{'trafia':>9}"
          f"{'luka':>8}{'korekta':>10}{'skąd':>13}")
    srodek = [r for r in settled if 0.55 <= float(r["p_model"]) < 0.70]
    wg: dict[str, list] = defaultdict(list)
    for r in srodek:
        wg[f"{r.get('rynek_kod')}|{r.get('strona')}"].append(r)
    for nazwa, grp in sorted(wg.items(), key=lambda x: -len(x[1])):
        if len(grp) < 10:
            continue
        n, dekl, traf, _roi, _se = staty(grp)
        kod = nazwa.split("|")[0]
        # średnia korekta REALNIE zastosowana do tych typów (każdy rekord
        # trafia do przedziału po swoim p_over, więc jedna grupa potrafi
        # rozjechać się na dwa przedziały)
        wartosci, zrodla_l = [], []
        for r in grp:
            w, z = bin_dla_rekordu(bias.get(kod), r)
            if isinstance(w, (int, float)):
                wartosci.append(float(w))
                zrodla_l.append(str(z))
        opis = (f"{sum(wartosci) / len(wartosci):+.3f}" if wartosci else "—")
        skad = max(set(zrodla_l), key=zrodla_l.count) if zrodla_l else "—"
        print(f"{nazwa[:26]:<26}{n:>6}{dekl:>10.1%}{traf:>9.1%}"
              f"{(traf - dekl) * 100:>+8.1f}{opis:>10}{skad:>13}")
    print("\nKorekta ujemna ŚCIĄGA deklarowaną szansę w dół. Wartość bliska zeru")
    print("(albo dodatnia) przy luce −20 pp znaczy, że warstwa ucząca patrzy")
    print("na ten przedział i uznaje, że jest w porządku.")

    # ---------------------------------------------------------------- 6
    print("\n" + "=" * 84)
    print("6. W KTÓRĄ STRONĘ ZADZIAŁAŁA KOREKTA")
    print("=" * 84)
    print("Korekta strumienia nakłada się na szansę ZDARZENIA (`p_over`), a typ")
    print("„poniżej” bierze dopełnienie — więc ściągnięcie p_over w dół PODNOSI")
    print("deklarację typom „poniżej”. To nie jest błąd: jeśli zdarzeń pada")
    print("mniej, niż liczy model, „poniżej” NAPRAWDĘ ma większą szansę.")
    print()
    print("DLATEGO LICZYMY TO OSOBNO DLA KAŻDEJ STRONY. Wspólna średnia pokazuje")
    print("ruch +4 pp „w górę mimo ujemnej luki” i wygląda jak zepsuty regulator,")
    print("a to tylko efekt tego, że 73% listy to „poniżej”.\n")
    print(f"{'strona':<12}{'n':>6}{'ze stempl':>11}{'ruch':>11}"
          f"{'deklaruje':>11}{'trafia':>9}{'luka':>8}{'ROI':>9}")
    for strona in ("ponizej", "powyzej"):
        grp = [r for r in settled if r.get("strona") == strona]
        if not grp:
            continue
        ze_stemplem = [r for r in grp if r.get("kal_strumien")]
        ruch = (
            sum(float(r["p_model"]) - R._p_surowe(r) for r in ze_stemplem)
            / len(ze_stemplem)
        ) if ze_stemplem else 0.0
        n, dekl, traf, roi, _se = staty(grp)
        print(f"{strona:<12}{n:>6}{len(ze_stemplem):>11}"
              f"{ruch * 100:>+10.1f} pp{dekl:>11.1%}{traf:>9.1%}"
              f"{(traf - dekl) * 100:>+8.1f}{roi:>9.1%}")
    print("\nKIERUNEK jest właściwy w obu przypadkach — korekta ściąga „powyżej”")
    print("i podnosi „poniżej”. Pytanie brzmi, czy jest DOŚĆ MOCNA: jeśli po niej")
    print("obie strony nadal mają dwucyfrową lukę, to nie wystarcza.")

    print("\n" + "=" * 84)
    print("PODSUMOWANIE")
    print("=" * 84)
    print(f"Sprawdzonych wycinków: {sprawdzonych}"
          f"   (przy tylu porównaniach 1–2 „istotne” wypada z samego przypadku)")
    if istotnych:
        print("Przekroczyły własny szum:")
        for i in istotnych:
            print(f"   • {i}")
    else:
        print("Żaden wycinek nie przekroczył własnego szumu.")
    print(f"\nPróg próby: {MIN_N} rozliczeń. Wycinki mniejsze NIE są wynikiem.")


if __name__ == "__main__":
    main()
