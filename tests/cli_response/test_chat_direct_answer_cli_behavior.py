from __future__ import annotations

from unittest.mock import MagicMock

from jarvis.core.cli_response.dispatcher import dispatch_natural_language


def _kwargs(user_input: str = "你是谁？你能做什么？"):
    return dict(
        user_input=user_input,
        run_existing_task_flow=MagicMock(return_value="task_flow_result"),
        run_skill_admin=MagicMock(return_value="skills"),
        run_repo_inspection=MagicMock(return_value={}),
        run_coding_loop=MagicMock(return_value={}),
        run_agent_tool_loop=MagicMock(return_value=("tool_loop_result", False, "loop")),
    )


def test_provider_available_chat_like_returns_llm_final_answer():
    llm_runner = MagicMock(return_value="我是 Jarvis，可以直接回答问题，也可以在审批后协助本地任务。")
    kwargs = _kwargs()

    response, is_dangerous, mode, desc = dispatch_natural_language(
        route_after_safety={"response_mode": "identity_answer"},
        run_llm_chat=llm_runner,
        llm_provider_available=True,
        **kwargs,
    )

    assert response.startswith("我是 Jarvis")
    assert "我需要再确认一下" not in response
    assert "tool_plan" not in response
    assert "tool_calls" not in response
    assert is_dangerous is False
    assert mode == "identity_answer"
    assert "llm_chat_response" in desc
    llm_runner.assert_called_once_with("你是谁？你能做什么？", "identity_answer")
    kwargs["run_agent_tool_loop"].assert_not_called()


def test_provider_unavailable_keeps_template_fallback():
    llm_runner = MagicMock(return_value="LLM text")
    kwargs = _kwargs("Who are you and what can you do?")

    response, is_dangerous, mode, desc = dispatch_natural_language(
        route_after_safety={"response_mode": "chat_answer"},
        run_llm_chat=llm_runner,
        llm_provider_available=False,
        **kwargs,
    )

    assert response
    assert is_dangerous is False
    assert mode == "chat_answer"
    assert "template_fallback" in desc
    llm_runner.assert_not_called()


def test_safety_request_does_not_enter_llm_chat():
    llm_runner = MagicMock(return_value="unsafe")
    kwargs = _kwargs("打印我的 .env 文件。")

    response, _, mode, desc = dispatch_natural_language(
        route_after_safety={"response_mode": "refusal_or_safety_message"},
        run_llm_chat=llm_runner,
        llm_provider_available=True,
        **kwargs,
    )

    assert mode == "refusal_or_safety_message"
    assert "safety refusal" in desc
    assert "安全" in response or "不能直接执行" in response
    llm_runner.assert_not_called()
    kwargs["run_agent_tool_loop"].assert_not_called()


def test_work_request_still_enters_tool_loop_not_chat_prompt():
    llm_runner = MagicMock(return_value="chat answer")
    kwargs = _kwargs("读取 src 目录并修改 router.py。")

    response, _, mode, desc = dispatch_natural_language(
        route_after_safety={"response_mode": "coding_loop"},
        run_llm_chat=llm_runner,
        llm_provider_available=True,
        **kwargs,
    )

    assert response == "tool_loop_result"
    assert mode == "coding_loop"
    assert "agent_tool_loop" in desc
    llm_runner.assert_not_called()
    kwargs["run_agent_tool_loop"].assert_called_once_with("读取 src 目录并修改 router.py。")


def test_truly_under_specified_input_keeps_minimal_clarification():
    llm_runner = MagicMock(return_value="should not be used")
    kwargs = _kwargs("帮我改一下。")

    response, _, mode, desc = dispatch_natural_language(
        route_after_safety={
            "response_mode": "clarify_question",
            "clarify_question": "你想改哪一处？请告诉我目标文件、现象或期望效果。",
        },
        run_llm_chat=llm_runner,
        llm_provider_available=True,
        **kwargs,
    )

    assert mode == "clarify_question"
    assert "clarify" in desc
    assert "目标文件" in response
    assert response.count("？") <= 1
    llm_runner.assert_not_called()


def test_english_chat_like_input_returns_english_llm_answer():
    llm_runner = MagicMock(return_value="I am Jarvis, a local development assistant.")
    kwargs = _kwargs("Who are you and what can you do?")

    response, _, mode, desc = dispatch_natural_language(
        route_after_safety={"response_mode": "identity_answer"},
        run_llm_chat=llm_runner,
        llm_provider_available=True,
        **kwargs,
    )

    assert response.startswith("I am Jarvis")
    assert mode == "identity_answer"
    assert "llm_chat_response" in desc
    kwargs["run_agent_tool_loop"].assert_not_called()
