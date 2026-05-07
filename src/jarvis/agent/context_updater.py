"""Write AgentRunResult effects back into ContextStore."""

from __future__ import annotations

from typing import Any

from .context_store import ContextStore
from .skill_context import ActiveTaskState, HandoffSummary, SkillObservation
from .types import AgentRunResult, TurnContext
from ..core.policy.approval import ApprovalRequest, ApprovalResponse
from ..store.thread_store import ThreadStore
from ..web.research_context import ResearchObservation


class ContextUpdater:
    """Persist turn outcomes, skill observations, and resumable task state."""

    def __init__(self, *, context_store: ContextStore | None = None) -> None:
        self.context_store = context_store or ContextStore()
        self.thread_store: ThreadStore | None = getattr(self.context_store, "thread_store", None)

    def apply_result(self, turn_context: TurnContext, agent_result: AgentRunResult) -> None:
        session_id = str(turn_context.session_id or agent_result.session_id or "default")
        self.context_store.append_turn(
            session_id,
            {
                "turn_id": agent_result.turn_id,
                "user_input": turn_context.user_input,
                "final_answer": agent_result.final_answer[:800],
                "skills_used": list(agent_result.skills_used or []),
                "related_files": self._related_files(agent_result),
            },
        )
        if self.thread_store is not None:
            self.thread_store.append_turn(session_id, agent_result, user_input=turn_context.user_input)

        observations: list[SkillObservation] = []
        research_observations: list[ResearchObservation] = []
        for item in list(agent_result.skill_results or []):
            if not isinstance(item, dict):
                continue
            for obs in list(item.get("observations") or []):
                if not isinstance(obs, dict):
                    continue
                observation = SkillObservation(
                    skill_name=str(obs.get("skill_name") or item.get("skill_name") or ""),
                    summary=str(obs.get("summary") or item.get("final_answer") or "")[:800],
                    facts=dict(obs.get("facts") or {}),
                    related_files=[str(x) for x in list(obs.get("related_files") or item.get("related_files") or [])],
                    tool_calls=[str(x) for x in list(obs.get("tool_calls") or [])],
                )
                observations.append(observation)
                self.context_store.add_skill_observation(session_id, observation)
                if self.thread_store is not None:
                    self.thread_store.append_skill_observation(session_id, observation, turn_id=agent_result.turn_id)

        machine = dict((agent_result.summary or {}).get("machine") or {})
        for obs in list(machine.get("research_observations") or []):
            if not isinstance(obs, dict):
                continue
            research = ResearchObservation(
                query=str(obs.get("query") or turn_context.user_input),
                search_tasks=[dict(x) for x in list(obs.get("search_tasks") or []) if isinstance(x, dict)],
                sources=[dict(x) for x in list(obs.get("sources") or []) if isinstance(x, dict)],
                evidence=[dict(x) for x in list(obs.get("evidence") or []) if isinstance(x, dict)],
                answer_summary=str(obs.get("answer_summary") or "")[:800],
                confidence=float(obs.get("confidence") or 0.0),
                remaining_questions=[str(x) for x in list(obs.get("remaining_questions") or [])],
            )
            research_observations.append(research)
            self.context_store.add_research_observation(session_id, research)
            if self.thread_store is not None:
                self.thread_store.append_research_observation(session_id, research, turn_id=agent_result.turn_id)

        active_task = self._build_active_task(turn_context, agent_result)
        self.context_store.set_active_task(session_id, active_task)
        handoff = self._build_handoff(turn_context, agent_result, observations, active_task)
        self.context_store.set_handoff_summary(session_id, handoff)
        if self.thread_store is not None:
            self.thread_store.save_active_task(session_id, active_task)
            self.thread_store.save_handoff_summary(session_id, handoff)
            state = self.context_store.get_state(session_id)
            self.thread_store.save_project_facts(turn_context.project_id, state.project_facts)
            self._persist_approval_audits(session_id, agent_result)

        machine["active_task"] = active_task.to_dict() if active_task else {}
        machine["handoff_summary"] = handoff.to_dict()
        machine["skill_observations"] = [obs.to_dict() for obs in observations]
        machine["research_observations"] = [obs.to_dict() for obs in research_observations]
        if research_observations:
            machine["research_context_reused"] = bool(machine.get("research_context_reused"))
        if active_task and active_task.risks:
            machine["risks"] = list(dict.fromkeys(list(machine.get("risks") or []) + active_task.risks))
        agent_result.summary.setdefault("machine", {}).update(machine)

    def _persist_approval_audits(self, session_id: str, agent_result: AgentRunResult) -> None:
        if self.thread_store is None:
            return
        for event in list(agent_result.events or []):
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("type") or "")
            payload = dict(event.get("payload") or {})
            if event_type == "approval_created":
                approval = ApprovalRequest(
                    approval_id=str(payload.get("approval_id") or ""),
                    tool_name=str(payload.get("tool_name") or ""),
                    arguments_preview=dict(payload.get("arguments_preview") or {}),
                    risk_level=str(payload.get("risk_level") or "medium"),
                    reason=str(payload.get("reason") or ""),
                    created_at=str(event.get("timestamp") or ""),
                    expires_at=None,
                    status="pending",
                    session_id=session_id,
                    turn_id=agent_result.turn_id,
                )
                self.thread_store.append_approval_audit(session_id, agent_result.turn_id, approval)
            elif event_type in {"approval_approved", "approval_denied"}:
                response = ApprovalResponse(
                    approval_id=str(payload.get("approval_id") or ""),
                    decision="approved" if event_type == "approval_approved" else "denied",
                    reason=str(payload.get("reason") or "") or None,
                    decided_at=str(event.get("timestamp") or ""),
                    decided_by=str(payload.get("decided_by") or "") or None,
                )
                self.thread_store.append_approval_audit(session_id, agent_result.turn_id, response)

    @staticmethod
    def _related_files(agent_result: AgentRunResult) -> list[str]:
        files: list[str] = []
        for item in list(agent_result.skill_results or []):
            if isinstance(item, dict):
                for path in list(item.get("related_files") or []):
                    if str(path) and str(path) not in files:
                        files.append(str(path))
        return files

    def _build_active_task(self, turn_context: TurnContext, agent_result: AgentRunResult) -> ActiveTaskState | None:
        if not agent_result.skills_used:
            return None
        remaining = []
        risks = list((agent_result.summary.get("machine") or {}).get("risks") or [])
        for item in list(agent_result.skill_results or []):
            if isinstance(item, dict):
                risks.extend([str(x) for x in list(item.get("risks") or [])])
        if agent_result.output_type in {"partial", "error"}:
            remaining.append("Resolve the partial result or blocking error before continuing.")
        if "fix_test_failure" in agent_result.skills_used:
            remaining.append("Review the dry-run repair plan and ask for approval before editing files.")
        state = ActiveTaskState.new(user_goal=turn_context.user_input, current_phase=agent_result.output_type)
        state.completed_steps = list(agent_result.skills_used)
        state.remaining_work = remaining
        state.related_files = self._related_files(agent_result)
        state.skills_used = list(agent_result.skills_used)
        state.risks = list(dict.fromkeys(risks))
        return state

    def _build_handoff(
        self,
        turn_context: TurnContext,
        agent_result: AgentRunResult,
        observations: list[SkillObservation],
        active_task: ActiveTaskState | None,
    ) -> HandoffSummary:
        related_files = self._related_files(agent_result)
        machine = dict((agent_result.summary or {}).get("machine") or {})
        recent_sources = [
            str(item.get("url") or "")
            for obs in list(machine.get("research_observations") or [])
            if isinstance(obs, dict)
            for item in list(obs.get("sources") or [])[:3]
            if isinstance(item, dict) and str(item.get("url") or "")
        ]
        context_to_keep = list(dict.fromkeys(related_files + [obs.skill_name for obs in observations] + recent_sources))
        risks = list((agent_result.summary.get("machine") or {}).get("risks") or [])
        if active_task:
            risks.extend(active_task.risks)
        return HandoffSummary(
            user_goal=turn_context.user_input,
            current_state=agent_result.output_type,
            completed_work=list(agent_result.skills_used or []),
            remaining_work=list(active_task.remaining_work if active_task else []),
            context_to_keep=context_to_keep,
            risks=list(dict.fromkeys(str(x) for x in risks)),
        )
