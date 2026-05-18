from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from .contracts import SearchRequest as ContractSearchRequest
from .contracts import SearchResult as ContractSearchResult
from .contracts import SearchRun as ContractSearchRun
from .providers.base import ProviderSearchResponse
from .providers.registry import SearchProviderRegistry
from .schema import SearchQuery, SearchResult, SearchRun, WebToolResult


def _normalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return raw
    try:
        parsed = urlsplit(raw)
    except Exception:
        return raw
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", ""))


def _to_contract_run(query: SearchQuery, run: SearchRun, results: list[SearchResult]) -> ContractSearchRun:
    request = ContractSearchRequest(
        query=query.query,
        target=query.site,
        engine=query.engine or None,
        provider=query.provider or None,
        top_k=int(query.top_k or 5),
        guided_by_skill=query.guided_by_skill,
        invocation_path=query.invocation_path,
        source=query.source or "user_input",
        time_range=query.time_range or query.freshness,
        language=query.language,
        metadata=dict(query.metadata or {}),
    )
    contract_results = [
        ContractSearchResult(
            title=row.title,
            url=row.url,
            snippet=row.snippet,
            rank=row.rank,
            source_type=row.source_type,
            provider=row.provider,
            engine=row.engine,
            query=query.query,
            metadata={},
        )
        for row in results
    ]
    return ContractSearchRun(
        request=request,
        ok=bool(run.ok),
        results=contract_results,
        error=run.error,
        result_count=len(contract_results),
        provider_error=bool(run.provider_error),
        no_results=(len(contract_results) == 0 and not run.provider_error),
        stale_source_detected=bool(run.stale_source_detected),
    )


@dataclass
class SearchExecutor:
    provider_registry: SearchProviderRegistry
    allow_live: bool = False

    def execute(self, query: SearchQuery) -> tuple[ContractSearchRun, list[SearchResult]]:
        provider = self.provider_registry.resolve(query.provider, allow_live=self.allow_live)
        response: ProviderSearchResponse = provider.search(query)
        deduped: list[SearchResult] = []
        seen: set[str] = set()
        for row in list(response.results or []):
            key = _normalize_url(row.url)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        run = response.run
        run.result_count = len(deduped)
        run.no_results = len(deduped) == 0 and not bool(run.provider_error)
        run.guided_by_skill = query.guided_by_skill
        run.invocation_path = query.invocation_path
        run.source = query.source or "user_input"
        contract = _to_contract_run(query, run, deduped)
        return contract, deduped


def to_web_tool_result(contract_run: ContractSearchRun, schema_results: list[SearchResult]) -> WebToolResult:
    run_payload = contract_run.to_dict()
    inferred_provider = schema_results[0].provider if schema_results else str(contract_run.request.provider or "")
    inferred_engine = schema_results[0].engine if schema_results else str(contract_run.request.engine or "")
    run_payload["provider"] = str(inferred_provider)
    run_payload["engine"] = str(inferred_engine)
    run_payload["query"] = contract_run.request.query
    return WebToolResult(
        ok=bool(contract_run.ok),
        error=contract_run.error,
        runs=[run_payload],
        results=[row.to_dict() for row in schema_results],
    )
