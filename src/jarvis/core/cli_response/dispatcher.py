"""CLI dispatcher for routed natural-language responses.

Dispatches based on response_mode from the routing pipeline.
Does NOT inspect user input text to determine response type.
"""

from __future__ import annotations

from typing import Any, Callable

from .natural_responses import (
    render_chat_answer,
    render_clarify_question,
    render_automation_unsupported,
    render_context_admin,
    render_context_followup,
    render_context_summary,
    render_debug_analysis,
    render_file_listing,
    render_help_answer,
    render_plan_answer,
    render_refusal_safety,
    render_repo_inspection_result,
    render_search_network_policy,
    render_url_network_policy,
    render_workspace_status,
)

TaskRunner = Callable[[str], str]
SkillAdminRunner = Callable[[], str]
RepoInspectionRunner = Callable[[str], dict[str, Any]]
CodingLoopRunner = Callable[[str], dict[str, Any]]
AgentToolLoopRunner = Callable[[str], tuple[str, bool, str]]
LLMChatRunner = Callable[[str, str], str | None]


def dispatch_natural_language(
    *,
    user_input: str,
    route_after_safety: dict[str, Any],
    run_existing_task_flow: TaskRunner,
    run_skill_admin: SkillAdminRunner,
    run_repo_inspection: RepoInspectionRunner,
    run_coding_loop: CodingLoopRunner | None = None,
    run_agent_tool_loop: AgentToolLoopRunner | None = None,
    run_llm_chat: LLMChatRunner | None = None,
    llm_provider_available: bool = False,
) -> tuple[str, bool, str, str]:
    """Dispatch natural language responses based on response_mode.

    Args:
        user_input: Original user input text (passed to renderers for context, not for intent matching).
        route_after_safety: The IntentRoute dict after safety gate processing.
        run_existing_task_flow: Fallback task runner for coding/executor modes.
        run_skill_admin: Skill admin runner.
        run_repo_inspection: Repo inspection runner.
        run_coding_loop: Optional coding loop runner.

    Returns:
        (response_text, is_dangerous, mode, mode_description)
    """
    mode = str(route_after_safety.get("response_mode") or "clarify_question")

    chat_like_modes = {"chat_answer", "identity_answer", "joke_answer", "plan_answer", "explain_answer"}
    if mode in chat_like_modes:
        if llm_provider_available and run_llm_chat is not None:
            llm_text = run_llm_chat(user_input, mode)
            if llm_text:
                return llm_text, False, mode, "llm_chat_response"
        # template fallback path
        if mode == "plan_answer":
            return render_plan_answer(route_after_safety, user_input), False, mode, "template_fallback_plan"
        return render_chat_answer(route_after_safety, user_input), False, mode, "template_fallback_chat"

    # Help and usage
    if mode == "help_answer":
        return render_help_answer(route_after_safety, user_input), False, mode, "help response"
    if mode == "usage_help":
        return render_help_answer(route_after_safety, user_input), False, mode, "usage help response"

    # Planning and analysis (no code changes)
    if mode == "debug_analysis":
        return render_debug_analysis(route_after_safety, user_input), False, mode, "debug analysis response"

    # Clarification
    if mode == "clarify_question":
        if llm_provider_available and run_llm_chat is not None and _should_try_llm_chat_from_clarify(user_input):
            llm_text = run_llm_chat(user_input, "chat_answer")
            if llm_text:
                return llm_text, False, "chat_answer", "llm_chat_recovered_from_clarify"
        return render_clarify_question(route_after_safety), False, mode, "clarify response"

    # Safety refusal
    if mode == "refusal_or_safety_message":
        return render_refusal_safety(), False, mode, "safety refusal"

    # AgentToolLoop — work requests with tool execution
    # This covers all work-type modes: agent_tool_loop, file_listing, workspace_status,
    # skill_management, repo_inspection, executor_action, coding_loop, url_summary, search_pipeline
    # NOTE: This MUST be checked BEFORE individual legacy handlers to ensure work modes
    # go through AgentToolLoop when available.
    _WORK_MODES = {
        "agent_tool_loop", "file_listing", "workspace_status",
        "skill_management", "repo_inspection", "executor_action",
        "coding_loop", "url_summary", "search_pipeline",
    }
    if mode in _WORK_MODES and run_agent_tool_loop is not None:
        response_text, is_dangerous, loop_summary = run_agent_tool_loop(user_input)
        return response_text, is_dangerous, mode, f"agent_tool_loop: {loop_summary}"

    # Legacy fallback: work modes without agent_tool_loop use existing task flow
    if mode in _WORK_MODES:
        return run_existing_task_flow(user_input), True, mode, f"{mode} routed to existing task flow (legacy)"

    # Repo inspection (read-only) — legacy path when agent_tool_loop not available
    if mode == "repo_inspection":
        payload = run_repo_inspection(user_input)
        return render_repo_inspection_result(payload), False, mode, "repo inspection read-only response"

    # File listing and workspace status — legacy path
    if mode == "file_listing":
        return render_file_listing(), False, mode, "file listing response"
    if mode == "workspace_status":
        from pathlib import Path
        workspace_root = str(Path.cwd().parent)
        return render_workspace_status(route_after_safety, workspace_root), False, mode, "workspace status response"

    # Context
    if mode == "context_admin":
        return render_context_admin(), False, mode, "context admin response"
    if mode == "context_summary":
        return render_context_summary(), False, mode, "context summary response"
    if mode == "context_followup":
        return render_context_followup(), False, mode, "context followup response"

    # Network-gated operations — legacy path
    if mode == "search_pipeline":
        return render_search_network_policy(), False, mode, "network gated search response"
    if mode == "url_summary":
        return render_url_network_policy(), False, mode, "network gated url response"

    # Coding loop (with optional dedicated runner, only if not caught above)
    if mode == "coding_loop" and run_coding_loop is not None:
        from .natural_responses import render_coding_loop_result
        return render_coding_loop_result(run_coding_loop(user_input)), True, mode, "coding_loop routed to orchestrator"

    # Coding loop and executor action fallback to existing task flow (legacy only)
    if mode in {"coding_loop", "executor_action"}:
        return run_existing_task_flow(user_input), True, mode, f"{mode} routed to existing task flow"

    # Model admin — not yet implemented
    if mode == "model_admin":
        return "Model management is handled through /model commands.", False, mode, "model admin response"

    # Final fallback — should rarely be reached
    return render_clarify_question(route_after_safety), False, "clarify_question", "clarify fallback"


def _should_try_llm_chat_from_clarify(user_input: str) -> bool:
    text = (user_input or "").strip().lower()
    if not text:
        return False
    markers = [
        "你是谁", "你能做什么", "你可以帮我", "解释", "讲一个", "笑话", "规划",
        "下一步", "靠谱吗", "会不会太复杂",
        "who are you", "what can you do", "explain", "joke", "plan", "next step",
    ]
    return any(m in text for m in markers)
