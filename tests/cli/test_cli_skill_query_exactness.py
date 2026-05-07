"""CLI integration tests for skill query exactness."""

from __future__ import annotations

from types import SimpleNamespace

from jarvis import cli as cli_mod


def _stub_skill_loop(monkeypatch, final_answer: str, output_type: str = "tool_result"):
    monkeypatch.setattr(cli_mod, "_quick_agent_result_for_cli", lambda *_a, **_k: None)

    class _DummyLoop:
        def __init__(self, *args, **kwargs):
            pass

        def run_turn(self, chat_input):
            return SimpleNamespace(
                ok=True,
                final_answer=final_answer,
                stop_reason="completed",
                status="completed",
                output_type=output_type,
                tool_calls=[{"name": "skill.list", "arguments": {}}],
                events=[],
                summary={"machine": {"outcome": "completed", "tools_used": ["skill.list"], "risks": []}},
            )

    monkeypatch.setattr("src.jarvis.agent.loop.AgentLoop", _DummyLoop)


class TestCLISkillQueryPositiveCases:
    def test_skill_query_shows_skills(self, monkeypatch):
        _stub_skill_loop(monkeypatch, "Available skills: repo, web, python.")
        output = cli_mod.run_agent_turn_for_cli("查看skill", output_mode="default")
        assert "Task task_" not in output
        assert "Available skills" in output

    def test_list_skills_not_coding(self, monkeypatch):
        _stub_skill_loop(monkeypatch, "Available skills: repo, web, python.")
        output = cli_mod.run_agent_turn_for_cli("列出 skills", output_mode="default")
        assert "Task task_" not in output


class TestCLISkillCodingTaskNotCaptured:
    def test_fix_skill_bug_is_coding(self, monkeypatch):
        _stub_skill_loop(monkeypatch, "Plan: inspect routing and add tests.")
        output = cli_mod.run_agent_turn_for_cli('修复"查看skill"被误判成澄清的问题，并跑相关测试', output_mode="default")
        assert "Plan:" in output or "Jarvis" in output

    def test_fix_skill_command_is_coding(self, monkeypatch):
        _stub_skill_loop(monkeypatch, "Plan: inspect routing and add tests.")
        output = cli_mod.run_agent_turn_for_cli("修复查看skill命令不能用的问题", output_mode="default")
        assert "Plan:" in output or "Jarvis" in output


class TestCLISkillAnalysisNoCodeChange:
    def test_analyze_skill_no_code_change(self, monkeypatch):
        _stub_skill_loop(monkeypatch, "Analysis only. No code changes needed.", output_type="answer")
        output = cli_mod.run_agent_turn_for_cli("帮我分析为什么查看skill会被误判，不要改代码", output_mode="default")
        assert "Approval required" not in output
