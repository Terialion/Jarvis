"""Deterministic router — handles ONLY high-confidence structural/safety rules.

Rules kept here are:
1. Empty input
2. Slash commands
3. Greetings (very short, exact match — hello, 你好, etc.)
4. Identity questions (你是谁, who are you)
5. Capability questions (你能做什么, what can you do)
6. Usage help (怎么让你改代码)
7. Context resume (继续上次任务)
8. Skill management (列出 skills, 查看skill — direct management actions)
9. Automation requests
10. URL detection
11. Web search hints
12. Repo inspection hints (structural: "读项目", "inspect this repo", etc.)
13. Coding creation (写 + code_object pattern)
14. Coding modification (修复, 改一下, bug fix)
15. Shell execution (运行 pytest, git status)
16. Non-code writing ambiguity (写个东西, write something)
17. Generic ambiguity (弄一下, do something)

MOVED TO LLM SEMANTIC ROUTER:
- Joke requests (给我讲个笑话, tell me a joke)
- Workspace status natural language (我现在的目录是什么)
- Project structure exploration that doesn't match exact tokens
- Explanation requests
- Planning requests
- Debug analysis requests
"""

from __future__ import annotations

from .input_gateway import InputEnvelope
from .schema import Intent, IntentRoute, ResponseMode, RiskLevel

# ---------------------------------------------------------------------------
# High-confidence exact-match sets — greeting, identity, capability
# ---------------------------------------------------------------------------

_CHAT_EN = {
    "hi",
    "hello",
    "hey",
    "hey there",
    "good morning",
    "good afternoon",
    "good evening",
    "ciallo",
}
_CHAT_ZH_EXACT = {
    "你好",
    "你好啊",
    "哈喽",
    "在吗",
    "早上好",
    "下午好",
    "晚上好",
    "嗨",
    "嘿",
}
_IDENTITY_EN = {"who are you", "what are you"}
_IDENTITY_ZH = {"你是谁", "你是什么"}
_CAPABILITY_EN = {
    "what can you do",
    "what u can do",
    "what can u do",
    "what are you able to do",
    "what can you help me with",
    "capabilities",
}
_CAPABILITY_ZH = {
    "你能做什么",
    "你能做什么？",
    "你能干嘛",
    "你能干嘛？",
    "你能帮我什么",
    "你能帮我做什么",
    "你可以帮我干嘛",
    "你会什么",
}
_USAGE_EN = {
    "how can you modify code",
    "how do i ask you to change code",
    "how to ask you to change code",
}
_USAGE_ZH = {"怎么让你改代码", "怎么让你改代码？"}

# ---------------------------------------------------------------------------
# Structural hints — search, shell, repo inspection
# ---------------------------------------------------------------------------

_SEARCH_HINTS_EN = ("web search", "search ", "look up ", "search for ", "find docs for ")
_SHELL_HINTS_EN = ("run pytest", "run tests", "pytest", "npm test", "run npm test", "git status")

_REPO_HINTS_EN = (
    "inspect this repo",
    "inspect the workspace",
    "inspect workspace",
    "inspect repo",
    "read this project",
    "read this repo",
    "do not modify files",
    "take a look at this repository without changing files",
    "workspace only",
    "this folder",
)

# ---------------------------------------------------------------------------
# Skill management tokens — direct skill management actions only
# ---------------------------------------------------------------------------

_SKILL_MANAGEMENT_TOKENS = (
    "列出 skills",
    "列出可用 skills",
    "可用 skills",
    "禁用某个 skill",
    "启用 terminal 工具",
    "disable web tool",
    "list skills",
    "disable skill",
    "查看skill",
    "查看 skills",
    "列出 skill",
    "skill 列表",
)


def route_deterministically(envelope: InputEnvelope, *, input_kind: str = "unknown_task") -> IntentRoute:
    """Run deterministic high-confidence rules.

    Returns a high-confidence route if matched, or a low-confidence
    default route that signals "pass to LLM semantic router".
    """
    text = envelope.normalized_text
    low = text.lower()
    route = _default_route(input_kind=input_kind)

    if envelope.is_empty:
        return _replace(
            route,
            intent=Intent.CLARIFY.value,
            response_mode=ResponseMode.CLARIFY_QUESTION.value,
            confidence=0.4,
            source="clarify",
            summary="empty input",
            reason="empty_input",
            should_clarify=True,
            clarify_question="你可以直接告诉我想读项目、改代码、跑测试，还是搜索资料。",
        )
    if envelope.slash.is_slash_command:
        return _replace(
            route,
            intent=Intent.UNKNOWN.value,
            response_mode=ResponseMode.CLARIFY_QUESTION.value,
            confidence=1.0,
            source="slash",
            summary="slash command handled outside natural router",
            reason="slash_command_fast_path",
            should_clarify=False,
            clarify_question=None,
        )
    if _looks_like_greeting(text, low):
        return _replace(
            route,
            intent=Intent.CHAT.value,
            response_mode=ResponseMode.CHAT_ANSWER.value,
            confidence=0.98,
            summary="greeting",
            should_clarify=False,
            clarify_question=None,
            reason="greeting_rule",
        )
    if text in _IDENTITY_ZH or low in _IDENTITY_EN:
        return _replace(
            route,
            intent=Intent.CAPABILITY_QA.value,
            response_mode=ResponseMode.HELP_ANSWER.value,
            confidence=0.95,
            summary="identity question",
            should_clarify=False,
            clarify_question=None,
            reason="identity_rule",
        )
    if _looks_like_capability_question(text, low):
        return _replace(
            route,
            intent=Intent.CAPABILITY_QA.value,
            response_mode=ResponseMode.HELP_ANSWER.value,
            confidence=0.96,
            summary="capability question",
            should_clarify=False,
            clarify_question=None,
            reason="capability_rule",
        )
    if text in _USAGE_ZH or low in _USAGE_EN:
        return _replace(
            route,
            intent=Intent.USAGE_HELP.value,
            response_mode=ResponseMode.HELP_ANSWER.value,
            confidence=0.95,
            summary="usage help question",
            should_clarify=False,
            clarify_question=None,
            reason="usage_help_rule",
        )
    if any(token in text for token in ("继续上次任务", "恢复刚才那个 task")):
        return _replace(
            route,
            intent=Intent.CONTEXT_RESUME.value,
            response_mode=ResponseMode.CONTEXT_ADMIN.value,
            confidence=0.9,
            summary="resume previous context",
            memory_relevance="high",
            should_clarify=False,
            clarify_question=None,
            reason="context_resume_rule",
        )
    # Skill management — direct management actions only (pure queries)
    # Must NOT match coding/debug tasks that mention skill tokens as their target.
    # Strategy: if coding action verbs co-occur with skill query tokens,
    # this is a coding task ABOUT skills, not a skill query — skip to LLM.
    if _is_skill_query_but_not_coding(text, low):
        return _replace(
            route,
            intent=Intent.SKILL_MANAGEMENT.value,
            response_mode=ResponseMode.SKILL_ADMIN.value,
            confidence=0.9,
            summary="skill management request",
            requires_tools=["skills_registry"],
            should_clarify=False,
            clarify_question=None,
            reason="skill_management_rule",
        )
    if _looks_like_automation_request(text, low):
        return _replace(
            route,
            intent=Intent.AUTOMATION.value,
            response_mode=ResponseMode.AUTOMATION_ACTION.value,
            confidence=0.9,
            summary="automation/reminder request unsupported",
            requires_tools=["scheduler"],
            should_clarify=False,
            clarify_question=None,
            reason="automation_unsupported_rule",
        )
    if envelope.has_url:
        return _replace(
            route,
            intent=Intent.URL_SUMMARY.value,
            response_mode=ResponseMode.URL_SUMMARY.value,
            confidence=0.92,
            summary="url summarization request",
            reason="url_rule",
            requires_tools=["web_fetch"],
            requires_network=True,
            should_clarify=False,
            clarify_question=None,
        )
    # Repo inspection — structural read-only tokens
    if _looks_like_repo_inspection(text, low):
        return _replace(
            route,
            intent=Intent.REPO_INSPECTION.value,
            response_mode=ResponseMode.REPO_INSPECTION.value,
            confidence=0.93,
            summary="repo read-only inspection request",
            requires_tools=["repo_reader"],
            requires_repo_read=True,
            project_instruction_relevance="medium",
            should_clarify=False,
            clarify_question=None,
            reason="repo_inspection_rule",
        )
    if any(token in text for token in ("搜一下", "查一下 ", "搜索一下")) or any(token in low for token in _SEARCH_HINTS_EN):
        return _replace(
            route,
            intent=Intent.WEB_SEARCH.value,
            response_mode=ResponseMode.SEARCH_PIPELINE.value,
            confidence=0.9,
            summary="web search request",
            requires_tools=["web_search"],
            requires_network=True,
            should_clarify=False,
            clarify_question=None,
            reason="web_search_rule",
        )
    if _looks_like_coding_creation(text, low):
        requires_shell = _looks_like_run_request(text, low)
        return _replace(
            route,
            intent=Intent.CODING_TASK.value,
            response_mode=ResponseMode.AGENT_TOOL_LOOP.value,
            confidence=0.94,
            summary="code creation request",
            requires_tools=["file_editor"],
            requires_repo_read=True,
            requires_write=True,
            requires_shell=requires_shell,
            requires_approval=True,
            risk_level=RiskLevel.MEDIUM.value,
            project_instruction_relevance="high",
            suggested_test_scope="scoped" if requires_shell else "none",
            should_clarify=False,
            clarify_question=None,
            reason="coding_creation_rule",
        )
    if _looks_like_coding_modify(text, low):
        requires_shell = _looks_like_run_request(text, low)
        return _replace(
            route,
            intent=Intent.CODING_TASK.value,
            response_mode=ResponseMode.AGENT_TOOL_LOOP.value,
            confidence=0.9,
            summary="code modification request",
            requires_tools=["file_editor"],
            requires_repo_read=True,
            requires_write=True,
            requires_shell=requires_shell,
            requires_approval=True,
            risk_level=RiskLevel.MEDIUM.value,
            project_instruction_relevance="high",
            suggested_test_scope="scoped" if requires_shell else "none",
            should_clarify=False,
            clarify_question=None,
            reason="coding_modify_rule",
        )
    if _looks_like_shell_request(text, low):
        return _replace(
            route,
            intent=Intent.SHELL_TASK.value,
            response_mode=ResponseMode.EXECUTOR_ACTION.value,
            confidence=0.94,
            summary="shell execution request",
            requires_tools=["command_runner"],
            requires_shell=True,
            requires_approval=True,
            risk_level=RiskLevel.MEDIUM.value,
            suggested_test_scope="scoped",
            should_clarify=False,
            clarify_question=None,
            reason="shell_rule",
        )
    # These two are the ONLY ambiguous cases that deterministic handles
    # because they have very specific patterns that are almost always ambiguous
    if _looks_like_generic_ambiguous(text, low):
        return _replace(
            route,
            intent=Intent.CLARIFY.value,
            response_mode=ResponseMode.CLARIFY_QUESTION.value,
            confidence=0.82,
            source="clarify",
            summary="ambiguous request",
            should_clarify=True,
            clarify_question="你想让我做哪类操作：读项目、修改代码、运行命令，还是搜索资料？",
            reason="generic_ambiguous_rule",
        )
    if _looks_like_non_code_writing(text, low):
        return _replace(
            route,
            intent=Intent.CLARIFY.value,
            response_mode=ResponseMode.CLARIFY_QUESTION.value,
            confidence=0.78,
            source="clarify",
            summary="non-code writing request needs clarification",
            should_clarify=True,
            clarify_question="你是想让我写一段普通说明文本，还是创建/修改项目里的代码或文档文件？",
            reason="non_code_writing_rule",
        )

    # No high-confidence match — return default (will go to LLM semantic router)
    return route


# ---------------------------------------------------------------------------
# Helper predicates
# ---------------------------------------------------------------------------

def _looks_like_greeting(text: str, low: str) -> bool:
    return low in _CHAT_EN or text in _CHAT_ZH_EXACT or any(token in text for token in ("你好", "您好"))


def _looks_like_capability_question(text: str, low: str) -> bool:
    if text in _CAPABILITY_ZH:
        return True
    if low in _CAPABILITY_EN:
        return True
    return any(token in text for token in ("你能帮我什么", "你能帮我做什么", "你可以帮我干嘛"))


def _looks_like_repo_inspection(text: str, low: str) -> bool:
    """Check for structural repo inspection patterns (not general NL).

    Kept deterministic because these have very specific structural patterns
    that clearly indicate read-only intent.
    """
    zh_tokens = (
        "读项目",
        "读一下这个项目",
        "看一下项目结构",
        "分析一下这个仓库",
        "先读一下这个仓库",
        "帮我看看这个项目结构",
        "我现在文件夹下有哪些东西",
        "当前目录有什么",
        "列一下当前目录",
        "看看当前文件夹",
        "看看这个仓库是干什么的",
    )
    return any(token in text for token in zh_tokens) or any(token in low for token in _REPO_HINTS_EN)


def _looks_like_coding_creation(text: str, low: str) -> bool:
    creation_verbs_zh = ("写", "新建", "创建", "加一个", "加个", "帮我写", "在项目里加", "在当前目录写", "在这个工作空间写")
    creation_verbs_en = ("write", "create", "add", "implement")
    code_objects_zh = ("程序", "脚本", "文件", ".py", "函数", "类", "模块", "CLI", "Python")
    code_objects_en = ("python", "script", "file", ".py", "function", "class", "module", "cli")
    explicit_files = ("hello.py", "main.py", "hello_world.py")
    has_creation = any(token in text for token in creation_verbs_zh) or any(token in low for token in creation_verbs_en)
    has_code_object = any(token in text for token in code_objects_zh) or any(token in low for token in code_objects_en) or any(token in low for token in explicit_files)
    return has_creation and has_code_object and not _looks_like_non_code_writing(text, low) and not _looks_like_repo_inspection(text, low)


def _looks_like_coding_modify(text: str, low: str) -> bool:
    zh_tokens = ("修复", "改一下", "修改", "bug", "修一下", "处理 bug")
    en_tokens = ("fix this bug", "fix bug", "modify function", "change code", "patch")
    # Exclude negated forms: "不要修改", "先不要改", "不要 change" etc.
    if any(neg in text for neg in ("不要修改", "不要改", "先不要", "不需要修改", "不需修改")):
        return False
    if any(neg in low for neg in ("don't modify", "don't change", "do not modify", "no need to change")):
        return False
    return any(token in text for token in zh_tokens) or any(token in low for token in en_tokens)


def _looks_like_run_request(text: str, low: str) -> bool:
    return any(token in text for token in ("运行一下", "并运行", "跑测试", "并跑相关测试", "然后跑相关测试")) or any(
        token in low for token in ("run it", "and run it", "run tests", "run the relevant tests")
    )


def _looks_like_shell_request(text: str, low: str) -> bool:
    zh_tokens = ("运行 pytest", "跑一下 tests/", "python -m pytest", "git status", "运行一下 git status")
    return any(token in text for token in zh_tokens) or any(token in low for token in _SHELL_HINTS_EN)


def _looks_like_automation_request(text: str, low: str) -> bool:
    zh_tokens = ("提醒我", "定时", "每天", "明天上午", "明天下午", "取消刚才的提醒", "列出我的提醒")
    en_tokens = ("remind me", "schedule", "reminder", "cancel the reminder", "list my reminders")
    return any(token in text for token in zh_tokens) or any(token in low for token in en_tokens)


def _looks_like_non_code_writing(text: str, low: str) -> bool:
    """Very specific non-code writing patterns that are genuinely ambiguous."""
    zh_non_code = ("写一段说明", "写个总结", "写一封邮件", "写一段项目介绍", "写个东西", "帮我写一下")
    en_non_code = ("write a summary", "write something", "write an introduction", "write an email")
    return any(token in text for token in zh_non_code) or any(token in low for token in en_non_code)


def _looks_like_generic_ambiguous(text: str, low: str) -> bool:
    """Very specific ambiguous patterns that are genuinely unclear."""
    zh_tokens = ("弄一下", "处理一下", "看看这个", "来一下", "随便", "看着办")
    en_tokens = ("do something", "handle it", "take a look", "you decide")
    return any(token in text for token in zh_tokens) or any(token in low for token in en_tokens)


def _has_coding_action_verb(text: str, low: str) -> bool:
    """Detect coding/debug/analysis action verbs that indicate a task, not a query.

    These verbs mean the user wants to write/modify/test/analyze code ABOUT
    something (e.g., skill routing), rather than query/list skills.
    """
    zh_coding = ("修复", "修改", "实现", "补测试", "回归测试", "跑测试", "修一下", "处理 bug")
    en_coding = ("fix ", "implement ", "change ", "update ", "add test", "regression", "patch ")
    zh_analysis = ("分析", "定位", "排查", "调试", "诊断")
    en_analysis = ("analyze ", "investigate ", "debug ", "diagnose ", "troubleshoot ")
    return (
        any(token in text for token in zh_coding)
        or any(token in low for token in en_coding)
        or any(token in text for token in zh_analysis)
        or any(token in low for token in en_analysis)
    )


def _is_skill_query_but_not_coding(text: str, low: str) -> bool:
    """Check if input is a pure skill management query (not a coding task about skills).

    Returns True only if:
    1. Input matches a skill management token, AND
    2. Input does NOT contain coding action verbs

    This prevents "修复'查看skill'被误判的问题" from being routed to
    skill_management instead of agent_tool_loop.
    """
    has_skill_token = any(token in text or token in low for token in _SKILL_MANAGEMENT_TOKENS)
    if not has_skill_token:
        return False
    # If coding action verbs are present, this is a coding task about skills
    if _has_coding_action_verb(text, low):
        return False
    return True


# ---------------------------------------------------------------------------
# Default route — low confidence, signals "pass to LLM semantic router"
# ---------------------------------------------------------------------------

def _default_route(*, input_kind: str) -> IntentRoute:
    return IntentRoute(
        intent=Intent.UNKNOWN.value,
        response_mode=ResponseMode.CLARIFY_QUESTION.value,
        confidence=0.42,
        source="deterministic",
        summary="deterministic router uncertain",
        reason="no_high_confidence_rule_match",
        should_clarify=True,
        clarify_question=None,
        operator_trace={
            "source_surface": "cli",
            "route_source": "deterministic",
            "reason": f"classified_by_input_kind:{input_kind}",
        },
        routing_trace={
            "input_kind": "natural_language",
            "deterministic_attempted": True,
            "deterministic_matched": False,
            "llm_fallback_called": False,
            "llm_confidence": None,
            "entered_llm": False,
            "final_decision": Intent.UNKNOWN.value,
            "why_not_clarify": "",
        },
    )


def _replace(route: IntentRoute, **kwargs: object) -> IntentRoute:
    raw = route.to_dict()
    raw.update(kwargs)
    raw["operator_trace"] = {
        "source_surface": "cli",
        "route_source": "deterministic",
        "reason": kwargs.get("reason", raw.get("reason", "")),
    }
    trace = dict(raw.get("routing_trace") or {})
    trace["input_kind"] = "natural_language"
    trace["deterministic_attempted"] = True
    trace["deterministic_matched"] = kwargs.get("intent") not in {Intent.UNKNOWN.value, Intent.CLARIFY.value}
    trace["entered_llm"] = False
    trace["final_decision"] = kwargs.get("intent", raw.get("intent"))
    if trace["deterministic_matched"]:
        trace["why_not_clarify"] = f"High-confidence {kwargs.get('reason', 'rule')} matched."
    raw["routing_trace"] = trace
    return IntentRoute(**raw)
