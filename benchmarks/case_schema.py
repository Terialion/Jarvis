from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _normalize_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [str(k).strip() for k in value.keys() if str(k).strip()]
    return []


@dataclass
class BenchmarkCase:
    id: str
    suite: str
    category: str
    input: str
    turns: list[dict[str, Any]] = field(default_factory=list)
    setup: dict[str, Any] = field(default_factory=dict)
    workspace: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    expected_behavior: dict[str, Any] = field(default_factory=dict)
    grading: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkCase":
        raw_turns = data.get("turns")
        turns: list[dict[str, Any]] = []
        if isinstance(raw_turns, list):
            turns = [dict(item) for item in raw_turns if isinstance(item, dict)]
        input_text = str(data.get("input") or "")
        if not turns and input_text:
            turns = [{"input": input_text}]
        return cls(
            id=str(data.get("id") or data.get("case_id") or ""),
            suite=str(data.get("suite") or ""),
            category=str(data.get("category") or ""),
            input=input_text or str((turns[0] or {}).get("input") or ""),
            turns=turns,
            setup=dict(data.get("setup") or {}),
            workspace=data.get("workspace"),
            allowed_tools=_normalize_str_list(data.get("allowed_tools")),
            forbidden_tools=_normalize_str_list(data.get("forbidden_tools")),
            expected_behavior=dict(data.get("expected_behavior") or data.get("expected") or {}),
            grading=dict(data.get("grading") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
