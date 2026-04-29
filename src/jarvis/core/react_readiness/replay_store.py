"""
Task / Event / Review Replay — ReAct Readiness Phase Pack 1 (A5)

只读 replay 骨架，支持：
  - task replay: 按任务 ID 回放完整执行轨迹
  - event replay: 按时间范围回放事件序列
  - review replay: 按 step 回放（用于 operator / eval 审查）

设计约束：
  - 先只读，不做复杂可视化
  - 与 Gateway / timeline / events 对齐
  - 可被 eval pack 和 operator surface 消费

消费方：eval pack, operator surface, future replay UI
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(Enum):
    """事件类型枚举。"""
    STEP_START = "step_start"
    OBSERVATION = "observation"
    PLAN = "plan"
    ACTION = "action"
    ACTION_RESULT = "action_result"
    CHECK = "check"
    RETRY = "retry"
    STOP = "stop"
    ERROR = "error"
    COMPACTION = "compaction"
    USER_INPUT = "user_input"
    MEMORY_WRITE = "memory_write"
    BUDGET_UPDATE = "budget_update"


@dataclass
class ReplayEvent:
    """单条可回放事件。"""
    id: str
    event_type: EventType
    task_id: str
    timestamp: float
    step_number: int
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = ""  # 来源组件名

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "step_number": self.step_number,
            "payload": self.payload,
            "source": self.source,
        }


@dataclass
class TaskReplay:
    """单个任务的完整回放数据。"""
    task_id: str
    events: List[ReplayEvent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    stop_reason: str = ""

    @property
    def total_events(self) -> int:
        return len(self.events)

    @property
    def duration(self) -> float:
        if not self.events:
            return 0.0
        if self.completed_at:
            return self.completed_at - self.events[0].timestamp
        # fallback: last event - first event
        return self.events[-1].timestamp - self.events[0].timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "total_events": self.total_events,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "stop_reason": self.stop_reason,
            "duration_seconds": round(self.duration, 3),
            "events": [e.to_dict() for e in self.events],
        }


class ReplayStore:
    """
    Replay Store — 存储和查询任务事件轨迹。

    线安全：threading.RLock
    设计为只读回放（写入通过 record_* 方法由运行时调用）。

    与 ContextManager 的关系：
      - ContextManager 管理"当前活跃上下文"
      - ReplayStore 管理"已完成的历史轨迹"
      - 任务结束后应将 ContextManager 的内容快照到 ReplayStore
    """

    def __init__(self):
        import threading
        self._replays: Dict[str, TaskReplay] = {}
        self._lock = threading.RLock()

    # =========================================================================
    # Recording API (called by runtime during execution)
    # =========================================================================

    def create_replay(self, task_id: str) -> TaskReplay:
        """为新任务创建回放记录。"""
        with self._lock:
            replay = TaskReplay(task_id=task_id)
            self._replays[task_id] = replay
            return replay

    def record_event(
        self,
        task_id: str,
        event_type: EventType,
        step_number: int,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "",
    ) -> str:
        """记录一条事件。返回事件 ID。"""
        event_id = uuid.uuid4().hex[:12]
        event = ReplayEvent(
            id=event_id,
            event_type=event_type,
            task_id=task_id,
            timestamp=time.time(),
            step_number=step_number,
            payload=payload or {},
            source=source,
        )
        with self._lock:
            replay = self._get(task_id)
            replay.events.append(event)
        return event_id

    def finalize_replay(
        self,
        task_id: str,
        stop_reason: str = "",
    ) -> bool:
        """标记任务回放完成。"""
        with self._lock:
            replay = self._get(task_id)
            replay.completed_at = time.time()
            replay.stop_reason = stop_reason
            return True

    # =========================================================================
    # Read-only Query API (for eval / operator / replay)
    # =========================================================================

    def get_task_replay(self, task_id: str) -> Optional[TaskReplay]:
        """获取任务的完整回放数据。"""
        with self._lock:
            return self._replays.get(task_id)

    def get_events(
        self,
        task_id: str,
        event_type: Optional[EventType] = None,
        start_step: Optional[int] = None,
        end_step: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[ReplayEvent]:
        """
        获取事件列表（支持过滤）。

        这是三种 replay 模式的统一入口：
          - task replay: 不传 filter → 全部事件
          - event replay: 传 event_type → 特定类型事件序列
          - review replay: 传 start_step/end_step → 指定步骤范围
        """
        with self._lock:
            replay = self._get(task_id)
            events = list(replay.events)

        if event_type is not None:
            events = [e for e in events if e.event_type == event_type]
        if start_step is not None:
            events = [e for e in events if e.step_number >= start_step]
        if end_step is not None:
            events = [e for e in events if e.step_number <= end_step]
        if limit is not None:
            events = events[-limit:]
        return events

    def get_step_events(
        self, task_id: str, step_number: int,
    ) -> List[ReplayEvent]:
        """获取指定步骤的所有事件（review replay）。"""
        return self.get_events(
            task_id, start_step=step_number, end_step=step_number,
        )

    def get_timeline(self, task_id: str) -> List[Dict[str, Any]]:
        """获取按时间排序的事件时间线。"""
        events = self.get_events(task_id)
        events.sort(key=lambda e: e.timestamp)
        return [
            {
                "time": e.timestamp,
                "type": e.event_type.value,
                "step": e.step_number,
                "source": e.source,
                "payload_summary": {k: str(v)[:80] for k, v in e.payload.items()},
            }
            for e in events
        ]

    def list_replays(
        self,
        only_completed: bool = False,
    ) -> List[str]:
        """列出所有 replay 的 task_id。"""
        with self._lock:
            if only_completed:
                return [
                    tid for tid, r in self._replays.items()
                    if r.completed_at is not None
                ]
            return list(self._replays.keys())

    def get_stats(self, task_id: str) -> Dict[str, Any]:
        """获取任务回放统计信息（供 eval 使用）。"""
        replay = self.get_task_replay(task_id)
        if replay is None:
            return {"error": f"No replay found for {task_id}"}
        events = replay.events
        type_counts: Dict[str, int] = {}
        for e in events:
            t = e.event_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        steps = set(e.step_number for e in events)
        errors = sum(1 for e in events if e.event_type == EventType.ERROR)
        retries = sum(1 for e in events if e.event_type == EventType.RETRY)
        return {
            "task_id": task_id,
            "total_events": len(events),
            "total_steps": max(steps) if steps else 0,
            "duration_seconds": round(replay.duration, 3),
            "stop_reason": replay.stop_reason,
            "completed": replay.completed_at is not None,
            "event_types": type_counts,
            "error_count": errors,
            "retry_count": retries,
            "first_event_time": events[0].timestamp if events else None,
            "last_event_time": events[-1].timestamp if events else None,
        }

    def export_replay_json(self, task_id: str) -> Optional[Dict[str, Any]]:
        """导出回放数据为 JSON-friendly dict。"""
        replay = self.get_task_replay(task_id)
        if replay is None:
            return None
        return replay.to_dict()

    def remove_replay(self, task_id: str) -> bool:
        """删除回放数据。"""
        with self._lock:
            if task_id in self._replays:
                del self._replays[task_id]
                return True
            return False

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _get(self, task_id: str) -> TaskReplay:
        replay = self._replays.get(task_id)
        if replay is None:
            raise KeyError(f"No replay found for task_id: {task_id}")
        return replay


# ── Singleton ──
import threading as _threading
_default_replay: Optional[ReplayStore] = None
_replay_lock = _threading.Lock()


def get_default_replay_store() -> ReplayStore:
    global _default_replay
    with _replay_lock:
        if _default_replay is None:
            _default_replay = ReplayStore()
        return _default_replay
