from __future__ import annotations

from src.jarvis.skills.reference_planner import ReferenceSkillPlanner
from src.jarvis.skills.schema import SkillSpec
from src.jarvis.web.schema import SearchQuery
from src.jarvis.web.search import run_web_search


def test_reference_planner_extracts_query_not_raw_wrapper():
    planner = ReferenceSkillPlanner()
    spec = SkillSpec(
        name="multi-search-engine",
        description="Search with multiple engines",
        path="skills/reference/multi-search-engine/SKILL.md",
        source="repo",
        source_format="markdown",
        risk_level="low",
        capabilities=["search"],
        tags=["web"],
        allowed_tools=["web.search"],
        skill_type="reference",
    )
    text = '使用 multi-search-engine skill 搜索 "今天的科技新闻"'
    plan = planner.plan(spec, text)
    call = plan.recommended_tool_calls[0]
    args = call["arguments"]
    assert args["query"] == "今天的科技新闻"
    assert args["guided_by_skill"] == "multi-search-engine"
    assert args["invocation_path"] == "reference_skill_guided_tool_call"
    assert args["source"] == "skill_guided"


def test_web_search_keeps_skill_guided_metadata():
    result = run_web_search(
        SearchQuery(
            query="今天的科技新闻",
            provider="auto",
            guided_by_skill="multi-search-engine",
            invocation_path="reference_skill_guided_tool_call",
            source="skill_guided",
        )
    )
    run = result.runs[0]
    assert run["request"]["guided_by_skill"] == "multi-search-engine"
    assert run["request"]["invocation_path"] == "reference_skill_guided_tool_call"
    assert run["request"]["source"] == "skill_guided"
