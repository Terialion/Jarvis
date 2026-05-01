"""Tests that natural_responses.py does NOT match user input text for intent.

These render functions must use response_mode/route context, not user_input text.
"""

from src.jarvis.core.cli_response.natural_responses import (
    render_chat_answer,
    render_workspace_status,
    render_help_answer,
    render_plan_answer,
    render_debug_analysis,
)


class TestChatAnswerNoIntentMatching:
    """render_chat_answer must not check user_input for intent classification."""

    def test_chat_answer_uses_response_mode_for_joke(self):
        """Joke response triggered by response_mode, not user input."""
        route = {"response_mode": "joke_answer", "summary": "joke request"}
        result = render_chat_answer(route, "随便说点什么")  # input is not about jokes
        # Should return a joke because mode is joke_answer, not because input contains joke words
        assert "程序员" in result or "SQL" in result or "Python" in result or "Oct 31" in result

    def test_chat_answer_uses_response_mode_for_identity(self):
        """Identity response triggered by response_mode, not user input."""
        route = {"response_mode": "identity_answer", "summary": "identity question"}
        result = render_chat_answer(route, "do something unrelated")
        assert "Jarvis CLI" in result

    def test_chat_answer_default_chinese_greeting(self):
        """Default greeting for Chinese input."""
        route = {"response_mode": "chat_answer", "summary": "greeting"}
        result = render_chat_answer(route, "你好")
        assert "你好" in result

    def test_chat_answer_default_english_greeting(self):
        """Default greeting for English input."""
        route = {"response_mode": "chat_answer", "summary": "greeting"}
        result = render_chat_answer(route, "hello")
        assert "Hi, I'm here." in result

    def test_chat_answer_no_joke_keywords_check(self):
        """Even if user input contains joke-like words, it should not auto-joke unless mode says so."""
        route = {"response_mode": "chat_answer", "summary": "chat"}
        result = render_chat_answer(route, "给我讲个笑话")  # user says joke but mode is generic chat
        # Should NOT return a random joke — it returns the default greeting
        assert "Oct 31" not in result and "SQL" not in result


class TestWorkspaceStatusNoIntentMatching:
    """render_workspace_status must not check user_input for intent."""

    def test_workspace_status_uses_route_not_input(self):
        route = {"response_mode": "workspace_status", "summary": "workspace query"}
        result = render_workspace_status(route, "完全无关的输入")
        assert "当前工作目录" in result


class TestHelpAnswerNoIntentMatching:
    """render_help_answer uses route intent, not user input for intent."""

    def test_help_answer_generic(self):
        route = {"intent": "capability_qa", "response_mode": "help_answer"}
        result = render_help_answer(route, "random text")
        assert "我可以帮你" in result or "I can help" in result


class TestPlanAndDebugResponses:
    """Plan and debug answers exist and produce reasonable output."""

    def test_plan_answer_returns_text(self):
        route = {"response_mode": "plan_answer", "summary": "planning"}
        result = render_plan_answer(route, "帮我规划重构")
        assert "分析并规划" in result or "plan" in result.lower()

    def test_debug_analysis_returns_text(self):
        route = {"response_mode": "debug_analysis", "summary": "debug analysis"}
        result = render_debug_analysis(route, "帮我查一下为什么超时")
        assert "排查" in result or "debug" in result.lower()
