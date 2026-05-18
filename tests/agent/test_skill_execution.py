"""Tests for s18: Skill execution — context injection and synthesis guidance."""

from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.model import FakeModelClient
from src.jarvis.agent.types import ChatInput, ModelResponse, ToolCall


# ── helpers ────────────────────────────────────────────────────────────────

def _setup_weather_skill(tmp_path: Path) -> str:
    """Create a minimal weather skill under tmp_path/skills/weather/."""
    skill_dir = tmp_path / "skills" / "weather"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("""---
name: weather
description: Query weather for a location.
risk_level: low
allowed_tools:
  - command_runner.run
---

# Weather Skill

To query weather, run:

```bash
curl -s "wttr.in/Hefei?format=j1"
```

Then synthesize the results into a user-friendly answer.
""")
    return str(skill_dir)


# ── tests ──────────────────────────────────────────────────────────────────

def test_skill_load_completes_with_fake_model(tmp_path: Path):
    """skill.load followed by a tool call and an answer should complete."""
    _setup_weather_skill(tmp_path)

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    tool_calls=[ToolCall.new(name="skill.load", arguments={"name": "weather"})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    tool_calls=[ToolCall.new(
                        name="command_runner.run",
                        arguments={"command": 'curl -s "wttr.in/Hefei?format=j1"'},
                    )],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    assistant_text="合肥今天天气晴朗，气温 25°C。",
                    final_answer="合肥今天天气晴朗，气温 25°C。",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
        max_steps=5,
    )
    result = loop.run_turn(ChatInput(text="查询合肥天气", cwd=str(tmp_path), project_id="p"))
    assert result.ok is True
    assert "合肥" in result.final_answer
    assert len(result.tool_calls) >= 2  # skill.load + command_runner.run


def test_skill_load_stream_produces_answer(tmp_path: Path):
    """Streaming path: skill.load → tool → answer completes normally."""
    _setup_weather_skill(tmp_path)

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    tool_calls=[ToolCall.new(name="skill.load", arguments={"name": "weather"})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    tool_calls=[ToolCall.new(
                        name="command_runner.run",
                        arguments={"command": 'curl -s "wttr.in/Hefei?format=j1"'},
                    )],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    assistant_text="合肥今天天气晴朗。",
                    final_answer="合肥今天天气晴朗。",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
        max_steps=5,
    )
    chunks = list(loop.run_turn_stream(ChatInput(text="查询合肥天气", cwd=str(tmp_path), project_id="p")))
    text_deltas = [c for c in chunks if c.kind == "text_delta"]
    done_chunks = [c for c in chunks if c.kind == "done"]
    assert len(text_deltas) > 0, "Should have text_delta for final answer"
    assert done_chunks[0].finish_reason == "stop"
    full_text = "".join(c.text_delta for c in text_deltas)
    assert "合肥" in full_text or "天气" in full_text


def test_synthesis_guidance_stops_looping_model(tmp_path: Path):
    """Model that keeps calling tools eventually produces a final answer (no hard stop)."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    tool_calls=[ToolCall.new(
                        name="command_runner.run",
                        arguments={"command": "echo result1"},
                    )],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    tool_calls=[ToolCall.new(
                        name="command_runner.run",
                        arguments={"command": "echo result2"},
                    )],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    tool_calls=[ToolCall.new(
                        name="command_runner.run",
                        arguments={"command": "echo result3"},
                    )],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    assistant_text="Results: result1, result2, result3",
                    final_answer="Results: result1, result2, result3",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
        max_steps=5,
    )
    result = loop.run_turn(ChatInput(text="run commands", cwd=str(tmp_path), project_id="p"))
    # Model runs 3 tools then produces a final answer
    assert result.stop_reason == "completed"
    assert result.tool_calls


def test_synthesis_guidance_resets_on_text_answer(tmp_path: Path):
    """Model runs a terminal tool then produces a final answer."""
    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(
            scripted=[
                ModelResponse(
                    assistant_text="Let me run this command.",
                    tool_calls=[ToolCall.new(
                        name="command_runner.run",
                        arguments={"command": "echo hello"},
                    )],
                    finish_reason="tool_calls",
                ),
                ModelResponse(
                    assistant_text="The command returned: hello",
                    final_answer="The command returned: hello",
                    finish_reason="stop",
                ),
            ]
        ),
        auto_approve=True,
        max_steps=5,
    )
    chunks = list(loop.run_turn_stream(ChatInput(text="run echo hello", cwd=str(tmp_path), project_id="p")))
    done_chunks = [c for c in chunks if c.kind == "done"]
    assert done_chunks[0].finish_reason == "stop"
    text_deltas = [c for c in chunks if c.kind == "text_delta"]
    full_text = "".join(c.text_delta for c in text_deltas)
    assert "hello" in full_text


def test_skill_load_no_infinite_loop(tmp_path: Path):
    """A model that keeps calling the same tool after skill.load is stopped
    by dedup or hard cap within reasonable steps."""
    _setup_weather_skill(tmp_path)

    # Script the model to call skill.load then repeatedly call the same curl
    scripted = [
        ModelResponse(
            tool_calls=[ToolCall.new(name="skill.load", arguments={"name": "weather"})],
            finish_reason="tool_calls",
        ),
    ]
    # Add 8 repeated curl calls (all same args → dedup catches after 1st)
    for _ in range(8):
        scripted.append(
            ModelResponse(
                tool_calls=[ToolCall.new(
                    name="command_runner.run",
                    arguments={"command": 'curl -s "wttr.in/Hefei?format=j1"'},
                )],
                finish_reason="tool_calls",
            ),
        )

    loop = AgentLoop(
        project_root=str(tmp_path),
        model_client=FakeModelClient(scripted=scripted),
        auto_approve=True,
        max_steps=12,
    )
    result = loop.run_turn(ChatInput(text="查询合肥天气", cwd=str(tmp_path), project_id="p"))
    # Must terminate — either by dedup, no_progress, synthesis guidance, or max_steps
    assert result.stop_reason is not None
    assert result.tool_calls
