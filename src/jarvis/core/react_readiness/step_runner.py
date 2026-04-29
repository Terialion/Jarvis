"""
Step Runner — ReAct Readiness Phase Pack 1 (B7)

把 Observation → Plan → Act → Check 串成可复用执行单元。

设计约束：
  - 不依赖 UI
  - 不依赖完整搜索 runtime
  - 以已有本地 tools + Gateway/ControlSurface 为基础
  - 对失败和 stop 条件有结构化记录

消费方：ReActLoop._run_single_step(), eval pack, standalone tool execution
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# Import from react_loop for type compatibility
from .react_loop import (
    Observation, Plan, ActionResult, CheckResult,
    StopReason, LoopPhase,
)


@dataclass
class StepConfig:
    """单步配置。"""
    step_number: int = 0
    timeout_seconds: Optional[float] = None      # 单步超时
    retry_on_failure: bool = True                 # 失败时是否重试
    max_retries: int = 2                          # 最大重试次数
    require_approval: bool = False                # 需要审批
    record_to_replay: bool = True                 # 记录到 replay
    update_context: bool = True                   # 更新 context manager
    update_working_memory: bool = True             # 更新 working memory


@dataclass
class StepResult:
    """Step Runner 单步执行结果。"""
    step_number: int
    phase: LoopPhase
    observation: Optional[Observation] = None
    plan: Optional[Plan] = None
    action_result: Optional[ActionResult] = None
    check_result: Optional[CheckResult] = None
    success: bool = False
    stopped: bool = False
    stop_reason: Optional[StopReason] = None
    retries_used: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "phase": self.phase.value,
            "success": self.success,
            "stopped": self.stopped,
            "stop_reason": self.stop_reason.value if self.stop_reason else None,
            "retries_used": self.retries_used,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
            "has_observation": self.observation is not None,
            "has_plan": self.plan is not None,
            "action_succeeded": self.action_result.success if self.action_result else None,
            "check_passed": self.check_result.passed if self.check_result else None,
        }


class StepRunner:
    """
    Step Runner — 可复用的 Observe→Plan→Act→Check 执行单元。

    与 BoundedReActLoop 的关系：
      - ReActLoop 管理整体循环边界（步数/失败数/预算）
      - StepRunner 管理单步的完整生命周期
      - ReActLoop 内部调用 StepRunner 或内联等价逻辑

    可以独立使用（不依赖完整 ReActLoop）：
      runner = StepRunner(observe_fn, plan_fn, act_fn, check_fn)
      result = runner.run_step(step_number=0)
    """

    def __init__(
        self,
        observe_fn: Callable[[], Observation],
        plan_fn: Callable[[Observation], Plan],
        act_fn: Callable[[Plan], ActionResult],
        check_fn: Callable[[Observation, Plan, ActionResult], CheckResult],
        context_manager=None,
        working_memory=None,
        replay_store=None,
        task_id: str = "",
        config: Optional[StepConfig] = None,
    ):
        """
        Args:
            observe_fn: 观察函数
            plan_fn: 规划函数
            act_fn: 执行函数
            check_fn: 检查函数
            context_manager: ContextManager 实例（可选）
            working_memory: WorkingMemory 实例（可选）
            replay_store: ReplayStore 实例（可选）
            task_id: 任务 ID
            config: 步骤配置
        """
        self.observe_fn = observe_fn
        self.plan_fn = plan_fn
        self.act_fn = act_fn
        self.check_fn = check_fn
        self.ctx_mgr = context_manager
        self.wm = working_memory
        self.replay = replay_store
        self.task_id = task_id
        self.config = config or StepConfig()

    def run_step(
        self,
        step_number: Optional[int] = None,
        override_config: Optional[StepConfig] = None,
    ) -> StepResult:
        """执行完整的一步 Observe→Plan→Act→Check。"""
        start_time = time.time()
        cfg = override_config or self.config
        step_num = step_number if step_number is not None else cfg.step_number

        result = StepResult(step_number=step_num, phase=LoopPhase.OBSERVE)

        try:
            # ── OBSERVE ──
            result.phase = LoopPhase.OBSERVE
            obs = self._call_with_timeout(
                self.observe_fn, cfg.timeout_seconds, "observe",
            )
            result.observation = obs

            if cfg.update_context and self.ctx_mgr:
                self.ctx_mgr.append_observation(self.task_id, obs.to_dict(), step_num)
            if cfg.update_working_memory and self.wm:
                from .working_memory import WorkingMemoryKey
                self.wm.set_working_memory(self.task_id, WorkingMemoryKey.LAST_OBSERVATION, obs.to_dict())
            if cfg.record_to_replay and self.replay:
                from .replay_store import EventType
                self.replay.record_event(self.task_id, EventType.OBSERVATION, step_num, obs.to_dict(), "step_runner")

            # ── PLAN ──
            result.phase = LoopPhase.PLAN
            plan = self._call_with_timeout(
                lambda: self.plan_fn(obs), cfg.timeout_seconds, "plan",
            )
            result.plan = plan

            if cfg.update_context and self.ctx_mgr:
                self.ctx_mgr.append_action(self.task_id, plan.to_dict(), step_num)
            if cfg.update_working_memory and self.wm:
                from .working_memory import WorkingMemoryKey
                self.wm.set_working_memory(self.task_id, WorkingMemoryKey.LAST_ACTION, plan.to_dict())
            if cfg.record_to_replay and self.replay:
                from .replay_store import EventType
                self.replay.record_event(self.task_id, EventType.PLAN, step_num, plan.to_dict(), "step_runner")

            # ── ACT ──
            result.phase = LoopPhase.ACT
            action_result = self._execute_action(plan, cfg)
            result.action_result = action_result

            if cfg.update_context and self.ctx_mgr:
                self.ctx_mgr.append_result(self.task_id, action_result.to_dict(), step_num)
            if cfg.update_working_memory and self.wm:
                from .working_memory import WorkingMemoryKey
                self.wm.set_working_memory(self.task_id, WorkingMemoryKey.LAST_RESULT, action_result.to_dict())
            if cfg.record_to_replay and self.replay:
                from .replay_store import EventType
                self.replay.record_event(self.task_id, EventType.ACTION_RESULT, step_num, action_result.to_dict(), "step_runner")

            # ── CHECK ──
            result.phase = LoopPhase.CHECK
            check = self._call_with_timeout(
                lambda: self.check_fn(obs, plan, action_result), cfg.timeout_seconds, "check",
            )
            result.check_result = check

            if cfg.record_to_replay and self.replay:
                from .replay_store import EventType
                self.replay.record_event(self.task_id, EventType.CHECK, step_num, check.to_dict(), "step_runner")

            # ── Determine outcome ──
            # Success = action succeeded AND check passed
            result.success = action_result.success and check.passed
            result.stopped = check.should_stop
            result.stop_reason = check.stop_reason

            # Retry logic
            if not result.success and cfg.retry_on_failure and result.retries_used < cfg.max_retries:
                for attempt in range(cfg.max_retries):
                    result.retries_used += 1
                    action_result = self._execute_action(plan, cfg)
                    result.action_result = action_result
                    check = self.check_fn(obs, plan, action_result)
                    result.check_result = check
                    result.success = action_result.success and check.passed
                    result.stopped = check.should_stop
                    result.stop_reason = check.stop_reason
                    if result.success or result.stopped:
                        break

            # Update step count in WM
            if cfg.update_working_memory and self.wm:
                self.wm.set_working_memory(self.task_id, "step_count", step_num + 1)

        except TimeoutError as e:
            result.error = f"Timeout in {result.phase.value}: {e}"
            result.stopped = True
            result.stop_reason = StopReason.TIMEOUT
        except Exception as e:
            result.error = f"Error in {result.phase.value}: {e}"
            result.stopped = True
            result.stop_reason = StopReason.ERROR

        result.duration_ms = (time.time() - start_time) * 1000
        return result

    def _execute_action(self, plan: Plan, cfg: StepConfig) -> ActionResult:
        """执行动作，带重试支持。"""
        try:
            result = self.act_fn(plan)

            # Track failures in WM
            if not result.success and self.wm:
                from .working_memory import WorkingMemoryKey
                self.wm.increment_counter(self.task_id, WorkingMemoryKey.FAILURE_COUNT)

            return result
        except Exception as e:
            return ActionResult(success=False, error=str(e))

    def _call_with_timeout(
        self, fn: Callable, timeout: Optional[float], phase_name: str,
    ) -> Any:
        """带超时调用的包装器（v1 不用 threading，直接调用；v2 可升级为真实 timeout）。"""
        # v1: direct call without real timeout enforcement
        # The timeout is informational; callers who need hard timeouts
        # should wrap run_step() themselves.
        try:
            return fn()
        except Exception as e:
            raise RuntimeError(f"{phase_name} failed: {e}") from e


# ── Convenience: build a StepRunner from a BoundedReActLoop ───────────

def create_step_runner_from_loop(loop) -> StepRunner:
    """从已有的 BoundedReActLoop 创建对应的 StepRunner。"""
    return StepRunner(
        observe_fn=loop.observe,
        plan_fn=loop.plan,
        act_fn=loop.act,
        check_fn=loop.check,
        context_manager=loop.ctx_mgr,
        working_memory=loop.wm,
        replay_store=loop.replay,
        task_id=loop._task_id,
    )
