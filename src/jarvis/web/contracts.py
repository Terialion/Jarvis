from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SearchRequest:
    query: str
    target: str | None = None
    engine: str | None = None
    provider: str | None = None
    top_k: int = 5
    guided_by_skill: str | None = None
    invocation_path: str | None = None
    source: str = "user_input"
    time_range: str | None = None
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    rank: int
    source_type: str | None = None
    provider: str = "fake"
    engine: str | None = None
    query: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchRun:
    request: SearchRequest
    ok: bool
    results: list[SearchResult] = field(default_factory=list)
    error: str | None = None
    result_count: int = 0
    provider_error: bool = False
    no_results: bool = False
    stale_source_detected: bool = False
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["request"] = self.request.to_dict()
        data["results"] = [row.to_dict() for row in self.results]
        return data
