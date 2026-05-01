from __future__ import annotations

from pathlib import Path

from src.jarvis.core.coding_loop.scoped_tests import run_scoped_fixture_tests


def test_scoped_test_command_targets_fixture(tmp_path: Path) -> None:
    workspace = tmp_path
    fixture = workspace / "examples" / "coding_fixture"
    tests_dir = fixture / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (workspace / "examples" / "__init__.py").write_text("", encoding="utf-8")
    (fixture / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (fixture / "greeting.py").write_text('def greeting(name: str) -> str:\n    return f"Hello, {name}!"\n', encoding="utf-8")
    (tests_dir / "test_greeting.py").write_text(
        "from examples.coding_fixture.greeting import greeting\n\n"
        "def test_greeting():\n"
        '    assert greeting("Jarvis") == "Hello, Jarvis!"\n',
        encoding="utf-8",
    )

    result = run_scoped_fixture_tests(workspace)
    assert "examples/coding_fixture/tests" in str(result["command"])
    assert result["test_scope"] == "fixture"
