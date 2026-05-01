from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_PATH = _ROOT / "jarvis" / "config" / "manager.py"
_CODE = _PATH.read_text(encoding="utf-8")
exec(compile(_CODE, str(_PATH), "exec"), globals(), globals())

