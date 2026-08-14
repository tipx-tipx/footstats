# -*- coding: utf-8 -*-
"""CZY MODEL UCZY SIĘ NA WSZYSTKIM — audyt warstw uczenia, strumień po strumieniu.

Pytanie usera (2026-08-05): „czy model faktycznie uczy się na wszystkie rodzaje
typów i wszystkie funkcje — zawodnicy, drużyny, drabinki".

Odpowiada na trzy rzeczy, których nie widać z kodu:

  1. KTÓRY STRUMIEŃ MA DOŚĆ ROZLICZEŃ, żeby którakolwiek warstwa ruszyła.
     Każda warstwa ma własny próg (MIN_N). Poniżej progu NIE dzieje się nic
     i nikt o tym nie krzyczy — warstwa po prostu zwraca wartość globalną
     albo zero, a produkt wygląda, jakby się uczył.
  2. ILE KAŻDA WARSTWA REALNIE POPRAWIA — deklaracja kontra trafienia przed
     korektą i po niej.
  3. KIEDY ZARABIAMY I NA CZYM. Dzień tygodnia i rozgrywki — bo ten sam
     skład typów daje ROI +11% w piątek i sobotę, a −9% w resztę tygodnia.
     Tu też widać, z jakich DNI zrobione jest okno alarmu z części 2:
     paczka to jeden–dwa dni meczowe, więc „model się psuje" bywa tylko
     tyle, że akurat graliśmy w gorsze dni.
  4. CZY CZYNNIKI MODELU ŻYJĄ. `czynniki` to mnożniki (rywal, sędzia,
     dom/wyjazd, scenariusz meczu, styl). Mnożnik równy 1,00 nic nie robi —
     pole może istnieć i być martwe. Sprawdzamy, ile typów danego rynku ma
     dany czynnik RÓŻNY od 1,00, czyli ile razy realnie ruszył liczbę.

    cd pipeline
    PYTHONUTF8=1 python scripts/audyt_uczenia.py

CZYTA TYLKO — nie zapisuje nic.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

NAZWY_STRUMIENI = {
    "pewniaki": "ZAWODNICY",
    "druzyny": "DRUŻYNY",
    "drabinki": "DRABINKI",
}

DNI_PL = ["poniedziałek", "wtorek", "środa", "czwartek",
          "piątek", "sobota", "niedziela"]
DNI_SKROT = ["pn", "wt", "śr", "cz", "pt", "sb", "nd"]

# Piątek i sobota grają w innym produkcie niż reszta tygodnia — zmierzone
# 05.08: ROI +12,3% wobec −17,2% przy tym samym składzie typów. Ten podział
# jest tu wpisany na sztywno, żeby kontrola startowa pokazywała go SAMA,
# a nie żeby ktoś odkrywał go raz na miesiąc.
WEEKEND_KODY = (4, 5)


def _roi(grp: list[dict]) -> float:
    if not grp:
        return 0.0
    return sum(
        (float(r["kurs"]) - 1.0) if r["wynik"] == "wygrany" else -1.0
        for r in grp if r.get("kurs")
    ) / max(len(grp), 1)


def _staty(grp: list[dict]) -> tuple[int, float, float, float, float, float]:
    """n, deklaracja, trafienia, luka, ROI i WŁASNY SZUM tego wycinka.

    Szum (błąd standardowy trafień) jedzie obok każdej liczby, bo bez niego
    „−17% na 40 typach" wygląda tak samo groźnie jak „−17% na 400" —
    ta sama pułapka, która kazała alarmowi trendu liczyć własny próg.
    """
    n = max(len(grp), 1)
    dekl = sum(float(r["p_model"]) for r in grp) / n
    traf = sum(1 for r in grp if r["wynik"] == "wygrany") / n
    szum = (traf * (1.0 - traf) / n) ** 0.5
    return len(grp), dekl, traf, traf - dekl, _roi(grp), szum


def _wiersz(nazwa: str, grp: list[dict], szer: int = 16) -> None:
    n, dekl, traf, luka, roi, szum = _staty(grp)
    print(f"{nazwa[:szer]:<{szer}}{n:>7}{dekl:>11.1%}{traf:>9.1%}"
          f"{luka * 100:>+8.1f}{roi:>9.1%}{szum * 100:>9.1f}")


def _naglowek_tabeli(pierwsza: str, szer: int = 16) -> None:
    print(f"{pierwsza:<{szer}}{'n':>7}{'deklaruje':>11}{'trafia':>9}"
          f"{'luka':>8}{'ROI':>9}{'szum':>9}")


def rozliczone(log: dict, R) -> list[dict]:
    return [
        r for r in log.values()
        if r.get("wynik") in ("wygrany", "przegrany")
        and not r.get("sugestia") and not r.get("odrzucony")
        and r.get("p_model") and r.get("kurs")
        and R._z_biezacej_epoki(r) and not R._z_martwej_epoki(r)
    ]


def czesc1_strumienie(settled: list[dict], R) -> None:
    print("=" * 78)
    print("1. CZY KAŻDY STRUMIEŃ MA Z CZEGO SIĘ UCZYĆ")
    print("=" * 78)
    print(f"{'strumień':<12}{'rozliczeń':>10}{'deklaruje':>11}{'trafia':>9}"
          f"{'luka':>9}{'ROI':>9}")
    grupy: dict[str, list] = defaultdict(list)
    for r in settled:
        grupy[R._strumien(r)].append(r)
    for kod in ("pewniaki", "druzyny", "drabinki"):
        grp = grupy.get(kod) or []
        nazwa = NAZWY_STRUMIENI[kod]
        if not grp:
            print(f"{nazwa:<12}{0:>10}   — BRAK ROZLICZEŃ, warstwy stoją")
            continue
        n = len(grp)
        dekl = sum(float(r["p_model"]) for r in grp) / n
        traf = sum(1 for r in grp if r["wynik"] == "wygrany") / n
        print(f"{nazwa:<12}{n:>10}{dekl:>10.1%}{traf:>9.1%}"
              f"{(traf - dekl) * 100:>+8.1f}{_roi(grp):>9.1%}")

    print(f"\n{'PROGI WARSTW — poniżej nich warstwa NIE działa:':<60}")
    print(f"  korekta strumienia   MIN_N = {R.KOREKTA_STRUMIENIA_MIN_N}"
          f"   (okno {R.KOREKTA_STRUMIENIA_OKNO})")
    print(f"  kalibracja rynku     MIN_N = {R.MIN_N_KALIBRACJI}")
    print(f"  kwarantanna rynku    MIN_N = {R.KWARANTANNA_MIN_N}"
          f"   (okno {R.KWARANTANNA_OKNO}, min. dni {R.KWARANTANNA_MIN_DNI})")
    print(f"  korekta drabinek     MIN_N = {R.KOREKTA_DRABINEK_MIN_N}")
    print(f"  przedziały korekty   MIN_N = {R.KOREKTA_PRZEDZIAL_MIN_N}")


def czesc2_warstwy(log: dict, R) -> None:
    print("\n" + "=" * 78)
    print("2. CO KAŻDA WARSTWA REALNIE WYLICZYŁA")
    print("=" * 78)

    print("\nKOREKTA STRUMIENIA (o ile ściągamy szansę przed publikacją):")
    try:
        kor = R.korekta_strumienia(log)
        if not kor:
            print("   PUSTA — żaden strumień nie zebrał progu")
        for k, v in sorted(kor.items()):
            if isinstance(v, dict):
                g = v.get("global")
                biny = v.get("bins") or []
                print(f"   {NAZWY_STRUMIENI.get(k, k):<12} {g:+.3f}"
                      f"   (+{len(biny)} przedziałów)")
            else:
                print(f"   {NAZWY_STRUMIENI.get(k, k):<12} {v:+.3f}")
    except Exception as e:
        print(f"   BŁĄD: {e}")

    print("\nKALIBRACJA PER RYNEK (bias logitowy z rozliczeń):")
    bias = {}
    try:
        bias = R.compute_bias_full(log)
        if not bias:
            print("   PUSTA")
        for k, v in sorted(bias.items(), key=lambda x: str(x[0]))[:20]:
            print(f"   {str(k):<28} {v if not isinstance(v, dict) else v}")
    except Exception as e:
        print(f"   BŁĄD: {e}")

    # SKĄD SIĘ WZIĘŁA KAŻDA Z TYCH LICZB (czujnik z 05.08). Wiersz wyżej
    # pokazuje cztery liczby na rynek i wygląda to jak cztery pomiary —
    # a przedział bez własnej próby dostaje po prostu wartość globalną.
    print("\n   ILE Z TEGO TO POMIAR:")
    try:
        kor = R.korekta_strumienia(log)
        print("   " + R.zdanie_pokrycia(R.pokrycie_przedzialow(bias, kor)))
        for k, v in sorted(bias.items(), key=lambda x: str(x[0])):
            zr = (v or {}).get("zrodla") or []
            wlasne = sum(1 for z in zr if z == R.ZRODLO_WLASNA)
            if zr:
                print(f"   {str(k):<28} {wlasne}/{len(zr)}  {', '.join(zr)}")
    except Exception as e:
        print(f"   BŁĄD: {e}")

    print("\nKWARANTANNY (co jest chwilowo wstrzymane):")
    for nazwa, fn in (("rynki", R.rynki_kwarantanna),
                      ("strony", R.strony_kwarantanna),
                      ("kategorie", R.kategorie_kwarantanna)):
        try:
            d = fn(log)
            print(f"   {nazwa:<10} {len(d)}"
                  + (f"  ({', '.join(sorted(d)[:6])})" if d else "  — nic"))
        except Exception as e:
            print(f"   {nazwa:<10} BŁĄD: {e}")

    print("\nCZY SIĘ PSUJE (trzy ostatnie paczki wobec trzech poprzednich):")
    try:
        uczenie = R.raport_uczenia(log)
        for nazwa, rec in sorted(uczenie.items()):
            t = rec.get("trend")
            if not t:
                print(f"   {NAZWY_STRUMIENI.get(nazwa, nazwa):<12} za krótka historia")
                continue
            print(f"   {NAZWY_STRUMIENI.get(nazwa, nazwa):<12}"
                  f" {t['luka_poprzednio'] * 100:+.1f} -> {t['luka_teraz'] * 100:+.1f} pp"
                  f"   (szum {t['szum'] * 100:.1f} pp)")
        for z in R.ostrzezenia_trendu(uczenie):
            print(f"   ALARM: {z}")
    except Exception as e:
        print(f"   BŁĄD: {e}")

    print("\nPRZEWAGA NAD CENĄ (czy nasza liczba bije kurs):")
    try:
        p = R.przewaga_rynkow(log)
        bija = [k for k, v in p.items() if v.get("przewaga", 0) > 0]
        print(f"   {len(bija)} z {len(p)} rynków bije cenę"
              + (f": {', '.join(bija)}" if bija else ""))
    except Exception as e:
        print(f"   BŁĄD: {e}")


def czesc3_kalendarz(settled: list[dict], log: dict, R) -> None:
    """KIEDY zarabiamy i NA CZYM — dzień tygodnia oraz rozgrywki.

    Oba przekroje tylko MIERZĄ. Nie ma tu progu, bramy ani reguły publikacji —
    dzień tygodnia nie jest przyczyną, tylko etykietą na czymś, czego jeszcze
    nie nazwaliśmy (rozgrywki? pora dnia? rozmiar oferty?). Rozbicie per liga
    jest jedyną rzeczą, która może pokazać mechanizm — dlatego stoi obok.
    """
    print("\n" + "=" * 78)
    print("3. KIEDY ZARABIAMY (dzień tygodnia) I NA CZYM (rozgrywki)")
    print("=" * 78)

    wg_dnia: dict[int, list] = defaultdict(list)
    for r in settled:
        try:
            d = datetime.strptime(R.dzien_pl(r.get("kickoff_ts")), "%Y-%m-%d")
        except Exception:
            continue
        wg_dnia[d.weekday()].append(r)

    _naglowek_tabeli("dzień")
    for kod in range(7):
        grp = wg_dnia.get(kod) or []
        if grp:
            _wiersz(DNI_PL[kod], grp)

    weekend = [r for k in WEEKEND_KODY for r in wg_dnia.get(k, [])]
    reszta = [r for k, g in wg_dnia.items() if k not in WEEKEND_KODY for r in g]
    if weekend and reszta:
        print()
        _wiersz("PIĄTEK+SOBOTA", weekend)
        _wiersz("RESZTA TYGODNIA", reszta)
        roznica = (_staty(weekend)[4] - _staty(reszta)[4]) * 100
        print(f"   różnica ROI: {roznica:+.1f} pp"
              f"   (na {len(weekend)} vs {len(reszta)} typach)")

    # CZY ALARM Z CZĘŚCI 2 TO NIE JEST ZNOWU KALENDARZ (2026-08-06).
    # Alarm porównuje trzy ostatnie paczki po 40 rozliczeń z trzema
    # poprzednimi. Paczka to ~jeden–dwa dni meczowe, więc okno potrafi
    # w całości wpaść w niedzielę i poniedziałek — i wtedy „model się psuje"
    # znaczy tylko tyle, że graliśmy w gorsze dni ([[uskok-luki-od-02-08]]).
    # Ta tabela pokazuje, z jakich DNI zrobione są ostatnie paczki.
    print("\nZ JAKICH DNI ZROBIONE SĄ PACZKI ALARMU (część 2):")
    try:
        uczenie = R.raport_uczenia(log)
        for nazwa, rec in sorted(uczenie.items()):
            paczki = [p for p in (rec.get("paczki") or []) if p.get("pelna")]
            if not paczki:
                continue
            print(f"   {NAZWY_STRUMIENI.get(nazwa, nazwa)}"
                  f"   (ostatnie {min(len(paczki), 6)} pełnych paczek,"
                  f" trzy ostatnie = okno alarmu)")
            for p in paczki[-6:]:
                od, do = p.get("od", "?"), p.get("do", "?")
                dni = []
                for d in (od, do):
                    try:
                        dni.append(DNI_SKROT[
                            datetime.strptime(d, "%Y-%m-%d").weekday()])
                    except Exception:
                        dni.append("??")
                roi = p.get("roi")
                # NA ILU MECZACH STOI PACZKA (2026-08-14) — patrz nota
                # w `raport_uczenia`. Jeden mecz potrafi dać 40 rozliczeń,
                # a wynik w jego obrębie jest silnie zgodny, więc paczka
                # z trzech meczów nie mówi tego, co paczka z trzydziestu.
                mecze = p.get("meczow")
                najw = p.get("najwiekszy_mecz") or 0
                opis_mecze = ""
                if mecze:
                    udzial = najw / max(p.get("n") or 1, 1)
                    opis_mecze = f"   {mecze:>2} mecz." + (
                        f"  ⚑ największy {udzial:.0%} paczki"
                        if udzial >= 0.25 else "")
                print(f"      {od} ({dni[0]}) – {do} ({dni[1]})"
                      f"   n={p.get('n'):>3}"
                      f"   luka {p.get('luka', 0) * 100:+6.1f} pp"
                      f"   ROI {(f'{roi:+.1%}' if roi is not None else '   —'):>8}"
                      f"{opis_mecze}")
            # OSTRZEŻENIE PRZY SAMYM ALARMIE, nie tylko w tabeli: trzy ostatnie
            # paczki to okno alarmu z części 2.
            okno = paczki[-3:]
            mecze_okna = sum(p.get("meczow") or 0 for p in okno)
            if okno and mecze_okna and mecze_okna <= 12:
                print(f"      ⚑ CAŁE OKNO ALARMU TO {mecze_okna} MECZÓW — "
                      "luka z tego okna opisuje kilka wieczorów, nie model")
    except Exception as e:
        print(f"   BŁĄD: {e}")

    print("\nROZGRYWKI — ile rozliczeń niesie stempel ligi:")
    ze_stemplem = [r for r in settled if r.get("liga")]
    print(f"   {len(ze_stemplem)} z {len(settled)} rozliczonych"
          f"   (stempel wszedł 03.08, więc rośnie z dnia na dzień)")
    if not ze_stemplem:
        print("   Za wcześnie na jakikolwiek wniosek per liga.")
        return

    wg_ligi: dict[str, list] = defaultdict(list)
    for r in ze_stemplem:
        wg_ligi[str(r["liga"])].append(r)

    MIN_LIGA = 10
    duze = {k: v for k, v in wg_ligi.items() if len(v) >= MIN_LIGA}
    print(f"   {len(wg_ligi)} rozgrywek, z tego {len(duze)} ma choć"
          f" {MIN_LIGA} rozliczeń:")
    if duze:
        _naglowek_tabeli("liga", szer=24)
        for nazwa, grp in sorted(duze.items(), key=lambda x: -len(x[1])):
            _wiersz(nazwa, grp, szer=24)
    ogon = sum(len(v) for k, v in wg_ligi.items() if k not in duze)
    if ogon:
        print(f"   + {ogon} rozliczeń w rozgrywkach poniżej progu — nie liczone")

    # Ten przekrój ma sens dopiero, gdy stempel obejmie WIĘKSZOŚĆ rozliczeń;
    # inaczej „piątek na lidze X" to garść typów udająca prawidłowość.
    if len(ze_stemplem) < 0.5 * len(settled):
        print("   UWAGA: stempel ma mniej niż połowa rozliczeń — rozbicie"
              " efektu dnia tygodnia PER LIGA jeszcze nie ma podstawy.")
    else:
        print("\n   DZIEŃ TYGODNIA W ROZBICIU NA LIGI (tylko rozgrywki z próbą):")
        for nazwa, grp in sorted(duze.items(), key=lambda x: -len(x[1])):
            we = [r for r in grp
                  if datetime.strptime(R.dzien_pl(r.get("kickoff_ts")),
                                       "%Y-%m-%d").weekday() in WEEKEND_KODY]
            re_ = [r for r in grp if r not in we]
            if we and re_:
                print(f"   {nazwa[:24]:<24} pt+sb {_staty(we)[4]:+6.1%}"
                      f" ({len(we)})   reszta {_staty(re_)[4]:+6.1%}"
                      f" ({len(re_)})")


def czesc4_czynniki(vb: list[dict]) -> None:
    """Czy czynniki modelu ŻYJĄ — mnożnik 1,00 niczego nie zmienia."""
    print("\n" + "=" * 78)
    print("4. CZY CZYNNIKI MODELU ŻYJĄ (mnożnik ≠ 1,00 = realnie ruszył liczbę)")
    print("=" * 78)
    zyw = [b for b in vb if not b.get("sugestia")]
    grupy: dict[str, list] = defaultdict(list)
    for b in zyw:
        grupy[str(b.get("rynek_kod") or "?")].append(b)

    czynniki_kolejnosc = [
        "rywal", "sedzia", "dom_wyjazd", "scenariusz_meczu", "matchup",
        "minuty", "forma", "tempo",
    ]
    naglowek = "".join(f"{c[:9]:>11}" for c in czynniki_kolejnosc)
    print(f"{'rynek':<18}{'n':>4}{naglowek}")
    for rynek, grp in sorted(grupy.items(), key=lambda x: -len(x[1])):
        wiersz = f"{rynek[:18]:<18}{len(grp):>4}"
        for c in czynniki_kolejnosc:
            ile = 0
            for b in grp:
                cz = b.get("czynniki") or {}
                v = cz.get(c)
                if isinstance(v, (int, float)) and abs(float(v) - 1.0) > 0.02:
                    ile += 1
            wiersz += f"{(f'{ile}/{len(grp)}' if ile else '–'):>11}"
        print(wiersz)
    print("\n„–" + "\" = ten czynnik NIE ruszył ani jednego typu na tym rynku.")
    print("Powód bywa niewinny (rynek go nie używa) albo nie — patrz raport.")


def _odniesienie_skladem(grp: list[dict], pub_wg: dict[str, list], R) -> float:
    """ROI publikowanych o TAKIM SAMYM składzie strumieni co `grp`.

    ⚑ NAPRAWA 13.08 — TA TABELA PORÓWNYWAŁA JABŁKA Z GRUSZKAMI I RAZ JUŻ
    ZMIENIŁA PRZEZ TO PRODUKT. Odniesieniem było „wszystko pokazane", czyli
    zbiór z 94 drabinkami o ROI −25,5%, a bramy niżej nie zdejmują drabinek
    ANI JEDNEJ (0% w każdej grupie — drabinki mają własne progi). Odniesienie
    było więc zaniżone o 2,3 pp (−4,2% zamiast −1,9%) i dwie bramy wychodziły
    na „zdejmujące lepszy materiał", choć zdejmowały gorszy:

        rozjazd_z_rynkiem   −2,4%  wobec −4,2% (całość)  ale −1,9% (bez drabinek)
        kwarantanna_strony  −4,3%  wobec −4,2% (całość)  ale −1,9% (bez drabinek)

    Ta pierwsza to okno zgody — brama, którą pomiar z 12.08 rekomendował
    rozluźnić WŁAŚNIE na tej podstawie (patrz OKNO_ZGODY_MAX w betting.py).

    Ważymy udziałem strumieni, a nie odsiewamy drabinek na sztywno: gdy
    drabinki dorobią się własnych bram, porównanie ma dalej być uczciwe.
    """
    if not grp:
        return 0.0
    wagi: dict[str, int] = defaultdict(int)
    for r in grp:
        wagi[R._strumien(r)] += 1
    licznik = mianownik = 0.0
    for strumien, waga in wagi.items():
        pub_s = pub_wg.get(strumien) or []
        if not pub_s:
            continue          # ten strumień nie ma publikowanych — pomijamy
        licznik += waga * _roi(pub_s)
        mianownik += waga
    return licznik / mianownik if mianownik else 0.0


def _w_obrebie_segmentu(
    grp: list[dict], pub: list[dict],
) -> tuple[float, int, float] | None:
    """Ta sama różnica, ale liczona WEWNĄTRZ segmentu (rynek|strona).

    ⚑ DRUGA POŁOWA TEJ SAMEJ PUŁAPKI, co w `_odniesienie_skladem`. Bramy nie
    wybierają losowo: kwarantanna wstrzymuje segment po serii pecha, czyli
    dokładnie wtedy, gdy ten i tak wraca do średniej. Porównanie „zdjęte wobec
    całej strony" miesza więc efekt BRAMY z efektem SEGMENTU i nie odpowiada
    na jedyne pytanie, które ma znaczenie: czy ten sam segment wypada gorzej
    w czasie wstrzymania niż poza nim.

    Zmierzone 13.08 na kwarantannie strony — oba porównania dają PRZECIWNE
    odpowiedzi, więc to nie jest różnica akademicka:

        wobec strony:        -4,3% wobec -1,9%    „brama zdejmowała gorsze"
        w obrębie segmentu:  +14,3%               „brama zdejmowała lepsze"

    Mechanizm widać wprost na największym segmencie: `team_corners|ponizej`
    miał ROI -38,9% na 40 rozliczeniach przed wstrzymaniem i +7,6% na 153
    typach zdjętych w jego trakcie. Brama złapała odbicie, nie słabość.

    ⚑ ZWRACAMY TEŻ UDZIAŁ NAJWIĘKSZEGO SEGMENTU, bo bez niego ta liczba kłamie
    równie łatwo jak tamta: tamte +14,3% to w 70% jeden segment, a w trzech
    pozostałych brama miała rację (próby 11-28, czyli szum).

    ⚑ ZWRACAMY OBIE RÓŻNICE — ROI I LUKĘ. ROI zmienia znak między połowami
    próby (dlatego progi w tym repo stoją na luce, patrz OKNO_ZGODY_MAX),
    więc sama różnica zwrotu potrafi tu powiedzieć „brama nie odróżnia", gdy
    brama odróżnia bardzo dobrze — tyle że po deklaracji, nie po kasie.

    Zwraca (różnica ROI, różnica luki w pp, ile segmentów, udział
    największego) albo None, gdy żaden segment nie ma próby po obu stronach.
    """
    zd_seg: dict[str, list] = defaultdict(list)
    pub_seg: dict[str, list] = defaultdict(list)
    for r in grp:
        zd_seg[f"{r.get('rynek_kod')}|{r.get('strona')}"].append(r)
    for r in pub:
        pub_seg[f"{r.get('rynek_kod')}|{r.get('strona')}"].append(r)

    MIN_PO_STRONIE = 10
    sumy = sumy_luk = wagi = 0.0
    najwieksza = 0.0
    ile = 0
    for s, z in zd_seg.items():
        p = pub_seg.get(s) or []
        if len(z) < MIN_PO_STRONIE or len(p) < MIN_PO_STRONIE:
            continue
        waga = float(min(len(z), len(p)))
        sumy += waga * (_roi(z) - _roi(p))
        sumy_luk += waga * (_staty(z)[3] - _staty(p)[3]) * 100
        wagi += waga
        najwieksza = max(najwieksza, waga)
        ile += 1
    if not wagi:
        return None
    return sumy / wagi, sumy_luk / wagi, ile, najwieksza / wagi


def czesc5_bramy(settled: list[dict], R) -> None:
    """ILE PIENIĘDZY ZDEJMUJĄ BRAMY — czyli czy w ogóle się opłacają.

    Typ zdjęty bramą nie znika: rozlicza się „w tle" i uczy model, więc znamy
    jego wynik. To jedyne miejsce w projekcie, gdzie widać, czy brama wycina
    coś gorszego od tego, co przepuszcza — a to nie jest oczywiste. Zmierzone
    14.08 na epoce ligowej: kwarantanna rynku zdejmowała typy o ROI +10,3%,
    przy publikowanych −3,5%. Trzy bramy trafiły wtedy do przeglądu, dwie
    zostały zdjęte.

    Bez tej tabeli takie rzeczy wychodzą raz na miesiąc, przy okazji.
    Z nią widać je w każdej kontroli startowej.

    KAŻDA BRAMA MA WŁASNE ODNIESIENIE, dopasowane składem strumieni —
    patrz `_odniesienie_skladem`, gdzie opisane jest, co bez tego wyszło.
    """
    print()
    print("=" * 78)
    print("5. CO ZDEJMUJĄ BRAMY (typ zdjęty rozlicza się dalej — znamy wynik)")
    print("=" * 78)
    pub = [r for r in settled if not r.get("poza_publikacja")]
    if not pub:
        print("   brak rozliczeń publikowanych — nie ma do czego porównywać")
        return
    pub_wg: dict[str, list] = defaultdict(list)
    for r in pub:
        pub_wg[R._strumien(r)].append(r)
    # 26 znaków, bo przy 22 nazwy bram ucinały się do „kwarantanna_st",
    # „kwarantanna_ry" i „kwarantanna_ka" — trzy różne bramy nie do odróżnienia
    # w tabeli, na której podejmuje się decyzje o produkcie
    _naglowek_tabeli("co się stało", szer=26)
    _wiersz("POKAZANE NA STRONIE", pub, szer=26)
    # rozbicie odniesienia — bez niego nie widać, że całość ciągnie w dół
    # strumień, którego bramy niżej w ogóle nie dotyczą
    for kod in ("pewniaki", "druzyny", "drabinki"):
        grp = pub_wg.get(kod) or []
        if grp and len(grp) != len(pub):
            _wiersz(f"   w tym {NAZWY_STRUMIENI[kod].lower()}", grp, szer=26)
    print()
    grupy: dict[str, list] = defaultdict(list)
    for r in settled:
        if r.get("poza_publikacja"):
            grupy[str(r["poza_publikacja"])].append(r)
    lepsze = []
    for powod, grp in sorted(grupy.items(), key=lambda kv: -len(kv[1])):
        _wiersz(f"zdjęte: {powod}", grp, szer=26)
        odn = _odniesienie_skladem(grp, pub_wg, R)
        if len(grp) >= 25 and _roi(grp) > odn:
            lepsze.append((powod, len(grp), _roi(grp), odn))
    if lepsze:
        print()
        print("   ⚑ BRAMY, KTÓRE ZDEJMUJĄ MATERIAŁ LEPSZY NIŻ PUBLIKOWANY:")
        for powod, n, roi, odn in lepsze:
            print(f"      {powod:<24} n={n:>4}  ROI {roi:>6.1%} "
                  f"wobec {odn:>6.1%} na tym samym materiale")
        print("      (bramy wybierają nielosowo — to sygnał do pomiaru,")
        print("       nie dowód; patrz docs/pomiar-bramy-i-kolejnosc.md)")
    else:
        print()
        print("   Żadna brama nie zdejmuje materiału lepszego niż publikowany"
              " — porównanie na tym samym składzie strumieni.")

    # TO SAMO PYTANIE, ZADANE UCZCIWIEJ — patrz `_w_obrebie_segmentu`.
    # Wiersze wyżej porównują brama-vs-strona; tu ten sam segment porównuje się
    # sam ze sobą, w czasie zdejmowania i poza nim. Gdy obie liczby mają
    # przeciwne znaki, rozstrzyga TA, a tamta mówi tylko, że brama trafiła
    # w słaby segment (co wiemy, bo po to jest).
    print()
    print("   TO SAMO W OBRĘBIE SEGMENTU (ten sam rynek|strona, zdjęte vs"
          " publikowane):")
    cokolwiek = False
    for powod, grp in sorted(grupy.items(), key=lambda kv: -len(kv[1])):
        if len(grp) < 25:
            continue
        wynik = _w_obrebie_segmentu(grp, pub)
        if wynik is None:
            print(f"      {powod:<24} brak segmentu z próbą po obu stronach")
            continue
        cokolwiek = True
        roznica, roznica_luki, ile, udzial = wynik
        # o kierunku rozstrzyga LUKA — ROI w tych wycinkach zmienia znak
        kierunek = ("zdejmuje LEPSZE" if roznica_luki > 0 else "zdejmuje gorsze")
        ostrzez = "  ⚑ jeden segment" if udzial >= 0.6 else ""
        print(f"      {powod:<24} luka {roznica_luki:>+5.1f} pp   "
              f"ROI {roznica:>+6.1%}   {kierunek:<15}"
              f" ({ile} segm., naj. {udzial:.0%}){ostrzez}")
    if cokolwiek:
        print("      Dodatnia luka = brama zdejmowała typy lepiej wycenione niż"
              " to, co zostawało")
        print("      w tym samym segmencie, czyli łapała powrót do średniej.")
        print('      Przy „jeden segment" liczba mówi o nim, nie o bramie.')


def czesc0_awarie(supa) -> None:
    """CZY CYKL PADAŁ — pierwsza rzecz, na którą trzeba spojrzeć.

    Cykl pada średnio raz na kilkanaście przebiegów, a padnięty NIE WYPYCHA
    NICZEGO — czyli strona zostaje z danymi sprzed godzin. Do 13.08 diagnoza
    ginęła razem z przebiegiem (traceback szedł tylko do logu Actions, a tego
    bez tokena nie da się pobrać). Od tej wersji cykl zostawia ślad w bazie
    i tu go czytamy.
    """
    awarie = supa.get_key("awarie_cyklu") or []
    if not awarie:
        print("0. AWARIE CYKLU: brak zapisanych — albo nic nie padło od "
              "wdrożenia śladu (13.08), albo baza nie oddała listy\n")
        return
    print("=" * 78)
    print(f"0. AWARIE CYKLU — {len(awarie)} zapisanych, najnowsze na dole")
    print("=" * 78)
    licznik: dict[str, int] = defaultdict(int)
    for a in awarie[-8:]:
        print(f"   {a.get('kiedy')}  po {a.get('minuty')} min  "
              f"{a.get('wyjatek')}: {str(a.get('komunikat'))[:90]}")
        for linia in (a.get("slad") or [])[-2:]:
            print(f"      {linia}")
    for a in awarie:
        licznik[str(a.get("wyjatek"))] += 1
    if len(awarie) > 1:
        print("   powtarzalność: " + ", ".join(
            f"{k} × {v}" for k, v in sorted(licznik.items(), key=lambda kv: -kv[1])
        ))
    print()


def czesc6_drabinki(log: dict, R) -> None:
    """DRABINKA MA DWA SZCZEBLE — a rozliczaliśmy jeden.

    Zakładka stoi na zdaniu usera „drugi szczebel bardzo często siada i jest
    jakby głównym celem". Ocena karty uśrednia przewagę OBU szczebli, więc ta
    liczba współdecyduje o kolejności — a do 13.08 nie miała ani jednego
    rozliczenia. Od tej wersji drugi szczebel idzie do księgi jako typ
    pomiarowy (poza Skutecznością i poza uczeniem) i tu widać jego wynik.
    """
    print()
    print("=" * 78)
    print("6. DRABINKI — PIERWSZY SZCZEBEL WOBEC DRUGIEGO")
    print("=" * 78)
    p = R.pomiar_szczebli_drabinek(log)
    if not p["hero"]["n"] and not p["drugi"]["n"]:
        print("   brak rozliczonych drabinek w bieżącej epoce")
        return
    print(f"{'poziom':<26}{'n':>5}{'deklaruje':>11}{'trafia':>9}"
          f"{'luka':>8}{'ROI':>9}")
    for kod, nazwa in (("hero", "pierwszy (nagłówek)"),
                       ("drugi", "drugi (cel polowania)")):
        s = p[kod]
        if not s["n"]:
            print(f"   {nazwa:<23}{0:>5}   — brak rozliczeń")
            continue
        luka = (s["hit"] - (s["sr_p"] or 0)) * 100
        print(f"   {nazwa:<23}{s['n']:>5}{s['sr_p']:>10.1%}{s['hit']:>9.1%}"
              f"{luka:>+8.1f}{(s['roi'] or 0):>9.1%}")

    par = p["pary"]
    if par["n"]:
        print(f"\n   KARTY Z OBOMA SZCZEBLAMI ROZLICZONYMI: {par['n']}")
        print(f"      weszły oba (upolowany cel)   {par['oba']:>4}"
              f"   {par['udzial_oba']:.0%}")
        print(f"      wszedł tylko pierwszy        {par['tylko_hero']:>4}")
        if par["niespojne"]:
            print(f"      ⚑ NIESPÓJNE: {par['niespojne']} — wyższy szczebel "
                  f"wszedł, niższy nie.")
            print("        To arytmetycznie niemożliwe: błąd rozliczania, "
                  "nie wynik modelu.")
    else:
        print("\n   Żadna karta nie ma jeszcze rozliczonych OBU szczebli.")

    k = p["korekta_strumienia"]
    if k["n"]:
        print("\n   CZY KOREKTĘ STRUMIENIA WOLNO NAKŁADAĆ NA DRUGI SZCZEBEL")
        print("   (delta jest zmierzona na szczeblach pierwszych — patrz "
              "kolejka po audycie)")
        print(f"      deklaracja PRZED ścięciem   {k['deklaracja_przed']:.1%}")
        print(f"      deklaracja PO ścięciu       {k['deklaracja_po']:.1%}"
              "   <- to pokazuje karta")
        print(f"      faktycznie weszło           {k['faktycznie']:.1%}")
        if p["drugi"]["n"] < p["min_n"]:
            print(f"      (n={p['drugi']['n']} przy progu {p['min_n']} — "
                  "za mało na wniosek, liczba ma rosnąć)")


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
    settled = rozliczone(log, R)
    print(f"Księga: {len(log)} wpisów, rozliczonych w bieżącej epoce: {len(settled)}\n")
    czesc0_awarie(supa)
    czesc1_strumienie(settled, R)
    czesc2_warstwy(log, R)
    czesc3_kalendarz(settled, log, R)
    czesc4_czynniki(supa.get_key("value_bets") or [])
    czesc5_bramy(settled, R)
    czesc6_drabinki(log, R)


if __name__ == "__main__":
    main()
