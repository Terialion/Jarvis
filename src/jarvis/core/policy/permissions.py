"""Permission modes and Phase 16 policy enforcement for the Jarvis tool system.

This module keeps the older PermissionMode compatibility API while adding the
Phase 16 PermissionPolicy layer used by ToolCallExecutor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from typing import Any, Literal
from urllib.parse import urlparse

from ...agent.types import _redact_value


@dataclass(frozen=True)
class PermissionMode:
    """Defines what actions are allowed and which require approval."""

    name: str
    allow_repo_read: bool
    allow_write: bool
    allow_shell: bool
    allow_network: bool
    approval_required_for: set[str]

    def allows(self, permission: str) -> bool:
        """Check if a specific permission is allowed in this mode."""
        if permission == "repo_read":
            return self.allow_repo_read
        if permission == "write":
            return self.allow_write
        if permission == "shell":
            return self.allow_shell
        if permission == "network":
            return self.allow_network
        return False

    def needs_approval(self, permission: str) -> bool:
        """Check if a permission requires approval in this mode."""
        return permission in self.approval_required_for


READ_ONLY = PermissionMode(
    name="read_only",
    allow_repo_read=True,
    allow_write=False,
    allow_shell=False,
    allow_network=False,
    approval_required_for=set(),
)

WORKSPACE_WRITE = PermissionMode(
    name="workspace_write",
    allow_repo_read=True,
    allow_write=True,
    allow_shell=True,
    allow_network=False,
    approval_required_for={"write", "shell"},
)

WORKSPACE_WRITE_NETWORK = PermissionMode(
    name="workspace_write_network",
    allow_repo_read=True,
    allow_write=True,
    allow_shell=True,
    allow_network=True,
    approval_required_for={"write", "shell", "network"},
)

DANGER_FULL_ACCESS = PermissionMode(
    name="danger_full_access",
    allow_repo_read=True,
    allow_write=True,
    allow_shell=True,
    allow_network=True,
    approval_required_for={"write", "shell", "network"},
)

BUILTIN_PERMISSION_MODES = {
    "read_only": READ_ONLY,
    "workspace_write": WORKSPACE_WRITE,
    "workspace_write_network": WORKSPACE_WRITE_NETWORK,
    "danger_full_access": DANGER_FULL_ACCESS,
}


def get_permission_mode(name: str) -> PermissionMode:
    """Get a permission mode by name."""
    return BUILTIN_PERMISSION_MODES.get(name, READ_ONLY)


PermissionAction = Literal["allow", "deny", "require_approval"]
RiskLevel = Literal["low", "medium", "high", "critical"]
PolicyProfile = Literal["read_only", "default", "default_network", "strict", "dangerous"]


def redact_args_preview(arguments: dict[str, Any] | None) -> dict[str, Any]:
    return dict(_redact_value(dict(arguments or {})))


@dataclass(frozen=True)
class ToolRule:
    tool_name: str
    action: PermissionAction
    risk_level: RiskLevel
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DomainRule:
    domain_pattern: str
    action: PermissionAction
    reason: str | None = None

    def matches(self, host: str) -> bool:
        host = str(host or "").strip().lower()
        if not host:
            return False
        pattern = self.domain_pattern.strip().lower()
        if not pattern:
            return False
        if pattern.startswith("*."):
            suffix = pattern[1:]
            return host.endswith(suffix)
        return fnmatch(host, pattern) or host == pattern

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PermissionDecision:
    action: PermissionAction
    reason: str
    risk_level: RiskLevel
    tool_name: str
    redacted_args_preview: dict[str, Any] | str | None = None
    rule_id: str | None = None
    domain: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass(frozen=True)
class ToolProfile:
    name: PolicyProfile
    default_action: PermissionAction
    tool_defaults: dict[str, ToolRule] = field(default_factory=dict)
    domain_defaults: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


def _tool_category(tool_name: str) -> str:
    if tool_name.startswith("repo_reader."):
        return "read"
    if tool_name.startswith("file_editor."):
        return "write"
    if tool_name in {"command_runner.run", "test_runner.run_test"}:
        return "shell"
    if tool_name.startswith("web."):
        return "network"
    if tool_name.startswith("checkpoint."):
        return "write"
    if tool_name.startswith("memory."):
        return "write"
    if tool_name.startswith("task."):
        return "write"
    if tool_name.startswith("skill."):
        return "read"
    if tool_name.startswith("mcp."):
        return "network"
    if tool_name.startswith("bg.task."):
        return "shell"
    if tool_name.startswith("agent."):
        return "read"
    return "read"  # safe default


def _profile_defaults(profile: PolicyProfile) -> ToolProfile:
    if profile == "read_only":
        return ToolProfile(
            name="read_only",
            default_action="deny",
            tool_defaults={
                "repo_reader.read_file": ToolRule("repo_reader.read_file", "allow", "low", "Read-only profile allows file reads."),
                "repo_reader.search_files": ToolRule("repo_reader.search_files", "allow", "low", "Read-only profile allows repository search."),
                "skill.load": ToolRule("skill.load", "allow", "low", "Read-only profile allows skill document loading."),
                "file_editor.replace_text": ToolRule("file_editor.replace_text", "deny", "high", "Read-only profile blocks file edits."),
                "command_runner.run": ToolRule("command_runner.run", "deny", "high", "Read-only profile blocks shell commands."),
                "test_runner.run_test": ToolRule("test_runner.run_test", "deny", "high", "Read-only profile blocks test execution."),
                "web.search": ToolRule("web.search", "deny", "medium", "Read-only profile blocks network search."),
                "web.fetch": ToolRule("web.fetch", "deny", "medium", "Read-only profile blocks network fetch."),
                "web.browse": ToolRule("web.browse", "deny", "medium", "Read-only profile blocks browser."),
            },
            domain_defaults={"unknown_action": "deny"},
        )
    if profile == "strict":
        return ToolProfile(
            name="strict",
            default_action="deny",
            tool_defaults={
                "repo_reader.read_file": ToolRule("repo_reader.read_file", "allow", "low", "Strict profile allows safe reads."),
                "repo_reader.search_files": ToolRule("repo_reader.search_files", "allow", "low", "Strict profile allows repository search."),
                "skill.load": ToolRule("skill.load", "allow", "low", "Strict profile allows skill loading."),
                "web.search": ToolRule("web.search", "allow", "medium", "Strict profile allows search planning."),
                "web.fetch": ToolRule("web.fetch", "require_approval", "medium", "Strict profile requires approval for web fetch by default."),
                "web.browse": ToolRule("web.browse", "require_approval", "medium", "Strict profile requires approval for browser."),
                "test_runner.run_test": ToolRule("test_runner.run_test", "require_approval", "high", "Strict profile requires approval for test execution."),
                "command_runner.run": ToolRule("command_runner.run", "require_approval", "high", "Strict profile requires approval for shell commands."),
                "file_editor.replace_text": ToolRule("file_editor.replace_text", "require_approval", "high", "Strict profile requires approval for file edits."),
            },
            domain_defaults={"unknown_action": "require_approval"},
        )
    if profile == "default_network":
        return ToolProfile(
            name="default_network",
            default_action="allow",
            tool_defaults={
                "command_runner.run": ToolRule("command_runner.run", "require_approval", "high", "Default+network profile requires approval for shell commands."),
                "test_runner.run_test": ToolRule("test_runner.run_test", "require_approval", "high", "Default+network profile requires approval for test execution."),
                "file_editor.write_file": ToolRule("file_editor.write_file", "require_approval", "high", "Default+network profile requires approval for file writes."),
                "file_editor.insert_text": ToolRule("file_editor.insert_text", "require_approval", "high", "Default+network profile requires approval for file edits."),
                "file_editor.replace_text": ToolRule("file_editor.replace_text", "require_approval", "high", "Default+network profile requires approval for file edits."),
                "file_editor.diff": ToolRule("file_editor.diff", "allow", "low", "Default+network profile allows diff viewing."),
                "checkpoint.create": ToolRule("checkpoint.create", "allow", "medium", "Default+network profile allows checkpoint creation."),
                "checkpoint.rollback": ToolRule("checkpoint.rollback", "require_approval", "high", "Default+network profile requires approval for rollback."),
                "web.search": ToolRule("web.search", "require_approval", "medium", "Default+network profile requires approval for web search."),
                "web.fetch": ToolRule("web.fetch", "require_approval", "medium", "Default+network profile requires approval for web fetch."),
                "web.browse": ToolRule("web.browse", "require_approval", "medium", "Default+network profile requires approval for browser."),
            },
            domain_defaults={"unknown_action": "require_approval"},
        )
    if profile == "dangerous":
        return ToolProfile(
            name="dangerous",
            default_action="allow",
            tool_defaults={
                "repo_reader.read_file": ToolRule("repo_reader.read_file", "allow", "low", "Dangerous profile allows reads."),
                "repo_reader.search_files": ToolRule("repo_reader.search_files", "allow", "low", "Dangerous profile allows search."),
                "skill.load": ToolRule("skill.load", "allow", "low", "Dangerous profile allows skill loading."),
                "web.search": ToolRule("web.search", "allow", "medium", "Dangerous profile allows search."),
                "web.fetch": ToolRule("web.fetch", "allow", "medium", "Dangerous profile allows fetch on safe URLs."),
                "web.browse": ToolRule("web.browse", "allow", "medium", "Dangerous profile allows browser."),
                "test_runner.run_test": ToolRule("test_runner.run_test", "allow", "high", "Dangerous profile allows test execution."),
                "command_runner.run": ToolRule("command_runner.run", "allow", "high", "Dangerous profile allows shell commands."),
                "file_editor.replace_text": ToolRule("file_editor.replace_text", "allow", "high", "Dangerous profile allows file edits."),
            },
            domain_defaults={"unknown_action": "allow"},
        )
    return ToolProfile(
        name="default",
        default_action="allow",
        tool_defaults={
            "command_runner.run": ToolRule("command_runner.run", "require_approval", "high", "Default profile requires approval for shell commands."),
            "test_runner.run_test": ToolRule("test_runner.run_test", "require_approval", "high", "Default profile requires approval for test execution."),
            "file_editor.write_file": ToolRule("file_editor.write_file", "require_approval", "high", "Default profile requires approval for file writes."),
            "file_editor.insert_text": ToolRule("file_editor.insert_text", "require_approval", "high", "Default profile requires approval for file edits."),
            "file_editor.replace_text": ToolRule("file_editor.replace_text", "require_approval", "high", "Default profile requires approval for file edits."),
            "file_editor.diff": ToolRule("file_editor.diff", "allow", "low", "Default profile allows diff viewing."),
            "checkpoint.create": ToolRule("checkpoint.create", "allow", "medium", "Default profile allows checkpoint creation."),
            "checkpoint.rollback": ToolRule("checkpoint.rollback", "require_approval", "high", "Default profile requires approval for rollback."),
        },
        domain_defaults={"unknown_action": "allow"},
    )


class PermissionPolicy:
    """Phase 16 permission policy for tool execution."""

    def __init__(
        self,
        *,
        profile: PolicyProfile = "default",
        tool_rules: list[ToolRule] | None = None,
        domain_rules: list[DomainRule] | None = None,
        default_action: PermissionAction | None = None,
    ) -> None:
        self.profile = profile
        defaults = _profile_defaults(profile)
        merged: dict[str, ToolRule] = dict(defaults.tool_defaults)
        for rule in tool_rules or []:
            merged[rule.tool_name] = rule
        self.tool_rules = list(merged.values())
        self._tool_rules = merged
        self.domain_rules = list(domain_rules or [])
        self.default_action = default_action or defaults.default_action
        self.domain_default_action = str(defaults.domain_defaults.get("unknown_action") or "allow")

    @classmethod
    def from_permission_mode(cls, permission_mode: str) -> "PermissionPolicy":
        mapping = {
            "read_only": "read_only",
            "workspace_write": "default",
            "workspace_write_network": "default_network",
            "danger_full_access": "dangerous",
        }
        profile = mapping.get(str(permission_mode or "").strip().lower(), "default")
        return cls(profile=profile)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "default_action": self.default_action,
            "tool_rules": [row.to_dict() for row in self.tool_rules],
            "domain_rules": [row.to_dict() for row in self.domain_rules],
        }

    def evaluate(self, tool_name: str, arguments: dict[str, Any] | None = None) -> PermissionDecision:
        preview = redact_args_preview(arguments)
        rule = self._tool_rules.get(tool_name)
        if rule is not None:
            return PermissionDecision(
                action=rule.action,
                reason=rule.reason or f"Matched tool rule for {tool_name}.",
                risk_level=rule.risk_level,
                rule_id=f"tool:{tool_name}",
                tool_name=tool_name,
                redacted_args_preview=preview,
                metadata={"category": _tool_category(tool_name)},
            )
        fallback_risk: RiskLevel = "medium" if _tool_category(tool_name) in {"shell", "write", "network"} else "low"
        return PermissionDecision(
            action=self.default_action,
            reason=f"No explicit rule for {tool_name}; using profile default.",
            risk_level=fallback_risk,
            tool_name=tool_name,
            redacted_args_preview=preview,
            metadata={"category": _tool_category(tool_name)},
        )

    def evaluate_domain(self, url: str, *, tool_name: str = "web.fetch", arguments: dict[str, Any] | None = None) -> PermissionDecision:
        parsed = urlparse(str(url or "").strip())
        host = (parsed.hostname or "").strip().lower()
        preview = redact_args_preview(arguments or {"url": url})
        for rule in self.domain_rules:
            if rule.matches(host):
                return PermissionDecision(
                    action=rule.action,
                    reason=rule.reason or f"Matched domain rule for {host}.",
                    risk_level="medium",
                    rule_id=f"domain:{rule.domain_pattern}",
                    tool_name=tool_name,
                    domain=host,
                    redacted_args_preview=preview,
                )
        return PermissionDecision(
            action=self.domain_default_action,  # type: ignore[arg-type]
            reason=f"No explicit domain rule for {host}; using {self.profile} domain default.",
            risk_level="medium",
            tool_name=tool_name,
            domain=host,
            redacted_args_preview=preview,
            metadata={"domain_default": True},
        )
