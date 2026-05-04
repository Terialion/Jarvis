"""Final answer and handoff summary composer."""

from __future__ import annotations

from .types import AgentRunResult, ToolResult


class SummaryComposer:
    def compose(self, *, answer: str, tool_results: list[ToolResult], stop_reason: str) -> dict:
        changed_files = []
        tests = []
        evidence = []
        risks = []
        for r in tool_results:
            if not r.ok:
                risks.append({"tool": r.name, "error": r.error, "error_type": r.error_type})
            if r.data.get("changed_files"):
                changed_files.extend(r.data.get("changed_files") or [])
            if r.data.get("tests"):
                tests.extend(r.data.get("tests") or [])
            if r.content:
                evidence.append({"tool": r.name, "summary": r.content[:500]})
        return {
            "answer": answer,
            "tools_used": [r.name for r in tool_results],
            "evidence": evidence,
            "changed_files": changed_files,
            "tests": tests,
            "risks": risks,
            "stop_reason": stop_reason,
        }
