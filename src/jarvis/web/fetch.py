from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..agent.types import redact_secret_text
from .cache import WebCache, make_fetch_cache_key
from .extract import extract_readable_text
from .fixtures import FAKE_FETCH_FIXTURES, FakeFetchFixture
from .safety import block_reason_for_url
from .schema import FetchRequest, FetchRun, ReadableDocument, WebToolResult
from .source_classifier import classify_source


MAX_BYTES_DEFAULT = 2_000_000
MIN_VIABLE_CONTENT_LENGTH = 200
USER_AGENT = "JarvisAgent/0.21 (web-fetch; +https://github.com/user/jarvis)"


def _detect_charset_from_meta(raw: bytes) -> str | None:
    """Try to detect charset from <meta> tags in raw HTML bytes."""
    try:
        # Scan the first 4KB as latin-1 (which preserves bytes 1:1) to find meta tags
        head = raw[:4096].decode("latin-1", errors="replace")
        m = re.search(r'<meta[^>]*charset=["\']?([^"\'>\s;]+)', head, re.IGNORECASE)
        if m:
            return m.group(1).strip().lower()
        m = re.search(
            r'<meta[^>]*http-equiv=["\']?Content-Type[^>]*content=["\'][^;]*;\s*charset=([^"\'>\s]+)',
            head, re.IGNORECASE,
        )
        if m:
            return m.group(1).strip().lower()
    except Exception:
        pass
    return None


@dataclass
class FetchTransportResponse:
    url: str
    final_url: str
    text: str
    status_code: int
    content_type: str


class FixtureFetchTransport:
    """Fake transport for offline testing — only serves pre-defined fixture URLs."""

    def fetch(self, url: str, *, timeout_s: int = 10, max_bytes: int = MAX_BYTES_DEFAULT) -> FetchTransportResponse:
        _ = timeout_s, max_bytes
        fixture = FAKE_FETCH_FIXTURES.get(url)
        if fixture is None:
            raise FileNotFoundError(f"fixture_not_found:{url}")
        final_url = fixture.final_url or fixture.url
        return FetchTransportResponse(
            url=fixture.url,
            final_url=final_url,
            text=fixture.text,
            status_code=fixture.status_code,
            content_type=fixture.content_type,
        )


class HttpFetchTransport:
    """Real HTTP/HTTPS fetch transport using urllib (stdlib, no extra deps)."""

    def fetch(self, url: str, *, timeout_s: int = 10, max_bytes: int = MAX_BYTES_DEFAULT) -> FetchTransportResponse:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,en;q=0.9",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read(max_bytes + 1)
                raw_body = raw[:max_bytes]
                charset = resp.headers.get_content_charset()
                if not charset:
                    charset = _detect_charset_from_meta(raw_body)
                body = raw_body.decode(charset or "utf-8", errors="replace")
                final_url = resp.geturl() or url
                content_type = resp.headers.get_content_type() or "text/html"
                return FetchTransportResponse(
                    url=url,
                    final_url=final_url,
                    text=body,
                    status_code=resp.status,
                    content_type=content_type,
                )
        except urllib.error.HTTPError as exc:
            # Return the error page body so the caller can still extract info
            try:
                body = exc.read(max_bytes).decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return FetchTransportResponse(
                url=url,
                final_url=exc.geturl() or url,
                text=body,
                status_code=exc.code,
                content_type=exc.headers.get_content_type() or "text/html",
            )
        except Exception as exc:
            raise RuntimeError(f"fetch_failed: {exc}") from exc


def run_web_fetch(
    request: FetchRequest,
    *,
    cache: WebCache | None = None,
    transport: FixtureFetchTransport | HttpFetchTransport | None = None,
    timeout_s: int = 10,
    max_bytes: int = MAX_BYTES_DEFAULT,
) -> WebToolResult:
    cache = cache or WebCache()
    transport = transport or HttpFetchTransport()
    initial_block = block_reason_for_url(request.url)
    if initial_block is not None:
        return WebToolResult(
            ok=False,
            runs=[FetchRun(url=request.url, final_url=request.url, ok=False, blocked=True, block_reason=initial_block).to_dict()],
            documents=[],
            error=initial_block,
        )
    cache_key = make_fetch_cache_key(request.url)
    cached = cache.get_fetch(cache_key)
    if cached is not None:
        return cached
    try:
        response = transport.fetch(request.url, timeout_s=timeout_s, max_bytes=max_bytes)
    except Exception as exc:
        result = WebToolResult(
            ok=False,
            runs=[FetchRun(url=request.url, final_url=request.url, ok=False, error=str(exc)).to_dict()],
            documents=[],
            error=str(exc),
        )
        cache.set_fetch(cache_key, result.to_dict())
        return result

    redirected_block = block_reason_for_url(response.final_url)
    if redirected_block is not None:
        result = WebToolResult(
            ok=False,
            runs=[
                FetchRun(
                    url=request.url,
                    final_url=response.final_url,
                    ok=False,
                    blocked=True,
                    block_reason=redirected_block,
                    status_code=response.status_code,
                    content_type=response.content_type,
                ).to_dict()
            ],
            documents=[],
            error=redirected_block,
        )
        cache.set_fetch(cache_key, result.to_dict())
        return result

    bytes_read = min(len(response.text.encode("utf-8", "replace")), max_bytes)
    truncated_text = response.text.encode("utf-8", "replace")[:max_bytes].decode("utf-8", "replace")
    try:
        title, text = extract_readable_text(
            truncated_text,
            content_type=response.content_type,
            max_chars=request.max_chars,
            extract_mode=request.extract_mode,
        )
    except Exception as exc:
        result = WebToolResult(
            ok=False,
            runs=[
                FetchRun(
                    url=request.url,
                    final_url=response.final_url,
                    ok=False,
                    error=str(exc),
                    status_code=response.status_code,
                    content_type=response.content_type,
                    bytes_read=bytes_read,
                ).to_dict()
            ],
            documents=[],
            error=str(exc),
        )
        cache.set_fetch(cache_key, result.to_dict())
        return result

    document = ReadableDocument(
        url=request.url,
        final_url=response.final_url,
        title=title or response.final_url,
        text=redact_secret_text(text),
        source_type=classify_source(response.final_url),
        is_untrusted=True,
        content_type=response.content_type,
        provenance=dict(request.provenance or {}),
    )
    # Auto-fallback to browser when HTTP fetch yields minimal text (JS-rendered SPA)
    if request.auto_browser_fallback and len(text.strip()) < MIN_VIABLE_CONTENT_LENGTH:
        try:
            from .browser import run_web_browse
            browser_result = run_web_browse(request.url, action="snapshot")
            if browser_result.get("ok") and browser_result.get("text", "").strip():
                browser_text = browser_result["text"]
                browser_title = browser_result.get("title") or title
                document = ReadableDocument(
                    url=request.url,
                    final_url=browser_result.get("url", response.final_url),
                    title=browser_title or request.url,
                    text=redact_secret_text(browser_text),
                    source_type=classify_source(response.final_url),
                    is_untrusted=True,
                    content_type="text/html",
                    provenance=dict(request.provenance or {}),
                )
        except Exception:
            pass  # Keep HTTP result if browser fails
    result = WebToolResult(
        ok=True,
        runs=[
            FetchRun(
                url=request.url,
                final_url=response.final_url,
                ok=True,
                blocked=False,
                status_code=response.status_code,
                content_type=response.content_type,
                bytes_read=bytes_read,
            ).to_dict()
        ],
        documents=[document.to_dict()],
    )
    cache.set_fetch(cache_key, result.to_dict())
    return result

