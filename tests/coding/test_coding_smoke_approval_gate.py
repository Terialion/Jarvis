from __future__ import annotations

from pathlib import Path

from src.jarvis.core.coding_loop.loop import run_coding_loop_for_fixture


def _prepare_fixture(workspace: Path) -> Path:
    fixture = workspace / "examples" / "coding_fixture"
    tests_dir = fixture / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (workspace / "examples" / "__init__.py").write_text("", encoding="utf-8")
    (fixture / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    target = fixture / "greeting.py"
    target.write_text('def greeting(name: str) -> str:\n    return f"Hello, {name}"\n', encoding="utf-8")
    (tests_dir / "test_greeting.py").write_text(
        "from examples.coding_fixture.greeting import greeting\n\n"
        "def test_greeting():\n"
        '    assert greeting("Jarvis") == "Hello, Jarvis!"\n',
        encoding="utf-8",
    )
    return target


def test_approval_denied_blocks_before_write_or_shell(tmp_path: Path) -> None:
    target = _prepare_fixture(tmp_path)
    before = target.read_text(encoding="utf-8")

    result = run_coding_loop_for_fixture(
        workspace_root=tmp_path,
        task_id="deny_case",
        user_goal="fix greeting",
        auto_approve=False,
        max_rounds=2,
    )

    after = target.read_text(encoding="utf-8")
    assert before == after
    assert result["stop_reason"] == "approval_denied"
    assert not result["test_results"]
