from __future__ import annotations

from unittest.mock import patch

from jarvis import cli as cli_mod


def test_run_agent_turn_for_cli_calls_agentloop_when_env_unset(monkeypatch):
    monkeypatch.delenv("JARVIS_CLI_LEGACY_NL", raising=False)
    monkeypatch.setattr(cli_mod, "_quick_agent_result_for_cli", lambda *_a, **_k: None)

    called: dict[str, str] = {}

    def fake_init(self, *args, **kwargs):
        return None

    def fake_run_turn(self, chat_input):
        called["text"] = chat_input.text
        return cli_mod._local_agent_result(final_answer="ok", output_type="answer")

    with patch("src.jarvis.agent.loop.AgentLoop.__init__", fake_init), patch(
        "src.jarvis.agent.loop.AgentLoop.run_turn",
        fake_run_turn,
    ):
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
