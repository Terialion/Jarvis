from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RecommendedAction:
    label: str
    reason: str
    priority: str = "medium"

