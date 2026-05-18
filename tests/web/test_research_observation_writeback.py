from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.context_store import ContextStore
from src.jarvis.agent.context_updater import ContextUpdater
from src.jarvis.agent.types import AgentRunResult, TurnContext
from src.jarvis.store import ThreadStore


def test_research_observation_with_skill_guidance_is_persisted(tmp_path: Path):
    db_path = tmp_path / "jarvis.db"
    thread_store = ThreadStore(sessions_dir=db_path)
    context_store = ContextStore(session_store=thread_store)
    updater = ContextUpdater(context_store=context_store)

    result = AgentRunResult(
        ok=True,
        session_id="thread-1",
        turn_id="turn-1",
        final_answer="ok",
        events=[],
        summary={
            "machine": {
                "research_observations": [
                    {
                        "query": "today tech news",
                        "rewritten_query": "today technology news",
                        "guided_by_skill": "multi-search-engine",
                        "invocation_path": "reference_skill_guided_tool_call",
                        "search_runs": [{"provider": "fake", "ok": True, "result_count": 2}],
                        "fetched_urls": ["https://example.com/a"],
                        "evidence_count": 1,
                        "source_types": ["official_docs"],
                        "provider_errors": 0,
                        "no_results": 0,
                        "stale_sources": 0,
                        "uncertainty_flags": [],
                        "search_tasks": [],
                        "sources": [{"url": "https://example.com/a"}],
                        "evidence": [{"summary": "e1"}],
                        "answer_summary": "summary",
                        "confidence": 0.7,
                        "remaining_questions": [],
                    }
                ]
            }
        },
        stop_reason="completed",
    )
    turn = TurnContext(user_input="today tech news", cwd=str(tmp_path), session_id="thread-1", turn_id="turn-1", project_id="p")
    updater.apply_result(turn, result)
    stored = thread_store.get_research_observations("thread-1", limit=5)
    assert len(stored) == 1
    assert stored[0].metadata.get("guided_by_skill") == "multi-search-engine"
    assert stored[0].metadata.get("invocation_path") == "reference_skill_guided_tool_call"

