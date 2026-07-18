"""Źródło kursów: STS — klient WebSocket (czysty Python, bez przeglądarki).

STS udostępnia ofertę wyłącznie po WebSocket. Protokół rozpracowany 2026-07-03:

  * URL:  wss://www.sts.pl/sbk/api/sbk  (nagłówek Origin: https://www.sts.pl)
  * handshake:
      {"t":1,"b":{"place.rsp":0,"session":0,"slips.rsp":0,"cashout":0}}
      {"t":4,"s":1}
  * subskrypcja meczu (KLUCZOWE: propsy zawodnicze są na kanale rcm_{id}):
      {"t":1,"u":[{"s":"i_pl","n":0},{"s":"rcm_global","n":0},
                  {"s":"f_{ID}_pl","n":0},{"s":"rcm_{ID}","n":0}]}
    gdzie ID np. f482692.
  * ramka = dwie linie: nagłówek {"s":kanał,...}\\n ładunek {"B":...}/{"P":...}
  * katalog rynków:  B/S/1/m/{mid}/n = nazwa rynku (np. 2348 = "Zawodnik - strzały")
  * kursy zawodnicze:
      P/{sel}/m/{mid}/l/{lineId}/n           = nazwa linii ("... - 3 lub więcej")
      P/{sel}/m/{mid}/l/{lineId}/o/{oid}/n   = NAZWISKO zawodnika
      P/{sel}/m/{mid}/l/{lineId}/o/{oid}/O   = kurs
    "N lub więcej" => powyżej N-0.5. Bx:true lub bardzo wysoki kurs = zablokowane.

STS ma rynki, których nie ma Superbet: strzały niecelne i zablokowane.
Bierzemy wersje 90-minutowe (bez "(z dogrywką)"), by pasowały do naszych statystyk.
"""

from __future__ import annotations

import json
import re
import time

from curl_cffi import requests as curl_requests

from .superbet import norm_name

WS_URL = "wss://www.sts.pl/sbk/api/sbk"
WS_HEADERS = {
    "Origin": "https://www.sts.pl",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126 Safari/537.36"
    ),
}

# nazwa rynku STS (90-minutowa, bez dogrywki) -> nasz kod
MARKET_MAP = {
    "Zawodnik - strzały": "shots",
    "Zawodnik - celne strzały": "sot",
    "Zawodnik - zablokowane strzały": "shots_blocked",
    "Zawodnik - niecelne strzały": "shots_off_target",
    "Zawodnik - faule popełnione": "fouls_committed",
    "Zawodnik - faule wywalczone": "fouls_won",
    "Zawodnik - odbiory": "tackles",
    "Zawodnik - przechwyty": "interceptions",
    "Zawodnik - otrzyma kartkę": "yellow_card",
}

_LINE_RE = re.compile(r"(\d+)\s+lub\s+więcej")
_PLUS_RE = re.compile(r"^\s*(\d+)\s*\+\s*$")  # próg jako nazwa wyniku: "1+", "2 +"
_TAK_RE = re.compile(r"^\s*tak\s*$", re.IGNORECASE)
MAX_SANE_ODDS = 50.0  # wyżej = zablokowane/placeholder


def _threshold_from_text(txt: str) -> int | None:
    """Wyciągnij próg N z 'N lub więcej' (układ A) albo 'N+' (układ B)."""
    m = _LINE_RE.search(txt) or _PLUS_RE.match(txt)
    return int(m.group(1)) if m else None


def _player_from_line_name(lname: str) -> str:
    """Układ B: 'Nazwisko Imię - <rynek> (z dogrywką)' -> 'Nazwisko Imię'."""
    return lname.split(" - ", 1)[0].strip()


def _ws_collect(channels: list[dict], seconds: float = 12.0) -> list[dict]:
    """Połącz z STS przez curl_cffi (impersonacja TLS Chrome — omija część blokad),
    wyślij handshake + subskrypcję i zbierz sparsowane ładunki ramek.

    Impersonacja TLS jest kluczowa: goły klient WS bywa odrzucany (403) z IP,
    które przy fingerprintcie przeglądarki przechodzą.
    """
    payloads: list[dict] = []
    ws = curl_requests.WebSocket()
    try:
        ws.connect(WS_URL, headers=WS_HEADERS, impersonate="chrome124")
    except Exception:
        return payloads
    try:
        for msg in (
            {"t": 1, "b": {"place.rsp": 0, "session": 0, "slips.rsp": 0, "cashout": 0}},
            {"t": 4, "s": 1},
            {"t": 1, "u": channels},
        ):
            ws.send(json.dumps(msg).encode())
        start = time.time()
        while time.time() - start < seconds:
            try:
                data = ws.recv()
            except Exception:
                break
            raw = data[0] if isinstance(data, tuple) else data
            text = raw.decode("utf-8", "ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        payloads.append(json.loads(line))
                    except Exception:
                        pass
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return payloads


def _fetch_frames(match_id: str, seconds: float = 12.0) -> list[dict]:
    return _ws_collect(
        [
            {"s": "i_pl", "n": 0},
            {"s": "rcm_global", "n": 0},
            {"s": f"f_{match_id}_pl", "n": 0},
            {"s": f"rcm_{match_id}", "n": 0},
        ],
        seconds,
    )


def _market_name_catalog(payloads: list[dict]) -> dict:
    """mid -> nazwa rynku (z B/S/*/m/{mid}/n)."""
    catalog = {}

    def walk(o, depth=0):
        if depth > 16 or not isinstance(o, (dict, list)):
            return
        if isinstance(o, dict):
            m = o.get("m")
            if isinstance(m, dict):
                for mid, mv in m.items():
                    if isinstance(mv, dict) and isinstance(mv.get("n"), str):
                        catalog.setdefault(mid, mv["n"])
            for v in o.values():
                walk(v, depth + 1)
        else:
            for v in o:
                walk(v, depth + 1)

    for body in payloads:
        if isinstance(body, dict) and "B" in body:
            walk(body["B"])
    return catalog


def parse_player_odds(payloads: list[dict], include_overtime: bool = False) -> dict:
    """Zbuduj {norm_name: {market_code: {line: {'over': kurs}}}} z ramek WS.

    Obsługuje DWA układy danych STS spotykane w tej samej ofercie:
      * układ A (popularne rynki 90-min): linia = '<rynek> - N lub więcej',
        wynik = zawodnik (grupowanie po progu, zawodnicy jako wyniki);
      * układ B (rynki „(z dogrywką)" / karta zawodnika): linia = 'Zawodnik -
        <rynek> (z dogrywką)', wynik = 'N+' (lub 'Tak'/'Nie' przy kartce) —
        grupowanie po zawodniku, progi jako wyniki.

    include_overtime — dołącz rynki „(z dogrywką)" pod kodem `code + '_ot'`.
    Przy meczach pucharowych część rynków (odbiory/niecelne/przechwyty/
    zablokowane) STS wystawia WYŁĄCZNIE z dogrywką, a to sztandarowe rynki
    value — rozliczają się z dogrywką, więc strona porównująca musi to oznaczyć.
    """
    catalog = _market_name_catalog(payloads)
    players: dict = {}

    def _emit(player_name, code, line, odd, is_ot):
        if not player_name or not odd or odd > MAX_SANE_ODDS or odd <= 1.0:
            return
        key = norm_name(player_name)
        if not key:
            return
        cc = f"{code}_ot" if is_ot else code
        slot = players.setdefault(key, {}).setdefault(cc, {})
        if line not in slot or odd > slot[line]["over"]:  # najlepszy kurs przy duplikatach
            slot[line] = {"over": float(odd)}

    for body in payloads:
        P = body.get("P") if isinstance(body, dict) else None
        if not isinstance(P, dict):
            continue
        for sel in P.values():
            if not isinstance(sel, dict):
                continue
            for mid, mv in (sel.get("m", {}) or {}).items():
                if not isinstance(mv, dict):
                    continue
                mname = catalog.get(mid, "")
                is_ot = "(z dogrywką)" in mname
                if is_ot and not include_overtime:
                    continue
                base = mname.replace(" (z dogrywką)", "").strip()
                code0 = MARKET_MAP.get(base)
                lines = mv.get("l", {})
                if not isinstance(lines, dict):
                    continue
                for lv in lines.values():
                    if not isinstance(lv, dict):
                        continue
                    lname = lv.get("n", "") or ""
                    outs = [o for o in (lv.get("o", {}) or {}).values() if isinstance(o, dict)]
                    if not outs:
                        continue
                    # kod rynku: z katalogu, a gdy brak — z nazwy linii (oba układy)
                    code = code0
                    if not code:
                        cand = _LINE_RE.sub("", lname).replace(" (z dogrywką)", "").strip(" -")
                        code = MARKET_MAP.get(cand) or MARKET_MAP.get(
                            lname.split(" - ", 1)[-1].replace(" (z dogrywką)", "").strip()
                        )
                    if not code:
                        continue
                    onames = [str(o.get("n") or "") for o in outs]
                    # układ B binarny: kartka (Tak/Nie), zawodnik w nazwie linii
                    if code == "yellow_card" and any(_TAK_RE.match(x) for x in onames):
                        player = _player_from_line_name(lname)
                        for ov in outs:
                            if ov.get("Bx") or not _TAK_RE.match(str(ov.get("n") or "")):
                                continue
                            _emit(player, code, 0.5, ov.get("O"), is_ot)
                        continue
                    # układ B numeryczny: progi 'N+' jako wyniki, zawodnik w linii
                    if any(_PLUS_RE.match(x) for x in onames):
                        player = _player_from_line_name(lname)
                        for ov in outs:
                            if ov.get("Bx"):
                                continue
                            thr = _threshold_from_text(str(ov.get("n") or ""))
                            if thr is None:
                                continue
                            _emit(player, code, float(thr) - 0.5, ov.get("O"), is_ot)
                        continue
                    # układ A: kartka -> linia 0.5; reszta -> próg z nazwy linii,
                    # a każdy wynik to zawodnik
                    if code == "yellow_card":
                        line = 0.5
                    else:
                        thr = _threshold_from_text(lname)
                        if thr is None:
                            continue
                        line = float(thr) - 0.5  # "N lub więcej" = > N-0.5
                    for ov in outs:
                        if ov.get("Bx"):
                            continue
                        _emit(ov.get("n"), code, line, ov.get("O"), is_ot)
    return {"players": players, "teams": {}}


def normalized_players(sts_result: dict) -> dict:
    """{player: {base_code: {line: (kurs, is_ot)}}} z wyniku fetch_stat_odds.

    Sprowadza kody „_ot" (z dogrywką) do bazowych. Gdy STS ma na tę samą linię
    i wersję 90-min, i z dogrywką — preferuje 90-min (czyste porównanie); przy
    tym samym typie bierze wyższy kurs. is_ot mówi, czy wybrany kurs jest
    z dogrywką (wtedy działa SuperSub — patrz parse_player_odds).
    """
    out: dict = {}
    for pkey, markets in (sts_result.get("players") or {}).items():
        for code, lines in markets.items():
            is_ot = code.endswith("_ot")
            base = code[:-3] if is_ot else code
            for line, slot in lines.items():
                odd = slot.get("over")
                if not odd:
                    continue
                d = out.setdefault(pkey, {}).setdefault(base, {})
                cur = d.get(line)
                if cur is None or (cur[1] and not is_ot) or (cur[1] == is_ot and odd > cur[0]):
                    d[line] = (float(odd), is_ot)
    return out


def fetch_stat_odds(match_id: str, seconds: float = 12.0,
                    include_overtime: bool = False) -> dict:
    """Pobierz kursy statystyczne meczu STS po jego ID (np. 'f482692').

    Zwraca {players: {norm_name: {market_code: {line: {'over': kurs}}}}}.
    include_overtime — patrz parse_player_odds (rynki '(z dogrywką)' jako `_ot`).
    """
    payloads = _fetch_frames(match_id, seconds)
    return parse_player_odds(payloads, include_overtime=include_overtime)


def match_ids_by_teams() -> dict:
    """Zwróć {(norm_home, norm_away): 'fID'} dla wszystkich meczów w katalogu i_pl.

    Pozwala znaleźć STS id meczu bez przeglądarki, po nazwach drużyn.
    """
    payloads = _ws_collect([{"s": "i_pl", "n": 0}], seconds=8.0)
    out = {}

    def walk(o, depth=0):
        if depth > 16 or not isinstance(o, (dict, list)):
            return
        if isinstance(o, dict):
            fx = o.get("FX")
            if isinstance(fx, dict):
                for fid, f in fx.items():
                    pr = f.get("pr") if isinstance(f, dict) else None
                    if isinstance(pr, dict) and isinstance(pr.get("H"), dict) and isinstance(pr.get("A"), dict):
                        h = norm_name(pr["H"].get("n", ""))
                        a = norm_name(pr["A"].get("n", ""))
                        if h and a:
                            out[(h, a)] = fid
            for v in o.values():
                walk(v, depth + 1)
        else:
            for v in o:
                walk(v, depth + 1)

    for body in payloads:
        walk(body)
    return out
