"""Chat-first AgentLoop implementation."""

from __future__ import annotations

import time
from typing import Any

from ..core.react_readiness.replay_store import ReplayStore
from .context import ContextBuilder, ContextCompactorAdapter
from .context_store import ContextStore
from .context_updater import ContextUpdater
from .events import EVENT_TYPES, InMemoryEventSink, ReplayEventSink
from .model import ModelClient, RuntimeModelClient
from .prompt_builder import PromptBuilder
from .retry import ErrorClassifier, ReplanPolicy, RetryPolicy
from .store import ThreadStore
from .summary import ResponseComposer
from .tools import ToolCallExecutor, ToolRegistryAdapter
from .types import AgentEvent, AgentOutputType, AgentRunResult, ChatInput, ToolCall, ToolResult
from ..store.memory_store import MemoryStore
from ..skills.executor import SkillExecutor
from ..skills.runtime import SkillCall
from ..web.research import SearchIntentClassifier, WebResearchPipeline


class AgentLoop:
    def __init__(
        self,
        *,
        project_root: str = ".",
        store: ThreadStore | None = None,
        context_builder: ContextBuilder | None = None,
        context_store: ContextStore | None = None,
        model_client: ModelClient | None = None,
        tool_registry: ToolRegistryAdapter | None = None,
        tool_executor: ToolCallExecutor | None = None,
        summary_composer: ResponseComposer | None = None,
        retry_policy: RetryPolicy | None = None,
        replan_policy: ReplanPolicy | None = None,
        error_classifier: ErrorClassifier | None = None,
        max_steps: int = 8,
        timeout_s: int = 90,
        permission_mode: str = "workspace_write",
        auto_approve: bool = False,
    ) -> None:
        self.project_root = project_root
        self.store = store or ThreadStore()
        self.tool_registry = tool_registry or ToolRegistryAdapter(
            project_root=project_root,
            permission_mode=permission_mode,
        )
        self.tool_executor = tool_executor or ToolCallExecutor(
            registry_adapter=self.tool_registry,
            permission_mode=permission_mode,
            auto_approve=auto_approve,
        )
        self.model_client = model_client or RuntimeModelClient()
        self.model_info = self.model_client.backend_info() if hasattr(self.model_client, "backend_info") else {
            "model_backend": "fake",
            "model_provider": "fake",
            "model_name": "fake-agent-v0",
        }
        self.memory_store = MemoryStore(self.store.db_path)
        self.context_store = context_store or ContextStore(thread_store=self.store, memory_store=self.memory_store)
        self.context_builder = context_builder or ContextBuilder(
            thread_store=self.store,
            memory_store=self.memory_store,
            compactor=ContextCompactorAdapter(max_tokens=12000),
            skill_registry=self.tool_registry.skill_registry,
            context_store=self.context_store,
            model_info=self.model_info,
            permission_mode=permission_mode,
        )
        self.prompt_builder = PromptBuilder()
        self.context_updater = ContextUpdater(context_store=self.context_store)
        self.skill_executor = SkillExecutor(
            skill_registry=self.tool_registry.skill_registry,
            tool_executor=self.tool_executor,
            project_root=project_root,
        )
        self.search_intent_classifier = SearchIntentClassifier()
        self.summary_composer = summary_composer or ResponseComposer()
        self.retry_policy = retry_policy or RetryPolicy(max_retries=1)
        self.replan_policy = replan_policy or ReplanPolicy(max_replans=2)
        self.error_classifier = error_classifier or ErrorClassifier()
        self.max_steps = max_steps
        self.timeout_s = timeout_s
        self._event_sink = ReplayEventSink(ReplayStore(), fallback=InMemoryEventSink())

    def run_turn(self, chat_input: ChatInput) -> AgentRunResult:
        started = time.perf_counter()
        session = self.store.create_or_resume_session(chat_input)
        session_id = str(session["session_id"])
        turn = self.store.create_turn(session_id, status="running", metadata={"project_id": chat_input.project_id})
        turn_id = turn.turn_id

        events: list[dict[str, Any]] = []
        tool_calls_log: list[dict[str, Any]] = []
        tool_results_log: list[dict[str, Any]] = []
        stop_reason = "max_steps"
        final_answer = ""
        output_type: AgentOutputType = "answer"
        clarification_payload: dict[str, Any] | None = None
        available_skills = list(self.tool_registry.skill_registry.available_names())
        loaded_skills: list[str] = []
        skill_results_log: list[dict[str, Any]] = []
        skills_used: list[str] = []
        turn_context = None
        seen_calls: dict[str, list[tuple[frozenset[tuple[str, Any]], dict[str, Any]]]] = {}

        self.store.append_message(session_id, turn_id, "user", chat_input.text, metadata={"kind": "user_input"})
        self._emit(events, turn_id, "turn_started", {"session_id": session_id, "text": chat_input.text})

        if self._is_sensitive_request(chat_input.text):
            return self._complete_early(
                session_id=session_id,
                turn_id=turn_id,
                events=events,
                final_answer="I can't print .env files or API keys because they may contain secrets.",
                stop_reason="safety_refusal",
                output_type="refusal",
                available_skills=available_skills,
                loaded_skills=loaded_skills,
            )

        clarification = self._build_clarification_if_needed(chat_input.text)
        if clarification is not None:
            return self._complete_early(
                session_id=session_id,
                turn_id=turn_id,
                events=events,
                final_answer=str(clarification.get("question") or "").strip(),
                stop_reason="needs_user_clarification",
                output_type="clarification",
                clarification=clarification,
                available_skills=available_skills,
                loaded_skills=loaded_skills,
            )

        tool_specs = self.tool_registry.list_tool_specs()
        turn_context, messages = self.context_builder.build_messages(
            session_id=session_id,
            turn_id=turn_id,
            chat_input=chat_input,
            runtime_state={
                "cwd": chat_input.cwd or self.project_root,
                "permission_mode": self.tool_executor.permission_mode,
                "model_backend": self.model_info.get("model_backend"),
                "model_provider": self.model_info.get("model_provider"),
                "model_name": self.model_info.get("model_name"),
            },
            prompt_builder=self.prompt_builder,
        )
        if turn_context.context_pack is not None:
            available_skills = [
                str(item.get("name") or "")
                for item in list(turn_context.context_pack.skills.available_skills or [])
                if str(item.get("name") or "")
            ]
        self._emit(events, turn_id, "skill_index_built", {"count": len(available_skills), "skills": available_skills[:12]})

        research_reuse = self._maybe_reuse_research_observation(chat_input.text, session_id)
        if research_reuse is not None:
            self._emit(
                events,
                turn_id,
                "context_observation_reused",
                {
                    "observation_type": "research",
                    "query": research_reuse.get("query"),
                    "source_count": len(list(research_reuse.get("sources") or [])),
                },
            )
            final_answer = self._answer_from_reused_research(chat_input.text, research_reuse)
            summary = self.summary_composer.compose(
                final_answer=final_answer,
                tool_results=[],
                stop_reason="completed",
                output_type="answer",
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=[],
                skill_calls_count=0,
                skill_results=[],
                context_reuse=True,
                research_observations=[research_reuse],
                research_context_reused=True,
            )
            result = AgentRunResult(
                ok=True,
                session_id=session_id,
                turn_id=turn_id,
                final_answer=final_answer,
                events=events,
                summary=summary,
                stop_reason="completed",
                tool_calls=[],
                tool_results=[],
                status="completed",
                output_type="answer",
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=[],
                skill_calls_count=0,
                skill_results=[],
                model_backend=str(self.model_info.get("model_backend") or ""),
                model_provider=str(self.model_info.get("model_provider") or ""),
                model_name=str(self.model_info.get("model_name") or ""),
            )
            self.context_updater.apply_result(turn_context, result)
            self._emit(events, turn_id, "context_updated", {"context_reuse": True, "research_context_reused": True})
            return result

        reuse = self._maybe_reuse_context_observation(chat_input.text, session_id)
        if reuse is not None:
            self._emit(events, turn_id, "context_observation_reused", {"skill_name": reuse.get("skill_name"), "related_files": reuse.get("related_files")})
            final_answer = self._answer_from_reused_observation(chat_input.text, reuse)
            summary = self.summary_composer.compose(
                final_answer=final_answer,
                tool_results=[],
                stop_reason="completed",
                output_type="answer",
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=[],
                skill_calls_count=0,
                skill_results=[],
                context_reuse=True,
                skill_observations=[reuse],
            )
            result = AgentRunResult(
                ok=True,
                session_id=session_id,
                turn_id=turn_id,
                final_answer=final_answer,
                events=events,
                summary=summary,
                stop_reason="completed",
                tool_calls=[],
                tool_results=[],
                status="completed",
                output_type="answer",
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=[],
                skill_calls_count=0,
                skill_results=[],
                model_backend=str(self.model_info.get("model_backend") or ""),
                model_provider=str(self.model_info.get("model_provider") or ""),
                model_name=str(self.model_info.get("model_name") or ""),
            )
            self.context_updater.apply_result(turn_context, result)
            self._emit(events, turn_id, "context_updated", {"context_reuse": True})
            return result

        research_intent = self.search_intent_classifier.classify(chat_input.text, turn_context.context_pack)
        if research_intent.need_web:
            pipeline = WebResearchPipeline(
                tool_executor=self.tool_executor,
                event_factory=lambda event_type, payload: AgentEvent.new(turn_id=turn_id, event_type=event_type, payload=payload),
            )
            research_result = pipeline.run(user_input=chat_input.text, turn_context=turn_context)
            self._append_event_dicts(events, research_result.events)
            tool_calls_log.extend(research_result.tool_calls)
            tool_results_log.extend(research_result.tool_results)
            final_answer = research_result.final_answer
            output_type = research_result.output_type  # type: ignore[assignment]
            stop_reason = research_result.stop_reason
            tool_result_objs = [ToolResult(**item) for item in tool_results_log if isinstance(item, dict) and item.get("name")]
            research_observations = [research_result.research_observation] if research_result.research_observation else []
            summary = self.summary_composer.compose(
                final_answer=final_answer,
                tool_results=tool_result_objs,
                stop_reason=stop_reason,
                output_type=output_type,
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=[],
                skill_calls_count=0,
                skill_results=[],
                research_observations=research_observations,
                web_search_runs_count=research_result.web_search_runs_count,
                web_fetch_runs_count=research_result.web_fetch_runs_count,
                web_fetch_blocked_count=research_result.web_fetch_blocked_count,
                evidence_count=research_result.evidence_count,
                official_sources_count=research_result.official_sources_count,
                github_sources_count=research_result.github_sources_count,
                web_provider_errors=research_result.web_provider_errors,
                web_no_results_count=research_result.web_no_results_count,
                search_results_count=research_result.search_results_count,
                search_result_dedup_count=research_result.search_result_dedup_count,
                release_note_sources_count=research_result.release_note_sources_count,
                stale_sources_count=research_result.stale_sources_count,
                citation_count=research_result.citation_count,
                source_coverage_score=research_result.source_coverage_score,
                prompt_injection_blocked=research_result.prompt_injection_blocked,
            )
            self.store.save_summary(session_id, turn_id, summary)
            self.store.save_final_answer(session_id, turn_id, final_answer)
            self._emit(events, turn_id, "final_answer_created", {"step": 0, "research_intent": research_intent.intent_type})
            self._emit(events, turn_id, "turn_completed", {"status": "completed", "stop_reason": stop_reason})
            self._emit(events, turn_id, "summary_created", {"status": "completed"})
            result = AgentRunResult(
                ok=output_type != "error",
                session_id=session_id,
                turn_id=turn_id,
                final_answer=final_answer,
                events=events,
                summary=summary,
                stop_reason=stop_reason,
                tool_calls=tool_calls_log,
                tool_results=tool_results_log,
                status="completed" if output_type != "error" else "failed",
                output_type=output_type,
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=[],
                skill_calls_count=0,
                skill_results=[],
                model_backend=str(self.model_info.get("model_backend") or ""),
                model_provider=str(self.model_info.get("model_provider") or ""),
                model_name=str(self.model_info.get("model_name") or ""),
            )
            self.context_updater.apply_result(turn_context, result)
            self._emit(events, turn_id, "context_updated", {"research_observations": len(research_observations), "context_reuse": False})
            return result

        skill_call = self._select_executable_skill(chat_input.text)
        if skill_call is not None:
            skill_result = self.skill_executor.run(skill_call, turn_context)
            self._append_skill_events(events, skill_result.events)
            tool_calls_log.extend(skill_result.tool_calls)
            tool_results_log.extend(skill_result.tool_results)
            skill_results_log.append(skill_result.to_dict())
            if skill_result.skill_name not in skills_used:
                skills_used.append(skill_result.skill_name)
            final_answer = skill_result.final_answer
            output_type = skill_result.output_type  # type: ignore[assignment]
            stop_reason = "completed" if skill_result.ok and output_type != "partial" else "skill_partial"
            tool_result_objs = [ToolResult(**item) for item in tool_results_log if isinstance(item, dict) and item.get("name")]
            summary = self.summary_composer.compose(
                final_answer=final_answer,
                tool_results=tool_result_objs,
                stop_reason=stop_reason,
                output_type=output_type,
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=skills_used,
                skill_calls_count=1,
                skill_results=skill_results_log,
                context_reuse=False,
            )
            self.store.save_summary(session_id, turn_id, summary)
            self.store.save_final_answer(session_id, turn_id, final_answer)
            self._emit(events, turn_id, "final_answer_created", {"step": 0, "skill_name": skill_result.skill_name})
            self._emit(events, turn_id, "turn_completed", {"status": "completed", "stop_reason": stop_reason})
            self._emit(events, turn_id, "summary_created", {"status": "completed"})
            result = AgentRunResult(
                ok=skill_result.ok,
                session_id=session_id,
                turn_id=turn_id,
                final_answer=final_answer,
                events=events,
                summary=summary,
                stop_reason=stop_reason,
                tool_calls=tool_calls_log,
                tool_results=tool_results_log,
                status="completed",
                output_type=output_type,
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=skills_used,
                skill_calls_count=1,
                skill_results=skill_results_log,
                model_backend=str(self.model_info.get("model_backend") or ""),
                model_provider=str(self.model_info.get("model_provider") or ""),
                model_name=str(self.model_info.get("model_name") or ""),
            )
            self.context_updater.apply_result(turn_context, result)
            self._emit(events, turn_id, "context_updated", {"skills_used": skills_used, "active_task": bool((result.summary.get("machine") or {}).get("active_task"))})
            return result

        last_progress_marker = ""
        no_progress_count = 0

        try:
            for step in range(1, self.max_steps + 1):
                if (time.perf_counter() - started) > self.timeout_s:
                    stop_reason = "timeout"
                    break

                self._emit(events, turn_id, "model_call_started", {"step": step})
                model_resp = self._call_model_with_retry(
                    events=events,
                    turn_id=turn_id,
                    step=step,
                    messages=messages,
                    tool_specs=tool_specs,
                )
                self._emit(
                    events,
                    turn_id,
                    "model_call_completed",
                    {
                        "step": step,
                        "finish_reason": model_resp.finish_reason,
                        "debug": self._model_debug_preview(model_resp),
                    },
                )

                if model_resp.reasoning_summary:
                    self._emit(events, turn_id, "reasoning_delta", {"step": step, "summary": model_resp.reasoning_summary})

                if (
                    not model_resp.tool_calls
                    and self._request_requires_tool(chat_input.text)
                    and len(tool_calls_log) == 0
                    and model_resp.finish_reason in {"stop", "retry_with_tool_instruction"}
                ):
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                "Retry: user request requires tool use. "
                                "Call one or more tools now instead of plain text."
                            ),
                        }
                    )
                    continue

                if model_resp.final_answer:
                    final_answer = model_resp.final_answer
                elif model_resp.assistant_text and not model_resp.tool_calls:
                    final_answer = model_resp.assistant_text

                if final_answer and not model_resp.tool_calls:
                    output_type = "tool_result" if len(tool_calls_log) > 0 else "answer"
                    stop_reason = "completed"
                    self._emit(events, turn_id, "final_answer_created", {"step": step})
                    break

                if not model_resp.tool_calls and not final_answer:
                    stop_reason = model_resp.finish_reason or "no_progress"
                    break

                for call in model_resp.tool_calls:
                    call = self._normalize_tool_call(chat_input.text, call)
                    if call.name == "skill.run":
                        tool_calls_log.append(call.to_dict())
                        self.store.append_tool_call(session_id, turn_id, call.to_dict())
                        self._emit(events, turn_id, "tool_call_started", {"step": step, "tool_call": call.to_dict()})
                        raw_skill_args = call.arguments.get("arguments")
                        skill_args = dict(raw_skill_args) if isinstance(raw_skill_args, dict) else {
                            k: v for k, v in call.arguments.items() if k not in {"name", "skill_name"}
                        }
                        skill_name = str(call.arguments.get("name") or call.arguments.get("skill_name") or "").strip()
                        skill_result = self.skill_executor.run(
                            SkillCall.new(name=skill_name, arguments=skill_args, source="model"),
                            turn_context,
                        )
                        self._append_skill_events(events, skill_result.events)
                        tool_calls_log.extend(skill_result.tool_calls)
                        tool_results_log.extend(skill_result.tool_results)
                        skill_results_log.append(skill_result.to_dict())
                        if skill_result.skill_name and skill_result.skill_name not in skills_used:
                            skills_used.append(skill_result.skill_name)
                        result = ToolResult(
                            call_id=call.id,
                            name="skill.run",
                            ok=skill_result.output_type != "error",
                            content=skill_result.final_answer,
                            error=None if skill_result.output_type != "error" else skill_result.final_answer,
                            metadata={
                                "skill_name": skill_result.skill_name,
                                "output_type": skill_result.output_type,
                                "risks": list(skill_result.risks),
                            },
                        )
                        result_dict = result.to_dict()
                        tool_results_log.append(result_dict)
                        self.store.append_tool_result(session_id, turn_id, result_dict)
                        self._emit(events, turn_id, "tool_call_completed", {"step": step, "tool_result": result_dict})
                        messages.append({"role": "tool", "content": self._observation_text(result)})
                        self._emit(events, turn_id, "observation_added", {"step": step, "tool_name": result.name})
                        continue
                    canonical_key = (call.name, self._tool_args_frozen(call))
                    reused_result = self._find_seen_result(seen_calls, call)
                    if reused_result is not None:
                        tool_calls_log.append(call.to_dict())
                        self.store.append_tool_call(session_id, turn_id, call.to_dict())
                        tool_results_log.append(reused_result)
                        self.store.append_tool_result(session_id, turn_id, reused_result)
                        prev_obs = self._observation_text(ToolResult(**reused_result))
                        messages.append({"role": "tool", "content": prev_obs})
                        self._emit(events, turn_id, "tool_call_deduped", {"step": step, "tool_name": call.name})
                        self._emit(events, turn_id, "observation_reused", {"step": step, "tool_name": call.name})
                        if call.name == "skill.load":
                            skill_name = str((reused_result.get("metadata") or {}).get("skill_name") or call.arguments.get("name") or "")
                            if skill_name and skill_name not in loaded_skills:
                                loaded_skills.append(skill_name)
                            self._emit(events, turn_id, "skill_observation_reused", {"step": step, "skill_name": skill_name})
                        continue

                    tool_calls_log.append(call.to_dict())
                    self.store.append_tool_call(session_id, turn_id, call.to_dict())
                    if call.name == "skill.load":
                        self._emit(events, turn_id, "skill_load_started", {"step": step, "skill_name": call.arguments.get("name")})
                    self._emit(events, turn_id, "tool_call_started", {"step": step, "tool_call": call.to_dict()})

                    result = self.tool_executor.execute(
                        call,
                        context={
                            "cwd": chat_input.cwd or self.project_root,
                            "session_id": session_id,
                            "turn_id": turn_id,
                            "permission_mode": self.tool_executor.permission_mode,
                            "mode": "agent_loop",
                        },
                    )
                    self._append_tool_runtime_events(events, result)
                    result_dict = result.to_dict()
                    tool_results_log.append(result_dict)
                    self.store.append_tool_result(session_id, turn_id, result_dict)
                    self._emit(events, turn_id, "tool_call_completed", {"step": step, "tool_result": result_dict})

                    if call.name == "skill.load":
                        skill_name = str(result.metadata.get("skill_name") or call.arguments.get("name") or "")
                        if result.ok:
                            if skill_name and skill_name not in loaded_skills:
                                loaded_skills.append(skill_name)
                            self._emit(events, turn_id, "skill_loaded", {"step": step, "skill_name": skill_name})
                        else:
                            self._emit(events, turn_id, "skill_load_failed", {"step": step, "skill_name": skill_name, "error": result.error})

                    if result.error and "approval_required" in str(result.error):
                        stop_reason = "approval_required"
                        output_type = "partial"
                        self._emit(events, turn_id, "approval_required", {"step": step, "tool_name": result.name, "error": result.error})
                        break

                    if result.ok:
                        seen_calls.setdefault(call.name, []).append((canonical_key[1], result_dict))
                        if call.name in ("repo_reader.read_file", "repo_reader.search_files", "directory_list", "list_directory"):
                            messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        "Based on the above observation, generate a concise final answer now. "
                                        "Do not call the same tool again unless the user explicitly asks for more content."
                                    ),
                                }
                            )
                        messages.append({"role": "tool", "content": self._observation_text(result)})
                        self._emit(events, turn_id, "observation_added", {"step": step, "tool_name": result.name})
                        continue

                    classification = self.error_classifier.classify(result)
                    if self.retry_policy.should_retry(call, classification):
                        self._emit(events, turn_id, "retry_started", {"step": step, "tool_name": result.name, "reason": classification.reason})
                        retry_result = self.tool_executor.execute(
                            call,
                            context={
                                "cwd": chat_input.cwd or self.project_root,
                                "session_id": session_id,
                                "turn_id": turn_id,
                                "permission_mode": self.tool_executor.permission_mode,
                                "mode": "agent_loop_retry",
                            },
                        )
                        self._append_tool_runtime_events(events, retry_result)
                        retry_dict = retry_result.to_dict()
                        tool_results_log.append(retry_dict)
                        self.store.append_tool_result(session_id, turn_id, retry_dict)
                        self._emit(events, turn_id, "tool_call_completed", {"step": step, "tool_result": retry_dict})
                        if retry_result.ok:
                            messages.append({"role": "tool", "content": self._observation_text(retry_result)})
                            self._emit(events, turn_id, "observation_added", {"step": step, "tool_name": retry_result.name})
                            continue

                    if self.replan_policy.should_replan(classification):
                        hint = self.replan_policy.build_replan_observation(result, classification)
                        messages.append({"role": "system", "content": f"Tool failed; replan with this hint: {hint}"})
                        self._emit(events, turn_id, "observation_added", {"step": step, "tool_name": result.name, "replan_hint": hint})
                        continue

                    stop_reason = classification.reason or "tool_failed"
                    output_type = "partial"
                    break

                if stop_reason in {"approval_required", "timeout"}:
                    break

                marker = f"{len(tool_calls_log)}:{len(tool_results_log)}:{final_answer[:60]}"
                if marker == last_progress_marker:
                    no_progress_count += 1
                else:
                    no_progress_count = 0
                    last_progress_marker = marker
                if no_progress_count >= 2:
                    stop_reason = "no_progress"
                    output_type = "partial"
                    break

            tool_result_objs = [ToolResult(**item) for item in tool_results_log]
            if not final_answer:
                final_answer = self._fallback_final_answer(tool_result_objs, stop_reason)
            if output_type == "answer" and stop_reason in {"timeout", "approval_required", "max_steps", "no_progress"}:
                output_type = "partial"

            summary = self.summary_composer.compose(
                final_answer=final_answer,
                tool_results=tool_result_objs,
                stop_reason=stop_reason,
                output_type=output_type,
                clarification=clarification_payload,
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=skills_used,
                skill_calls_count=len(skill_results_log),
                skill_results=skill_results_log,
            )
            self.store.save_summary(session_id, turn_id, summary)
            if final_answer:
                self.store.save_final_answer(session_id, turn_id, final_answer)

            status = "completed" if final_answer and stop_reason == "completed" else "partial"
            if not final_answer:
                status = "failed" if stop_reason not in {"approval_required", "max_steps", "no_progress", "timeout"} else "partial"
            if status == "failed" and output_type != "error":
                output_type = "error"
            event_type = "turn_completed" if status != "failed" else "turn_failed"
            self._emit(events, turn_id, event_type, {"status": status, "stop_reason": stop_reason})
            self._emit(events, turn_id, "summary_created", {"status": status})

            result = AgentRunResult(
                ok=status != "failed",
                session_id=session_id,
                turn_id=turn_id,
                final_answer=final_answer,
                events=events,
                summary=summary,
                stop_reason=stop_reason,
                tool_calls=tool_calls_log,
                tool_results=tool_results_log,
                status=status,
                output_type=output_type,
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=skills_used,
                skill_calls_count=len(skill_results_log),
                skill_results=skill_results_log,
                model_backend=str(self.model_info.get("model_backend") or ""),
                model_provider=str(self.model_info.get("model_provider") or ""),
                model_name=str(self.model_info.get("model_name") or ""),
            )
            if turn_context is not None:
                self.context_updater.apply_result(turn_context, result)
            return result
        except Exception as exc:
            self._emit(events, turn_id, "turn_failed", {"error": str(exc), "error_type": type(exc).__name__})
            stop_reason = self._map_provider_error_stop_reason(exc)
            output_type = "error"
            final_answer = self._friendly_error_message(exc)
            summary = self.summary_composer.compose(
                final_answer=final_answer,
                tool_results=[],
                stop_reason=stop_reason,
                output_type=output_type,
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
            )
            self.store.save_summary(session_id, turn_id, summary)
            self.store.save_final_answer(session_id, turn_id, final_answer)
            return AgentRunResult(
                ok=False,
                session_id=session_id,
                turn_id=turn_id,
                final_answer=final_answer,
                events=events,
                summary=summary,
                stop_reason=stop_reason,
                tool_calls=tool_calls_log,
                tool_results=tool_results_log,
                status="failed",
                output_type=output_type,
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=skills_used,
                skill_calls_count=len(skill_results_log),
                skill_results=skill_results_log,
                model_backend=str(self.model_info.get("model_backend") or ""),
                model_provider=str(self.model_info.get("model_provider") or ""),
                model_name=str(self.model_info.get("model_name") or ""),
            )

    def _complete_early(
        self,
        *,
        session_id: str,
        turn_id: str,
        events: list[dict[str, Any]],
        final_answer: str,
        stop_reason: str,
        output_type: AgentOutputType,
        available_skills: list[str],
        loaded_skills: list[str],
        clarification: dict[str, Any] | None = None,
    ) -> AgentRunResult:
        summary = self.summary_composer.compose(
            final_answer=final_answer,
            tool_results=[],
            stop_reason=stop_reason,
            output_type=output_type,
            clarification=clarification,
            available_skills=available_skills,
            loaded_skills=loaded_skills,
            skill_loads_count=len(loaded_skills),
        )
        self.store.save_summary(session_id, turn_id, summary)
        self.store.save_final_answer(session_id, turn_id, final_answer)
        self._emit(events, turn_id, "final_answer_created", {"step": 0})
        self._emit(events, turn_id, "turn_completed", {"status": "completed", "stop_reason": stop_reason})
        self._emit(events, turn_id, "summary_created", {"status": "completed"})
        return AgentRunResult(
            ok=True,
            session_id=session_id,
            turn_id=turn_id,
            final_answer=final_answer,
            events=events,
            summary=summary,
            stop_reason=stop_reason,
            tool_calls=[],
            tool_results=[],
            status="completed",
            output_type=output_type,
            available_skills=available_skills,
            loaded_skills=loaded_skills,
            skill_loads_count=len(loaded_skills),
            model_backend=str(self.model_info.get("model_backend") or ""),
            model_provider=str(self.model_info.get("model_provider") or ""),
            model_name=str(self.model_info.get("model_name") or ""),
        )

    def _emit(self, collector: list[dict[str, Any]], turn_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if event_type not in EVENT_TYPES:
            payload = dict(payload)
            payload["unknown_event_type"] = event_type
            event_type = "turn_failed"
        event = AgentEvent.new(turn_id=turn_id, event_type=event_type, payload=payload)
        self._event_sink.emit(event)
        collector.append(event.to_dict())

    def _append_skill_events(self, collector: list[dict[str, Any]], skill_events: list[AgentEvent]) -> None:
        for event in skill_events:
            self._event_sink.emit(event)
            collector.append(event.to_dict())

    @staticmethod
    def _append_tool_runtime_events(collector: list[dict[str, Any]], result: ToolResult) -> None:
        for event in list((result.metadata or {}).get("agent_events") or []):
            if isinstance(event, dict):
                collector.append(dict(event))

    @staticmethod
    def _append_event_dicts(collector: list[dict[str, Any]], event_dicts: list[dict[str, Any]]) -> None:
        for event in event_dicts:
            if isinstance(event, dict):
                collector.append(dict(event))

    def _maybe_reuse_context_observation(self, text: str, session_id: str) -> dict[str, Any] | None:
        lowered = str(text or "").lower()
        markers = ("刚才", "that file", "previous result", "刚才那个文件", "刚才的结果", "based on the previous")
        if not any(marker in lowered for marker in markers):
            return None
        observation = self.context_store.retrieve_skill_observation(session_id)
        return observation.to_dict() if observation is not None else None

    @staticmethod
    def _answer_from_reused_observation(text: str, observation: dict[str, Any]) -> str:
        files = ", ".join(str(x) for x in list(observation.get("related_files") or [])) or "the previous file/result"
        summary = str(observation.get("summary") or "").strip()
        return f"Using the previous context for {files}: {summary}"

    def _maybe_reuse_context_observation(self, text: str, session_id: str) -> dict[str, Any] | None:
        lowered = str(text or "").lower()
        markers = ("刚才", "that file", "previous result", "刚才那个文件", "刚才的结果", "based on the previous")
        if not any(marker in lowered for marker in markers):
            return None
        observation = self.context_store.retrieve_skill_observation(session_id)
        return observation.to_dict() if observation is not None else None

    def _maybe_reuse_research_observation(self, text: str, session_id: str) -> dict[str, Any] | None:
        lowered = str(text or "").lower()
        markers = (
            "刚才查到",
            "官方资料",
            "official source",
            "official docs",
            "previous research",
            "based on the previous research",
        )
        if not any(marker in lowered for marker in markers):
            return None
        observation = self.context_store.retrieve_research_observation(session_id)
        return observation.to_dict() if observation is not None else None

    @staticmethod
    def _answer_from_reused_research(text: str, observation: dict[str, Any]) -> str:
        _ = text
        summary = str(observation.get("answer_summary") or "").strip() or "No stored research summary."
        sources = ", ".join(
            str(item.get("url") or "")
            for item in list(observation.get("sources") or [])[:3]
            if isinstance(item, dict) and str(item.get("url") or "")
        ) or "none"
        return f"Using the previous web research: {summary}\nSources: {sources}"

    @staticmethod
    def _select_executable_skill(text: str) -> SkillCall | None:
        raw = str(text or "").strip()
        lowered = raw.lower()
        if not raw:
            return None
        if any(marker in lowered for marker in ("fix test", "修复测试失败", "repair failing test", "诊断测试失败")):
            return SkillCall.new(name="fix_test_failure", arguments={}, source="deterministic")
        if any(marker in lowered for marker in ("run agent test", "run agent tests", "运行 agent 测试", "运行agent测试")):
            return SkillCall.new(name="run_tests", arguments={"scope": "agent"}, source="deterministic")
        if any(marker in lowered for marker in ("what does this repo", "project overview", "repo overview", "项目是做什么", "项目结构", "分析项目结构", "看一下这个项目")):
            return SkillCall.new(name="repo_overview", arguments={"root": "."}, source="deterministic")
        if any(marker in lowered for marker in ("summarize", "总结", "概括", "explain")) and ("readme" in lowered or "." in lowered):
            return SkillCall.new(name="summarize_file", arguments={"path": SkillExecutor._guess_file_path(raw) or "README.md"}, source="deterministic")
        return None

    @staticmethod
    def _observation_text(result: ToolResult) -> str:
        return f"Tool `{result.name}` returned ok={result.ok}. content={result.content}"

    @staticmethod
    def _request_requires_tool(text: str) -> bool:
        lowered = str(text or "").lower()
        markers = (
            "readme",
            "read file",
            "list current directory",
            "current directory",
            "run pytest",
            "run tests",
            "fix ",
            "bug",
            "modify file",
            "run command",
            "总结 readme",
            "读取",
            "列一下当前目录",
            "运行测试",
        )
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _is_sensitive_request(text: str) -> bool:
        lowered = str(text or "").lower()
        markers = (".env", "api key", "token", "password", "id_rsa", "secret", "jarvis_llm_api_key")
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _model_debug_preview(model_resp: Any) -> dict[str, Any]:
        raw = getattr(model_resp, "raw", None)
        if isinstance(raw, dict):
            debug = raw.get("debug")
            if isinstance(debug, dict):
                out = dict(debug)
                preview = str(out.get("content_preview") or "")
                out["content_preview"] = preview[:200]
                return out
        return {}

    def _call_model_with_retry(
        self,
        *,
        events: list[dict[str, Any]],
        turn_id: str,
        step: int,
        messages: list[dict[str, Any]],
        tool_specs: list[Any],
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, 3):
            try:
                return self.model_client.complete(
                    messages,
                    tools=tool_specs,
                    stream=False,
                    metadata={"step": step, "attempt": attempt},
                )
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    self._emit(
                        events,
                        turn_id,
                        "retry_started",
                        {"step": step, "reason": "model_call_error", "attempt": attempt, "error_type": type(exc).__name__},
                    )
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("model call failed")

    @staticmethod
    def _normalize_tool_call(user_text: str, call: ToolCall) -> ToolCall:
        lowered = str(user_text or "").lower()
        list_dir_intent = any(marker in lowered for marker in ("列一下当前目录", "当前目录", "list current directory"))
        if list_dir_intent and call.name == "command_runner.run":
            return ToolCall.new(
                name="repo_reader.search_files",
                arguments={"repo_path": ".", "pattern": "*", "max_results": 80},
                reason="normalize_directory_listing",
            )
        return call

    @staticmethod
    def _tool_args_frozen(call: ToolCall) -> frozenset[tuple[str, Any]]:
        return frozenset((str(k), str(v)) for k, v in sorted((call.arguments or {}).items()))

    @staticmethod
    def _find_seen_result(
        seen_calls: dict[str, list[tuple[frozenset[tuple[str, Any]], dict[str, Any]]]],
        call: ToolCall,
    ) -> dict[str, Any] | None:
        if call.name not in seen_calls:
            return None
        frozen = AgentLoop._tool_args_frozen(call)
        for args_frozen, previous in seen_calls[call.name]:
            if args_frozen == frozen:
                return previous
        return None

    @staticmethod
    def _fallback_final_answer(tool_results: list[ToolResult], stop_reason: str) -> str:
        if not tool_results:
            return ""
        last = tool_results[-1]
        if last.ok:
            return f"Completed tool execution with `{last.name}`. The model did not provide a fuller summary before stop_reason={stop_reason}."
        return f"Tool execution did not complete (`{last.name}`): {last.error or 'unknown error'}. stop_reason={stop_reason}."

    @staticmethod
    def _build_clarification_if_needed(text: str) -> dict[str, Any] | None:
        raw = str(text or "").strip()
        lowered = raw.lower()
        normalized = raw.replace("。", "").replace("，", "").replace("?", "").strip()
        if normalized in {"帮我弄一下", "处理一个", "修一个", "优化它", "这个有问题", "处理这个"}:
            return {"missing_fields": ["target"], "question": "你希望我处理哪个文件、命令或具体问题？"}
        if "读取那个文件" in raw or "read that file" in lowered:
            return {"missing_fields": ["file_path"], "question": "你希望我读取哪个文件？"}
        return None

    @staticmethod
    def _map_provider_error_stop_reason(exc: Exception) -> str:
        lowered = f"{type(exc).__name__}: {exc}".lower()
        if any(marker in lowered for marker in ("winerror 10013", "access socket", "permission", "connection", "timed out", "timeout", "refused", "reset", "certificate")):
            return "provider_network_error"
        if "401" in lowered or "unauthorized" in lowered or "auth" in lowered:
            return "provider_auth_error"
        if "403" in lowered or "forbidden" in lowered or "404" in lowered or "not found" in lowered:
            return "provider_http_error"
        if "provider unavailable" in lowered or "service unavailable" in lowered:
            return "provider_unavailable"
        return "model_call_failed"

    @staticmethod
    def _friendly_error_message(exc: Exception) -> str:
        stop_reason = AgentLoop._map_provider_error_stop_reason(exc)
        if stop_reason == "provider_network_error":
            return "Real LLM call failed because the network connection was blocked. You can run `python scripts/check_llm_api.py` to verify API, proxy, or firewall settings."
        if stop_reason == "provider_auth_error":
            return "LLM API authentication failed (401/Unauthorized). Please check whether the API key is valid and still active."
        if stop_reason == "provider_http_error":
            return "The LLM provider returned an HTTP error (such as 403 or 404). Please check whether the base URL and provider config are correct."
        if stop_reason == "provider_unavailable":
            return "The current LLM provider is unavailable. Please check the .env configuration or try again later."
        return f"Model call failed: {type(exc).__name__}"
