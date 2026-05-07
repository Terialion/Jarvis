from __future__ import annotations

from unittest.mock import patch

from jarvis import cli as cli_mod


def test_handle_natural_language_delegates_to_agentloop_renderer(monkeypatch):
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    called: list[tuple[str, bool]] = []

    def fake_run_agent_turn(text: str, **kwargs) -> str:
        called.append((text, bool(kwargs.get("interactive"))))
        return "Jarvis\nhandled"

    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", fake_run_agent_turn)
    rendered = cli_mod._handle_natural_language(state, "读取 README.md")

    assert "handled" in rendered
    assert called == [("读取 README.md", True)]


def test_handle_natural_language_keeps_refusal_shape(monkeypatch):
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", lambda *_a, **_k: "Jarvis\n不能直接打印 .env")

    rendered = cli_mod._handle_natural_language(state, "打印我的 .env")
    assert ".env" in rendered
    assert "sk-" not in rendered


def test_handle_natural_language_keeps_clarification_shape(monkeypatch):
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", lambda *_a, **_k: "Jarvis\n你希望我读取哪个文件？")

    rendered = cli_mod._handle_natural_language(state, "帮我弄一下")
    assert "哪个文件" in rendered


def test_handle_natural_language_ignores_legacy_env(monkeypatch):
    state = cli_mod.ShellState(cli_mod.DEFAULT_API_BASE)
    outputs: list[str] = []
    monkeypatch.setenv("JARVIS_CLI_LEGACY_NL", "1")
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg="", *a, **k: outputs.append(str(msg)))
    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", lambda *_a, **_k: "Jarvis\nok")

    rendered = cli_mod._handle_natural_language(state, "读取 README.md")
    assert "ok" in rendered
    assert any("deprecated and ignored" in line for line in outputs)


def test_run_shell_from_text_uses_handle_natural_language_for_non_slash(monkeypatch):
    outputs: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg="", *a, **k: outputs.append(str(msg)))
    monkeypatch.setattr(cli_mod, "_handle_natural_language", lambda *_a, **_k: "Jarvis\ntrace")

    code = cli_mod.run_shell_from_text("读取 README.md\n")
    assert code == 0
    assert any("trace" in line for line in outputs)


def test_run_shell_from_text_slash_help_stays_local(monkeypatch):
    outputs: list[str] = []
    called = {"agent": 0}
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg="", *a, **k: outputs.append(str(msg)))
    monkeypatch.setattr(
        cli_mod,
        "run_agent_turn_for_cli",
        lambda *_a, **_k: called.__setitem__("agent", called["agent"] + 1) or "Jarvis\nunexpected",
    )

    code = cli_mod.run_shell_from_text("/help\n")
    assert code == 0
    assert called["agent"] == 0
    assert any("/help" in line or "Commands" in line for line in outputs)
