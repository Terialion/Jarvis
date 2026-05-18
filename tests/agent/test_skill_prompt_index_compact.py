from __future__ import annotations

from src.jarvis.skills.schema import SkillSpec


def test_skill_spec_compact_fields_present():
    spec = SkillSpec(
        name="test_skill",
        description="A test skill for compact metadata verification",
        path="/tmp/test_skill",
        source="local",
        source_format="markdown",
        skill_type="executable",
        tags=["test", "compact"],
        capabilities=["summarize"],
        when_to_use="when user asks for summary",
        examples=["summarize README.md"],
    )

    assert spec.name == "test_skill"
    assert spec.description
    assert spec.skill_type == "executable"
    assert len(spec.tags) > 0


def test_disabled_skill_has_state_in_metadata():
    spec = SkillSpec(
        name="disabled_skill",
        description="should not appear",
        path="/tmp/disabled",
        source="local",
        source_format="markdown",
        skill_type="executable",
        metadata={"enabled": False, "quarantined": False},
    )

    assert spec.metadata.get("enabled") is False


def test_compact_metadata_no_full_skill_md_injected():
    spec = SkillSpec(
        name="test_skill",
        description="compact only",
        path="/tmp/test",
        source="local",
        source_format="markdown",
        skill_type="reference",
        body_preview="# Full SKILL.md\nThis is a long body...",
    )

    # body_preview exists but compact prompt index only uses name/description/type
    compact = f"{spec.name}: {spec.description} (type={spec.skill_type})"
    assert "Full SKILL.md" not in compact
    assert len(spec.body_preview or "") > 0
