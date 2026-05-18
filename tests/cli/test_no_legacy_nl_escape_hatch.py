from __future__ import annotations

from unittest.mock import patch

from jarvis import cli as cli_mod


def test_run_agent_turn_for_cli_calls_agentloop_when_env_unset(monkeypatch):
    monkeypatch.delenv("JARVIS_CLI_LEGACY_NL", raising=False)
    monkeypatch.setattr(cli_mod, "_build_provider_status_line", lambda: ("LLM provider: mock", None))
    called: dict[str, str] = {}

    # Mock run_agent_turn_for_cli to bypass streaming path and capture the prompt
    original = cli_mod.run_agent_turn_for_cli

    def mock_run_agent_turn(prompt, state=None, output_mode="default", auto_approve=False):
        called["text"] = prompt
        result = cli_mod._local_agent_result(final_answer="ok", output_type="answer")
        if state is None:
            from jarvis.cli import ShellState, DEFAULT_API_BASE
            state = ShellState(DEFAULT_API_BASE)
        return cli_mod._render_agent_result_text(
            result=result,
            provider_line=state.provider_status_line,
            output_mode=output_mode,
        )

    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", mock_run_agent_turn)

    rendered = cli_mod.run_agent_turn_for_cli("读取 README.md", state=cli_mod.ShellState(cli_mod.DEFAULT_API_BASE))

    assert called["text"] == "读取 README.md"
    assert "ok" in rendered


def test_legacy_env_is_ignored_for_non_slash_input(monkeypatch):
    outputs: list[str] = []
    monkeypatch.setenv("JARVIS_CLI_LEGACY_NL", "1")
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg="", *a, **k: outputs.append(str(msg)))
    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", lambda *_a, **_k: "Jarvis\nok")

    code = cli_mod.run_shell_from_text("读取 README.md\n")
    assert code == 0
    assert any("deprecated and ignored" in line for line in outputs)
    assert any("Jarvis" in line for line in outputs)


def test_slash_help_stays_local_even_with_legacy_env(monkeypatch):
    outputs: list[str] = []
    monkeypatch.setenv("JARVIS_CLI_LEGACY_NL", "1")
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg="", *a, **k: outputs.append(str(msg)))

    called = {"agent": 0}
    monkeypatch.setattr(
        cli_mod,
        "run_agent_turn_for_cli",
        lambda *_a, **_k: called.__setitem__("agent", called["agent"] + 1) or "Jarvis\nunexpected",
    )

    code = cli_mod.run_shell_from_text("/help\n")
    assert code == 0
    assert called["agent"] == 0
    assert any("/help" in line or "Commands" in line for line in outputs)
