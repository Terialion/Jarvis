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
    "approval_required",
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
