"""Tests for LLM semantic routing."""

from __future__ import annotations

import json

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import ChatInput, ModelResponse
from src.jarvis.core.llm.provider import FakeLLMProvider
from src.jarvis.core.routing.examples import ROUTING_EXAMPLES
from src.jarvis.core.routing.input_gateway import build_input_envelope
from src.jarvis.core.routing.intent_gateway import route_intent


def _make_llm(intent: str, mode: str, confidence: float, **extra):
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
    def test_joke_request_without_llm_falls_to_clarify(self):
        envelope = build_input_envelope("给我讲个笑话")
        route = route_intent(envelope, examples=ROUTING_EXAMPLES)
        assert route.response_mode == "clarify_question"

    def test_workspace_status_without_llm_falls_to_clarify(self):
        envelope = build_input_envelope("我现在的目录是什么")
        route = route_intent(envelope, examples=ROUTING_EXAMPLES)
        assert route.response_mode == "clarify_question"


class TestLLMHandlesNLCorrectly:
    def test_llm_classifies_joke_as_chat(self):
        provider = _make_llm("chat", "chat_answer", 0.95, summary="joke request")
        envelope = build_input_envelope("给我讲个笑话")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.source == "llm"
        assert route.response_mode == "chat_answer"

    def test_llm_classifies_project_structure(self):
        provider = _make_llm(
            "repo_inspection",
            "repo_inspection",
            0.95,
            requires_repo_read=True,
            summary="project structure inspection",
        )
        envelope = build_input_envelope("帮我检查一下这个项目的结构")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.source == "llm"
        assert route.response_mode == "repo_inspection"
        assert route.requires_write is False


class TestClarificationPolicyPostLLM:
    def test_high_confidence_llm_skips_clarification(self):
        provider = _make_llm("chat", "chat_answer", 0.9, summary="direct answer")
        envelope = build_input_envelope("给我讲个笑话")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.response_mode == "chat_answer"

    def test_low_confidence_llm_triggers_clarification(self):
        provider = _make_llm("clarify", "clarify_question", 0.3, should_clarify=True)
        envelope = build_input_envelope("帮我做点什么")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.response_mode == "clarify_question"

    def test_agent_loop_ambiguous_input_clarifies(self, tmp_path):
        loop = AgentLoop(
            project_root=str(tmp_path),
            model_client=FakeModelClient(
                scripted=[ModelResponse(final_answer="unused", finish_reason="stop")]
            ),
            auto_approve=True,
        )
        result = loop.run_turn(ChatInput(text="帮我弄一下", cwd=str(tmp_path), project_id="test"))
        assert result.output_type == "clarification"
        assert result.stop_reason == "needs_user_clarification"


class TestLLMCannotOverrideSafety:
    def test_safety_precheck_blocks_before_llm(self):
        provider = _make_llm("chat", "chat_answer", 0.99, summary="read env file")
        envelope = build_input_envelope("读取 .env 看看")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.response_mode == "refusal_or_safety_message"
        assert route.source == "safety"


class TestAmbiguousInputClarifies:
    def test_llm_low_confidence_clarifies(self):
        provider = _make_llm("clarify", "clarify_question", 0.4, should_clarify=True)
        envelope = build_input_envelope("帮我做点什么")
        route = route_intent(envelope, llm_provider=provider, examples=ROUTING_EXAMPLES)
        assert route.response_mode == "clarify_question"
