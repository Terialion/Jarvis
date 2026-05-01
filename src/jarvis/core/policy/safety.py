"""SafetyGate — pre-execution safety checks for tool calls.

SafetyGate is the FIRST check in the ToolRuntime chain.
It blocks dangerous operations BEFORE permission or approval checks.
It cannot be overridden by LLM, JARVIS.md, AGENTS.md, or SKILL.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..tools.schema import ToolCall, ToolContext, ToolSpec

# Sensitive file patterns that MUST always be refused
_SENSITIVE_PATTERNS = [
    ".env",
    ".npmrc",
    ".pypirc",
    ".ssh/id_rsa",
    ".ssh/id_ed25519",
    ".ssh/id_dsa",
    "credential",
    "token",
    "secret",
    "private_key",
    "api_key",
    "password",
]

# Destructive command patterns
_DESTRUCTIVE_PATTERNS = [
    "rm -rf",
    "rm -r /",
    "del /s /q",
    "rmdir /s /q",
    "format ",
    "shutdown",
    "drop table",
]

# Dangerous shell pipelines
_DANGEROUS_PIPELINES = [
    ("curl ", "| sh"),
    ("curl ", "| bash"),
    ("wget ", "| sh"),
    ("wget ", "| bash"),
    ("invoke-webrequest", "| iex"),
    ("invoke-webrequest", "| invoke-expression"),
]


@dataclass
class SafetyCheckResult:
    allowed: bool
    reason: str | None = None
    risk_level: str = "low"


class SafetyGate:
    """Pre-execution safety gate.

    Rules:
    1. Sensitive file reads are ALWAYS refused (even in danger_full_access)
    2. Destructive commands are ALWAYS refused
    3. Dangerous shell pipelines are ALWAYS refused
    4. Cannot be overridden by LLM output, JARVIS.md, AGENTS.md, or SKILL.md
    """

    def check(self, spec: "ToolSpec", call: "ToolCall", context: "ToolContext") -> SafetyCheckResult:
        """Run safety checks on a tool call."""
        # Check arguments for sensitive file access
        args_str = _args_to_string(call.arguments)
        low = args_str.lower()

        # Sensitive file patterns
        for pattern in _SENSITIVE_PATTERNS:
            if pattern in low:
                return SafetyCheckResult(
                    allowed=False,
                    reason=f"safety_refusal: cannot access sensitive files matching '{pattern}'",
                    risk_level="blocked",
                )

        # Destructive commands
        for pattern in _DESTRUCTIVE_PATTERNS:
            if pattern in low:
                return SafetyCheckResult(
                    allowed=False,
                    reason=f"safety_refusal: destructive command '{pattern}' is blocked",
                    risk_level="blocked",
                )

        # Dangerous pipelines
        for pipe_cmd, pipe_sink in _DANGEROUS_PIPELINES:
            if pipe_cmd in low and pipe_sink in low:
                return SafetyCheckResult(
                    allowed=False,
                    reason="safety_refusal: dangerous shell pipeline (curl|wget|Invoke-WebRequest piped to shell)",
                    risk_level="blocked",
                )

        return SafetyCheckResult(allowed=True)


def _args_to_string(args: dict[str, Any]) -> str:
    """Convert arguments dict to a searchable string."""
    parts = []
    for key, value in args.items():
        parts.append(f"{key}={value}")
    return " ".join(parts)
