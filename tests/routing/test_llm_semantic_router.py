"""Tests for LLM semantic routing — verifies ordinary NL goes through LLM, not deterministic.

Core invariants:
1. Ordinary NL (joke, skill query, workspace status, etc.) falls through deterministic to LLM
2. ClarificationPolicy does NOT fire for these when LLM returns sufficient confidence
3. ClarificationPolicy ONLY fires when LLM confidence < 0.55
4. Safety rules still work (cannot be overridden)
5. LLM cannot cancel approval requirements
6. LLM cannot override safety refusals

NOTE: Some tests directly call the deprecated should_clarify_from_llm from
clarification.py. These are marked with filterwarnings to suppress
DeprecationWarning.
"""

import pytest

from src.jarvis.core.instructions.schema import InstructionBundle
from src.jarvis.core.llm.provider import FakeLLMProvider, NullLLMProvider
from src.jarvis.core.routing.examples import ROUTING_EXAMPLES
from src.jarvis.core.routing.input_gateway import build_input_envelope
from src.jarvis.core.routing.intent_gateway import route_intent
from src.jarvis.core.routing.clarification import should_clarify_from_llm  # DEPRECATED — emits warnings


def _make_llm(intent: str, mode: str, confidence: float, **extra):
    """Helper to create a FakeLLMProvider that returns a valid JSON classification."""
    import json
    payload = {
        "intent": intent,
        "response_mode": mode,
        "confidence": confidence,
        "summary": extra.get("summary", f"{intent} request"),
        "requires_write": extra.get("requires_write", False),
        "requires_shell": extra.get("requires_shell", False),
        "requires_repo_read": extra.get("requires_repo_read", False),
        "requires_network": extra.get("requires_network", False),
        "requires_approval": extra.get("requires_approval", False),
        "risk_level": extra.get("risk_level", "low"),
        "should_clarify": extra.get("should_clarify", False),
        "clarify_question": None,
        "candidate_skills": [],
        "reason": extra.get("reason", f"classified as {intent}"),
    }
    return FakeLLMProvider(response=json.dumps(payload))


class TestNLFallsThroughToLLM:
    """Verify ordinary natural language passes through deterministic to LLM."""

    def test_joke_request_goes_to_llm(self):
        """Joke requests should NOT be caught by deterministic router."""
        envelope = build_input_envelope("给我讲个笑话")
        deterministic = route_intent(envelope, examples=ROUTING_EXAMPLES)
        # Without LLM, it should fall to clarify (not match deterministic joke rule)
        assert deterministic.response_mode == "clarify_question"

    def test_workspace_status_goes_to_llm(self):
        """Workspace status NL should NOT be caught by deterministic router."""
        envelope = build_input_envelope("我现在的目录是什么")
        route = route_intent(envelope, examples=ROUTING_EXAMPLES)
        # Without LLM, should fall to clarify
        assert route.response_mode == "clarify_question"

    def test_project_structure_nlg_goes_to_llm(self):
        """Project structure NL variations should fall through deterministic."""
        envelope = build_input_envelope("帮我检查一下这个项目的结构")
        route = route_intent(envelope, examples=ROUTING_EXAMPLES)
        # Without LLM, this was previously matched by deterministic
        # Now it should go through deterministic (no match) -> LLM (unavailable) -> clarify
        assert route.response_mode == "clarify_question"

    def test_skill_query_nlg_goes_to_llm(self):
        """Skill queries not in the exact token list should go to LLM."""
        envelope = build_input_envelope("有哪些技能")
        route = route_intent(envelope, examples=ROUTING_EXAMPLES)
        # "有哪些技能" is NOT in the deterministic skill_management tokens
        # Should fall through to LLM -> clarify (without LLM)
        assert route.response_mode == "clarify_question"


class TestLLMHandlesNLCorrectly:
    """Verify LLM correctly classifies ordinary NL when available."""

    def test_llm_classifies_joke_as_chat(self):
        provider = _make_llm("chat", "chat_answer", 0.95, summary="joke request")
        envelope = build_input_envelope("给我讲个笑话")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.source == "llm"
        assert route.response_mode == "chat_answer"
        assert route.requires_approval is False

    def test_llm_classifies_skill_query(self):
        provider = _make_llm("skill_management", "skill_management", 0.95)
        envelope = build_input_envelope("有哪些技能")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.source == "llm"
        assert route.intent == "skill_management"
        assert route.requires_approval is False

    def test_llm_classifies_workspace_status(self):
        provider = _make_llm("repo_inspection", "workspace_status", 0.95,
                            requires_repo_read=True, summary="workspace status query")
        envelope = build_input_envelope("我现在的目录是什么")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.source == "llm"
        assert route.response_mode == "workspace_status"
        assert route.requires_repo_read is True
        assert route.requires_write is False

    def test_llm_classifies_project_structure(self):
        provider = _make_llm("repo_inspection", "repo_inspection", 0.95,
                            requires_repo_read=True, summary="project structure inspection")
        envelope = build_input_envelope("帮我检查一下这个项目的结构")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.source == "llm"
        assert route.response_mode == "repo_inspection"
        assert route.requires_write is False

    def test_llm_classifies_planning(self):
        provider = _make_llm("repo_inspection", "plan_answer", 0.9,
                            requires_repo_read=True, summary="planning request")
        envelope = build_input_envelope("帮我规划一下如何重构输入路由，不要直接改代码")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.source == "llm"
        assert route.response_mode == "plan_answer"
        assert route.requires_write is False

    def test_llm_classifies_explain_as_chat(self):
        provider = _make_llm("chat", "chat_answer", 0.85, summary="explanation request")
        envelope = build_input_envelope("解释 sandbox 和 approval")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.source == "llm"
        assert route.requires_write is False
        assert route.requires_approval is False


class TestClarificationPolicyPostLLM:
    """Verify ClarificationPolicy fires ONLY when LLM confidence < 0.55.

    These tests directly call should_clarify_from_llm from clarification.py,
    which is deprecated. They are kept for legacy coverage.
    """

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_high_confidence_llm_skips_clarification(self):
        assert should_clarify_from_llm(0.9) is False
        assert should_clarify_from_llm(0.55) is False
        assert should_clarify_from_llm(0.56) is False

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_low_confidence_llm_triggers_clarification(self):
        assert should_clarify_from_llm(0.54) is True
        assert should_clarify_from_llm(0.3) is True
        assert should_clarify_from_llm(0.0) is True

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_threshold_boundary(self):
        """Threshold is 0.55 — exactly 0.55 should NOT clarify."""
        assert should_clarify_from_llm(0.55) is False


class TestLLMCannotOverrideSafety:
    """Verify LLM output safety constraints are enforced."""

    def test_llm_cannot_remove_coding_approval(self):
        provider = _make_llm("coding_task", "coding_loop", 0.9,
                            requires_write=False, requires_approval=False)
        envelope = build_input_envelope("修复 bug 并跑测试")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.requires_write is True  # enforced
        assert route.requires_approval is True  # enforced

    def test_llm_cannot_remove_shell_approval(self):
        provider = _make_llm("shell_task", "executor_action", 0.9,
                            requires_shell=False, requires_approval=False)
        envelope = build_input_envelope("运行 pytest")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.requires_shell is True  # enforced
        assert route.requires_approval is True  # enforced

    def test_safety_precheck_blocks_before_llm(self):
        """Safety precheck runs BEFORE LLM — .env requests always blocked."""
        provider = _make_llm("chat", "chat_answer", 0.99, summary="read env file")
        envelope = build_input_envelope("读取 .env 看看")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.response_mode == "refusal_or_safety_message"
        assert route.source == "safety"

    def test_destructive_blocked_before_llm(self):
        provider = _make_llm("coding_task", "coding_loop", 0.99)
        envelope = build_input_envelope("删除整个项目")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.response_mode == "refusal_or_safety_message"
        assert route.source == "safety"


class TestAmbiguousInputClarifies:
    """Verify genuinely ambiguous input still triggers clarification."""

    def test_write_something_clarifies(self):
        """'写个东西' is genuinely ambiguous — should clarify."""
        envelope = build_input_envelope("写个东西")
        route = route_intent(envelope, examples=ROUTING_EXAMPLES)
        # Deterministic matches non_code_writing -> clarify
        assert route.response_mode == "clarify_question"

    def test_do_something_clarifies(self):
        """'弄一下' is genuinely ambiguous — should clarify."""
        envelope = build_input_envelope("随便弄一下")
        route = route_intent(envelope, examples=ROUTING_EXAMPLES)
        # Deterministic matches generic_ambiguous -> clarify
        assert route.response_mode == "clarify_question"

    def test_llm_low_confidence_clarifies(self):
        """If LLM returns low confidence, should clarify."""
        provider = _make_llm("clarify", "clarify_question", 0.4, should_clarify=True)
        envelope = build_input_envelope("帮我做点什么")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.response_mode == "clarify_question"
