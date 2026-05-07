from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Literal

from ...agent.types import _redact_value


@dataclass(frozen=True)
class ApprovalPolicy:
    requires_write_approval: bool = True
    requires_shell_approval: bool = True
    requires_network_approval: bool = True
    notes: list[str] = field(default_factory=lambda: ["Approval is enforced by code, not by model output."])


def default_approval_policy() -> ApprovalPolicy:
    return ApprovalPolicy()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


ApprovalStatus = Literal["pending", "approved", "denied", "expired"]


@dataclass
class ApprovalRequest:
    approval_id: str
    tool_name: str
    arguments_preview: dict[str, Any] | str
    risk_level: str
    reason: str
    created_at: str
    expires_at: str | None = None
    status: ApprovalStatus = "pending"
    session_id: str | None = None
    turn_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class ApprovalResponse:
    approval_id: str
    decision: Literal["approved", "denied"]
    reason: str | None
    decided_at: str
    decided_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


class ApprovalStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._requests: dict[str, ApprovalRequest] = {}
        self._responses: dict[str, ApprovalResponse] = {}
        self._counter = 0

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._responses.clear()
            self._counter = 0

    def create_request(
        self,
        *,
        tool_name: str,
        arguments_preview: dict[str, Any] | str,
        risk_level: str,
        reason: str,
        session_id: str | None = None,
        turn_id: str | None = None,
        ttl_seconds: int | None = 900,
    ) -> ApprovalRequest:
        with self._lock:
            self._counter += 1
            approval_id = f"approval_{self._counter:06d}"
            expires_at = None
            if ttl_seconds:
                expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
            request = ApprovalRequest(
                approval_id=approval_id,
                tool_name=tool_name,
                arguments_preview=_redact_value(arguments_preview),
                risk_level=str(risk_level or "medium"),
                reason=str(reason or "approval required"),
                created_at=_utc_now(),
                expires_at=expires_at,
                session_id=session_id,
                turn_id=turn_id,
            )
            self._requests[approval_id] = request
            return request

    def get_request(self, approval_id: str) -> ApprovalRequest | None:
        with self._lock:
            request = self._requests.get(approval_id)
            if request is None:
                return None
            if request.status == "pending" and self._is_expired(request):
                request.status = "expired"
            return request

    def list_pending(self) -> list[ApprovalRequest]:
        with self._lock:
            rows: list[ApprovalRequest] = []
            for request in self._requests.values():
                if request.status == "pending" and self._is_expired(request):
                    request.status = "expired"
                if request.status == "pending":
                    rows.append(request)
            return rows

    def list_all(self) -> list[ApprovalRequest]:
        with self._lock:
            rows = list(self._requests.values())
            for request in rows:
                if request.status == "pending" and self._is_expired(request):
                    request.status = "expired"
            return rows

    def approve(self, approval_id: str, *, reason: str | None = None, decided_by: str | None = None) -> ApprovalResponse | None:
        with self._lock:
            request = self._requests.get(approval_id)
            if request is None:
                return None
            if request.status == "pending" and self._is_expired(request):
                request.status = "expired"
                return None
            request.status = "approved"
            response = ApprovalResponse(
                approval_id=approval_id,
                decision="approved",
                reason=reason,
                decided_at=_utc_now(),
                decided_by=decided_by,
            )
            self._responses[approval_id] = response
            return response

    def deny(self, approval_id: str, *, reason: str | None = None, decided_by: str | None = None) -> ApprovalResponse | None:
        with self._lock:
            request = self._requests.get(approval_id)
            if request is None:
                return None
            if request.status == "pending" and self._is_expired(request):
                request.status = "expired"
                return None
            request.status = "denied"
            response = ApprovalResponse(
                approval_id=approval_id,
                decision="denied",
                reason=reason,
                decided_at=_utc_now(),
                decided_by=decided_by,
            )
            self._responses[approval_id] = response
            return response

    def expire(self, approval_id: str) -> ApprovalRequest | None:
        with self._lock:
            request = self._requests.get(approval_id)
            if request is None:
                return None
            request.status = "expired"
            return request

    def find_matching_approved(
        self,
        *,
        tool_name: str,
        arguments_preview: dict[str, Any] | str,
        session_id: str | None = None,
    ) -> ApprovalRequest | None:
        preview = _redact_value(arguments_preview)
        with self._lock:
            for request in reversed(list(self._requests.values())):
                if request.status == "pending" and self._is_expired(request):
                    request.status = "expired"
                if request.status != "approved":
                    continue
                if request.tool_name != tool_name:
                    continue
                if session_id and request.session_id and request.session_id != session_id:
                    continue
                if request.arguments_preview == preview:
                    return request
            return None

    def find_matching_pending(
        self,
        *,
        tool_name: str,
        arguments_preview: dict[str, Any] | str,
        session_id: str | None = None,
    ) -> ApprovalRequest | None:
        preview = _redact_value(arguments_preview)
        with self._lock:
            for request in reversed(list(self._requests.values())):
                if request.status == "pending" and self._is_expired(request):
                    request.status = "expired"
                if request.status != "pending":
                    continue
                if request.tool_name != tool_name:
                    continue
                if session_id and request.session_id and request.session_id != session_id:
                    continue
                if request.arguments_preview == preview:
                    return request
            return None

    def find_matching_denied(
        self,
        *,
        tool_name: str,
        arguments_preview: dict[str, Any] | str,
        session_id: str | None = None,
    ) -> ApprovalRequest | None:
        preview = _redact_value(arguments_preview)
        with self._lock:
            for request in reversed(list(self._requests.values())):
                if request.status != "denied":
                    continue
                if request.tool_name != tool_name:
                    continue
                if session_id and request.session_id and request.session_id != session_id:
                    continue
                if request.arguments_preview == preview:
                    return request
            return None

    @staticmethod
    def _is_expired(request: ApprovalRequest) -> bool:
        if not request.expires_at:
            return False
        try:
            return datetime.now(timezone.utc) >= datetime.fromisoformat(request.expires_at)
        except ValueError:
            return False


_GLOBAL_APPROVAL_STORE = ApprovalStore()


def get_approval_store() -> ApprovalStore:
    return _GLOBAL_APPROVAL_STORE

