from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class GatewayRequest:
    request_id: str
    channel: str
    user_id: str | None
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GatewayResponse:
    request_id: str
    status: str
    output: str
    agent_result: dict[str, Any] | None = None
    events_redacted: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChannelSpec:
    name: str
    kind: Literal["api", "mcp", "cli", "webhook", "mock", "control_surface"]
    enabled: bool
    permissions_profile: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GatewayAuditRecord:
    audit_id: str
    request_id: str
    channel: str
    method: str
    user_id_hash: str | None
    client_name: str | None
    permissions_profile: str
    redacted_input: dict[str, Any] | str
    redacted_output: dict[str, Any] | str
    status: str
    approval_ids: list[str] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    resource_uris: list[str] = field(default_factory=list)
    prompt_names: list[str] = field(default_factory=list)
    error_code: int | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=utc_now)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class McpJsonRpcRequest:
    jsonrpc: Literal["2.0"]
    id: str | int | None
    method: str
    params: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class McpJsonRpcResponse:
    jsonrpc: Literal["2.0"]
    id: str | int | None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class McpCapability:
    name: str
    description: str
    mutating: bool
    requires_approval: bool
    input_schema: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "mutating": self.mutating,
            "requires_approval": self.requires_approval,
            "inputSchema": self.input_schema,
        }

