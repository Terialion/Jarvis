from __future__ import annotations

from src.jarvis.agent.tools import ToolCallExecutor, ToolRegistryAdapter
from src.jarvis.agent.types import TurnContext
from src.jarvis.skills.executor import SkillExecutor
from src.jarvis.skills.runtime import SkillCall


def test_skill_allowed_tools_denial_precedes_global_policy(tmp_path):
    adapter = ToolRegistryAdapter(project_root=str(tmp_path))
    executor = SkillExecutor(
        skill_registry=adapter.skill_registry,
        tool_executor=ToolCallExecutor(registry_adapter=adapter, auto_approve=True),
        project_root=str(tmp_path),
    )
    original = executor._handlers["summarize_file"]

    def _forced(ctx):
        step, tool_result, _ = executor._execute_tool(ctx, "forced", "forced", "command_runner.run", {"command": "python -V"})
        from src.jarvis.skills.runtime import SkillResult
        return SkillResult(ok=False, skill_name=ctx.skill_spec.name, final_answer="blocked", output_type="partial", steps=[step], tool_calls=[], tool_results=[tool_result.to_dict()], events=list(ctx.events), risks=["tool_not_allowed_by_skill"])

    executor._handlers["summarize_file"] = _forced
    result = executor.run(
        SkillCall.new(name="summarize_file", arguments={"path": "README.md"}, source="test"),
        TurnContext(user_input="summary", cwd=str(tmp_path)),
    )
    executor._handlers["summarize_file"] = original
    assert "tool_not_allowed_by_skill" in result.risks
