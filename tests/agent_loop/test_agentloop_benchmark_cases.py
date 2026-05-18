from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.retry import ReplanPolicy
from src.jarvis.agent.types import ChatInput, ModelResponse, ToolCall, ToolResult


class FailingExecutor:
    permission_mode = "read_only"

    def execute(self, call, context=None):
        return ToolResult(
            call_id=call.id,
            name=call.name,
            ok=False,
            content="",
            error="command_failed",
            metadata={"error_code": "command_failed"},
        )


def test_benchmark_style_readme_request_uses_tool_events(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("Jarvis benchmark test", encoding="utf-8")

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    reasoning_summary="Need to read the README first.",
                    tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": str(readme)})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    assistant_text="README inspected",
                    final_answer="README inspected",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )

    result = loop.run_turn(ChatInput(text="读取 README.md", cwd=str(tmp_path)))
    assert result.output_type in {"answer", "tool_result"}
    assert result.stop_reason == "completed"
    assert len(result.tool_calls) >= 1
    assert any(evt.get("type") == "tool_call_started" for evt in result.events)
    assert any(evt.get("type") == "tool_call_completed" for evt in result.events)


def test_benchmark_style_ambiguous_request_clarifies(tmp_path: Path):
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    assistant_text="你希望我处理哪个文件、命令或具体问题？",
                    final_answer="你希望我处理哪个文件、命令或具体问题？",
                    finish_reason="stop",
                )
            ]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="帮我弄一下", cwd=str(tmp_path)))
    # The model responded with a clarification question — the loop relays it.
    assert result.final_answer
    assert "具体" in result.final_answer


def test_benchmark_style_sensitive_request_refuses(tmp_path: Path):
    # The _is_sensitive_request gate catches ".env" before the model is called.
    loop = AgentLoop(project_root=str(tmp_path), model_client=FakeModelClient(), auto_approve=True)
    result = loop.run_turn(ChatInput(text="打印我的 .env", cwd=str(tmp_path)))
    assert result.output_type == "refusal"
    assert result.stop_reason == "safety_refusal"
    assert "sk-" not in result.final_answer


def test_benchmark_style_tool_failure_returns_partial(tmp_path: Path):
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    reasoning_summary="Need a command first.",
                    tool_calls=[ToolCall.new(name="command_runner.run", arguments={"command": "python -V"})],
                    finish_reason="tool_calls",
                )
            ]
        ),
        tool_executor=FailingExecutor(),
        replan_policy=ReplanPolicy(max_replans=0),
        max_steps=1,
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="运行一个命令", cwd=str(tmp_path)))
    assert result.output_type in {"partial", "error"}
    assert result.stop_reason in {"tool_failed", "command_failed", "tests_failed"}
    assert result.final_answer
