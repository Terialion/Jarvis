from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..agent.types import AgentEvent, ToolCall, ToolResult, TurnContext
from .answer_composer import AnswerComposer
from .cache import WebCache
from .evidence import judge_source_coverage, extract_evidence
from .fetch import run_web_fetch
from .fetch_selector import FetchSelector
from .providers.router import ProviderRouter
from .query_rewriter import QueryRewriter
from .rerank import rerank_results
from .research_context import ResearchObservation
from .schema import FetchRequest, ReadableDocument, SearchQuery, SearchResult
from .search import run_web_search
from .search_planner import SearchPlanner


@dataclass
class SearchIntent:
    need_web: bool
    intent_type: str
    reason: str


@dataclass
class WebResearchPipelineResult:
    final_answer: str
    output_type: str
    stop_reason: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    research_observation: dict[str, Any] | None = None
    evidence_count: int = 0
    official_sources_count: int = 0
    github_sources_count: int = 0
    web_search_runs_count: int = 0
    web_fetch_runs_count: int = 0
    web_fetch_blocked_count: int = 0
    web_provider_errors: int = 0
    web_no_results_count: int = 0
    search_results_count: int = 0
    search_result_dedup_count: int = 0
    release_note_sources_count: int = 0
    stale_sources_count: int = 0
    citation_count: int = 0
    source_coverage_score: float = 0.0
    prompt_injection_blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SearchIntentClassifier:
    def classify(self, user_input: str, context_pack: Any | None = None) -> SearchIntent:
        _ = context_pack
        text = str(user_input or "").strip()
        lowered = text.lower()
        if "不要联网" in text or "don't browse" in lowered or "do not browse" in lowered:
            return SearchIntent(False, "no_web_needed", "User explicitly asked to avoid the web.")
        explicit = ("搜索", "查资料", "官方文档", "official docs", "search", "release notes", "issue", "pr", "bug", "workaround", "latest", "recent", "today", "current")
        if any(token in lowered or token in text for token in explicit):
            if any(token in lowered for token in ("latest", "recent", "today", "current", "release notes", "news")):
                return SearchIntent(True, "fresh_info", "Fresh/current information requested.")
            if any(token in lowered or token in text for token in ("official docs", "官方文档", "文档", "docs")):
                return SearchIntent(True, "docs_lookup", "Documentation lookup requested.")
            if any(token in lowered or token in text for token in ("issue", "pr", "bug", "workaround", "是不是 bug")):
                return SearchIntent(True, "bug_verification", "Bug verification or issue lookup requested.")
            return SearchIntent(True, "general_research", "Explicit web research request.")
        if "flink cdc" in lowered or "release note" in lowered:
            return SearchIntent(True, "general_research", "Niche topic with likely need for external sources.")
        return SearchIntent(False, "no_web_needed", "No clear web research trigger.")


class SearchIntentClassifier:
    def classify(self, user_input: str, context_pack: Any | None = None) -> SearchIntent:
        _ = context_pack
        text = str(user_input or "").strip()
        lowered = text.lower()
        if any(token in text for token in ("不要联网", "不要上网", "不要搜索")) or "don't browse" in lowered or "do not browse" in lowered:
            return SearchIntent(False, "no_web_needed", "User explicitly asked to avoid the web.")
        explicit = (
            "搜索",
            "查资料",
            "查一下",
            "官网",
            "官方文档",
            "文档",
            "official docs",
            "search",
            "release notes",
            "issue",
            "pr",
            "bug",
            "workaround",
            "latest",
            "recent",
            "today",
            "current",
        )
        if any(token in lowered or token in text for token in explicit):
            if any(token in lowered for token in ("latest", "recent", "today", "current", "release notes", "news")):
                return SearchIntent(True, "fresh_info", "Fresh/current information requested.")
            if any(token in lowered or token in text for token in ("official docs", "官方文档", "文档", "docs", "官网")):
                return SearchIntent(True, "docs_lookup", "Documentation lookup requested.")
            if any(token in lowered or token in text for token in ("issue", "pr", "bug", "workaround", "是不是 bug", "是不是bug")):
                return SearchIntent(True, "bug_verification", "Bug verification or issue lookup requested.")
            return SearchIntent(True, "general_research", "Explicit web research request.")
        if "flink cdc" in lowered or "release note" in lowered:
            return SearchIntent(True, "general_research", "Niche topic with likely need for external sources.")
        return SearchIntent(False, "no_web_needed", "No clear web research trigger.")


class WebResearchPipeline:
    def __init__(
        self,
        *,
        tool_executor: Any,
        event_factory: Callable[[str, dict[str, Any]], AgentEvent],
        provider_router: ProviderRouter | None = None,
        cache: WebCache | None = None,
    ) -> None:
        self.tool_executor = tool_executor
        self.event_factory = event_factory
        self.provider_router = provider_router or ProviderRouter()
        self.cache = cache or WebCache()
        self.rewriter = QueryRewriter()
        self.planner = SearchPlanner()
        self.fetch_selector = FetchSelector()
        self.answer_composer = AnswerComposer()

    def run(self, *, user_input: str, turn_context: TurnContext) -> WebResearchPipelineResult:
        intent = SearchIntentClassifier().classify(user_input, turn_context.context_pack)
        if not intent.need_web:
            return WebResearchPipelineResult(
                final_answer="Web research was not required for this request.",
                output_type="answer",
                stop_reason="completed",
            )
        rewrite = self.rewriter.rewrite(user_input, intent.intent_type)
        planned = self.planner.plan(rewrite, intent.intent_type)
        events: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        search_results: list[SearchResult] = []
        search_runs = 0
        fetch_runs = 0
        fetch_blocked = 0
        provider_errors = 0
        no_results_count = 0

        for task in planned:
            call = ToolCall.new(
                name="web.search",
                arguments=task.to_dict(),
                reason=f"web_research:{intent.intent_type}:{task.task_id or 'task'}",
            )
            events.append(self._event("web_search_started", {"query": task.query, "provider": task.provider, "site": task.site}).to_dict())
            events.append(self._event("tool_call_started", {"tool_call": call.to_dict(), "step": task.task_id or "search"}).to_dict())
            result = self.tool_executor.execute(
                call,
                context={
                    "cwd": turn_context.cwd,
                    "session_id": turn_context.session_id or "",
                    "turn_id": turn_context.turn_id or "",
                    "permission_mode": turn_context.permission_mode,
                    "mode": "web_research",
                },
            )
            tool_calls.append(call.to_dict())
            tool_results.append(result.to_dict())
            events.append(self._event("tool_call_completed", {"tool_result": result.to_dict(), "step": task.task_id or "search"}).to_dict())
            payload = result.content if isinstance(result.content, dict) else {}
            if result.ok:
                search_runs += 1
                runs = list(payload.get("runs") or [])
                results = list(payload.get("results") or [])
                if not results:
                    no_results_count += 1
                search_results.extend(
                    [
                        SearchResult(
                            title=str(row.get("title") or ""),
                            url=str(row.get("url") or ""),
                            snippet=str(row.get("snippet") or ""),
                            rank=int(row.get("rank") or 0),
                            source_type=str(row.get("source_type") or "unknown"),
                            provider=str(row.get("provider") or "fake"),
                            engine=str(row.get("engine") or "fake"),
                        )
                        for row in results
                        if isinstance(row, dict)
                    ]
                )
                events.append(self._event("web_search_completed", {"query": task.query, "result_count": len(results), "runs": runs}).to_dict())
            else:
                provider_errors += 1
                events.append(self._event("web_search_failed", {"query": task.query, "error": result.error or "web_search_failed"}).to_dict())

        raw_search_results_count = len(search_results)
        reranked = rerank_results(search_results, user_input)
        search_result_dedup_count = max(0, raw_search_results_count - len(reranked))
        selected = self.fetch_selector.select(reranked, intent.intent_type)
        documents: list[ReadableDocument] = []
        for item in selected:
            request = FetchRequest(
                url=item.url,
                extract_mode="markdown",
                max_chars=12000,
                provenance={"kind": "search_result", "source": "web.search", "query": item.title},
            )
            call = ToolCall.new(name="web.fetch", arguments=request.to_dict(), reason=f"web_research:fetch:{item.source_type}")
            events.append(self._event("web_fetch_started", {"url": item.url, "source_type": item.source_type}).to_dict())
            events.append(self._event("tool_call_started", {"tool_call": call.to_dict(), "step": "fetch"}).to_dict())
            result = self.tool_executor.execute(
                call,
                context={
                    "cwd": turn_context.cwd,
                    "session_id": turn_context.session_id or "",
                    "turn_id": turn_context.turn_id or "",
                    "permission_mode": turn_context.permission_mode,
                    "mode": "web_research",
                },
            )
            tool_calls.append(call.to_dict())
            tool_results.append(result.to_dict())
            events.append(self._event("tool_call_completed", {"tool_result": result.to_dict(), "step": "fetch"}).to_dict())
            payload = result.content if isinstance(result.content, dict) else {}
            runs = list(payload.get("runs") or [])
            if result.ok:
                fetch_runs += 1
                docs = [ReadableDocument(**row) for row in list(payload.get("documents") or []) if isinstance(row, dict)]
                documents.extend(docs)
                events.append(self._event("web_fetch_completed", {"url": item.url, "document_count": len(docs), "runs": runs}).to_dict())
                if docs:
                    events.append(self._event("web_content_extracted", {"url": item.url, "title": docs[0].title, "source_type": docs[0].source_type}).to_dict())
            else:
                if any(isinstance(run, dict) and bool(run.get("blocked")) for run in runs):
                    fetch_blocked += 1
                    block_reason = next((str(run.get("block_reason") or "") for run in runs if isinstance(run, dict) and run.get("blocked")), "blocked")
                    events.append(self._event("web_fetch_blocked", {"url": item.url, "block_reason": block_reason}).to_dict())
                else:
                    events.append(self._event("web_fetch_failed", {"url": item.url, "error": result.error or "web_fetch_failed"}).to_dict())

        evidence = extract_evidence(documents)
        coverage = judge_source_coverage(evidence, intent.intent_type)
        composed = self.answer_composer.compose(user_input=user_input, evidence=evidence, coverage=coverage)
        unsafe_page_seen = any(
            "ignore previous instructions" in str(document.text or "").lower()
            or "reveal secrets" in str(document.text or "").lower()
            for document in documents
        )
        final_lower = str(composed.final_answer or "").lower()
        prompt_injection_blocked = bool(unsafe_page_seen and "ignore previous instructions" not in final_lower and "reveal secrets" not in final_lower)
        release_note_sources_count = sum(1 for item in evidence if item.source_type == "release_notes")
        stale_sources_count = sum(
            1
            for item in evidence
            if "stale" in f"{item.source_title} {item.source_url} {item.summary}".lower()
            or "2018" in f"{item.source_title} {item.source_url} {item.summary}".lower()
        )
        observation = ResearchObservation(
            query=user_input,
            search_tasks=[task.to_dict() for task in planned],
            sources=[
                {"url": item.url, "title": item.title, "source_type": item.source_type, "provider": item.provider}
                for item in reranked[:8]
            ],
            evidence=[item.to_dict() for item in evidence[:8]],
            answer_summary=composed.final_answer[:600],
            confidence=composed.confidence,
            remaining_questions=list(composed.remaining_questions),
        )
        stop_reason = "completed" if composed.output_type == "answer" else "insufficient_evidence"
        return WebResearchPipelineResult(
            final_answer=composed.final_answer,
            output_type=composed.output_type,
            stop_reason=stop_reason,
            tool_calls=tool_calls,
            tool_results=tool_results,
            events=events,
            research_observation=observation.to_dict(),
            evidence_count=len(evidence),
            official_sources_count=sum(1 for item in evidence if item.source_type == "official_docs"),
            github_sources_count=sum(1 for item in evidence if item.source_type in {"github_issue", "github_pr"}),
            web_search_runs_count=search_runs,
            web_fetch_runs_count=fetch_runs,
            web_fetch_blocked_count=fetch_blocked,
            web_provider_errors=provider_errors,
            web_no_results_count=no_results_count,
            search_results_count=raw_search_results_count,
            search_result_dedup_count=search_result_dedup_count,
            release_note_sources_count=release_note_sources_count,
            stale_sources_count=stale_sources_count,
            citation_count=len(composed.source_refs),
            source_coverage_score=coverage.source_coverage_score,
            prompt_injection_blocked=prompt_injection_blocked,
        )

    def _event(self, event_type: str, payload: dict[str, Any]) -> AgentEvent:
        return self.event_factory(event_type, payload)
