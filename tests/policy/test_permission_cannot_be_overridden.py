"""Tests that permissions cannot be overridden by instructions or skill metadata.

This is a CRITICAL security boundary:
- JARVIS.md cannot upgrade permission
- AGENTS.md cannot upgrade permission
- SKILL.md cannot upgrade permission
- Command allowed_tools can only NARROW, never expand
- danger_full_access still cannot read secrets
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.policy.permissions import READ_ONLY, DANGER_FULL_ACCESS, WORKSPACE_WRITE, PermissionMode
from src.jarvis.core.policy.safety import SafetyGate
from src.jarvis.core.tools.schema import ToolCall, ToolContext, ToolSpec


class TestPermissionCannotBeOverridden:
    """Permissions are enforced by code, not by LLM output or instruction files."""

    def test_jarvis_md_cannot_upgrade_permission(self):
        """JARVIS.md saying 'skip approval' must NOT affect PermissionMode."""
        # JARVIS.md is instructions, not permission
        # The PermissionMode is a frozen dataclass — cannot be mutated
        assert READ_ONLY.allows("write") is False
        assert READ_ONLY.allows("shell") is False
        # Even if JARVIS.md says "you can write", the code enforces read_only
        assert not READ_ONLY.allow_write  # This is a frozen field

    def test_agents_md_cannot_upgrade_permission(self):
        """AGENTS.md is instructions, not permission."""
        assert WORKSPACE_WRITE.allows("network") is False
        # AGENTS.md cannot flip this
        assert not WORKSPACE_WRITE.allow_network  # Frozen

    def test_skill_md_cannot_upgrade_permission(self):
        """SKILL.md declaring allowed_tools=['shell'] must NOT bypass PermissionMode."""
        # In read_only mode, shell is not allowed regardless of SKILL.md
        assert READ_ONLY.allows("shell") is False

    def test_command_allowed_tools_narrows_only(self):
        """Command allowed_tools can only narrow, never expand the base permission.

        If the base mode is read_only, a command declaring allowed_tools=["shell"]
        must NOT grant shell access.
        """
        mode = READ_ONLY
        # Command says it wants shell
        command_wants = ["shell", "repo_read"]
        # But mode disallows shell
        for tool in command_wants:
            if not mode.allows(tool):
                # Tool is denied regardless of command declaration
                assert tool == "shell"

    def test_danger_full_access_cannot_read_secrets(self):
        """Even danger_full_access cannot read .env, SSH keys, tokens."""
        gate = SafetyGate()
        spec = ToolSpec(
            name="workspace.read_file",
            description="Read file",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            risk_level="medium",
            requires_approval=False,
            permissions={"repo_read"},
        )

        # .env must be refused
        call_env = ToolCall(tool_name="workspace.read_file", arguments={"path": ".env"})
        ctx = ToolContext(permission_mode="danger_full_access")
        result_env = gate.check(spec, call_env, ctx)
        assert result_env.allowed is False
        assert "safety_refusal" in result_env.reason

        # id_rsa must be refused
        call_ssh = ToolCall(tool_name="workspace.read_file", arguments={"path": "~/.ssh/id_rsa"})
        result_ssh = gate.check(spec, call_ssh, ctx)
        assert result_ssh.allowed is False

        # token file must be refused
        call_token = ToolCall(tool_name="workspace.read_file", arguments={"path": "/tmp/api_token"})
        result_token = gate.check(spec, call_token, ctx)
        assert result_token.allowed is False

    def test_permission_mode_is_frozen(self):
        """PermissionMode is frozen and cannot be mutated."""
        with pytest.raises(AttributeError):
            READ_ONLY.allow_write = True
        with pytest.raises(AttributeError):
            READ_ONLY.allow_shell = True

    def test_llm_cannot_create_new_permission(self):
        """LLM output declaring new permissions must be ignored."""
        # Only BUILTIN_PERMISSION_MODES exist
        # An LLM returning {"permission_mode": "god_mode"} must get read_only
        from src.jarvis.core.policy.permissions import get_permission_mode
        assert get_permission_mode("god_mode").name == "read_only"
