"""
Context Compaction / Summary Strategy — ReAct Readiness Phase Pack 1 (A4)

做最小 compaction，不是只"把历史裁短"。
支持：token budget threshold, compaction trigger, summarize old observations,
     preserve critical facts, keep latest N steps verbatim。

参考收编（hermes/trajectory_compressor.py）：
  ✅ 保留：保护头尾区域策略、budget 驱动压缩、summary 替换
  🔄 适配：去掉 HuggingFace tokenizer 依赖 → 用字符估算 + budget 字段
  🔄 适配：去掉 LLM summarizer 依赖 → v1 用规则摘要，预留 LLM 接口

消费方：ContextManager.compact_context(), eval pack, replay
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# ── Configuration ────────────────────────────────────────────────────

@dataclass
class CompactionConfig:
    """压缩配置。"""
    # Budget 控制（v1 用字符估算，不要求真实 tokenizer）
    max_chars_budget: int = 50000          # 最大上下文字符预算
    warning_threshold: float = 0.8         # 超过 80% 时触发警告
    # 保留策略
    keep_latest_n_observations: int = 5    # 保留最近 N 条 observation
    keep_latest_n_actions: int = 5         # 保留最近 N 条 action
    keep_latest_n_results: int = 5         # 保留最近 N 条 result
    preserve_all_facts: bool = True        # 始终保留所有 immutable facts
    # Summary 配置
    summary_max_length: int = 2000         # 摘要最大长度
    use_llm_summarizer: bool = False       # 是否用 LLM 做摘要（v1=False）
    summarizer_fn: Optional[Callable[[List[str]], str]] = None  # 自定义摘要函数
    # 元数据
    track_metrics: bool = True             # 是否记录压缩指标


@dataclass
class CompactionMetrics:
    """单次压缩指标。"""
    before_entries: int = 0
    after_entries: int = 0
    entries_removed: int = 0
    chars_before: int = 0
    chars_after: int = 0
    chars_saved: int = 0
    was_compacted: bool = False
    triggered_at: str = ""
    duration_ms: float = 0.0
    strategy_used: str = ""
    facts_preserved: int = 0
    latest_preserved: int = 0
    summary_generated: bool = False
    summary_length: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "before_entries": self.before_entries,
            "after_entries": self.after_entries,
            "entries_removed": self.entries_removed,
            "chars_before": self.chars_before,
            "chars_after": self.chars_after,
            "chars_saved": self.chars_saved,
            "was_compacted": self.was_compacted,
            "triggered_at": self.triggered_at,
            "duration_ms": round(self.duration_ms, 2),
            "strategy_used": self.strategy_used,
            "facts_preserved": self.facts_preserved,
            "latest_preserved": self.latest_preserved,
            "summary_generated": self.summary_generated,
            "summary_length": self.summary_length,
        }


# ── Core Compactor ───────────────────────────────────────────────────

class ContextCompactor:
    """
    Context Compactor — 基于 budget 和规则的上下文压缩器。

    算法（改编自 Hermes TrajectoryCompressor 的保护区域策略）：
      1. 计算当前总大小
      2. 如果在预算内 → skip
      3. 保护 immutable_facts 层（全部保留）
      4. 保护每层最新 N 条
      5. 对中间的旧条目生成规则摘要
      6. 用摘要替换被移除条目
      7. 返回指标
    """

    def __init__(self, config: Optional[CompactionConfig] = None):
        self.config = config or CompactionConfig()

    def should_trigger(self, ctx) -> bool:
        """检查是否应该触发压缩。"""
        total = self._estimate_size(ctx)
        return total > self.config.max_chars_budget * self.config.warning_threshold

    def compact(
        self,
        context_manager: Any,  # SessionContextManager
        task_id: str,
    ) -> Dict[str, Any]:
        """
        执行压缩。返回包含 'success', 'metrics', 'compacted' 的结果 dict。

        这是 ContextManager.compact_context() 的委托目标。
        """
        start_time = time.time()

        ctx = context_manager.get_context(task_id)
        if ctx is None:
            return {
                "success": False,
                "error": f"No context found for task_id: {task_id}",
                "metrics": {},
                "compacted": False,
            }

        metrics = CompactionMetrics()
        metrics.before_entries = ctx.total_entries
        metrics.chars_before = self._estimate_size(ctx)
        metrics.triggered_at = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(),
        )

        # 检查是否需要压缩
        if not self.should_trigger(ctx):
            return {
                "success": True,
                "error": None,
                "metrics": metrics.to_dict(),
                "compacted": False,
                "reason": "under_budget",
            }

        cfg = self.config

        # ── Step 1: 保留所有 immutable_facts ──
        preserved_fact_count = len(ctx.immutable_facts)

        # ── Step 2: 截断各层到最新 N 条 ──
        old_obs = list(ctx.observations[:-cfg.keep_latest_n_observations]) if len(ctx.observations) > cfg.keep_latest_n_observations else []
        old_act = list(ctx.actions[:-cfg.keep_latest_n_actions]) if len(ctx.actions) > cfg.keep_latest_n_actions else []
        old_res = list(ctx.results[:-cfg.keep_latest_n_results]) if len(ctx.results) > cfg.keep_latest_n_results else []

        new_obs = list(ctx.observations[-cfg.keep_latest_n_observations:]) or []
        new_act = list(ctx.actions[-cfg.keep_latest_n_actions:]) or []
        new_res = list(ctx.results[-cfg.keep_latest_n_results:]) or []

        removed_count = len(old_obs) + len(old_act) + len(old_res)

        # ── Step 3: 生成规则摘要 ──
        summary_text = ""
        all_old = old_obs + old_act + old_res
        if all_old:
            summary_text = self._generate_summary(all_old)
            metrics.summary_generated = True
            metrics.summary_length = len(summary_text)

            # 将摘要写入 summary 层
            from .context_manager import ContextEntry, ContextLayer
            context_manager.append_result(
                task_id,
                f"[COMPACTED SUMMARY] {summary_text}",
                metadata={"compaction": True, "entries_replaced": removed_count},
            )

        # ── Step 4: 替换原列表为截断后的版本 ──
        # Use context manager's lock if available, otherwise no-op
        cm_lock = getattr(context_manager, '_lock', None)
        if cm_lock:
            with cm_lock:
                inner_ctx = self._do_replace(context_manager, task_id, new_obs, new_act, new_res)
        else:
            inner_ctx = self._do_replace(context_manager, task_id, new_obs, new_act, new_res)

        # ── 计算最终指标 ──
        metrics.after_entries = (
            preserved_fact_count + len(new_obs) + len(new_act) + len(new_res)
        )
        metrics.entries_removed = removed_count
        metrics.chars_after = self._estimate_size(inner_ctx) if inner_ctx else 0
        metrics.chars_saved = metrics.chars_before - metrics.chars_after
        metrics.was_compacted = True
        metrics.duration_ms = (time.time() - start_time) * 1000
        metrics.strategy_used = "protected_head_tail_with_summary"
        metrics.facts_preserved = preserved_fact_count
        metrics.latest_preserved = len(new_obs) + len(new_act) + len(new_res)

        return {
            "success": True,
            "error": None,
            "metrics": metrics.to_dict(),
            "compacted": True,
            "reason": "budget_exceeded",
            "removed_count": removed_count,
            "summary_length": len(summary_text),
        }

    def _do_replace(self, context_manager, task_id, new_obs, new_act, new_res):
        """Internal: replace layer lists with truncated versions."""
        inner_ctx = context_manager._contexts.get(task_id)
        if inner_ctx:
            inner_ctx.observations = new_obs
            inner_ctx.actions = new_act
            inner_ctx.results = new_res
            inner_ctx.compact_count += 1
            inner_ctx.last_updated = time.time()
        return inner_ctx

    # =========================================================================
    # Size estimation
    # =========================================================================

    def _estimate_size(self, ctx) -> int:
        """估算上下文总大小（字符数）。v1 不接 tokenizer。"""
        total = 0
        for entry in (
            ctx.immutable_facts + ctx.observations
            + ctx.actions + ctx.results + ctx.summary
        ):
            total += len(str(entry.content))
            total += len(entry.id) + 40  # metadata overhead estimate
        return total

    # =========================================================================
    # Summary generation (rule-based for v1)
    # =========================================================================

    def _generate_summary(self, entries: List[Any]) -> str:
        """基于规则生成摘要（v1 不调用 LLM）。"""
        if self.config.summarizer_fn:
            try:
                texts = [str(e.content) for e in entries]
                result = self.config.summarizer_fn(texts)
                if result and isinstance(result, str):
                    return result[:self.config.summary_max_length]
            except Exception:
                pass

        # 规则摘要 fallback
        parts = [f"Compacted {len(entries)} entries:"]
        by_type: Dict[str, int] = {}
        for e in entries:
            layer_name = getattr(e.layer, 'value', str(getattr(e, 'layer', 'unknown')))
            by_type[layer_name] = by_type.get(layer_name, 0) + 1
        for layer_name, count in sorted(by_type.items()):
            parts.append(f"- {count}x {layer_name}")

        content_preview = ""
        for e in entries[:3]:
            text = str(e.content)[:80]
            if text:
                content_preview += f"  [{text}...]"

        summary = "\n".join(parts)
        if content_preview and len(summary) < self.config.summary_max_length - 200:
            summary += f"\nSample:{content_preview}"

        return summary[:self.config.summary_max_length]

    # =========================================================================
    # Public introspection
    # =========================================================================

    def get_config(self) -> CompactionConfig:
        return self.config

    def get_budget_status(self, ctx) -> Dict[str, Any]:
        """获取当前预算使用状态。"""
        current = self._estimate_size(ctx)
        ratio = current / max(self.config.max_chars_budget, 1)
        return {
            "current_chars": current,
            "max_budget": self.config.max_chars_budget,
            "usage_ratio": round(ratio, 4),
            "percentage": f"{ratio * 100:.1f}%",
            "should_trigger": ratio >= self.config.warning_threshold,
            "remaining": max(0, self.config.max_chars_budget - current),
        }
