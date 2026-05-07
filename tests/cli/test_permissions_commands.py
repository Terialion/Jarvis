from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run_cli(input_text: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli"],
        cwd=str(ROOT),
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=40,
        env=env,
    )


def test_permissions_slash_commands_round_trip():
    result = _run_cli("/permissions\n/test tests/agent\n/approve last\n/deny missing-id\n/exit\n")
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0
    assert "Permission profile" in output
    assert "Approved:" in output
