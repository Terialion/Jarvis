#!/usr/bin/env python
"""Jarvis CLI command mapping registry.

This module is intentionally lightweight and safe to import in tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from difflib import get_close_matches
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class CliCommandSpec:
    name: str
    aliases: List[str]
    category: str
    claude_equivalent: Optional[str]
    description: str
    status: str  # implemented | skeleton | unsupported | deprecated
    safety: str  # safe | ask | approval_required | disabled
    handler: Optional[str]
    examples: List[str] = field(default_factory=list)


def _slash_specs() -> List[CliCommandSpec]:
    specs: List[CliCommandSpec] = [
        CliCommandSpec("/help", [], "misc", "/help", "Show help", "implemented", "safe", "shell_help", ["/help"]),
        CliCommandSpec("/exit", ["/quit"], "session", "/exit", "Exit shell", "implemented", "safe", "shell_exit", ["/exit"]),
        CliCommandSpec("/clear", ["/reset", "/new"], "session", "/clear", "Clear shell context", "implemented", "safe", "shell_clear", ["/clear"]),
        CliCommandSpec("/status", [], "diagnostics", "/status", "Show shell status", "implemented", "safe", "shell_status", ["/status"]),
        CliCommandSpec("/config", [], "config", "/config", "Show masked config", "implemented", "safe", "shell_config", ["/config"]),
        CliCommandSpec("/settings", [], "config", "/settings", "Show masked config", "implemented", "safe", "shell_config", ["/settings"]),
        CliCommandSpec("/tools", [], "skills", "/tools", "List tools and capabilities", "implemented", "safe", "shell_tools", ["/tools"]),
        CliCommandSpec("/skills", [], "skills", "/skills", "List discovered skills", "implemented", "safe", "shell_skills", ["/skills"]),
        CliCommandSpec("/skill", [], "skills", "/skills", "Run or inspect a specific skill command", "implemented", "safe", "shell_skill", ["/skill", "/skill list", "/skill <skill-name> <task>"]),
        CliCommandSpec("/commands", [], "misc", "/commands", "Show command map", "implemented", "safe", "shell_commands", ["/commands", "/commands skills"]),
        CliCommandSpec("/permissions", [], "permissions", "/permissions", "Show current permission policy", "implemented", "safe", "shell_permissions", ["/permissions"]),
        CliCommandSpec("/sandbox-add-read-dir", [], "permissions", "/permissions", "Register an additional read-only sandbox directory", "skeleton", "ask", None, ["/sandbox-add-read-dir D:/tmp"]),
        CliCommandSpec("/allowed-tools", [], "permissions", "/permissions", "Show allowed tools and skills", "implemented", "safe", "shell_allowed_tools", ["/allowed-tools"]),
        CliCommandSpec("/approvals", [], "approval", "/permissions", "List pending approvals", "implemented", "safe", "shell_approvals", ["/approvals"]),
        CliCommandSpec("/approve", [], "approval", "/permissions", "Approve pending action", "implemented", "approval_required", "shell_approve", ["/approve approval_0001"]),
        CliCommandSpec("/reject", [], "approval", "/permissions", "Reject pending action", "implemented", "approval_required", "shell_reject", ["/reject approval_0001"]),
        CliCommandSpec("/mode", [], "permissions", "/permissions", "Set permission mode", "implemented", "ask", "shell_mode", ["/mode safe"]),
        CliCommandSpec("/plan", [], "workflow", "/plan", "Generate plan only", "implemented", "safe", "shell_plan", ["/plan Inspect this repo"]),
        CliCommandSpec("/diff", [], "workflow", "/diff", "Show diff summary", "implemented", "safe", "shell_diff", ["/diff"]),
        CliCommandSpec("/test", [], "workflow", "/test", "Create test run approval or dry-run", "implemented", "approval_required", "shell_test", ["/test"]),
        CliCommandSpec("/fix", [], "workflow", "/fix", "Propose minimal patch and request approval", "implemented", "approval_required", "shell_fix", ["/fix Fix add() bug"]),
        CliCommandSpec("/review", [], "workflow", "/review", "Summarize patch risk and test state", "implemented", "safe", "shell_review", ["/review"]),
        CliCommandSpec("/replay", [], "workflow", "/replay", "Show replay (latest task by default)", "implemented", "safe", "shell_replay", ["/replay", "/replay task_0001"]),
        CliCommandSpec("/evidence", [], "workflow", "/evidence", "Show evidence (latest task by default)", "implemented", "safe", "shell_evidence", ["/evidence", "/evidence task_0001"]),
        CliCommandSpec("/logs", [], "diagnostics", "/logs", "Show log locations", "implemented", "safe", "shell_logs", ["/logs"]),
        CliCommandSpec("/doctor", [], "diagnostics", "/doctor", "Run CLI diagnostics", "implemented", "safe", "shell_doctor", ["/doctor"]),
        CliCommandSpec("/server", [], "remote", "/server", "Show API server hint", "implemented", "safe", "shell_server", ["/server"]),
        CliCommandSpec("/web", ["/app"], "web", "/web", "Show Web UI URL", "implemented", "safe", "shell_web", ["/web"]),
        CliCommandSpec("/tasks", [], "workflow", "/tasks", "List shell tasks", "implemented", "safe", "shell_tasks", ["/tasks"]),
        CliCommandSpec("/state", [], "workflow", "/state", "Show local CLI coding state summary", "implemented", "safe", "shell_state", ["/state"]),
        CliCommandSpec("/trace", [], "diagnostics", "/trace", "Toggle task trace visibility", "implemented", "safe", "shell_trace", ["/trace", "/trace on", "/trace off"]),
        CliCommandSpec("/memory", [], "memory", "/memory", "Memory summary", "implemented", "safe", "shell_memory", ["/memory"]),
        CliCommandSpec("/agents", [], "agents", "/agents", "List agent modes", "implemented", "safe", "shell_agents", ["/agents"]),
    ]
    skeletons = [
        ("/compact", "context"), ("/context", "context"), ("/branch", "workflow"), ("/fork", "workflow"),
        ("/resume", "session"), ("/continue", "session"), ("/export", "workflow"), ("/copy", "workflow"),
        ("/rename", "session"), ("/recap", "session"), ("/model", "model"), ("/effort", "model"),
        ("/fast", "model"), ("/usage", "diagnostics"), ("/cost", "diagnostics"), ("/stats", "diagnostics"),
        ("/sandbox", "permissions"), ("/security-review", "permissions"),
        ("/batch", "workflow"), ("/simplify", "workflow"), ("/hooks", "automation"), ("/mcp", "misc"),
        ("/debug", "diagnostics"), ("/plugin", "plugin"), ("/reload-plugins", "plugin"), ("/init", "misc"),
        ("/jarvis-api", "remote"), ("/remote-control", "remote"), ("/rc", "remote"), ("/web-setup", "web"),
        ("/add-dir", "permissions"), ("/btw", "misc"), ("/bashes", "misc"),
    ]
    for name, category in skeletons:
        specs.append(
            CliCommandSpec(
                name=name,
                aliases=[],
                category=category,
                claude_equivalent=name,
                description="Recognized command skeleton",
                status="skeleton",
                safety="ask",
                handler=None,
                examples=[name],
            )
        )
    unsupported = [
        "/ultrareview", "/autofix-pr", "/install-github-app", "/install-slack-app", "/feedback", "/bug",
        "/release-notes", "/profile", "/team-onboarding", "/insights", "/remote-env", "/teleport", "/tp",
        "/mobile", "/ios", "/android", "/chrome", "/loop", "/proactive", "/schedule", "/routines",
        "/ultraplan", "/powerup", "/setup-bedrock", "/setup-vertex", "/login", "/logout", "/ide",
        "/voice", "/color", "/theme", "/statusline", "/tui", "/focus", "/keybindings", "/terminal-setup",
        "/fewer-permission-prompts", "/privacy-settings",
    ]
    for name in unsupported:
        specs.append(
            CliCommandSpec(
                name=name,
                aliases=[],
                category="misc",
                claude_equivalent=name,
                description="Unsupported in current Jarvis CLI",
                status="unsupported",
                safety="disabled",
                handler=None,
                examples=[name],
            )
        )
    return specs


def _external_specs() -> List[CliCommandSpec]:
    return [
        CliCommandSpec("auth", [], "provider", "auth", "Auth status and setup", "implemented", "safe", "cmd_auth", ["auth status"]),
        CliCommandSpec("config", [], "config", "config", "Show and manage config", "implemented", "safe", "cmd_config", ["config --show"]),
        CliCommandSpec("tools", [], "skills", "tools", "List tools/capabilities", "implemented", "safe", "cmd_tools", ["tools --debug"]),
        CliCommandSpec("skills", [], "skills", "skills", "List discovered skills", "implemented", "safe", "cmd_skills", ["skills --debug"]),
        CliCommandSpec("commands", [], "misc", "help", "Show command mapping", "implemented", "safe", "cmd_commands", ["commands --json"]),
        CliCommandSpec("test", [], "workflow", "test", "Run local self-check", "implemented", "approval_required", "cmd_test", ["test"]),
        CliCommandSpec("server", [], "remote", "server", "API server commands", "implemented", "ask", "cmd_server", ["server status"]),
        CliCommandSpec("task", [], "workflow", "task", "Task lifecycle commands", "implemented", "ask", "cmd_task", ["task run \"Inspect repo\" --safe"]),
        CliCommandSpec("approvals", [], "approval", "permissions", "Approval queue commands", "implemented", "approval_required", "cmd_approvals", ["approvals list"]),
        CliCommandSpec("state", [], "workflow", "state", "Show local CLI coding state summary", "implemented", "safe", "cmd_state", ["state"]),
        CliCommandSpec("diff", [], "workflow", "diff", "Show latest local diff summary", "implemented", "safe", "cmd_diff", ["diff"]),
        CliCommandSpec("review", [], "workflow", "review", "Show latest local review summary", "implemented", "safe", "cmd_review", ["review"]),
        CliCommandSpec("replay", [], "workflow", "replay", "Replay commands", "implemented", "safe", "cmd_replay", ["replay show task_0001"]),
        CliCommandSpec("evidence", [], "workflow", "evidence", "Evidence commands", "implemented", "safe", "cmd_evidence", ["evidence show task_0001"]),
        CliCommandSpec("agents", [], "agents", "agents", "Agent commands", "implemented", "safe", "cmd_agents", ["agents"]),
        CliCommandSpec("memory", [], "memory", "memory", "Memory commands", "skeleton", "safe", None, ["memory"]),
        CliCommandSpec("mcp", [], "misc", "mcp", "MCP commands", "implemented", "safe", "cmd_mcp", ["mcp"]),
        CliCommandSpec("plugin", [], "plugin", "plugin", "Plugin commands", "implemented", "ask", "cmd_plugin", ["plugin"]),
        CliCommandSpec("update", [], "misc", "update", "CLI update command", "implemented", "ask", "cmd_update", ["update --dry-run"]),
        CliCommandSpec("doctor", [], "diagnostics", "doctor", "Diagnostics command", "implemented", "safe", "shell_doctor", ["doctor"]),
        CliCommandSpec("logs", [], "diagnostics", "logs", "Log command", "implemented", "safe", "shell_logs", ["logs"]),
        CliCommandSpec("web", [], "web", "web", "Web control surface hint", "skeleton", "safe", None, ["web"]),
    ]


_COMMAND_SPECS: List[CliCommandSpec] = _slash_specs() + _external_specs()


def list_command_specs(category: Optional[str] = None) -> List[CliCommandSpec]:
    if not category:
        return list(_COMMAND_SPECS)
    needle = category.strip().lower()
    return [spec for spec in _COMMAND_SPECS if spec.category.lower() == needle]


def resolve_command(name: str) -> Optional[CliCommandSpec]:
    needle = (name or "").strip().lower()
    if not needle:
        return None
    alias_map: Dict[str, CliCommandSpec] = {}
    for spec in _COMMAND_SPECS:
        alias_map[spec.name.lower()] = spec
        for alias in spec.aliases:
            alias_map[alias.lower()] = spec
    return alias_map.get(needle)


def suggest_commands(name: str, limit: int = 3) -> List[str]:
    needle = name.strip().lower()
    slash_only = needle.startswith("/")
    names = sorted({spec.name for spec in _COMMAND_SPECS if not slash_only or spec.name.startswith("/")})
    matches = get_close_matches(needle, [n.lower() for n in names], n=max(limit * 3, limit))
    deduped: List[str] = []
    seen: set[str] = set()
    for item in matches:
        display = item if item.startswith("/") or not slash_only else f"/{item}"
        if display in seen:
            continue
        seen.add(display)
        deduped.append(display)
        if len(deduped) >= limit:
            break
    return deduped


def command_specs_json(category: Optional[str] = None) -> List[Dict[str, object]]:
    return [asdict(spec) for spec in list_command_specs(category)]


def render_command_table(specs: Iterable[CliCommandSpec]) -> str:
    rows = list(specs)
    lines = [
        "Jarvis Command Map",
        "------------------",
        "name                 category      status        safety              claude_equivalent",
        "-------------------- ------------ ------------- ------------------- -------------------",
    ]
    for spec in rows:
        lines.append(
            f"{spec.name[:20]:<20} {spec.category[:12]:<12} {spec.status[:13]:<13} {spec.safety[:19]:<19} {(spec.claude_equivalent or '-'): <19}"
        )
    return "\n".join(lines)
