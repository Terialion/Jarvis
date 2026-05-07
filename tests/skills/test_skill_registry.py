"""Tests for SkillRegistry, progressive disclosure, trust boundary, and dynamic commands."""

from pathlib import Path

import pytest

from jarvis.core.skills.registry import SkillRegistry, SkillSpec
from src.jarvis.skills.registry import SkillRegistry as Phase9SkillRegistry

ROOT = Path(__file__).resolve().parents[2]


def _make_skill(
    name: str = "test-skill",
    trust_level: str = "local",
    allowed_tools: list[str] | None = None,
    enabled: bool = True,
) -> SkillSpec:
    return SkillSpec(
        name=name,
        description=f"Test skill: {name}",
        path=ROOT / "skills" / name,
        metadata={},
        allowed_tools=allowed_tools or ["read"],
        risk_level="medium",
        trust_level=trust_level,
        installed=True,
        enabled=enabled,
    )


class TestSkillRegistry:
    def test_register_and_get(self):
        reg = SkillRegistry()
        spec = _make_skill("a")
        reg.register(spec)
        assert reg.has("a")
        assert reg.get("a").name == "a"

    def test_list_enabled(self):
        reg = SkillRegistry()
        reg.register(_make_skill("enabled-skill", enabled=True))
        reg.register(_make_skill("disabled-skill", enabled=False))
        assert len(reg.list_enabled()) == 1

    def test_list_names_sorted(self):
        reg = SkillRegistry()
        reg.register(_make_skill("c"))
        reg.register(_make_skill("a"))
        reg.register(_make_skill("b"))
        assert reg.list_names() == ["a", "b", "c"]


class TestSkillProgressiveDisclosure:
    def test_llm_summary_no_full_instructions(self):
        """LLM summary must not contain full instructions."""
        reg = SkillRegistry()
        spec = _make_skill("test")
        reg.register(spec)
        summary = spec.to_llm_summary()
        assert "full_instructions" not in summary
        assert "name" in summary
        assert "trust_level" in summary

    def test_llm_skill_context_metadata_only(self):
        """LLM skill context must be metadata only."""
        reg = SkillRegistry()
        reg.register(_make_skill("a"))
        reg.register(_make_skill("b"))
        ctx = reg.to_llm_skill_context()
        assert "a" in ctx
        assert "b" in ctx
        assert "SKILL.md" not in ctx


class TestSkillTrustBoundary:
    def test_untrusted_cannot_shell(self):
        """Untrusted skills cannot use shell."""
        reg = SkillRegistry()
        reg.register(_make_skill("malicious", trust_level="untrusted"))
        allowed, reason = reg.check_trust("malicious", ["shell", "read"])
        assert allowed is False
        assert "trust_denied" in reason

    def test_untrusted_cannot_network(self):
        """Untrusted skills cannot use network."""
        reg = SkillRegistry()
        reg.register(_make_skill("web-skill", trust_level="untrusted"))
        allowed, reason = reg.check_trust("web-skill", ["network"])
        assert allowed is False

    def test_untrusted_cannot_write(self):
        """Untrusted skills cannot write."""
        reg = SkillRegistry()
        reg.register(_make_skill("editor", trust_level="untrusted"))
        allowed, reason = reg.check_trust("editor", ["write"])
        assert allowed is False

    def test_local_skill_can_read(self):
        """Local skills can read."""
        reg = SkillRegistry()
        reg.register(_make_skill("reader", trust_level="local", allowed_tools=["read"]))
        allowed, reason = reg.check_trust("reader", ["read"])
        assert allowed is True

    def test_skill_not_found(self):
        """Nonexistent skill returns skill_not_found."""
        reg = SkillRegistry()
        allowed, reason = reg.check_trust("nonexistent", ["read"])
        assert allowed is False
        assert "skill_not_found" in reason

    def test_disabled_skill_denied(self):
        """Disabled skills cannot be invoked."""
        reg = SkillRegistry()
        reg.register(_make_skill("disabled", enabled=False))
        allowed, reason = reg.check_trust("disabled", ["read"])
        assert allowed is False
        assert "skill_disabled" in reason

    def test_allowed_tools_narrows_only(self):
        """Skill allowed_tools can only narrow, not expand."""
        reg = SkillRegistry()
        reg.register(_make_skill("limited", allowed_tools=["read", "search"]))
        allowed, reason = reg.check_trust("limited", ["shell"])
        assert allowed is False
        assert "tool_not_allowed" in reason


class TestDynamicSkillCommand:
    def test_dynamic_skill_found(self):
        """Dynamic skill command resolves to a skill."""
        reg = SkillRegistry()
        reg.register(_make_skill("my-tool"))
        assert reg.has("my-tool")

    def test_dynamic_skill_not_found(self):
        """Unknown skill command returns not found."""
        reg = SkillRegistry()
        assert not reg.has("nonexistent-skill")

    def test_installed_not_equals_trusted(self):
        """An installed skill is not automatically trusted."""
        spec = _make_skill("new-skill", trust_level="untrusted")
        assert spec.installed is True
        assert spec.trust_level == "untrusted"


def test_phase9_registry_lists_builtin_skills():
    registry = Phase9SkillRegistry()
    names = registry.available_names()
    assert "repo_overview" in names
    assert "summarize_file" in names
    assert "run_tests" in names
    assert "fix_test_failure" in names


def test_phase9_registry_exports_metadata_only():
    registry = Phase9SkillRegistry()
    rows = registry.export_index()
    summarize_file = next(row for row in rows if row["name"] == "summarize_file")
    assert summarize_file["description"]
    assert "allowed_tools" in summarize_file
    assert "# Steps" not in str(summarize_file)
