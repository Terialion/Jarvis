"""Gateway minimum skeleton for Jarvis Core.

Provides:
  1. GatewayState  — lightweight state registry (tasks, runtime, release-gate, review, bridge, sdk)
  2. GatewayReadOnlyAPI  — read-only query layer (runtime.status, tasks.recent, task.get, review.get, gate.summary, bridge.get)
  3. GatewayEventStream  — in-process pub/sub event skeleton
  4. bind_gateway  — one-shot wiring to existing ControlSurface / TaskRuntime / DataOutlets / release_gate_store / ui_bridge / SDK adapter

Design principles (from jarvis_plan_v0.8 §15):
  - Gateway is the system center, not an auxiliary service
  - Core capabilities exposed through Gateway, not private logic per surface
  - Lightweight, single-process, local-first
  - Observable, manageable, restartable, recoverable

Wire with existing modules — never rewrite them:
  - TaskRuntime       → read-only task registry (direct reference)
  - ControlSurface    → delegated review / gate / task queries (direct reference)
  - DataOutlets       → stable data outlet layer (direct reference)
  - release_gate_store → release gate snapshot (indirect via ControlSurface)
  - ui_bridge         → versioned payload builder (adapter pattern, bridge.get)
  - SDK adapter       → parse_bridge_payload (adapter pattern, minimal hook)

Event naming follows jarvis_interface_alignment_v0.1 §6:
  domain.entity.action  e.g. task.updated, review.updated, gate.updated, runtime.status.changed, bridge.updated

Legacy reuse decisions (per user requirement):
  - TaskRuntime:       直接保留 — Gateway 只引用
  - ControlSurface:    直接保留 — Gateway API 100% 委托
  - DataOutlets:       直接保留 — 作为 ControlSurface 依赖间接使用
  - release_gate_store:直接保留 — 通过 ControlSurface 间接使用
  - control_http_adapter: 直接保留 — Phase 2 HTTP 不改动
  - ui_bridge:         适配器收编 — _build_versioned_payload 逻辑迁入 bridge.get
  - app_web_sdk_adapter:适配器收编 — parse_bridge_payload 通过绑定点暴露
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from .data_outlets import DataOutlets
from .result import error_result, ok_result
from .eval.harness_metrics_store import HarnessMetricsStore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GATEWAY_VERSION = "0.2.0"
GATEWAY_PROTOCOL_VERSION = "1.0.0"

_EVENT_BUFFER_MAX = 200

# Bridge envelope constants (mirrors run_phase3_ui_bridge.py)
BRIDGE_SCHEMA_ID = "jarvis.ui_bridge"
BRIDGE_SCHEMA_VERSION = "1.0.0"
BRIDGE_PAYLOAD_VERSION = "1.0.0"
BRIDGE_SOURCE = "gateway"


# ---------------------------------------------------------------------------
# 1. Gateway State Registry
# ---------------------------------------------------------------------------


class GatewayState:
    """Lightweight in-process state registry.

    Holds references (not copies) to existing runtime objects and
    provides a single entry point for Gateway consumers.

    Bindings:
      - _task_runtime:     TaskRuntime instance (required)
      - _control_surface:  ControlSurface instance (required)
      - _data_outlets:     DataOutlets class reference (optional, for introspection)
      - _ui_bridge_fn:     callable that builds versioned bridge payload (optional)
      - _sdk_adapter_parse: parse_bridge_payload function (optional)
    """

    def __init__(self) -> None:
        # Required references (set via bind_gateway)
        self._task_runtime: Any | None = None
        self._control_surface: Any | None = None

        # Optional references (set via bind_gateway)
        self._data_outlets: Any | None = None
        self._ui_bridge_fn: Callable[..., dict] | None = None
        self._sdk_adapter_parse: Callable[[dict], Any] | None = None

        # Optional registries (set via bind_gateway)
        self._channel_registry: Any | None = None
        self._node_registry: Any | None = None

        # Gateway's own bookkeeping
        self._project_root: str = "."
        self._started_at: str = _utc_now()
        self._gateway_id: str = f"gw_{_short_id()}"
        self._labels: dict[str, str] = {}

    # --- bindings (called by bind_gateway) ---

    def _set_task_runtime(self, runtime: Any) -> None:
        self._task_runtime = runtime

    def _set_control_surface(self, surface: Any) -> None:
        self._control_surface = surface

    def _set_data_outlets(self, outlets: Any) -> None:
        self._data_outlets = outlets

    def _set_ui_bridge_fn(self, fn: Callable[..., dict] | None) -> None:
        self._ui_bridge_fn = fn

    def _set_sdk_adapter_parse(self, fn: Callable[[dict], Any] | None) -> None:
        self._sdk_adapter_parse = fn

    def _set_channel_registry(self, registry: Any) -> None:
        self._channel_registry = registry

    def _set_node_registry(self, registry: Any) -> None:
        self._node_registry = registry

    def _set_project_root(self, root: str) -> None:
        self._project_root = root

    def set_label(self, key: str, value: str) -> None:
        self._labels[key] = value

    # --- property accessors ---

    @property
    def task_runtime(self) -> Any:
        return self._task_runtime

    @property
    def control_surface(self) -> Any:
        return self._control_surface

    @property
    def data_outlets(self) -> Any:
        return self._data_outlets

    @property
    def ui_bridge_fn(self) -> Callable[..., dict] | None:
        return self._ui_bridge_fn

    @property
    def sdk_adapter_parse(self) -> Callable[[dict], Any] | None:
        return self._sdk_adapter_parse

    @property
    def channel_registry(self) -> Any:
        return self._channel_registry

    @property
    def node_registry(self) -> Any:
        return self._node_registry

    @property
    def project_root(self) -> str:
        return self._project_root

    @property
    def gateway_id(self) -> str:
        return self._gateway_id

    @property
    def started_at(self) -> str:
        return self._started_at

    @property
    def uptime_ms(self) -> int:
        try:
            started = datetime.fromisoformat(self._started_at)
            return max(0, int((datetime.now(timezone.utc) - started).total_seconds() * 1000))
        except Exception:
            return 0

    @property
    def is_bound(self) -> bool:
        """Core bindings satisfied (task_runtime + control_surface)."""
        return self._task_runtime is not None and self._control_surface is not None

    @property
    def is_fully_bound(self) -> bool:
        """All optional bindings also satisfied."""
        return (
            self.is_bound
            and self._data_outlets is not None
            and self._ui_bridge_fn is not None
            and self._sdk_adapter_parse is not None
        )

    # --- snapshot ---

    def snapshot(self) -> dict:
        """Return a read-only snapshot of gateway state."""
        return {
            "gateway_id": self._gateway_id,
            "gateway_version": GATEWAY_VERSION,
            "started_at": self._started_at,
            "uptime_ms": self.uptime_ms,
            "is_bound": self.is_bound,
            "is_fully_bound": self.is_fully_bound,
            "project_root": self._project_root,
            "labels": dict(self._labels),
            "bindings": {
                "task_runtime": self._task_runtime is not None,
                "control_surface": self._control_surface is not None,
                "data_outlets": self._data_outlets is not None,
                "ui_bridge_fn": self._ui_bridge_fn is not None,
                "sdk_adapter_parse": self._sdk_adapter_parse is not None,
            },
            "task_count": len(self._task_runtime.tasks) if self._task_runtime else 0,
            "session_count": len(self._task_runtime.sessions) if self._task_runtime else 0,
        }


# ---------------------------------------------------------------------------
# 2. Gateway Read-Only API Layer
# ---------------------------------------------------------------------------


class GatewayReadOnlyAPI:
    """Read-only API layer that delegates to existing ControlSurface / TaskRuntime.

    Methods mirror the API草案 from jarvis_interface_alignment_v0.1 §13.3:
      runtime.status / tasks.recent / task.get / review.get / gate.summary / bridge.get
    """

    def __init__(self, state: GatewayState) -> None:
        self._state = state

    # --- core endpoints (delegate to ControlSurface) ---

    def runtime_status(self) -> dict:
        """runtime.status — gateway heartbeat / version / bound status."""
        started = time.perf_counter()
        snap = self._state.snapshot()
        return ok_result(
            {
                "status": "ok" if self._state.is_bound else "degraded",
                "gateway_id": snap["gateway_id"],
                "gateway_version": snap["gateway_version"],
                "protocol_version": GATEWAY_PROTOCOL_VERSION,
                "started_at": snap["started_at"],
                "uptime_ms": snap["uptime_ms"],
                "is_bound": snap["is_bound"],
                "is_fully_bound": snap["is_fully_bound"],
                "bindings": snap["bindings"],
                "task_count": snap["task_count"],
                "session_count": snap["session_count"],
                "project_root": snap["project_root"],
                "labels": snap["labels"],
            },
            started,
        )

    def tasks_recent(self, limit: int = 10) -> dict:
        """tasks.recent — delegate to ControlSurface.list_recent_tasks."""
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        return surface.list_recent_tasks(limit=limit)

    def task_get(self, task_id: str) -> dict:
        """task.get — delegate to ControlSurface.get_task_summary."""
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        result = surface.get_task_summary(task_id)
        # Emit task.updated event (S3: minimal emit)
        if hasattr(self, "_events_ref") and self._events_ref is not None:
            task_data = (result.get("data") or {}) if result.get("ok") else {}
            self._events_ref.emit("task.updated", {"task_id": task_id, "status": task_data.get("status", "unknown")})
        return result

    def task_timeline(self, task_id: str, limit: int = 50) -> dict:
        """task.get timeline — delegate to ControlSurface.get_task_timeline."""
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        return surface.get_task_timeline(task_id, limit=limit)

    def review_get(self, task_id: str, checkpoint_id: str | None = None) -> dict:
        """review.get — delegate to ControlSurface.get_review_pane."""
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        result = surface.get_review_pane(task_id, checkpoint_id=checkpoint_id)
        # Emit review.updated event (S3: minimal emit)
        if hasattr(self, "_events_ref") and self._events_ref is not None:
            review_data = (result.get("data") or {}) if result.get("ok") else {}
            self._events_ref.emit("review.updated", {"task_id": task_id, "status": review_data.get("review_status", "unknown")})
        return result

    def gate_summary(self) -> dict:
        """gate.summary — delegate to ControlSurface.get_release_gate_summary."""
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        result = surface.get_release_gate_summary()
        # Emit gate.updated event (S3: minimal emit)
        if hasattr(self, "_events_ref") and self._events_ref is not None:
            gate_data = (result.get("data") or {}) if result.get("ok") else {}
            self._events_ref.emit("gate.updated", {
                "open": gate_data.get("open", 0),
                "close": gate_data.get("close", 0),
            })
        return result

    # --- bridge endpoint (adapter收编 ui_bridge 逻辑) ---

    def bridge_get(self, task_id: str, checkpoint_id: str | None = None) -> dict:
        """bridge.get — build versioned bridge payload via Gateway.

        Adapter收编: replicates the envelope structure from run_phase3_ui_bridge.py
        but queries ControlSurface in-process instead of over HTTP.
        """
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)

        request_id = f"gw_{uuid4().hex[:12]}"
        correlation_id = f"gw_corr_{uuid4().hex[:8]}"

        # Query all four data sections from ControlSurface
        summary_result = surface.get_task_summary(task_id)
        if not summary_result.get("ok"):
            return summary_result

        review_result = surface.get_review_pane(task_id, checkpoint_id=checkpoint_id)
        if not review_result.get("ok"):
            return review_result

        gate_result = surface.get_release_gate_summary()

        ordered_result = surface.get_ordered_review_fields(task_id, checkpoint_id=checkpoint_id)

        # Extract ordered_review_fields from the ordered result
        ordered_data = (ordered_result.get("data") or {}) if ordered_result.get("ok") else {}
        ordered_fields = ordered_data.get("ordered_review_fields", [])

        # Build versioned payload envelope (adapter收编 of run_phase3_ui_bridge._build_versioned_payload)
        payload = _build_versioned_payload(
            task_summary=summary_result.get("data"),
            ordered_review_fields=ordered_fields,
            review_pane=review_result.get("data"),
            release_gate_summary=gate_result.get("data") if gate_result.get("ok") else None,
            request_id=request_id,
            correlation_id=correlation_id,
        )

        # Emit bridge.updated event
        if hasattr(self, "_events_ref") and self._events_ref is not None:
            self._events_ref.emit("bridge.updated", {"task_id": task_id, "request_id": request_id})

        return ok_result(payload, started)

    # ------------------------------------------------------------------
    # Channel read-only endpoints (wire to ChannelRegistry)
    # ------------------------------------------------------------------

    def channels_list(self, status: str | None = None) -> dict:
        """channels.list — list all registered channels, optionally filtered by status."""
        started = time.perf_counter()
        registry = self._state.channel_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "ChannelRegistry not bound", {}, started)
        try:
            channels = registry.list_channels(status=status)
            channel_dicts = [c.to_dict() for c in channels]
            return ok_result({"items": channel_dicts, "total": len(channels)}, started)
        except Exception as e:
            return error_result("CHANNEL_LIST_ERROR", str(e), {}, started)

    def channel_get(self, channel_id: str) -> dict:
        """channel.get — get a single channel by id."""
        started = time.perf_counter()
        registry = self._state.channel_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "ChannelRegistry not bound", {}, started)
        try:
            channel = registry.get_channel(channel_id)
            if channel is None:
                return error_result("CHANNEL_NOT_FOUND", f"Channel {channel_id} not found", {}, started)
            return ok_result(channel.to_dict(), started)
        except Exception as e:
            return error_result("CHANNEL_GET_ERROR", str(e), {}, started)

    def channel_status(self, channel_id: str) -> dict:
        """channel.status — get channel status only (lightweight)."""
        started = time.perf_counter()
        registry = self._state.channel_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "ChannelRegistry not bound", {}, started)
        try:
            channel = registry.get_channel(channel_id)
            if channel is None:
                return error_result("CHANNEL_NOT_FOUND", f"Channel {channel_id} not found", {}, started)
            return ok_result({"channel_id": channel_id, "status": channel.status}, started)
        except Exception as e:
            return error_result("CHANNEL_STATUS_ERROR", str(e), {}, started)

    # ------------------------------------------------------------------
    # Channel 治理视图 API（目标 3/4）
    # ------------------------------------------------------------------

    def channels_summary(self) -> dict:
        """channels.summary — operator 视图：Channel 汇总统计。"""
        started = time.perf_counter()
        registry = self._state.channel_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "ChannelRegistry not bound", {}, started)
        try:
            summary = registry.channels_summary()
            return ok_result(summary, started)
        except Exception as e:
            return error_result("CHANNELS_SUMMARY_ERROR", str(e), {}, started)

    def channels_health(self) -> dict:
        """channels.health — operator 视图：每个 Channel 的健康详情。"""
        started = time.perf_counter()
        registry = self._state.channel_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "ChannelRegistry not bound", {}, started)
        try:
            health_list = registry.channels_health()
            return ok_result({"items": health_list, "total": len(health_list)}, started)
        except Exception as e:
            return error_result("CHANNELS_HEALTH_ERROR", str(e), {}, started)

    def channel_snapshot(self, channel_id: str) -> dict:
        """channel.snapshot — operator 视图：单个 Channel 的详细快照。"""
        started = time.perf_counter()
        registry = self._state.channel_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "ChannelRegistry not bound", {}, started)
        try:
            snap = registry.channel_snapshot(channel_id)
            if snap is None:
                return error_result("CHANNEL_NOT_FOUND", f"Channel {channel_id} not found", {}, started)
            return ok_result(snap, started)
        except Exception as e:
            return error_result("CHANNEL_SNAPSHOT_ERROR", str(e), {}, started)

    # ------------------------------------------------------------------
    # Node read-only endpoints (wire to NodeRegistry)
    # ------------------------------------------------------------------

    def nodes_list(self, status: str | None = None) -> dict:
        """nodes.list — list all registered nodes, optionally filtered by status."""
        started = time.perf_counter()
        registry = self._state.node_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "NodeRegistry not bound", {}, started)
        try:
            nodes = registry.list_nodes(status=status)
            node_dicts = [n.to_dict() for n in nodes]
            return ok_result({"items": node_dicts, "total": len(nodes)}, started)
        except Exception as e:
            return error_result("NODE_LIST_ERROR", str(e), {}, started)

    def node_get(self, node_id: str) -> dict:
        """node.get — get a single node by id."""
        started = time.perf_counter()
        registry = self._state.node_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "NodeRegistry not bound", {}, started)
        try:
            node = registry.get_node(node_id)
            if node is None:
                return error_result("NODE_NOT_FOUND", f"Node {node_id} not found", {}, started)
            return ok_result(node.to_dict(), started)
        except Exception as e:
            return error_result("NODE_GET_ERROR", str(e), {}, started)

    def node_capabilities(self, node_id: str) -> dict:
        """node.capabilities — get node capabilities only (lightweight)."""
        started = time.perf_counter()
        registry = self._state.node_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "NodeRegistry not bound", {}, started)
        try:
            node = registry.get_node(node_id)
            if node is None:
                return error_result("NODE_NOT_FOUND", f"Node {node_id} not found", {}, started)
            return ok_result({
                "node_id": node_id,
                "capabilities": [c.to_dict() for c in node.capabilities],
                "status": node.status,
            }, started)
        except Exception as e:
            return error_result("NODE_CAPABILITIES_ERROR", str(e), {}, started)

    # ------------------------------------------------------------------
    # Node 治理视图 API（目标 3/4）
    # ------------------------------------------------------------------

    def nodes_summary(self) -> dict:
        """nodes.summary — operator 视图：Node 汇总统计。"""
        started = time.perf_counter()
        registry = self._state.node_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "NodeRegistry not bound", {}, started)
        try:
            summary = registry.nodes_summary()
            return ok_result(summary, started)
        except Exception as e:
            return error_result("NODES_SUMMARY_ERROR", str(e), {}, started)

    def nodes_health(self) -> dict:
        """nodes.health — operator 视图：每个 Node 的健康详情。"""
        started = time.perf_counter()
        registry = self._state.node_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "NodeRegistry not bound", {}, started)
        try:
            health_list = registry.nodes_health()
            return ok_result({"items": health_list, "total": len(health_list)}, started)
        except Exception as e:
            return error_result("NODES_HEALTH_ERROR", str(e), {}, started)

    def node_snapshot(self, node_id: str) -> dict:
        """node.snapshot — operator 视图：单个 Node 的详细快照。"""
        started = time.perf_counter()
        registry = self._state.node_registry
        if registry is None:
            return error_result("GATEWAY_NOT_BOUND", "NodeRegistry not bound", {}, started)
        try:
            snap = registry.node_snapshot(node_id)
            if snap is None:
                return error_result("NODE_NOT_FOUND", f"Node {node_id} not found", {}, started)
            return ok_result(snap, started)
        except Exception as e:
            return error_result("NODE_SNAPSHOT_ERROR", str(e), {}, started)

    # ------------------------------------------------------------------
    # Operator read-only endpoints (Sprint 1)
    # ------------------------------------------------------------------

    def operator_runs_recent(
        self,
        *,
        limit: int = 20,
        runtime_status: str | None = None,
        stop_reason: str | None = None,
        success: bool | None = None,
    ) -> dict:
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        return surface.get_operator_runs_recent(
            limit=limit,
            runtime_status=runtime_status,
            stop_reason=stop_reason,
            success=success,
        )

    def operator_run_get(self, run_id: str) -> dict:
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        return surface.get_operator_run(run_id)

    def operator_run_trace(self, run_id: str, limit: int = 200) -> dict:
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        return surface.get_operator_run_trace(run_id, limit=limit)

    def operator_run_skill_hits(self, run_id: str) -> dict:
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        return surface.get_operator_run_skill_hits(run_id)

    def operator_run_tool_calls(self, run_id: str) -> dict:
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        return surface.get_operator_run_tool_calls(run_id)

    def operator_run_stop_summary(self, run_id: str) -> dict:
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        return surface.get_operator_run_stop_summary(run_id)

    def operator_gateway_summary(self) -> dict:
        started = time.perf_counter()
        status = self.runtime_status()
        if not status.get("ok"):
            return status
        return ok_result(DataOutlets.operator_gateway_summary(status.get("data")), started)

    def operator_channels_summary(self) -> dict:
        started = time.perf_counter()
        channels = self.channels_summary()
        if not channels.get("ok"):
            return ok_result(DataOutlets.operator_channels_summary({}), started)
        return ok_result(DataOutlets.operator_channels_summary(channels.get("data")), started)

    def operator_nodes_summary(self) -> dict:
        started = time.perf_counter()
        nodes = self.nodes_summary()
        if not nodes.get("ok"):
            return ok_result(DataOutlets.operator_nodes_summary({}), started)
        return ok_result(DataOutlets.operator_nodes_summary(nodes.get("data")), started)

    def operator_review_summary(self) -> dict:
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        result = surface.get_operator_review_summary()
        if not result.get("ok"):
            return result
        return ok_result(DataOutlets.operator_review_summary(result.get("data")), started)

    def operator_gate_summary(self) -> dict:
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        gate = surface.get_release_gate_summary()
        if not gate.get("ok"):
            return gate
        return ok_result(DataOutlets.operator_gate_summary(gate.get("data")), started)

    def operator_dashboard(self) -> dict:
        started = time.perf_counter()
        surface = self._state.control_surface
        if surface is None:
            return error_result("GATEWAY_NOT_BOUND", "ControlSurface not bound", {}, started)
        runs = self.operator_runs_recent(limit=20)
        gateway_summary = self.operator_gateway_summary()
        channels_summary = self.operator_channels_summary()
        nodes_summary = self.operator_nodes_summary()
        gate_summary = self.operator_gate_summary()
        review_summary = self.operator_review_summary()
        runtime_status = self.runtime_status()
        payload = DataOutlets.operator_dashboard(
            gateway_summary=gateway_summary.get("data") if gateway_summary.get("ok") else {},
            active_runs_summary={
                "total_runs": (runs.get("data") or {}).get("total_runs", 0),
                "active_runs": len(
                    [
                        item
                        for item in ((runs.get("data") or {}).get("items") or [])
                        if item.get("runtime_status") in {"running", "retrying", "waiting_for_approval"}
                    ]
                ),
                "failed_or_stopped_runs": len(
                    [
                        item
                        for item in ((runs.get("data") or {}).get("items") or [])
                        if item.get("runtime_status") in {"failed", "stopped"}
                    ]
                ),
            },
            recent_runs=(runs.get("data") or {"items": [], "count": 0, "total_runs": 0}),
            channels_summary=channels_summary.get("data") if channels_summary.get("ok") else {},
            nodes_summary=nodes_summary.get("data") if nodes_summary.get("ok") else {},
            gate_summary=gate_summary.get("data") if gate_summary.get("ok") else {},
            review_summary=review_summary.get("data") if review_summary.get("ok") else {},
            runtime_observability_summary={
                "gateway_requests": None,
                "gateway_errors": None,
                "gateway_status": (runtime_status.get("data") or {}).get("status"),
                "uptime_ms": (runtime_status.get("data") or {}).get("uptime_ms"),
            },
        )
        return ok_result(payload, started)

    def operator_harness_quality_summary(self) -> dict:
        started = time.perf_counter()
        store = HarnessMetricsStore()
        summary = store.summarize()
        kinds = summary.get("kind_distribution", {}) or {}
        return ok_result(
            {
                "route": {"events": kinds.get("route", 0)},
                "skill": {"events": kinds.get("skill", 0)},
                "risk": {"distribution": summary.get("risk_distribution", {})},
                "recovery": {"events": kinds.get("recovery", 0)},
                "strategy": {"events": kinds.get("strategy", 0)},
                "hooks": {
                    "fired_count": kinds.get("hook", 0),
                    "failed_count": kinds.get("hook_failed", 0),
                    "blocked_count": kinds.get("hook_blocked", 0),
                },
                "memory": {
                    "memory_used": kinds.get("memory_recall", 0),
                    "memory_written": kinds.get("memory_write", 0),
                    "memory_rejected": kinds.get("memory_reject", 0),
                    "memory_redacted": kinds.get("memory_redact", 0),
                },
                "subagents": {
                    "events": kinds.get("subagent", 0),
                    "failures": kinds.get("subagent_failed", 0),
                },
                "rethink": {
                    "events": kinds.get("rethink", 0),
                    "started": kinds.get("rethink_started", 0),
                    "failed": kinds.get("rethink_failed", 0),
                },
                "demo": {"events": kinds.get("demo", 0)},
                "summary": summary,
            },
            started,
        )

    def operator_approval_queue(self) -> dict:
        started = time.perf_counter()
        runs = self.operator_runs_recent(limit=50)
        if not runs.get("ok"):
            return runs
        items = []
        for run in (runs.get("data") or {}).get("items", []):
            if run.get("runtime_status") == "waiting_for_approval":
                items.append(
                    {
                        "run_id": run.get("run_id"),
                        "task_id": run.get("task_id"),
                        "stop_reason": run.get("stop_reason"),
                        "route_summary": run.get("route_summary"),
                    }
                )
        return ok_result({"items": items, "count": len(items)}, started)

    def operator_patch_review(self, run_id: str) -> dict:
        started = time.perf_counter()
        run = self.operator_run_get(run_id)
        if not run.get("ok"):
            return run
        data = run.get("data") or {}
        return ok_result(
            {
                "run_id": run_id,
                "task_id": data.get("run", {}).get("task_id"),
                "summary": data.get("final_summary", {}),
                "tool_calls": data.get("tool_calls", {}),
                "fallback_summary": data.get("fallback_summary", {}),
                "rollback_available": True,
            },
            started,
        )

    # Internal: set by Gateway.__init__ to allow bridge_get to emit events
    _events_ref: Any = None


# ---------------------------------------------------------------------------
# 3. Gateway Event Stream Skeleton
# ---------------------------------------------------------------------------


class GatewayEvent:
    """Single event object following domain.entity.action naming."""

    __slots__ = ("event_type", "params", "timestamp", "sequence")

    def __init__(self, event_type: str, params: dict | None = None, *, timestamp: str | None = None, sequence: int = 0) -> None:
        self.event_type: str = event_type
        self.params: dict = params or {}
        self.timestamp: str = timestamp or _utc_now()
        self.sequence: int = sequence

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "params": self.params,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
        }


class GatewayEventStream:
    """In-process pub/sub event stream for Gateway.

    Features:
      - Thread-safe event buffer (ring buffer of _EVENT_BUFFER_MAX)
      - In-process subscriber callbacks (no network transport)
      - emit() is the single entry point for all events
      - subscribe() returns an unsubscribe callable

    Event types (from interface_alignment v0.1 §6):
      task.updated / review.updated / gate.updated / runtime.status.changed / bridge.updated
    """

    def __init__(self, state: GatewayState) -> None:
        self._state = state
        self._buffer: deque[GatewayEvent] = deque(maxlen=_EVENT_BUFFER_MAX)
        self._sequence: int = 0
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[GatewayEvent], None]] = []

    def emit(self, event_type: str, params: dict | None = None) -> GatewayEvent:
        """Emit an event. Thread-safe."""
        with self._lock:
            self._sequence += 1
            event = GatewayEvent(
                event_type=event_type,
                params=params or {},
                sequence=self._sequence,
            )
            self._buffer.append(event)
        # Notify subscribers outside the lock to avoid deadlocks
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception:
                pass  # subscribers must not crash the stream
        return event

    def subscribe(self, callback: Callable[[GatewayEvent], None]) -> Callable[[], None]:
        """Subscribe to events. Returns an unsubscribe callable."""
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def recent(self, limit: int = 20, event_type: str | None = None) -> list[dict]:
        """Read recent events from the buffer. Optionally filter by event_type."""
        with self._lock:
            items = list(self._buffer)
        if event_type:
            items = [e for e in items if e.event_type == event_type]
        selected = items[-limit:] if limit > 0 else items
        return [e.to_dict() for e in selected]

    def event_count(self) -> int:
        with self._lock:
            return len(self._buffer)

    def reset(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._sequence = 0


# ---------------------------------------------------------------------------
# 4. Gateway Binding — wire to existing modules
# ---------------------------------------------------------------------------


class Gateway:
    """Minimal Gateway facade.

    Composes GatewayState + GatewayReadOnlyAPI + GatewayEventStream.
    Created via bind_gateway() factory function.
    """

    def __init__(self, state: GatewayState, api: GatewayReadOnlyAPI, events: GatewayEventStream) -> None:
        self.state = state
        self.api = api
        self.events = events
        # Wire events ref into API so bridge_get can emit events
        api._events_ref = events

    def to_dict(self) -> dict:
        return {
            "gateway_id": self.state.gateway_id,
            "gateway_version": GATEWAY_VERSION,
            "protocol_version": GATEWAY_PROTOCOL_VERSION,
            "started_at": self.state.started_at,
            "is_bound": self.state.is_bound,
            "is_fully_bound": self.state.is_fully_bound,
        }


def bind_gateway(
    *,
    task_runtime: Any,
    control_surface: Any,
    data_outlets: Any | None = None,
    ui_bridge_fn: Callable[..., dict] | None = None,
    sdk_adapter_parse: Callable[[dict], Any] | None = None,
    channel_registry: Any | None = None,
    node_registry: Any | None = None,
    project_root: str | None = None,
    labels: dict[str, str] | None = None,
) -> Gateway:
    """Create and bind a Gateway to existing Jarvis Core modules.

    This is the single entry point for Gateway initialization.
    It does NOT rewrite any existing module — it only holds references
    and provides a unified read-only + event interface.

    Args:
        task_runtime: Existing TaskRuntime instance. (required)
        control_surface: Existing ControlSurface instance. (required)
        data_outlets: DataOutlets class reference for introspection. (optional)
        ui_bridge_fn: Callable that builds versioned bridge payload. (optional)
            If provided, bridge.get will use it instead of the built-in builder.
        sdk_adapter_parse: parse_bridge_payload function from app_web_sdk_adapter. (optional)
            If provided, bridge.get can verify payload via SDK adapter.
        project_root: Project root path for release gate lookups. (optional)
        labels: Optional key-value labels for gateway metadata. (optional)

    Returns:
        Bound Gateway instance ready for queries and events.
    """
    state = GatewayState()
    state._set_task_runtime(task_runtime)
    state._set_control_surface(control_surface)
    state._set_data_outlets(data_outlets)
    state._set_ui_bridge_fn(ui_bridge_fn)
    state._set_sdk_adapter_parse(sdk_adapter_parse)
    state._set_channel_registry(channel_registry)
    state._set_node_registry(node_registry)
    state._set_project_root(project_root or ".")
    if labels:
        for k, v in labels.items():
            state.set_label(k, v)

    api = GatewayReadOnlyAPI(state)
    events = GatewayEventStream(state)

    gateway = Gateway(state=state, api=api, events=events)

    # Wire registry events to GatewayEventStream (P1: minimal invasive)
    if channel_registry is not None and hasattr(channel_registry, "set_events"):
        channel_registry.set_events(lambda event_type, params: events.emit(event_type, params))
    if node_registry is not None and hasattr(node_registry, "set_events"):
        node_registry.set_events(lambda event_type, params: events.emit(event_type, params))

    # Emit bootstrap event
    events.emit(
        "runtime.status.changed",
        {
            "gateway_id": state.gateway_id,
            "status": "bound",
            "is_fully_bound": state.is_fully_bound,
            "task_count": len(task_runtime.tasks),
            "bindings": state.snapshot()["bindings"],
        },
    )

    return gateway


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


def _build_versioned_payload(
    *,
    task_summary: dict | None,
    ordered_review_fields: list[dict] | None,
    review_pane: dict | None,
    release_gate_summary: dict | None,
    request_id: str,
    correlation_id: str,
) -> dict:
    """Build a versioned payload envelope.

    Adapter收编 from run_phase3_ui_bridge._build_versioned_payload.
    Same structure, same constants — consumers (SDK adapter) remain compatible.
    """
    return {
        "schema_id": BRIDGE_SCHEMA_ID,
        "schema_version": BRIDGE_SCHEMA_VERSION,
        "payload_version": BRIDGE_PAYLOAD_VERSION,
        "generated_at": _utc_now(),
        "source": BRIDGE_SOURCE,
        "data": {
            "task_summary": task_summary,
            "ordered_review_fields": ordered_review_fields or [],
            "review_pane": review_pane,
            "release_gate_summary": release_gate_summary,
        },
        "meta": {
            "request_id": request_id,
            "correlation_id": correlation_id,
            "source": BRIDGE_SOURCE,
        },
    }
