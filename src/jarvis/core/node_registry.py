"""
NodeRegistry — 最小骨架 (Channels / Nodes 轻量骨架 Sprint)

参考 OpenClaw node-registry.ts + Codex session_registry.rs 的设计。
支持：
- register_node / get_node / list_nodes
- update_node_status / disable_node
- capability / trust_level / permission_scope 管理
- 变更时通过可选 events 引用发射 node.updated 事件

与 GatewayState 解耦，通过 bind_gateway 挂载。
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Enums & Constants (目标 1: Trust/Permission/Policy 规范化)
# ---------------------------------------------------------------------------

class NodeStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class NodeType(str, Enum):
    DESKTOP = "desktop"
    MOBILE = "mobile"
    SERVER = "server"
    BROWSER = "browser"
    IOT = "iot"
    OTHER = "other"


class TrustLevel(str, Enum):
    """统一 trust_level 枚举（目标 1，与 Channel 侧一致）。"""
    UNTRUSTED = "untrusted"
    STANDARD = "standard"
    PRIVILEGED = "privileged"
    ADMIN = "admin"


# Node 侧 permission_scope 标准值（目标 1）
# 沿用 jarvis_runtime/command_registry.py 的 value set
NODE_PERMISSION_SCOPE_KEYS = (
    "default",
    "safe_readonly",
    "connector_safe",
    "agent_control_plane",
    "dangerous_exec",
)


@dataclass
class NodeCapability:
    """单个能力描述（参考 OpenClaw Capabilities.swift 枚举）。"""
    name: str
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "enabled": self.enabled, **self.metadata}


@dataclass
class NodeEntry:
    node_id: str
    node_type: str
    display_name: str
    status: str = NodeStatus.DISCONNECTED.value
    trust_level: str = TrustLevel.STANDARD.value
    capabilities: list[NodeCapability] = field(default_factory=list)
    permission_scope: dict[str, bool] = field(default_factory=dict)
    runtime_kind: str = "unknown"
    transport: str = "unknown"
    location: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    last_active_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    conn_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["capabilities"] = [c.to_dict() for c in self.capabilities]
        return d

    def touch(self) -> None:
        self.last_active_at_ms = int(time.time() * 1000)

    def has_capability(self, name: str) -> bool:
        return any(c.name == name and c.enabled for c in self.capabilities)

    def get_trust_level(self) -> str:
        """返回 trust_level，确保是 TrustLevel 枚举的有效值。"""
        try:
            return TrustLevel(self.trust_level).value
        except ValueError:
            return TrustLevel.STANDARD.value

    def get_permission_scope(self) -> dict[str, bool]:
        """返回标准化 permission_scope（仅包含已知键）。"""
        return {k: bool(v) for k, v in self.permission_scope.items() if k in NODE_PERMISSION_SCOPE_KEYS}


class NodeRegistry:
    """
    线程安全的 Node 注册表。

    设计参考：
    - OpenClaw node-registry.ts: Map<string, NodeSession> + Map<string, string>
    - Codex session_registry.rs: HashMap<String, Arc<SessionEntry>> + TTL 过期
    """

    def __init__(
        self,
        events: Callable[[str, dict], Any] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[str, NodeEntry] = {}
        self._conn_to_id: dict[str, str] = {}   # conn_id -> node_id
        self._events = events  # Callable[[str, dict], Any] | None

    def set_events(self, events: Callable[[str, dict], Any] | None) -> None:
        """运行时注入 events 回调（用于 bind_gateway 接线）。"""
        self._events = events

    # ── 事件发射辅助 ──────────────────────────────#

    def _emit_updated(self, entry: NodeEntry) -> None:
        """发射 node.updated 事件（忽略异常）。"""
        if self._events is not None:
            try:
                self._events("node.updated", entry.to_dict())
            except Exception:
                pass

    # ── 写操作 ─────────────────────────────────────#

    def register_node(self, entry: NodeEntry, conn_id: str = "") -> None:
        with self._lock:
            entry.conn_id = conn_id
            self._by_id[entry.node_id] = entry
            if conn_id:
                self._conn_to_id[conn_id] = entry.node_id
        self._emit_updated(entry)

    def unregister_node(self, node_id: str) -> bool:
        """返回 True 表示确实删除了。"""
        with self._lock:
            entry = self._by_id.pop(node_id, None)
            if entry is None:
                return False
            if entry.conn_id:
                self._conn_to_id.pop(entry.conn_id, None)
        self._emit_updated(entry)  # 发射删除事件（含最后状态）
        return True

    def disconnect_by_conn(self, conn_id: str) -> str | None:
        """
        WebSocket 断开时调用。
        返回被断开的 node_id（如有），供调用方 emit node.updated。
        """
        with self._lock:
            node_id = self._conn_to_id.pop(conn_id, None)
            if node_id is None:
                return None
            entry = self._by_id.get(node_id)
            if entry is not None:
                entry.status = NodeStatus.DISCONNECTED.value
                entry.touch()
                evt_entry = entry  # 捕获引用
        if entry is not None:
            self._emit_updated(evt_entry)
        return node_id

    # ── 状态转换规则（目标 2）─────────────────────────────────────

    @staticmethod
    def valid_status_transition(old_status: str, new_status: str) -> bool:
        """校验 Node 状态转换是否合法（目标 2）。

        合法转换:
        - connected ↔ disconnected（正常连接/断开）
        - connected / disconnected → degraded（标记为降级）
        - connected / disconnected / degraded → disabled（标记禁用）
        - disabled → connected（管理员重新启用）
        - disabled → disconnected（管理员重新启用到断开状态）
        """
        if old_status == new_status:
            return True
        # 任何状态都可以变成 disabled
        if new_status == NodeStatus.DISABLED.value:
            return True
        # disabled 可以变成 connected 或 disconnected
        if old_status == NodeStatus.DISABLED.value:
            return new_status in (NodeStatus.CONNECTED.value, NodeStatus.DISCONNECTED.value)
        # connected / disconnected / degraded 之间可以互相转换
        return True  # 允许 connected ↔ disconnected, connected → degraded, etc.

    # ── 写操作（续）──────────────────────────────#

    def update_node_status(self, node_id: str, status: str) -> bool:
        """更新状态，校验合法转换（目标 2）。返回 False 表示转换不合法或 node 不存在。"""
        with self._lock:
            entry = self._by_id.get(node_id)
            if entry is None:
                return False
            if not self.valid_status_transition(entry.status, status):
                return False
            entry.status = status
            entry.touch()
            evt_entry = entry
        self._emit_updated(evt_entry)
        return True

    def update_node_permission_scope(self, node_id: str, scope: dict[str, bool]) -> bool:
        """更新 permission_scope（目标 1）。仅接受已知键。"""
        filtered = {k: bool(v) for k, v in scope.items() if k in NODE_PERMISSION_SCOPE_KEYS}
        with self._lock:
            entry = self._by_id.get(node_id)
            if entry is None:
                return False
            entry.permission_scope = filtered
            entry.touch()
            evt_entry = entry
        self._emit_updated(evt_entry)
        return True

    def disable_node(self, node_id: str) -> bool:
        return self.update_node_status(node_id, NodeStatus.DISABLED.value)

    def update_node_metadata(self, node_id: str, metadata: dict[str, Any]) -> bool:
        with self._lock:
            entry = self._by_id.get(node_id)
            if entry is None:
                return False
            entry.metadata.update(metadata)
            entry.touch()
            evt_entry = entry
        self._emit_updated(evt_entry)
        return True

    def bind_conn(self, node_id: str, conn_id: str) -> None:
        """将 node 与 WebSocket conn_id 绑定。"""
        with self._lock:
            if node_id in self._by_id:
                self._by_id[node_id].conn_id = conn_id
                self._by_id[node_id].status = NodeStatus.CONNECTED.value
                self._by_id[node_id].touch()
                self._conn_to_id[conn_id] = node_id

    # ── 读操作 ─────────────────────────────────────#

    def get_node(self, node_id: str) -> NodeEntry | None:
        with self._lock:
            entry = self._by_id.get(node_id)
            if entry is not None:
                entry.touch()
            return entry

    def list_nodes(self, status: str | None = None) -> list[NodeEntry]:
        with self._lock:
            entries = list(self._by_id.values())
        if status:
            entries = [e for e in entries if e.status == status]
        return entries

    def get_nodes_by_capability(self, cap_name: str) -> list[NodeEntry]:
        with self._lock:
            return [e for e in self._by_id.values() if e.has_capability(cap_name)]

    def node_count(self) -> int:
        with self._lock:
            return len(self._by_id)

    # ── 快照（给 Gateway snapshot）─────────────────────────────#

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "node_count": len(self._by_id),
                "nodes": [e.to_dict() for e in self._by_id.values()],
            }

    # ── 治理视图（目标 3）─────────────────────────────────────

    def nodes_summary(self) -> dict[str, Any]:
        """Operator 视图：Node 汇总统计（目标 3）。"""
        with self._lock:
            entries = list(self._by_id.values())
        now_ms = int(time.time() * 1000)
        summary: dict[str, Any] = {
            "total": len(entries),
            "by_status": {},
            "by_type": {},
            "by_trust_level": {},
            "by_runtime_kind": {},
            "health": {"healthy": 0, "stale": 0, "disconnected": 0},
        }
        for e in entries:
            summary["by_status"][e.status] = summary["by_status"].get(e.status, 0) + 1
            summary["by_type"][e.node_type] = summary["by_type"].get(e.node_type, 0) + 1
            tl = e.get_trust_level()
            summary["by_trust_level"][tl] = summary["by_trust_level"].get(tl, 0) + 1
            summary["by_runtime_kind"][e.runtime_kind] = summary["by_runtime_kind"].get(e.runtime_kind, 0) + 1
            # health
            if e.status == NodeStatus.CONNECTED.value:
                if now_ms - e.last_active_at_ms < 5 * 60 * 1000:
                    summary["health"]["healthy"] += 1
                else:
                    summary["health"]["stale"] += 1
            else:
                summary["health"]["disconnected"] += 1
        return summary

    def nodes_health(self) -> list[dict[str, Any]]:
        """Operator 视图：每个 Node 的健康详情（目标 3）。"""
        now_ms = int(time.time() * 1000)
        with self._lock:
            entries = list(self._by_id.values())
        result = []
        for e in entries:
            age_ms = now_ms - e.last_active_at_ms
            if e.status != NodeStatus.CONNECTED.value:
                health = "disconnected"
            elif age_ms > 5 * 60 * 1000:
                health = "stale"
            else:
                health = "healthy"
            result.append({
                "node_id": e.node_id,
                "status": e.status,
                "trust_level": e.get_trust_level(),
                "health": health,
                "last_active_at_ms": e.last_active_at_ms,
                "age_seconds": age_ms // 1000,
                "capabilities": [c.to_dict() for c in e.capabilities],
            })
        return result

    def node_snapshot(self, node_id: str) -> dict[str, Any] | None:
        """Operator 视图：单个 Node 的详细快照（目标 3）。"""
        with self._lock:
            entry = self._by_id.get(node_id)
            if entry is None:
                return None
            d = entry.to_dict()
        now_ms = int(time.time() * 1000)
        d["age_seconds"] = (now_ms - entry.registered_at_ms) // 1000
        d["last_active_age_seconds"] = (now_ms - entry.last_active_at_ms) // 1000
        d["is_healthy"] = (
            entry.status == NodeStatus.CONNECTED.value
            and (now_ms - entry.last_active_at_ms) < 5 * 60 * 1000
        )
        return d
