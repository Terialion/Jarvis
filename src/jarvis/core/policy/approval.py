from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ApprovalPolicy:
    requires_write_approval: bool = True
    requires_shell_approval: bool = True
    requires_network_approval: bool = True
    notes: list[str] = field(default_factory=lambda: ["Approval is enforced by code, not by model output."])


def default_approval_policy() -> ApprovalPolicy:
    return ApprovalPolicy()

