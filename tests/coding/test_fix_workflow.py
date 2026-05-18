from __future__ import annotations

import shutil
from pathlib import Path

from src.jarvis.coding.workflow import CodingWorkflow
from src.jarvis.core.policy import get_approval_store


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmarks" / "suites" / "coding" / "fixtures" / "calculator_bug"


def test_fix_requires_approval_before_apply(tmp_path):
    get_approval_store().reset()
    workspace = tmp_path / "calculator_bug"
    shutil.copytree(FIXTURE, workspace)
    source_file = workspace / "src" / "calculator.py"
    original = source_file.read_text(encoding="utf-8")

    workflow = CodingWorkflow(project_root=workspace, auto_approve=False, session_id="test_fix")
    result = workflow.fix("Fix calculator bug", apply=True, run_tests_after=False)

    assert result.status == "approval_required"
    assert result.patch_plan is not None
    assert result.diff_preview is not None
    assert result.patch_apply_result is not None
    assert result.patch_apply_result.applied is False
    assert result.patch_apply_result.approval_id
    assert source_file.read_text(encoding="utf-8") == original


def test_fix_applies_after_approval_and_runs_tests(tmp_path):
    get_approval_store().reset()
    workspace = tmp_path / "calculator_bug"
    shutil.copytree(FIXTURE, workspace)

    workflow = CodingWorkflow(project_root=workspace, auto_approve=True, session_id="test_fix_apply")
    result = workflow.fix("Fix calculator bug", apply=True, run_tests_after=True)

    assert result.status == "completed"
    assert result.patch_apply_result is not None
    assert result.patch_apply_result.applied is True
    assert result.test_results
    assert result.test_results[0].passed is True
