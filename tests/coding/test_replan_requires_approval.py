from pathlib import Path

from src.jarvis.core.coding_loop.orchestrator import run_coding_loop


def test_replan_or_coding_write_requires_approval(tmp_path: Path) -> None:
    result = run_coding_loop("fix greeting", tmp_path, auto_approve=False)
    assert result["stop_reason"] == "approval_required"
    assert result["approvals"][0]["status"] == "pending"
    assert not result["changed_files"]
    assert not result["test_results"]

