"""Deterministic CLI responses for natural-language response modes.

These render functions take a route/context dict and response_mode to produce
output. They do NOT inspect user input text to determine intent — intent
classification is the router's job.
"""

from __future__ import annotations

from typing import Any

from src.jarvis.core.routing.schema import Intent


def render_chat_answer(route: dict[str, Any], user_input: str = "") -> str:
    """Render a chat answer based on response_mode and route context.

    Does NOT parse user_input to decide intent. Uses route summary/context
    to determine the type of chat response.
    """
    summary = str(route.get("summary") or "").lower()
    mode = str(route.get("response_mode") or "")

    # Joke response — based on response_mode, not user input text
    if mode == "joke_answer" or "joke" in summary:
        import random
        jokes = [
            "为什么程序员总是分不清圣诞节和万圣节？因为 Oct 31 == Dec 25！",
            "程序员的三大谎言：1. 这个 bug 不在我这边；2. 我测过了，没问题；3. 这代码我写了注释。",
            "为什么Python程序员喜欢Python？因为他们不喜欢被编译器说'你错了'。",
            "一个SQL查询走进一家酒吧，看到两张表。他走过去问：'我能 JOIN 你们吗？'",
        ]
        return random.choice(jokes)

    # Identity response
    if mode == "identity_answer" or "identity" in summary:
        return "我是 Jarvis CLI，一个交互式命令行开发助手。我可以帮你读项目、解释代码、规划修改、跑测试，或者搜索技术资料。"

    # Use user language hint (from user_input) for rendering, not for intent
    has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in (user_input or ""))
    if has_chinese:
        return "你好，我在。你可以让我读项目、解释代码、规划修改、跑测试，或者查资料。"
    return "Hi, I'm here. I can inspect repositories, explain code, plan changes, run approved tests, or help search technical references."


def render_workspace_status(route: dict[str, Any], workspace_root: str = "") -> str:
    """Return current workspace directory information.

    Uses route context, not user input text, to determine this is a
    workspace status query.
    """
    import os
    cwd = os.getcwd()
    if not workspace_root:
        workspace_root = cwd
    return (
        f"当前工作目录：{cwd}\n"
        f"Jarvis 工作空间根目录：{workspace_root}\n\n"
        "如果需要查看目录内容，可以说：\"列一下当前目录\" 或 \"当前目录有什么\"。"
    )


def render_help_answer(route: dict[str, Any], user_input: str = "") -> str:
    """Render help answer based on route intent and response_mode."""
    intent = str(route.get("intent") or "")
    low = str(user_input or "").lower()
    if intent == Intent.USAGE_HELP.value:
        if "how" in low or "modify code" in low or "change code" in low:
            return (
                "You can ask me like this:\n\n"
                "1. Inspect first: \"Inspect this repo. Do not modify files.\"\n"
                "2. Plan the change: \"Fix the login bug, but show me the plan first.\"\n"
                "3. Approve editing: \"Apply option 1 and show me the diff.\"\n"
                "4. Run scoped tests: \"Run only the relevant tests.\"\n\n"
                "Flow: inspect -> plan -> approval -> edit -> diff -> scoped tests -> review."
            )
        return (
            "你可以这样让我改代码：\n\n"
            "1. 先让我读项目：\"先看看这个项目结构，不要修改。\"\n"
            "2. 再让我规划：\"帮我修复登录失败的问题，先给计划。\"\n"
            "3. 确认后再修改：\"按方案一改，改完给我 diff。\"\n"
            "4. 最后跑测试：\"只跑相关测试，不要全量回归。\"\n\n"
            "流程是：读项目 -> 计划 -> 等待确认 -> 修改 -> diff -> 测试 -> review。"
        )
    if "what" in low or "able to do" in low:
        return (
            "I can help with:\n\n"
            "1. Inspecting a repository without modifying files.\n"
            "2. Planning code changes before editing.\n"
            "3. Applying approved patches and showing diffs.\n"
            "4. Running scoped tests when allowed.\n"
            "5. Searching docs, GitHub issues, and release notes when network is enabled.\n"
            "6. Managing skills and keeping replay/evidence traces.\n\n"
            "To ask me to change code, say: \"Fix this bug, show me the plan first, and do not modify files until I approve.\""
        )
    return (
        "我可以帮你做这些事：\n\n"
        "1. 读项目：只读分析 README、配置、源码结构和测试目录。\n"
        "2. 改代码：先给计划，经你确认后修改，并展示 diff。\n"
        "3. 跑测试：根据改动范围运行 scoped tests，不默认全量回归。\n"
        "4. 查资料：在允许联网时搜索官方文档、GitHub issue、release notes。\n"
        "5. 管理 skills：查看、选择、审查和执行技能。\n"
        "6. 留痕回放：记录 route、evidence、replay，方便复盘。\n\n"
        "如果你想让我改代码，可以说：\"帮我修复 xxx，先给计划，不要直接改。\""
    )


def render_plan_answer(route: dict[str, Any], user_input: str = "") -> str:
    """Render a planning/analysis answer (no code written)."""
    return (
        "我可以帮你分析并规划修改方案。请告诉我你想要修改或重构的具体内容，"
        "我会先阅读相关代码，然后给出详细的修改计划，不会直接写入文件。\n\n"
        "例如：\"帮我规划如何重构输入路由模块\" 或 \"分析一下为什么登录会超时\"。"
    )


def render_debug_analysis(route: dict[str, Any], user_input: str = "") -> str:
    """Render a debug analysis response."""
    return (
        "我可以帮你排查问题。请告诉我具体的错误信息、现象、或你想排查的模块，"
        "我会先阅读相关代码和日志来定位问题，然后给出分析结果和修复建议。\n\n"
        "例如：\"帮我查一下为什么 pytest 超时\" 或 \"为什么这个函数返回 None\"。"
    )


def render_clarify_question(route: dict[str, Any]) -> str:
    return str(route.get("clarify_question") or "我需要再确认一下：你希望我读项目、修改代码、运行测试，还是搜索资料？")


def render_repo_inspection_result(result: dict[str, Any]) -> str:
    lines: list[str] = ["Repository inspection complete.", "", "Workspace:", f"  {result.get('workspace_root', '-')}", ""]
    lines.append("Project type:")
    for item in list(result.get("project_type") or ["unknown"]):
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("Read files:")
    for item in list(result.get("files_read") or [])[:12]:
        p = item.get("path", "") if isinstance(item, dict) else ""
        lines.append(f"  - {p}")
    lines.append("")
    lines.append("Skipped:")
    for item in list(result.get("files_skipped") or [])[:12]:
        if isinstance(item, dict):
            lines.append(f"  - {item.get('path', '')} ({item.get('reason', '')})")
    lines.append("")
    lines.append("Entrypoints:")
    for item in list(result.get("entrypoints") or []):
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("Important modules:")
    for item in list(result.get("important_modules") or []):
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("Tests:")
    for item in list(result.get("test_layout") or []):
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("Summary:")
    lines.append(f"  {result.get('architecture_summary', '')}")
    lines.append("")
    lines.append("Safety notes:")
    for item in list(result.get("safety_notes") or []):
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("Next suggestions:")
    for idx, item in enumerate(list(result.get("next_suggestions") or []), start=1):
        lines.append(f"  {idx}. {item}")
    return "\n".join(lines)


def render_coding_loop_result(result: dict[str, Any]) -> str:
    review = dict(result.get("final_review") or {})
    lines = [
        "Coding loop complete.",
        "",
        "Status",
        f"  {review.get('status', result.get('status', 'unknown'))}",
        "",
        "Stop reason",
        f"  {review.get('stop_reason', result.get('stop_reason', '-'))}",
        "",
        "Rounds",
        f"  {review.get('rounds', result.get('rounds', 0))}",
        "",
        "Changed files",
    ]
    if str(review.get("stop_reason") or result.get("stop_reason") or "") == "approval_required":
        lines.insert(1, "Approval required")
        lines.insert(2, "")
    changed = list(review.get("changed_files") or result.get("changed_files") or [])
    lines.extend([f"  - {item}" for item in changed] or ["  - none"])
    lines.extend(["", "Test status", f"  {review.get('test_status', 'not_run')}", "", "Risk level", f"  {review.get('risk_level', result.get('risk_level', 'medium'))}"])
    if result.get("approvals"):
        lines.extend(["", "Approvals"])
        for item in list(result.get("approvals") or [])[:3]:
            lines.append(f"  - {item.get('kind', 'action')}: {item.get('status', '-')}")
    if result.get("diffs"):
        lines.extend(["", "Diff"])
        first = dict(list(result.get("diffs") or [{}])[0])
        lines.append(str(first.get("diff", ""))[:1200])
    lines.extend(["", "Evidence"])
    refs = list(review.get("evidence_refs") or [])
    lines.extend([f"  - {item}" for item in refs] or ["  - none"])
    suggestions = list(review.get("next_suggestions") or result.get("next_suggestions") or [])
    if suggestions:
        lines.extend(["", "Next suggestions"])
        for idx, item in enumerate(suggestions[:3], 1):
            label = item.get("label", item) if isinstance(item, dict) else str(item)
            lines.append(f"  {idx}. {label}")
    return "\n".join(lines)


def render_search_network_policy() -> str:
    return "我已识别为搜索请求，但当前网络能力未启用或需要审批。不会自动联网执行。"


def render_url_network_policy() -> str:
    return "我已识别为 URL 总结请求，但当前网络能力未启用或需要审批。不会自动联网执行。"


def render_context_admin() -> str:
    return "我可以继续最近的任务。请用 /replay 查看最近 task，或用 /tasks 查看任务列表后指定继续目标。"


def render_automation_unsupported() -> str:
    return "Automation/reminder scheduling is not implemented in this Jarvis CLI yet. No reminder was created."


def render_refusal_safety() -> str:
    return "这个请求涉及高风险或敏感文件，我不能直接执行。你可以改成让我检查项目结构、查看非敏感配置，或说明具体安全目的后走审批流程。"


def render_context_summary() -> str:
    return "当前没有活跃的任务上下文。你可以开始一个新任务，或用 /tasks 查看历史任务。"


def render_context_followup() -> str:
    return "你想继续讨论之前的话题吗？请告诉我具体想了解什么。"


def render_file_listing() -> str:
    """Default file listing response (actual listing done by executor)."""
    import os
    cwd = os.getcwd()
    items = os.listdir(cwd) if os.path.isdir(cwd) else []
    if not items:
        return f"当前目录 {cwd} 为空。"
    lines = [f"当前目录 {cwd} 的内容："]
    for item in sorted(items)[:30]:
        lines.append(f"  {item}")
    if len(items) > 30:
        lines.append(f"  ... 共 {len(items)} 项")
    return "\n".join(lines)
