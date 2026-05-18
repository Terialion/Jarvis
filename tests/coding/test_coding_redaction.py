from __future__ import annotations

from src.jarvis.coding.workflow import CodingWorkflow


def test_coding-workflow_redacts_secret_like_values():
    workflow = CodingWorkflow(project_root=".", auto_approve=False, session_id="test_redaction")
    result = workflow.run_tests("python -m pytest tests/cli/test_core_coding_test_command.py -q OPENAI_API_KEY=sk-secret")
    payload = workflow.to_agent_result(result).to_dict()
    dumped = str(payload)

    assert "sk-secret" not in dumped
    assert "OPENAI_API_KEY" in dumped
