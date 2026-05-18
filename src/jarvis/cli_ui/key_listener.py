"""Non-blocking keyboard listener for post-stream toggle (Ctrl+T to show/hide thinking)."""

from __future__ import annotations

import sys
import threading
from typing import Callable


_CTRL_T = "\x14"  # Ctrl+T


def listen_for_key(
    callback: Callable[[str], bool],
    *,
    timeout: float = 30.0,
) -> threading.Thread:
    """Listen for a single keypress in a background thread.

    Calls ``callback(key)`` on keypress.  If the callback returns ``True``
    the listener exits; otherwise it keeps listening until *timeout*.

    Returns the listener thread (daemon, already started).
    """
    listener = threading.Thread(
        target=_listen_loop,
        args=(callback, timeout),
        daemon=True,
    )
    listener.start()
    return listener


def _listen_loop(
    callback: Callable[[str], bool],
    timeout: float,
) -> None:
    import time
    deadline = time.monotonic() + timeout

    if sys.platform == "win32":
        import msvcrt
        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                try:
                    key = ch.decode("utf-8", errors="replace")
                except UnicodeDecodeError:
                    key = ch.decode("latin-1", errors="replace")
                try:
                    if callback(key):
                        return
                except Exception:
                    return
            time.sleep(0.05)
    else:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while time.monotonic() < deadline:
                r, _, _ = select.select([sys.stdin], [], [], 0.1)
                if r:
                    key = sys.stdin.read(1)
                    try:
                        if callback(key):
                            return
                    except Exception:
                        return
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
