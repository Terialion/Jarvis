import subprocess
import sys


def run_cli(*args, input_text=None, timeout=25):
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
    )


def test_trace_off_by_default():
    result = run_cli(input_text="Inspect this repo. Do not modify files.\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "skill.registry.loaded" not in output
    assert "Task task_" not in output


def test_trace_on_shows_internal_events():
    result = run_cli(input_text="/trace on\nInspect this repo. Do not modify files.\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Trace mode: on" in output or "trace on" in output.lower()
    assert "Task task_" not in output
    # Now routed through AgentToolLoop
    assert "llm provider" in output.lower() or "无法连接" in output or "repository inspection" in output.lower()


def test_trace_off_hides_internal_events_again():
    result = run_cli(input_text="/trace on\n/trace off\nInspect this repo. Do not modify files.\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Trace mode: off" in output or "trace off" in output.lower()
    tail = output.rsplit("Do not modify files.", 1)[-1]
    assert "skill.registry.loaded" not in tail
