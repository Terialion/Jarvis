from __future__ import annotations

from threading import Lock
from uuid import uuid4

from .schema import GatewayAuditRecord
from ..store.redaction import redact_for_persistence


class GatewayAuditStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._rows: list[GatewayAuditRecord] = []

    def append(self, record: GatewayAuditRecord) -> GatewayAuditRecord:
        with self._lock:
            sanitized = GatewayAuditRecord(
                audit_id=record.audit_id or f"audit_{uuid4().hex[:12]}",
                request_id=record.request_id,
                channel=record.channel,
                method=record.method,
                user_id_hash=record.user_id_hash,
                client_name=record.client_name,
                permissions_profile=record.permissions_profile,
                redacted_input=redact_for_persistence(record.redacted_input),
                redacted_output=redact_for_persistence(record.redacted_output),
                status=record.status,
                approval_ids=list(record.approval_ids or []),
                tool_names=list(record.tool_names or []),
                resource_uris=list(record.resource_uris or []),
                prompt_names=list(record.prompt_names or []),
                error_code=record.error_code,
                error_message=str(redact_for_persistence(record.error_message or "")) or None,
                created_at=record.created_at,
                duration_ms=int(record.duration_ms or 0),
            )
            self._rows.append(sanitized)
            return sanitized

    def list(self, limit: int = 200) -> list[GatewayAuditRecord]:
        with self._lock:
            if limit <= 0:
                return []
            return list(self._rows[-limit:])

    def reset(self) -> None:
        with self._lock:
            self._rows.clear()


_GLOBAL_AUDIT_STORE = GatewayAuditStore()


def get_gateway_audit_store() -> GatewayAuditStore:
    return _GLOBAL_AUDIT_STORE

