from __future__ import annotations

from unittest.mock import MagicMock

from jarvis.core.cli_response.dispatcher import dispatch_natural_language


def _base_kwargs():
    return dict(
        user_input="test input",
        run_existing_task_flow=MagicMock(return_value="task_flow_result"),
        run_skill_admin=MagicMock(return_value="skills"),
        run_repo_inspection=MagicMock(return_value={}),
        run_agent_tool_loop=MagicMock(return_value=("tool_loop_result", False, "loop")),
    )


def test_chat_like_uses_llm_when_provider_available():
    llm_runner = MagicMock(return_value="LLM: 我是 Jarvis，可以帮你分析和编码。")
    kwargs = _base_kwargs()
    response, is_dangerous, mode, desc = dispatch_natural_language(
        route_after_safety={"response_mode": "identity_answer"},
        run_llm_chat=llm_runner,
        llm_provider_available=True,
        **kwargs,
    )
    assert "LLM:" in response
    assert is_dangerous is False
    assert mode == "identity_answer"
    assert "llm_chat" in desc
    llm_runner.assert_called_once()
    kwargs["run_agent_tool_loop"].assert_not_called()


def test_plan_like_uses_llm_when_provider_available():
    llm_runner = MagicMock(return_value="LLM: 先拆分路由责任，再做回归。")
    kwargs = _base_kwargs()
    response, is_dangerous, mode, desc = dispatch_natural_language(
        route_after_safety={"response_mode": "plan_answer"},
        run_llm_chat=llm_runner,
        llm_provider_available=True,
        **kwargs,
    )
    assert "LLM:" in response
    assert is_dangerous is False
    assert mode == "plan_answer"
    assert "llm_chat" in desc
    kwargs["run_agent_tool_loop"].assert_not_called()


def test_chat_like_falls_back_to_template_when_provider_unavailable():
    llm_runner = MagicMock(return_value="LLM text")
    kwargs = _base_kwargs()
    response, _, mode, desc = dispatch_natural_language(
        route_after_safety={"response_mode": "chat_answer"},
        run_llm_chat=llm_runner,
        llm_provider_available=False,
        **kwargs,
    )
    assert mode == "chat_answer"
    assert "template_fallback" in desc
    assert response != ""
    llm_runner.assert_not_called()


def test_safety_never_enters_llm_chat():
    llm_runner = MagicMock(return_value="LLM text")
    kwargs = _base_kwargs()
    response, _, mode, _ = dispatch_natural_language(
        route_after_safety={"response_mode": "refusal_or_safety_message"},
        run_llm_chat=llm_runner,
        llm_provider_available=True,
        **kwargs,
    )
    assert mode == "refusal_or_safety_message"
    assert "不能直接执行" in response or "安全" in response
    llm_runner.assert_not_called()


def test_work_still_uses_tool_loop_not_llm_chat():
    llm_runner = MagicMock(return_value="LLM text")
    kwargs = _base_kwargs()
    response, _, mode, desc = dispatch_natural_language(
        route_after_safety={"response_mode": "file_listing"},
        run_llm_chat=llm_runner,
        llm_provider_available=True,
        **kwargs,
    )
    assert mode == "file_listing"
    assert "work_runner" in desc
    assert response == "tool_loop_result"
    kwargs["run_agent_tool_loop"].assert_called_once()
    llm_runner.assert_not_called()


def test_clarify_can_recover_to_llm_chat_for_chat_like_input():
    llm_runner = MagicMock(return_value="LLM: 我是 Jarvis。")
    kwargs = _base_kwargs()
    kwargs["user_input"] = "你是谁？你能做什么？"
    response, _, mode, desc = dispatch_natural_language(
        route_after_safety={"response_mode": "clarify_question"},
        run_llm_chat=llm_runner,
        llm_provider_available=True,
        **kwargs,
    )
    assert response.startswith("LLM:")
    assert mode == "chat_answer"
    assert "recovered_from_clarify" in desc
    llm_runner.assert_called_once()
