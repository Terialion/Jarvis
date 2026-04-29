from pathlib import Path

from jarvis.core.skill_harness.registry import SkillRegistry


def test_workspace_skill_shadows_openclaw_duplicate(tmp_path: Path):
    high = tmp_path / "skills" / "repo-inspector"
    high.mkdir(parents=True)
    (high / "manifest.json").write_text(
        '{"id":"repo-inspector","name":"Repo Inspector","description":"workspace","trust":"trusted"}',
        encoding="utf-8",
    )
    low = tmp_path / "openclaw" / "skills" / "repo-inspector"
    low.mkdir(parents=True)
    (low / "manifest.json").write_text(
        '{"id":"repo-inspector","name":"Repo Inspector","description":"openclaw","trust":"trusted"}',
        encoding="utf-8",
    )

    registry = SkillRegistry()
    registry.discover(tmp_path)
    snap = registry.snapshot().get("data", {})
    items = list(snap.get("items") or [])
    winner = next(item for item in items if item.get("skill_id") == "repo-inspector" and item.get("status") == "enabled")
    assert str(winner.get("source")).lower() in {"local", "project", "workspace"}

    discovery = dict(snap.get("discovery") or {})
    shadowed = list(discovery.get("shadowed") or [])
    assert any(str(row.get("skill_id")) == "repo-inspector" for row in shadowed)

