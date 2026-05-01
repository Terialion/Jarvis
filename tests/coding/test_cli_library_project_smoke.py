from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cli_library_project_smoke_script():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.run(
        [sys.executable, "scripts/smoke_cli_coding_library_project.py"],
        cwd=str(ROOT),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=240,
    )
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    report = ROOT / "temp" / "cli_fuzz" / "coding_library_project_report.md"
    assert report.exists()
    assert "library_project_workspace" in report.read_text(encoding="utf-8")
