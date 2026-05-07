from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SkillSource:
    name: str
    kind: str
    uri_or_path: str
    enabled: bool = True
    priority: int = 50
    added_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
