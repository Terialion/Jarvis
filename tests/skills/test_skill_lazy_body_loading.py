from pathlib import Path

from jarvis.core.skill_harness.registry import SkillRegistry


def test_skill_body_is_lazy_loaded(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "doc-helper"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# Doc Helper\n\ndescription: Helps summarize docs.\ntriggers: docs, summary\n",
        encoding="utf-8",
    )
    registry = SkillRegistry()
    registry.discover(tmp_path)

    before = registry.snapshot().get("data", {})
    item_before = next(item for item in list(before.get("items") or []) if item.get("skill_id") == "doc-helper")
    assert item_before.get("body_loaded") is False

    result = registry.load_skill_body("doc-helper")
    assert result.get("ok") is True
    assert result.get("data", {}).get("body_loaded") is True
    assert "Doc Helper" in result.get("data", {}).get("body", "")

    after = registry.snapshot().get("data", {})
    item_after = next(item for item in list(after.get("items") or []) if item.get("skill_id") == "doc-helper")
    assert item_after.get("body_loaded") is True

