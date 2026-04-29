"""Skill usage telemetry and lightweight insights."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _truncate(text: str, limit: int = 160) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


@dataclass
class SkillUsageRecord:
    skill_id: str
    input_preview: str
    selected: bool
    executed: bool
    mode: str
    outcome: str
    reason: str
    policy: dict[str, Any] = field(default_factory=dict)
    instruction_sources: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)

    def to_event(self) -> dict[str, Any]:
        return {
            "event": "skill.usage.recorded",
            "skill_id": self.skill_id,
            "input_preview": _truncate(self.input_preview),
            "selected": bool(self.selected),
            "executed": bool(self.executed),
            "mode": self.mode,
            "outcome": self.outcome,
            "reason": self.reason,
            "policy": dict(self.policy),
            "instruction_sources": list(self.instruction_sources),
            "timestamp": self.timestamp,
        }


class SkillTelemetryStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or "temp/skill_usage/usage.jsonl")

    def append(self, record: SkillUsageRecord) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = record.to_event()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return payload

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
        return rows

    def insights(self) -> dict[str, Any]:
        rows = self.read_all()
        by_skill: dict[str, dict[str, int]] = {}
        for item in rows:
            skill_id = str(item.get("skill_id") or "")
            if not skill_id:
                continue
            counters = by_skill.setdefault(
                skill_id,
                {
                    "selected": 0,
                    "blocked": 0,
                    "approval_required": 0,
                    "failed": 0,
                    "success": 0,
                    "selection_empty": 0,
                },
            )
            if item.get("selected"):
                counters["selected"] += 1
            outcome = str(item.get("outcome") or "")
            if outcome in counters:
                counters[outcome] += 1
            elif outcome == "approval_required":
                counters["approval_required"] += 1
            elif outcome in {"executed", "success"}:
                counters["success"] += 1
            elif outcome == "failed":
                counters["failed"] += 1
        top_selected = sorted(by_skill.items(), key=lambda kv: (-kv[1]["selected"], kv[0]))[:10]
        blocked = [sid for sid, counts in by_skill.items() if counts["blocked"] > 0]
        approval = [sid for sid, counts in by_skill.items() if counts["approval_required"] > 0]
        return {
            "total_records": len(rows),
            "skills": by_skill,
            "most_selected": [{"skill_id": sid, "selected": counts["selected"]} for sid, counts in top_selected],
            "blocked_skills": sorted(blocked),
            "approval_required_skills": sorted(approval),
            "suggestions": [
                "Add clearer triggers for skills with frequent selection_empty outcomes.",
                "Review blocked/approval-heavy skills for safer allowed_tools and permissions.",
            ],
        }
