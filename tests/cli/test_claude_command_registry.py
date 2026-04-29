"""Tests for CLI command mapping registry."""

from jarvis.cli_command_map import command_specs_json, list_command_specs, resolve_command


def test_command_registry_non_empty():
    specs = list_command_specs()
    assert specs


def test_p0_commands_exist():
    required = [
        "/help",
        "/exit",
        "/clear",
        "/status",
        "/config",
        "/settings",
        "/tools",
        "/skills",
        "/commands",
        "/permissions",
        "/allowed-tools",
        "/approvals",
        "/approve",
        "/reject",
        "/mode",
        "/plan",
        "/diff",
        "/test",
        "/replay",
        "/evidence",
        "/logs",
        "/doctor",
        "/server",
        "/web",
        "/tasks",
        "/memory",
        "/agents",
    ]
    names = {spec.name for spec in list_command_specs()}
    for cmd in required:
        assert cmd in names


def test_aliases_resolve():
    assert resolve_command("/quit").name == "/exit"
    assert resolve_command("/reset").name == "/clear"
    assert resolve_command("/new").name == "/clear"
    assert resolve_command("/app").name == "/web"


def test_command_json_shape():
    rows = command_specs_json()
    assert isinstance(rows, list) and rows
    sample = rows[0]
    for key in ["name", "aliases", "category", "status", "safety", "description"]:
        assert key in sample

