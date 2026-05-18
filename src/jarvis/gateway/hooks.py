from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GatewayHookDecision:
    allowed: bool = True
    warnings: list[str] = field(default_factory=list)
    reason: str | None = None


def run_gateway_hooks(*, method: str, params: dict[str, Any] | None) -> GatewayHookDecision:
    _ = params
    if method.startswith("admin/"):
        return GatewayHookDecision(allowed=False, warnings=["admin method blocked"], reason="blocked_by_gateway_hook")
    return GatewayHookDecision(allowed=True)

