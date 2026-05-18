import os
import subprocess
import sys


def run_cli(*args, input_text=None, timeout=30):
    env = os.environ.copy()
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
        env=env,
    )


def test_state_does_not_leak_secret(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-1234567890")
    result = run_cli("task", "state")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "sk-test-1234567890" not in output


def test_agent_tool_loop_still_has_approval_flow():
    result = run_cli(
        input_text="/fix Fix the add bug in examples/coding_fixture. Apply the smallest patch only.\n/approvals\n/exit\n"
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "approval" in output.lower()
    assert "Traceback" not in output
