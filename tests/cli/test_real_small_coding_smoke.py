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


def test_real_small_coding_smoke_requires_approval():
    result = run_cli(
        input_text="/plan Add one sentence to docs/product/cli_surface.md. Do not modify files yet.\n/fix Add one sentence to docs/product/cli_surface.md.\n/approvals\n/exit\n"
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "approval" in output.lower()
    assert "Traceback" not in output
