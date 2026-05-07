from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.context import ContextBuilder
from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.tools import ToolCallExecutor, ToolRegistryAdapter
from src.jarvis.agent.types import ChatInput
from src.jarvis.skills.executor import SkillExecutor
from src.jarvis.skills.runtime import SkillCall, SkillResult


def _turn_context(tmp_path: Path, text: str):
    store = ThreadStore(root=tmp_path / "threads")
    session = store.create_or_resume_session(ChatInput(text=text, cwd=str(tmp_path), project_id="p", session_id="s"))
    turn = store.create_turn(session["session_id"])
    registry = ToolRegistryAdapter(project_root=str(tmp_path))
    return ContextBuilder(thread_store=store, skill_registry=registry.skill_registry).build(
        session_id=session["session_id"],
        turn_id=turn.turn_id,
        chat_input=ChatInput(text=text, cwd=str(tmp_path), project_id="p", session_id=session["session_id"]),
        runtime_state={},
    )


def test_summarize_file_skill_executes_through_tool_executor(tmp_path: Path):
    (tmp_path / "README.md").write_text("# Demo\n\nJarvis demo project.", encoding="utf-8")
    registry = ToolRegistryAdapter(project_root=str(tmp_path))
    executor = SkillExecutor(
        skill_registry=registry.skill_registry,
        tool_executor=ToolCallExecutor(registry_adapter=registry, auto_approve=True),
        project_root=str(tmp_path),
    )

    result = executor.run(
        SkillCall.new(name="summarize_file", arguments={"path": "README.md"}, source="deterministic"),
        _turn_context(tmp_path, "总结 README.md"),
    )

    assert result.ok is True
    assert result.skill_name == "summarize_file"
    assert result.related_files == ["README.md"]
    assert any(call.get("name") == "repo_reader.read_file" for call in result.tool_calls)
    assert {"skill_call_started", "skill_step_started", "tool_call_started", "skill_call_completed"}.issubset(
        {event.type for event in result.events}
    )


def test_allowed_tools_runtime_denies_disallowed_tool(tmp_path: Path):
    class RecordingToolExecutor:
        called = False

        def execute(self, *args, **kwargs):  # pragma: no cover - should be denied before execution
            self.called = True
            raise AssertionError("disallowed tool should not execute")

    registry = ToolRegistryAdapter(project_root=str(tmp_path))
    recording_executor = RecordingToolExecutor()
    executor = SkillExecutor(
        skill_registry=registry.skill_registry,
        tool_executor=recording_executor,
        project_root=str(tmp_path),
    )

    def malicious_handler(ctx):
        step, denied, _call = executor._execute_tool(
            ctx,
            "bad_command",
            "Attempt command from read-only skill",
            "command_runner.run",
            {"command": "echo nope"},
        )
        return SkillResult(
            ok=False,
            skill_name=ctx.skill_spec.name,
            final_answer="Denied.",
            output_type="partial",
            steps=[step],
            tool_results=[denied.to_dict()],
            events=list(ctx.events),
            risks=["tool_not_allowed_by_skill"],
        )

    executor._handlers["summarize_file"] = malicious_handler
    result = executor.run(
        SkillCall.new(name="summarize_file", arguments={"path": "README.md"}, source="deterministic"),
        _turn_context(tmp_path, "总结 README.md"),
    )

    assert recording_executor.called is False
    assert "tool_not_allowed_by_skill" in result.risks
    assert "skill_tool_denied" in {event.type for event in result.events}


def test_secret_file_refused_before_read(tmp_path: Path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-secret", encoding="utf-8")
    registry = ToolRegistryAdapter(project_root=str(tmp_path))
    executor = SkillExecutor(
        skill_registry=registry.skill_registry,
        tool_executor=ToolCallExecutor(registry_adapter=registry, auto_approve=True),
        project_root=str(tmp_path),
    )

    result = executor.run(
        SkillCall.new(name="summarize_file", arguments={"path": ".env"}, source="deterministic"),
        _turn_context(tmp_path, "总结 .env"),
    )

    assert result.output_type == "refusal"
    assert "secret_file_refused" in result.risks
    assert not any(call.get("name") == "repo_reader.read_file" for call in result.tool_calls)
    assert "sk-secret" not in result.final_answer
