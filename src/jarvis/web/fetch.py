from __future__ import annotations

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


@dataclass
class FetchTransportResponse:
    url: str
    final_url: str
    text: str
    status_code: int
    content_type: str


class FixtureFetchTransport:
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


def run_web_fetch(
    request: FetchRequest,
    *,
    cache: WebCache | None = None,
    transport: FixtureFetchTransport | None = None,
    timeout_s: int = 10,
    max_bytes: int = MAX_BYTES_DEFAULT,
) -> WebToolResult:
    cache = cache or WebCache()
    transport = transport or FixtureFetchTransport()
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

