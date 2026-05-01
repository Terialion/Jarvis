from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExecPolicy:
    allowed_prefixes: list[list[str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=lambda: ["Allowed tool metadata can only narrow execution scope, never expand permissions."])


def default_exec_policy() -> ExecPolicy:
    return ExecPolicy()

