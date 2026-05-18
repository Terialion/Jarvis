"""Unified schema for Hybrid Intent Router."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Intent(str, Enum):
    CHAT = "chat"
    CAPABILITY_QA = "capability_qa"
    USAGE_HELP = "usage_help"
    REPO_INSPECTION = "repo_inspection"
    CODING_TASK = "coding_task"
    WEB_SEARCH = "web_search"
    URL_SUMMARY = "url_summary"
    SHELL_TASK = "shell_task"
    SKILL_MANAGEMENT = "skill_management"
    CONTEXT_RESUME = "context_resume"
    MODEL_MANAGEMENT = "model_management"
    AUTOMATION = "automation"
    CLARIFY = "clarify"
    UNKNOWN = "unknown"

    # New intents
    IDENTITY = "identity"
    EXPLAIN = "explain"
    WRITING = "writing"
    SUMMARY = "summary"
    DOC_EDIT = "doc_edit"
    AMBIGUOUS = "ambiguous"
    SAFETY = "safety"
    CONTEXT_FOLLOWUP = "context_followup"


class ResponseMode(str, Enum):
    CHAT_ANSWER = "chat_answer"
    HELP_ANSWER = "help_answer"
    REPO_INSPECTION = "repo_inspection"
    AGENT_TOOL_LOOP = "agent_tool_loop"
    SEARCH_PIPELINE = "search_pipeline"
    URL_SUMMARY = "url_summary"
    EXECUTOR_ACTION = "executor_action"
    SKILL_ADMIN = "skill_admin"
    CONTEXT_ADMIN = "context_admin"
    MODEL_ADMIN = "model_admin"
    AUTOMATION_ACTION = "automation_action"
    CLARIFY_QUESTION = "clarify_question"
    REFUSAL_OR_SAFETY_MESSAGE = "refusal_or_safety_message"
    
    # New response modes
    WORKSPACE_STATUS = "workspace_status"
    FILE_LISTING = "file_listing"
    JOKE_ANSWER = "joke_answer"
    PLAN_ANSWER = "plan_answer"
    DEBUG_ANALYSIS = "debug_analysis"
    CONTEXT_SUMMARY = "context_summary"
    CONTEXT_FOLLOWUP = "context_followup"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SafetyDecision:
    requires_approval: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class IntentRoute:
    intent: str
    response_mode: str
    confidence: float
    summary: str
    source: str = "deterministic"
    reason: str = ""
    requires_tools: list[str] = field(default_factory=list)
    requires_repo_read: bool = False
    requires_write: bool = False
    requires_shell: bool = False
    requires_network: bool = False
    requires_approval: bool = False
    risk_level: str = RiskLevel.LOW.value
    should_clarify: bool = False
    clarify_question: str | None = None
    candidate_skills: list[str] = field(default_factory=list)
    project_instruction_relevance: str = "none"
    suggested_test_scope: str = "none"
    memory_relevance: str = "none"
    learning_signal: str = "none"
    operator_trace: dict[str, Any] = field(default_factory=dict)
    routing_trace: dict[str, Any] = field(default_factory=dict)
    safety_decision: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
