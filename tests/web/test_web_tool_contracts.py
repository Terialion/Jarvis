from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.tools import ToolCallExecutor, ToolRegistryAdapter
from src.jarvis.agent.types import ToolCall


def test_web_tools_are_registered_and_execute_with_structured_results(tmp_path: Path):
    registry = ToolRegistryAdapter(project_root=str(tmp_path))
    executor = ToolCallExecutor(registry_adapter=registry, auto_approve=True)
    specs = {spec.name for spec in registry.list_tool_specs()}

    assert "web.search" in specs
    assert "web.fetch" in specs

    search = executor.execute(
        ToolCall.new(name="web.search", arguments={"query": "Flink CDC CAST STRING bug", "provider": "auto"}),
        context={"cwd": str(tmp_path), "session_id": "s", "turn_id": "t"},
    )
    fetch = executor.execute(
        ToolCall.new(name="web.fetch", arguments={"url": "https://nightlies.apache.org/flink/flink-cdc-docs-master/docs/connectors/pipeline-transforms/"}),
        context={"cwd": str(tmp_path), "session_id": "s", "turn_id": "t"},
    )

    assert search.ok is True
    assert isinstance(search.content, dict)
    assert "results" in search.content
    assert fetch.ok is True
    assert isinstance(fetch.content, dict)
    assert fetch.content["documents"][0]["is_untrusted"] is True
