"""Tests that clarification does not overeagerly fire for ordinary NL."""

from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import ChatInput, ModelResponse
from src.jarvis.core.routing.deterministic_router import route_deterministically
from src.jarvis.core.routing.input_gateway import build_input_envelope


class TestDeterministicDoesNotCatchMovedRules:
    def test_joke_not_deterministic(self):
        envelope = build_input_envelope("给我讲个笑话")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85

    def test_workspace_status_not_deterministic(self):
        envelope = build_input_envelope("我现在的目录是什么")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85

    def test_project_structure_check_not_deterministic(self):
        envelope = build_input_envelope("帮我检查一下这个项目的结构")
        route = route_deterministically(envelope)
        assert route.confidence < 0.85


class TestDeterministicKeepsReasonableRules:
    def test_greeting_is_deterministic(self):
        envelope = build_input_envelope("你好")
        route = route_deterministically(envelope)
        assert route.confidence >= 0.85
        assert route.response_mode == "chat_answer"

    def test_identity_is_deterministic(self):
        envelope = build_input_envelope("你是谁")
        route = route_deterministically(envelope)
        assert route.confidence >= 0.85
        assert route.response_mode == "help_answer"

    def test_generic_ambiguous_still_deterministic(self):
        envelope = build_input_envelope("弄一下")
        route = route_deterministically(envelope)
        assert route.response_mode == "clarify_question"


class TestDefaultPathNotOvereager:
    @staticmethod
    def _run_turn(text: str, tmp_path: Path):
        loop = AgentLoop(
            project_root=str(tmp_path),
            model_client=FakeModelClient(
                scripted=[ModelResponse(final_answer="plain answer", finish_reason="stop")]
            ),
            auto_approve=True,
        )
        return loop.run_turn(ChatInput(text=text, cwd=str(tmp_path), project_id="test"))

    def test_model_question_is_not_clarification(self, tmp_path: Path):
        result = self._run_turn("你是什么模型", tmp_path)
        assert result.output_type == "answer"

    def test_capability_question_is_not_clarification(self, tmp_path: Path):
        result = self._run_turn("你能帮我写代码吗", tmp_path)
        assert result.output_type == "answer"

    def test_joke_request_is_not_clarification(self, tmp_path: Path):
        result = self._run_turn("给我讲个笑话", tmp_path)
        assert result.output_type == "answer"

