"""
Memory Read / Write Policy — ReAct Readiness Phase Pack 1 (A3)

定义什么结果可以写入 execution memory，什么信息只留在 working memory，
什么内容禁止写入长期 memory，以及触发时机。

设计约束：
  - 最小规则引擎（不依赖外部策略框架）
  - 可被 eval pack 消费验证
  - 与 Context Manager / Working Memory 配合使用
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


class MemoryTier(enum.Enum):
    """Memory 层级。"""
    EXECUTION = "execution"    # 执行 memory：跨任务持久化
    WORKING = "working"         # working memory：任务内临时
    NONE = "none"               # 不写入任何 memory
    DENIED = "denied"           # 明确禁止


@dataclass
class MemoryPolicyDecision:
    """单条 memory 策略决策结果。"""
    tier: MemoryTier
    key: str
    value: Any
    reason: str = ""
    source_rule: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def is_allowed(self) -> bool:
        return self.tier != MemoryTier.DENIED

    @property
    def should_persist(self) -> bool:
        return self.tier == MemoryTier.EXECUTION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier.value,
            "key": self.key,
            "reason": self.reason,
            "source_rule": self.source_rule,
            "timestamp": self.timestamp,
            "allowed": self.is_allowed,
            "persist": self.should_persist,
        }


# ── 预定义规则集 ────────────────────────────────────────────────

class DefaultMemoryRules:
    """
    默认 Memory 读写策略。

    Write Policy:
      ✅ ALLOW → Execution Memory:
        - 最终结果 (final_result)
        - 关键发现/结论 (key_finding)
        - 用户明确要求记住的内容 (user_requested)
        - 错误模式/踩坑经验 (error_pattern)
        - 成功的代码变更记录 (code_change)

      ⚠️ WORKING ONLY:
        - 中间观察值 (observation)
        - 正在执行的 action (action)
        - 当前假设 (hypothesis)
        - 候选方案 (candidate)
        - 步骤计数器 (step_count)

      ❌ DENY:
        - 敏感信息 (api_key, password, token)
        - 大型原始输出 (>10KB 的 raw output)
        - 重复性日志 (repetitive_log)
        - 临时文件路径 (temp_file_path)

    Recall Policy:
      - 仅允许从 execution memory recall 已持久化的内容
      - working memory 内容随任务结束自动丢弃
    """

    # Keys allowed for execution memory (persistent)
    EXECUTION_KEYS: Set[str] = {
        "final_result", "key_finding", "user_requested",
        "error_pattern", "code_change",
        "successful_command", "test_outcome",
        "architecture_decision", "performance_metric",
    }

    # Keys that stay in working memory only
    WORKING_ONLY_KEYS: Set[str] = {
        "observation", "action", "hypothesis", "candidate",
        "step_count", "failure_count", "current_plan",
        "active_hypothesis", "failed_attempts",
        "candidate_files", "candidate_commands", "candidate_tests",
        "last_observation", "last_action", "last_result",
        "current_stop_reason", "budget_used",
    }

    # Keys explicitly denied
    DENIED_KEYS: Set[str] = {
        "api_key", "password", "token", "secret",
        "credential", "private_key",
        "raw_output_large", "repetitive_log",
        "temp_file_path", "intermediate_buffer",
    }

    # Key patterns denied (prefix match)
    DENIED_PREFIXES: List[str] = [
        "api_key_", "password_", "token_", "secret_",
        "temp_", "tmp_",
    ]

    @classmethod
    def classify(
        cls,
        key: str,
        value: Any,
        size_limit_bytes: int = 10240,
    ) -> MemoryPolicyDecision:
        """对给定的 key/value 进行分类决策。

        Args:
            key: memory 键名
            value: memory 值
            size_limit_bytes: 超过此大小的大值降级为 working-only

        Returns:
            MemoryPolicyDecision
        """
        key_lower = key.lower()

        # 1. Explicit deny list
        if key_lower in cls.DENIED_KEYS:
            return MemoryPolicyDecision(
                tier=MemoryTier.DENIED, key=key, value=value,
                reason=f"Key '{key}' in explicit deny list",
                source_rule="explicit_deny",
            )

        # 2. Deny by prefix
        for prefix in cls.DENIED_PREFIXES:
            if key_lower.startswith(prefix):
                return MemoryPolicyDecision(
                    tier=MemoryTier.DENIED, key=key, value=value,
                    reason=f"Key '{key}' matches deny prefix '{prefix}'",
                    source_rule="deny_prefix",
                )

        # 3. Working-only keys
        if key_lower in cls.WORKING_ONLY_KEYS:
            return MemoryPolicyDecision(
                tier=MemoryTier.WORKING, key=key, value=value,
                reason=f"Key '{key}' is working-memory-only",
                source_rule="working_only",
            )

        # 4. Size-based downgrade: large values → working only
        try:
            value_size = len(str(value))
            if value_size > size_limit_bytes:
                return MemoryPolicyDecision(
                    tier=MemoryTier.WORKING, key=key, value=value,
                    reason=f"Value size ({value_size} bytes) exceeds limit "
                          f"({size_limit_bytes} bytes)",
                    source_rule="size_limit",
                )
        except Exception:
            pass

        # 5. Execution keys
        if key_lower in cls.EXECUTION_KEYS:
            return MemoryPolicyDecision(
                tier=MemoryTier.EXECUTION, key=key, value=value,
                reason=f"Key '{key}' approved for execution memory",
                source_rule="execution_allow",
            )

        # 6. Default: allow into working memory
        return MemoryPolicyDecision(
            tier=MemoryTier.WORKING, key=key, value=value,
            reason=f"Key '{key}' not classified — default to working memory",
            source_rule="default_working",
        )


@dataclass
class MemoryPolicyConfig:
    """可配置的策略参数。"""
    size_limit_bytes: int = 10240
    custom_execution_keys: Set[str] = field(default_factory=set)
    custom_denied_keys: Set[str] = field(default_factory=set)
    custom_denied_prefixes: List[str] = field(default_factory=list)
    pre_write_hook: Optional[Callable[[str, Any], MemoryPolicyDecision]] = None
    post_write_hook: Optional[Callable[[MemoryPolicyDecision], None]] = None


class MemoryPolicyEngine:
    """
    Memory 策略引擎 — 基于 DefaultMemoryRules + 自定义配置做分类决策。

    支持自定义 hook 和扩展规则。
    """

    def __init__(self, config: Optional[MemoryPolicyConfig] = None):
        self.config = config or MemoryPolicyConfig()

    def decide(self, key: str, value: Any) -> MemoryPolicyDecision:
        """做出策略决策。"""
        # 1. Run default rules
        decision = DefaultMemoryRules.classify(
            key, value, self.config.size_limit_bytes,
        )

        # 2. Apply custom execution keys
        if key.lower() in self.config.custom_execution_keys:
            decision.tier = MemoryTier.EXECUTION
            decision.reason = f"Custom execution key override: {decision.reason}"
            decision.source_rule = "custom_execution"

        # 3. Apply custom denied keys
        if key.lower() in self.config.custom_denied_keys:
            decision.tier = MemoryTier.DENIED
            decision.reason = f"Custom deny override: {decision.reason}"
            decision.source_rule = "custom_deny"

        # 4. Pre-write hook
        if self.config.pre_write_hook:
            try:
                decision = self.config.pre_write_hook(key, value) or decision
            except Exception:
                pass

        # 5. Post-write hook
        if self.config.post_write_hook:
            try:
                self.config.post_write_hook(decision)
            except Exception:
                pass

        return decision

    def should_write_to_memory(
        self, key: str, value: Any,
    ) -> tuple[bool, MemoryTier]:
        """便捷方法：返回 (是否允许写入, 目标层级)。"""
        decision = self.decide(key, value)
        return decision.is_allowed, decision.tier

    def validate_batch(
        self, items: Dict[str, Any],
    ) -> List[MemoryPolicyDecision]:
        """批量校验多个 key-value 对。"""
        return [self.decide(k, v) for k, v in items.items()]


# ── Singleton ──
_default_policy: Optional[MemoryPolicyEngine] = None
_policy_lock = object()  # simple lock placeholder


def get_default_policy_engine() -> MemoryPolicyEngine:
    global _default_policy
    if _default_policy is None:
        _default_policy = MemoryPolicyEngine()
    return _default_policy
