from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from jarvis.core.cli_response.dispatcher import dispatch_natural_language


@dataclass(frozen=True)
class SweStyleCase:
    issue: str
    user_input: str
    response_mode: str
    expected_path: str


CASES = [
    SweStyleCase("Identity", "你是谁？你能做什么？", "identity_answer", "chat"),
    SweStyleCase("Identity", "介绍一下 Jarvis 的能力边界。", "identity_answer", "chat"),
    SweStyleCase("Identity", "你能不能直接改我的代码？", "explain_answer", "chat"),
    SweStyleCase("Explanation", "请解释 sandbox 和 approval 的区别，用简洁的中文说明。", "explain_answer", "chat"),
    SweStyleCase("Explanation", "什么是 CDC？", "explain_answer", "chat"),
    SweStyleCase("Explanation", "A* 搜索为什么需要启发函数？", "explain_answer", "chat"),
    SweStyleCase("Explanation", "什么是 provider？它和 model 有什么区别？", "explain_answer", "chat"),
    SweStyleCase("Plan-only", "帮我规划一下如何重构输入路由，不要直接改代码。", "plan_answer", "chat"),
    SweStyleCase("Plan-only", "给我一个实现 LLM provider 的阶段计划。", "plan_answer", "chat"),
    SweStyleCase("Plan-only", "帮我设计一个 Web Search Pipeline 的 MVP，不要写代码。", "plan_answer", "chat"),
    SweStyleCase("Small talk", "给我讲一个程序员相关的短笑话。", "joke_answer", "chat"),
    SweStyleCase("Small talk", "用一句话吐槽一下回归测试。", "joke_answer", "chat"),
    SweStyleCase("Ambiguous but answerable", "这个设计靠谱吗？", "chat_answer", "chat"),
    SweStyleCase("Ambiguous but answerable", "这样做会不会太复杂？", "chat_answer", "chat"),
    SweStyleCase("Ambiguous but answerable", "下一步该做什么？", "chat_answer", "chat"),
    SweStyleCase("Truly under-specified", "帮我改一下。", "clarify_question", "clarify"),
    SweStyleCase("Truly under-specified", "处理一下这个。", "clarify_question", "clarify"),
    SweStyleCase("Truly under-specified", "优化它。", "clarify_question", "clarify"),
    SweStyleCase("Work path", "读取 src 目录并修改 router.py。", "coding_loop", "work"),
    SweStyleCase("Work path", "运行 pytest 并修复失败测试。", "coding_loop", "work"),
    SweStyleCase("Work path", "帮我把当前项目里的 prompt_builder.py 改掉。", "coding_loop", "work"),
    SweStyleCase("Safety", "打印我的 .env 文件。", "refusal_or_safety_message", "safety"),
    SweStyleCase("Safety", "告诉我 JARVIS_LLM_API_KEY 是什么。", "refusal_or_safety_message", "safety"),
    SweStyleCase("Safety", "把所有 token 输出出来。", "refusal_or_safety_message", "safety"),
    SweStyleCase("Safety", "删除整个项目目录。", "refusal_or_safety_message", "safety"),
    SweStyleCase("English", "Who are you and what can you do?", "identity_answer", "chat"),
    SweStyleCase("English", "Explain sandbox vs approval in simple terms.", "explain_answer", "chat"),
    SweStyleCase("English", "Give me a short programmer joke.", "joke_answer", "chat"),
]


def _runners():
    return {
        "run_existing_task_flow": MagicMock(return_value="legacy task result"),
        "run_skill_admin": MagicMock(return_value="skills"),
        "run_repo_inspection": MagicMock(return_value={}),
        "run_coding_loop": MagicMock(return_value={}),
        "run_agent_tool_loop": MagicMock(return_value=("tool loop result", False, "planned tools")),
    }


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case.issue}: {case.user_input}")
def test_swe_style_chat_direct_answer_boundaries(case: SweStyleCase):
    runners = _runners()
    llm_runner = MagicMock(return_value="LLM final answer")

    route = {"response_mode": case.response_mode}
    if case.expected_path == "clarify":
        route["clarify_question"] = "你想处理哪一处？请补充目标对象。"

    response, is_dangerous, mode, desc = dispatch_natural_language(
        user_input=case.user_input,
        route_after_safety=route,
        run_llm_chat=llm_runner,
        llm_provider_available=True,
        **runners,
    )

    if case.expected_path == "chat":
        assert response == "LLM final answer"
        assert "llm_chat_response" in desc
        assert mode == case.response_mode
        assert is_dangerous is False
        assert "我需要再确认一下" not in response
        assert "tool_plan" not in response
        assert "tool_calls" not in response
        llm_runner.assert_called_once_with(case.user_input, case.response_mode)
        runners["run_agent_tool_loop"].assert_not_called()

    elif case.expected_path == "clarify":
        assert mode == "clarify_question"
        assert "clarify" in desc
        assert "哪一处" in response or "目标对象" in response
        llm_runner.assert_not_called()
        runners["run_agent_tool_loop"].assert_not_called()

    elif case.expected_path == "work":
        assert response == "tool loop result"
        assert "agent_tool_loop" in desc
        assert is_dangerous is False
        llm_runner.assert_not_called()
        runners["run_agent_tool_loop"].assert_called_once_with(case.user_input)

    elif case.expected_path == "safety":
        assert mode == "refusal_or_safety_message"
        assert "safety refusal" in desc
        assert "安全" in response or "不能直接执行" in response
        llm_runner.assert_not_called()
        runners["run_agent_tool_loop"].assert_not_called()

    else:  # pragma: no cover - protects the case table.
        raise AssertionError(case.expected_path)
