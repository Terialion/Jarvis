from pathlib import Path

from jarvis.core.skill_harness.telemetry import SkillTelemetryStore, SkillUsageRecord


def test_skill_usage_telemetry_records_event(tmp_path: Path):
    path = tmp_path / "usage.jsonl"
    store = SkillTelemetryStore(path)
    payload = store.append(
        SkillUsageRecord(
            skill_id="repo-inspector",
            input_preview="Inspect this repo.",
            selected=True,
            executed=False,
            mode="safe",
            outcome="dry_run",
            reason="policy_safe_mode",
            policy={"mode": "safe"},
            instruction_sources=[],
        )
    )
    assert payload.get("event") == "skill.usage.recorded"
    rows = store.read_all()
    assert len(rows) == 1
    assert rows[0].get("skill_id") == "repo-inspector"

