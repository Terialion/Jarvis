from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal


SkillTrustLevel = Literal["trusted", "untrusted", "unknown"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SkillTrustStatus:
    name: str
    status: SkillTrustLevel = "unknown"
    reason: str | None = None
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
