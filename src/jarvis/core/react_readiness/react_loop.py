"""
Bounded ReActLoop Skeleton — ReAct Readiness Phase Pack 1 (B6)

正式的最小 ReActLoop，不是隐式循环。
包含：observe() → plan() → act() → check() → maybe_retry() → stop()

参考收编（hermes/mini_swe_runner.py）：
  ✅ 保留：有界迭代(max_iterations)、step 计数、完成信号检测
  🔄 适配：去掉 Hermes 特定环境/Docker/Modal 依赖
  🔄 适配：接入 Jarvis ContextManager/WorkingMemory/ReplayStore/StopConditions

设计约束：
  - 不是 "while True + 几个 if"
  - bounded: max_steps / max_failures / max_budget 全部可配置
  - 有结构化 StopReason
  - 不绕开现有 TaskRuntime / Gateway / ControlSurface
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

# Import WorkingMemoryKey for use in _initialize and other methods
from .working_memory import WorkingMemoryKey
# Import EventType for error recording in run()
from .replay_store import EventType


# ── Loop State ───────────────────────────────────────────────────────

class LoopPhase(Enum):
    """ReAct 循环当前所处阶段。"""
    INIT = "init"
    OBSERVE = "observe"
    PLAN = "plan"
    ACT = "act"
    CHECK = "check"
    RETRY = "retry"
    STOPPED = "stopped"


class StopReason(Enum):
    """结构化停止原因。"""
    # 正常停止
    SUCCESS = "success"                     # 任务成功完成
    MAX_STEPS_REACHED = "max_steps"         # 达到最大步数
    # 失败停止
    MAX_FAILURES = "max_failures"           # 连续失败达到上限
    NO_PROGRESS = "no_progress"             # 无进展检测
    # 外部控制
    USER_CANCELLED = "user_cancelled"       # 用户取消
    APPROVAL_REQUIRED = "approval_required" # 需要人工审批
    # 资源耗尽
    BUDGET_EXHAUSTED = "budget_exhausted"   # 预算用尽
    TIMEOUT = "timeout"                    # 超时
    # 错误
    ERROR = "error"                        # 未预期的错误


@dataclass
class Observation:
    """Observe 阶段输出。"""
    content: Any                           # 观察到的内容
    source: str = ""                       # 来源 (e.g., "tool", "user", "system")
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_error: bool = False
    is_final: bool = False                 # 是否表示任务已完成

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "source": self.source,
            "metadata": self.metadata,
            "is_error": self.is_error,
            "is_final": self.is_final,
        }


@dataclass
class Plan:
    """Plan 阶段输出。"""
    action_name: str                       # 要执行的动作名称
    action_args: Dict[str, Any] = field(default_factory=dict)  # 动作参数
    reasoning: str = ""                    # 推理说明
    confidence: float = 1.0                # 置信度 (0-1)
    expected_outcome: str = ""             # 预期结果描述
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_name": self.action_name,
            "action_args": self.action_args,
            "reasoning": self.reasoning,
            "confidence": round(self.confidence, 3),
            "expected_outcome": self.expected_outcome,
            "metadata": self.metadata,
        }


@dataclass
class ActionResult:
    """Act 阶段输出。"""
    success: bool
    content: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "content": str(self.content)[:500] if self.content else None,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "metadata": self.metadata,
        }


@dataclass
class CheckResult:
    """Check 阶段输出。"""
    passed: bool                          # 检查是否通过
    should_stop: bool = False             # 是否应该停止（默认 False）
    stop_reason: Optional[StopReason] = None
    should_retry: bool = False            # 是否应该重试
    feedback: str = ""                     # 反馈信息
    progress_score: float = 0.0           # 进展评分 (0-1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "should_stop": self.should_stop,
            "stop_reason": self.stop_reason.value if self.stop_reason else None,
            "should_retry": self.should_retry,
            "feedback": self.feedback,
            "progress_score": round(self.progress_score, 3),
        }


# ── ReActLoop Configuration ──────────────────────────────────────────

@dataclass
class ReActLoopConfig:
    """ReActLoop 配置。"""
    max_steps: int = 20                   # 最大步数
    max_failures: int = 3                  # 最大连续失败次数
    max_retries_per_step: int = 2          # 每步最大重试次数
    max_context_budget: int = 50000        # 最大上下文预算（字符）
    timeout_seconds: Optional[float] = None  # 整体超时（None=不限）
    auto_compact: bool = True              # 自动触发上下文压缩
    record_replay: bool = True             # 记录回放数据
    require_approval_for_actions: bool = False  # 动作需要审批
    no_progress_threshold: int = 5         # N 步无进展则停止


# ── ReActLoop Result ─────────────────────────────────────────────────

@dataclass
class ReActLoopResult:
    """ReActLoop 执行结果。"""
    success: bool
    stop_reason: StopReason
    total_steps: int = 0
    total_failures: int = 0
    total_retries: int = 0
    observations: List[Observation] = field(default_factory=list)
    actions_taken: List[Plan] = field(default_factory=list)
    results: List[ActionResult] = field(default_factory=list)
    final_output: Any = None
    context_summary: Dict[str, Any] = field(default_factory=dict)
    replay_id: Optional[str] = None
    duration_seconds: float = 0.0
    budget_used: float = 0.0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "stop_reason": self.stop_reason.value,
            "total_steps": self.total_steps,
            "total_failures": self.total_failures,
            "total_retries": self.total_retries,
            "final_output": str(self.final_output)[:1000] if self.final_output else None,
            "duration_seconds": round(self.duration_seconds, 3),
            "budget_used": round(self.budget_used, 2),
            "replay_id": self.replay_id,
            "error_message": self.error_message,
            "num_observations": len(self.observations),
            "num_actions": len(self.actions_taken),
        }


# ── Core ReActLoop Class ──────────────────────────────────────────────

class BoundedReActLoop:
    """
    Bounded ReAct Loop — 核心编排骨架。

    循环流程：
      INIT → [OBSERVE → PLAN → ACT → CHECK → (RETRY?)] → STOP

    设计约束：
      - 不是 "while True + 几个 if"
      - 每个阶段是独立方法，可被子类覆盖
      - 所有边界条件通过 StopConditions 管理
      - 自动记录到 ReplayStore
      - 自动更新 ContextManager 和 WorkingMemory

    与 hermes/mini_swe_runner.py 的关系：
      - mini_swe_runner 是一个完整 runner（含 LLM 调用、Docker 环境）
      - BoundedReActLoop 是纯编排骨架（不含 LLM、不含环境）
      - StepRunner 负责 execute_action() 的实际执行
    """

    def __init__(
        self,
        config: Optional[ReActLoopConfig] = None,
        context_manager=None,
        working_memory=None,
        replay_store=None,
    ):
        self.config = config or ReActLoopConfig()
        self.ctx_mgr = context_manager
        self.wm = working_memory
        self.replay = replay_store

        # Runtime state
        self._phase = LoopPhase.INIT
        self._step_count = 0
        self._failure_count = 0
        self._retry_count = 0
        self._consecutive_failures = 0
        self._start_time: float = 0
        self._task_id: str = ""
        self._last_progress_score: float = 0.0
        self._steps_without_progress: int = 0

    # =========================================================================
    # Main entry point
    # =========================================================================

    def run(
        self,
        task_input: Any,
        task_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> ReActLoopResult:
        """
        执行完整的 ReAct 循环。

        Args:
            task_input: 任务输入（用户请求等）
            task_id: 任务 ID（不传则自动生成）
            initial_context: 初始上下文

        Returns:
            ReActLoopResult
        """
        result = ReActLoopResult(
            success=False,
            stop_reason=StopReason.ERROR,
        )
        self._start_time = time.time()
        self._task_id = task_id or f"react_{int(self._start_time)}_{id(self):x}"

        try:
            # ── Initialize ──
            self._phase = LoopPhase.INIT
            self._initialize(task_id=self._task_id, task_input=task_input, initial_context=initial_context)

            if self.replay:
                self.replay.create_replay(self._task_id)
                result.replay_id = self._task_id

            # ── Main loop ──
            while not self._should_stop():
                step_result = self._run_single_step()
                if step_result is None:
                    break  # 停止信号已在 _should_stop 或 _run_single_step 中设置

                obs, plan, action_result, check = step_result

                # Record
                result.observations.append(obs)
                if plan:
                    result.actions_taken.append(plan)
                if action_result:
                    result.results.append(action_result)

                # Update state
                self._step_count += 1
                result.total_steps = self._step_count

                # Progress tracking
                if hasattr(check, 'progress_score'):
                    if check.progress_score <= self._last_progress_score + 0.01:
                        self._steps_without_progress += 1
                    else:
                        self._steps_without_progress = 0
                    self._last_progress_score = check.progress_score

                # Early exit if check() signals stop (e.g., SUCCESS)
                if getattr(check, 'should_stop', False):
                    break

                # Auto compact
                if (
                    self.config.auto_compact
                    and self.ctx_mgr
                    and self._step_count % 5 == 0
                ):
                    from .context_compactor import ContextCompactor
                    compactor = ContextCompactor()
                    compactor.compact(self.ctx_mgr, self._task_id)

            # ── Finalize ──
            result.stop_reason = self._determine_stop_reason()
            result.success = result.stop_reason == StopReason.SUCCESS
            result.total_failures = self._failure_count
            result.total_retries = self._retry_count
            result.duration_seconds = time.time() - self._start_time

            # Copy final output from instance (set during _run_single_step)
            if hasattr(self, 'final_output'):
                result.final_output = self.final_output

            if self.ctx_mgr:
                result.context_summary = self.ctx_mgr.context_summary(self._task_id)
            if self.wm:
                result.budget_used = self.wm.get_working_memory(self._task_id, WorkingMemoryKey.BUDGET_USED, 0)

            if self.replay:
                self.replay.finalize_replay(
                    self._task_id,
                    stop_reason=result.stop_reason.value,
                )

        except Exception as e:
            result.error_message = str(e)
            # Preserve original stop reason if already determined
            # (e.g., max_steps was hit before an error occurred in cleanup)
            if result.stop_reason == StopReason.SUCCESS or not result.stop_reason.value.startswith("error"):
                result.stop_reason = StopReason.ERROR
            result.duration_seconds = time.time() - self._start_time
            if self.replay:
                self.replay.record_event(
                    self._task_id, EventType.ERROR, self._step_count,
                    {"error": str(e)}, "react_loop",
                )
                self.replay.finalize_replay(self._task_id, "error")

        return result

    # =========================================================================
    # Phase methods (override in subclass for custom behavior)
    # =========================================================================

    def _initialize(
        self, task_id: str, task_input: Any, initial_context: Optional[Dict],
    ) -> None:
        """初始化：创建上下文和 working memory。"""
        if self.ctx_mgr:
            ic = dict(initial_context or {})
            ic["facts"] = [f"Task input: {str(task_input)[:500]}"]
            self.ctx_mgr.create_context(task_id, ic)
        if self.wm:
            self.wm.create_store(task_id)
            self.wm.set_working_memory(task_id, WorkingMemoryKey.LOOP_START_TIME, time.time())

    def observe(self) -> Observation:
        """
        Observe 阶段 — 收集当前状态信息。

        默认实现返回空 observation。
        子类应覆盖此方法以连接真实工具/Gateway/ControlSurface。
        """
        return Observation(content={"status": "ready", "step": self._step_count})

    def plan(self, observation: Observation) -> Plan:
        """
        Plan 阶段 — 基于观察制定动作计划。

        默认实现返回空 plan（子类必须覆盖）。
        """
        return Plan(action_name="noop", reasoning="No planner configured")

    def act(self, plan: Plan) -> ActionResult:
        """
        Act 阶段 — 执行计划。

        默认实现返回空结果。子类应覆盖或使用 StepRunner。
        """
        start = time.time()
        return ActionResult(success=True, content=f"Executed: {plan.action_name}", duration_ms=(time.time()-start)*1000)

    def check(self, observation: Observation, plan: Plan, action_result: ActionResult) -> CheckResult:
        """
        Check 阶段 — 验证动作结果并决定下一步。

        默认实现：如果 action 成功且非 final → 继续；否则 → 停止。
        """
        if (action_result.error is not None) or not action_result.success:
            return CheckResult(
                passed=False, should_retry=True,
                feedback="Action failed, retrying",
            )

        if observation.is_final:
            return CheckResult(
                passed=True, should_stop=True,
                stop_reason=StopReason.SUCCESS,
                feedback="Task completed successfully",
                progress_score=1.0,
            )

        return CheckResult(
            passed=True, should_stop=False, should_retry=False,
            feedback="Continue",
            progress_score=min(0.5 + self._step_count * 0.05, 0.95),
        )

    def maybe_retry(
        self, observation: Observation, plan: Plan, action_result: ActionResult,
        check_result: CheckResult,
    ) -> tuple[bool, Plan]:
        """决定是否重试当前步骤。返回 (should_retry, maybe_new_plan)。"""
        if not check_result.should_retry:
            return False, plan
        if self._retry_count >= self.config.max_retries_per_step:
            return False, plan
        self._retry_count += 1
        return True, plan  # 默认重试相同 plan

    # =========================================================================
    # Internal loop control
    # =========================================================================

    def _run_single_step(self) -> Optional[tuple]:
        """执行单步 Observe→Plan→Act→Check。"""
        self._phase = LoopPhase.OBSERVE

        # Record step start
        if self.replay:
            self.replay.record_event(
                self._task_id, EventType.STEP_START, self._step_count,
                {"phase": "starting"}, "react_loop",
            )

        # Observe
        obs = self.observe()
        if self.ctx_mgr:
            self.ctx_mgr.append_observation(self._task_id, obs.to_dict(), self._step_count)
        if self.replay:
            self.replay.record_event(
                self._task_id, EventType.OBSERVATION, self._step_count,
                obs.to_dict(), "observe",
            )

        # Plan
        self._phase = LoopPhase.PLAN
        plan = self.plan(obs)
        if self.ctx_mgr:
            self.ctx_mgr.append_action(self._task_id, plan.to_dict(), self._step_count)
        if self.replay:
            self.replay.record_event(
                self._task_id, EventType.PLAN, self._step_count,
                plan.to_dict(), "plan",
            )

        # Act
        self._phase = LoopPhase.ACT
        action_result = self.act(plan)
        if self.ctx_mgr:
            self.ctx_mgr.append_result(self._task_id, action_result.to_dict(), self._step_count)
        if self.replay:
            self.replay.record_event(
                self._task_id, EventType.ACTION_RESULT, self._step_count,
                action_result.to_dict(), "act",
            )

        # Track failures
        if not action_result.success or (action_result.error is not None):
            self._failure_count += 1
            self._consecutive_failures += 1
            if self.wm:
                self.wm.increment_counter(self._task_id, WorkingMemoryKey.FAILURE_COUNT)
        else:
            self._consecutive_failures = 0

        # Check
        self._phase = LoopPhase.CHECK
        check_result = self.check(obs, plan, action_result)
        if self.replay:
            self.replay.record_event(
                self._task_id, EventType.CHECK, self._step_count,
                check_result.to_dict(), "check",
            )

        # Maybe Retry
        if check_result.should_retry:
            self._phase = LoopPhase.RETRY
            should_retry, new_plan = self.maybe_retry(obs, plan, action_result, check_result)
            if should_retry:
                if self.replay:
                    self.replay.record_event(
                        self._task_id, EventType.RETRY, self._step_count,
                        {"retry_number": self._retry_count}, "react_loop",
                    )
                if new_plan != plan:
                    plan = new_plan
                action_result = self.act(plan)
                check_result = self.check(obs, plan, action_result)
                if self.wm:
                    self.wm.increment_counter(self._task_id, WorkingMemoryKey.FAILURE_COUNT)

        # Update working memory with latest state
        if self.wm:
            self.wm.set_working_memory(self._task_id, WorkingMemoryKey.LAST_OBSERVATION, obs.to_dict())
            self.wm.set_working_memory(self._task_id, WorkingMemoryKey.LAST_ACTION, plan.to_dict())
            self.wm.set_working_memory(self._task_id, WorkingMemoryKey.LAST_RESULT, action_result.to_dict())
            self.wm.set_working_memory(self._task_id, WorkingMemoryKey.STEP_COUNT, self._step_count)

        # Set final output if successful
        # Note: final_output stored on instance; run() copies it to result
        if check_result.should_stop and check_result.stop_reason == StopReason.SUCCESS:
            final_val = getattr(action_result, 'content', None) or getattr(obs, 'content', None)
            object.__setattr__(self, 'final_output', final_val)

        return (obs, plan, action_result, check_result)

    def _should_stop(self) -> bool:
        """检查是否应该停止循环。"""
        cfg = self.config

        # Max steps
        if self._step_count >= cfg.max_steps:
            return True

        # Consecutive failures
        if self._consecutive_failures >= cfg.max_failures:
            return True

        # No progress
        if cfg.no_progress_threshold > 0 and self._steps_without_progress >= cfg.no_progress_threshold:
            return True

        # Timeout
        if cfg.timeout_seconds:
            elapsed = time.time() - self._start_time
            if elapsed >= cfg.timeout_seconds:
                return True

        # Budget
        if self.wm and cfg.max_context_budget > 0:
            budget_used = self.wm.get_working_memory(self._task_id, WorkingMemoryKey.BUDGET_USED, 0)
            if budget_used >= cfg.max_context_budget:
                return True

        return False

    def _determine_stop_reason(self) -> StopReason:
        """根据最终状态确定结构化停止原因。"""
        cfg = self.config

        if self._step_count >= cfg.max_steps:
            return StopReason.MAX_STEPS_REACHED
        if self._consecutive_failures >= cfg.max_failures:
            return StopReason.MAX_FAILURES
        if self._steps_without_progress >= cfg.no_progress_threshold:
            return StopReason.NO_PROGRESS
        if cfg.timeout_seconds and (time.time() - self._start_time) >= cfg.timeout_seconds:
            return StopReason.TIMEOUT
        # If we stopped with steps but no failures/limits hit, likely SUCCESS
        # (from check() signaling should_stop=True)
        if self._step_count > 0 and self._consecutive_failures == 0:
            return StopReason.SUCCESS
        return StopReason.MAX_STEPS_REACHED

    @property
    def phase(self) -> LoopPhase:
        return self._phase

    @property
    def step_count(self) -> int:
        return self._step_count
