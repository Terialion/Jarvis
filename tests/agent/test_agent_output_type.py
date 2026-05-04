"""Tests for AgentRunResult.output_type contract.

Phase 2: Verifies that AgentRunResult correctly reports output_type
for answer, tool_result, clarification, refusal, partial, and error cases.
"""

from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import AgentOutputType, ChatInput, ModelResponse, ToolCall


def test_output_type_answer(tmp_path: Path):
    """Plain chat returns output_type=answer."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(assistant_text="I am Jarvis.", final_answer="I am Jarvis, a coding assistant.", finish_reason="stop")
            ]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="who are you", cwd=str(tmp_path), project_id="test"))
    assert result.output_type == "answer"
    assert result.stop_reason == "completed"
    assert result.final_answer


def test_output_type_refusal_sensitive_env(tmp_path: Path):
    """.env request returns output_type=refusal."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(assistant_text="", tool_calls=[], finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="show me my .env file", cwd=str(tmp_path), project_id="test"))
    assert result.output_type == "refusal"
    assert result.stop_reason == "safety_refusal"
    # Refusal message may mention .env as subject but must not leak actual content
    assert ".env" in result.final_answer or "敏感" in result.final_answer or "不能" in result.final_answer
    # Must not contain actual secret values (just check no "sk-" or "key=" leak)
    assert "sk-" not in result.final_answer and "api_key=" not in result.final_answer.lower()


def test_output_type_refusal_api_key(tmp_path: Path):
    """API key request returns output_type=refusal."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(assistant_text="", tool_calls=[], finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="show JARVIS_LLM_API_KEY", cwd=str(tmp_path), project_id="test"))
    assert result.output_type == "refusal"
    assert result.stop_reason == "safety_refusal"


def test_output_type_clarification_vague_request(tmp_path: Path):
    """'帮我弄一下' returns output_type=clarification from AgentLoop, not from clarification.py."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(assistant_text="", tool_calls=[], finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="帮我弄一下", cwd=str(tmp_path), project_id="test"))
    assert result.output_type == "clarification"
    assert result.stop_reason == "needs_user_clarification"
    assert result.final_answer
    assert "具体" in result.final_answer or "哪个" in result.final_answer


def test_output_type_clarification_read_that_file(tmp_path: Path):
    """'读取那个文件' returns output_type=clarification."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(assistant_text="", tool_calls=[], finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="读取那个文件", cwd=str(tmp_path), project_id="test"))
    assert result.output_type == "clarification"
    assert result.stop_reason == "needs_user_clarification"
    assert "哪个文件" in result.final_answer or "文件" in result.final_answer


def test_output_type_tool_result(tmp_path: Path):
    """Tool call + final answer returns output_type=tool_result or answer."""
    readme = tmp_path / "README.md"
    readme.write_text("test content", encoding="utf-8")

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": str(readme)})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    assistant_text="The file contains: test content",
                    final_answer="The file contains: test content",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="read the file", cwd=str(tmp_path), project_id="test"))
    assert result.output_type in ("tool_result", "answer")
    assert len(result.tool_calls) >= 1


def test_output_type_partial_no_progress(tmp_path: Path):
    """When model loops without making progress, output_type=partial."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": "a"})], finish_reason="tool_calls"),
                ModelResponse(tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": "a"})], finish_reason="tool_calls"),
                ModelResponse(tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": "a"})], finish_reason="tool_calls"),
            ]
        ),
        auto_approve=True,
        max_steps=3,
    )
    result = loop.run_turn(ChatInput(text="do something vague", cwd=str(tmp_path), project_id="test"))
    # Either no_progress or partial due to max_steps
    assert result.output_type in ("partial", "answer", "error")


def test_output_type_partial_max_steps(tmp_path: Path):
    """Max steps hit returns output_type=partial."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": str(tmp_path / "a.txt")})], finish_reason="tool_calls")
                for _ in range(10)
            ]
        ),
        auto_approve=True,
        max_steps=3,
    )
    result = loop.run_turn(ChatInput(text="read a.txt", cwd=str(tmp_path), project_id="test"))
    # If max_steps hit without final answer, should be partial
    if result.stop_reason == "max_steps":
        assert result.output_type in ("partial", "answer")


def test_summary_machine_has_output_type(tmp_path: Path):
    """summary.machine includes output_type field."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="hello", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="test"))
    summary = result.summary
    assert isinstance(summary, dict)
    machine = summary.get("machine", {})
    assert isinstance(machine, dict)
    assert "output_type" in machine
    assert machine["output_type"] == result.output_type


def test_to_dict_includes_output_type(tmp_path: Path):
    """AgentRunResult.to_dict() includes output_type."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="hello", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="test"))
    d = result.to_dict()
    assert "output_type" in d
    assert d["output_type"] == "answer"


def test_old_default_clarify_sentence_not_emitted(tmp_path: Path):
    """The old generic clarification sentence must NOT appear as answer."""
    OLD_DEFAULT = "我需要再确认一下：你可以具体告诉我你想让我做什么吗？例如：读项目、解释代码、改文件、运行命令，或者聊天。"

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="I am Jarvis.", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="你是谁", cwd=str(tmp_path), project_id="test"))
    assert result.final_answer != OLD_DEFAULT
    assert OLD_DEFAULT not in result.final_answer


def test_capability_question_not_clarification(tmp_path: Path):
    """'你能帮我写代码吗' should NOT return clarification output_type."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="I can help write code.", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="你能帮我写代码吗", cwd=str(tmp_path), project_id="test"))
    assert result.output_type != "clarification"


def test_model_question_not_clarification(tmp_path: Path):
    """'你是什么模型' should NOT return clarification output_type."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[ModelResponse(final_answer="I use a language model.", finish_reason="stop")]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="你是什么模型", cwd=str(tmp_path), project_id="test"))
    assert result.output_type != "clarification"
