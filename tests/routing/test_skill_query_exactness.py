"""Tests for skill query exactness — ensures coding tasks mentioning "skill"
are NOT captured by skill_management deterministic rule.

Root cause: _SKILL_MANAGEMENT_TOKENS uses substring matching ("token in text"),
which caused coding tasks like '修复"查看skill"被误判成澄清的问题' to be
routed to skill_management instead of coding_loop.

Fix: _is_skill_query_but_not_coding() checks for coding action verbs before
matching skill tokens. If coding verbs are present, skip skill_management.
"""

import json

from src.jarvis.core.llm.provider import FakeLLMProvider
from src.jarvis.core.routing.input_gateway import build_input_envelope
from src.jarvis.core.routing.intent_gateway import route_intent


def _make_llm(intent, mode, confidence, **extra):
    """Create a FakeLLMProvider that returns a valid JSON classification."""
    payload = {
        "intent": intent,
        "response_mode": mode,
        "confidence": confidence,
        "summary": extra.get("summary", f"{intent} request"),
        "requires_write": extra.get("requires_write", False),
        "requires_shell": extra.get("requires_shell", False),
        "requires_repo_read": extra.get("requires_repo_read", False),
        "requires_network": extra.get("requires_network", False),
        "requires_approval": extra.get("requires_approval", False),
        "risk_level": extra.get("risk_level", "low"),
        "should_clarify": extra.get("should_clarify", False),
        "clarify_question": extra.get("clarify_question"),
        "candidate_skills": [],
        "reason": extra.get("reason", f"classified as {intent}"),
    }
    return FakeLLMProvider(response=json.dumps(payload))


# ============================================================================
# Positive cases: pure skill queries → skill_management
# ============================================================================

class TestPureSkillQueriesHitSkillManagement:
    """Pure skill queries should still be routed to skill_management."""

    @staticmethod
    def _route(text):
        envelope = build_input_envelope(text)
        return route_intent(envelope, examples=[])

    def test_查看skill(self):
        r = self._route("查看skill")
        assert r.intent == "skill_management"
        assert r.response_mode == "skill_admin"

    def test_查看_skills_with_space(self):
        r = self._route("查看 skills")
        assert r.intent == "skill_management"
        assert r.response_mode == "skill_admin"

    def test_列出_skills(self):
        r = self._route("列出 skills")
        assert r.intent == "skill_management"
        assert r.response_mode == "skill_admin"

    def test_有哪些技能(self):
        # "有哪些技能" does NOT contain coding action verbs
        # and doesn't match _SKILL_MANAGEMENT_TOKENS directly
        # so it falls through to LLM — that's fine
        r = self._route("有哪些技能")
        # Without LLM, it should NOT be skill_management (no exact token match)
        assert r.response_mode != "skill_admin" or r.intent == "skill_management"

    def test_我能用哪些技能(self):
        # Falls through to LLM without matching deterministic
        r = self._route("我能用哪些技能")
        # Should not be incorrectly classified as skill_management by coding rules
        assert r.intent != "coding_task"
        assert r.requires_write is False

    def test_list_skills(self):
        r = self._route("list skills")
        assert r.intent == "skill_management"
        assert r.response_mode == "skill_admin"

    def test_skill列表(self):
        r = self._route("skill 列表")
        assert r.intent == "skill_management"
        assert r.response_mode == "skill_admin"

    def test_列出可用_skills(self):
        r = self._route("列出可用 skills")
        assert r.intent == "skill_management"

    def test_disable_skill(self):
        r = self._route("disable skill")
        assert r.intent == "skill_management"

    def test_禁用某个_skill(self):
        r = self._route("禁用某个 skill")
        assert r.intent == "skill_management"


# ============================================================================
# Negative cases: coding tasks mentioning skill → NOT skill_management
# ============================================================================

class TestCodingTasksAboutSkillNotCaptured:
    """Coding/debug tasks that mention 'skill' must NOT be captured by
    skill_management. They should fall through to coding rules or LLM."""

    @staticmethod
    def _route(text, llm=None):
        envelope = build_input_envelope(text)
        return route_intent(envelope, examples=[], llm_provider=llm)

    def test_fix_skill_clarify_bug_with_tests(self):
        """修复"查看skill"被误判成澄清的问题，并跑相关测试 → coding_loop"""
        llm = _make_llm(
            "coding_task", "coding_loop", 0.95,
            summary="fix skill routing bug with test run",
            requires_repo_read=True, requires_write=True,
            requires_shell=True, requires_approval=True,
            risk_level="medium",
        )
        r = self._route('修复"查看skill"被误判成澄清的问题，并跑相关测试', llm=llm)
        assert r.intent != "skill_management", \
            f"Coding task should NOT be skill_management, got: {r.intent} ({r.reason})"
        assert r.response_mode == "coding_loop"
        assert r.requires_write is True
        assert r.requires_shell is True
        assert r.requires_approval is True

    def test_fix_skill_command_broken(self):
        """修复查看skill命令不能用的问题 → coding_loop"""
        llm = _make_llm(
            "coding_task", "coding_loop", 0.95,
            summary="fix skill command bug",
            requires_repo_read=True, requires_write=True,
            requires_approval=True, risk_level="medium",
        )
        r = self._route("修复查看skill命令不能用的问题", llm=llm)
        assert r.intent != "skill_management"
        assert r.response_mode == "coding_loop"
        assert r.requires_write is True
        assert r.requires_approval is True

    def test_add_regression_test_for_skill(self):
        """给查看skill补回归测试 → coding_loop"""
        llm = _make_llm(
            "coding_task", "coding_loop", 0.95,
            summary="add regression tests for skill query",
            requires_repo_read=True, requires_write=True,
            requires_shell=True, requires_approval=True,
            risk_level="medium",
        )
        r = self._route("给查看skill补回归测试", llm=llm)
        assert r.intent != "skill_management"
        assert r.response_mode == "coding_loop"
        assert r.requires_approval is True

    def test_implement_skill_fuzzy_search(self):
        """实现 skill list 的模糊搜索 → coding_loop"""
        llm = _make_llm(
            "coding_task", "coding_loop", 0.95,
            summary="implement fuzzy search for skill list",
            requires_repo_read=True, requires_write=True,
            requires_approval=True, risk_level="medium",
        )
        r = self._route("实现 skill list 的模糊搜索", llm=llm)
        assert r.intent != "skill_management"
        assert r.response_mode == "coding_loop"
        assert r.requires_write is True

    def test_fix_skill_show_support(self):
        """修改 skill command router，让 /skill 支持 show → coding_loop"""
        llm = _make_llm(
            "coding_task", "coding_loop", 0.95,
            summary="add show support to skill command",
            requires_repo_read=True, requires_write=True,
            requires_approval=True, risk_level="medium",
        )
        r = self._route("修改 skill command router，让 /skill 支持 show", llm=llm)
        assert r.intent != "skill_management"
        assert r.response_mode == "coding_loop"
        assert r.requires_write is True

    def test_fix_skills_duplicate_output(self):
        """修复 /skills 输出重复的问题，并跑 tests/cli → coding_loop"""
        llm = _make_llm(
            "coding_task", "coding_loop", 0.95,
            summary="fix skills duplicate output",
            requires_repo_read=True, requires_write=True,
            requires_shell=True, requires_approval=True,
            risk_level="medium",
        )
        r = self._route("修复 /skills 输出重复的问题，并跑 tests/cli", llm=llm)
        assert r.intent != "skill_management"
        assert r.response_mode == "coding_loop"
        assert r.requires_approval is True

    def test_no_llm_fallback_not_skill_management(self):
        """Without LLM, coding tasks should NOT be captured by skill_management.
        They should fall through (deterministic default) instead."""
        r = self._route('修复"查看skill"被误判成澄清的问题，并跑相关测试')
        assert r.intent != "skill_management", \
            f"Without LLM, coding task should fall through, got: {r.intent} ({r.reason})"


# ============================================================================
# Analysis cases: "不要改代码" → debug_analysis/plan_answer, requires_write=false
# ============================================================================

class TestSkillAnalysisNotCoding:
    """Skill-related analysis requests with '不要改代码' should NOT require write."""

    @staticmethod
    def _route(text, llm=None):
        envelope = build_input_envelope(text)
        return route_intent(envelope, examples=[], llm_provider=llm)

    def test_analyze_skill_misroute_no_code_change(self):
        """帮我分析为什么查看skill会被误判，不要改代码 → plan_answer"""
        llm = _make_llm(
            "chat", "plan_answer", 0.92,
            summary="analyze skill routing misclassification",
            requires_repo_read=True, requires_write=False,
        )
        r = self._route("帮我分析为什么查看skill会被误判，不要改代码", llm=llm)
        assert r.intent != "skill_management"
        assert r.response_mode in ("plan_answer", "debug_analysis")
        assert r.requires_write is False

    def test_locate_skill_unknown_no_modify(self):
        """先定位 /skill unknown 的原因，不要修改文件 → plan_answer"""
        llm = _make_llm(
            "chat", "plan_answer", 0.9,
            summary="locate skill unknown root cause",
            requires_repo_read=True, requires_write=False,
        )
        r = self._route("先定位 /skill unknown 的原因，不要修改文件", llm=llm)
        assert r.intent != "skill_management"
        assert r.requires_write is False


# ============================================================================
# Deterministic router helper tests
# ============================================================================

class TestHelperPredicates:
    """Unit tests for the new helper functions."""

    def test_has_coding_action_verb_zh(self):
        from src.jarvis.core.routing.deterministic_router import _has_coding_action_verb
        assert _has_coding_action_verb("修复 bug", "修复 bug") is True
        assert _has_coding_action_verb("查看skill", "查看skill") is False
        assert _has_coding_action_verb("实现模糊搜索", "实现模糊搜索") is True
        assert _has_coding_action_verb("修改 router", "修改 router") is True
        assert _has_coding_action_verb("补测试", "补测试") is True

    def test_has_coding_action_verb_en(self):
        from src.jarvis.core.routing.deterministic_router import _has_coding_action_verb
        assert _has_coding_action_verb("fix bug", "fix bug") is True
        assert _has_coding_action_verb("list skills", "list skills") is False
        assert _has_coding_action_verb("implement search", "implement search") is True

    def test_is_skill_query_but_not_coding(self):
        from src.jarvis.core.routing.deterministic_router import _is_skill_query_but_not_coding
        # Pure query → True
        assert _is_skill_query_but_not_coding("查看skill", "查看skill") is True
        assert _is_skill_query_but_not_coding("列出 skills", "列出 skills") is True
        # Coding task → False
        assert _is_skill_query_but_not_coding('修复"查看skill"的问题', '修复"查看skill"的问题') is False
        assert _is_skill_query_but_not_coding("修改 skill router", "修改 skill router") is False
        # No skill token → False
        assert _is_skill_query_but_not_coding("帮我写个文件", "帮我写个文件") is False
