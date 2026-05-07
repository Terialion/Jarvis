from __future__ import annotations

import sys
from pathlib import Path

from src.jarvis.core.command_runner import CommandRunner
from src.jarvis.core.test_runner import TestRunner


def _invalid_bytes_command() -> str:
    code = (
        "import sys; "
        "sys.stdout.buffer.write(bytes([255,254,97])); "
        "sys.stderr.buffer.write(bytes([255,254,98]))"
    )
    return f'"{sys.executable}" -c "{code}"'


def test_command_runner_replaces_invalid_utf8(tmp_path: Path):
    runner = CommandRunner()
    result = runner.run(_invalid_bytes_command(), str(tmp_path), timeout_s=10)
    assert result["ok"] is True
    stdout = str((result.get("data") or {}).get("stdout") or "")
    stderr = str((result.get("data") or {}).get("stderr") or "")
    assert "abc" not in stdout
    assert "a" in stdout
    assert "b" in stderr


def test_test_runner_replaces_invalid_utf8(tmp_path: Path):
    runner = TestRunner()
    result = runner.run_test(_invalid_bytes_command(), str(tmp_path), timeout_s=10)
    assert result["ok"] is True
    data = result.get("data") or {}
    assert data.get("passed") is True
    assert "a" in str(data.get("stdout") or "")
    assert "b" in str(data.get("stderr") or "")
