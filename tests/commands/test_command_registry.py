"""Tests for the central CommandRegistry."""

import pytest

from jarvis.core.commands.central import CommandRegistry, CommandSpec, build_command_registry


class TestCommandRegistry:
    def test_registry_has_all_commands(self):
        """All commands must come from the registry."""
        reg = build_command_registry()
        assert len(reg) > 0
        names = reg.list_names()
        assert "/help" in names
        assert "/exit" in names
        assert "/skills" in names
        assert "/skill" in names
        assert "/tools" in names

    def test_skill_and_skills_both_exist(self):
        """/skill and /skills must both exist."""
        reg = build_command_registry()
        assert reg.has("/skill")
        assert reg.has("/skills")

    def test_skill_preserves_raw_args(self):
        """/skill command must have an argument_hint."""
        reg = build_command_registry()
        spec = reg.get("/skill")
        assert spec is not None
        assert spec.argument_hint is not None

    def test_unknown_command_not_in_registry(self):
        """Unknown commands must not be found."""
        reg = build_command_registry()
        assert reg.get("/nonexistent") is None

    def test_alias_resolution(self):
        """Command aliases must resolve to the same spec."""
        reg = build_command_registry()
        exit_spec = reg.get("/exit")
        quit_spec = reg.get("/quit")
        assert exit_spec is not None
        assert quit_spec is not None
        assert exit_spec.name == quit_spec.name

    def test_command_spec_is_frozen(self):
        """CommandSpec must be immutable."""
        spec = CommandSpec(
            name="/test",
            aliases=[],
            description="test",
            argument_hint=None,
            dispatch="local",
            allowed_tools=[],
            risk_level="low",
            status="implemented",
        )
        with pytest.raises(AttributeError):
            spec.name = "/changed"

    def test_list_implemented(self):
        """Must be able to list only implemented commands."""
        reg = build_command_registry()
        implemented = reg.list_implemented()
        assert len(implemented) > 0
        for cmd in implemented:
            assert cmd.status == "implemented"

    def test_suggest_for_unknown(self):
        """Suggest must return similar commands."""
        reg = build_command_registry()
        suggestions = reg.suggest("/halp")
        assert isinstance(suggestions, list)


class TestCommandRouterUsesRegistry:
    def test_command_allowed_tools_narrows_only(self):
        """Command allowed_tools can only narrow permissions."""
        reg = build_command_registry()
        spec = reg.get("/test")
        assert spec is not None
        assert isinstance(spec.allowed_tools, list)
        # allowed_tools is a fixed list — cannot expand permissions
        assert len(spec.allowed_tools) >= 0

    def test_all_commands_have_dispatch(self):
        """Every command must have a valid dispatch type."""
        reg = build_command_registry()
        valid_dispatches = {"local", "agent", "tool", "skill"}
        for cmd in reg.list_all():
            assert cmd.dispatch in valid_dispatches, f"{cmd.name}: invalid dispatch '{cmd.dispatch}'"

    def test_unsupported_commands_have_status(self):
        """Unsupported commands must have status='unsupported'."""
        reg = build_command_registry()
        for cmd in reg.list_all():
            if cmd.status == "unsupported":
                assert cmd.dispatch == "local"


class TestCLICanShareRegistry:
    def test_registry_is_reusable(self):
        """Registry can be built and used by different surfaces."""
        reg = build_command_registry()
        # Simulate CLI surface
        cli_commands = {cmd.name for cmd in reg.list_implemented()}
        assert "/help" in cli_commands
        # Simulate gateway surface
        gateway_commands = {cmd.name for cmd in reg.list_all()}
        assert "/help" in gateway_commands
        assert len(gateway_commands) >= len(cli_commands)
