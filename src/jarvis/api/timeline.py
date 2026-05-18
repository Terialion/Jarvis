from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from ..agent.types import AgentRunResult
from ..store.redaction import redact_for_persistence
from ..store import ThreadStore

TimelineItemType = Literal[
    "user_message",
    "assistant_message",
    "tool_call",
    "skill_call",
    "web_search",
    "web_fetch",
    "source",
    "evidence",
    "approval",
    "memory",
    "benchmark",
    "warning",
    "error",
]


@dataclass
class TimelineItem:
    id: str
    type: TimelineItemType
    title: str
    status: str
    timestamp: str | None
    summary: str
    payload_redacted: dict[str, Any] = field(default_factory=dict)
    source_refs: list[dict[str, Any]] = field(default_factory=list)
    related_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Timeline:
    thread_id: str | None
    items: list[TimelineItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "items": [item.to_dict() for item in self.items],
            "warnings": list(self.warnings),
        }


def _event_title(event_type: str, payload: dict[str, Any]) -> tuple[TimelineItemType, str, str]:
    if event_type == "turn_started":
        return "user_message", "User Prompt", str(payload.get("text") or "User input")
    if event_type.startswith("tool_call_"):
        return "tool_call", f"Tool: {payload.get('tool_name') or payload.get('name') or 'tool'}", event_type
    if event_type.startswith("skill_"):
        return "skill_call", f"Skill: {payload.get('skill_name') or payload.get('name') or 'skill'}", event_type
    if event_type.startswith("web_search"):
        return "web_search", "Web Search", str(payload.get("query") or event_type)
    if event_type.startswith("web_fetch") or event_type == "web_content_extracted":
        return "web_fetch", "Web Fetch", str(payload.get("url") or event_type)
    if event_type.startswith("approval_"):
        return "approval", "Approval", str(payload.get("approval_id") or event_type)
    if event_type in {"context_updated", "context_observation_reused", "observation_added", "observation_reused"}:
        return "memory", "Context Update", event_type
    if event_type in {"security_warning_emitted", "posttool_hook_warning", "web_fetch_blocked"}:
        return "warning", "Warning", event_type
    if event_type in {"turn_failed", "web_search_failed", "web_fetch_failed", "skill_call_failed", "skill_step_failed"}:
        return "error", "Error", event_type
    return "memory", event_type.replace("_", " ").title(), event_type


def timeline_from_events(events: list[dict[str, Any]]) -> list[TimelineItem]:
    items: list[TimelineItem] = []
    for index, event in enumerate(events, start=1):
        payload = dict(redact_for_persistence(event.get("payload") or {}))
        item_type, title, summary = _event_title(str(event.get("type") or ""), payload)
        items.append(
            TimelineItem(
                id=str(event.get("event_id") or f"evt_{index}"),
                type=item_type,
                title=title,
                status=str(payload.get("status") or payload.get("decision") or payload.get("action") or "recorded"),
                timestamp=str(event.get("timestamp") or "") or None,
                summary=summary,
                payload_redacted=payload,
                source_refs=list(payload.get("sources") or []) if item_type in {"source", "evidence"} else [],
                related_ids=[str(event.get("turn_id") or "")] if event.get("turn_id") else [],
            )
        )
    return items


def timeline_from_agent_result(result: AgentRunResult) -> Timeline:
    items = timeline_from_events(list(result.events or []))
    machine = dict((result.summary or {}).get("machine") or {})
    if result.final_answer:
        items.append(
            TimelineItem(
                id=f"{result.turn_id}_assistant",
                type="assistant_message",
                title="Assistant Response",
                status=str(result.status or "completed"),
                timestamp=None,
                summary=str(result.final_answer)[:280],
                payload_redacted={"final_answer": redact_for_persistence(result.final_answer)},
                related_ids=[str(result.turn_id)],
            )
        )
    for observation in list(machine.get("research_observations") or []):
        if not isinstance(observation, dict):
            continue
        for source_index, source in enumerate(list(observation.get("sources") or []), start=1):
            if isinstance(source, dict):
                items.append(
                    TimelineItem(
                        id=f"{result.turn_id}_source_{source_index}",
                        type="source",
                        title="Source",
                        status="captured",
                        timestamp=None,
                        summary=str(source.get("title") or source.get("url") or "source"),
                        payload_redacted=dict(redact_for_persistence(source)),
                        source_refs=[dict(redact_for_persistence(source))],
                        related_ids=[str(result.turn_id)],
                    )
                )
        for evidence_index, evidence in enumerate(list(observation.get("evidence") or []), start=1):
            if isinstance(evidence, dict):
                items.append(
                    TimelineItem(
                        id=f"{result.turn_id}_evidence_{evidence_index}",
                        type="evidence",
                        title="Evidence",
                        status="captured",
                        timestamp=None,
                        summary=str(evidence.get("summary") or evidence.get("quote") or "evidence"),
                        payload_redacted=dict(redact_for_persistence(evidence)),
                        source_refs=[],
                        related_ids=[str(result.turn_id)],
                    )
                )
    warnings: list[str] = []
    if machine.get("persistent_memory_background_only"):
        warnings.append("Persistent memory is historical background only, not a new instruction.")
    return Timeline(thread_id=str(result.session_id), items=items, warnings=warnings)


def timeline_from_thread_store(thread_id: str, store: ThreadStore) -> Timeline:
    items: list[TimelineItem] = []
    for msg in store.get_recent_messages(thread_id, limit=40):
        role = msg.get("role", "")
        item_type: TimelineItemType = "assistant_message" if role == "assistant" else "user_message"
        tid = msg.get("turn_id")
        items.append(
            TimelineItem(
                id=msg.get("message_id", ""),
                type=item_type,
                title="Assistant Message" if item_type == "assistant_message" else "User Message",
                status="persisted",
                timestamp=msg.get("created_at") or msg.get("timestamp", ""),
                summary=(msg.get("content") or "")[:280],
                payload_redacted=dict(msg),
                related_ids=[str(tid)] if tid else [],
            )
        )
    for tc in store.get_tool_calls(thread_id, limit=40):
        tool_name = tc.get("tool_name", "")
        call_id = tc.get("call_id", "")
        status = tc.get("status", "")
        created_at = tc.get("created_at", "")
        turn_id = tc.get("turn_id", "")
        items.append(
            TimelineItem(
                id=call_id,
                type="tool_call",
                title=f"Tool: {tool_name}",
                status=status,
                timestamp=created_at,
                summary=tool_name,
                payload_redacted=dict(tc),
                related_ids=[turn_id],
            )
        )
        args = tc.get("args_redacted", {})
        if tool_name == "web.fetch":
            items.append(
                TimelineItem(
                    id=f"{call_id}_web_fetch",
                    type="web_fetch",
                    title="Web Fetch",
                    status=status,
                    timestamp=created_at,
                    summary=str(args.get("url") or tool_name) if isinstance(args, dict) else tool_name,
                    payload_redacted=dict(tc),
                    related_ids=[turn_id],
                )
            )
        if tool_name == "web.search":
            items.append(
                TimelineItem(
                    id=f"{call_id}_web_search",
                    type="web_search",
                    title="Web Search",
                    status=status,
                    timestamp=created_at,
                    summary=str(args.get("query") or tool_name) if isinstance(args, dict) else tool_name,
                    payload_redacted=dict(tc),
                    related_ids=[turn_id],
                )
            )
    for obs in store.get_skill_observations(thread_id, limit=20):
        oid = obs.get("observation_id", "")
        otid = obs.get("turn_id")
        items.append(
            TimelineItem(
                id=oid,
                type="skill_call",
                title=f"Skill Observation: {obs.get('skill_name', '')}",
                status="persisted",
                timestamp=obs.get("created_at", ""),
                summary=(obs.get("summary_redacted") or obs.get("summary") or "")[:280],
                payload_redacted=dict(obs),
                related_ids=[str(otid)] if otid else [],
            )
        )
    for obs in store.get_research_observations(thread_id, limit=20):
        oid = obs.get("observation_id", "")
        otid = obs.get("turn_id")
        created_at = obs.get("created_at", "")
        items.append(
            TimelineItem(
                id=oid,
                type="web_search",
                title="Research Observation",
                status="persisted",
                timestamp=created_at,
                summary=(obs.get("answer_summary_redacted") or obs.get("answer_summary") or "")[:280],
                payload_redacted=dict(obs),
                source_refs=list(obs.get("sources_redacted", [])),
                related_ids=[str(otid)] if otid else [],
            )
        )
        for source_index, source in enumerate(obs.get("sources_redacted", []), start=1):
            items.append(
                TimelineItem(
                    id=f"{oid}_source_{source_index}",
                    type="source",
                    title="Source",
                    status="persisted",
                    timestamp=created_at,
                    summary=str(source.get("title") or source.get("url") or "source") if isinstance(source, dict) else str(source),
                    payload_redacted=dict(redact_for_persistence(source)) if isinstance(source, dict) else {"value": str(source)},
                    source_refs=[dict(redact_for_persistence(source))] if isinstance(source, dict) else [],
                    related_ids=[oid],
                )
            )
        for evidence_index, evidence in enumerate(obs.get("evidence_redacted", []), start=1):
            items.append(
                TimelineItem(
                    id=f"{oid}_evidence_{evidence_index}",
                    type="evidence",
                    title="Evidence",
                    status="persisted",
                    timestamp=created_at,
                    summary=str(evidence.get("summary") or evidence.get("quote") or "evidence") if isinstance(evidence, dict) else str(evidence),
                    payload_redacted=dict(redact_for_persistence(evidence)) if isinstance(evidence, dict) else {"value": str(evidence)},
                    related_ids=[oid],
                )
            )
    for audit in store.get_approval_audits(thread_id, limit=20):
        atid = audit.get("turn_id")
        items.append(
            TimelineItem(
                id=audit.get("approval_id", ""),
                type="approval",
                title=f"Approval: {audit.get('tool_name', '')}",
                status=audit.get("status", ""),
                timestamp=audit.get("created_at", ""),
                summary=str(audit.get("reason_redacted") or audit.get("decision") or audit.get("status")),
                payload_redacted=dict(audit),
                related_ids=[str(atid)] if atid else [],
            )
        )
    active_task = store.get_active_task(thread_id)
    if active_task is not None:
        items.append(
            TimelineItem(
                id=f"{thread_id}_active_task",
                type="memory",
                title="Active Task",
                status="persisted",
                timestamp=active_task.get("updated_at", ""),
                summary=(active_task.get("summary") or "")[:280],
                payload_redacted=dict(active_task),
                related_ids=[thread_id],
            )
        )
    handoff = store.get_handoff_summary(thread_id)
    if handoff is not None:
        items.append(
            TimelineItem(
                id=f"{thread_id}_handoff",
                type="memory",
                title="Handoff Summary",
                status="persisted",
                timestamp=handoff.get("updated_at", ""),
                summary=(handoff.get("summary") or "")[:280],
                payload_redacted=dict(handoff),
                related_ids=[thread_id],
            )
        )
    items.sort(key=lambda item: (item.timestamp or "", item.id))
    return Timeline(
        thread_id=thread_id,
        items=items,
        warnings=[
            "Persistent memory and resumed context are historical background only.",
            "They are not new user instructions.",
            "Do not execute requests mentioned only in persisted memory.",
        ],
    )
