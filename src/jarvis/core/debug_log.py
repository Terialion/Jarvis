"""Lightweight debug log for tracing agent internals.

Enabled by setting JARVIS_DEBUG=1 or JARVIS_DEBUG_LOG=<path> in the
environment.  When enabled, each call to debug_log() appends a timestamped
entry to the log file (default: .jarvis/debug.log).

Thread-safe — uses a per-process lock so concurrent writes from the bridge
worker thread and the TUI main thread stay serialized.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_log_path: str | None = None
_lock = threading.Lock()
_enabled: bool | None = None  # tri-state: None = not checked yet


def _resolve() -> str | None:
    global _log_path, _enabled
    if _enabled is None:
        explicit = os.environ.get("JARVIS_DEBUG_LOG", "").strip()
        if explicit:
            _log_path = explicit
            _enabled = True
        elif os.environ.get("JARVIS_DEBUG", "").strip() in ("1", "true", "yes", "on"):
            _log_path = str(Path.cwd() / ".jarvis" / "debug.log")
            _enabled = True
        else:
            _enabled = False
    return _log_path


def is_debug_enabled() -> bool:
    _resolve()
    return bool(_enabled)


def debug_log(source: str, message: str) -> None:
    """Append a timestamped entry to the debug log.

    Args:
        source: A short component label, e.g. ``"agent_bridge"``, ``"loop"``, ``"tui"``.
        message: Free-text message.
    """
    path = _resolve()
    if not path:
        return
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    tid = threading.get_ident()
    line = f"[{ts}] [{source}] [{tid}] {message}\n"
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass  # Debug log must never crash the application
