"""Template-based natural language response renderers for the CLI dispatcher."""

from __future__ import annotations

from typing import Any


def render_chat_answer(route: dict[str, Any], user_input: str) -> str:
    return "I'm Jarvis, a local development assistant. How can I help?"


def render_help_answer(route: dict[str, Any], user_input: str) -> str:
    return "I'm Jarvis, a local development assistant. I can help with code, file operations, and running commands."


def render_plan_answer(route: dict[str, Any], user_input: str) -> str:
    return "Here's a plan for your request. Please let me know if you'd like to proceed."


def render_clarify_question(route: dict[str, Any]) -> str:
    clarify = route.get("clarify_question", "Could you clarify what you'd like me to do?")
    return str(clarify)


def render_refusal_safety() -> str:
    return "安全拒绝：不能直接执行敏感操作，涉及安全问题。"


def render_repo_inspection_result(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", "Repository inspection completed.")
    return str(summary)


def render_file_listing() -> str:
    return "Current directory listing completed."


def render_workspace_status(route: dict[str, Any], workspace_root: str) -> str:
    return f"Workspace status: {workspace_root}"


def render_debug_analysis(route: dict[str, Any], user_input: str) -> str:
    return "Debug analysis completed."


def render_context_admin() -> str:
    return "Context management operations completed."


def render_context_summary() -> str:
    return "Context summary completed."


def render_context_followup() -> str:
    return "Following up on previous context."


def render_automation_unsupported() -> str:
    return "Automation is not supported in this mode."


def render_search_network_policy() -> str:
    return "Web search requires network access approval."


def render_url_network_policy() -> str:
    return "URL fetching requires network access approval."


def render_skill_invocation_result(payload: dict[str, Any]) -> str:
    return payload.get("final_answer", "Skill execution completed.")
