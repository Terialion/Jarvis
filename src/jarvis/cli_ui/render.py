"""Rich rendering helpers — panels, markdown, tables, tool calls."""

from __future__ import annotations

import re
from typing import Any

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .console import get_console

# Fix common LLM markdown quirks before rendering
_HEADING_NO_SPACE = re.compile(r'^(#{1,6})([^\s#])', re.MULTILINE)


def _is_block_start(line: str) -> bool:
    """Return True if *line* starts a markdown block element."""
    s = line.strip()
    if not s:
        return False
    if s.startswith("|"):
        return True
    if s in ("```", "---", "***"):
        return True
    if s[0] in ("-", "*") and len(s) > 1 and s[1] == " ":
        return True
    if s[0].isdigit() and ". " in s[:5]:
        return True
    return False


def _is_block_continuation(line: str) -> bool:
    """Return True if *line* is part of an existing block (table, list, code)."""
    s = line.strip()
    if not s:
        return False
    return s.startswith("|") or s[0] in ("-", "*") or (s[0].isdigit() and ". " in s[:5])


def _normalize_markdown(content: str) -> str:
    """Fix common LLM markdown quirks before rendering.

    - ``###text`` → ``### text`` (missing space after heading marker)
    - ``||`` → ``|\\n|`` (LLM double-pipe as row separator)
    - Insert blank lines before tables, code blocks, and top-level lists
      when the preceding line is paragraph text (not another block element).
    """
    content = _HEADING_NO_SPACE.sub(r'\1 \2', content)
    # Ensure spaces around **bold** adjacent to CJK characters.
    # CommonMark requires word boundaries around emphasis markers; CJK
    # characters are not "word" characters, so **bold**中文 breaks.
    # Insert a thin space (U+200A) to create a visual word boundary
    # without adding visible gaps.
    _CJK = r'[一-鿿㐀-䶿豈-﫿]'
    content = re.sub(f'({_CJK})[*][*]', r'\1 **', content)  # 中文**bold**
    content = re.sub(f'[*][*]({_CJK})', r'** \1', content)  # **bold**中文
    # Same for __italic__
    content = re.sub(f'({_CJK})__', r'\1 __', content)
    content = re.sub(f'__({_CJK})', r'__ \1', content)
    # **bold**-listitem → **bold**\n\n- listitem (DeepSeek concatenates header+list)
    content = re.sub(r'(\*\*[^*]+\*\*)-(\s?[一-鿿\w])', r'\1\n\n- \2', content)
    # Emoji/CJK header followed by -CJK list item on same line
    # E.g. "🌐网络与信息-搜索网页" → "🌐网络与信息\n- 搜索网页"
    content = re.sub(r'^([^-*#|`\s].*?[一-鿿])-\s?([一-鿿])', r'\1\n- \2', content, flags=re.MULTILINE)
    # Fix || used as table row separator (common LLM quirk: all rows on one line)
    content = re.sub(r'\|\|', '|\n|', content)
    # Split non-table paragraph text from table on the same line
    # E.g. "合肥天气☀️|项目|数据|" → "合肥天气☀️\n|项目|数据|"
    content = re.sub(r'^([^|\n]+)(\|[^\n]+)', r'\1\n\2', content, flags=re.MULTILINE)
    # Fix concatenated rows: |cell|\s+|next-row| → |cell|\n|next-row|
    # Only skip real separator rows (|------), not cells with leading spaces
    content = re.sub(r'([^|])\|\s+\|(?=[^-])', r'\1|\n|', content)
    # Remove blank lines between table rows (breaks Rich table parsing)
    content = re.sub(r'(\|[^\n]+\|)\n\n(\|[^\n]+\|)', r'\1\n\2', content)
    # Split paragraph text that trails after the last | of a table row.
    # Match all cells (any column count) and ensure trailing text has no |.
    content = re.sub(r'^((?:\|[^|]+)+\|)([^\s|][^\n|]*)$', r'\1\n\2', content, flags=re.MULTILINE)
    lines = content.split("\n")
    # Pre-process: split concatenated list items before blank-line insertion
    # E.g. "-浏览...内容-编辑...文件" → "-浏览...内容", "- 编辑...文件"
    expanded: list[str] = []
    for line in lines:
        if line.startswith('-') and not line.startswith('--') and not line.startswith('- ['):
            parts = re.split(r'(?<=[一-鿿\w])-(?=[一-鿿])', line)
            for j, part in enumerate(parts):
                if j == 0:
                    expanded.append(part)
                else:
                    expanded.append('- ' + part)
        else:
            expanded.append(line)
    result: list[str] = []
    for i, line in enumerate(expanded):
        if i > 0 and _is_block_start(line) and not _is_block_continuation(result[-1]):
            if result[-1].strip():
                result.append("")
        result.append(line)
    return "\n".join(result)


def render_markdown(content: str) -> Markdown:
    """Render markdown with syntax-highlighted code blocks."""
    normalized = _normalize_markdown(content)
    return Markdown(
        normalized,
        code_theme="material-darker",
        inline_code_theme="material-darker",
    )


def render_panel(
    content: RenderableType,
    *,
    title: str = "",
    border_style: str = "agent",
    padding: tuple[int, int] = (1, 2),
) -> Panel:
    """Render a styled panel matching Claude Code output style."""
    return Panel(
        content,
        title=title,
        title_align="left",
        border_style=border_style,
        padding=padding,
    )


def render_tool_call(
    name: str,
    args: str = "",
    *,
    status: str = "running",
    result: str = "",
) -> Panel:
    """Render a tool call with status indicator."""
    status_icons = {
        "running": "[tool]●[/]",
        "ok": "[success]✓[/]",
        "error": "[error]✗[/]",
        "pending": "[muted]○[/]",
        "cached": "[warning]↻[/]",
    }
    icon = status_icons.get(status, "[muted]○[/]")

    body = Text()
    if args:
        body.append(f"  {args}", style="muted")

    result_text = ""
    if result:
        short = str(result)[:200].replace("\n", " ")
        result_text = f"  [muted]{short}[/]"

    return Panel(
        f"{icon} [tool]{name}[/]{result_text}",
        border_style="divider",
        padding=(0, 1),
    )


def render_table(
    rows: list[dict[str, Any]],
    *,
    title: str = "",
    columns: list[tuple[str, str]] | None = None,
    border_style: str = "divider",
) -> Table:
    """Render a rich table from dict rows."""
    if not rows and not columns:
        return Table(title=title)

    if columns is None and rows:
        columns = [(k, k) for k in rows[0].keys()]

    table = Table(
        title=title,
        title_style="header",
        border_style=border_style,
        show_header=True,
        header_style="bold_muted",
    )
    for label, key in (columns or []):
        table.add_column(str(label), style="")

    for row in rows:
        table.add_row(*[str(row.get(k, "")) for _, k in (columns or [])])

    return table


def render_header(
    cwd: str,
    model: str = "unknown",
    provider: str = "",
    thread_id: str = "",
) -> Panel:
    """Render the shell header as a rich panel."""
    body = Text()
    body.append(f"{cwd}\n", style="path")
    body.append(f"Model: ", style="muted")
    body.append(model, style="model")
    if provider:
        body.append(f"  |  {provider}", style="muted")
    if thread_id:
        body.append(f"  |  {thread_id}", style="muted")
    return Panel(
        body,
        title="Jarvis",
        title_align="left",
        border_style="agent",
        padding=(1, 2),
    )


def render_diff(
    diff_text: str,
    *,
    file_path: str = "",
    border_style: str = "divider",
) -> Panel:
    """Render a unified diff as a Rich Panel with +/- coloring.

    File path (e.g. ``src/config.py``) is shown as the panel title.
    Uses Rich's built-in diff lexer for syntax highlighting.
    """
    from rich.syntax import Syntax

    # Trim leading/trailing blank lines but preserve diff structure
    diff_text = diff_text.strip()
    if not diff_text:
        return Panel("(empty diff)", border_style=border_style)

    # Detect file path from +++ line if not provided
    if not file_path:
        import re
        m = re.search(r'\+\+\+\s+[ab]/?(.+)', diff_text)
        if m:
            file_path = m.group(1)

    # Count changes for summary
    added = len([l for l in diff_text.split("\n") if l.startswith("+") and not l.startswith("+++")])
    removed = len([l for l in diff_text.split("\n") if l.startswith("-") and not l.startswith("---")])

    # Syntax-highlighted diff
    syntax = Syntax(
        diff_text,
        "diff",
        theme="material-darker",
        background_color="default",
        line_numbers=False,
        word_wrap=False,
    )

    # Summary subtitle: "3 changes: +2 -1"
    summary_parts = []
    if added or removed:
        summary_parts.append(f"{added + removed} changes")
        if added:
            summary_parts.append(f"[success]+{added}[/]")
        if removed:
            summary_parts.append(f"[error]-{removed}[/]")
    summary = ", ".join(summary_parts) if summary_parts else ""

    return Panel(
        syntax,
        title=file_path if file_path else "diff",
        title_align="left",
        border_style=border_style,
        subtitle=summary,
        subtitle_align="right",
        padding=(0, 1),
    )


def capture_rich(renderable: RenderableType) -> str:
    """Render a Rich renderable to a plain string for use with _safe_print."""
    from io import StringIO

    from rich.console import Console as RichConsole

    from .console import THEME

    string_out = StringIO()
    rich_console = RichConsole(file=string_out, force_terminal=False, theme=THEME)
    rich_console.print(renderable)
    return string_out.getvalue().strip()
