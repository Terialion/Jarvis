"""
ChannelRegistry — 最小骨架 (Channels / Nodes 轻量骨架 Sprint)

参考 OpenClaw node-registry.ts 的设计，用 Python 重写。
支持：
- register_channel / get_channel / list_channels
- update_channel_status / remove_channel
- 每个 channel 含：channel_id, channel_type, display_name, status,
  trust_level, trigger_rules, allow_policy, conversation_mapping, metadata
- 变更时通过可选 events 引用发射 channel.updated 事件

与 GatewayState 解耦，通过 bind_gateway 挂载。
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------

class ChannelStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISABLED = "disabled"


class ChannelType(str, Enum):
    WECHAT = "wechat"
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    SLACK = "slack"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    WEB = "web"
    API = "api"
    OTHER = "other"


class TrustLevel(str, Enum):
    """统一 trust_level 枚举（目标 1）。

    优先级: UNTRUSTED < STANDARD < PRIVILEGED < ADMIN
    参考: OpenClaw operator-scopes.ts 的权限分级思路
    """
    UNTRUSTED = "untrusted"
    STANDARD = "standard"
    PRIVILEGED = "privileged"
    ADMIN = "admin"


# Channel 侧 permission_scope 标准键（目标 1）
CHANNEL_PERMISSION_KEYS = (
    "can_reply",          # 允许 Channel 主动回复消息
    "can_initiate",       # 允许 Channel 主动发起对话（不依赖用户消息）
    "can_access_history", # 允许 Channel 读取历史消息
)


@dataclass
class AllowPolicy:
    """allow_policy 标准化结构（目标 1）。

    统一为: {"allow": [...], "deny": [...], "default": "deny|allow"}
    - allow: 明确允许的 intent / action 列表
    - deny: 明确拒绝的 intent / action 列表
    - default: 默认策略（deny = 白名单模式，allow = 黑名单模式）
    """
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
    default: str = "deny"

    def to_dict(self) -> dict[str, Any]:
        return {"allow": self.allow, "deny": self.deny, "default": self.default}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AllowPolicy:
        return cls(
            allow=d.get("allow", []),
            deny=d.get("deny", []),
            default=d.get("default", "deny"),
        )


@dataclass
class ChannelEntry:
    channel_id: str
    channel_type: str
    display_name: str
    status: str = ChannelStatus.ACTIVE.value
    trust_level: str = TrustLevel.STANDARD.value
    trigger_rules: list[str] = field(default_factory=list)
    allow_policy: dict[str, Any] = field(default_factory=dict)
    permission_scope: dict[str, bool] = field(default_factory=dict)
    conversation_mapping: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    last_active_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # 确保 allow_policy 是标准结构
        if "allow_policy" in d:
            ap = d["allow_policy"]
            if not isinstance(ap, dict) or "allow" not in ap:
                d["allow_policy"] = {"allow": [], "deny": [], "default": "deny"}
        return d

    def get_trust_level(self) -> str:
        """返回 trust_level，确保是 TrustLevel 枚举的有效值。"""
        try:
            return TrustLevel(self.trust_level).value
        except ValueError:
            return TrustLevel.STANDARD.value

    def get_permission_scope(self) -> dict[str, bool]:
        """返回标准化 permission_scope（仅包含已知键）。"""
        return {k: bool(v) for k, v in self.permission_scope.items() if k in CHANNEL_PERMISSION_KEYS}

    def touch(self) -> None:
        self.last_active_at_ms = int(time.time() * 1000)


class ChannelRegistry:
    """
    线程安全的 Channel 注册表。

    设计参考 OpenClaw node-registry.ts：
    - 用 dict 模拟 TypeScript 的 Map<string, NodeSession>
    - 支持按 conn_id 反向查找（用于 WebSocket 断开时清理）

    events: 可选，GatewayEventStream.emit 的引用，
           用于在 register/unregister/update 时发射 channel.updated。
    """

    def __init__(
        self,
        events: Callable[[str, dict], Any] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[str, ChannelEntry] = {}
        self._conn_to_id: dict[str, str] = {}   # conn_id -> channel_id
        self._events = events  # Callable[[str, dict], Any] | None

    def set_events(self, events: Callable[[str, dict], Any] | None) -> None:
        """运行时注入 events 回调（用于 bind_gateway 接线）。"""
        self._events = events

    # ── 事件发射辅助 ──────────────────────────────

    def _emit_updated(self, entry: ChannelEntry) -> None:
        """发射 channel.updated 事件（忽略异常）。"""
        if self._events is not None:
            try:
                self._events("channel.updated", entry.to_dict())
            except Exception:
                pass

    # ── 状态转换规则（目标 2）─────────────────────────────────────

    @staticmethod
    def valid_status_transition(old_status: str, new_status: str) -> bool:
        """校验 Channel 状态转换是否合法（目标 2）。

        合法转换:
        - active ↔ inactive（正常启用/停用）
        - active / inactive → disabled（标记禁用）
        - disabled → active（管理员重新启用）
        - disabled → inactive（管理员重新启用到非激活状态）
        """
        if old_status == new_status:
            return True
        # 任何状态都可以变成 disabled
        if new_status == ChannelStatus.DISABLED.value:
            return True
        # disabled 可以变成 active 或 inactive
        if old_status == ChannelStatus.DISABLED.value:
            return new_status in (ChannelStatus.ACTIVE.value, ChannelStatus.INACTIVE.value)
        # active ↔ inactive
        return (
            (old_status == ChannelStatus.ACTIVE.value and new_status == ChannelStatus.INACTIVE.value)
            or (old_status == ChannelStatus.INACTIVE.value and new_status == ChannelStatus.ACTIVE.value)
        )

    # ── 写操作 ─────────────────────────────────────
    

    def register_channel(self, entry: ChannelEntry, conn_id: str | None = None) -> None:
        with self._lock:
            self._by_id[entry.channel_id] = entry
            if conn_id:
                self._conn_to_id[conn_id] = entry.channel_id
        self._emit_updated(entry)

    def unregister_channel(self, channel_id: str) -> bool:
        """返回 True 表示确实删除了。"""
        with self._lock:
            entry = self._by_id.pop(channel_id, None)
            if entry is None:
                return False
            # 清理反向映射
            to_remove = [c for c, cid in self._conn_to_id.items() if cid == channel_id]
            for c in to_remove:
                del self._conn_to_id[c]
        self._emit_updated(entry)  # 发射删除事件（含最后状态）
        return True

    def update_channel_status(self, channel_id: str, status: str) -> bool:
        """更新状态，校验合法转换（目标 2）。返回 False 表示转换不合法或 channel 不存在。"""
        with self._lock:
            entry = self._by_id.get(channel_id)
            if entry is None:
                return False
            if not self.valid_status_transition(entry.status, status):
                return False
            entry.status = status
            entry.touch()
            evt_entry = entry  # 捕获引用
        self._emit_updated(evt_entry)
        return True

    def update_channel_allow_policy(self, channel_id: str, policy: dict[str, Any]) -> bool:
        """更新 allow_policy（目标 1：标准化结构）。"""
        normalized = AllowPolicy.from_dict(policy)
        with self._lock:
            entry = self._by_id.get(channel_id)
            if entry is None:
                return False
            entry.allow_policy = normalized.to_dict()
            entry.touch()
            evt_entry = entry
        self._emit_updated(evt_entry)
        return True

    def update_channel_permission_scope(self, channel_id: str, scope: dict[str, bool]) -> bool:
        """更新 permission_scope（目标 1）。仅接受已知键。"""
        filtered = {k: bool(v) for k, v in scope.items() if k in CHANNEL_PERMISSION_KEYS}
        with self._lock:
            entry = self._by_id.get(channel_id)
            if entry is None:
                return False
            entry.permission_scope = filtered
            entry.touch()
            evt_entry = entry
        self._emit_updated(evt_entry)
        return True

    def update_channel_metadata(self, channel_id: str, metadata: dict[str, Any]) -> bool:
        with self._lock:
            entry = self._by_id.get(channel_id)
            if entry is None:
                return False
            entry.metadata.update(metadata)
            entry.touch()
            evt_entry = entry
        self._emit_updated(evt_entry)
        return True

    def bind_conn(self, channel_id: str, conn_id: str) -> None:
        """将 channel 与 WebSocket conn_id 绑定（用于断开时自动清理）。"""
        with self._lock:
            if channel_id in self._by_id:
                self._conn_to_id[conn_id] = channel_id

    def unbind_conn(self, conn_id: str) -> str | None:
        """
        当 WebSocket 断开时调用。
        返回被清理的 channel_id（如果有），供调用方 emit channel.updated。
        """
        with self._lock:
            channel_id = self._conn_to_id.pop(conn_id, None)
            return channel_id

    # ── 读操作 ─────────────────────────────────────

    def get_channel(self, channel_id: str) -> ChannelEntry | None:
        with self._lock:
            entry = self._by_id.get(channel_id)
            if entry is not None:
                entry.touch()
            return entry

    def list_channels(self, status: str | None = None) -> list[ChannelEntry]:
        with self._lock:
            entries = list(self._by_id.values())
        if status:
            entries = [e for e in entries if e.status == status]
        return entries

    def channel_count(self) -> int:
        with self._lock:
            return len(self._by_id)

    # ── 快照（给 Gateway snapshot）─────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "channel_count": len(self._by_id),
                "channels": [e.to_dict() for e in self._by_id.values()],
            }

    # ── 治理视图（目标 3）─────────────────────────────────────

    def channels_summary(self) -> dict[str, Any]:
        """Operator 视图：Channel 汇总统计（目标 3）。"""
        with self._lock:
            entries = list(self._by_id.values())
        now_ms = int(time.time() * 1000)
        summary: dict[str, Any] = {
            "total": len(entries),
            "by_status": {},
            "by_type": {},
            "by_trust_level": {},
            "health": {"healthy": 0, "stale": 0, "unknown": 0},
        }
        for e in entries:
            # by status
            summary["by_status"][e.status] = summary["by_status"].get(e.status, 0) + 1
            # by type
            t = e.channel_type
            summary["by_type"][t] = summary["by_type"].get(t, 0) + 1
            # by trust_level
            tl = e.get_trust_level()
            summary["by_trust_level"][tl] = summary["by_trust_level"].get(tl, 0) + 1
            # health (active channels with recent activity are "healthy")
            if e.status == ChannelStatus.ACTIVE.value:
                if now_ms - e.last_active_at_ms < 5 * 60 * 1000:  # 5 minutes
                    summary["health"]["healthy"] += 1
                else:
                    summary["health"]["stale"] += 1
            else:
                summary["health"]["unknown"] += 1
        return summary

    def channels_health(self) -> list[dict[str, Any]]:
        """Operator 视图：每个 Channel 的健康详情（目标 3）。

        参考 OpenClaw channel-health-monitor.ts 的思路。
        """
        now_ms = int(time.time() * 1000)
        with self._lock:
            entries = list(self._by_id.values())
        result = []
        for e in entries:
            age_ms = now_ms - e.last_active_at_ms
            if e.status != ChannelStatus.ACTIVE.value:
                health = "inactive"
            elif age_ms > 5 * 60 * 1000:
                health = "stale"
            else:
                health = "healthy"
            result.append({
                "channel_id": e.channel_id,
                "status": e.status,
                "trust_level": e.get_trust_level(),
                "health": health,
                "last_active_at_ms": e.last_active_at_ms,
                "age_seconds": age_ms // 1000,
            })
        return result

    def channel_snapshot(self, channel_id: str) -> dict[str, Any] | None:
        """Operator 视图：单个 Channel 的详细快照（目标 3）。"""
        with self._lock:
            entry = self._by_id.get(channel_id)
            if entry is None:
                return None
            d = entry.to_dict()
        # 添加计算字段
        now_ms = int(time.time() * 1000)
        d["age_seconds"] = (now_ms - entry.registered_at_ms) // 1000
        d["last_active_age_seconds"] = (now_ms - entry.last_active_at_ms) // 1000
        d["is_healthy"] = (
            entry.status == ChannelStatus.ACTIVE.value
            and (now_ms - entry.last_active_at_ms) < 5 * 60 * 1000
        )
        return d
