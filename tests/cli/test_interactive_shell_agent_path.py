from __future__ import annotations

from jarvis import cli as cli_mod


def test_interactive_non_slash_calls_agent_loop(monkeypatch):
    outputs: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg="", *a, **k: outputs.append(str(msg)))
    monkeypatch.setenv("JARVIS_CLI_LEGACY_NL", "0")

    called = {"agent": 0, "legacy": 0}
    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", lambda text, **_: called.__setitem__("agent", called["agent"] + 1) or "Jarvis\nok")
    monkeypatch.setattr(cli_mod, "_handle_natural_language", lambda *_a, **_k: called.__setitem__("legacy", called["legacy"] + 1) or "legacy")

    code = cli_mod.run_shell_from_text("下午好\n")
    assert code == 0
    assert called["agent"] == 1
    assert called["legacy"] == 0
    assert any("Jarvis" in line for line in outputs)


def test_interactive_slash_help_does_not_call_agent_loop(monkeypatch):
    outputs: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg="", *a, **k: outputs.append(str(msg)))
    monkeypatch.setenv("JARVIS_CLI_LEGACY_NL", "0")

    called = {"agent": 0}
    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", lambda *_a, **_k: called.__setitem__("agent", called["agent"] + 1) or "Jarvis\nok")

    code = cli_mod.run_shell_from_text("/help\n")
    assert code == 0
    assert called["agent"] == 0
    merged = "\n".join(outputs)
    assert "Commands" in merged or "/help" in merged


def test_interactive_unknown_slash_does_not_call_agent_loop(monkeypatch):
    outputs: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg="", *a, **k: outputs.append(str(msg)))
    monkeypatch.setenv("JARVIS_CLI_LEGACY_NL", "0")

    called = {"agent": 0}
    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", lambda *_a, **_k: called.__setitem__("agent", called["agent"] + 1) or "Jarvis\nok")

    code = cli_mod.run_shell_from_text("/hlep\n")
    assert code == 0
    assert called["agent"] == 0
    merged = "\n".join(outputs)
    assert "Unknown command" in merged
    assert "Did you mean" in merged


def test_interactive_non_slash_does_not_call_legacy_dispatcher_by_default(monkeypatch):
    outputs: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg="", *a, **k: outputs.append(str(msg)))
    monkeypatch.setenv("JARVIS_CLI_LEGACY_NL", "0")

    def _legacy_fail(*_a, **_k):
        raise AssertionError("legacy dispatcher should not be called")

    monkeypatch.setattr(cli_mod, "_handle_natural_language", _legacy_fail)
    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", lambda *_a, **_k: "Jarvis\nok")

    code = cli_mod.run_shell_from_text("列一下当前目录\n")
    assert code == 0
    assert any("Jarvis" in line for line in outputs)
