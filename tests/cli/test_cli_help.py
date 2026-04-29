import subprocess
import sys
from pathlib import Path


def _run_cli(*args: str):
    repo_root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        text=True,
        capture_output=True,
        timeout=20,
        cwd=str(repo_root),
    )


def test_cli_help_exits_zero():
    result = _run_cli("--help")
    assert result.returncode == 0
    output = (result.stdout or "") + (result.stderr or "")
    assert "config" in output
    assert "tools" in output
    assert "server" in output

