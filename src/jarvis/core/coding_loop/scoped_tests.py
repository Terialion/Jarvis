from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_scoped_fixture_tests(workspace_root: Path, *, timeout_s: int = 60) -> dict[str, object]:
    command = [sys.executable, "-m", "pytest", "examples/coding_fixture/tests", "-q"]
    proc = subprocess.run(
        command,
        cwd=str(workspace_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
    )
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return {
        "test_scope": "fixture",
        "command": " ".join(command),
        "passed": proc.returncode == 0,
        "exit_code": proc.returncode,
        "output_excerpt": output.strip()[:1200],
    }

