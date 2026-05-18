"""Team protocols — structured request-response FSMs for shutdown and plan approval."""

from __future__ import annotations

import threading
import uuid
from typing import Any


class ShutdownTracker:
    """Correlates shutdown_request → shutdown_response by request_id.

    FSM: pending → approved | rejected
    """

    def __init__(self) -> None:
        self._requests: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, target: str) -> str:
        """Create a new shutdown request for *target*. Returns request_id."""
        req_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._requests[req_id] = {"target": target, "status": "pending"}
        return req_id

    def resolve(self, request_id: str, approved: bool) -> dict[str, Any] | None:
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                return None
            req["status"] = "approved" if approved else "rejected"
            return dict(req)

    def status(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            req = self._requests.get(request_id)
            return dict(req) if req else None


class PlanTracker:
    """Correlates plan_approval → plan_approval_response by request_id.

    FSM: pending → approved | rejected
    """

    def __init__(self) -> None:
        self._requests: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def submit(self, from_name: str, plan_text: str) -> str:
        """Submit a plan for review. Returns request_id."""
        req_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._requests[req_id] = {
                "from": from_name,
                "plan": plan_text,
                "status": "pending",
            }
        return req_id

    def review(self, request_id: str, approved: bool, feedback: str = "") -> dict[str, Any] | None:
        with self._lock:
            req = self._requests.get(request_id)
            if req is None:
                return None
            req["status"] = "approved" if approved else "rejected"
            req["feedback"] = feedback
            return dict(req)

    def status(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            req = self._requests.get(request_id)
            return dict(req) if req else None
