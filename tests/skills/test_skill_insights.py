from pathlib import Path

from jarvis.core.skill_harness.telemetry import SkillTelemetryStore, SkillUsageRecord


def test_skill_insights_summary(tmp_path: Path):
    path = tmp_path / "usage.jsonl"
    store = SkillTelemetryStore(path)
    store.append(
        SkillUsageRecord(
            skill_id="repo-inspector",
            input_preview="Inspect repo",
            selected=True,
            executed=False,
            mode="safe",
            outcome="dry_run",
            reason="safe_mode",
            policy={"mode": "safe"},
        )
    )
    store.append(
        SkillUsageRecord(
            skill_id="web-search",
            input_preview="Search web",
            selected=False,
            executed=False,
            mode="safe",
            outcome="blocked",
            reason="network_disabled",
            policy={"mode": "safe"},
        )
    )
    data = store.insights()
    assert data["total_records"] == 2
    assert "skills" in data
    assert "suggestions" in data
    assert any(item["skill_id"] == "repo-inspector" for item in data["most_selected"])

