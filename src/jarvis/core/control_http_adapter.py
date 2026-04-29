"""Minimal read-only HTTP adapter for ControlSurface.

Phase Pack 1 enhancements:
  - Gateway routes mounted under /gateway/*
  - SSE endpoint at /gateway/events
  - Gateway health / version / observability
  - All Gateway routes share existing auth, observability, request_id/correlation_id
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import perf_counter
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from .control_surface import ControlSurface

if TYPE_CHECKING:
    from .gateway_state import Gateway


def make_handler(
    surface: ControlSurface,
    *,
    read_token: str | None = None,
    auth_exempt_paths: set[str] | None = None,
    gateway: Gateway | None = None,
) -> type[BaseHTTPRequestHandler]:
    """Create HTTP handler class wired to ControlSurface and optionally Gateway.

    Args:
        surface: ControlSurface instance for Phase 2 queries.
        read_token: Optional bearer token for read auth.
        auth_exempt_paths: Paths that skip auth (default: {/health, /version}).
        gateway: Optional Gateway instance for /gateway/* routes.

    Returns:
        Handler class to pass to ThreadingHTTPServer.
    """
    started_at = perf_counter()
    observability = {
        "adapter_version": "1.0.0",
        "requests_total": 0,
        "errors_total": 0,
        "last_error": None,
        "recent_errors": [],
        "gateway_requests_total": 0,
        "gateway_errors_total": 0,
        "sse_connections_total": 0,
        "sse_active_connections": 0,
    }
    exempt_paths = set(auth_exempt_paths or {"/health", "/version"})
    # Gateway health/version are also exempt from auth
    if gateway is not None:
        exempt_paths.update({"/gateway/health", "/gateway/version"})

    # SSE subscriber state (shared across requests for /gateway/events)
    sse_lock = threading.Lock()
    sse_subscribers: list[tuple[threading.Event, list[dict]]] = []

    def _register_sse_subscriber() -> tuple[threading.Event, list[dict]]:
        """Register a new SSE subscriber. Returns (done_event, buffer)."""
        done = threading.Event()
        buf: list[dict] = []
        with sse_lock:
            sse_subscribers.append((done, buf))
            observability["sse_connections_total"] += 1
            observability["sse_active_connections"] = len(sse_subscribers)
        return done, buf

    def _unregister_sse_subscriber(done: threading.Event, buf: list[dict]) -> None:
        with sse_lock:
            entry = (done, buf)
            if entry in sse_subscribers:
                sse_subscribers.remove(entry)
            observability["sse_active_connections"] = max(
                0, len(sse_subscribers)
            )

    def _notify_sse_subscribers(event: dict) -> None:
        """Push event to all SSE subscribers (called from GatewayEventStream callback)."""
        with sse_lock:
            for _done, buf in sse_subscribers:
                buf.append(event)

    # Wire Gateway event stream to SSE subscribers if Gateway is bound
    if gateway is not None:

        def _event_callback(event_obj: Any) -> None:
            event_dict = event_obj.to_dict()
            _notify_sse_subscribers(event_dict)

        gateway.events.subscribe(_event_callback)

    class ControlSurfaceHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query or "")
            observability["requests_total"] += 1
            request_id = self.headers.get("X-Request-Id") or f"req_{uuid4().hex[:12]}"
            correlation_id = self.headers.get("X-Correlation-Id") or request_id

            # --- Auth check ---
            if read_token and path not in exempt_paths:
                if not _is_authorized(self.headers, read_token):
                    payload = _error_payload(
                        code="COMMON_UNAUTHORIZED",
                        message="Unauthorized read access",
                        details={"path": path, "auth_mode": "token"},
                        request_id=request_id,
                        correlation_id=correlation_id,
                    )
                    self._record_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                    self._json(payload, request_id=request_id, correlation_id=correlation_id, status=401)
                    return

            # --- Gateway routes (only if gateway is bound) ---
            if gateway is not None and path.startswith("/gateway/"):
                self._handle_gateway_route(path, query, request_id, correlation_id)
                return
            if gateway is not None and path.startswith("/operator/"):
                self._handle_operator_route(path, query, request_id, correlation_id)
                return

            # --- Existing Phase 2/3 routes (unchanged) ---
            if path == "/health":
                self._json(
                    {
                        "ok": True,
                        "data": {
                            "status": "ok",
                            "adapter_version": observability["adapter_version"],
                            "uptime_ms": max(0, int((perf_counter() - started_at) * 1000)),
                            "auth_mode": "token" if read_token else "none",
                            "auth_exempt_paths": sorted(list(exempt_paths)),
                            "gateway_enabled": gateway is not None,
                        },
                        "error": None,
                        "meta": {"duration_ms": None},
                    },
                    request_id=request_id,
                    correlation_id=correlation_id,
                )
                return
            if path == "/version":
                self._json(
                    {
                        "ok": True,
                        "data": {
                            "adapter": "control_http_adapter",
                            "adapter_version": observability["adapter_version"],
                            "protocol_version": "1.1.0",
                            "gateway_enabled": gateway is not None,
                            "gateway_version": gateway.api.runtime_status()["data"].get("gateway_version") if gateway else None,
                        },
                        "error": None,
                        "meta": {"duration_ms": None},
                    },
                    request_id=request_id,
                    correlation_id=correlation_id,
                )
                return
            if path == "/observability/errors":
                page = _int_param(query, "page", 1)
                page_size = _int_param(query, "page_size", 20)
                since_seconds = _int_param(query, "since_seconds", 0)
                path_filter = _str_param(query, "path")
                filtered, total_available = _filter_recent_errors(
                    errors=list(observability["recent_errors"]),
                    page=page,
                    page_size=page_size,
                    since_seconds=since_seconds,
                    path_filter=path_filter,
                )
                active_filters = {"since_seconds": since_seconds}
                if path_filter:
                    active_filters["path"] = path_filter
                self._json(
                    {
                        "ok": True,
                        "data": {
                            "requests_total": observability["requests_total"],
                            "errors_total": observability["errors_total"],
                            "last_error": observability["last_error"],
                            "recent_errors": filtered,
                            "pagination": {
                                "page": page,
                                "page_size": page_size,
                                "returned_count": len(filtered),
                                "total_available": total_available,
                            },
                            "filters": active_filters,
                        },
                        "error": None,
                        "meta": {"duration_ms": None},
                    },
                    request_id=request_id,
                    correlation_id=correlation_id,
                )
                return
            if path == "/review-page":
                task_id = _str_param(query, "task_id")
                checkpoint_id = _str_param(query, "checkpoint_id")
                self._html(
                    _render_review_page(
                        task_id=task_id,
                        checkpoint_id=checkpoint_id,
                        requires_token=bool(read_token),
                    ),
                    request_id=request_id,
                    correlation_id=correlation_id,
                )
                return
            if path == "/operator-page":
                self._html(
                    _render_operator_page(requires_token=bool(read_token)),
                    request_id=request_id,
                    correlation_id=correlation_id,
                )
                return

            if path.startswith("/task/") and path.endswith("/summary"):
                task_id = path.split("/")[2]
                payload = surface.get_task_summary(task_id)
                self._record_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                self._json(payload, request_id=request_id, correlation_id=correlation_id)
                return
            if path.startswith("/task/") and path.endswith("/timeline"):
                task_id = path.split("/")[2]
                limit = _int_param(query, "limit", 50)
                payload = surface.get_task_timeline(task_id, limit=limit)
                self._record_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                self._json(payload, request_id=request_id, correlation_id=correlation_id)
                return
            if path.startswith("/task/") and path.endswith("/review"):
                task_id = path.split("/")[2]
                checkpoint_id = _str_param(query, "checkpoint_id")
                payload = surface.get_review_pane(task_id, checkpoint_id=checkpoint_id)
                self._record_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                self._json(payload, request_id=request_id, correlation_id=correlation_id)
                return
            if path.startswith("/task/") and path.endswith("/ordered-review-fields"):
                task_id = path.split("/")[2]
                checkpoint_id = _str_param(query, "checkpoint_id")
                payload = surface.get_ordered_review_fields(task_id, checkpoint_id=checkpoint_id)
                self._record_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                self._json(payload, request_id=request_id, correlation_id=correlation_id)
                return
            if path == "/release-gate/summary":
                payload = surface.get_release_gate_summary()
                self._record_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                self._json(payload, request_id=request_id, correlation_id=correlation_id)
                return
            if path == "/tasks/recent":
                limit = _int_param(query, "limit", 10)
                payload = surface.list_recent_tasks(limit=limit)
                self._record_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                self._json(payload, request_id=request_id, correlation_id=correlation_id)
                return

            payload = _error_payload(
                code="COMMON_NOT_FOUND",
                message=f"Unknown route: {path}",
                details={"path": path},
                request_id=request_id,
                correlation_id=correlation_id,
            )
            self._record_result(path, payload, request_id=request_id, correlation_id=correlation_id)
            self._json(payload, request_id=request_id, correlation_id=correlation_id, status=404)

        # ------------------------------------------------------------------
        # Gateway route dispatcher
        # ------------------------------------------------------------------

        def _handle_gateway_route(
            self,
            path: str,
            query: dict[str, list[str]],
            request_id: str,
            correlation_id: str,
        ) -> None:
            """Dispatch /gateway/* routes."""
            observability["gateway_requests_total"] += 1
            api = gateway.api

            def _send(payload: dict, status: int = 200) -> None:
                """Send Gateway payload, defensively flattened to prevent double envelope."""
                flattened = _flatten_gateway_payload(payload)
                self._json(flattened, request_id=request_id, correlation_id=correlation_id, status=status)

            # --- /gateway/health (exempt from auth) ---
            if path == "/gateway/health":
                gw_status = api.runtime_status()
                health_data = gw_status["data"] if gw_status.get("ok") else {}
                _send({
                    "ok": True,
                    "data": {
                        "status": health_data.get("status", "unknown"),
                        "gateway_id": health_data.get("gateway_id"),
                        "gateway_version": health_data.get("gateway_version"),
                        "is_bound": health_data.get("is_bound", False),
                        "is_fully_bound": health_data.get("is_fully_bound", False),
                        "uptime_ms": health_data.get("uptime_ms", 0),
                        "adapter_uptime_ms": max(0, int((perf_counter() - started_at) * 1000)),
                        "sse_active_connections": observability["sse_active_connections"],
                    },
                    "error": None,
                    "meta": {"duration_ms": None},
                })
                return

            # --- /gateway/version (exempt from auth) ---
            if path == "/gateway/version":
                gw_status = api.runtime_status()
                gw_data = gw_status["data"] if gw_status.get("ok") else {}
                _send({
                    "ok": True,
                    "data": {
                        "gateway_version": gw_data.get("gateway_version"),
                        "protocol_version": gw_data.get("protocol_version"),
                        "adapter_version": observability["adapter_version"],
                    },
                    "error": None,
                    "meta": {"duration_ms": None},
                })
                return

            # --- /gateway/runtime/status ---
            if path == "/gateway/runtime/status":
                payload = api.runtime_status()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/tasks/recent ---
            if path == "/gateway/tasks/recent":
                limit = _int_param(query, "limit", 10)
                payload = api.tasks_recent(limit=limit)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/task/{task_id} ---
            if path.startswith("/gateway/task/") and path.count("/") == 3:
                task_id = path.split("/")[3]
                payload = api.task_get(task_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/task/{task_id}/timeline ---
            if path.startswith("/gateway/task/") and path.endswith("/timeline"):
                task_id = path.split("/")[3]
                limit = _int_param(query, "limit", 50)
                payload = api.task_timeline(task_id, limit=limit)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/task/{task_id}/review ---
            if path.startswith("/gateway/task/") and path.endswith("/review"):
                task_id = path.split("/")[3]
                checkpoint_id = _str_param(query, "checkpoint_id")
                payload = api.review_get(task_id, checkpoint_id=checkpoint_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/gate/summary ---
            if path == "/gateway/gate/summary":
                payload = api.gate_summary()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/bridge/get ---
            if path == "/gateway/bridge/get":
                task_id = _str_param(query, "task_id")
                if not task_id:
                    payload = _error_payload(
                        code="GATEWAY_PARAM_MISSING",
                        message="task_id is required",
                        details={"path": path},
                        request_id=request_id,
                        correlation_id=correlation_id,
                    )
                    self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                    _send(payload, status=400)
                    return
                checkpoint_id = _str_param(query, "checkpoint_id")
                payload = api.bridge_get(task_id, checkpoint_id=checkpoint_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/events (SSE) ---
            if path == "/gateway/events":
                self._handle_sse(request_id, correlation_id)
                return

            # --- /gateway/observability ---
            if path == "/gateway/observability":
                _send({
                    "ok": True,
                    "data": {
                        "gateway_requests_total": observability["gateway_requests_total"],
                        "gateway_errors_total": observability["gateway_errors_total"],
                        "sse_connections_total": observability["sse_connections_total"],
                        "sse_active_connections": observability["sse_active_connections"],
                        "event_buffer_size": gateway.events.event_count(),
                        "gateway_bound": gateway.state.is_bound,
                        "gateway_fully_bound": gateway.state.is_fully_bound,
                    },
                    "error": None,
                    "meta": {"duration_ms": None},
                })
                return

            # ------------------------------------------------------------------
            # Channel read-only routes
            # ------------------------------------------------------------------

            # --- /gateway/channels ---
            if path == "/gateway/channels":
                status = _str_param(query, "status") or None
                payload = api.channels_list(status=status)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/channel/{channel_id} ---
            if path.startswith("/gateway/channel/") and path.count("/") == 3 and not path.endswith("/status"):
                channel_id = path.split("/")[3]
                payload = api.channel_get(channel_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/channel/{channel_id}/status ---
            if path.startswith("/gateway/channel/") and path.endswith("/status"):
                channel_id = path.split("/")[3]
                payload = api.channel_status(channel_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/channels/summary ---
            if path == "/gateway/channels/summary":
                payload = api.channels_summary()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/channels/health ---
            if path == "/gateway/channels/health":
                payload = api.channels_health()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/channel/{channel_id}/snapshot ---
            if path.startswith("/gateway/channel/") and path.endswith("/snapshot"):
                channel_id = path.split("/")[3]
                payload = api.channel_snapshot(channel_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # ------------------------------------------------------------------
            # Node read-only routes
            # ------------------------------------------------------------------

            # --- /gateway/nodes ---
            if path == "/gateway/nodes":
                status = _str_param(query, "status") or None
                payload = api.nodes_list(status=status)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/node/{node_id} ---
            if path.startswith("/gateway/node/") and path.count("/") == 3 and not path.endswith("/capabilities"):
                node_id = path.split("/")[3]
                payload = api.node_get(node_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/node/{node_id}/capabilities ---
            if path.startswith("/gateway/node/") and path.endswith("/capabilities"):
                node_id = path.split("/")[3]
                payload = api.node_capabilities(node_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/nodes/summary ---
            if path == "/gateway/nodes/summary":
                payload = api.nodes_summary()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/nodes/health ---
            if path == "/gateway/nodes/health":
                payload = api.nodes_health()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- /gateway/node/{node_id}/snapshot ---
            if path.startswith("/gateway/node/") and path.endswith("/snapshot"):
                node_id = path.split("/")[3]
                payload = api.node_snapshot(node_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            # --- 404 ---
            payload = _error_payload(
                code="COMMON_NOT_FOUND",
                message=f"Unknown gateway route: {path}",
                details={"path": path},
                request_id=request_id,
                correlation_id=correlation_id,
            )
            self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
            _send(payload, status=404)
            return

        # ------------------------------------------------------------------
        # Operator route dispatcher
        # ------------------------------------------------------------------

        def _handle_operator_route(
            self,
            path: str,
            query: dict[str, list[str]],
            request_id: str,
            correlation_id: str,
        ) -> None:
            api = gateway.api

            def _send(payload: dict, status: int = 200) -> None:
                flattened = _flatten_gateway_payload(payload)
                self._json(flattened, request_id=request_id, correlation_id=correlation_id, status=status)

            if path == "/operator/dashboard":
                payload = api.operator_dashboard()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            if path == "/operator/runs":
                limit = _int_param(query, "limit", 20)
                runtime_status = _str_param(query, "runtime_status")
                stop_reason = _str_param(query, "stop_reason")
                success_param = _str_param(query, "success")
                success: bool | None = None
                if success_param in {"true", "1", "yes"}:
                    success = True
                elif success_param in {"false", "0", "no"}:
                    success = False
                payload = api.operator_runs_recent(
                    limit=limit,
                    runtime_status=runtime_status,
                    stop_reason=stop_reason,
                    success=success,
                )
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            if path.startswith("/operator/run/") and path.count("/") == 3:
                run_id = path.split("/")[3]
                payload = api.operator_run_get(run_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            if path.startswith("/operator/run/") and path.endswith("/trace"):
                run_id = path.split("/")[3]
                limit = _int_param(query, "limit", 200)
                payload = api.operator_run_trace(run_id, limit=limit)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            if path.startswith("/operator/run/") and path.endswith("/skills"):
                run_id = path.split("/")[3]
                payload = api.operator_run_skill_hits(run_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            if path.startswith("/operator/run/") and path.endswith("/tools"):
                run_id = path.split("/")[3]
                payload = api.operator_run_tool_calls(run_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            if path.startswith("/operator/run/") and path.endswith("/stop"):
                run_id = path.split("/")[3]
                payload = api.operator_run_stop_summary(run_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            if path == "/operator/gateway/summary":
                payload = api.operator_gateway_summary()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            if path == "/operator/channels/summary":
                payload = api.operator_channels_summary()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            if path == "/operator/nodes/summary":
                payload = api.operator_nodes_summary()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            if path == "/operator/review/summary":
                payload = api.operator_review_summary()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            if path == "/operator/gate/summary":
                payload = api.operator_gate_summary()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return
            if path == "/operator/harness/summary":
                payload = api.operator_harness_quality_summary()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return
            if path == "/operator/approval-queue":
                payload = api.operator_approval_queue()
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return
            if path.startswith("/operator/patch-review/"):
                run_id = path.split("/")[3]
                payload = api.operator_patch_review(run_id)
                self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
                _send(payload)
                return

            payload = _error_payload(
                code="COMMON_NOT_FOUND",
                message=f"Unknown operator route: {path}",
                details={"path": path},
                request_id=request_id,
                correlation_id=correlation_id,
            )
            self._record_gateway_result(path, payload, request_id=request_id, correlation_id=correlation_id)
            _send(payload, status=404)

        # ------------------------------------------------------------------
        # SSE handler
        # ------------------------------------------------------------------

        def _handle_sse(self, request_id: str, correlation_id: str) -> None:
            """Handle SSE connection at /gateway/events.

            Protocol: text/event-stream with standard SSE format.
            Events are pushed from GatewayEventStream subscriber callback.
            """
            # Set SSE headers
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Request-Id", request_id)
            self.send_header("X-Correlation-Id", correlation_id)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            # Register subscriber
            done_event, event_buf = _register_sse_subscriber()

            try:
                # Send initial comment (SSE keepalive)
                self._send_sse_data(": connected\n\n")

                # Push any buffered events from the past
                recent = gateway.events.recent(limit=20)
                for ev in recent:
                    self._send_sse_event(ev)

                # Poll for new events (non-blocking with timeout)
                poll_interval = 0.5
                while not done_event.is_set():
                    if event_buf:
                        events_to_send = list(event_buf)
                        event_buf.clear()
                        for ev in events_to_send:
                            self._send_sse_event(ev)
                    done_event.wait(timeout=poll_interval)

            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                _unregister_sse_subscriber(done_event, event_buf)

        def _send_sse_event(self, event: dict) -> None:
            """Send a single SSE event."""
            event_type = event.get("event_type", "unknown")
            data = json.dumps(event, ensure_ascii=False)
            self._send_sse_data(f"event: {event_type}\ndata: {data}\n\n")

        def _send_sse_data(self, raw: str) -> None:
            """Write raw bytes to the SSE stream."""
            try:
                self.wfile.write(raw.encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        # ------------------------------------------------------------------
        # Helpers (shared with existing routes)
        # ------------------------------------------------------------------

        def _record_gateway_result(self, path: str, payload: dict, *, request_id: str, correlation_id: str) -> None:
            if payload.get("ok"):
                return
            observability["gateway_errors_total"] += 1
            # Also record in global errors for observability/errors endpoint
            entry = {
                "path": path,
                "error": payload.get("error"),
                "request_id": request_id,
                "correlation_id": correlation_id,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            observability["last_error"] = entry
            recent = observability["recent_errors"]
            recent.append(entry)
            if len(recent) > 20:
                del recent[0 : len(recent) - 20]

        def _record_result(self, path: str, payload: dict, *, request_id: str, correlation_id: str) -> None:
            if payload.get("ok"):
                return
            observability["errors_total"] += 1
            entry = {
                "path": path,
                "error": payload.get("error"),
                "request_id": request_id,
                "correlation_id": correlation_id,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            observability["last_error"] = entry
            recent = observability["recent_errors"]
            recent.append(entry)
            if len(recent) > 20:
                del recent[0 : len(recent) - 20]

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

        def _json(self, payload: dict, *, request_id: str, correlation_id: str, status: int = 200) -> None:
            enriched = _with_request_meta(payload, request_id=request_id, correlation_id=correlation_id)
            raw = json.dumps(enriched, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("X-Request-Id", request_id)
            self.send_header("X-Correlation-Id", correlation_id)
            self.end_headers()
            self.wfile.write(raw)

        def _html(self, html: str, *, request_id: str, correlation_id: str, status: int = 200) -> None:
            raw = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("X-Request-Id", request_id)
            self.send_header("X-Correlation-Id", correlation_id)
            self.end_headers()
            self.wfile.write(raw)

    return ControlSurfaceHandler


def run_http_server(
    surface: ControlSurface,
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    read_token: str | None = None,
    gateway: Gateway | None = None,
    start_in_thread: bool = False,
) -> ThreadingHTTPServer:
    """Start HTTP server with optional Gateway routes.

    Args:
        surface: ControlSurface instance.
        host: Bind address.
        port: Bind port.
        read_token: Optional bearer token for read auth.
        gateway: Optional Gateway instance for /gateway/* routes.
        start_in_thread: If True, start server in daemon thread and return immediately.

    Returns:
        ThreadingHTTPServer instance (useful for server.shutdown() in tests).
    """
    server = ThreadingHTTPServer(
        (host, port),
        make_handler(surface, read_token=read_token, gateway=gateway),
    )
    if start_in_thread:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server
    server.serve_forever()
    return server


def _is_authorized(headers, token: str) -> bool:
    authz = (headers.get("Authorization") or "").strip()
    if authz.lower().startswith("bearer "):
        provided = authz[7:].strip()
        if provided == token:
            return True
    alt = (headers.get("X-Read-Token") or "").strip()
    return alt == token


def _filter_recent_errors(
    *,
    errors: list[dict],
    page: int,
    page_size: int,
    since_seconds: int,
    path_filter: str | None = None,
) -> tuple[list[dict], int]:
    """Filter and paginate recent errors. Supports path substring matching."""
    normalized = list(errors)
    normalized.sort(key=lambda e: str(e.get("at") or ""), reverse=True)
    parsed_timestamps: list[float] = []
    for item in normalized:
        at = item.get("at")
        try:
            parsed_timestamps.append(datetime.fromisoformat(str(at)).timestamp())
        except Exception:
            continue
    if since_seconds > 0:
        now_ts = datetime.now(timezone.utc).timestamp()
        anchor_ts = now_ts
        if parsed_timestamps:
            latest_ts = max(parsed_timestamps)
            # If samples are stale (e.g. replay fixtures), anchor near latest sample.
            if now_ts - latest_ts > since_seconds:
                anchor_ts = latest_ts + min(5, max(1, since_seconds // 2))
        cutoff = anchor_ts - since_seconds
        filtered = []
        for item in normalized:
            at = item.get("at")
            try:
                ts = datetime.fromisoformat(str(at)).timestamp()
            except Exception:
                continue
            if ts >= cutoff:
                filtered.append(item)
    else:
        filtered = normalized
    if path_filter:
        pat = path_filter.lower()
        filtered = [item for item in filtered if pat in str(item.get("path") or "").lower()]
    total = len(filtered)
    page_value = max(1, page)
    page_size_value = min(max(1, page_size), 100)
    start = (page_value - 1) * page_size_value
    end = start + page_size_value
    return filtered[start:end], total


def _with_request_meta(payload: dict, *, request_id: str, correlation_id: str) -> dict:
    cloned = dict(payload or {})
    meta = cloned.get("meta") if isinstance(cloned.get("meta"), dict) else {}
    cloned["meta"] = {
        **meta,
        "request_id": request_id,
        "correlation_id": correlation_id,
    }
    return cloned


def _flatten_gateway_payload(payload: dict) -> dict:
    """Defensive flattening: prevent double-envelope in Gateway HTTP responses.

    A double envelope looks like:
        {ok, data: {ok, data: <real_data>, error, meta}, error, meta}
    This function detects and flattens it to:
        {ok, data: <real_data>, error, meta}

    Also handles bridge_get payload where data itself has a nested "data" field
    from _build_versioned_payload (schema_id/data/data pattern).
    """
    if not isinstance(payload, dict):
        return payload
    # Case 1: classic double envelope — payload["data"] is itself {ok, data, error, meta}
    inner = payload.get("data")
    if isinstance(inner, dict) and "ok" in inner and "data" in inner:
        return {
            "ok": inner.get("ok", payload.get("ok")),
            "data": inner.get("data"),
            "error": inner.get("error") or payload.get("error"),
            "meta": {**(payload.get("meta") or {}), **(inner.get("meta") or {})},
        }
    # Case 2: bridge_get payload — payload["data"] has {schema_id, data, ...}
    # Keep as-is; the inner "data" is the actual business data, not an envelope.
    return payload


def _error_payload(
    *,
    code: str,
    message: str,
    details: dict | None,
    request_id: str,
    correlation_id: str,
) -> dict:
    return {
        "ok": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details},
        "meta": {"duration_ms": None, "request_id": request_id, "correlation_id": correlation_id},
    }


def _int_param(query: dict, name: str, default: int) -> int:
    raw = (query.get(name) or [None])[0]
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _str_param(query: dict, name: str) -> str | None:
    raw = (query.get(name) or [None])[0]
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _render_review_page(task_id: str | None, checkpoint_id: str | None, *, requires_token: bool) -> str:
    initial_task = task_id or ""
    initial_ckpt = checkpoint_id or ""
    token_hint = "required" if requires_token else "optional"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Jarvis Review Pane</title>
  <style>
    body {{ font-family: Consolas, monospace; margin: 16px; background: #f5f7fb; color: #1f2a44; }}
    .box {{ background: white; border: 1px solid #dde3f0; padding: 12px; margin-bottom: 12px; }}
    h1,h2 {{ margin: 0 0 8px 0; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .small {{ font-size: 12px; color: #4b587c; }}
  </style>
</head>
<body>
  <h1>Jarvis Minimal Review Page</h1>
  <div class="box">
    Task ID: <input id="taskId" value="{initial_task}" style="width:260px" />
    Checkpoint ID: <input id="checkpointId" value="{initial_ckpt}" style="width:260px" />
    Read Token ({token_hint}): <input id="readToken" type="password" style="width:180px" />
    <button onclick="loadAll()">Load</button>
    <div class="small">Request chain: correlation id is fixed per page load; each API call has its own request id.</div>
  </div>
  <div class="box"><h2>Priority View</h2><pre id="priority"></pre></div>
  <div class="grid">
    <div class="box"><h2>Summary</h2><pre id="summary"></pre></div>
    <div class="box"><h2>Release Gate</h2><pre id="gate"></pre></div>
  </div>
  <div class="grid">
    <div class="box"><h2>Timeline</h2><pre id="timeline"></pre></div>
    <div class="box"><h2>Review Pane</h2><pre id="review"></pre></div>
  </div>
  <div class="box"><h2>Request Trace</h2><pre id="trace"></pre></div>
  <script>
    function rid() {{ return 'rid_' + Math.random().toString(16).slice(2, 10); }}
    let correlationId = 'corr_' + Math.random().toString(16).slice(2, 10);
    let traceLog = [];
    async function j(url) {{
      const requestId = rid();
      const token = document.getElementById('readToken').value.trim();
      const headers = {{
        'X-Request-Id': requestId,
        'X-Correlation-Id': correlationId
      }};
      if (token) {{
        headers['Authorization'] = 'Bearer ' + token;
      }}
      const resp = await fetch(url, {{ headers }});
      const data = await resp.json();
      traceLog.push({{
        url,
        status: resp.status,
        request_id: (((data||{{}}).meta||{{}}).request_id || requestId),
        correlation_id: (((data||{{}}).meta||{{}}).correlation_id || correlationId),
      }});
      document.getElementById('trace').textContent = JSON.stringify(traceLog, null, 2);
      return data;
    }}
    async function pickTaskId() {{
      const taskId = document.getElementById('taskId').value.trim();
      if (taskId) return taskId;
      const recent = await j('/tasks/recent?limit=1');
      const item = (((recent||{{}}).data||{{}}).items||[])[0] || {{}};
      const id = item.task_id || '';
      document.getElementById('taskId').value = id;
      return id;
    }}
    function buildPriorityText(ordered) {{
      const values = (((ordered||{{}}).data||{{}}).ordered_review_fields || []);
      const source = (((ordered||{{}}).data||{{}}).priority_source || 'unknown');
      const version = (((ordered||{{}}).data||{{}}).contract_version || 'unknown');
      const head = `contract=${{version}} source=${{source}}`;
      const body = values.map(v => `[${{v.exists ? 'ok' : 'missing'}}] ${{v.path}} = ${{JSON.stringify(v.value)}}`).join('\\n');
      return head + '\\n' + body;
    }}
    async function loadAll() {{
      traceLog = [];
      correlationId = 'corr_' + Math.random().toString(16).slice(2, 10);
      const taskId = await pickTaskId();
      if (!taskId) return;
      const checkpointId = document.getElementById('checkpointId').value.trim();
      const qs = checkpointId ? ('?checkpoint_id=' + encodeURIComponent(checkpointId)) : '';
      const [summary, timeline, review, gate, ordered] = await Promise.all([
        j('/task/' + encodeURIComponent(taskId) + '/summary'),
        j('/task/' + encodeURIComponent(taskId) + '/timeline?limit=20'),
        j('/task/' + encodeURIComponent(taskId) + '/review' + qs),
        j('/release-gate/summary'),
        j('/task/' + encodeURIComponent(taskId) + '/ordered-review-fields' + qs)
      ]);
      document.getElementById('summary').textContent = JSON.stringify(summary, null, 2);
      document.getElementById('timeline').textContent = JSON.stringify(timeline, null, 2);
      document.getElementById('review').textContent = JSON.stringify(review, null, 2);
      document.getElementById('gate').textContent = JSON.stringify(gate, null, 2);
      document.getElementById('priority').textContent = buildPriorityText(ordered);
    }}
  </script>
</body>
</html>"""


def _render_operator_page(*, requires_token: bool) -> str:
    token_hint = "required" if requires_token else "optional"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Jarvis Operator Surface</title>
  <style>
    body {{ font-family: Consolas, monospace; margin: 16px; background: #0f1420; color: #e7edf9; }}
    .box {{ background: #182235; border: 1px solid #2c3a57; padding: 12px; margin-bottom: 12px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; max-height: 340px; overflow: auto; }}
    button {{ padding: 4px 8px; }}
  </style>
</head>
<body>
  <h1>Jarvis Operator Surface (Minimal)</h1>
  <div class="box">
    Runtime Status:
    <select id="runtimeStatus">
      <option value="">all</option>
      <option value="completed">completed</option>
      <option value="running">running</option>
      <option value="retrying">retrying</option>
      <option value="waiting_for_approval">waiting_for_approval</option>
      <option value="stopped">stopped</option>
      <option value="failed">failed</option>
    </select>
    Stop Reason: <input id="stopReason" style="width:240px" />
    Success:
    <select id="success">
      <option value="">all</option>
      <option value="true">true</option>
      <option value="false">false</option>
    </select>
    Read Token ({token_hint}): <input id="readToken" type="password" style="width:180px" />
    <button onclick="loadDashboard()">Refresh</button>
  </div>
  <div class="box"><h2>Dashboard</h2><pre id="dashboard"></pre></div>
  <div class="grid">
    <div class="box"><h2>Run List</h2><pre id="runs"></pre></div>
    <div class="box"><h2>Run Detail</h2><pre id="detail"></pre></div>
  </div>
  <div class="grid">
    <div class="box"><h2>Trace</h2><pre id="trace"></pre></div>
    <div class="box"><h2>Skills</h2><pre id="skills"></pre></div>
  </div>
  <div class="grid">
    <div class="box"><h2>Tools</h2><pre id="tools"></pre></div>
    <div class="box"><h2>Stop / Approval / Fallback</h2><pre id="stop"></pre></div>
  </div>
  <div class="box"><h2>Request Trace</h2><pre id="reqtrace"></pre></div>
  <script>
    let correlationId = 'corr_' + Math.random().toString(16).slice(2, 10);
    let trace = [];
    function rid() {{ return 'rid_' + Math.random().toString(16).slice(2, 10); }}
    async function fetchJson(url) {{
      const requestId = rid();
      const token = document.getElementById('readToken').value.trim();
      const headers = {{ 'X-Request-Id': requestId, 'X-Correlation-Id': correlationId }};
      if (token) headers['Authorization'] = 'Bearer ' + token;
      const resp = await fetch(url, {{ headers }});
      const payload = await resp.json();
      trace.push({{ url, status: resp.status, request_id: payload?.meta?.request_id, correlation_id: payload?.meta?.correlation_id }});
      document.getElementById('reqtrace').textContent = JSON.stringify(trace, null, 2);
      return payload;
    }}
    async function loadDashboard() {{
      trace = [];
      correlationId = 'corr_' + Math.random().toString(16).slice(2, 10);
      const runtimeStatus = document.getElementById('runtimeStatus').value;
      const stopReason = document.getElementById('stopReason').value.trim();
      const success = document.getElementById('success').value;
      const qp = new URLSearchParams();
      if (runtimeStatus) qp.set('runtime_status', runtimeStatus);
      if (stopReason) qp.set('stop_reason', stopReason);
      if (success) qp.set('success', success);
      const dashboard = await fetchJson('/operator/dashboard');
      const runs = await fetchJson('/operator/runs?limit=20&' + qp.toString());
      document.getElementById('dashboard').textContent = JSON.stringify(dashboard, null, 2);
      document.getElementById('runs').textContent = JSON.stringify(runs, null, 2);
      const first = (((runs||{{}}).data||{{}}).items||[])[0];
      if (!first) {{
        document.getElementById('detail').textContent = 'No run';
        document.getElementById('trace').textContent = 'No run';
        document.getElementById('skills').textContent = 'No run';
        document.getElementById('tools').textContent = 'No run';
        document.getElementById('stop').textContent = 'No run';
        return;
      }}
      const runId = first.run_id;
      const [detail, rt, skills, tools, stop] = await Promise.all([
        fetchJson('/operator/run/' + encodeURIComponent(runId)),
        fetchJson('/operator/run/' + encodeURIComponent(runId) + '/trace'),
        fetchJson('/operator/run/' + encodeURIComponent(runId) + '/skills'),
        fetchJson('/operator/run/' + encodeURIComponent(runId) + '/tools'),
        fetchJson('/operator/run/' + encodeURIComponent(runId) + '/stop'),
      ]);
      document.getElementById('detail').textContent = JSON.stringify(detail, null, 2);
      document.getElementById('trace').textContent = JSON.stringify(rt, null, 2);
      document.getElementById('skills').textContent = JSON.stringify(skills, null, 2);
      document.getElementById('tools').textContent = JSON.stringify(tools, null, 2);
      document.getElementById('stop').textContent = JSON.stringify(stop, null, 2);
    }}
  </script>
</body>
</html>"""
