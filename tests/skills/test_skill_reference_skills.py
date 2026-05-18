"""Tests for the reference skill SKILL.md files."""

from __future__ import annotations

from src.jarvis.skills.registry import SkillRegistry

EXPECTED_SKILLS = ["web_research", "code_review", "fix_bug", "refactor"]


def _get_skills():
    registry = SkillRegistry()
    return {s.name: s for s in registry.list_discovered_skills()}


def test_all_four_reference_skills_discoverable():
    """Each new reference skill must be visible in the registry."""
    skills = _get_skills()
    for name in EXPECTED_SKILLS:
        assert name in skills, f"Skill '{name}' not found in registry"


def test_web_research_has_network_risk():
    skills = _get_skills()
    spec = skills["web_research"]
    assert spec.risk_level == "network" or "network" in str(spec.risk_level).lower()


def test_code_review_is_read_only():
    skills = _get_skills()
    spec = skills["code_review"]
    assert "read" in str(spec.risk_level or "").lower()


def test_fix_bug_requires_write_approval():
    skills = _get_skills()
    spec = skills["fix_bug"]
    assert "write" in str(spec.risk_level or "").lower() or "approval" in str(spec.risk_level or "").lower()


def test_refactor_requires_write_approval():
    skills = _get_skills()
    spec = skills["refactor"]
    assert "write" in str(spec.risk_level or "").lower() or "approval" in str(spec.risk_level or "").lower()


def test_each_skill_body_loads():
    """Each skill body must be loadable and contain expected sections."""
    registry = SkillRegistry()
    for name in EXPECTED_SKILLS:
        body = registry.load_body(name)
        assert body, f"Skill '{name}' body is empty"
        # Verify required sections exist
        assert "# When to use" in body, f"'{name}' missing '# When to use'"
        assert "# Workflow" in body, f"'{name}' missing '# Workflow'"
        assert "# Output Format" in body, f"'{name}' missing '# Output Format'"


def test_web_research_body_mentions_web_fetch():
    registry = SkillRegistry()
    body = registry.load_body("web_research")
    assert "web.fetch" in body, "web_research should reference web.fetch in workflow"


def test_code_review_body_mentions_security():
    registry = SkillRegistry()
    body = registry.load_body("code_review")
    assert "Security" in body or "security" in body.lower()


def test_fix_bug_body_mentions_approval():
    registry = SkillRegistry()
    body = registry.load_body("fix_bug")
    assert "approval" in body.lower(), "fix_bug must mention approval"


def test_refactor_body_mentions_incremental():
    registry = SkillRegistry()
    body = registry.load_body("refactor")
    assert "increment" in body.lower() or "step" in body.lower(), "refactor must mention incremental changes"


def test_all_skills_have_valid_frontmatter():
    """Each skill must have a parsable name and description in frontmatter."""
    skills = _get_skills()
    for name in EXPECTED_SKILLS:
        spec = skills[name]
        assert spec.name == name, f"Expected name '{name}', got '{spec.name}'"
        assert spec.description, f"Skill '{name}' has empty description"
        assert len(spec.description) > 20, f"Skill '{name}' description too short: {spec.description}"


def test_skill_descriptions_fit_in_prompt_limit():
    """Descriptions should be informative but fit within the 200-char limit."""
    skills = _get_skills()
    for name in EXPECTED_SKILLS:
        spec = skills[name]
        assert len(spec.description) <= 200, (
            f"Skill '{name}' description is {len(spec.description)} chars (max 200)"
        )
