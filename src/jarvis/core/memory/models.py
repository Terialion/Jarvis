from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryRecord:
    memory_id: str
    memory_type: str
    key: str
    value: str
    metadata: dict[str, Any] = field(default_factory=dict)

