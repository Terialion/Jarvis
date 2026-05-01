from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SessionState:
    workspace_root: Path | None = None
    session_id: str | None = None

