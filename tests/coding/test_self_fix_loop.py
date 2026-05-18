from __future__ import annotations

import shutil
from pathlib import Path

from src.jarvis.coding.schema import CodingWorkflowResult, TestRunResult
from src.jarvis.coding.workflow import CodingWorkflow


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmarks" / "suites" / "coding" / "fixtures" / "calculator_bug"


def test_self_fix_loop_records_bounded_attempt(monkeypatch, tmp_path):
    workspace = tmp_path / "calculator_bug"
    shutil.copytree(FIXTURE, workspace)
    workflow = CodingWorkflow(project_root=workspace, auto_approve=True, session_id="test_self_fix")

    def _failing_run_tests(command=None):
        return CodingWorkflowResult(
            task_id="child_test",
            status="failed",
            test_results=[
                TestRunResult(
                    command=str(command or "pytest"),
                    passed=False,
                    exit_code=1,
                    stdout_redacted="",
                    stderr_redacted="failure",
                )
            ],
            summary="Tests failed.",
        )

    monkeypatch.setattr(workflow, "run_tests", _failing_run_tests)
    result = workflow.fix("Fix calculator bug", apply=True, run_tests_after=True)
    agent = workflow.to_agent_result(result).to_dict()
    machine = dict((agent.get("summary") or {}).get("machine") or {})

    assert machine["self_fix_attempted"] is True
    assert machine["self_fix_iterations"] <= workflow.max_fix_iterations
    assert machine["self_fix_succeeded"] is False
