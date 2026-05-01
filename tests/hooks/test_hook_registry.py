"""Tests for HookRegistry — independent registry for pre/post tool use hooks.

Covers: register_spec, list_specs, matcher, pre/post hook execution.
"""

from __future__ import annotations

import pytest

from src.jarvis.core.hooks.schema import HookResult, HookSpec
from src.jarvis.core.hooks.registry import HookRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _allow_handler(**kw):
    return HookResult(allowed=True)


def _deny_handler(**kw):
    return HookResult(allowed=False, reason="blocked by hook")


def _raise_handler(**kw):
    raise RuntimeError("hook exploded")


# ---------------------------------------------------------------------------
# register_spec
# ---------------------------------------------------------------------------

class TestRegisterSpec:
    def test_register_spec_success(self):
        reg = HookRegistry()
        spec = HookSpec(name="test-hook", stage="pre_tool_use")
        result = reg.register_spec(spec)
        assert result["ok"] is True
        assert result["data"]["name"] == "test-hook"
        assert result["data"]["stage"] == "pre_tool_use"

    def test_register_multiple_specs(self):
        reg = HookRegistry()
        reg.register_spec(HookSpec(name="h1", stage="pre_tool_use"))
        reg.register_spec(HookSpec(name="h2", stage="post_tool_use"))
        assert len(reg.list_specs()) == 2


# ---------------------------------------------------------------------------
# list_specs
# ---------------------------------------------------------------------------

class TestListSpecs:
    def test_list_specs(self):
        reg = HookRegistry()
        s1 = HookSpec(name="a", stage="pre_tool_use")
        s2 = HookSpec(name="b", stage="post_tool_use")
        reg.register_spec(s1)
        reg.register_spec(s2)
        specs = reg.list_specs()
        assert len(specs) == 2
        assert specs[0].name == "a"
        assert specs[1].name == "b"

    def test_list_specs_empty(self):
        reg = HookRegistry()
        assert reg.list_specs() == []


# ---------------------------------------------------------------------------
# HookSpec.matches
# ---------------------------------------------------------------------------

class TestHookSpecMatcher:
    def test_matcher_empty_matches_all(self):
        spec = HookSpec(name="universal", stage="pre_tool_use", matcher={})
        assert spec.matches(tool_name="anything") is True
        assert spec.matches(tool_name="shell.run") is True
        assert spec.matches() is True

    def test_matcher_tool_name_exact(self):
        spec = HookSpec(
            name="deny-shell",
            stage="pre_tool_use",
            matcher={"tool_name": "shell.run"},
        )
        assert spec.matches(tool_name="shell.run") is True
        assert spec.matches(tool_name="workspace.status") is False

    def test_matcher_risk_level(self):
        spec = HookSpec(
            name="high-risk-audit",
            stage="post_tool_use",
            matcher={"risk_level": "high"},
        )
        assert spec.matches(risk_level="high") is True
        assert spec.matches(risk_level="low") is False
        assert spec.matches(risk_level="medium") is False

    def test_matcher_permission(self):
        spec = HookSpec(
            name="write-audit",
            stage="pre_tool_use",
            matcher={"permission": "write"},
        )
        assert spec.matches(permission="write") is True
        assert spec.matches(permission="repo_read") is False

    def test_matcher_multiple_fields(self):
        spec = HookSpec(
            name="shell-write-audit",
            stage="pre_tool_use",
            matcher={"tool_name": "shell.run", "risk_level": "high"},
        )
        assert spec.matches(tool_name="shell.run", risk_level="high") is True
        assert spec.matches(tool_name="shell.run", risk_level="low") is False
        assert spec.matches(tool_name="workspace.status", risk_level="high") is False


# ---------------------------------------------------------------------------
# get_pre_tool_hooks / get_post_tool_hooks
# ---------------------------------------------------------------------------

class TestGetHooks:
    def test_pre_tool_hooks_matching(self):
        reg = HookRegistry()
        spec = HookSpec(
            name="deny-shell",
            stage="pre_tool_use",
            matcher={"tool_name": "shell.run"},
            handler=_deny_handler,
        )
        reg.register_spec(spec)
        matches = reg.get_pre_tool_hooks(tool_name="shell.run")
        assert len(matches) == 1
        assert matches[0].name == "deny-shell"

    def test_pre_tool_hooks_non_matching(self):
        reg = HookRegistry()
        spec = HookSpec(
            name="deny-shell",
            stage="pre_tool_use",
            matcher={"tool_name": "shell.run"},
            handler=_deny_handler,
        )
        reg.register_spec(spec)
        matches = reg.get_pre_tool_hooks(tool_name="workspace.status")
        assert matches == []

    def test_post_tool_hooks_matching(self):
        reg = HookRegistry()
        spec = HookSpec(
            name="audit-dir",
            stage="post_tool_use",
            matcher={"tool_name": "workspace.list_dir"},
            handler=_allow_handler,
        )
        reg.register_spec(spec)
        matches = reg.get_post_tool_hooks(tool_name="workspace.list_dir")
        assert len(matches) == 1

    def test_post_tool_hooks_non_matching(self):
        reg = HookRegistry()
        spec = HookSpec(
            name="audit-dir",
            stage="post_tool_use",
            matcher={"tool_name": "workspace.list_dir"},
            handler=_allow_handler,
        )
        reg.register_spec(spec)
        matches = reg.get_post_tool_hooks(tool_name="shell.run")
        assert matches == []

    def test_stage_filtering(self):
        reg = HookRegistry()
        reg.register_spec(HookSpec(name="pre-h", stage="pre_tool_use"))
        reg.register_spec(HookSpec(name="post-h", stage="post_tool_use"))
        assert len(reg.get_pre_tool_hooks()) == 1
        assert len(reg.get_post_tool_hooks()) == 1


# ---------------------------------------------------------------------------
# run_pre_tool_use
# ---------------------------------------------------------------------------

class TestRunPreToolUse:
    def test_run_pre_tool_use_allows_when_no_hooks(self):
        reg = HookRegistry()
        result = reg.run_pre_tool_use(tool_name="workspace.status")
        assert result.allowed is True

    def test_run_pre_tool_use_allows_when_hook_allows(self):
        reg = HookRegistry()
        reg.register_spec(HookSpec(
            name="allow", stage="pre_tool_use", handler=_allow_handler,
        ))
        result = reg.run_pre_tool_use(tool_name="workspace.status")
        assert result.allowed is True

    def test_run_pre_tool_use_denies(self):
        reg = HookRegistry()
        reg.register_spec(HookSpec(
            name="deny", stage="pre_tool_use", handler=_deny_handler,
        ))
        result = reg.run_pre_tool_use(tool_name="shell.run")
        assert result.allowed is False
        assert result.reason == "blocked by hook"

    def test_run_pre_tool_use_exception_is_denial(self):
        reg = HookRegistry()
        reg.register_spec(HookSpec(
            name="exploder", stage="pre_tool_use", handler=_raise_handler,
        ))
        result = reg.run_pre_tool_use(tool_name="shell.run")
        assert result.allowed is False
        assert "exploder" in result.reason
        assert "RuntimeError" in result.reason

    def test_run_pre_tool_use_skips_none_handler(self):
        reg = HookRegistry()
        reg.register_spec(HookSpec(
            name="no-handler", stage="pre_tool_use", handler=None,
        ))
        result = reg.run_pre_tool_use(tool_name="shell.run")
        assert result.allowed is True

    def test_run_pre_tool_use_first_denial_wins(self):
        reg = HookRegistry()
        reg.register_spec(HookSpec(
            name="deny1", stage="pre_tool_use",
            matcher={"tool_name": "shell.run"},
            handler=_deny_handler,
        ))
        reg.register_spec(HookSpec(
            name="allow1", stage="pre_tool_use",
            matcher={"tool_name": "shell.run"},
            handler=_allow_handler,
        ))
        result = reg.run_pre_tool_use(tool_name="shell.run")
        assert result.allowed is False

    def test_run_pre_tool_use_non_matching_not_called(self):
        reg = HookRegistry()
        reg.register_spec(HookSpec(
            name="deny-shell", stage="pre_tool_use",
            matcher={"tool_name": "shell.run"},
            handler=_deny_handler,
        ))
        result = reg.run_pre_tool_use(tool_name="workspace.status")
        assert result.allowed is True


# ---------------------------------------------------------------------------
# run_post_tool_use
# ---------------------------------------------------------------------------

class TestRunPostToolUse:
    def test_run_post_tool_use_allows_when_no_hooks(self):
        reg = HookRegistry()
        result = reg.run_post_tool_use(tool_name="workspace.status")
        assert result.allowed is True

    def test_run_post_tool_use_error_swallowed(self):
        reg = HookRegistry()
        reg.register_spec(HookSpec(
            name="exploder", stage="post_tool_use", handler=_raise_handler,
        ))
        result = reg.run_post_tool_use(tool_name="workspace.status")
        assert result.allowed is True

    def test_run_post_tool_use_called_for_matching(self):
        called = []

        def audit_handler(**kw):
            called.append(True)
            return HookResult(allowed=True)

        reg = HookRegistry()
        reg.register_spec(HookSpec(
            name="audit", stage="post_tool_use", handler=audit_handler,
        ))
        reg.run_post_tool_use(tool_name="workspace.list_dir")
        assert len(called) == 1

    def test_run_post_tool_use_return_value_is_always_allowed(self):
        """Even if a post hook returns allowed=False, run_post_tool_use still returns allowed=True."""

        def deny_post(**kw):
            return HookResult(allowed=False, reason="post hook denial")

        reg = HookRegistry()
        reg.register_spec(HookSpec(
            name="deny-post", stage="post_tool_use", handler=deny_post,
        ))
        # run_post_tool_use ignores return values from handlers
        result = reg.run_post_tool_use(tool_name="shell.run")
        assert result.allowed is True


# ---------------------------------------------------------------------------
# Backward compat: original HookRegistration
# ---------------------------------------------------------------------------

class TestHookRegistrationCompat:
    def test_register_original_hook_registration(self):
        from src.jarvis.core.hooks.models import HookRegistration

        reg = HookRegistry()
        hr = HookRegistration(
            hook_id="test-1",
            hook_point="before_tool_call",
            callback=lambda payload: None,
        )
        result = reg.register(hr)
        assert result["ok"] is True
        assert len(reg.get("before_tool_call")) == 1

    def test_register_invalid_hook_point(self):
        from src.jarvis.core.hooks.models import HookRegistration

        reg = HookRegistry()
        hr = HookRegistration(
            hook_id="bad",
            hook_point="nonexistent_point",
            callback=lambda payload: None,
        )
        result = reg.register(hr)
        assert result["ok"] is False
