from __future__ import annotations

from src.jarvis.core.llm.prompt_builder import (
    build_chat_prompt,
    build_chat_prompt_direct,
    generate_chat_response,
    generate_chat_response_direct,
)


class _StubProvider:
    def __init__(self, response: str = "ok", raise_exc: Exception | None = None):
        self.response = response
        self.raise_exc = raise_exc
        self.calls: list[dict[str, str]] = []

    def complete(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        self.calls.append({"prompt": prompt, "system": system or ""})
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


def test_public_chat_api_reuses_direct_answer_contract():
    assert build_chat_prompt is build_chat_prompt_direct
    assert generate_chat_response is generate_chat_response_direct


def test_prompt_declares_chat_path_and_direct_answer_rules():
    prompt = build_chat_prompt(user_input="你是谁？你能做什么？", chat_type="identity_answer")

    assert "Current mode: chat path" in prompt
    assert "This is not the work path" in prompt
    assert "answer directly" in prompt
    assert "Do not default to clarification" in prompt
    assert "directly introduce Jarvis" in prompt


def test_prompt_prohibits_tool_plans_and_local_execution_claims():
    prompt = build_chat_prompt(user_input="给我讲一个程序员相关的短笑话。", chat_type="joke_answer")

    assert "Do not output tool_plan" in prompt
    assert "Do not output tool_calls" in prompt
    assert "Do not output JSON tool-call plans" in prompt
    assert "Do not claim you have executed commands" in prompt


def test_prompt_contains_required_few_shots():
    prompt = build_chat_prompt(user_input="test", chat_type="chat_answer")

    for marker in [
        "你是谁？你能做什么？",
        "请解释 sandbox 和 approval 的区别。",
        "帮我规划一下如何重构输入路由，不要直接改代码。",
        "给我讲一个程序员相关的短笑话。",
        "下一步该做什么？",
        "帮我改一下。",
    ]:
        assert marker in prompt


def test_provider_available_identity_returns_llm_final_answer():
    provider = _StubProvider(response="我是 Jarvis，可以回答问题、规划修改，并在审批后协助执行本地任务。")

    out = generate_chat_response(
        user_input="你是谁？你能做什么？",
        chat_type="identity_answer",
        llm_provider=provider,
    )

    assert out.startswith("我是 Jarvis")
    assert "我需要再确认一下" not in out
    assert "tool_plan" not in out
    assert provider.calls
    assert "直接回答" not in out


def test_explain_input_uses_llm_chat_not_clarify_template():
    provider = _StubProvider(response="sandbox 限制运行环境，approval 是执行前授权。")

    out = generate_chat_response(
        user_input="请解释 sandbox 和 approval 的区别，用简洁的中文说明。",
        chat_type="explain_answer",
        llm_provider=provider,
    )

    assert "sandbox" in out
    assert "我需要再确认一下" not in out


def test_plan_no_edit_stays_chat_and_does_not_emit_tool_json():
    provider = _StubProvider(response="建议分四步：梳理入口、定义路由类型、补测试、逐步替换旧逻辑。")

    out = generate_chat_response(
        user_input="帮我规划一下如何重构输入路由，不要直接改代码。",
        chat_type="plan_answer",
        llm_provider=provider,
    )

    assert "建议" in out
    assert "tool_plan" not in out
    assert "tool_calls" not in out


def test_joke_input_direct_answer():
    provider = _StubProvider(response="为什么程序员喜欢深夜修 bug？因为白天 bug 会装作需求。")

    out = generate_chat_response(
        user_input="给我讲一个程序员相关的短笑话。",
        chat_type="joke_answer",
        llm_provider=provider,
    )

    assert "bug" in out
    assert "我需要再确认一下" not in out


def test_truly_under_specified_input_may_clarify_once():
    provider = _StubProvider(response="可以，你想改哪一处？请告诉我目标文件、现象或期望效果。")

    out = generate_chat_response(
        user_input="帮我改一下。",
        chat_type="clarify_answer",
        llm_provider=provider,
    )

    assert out.count("？") <= 1
    assert "目标文件" in out
    assert provider.calls == []


def test_provider_unavailable_keeps_local_fallback():
    out = generate_chat_response(
        user_input="请解释 sandbox 和 approval 的区别。",
        chat_type="explain_answer",
        llm_provider=None,
    )

    assert "LLM provider" in out
    assert "不可用" in out


def test_provider_available_empty_content_returns_error():
    provider = _StubProvider(response="   ")

    out = generate_chat_response(
        user_input="请解释 sandbox 和 approval 的区别。",
        chat_type="explain_answer",
        llm_provider=provider,
    )

    assert out.startswith("[ERROR] LLM 返回空回答")
    assert "content_length=0" in out
    assert "我需要再确认一下" not in out


def test_provider_network_failure_returns_explicit_error_not_clarify():
    provider = _StubProvider(raise_exc=ConnectionError("socket blocked"))

    out = generate_chat_response(
        user_input="请解释 sandbox 和 approval 的区别。",
        chat_type="explain_answer",
        llm_provider=provider,
    )

    assert out.startswith("[ERROR] 无法连接 LLM")
    assert "socket blocked" in out
    assert "我需要再确认一下" not in out


def test_unavailable_provider_exception_uses_fallback():
    provider = _StubProvider(raise_exc=RuntimeError("LLM provider unavailable"))

    out = generate_chat_response(
        user_input="请解释 sandbox 和 approval 的区别。",
        chat_type="explain_answer",
        llm_provider=provider,
    )

    assert "LLM provider" in out
    assert "不可用" in out
