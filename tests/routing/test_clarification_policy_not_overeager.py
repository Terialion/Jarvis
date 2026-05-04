"""Tests that ClarificationPolicy does NOT overeagerly fire for ordinary NL.

ClarificationPolicy must only fire when:
1. LLM confidence < 0.55
2. Input is genuinely ambiguous ("写个东西", "弄一下")
3. Both deterministic and LLM have no high-confidence match

Must NOT fire for: joke, skill query, workspace status, project structure,
explanation, planning, capability question, identity question.

NOTE: Default path uses AgentLoop._build_clarification_if_needed() instead.
The test_default_question_is_open_ended test uses the deprecated
clarification.py module directly and will emit DeprecationWarning.
"""

import pytest

from src.jarvis.core.routing.input_gateway import build_input_envelope
from src.jarvis.core.routing.intent_gateway import route_intent
from src.jarvis.core.routing.deterministic_router import route_deterministically
from src.jarvis.core.routing.clarification import build_clarification_route  # DEPRECATED — emits warnings
from src.jarvis.core.routing.examples import ROUTING_EXAMPLES


class TestDeterministicDoesNotCatchMovedRules:
    """Verify deterministic router no longer catches rules moved to LLM."""

    def test_joke_not_deterministic(self):
        envelope = build_input_envelope("给我讲个笑话")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85  # should NOT be high-confidence

    def test_tell_joke_english_not_deterministic(self):
        envelope = build_input_envelope("tell me a joke")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85

    def test_cold_joke_not_deterministic(self):
        envelope = build_input_envelope("讲个冷笑话")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85

    def test_workspace_status_not_deterministic(self):
        envelope = build_input_envelope("我现在的目录是什么")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85

    def test_workspace_root_not_deterministic(self):
        envelope = build_input_envelope("当前工作空间路径是什么")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85

    def test_project_structure_check_not_deterministic(self):
        """'帮我检查一下这个项目的结构' was moved to LLM."""
        envelope = build_input_envelope("帮我检查一下这个项目的结构")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85

    def test_skill_variants_not_all_deterministic(self):
        """'有哪些技能' is NOT in the deterministic token list."""
        envelope = build_input_envelope("有哪些技能")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85

    def test_explain_not_deterministic(self):
        envelope = build_input_envelope("解释 sandbox 和 approval")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85

    def test_plan_not_deterministic(self):
        envelope = build_input_envelope("帮我规划重构")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85


class TestDeterministicKeepsReasonableRules:
    """Verify deterministic router still catches reasonable high-confidence rules."""

    def test_greeting_zh_is_deterministic(self):
        envelope = build_input_envelope("你好")
        route = route_deterministically(envelope)
        assert route.confidence >= 0.85
        assert route.response_mode == "chat_answer"

    def test_greeting_en_is_deterministic(self):
        envelope = build_input_envelope("hello")
        route = route_deterministically(envelope)
        assert route.confidence >= 0.85
        assert route.response_mode == "chat_answer"

    def test_identity_zh_is_deterministic(self):
        envelope = build_input_envelope("你是谁")
        route = route_deterministically(envelope)
        assert route.confidence >= 0.85
        assert route.response_mode == "help_answer"

    def test_capability_qa_zh_is_deterministic(self):
        envelope = build_input_envelope("你能做什么")
        route = route_deterministically(envelope)
        assert route.confidence >= 0.85
        assert route.response_mode == "help_answer"

    def test_skill_management_direct_is_deterministic(self):
        envelope = build_input_envelope("查看skill")
        route = route_deterministically(envelope)
        assert route.confidence >= 0.85
        assert route.response_mode == "skill_admin"

    def test_coding_creation_is_deterministic(self):
        envelope = build_input_envelope("在这个工作空间写一个python程序")
        route = route_deterministically(envelope)
        assert route.confidence >= 0.85
        assert route.response_mode == "coding_loop"

    def test_shell_execution_is_deterministic(self):
        envelope = build_input_envelope("运行 pytest")
        route = route_deterministically(envelope)
        assert route.confidence >= 0.85
        assert route.response_mode == "executor_action"

    def test_ambiguous_still_deterministic(self):
        """Genuinely ambiguous inputs are still caught by deterministic."""
        envelope = build_input_envelope("写个东西")
        route = route_deterministically(envelope)
        # This IS a deterministic clarify (non_code_writing)
        assert route.response_mode == "clarify_question"

    def test_generic_ambiguous_still_deterministic(self):
        envelope = build_input_envelope("弄一下")
        route = route_deterministically(envelope)
        assert route.response_mode == "clarify_question"


class TestClarificationDefaultQuestion:
    """Verify default clarification question is open-ended."""

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_default_question_is_open_ended(self):
        envelope = build_input_envelope("some random input")
        route = build_clarification_route(envelope, reason="test")
        q = route.clarify_question or ""
        assert "读项目" in q or "解释代码" in q or "聊天" in q
