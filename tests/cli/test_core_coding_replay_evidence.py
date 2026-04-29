import subprocess
import sys


def run_cli(*args, input_text=None, timeout=30):
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


def test_replay_evidence_commands_available_after_coding_task():
    result = run_cli(
        input_text="/plan Fix the add bug in examples/coding_fixture\n/replay\n/evidence\n/exit\n"
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Replay" in output
    assert "Evidence" in output
    assert "Traceback" not in output
