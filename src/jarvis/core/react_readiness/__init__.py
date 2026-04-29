"""
ReAct Readiness Phase Pack 1 — Context / Memory / Orchestration Harness

Modules:
  A1: context_manager.py    — Session Context Manager (分层上下文管理)
  A2: working_memory.py     — Working Memory (运行时短期状态)
  A3: memory_policy.py      — Memory Read/Write Policy (策略引擎)
  A4: context_compactor.py  — Context Compaction (预算驱动压缩)
  A5: replay_store.py       — Task/Event/Review Replay (只读回放)
  B6: react_loop.py         — Bounded ReActLoop Skeleton
  B7: step_runner.py        — Step Runner (observe→plan→act→check)
  B8: stop_conditions.py    — Stop Conditions/Budget/Retry/Fallback

All modules are zero-external-dependency (stdlib + dataclasses only).
"""

from .context_manager import (
    SessionContextManager,
    TaskContext,
    ContextEntry,
    ContextLayer,
    get_default_context_manager,
)
from .working_memory import (
    WorkingMemory,
    TaskWorkingMemory,
    WorkingMemoryKey,
    WorkingMemoryEntry,
    get_default_working_memory,
)
from .memory_policy import (
    MemoryPolicyEngine,
    DefaultMemoryRules,
    MemoryPolicyConfig,
    MemoryPolicyDecision,
    MemoryTier,
)
from .context_compactor import (
    ContextCompactor,
    CompactionConfig,
    CompactionMetrics,
)
from .replay_store import (
    ReplayStore,
    TaskReplay,
    ReplayEvent,
    EventType,
)
from .react_loop import (
    BoundedReActLoop,
    ReActLoopConfig,
    ReActLoopResult,
    Observation,
    Plan,
    ActionResult,
    CheckResult,
    LoopPhase,
    StopReason,
)
from .step_runner import (
    StepRunner,
    StepResult,
    StepConfig,
    create_step_runner_from_loop,
)
from .stop_conditions import (
    StopConditionsManager,
    BudgetState,
    RetryState,
    FallbackAction,
    StopCondition,
    StopTrigger,
)
from .heavy_runtime import (
    HeavyReActRuntime,
    HeavyReActConfig,
    RuntimeState,
    ObservationRecord,
    ActionRecord,
    CheckRecord,
    RuntimeStopRecord,
    StepTrace,
    RunResult,
)

__all__ = [
    # A-line
    "SessionContextManager", "TaskContext", "ContextEntry", "ContextLayer",
    "WorkingMemory", "TaskWorkingMemory", "WorkingMemoryKey", "WorkingMemoryEntry",
    "MemoryPolicyEngine", "DefaultMemoryRules", "MemoryPolicyConfig",
    "MemoryPolicyDecision", "MemoryTier",
    "ContextCompactor", "CompactionConfig", "CompactionMetrics",
    "ReplayStore", "TaskReplay", "ReplayEvent", "EventType",
    # B-line
    "BoundedReActLoop", "ReActLoopConfig", "ReActLoopResult",
    "Observation", "Plan", "ActionResult", "CheckResult",
    "LoopPhase", "StopReason",
    "StepRunner", "StepResult", "StepConfig", "create_step_runner_from_loop",
    "StopConditionsManager", "BudgetState", "RetryState", "FallbackAction",
    "StopCondition", "StopTrigger",
    "HeavyReActRuntime", "HeavyReActConfig", "RuntimeState",
    "ObservationRecord", "ActionRecord", "CheckRecord", "RuntimeStopRecord",
    "StepTrace", "RunResult",
    # Convenience
    "get_default_context_manager", "get_default_working_memory",
]
