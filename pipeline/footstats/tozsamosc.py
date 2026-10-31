"""TOŻSAMOŚĆ: numery FotMob → numery statshub/Sofascore (etap 3, docs/plan-fotmob.md).

Po co
-----
Cała pamięć pipeline'u stoi na numerach Sofascore (statshub): księga typów,
`trend_lib`, magazyn drużyn `hd_*`, profile, formy, sędziowie. Właściciel
30.10: numery Sofascore ZOSTAJĄ kanoniczne – zero migracji historii. Mecz
z FotMob dostaje więc numery Sofascore swoich drużyn i zawodników, a historia
sprzed 29.10 ciągnie się dalej bez szwu.

Jak budujemy mapę (na meczach sprzed 29.10, które mają oba źródła)
------------------------------------------------------------------
* **Drużyny – po terminarzu, nie po nazwie.** Nazwy w dwóch źródłach bywają
  zupełnie inne („Chivas” / „CD Guadalajara”, „OB” / „Odense Boldklub”), a
  nazw Sofascore znamy tylko część. Za to godziny startu i strony (gospodarz /
  gość) z kilku tygodni to odcisk drużyny. Głosujemy na poziomie MECZU:
  mecz FotMob wybiera ten mecz Sofascore o tej samej porze, którego obie
  drużyny najlepiej pasują, i tak w kółko, aż wybory przestaną się zmieniać.
* **Weryfikacja przez rywali.** Sam czas daje przypadki (liga duńska i
  3. Liga grają o tej samej godzinie – „Hallescher = Silkeborg” przeszedł
  głosowanie). Para zostaje tylko wtedy, gdy w meczach z ≥ 2 RÓŻNYMI rywalami
  rywal też jest zmapowany i pasuje. Cała liga dopasowana do innej ligi
  wymagałaby identycznego terminarza par – to się nie zdarza.
* **Propagacja.** Drużyna z jednym meczem w oknie (puchar, reprezentacja)
  dostaje parę, gdy jej rywal jest pewny, a mecz Sofascore jednoznaczny
  i żaden inny jej mecz temu nie przeczy.
* **Zawodnicy – po nazwisku w obrębie meczu.** Kandydaci to zawodnicy OBU
  drużyn meczu (statshub potrafi zapisać zawodnika pod drużyną rywala),
  dopasowanie 1:1 od najpodobniejszych. Gdy znamy grę Sofascore z tego meczu
  (minuty), rozstrzyga też dublety (statshub ma czasem dwa numery jednej
  osoby). Remis = niejednoznaczny → do przeglądu, nie zgadujemy.

Byty bez odpowiednika (nowi zawodnicy, drużyny spoza dawnego zakresu):
numer zastępczy `ZASTEPCZY + id FotMob` (4·10⁹ – nie zderza się z Sofascore
< 10⁸ ani z `PID_SYNTETYCZNY` 9·10⁸ w rozliczaniu).

⚑ Decyzja raz zapisana jest STAŁA. Mapa tylko rośnie – zmiana pary zawodnika
po fakcie rozcięłaby jego historię na dwie.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from . import supa

KLUCZ = "fm_tozsamosc"
WERSJA = 1
ZASTEPCZY = 4_000_000_000

# numery nadawane przez nasze rozliczanie zawodnikom spoza statshub
# (`rozliczanie.PID_SYNTETYCZNY`) – przy dublecie wygrywa numer prawdziwy
PID_SYNTETYCZNY = 900_000_000

TOL_STARTU_S = 300            # ta sama pora meczu w obu źródłach
TOL_MECZU_PO_PARZE_S = 2 * 86400   # mecz po parze drużyn (przesunięta godzina)
ITERACJE_GLOSOW = 15
MIN_RYWALI = 2                # weryfikacja przez rywali
PROG_NAZWISKA = 0.8


def zastepczy(fm_id: int) -> int:
    return ZASTEPCZY + int(fm_id)


def czy_zastepczy(sh_id: int) -> bool:
    return int(sh_id or 0) >= ZASTEPCZY


# --------------------------------------------------------------- nazwy ----
# litery, których NFKD nie rozkłada (ø, æ, ł…) – bez tego „Bjørn” = „bjrn”
_TRANSLIT = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
                           "ß": "ss", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D", "ð": "d",
                           "þ": "th", "ı": "i", "-": " ", "'": "", "’": "", "`": ""})
# człony, które nie odróżniają osób
_PARTYKULY = {"de", "da", "do", "dos", "das", "del", "la", "le", "el", "al", "van", "der", "den",
              "von", "di", "du", "jr", "junior", "bin", "ben", "y", "e"}


def norm_nazwy(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").translate(_TRANSLIT))
    s = s.encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", s))


def podobienstwo_nazwisk(a: str, b: str) -> float:
    """0–1. Pełna zgodność 1; jedna nazwa zawiera drugą („John Montaño” /
    „John Edwin Montaño”, „Tissi” / „Vitor Gonçalves Tissi”) 0,92; to samo
    nazwisko i inicjał („M. Gjerstrøm”) 0,9; dalej podobieństwo napisów."""
    na, nb = norm_nazwy(a), norm_nazwy(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = na.split(), nb.split()
    sa, sb = set(ta) - _PARTYKULY, set(tb) - _PARTYKULY
    if sa and sb and (sa <= sb or sb <= sa):
        return 0.92
    if ta[-1] == tb[-1] and ta[0][0] == tb[0][0]:
        return 0.9
    # sama zgodność napisu: „Sayed Abu Farkhi” / „Saied Abu Farchi” (0,875)
    # przechodzi, „Takeshi Wada” / „Takashi Sawada” (0,846 – dwie osoby) nie
    r = SequenceMatcher(None, na, nb).ratio()
    return r * 0.95 if r >= 0.86 else r * 0.85


# -------------------------------------------------------------- drużyny ----
def eventy_z_magazynu(hd: dict) -> dict[int, dict]:
    """Magazyn drużyn statshub (`hd_*`: {team_id: {"m": [{e, t, h, o, l}]}})
    → {id meczu Sofascore: {t, h, a, l}}."""
    ev: dict[int, dict] = {}
    for tid, rec in (hd or {}).items():
        for m in (rec or {}).get("m") or []:
            if not m.get("e") or not m.get("t"):
                continue
            t, o = int(tid), int(m.get("o") or 0)
            h, a = (t, o) if m.get("h") == 1 else (o, t)
            ev[int(m["e"])] = {"t": int(m["t"]), "h": h, "a": a, "l": m.get("l")}
    return ev


def mapuj_druzyny(mecze_fm: list[dict], eventy: dict[int, dict]) -> dict:
    """Mecze FotMob z terminarza (`fotmob.mecze_dnia`) + mecze Sofascore
    (`eventy_z_magazynu`) → {"druzyny": {fm: sh}, "mecze": {fm: sh},
    "rozgrywki": {liga fm: utid}, "raport": {...}}."""
    fm = [m for m in mecze_fm if m.get("status") not in ("postponed", "canceled", "abandoned")
          and m.get("home_id") and m.get("away_id") and m.get("start_ts")]
    if not fm:
        return {"druzyny": {}, "mecze": {}, "rozgrywki": {}, "raport": {}}
    pocz = min(m["start_ts"] for m in fm) - 2 * TOL_STARTU_S
    kon = max(m["start_ts"] for m in fm) + 2 * TOL_STARTU_S
    ev = {e: v for e, v in eventy.items() if pocz <= v["t"] <= kon and v["h"] and v["a"]}
    kubly: dict[int, list[int]] = defaultdict(list)
    for e, v in ev.items():
        kubly[v["t"] // 600].append(e)

    def o_tej_porze(ts: int) -> list[int]:
        return [e for b in (ts // 600 - 1, ts // 600, ts // 600 + 1)
                for e in kubly.get(b, ()) if abs(ev[e]["t"] - ts) <= TOL_STARTU_S]

    kand = {m["id"]: o_tej_porze(m["start_ts"]) for m in fm}

    # 1) głosy na poziomie meczu, aż wybory przestaną się zmieniać
    glosy: dict[int, Counter] = defaultdict(Counter)
    for m in fm:
        for e in kand[m["id"]]:
            glosy[m["home_id"]][ev[e]["h"]] += 1
            glosy[m["away_id"]][ev[e]["a"]] += 1
    for _ in range(ITERACJE_GLOSOW):
        nowe: dict[int, Counter] = defaultdict(Counter)
        for m in fm:
            oc = sorted(((glosy[m["home_id"]][ev[e]["h"]] + glosy[m["away_id"]][ev[e]["a"]], e)
                         for e in kand[m["id"]]), reverse=True)
            if not oc or oc[0][0] <= 0 or (len(oc) > 1 and oc[1][0] == oc[0][0]):
                continue
            e = oc[0][1]
            nowe[m["home_id"]][ev[e]["h"]] += 1
            nowe[m["away_id"]][ev[e]["a"]] += 1
        if nowe == glosy:
            break
        glosy = nowe
    mapa = {f: c.most_common(1)[0][0] for f, c in glosy.items() if c}

    # 2) weryfikacja przez rywali
    mecze_druzyny: dict[int, list[tuple[dict, str, int]]] = defaultdict(list)
    for m in fm:
        mecze_druzyny[m["home_id"]].append((m, "h", m["away_id"]))
        mecze_druzyny[m["away_id"]].append((m, "a", m["home_id"]))

    def zgodne(f: int, s: int, mp: dict) -> tuple[int, int]:
        n, rywale = 0, set()
        for m, st, fo in mecze_druzyny[f]:
            so = mp.get(fo)
            if so is None:
                continue
            dr = "a" if st == "h" else "h"
            if any(ev[e][st] == s and ev[e][dr] == so for e in kand[m["id"]]):
                n += 1
                rywale.add(fo)
        return n, len(rywale)

    for _ in range(20):
        nowa = {f: s for f, s in mapa.items() if zgodne(f, s, mapa)[1] >= MIN_RYWALI}
        po_sh: dict[int, list[int]] = defaultdict(list)
        for f, s in nowa.items():
            po_sh[s].append(f)
        for s, fs in po_sh.items():
            if len(fs) > 1:     # dwie drużyny FotMob na jedną Sofascore: zostaje pewniejsza
                oc = sorted(((zgodne(f, s, nowa)[0], f) for f in fs), reverse=True)
                for _, f in (oc[1:] if oc[0][0] > oc[1][0] else oc):
                    nowa.pop(f, None)
        if nowa == mapa:
            break
        mapa = nowa
    zweryfikowane = len(mapa)

    # 3) propagacja na drużyny z jednym meczem w oknie
    for _ in range(10):
        zajete = set(mapa.values())
        dodane = 0
        for m in fm:
            for f, st, fo in ((m["home_id"], "h", m["away_id"]), (m["away_id"], "a", m["home_id"])):
                if f in mapa or fo not in mapa:
                    continue
                dr = "a" if st == "h" else "h"
                tr = [e for e in kand[m["id"]] if ev[e][dr] == mapa[fo]]
                if len(tr) != 1 or ev[tr[0]][st] in zajete:
                    continue
                s = ev[tr[0]][st]
                przeczy = False
                for m2, st2, fo2 in mecze_druzyny[f]:
                    if m2 is m or fo2 not in mapa:
                        continue
                    dr2 = "a" if st2 == "h" else "h"
                    z_rywalem = [e for e in kand[m2["id"]] if ev[e][dr2] == mapa[fo2]]
                    if z_rywalem and not any(ev[e][st2] == s for e in z_rywalem):
                        przeczy = True
                        break
                if przeczy:
                    continue
                mapa[f] = s
                zajete.add(s)
                dodane += 1
        if not dodane:
            break

    # 4) mecze: para drużyn (godzina mogła się przesunąć)
    po_parze: dict[tuple[int, int], list[int]] = defaultdict(list)
    for e, v in eventy.items():
        po_parze[(v["h"], v["a"])].append(e)
    mecze: dict[int, int] = {}
    for m in fm:
        sh, sa = mapa.get(m["home_id"]), mapa.get(m["away_id"])
        if not sh or not sa:
            continue
        tr = [e for e in po_parze.get((sh, sa), ())
              if abs(eventy[e]["t"] - m["start_ts"]) <= TOL_MECZU_PO_PARZE_S]
        if len(tr) == 1:
            mecze[m["id"]] = tr[0]

    # 5) rozgrywki: liga FotMob → utid z większości zmapowanych meczów
    gl_lig: dict[int, Counter] = defaultdict(Counter)
    for m in fm:
        e = mecze.get(m["id"])
        if e is not None and eventy[e].get("l"):
            # oba poziomy: liga nadrzędna (wspólna dla grup – remis odpada)
            # i grupa (Serie C Grp. A = jedno utid Sofascore)
            for liga in {m.get("liga_id"), m.get("liga_grupa")} - {None, 0}:
                gl_lig[int(liga)][int(eventy[e]["l"])] += 1
    rozgrywki = {}
    for liga, c in gl_lig.items():
        (u, n), *reszta = c.most_common(2)
        if n >= 2 and (not reszta or reszta[0][1] * 3 < n):
            rozgrywki[liga] = u

    return {"druzyny": mapa, "mecze": mecze, "rozgrywki": rozgrywki,
            "raport": {"mecze_fm": len(fm), "mecze_sh_w_oknie": len(ev),
                       "druzyny_zweryfikowane": zweryfikowane,
                       "druzyny_z_propagacji": len(mapa) - zweryfikowane,
                       "mecze_zmapowane": len(mecze), "rozgrywki": len(rozgrywki)}}


def nazwy_druzyn_sh(trend_lib: dict | None = None, ksiega: dict | None = None,
                    zakres: list | None = None, eventy: dict[int, dict] | None = None) -> dict[int, str]:
    """Nazwy drużyn Sofascore, jakie mamy: `trend_lib` (drużyna i rywal),
    księga typów i zakres meczów („Gospodarz – Gość” + numer meczu → strony
    z `eventy`)."""
    n: dict[int, str] = {}
    for v in (trend_lib or {}).values():
        if v.get("team_id") and v.get("team_name"):
            n[int(v["team_id"])] = v["team_name"]
        if v.get("opponent_id") and v.get("opponent_name"):
            n.setdefault(int(v["opponent_id"]), v["opponent_name"])
    ev = eventy or {}
    for r in (ksiega or {}).values():
        e, s = r.get("mecz_id"), str(r.get("mecz") or "")
        if e in ev and " – " in s:
            a, b = s.split(" – ", 1)
            n.setdefault(ev[e]["h"], a)
            n.setdefault(ev[e]["a"], b)
    for r in zakres or []:
        if r.get("id") in ev:
            n.setdefault(ev[r["id"]]["h"], r.get("gospodarz") or "")
            n.setdefault(ev[r["id"]]["a"], r.get("gosc") or "")
    return {k: v for k, v in n.items() if v}


# ⚑ MECZE ZNANE ZE STATSHUB (cykl próbny 31.10). Typy opublikowane do 29.10 na
# mecze po tej dacie zostają na stronie pod numerem Sofascore, a mapa meczów zna
# tylko mecze z `hd_*` (rozegrane). Bez tej pary ten sam mecz z terminarza FotMob
# dostawał numer zastępczy: 22 mecze dwa razy na stronie, typy pod dwoma numerami
# (limit „3 na mecz” i „jedna linia na stronę” nie widziały dubla), a typ sprzed
# przełączenia nie miałby czym się rozliczyć.
def znane_mecze_sofascore(zakres: list | None, ksiega: dict | None,
                          od_ts: int = 0) -> list[tuple[int, int, str, str]]:
    """[(numer meczu Sofascore, start, gospodarz, gość)] z zapisu zakresu meczów
    cyklu statshub i z księgi typów (mecz „A – B”), start ≥ `od_ts`."""
    out: dict[int, tuple[int, int, str, str]] = {}
    for r in zakres or []:
        try:
            e, k = int(r.get("id") or 0), int(r.get("kickoff_ts") or 0)
        except (TypeError, ValueError):
            continue
        if e and k >= od_ts and r.get("gospodarz") and r.get("gosc") and not czy_zastepczy(e):
            out[e] = (e, k, str(r["gospodarz"]), str(r["gosc"]))
    for r in (ksiega or {}).values():
        try:
            e, k = int(r.get("mecz_id") or 0), int(r.get("kickoff_ts") or 0)
        except (TypeError, ValueError):
            continue
        s = str(r.get("mecz") or "")
        if e and e not in out and k >= od_ts and " – " in s and not czy_zastepczy(e):
            a, b = s.split(" – ", 1)
            out[e] = (e, k, a.strip(), b.strip())
    return list(out.values())


def dopasuj_mecze_znane(t: "Tozsamosc", mecze_fm: list[dict], znane, nazwy: dict[int, str],
                        tol_s: int = TOL_MECZU_PO_PARZE_S) -> tuple[int, Counter]:
    """Mecz FotMob bez pary w mapie ← znany mecz Sofascore z `znane`, gdy OBIE
    zmapowane drużyny zgadzają się z nazwami Sofascore (≥ PROG_NAZWISKA – jak
    nazwiska, każda strona osobno) i start różni się najwyżej o `tol_s`
    (przełożona godzina; drużyna nie gra dwa razy w dwa dni). Para jednoznaczna:
    przy dwóch kandydatach równie dobrych mecz zostaje zastępczy. Dopisuje do
    `t.mecze`; zwraca (ile dopisano, liczniki)."""
    licz: Counter = Counter()
    zajete = set(t.mecze.values())
    n = 0
    for m in mecze_fm:
        try:
            fid, ts = int(m["id"]), int(m.get("start_ts") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if fid in t.mecze:
            continue
        h, a = t.druzyny.get(int(m.get("home_id") or 0)), t.druzyny.get(int(m.get("away_id") or 0))
        if not h or not a or not nazwy.get(h) or not nazwy.get(a):
            licz["bez_druzyn"] += 1
            continue
        kand = []
        for e, k, nh, na in znane:
            if e in zajete or abs(k - ts) > tol_s:
                continue
            ph, pa = podobienstwo_nazwisk(nazwy[h], nh), podobienstwo_nazwisk(nazwy[a], na)
            if ph >= PROG_NAZWISKA and pa >= PROG_NAZWISKA:
                kand.append((-(ph + pa), abs(k - ts), e))
        if not kand:
            licz["bez_znanego"] += 1
            continue
        kand.sort()
        if len(kand) > 1 and kand[1][:2] == kand[0][:2]:
            licz["niejednoznaczne"] += 1
            continue
        t.mecze[fid] = kand[0][2]
        zajete.add(kand[0][2])
        n += 1
        licz["dopasowane"] += 1
    t.__dict__.pop("_odwr_mecze", None)
    return n, licz


def dopasuj_druzyny_po_nazwie(mecze_fm: list[dict], eventy: dict[int, dict],
                              nazwy_sh: dict[int, str], druzyny: dict[int, int]) -> dict[int, int]:
    """Zapas dla drużyn, których terminarz nie rozstrzygnął (reprezentacje
    z 1–2 meczami w oknie, ligi bez meczów w magazynie `hd_*`): ta sama nazwa
    po normalizacji („Şanlıurfaspor” = „Sanliurfaspor”), JEDYNA w obu
    źródłach („Olimpia” jest w Paragwaju i Hondurasie – odpada) i bez
    sprzeczności z godzinami: gdy drużyna Sofascore grała w oknie, któryś
    jej mecz musi się zgadzać z meczem drużyny FotMob."""
    fm_nazwa: dict[int, str] = {}
    fm_starty: dict[int, list[int]] = defaultdict(list)
    for m in mecze_fm:
        for k in ("home", "away"):
            if m.get(f"{k}_id"):
                fm_nazwa[m[f"{k}_id"]] = m.get(k) or ""
                fm_starty[m[f"{k}_id"]].append(int(m.get("start_ts") or 0))
    if not fm_starty:
        return {}
    pocz = min(min(v) for v in fm_starty.values())
    kon = max(max(v) for v in fm_starty.values())
    idx_fm: dict[str, set[int]] = defaultdict(set)
    for f, n in fm_nazwa.items():
        idx_fm[norm_nazwy(n)].add(f)
    idx_sh: dict[str, set[int]] = defaultdict(set)
    for s, n in nazwy_sh.items():
        idx_sh[norm_nazwy(n)].add(s)
    sh_starty: dict[int, list[int]] = defaultdict(list)
    for v in eventy.values():
        if pocz <= v["t"] <= kon:
            sh_starty[v["h"]].append(v["t"])
            sh_starty[v["a"]].append(v["t"])
    zajete = set(druzyny.values())
    out: dict[int, int] = {}
    for s, n in nazwy_sh.items():
        k = norm_nazwy(n)
        if s in zajete or not k or len(idx_sh[k]) != 1 or len(idx_fm.get(k, ())) != 1:
            continue
        f = next(iter(idx_fm[k]))
        if f in druzyny or f in out:
            continue
        if sh_starty.get(s) and not any(abs(a - b) <= TOL_STARTU_S
                                        for a in sh_starty[s] for b in fm_starty[f]):
            continue
        out[f] = s
    return out


# ------------------------------------------------------------ zawodnicy ----
def zawodnicy_z_trend_lib(trend_lib: dict) -> dict[int, dict]:
    """`trend_lib` ({"pid:rynek": rekord}) → {pid: {name, team, ost, gry: {ts: minuty}}}."""
    out: dict[int, dict] = {}
    for rec in (trend_lib or {}).values():
        try:
            pid = int(rec.get("player_id") or 0)
        except (TypeError, ValueError):
            continue
        if not pid:
            continue
        z = out.setdefault(pid, {"name": rec.get("player_name") or "", "poz": rec.get("position"),
                                 "team": int(rec.get("team_id") or 0), "ost": 0, "gry": {}})
        for ts, mi in zip(rec.get("timestamps") or [], rec.get("minutes") or []):
            z["gry"][int(ts)] = float(mi or 0)
            z["ost"] = max(z["ost"], int(ts))
    return out


def kadry(zawodnicy: dict[int, dict]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = defaultdict(list)
    for pid, z in zawodnicy.items():
        if z.get("team"):
            out[z["team"]].append(pid)
    return dict(out)


def indeks_nazw(zawodnicy: dict[int, dict]) -> dict[str, list[int]]:
    """{nazwa znormalizowana: [pid]} – do zawodników zapisanych pod starą
    drużyną (transfer, wypożyczenie)."""
    out: dict[str, list[int]] = defaultdict(list)
    for pid, z in zawodnicy.items():
        n = norm_nazwy(z.get("name"))
        if n:
            out[n].append(pid)
    return dict(out)


def _prawdziwe(pidy) -> list[int]:
    """Numery Sofascore bez naszych syntetycznych – o ile jakiś prawdziwy jest."""
    p = [x for x in pidy if x < PID_SYNTETYCZNY]
    return p or list(pidy)


def _gra_w_meczu(z: dict, ts: int) -> float | None:
    """Minuty zawodnika Sofascore w meczu o starcie `ts` (None = brak gry)."""
    for t, mi in (z.get("gry") or {}).items():
        if abs(t - ts) <= 3 * 3600:
            return mi
    return None


def mapuj_zawodnikow_meczu(rek: dict, sh_home: int, sh_away: int, zawodnicy: dict[int, dict],
                           kadry_sh: dict[int, list[int]], zajete: set[int] | None = None,
                           indeks: dict[str, list[int]] | None = None
                           ) -> tuple[dict[int, tuple[int, float]], dict[int, list[int]]]:
    """Zawodnicy meczu FotMob (`fotmob.mecz_do_bazy`) → numery Sofascore.

    Zwraca ({pid FotMob: (pid Sofascore, ocena)}, {pid FotMob: [remisujący kandydaci]}).
    `zajete` – numery Sofascore już przypisane innym zawodnikom FotMob (mapa
    jest 1:1, więc ich nie proponujemy). `indeks` (`indeks_nazw`) – zawodnik
    spoza kadr obu drużyn (transfer po ostatniej aktualizacji statshub)
    wchodzi tylko z dowodem: pełna nazwa JEDYNA w całej bazie i gra Sofascore
    w tym meczu z tymi samymi minutami. Sama unikalność nazwy nie wystarcza –
    „Carlos Hernández” czy „Juan Pérez” są u nas jedyni, na świecie nie."""
    zajete = zajete or set()
    druzyna_sh = {rek["home"]["id"]: sh_home, rek["away"]["id"]: sh_away}
    pula = [p for t in {sh_home, sh_away} if t for p in kadry_sh.get(t, ()) if p not in zajete]
    w_puli = set(pula)
    nazwa_fm = {z["pid"]: z["name"] for z in rek.get("zawodnicy") or []}
    pary = []
    for z in rek.get("zawodnicy") or []:
        wlasna = druzyna_sh.get(z["team_id"])
        kand = list(pula)
        if indeks:
            n = norm_nazwy(z["name"])
            obcy = _prawdziwe([p for p in indeks.get(n, ()) if p not in w_puli and p not in zajete])
            if len(obcy) == 1 and len(n.split()) >= 2:
                mi = _gra_w_meczu(zawodnicy[obcy[0]], rek["ts"])
                if mi is not None and abs(mi - z["minuty"]) <= 3:
                    kand.append(obcy[0])
        for pid in kand:
            zs = zawodnicy[pid]
            p = podobienstwo_nazwisk(z["name"], zs["name"])
            if p < PROG_NAZWISKA:
                continue
            ocena = p
            if pid not in w_puli:
                ocena -= 0.1           # spoza obu kadr: tylko przy pełnej, jedynej nazwie
            elif zs["team"] != wlasna:
                ocena -= 0.05          # zapisany pod rywalem: dopuszczamy, ale słabiej
            mi = _gra_w_meczu(zs, rek["ts"])
            if mi is not None:
                # Sofascore zna jego grę w TYM meczu – zgodne minuty to najlepszy dowód
                ocena += 0.3 if abs(mi - z["minuty"]) <= 15 or (mi > 0) == (z["minuty"] > 0) else -0.3
            pary.append((round(ocena, 4), z["pid"], pid, zs["ost"]))
    pary.sort(key=lambda x: (x[0], x[3]), reverse=True)
    naj: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for ocena, fid, pid, _ in pary:
        naj[fid].append((ocena, pid))
    wynik: dict[int, tuple[int, float]] = {}
    niejedn: dict[int, list[int]] = {}
    uzyte: set[int] = set()
    for ocena, fid, pid, _ in pary:
        if fid in wynik or fid in niejedn or pid in uzyte:
            continue
        remis = [pp for q, pp in naj[fid] if pp != pid and pp not in uzyte and q == ocena]
        if remis:
            # dwa numery z identyczną oceną. Dubel jednej osoby (statshub
            # potrafi mieć „T. Bramble” i „Thomas-James Bramble”, my – numer
            # syntetyczny obok prawdziwego): wygrywa prawdziwy, potem dłuższa
            # historia. Dwie RÓŻNE osoby („Danilo Santos” / „Danilo Pereira”
            # dla „Danilo”) – przegląd, nie zgadujemy
            grupa = [pid] + remis
            if all(podobienstwo_nazwisk(zawodnicy[pid]["name"], zawodnicy[pp]["name"]) >= 0.9
                   for pp in remis):
                pid = max(_prawdziwe(grupa), key=lambda pp: (len(zawodnicy[pp]["gry"]), zawodnicy[pp]["ost"]))
            else:
                niejedn[fid] = grupa
                continue
        if pid >= PID_SYNTETYCZNY:
            # nasz numer syntetyczny (z rozliczania, 3 mecze) przegrywa z prawdziwym
            # numerem tej osoby, nawet gdy to syntetyczny „ma” ten mecz – prawdziwy
            # niesie długą historię („Sebastián Sáez” 15 meczów vs 3)
            prawdziwi = [(q, pp) for q, pp in naj[fid] if pp < PID_SYNTETYCZNY and pp not in uzyte
                         and podobienstwo_nazwisk(nazwa_fm[fid], zawodnicy[pp]["name"]) >= PROG_NAZWISKA]
            if prawdziwi:
                pid = max(prawdziwi, key=lambda x: (x[0], len(zawodnicy[x[1]]["gry"])))[1]
        wynik[fid] = (pid, ocena)
        uzyte.add(pid)

    # pseudonimy („Cebolinha” / „Everton”): nazwa nie pomoże, ale gdy Sofascore
    # zna grę w TYM meczu, jednoznaczne minuty + pozycja w tej samej drużynie
    # rozstrzygają. Tylko pozostali bez pary i tylko para jedyna w obie strony
    for fm_team, sh_team in druzyna_sh.items():
        if not sh_team:
            continue
        fm_wolni = [z for z in rek.get("zawodnicy") or [] if z["team_id"] == fm_team
                    and z["pid"] not in wynik and z["pid"] not in niejedn and z["minuty"] > 0]
        sh_wolni = []
        for pid in kadry_sh.get(sh_team, ()):
            if pid in uzyte or pid in zajete:
                continue
            mi = _gra_w_meczu(zawodnicy[pid], rek["ts"])
            if mi:
                sh_wolni.append((pid, mi))
        if not fm_wolni or not sh_wolni:
            continue

        def pasuje(z, pid, mi):
            poz = zawodnicy[pid].get("poz")
            return abs(mi - z["minuty"]) <= 1 and (not poz or not z.get("poz") or poz == z["poz"])

        def nazwisko(s):
            t = norm_nazwy(s).split()
            return t[-1] if t else ""
        # najpierw to samo nazwisko i minuty ±3 („Christian Ebere” / „Osinachi Ebere”),
        # jedyne w obie strony – minuty 90 dzieli pół składu, nazwisko już nie
        for z in fm_wolni:
            tr = [pid for pid, mi in sh_wolni if pid not in uzyte and abs(mi - z["minuty"]) <= 3
                  and nazwisko(zawodnicy[pid]["name"]) == nazwisko(z["name"])]
            if len(tr) == 1 and sum(1 for z2 in fm_wolni if z2["pid"] not in wynik
                                    and nazwisko(z2["name"]) == nazwisko(z["name"])) == 1:
                wynik[z["pid"]] = (tr[0], 0.6)
                uzyte.add(tr[0])
        for z in fm_wolni:
            if z["pid"] in wynik:
                continue
            tr = [(pid, mi) for pid, mi in sh_wolni if pid not in uzyte and pasuje(z, pid, mi)]
            if len(tr) != 1:
                continue
            pid, mi = tr[0]
            if sum(1 for z2 in fm_wolni if pasuje(z2, pid, mi)) != 1:
                continue
            wynik[z["pid"]] = (pid, 0.5)
            uzyte.add(pid)
    return wynik, niejedn


# ---------------------------------------------------------------- mapa ----
class Tozsamosc:
    """Mapa tożsamości w pamięci + zapis/odczyt w magazynie (`fm_tozsamosc`).

    Zapis: {"wersja", "druzyny": {fm: sh}, "zawodnicy": {fm: sh | 0},
    "nazwy": {fm pid: nazwisko FotMob}, "mecze": {fm: sh}, "rozgrywki":
    {liga fm: utid}, "niejednoznaczne": {fm pid: [kandydaci sh]},
    "kolizje": {fm pid: [inne nazwiska pod tym numerem]}, "przetworzone":
    [mecze FotMob, których zawodników już mapowaliśmy – budowa nie pyta o nie drugi raz].

    0 przy zawodniku = sprawdzony, bez pary (numer zastępczy) – decyzja
    stała, nie dopasowujemy go ponownie.

    ⚑ NUMER FOTMOB NIE ZAWSZE JEST JEDNĄ OSOBĄ (31.10, 9 na 18 775 numerów
    z 634 meczów): FotMob użył ponownie numerów ~750 000–760 000 –
    750027 to „Brahim Díaz” w Realu i „Fabricio Perez” na ławce w Boliwii.
    Dlatego przy numerze pamiętamy nazwisko, a wiersz z tym numerem i INNYM
    nazwiskiem jest kolizją (`wiersz_zgodny` = False) – nie dokleja się do
    cudzej historii."""

    def __init__(self, dane: dict | None = None):
        d = dane or {}
        self.druzyny = {int(k): int(v) for k, v in (d.get("druzyny") or {}).items()}
        self.zawodnicy = {int(k): int(v) for k, v in (d.get("zawodnicy") or {}).items()}
        self.nazwy = {int(k): str(v) for k, v in (d.get("nazwy") or {}).items()}
        self.mecze = {int(k): int(v) for k, v in (d.get("mecze") or {}).items()}
        self.rozgrywki = {int(k): int(v) for k, v in (d.get("rozgrywki") or {}).items()}
        self.niejednoznaczne = {int(k): [int(x) for x in v]
                                for k, v in (d.get("niejednoznaczne") or {}).items()}
        self.kolizje = {int(k): list(v) for k, v in (d.get("kolizje") or {}).items()}
        self.przetworzone = {int(x) for x in d.get("przetworzone") or []}

    # --- odczyt numerów -----------------------------------------------------
    def id_druzyny(self, fm_id: int) -> int:
        return self.druzyny.get(int(fm_id)) or zastepczy(fm_id)

    def id_zawodnika(self, fm_pid: int) -> int:
        return self.zawodnicy.get(int(fm_pid)) or zastepczy(fm_pid)

    def wiersz_zgodny(self, fm_pid: int, nazwa: str) -> bool:
        """Czy wiersz meczu (numer + nazwisko) to osoba, którą znamy pod tym
        numerem. Numer jeszcze nieznany – tak (nie ma z czym się kłócić)."""
        znana = self.nazwy.get(int(fm_pid))
        return znana is None or podobienstwo_nazwisk(znana, nazwa) >= PROG_NAZWISKA

    def id_meczu(self, fm_mid: int) -> int:
        return self.mecze.get(int(fm_mid)) or zastepczy(fm_mid)

    def utid(self, liga_fm: int, grupa_fm: int | None = None) -> int | None:
        """utid rozgrywek: najpierw grupa (Serie C Grp. A), potem liga nadrzędna."""
        return self.rozgrywki.get(int(grupa_fm or 0)) or self.rozgrywki.get(int(liga_fm or 0))

    def mecz_fm(self, sh_eid: int) -> int | None:
        """Odwrotnie: mecz Sofascore (np. typ sprzed przełączenia) → mecz FotMob."""
        if not hasattr(self, "_odwr_mecze"):
            self._odwr_mecze = {v: k for k, v in self.mecze.items()}
        return self._odwr_mecze.get(int(sh_eid))

    # --- budowa ---------------------------------------------------------------
    def dodaj_druzyny(self, wynik: dict) -> int:
        """Dopisz wynik `mapuj_druzyny`. Istniejących par nie zmieniamy;
        para, której drużyna Sofascore jest już zajęta, przepada."""
        n = 0
        zajete = set(self.druzyny.values())
        for f, s in wynik.get("druzyny", {}).items():
            if int(f) not in self.druzyny and int(s) not in zajete:
                self.druzyny[int(f)] = int(s)
                zajete.add(int(s))
                n += 1
        for f, s in wynik.get("mecze", {}).items():
            self.mecze.setdefault(int(f), int(s))
        for f, u in wynik.get("rozgrywki", {}).items():
            self.rozgrywki.setdefault(int(f), int(u))
        self.__dict__.pop("_odwr_mecze", None)
        return n

    def _kolizja(self, fid: int, nazwa: str, licz: Counter) -> None:
        licz["kolizja_numeru"] += 1
        lst = self.kolizje.setdefault(fid, [])
        if nazwa not in lst:
            lst.append(nazwa)

    def dodaj_mecz(self, rek: dict, zawodnicy: dict[int, dict], kadry_sh: dict[int, list[int]],
                   indeks: dict[str, list[int]] | None = None, zamknij_brak: bool = False) -> Counter:
        """Zmapuj zawodników jednego meczu FotMob. `zamknij_brak` – zawodnik
        bez pary dostaje stałe 0 (numer zastępczy); bez tej flagi zostaje
        do ponownej próby (budowa mapy na wielu meczach).

        Numer zamknięty bez pary (0), który wraca z INNYM nazwiskiem, może
        jeszcze dostać parę – historia pod numerem zastępczym nie ma wartości,
        a „Brahim Díaz” nie może przegrać z ławką w Boliwii tylko dlatego, że
        ten mecz przyszedł pierwszy. Numer z parą i innym nazwiskiem = kolizja."""
        licz: Counter = Counter()
        if rek.get("id"):
            self.przetworzone.add(int(rek["id"]))
        nowi, sporne = [], set()
        for z in rek.get("zawodnicy") or []:
            fid = z["pid"]
            if fid in self.zawodnicy:
                if self.wiersz_zgodny(fid, z["name"]):
                    continue
                if self.zawodnicy[fid]:
                    self._kolizja(fid, z["name"], licz)
                    continue
                sporne.add(fid)
            elif not self.wiersz_zgodny(fid, z["name"]):
                self._kolizja(fid, z["name"], licz)   # znany numer bez decyzji, inne nazwisko
                continue
            nowi.append(z)
        if not nowi:
            return licz
        sh_home = self.druzyny.get(rek["home"]["id"])
        sh_away = self.druzyny.get(rek["away"]["id"])
        wynik: dict[int, tuple[int, float]] = {}
        niejedn: dict[int, list[int]] = {}
        if sh_home or sh_away:
            zajete = {v for v in self.zawodnicy.values() if v}
            wynik, niejedn = mapuj_zawodnikow_meczu({**rek, "zawodnicy": nowi}, sh_home or 0, sh_away or 0,
                                                    zawodnicy, kadry_sh, zajete, indeks)
        for z in nowi:
            fid = z["pid"]
            if fid in wynik:
                if fid in sporne:          # stara nazwa pod tym numerem to teraz kolizja
                    self._kolizja(fid, self.nazwy.get(fid, ""), licz)
                self.zawodnicy[fid] = wynik[fid][0]
                self.nazwy[fid] = z["name"]
                self.niejednoznaczne.pop(fid, None)
                licz["para"] += 1
            elif fid in sporne:
                self._kolizja(fid, z["name"], licz)
            elif fid in niejedn:
                self.niejednoznaczne[fid] = niejedn[fid]
                self.nazwy.setdefault(fid, z["name"])
                licz["niejednoznaczny"] += 1
            else:
                licz["bez_pary" if sh_home or sh_away else "bez_druzyny"] += 1
                if zamknij_brak:
                    self.zawodnicy[fid] = 0
                    self.nazwy[fid] = z["name"]
        return licz

    # --- zapis ---------------------------------------------------------------
    def do_zapisu(self) -> dict:
        return {"wersja": WERSJA,
                "druzyny": {str(k): v for k, v in sorted(self.druzyny.items())},
                "zawodnicy": {str(k): v for k, v in sorted(self.zawodnicy.items())},
                "nazwy": {str(k): v for k, v in sorted(self.nazwy.items())},
                "mecze": {str(k): v for k, v in sorted(self.mecze.items())},
                "rozgrywki": {str(k): v for k, v in sorted(self.rozgrywki.items())},
                "niejednoznaczne": {str(k): v for k, v in sorted(self.niejednoznaczne.items())},
                "kolizje": {str(k): v for k, v in sorted(self.kolizje.items())},
                "przetworzone": sorted(self.przetworzone)}


def wczytaj() -> tuple[Tozsamosc | None, bool]:
    """(mapa, ok). Awaria odczytu = (None, False) – wtedy NIE budujemy od zera
    i nie zapisujemy (nadpisalibyśmy stałe decyzje pustką)."""
    dane, ok = supa.get_key_ok(KLUCZ)
    if not ok:
        return None, False
    return Tozsamosc(dane), True


def zapisz(t: Tozsamosc) -> bool:
    return bool(supa.put_key(KLUCZ, t.do_zapisu()))
