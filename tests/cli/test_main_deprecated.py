import subprocess
import sys
from pathlib import Path


def test_main_deprecated_entrypoint_does_not_crash():
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        text=True,
        capture_output=True,
        timeout=15,
        cwd=str(repo_root),
    )
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "Traceback" not in output
    assert "analyze_search_decision" not in output
    assert "jarvis.cli" in output or "usage" in output.lower()

