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


def czynniki(b: dict) -> list[dict]:
    """Czynniki opisu dla typu `b` (rekord listy dnia z `p_uczony.skl`)."""
    pu = b.get("p_uczony") or {}
    skl = pu.get("skl") or {}
    mn = skl.get("mn") or {}
    x = skl.get("x") or {}
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

    if zawodnik:
        if x.get("t12") is not None:
            t3 = f", w ostatnich 3 meczach {_l(x['t3'])}" if x.get("t3") is not None else ""
            dodaj("Tempo", "forma", f"Średnio {_l(x['t12'])} na 90 minut{t3}")
        if x.get("min"):
            dodaj("Minuty gry", "minuty", f"Powinien zagrać ok. {int(x['min'])} minut")
        if x.get("rywal"):
            r = float(x["rywal"])
            ile = abs(round((r - 1.0) * 100))
            if ile >= 5:
                dodaj("Rywal", "rywal",
                      f"Przeciw {rywal} zawodnicy na tej pozycji mają o {ile}% "
                      f"{'więcej' if r > 1 else 'mniej'} niż średnio w lidze")
        dodaj("Gdzie gra", "dom", "Gra u siebie" if x.get("dom") else "Gra na wyjeździe")
        if pu.get("pkw") is not None and pu.get("pkn"):
            n = int(pu["pkn"])
            k = round(float(pu["pkw"]) * n)
            k = k if strona == "powyzej" else n - k
            out.append({"nazwa": "Ostatnie mecze", "mnoznik": None,
                        "opis": f"{'Powyżej' if strona == 'powyzej' else 'Poniżej'} "
                                f"{_l(linia)} w {k} z {n} ostatnich meczów"})
    else:
        if x.get("w12") is not None:
            w6 = f", w ostatnich 6 – {_l(x['w6'])}" if x.get("w6") is not None else ""
            dodaj("Forma", "forma", f"Średnio {_l(x['w12'])} w ostatnich 12 meczach{w6}")
        dom = x.get("dom")
        gdzie = "Gra u siebie" if dom else "Gra na wyjeździe"
        if x.get("w_dom") is not None:
            gdzie += f" – w takich meczach średnio {_l(x['w_dom'])}"
        dodaj("Gdzie gra", "dom", gdzie)
        if x.get("opp12") is not None:
            dodaj("Rywal", "rywal", f"Przeciw {rywal} drużyny mają średnio {_l(x['opp12'])}")
        if x.get("liga") is not None:
            dodaj("Liga", "liga", f"Średnia w tej lidze {_l(x['liga'])}")
        styl = [n for n, _ in (skl.get("styl") or [])]
        if styl:
            dodaj("Styl gry", "styl", "Styl gry drużyny: " + " i ".join(styl))
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
