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
    workspace: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    expected_behavior: dict[str, Any] = field(default_factory=dict)
    grading: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkCase":
        return cls(
            id=str(data.get("id") or ""),
            suite=str(data.get("suite") or ""),
            category=str(data.get("category") or ""),
            input=str(data.get("input") or ""),
            workspace=data.get("workspace"),
            allowed_tools=_normalize_str_list(data.get("allowed_tools")),
            forbidden_tools=_normalize_str_list(data.get("forbidden_tools")),
            expected_behavior=dict(data.get("expected_behavior") or {}),
            grading=dict(data.get("grading") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
