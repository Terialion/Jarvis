"""Agent event sinks.

Use this to make CLI/API/Web UI consume the same stream: turn.started,
model.delta, tool.started, tool.completed, turn.completed, etc.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Protocol

from .types import AgentEvent


class EventSink(Protocol):
    def emit(self, event: AgentEvent) -> None: ...


class InMemoryEventSink:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


class ReplayEventSink:
    """Bridge to existing Jarvis ReplayStore when available."""

    def __init__(self, replay_store, fallback: EventSink | None = None) -> None:
        self.replay_store = replay_store
        self.fallback = fallback or InMemoryEventSink()

    def emit(self, event: AgentEvent) -> None:
        self.fallback.emit(event)
        if self.replay_store is None:
            return
        try:
            # Keep this adapter tolerant because ReplayStore event enums may evolve.
            self.replay_store.record_event(
                event.turn_id,
                event.type,
                -1,
                asdict(event),
                "agent.loop",
            )
        except Exception:
            # Events must never break the agent loop.
            pass
