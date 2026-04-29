from pathlib import Path

from jarvis.core.skill_harness.registry import SkillRegistry


def test_skill_metadata_contract_fields_present(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "repo-inspector"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: Repo Inspector",
                "id: repo-inspector",
                "description: Inspect repository structure safely",
                "triggers: [repo, inspect]",
                "when_to_use: [inspect repository, summarize structure]",
                "invocation: auto",
                "allowed-tools: [repo_reader]",
                "permissions: [filesystem.read]",
                "dynamic_context: true",
                "subagent: false",
                "---",
                "# Repo Inspector",
            ]
        ),
        encoding="utf-8",
    )

    registry = SkillRegistry()
    registry.discover(tmp_path)
    snap = registry.snapshot().get("data", {})
    items = list(snap.get("items") or [])
    target = next(item for item in items if str(item.get("skill_id")) == "repo-inspector")
    for key in (
        "invocation",
        "source_priority",
        "allowed_tools",
        "dynamic_context",
        "subagent",
        "when_to_use",
        "body_loaded",
    ):
        assert key in target

