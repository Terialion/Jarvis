from __future__ import annotations

from typing import Any

from ..agent.types import AgentEvent
from ..store.redaction import redact_for_persistence


def coding_event(turn_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a redacted coding workflow event for AgentRunResult timelines."""

    return AgentEvent.new(
        turn_id=turn_id,
        event_type=event_type,
        payload=dict(redact_for_persistence(payload or {})),
    ).to_dict()
