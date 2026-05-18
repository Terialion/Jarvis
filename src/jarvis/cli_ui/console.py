"""Global Console and theme configuration matching Claude Code's aesthetic."""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme
from rich.style import Style

THEME = Theme(
    {
        # Claude Code color palette
        "prompt": Style(color="#6C8EBF", bold=True),
        "agent": Style(color="#82AAFF"),
        "user": Style(color="#C792EA"),
        "tool": Style(color="#89DDFF"),
        "success": Style(color="#C3E88D"),
        "error": Style(color="#FF5370"),
        "warning": Style(color="#FFCB6B"),
        "muted": Style(color="#546E7A", italic=True),
        "bold_muted": Style(color="#546E7A", bold=True),
        "header": Style(color="#82AAFF", bold=True),
        "command": Style(color="#F78C6C"),
        "path": Style(color="#89DDFF", italic=True),
        "model": Style(color="#C792EA", bold=True),
        "divider": Style(color="#2E3B4E"),
        "skill": Style(color="#C3E88D"),
        "number": Style(color="#F78C6C"),
    }
)

_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(
            theme=THEME,
            highlight=True,
            markup=True,
            force_terminal=True,
        )
    return _console
