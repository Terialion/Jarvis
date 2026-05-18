from __future__ import annotations

from unittest.mock import MagicMock

from src.jarvis.skills.executor import SkillExecutor
from src.jarvis.skills.schema import SkillSpec


def test_skill_executor_run_returns_structured_result():
    mock_registry = MagicMock()
    mock_registry.get.return_value = SkillSpec(
        name="summarize_file",
        description="Summarize a file",
        path="/tmp/summarize_file",
        source="local",
        source_format="markdown",
        skill_type="executable",
    )
    mock_registry.get_runnable.return_value = MagicMock()

    executor = SkillExecutor(
        skill_registry=mock_registry,
        tool_executor=None,
        project_root=".",
    )

    from src.jarvis.skills.runtime import SkillCall

    mock_ctx = MagicMock()
    mock_ctx.permission_mode = "workspace_write"

    result = executor.run(
        SkillCall.new(name="summarize_file", arguments={"path": "README.md"}, source="cli"),
        turn_context=mock_ctx,
    )

    assert hasattr(result, "ok")
    assert hasattr(result, "final_answer")
    assert hasattr(result, "skill_name")


def test_skill_executor_handles_unknown_skill():
    mock_registry = MagicMock()
    mock_registry.get.side_effect = KeyError("not found")

    executor = SkillExecutor(
        skill_registry=mock_registry,
        tool_executor=None,
        project_root=".",
    )

    from src.jarvis.skills.runtime import SkillCall

    mock_ctx = MagicMock()
    mock_ctx.permission_mode = "workspace_write"

    result = executor.run(
        SkillCall.new(name="nonexistent_skill", arguments={}, source="cli"),
        turn_context=mock_ctx,
    )

    assert not result.ok
