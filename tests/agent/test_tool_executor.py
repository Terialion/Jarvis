from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.tools import ToolCallExecutor, ToolRegistryAdapter
from src.jarvis.agent.types import ToolCall


def test_tool_executor_repo_read(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("abc", encoding="utf-8")
    registry = ToolRegistryAdapter(project_root=str(tmp_path))
    executor = ToolCallExecutor(registry_adapter=registry, auto_approve=True)
    result = executor.execute(
        ToolCall.new(name="repo_reader.read_file", arguments={"path": str(f)}),
        context={"cwd": str(tmp_path)},
    )
    assert result.ok is True


def test_tool_executor_sensitive_read_blocked(tmp_path: Path):
    registry = ToolRegistryAdapter(project_root=str(tmp_path))
    executor = ToolCallExecutor(registry_adapter=registry, auto_approve=True)
    result = executor.execute(
        ToolCall.new(name="repo_reader.read_file", arguments={"path": str(tmp_path / ".env")}),
        context={"cwd": str(tmp_path)},
    )
    assert result.ok is False
    assert "safety" in str(result.error).lower() or "not found" in str(result.error).lower()

