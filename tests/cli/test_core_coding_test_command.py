from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from jarvis import cli as cli_mod

ROOT = Path(__file__).resolve().parents[2]


def run_cli(*args, input_text=None, timeout=30):
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd=str(ROOT),
    )


def test_test_command_is_scoped_and_not_full_pytest():
    result = run_cli(input_text="/test examples/coding_fixture\n/exit\n")
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "examples/coding_fixture" in output
    assert "shell: pytest -q" not in output
    assert "python -m pytest examples/coding_fixture -q" in output


def test_no_silent_full_regression_for_run_tests(monkeypatch):
    monkeypatch.setattr(cli_mod, "_quick_agent_result_for_cli", lambda *_a, **_k: None)

    class _DummyLoop:
        def __init__(self, *args, **kwargs):
            pass

        def run_turn(self, chat_input):
            return SimpleNamespace(
                ok=True,
                final_answer="Approval required before running python -m pytest examples/coding_fixture -q",
                stop_reason="completed",
                status="completed",
                output_type="tool_result",
                tool_calls=[{"name": "shell.run", "arguments": {"command": "python -m pytest examples/coding_fixture -q"}}],
                events=[],
                summary={"machine": {"outcome": "completed", "tools_used": ["shell.run"], "risks": []}},
            )

    monkeypatch.setattr("src.jarvis.agent.loop.AgentLoop", _DummyLoop)
    output = cli_mod.run_agent_turn_for_cli("Run tests", output_mode="default")
    assert "Traceback" not in output
    assert "Approval required" in output or "python -m pytest" in output
