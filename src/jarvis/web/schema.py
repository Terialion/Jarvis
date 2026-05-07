from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SearchQuery:
    query: str
    provider: str = "auto"
    engine: str = ""
    top_k: int = 5
    freshness: str | None = None
    site: str | None = None
    task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    rank: int
    source_type: str = "unknown"
    provider: str = "fake"
    engine: str = "fake"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchRun:
    provider: str
    engine: str
    query: str
    ok: bool
    result_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FetchRequest:
    url: str
    extract_mode: str = "markdown"
    max_chars: int = 12000
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceRef:
    url: str
    title: str
    source_type: str
    provider: str = "fake"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReadableDocument:
    url: str
    final_url: str
    title: str
    text: str
    source_type: str
    is_untrusted: bool = True
    content_type: str = "text/plain"
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FetchRun:
    url: str
    final_url: str
    ok: bool
    blocked: bool = False
    block_reason: str | None = None
    error: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    bytes_read: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WebToolResult:
    runs: list[dict[str, Any]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    ok: bool = True
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

