from __future__ import annotations

import sys
from pathlib import Path

from .schema import TestRunPlan


def default_pytest_command() -> str:
    exe = str(Path(sys.executable))
    if " " in exe:
        exe = f'"{exe}"'
    return f"{exe} -m pytest tests -q"


def build_test_plan(command: str | None = None) -> TestRunPlan:
    cmd = str(command or "").strip() or default_pytest_command()
    return TestRunPlan(
        command=cmd,
        reason="Run the narrowest scoped pytest suite for this coding task.",
        expected_signal="exit_code_zero",
    )
