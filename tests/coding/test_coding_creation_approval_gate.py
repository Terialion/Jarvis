from pathlib import Path

from src.jarvis.core.coding_loop.orchestrator import run_coding_loop


def test_coding_creation_requires_approval_before_file_write(tmp_path: Path) -> None:
    target = tmp_path / "hello.py"
    assert not target.exists()
    result = run_coding_loop(
        "Create a hello.py file that prints hello world.",
        tmp_path,
        max_rounds=1,
        auto_approve=False,
    )
    assert result["stop_reason"] == "approval_required"
    assert not target.exists()
