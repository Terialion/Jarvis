"""Shared TUI utilities — single source of truth for rendering helpers.

Consolidates functions that were duplicated across shell_tui.py, persistent_tui.py,
and input.py. Used by PersistentTUI and one-shot streaming paths.
"""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path
from typing import Any

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from rich.console import Console as RichConsole
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text as RichText

from .console import THEME as RICH_THEME

# ── Rich-to-ANSI bridge ------------------------------------------------------

def rich_to_ansi(renderable: Any, width: int = 80) -> str:
    """Convert any Rich renderable to an ANSI terminal string."""
    buf = StringIO()
    rc = RichConsole(
        file=buf, force_terminal=True, width=max(width, 40),
        color_system="truecolor", theme=RICH_THEME,
    )
    rc.print(renderable)
    return buf.getvalue()


# ── Styling ------------------------------------------------------------------

_TUI_STYLE_RULES = {
    "prompt": "#6C8EBF bold",
    "muted": "#546E7A italic",
    "input": "#D4D4D4",
    "input-area": "",
    "text-area": "",
    "completion-menu": "bg:#1E2A3A #D4D4D4",
    "completion-menu.completion": "bg:#2E3B4E #D4D4D4",
    "completion-menu.completion.current": "bg:#3E5068 #FFFFFF bold",
    "user": "#6C8EBF bold",
    "tool": "#89DDFF",
    "success": "#C3E88D",
    "error": "#FF5370",
    "warning": "#FFCB6B",
}

TUI_STYLE = Style.from_dict(_TUI_STYLE_RULES)

_PROMPT_FORMATTED = FormattedText([
    ("class:prompt", "> "),
    ("class:muted", "Jarvis "),
])


# ── Slash command autocomplete -----------------------------------------------

def _match_score(prefix: str, cmd_name: str, desc: str) -> int:
    """Score a command against the user's prefix. Higher = better match."""
    pl = prefix.lower()
    nl = cmd_name.lower()
    if nl.startswith(pl):
        return 300 - min(len(cmd_name), 99)
    if pl in nl:
        return 200
    if pl in desc.lower():
        return 100
    if _sequential_match(pl, nl):
        return 50
    return 0


def _sequential_match(prefix: str, target: str) -> bool:
    """Return True if *prefix* characters appear sequentially in *target*."""
    i = 0
    for ch in target:
        if i < len(prefix) and ch == prefix[i]:
            i += 1
    return i == len(prefix)


class SlashCompleter(Completer):
    """Prompt-toolkit completer with fuzzy matching, categories, and status badges."""

    def __init__(self) -> None:
        self._commands: list[tuple[str, str, str, str]] = []

    def register_commands(self, commands: list[tuple[str, str, str, str]]) -> None:
        self._commands = list(commands)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        prefix = text[1:]
        if " " in prefix:
            return
        if not prefix:
            for cmd_name, desc, category, status in sorted(self._commands, key=lambda x: x[0])[:8]:
                yield self._make_completion(cmd_name, desc, category, status, text)
            return
        scored: list[tuple[int, str, str, str, str]] = []
        for cmd_name, desc, category, status in self._commands:
            s = _match_score(prefix, cmd_name, desc)
            if s > 0:
                scored.append((s, cmd_name, desc, category, status))
        scored.sort(key=lambda x: x[0], reverse=True)
        for _, cmd_name, desc, category, status in scored[:8]:
            yield self._make_completion(cmd_name, desc, category, status, text)

    def _make_completion(self, name: str, desc: str, category: str, status: str, text: str) -> Completion:
        meta_parts: list[str] = []
        if category:
            meta_parts.append(f"[{category}]")
        if status == "skeleton":
            meta_parts.append("[skeleton]")
        meta_parts.append(desc)
        return Completion(
            name,
            start_position=-len(text),
            display=name,
            display_meta=" ".join(meta_parts),
        )


# ── Markdown rendering -------------------------------------------------------

def render_markdown(text: str, width: int = 80) -> str:
    """Render markdown to ANSI using Rich's Markdown renderer."""
    if not text.strip():
        return text
    try:
        from .render import _normalize_markdown
        text = _normalize_markdown(text.strip())
    except Exception:
        pass
    try:
        md = Markdown(
            text,
            code_theme="material-darker",
            inline_code_theme="material-darker",
        )
        return rich_to_ansi(md, width=min(width, 100))
    except Exception:
        return text


# ── Artifact stripping -------------------------------------------------------

def strip_artifacts(text: str) -> str:
    """Remove tool_plan_json JSON and <tool_call> XML from text."""
    # Brace-counting: find {"tool_plan_json":{...}} with arbitrary nesting
    needle = '"tool_plan_json"'
    while True:
        idx = text.find(needle)
        if idx == -1:
            break
        brace_start = -1
        for i in range(idx, -1, -1):
            if text[i] == "{":
                brace_start = i
                break
        if brace_start == -1:
            break
        depth = 0
        pos = brace_start
        while pos < len(text):
            ch = text[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            pos += 1
        text = text[:brace_start] + text[pos + 1:]

    # Remove ```json ... ``` code fences
    text = re.sub(r"```json\s*[\s\S]*?```", "", text, flags=re.DOTALL)

    # Remove <tool_call> XML
    text = re.sub(
        r"<tool_call>\s*<function=[^>]+>.*?</function>\s*</tool_call>",
        "",
        text,
        flags=re.DOTALL,
    )
    return text


# ── Tool result formatting ---------------------------------------------------

_DIFF_TOOLS = frozenset({"file_editor.diff"})


def _render_diff_panel(diff_text: str) -> str:
    """Render unified diff text as a Rich panel with +/- coloring."""
    from shutil import get_terminal_size
    from .render import render_diff
    try:
        width = get_terminal_size().columns - 4
    except Exception:
        width = 76
    return rich_to_ansi(render_diff(diff_text), width=max(width, 40))


def format_tool_result(raw_text: str, elapsed_str: str = "") -> str:
    """Parse [Tool `name`: content] wrapper → single-line summary.

    Matches Claude Code / Codex CLI tool result display style.
    """
    m = re.match(
        r"\s*\[Tool\s+`([^`]+)`:\s*(.*?)\]\s*$",
        raw_text.strip(),
        flags=re.DOTALL,
    )
    if not m:
        return raw_text
    name = m.group(1)
    content = m.group(2).strip()

    ok = "\x1b[32m└\x1b[0m"
    err = "\x1b[31m└\x1b[0m"
    is_error = content.lower().startswith(("error", "exception", "failed", "traceback", "rejected"))

    if is_error:
        short = content.split("\n")[0][:100]
        return f"    {err} {short}{elapsed_str}"

    suffix = elapsed_str

    # Diff tools — render full diff panel
    if name in _DIFF_TOOLS and content and not is_error:
        return _render_diff_panel(content)

    if "list_tree" in name or "glob" in name:
        n = len([l for l in content.split("\n") if l.strip()])
        return f"    {ok} {n} items{suffix}"

    if "search" in name or "grep" in name or "search_symbol" in name:
        n = len([l for l in content.split("\n") if l.strip()])
        return f"    {ok} {n} matches{suffix}"

    if "read_file" in name or name.endswith(".read_file"):
        n = content.count("\n") + 1
        return f"    {ok} {n} lines{suffix}"

    if "run" in name or "shell" in name or "bash" in name:
        n = len(content.encode("utf-8"))
        return f"    {ok} exit 0 · {n} bytes{suffix}"

    if "web_search" in name or "web.search" in name:
        n = len([l for l in content.split("\n") if l.strip()])
        return f"    {ok} {n} results{suffix}"

    if "web_fetch" in name or "web.fetch" in name:
        n = len(content.encode("utf-8"))
        return f"    {ok} {n} bytes{suffix}"

    first_line = content.split("\n")[0]
    if len(first_line) > 120:
        first_line = first_line[:117] + "..."
    return f"    {ok} {first_line}{suffix}"


# ── Status indicators --------------------------------------------------------

def build_status_indicators(project_root: str) -> str:
    """Return short status indicators for bg tasks, team inbox, worktrees."""
    parts: list[str] = []
    try:
        from jarvis.core.background import BackgroundTaskManager
        bg = BackgroundTaskManager(max_workers=1)
        bg_tasks = bg.list_tasks()
        running = sum(1 for t in bg_tasks if t.get("status") in ("running", "pending"))
        if running:
            parts.append(f" · ⚡ {running}")
    except Exception:
        pass
    try:
        from jarvis.core.teams.message_bus import MessageBus
        bus = MessageBus(inbox_dir=Path(".jarvis/teams/inbox"))
        inbox = bus.read_inbox("user")
        unread = len(inbox)
        if unread:
            parts.append(f" · ✉ {unread}")
    except Exception:
        pass
    try:
        from jarvis.core.worktree.manager import WorktreeManager
        from jarvis.core.tasks.manager import PersistentTaskManager
        root = Path(project_root)
        tasks_dir = root / ".jarvis" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        tm = PersistentTaskManager(tasks_dir=tasks_dir)
        wtm = WorktreeManager(repo_root=root, tasks=tm)
        wts = wtm.list_all()
        active = sum(1 for wt in (wts.get("worktrees", []) if isinstance(wts, dict) else [])
                     if wt.get("active"))
        if active:
            parts.append(f" · 🌲 {active}")
    except Exception:
        pass
    return "".join(parts) if parts else ""
