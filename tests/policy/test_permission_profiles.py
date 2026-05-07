from __future__ import annotations

from src.jarvis.core.policy.permissions import PermissionPolicy


def test_read_only_profile_blocks_shell_and_network():
    policy = PermissionPolicy(profile="read_only")
    assert policy.evaluate("repo_reader.read_file", {"path": "README.md"}).action == "allow"
    assert policy.evaluate("command_runner.run", {"command": "python -V"}).action == "deny"
    assert policy.evaluate("web.fetch", {"url": "https://example.com"}).action == "deny"


def test_strict_profile_requires_approval_for_shell_write_network():
    policy = PermissionPolicy(profile="strict")
    assert policy.evaluate("command_runner.run", {"command": "python -V"}).action == "require_approval"
    assert policy.evaluate("file_editor.replace_text", {"path": "a.txt"}).action == "require_approval"
    assert policy.evaluate("web.fetch", {"url": "https://example.com"}).action == "require_approval"
