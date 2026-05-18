from jarvis import cli as cli_mod


def test_cli_coding_creation_uses_agent_tool_loop(monkeypatch) -> None:
    monkeypatch.setattr(cli_mod, "_build_provider_status_line", lambda: ("LLM provider: mock", None))
    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", lambda *a, **kw: "Mock agent response")
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    output = cli_mod._handle_natural_language(state, "在这个工作空间写一个python程序，打印helloworld。")
    assert output != ""
    assert "我需要再确认一下" not in output
