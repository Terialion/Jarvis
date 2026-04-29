"""
Session Context Manager — ReAct Readiness Phase Pack 1 (A1)

统一管理单任务上下文，而不是让 loop 直接拼 prompt。
区分 immutable facts / recent observations / recent actions / recent results / derived summary。

参考收编：
  - hermes/hermes_state.py → 迁移 session/message 结构化模型思路（适配为 in-memory）
  - 不引入 SQLite/FTS5，v1 做 in-memory，后续可升级持久化

消费方：future ReAct runtime, operator surface, replay, eval pack, context compactor
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ContextLayer(Enum):
    """Context 层级枚举。"""
    IMMUTABLE_FACTS = "immutable_facts"
    OBSERVATIONS = "observations"
    ACTIONS = "actions"
    RESULTS = "results"
    SUMMARY = "summary"


@dataclass
class ContextEntry:
    """单条上下文条目。"""
    id: str
    layer: ContextLayer
    content: Any  # str or dict
    timestamp: float
    step_number: int = -1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "layer": self.layer.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "step_number": self.step_number,
            "metadata": self.metadata,
        }


@dataclass
class TaskContext:
    """单个任务的完整上下文窗口。

    设计约束：
    - 各层严格分离，不允许混用 dict 存所有东西
    - 与 Working Memory 分层清楚（Working Memory 是运行状态，Context 是历史轨迹）
    - 与 TaskRuntime 保持边界（TaskRuntime 管任务生命周期，ContextManager 管上下文内容）
    """
    task_id: str
    created_at: float = field(default_factory=time.time)
    # 各层有序列表
    immutable_facts: List[ContextEntry] = field(default_factory=list)
    observations: List[ContextEntry] = field(default_factory=list)
    actions: List[ContextEntry] = field(default_factory=list)
    results: List[ContextEntry] = field(default_factory=list)
    summary: List[ContextEntry] = field(default_factory=list)
    # 元数据
    total_steps: int = 0
    last_updated: float = field(default_factory=time.time)
    compact_count: int = 0

    # ── 层访问器 ──

    def get_layer(self, layer: ContextLayer) -> List[ContextEntry]:
        mapping = {
            ContextLayer.IMMUTABLE_FACTS: self.immutable_facts,
            ContextLayer.OBSERVATIONS: self.observations,
            ContextLayer.ACTIONS: self.actions,
            ContextLayer.RESULTS: self.results,
            ContextLayer.SUMMARY: self.summary,
        }
        return mapping[layer]

    @property
    def total_entries(self) -> int:
        return (
            len(self.immutable_facts)
            + len(self.observations)
            + len(self.actions)
            + len(self.results)
            + len(self.summary)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "created_at": self.created_at,
            "total_steps": self.total_steps,
            "last_updated": self.last_updated,
            "compact_count": self.compact_count,
            "immutable_facts": [e.to_dict() for e in self.immutable_facts],
            "observations": [e.to_dict() for e in self.observations],
            "actions": [e.to_dict() for e in self.actions],
            "results": [e.to_dict() for e in self.results],
            "summary": [e.to_dict() for e in self.summary],
        }


class SessionContextManager:
    """
    Session Context Manager — 管理 TaskContext 的创建、追加、查询、压缩。

    线安全：使用 threading.RLock 保护内部状态。
    零外部依赖：仅标准库 + dataclasses。
    """

    def __init__(self):
        self._contexts: Dict[str, TaskContext] = {}
        self._lock = threading.RLock()

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def create_context(
        self,
        task_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """创建新任务上下文。

        Args:
            task_id: 可选的任务 ID，不传则自动生成 UUID
            initial_context: 初始上下文，可包含 'facts' 键（存入 immutable_facts 层）

        Returns:
            task_id 字符串
        """
        tid = task_id or f"task_{uuid.uuid4().hex[:12]}"
        ctx = TaskContext(task_id=tid)

        if initial_context:
            # 初始事实进入 immutable_facts 层
            facts = initial_context.get("facts", [])
            if isinstance(facts, list):
                for fact in facts:
                    ctx.immutable_facts.append(ContextEntry(
                        id=uuid.uuid4().hex[:8],
                        layer=ContextLayer.IMMUTABLE_FACTS,
                        content=fact,
                        timestamp=time.time(),
                        step_number=0,
                    ))
            # 其他初始信息也作为事实
            for key, value in initial_context.items():
                if key == "facts":
                    continue
                ctx.immutable_facts.append(ContextEntry(
                    id=uuid.uuid4().hex[:8],
                    layer=ContextLayer.IMMUTABLE_FACTS,
                    content={key: value},
                    timestamp=time.time(),
                    step_number=0,
                ))

        with self._lock:
            self._contexts[tid] = ctx
        return tid

    def has_context(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._contexts

    def remove_context(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._contexts:
                del self._contexts[task_id]
                return True
            return False

    def list_contexts(self) -> List[str]:
        with self._lock:
            return list(self._contexts.keys())

    # =========================================================================
    # Append operations
    # =========================================================================

    def append_observation(
        self,
        task_id: str,
        observation: Any,
        step_number: int = -1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """追加观察到 observations 层。

        Args:
            task_id: 任务 ID
            observation: 观察内容（str 或 dict）
            step_number: 步骤编号（-1 表示自动递增）
            metadata: 可选元数据

        Returns:
            条目 ID

        Raises:
            KeyError: task_id 不存在时
        """
        entry_id = uuid.uuid4().hex[:8]
        entry = ContextEntry(
            id=entry_id,
            layer=ContextLayer.OBSERVATIONS,
            content=observation,
            timestamp=time.time(),
            step_number=step_number,
            metadata=metadata or {},
        )
        with self._lock:
            ctx = self._get_ctx(task_id)
            if entry.step_number < 0:
                entry.step_number = ctx.total_steps
            ctx.observations.append(entry)
            ctx.total_steps = max(ctx.total_steps, entry.step_number + 1)
            ctx.last_updated = time.time()
        return entry_id

    def append_action(
        self,
        task_id: str,
        action: Any,
        step_number: int = -1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """追加动作到 actions 层。返回条目 ID。"""
        entry_id = uuid.uuid4().hex[:8]
        entry = ContextEntry(
            id=entry_id,
            layer=ContextLayer.ACTIONS,
            content=action,
            timestamp=time.time(),
            step_number=step_number,
            metadata=metadata or {},
        )
        with self._lock:
            ctx = self._get_ctx(task_id)
            if entry.step_number < 0:
                entry.step_number = ctx.total_steps
            ctx.actions.append(entry)
            ctx.total_steps = max(ctx.total_steps, entry.step_number + 1)
            ctx.last_updated = time.time()
        return entry_id

    def append_result(
        self,
        task_id: str,
        result: Any,
        step_number: int = -1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """追加结果到 results 层。返回条目 ID。"""
        entry_id = uuid.uuid4().hex[:8]
        entry = ContextEntry(
            id=entry_id,
            layer=ContextLayer.RESULTS,
            content=result,
            timestamp=time.time(),
            step_number=step_number,
            metadata=metadata or {},
        )
        with self._lock:
            ctx = self._get_ctx(task_id)
            if entry.step_number < 0:
                entry.step_number = ctx.total_steps
            ctx.results.append(entry)
            ctx.total_steps = max(ctx.total_steps, entry.step_number + 1)
            ctx.last_updated = time.time()
        return entry_id

    def add_immutable_fact(
        self,
        task_id: str,
        fact: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """添加不可变事实。返回条目 ID。"""
        entry_id = uuid.uuid4().hex[:8]
        entry = ContextEntry(
            id=entry_id,
            layer=ContextLayer.IMMUTABLE_FACTS,
            content=fact,
            timestamp=time.time(),
            step_number=0,
            metadata=metadata or {},
        )
        with self._lock:
            ctx = self._get_ctx(task_id)
            ctx.immutable_facts.append(entry)
            ctx.last_updated = time.time()
        return entry_id

    # =========================================================================
    # Read operations
    # =========================================================================

    def get_context(self, task_id: str) -> Optional[TaskContext]:
        """获取完整任务上下文（副本语义）。"""
        with self._lock:
            ctx = self._contexts.get(task_id)
            if ctx is None:
                return None
            # 返回深拷贝避免外部修改（简化版：直接返回，调用方不应修改）
            return ctx

    def get_observations(self, task_id: str) -> List[ContextEntry]:
        with self._lock:
            ctx = self._get_ctx(task_id)
            return list(ctx.observations)

    def get_actions(self, task_id: str) -> List[ContextEntry]:
        with self._lock:
            ctx = self._get_ctx(task_id)
            return list(ctx.actions)

    def get_results(self, task_id: str) -> List[ContextEntry]:
        with self._lock:
            ctx = self._get_ctx(task_id)
            return list(ctx.results)

    def get_facts(self, task_id: str) -> List[ContextEntry]:
        with self._lock:
            ctx = self._get_ctx(task_id)
            return list(ctx.immutable_facts)

    def get_recent_entries(
        self,
        task_id: str,
        layer: Optional[ContextLayer] = None,
        last_n: int = 10,
    ) -> List[ContextEntry]:
        """获取最近 N 条指定层级的条目。

        Args:
            task_id: 任务 ID
            layer: 指定层级（None 表示跨所有层级按时间排序）
            last_n: 返回最近 N 条
        """
        with self._lock:
            ctx = self._get_ctx(task_id)
            if layer is not None:
                entries = list(ctx.get_layer(layer))
            else:
                entries = (
                    ctx.observations + ctx.actions + ctx.results + ctx.summary
                )
                entries.sort(key=lambda e: e.timestamp)
        return entries[-last_n:] if last_n > 0 else entries

    # =========================================================================
    # Summary
    # =========================================================================

    def context_summary(self, task_id: str) -> Dict[str, Any]:
        """生成上下文摘要统计。"""
        with self._lock:
            ctx = self._get_ctx(task_id)
            return {
                "task_id": ctx.task_id,
                "created_at": ctx.created_at,
                "last_updated": ctx.last_updated,
                "total_steps": ctx.total_steps,
                "total_entries": ctx.total_entries,
                "compact_count": ctx.compact_count,
                "layer_counts": {
                    "immutable_facts": len(ctx.immutable_facts),
                    "observations": len(ctx.observations),
                    "actions": len(ctx.actions),
                    "results": len(ctx.results),
                    "summary": len(ctx.summary),
                },
                "oldest_entry": min(
                    (e.timestamp for e in ctx.immutable_facts),
                    default=None,
                ),
                "newest_entry": ctx.last_updated,
            }

    # =========================================================================
    # Compaction (delegates to ContextCompactor)
    # =========================================================================

    def compact_context(
        self,
        task_id: str,
        strategy: Any = None,
    ) -> Dict[str, Any]:
        """压缩上下文（委托给 ContextCompactor）。

        如果没有传入 compactor 实例，执行最小内联压缩：
        - 保留所有 immutable_facts
        - 截断 observations/actions/results 到最近 N 条
        - 将被截断的条目计数记录到 summary 层
        """
        from .context_compactor import ContextCompactor

        compactor = strategy or ContextCompactor()
        return compactor.compact(self, task_id)

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _get_ctx(self, task_id: str) -> TaskContext:
        ctx = self._contexts.get(task_id)
        if ctx is None:
            raise KeyError(f"Context not found for task_id: {task_id}")
        return ctx


# ── Module-level singleton for convenience ──
_default_manager: Optional[SessionContextManager] = None
_singleton_lock = threading.Lock()


def get_default_context_manager() -> SessionContextManager:
    global _default_manager
    with _singleton_lock:
        if _default_manager is None:
            _default_manager = SessionContextManager()
        return _default_manager
