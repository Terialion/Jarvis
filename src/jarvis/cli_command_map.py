"""Compatibility loader for legacy `/jarvis/cli_command_map.py`."""

from __future__ import annotations

from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_PATH = _ROOT / "jarvis" / "cli_command_map.py"
_CODE = _PATH.read_text(encoding="utf-8")
exec(compile(_CODE, str(_PATH), "exec"), globals(), globals())

