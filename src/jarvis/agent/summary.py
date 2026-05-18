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
        available_skills: list[str] | None = None,
        loaded_skills: list[str] | None = None,
        skill_loads_count: int = 0,
        skills_used: list[str] | None = None,
        skill_calls_count: int = 0,
        skill_results: list[dict[str, Any]] | None = None,
        active_task: dict[str, Any] | None = None,
        handoff_summary: dict[str, Any] | None = None,
        previous_summaries: list[dict[str, Any]] | None = None,
        context_reuse: bool = False,
        skill_observations: list[dict[str, Any]] | None = None,
        research_observations: list[dict[str, Any]] | None = None,
        web_search_runs_count: int = 0,
        web_fetch_runs_count: int = 0,
        web_fetch_blocked_count: int = 0,
        evidence_count: int = 0,
        official_sources_count: int = 0,
        github_sources_count: int = 0,
        research_context_reused: bool = False,
        web_provider_errors: int = 0,
        web_no_results_count: int = 0,
        search_results_count: int = 0,
        search_result_dedup_count: int = 0,
        release_note_sources_count: int = 0,
        stale_sources_count: int = 0,
        citation_count: int = 0,
        source_coverage_score: float = 0.0,
        prompt_injection_blocked: bool = False,
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

        built_handoff: dict[str, Any] = {
            "user_goal": conclusion[:160],
            "current_state": outcome,
            "last_action": ", ".join(tools_used[-3:]) if tools_used else "no tools called",
            "modified_files": list(dict.fromkeys(files_changed))[:10],
            "completed_work": [f"Called {t}" for t in tools_used] if tools_used else [],
            "remaining_work": [],
            "context_to_keep": list(dict.fromkeys(files_changed))[:5],
            "risks": risks,
        }
        if handoff_summary and isinstance(handoff_summary, dict):
            for k, v in handoff_summary.items():
                if v:
                    built_handoff[k] = v

        # Accumulate key facts from previous summaries so cross-turn knowledge
        # survives multiple compactions (Hermes re-summarization pattern).
        accumulated_context = self._build_accumulated_context(previous_summaries)

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
            "available_skills": list(available_skills or []),
            "loaded_skills": list(loaded_skills or []),
            "skill_loads_count": int(skill_loads_count or 0),
            "skills_used": list(skills_used or []),
            "skill_calls_count": int(skill_calls_count or 0),
            "skill_results_count": len(list(skill_results or [])),
            "skill_results": list(skill_results or []),
            "context_reuse": bool(context_reuse),
            "active_task": dict(active_task or {}),
            "handoff_summary": built_handoff,
            "accumulated_context": accumulated_context,
            "skill_observations": list(skill_observations or []),
            "research_observations": list(research_observations or []),
            "web_search_runs_count": int(web_search_runs_count or 0),
            "web_fetch_runs_count": int(web_fetch_runs_count or 0),
            "web_fetch_blocked_count": int(web_fetch_blocked_count or 0),
            "evidence_count": int(evidence_count or 0),
            "official_sources_count": int(official_sources_count or 0),
            "github_sources_count": int(github_sources_count or 0),
            "research_context_reused": bool(research_context_reused),
            "web_provider_errors": int(web_provider_errors or 0),
            "web_no_results_count": int(web_no_results_count or 0),
            "search_results_count": int(search_results_count or 0),
            "search_result_dedup_count": int(search_result_dedup_count or 0),
            "release_note_sources_count": int(release_note_sources_count or 0),
            "stale_sources_count": int(stale_sources_count or 0),
            "citation_count": int(citation_count or 0),
            "source_coverage_score": float(source_coverage_score or 0.0),
            "prompt_injection_blocked": bool(prompt_injection_blocked),
        }
        if clarification:
            machine["needs_user_clarification"] = True
            machine["missing_fields"] = list(clarification.get("missing_fields") or [])
            machine["clarification_question"] = str(clarification.get("question") or "").strip()
        return {"human": human, "machine": machine}

    @staticmethod
    def _build_accumulated_context(
        previous_summaries: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        """Extract key cross-turn facts from older summaries.

        Returns a list of compact fact records so the next compaction
        does not silently discard knowledge from earlier turns.
        """
        if not previous_summaries:
            return []
        facts: list[dict[str, Any]] = []
        seen_goals: set[str] = set()
        seen_files: set[str] = set()
        for s in previous_summaries:
            sm = dict(s.get("summary") or {}).get("machine") or {}
            if not isinstance(sm, dict):
                continue
            ho = sm.get("handoff_summary") or {}
            if isinstance(ho, dict):
                goal = str(ho.get("user_goal") or "").strip()
                if goal and goal not in seen_goals:
                    seen_goals.add(goal)
                    facts.append({"kind": "goal", "text": goal[:200]})
                for f in (ho.get("modified_files") or [])[:3]:
                    f_str = str(f)
                    if f_str and f_str not in seen_files:
                        seen_files.add(f_str)
                        facts.append({"kind": "file", "text": f_str})
                for w in (ho.get("completed_work") or [])[:2]:
                    w_str = str(w)
                    if w_str:
                        facts.append({"kind": "work", "text": w_str[:200]})
            # Also carry forward any accumulated_context from older summaries
            for prev_fact in sm.get("accumulated_context") or []:
                if isinstance(prev_fact, dict) and prev_fact not in facts:
                    facts.append(prev_fact)
        return facts[:20]
