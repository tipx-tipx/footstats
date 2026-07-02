"""Klient HTTP dla źródeł danych.

Zasady:
  * impersonacja TLS przeglądarki (curl_cffi) — bez tego Sofascore zwraca 403,
  * limit zapytań (domyślnie 1 na 2 sekundy) — gramy fair wobec źródła,
  * cache surowych odpowiedzi JSON na dysku — ponowne uruchomienie backfillu
    nie odpytuje źródła drugi raz (odpowiedzi meczów zakończonych są niezmienne),
  * wyłącznie do uruchamiania LOKALNIE (domowe IP) — nie wrzucać do chmury.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from curl_cffi import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "http_cache"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    "Referer": "https://www.sofascore.com/",
}


class RateLimitedClient:
    def __init__(self, min_interval_s: float = 2.0, impersonate: str = "chrome124"):
        self.min_interval_s = min_interval_s
        self.impersonate = impersonate
        self._last_request_at = 0.0
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha256(url.encode()).hexdigest()[:24]
        return CACHE_DIR / f"{h}.json"

    def get_json(self, url: str, use_cache: bool = True, max_retries: int = 5) -> dict:
        cache_file = self._cache_path(url)
        if use_cache and cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))

        for attempt in range(max_retries):
            wait = self.min_interval_s - (time.time() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
            self._last_request_at = time.time()
            try:
                r = requests.get(
                    url, headers=DEFAULT_HEADERS, impersonate=self.impersonate, timeout=30
                )
            except Exception:
                if attempt == max_retries - 1:
                    raise
                time.sleep(5.0 * (attempt + 1))
                continue

            if r.status_code == 200:
                data = r.json()
                cache_file.write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8"
                )
                return data
            if r.status_code in (403, 429):
                # przystopuj wyraźnie — źródło sygnalizuje przeciążenie/blokadę;
                # po dużym backfillu schłodzenie potrafi trwać kilka minut
                time.sleep(60.0 * (attempt + 1))
                continue
            if r.status_code == 404:
                raise LookupError(f"404: {url}")
            time.sleep(5.0 * (attempt + 1))

        raise ConnectionError(f"Nie udało się pobrać po {max_retries} próbach: {url}")
