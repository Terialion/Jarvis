"""Builtin tool specifications for the Jarvis core tool system.

These are the minimum tools that must be registered in the first version.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .schema import ToolCall, ToolContext, ToolResult, ToolSpec


# ---------------------------------------------------------------------------
# Sensitive file patterns — these must NEVER be readable
# ---------------------------------------------------------------------------

_SENSITIVE_PATTERNS = {
    ".env",
    ".npmrc",
    ".pypirc",
    ".ssh",
    "id_rsa",
    "id_ed25519",
    "id_dsa",
    "credential",
    "token",
    "secret",
    "private_key",
    "api_key",
    "password",
}

_SENSITIVE_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".jks"}


def _is_sensitive_path(path: str) -> bool:
    """Check if a path refers to a sensitive file."""
    low = path.lower().replace("\\", "/")
    for pattern in _SENSITIVE_PATTERNS:
        if pattern in low:
            return True
    for ext in _SENSITIVE_EXTENSIONS:
        if low.endswith(ext):
            return True
    return False


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def _handler_workspace_status(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    workspace = arguments.get("path") or context.workspace_root
    p = Path(workspace).resolve()
    return ToolResult(
        tool_name="workspace.status",
        ok=True,
        output={"root": str(p), "exists": p.exists(), "is_dir": p.is_dir()},
        risk_level="low",
    )


def _handler_workspace_list_dir(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    target = arguments.get("path") or context.workspace_root
    p = Path(target).resolve()
    if not p.exists() or not p.is_dir():
        return ToolResult(
            tool_name="workspace.list_dir",
            ok=False,
            error=f"Directory not found: {target}",
            risk_level="low",
        )
    try:
        entries = sorted(p.iterdir())
        items = [
            {"name": e.name, "type": "dir" if e.is_dir() else "file", "size": e.stat().st_size if e.is_file() else None}
            for e in entries
            if not e.name.startswith(".")
        ]
        return ToolResult(
            tool_name="workspace.list_dir",
            ok=True,
            output=items,
            risk_level="low",
            metadata={"count": len(items), "path": str(p)},
        )
    except PermissionError as exc:
        return ToolResult(
            tool_name="workspace.list_dir",
            ok=False,
            error=f"Permission denied: {exc}",
            risk_level="low",
        )


def _handler_workspace_read_file(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    path = arguments.get("path", "")
    if not path:
        return ToolResult(
            tool_name="workspace.read_file",
            ok=False,
            error="path is required",
            risk_level="medium",
        )
    if _is_sensitive_path(path):
        return ToolResult(
            tool_name="workspace.read_file",
            ok=False,
            error="safety_refusal: cannot read sensitive files (.env, .ssh, tokens, secrets)",
            risk_level="blocked",
            metadata={"safety_refusal": True},
        )
    p = Path(path).resolve()
    if not p.exists():
        return ToolResult(
            tool_name="workspace.read_file",
            ok=False,
            error=f"File not found: {path}",
            risk_level="medium",
        )
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        return ToolResult(
            tool_name="workspace.read_file",
            ok=True,
            output={"path": str(p), "line_count": len(lines), "content": content[:50000]},
            risk_level="medium",
            metadata={"line_count": len(lines), "size": len(content)},
        )
    except PermissionError as exc:
        return ToolResult(
            tool_name="workspace.read_file",
            ok=False,
            error=f"Permission denied: {exc}",
            risk_level="medium",
        )


def _handler_workspace_search_files(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    pattern = arguments.get("pattern", "")
    directory = arguments.get("directory") or context.workspace_root
    if not pattern:
        return ToolResult(
            tool_name="workspace.search_files",
            ok=False,
            error="pattern is required",
            risk_level="low",
        )
    import fnmatch

    p = Path(directory).resolve()
    if not p.exists():
        return ToolResult(
            tool_name="workspace.search_files",
            ok=False,
            error=f"Directory not found: {directory}",
            risk_level="low",
        )
    matches = []
    try:
        for item in p.rglob("*"):
            if item.is_file() and fnmatch.fnmatch(item.name, pattern):
                matches.append(str(item))
            if len(matches) >= 100:
                matches.append("... (truncated at 100 results)")
                break
    except PermissionError:
        pass
    return ToolResult(
        tool_name="workspace.search_files",
        ok=True,
        output=matches,
        risk_level="low",
        metadata={"count": len(matches), "pattern": pattern},
    )


def _handler_patch_apply(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    file_path = arguments.get("file_path", "")
    content = arguments.get("content", "")
    if not file_path or not content:
        return ToolResult(
            tool_name="patch.apply",
            ok=False,
            error="file_path and content are required",
            risk_level="medium",
        )
    p = Path(file_path).resolve()
    return ToolResult(
        tool_name="patch.apply",
        ok=False,
        error="approval_required: patch.apply requires approval before writing files",
        risk_level="high",
        requires_approval=True,
        metadata={"pending_file_path": str(p), "requires_approval": True},
    )


def _handler_shell_run(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    command = arguments.get("command", "")
    if not command:
        return ToolResult(
            tool_name="shell.run",
            ok=False,
            error="command is required",
            risk_level="medium",
        )
    low = command.lower().strip()
    # Dangerous command patterns
    dangerous = any(
        token in low
        for token in ("rm -rf", "del /s", "format ", "shutdown", "curl ", "wget ")
    )
    if dangerous:
        return ToolResult(
            tool_name="shell.run",
            ok=False,
            error="approval_required: shell.run requires approval before executing commands",
            risk_level="high",
            requires_approval=True,
            metadata={"pending_command": command, "requires_approval": True},
        )
    return ToolResult(
        tool_name="shell.run",
        ok=False,
        error="approval_required: shell.run requires approval before executing commands",
        risk_level="high",
        requires_approval=True,
        metadata={"pending_command": command, "requires_approval": True},
    )


def _handler_web_search(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    query = arguments.get("query", "")
    if not query:
        return ToolResult(
            tool_name="web.search",
            ok=False,
            error="query is required",
            risk_level="medium",
        )
    return ToolResult(
        tool_name="web.search",
        ok=False,
        error="network_unavailable: web.search requires network access",
        risk_level="medium",
        metadata={"pending_query": query, "requires_network": True},
    )


def _handler_web_fetch(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    url = arguments.get("url", "")
    if not url:
        return ToolResult(
            tool_name="web.fetch",
            ok=False,
            error="url is required",
            risk_level="medium",
        )
    return ToolResult(
        tool_name="web.fetch",
        ok=False,
        error="network_unavailable: web.fetch requires network access",
        risk_level="medium",
        metadata={"pending_url": url, "requires_network": True},
    )


def _handler_skill_list(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    """List available skills (metadata only, no full SKILL.md)."""
    try:
        from ..skill_harness.registry import get_skill_registry

        reg = get_skill_registry(Path(context.workspace_root), refresh=False)
        snap = reg.snapshot().get("data", {})
        items = list(snap.get("items") or [])
        skills = [
            {
                "name": str(i.get("skill_id") or i.get("id") or ""),
                "description": str(i.get("description") or "")[:100],
                "status": str(i.get("status") or ""),
                "trust": str(i.get("trust") or ""),
                "source": str(i.get("source") or ""),
            }
            for i in items
            if str(i.get("status", "")).lower() in {"enabled", "available"}
        ]
        return ToolResult(
            tool_name="skill.list",
            ok=True,
            output=skills,
            risk_level="low",
            metadata={"count": len(skills)},
        )
    except Exception as exc:
        return ToolResult(
            tool_name="skill.list",
            ok=False,
            error=f"skill registry error: {exc}",
            risk_level="low",
        )


def _handler_skill_invoke(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    skill_name = arguments.get("skill_name", "")
    task = arguments.get("task", "")
    if not skill_name:
        return ToolResult(
            tool_name="skill.invoke",
            ok=False,
            error="skill_name is required",
            risk_level="medium",
        )
    return ToolResult(
        tool_name="skill.invoke",
        ok=False,
        error="approval_required: skill.invoke requires approval and trust check",
        risk_level="medium",
        requires_approval=True,
        metadata={"pending_skill": skill_name, "pending_task": task, "requires_approval": True},
    )


def _handler_repo_inspect(arguments: dict[str, Any], context: ToolContext) -> ToolResult:
    workspace = arguments.get("path") or context.workspace_root
    p = Path(workspace).resolve()
    if not p.exists():
        return ToolResult(
            tool_name="repo.inspect",
            ok=False,
            error=f"Path not found: {workspace}",
            risk_level="low",
        )
    try:
        entries = []
        for item in sorted(p.iterdir()):
            if item.name.startswith("."):
                continue
            entries.append({"name": item.name, "type": "dir" if item.is_dir() else "file"})
        return ToolResult(
            tool_name="repo.inspect",
            ok=True,
            output={"root": str(p), "entries": entries},
            risk_level="low",
            metadata={"entry_count": len(entries)},
        )
    except PermissionError as exc:
        return ToolResult(
            tool_name="repo.inspect",
            ok=False,
            error=f"Permission denied: {exc}",
            risk_level="low",
        )


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

_WORKSPACE_STATUS_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string", "description": "Workspace path (default: current)"}},
    "required": [],
}

_LIST_DIR_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string", "description": "Directory path to list"}},
    "required": [],
}

_READ_FILE_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string", "description": "File path to read"}},
    "required": ["path"],
}

_SEARCH_FILES_SCHEMA = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "Glob pattern to match"},
        "directory": {"type": "string", "description": "Root directory (default: workspace)"},
    },
    "required": ["pattern"],
}

_PATCH_APPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "Target file path"},
        "content": {"type": "string", "description": "New file content"},
    },
    "required": ["file_path", "content"],
}

_SHELL_RUN_SCHEMA = {
    "type": "object",
    "properties": {"command": {"type": "string", "description": "Shell command to execute"}},
    "required": ["command"],
}

_WEB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string", "description": "Search query"}},
    "required": ["query"],
}

_WEB_FETCH_SCHEMA = {
    "type": "object",
    "properties": {"url": {"type": "string", "description": "URL to fetch"}},
    "required": ["url"],
}

_SKILL_LIST_SCHEMA = {"type": "object", "properties": {}, "required": []}

_SKILL_INVOKE_SCHEMA = {
    "type": "object",
    "properties": {
        "skill_name": {"type": "string", "description": "Skill name to invoke"},
        "task": {"type": "string", "description": "Task description"},
    },
    "required": ["skill_name"],
}

_REPO_INSPECT_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string", "description": "Repository/workspace path"}},
    "required": [],
}

# Output schemas are simple type indicators
_OUTPUT_LIST = {"type": "array", "items": {"type": "object"}}
_OUTPUT_OBJECT = {"type": "object"}
_OUTPUT_STATUS = {"type": "object", "properties": {"root": {"type": "string"}}}


# ---------------------------------------------------------------------------
# Tool spec definitions
# ---------------------------------------------------------------------------

BUILTIN_TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="workspace.status",
        description="Show current workspace root path and status.",
        input_schema=_WORKSPACE_STATUS_SCHEMA,
        output_schema=_OUTPUT_STATUS,
        risk_level="low",
        requires_approval=False,
        permissions={"repo_read"},
        handler=_handler_workspace_status,
    ),
    ToolSpec(
        name="workspace.list_dir",
        description="List files and directories in a given path or workspace root.",
        input_schema=_LIST_DIR_SCHEMA,
        output_schema=_OUTPUT_LIST,
        risk_level="low",
        requires_approval=False,
        permissions={"repo_read"},
        handler=_handler_workspace_list_dir,
    ),
    ToolSpec(
        name="workspace.read_file",
        description="Read a file's contents. Refuses sensitive files (.env, .ssh, tokens, secrets).",
        input_schema=_READ_FILE_SCHEMA,
        output_schema=_OUTPUT_OBJECT,
        risk_level="medium",
        requires_approval=False,
        permissions={"repo_read"},
        handler=_handler_workspace_read_file,
    ),
    ToolSpec(
        name="workspace.search_files",
        description="Search for files matching a glob pattern in the workspace.",
        input_schema=_SEARCH_FILES_SCHEMA,
        output_schema=_OUTPUT_LIST,
        risk_level="low",
        requires_approval=False,
        permissions={"repo_read"},
        handler=_handler_workspace_search_files,
    ),
    ToolSpec(
        name="repo.inspect",
        description="Inspect repository/workspace structure (top-level entries).",
        input_schema=_REPO_INSPECT_SCHEMA,
        output_schema=_OUTPUT_OBJECT,
        risk_level="low",
        requires_approval=False,
        permissions={"repo_read"},
        handler=_handler_repo_inspect,
    ),
    ToolSpec(
        name="patch.apply",
        description="Apply a content patch to a file. Requires approval before writing.",
        input_schema=_PATCH_APPLY_SCHEMA,
        output_schema=_OUTPUT_OBJECT,
        risk_level="high",
        requires_approval=True,
        permissions={"write"},
        handler=_handler_patch_apply,
    ),
    ToolSpec(
        name="shell.run",
        description="Execute a shell command. Requires approval before running.",
        input_schema=_SHELL_RUN_SCHEMA,
        output_schema=_OUTPUT_OBJECT,
        risk_level="high",
        requires_approval=True,
        permissions={"shell"},
        handler=_handler_shell_run,
    ),
    ToolSpec(
        name="web.search",
        description="Search the web for information. Requires network access.",
        input_schema=_WEB_SEARCH_SCHEMA,
        output_schema=_OUTPUT_OBJECT,
        risk_level="medium",
        requires_approval=True,
        permissions={"network"},
        handler=_handler_web_search,
    ),
    ToolSpec(
        name="web.fetch",
        description="Fetch content from a URL. Requires network access.",
        input_schema=_WEB_FETCH_SCHEMA,
        output_schema=_OUTPUT_OBJECT,
        risk_level="medium",
        requires_approval=True,
        permissions={"network"},
        handler=_handler_web_fetch,
    ),
    ToolSpec(
        name="skill.list",
        description="List available skills with metadata (name, description, status, trust).",
        input_schema=_SKILL_LIST_SCHEMA,
        output_schema=_OUTPUT_LIST,
        risk_level="low",
        requires_approval=False,
        permissions=set(),
        handler=_handler_skill_list,
    ),
    ToolSpec(
        name="skill.invoke",
        description="Invoke a skill by name. Requires approval and trust check.",
        input_schema=_SKILL_INVOKE_SCHEMA,
        output_schema=_OUTPUT_OBJECT,
        risk_level="medium",
        requires_approval=True,
        permissions=set(),
        handler=_handler_skill_invoke,
    ),
]


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all builtin tool specs into the given registry."""
    for spec in BUILTIN_TOOL_SPECS:
        registry.register(spec)
