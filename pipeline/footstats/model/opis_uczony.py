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
    rywal = b.get("przeciwnik") or "rywalem"
    zawodnik = b.get("podmiot_typ") == "zawodnik"
    out: list[dict] = []

    if pu.get("lam") is not None:
        out.append({"nazwa": "Spodziewana liczba", "mnoznik": None,
                    "opis": f"Model spodziewa się {_l(pu['lam'])} przy linii {_l(linia)}"})

    def dodaj(nazwa: str, grupa: str, opis: str) -> None:
        m = _kier(mn.get(grupa), strona)
        if _istotny(m):
            out.append({"nazwa": nazwa, "mnoznik": m, "opis": opis})

    def gdzie_gra() -> None:
        dom, s = x.get("dom"), mn.get("dom")
        if dom is None or s is None or float(dom) not in (0.0, 1.0):
            return
        kto = "gospodarze" if dom else "goście"
        dodaj("Gdzie gra", "dom",
              f"Gra {'u siebie' if dom else 'na wyjeździe'}, a {kto} mają zwykle "
              f"{'więcej' if float(s) > 1 else 'mniej'}")

    if zawodnik:
        s = mn.get("forma")
        if _zgodny(x.get("t12"), ref.get("t12"), s):
            t3 = (f", w ostatnich 3 meczach {_l(x['t3'])}"
                  if _zgodny(x.get("t3"), ref.get("t12"), s) else "")
            dodaj("Tempo", "forma", f"Średnio {_l(x['t12'])} na 90 minut{t3}, "
                                    f"przeciętny zawodnik {_l(ref['t12'])}")
        elif _zgodny(x.get("t3"), ref.get("t3"), s):
            dodaj("Tempo", "forma", f"W ostatnich 3 meczach {_l(x['t3'])} na 90 minut, "
                                    f"przeciętny zawodnik {_l(ref['t3'])}")
        if x.get("min"):
            dodaj("Minuty gry", "minuty", f"Powinien zagrać ok. {int(x['min'])} minut")
        if x.get("rywal"):
            r = float(x["rywal"])
            ile = abs(round((r - 1.0) * 100))
            if ile >= 5 and (r > 1) == (float(mn.get("rywal") or 1.0) > 1):
                dodaj("Rywal", "rywal",
                      f"Przeciw {rywal} zawodnicy na tej pozycji mają o {ile}% "
                      f"{'więcej' if r > 1 else 'mniej'} niż średnio w lidze")
        gdzie_gra()
    else:
        s = mn.get("forma")
        for k, tekst in (("w12", "w ostatnich 12 meczach"), ("w6", "w ostatnich 6 meczach"),
                         ("w_dom", "u siebie" if x.get("dom") else "na wyjeździe")):
            if _zgodny(x.get(k), ref.get(k), s):
                dodaj("Forma", "forma", f"Średnio {_l(x[k])} {tekst}, "
                                        f"przeciętna drużyna {_l(ref[k])}")
                break
        gdzie_gra()
        if _zgodny(x.get("opp12"), ref.get("opp12"), mn.get("rywal")):
            dodaj("Rywal", "rywal", f"Przeciw {rywal} drużyny mają średnio {_l(x['opp12'])}, "
                                    f"przy przeciętnym rywalu {_l(ref['opp12'])}")
        if _zgodny(x.get("liga"), ref.get("liga"), mn.get("liga")):
            dodaj("Liga", "liga", f"Średnia w tej lidze {_l(x['liga'])}, "
                                  f"w przeciętnej {_l(ref['liga'])}")
        # pokrycie linii – mieszane z modelem, wpływ = p z pokryciem / p bez
        if pu.get("p_bez_pokrycia") and pu.get("p"):
            m = round(float(pu["p"]) / float(pu["p_bez_pokrycia"]), 3)
            czesci = []
            if pu.get("pkw") is not None and pu.get("pkn"):
                n = int(pu["pkn"])
                k = round(float(pu["pkw"]) * n)
                czesci.append(f"{k if strona == 'powyzej' else n - k} z {n} meczów drużyny")
            if pu.get("pkr") is not None and pu.get("pkrn"):
                n = int(pu["pkrn"])
                k = round(float(pu["pkr"]) * n)
                czesci.append(f"{k if strona == 'powyzej' else n - k} z {n} meczów rywali {rywal}")
            if czesci and _istotny(m):
                out.append({"nazwa": "Linia w historii", "mnoznik": m,
                            "opis": f"{'Powyżej' if strona == 'powyzej' else 'Poniżej'} "
                                    f"{_l(linia)}: " + ", ".join(czesci)})
    # najpierw fakt (spodziewana liczba), potem najsilniejsze za, potem przeciw
    baza = [c for c in out if c["mnoznik"] is None]
    za = sorted((c for c in out if c["mnoznik"] is not None and c["mnoznik"] > 1),
                key=lambda c: -c["mnoznik"])
    przeciw = sorted((c for c in out if c["mnoznik"] is not None and c["mnoznik"] < 1),
                     key=lambda c: c["mnoznik"])
    return baza + za + przeciw
