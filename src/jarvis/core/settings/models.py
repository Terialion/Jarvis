from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SettingsBundle:
    defaults: dict[str, Any] = field(default_factory=dict)
    global_settings: dict[str, Any] = field(default_factory=dict)
    project_settings: dict[str, Any] = field(default_factory=dict)
    runtime_overrides: dict[str, Any] = field(default_factory=dict)

