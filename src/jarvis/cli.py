"""Compatibility loader for legacy `/jarvis/cli.py`."""

from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_CLI_PATH = _ROOT / "jarvis" / "cli.py"
_CODE = _CLI_PATH.read_text(encoding="utf-8")
exec(compile(_CODE, str(_CLI_PATH), "exec"), globals(), globals())

