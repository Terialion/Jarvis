from __future__ import annotations

from jarvis import cli as cli_mod


def test_interactive_non_slash_calls_agent_loop(monkeypatch):
    outputs: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg="", *a, **k: outputs.append(str(msg)))

    called = {"handler": 0}
    monkeypatch.setattr(cli_mod, "_handle_natural_language", lambda *_a, **_k: called.__setitem__("handler", called["handler"] + 1) or "Jarvis\nok")

    code = cli_mod.run_shell_from_text("下午好\n")
    assert code == 0
    assert called["handler"] == 1
    assert any("Jarvis" in line for line in outputs)


def test_interactive_slash_help_does_not_call_agent_loop(monkeypatch):
    outputs: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg="", *a, **k: outputs.append(str(msg)))

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
    monkeypatch.setattr(cli_mod, "_handle_natural_language", lambda *_a, **_k: "Jarvis\nok")

    code = cli_mod.run_shell_from_text("列一下当前目录\n")
    assert code == 0
    assert any("Jarvis" in line for line in outputs)
