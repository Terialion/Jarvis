"""Agent event sink and event helpers."""

from __future__ import annotations

from dataclasses import asdict
from typing import Protocol

from .types import AgentEvent

EVENT_TYPES = {
    "turn_started",
    "model_call_started",
    "model_call_completed",
    "reasoning_delta",
    "tool_call_started",
    "tool_call_completed",
    "tool_call_deduped",
    "skill_index_built",
    "skill_load_started",
    "skill_loaded",
    "skill_load_failed",
    "skill_already_loaded",
    "skill_observation_reused",
    "skill_call_started",
    "skill_step_started",
    "skill_step_completed",
    "skill_step_failed",
    "skill_tool_denied",
    "skill_call_completed",
    "skill_call_failed",
    "skill_observation_added",
    "web_search_started",
    "web_search_completed",
    "web_search_failed",
    "web_fetch_started",
    "web_fetch_completed",
    "web_fetch_failed",
    "web_fetch_blocked",
    "web_content_extracted",
    "permission_policy_evaluated",
    "tool_policy_allowed",
    "tool_policy_denied",
    "tool_rejected",
    "consecutive_failures_detected",
    "context_observation_reused",
    "context_updated",
    "context_window_usage",
    "approval_required",
    "approval_created",
    "approval_approved",
    "approval_denied",
    "pretool_hook_started",
    "pretool_hook_completed",
    "pretool_hook_denied",
    "posttool_hook_started",
    "posttool_hook_completed",
    "posttool_hook_warning",
    "domain_policy_evaluated",
    "domain_policy_denied",
    "domain_approval_required",
    "security_warning_emitted",
    "observation_added",
    "observation_reused",
    "retry_started",
    "final_answer_created",
    "summary_created",
    "turn_completed",
    "turn_failed",
}


class EventSink(Protocol):
    def emit(self, event: AgentEvent) -> None: ...


class InMemoryEventSink:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


class ReplayEventSink:
    """Bridge agent events into existing ReplayStore and keep local memory copy."""

    def __init__(self, replay_store: object | None, fallback: InMemoryEventSink | None = None) -> None:
        self.replay_store = replay_store
        self.fallback = fallback or InMemoryEventSink()

    def emit(self, event: AgentEvent) -> None:
        self.fallback.emit(event)
        if self.replay_store is None:
            return
        try:
            self.replay_store.record_event(  # type: ignore[attr-defined]
                event.turn_id,
                "MEMORY_WRITE",
                -1,
                asdict(event),
                "agent.loop",
            )
        except Exception:
            # Event persistence must not break runtime behavior.
            return
