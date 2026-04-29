from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserPreferences:
    user_id: str
    prefer_safe_mode: bool = True
    prefer_short_answers: bool = False
    memory_opt_in: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

