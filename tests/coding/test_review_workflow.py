from __future__ import annotations

import shutil
from pathlib import Path

from src.jarvis.coding.workflow import CodingWorkflow


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmarks" / "suites" / "coding" / "fixtures" / "calculator_bug"


def test_review_finds_issue_without_writing(tmp_path):
    workspace = tmp_path / "calculator_bug"
    shutil.copytree(FIXTURE, workspace)
    original = (workspace / "src" / "calculator.py").read_text(encoding="utf-8")

    workflow = CodingWorkflow(project_root=workspace, auto_approve=False, session_id="test_review")
    result = workflow.review(".")

    assert result.status == "completed"
    assert result.issues
    assert any("subtracts instead of adding" in issue.summary for issue in result.issues)
    assert result.tool_calls
    assert (workspace / "src" / "calculator.py").read_text(encoding="utf-8") == original
