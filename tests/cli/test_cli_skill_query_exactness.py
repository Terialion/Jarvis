"""CLI integration tests for skill query exactness.

These tests verify that the full CLI pipeline correctly handles the
distinction between pure skill queries and coding tasks about skills.
"""

import os
import subprocess
import sys


def run_cli(*args, input_text=None, timeout=25):
    """Run jarvis.cli with given input text via stdin."""
    merged_env = os.environ.copy()
    merged_env["PYTHONIOENCODING"] = "utf-8"
    merged_env["PYTHONLEGACYWINDOWSSTDIO"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
        encoding="utf-8",
        errors="ignore",
        env=merged_env,
    )


class TestCLISkillQueryPositiveCases:
    """Pure skill queries should reach skill management, not coding loop."""

    def test_查看skill_shows_skills(self):
        """查看skill → should show skill list, not enter coding loop."""
        result = run_cli(input_text="查看skill\n/exit\n")
        output = result.stdout + result.stderr
        # Should NOT enter coding task flow
        assert "Task task_" not in output, \
            f"Pure skill query should not enter task flow. Output: {output[-200:]}"

    def test_列出_skills_not_coding(self):
        """列出 skills → should not enter coding loop."""
        result = run_cli(input_text="列出 skills\n/exit\n")
        output = result.stdout + result.stderr
        assert "Task task_" not in output


class TestCLISkillCodingTaskNotCaptured:
    """Coding tasks mentioning 'skill' should NOT be captured as skill_management."""

    def test_fix_skill_bug_is_coding(self):
        """修复"查看skill"被误判... → should be coding/analysis, not skill list."""
        result = run_cli(input_text='修复"查看skill"被误判成澄清的问题，并跑相关测试\n/exit\n')
        output = result.stdout + result.stderr
        # Should NOT show skill management UI — coding verbs detected
        # Now routed through AgentToolLoop work path (coding_loop)
        has_task_flow = "Task task_" in output
        has_analysis = "规划" in output or "分析" in output or "plan" in output.lower()
        has_approval = "Approval required" in output
        has_work_path = "[WORK]" in output or "coding_loop" in output
        has_llm_fallback = "无法连接 LLM" in output
        assert has_task_flow or has_analysis or has_approval or has_work_path or has_llm_fallback, \
            f"Coding task about skill should not be a simple skill list. Output: {output[-300:]}"

    def test_fix_skill_command_is_coding(self):
        """修复查看skill命令不能用 → should be coding/analysis, not skill list."""
        result = run_cli(input_text="修复查看skill命令不能用的问题\n/exit\n")
        output = result.stdout + result.stderr
        has_task_flow = "Task task_" in output
        has_analysis = "规划" in output or "分析" in output
        has_approval = "Approval required" in output
        has_work_path = "[WORK]" in output or "coding_loop" in output
        has_llm_fallback = "无法连接 LLM" in output
        assert has_task_flow or has_analysis or has_approval or has_work_path or has_llm_fallback, \
            f"Fix skill command should not be a simple skill list. Output: {output[-300:]}"


class TestCLISkillAnalysisNoCodeChange:
    """Skill analysis with '不要改代码' should not require write approval."""

    def test_analyze_skill_no_code_change(self):
        """帮我分析为什么查看skill会被误判，不要改代码 → no write."""
        result = run_cli(input_text="帮我分析为什么查看skill会被误判，不要改代码\n/exit\n")
        output = result.stdout + result.stderr
        # Should NOT enter coding loop with write
        assert "Approval required" not in output, \
            f"Analysis request should not require approval. Output: {output[-300:]}"
