"""Clarification policy — LAST RESORT, not default path.

ClarificationPolicy triggers ONLY when:
1. LLM confidence < 0.55 (low confidence)
2. Input is extremely short with no clear semantics
3. Multiple response_modes have conflicting confidence
4. Execution requested but missing necessary target
5. Truly ambiguous expressions: "弄一下", "处理一下", "写个东西"

ClarificationPolicy must NOT trigger for:
- Jokes, identity, capability questions
- Skill queries
- Workspace/directory questions
- Project structure queries
- Explanation requests
- Planning requests
- Debug analysis requests
- General conversation
"""

from __future__ import annotations

from .input_gateway import InputEnvelope
from .schema import Intent, IntentRoute, ResponseMode


def build_clarification_route(envelope: InputEnvelope, *, reason: str, confidence: float = 0.45) -> IntentRoute:
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
    """Only clarify if LLM confidence is very low.

    Threshold of 0.55 means: if LLM says confidence >= 0.55, we trust it.
    Only if LLM is genuinely uncertain (< 0.55) do we fall through to clarification.
    This prevents clarification from being the default path.
    """
    return confidence < threshold


def _choose_question(text: str) -> str:
    """Choose clarification question based on input patterns.

    This only handles patterns that the deterministic router has already
    identified as genuinely ambiguous.
    """
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
    # Generic fallback — open-ended question without assuming code vs text
    return "我需要再确认一下：你可以具体告诉我你想让我做什么吗？例如：读项目、解释代码、改文件、运行命令，或者聊天。"
