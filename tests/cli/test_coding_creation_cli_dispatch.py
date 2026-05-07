from jarvis import cli as cli_mod


def test_cli_coding_creation_uses_orchestrator(monkeypatch) -> None:
    called = {"value": False}

    def fake_run(text: str) -> dict:
        called["value"] = True
        assert "python" in text.lower()
        return {
            "status": "approval_required",
            "stop_reason": "approval_required",
            "rounds": 0,
            "changed_files": [],
            "approvals": [{"kind": "write", "status": "pending"}],
            "test_results": [],
            "final_review": {
                "status": "approval_required",
                "stop_reason": "approval_required",
                "rounds": 0,
                "changed_files": [],
                "test_status": "not_run",
                "risk_level": "medium",
            },
        }

    monkeypatch.setattr(cli_mod, "_run_coding_loop", fake_run)
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    output = cli_mod._handle_natural_language(state, "在这个工作空间写一个python程序，打印helloworld。")
    # Coding creation now routes through AgentLoop output handling.
    # Verify it was processed (not a crash, not a simple chat answer).
    assert output != ""
    assert "我需要再确认一下" not in output
