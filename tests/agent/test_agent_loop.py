from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import ChatInput, ModelResponse, ToolCall


def test_agent_loop_smoke_no_tool(tmp_path: Path):
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    assistant_text="hello",
                    final_answer="hello",
                    finish_reason="stop",
                )
            ]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="hi", cwd=str(tmp_path), project_id="p"))
    assert result.ok is True
    assert result.final_answer == "hello"
    assert result.stop_reason == "completed"
    assert result.events


def test_agent_loop_tool_call_then_final(tmp_path: Path):
    readme = tmp_path / "README.md"
    readme.write_text("hello world", encoding="utf-8")

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    reasoning_summary="need read file",
                    tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": str(readme)})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    assistant_text="read complete",
                    final_answer="read complete",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="read file", cwd=str(tmp_path), project_id="p2"))
    assert result.ok is True
    assert result.final_answer == "read complete"
    assert len(result.tool_calls) >= 1
    assert len(result.tool_results) >= 1


def test_agent_loop_stream_smoke_no_tool(tmp_path: Path):
    """Streaming path: text-only answer yields text_delta + done."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    assistant_text="Hello, how can I help?",
                    final_answer="Hello, how can I help?",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )
    chunks = list(loop.run_turn_stream(ChatInput(text="hi", cwd=str(tmp_path), project_id="p")))
    text_deltas = [c for c in chunks if c.kind == "text_delta"]
    done_chunks = [c for c in chunks if c.kind == "done"]
    progress_deltas = [c for c in chunks if c.kind == "progress_delta"]
    assert len(text_deltas) > 0, "Should have text_delta for final answer"
    assert len(done_chunks) == 1
    assert done_chunks[0].finish_reason == "stop"
    assert len(progress_deltas) == 0, "No progress_delta when no tools called"
    full_text = "".join(c.text_delta for c in text_deltas)
    assert "Hello" in full_text


def test_agent_loop_stream_tool_then_answer(tmp_path: Path):
    """Streaming path: text + tool calls → progress_delta, then final answer."""
    readme = tmp_path / "README.md"
    readme.write_text("hello world", encoding="utf-8")

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    reasoning_summary="let me read that file",
                    tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": str(readme)})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    assistant_text="The file says hello world.",
                    final_answer="The file says hello world.",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )
    chunks = list(loop.run_turn_stream(ChatInput(text="read file", cwd=str(tmp_path), project_id="p")))
    progress_deltas = [c for c in chunks if c.kind == "progress_delta"]
    tool_deltas = [c for c in chunks if c.kind == "tool_call_delta"]
    text_deltas = [c for c in chunks if c.kind == "text_delta"]
    done_chunks = [c for c in chunks if c.kind == "done"]

    # First step: text = progress + tool call
    assert len(progress_deltas) >= 1, "Should have progress_delta for tool-intent text in first step"
    assert len(tool_deltas) >= 1, "Should have tool_call_delta for read_file"
    # Final step: text = answer
    assert len(text_deltas) >= 1, "Should have text_delta for final answer"
    assert len(done_chunks) == 1 and done_chunks[0].finish_reason == "stop"
    full_answer = "".join(c.text_delta for c in text_deltas)
    assert "hello world" in full_answer


def test_agent_loop_stream_tool_intent_retry(tmp_path: Path):
    """Streaming path: tool-intent text without tool_calls triggers retry."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                # First response: describes intent but no tool calls
                ModelResponse(
                    assistant_text="让我查看项目结构",
                    final_answer="",
                    finish_reason="retry_with_tool_instruction",
                ),
                # Second response after feedback: calls tool
                ModelResponse(
                    tool_calls=[ToolCall.new(name="repo_reader.list_tree", arguments={"path": str(tmp_path)})],
                    finish_reason="tool_calls",
                ),
                # Third: final answer
                ModelResponse(
                    assistant_text="项目结构包含...",
                    final_answer="项目结构包含...",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )
    chunks = list(loop.run_turn_stream(ChatInput(text="list files", cwd=str(tmp_path), project_id="p")))
    tool_deltas = [c for c in chunks if c.kind == "tool_call_delta"]
    done_chunks = [c for c in chunks if c.kind == "done"]
    assert len(tool_deltas) >= 1, "Should have tool_call_delta after retry"
    assert len(done_chunks) == 1 and done_chunks[0].finish_reason == "stop"


def test_agent_loop_no_false_positive_on_tech_answer(tmp_path: Path):
    """Streaming path: answers mentioning git/python/etc should NOT trigger tool intent."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    assistant_text=(
                        "你可以使用 git status 查看状态，用 python 运行脚本，"
                        "用 pip 安装依赖，用 npm 管理前端包，用 docker 部署服务。"
                    ),
                    final_answer=(
                        "你可以使用 git status 查看状态，用 python 运行脚本，"
                        "用 pip 安装依赖，用 npm 管理前端包，用 docker 部署服务。"
                    ),
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )
    chunks = list(loop.run_turn_stream(ChatInput(text="how to check status?", cwd=str(tmp_path), project_id="p")))
    done_chunks = [c for c in chunks if c.kind == "done"]
    progress_deltas = [c for c in chunks if c.kind == "progress_delta"]
    text_deltas = [c for c in chunks if c.kind == "text_delta"]

    # Should be treated as final answer, not tool intent
    assert len(done_chunks) == 1
    assert done_chunks[0].finish_reason == "stop"
    assert len(progress_deltas) == 0, "Tech terms in answer should not trigger progress_delta"
    full_text = "".join(c.text_delta for c in text_deltas)
    assert "git status" in full_text


def test_agent_loop_stream_length_retry(tmp_path: Path):
    """Streaming path: finish_reason=length triggers compact+retry."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                # First response truncated (length)
                ModelResponse(
                    assistant_text="This is a trunca",
                    final_answer="This is a trunca",
                    finish_reason="length",
                ),
                # After compaction, model gets full response
                ModelResponse(
                    assistant_text="This is the complete response after compaction.",
                    final_answer="This is the complete response after compaction.",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )
    chunks = list(loop.run_turn_stream(ChatInput(text="explain", cwd=str(tmp_path), project_id="p")))
    done_chunks = [c for c in chunks if c.kind == "done"]
    text_deltas = [c for c in chunks if c.kind == "text_delta"]
    assert len(done_chunks) == 1 and done_chunks[0].finish_reason == "stop"
    full_text = "".join(c.text_delta for c in text_deltas)
    assert "complete response" in full_text


def test_agent_loop_non_streaming_clean_gate(tmp_path: Path):
    """Non-streaming path: unclean stop_reason should NOT persist final_answer."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                # Response that will hit max_steps (script exhausted → fallback text)
                ModelResponse(
                    assistant_text="",
                    final_answer="",
                    finish_reason="empty",
                ),
            ]
        ),
        auto_approve=True,
        max_steps=1,
    )
    result = loop.run_turn(ChatInput(text="test", cwd=str(tmp_path), project_id="p"))
    # After max_steps exhausted, final_answer should NOT have been saved
    msgs = loop.store.load_messages(result.session_id, limit=10)
    # Should only have the user message, not an assistant answer
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 0, f"Unclean finish should not persist answer, got {assistant_msgs}"


def test_agent_loop_non_streaming_clean_finish_persists(tmp_path: Path):
    """Non-streaming path: clean stop_reason should persist final_answer."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    assistant_text="All done!",
                    final_answer="All done!",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
    )
    result = loop.run_turn(ChatInput(text="test", cwd=str(tmp_path), project_id="p2"))
    msgs = loop.store.load_messages(result.session_id, limit=10)
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]
    assert len(assistant_msgs) == 1
    assert "All done" in str(assistant_msgs[0].get("content", ""))

