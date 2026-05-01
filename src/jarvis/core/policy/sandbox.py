from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SandboxPolicy:
    mode: str = "workspace-write"
    network_enabled: bool = False
    notes: list[str] = field(default_factory=lambda: ["Sandbox scaffold only. Full sandbox adapter remains a later sprint."])


def default_sandbox_policy() -> SandboxPolicy:
    return SandboxPolicy()

