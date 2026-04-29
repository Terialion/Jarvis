from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectProfile:
    project_id: str
    repo_root: str
    detected_test_command: str = "pytest -q"
    entrypoints: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

