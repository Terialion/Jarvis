from __future__ import annotations

import json
import logging
from typing import Any

from ..instructions.schema import InstructionBundle
from ..llm.prompt_builder import build_intent_classification_prompt
from ..llm.provider import LLMProvider, safe_complete

from .input_gateway import InputEnvelope
from .schema import Intent, IntentRoute, ResponseMode, RiskLevel

logger = logging.getLogger(__name__)

# Valid intents — LLM output must be one of these
_VALID_INTENTS = {
    Intent.CHAT.value,
    Intent.CAPABILITY_QA.value,
    Intent.USAGE_HELP.value,
    Intent.REPO_INSPECTION.value,
    Intent.CODING_TASK.value,
    Intent.SHELL_TASK.value,
    Intent.WEB_SEARCH.value,
    Intent.URL_SUMMARY.value,
    Intent.SKILL_MANAGEMENT.value,
    Intent.CONTEXT_RESUME.value,
    Intent.MODEL_MANAGEMENT.value,
    Intent.AUTOMATION.value,
    Intent.CLARIFY.value,
    Intent.UNKNOWN.value,
    # New intents that LLM may classify into
    "identity",
    "explain",
    "writing",
    "summary",
    "doc_edit",
    "context_followup",
}

# Valid response_modes — LLM output must be one of these
_VALID_RESPONSE_MODES = {
    ResponseMode.CHAT_ANSWER.value,
    ResponseMode.HELP_ANSWER.value,
    ResponseMode.REPO_INSPECTION.value,
    ResponseMode.AGENT_TOOL_LOOP.value,
    ResponseMode.SEARCH_PIPELINE.value,
    ResponseMode.URL_SUMMARY.value,
    ResponseMode.EXECUTOR_ACTION.value,
    ResponseMode.SKILL_ADMIN.value,
    ResponseMode.CONTEXT_ADMIN.value,
    ResponseMode.MODEL_ADMIN.value,
    ResponseMode.AUTOMATION_ACTION.value,
    ResponseMode.CLARIFY_QUESTION.value,
    ResponseMode.REFUSAL_OR_SAFETY_MESSAGE.value,
    ResponseMode.WORKSPACE_STATUS.value,
    ResponseMode.FILE_LISTING.value,
    ResponseMode.JOKE_ANSWER.value,
    ResponseMode.PLAN_ANSWER.value,
    ResponseMode.DEBUG_ANALYSIS.value,
    ResponseMode.CONTEXT_SUMMARY.value,
    ResponseMode.CONTEXT_FOLLOWUP.value,
}


def classify_intent_with_llm(
    envelope: InputEnvelope,
    instruction_bundle: InstructionBundle,
    examples: list[dict[str, object]],
    llm_provider: LLMProvider | None,
    tool_context: str | None = None,
) -> IntentRoute | None:
    """Classify user intent using LLM semantic understanding.

    This is the PRIMARY natural language routing path. The deterministic
    router handles only structural/safety high-confidence rules; everything
    else flows through here.

    Args:
        envelope: Input envelope with user text and metadata.
        instruction_bundle: Project instructions for context.
        examples: Few-shot examples for classification.
        llm_provider: LLM provider instance (None = skip).
        tool_context: Optional tool summary from ToolRegistry.to_llm_tool_context().
            When provided, the LLM classifier can consider available tools.
    """
    if llm_provider is None:
        logger.debug("LLM provider unavailable, returning None for fallback")
        return None

    prompt = build_intent_classification_prompt(
        instructions=instruction_bundle,
        user_input=envelope.raw_text,
        envelope={
            "language": envelope.language_hint,
            "workspace_root": str(envelope.workspace_root) if envelope.workspace_root else "",
            "is_slash_command": envelope.slash.is_slash_command,
            "has_url": envelope.has_url,
            "path_hints": list(envelope.path_hints),
            "sensitive_hints": list(envelope.sensitive_hints),
        },
        examples=examples,
        tool_context=tool_context,
    )
    raw = safe_complete(llm_provider, prompt, system="Return strict JSON only. No markdown, no explanation.")
    if raw is None:
        logger.debug("LLM returned None")
        return None

    # Strip markdown code fences if LLM wraps JSON in them
    raw = _strip_code_fences(raw)

    payload: dict[str, Any] | None = None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("LLM output is not valid JSON: %s — raw: %.200s", exc, raw)
        return None

    if not isinstance(payload, dict):
        logger.warning("LLM output is not a dict: %s", type(payload).__name__)
        return None

    # Validate intent
    intent = str(payload.get("intent") or "").strip()
    if intent not in _VALID_INTENTS:
        logger.warning("LLM returned unknown intent=%r, falling back", intent)
        return None

    # Validate response_mode — safe fallback to mapped mode if unknown
    response_mode = str(payload.get("response_mode") or "").strip()
    if response_mode not in _VALID_RESPONSE_MODES:
        response_mode = _safe_mode_fallback(intent)
        logger.info("LLM returned unknown response_mode=%r, mapped to %s", payload.get("response_mode"), response_mode)

    confidence = _parse_confidence(payload.get("confidence"))

    # Build route
    route = IntentRoute(
        intent=intent,
        response_mode=response_mode,
        confidence=confidence,
        summary=str(payload.get("summary") or "llm classified request"),
        reason=str(payload.get("reason") or "llm_semantic_classifier"),
        source="llm",
        requires_tools=list(payload.get("requires_tools") or []),
        requires_repo_read=bool(payload.get("requires_repo_read")),
        requires_write=bool(payload.get("requires_write")),
        requires_shell=bool(payload.get("requires_shell")),
        requires_network=bool(payload.get("requires_network")),
        requires_approval=bool(payload.get("requires_approval")),
        risk_level=_parse_risk_level(payload.get("risk_level")),
        should_clarify=bool(payload.get("should_clarify")),
        clarify_question=payload.get("clarify_question") if bool(payload.get("should_clarify")) else None,
        candidate_skills=list(payload.get("candidate_skills") or []),
        project_instruction_relevance=str(payload.get("project_instruction_relevance") or "none"),
        suggested_test_scope=str(payload.get("suggested_test_scope") or "none"),
        memory_relevance=str(payload.get("memory_relevance") or "none"),
        learning_signal=str(payload.get("learning_signal") or "none"),
        operator_trace={
            "source_surface": "cli",
            "route_source": "llm",
            "reason": str(payload.get("reason") or "llm_semantic_classifier"),
        },
        routing_trace={
            "input_kind": "natural_language",
            "deterministic_attempted": True,
            "deterministic_matched": False,
            "llm_fallback_called": True,
            "llm_confidence": confidence,
            "entered_llm": True,
            "final_decision": intent,
            "why_not_clarify": str(payload.get("why_not_clarify") or ""),
        },
    )
    return _enforce_llm_safety(route)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_confidence(value: Any) -> float:
    """Parse confidence from LLM output, clamping to [0, 1]."""
    try:
        c = float(value)
        return max(0.0, min(1.0, c))
    except (TypeError, ValueError):
        return 0.0


def _parse_risk_level(value: Any) -> str:
    """Parse risk_level from LLM output, defaulting to low."""
    valid = {r.value for r in RiskLevel}
    v = str(value or "").strip().lower()
    return v if v in valid else RiskLevel.LOW.value


def _safe_mode_fallback(intent: str) -> str:
    """Map an unknown response_mode to a safe default based on intent."""
    mapping = {
        Intent.CHAT.value: ResponseMode.CHAT_ANSWER.value,
        Intent.CAPABILITY_QA.value: ResponseMode.HELP_ANSWER.value,
        Intent.USAGE_HELP.value: ResponseMode.HELP_ANSWER.value,
        Intent.REPO_INSPECTION.value: ResponseMode.REPO_INSPECTION.value,
        Intent.CODING_TASK.value: ResponseMode.AGENT_TOOL_LOOP.value,
        Intent.SHELL_TASK.value: ResponseMode.EXECUTOR_ACTION.value,
        Intent.WEB_SEARCH.value: ResponseMode.SEARCH_PIPELINE.value,
        Intent.URL_SUMMARY.value: ResponseMode.URL_SUMMARY.value,
        Intent.SKILL_MANAGEMENT.value: ResponseMode.SKILL_ADMIN.value,
        Intent.CONTEXT_RESUME.value: ResponseMode.CONTEXT_ADMIN.value,
        Intent.MODEL_MANAGEMENT.value: ResponseMode.MODEL_ADMIN.value,
        Intent.AUTOMATION.value: ResponseMode.AUTOMATION_ACTION.value,
        Intent.CLARIFY.value: ResponseMode.CLARIFY_QUESTION.value,
        "identity": ResponseMode.CHAT_ANSWER.value,
        "explain": ResponseMode.PLAN_ANSWER.value,
        "writing": ResponseMode.PLAN_ANSWER.value,
        "summary": ResponseMode.CHAT_ANSWER.value,
        "context_followup": ResponseMode.CONTEXT_FOLLOWUP.value,
    }
    return mapping.get(intent, ResponseMode.CLARIFY_QUESTION.value)


def _strip_code_fences(raw: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = raw.strip()
    if text.startswith("```"):
        # Remove opening fence (may have language tag like ```json)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        # Remove closing fence
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    return text.strip()


def _enforce_llm_safety(route: IntentRoute) -> IntentRoute:
    """Enforce that LLM cannot bypass safety constraints.

    These are non-negotiable safety rules that the LLM output must satisfy.
    Even if the LLM tries to remove approval or lower risk, we enforce it.
    """
    raw = route.to_dict()
    changed = False

    # coding_task MUST have write + approval
    if raw["intent"] == Intent.CODING_TASK.value:
        if not raw["requires_write"]:
            raw["requires_write"] = True
            changed = True
        if not raw["requires_repo_read"]:
            raw["requires_repo_read"] = True
            changed = True
        if not raw["requires_approval"]:
            raw["requires_approval"] = True
            changed = True
        raw["response_mode"] = ResponseMode.AGENT_TOOL_LOOP.value
        raw["risk_level"] = max(raw.get("risk_level") or RiskLevel.LOW.value, RiskLevel.MEDIUM.value)
        if raw["risk_level"] == RiskLevel.LOW.value:
            changed = True

    # shell_task MUST have shell + approval
    if raw["intent"] == Intent.SHELL_TASK.value:
        if not raw["requires_shell"]:
            raw["requires_shell"] = True
            changed = True
        if not raw["requires_approval"]:
            raw["requires_approval"] = True
            changed = True
        raw["response_mode"] = ResponseMode.EXECUTOR_ACTION.value

    # web_search/url_summary MUST have network
    if raw["intent"] in {Intent.WEB_SEARCH.value, Intent.URL_SUMMARY.value}:
        if not raw["requires_network"]:
            raw["requires_network"] = True
            changed = True

    # safety refusal cannot be overridden — if response_mode is refusal, keep it
    if raw["response_mode"] == ResponseMode.REFUSAL_OR_SAFETY_MESSAGE.value:
        raw["risk_level"] = RiskLevel.BLOCKED.value if not raw.get("risk_level") or raw["risk_level"] == RiskLevel.LOW.value else raw["risk_level"]
        raw["requires_approval"] = True

    if changed:
        logger.warning("LLM safety enforcement applied to route: intent=%s", raw.get("intent"))

    return IntentRoute(**raw)
