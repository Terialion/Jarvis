from __future__ import annotations

from jarvis import cli as cli_mod


def test_shell_fix_returns_approval_required_result():
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    output = cli_mod._shell_fix(state, [])

    assert "Usage:" in output
    assert "coding_fixture" in output or "cli_surface" in output


def test_shell_review_uses_coding_workflow():
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    output = cli_mod._shell_review(state)

    assert "Review" in output
    assert "Changed files" in output
