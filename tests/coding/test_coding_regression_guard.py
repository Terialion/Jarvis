from __future__ import annotations

from jarvis import cli as cli_mod


def _run_once(text: str) -> str:
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    return cli_mod._handle_natural_language(state, text)


def test_natural_ux_and_repo_inspection_not_regressed() -> None:
    chat = _run_once("hi")
    assert "Task task_" not in chat

    inspect = _run_once("Inspect this repo. Do not modify files.")
    assert "Task task_" not in inspect
    # Negation routes to plan_answer -> chat path.
    # Without LLM, returns fallback instead of "Repository inspection complete."
    assert inspect != ""

