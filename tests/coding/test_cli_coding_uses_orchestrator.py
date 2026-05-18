from jarvis import cli as cli_mod


def test_cli_coding_task_uses_orchestrator(monkeypatch) -> None:
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    output = cli_mod._handle_natural_language(state, "fix this bug and run tests")
    # Coding verb -> AgentLoop path.
    # Verify it was routed as work (not a simple chat answer).
    assert ("[WORK]" in output
            or "Agent tool loop" in output
            or "Approval required" in output
            or "task_" in output)
    assert "Completed in safe mode" not in output

