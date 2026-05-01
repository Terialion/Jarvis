"""Tests for permission modes."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.policy.permissions import (
    DANGER_FULL_ACCESS,
    READ_ONLY,
    WORKSPACE_WRITE,
    PermissionMode,
    get_permission_mode,
)


class TestPermissionModes:
    def test_read_only_allows_repo_read(self):
        assert READ_ONLY.allows("repo_read") is True

    def test_read_only_disallows_write(self):
        assert READ_ONLY.allows("write") is False

    def test_read_only_disallows_shell(self):
        assert READ_ONLY.allows("shell") is False

    def test_read_only_disallows_network(self):
        assert READ_ONLY.allows("network") is False

    def test_read_only_no_approval_needed(self):
        assert READ_ONLY.needs_approval("write") is False  # not even applicable

    def test_workspace_write_allows_repo_read(self):
        assert WORKSPACE_WRITE.allows("repo_read") is True

    def test_workspace_write_allows_write(self):
        assert WORKSPACE_WRITE.allows("write") is True

    def test_workspace_write_allows_shell(self):
        assert WORKSPACE_WRITE.allows("shell") is True

    def test_workspace_write_disallows_network(self):
        assert WORKSPACE_WRITE.allows("network") is False

    def test_workspace_write_requires_approval_for_write(self):
        assert WORKSPACE_WRITE.needs_approval("write") is True

    def test_workspace_write_requires_approval_for_shell(self):
        assert WORKSPACE_WRITE.needs_approval("shell") is True

    def test_workspace_write_no_approval_for_repo_read(self):
        assert WORKSPACE_WRITE.needs_approval("repo_read") is False

    def test_danger_full_access_allows_everything(self):
        assert DANGER_FULL_ACCESS.allows("repo_read") is True
        assert DANGER_FULL_ACCESS.allows("write") is True
        assert DANGER_FULL_ACCESS.allows("shell") is True
        assert DANGER_FULL_ACCESS.allows("network") is True

    def test_danger_full_access_requires_approval(self):
        assert DANGER_FULL_ACCESS.needs_approval("write") is True
        assert DANGER_FULL_ACCESS.needs_approval("shell") is True
        assert DANGER_FULL_ACCESS.needs_approval("network") is True

    def test_danger_full_access_no_approval_for_read(self):
        assert DANGER_FULL_ACCESS.needs_approval("repo_read") is False

    def test_get_permission_mode_default(self):
        mode = get_permission_mode("nonexistent")
        assert mode is READ_ONLY

    def test_get_permission_mode_by_name(self):
        assert get_permission_mode("read_only") is READ_ONLY
        assert get_permission_mode("workspace_write") is WORKSPACE_WRITE
        assert get_permission_mode("danger_full_access") is DANGER_FULL_ACCESS
