from __future__ import annotations

from pathlib import Path

from src.jarvis.core.coding_loop.loop import run_coding_loop_for_fixture


def _prepare_fixture(workspace: Path) -> None:
    fixture = workspace / "examples" / "coding_fixture"
    tests_dir = fixture / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (workspace / "examples" / "__init__.py").write_text("", encoding="utf-8")
    (fixture / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (fixture / "greeting.py").write_text('def greeting(name: str) -> str:\n    return f"Hello, {name}"\n', encoding="utf-8")
    (tests_dir / "test_greeting.py").write_text(
        "from examples.coding_fixture.greeting import greeting\n\n"
        "def test_greeting():\n"
        '    assert greeting("Jarvis") == "Hello, Jarvis!"\n',
        encoding="utf-8",
    )


def test_coding_fixture_success_first_try(tmp_path: Path) -> None:
    _prepare_fixture(tmp_path)
    result = run_coding_loop_for_fixture(
        workspace_root=tmp_path,
        task_id="success_case",
        user_goal="fix greeting",
        max_rounds=3,
        auto_approve=True,
        force_first_failure=False,
    )
    assert result["stop_reason"] == "done"
    assert result["rounds"] == 1
    assert result["test_results"][-1]["passed"] is True


def test_coding_fixture_rethink_path(tmp_path: Path) -> None:
    _prepare_fixture(tmp_path)
    result = run_coding_loop_for_fixture(
        workspace_root=tmp_path,
        task_id="rethink_case",
        user_goal="fix greeting",
        max_rounds=3,
        auto_approve=True,
        force_first_failure=True,
    )
    assert result["rounds"] >= 2
    assert result["rethink_records"]
    assert result["stop_reason"] in {"done", "max_rounds"}
