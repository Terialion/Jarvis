"""Skill usage telemetry — record skill selection, execution, and outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.skill_harness.telemetry import SkillTelemetryStore, SkillUsageRecord

SkillUsageEventType = Literal[
    "skill_selected",
    "skill_rejected",
    "skill_loaded",
    "skill_executed",
    "reference_skill_used",
    "fallback_used",
    "success",
    "failure",
    "user_correction",
    "blocked",
]


@dataclass
class SkillUsageObservation:
    """Record of a single skill use event for telemetry and future learning."""

    event_type: SkillUsageEventType
    skill_name: str
    skill_type: str = "unknown"
    invocation_source: str = "none"
    invocation_path: str = "none"
    confidence: float = 0.0
    user_instruction: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    success: bool = False
    error: str | None = None
    blocked_reason: str | None = None
    suggested_metadata_update: dict[str, Any] | None = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "skill_name": self.skill_name,
            "skill_type": self.skill_type,
            "invocation_source": self.invocation_source,
            "invocation_path": self.invocation_path,
            "confidence": self.confidence,
            "user_instruction": self.user_instruction[:200],
            "tool_calls": self.tool_calls,
            "success": self.success,
            "error": self.error,
            "blocked_reason": self.blocked_reason,
            "suggested_metadata_update": self.suggested_metadata_update,
            "timestamp": self.timestamp,
        }


class SkillUsageTracker:
    """Tracks skill usage observations during an agent turn."""

    def __init__(self, telemetry_store: "SkillTelemetryStore | None" = None) -> None:
        self.observations: list[SkillUsageObservation] = []
        self._telemetry_store = telemetry_store

    def flush(self, skill_id: str = "", mode: str = "agent_turn") -> int:
        """Persist all observations to the durable SkillTelemetryStore (if configured).

        Returns the number of records written.
        """
        if self._telemetry_store is None:
            return 0
        from ..core.skill_harness.telemetry import SkillUsageRecord

        written = 0
        for obs in self.observations:
            record = SkillUsageRecord(
                skill_id=skill_id or obs.skill_name,
                input_preview=obs.user_instruction,
                selected=(obs.event_type == "skill_selected"),
                executed=(obs.event_type in ("skill_executed", "reference_skill_used")),
                mode=mode,
                outcome=(
                    "success" if obs.success
                    else "blocked" if obs.blocked_reason
                    else "failed" if obs.error
                    else obs.event_type
                ),
                reason=obs.blocked_reason or obs.error or obs.event_type,
                instruction_sources=[obs.invocation_source] if obs.invocation_source != "none" else [],
            )
            self._telemetry_store.append(record)
            written += 1
        return written

    def with_telemetry_store(self, store: "SkillTelemetryStore") -> "SkillUsageTracker":
        """Return a new tracker that writes to the given durable store."""
        self._telemetry_store = store
        return self

    def record_selected(
        self,
        skill_name: str,
        skill_type: str,
        source: str,
        confidence: float,
        instruction: str,
    ) -> SkillUsageObservation:
        obs = SkillUsageObservation(
            event_type="skill_selected",
            skill_name=skill_name,
            skill_type=skill_type,
            invocation_source=source,
            invocation_path=source,
            confidence=confidence,
            user_instruction=instruction,
        )
        self.observations.append(obs)
        return obs

    def record_loaded(self, skill_name: str, skill_type: str) -> SkillUsageObservation:
        obs = SkillUsageObservation(
            event_type="skill_loaded",
            skill_name=skill_name,
            skill_type=skill_type,
        )
        self.observations.append(obs)
        return obs

    def record_executed(
        self,
        skill_name: str,
        skill_type: str,
        invocation_path: str,
        success: bool,
        error: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> SkillUsageObservation:
        obs = SkillUsageObservation(
            event_type="skill_executed",
            skill_name=skill_name,
            skill_type=skill_type,
            invocation_path=invocation_path,
            success=success,
            error=error,
            tool_calls=list(tool_calls or []),
        )
        self.observations.append(obs)
        return obs

    def record_reference_used(
        self,
        skill_name: str,
        tool_calls: list[dict[str, Any]],
        success: bool,
    ) -> SkillUsageObservation:
        obs = SkillUsageObservation(
            event_type="reference_skill_used",
            skill_name=skill_name,
            skill_type="reference",
            invocation_path="reference_guided_tool_call",
            success=success,
            tool_calls=list(tool_calls),
        )
        self.observations.append(obs)
        return obs

    def record_fallback(
        self,
        skill_name: str,
        reason: str,
        instruction: str,
    ) -> SkillUsageObservation:
        obs = SkillUsageObservation(
            event_type="fallback_used",
            skill_name=skill_name,
            invocation_source="fallback",
            user_instruction=instruction,
            blocked_reason=reason,
        )
        self.observations.append(obs)
        return obs

    def record_blocked(
        self,
        skill_name: str,
        reason: str,
    ) -> SkillUsageObservation:
        obs = SkillUsageObservation(
            event_type="blocked",
            skill_name=skill_name,
            blocked_reason=reason,
        )
        self.observations.append(obs)
        return obs

    def to_dicts(self) -> list[dict[str, Any]]:
        return [obs.to_dict() for obs in self.observations]

    def success_rate(self) -> float:
        executed = [o for o in self.observations if o.event_type in ("skill_executed", "reference_skill_used")]
        if not executed:
            return 1.0
        return sum(1 for o in executed if o.success) / len(executed)
