"""
Stop Conditions / Budget / Retry / Fallback — ReAct Readiness Phase Pack 1 (B8)

明确定义而不是散落在代码里：
  - max_steps, max_retries, max_failures, max_context_budget
  - approval_required_stop, repeated_failure_stop, no_progress_stop
  - 结构化 stop reason
  - 可被 eval / operator surface 消费

消费方：ReActLoop._should_stop(), eval pack, StepRunner, operator UI
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

# Import from react_loop for compatibility
from .react_loop import StopReason


class StopTrigger(Enum):
    """停止触发器枚举（更细粒度的触发原因）。"""
    STEP_LIMIT = "step_limit"
    FAILURE_LIMIT = "failure_limit"
    RETRY_EXHAUSTED = "retry_exhausted"
    BUDGET_EXCEEDED = "budget_exceeded"
    TIMEOUT = "timeout"
    NO_PROGRESS = "no_progress"
    USER_CANCEL = "user_cancel"
    APPROVAL_NEEDED = "approval_needed"
    SUCCESS = "success"
    ERROR_FATAL = "error_fatal"


@dataclass
class StopCondition:
    """单个停止条件。"""
    name: str
    trigger: StopTrigger
    is_met: bool = False
    description: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)
    triggered_at_step: int = -1
    severity: str = "normal"  # normal | warning | critical

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "trigger": self.trigger.value,
            "is_met": self.is_met,
            "description": self.description,
            "detail": self.detail,
            "triggered_at_step": self.triggered_at_step,
            "severity": self.severity,
        }


@dataclass
class BudgetState:
    """预算状态追踪。"""
    total_budget: float = 0.0              # 总预算
    used_budget: float = 0.0               # 已使用
    budget_unit: str = "chars"             # 单位 (chars/tokens/calls/dollars)
    warnings_issued: int = 0               # 已发警告数
    last_warning_at: Optional[float] = None

    @property
    def remaining(self) -> float:
        return max(0, self.total_budget - self.used_budget)

    @property
    def usage_ratio(self) -> float:
        if self.total_budget <= 0:
            return 1.0
        return self.used_budget / max(self.total_budget, 1)

    @property
    def is_exhausted(self) -> bool:
        return self.used_budget >= self.total_budget and self.total_budget > 0

    @property
    def is_warning_level(self) -> bool:
        """是否达到警告阈值（>80% 使用率）。"""
        return self.usage_ratio >= 0.8 and not self.is_exhausted

    def use(self, amount: float) -> float:
        """消耗指定量预算。返回剩余预算。"""
        self.used_budget += amount
        return self.remaining

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_budget": self.total_budget,
            "used_budget": round(self.used_budget, 2),
            "remaining": round(self.remaining, 2),
            "usage_ratio": round(self.usage_ratio, 4),
            "usage_percent": f"{self.usage_ratio * 100:.1f}%",
            "is_exhausted": self.is_exhausted,
            "is_warning_level": self.is_warning_level,
            "warnings_issued": self.warnings_issued,
            "budget_unit": self.budget_unit,
        }


@dataclass
class RetryState:
    """重试状态追踪。"""
    max_retries: int = 2
    current_retries: int = 0
    failures: List[Dict[str, Any]] = field(default_factory=list)
    last_failure_error: Optional[str] = None
    backoff_base_seconds: float = 1.0

    @property
    def retries_remaining(self) -> int:
        return max(0, self.max_retries - self.current_retries)

    @property
    def is_exhausted(self) -> bool:
        return self.current_retries >= self.max_retries

    @property
    def can_retry(self) -> bool:
        return not self.is_exhausted

    def record_failure(self, error: str, context: Optional[Dict[str, Any]] = None) -> None:
        """记录一次失败。"""
        self.current_retries += 1
        self.last_failure_error = error
        self.failures.append({
            "attempt": self.current_retries,
            "error": error,
            "context": context or {},
            "timestamp": time.time(),
        })

    def reset(self) -> None:
        """重置重试状态（用于新步骤）。"""
        self.current_retries = 0
        self.last_failure_error = None
        # Keep failure history for diagnostics

    def get_backoff_delay(self) -> float:
        """计算退避延迟（指数退避）。"""
        import random
        delay = self.backoff_base_seconds * (2 ** self.current_retries)
        jitter = random.uniform(0, delay * 0.3)
        return min(delay + jitter, 30.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "current_retries": self.current_retries,
            "retries_remaining": self.retries_remaining,
            "is_exhausted": self.is_exhausted,
            "can_retry": self.can_retry,
            "last_failure_error": self.last_failure_error,
            "total_failures_recorded": len(self.failures),
            "backoff_base_s": self.backoff_base_seconds,
        }


@dataclass
class FallbackAction:
    """回退动作定义。"""
    name: str
    fn: Optional[Callable[[], Any]] = None       # 回退执行函数
    description: str = ""
    priority: int = 0                            # 越小越优先
    condition: Optional[Callable[[], bool]] = None  # 触发条件

    def is_available(self) -> bool:
        if self.condition is not None:
            try:
                return self.condition()
            except Exception:
                return False
        return True

    def execute(self) -> Any:
        if self.fn is not None:
            return self.fn()
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "available": self.is_available(),
            "has_handler": self.fn is not None,
        }


# ── Stop Conditions Manager ─────────────────────────────────────────

class StopConditionsManager:
    """
    Stop Conditions 管理器 — 集中管理所有停止条件和状态。

    设计为 ReActLoop 和 StepRunner 的共享决策引擎。
    """

    def __init__(
        self,
        max_steps: int = 20,
        max_failures: int = 3,
        max_retries_per_step: int = 2,
        max_context_budget: int = 50000,
        timeout_seconds: Optional[float] = None,
        no_progress_threshold: int = 5,
        require_approval: bool = False,
    ):
        self.max_steps = max_steps
        self.max_failures = max_failures
        self.max_retries_per_step = max_retries_per_step
        self.timeout_seconds = timeout_seconds
        self.no_progress_threshold = no_progress_threshold
        self.require_approval = require_approval

        # State tracking
        self._step_count: int = 0
        self._consecutive_failures: int = 0
        self._start_time: Optional[float] = None
        self._steps_without_progress: int = 0
        self._last_progress_score: float = 0.0

        # Sub-managers
        self.budget = BudgetState(total_budget=float(max_context_budget), budget_unit="chars")
        self.retry_state = RetryState(max_retries=max_retries_per_step)

        # Fallback chain
        self._fallbacks: List[FallbackAction] = []

        # All registered conditions
        self._conditions: List[StopCondition] = []
        self._init_default_conditions()

    def _init_default_conditions(self) -> None:
        """初始化默认停止条件列表。"""
        self._conditions = [
            StopCondition(
                name="max_steps", trigger=StopTrigger.STEP_LIMIT,
                description=f"Maximum steps ({self.max_steps}) reached",
                severity="warning",
            ),
            StopCondition(
                name="max_failures", trigger=StopTrigger.FAILURE_LIMIT,
                description=f"Consecutive failures ({self.max_failures}) reached",
                severity="critical",
            ),
            StopCondition(
                name="no_progress", trigger=StopTrigger.NO_PROGRESS,
                description=f"No progress for {self.no_progress_threshold} steps",
                severity="warning",
            ),
            StopCondition(
                name="budget_exceeded", trigger=StopTrigger.BUDGET_EXCEEDED,
                description="Context budget exhausted",
                severity="critical",
            ),
            StopCondition(
                name="timeout", trigger=StopTrigger.TIMEOUT,
                description="Execution timeout",
                severity="critical",
            ),
            StopCondition(
                name="approval_required", trigger=StopTrigger.APPROVAL_NEEDED,
                description="User approval required before action",
                severity="normal",
            ),
            StopCondition(
                name="success", trigger=StopTrigger.SUCCESS,
                description="Task completed successfully",
                severity="normal",
            ),
        ]

    # =========================================================================
    # Step lifecycle hooks (called by ReActLoop/StepRunner each step)
    # =========================================================================

    def on_step_start(self, step_number: int) -> None:
        """每步开始时调用。"""
        if self._start_time is None:
            self._start_time = time.time()
        self._step_count = step_number
        # Reset per-step retry state (but keep history)
        old_count = self.retry_state.current_retries
        self.retry_state.reset()
        self.retry_state.current_retries = old_count  # preserve global retry count

    def on_step_success(self, progress_score: float = 0.5) -> None:
        """步骤成功时调用。"""
        self._consecutive_failures = 0
        if progress_score > self._last_progress_score + 0.01:
            self._steps_without_progress = 0
            self._last_progress_score = progress_score
        else:
            # No meaningful progress detected
            self._steps_without_progress += 1
        self.budget.use(100)  # approximate cost per successful step

    def on_step_failure(self, error: str = "", context: Optional[Dict[str, Any]] = None) -> None:
        """步骤失败时调用。"""
        self._consecutive_failures += 1
        self.retry_state.record_failure(error or "Unknown error", context)

    def on_observation(self, observation_data: Any) -> None:
        """记录观察（计入预算）。"""
        size = len(str(observation_data)) if observation_data else 0
        self.budget.use(size)

    # =========================================================================
    # Evaluation API (main decision point)
    # =========================================================================

    def should_stop(self) -> tuple[bool, StopReason, StopCondition]:
        """
        检查是否应该停止。

        Returns:
          (should_stop, stop_reason, triggering_condition)
        """
        met_condition = None

        for cond in self._conditions:
            is_met = self._evaluate_condition(cond)
            cond.is_met = is_met
            if is_met and met_condition is None:
                cond.triggered_at_step = self._step_count
                met_condition = cond

        if met_condition is not None:
            reason = self._trigger_to_reason(met_condition.trigger)
            return True, reason, met_condition

        return False, StopReason.SUCCESS, StopCondition(name="none", trigger=StopTrigger.SUCCESS)

    def evaluate_all(self) -> List[StopCondition]:
        """评估所有条件，返回当前状态快照。"""
        for cond in self._conditions:
            cond.is_met = self._evaluate_condition(cond)
        return list(self._conditions)

    # =========================================================================
    # Fallback management
    # =========================================================================

    def add_fallback(self, fallback: FallbackAction) -> None:
        """注册回退动作。"""
        self._fallbacks.append(fallback)
        self._fallbacks.sort(key=lambda f: f.priority)

    def execute_best_fallback(self) -> Optional[Any]:
        """执行最高优先级的可用回退动作。"""
        for fb in self._fallbacks:
            if fb.is_available():
                return fb.execute()
        return None

    def list_fallbacks(self) -> List[FallbackAction]:
        return list(self._fallbacks)

    # =========================================================================
    # Status & introspection
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """获取完整状态报告（供 eval / operator 消费）。"""
        should_stop, reason, condition = self.should_stop()
        return {
            "should_stop": should_stop,
            "stop_reason": reason.value if reason else None,
            "triggering_condition": condition.to_dict() if condition else None,
            "step_count": self._step_count,
            "consecutive_failures": self._consecutive_failures,
            "steps_without_progress": self._steps_without_progress,
            "elapsed_seconds": round(time.time() - self._start_time, 2) if self._start_time else 0,
            "budget": self.budget.to_dict(),
            "retry_state": self.retry_state.to_dict(),
            "all_conditions": [c.to_dict() for c in self.evaluate_all()],
            "fallbacks_available": [fb.to_dict() for fb in self._fallbacks if fb.is_available()],
        }

    # =========================================================================
    # Internal evaluation logic
    # =========================================================================

    def _evaluate_condition(self, cond: StopCondition) -> bool:
        trigger = cond.trigger
        if trigger == StopTrigger.STEP_LIMIT:
            return self._step_count >= self.max_steps
        elif trigger == StopTrigger.FAILURE_LIMIT:
            return self._consecutive_failures >= self.max_failures
        elif trigger == StopTrigger.RETRY_EXHAUSTED:
            return self.retry_state.is_exhausted
        elif trigger == StopTrigger.BUDGET_EXCEEDED:
            return self.budget.is_exhausted
        elif trigger == StopTrigger.TIMEOUT:
            if self.timeout_seconds and self._start_time:
                return (time.time() - self._start_time) >= self.timeout_seconds
            return False
        elif trigger == StopTrigger.NO_PROGRESS:
            return (
                self.no_progress_threshold > 0
                and self._steps_without_progress >= self.no_progress_threshold
            )
        elif trigger == StopTrigger.APPROVAL_NEEDED:
            return self.require_approval
        elif trigger == StopTrigger.SUCCESS:
            return False  # success is externally set
        elif trigger == StopTrigger.ERROR_FATAL:
            return False  # externally set
        return False

    @staticmethod
    def _trigger_to_reason(trigger: StopTrigger) -> StopReason:
        mapping = {
            StopTrigger.STEP_LIMIT: StopReason.MAX_STEPS_REACHED,
            StopTrigger.FAILURE_LIMIT: StopReason.MAX_FAILURES,
            StopTrigger.RETRY_EXHAUSTED: StopReason.MAX_FAILURES,
            StopTrigger.BUDGET_EXCEEDED: StopReason.BUDGET_EXHAUSTED,
            StopTrigger.TIMEOUT: StopReason.TIMEOUT,
            StopTrigger.NO_PROGRESS: StopReason.NO_PROGRESS,
            StopTrigger.USER_CANCEL: StopReason.USER_CANCELLED,
            StopTrigger.APPROVAL_NEEDED: StopReason.APPROVAL_REQUIRED,
            StopTrigger.SUCCESS: StopReason.SUCCESS,
            StopTrigger.ERROR_FATAL: StopReason.ERROR,
        }
        return mapping.get(trigger, StopReason.MAX_STEPS_REACHED)
