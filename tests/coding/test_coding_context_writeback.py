from __future__ import annotations

import shutil
from pathlib import Path

from src.jarvis.coding.workflow import CodingWorkflow
from src.jarvis.store import ThreadStore


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "benchmarks" / "suites" / "coding" / "fixtures" / "calculator_bug"


def test_coding-workflow_writes_thread_observation_and_active_task(tmp_path):
    workspace = tmp_path / "calculator_bug"
    shutil.copytree(FIXTURE, workspace)
    store = ThreadStore(sessions_dir=tmp_path / "jarvis.db")
    workflow = CodingWorkflow(
        project_root=workspace,
        auto_approve=True,
        session_store=store,
        session_id="coding_thread",
        turn_id="turn_ctx_001",
    )

    result = workflow.fix("Fix calculator bug", apply=True, run_tests_after=True)

    assert result.status == "completed"
    observations = store.get_skill_observations("coding_thread", limit=5)
    assert observations
    assert observations[0].skill_name == "coding-workflow"
    active_task = store.get_active_task("coding_thread")
    handoff = store.get_handoff_summary("coding_thread")
    assert active_task is not None
    assert handoff is not None
