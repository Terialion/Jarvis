"""Response and summary composition for AgentLoop."""

from __future__ import annotations

from typing import Any

from .types import ToolResult


class ResponseComposer:
    def compose(
        self,
        *,
        final_answer: str,
        tool_results: list[ToolResult],
        stop_reason: str,
        output_type: str = "answer",
        clarification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tools_used: list[str] = []
        files_changed: list[str] = []
        commands_run: list[str] = []
        tests_run: list[str] = []
        risks: list[str] = []

        for result in tool_results:
            tools_used.append(result.name)
            md = dict(result.metadata or {})
            files_changed.extend([str(x) for x in list(md.get("changed_files") or [])])
            commands_run.extend([str(x) for x in list(md.get("commands_run") or [])])
            tests_run.extend([str(x) for x in list(md.get("tests_run") or [])])
            if not result.ok and result.error:
                risks.append(f"{result.name}: {result.error}")

        outcome = "completed"
        if stop_reason in {"max_steps", "timeout", "approval_required", "no_progress"}:
            outcome = "partial"
        if not final_answer:
            outcome = "failed"

        conclusion = final_answer or "No final answer produced."
        human = (
            "结论:\n"
            f"- {conclusion}\n"
            "做了什么:\n"
            f"- 调用了 {len(tools_used)} 个工具\n"
            "调用了哪些工具:\n"
            f"- {', '.join(tools_used) if tools_used else '无'}\n"
            "改了哪些文件:\n"
            f"- {', '.join(files_changed) if files_changed else '无'}\n"
            "测试结果:\n"
            f"- {', '.join(tests_run) if tests_run else '无'}\n"
            "风险和未完成项:\n"
            f"- {('; '.join(risks)) if risks else '无'}\n"
            "下一步建议:\n"
            "- 如果是 partial/failed，先修复 stop_reason 对应问题后重试。"
        )

        machine = {
            "outcome": outcome,
            "output_type": output_type,
            "tools_used": tools_used,
            "files_changed": files_changed,
            "commands_run": commands_run,
            "tests_run": tests_run,
            "risks": risks,
            "stop_reason": stop_reason,
            "handoff_summary": conclusion[:400],
        }
        if clarification:
            machine["needs_user_clarification"] = True
            machine["missing_fields"] = list(clarification.get("missing_fields") or [])
            machine["clarification_question"] = str(clarification.get("question") or "").strip()
        return {"human": human, "machine": machine}
