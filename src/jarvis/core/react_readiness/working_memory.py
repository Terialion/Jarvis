"""
Working Memory — ReAct Readiness Phase Pack 1 (A2)

运行中短期状态存储，不等同于长期 memory。
存放：active hypothesis, current plan, failed attempts summary,
      candidate files/commands/tests, current stop reason 等。

设计约束：
  - 与 Context Manager 分层清楚（Context=历史轨迹，Working=当前状态）
  - 不直接复用 task metadata 混在一起
  - 与 TaskRuntime 保持边界
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── 预定义 key 常量（建议使用，但不强制）─────────────────────────────

class WorkingMemoryKey:
    """预定义的 Working Memory key 常量。"""
    ACTIVE_HYPOTHESIS = "active_hypothesis"
    CURRENT_PLAN = "current_plan"
    FAILED_ATTEMPTS = "failed_attempts"
    CANDIDATE_FILES = "candidate_files"
    CANDIDATE_COMMANDS = "candidate_commands"
    CANDIDATE_TESTS = "candidate_tests"
    CURRENT_STOP_REASON = "current_stop_reason"
    LAST_OBSERVATION = "last_observation"
    LAST_ACTION = "last_action"
    LAST_RESULT = "last_result"
    STEP_COUNT = "step_count"
    FAILURE_COUNT = "failure_count"
    BUDGET_USED = "budget_used"
    LOOP_START_TIME = "loop_start_time"


@dataclass
class WorkingMemoryEntry:
    """Working Memory 单条记录。"""
    key: str
    value: Any
    timestamp: float
    ttl: Optional[float] = None  # 可选过期时间（None = 不过期）
    updated_count: int = 0  # 更新次数

    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        return time.time() > self.ttl

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
            "updated_count": self.updated_count,
        }


@dataclass
class TaskWorkingMemory:
    """单个任务的 Working Memory 空间。

    设计为 flat key-value store（不是嵌套 dict），保证：
    - 查询 O(1)
    - 清晰的 key 命名约定
    - 易于序列化给 eval / replay / operator surface
    """
    task_id: str
    entries: Dict[str, WorkingMemoryEntry] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    @property
    def size(self) -> int:
        return len(self.entries)

    def keys(self) -> List[str]:
        return list(self.entries.keys())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "created_at": self.created_at,
            "size": self.size,
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
        }


class WorkingMemory:
    """
    Working Memory 管理器 — 管理多任务运行时短期状态。

    线安全：threading.RLock
    零外部依赖
    """

    def __init__(self):
        self._stores: Dict[str, TaskWorkingMemory] = {}
        self._lock = threading.RLock()

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def create_store(self, task_id: str) -> TaskWorkingMemory:
        """为新任务创建 Working Memory 空间。"""
        with self._lock:
            if task_id not in self._stores:
                self._stores[task_id] = TaskWorkingMemory(task_id=task_id)
            return self._stores[task_id]

    def has_store(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._stores

    def remove_store(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._stores:
                del self._stores[task_id]
                return True
            return False

    # =========================================================================
    # Core operations: set / get / list / clear
    # =========================================================================

    def set_working_memory(
        self,
        task_id: str,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
    ) -> None:
        """设置 Working Memory 键值对。

        Args:
            task_id: 任务 ID
            key: 键名（建议使用 WorkingMemoryKey 常量）
            value: 值（任意可序列化的对象）
            ttl: 过期时间戳（绝对时间，None = 不过期）
        """
        with self._lock:
            store = self._get_or_create_store(task_id)
            existing = store.entries.get(key)
            now = time.time()
            if existing:
                # 更新已有条目
                existing.value = value
                existing.timestamp = now
                existing.ttl = ttl or existing.ttl
                existing.updated_count += 1
            else:
                store.entries[key] = WorkingMemoryEntry(
                    key=key,
                    value=value,
                    timestamp=now,
                    ttl=ttl,
                    updated_count=0,
                )

    def get_working_memory(
        self,
        task_id: str,
        key: str,
        default: Any = None,
    ) -> Any:
        """获取 Working Memory 值。过期的键返回 default。"""
        with self._lock:
            store = self._stores.get(task_id)
            if store is None:
                return default
            entry = store.entries.get(key)
            if entry is None:
                return default
            if entry.is_expired():
                del store.entries[key]
                return default
            return entry.value

    def list_working_memory(self, task_id: str) -> Dict[str, Any]:
        """列出任务的所有 Working Memory（清理过期条目后返回）。"""
        with self._lock:
            store = self._stores.get(task_id)
            if store is None:
                return {}
            # 清理过期条目
            expired_keys = [
                k for k, v in store.entries.items() if v.is_expired()
            ]
            for k in expired_keys:
                del store.entries[k]
            return {k: v.value for k, v in store.entries.items()}

    def clear_working_memory(self, task_id: str) -> int:
        """清除任务的 Working Memory。返回被清除的条目数。"""
        with self._lock:
            store = self._stores.get(task_id)
            if store is None:
                return 0
            count = len(store.entries)
            store.entries.clear()
            return count

    # =========================================================================
    # Convenience helpers
    # =========================================================================

    def get_all_stores(self) -> Dict[str, TaskWorkingMemory]:
        with self._lock:
            return dict(self._stores)

    def increment_counter(self, task_id: str, key: str, delta: int = 1) -> int:
        """原子递增计数器。"""
        with self._lock:
            store = self._get_or_create_store(task_id)
            current_val = 0
            entry = store.entries.get(key)
            if entry and not entry.is_expired():
                current_val = entry.value if isinstance(entry.value, int) else 0
            new_val = current_val + delta
            self.set_working_memory(task_id, key, new_val)
            return new_val

    def append_to_list(
        self,
        task_id: str,
        key: str,
        item: Any,
        max_length: Optional[int] = None,
    ) -> int:
        """向列表类型值追加元素。"""
        with self._lock:
            store = self._get_or_create(task_id)
            current_list = []
            entry = store.entries.get(key)
            if entry and not entry.is_expired():
                current_list = (
                    list(entry.value)
                    if isinstance(entry.value, (list, tuple))
                    else [entry.value]
                )
            current_list.append(item)
            if max_length and len(current_list) > max_length:
                current_list = current_list[-max_length:]
            self.set_working_memory(task_id, key, current_list)
            return len(current_list)

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _get_or_create_store(self, task_id: str) -> TaskWorkingMemory:
        if task_id not in self._stores:
            self._stores[task_id] = TaskWorkingMemory(task_id=task_id)
        return self._stores[task_id]

    def _get_or_create(self, task_id: str) -> TaskWorkingMemory:
        return self._get_or_create_store(task_id)


# ── Singleton ──
_default_wm: Optional[WorkingMemory] = None
_wm_lock = threading.Lock()


def get_default_working_memory() -> WorkingMemory:
    global _default_wm
    with _wm_lock:
        if _default_wm is None:
            _default_wm = WorkingMemory()
        return _default_wm
