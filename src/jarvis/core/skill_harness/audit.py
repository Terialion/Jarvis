from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_skill_audit_record(*, skill_id: str, action: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "skill_id": skill_id,
        "action": action,
        "detail": detail or {},
    }

