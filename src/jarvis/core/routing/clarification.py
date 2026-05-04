"""Clarification policy — DEPRECATED. Last resort only.

.. deprecated::
    Clarification is now represented by:
        AgentRunResult.output_type = "clarification"
        stop_reason = "needs_user_clarification"
    This module must not be used by default runtime paths.
    Only kept for JARVIS_CLI_LEGACY_NL=1 legacy path.
    Deletion target: Phase 6 (blocked by intent_gateway.py runtime import + routing test deps).

Runtime import is DEPRECATED and will emit a DeprecationWarning.
"""

from __future__ import annotations

import warnings

from .input_gateway import InputEnvelope
from .schema import Intent, IntentRoute, ResponseMode


def _choose_question(text: str) -> str:
    """Choose clarification question based on input patterns."""
    low = text.lower()
    if any(token in text for token in ("写一段说明", "写个东西", "帮我写一下", "写个总结", "写一封邮件", "项目介绍")):
        return "你是想让我写一段普通说明文本，还是创建/修改项目里的代码文件或文档文件？"
    if any(token in low for token in ("write a summary", "write something", "write an introduction", "write an email")):
        return "Do you want plain prose, or do you want me to create or modify code or document files in this workspace?"
    if any(token in text for token in ("跑一下", "运行一下", "测一下")) or any(token in low for token in ("run something", "test something")):
        return "你想运行哪个命令或测试范围：相关测试、某个目录，还是指定命令？"
    if any(token in text for token in ("弄一下", "处理一下", "看看这个", "来一下", "随便", "看着办")) or any(
        token in low for token in ("do something", "handle it", "take a look", "you decide")
    ):
        return "你想让我做哪类操作：读项目、修改代码、运行命令，还是搜索资料？"
    return "我需要再确认一下：你可以具体告诉我你想让我做什么吗？例如：读项目、解释代码、改文件、运行命令，或者聊天。"


def build_clarification_route(envelope: InputEnvelope, *, reason: str, confidence: float = 0.45) -> IntentRoute:
    """Build a clarification route — DEPRECATED.

    .. deprecated::
        Use AgentLoop._build_clarification_if_needed() instead.
        This function is only kept for JARVIS_CLI_LEGACY_NL=1 compatibility.
    """
    warnings.warn(
        "build_clarification_route is deprecated. "
        "Use AgentLoop._build_clarification_if_needed() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    question = _choose_question(envelope.normalized_text)
    return IntentRoute(
        intent=Intent.CLARIFY.value,
        response_mode=ResponseMode.CLARIFY_QUESTION.value,
        confidence=confidence,
        source="clarify",
        summary="clarification required",
        reason=reason,
        should_clarify=True,
        clarify_question=question,
        operator_trace={
            "source_surface": "cli",
            "route_source": "clarify",
            "reason": reason,
        },
        routing_trace={
            "input_kind": "natural_language",
            "deterministic_attempted": True,
            "deterministic_matched": False,
            "llm_fallback_called": False,
            "entered_llm": False,
            "final_decision": Intent.CLARIFY.value,
            "why_not_clarify": "",
        },
    )


def should_clarify_from_llm(confidence: float, *, threshold: float = 0.55) -> bool:
    """Check if LLM confidence is low enough to need clarification — DEPRECATED.

    .. deprecated::
        Use AgentLoop._build_clarification_if_needed() instead.
        This function is only kept for JARVIS_CLI_LEGACY_NL=1 compatibility.
    """
    warnings.warn(
        "should_clarify_from_llm is deprecated. "
        "Use AgentLoop._build_clarification_if_needed() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return confidence < threshold
