from __future__ import annotations

import json
from argparse import Namespace
from types import SimpleNamespace

from jarvis import cli as cli_mod


def _fake_result() -> SimpleNamespace:
    return SimpleNamespace(
        ok=True,
        final_answer="Done. token=abc123 sk-live-secret",
        stop_reason="completed",
        status="completed",
        output_type="answer",
        tool_calls=[
            {"name": "repo_reader.search_files", "arguments": {"path": ".", "pattern": "README"}},
        ],
        events=[
            {"type": "model_call_started", "payload": {"step": 1}},
            {"type": "tool_call_completed", "payload": {"ok": True}},
        ],
        summary={
            "machine": {
                "outcome": "completed",
                "tools_used": ["repo_reader.search_files"],
                "commands_run": [],
                "tests_run": [],
                "risks": ["sensitive_env_requested"],
            }
        },
    )


def _install_dummy_loop(monkeypatch, result=None):
    """Mock AgentLoop + run_agent_turn_for_cli to bypass streaming path.

    Streaming renders directly to stdout via Rich and returns "", but tests
    capture _safe_print. This mock forces the non-streaming render path so
    _safe_print capture sees the rendered output.
    """
    _result = result if result is not None else _fake_result()

    class _DummyLoop:
        def __init__(self, *args, **kwargs):
            pass

        def run_turn(self, chat_input):
            return _result

    monkeypatch.setattr("jarvis.agent.loop.AgentLoop", _DummyLoop)

    from jarvis.agent.types import ChatInput

    def _mock_run_agent_turn(prompt, state=None, output_mode="default", auto_approve=False):
        if state is None:
            from jarvis.cli import ShellState, DEFAULT_API_BASE
            state = ShellState(DEFAULT_API_BASE)
        loop = _DummyLoop()
        result = loop.run_turn(
            ChatInput(text=prompt, cwd=".", session_id="test",
                      metadata={"source": "jarvis.cli", "mode": "default"})
        )
        return cli_mod._render_agent_result_text(
            result=result,
            provider_line=state.provider_status_line,
            output_mode=output_mode,
        )

    monkeypatch.setattr(cli_mod, "run_agent_turn_for_cli", _mock_run_agent_turn)


def test_default_mode_renders_answer_and_tool_summary(monkeypatch):
    _install_dummy_loop(monkeypatch)
    monkeypatch.setattr(cli_mod, "_build_provider_status_line", lambda: ("LLM provider: fake status=available", object()))
    lines: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg, *a, **k: lines.append(str(msg)))
    code = cli_mod._run_non_interactive_with_mode("list files", output_mode="default")
    out = "\n".join(lines)
    assert code == 0
    # Default mode: final answer (masked) + tool summary, no provider/status lines
    assert "LLM provider:" not in out
    assert "Status:" not in out
    assert "Stop reason:" not in out
    assert "token=****" in out
    assert "sk-****" in out
    # Tool name displayed via _TOOL_DISPLAY mapping (repo_reader.search_files → Grep)
    assert "Grep" in out or "repo_reader" in out


def test_quiet_mode_only_prints_final_answer(monkeypatch):
    _install_dummy_loop(monkeypatch)
    monkeypatch.setattr(cli_mod, "_build_provider_status_line", lambda: ("LLM provider: fake status=available", object()))
    lines: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg, *a, **k: lines.append(str(msg)))
    code = cli_mod._run_non_interactive_with_mode("list files", output_mode="quiet")
    out = "\n".join(lines).strip()
    assert code == 0
    assert "LLM provider:" not in out
    assert out.startswith("Done.")


def test_verbose_and_trace_modes_include_summary_and_events(monkeypatch):
    _install_dummy_loop(monkeypatch)
    monkeypatch.setattr(cli_mod, "_build_provider_status_line", lambda: ("LLM provider: fake status=available", object()))
    lines_v: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg, *a, **k: lines_v.append(str(msg)))

    code_v = cli_mod._run_non_interactive_with_mode("list files", output_mode="verbose")
    out_v = "\n".join(lines_v)
    assert code_v == 0
    assert "LLM provider: fake status=available" in out_v
    # Rich Table renders "Status" and "completed" in separate columns
    assert "Status" in out_v
    assert "completed" in out_v
    assert "Stop reason" in out_v
    assert "Runtime Info" in out_v or "Summary" in out_v

    lines_t: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg, *a, **k: lines_t.append(str(msg)))
    code_t = cli_mod._run_non_interactive_with_mode("list files", output_mode="trace")
    out_t = "\n".join(lines_t)
    assert code_t == 0
    assert "Trace" in out_t
    assert "model_call_started" in out_t


def test_json_mode_outputs_machine_readable_contract(monkeypatch):
    _install_dummy_loop(monkeypatch)
    monkeypatch.setattr(cli_mod, "_build_provider_status_line", lambda: ("LLM provider: fake status=available", object()))
    lines: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg, *a, **k: lines.append(str(msg)))
    code = cli_mod._run_non_interactive_with_mode("list files", output_mode="json")
    out = "\n".join(lines)
    assert code == 0
    payload = json.loads(out)
    assert payload["result"]["stop_reason"] == "completed"
    assert payload["result"]["tool_calls_count"] == 1
    assert payload["result"]["final_answer"].startswith("Done.")


def test_output_aliases_trace_and_json():
    assert cli_mod._resolve_output_mode(Namespace(output_mode="default", quiet=False, verbose=False, trace_output=False, json_output=False, trace=True, json=False)) == "trace"
    assert cli_mod._resolve_output_mode(Namespace(output_mode="default", quiet=False, verbose=False, trace_output=False, json_output=False, trace=False, json=True)) == "json"


def test_default_shows_stop_reason_on_failure(monkeypatch):
    failure_result = SimpleNamespace(
        ok=False,
        final_answer="",
        stop_reason="timeout",
        status="failed",
        output_type="error",
        tool_calls=[],
        events=[],
        summary={"machine": {"outcome": "failed", "tools_used": [], "risks": []}},
    )
    _install_dummy_loop(monkeypatch, result=failure_result)
    monkeypatch.setattr(cli_mod, "_build_provider_status_line", lambda: ("LLM provider: fake status=available", object()))
    lines: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg, *a, **k: lines.append(str(msg)))
    code = cli_mod._run_non_interactive_with_mode("list files", output_mode="verbose")
    out = "\n".join(lines)
    assert code == 0
    # Verbose mode shows stop reason in Runtime Info table
    assert "timeout" in out


def test_provider_network_error_is_friendly_and_no_traceback(monkeypatch):
    network_error_result = SimpleNamespace(
        ok=False,
        final_answer="",
        stop_reason="exception",
        status="failed",
        output_type="error",
        tool_calls=[],
        events=[
            {
                "type": "turn_failed",
                "payload": {
                    "error": "LLM network error: [WinError 10013] access socket denied.",
                    "error_type": "RuntimeError",
                },
            }
        ],
        summary={"machine": {"outcome": "failed", "tools_used": [], "risks": []}},
    )
    _install_dummy_loop(monkeypatch, result=network_error_result)
    monkeypatch.setattr(cli_mod, "_build_provider_status_line", lambda: ("LLM provider: fake status=available", object()))
    lines: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg, *a, **k: lines.append(str(msg)))
    code = cli_mod._run_non_interactive_with_mode("list files", output_mode="default")
    out = "\n".join(lines)
    assert code == 0
    assert "python scripts/check_llm_api.py" in out
    assert "Traceback" not in out


def test_json_provider_network_error_contract(monkeypatch):
    network_error_result = SimpleNamespace(
        ok=False,
        final_answer="",
        stop_reason="exception",
        status="failed",
        output_type="error",
        tool_calls=[],
        events=[
            {
                "type": "turn_failed",
                "payload": {
                    "error": "LLM network error: [WinError 10013] access socket denied.",
                    "error_type": "RuntimeError",
                },
            }
        ],
        summary={"machine": {"outcome": "failed", "tools_used": [], "risks": []}},
    )
    _install_dummy_loop(monkeypatch, result=network_error_result)
    monkeypatch.setattr(cli_mod, "_build_provider_status_line", lambda: ("LLM provider: fake status=available", object()))
    lines: list[str] = []
    monkeypatch.setattr(cli_mod, "_safe_print", lambda msg, *a, **k: lines.append(str(msg)))
    code = cli_mod._run_non_interactive_with_mode("list files", output_mode="json")
    out = "\n".join(lines)
    assert code == 0
    payload = json.loads(out)
    assert payload["result"]["status"] == "failed"
    assert payload["result"]["stop_reason"] == "provider_network_error"
    assert payload["result"]["error"]["type"] == "NetworkError"
    assert "Traceback" not in out


def test_main_ask_uses_new_renderer(monkeypatch):
    monkeypatch.setattr(cli_mod, "_load_local_env_file", lambda *_a, **_k: None)
    monkeypatch.setattr(cli_mod, "_write_cli_diagnostic", lambda *_a, **_k: None)
    called: dict[str, str] = {}

    def _fake_runner(prompt: str, *, output_mode: str = "default", **kwargs) -> int:
        called["prompt"] = prompt
        called["output_mode"] = output_mode
        return 0

    monkeypatch.setattr(cli_mod, "_run_non_interactive_with_mode", _fake_runner)
    monkeypatch.setattr("sys.argv", ["python", "--ask", "你是谁", "--output", "quiet"])
    code = cli_mod.main()
    assert code == 0
    assert called["prompt"] == "你是谁"
    assert called["output_mode"] == "quiet"
