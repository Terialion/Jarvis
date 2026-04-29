import json
import subprocess
import sys
from pathlib import Path


def test_minimal_agent_loop_demo_runs():
    root = Path("d:/jarvis")
    py = root / ".venv" / "Scripts" / "python.exe"
    cmd = [str(py if py.exists() else "python"), "scripts/run_minimal_agent_loop_demo.py"]
    run = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, check=False)
    assert run.returncode == 0
    payload = json.loads(run.stdout.strip())
    assert "steps" in payload and len(payload["steps"]) >= 6
