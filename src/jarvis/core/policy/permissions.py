"""Permission modes and policy enforcement for the Jarvis tool system.

Three built-in permission modes:
- read_only: can read repo files, nothing else
- workspace_write: can read + write + shell, but write/shell need approval
- danger_full_access: can do everything, but still needs approval for write/shell/network
                     and STILL cannot read sensitive files
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
    "danger_full_access": DANGER_FULL_ACCESS,
}


def get_permission_mode(name: str) -> PermissionMode:
    """Get a permission mode by name."""
    return BUILTIN_PERMISSION_MODES.get(name, READ_ONLY)
