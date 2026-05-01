"""Intent gateway — orchestrates the full routing pipeline.

Routing order:
1. InputEnvelope (structural parsing: slash, URL, path, sensitive)
2. CommandRouter (slash commands — handled before this gateway)
3. SafetyPrecheck (high-confidence safety: .env, rm -rf, dangerous shell)
4. VeryHighConfidenceDeterministicRouter (greeting, identity, capability, etc.)
5. LLMIntentClassifier (primary natural language path)
6. ClarificationPolicy (LAST RESORT — only if LLM confidence < 0.55)
7. SafetyGate (post-routing safety check)
8. ResponseDispatcher

Key design principle:
- Ordinary natural language MUST go through LLMIntentClassifier
- ClarificationPolicy is NOT the default path for natural language
- DeterministicRouter only handles structural/high-confidence rules
"""

from __future__ import annotations

from pathlib import Path

from ..instructions.loader import load_project_instructions
from ..instructions.schema import InstructionBundle
from ..llm.provider import LLMProvider
from .clarification import build_clarification_route, should_clarify_from_llm
from .deterministic_router import route_deterministically
from .input_gateway import InputEnvelope, build_input_envelope
from .llm_classifier import classify_intent_with_llm
from .natural_language_preparer import prepare_natural_input
from .schema import Intent, IntentRoute, ResponseMode, RiskLevel


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
    if llm_route is not None and not should_clarify_from_llm(llm_route.confidence):
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
    clarify = build_clarification_route(
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
