import os
import sys


from jarvis.core.skill_harness import (
    SkillContextAssembler,
    SkillHitLogger,
    SkillLoader,
    SkillMatcher,
    SkillRegistry,
)


def test_skill_registry_crud_snapshot():
    reg = SkillRegistry()
    created = reg.register_skill(
        {
            "skill_id": "skill.test",
            "skill_name": "Test Skill",
            "source": "override",
            "required_tools": ["repo_reader"],
            "tags": ["bugfix"],
            "description": "demo",
        }
    )
    assert created["ok"]
    assert reg.get_skill("skill.test")["ok"]
    assert reg.disable_skill("skill.test")["ok"]
    snap = reg.snapshot()
    assert snap["ok"]
    assert snap["data"]["disabled_count"] == 1


def test_skill_loader_source_layers_and_gating(tmp_path):
    loader = SkillLoader(available_tools=["repo_reader", "file_editor", "test_runner"])
    bundled = loader.load_bundled_skills()
    assert bundled["ok"]
    assert bundled["data"]["loaded_skills"]

    skill_dir = tmp_path / "skills" / "local_fix"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "name: Local Fix\ndescription: Local repair\ntags: bugfix,repo\nrequired_tools: repo_reader,file_editor\n",
        encoding="utf-8",
    )
    local = loader.load_local_skills(str(tmp_path))
    assert local["ok"]
    assert local["data"]["loaded_skills"]

    override = loader.load_override_skills(
        [
            {
                "skill_id": "skill.override.fail",
                "skill_name": "Override Fail",
                "required_tools": ["unavailable_tool"],
            }
        ]
    )
    assert override["ok"]
    assert override["data"]["filtered_skills"][0]["reason"] == "required_tools_unavailable"


def test_skill_matcher_and_context_assembler():
    matcher = SkillMatcher()
    skills = [
        {
            "skill_id": "skill.repo_fix",
            "skill_name": "Repo Fix",
            "status": "enabled",
            "required_tools": ["repo_reader", "file_editor"],
            "tags": ["bugfix", "repo"],
            "priority_hint": 0.7,
            "description": "Fix code",
        },
        {
            "skill_id": "skill.test_only",
            "skill_name": "Test Only",
            "status": "enabled",
            "required_tools": ["test_runner"],
            "tags": ["test"],
            "priority_hint": 0.3,
            "description": "Run tests",
        },
    ]
    matched = matcher.match_skills(
        task_input="Please bugfix the repo and rerun tests",
        context={"hint": "repo"},
        available_tools=["repo_reader", "file_editor", "test_runner"],
        available_skills=skills,
    )
    assert matched["ok"]
    assert matched["data"]["matched_skills"]

    assembler = SkillContextAssembler()
    assembled = assembler.assemble(
        matched_skills=matched["data"]["matched_skills"],
        registry_snapshot=skills,
        context_budget_chars=500,
        max_active_skills=2,
    )
    assert assembled["ok"]
    assert assembled["data"]["instruction_block"]
    assert len(assembled["data"]["active_skill_ids"]) <= 2


def test_skill_matcher_with_pre_routing_hints_biases_seeded_skills():
    matcher = SkillMatcher()
    skills = [
        {
            "skill_id": "skill.repo_fix",
            "skill_name": "Repo Fix",
            "status": "enabled",
            "required_tools": ["repo_reader", "file_editor"],
            "tags": ["bugfix", "repo"],
            "priority_hint": 0.1,
            "description": "Fix code",
        },
        {
            "skill_id": "skill.command_verify",
            "skill_name": "Command Verify",
            "status": "enabled",
            "required_tools": ["command_runner"],
            "tags": ["command", "verify"],
            "priority_hint": 0.1,
            "description": "Run command probes",
        },
    ]
    matched = matcher.match_skills(
        task_input="run verify command",
        context={"hint": "verify"},
        available_tools=["repo_reader", "file_editor", "command_runner"],
        available_skills=skills,
        pre_routing_hints={
            "attached_default_skills": ["skill.repo_fix"],
            "selected_policies": ["safe-action-guard"],
            "planner_hints": {"skill_preferences": ["skill.repo_fix"], "task_shape": "multi_step"},
            "runtime_feedback": {"prefer_safe_skills": True, "last_failure_type": "test_assertion_failure"},
        },
    )
    assert matched["ok"]
    ranked = matched["data"]["ranking"]
    assert ranked[0] == "skill.repo_fix"
    top = matched["data"]["matched_skills"][0]
    assert "seeded_by_policy" in top["reasons"]
    assert matched["data"]["selected_skills"]
    assert "used_policy_seed" in matched["data"]["selection_reasons"]
    assert "skill.repo_fix" in matched["data"]["seed_sources"]


def test_skill_hit_logging_and_eval():
    logger = SkillHitLogger()
    logger.log_hit(
        run_id="run1",
        task_id="task1",
        step_number=0,
        active_skills=["skill.repo_fix"],
        matched_skill_ids=["skill.repo_fix"],
        chosen_skill_id="skill.repo_fix",
        chosen_tool="file_editor.replace_text",
        action_outcome="success",
    )
    logger.log_hit(
        run_id="run1",
        task_id="task1",
        step_number=1,
        active_skills=["skill.repo_fix"],
        matched_skill_ids=["skill.repo_fix"],
        chosen_skill_id="skill.repo_fix",
        chosen_tool="test_runner.run_test",
        action_outcome="retry",
    )
    logger.log_hit(
        run_id="run1",
        task_id="task1",
        step_number=2,
        active_skills=["skill.repo_fix"],
        matched_skill_ids=["skill.repo_fix"],
        chosen_skill_id="skill.repo_fix",
        chosen_tool="file_editor.replace_text",
        action_outcome="success",
        seeded_by_policy=True,
        seed_sources=["policy_seed"],
    )
    listed = logger.list_hits("run1")
    assert listed["ok"]
    assert listed["data"]["count"] == 3
    assert listed["data"]["items"][-1]["seeded_by_policy"] is True

    eval_result = logger.evaluate("run1")
    assert eval_result["ok"]
    assert eval_result["data"]["chosen_skill_steps"] == 3
    assert eval_result["data"]["average_usefulness"] > 0
    assert eval_result["data"]["seeded_hit_count"] == 1

    logger.log_hit(
        run_id="run2",
        task_id="task1",
        step_number=0,
        active_skills=["skill.repo_fix"],
        matched_skill_ids=["skill.repo_fix"],
        chosen_skill_id="skill.repo_fix",
        chosen_tool="file_editor.replace_text",
        action_outcome="success",
        seeded_by_policy=False,
    )
    aggregated = logger.aggregate_effectiveness(task_id="task1")
    assert aggregated["ok"]
    assert aggregated["data"]["total_runs"] == 2
    summary = aggregated["data"]["skill_effectiveness_summary"]["skill.repo_fix"]
    assert summary["records"] == 4
    assert summary["average_usefulness"] > 0
