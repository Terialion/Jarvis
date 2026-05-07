from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SkillQuarantineStatus:
    name: str
    quarantined: bool = False
    reason: str | None = None
    scanner_findings: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
