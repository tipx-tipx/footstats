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
MAX_SANE_ODDS = 50.0  # wyżej = zablokowane/placeholder


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


def parse_player_odds(payloads: list[dict]) -> dict:
    """Zbuduj {norm_name: {market_code: {line: {'over': kurs}}}} z ramek WS."""
    catalog = _market_name_catalog(payloads)
    # nazwa rynku -> kod (dopasowanie po nazwie z katalogu ORAZ z nazw linii)
    players: dict = {}

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
                # pomiń warianty "(z dogrywką)"
                base = mname.replace(" (z dogrywką)", "").strip()
                code = MARKET_MAP.get(base)
                lines = mv.get("l", {})
                if not isinstance(lines, dict):
                    continue
                for lv in lines.values():
                    if not isinstance(lv, dict):
                        continue
                    lname = lv.get("n", "") or ""
                    # kod może wynikać z nazwy linii, gdy katalog nie miał rynku
                    if not code:
                        lbase = _LINE_RE.sub("", lname).strip(" -")
                        code = MARKET_MAP.get(lbase)
                    if not code:
                        continue
                    if "(z dogrywką)" in lname:
                        continue
                    if code == "yellow_card":
                        line = 0.5
                    else:
                        m = _LINE_RE.search(lname)
                        if not m:
                            continue
                        line = float(int(m.group(1)) - 0.5)  # "N lub więcej" = > N-0.5
                    for ov in (lv.get("o", {}) or {}).values():
                        if not isinstance(ov, dict) or ov.get("Bx"):
                            continue
                        odd = ov.get("O")
                        name = ov.get("n")
                        if not name or not odd or odd > MAX_SANE_ODDS or odd <= 1.0:
                            continue
                        key = norm_name(name)
                        slot = players.setdefault(key, {}).setdefault(code, {})
                        # bierz najlepszy (najwyższy) kurs, gdy duplikaty
                        if line not in slot or odd > slot[line]["over"]:
                            slot[line] = {"over": float(odd)}
    return {"players": players, "teams": {}}


def fetch_stat_odds(match_id: str, seconds: float = 12.0) -> dict:
    """Pobierz kursy statystyczne meczu STS po jego ID (np. 'f482692').

    Zwraca {players: {norm_name: {market_code: {line: {'over': kurs}}}}}.
    """
    payloads = _fetch_frames(match_id, seconds)
    return parse_player_odds(payloads)


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
