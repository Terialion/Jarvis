"""Intent gateway — orchestrates the full routing pipeline.

Routing order:
1. InputEnvelope (structural parsing: slash, URL, path, sensitive)
2. CommandRouter (slash commands — handled before this gateway)
3. SafetyPrecheck (high-confidence safety: .env, rm -rf, dangerous shell)
4. VeryHighConfidenceDeterministicRouter (greeting, identity, capability, etc.)
5. LLMIntentClassifier (primary natural language path)
6. ClarificationPolicy inline stub (LAST RESORT — only if LLM confidence < 0.55)
7. SafetyGate (post-routing safety check)
8. ResponseDispatcher

Key design principle:
- Ordinary natural language MUST go through LLMIntentClassifier
- ClarificationPolicy is NOT the default path for natural language
- DeterministicRouter only handles structural/high-confidence rules
- NOTE: This module NO LONGER imports clarification.py at module level.
  The legacy JARVIS_CLI_LEGACY_NL=1 path uses inline stubs instead.
  Default path uses AgentLoop._build_clarification_if_needed().
"""

from __future__ import annotations

from pathlib import Path

from ..instructions.loader import load_project_instructions
from ..instructions.schema import InstructionBundle
from ..llm.provider import LLMProvider
from .deterministic_router import route_deterministically
from .input_gateway import InputEnvelope, build_input_envelope
from .llm_classifier import classify_intent_with_llm
from .natural_language_preparer import prepare_natural_input
from .schema import Intent, IntentRoute, ResponseMode, RiskLevel


def _legacy_clarify_fallback(envelope: InputEnvelope, reason: str, confidence: float) -> IntentRoute:
    """Return a safe fallback clarification route for the legacy path.

    This is an inline stub so that intent_gateway.py does NOT import
    clarification.py at module load time. The legacy path
    (JARVIS_CLI_LEGACY_NL=1) uses this instead of build_clarification_route.
    """
    low = envelope.normalized_text.lower()
    if any(token in envelope.normalized_text for token in ("写一段说明", "写个东西", "帮我写一下", "写个总结", "写一封邮件", "项目介绍")):
        question = "你是想让我写一段普通说明文本，还是创建/修改项目里的代码文件或文档文件？"
    elif any(token in low for token in ("write a summary", "write something", "write an introduction", "write an email")):
        question = "Do you want plain prose, or do you want me to create or modify code or document files in this workspace?"
    elif any(token in envelope.normalized_text for token in ("跑一下", "运行一下", "测一下")) or any(token in low for token in ("run something", "test something")):
        question = "你想运行哪个命令或测试范围：相关测试、某个目录，还是指定命令？"
    elif any(token in envelope.normalized_text for token in ("弄一下", "处理一下", "看看这个", "来一下", "随便", "看着办")) or any(token in low for token in ("do something", "handle it", "take a look", "you decide")):
        question = "你想让我做哪类操作：读项目、修改代码、运行命令，还是搜索资料？"
    else:
        question = "我需要再确认一下：你可以具体告诉我你想让我做什么吗？例如：读项目、解释代码、改文件、运行命令，或者聊天。"
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


def _should_clarify_legacy(confidence: float, threshold: float = 0.55) -> bool:
    """Legacy clarification check — returns True if confidence < threshold."""
    return confidence < threshold


def route_intent(
    envelope: InputEnvelope,
    *,
    input_kind: str = "unknown_task",
    instruction_bundle: InstructionBundle | None = None,
    llm_provider: LLMProvider | None = None,
    examples: list[dict[str, object]] | None = None,
) -> IntentRoute:
    """Route user input through the full intent classification pipeline.

    Pipeline order (documented in module docstring):
    1. Slash command fast path
    2. Safety precheck (high-confidence safety)
    3. Deterministic router (structural/high-confidence rules only)
    4. LLM semantic classifier (primary NL path)
    5. Clarification policy (last resort)
    """
    instructions = instruction_bundle or load_project_instructions(Path(envelope.workspace_root or Path.cwd()))
    prepared = prepare_natural_input(envelope)

    # Step 1: Slash command fast path
    if envelope.slash.is_slash_command:
        return IntentRoute(
            intent=Intent.UNKNOWN.value,
            response_mode=ResponseMode.CLARIFY_QUESTION.value,
            confidence=1.0,
            source="slash",
            summary="slash command handled outside intent gateway",
            reason="slash_command_fast_path",
            should_clarify=False,
            clarify_question=None,
            operator_trace={"source_surface": "cli", "route_source": "slash", "reason": "slash_command_fast_path"},
            routing_trace={
                "input_kind": "slash",
                "deterministic_attempted": False,
                "deterministic_matched": False,
                "llm_fallback_called": False,
                "llm_confidence": None,
                "entered_llm": False,
                "final_decision": "slash_bypass",
                "why_not_clarify": "Slash commands are handled by CommandRouter before intent routing.",
            },
        )

    # Step 2: Safety precheck (high-confidence safety — cannot be overridden)
    prechecked = _route_high_confidence_safety(envelope)
    if prechecked is not None:
        return prechecked

    # Step 3: Deterministic router (structural/high-confidence rules only)
    deterministic = route_deterministically(envelope, input_kind=input_kind)
    if _is_high_confidence_route(deterministic):
        deterministic.routing_trace = {
            **dict(deterministic.routing_trace or {}),
            "prepared_command_count": len(prepared.command_metadata),
            "prepared_skill_count": len(prepared.skill_metadata),
        }
        return deterministic

    # Step 4: LLM semantic classifier (PRIMARY natural language path)
    llm_route = classify_intent_with_llm(
        envelope,
        instructions,
        examples or [],
        llm_provider,
    )

    # Step 4a: If LLM returned a valid route with sufficient confidence, use it
    if llm_route is not None and not _should_clarify_legacy(llm_route.confidence):
        llm_route.routing_trace = {
            **dict(llm_route.routing_trace or {}),
            "prepared_command_count": len(prepared.command_metadata),
            "prepared_skill_count": len(prepared.skill_metadata),
        }
        return llm_route

    # Step 5: Clarification policy (LAST RESORT)
    # Only reached if:
    # - Deterministic router had no high-confidence match, AND
    # - LLM was unavailable OR LLM confidence < 0.55
    # NOTE: Uses inline _legacy_clarify_fallback instead of clarification.py
    # to avoid loading the deprecated module at module level.
    clarify = _legacy_clarify_fallback(
        envelope,
        reason="deterministic_and_llm_uncertain" if llm_route is not None else "deterministic_uncertain_llm_unavailable",
        confidence=0.5 if llm_route is None else max(0.45, llm_route.confidence),
    )
    trace = dict(clarify.routing_trace)
    trace["input_kind"] = "natural_language"
    trace["llm_fallback_called"] = llm_route is not None or llm_provider is not None
    trace["llm_confidence"] = None if llm_route is None else llm_route.confidence
    trace["entered_llm"] = llm_provider is not None
    trace["why_not_clarify"] = "No high-confidence deterministic or LLM route."
    trace["prepared_command_count"] = len(prepared.command_metadata)
    trace["prepared_skill_count"] = len(prepared.skill_metadata)
    clarify.routing_trace = trace
    return clarify


def route_user_text(
    user_input: str,
    *,
    source_surface: str = "cli",
    input_kind: str = "unknown_task",
    workspace_root: Path | None = None,
    session_id: str = "cli_shell",
    instruction_bundle: InstructionBundle | None = None,
    llm_provider: LLMProvider | None = None,
    examples: list[dict[str, object]] | None = None,
) -> IntentRoute:
    envelope = build_input_envelope(user_input, workspace_root=workspace_root, session_id=session_id)
    return route_intent(
        envelope,
        input_kind=input_kind,
        instruction_bundle=instruction_bundle,
        llm_provider=llm_provider,
        examples=examples,
    )


def _route_high_confidence_safety(envelope: InputEnvelope) -> IntentRoute | None:
    """High-confidence safety precheck — runs BEFORE deterministic and LLM.

    These rules are non-negotiable and cannot be overridden by any router.
    """
    low = envelope.normalized_text.lower()
    if any(
        token in low
        for token in (
            ".env",
            ".npmrc",
            ".ssh",
            "id_rsa",
            "id_ed25519",
            "credential",
            "token",
            "secret",
            "private key",
            "api key",
            "password",
        )
    ):
        return IntentRoute(
            intent=Intent.UNKNOWN.value,
            response_mode=ResponseMode.REFUSAL_OR_SAFETY_MESSAGE.value,
            confidence=0.99,
            source="safety",
            summary="sensitive read request",
            reason="sensitive_read_precheck",
            requires_approval=True,
            risk_level=RiskLevel.HIGH.value,
            operator_trace={"source_surface": "cli", "route_source": "safety", "reason": "sensitive_read_precheck"},
            routing_trace={
                "input_kind": "natural_language",
                "deterministic_attempted": False,
                "deterministic_matched": False,
                "llm_fallback_called": False,
                "llm_confidence": None,
                "entered_llm": False,
                "final_decision": Intent.UNKNOWN.value,
                "why_not_clarify": "High-confidence safety refusal takes precedence.",
            },
        )
    if any(token in low for token in ("删除整个项目", "delete entire project", "delete the project", "rm -rf", "del /s")):
        return IntentRoute(
            intent=Intent.UNKNOWN.value,
            response_mode=ResponseMode.REFUSAL_OR_SAFETY_MESSAGE.value,
            confidence=0.99,
            source="safety",
            summary="destructive request blocked",
            reason="destructive_request_precheck",
            requires_write=True,
            requires_approval=True,
            risk_level=RiskLevel.HIGH.value,
            operator_trace={"source_surface": "cli", "route_source": "safety", "reason": "destructive_request_precheck"},
            routing_trace={
                "input_kind": "natural_language",
                "deterministic_attempted": False,
                "deterministic_matched": False,
                "llm_fallback_called": False,
                "llm_confidence": None,
                "entered_llm": False,
                "final_decision": Intent.UNKNOWN.value,
                "why_not_clarify": "High-confidence safety refusal takes precedence.",
            },
        )
    if _looks_like_dangerous_shell(low):
        return IntentRoute(
            intent=Intent.UNKNOWN.value,
            response_mode=ResponseMode.REFUSAL_OR_SAFETY_MESSAGE.value,
            confidence=0.99,
            source="safety",
            summary="dangerous shell pipeline blocked",
            reason="dangerous_shell_precheck",
            requires_shell=True,
            requires_network=True,
            requires_approval=True,
            risk_level=RiskLevel.CRITICAL.value,
            operator_trace={"source_surface": "cli", "route_source": "safety", "reason": "dangerous_shell_precheck"},
            routing_trace={
                "input_kind": "natural_language",
                "deterministic_attempted": False,
                "deterministic_matched": False,
                "llm_fallback_called": False,
                "llm_confidence": None,
                "entered_llm": False,
                "final_decision": Intent.UNKNOWN.value,
                "why_not_clarify": "High-confidence safety refusal takes precedence.",
            },
        )
    return None


def _looks_like_dangerous_shell(low: str) -> bool:
    if ("curl " in low or "wget " in low) and ("| sh" in low or "| bash" in low):
        return True
    if "invoke-webrequest" in low and ("| iex" in low or "invoke-expression" in low):
        return True
    return False


def _is_high_confidence_route(route: IntentRoute) -> bool:
    """Check if the deterministic router produced a high-confidence match.

    A route is high-confidence if:
    - Intent is not UNKNOWN
    - Response mode is not CLARIFY_QUESTION
    - Confidence >= 0.85

    Routes that don't meet this threshold will fall through to LLM.
    """
    if route.intent == Intent.UNKNOWN.value:
        return False
    if route.response_mode == ResponseMode.CLARIFY_QUESTION.value:
        return False
    return route.confidence >= 0.85
