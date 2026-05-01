"""AgentRequestRouter — determines if user input is chat or work, and what tools are needed.

This is the P0 component. Without it, ToolRuntime cannot be integrated.

Output:
- is_work_request: bool
- work_type: repo_inspection | file_listing | skill_management | skill_agent | coding_loop | executor_action | url_summary | search_pipeline | automation_action | null
- chat_type: chat_answer | identity_answer | help_answer | usage_help | explain_answer | plan_answer | joke_answer | null
- required_tools: list[str]
- tool_plan: list[dict]
- requires_repo_read, requires_write, requires_shell, requires_network, requires_approval

Core rules:
- Chat requests: no tools, no approval, no file/shell/network
- Work requests: generate required_tools and tool_plan
- Global intent verbs override local noun keywords
- "不要改代码" / "先分析" = analysis/plan, no write
- Safety高危 (rm -rf, .env) = refusal, not LLM
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRequest:
    """Structured output of the AgentRequestRouter."""

    raw_text: str
    is_work_request: bool
    work_type: str | None
    chat_type: str | None
    response_mode: str
    confidence: float
    summary: str
    required_tools: list[str] = field(default_factory=list)
    tool_plan: list[dict[str, Any]] = field(default_factory=list)
    requires_repo_read: bool = False
    requires_write: bool = False
    requires_shell: bool = False
    requires_network: bool = False
    requires_approval: bool = False
    risk_level: str = "low"
    should_clarify: bool = False
    clarify_question: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "is_work_request": self.is_work_request,
            "work_type": self.work_type,
            "chat_type": self.chat_type,
            "response_mode": self.response_mode,
            "confidence": self.confidence,
            "summary": self.summary,
            "required_tools": self.required_tools,
            "tool_plan": self.tool_plan,
            "requires_repo_read": self.requires_repo_read,
            "requires_write": self.requires_write,
            "requires_shell": self.requires_shell,
            "requires_network": self.requires_network,
            "requires_approval": self.requires_approval,
            "risk_level": self.risk_level,
            "should_clarify": self.should_clarify,
            "clarify_question": self.clarify_question,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Safety patterns — these ALWAYS produce refusal
# ---------------------------------------------------------------------------

_SENSITIVE_FILE_PATTERNS = [
    ".env", ".npmrc", ".ssh", "id_rsa", "id_ed25519",
    "credential", "token", "secret", "private_key", "api_key", "password",
]

_DESTRUCTIVE_PATTERNS = [
    "rm -rf", "rm -r /", "del /s /q", "rmdir /s /q",
    "删除整个项目", "delete entire project",
]

_DANGEROUS_PIPELINES = [
    ("curl ", "| sh"), ("curl ", "| bash"),
    ("wget ", "| sh"), ("wget ", "| bash"),
    ("invoke-webrequest", "| iex"),
]


# ---------------------------------------------------------------------------
# Chat classification patterns — high confidence, no tools needed
# ---------------------------------------------------------------------------

_CHAT_EXACT = {
    "你好", "你好啊", "嗨", "嘿", "哈喽", "在吗",
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
    "ciallo",
}

_IDENTITY_EXACT = {
    "你是谁", "你是什么", "who are you", "what are you",
}

_CAPABILITY_EXACT = {
    "你能做什么", "你能做什么？", "你能干嘛", "你能干嘛？",
    "你能帮我什么", "你能帮我做什么", "你可以帮我干嘛", "你会什么",
    "what can you do", "capabilities",
}

_USAGE_EXACT = {
    "怎么让你改代码", "怎么让你改代码？",
    "how can you modify code",
}

_THANKS_EXACT = {
    "thanks", "thank you", "ok", "okay", "great", "谢谢", "多谢",
}

_JOKE_PATTERNS = [
    "给我讲个笑话", "讲个笑话", "tell me a joke", "说个笑话",
    "来个笑话",
]

# ---------------------------------------------------------------------------
# Work classification patterns
# ---------------------------------------------------------------------------

_WORK_DIR_PATTERNS = [
    "我现在的目录是什么", "当前目录是什么", "当前目录有什么",
    "列一下当前目录", "列出当前目录", "看看当前文件夹",
    "我现在的文件夹下有哪些东西",
]

_WORK_SKILL_PATTERNS = [
    "查看skill", "查看 skills", "查看技能", "列出 skill", "列出 skills",
    "列出技能", "skill 列表", "skill列表", "可用 skills",
]

_WORK_REPO_PATTERNS = [
    "检查一下这个项目的结构", "帮我看看项目结构", "读项目", "读一下这个项目",
    "看一下项目结构", "先读一下这个仓库", "帮我检查一下项目的结构",
    "inspect this repo", "inspect repo", "read this project",
    "do not modify files", "workspace only",
]

# Multi-step patterns — "先X，再Y" style requests
_MULTI_STEP_PREFIX = ("先", "先帮我", "先读", "先检查", "先看", "先列", "先搜索", "先找到", "然后", "接着")

_WORK_SHELL_PATTERNS = [
    "运行 pytest", "跑一下 tests", "跑测试", "运行一下 git status",
    "git status", "pytest", "run tests", "run pytest",
]

_WORK_URL_PATTERNS = ["总结一下 https://", "总结 https://", "summary https://"]

_WORK_SEARCH_PATTERNS = [
    "搜一下", "搜一搜", "查一下 ", "搜索一下", "搜索 ", "web search", "search for",
    "用 web-search", "用 web search",
]

# ---------------------------------------------------------------------------
# Coding action verbs — these override local noun keywords
# ---------------------------------------------------------------------------

_CODING_VERBS_ZH = ("修复", "修改", "实现", "补测试", "回归测试", "跑测试", "修一下", "处理 bug", "新建", "创建")
_CODING_VERBS_EN = ("fix ", "implement ", "change ", "update ", "add test", "regression", "patch ")

_NEGATION_ZH = ("不要修改", "不要改", "先不要", "不需要修改", "不需修改", "不要直接改", "不要写", "不用写")
_NEGATION_EN = ("don't modify", "don't change", "do not modify", "no need to change", "先不要")

_PLAN_VERBS_ZH = ("帮我分析", "先分析", "帮我规划", "帮我设计", "先给计划", "不要改代码", "不要直接改")
_PLAN_VERBS_EN = ("analyze why", "help me plan", "help me design", "without writing code", "don't change")


def _has_coding_verb(text: str, low: str) -> bool:
    return any(v in text for v in _CODING_VERBS_ZH) or any(v in low for v in _CODING_VERBS_EN)


def _has_negation(text: str, low: str) -> bool:
    return any(n in text for n in _NEGATION_ZH) or any(n in low for n in _NEGATION_EN)


def _has_plan_intent(text: str, low: str) -> bool:
    return any(p in text for p in _PLAN_VERBS_ZH) or any(p in low for p in _PLAN_VERBS_EN)


def _has_shell_intent(text: str, low: str) -> bool:
    return (any(t in text for t in ("跑测试", "并跑", "然后跑", "运行 pytest", "运行一下", "run tests", "run pytest"))
            or any(t in low for t in ("run tests", "and run", "pytest")))


def _is_safety_hazard(text: str, low: str) -> bool:
    if any(p in low for p in _SENSITIVE_FILE_PATTERNS):
        return True
    if any(p in low for p in _DESTRUCTIVE_PATTERNS):
        return True
    for cmd, sink in _DANGEROUS_PIPELINES:
        if cmd in low and sink in low:
            return True
    return False


def route_agent_request(raw_text: str) -> AgentRequest:
    """Route a user input to either chat or work path.

    Returns an AgentRequest with is_work_request, required_tools, and tool_plan.
    """
    text = raw_text.strip()
    low = text.lower()

    # 0. Safety first — ALWAYS refuse, never enter LLM
    if _is_safety_hazard(text, low):
        return AgentRequest(
            raw_text=text,
            is_work_request=False,
            work_type=None,
            chat_type=None,
            response_mode="refusal_or_safety_message",
            confidence=0.99,
            summary="safety refusal",
            required_tools=[],
            tool_plan=[],
            risk_level="blocked",
            reason="safety_hazard_detected",
        )

    # 1. Chat classification — high confidence exact matches
    if text in _CHAT_EXACT or low in _CHAT_EXACT:
        return _chat_request(text, "chat_answer", "greeting")

    if text in _IDENTITY_EXACT or low in _IDENTITY_EXACT:
        return _chat_request(text, "help_answer", "identity question")

    if text in _CAPABILITY_EXACT:
        return _chat_request(text, "help_answer", "capability question")

    if text in _USAGE_EXACT:
        return _chat_request(text, "help_answer", "usage help")

    if text in _THANKS_EXACT:
        return _chat_request(text, "chat_answer", "thanks")

    # Joke patterns
    if any(p in text for p in _JOKE_PATTERNS):
        return _chat_request(text, "joke_answer", "joke request")

    # 2. Explain/plan WITHOUT writing code
    if _has_plan_intent(text, low) and not _has_coding_verb(text, low):
        return _chat_request(text, "plan_answer", "planning/analysis request")

    # "不要改代码" explicit negation
    if _has_negation(text, low):
        return _chat_request(text, "plan_answer", "analysis with no code changes")

    # 3. Work classification — check for coding verbs first (they override local keywords)
    if _has_coding_verb(text, low) and not _has_negation(text, low):
        has_shell = _has_shell_intent(text, low)
        return _work_request(
            text,
            "coding_loop",
            required_tools=["workspace.search_files", "workspace.read_file", "patch.apply"],
            requires_repo_read=True,
            requires_write=True,
            requires_shell=has_shell,
            requires_approval=True,
            reason="coding action verb detected",
        )

    # 4. Skill management — ONLY if no coding verb co-occurs
    if any(p in text for p in _WORK_SKILL_PATTERNS) and not _has_coding_verb(text, low):
        return _work_request(
            text,
            "skill_management",
            required_tools=["skill.list"],
            reason="skill management query",
        )

    # 5. Shell/executor actions — but coding verbs or write+code object override
    _has_write_code = False
    if not _has_coding_verb(text, low):
        _write_verbs = ("写", "新建", "创建", "帮我写")
        _code_objects = ("程序", "脚本", "文件", ".py", "函数", "类", "模块", "CLI", "Python")
        _has_write_code = (any(v in text for v in _write_verbs)
                          and (any(o in text for o in _code_objects) or any(o in low for o in ("python", "script", "function", "class"))))
    if any(p in text for p in _WORK_SHELL_PATTERNS) and not _has_negation(text, low) and not _has_coding_verb(text, low) and not _has_write_code:
        return _work_request(
            text,
            "executor_action",
            required_tools=["shell.run"],
            requires_shell=True,
            requires_approval=True,
            reason="shell execution request",
        )

    # 6. URL summary
    if any(p in text for p in _WORK_URL_PATTERNS) or "https://" in text or "http://" in text:
        return _work_request(
            text,
            "url_summary",
            required_tools=["web.fetch"],
            requires_network=True,
            reason="URL summarization request",
        )

    # 7. Web search
    if any(p in text for p in _WORK_SEARCH_PATTERNS):
        return _work_request(
            text,
            "search_pipeline",
            required_tools=["web.search"],
            requires_network=True,
            reason="web search request",
        )

    # 8. Directory/file listing
    if any(p in text for p in _WORK_DIR_PATTERNS):
        return _work_request(
            text,
            "file_listing",
            required_tools=["workspace.status", "workspace.list_dir"],
            requires_repo_read=True,
            reason="directory listing request",
        )

    # 9. Repo inspection
    if any(p in text for p in _WORK_REPO_PATTERNS):
        return _work_request(
            text,
            "repo_inspection",
            required_tools=["repo.inspect", "workspace.search_files", "workspace.read_file"],
            requires_repo_read=True,
            reason="repo inspection request",
        )

    # 10. "解释/介绍" type requests — chat unless explicitly asking to read repo
    if any(w in text for w in ("解释", "介绍一下", "什么是", "explain", "tell me about")):
        if "项目" in text or "repo" in low or "仓库" in text:
            return _work_request(
                text,
                "repo_inspection",
                required_tools=["repo.inspect"],
                requires_repo_read=True,
                reason="explain with repo context",
            )
        return _chat_request(text, "plan_answer", "explanation request")

    # 11. Write/create actions (写 + code object)
    _WRITE_VERBS_ZH = ("写", "新建", "创建", "帮我写")
    _CODE_OBJECTS = ("程序", "脚本", "文件", ".py", "函数", "类", "模块", "CLI", "Python")
    has_write_verb = any(v in text for v in _WRITE_VERBS_ZH)
    has_code_object = any(o in text for o in _CODE_OBJECTS) or any(o in low for o in ("python", "script", "function", "class"))
    if has_write_verb and has_code_object and not _has_negation(text, low):
        has_shell = _has_shell_intent(text, low)
        return _work_request(
            text,
            "coding_loop",
            required_tools=["workspace.search_files", "workspace.read_file", "patch.apply"],
            requires_repo_read=True,
            requires_write=True,
            requires_shell=has_shell,
            requires_approval=True,
            reason="code creation request",
        )

    # 12. Multi-step requests ("先X，再Y") — read-only unless coding verb present
    if any(text.startswith(p) for p in _MULTI_STEP_PREFIX) or "，再" in text or "，然后" in text:
        if _has_coding_verb(text, low) and not _has_negation(text, low):
            has_shell = _has_shell_intent(text, low)
            return _work_request(
                text,
                "coding_loop",
                required_tools=["workspace.search_files", "workspace.read_file", "patch.apply"],
                requires_repo_read=True,
                requires_write=True,
                requires_shell=has_shell,
                requires_approval=True,
                reason="multi-step coding request",
            )
        # Multi-step read-only
        return _work_request(
            text,
            "repo_inspection",
            required_tools=["repo.inspect", "workspace.search_files", "workspace.read_file"],
            requires_repo_read=True,
            reason="multi-step inspection request",
        )

    # 13. Default — classify as chat (safer than assuming work)
    return _chat_request(text, "chat_answer", "default classification")


def _chat_request(text: str, chat_type: str, summary: str) -> AgentRequest:
    """Create a chat request with no tools."""
    return AgentRequest(
        raw_text=text,
        is_work_request=False,
        work_type=None,
        chat_type=chat_type,
        response_mode=chat_type,
        confidence=0.9,
        summary=summary,
        required_tools=[],
        tool_plan=[],
        reason=f"chat_request: {summary}",
    )


def _work_request(
    text: str,
    work_type: str,
    *,
    required_tools: list[str] | None = None,
    requires_repo_read: bool = False,
    requires_write: bool = False,
    requires_shell: bool = False,
    requires_network: bool = False,
    requires_approval: bool = False,
    reason: str = "",
) -> AgentRequest:
    """Create a work request with tools."""
    tools = required_tools or []
    tool_plan = [{"tool_name": t, "arguments": {}, "reason": reason} for t in tools]
    return AgentRequest(
        raw_text=text,
        is_work_request=True,
        work_type=work_type,
        chat_type=None,
        response_mode=work_type,
        confidence=0.9,
        summary=f"work request: {work_type}",
        required_tools=tools,
        tool_plan=tool_plan,
        requires_repo_read=requires_repo_read,
        requires_write=requires_write,
        requires_shell=requires_shell,
        requires_network=requires_network,
        requires_approval=requires_approval,
        risk_level="medium" if requires_write or requires_shell else "low",
        reason=reason,
    )
