from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}


def normalize_url(url: str) -> str:
    parts = urlsplit(str(url or "").strip())
    filtered = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urlencode(filtered), ""))


def make_search_cache_key(provider: str, engine: str, query: str, top_k: int, freshness: str | None, site: str | None) -> str:
    return "|".join(
        [
            str(provider or "auto").strip().lower(),
            str(engine or "").strip().lower(),
            str(query or "").strip(),
            str(int(top_k or 0)),
            str(freshness or "").strip().lower(),
            str(site or "").strip().lower(),
        ]
    )


def make_fetch_cache_key(url: str) -> str:
    return normalize_url(url)


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class WebCache:
    def __init__(self, *, ttl_s: int = 900) -> None:
        self.ttl_s = ttl_s
        self._search: dict[str, _CacheEntry] = {}
        self._fetch: dict[str, _CacheEntry] = {}

    def get_search(self, key: str) -> Any | None:
        return self._get(self._search, key)

    def set_search(self, key: str, value: Any) -> None:
        self._search[key] = _CacheEntry(value=value, expires_at=time.time() + self.ttl_s)

    def get_fetch(self, key: str) -> Any | None:
        return self._get(self._fetch, key)

    def set_fetch(self, key: str, value: Any) -> None:
        self._fetch[key] = _CacheEntry(value=value, expires_at=time.time() + self.ttl_s)

    @staticmethod
    def _get(bucket: dict[str, _CacheEntry], key: str) -> Any | None:
        entry = bucket.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.time():
            bucket.pop(key, None)
            return None
        return entry.value

