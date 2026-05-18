from __future__ import annotations

from src.jarvis.coding.workflow import CodingWorkflow


def test_test_workflow_uses_tool_executor_and_redacts_command():
    workflow = CodingWorkflow(project_root=".", auto_approve=False, session_id="test_run")
    result = workflow.run_tests("python -m pytest tests/cli/test_core_coding_test_command.py -q OPENAI_API_KEY=sk-secret")
    agent = workflow.to_agent_result(result).to_dict()

    assert result.tool_calls
    assert result.tool_calls[0]["name"] == "test_runner.run_test"
    assert "sk-secret" not in str(agent)
    assert "OPENAI_API_KEY" in str(agent)
