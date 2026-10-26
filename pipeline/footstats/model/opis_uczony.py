"""Opis typu modelu uczonego – czynniki z rozkładu λ (`uczony.skladniki_*`).

⚑ 2026-10-11 (właściciel: „opisy pod typami przepisać dokładnie”). Karta
typu pokazywała czynniki STAREGO silnika (scenariusz meczu, sędzia, styl
rywala), a szansę liczy model uczony. Tu każdy czynnik to grupa cech, która
REALNIE weszła do λ, z liczbą, z której powstała, i z siłą wpływu.

Kształt wyniku taki sam jak `uzasadnienie.czynniki` starego silnika
({nazwa, mnoznik, opis}), żeby front (`powodPoLudzku`) czytał oba. Zasady:
  * `mnoznik` jest już w KIERUNKU TYPU: przy „poniżej” czynnik, który
    podnosi λ, działa PRZECIW typowi (mnoznik < 1),
  * `mnoznik` None = fakt bez kierunku (oczekiwana liczba, pokrycie zawodnika),
  * opis bez „;” i „(”, bo front tnie tekst w tych miejscach,
  * liczby z przecinkiem, jedno miejsce po przecinku.
"""
from __future__ import annotations

# poniżej tej siły czynnik nie trafia na kartę (front i tak gasi ±2%)
MIN_WPLYW = 0.03

# ⚑ PEŁNE ZDANIA (2026-10-26, właściciel: „logicznie napisane, zgodnie
# z prawdą, bez skrótów myślowych”). Każde zdanie mówi, KTO, CO i ILE, z nazwą
# statystyki: liczba z przecinkiem łączy się z dopełniaczem liczby pojedynczej
# („13,8 faulu”), porównanie „więcej/mniej” z dopełniaczem mnogiej („fauli”).
# Nazwy drużyn bez odmiany, więc „drużyny X”, „przeciw drużynie X”.
STATYSTYKA = {
    "shots": ("strzału", "strzałów"),
    "sot": ("celnego strzału", "celnych strzałów"),
    "shots_outside_box": ("strzału zza pola karnego", "strzałów zza pola karnego"),
    "sot_outside_box": ("celnego strzału zza pola karnego", "celnych strzałów zza pola karnego"),
    "headed_shots": ("strzału głową", "strzałów głową"),
    "headed_sot": ("celnego strzału głową", "celnych strzałów głową"),
    "fouls_committed": ("faulu", "fauli"),
    "fouls_won": ("wywalczonego faulu", "wywalczonych fauli"),
    "offsides": ("spalonego", "spalonych"),
    "tackles": ("odbioru", "odbiorów"),
    "corners": ("rzutu rożnego", "rzutów rożnych"),
    "cards": ("kartki", "kartek"),
    "fouls": ("faulu", "fauli"),
    "goals": ("gola", "goli"),
}


def statystyka(rynek_kod) -> tuple[str, str]:
    """(dopełniacz l. poj., dopełniacz l. mn.) statystyki rynku."""
    kod = str(rynek_kod or "")
    for prefiks in ("team_", "match_", "wiecej_"):
        if kod.startswith(prefiks):
            kod = kod[len(prefiks):]
    return STATYSTYKA.get(kod, ("tej statystyki", "tej statystyki"))


def _l(x) -> str:
    return f"{float(x):.1f}".replace(".", ",")


def _kier(mn: float | None, strona: str) -> float | None:
    if mn is None:
        return None
    m = float(mn)
    return round(m if strona == "powyzej" else 1.0 / m, 3)


def _istotny(m: float | None) -> bool:
    return m is not None and abs(m - 1.0) >= MIN_WPLYW


def _zgodny(v, r, surowy: float | None) -> bool:
    """Liczba stoi po tej stronie odniesienia, w którą czynnik pcha λ.

    Kierunek `mn` model liczy względem mediany z treningu, nie względem
    linii. Bez tego warunku karta potrafiła pokazać „przeciw” przy liczbie,
    która na oko pomaga (Thun, rożne powyżej 1,5: „przeciw Twente średnio
    3,5” – mniej niż przy przeciętnym rywalu 4,6, ale gracz porównuje z 1,5).
    Czynnik, którego liczba przeczy kierunkowi, nie trafia na kartę."""
    if v is None or r is None or surowy is None:
        return False
    v, r = float(v), float(r)
    if round(v, 1) == round(r, 1):
        return False
    return (v > r) == (float(surowy) > 1.0)


def czynniki(b: dict) -> list[dict]:
    """Czynniki opisu dla typu `b` (rekord listy dnia z `p_uczony.skl`).

    14.10 (właściciel: „krótko, z głową”): każda liczba z porównaniem do
    przeciętnej (tego, względem czego model liczy kierunek), „gdzie gra”
    z ogólnego efektu gospodarza (średnia drużyny u siebie siedzi w formie),
    bez stylu gry (nieczytelny: „posiadanie piłki” przy kartkach) i bez
    „ostatnich meczów” zawodnika (karta pokazuje je kratkami)."""
    pu = b.get("p_uczony") or {}
    skl = pu.get("skl") or {}
    mn = skl.get("mn") or {}
    x = skl.get("x") or {}
    ref = skl.get("ref") or {}
    strona = b.get("strona")
    if not mn or strona not in ("powyzej", "ponizej"):
        return []
    linia = float(b.get("linia") or 0)
    rywal = b.get("przeciwnik") or ""
    zawodnik = b.get("podmiot_typ") == "zawodnik"
    kto = b.get("podmiot") or ("Zawodnik" if zawodnik else "Drużyna")
    druzyna = (b.get("druzyna") or "") if zawodnik else kto
    sg, mn_l = statystyka(b.get("rynek_kod"))
    przeciw_kogo = f"przeciw drużynie {rywal}" if rywal else "przeciw temu rywalowi"
    out: list[dict] = []

    if pu.get("lam") is not None:
        out.append({"nazwa": "Spodziewana liczba", "mnoznik": None,
                    "opis": f"Nasz model spodziewa się, że {kto} zanotuje ok. "
                            f"{_l(pu['lam'])} {sg} – linia wynosi {_l(linia)}"})

    def dodaj(nazwa: str, grupa: str, opis: str) -> None:
        m = _kier(mn.get(grupa), strona)
        if _istotny(m):
            out.append({"nazwa": nazwa, "mnoznik": m, "opis": opis})

    def gdzie_gra() -> None:
        dom, s = x.get("dom"), mn.get("dom")
        if dom is None or s is None or float(dom) not in (0.0, 1.0):
            return
        grupa = "gospodarze" if dom else "goście"
        podmiot = f"Drużyna {druzyna}" if druzyna else ("Jego drużyna" if zawodnik else "Drużyna")
        dodaj("Gdzie gra", "dom",
              f"{podmiot} gra {'u siebie' if dom else 'na wyjeździe'}, a {grupa} notują "
              f"zwykle {'więcej' if float(s) > 1 else 'mniej'} {mn_l}")

    if zawodnik:
        s = mn.get("forma")
        if _zgodny(x.get("t12"), ref.get("t12"), s):
            t3 = (f", w ostatnich 3 meczach {_l(x['t3'])}"
                  if _zgodny(x.get("t3"), ref.get("t12"), s) else "")
            dodaj("Tempo", "forma", f"{kto} ma średnio {_l(x['t12'])} {sg} na 90 minut{t3}, "
                                    f"a przeciętny zawodnik {_l(ref['t12'])}")
        elif _zgodny(x.get("t3"), ref.get("t3"), s):
            dodaj("Tempo", "forma", f"{kto} w ostatnich 3 meczach miał średnio {_l(x['t3'])} "
                                    f"{sg} na 90 minut, a przeciętny zawodnik {_l(ref['t3'])}")
        if x.get("min"):
            dodaj("Minuty gry", "minuty", f"{kto} powinien zagrać ok. {int(x['min'])} minut")
        if x.get("rywal"):
            r = float(x["rywal"])
            ile = abs(round((r - 1.0) * 100))
            if ile >= 5 and (r > 1) == (float(mn.get("rywal") or 1.0) > 1):
                dodaj("Rywal", "rywal",
                      f"Zawodnicy na tej pozycji grający {przeciw_kogo} mają o {ile}% "
                      f"{'więcej' if r > 1 else 'mniej'} {mn_l} niż średnio w lidze")
        gdzie_gra()
    else:
        s = mn.get("forma")
        for k, tekst in (("w12", "w ostatnich 12 meczach"), ("w6", "w ostatnich 6 meczach"),
                         ("w_dom", "u siebie" if x.get("dom") else "na wyjeździe")):
            if _zgodny(x.get(k), ref.get(k), s):
                dodaj("Forma", "forma", f"{kto} {tekst} notuje średnio {_l(x[k])} {sg} "
                                        f"na mecz, a przeciętna drużyna {_l(ref[k])}")
                break
        gdzie_gra()
        # siła klubu z wyników (15.10) – bez przewagi domu, bo ta ma własny
        # wiersz „Gdzie gra”; zdanie tylko, gdy różnica jest wyraźna
        # (≥ 40 pkt rankingu) i przewaga domu nie odwraca jej znaku (czynnik
        # liczy się z różnicą RAZEM z domem – inaczej zdanie mówiłoby
        # „słabsza”, a czynnik działałby jak dla silniejszej)
        if x.get("sila") is not None and x.get("dom") in (0, 1, 0.0, 1.0) and mn.get("sila"):
            s_r = float(x["sila"]) - (0.15 if float(x["dom"]) else -0.15)
            if abs(s_r) >= 0.1 and (s_r > 0) == (float(x["sila"]) > 0):
                wobec = f"od drużyny {rywal}" if rywal else "od rywala"
                stopien = "wyraźnie " if abs(s_r) >= 0.25 else ""
                dodaj("Siła drużyn", "sila",
                      f"Według wyników ostatnich meczów drużyna {kto} jest {stopien}"
                      f"{'silniejsza' if s_r > 0 else 'słabsza'} {wobec}")
        if _zgodny(x.get("opp12"), ref.get("opp12"), mn.get("rywal")):
            ryw = f"drużyny {rywal}" if rywal else "tego rywala"
            dodaj("Rywal", "rywal", f"Przeciwnicy {ryw} notują średnio {_l(x['opp12'])} {sg} "
                                    f"na mecz, a przy przeciętnym rywalu {_l(ref['opp12'])}")
        if _zgodny(x.get("liga"), ref.get("liga"), mn.get("liga")):
            dodaj("Liga", "liga", f"W tej lidze drużyny notują średnio {_l(x['liga'])} {sg} "
                                  f"na mecz, a w przeciętnej lidze {_l(ref['liga'])}")
        # pokrycie linii – mieszane z modelem, wpływ = p z pokryciem / p bez
        if pu.get("p_bez_pokrycia") and pu.get("p"):
            m = round(float(pu["p"]) / float(pu["p_bez_pokrycia"]), 3)
            czesci = []
            if pu.get("pkw") is not None and pu.get("pkn"):
                n = int(pu["pkn"])
                k = round(float(pu["pkw"]) * n)
                czesci.append(f"w {k if strona == 'powyzej' else n - k} z {n} ostatnich "
                              f"meczów drużyny {kto}")
            if pu.get("pkr") is not None and pu.get("pkrn"):
                n = int(pu["pkrn"])
                k = round(float(pu["pkr"]) * n)
                ryw = f"drużyny {rywal}" if rywal else "tego rywala"
                czesci.append(f"a u przeciwników {ryw} – w "
                              f"{k if strona == 'powyzej' else n - k} z {n} jej ostatnich meczów")
            if czesci and _istotny(m):
                out.append({"nazwa": "Linia w historii", "mnoznik": m,
                            "opis": f"{'Więcej' if strona == 'powyzej' else 'Mniej'} niż "
                                    f"{_l(linia)} {sg} było " + ", ".join(czesci)})
    # najpierw fakt (spodziewana liczba), potem najsilniejsze za, potem przeciw
    baza = [c for c in out if c["mnoznik"] is None]
    za = sorted((c for c in out if c["mnoznik"] is not None and c["mnoznik"] > 1),
                key=lambda c: -c["mnoznik"])
    przeciw = sorted((c for c in out if c["mnoznik"] is not None and c["mnoznik"] < 1),
                     key=lambda c: c["mnoznik"])
    return baza + za + przeciw
