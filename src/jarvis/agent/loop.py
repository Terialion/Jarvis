"""LLM-first AgentLoop — LLM decides WHAT to do; framework enforces HOW."""

from __future__ import annotations

import json
import time
from typing import Any, Iterator

from ..core.checkpoint_manager import CheckpointManager
from ..core.checkpoint_snapshot import CheckpointSnapshotter
from ..core.react_readiness.replay_store import ReplayStore
from ..core.task_runtime import TaskRuntime
from ..core.tokens import TokenEstimator, get_context_window
from .context import ContextBuilder, ContextCompactorAdapter
from .context_compactor import compact as compact_messages
from .context_store import ContextStore
from .context_updater import ContextUpdater
from .events import EVENT_TYPES, InMemoryEventSink, ReplayEventSink
from .model import ModelClient, RuntimeModelClient
from .prompt_builder import PromptBuilder
from .retry import ErrorClassifier, FailureTracker, ReplanPolicy, RetryPolicy
from .store import ThreadStore
from .summary import ResponseComposer
from .tools import ToolCallExecutor, ToolRegistryAdapter
from .types import (
    AgentEvent,
    AgentOutputType,
    AgentRunResult,
    ChatInput,
    ModelChunk,
    ToolCall,
    ToolResult,
)
from ..store.memory_store import MemoryStore
from ..skills.executor import SkillExecutor
from ..skills.runtime import SkillCall


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
        max_steps: int = 20,
        timeout_s: int = 300,
        tool_timeout_s: int = 60,
        permission_mode: str = "workspace_write",
        auto_approve: bool = False,
        user_prompt: Any = None,
        event_bus: Any = None,
    ) -> None:
        self.event_bus = event_bus  # LifecycleEventBus | None
        self.project_root = project_root
        self.store = store or ThreadStore()
        self.memory_store = MemoryStore()
        task_runtime = TaskRuntime()
        self.checkpoint_manager = CheckpointManager(
            task_runtime=task_runtime,
            snapshotter=CheckpointSnapshotter(),
            workspace_root=project_root,
        )
        self.tool_registry = tool_registry or ToolRegistryAdapter(
            project_root=project_root,
            permission_mode=permission_mode,
            memory_store=self.memory_store,
            checkpoint_manager=self.checkpoint_manager,
            thread_store=self.store,
            user_prompt=user_prompt,
        )
        self.tool_executor = tool_executor or ToolCallExecutor(
            registry_adapter=self.tool_registry,
            permission_mode=permission_mode,
            auto_approve=auto_approve,
            tool_timeout_s=tool_timeout_s,
        )
        self.model_client = model_client or RuntimeModelClient()
        self.model_info = self.model_client.backend_info() if hasattr(self.model_client, "backend_info") else {
            "model_backend": "fake",
            "model_provider": "fake",
            "model_name": "fake-agent-v0",
        }
        self.context_store = context_store or ContextStore(session_store=self.store, memory_store=self.memory_store)
        model_name = str(self.model_info.get("model_name") or "")
        self._context_window = get_context_window(model_name)
        self._model_name = model_name
        compaction_threshold = 12000
        try:
            from ..config.manager import get_config
            cfg = get_config()
            ct = cfg.get("llm.compaction_threshold")
            if ct and int(ct) > 0:
                compaction_threshold = int(ct)
        except Exception:
            pass

        self.context_builder = context_builder or ContextBuilder(
            session_store=self.store,
            memory_store=self.memory_store,
            compactor=ContextCompactorAdapter(max_tokens=compaction_threshold, model_name=model_name),
            skill_registry=self.tool_registry.skill_registry,
            context_store=self.context_store,
            model_info=self.model_info,
            permission_mode=permission_mode,
        )
        self.prompt_builder = PromptBuilder(skill_registry=self.tool_registry.skill_registry)
        self.context_updater = ContextUpdater(context_store=self.context_store)
        self.skill_executor = SkillExecutor(
            skill_registry=self.tool_registry.skill_registry,
            tool_executor=self.tool_executor,
            project_root=project_root,
        )
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
        available_skills = list(self.tool_registry.skill_registry.available_names())
        loaded_skills: list[str] = []
        skill_results_log: list[dict[str, Any]] = []
        skills_used: list[str] = []
        turn_context = None
        seen_calls: dict[str, list[tuple[frozenset[tuple[str, Any]], dict[str, Any]]]] = {}
        read_file_paths: set[str] = set()

        # s16: Fire lifecycle hooks — session_start / turn_start
        if self.event_bus is not None:
            from ..core.hooks.schema import HookStage
            self.event_bus.fire_audit(HookStage.SESSION_START, {
                "session_id": session_id,
                "project_id": chat_input.project_id,
                "cwd": chat_input.cwd,
            })
            result = self.event_bus.fire(HookStage.TURN_START, {
                "session_id": session_id,
                "turn_id": turn_id,
                "text": chat_input.text,
            })
            if not result.allowed:
                return self._complete_early(
                    session_id=session_id,
                    turn_id=turn_id,
                    events=events,
                    final_answer=result.reason or "Turn blocked by lifecycle hook",
                    stop_reason="hook_denied",
                    output_type="refusal",
                    available_skills=available_skills,
                    loaded_skills=loaded_skills,
                )

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

        # s16: Fire compact_pre hook before context building (may trigger compaction)
        if self.event_bus is not None:
            from ..core.hooks.schema import HookStage
            self.event_bus.fire_audit(HookStage.COMPACT_PRE, {
                "session_id": session_id,
                "turn_id": turn_id,
            })

        # — LLM-first: build context, then let the LLM decide via tool calls —
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

        # Inject prior context reuse signals so the LLM can reference previous turns
        context_reuse_signals = self._detect_context_reuse_signals(chat_input.text, session_id)
        context_reuse_detected = context_reuse_signals is not None
        if context_reuse_signals:
            self._emit(events, turn_id, "context_observation_reused", context_reuse_signals)
            # Inject previous research/skill context as a system hint for the LLM
            hint_parts: list[str] = []
            if "skill_observation" in context_reuse_signals:
                obs = context_reuse_signals["skill_observation"]
                hint_parts.append(
                    f"Previous skill result for '{obs.get('skill_name')}': {obs.get('summary')} "
                    f"(files: {', '.join(obs.get('related_files') or []) or 'none'})"
                )
            if "research_observation" in context_reuse_signals:
                obs = context_reuse_signals["research_observation"]
                hint_parts.append(
                    f"Previous research for '{obs.get('query')}': {obs.get('answer_summary')} "
                    f"(sources: {len(obs.get('sources') or [])})"
                )
            if hint_parts:
                messages.append({"role": "user", "content": "Prior context reuse:\n" + "\n".join(hint_parts)})

        # Track context window usage
        estimator = TokenEstimator(self._model_name)
        context_used = estimator.count_messages(messages)
        context_pct = context_used / self._context_window if self._context_window > 0 else 0.0
        self._emit(events, turn_id, "context_window_usage", {
            "used_tokens": context_used,
            "context_window": self._context_window,
            "usage_pct": round(context_pct, 3),
            "message_count": len(messages),
        })

        last_progress_marker = ""
        no_progress_count = 0
        failure_tracker = FailureTracker(max_same_tool=3, max_repeat=3)
        retry_with_tool_instruction_count = 0
        retry_with_length_count = 0

        # Provide model_client to subagent runner if not already set
        if self.tool_registry is not None:
            from ..core.subagents.runner import SubagentRunner
            _runner = SubagentRunner(
                project_root=self.project_root,
                model_client=self.model_client,
                tool_registry=self.tool_registry,
            )
            self.tool_registry.subagent_pool.set_runner(_runner.run)

        try:
            for step in range(1, self.max_steps + 1):
                final_answer = ""  # Reset per-step — stale value from previous step is not valid
                if (time.perf_counter() - started) > self.timeout_s:
                    stop_reason = "timeout"
                    break

                # Inject completed background task results before the LLM call
                if self.tool_registry is not None:
                    notifs = self.tool_registry.bg_task_manager.drain_notifications()
                    if notifs:
                        notif_lines = "\n".join(
                            f"[bg:{n['task_id']}] {n['status']}: "
                            f"{n.get('result') or n.get('error') or ''}"
                            for n in notifs
                        )
                        messages.append({
                            "role": "user",
                            "content": f"<background-results>\n{notif_lines}\n</background-results>",
                        })
                        self._emit(events, turn_id, "bg_notifications_injected", {"count": len(notifs)})

                    # Inject team inbox messages
                    team_inbox = self.tool_registry.message_bus.read_inbox("lead")
                    if team_inbox:
                        messages.append({
                            "role": "user",
                            "content": f"<team-inbox>{json.dumps(team_inbox, ensure_ascii=False)}</team-inbox>",
                        })
                        self._emit(events, turn_id, "team_inbox_injected", {"count": len(team_inbox)})

                    # Inject completed subagent results
                    subagent_notifs = self.tool_registry.subagent_pool.drain_notifications()
                    if subagent_notifs:
                        notif_lines = "\n".join(
                            f"[{n['agent_id']}] ({n['agent_type']}) {n['status']}: "
                            f"{n.get('result') or n.get('error') or ''}"
                            for n in subagent_notifs
                        )
                        messages.append({
                            "role": "user",
                            "content": f"<subagent-results>\n{notif_lines}\n</subagent-results>",
                        })
                        self._emit(events, turn_id, "subagent_notifications_injected", {"count": len(subagent_notifs)})

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

                # Handle truncated response — compact and retry once
                if model_resp.finish_reason == "length" and retry_with_length_count < 1:
                    retry_with_length_count += 1
                    self._emit(events, turn_id, "length_retry_started", {"step": step})
                    compacted, report = compact_messages(
                        messages, session_id=session_id, model_name=self._model_name,
                    )
                    messages = list(compacted)
                    self._emit(events, turn_id, "length_retry_compacted", {
                        "step": step,
                        "stage": report.stage,
                        "tokens_before": report.tokens_before,
                        "tokens_after": report.tokens_after,
                    })
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
                    finish = model_resp.finish_reason or ""
                    # Only process tool-intent retry on the first step — once tools have
                    # been called, model text describing results ("让我查看结果") is legitimate.
                    if finish == "retry_with_tool_instruction":
                        if len(tool_calls_log) == 0:
                            retry_with_tool_instruction_count += 1
                            if retry_with_tool_instruction_count >= 2:
                                stop_reason = "retry_with_tool_instruction"
                                self._emit(events, turn_id, "retry_with_tool_instruction_exhausted", {
                                    "step": step, "count": retry_with_tool_instruction_count,
                                })
                                break
                            self._emit(events, turn_id, "retry_with_tool_instruction", {
                                "step": step, "count": retry_with_tool_instruction_count,
                                "retry_reason": (model_resp.raw or {}).get("retry_reason", "natural_language_tool_intent"),
                            })
                            # Tell the LLM WHY its response was rejected so it can fix it
                            messages.append({
                                "role": "user",
                                "content": (
                                    "Your last response described what you intend to do "
                                    "but did NOT actually call any tool. You MUST call the "
                                    "appropriate tool function directly — do NOT just say "
                                    "what you will do. Use the tool now."
                                ),
                            })
                            continue
                        # Tools were already called — model's text is a synthesis of results.
                        # Accept it as the final answer instead of breaking.
                        final_answer = model_resp.final_answer or model_resp.assistant_text or model_resp.reasoning_summary or ""
                        if not final_answer:
                            stop_reason = finish or "no_progress"
                            break
                        output_type = "answer"
                        stop_reason = "completed"
                        self._emit(events, turn_id, "final_answer_synthesized", {
                            "step": step, "text_length": len(final_answer),
                        })
                        break
                    stop_reason = finish or "no_progress"
                    break

                # Build assistant message for conversation history (OpenAI protocol)
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": model_resp.reasoning_summary or model_resp.assistant_text or None,
                }
                if model_resp.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in model_resp.tool_calls
                    ]
                messages.append(assistant_msg)

                for call in model_resp.tool_calls:
                    call = self._normalize_tool_call(chat_input.text, call)

                    # Check if this tool has already failed or been called too many times
                    reject, reject_reason, reject_kind = failure_tracker.should_reject_tool(call.name)
                    if reject:
                        self._emit(events, turn_id, "tool_rejected", {
                            "step": step, "tool_name": call.name,
                            "reason": reject_reason, "kind": reject_kind,
                        })
                        if reject_kind == "repeat":
                            if failure_tracker.is_repeat_hard_stop(call.name):
                                # Model already got a synthesis nudge — hard stop
                                stop_reason = "consecutive_rejections"
                                self._emit(events, turn_id, "consecutive_failures_detected", {
                                    "step": step, "message": reject_reason,
                                })
                                break
                            # First repeat rejection — inject synthesis nudge, skip tool
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"<rejected>You have called `{call.name}` "
                                    f"too many times. Do NOT call it again. "
                                    "Synthesize your final answer NOW from the "
                                    "results you already have. Write the answer "
                                    "directly — no more tool calls.</rejected>"
                                ),
                            })
                            continue
                        # Failure kind — tool has failed too many times
                        messages.append({
                            "role": "user",
                            "content": f"Tool `{call.name}` rejected: {reject_reason}",
                        })
                        continue

                    # Prevent duplicate skill.load — once loaded, the instructions
                    # are already in context. Reloading wastes turns and creates loops.
                    if call.name == "skill.load":
                        skill_name = str(call.arguments.get("name") or "").strip()
                        if skill_name and skill_name in loaded_skills:
                            self._emit(events, turn_id, "skill_already_loaded", {
                                "step": step, "skill_name": skill_name,
                            })
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"Skill `{skill_name}` is already loaded. Its instructions "
                                    "are in the context above. Do NOT call skill.load again — "
                                    "follow the skill instructions to complete the task."
                                ),
                            })
                            failure_tracker.record_success(call.name)
                            continue

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

                        if result.ok:
                            failure_tracker.record_success(result.name)
                        else:
                            failure_tracker.record_failure(
                                tool_name=result.name,
                                error_category="skill_error",
                                error_message=str(result.error or "")[:200],
                                step=step,
                            )
                            should_stop, stop_msg = failure_tracker.should_stop()
                            if should_stop:
                                stop_reason = "consecutive_failures"
                                output_type = "error"
                                final_answer = stop_msg
                                self._emit(events, turn_id, "consecutive_failures_detected", {
                                    "step": step, "message": stop_msg,
                                })
                                break

                        messages.append({"role": "tool", "tool_call_id": call.id, "content": self._observation_text(result)})
                        self._persist_tool_message(session_id, turn_id, call.id, result.name, self._observation_text(result))
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
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": prev_obs})
                        self._persist_tool_message(session_id, turn_id, call.id, call.name, prev_obs)
                        self._emit(events, turn_id, "tool_call_deduped", {"step": step, "tool_name": call.name})
                        self._emit(events, turn_id, "observation_reused", {"step": step, "tool_name": call.name})
                        failure_tracker.record_success(call.name)
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
                        failure_tracker.record_success(call.name)
                        seen_calls.setdefault(call.name, []).append((canonical_key[1], result_dict))
                        if call.name == "repo_reader.read_file":
                            path = str(call.arguments.get("path") or call.arguments.get("file_path") or "")
                            if path:
                                read_file_paths.add(path)
                        if call.name == "skill.load":
                            skill_body = self._observation_text(result)
                            skill_name = str(result.metadata.get("skill_name") or call.arguments.get("name") or "").strip()
                            # Aligned with Claude Code: skill body goes directly into the
                            # tool result so the model can act on it. The model called
                            # skill.load — it gets the instructions as the response.
                            # No separate user message that breaks the ReAct loop.
                            skill_tool_msg = (
                                f"<skill-context name=\"{skill_name}\">\n"
                                f"{skill_body}\n"
                                "</skill-context>\n\n"
                                f"These are the complete instructions for the `{skill_name}` skill. "
                                "Call the tools described above NOW to complete the user's task. "
                                "Do NOT describe what you plan to do — use the tool functions directly."
                            )
                            messages.append({
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": skill_tool_msg,
                            })
                            self._persist_tool_message(session_id, turn_id, call.id, call.name, skill_tool_msg)
                        else:
                            messages.append({"role": "tool", "tool_call_id": call.id, "content": self._observation_text(result)})
                            self._persist_tool_message(session_id, turn_id, call.id, result.name, self._observation_text(result))
                        self._emit(events, turn_id, "observation_added", {"step": step, "tool_name": result.name})
                        continue

                    # ── Tool failed ──
                    # Always show the model what went wrong so it can adapt.
                    # Without this, DeepSeek keeps retrying the same failing call
                    # because it never sees the actual error.
                    obs_text = self._observation_text(result)
                    classification = self.error_classifier.classify(result)
                    failure_tracker.record_failure(
                        tool_name=result.name,
                        error_category=classification.category,
                        error_message=str(result.error or ""),
                        step=step,
                    )
                    should_stop, stop_msg = failure_tracker.should_stop()
                    if should_stop:
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": obs_text})
                        self._persist_tool_message(session_id, turn_id, call.id, result.name, obs_text)
                        stop_reason = "consecutive_failures"
                        output_type = "error"
                        final_answer = stop_msg
                        self._emit(events, turn_id, "consecutive_failures_detected", {
                            "step": step, "message": stop_msg,
                        })
                        break

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
                            failure_tracker.record_success(retry_result.name)
                            messages.append({"role": "tool", "tool_call_id": call.id, "content": self._observation_text(retry_result)})
                            self._persist_tool_message(session_id, turn_id, call.id, retry_result.name, self._observation_text(retry_result))
                            self._emit(events, turn_id, "observation_added", {"step": step, "tool_name": retry_result.name})
                            continue
                        # Retry also failed — show both results + stop guidance
                        retry_classification = self.error_classifier.classify(retry_result)
                        failure_tracker.record_failure(
                            tool_name=retry_result.name,
                            error_category=retry_classification.category,
                            error_message=str(retry_result.error or ""),
                            step=step,
                        )
                        should_stop2, stop_msg2 = failure_tracker.should_stop()
                        if should_stop2:
                            retry_obs = f"{obs_text}\n\n[Retry also failed]\n{self._observation_text(retry_result)}"
                            messages.append({"role": "tool", "tool_call_id": call.id, "content": retry_obs})
                            self._persist_tool_message(session_id, turn_id, call.id, result.name, retry_obs)
                            stop_reason = "consecutive_failures"
                            output_type = "error"
                            final_answer = stop_msg2
                            self._emit(events, turn_id, "consecutive_failures_detected", {
                                "step": step, "message": stop_msg2,
                            })
                            break

                    # Feed the failure to the model so it can adapt
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": obs_text})
                    self._persist_tool_message(session_id, turn_id, call.id, result.name, obs_text)
                    self._emit(events, turn_id, "observation_added", {"step": step, "tool_name": result.name})
                    continue

                if stop_reason in {"approval_required", "timeout", "consecutive_failures", "consecutive_rejections"}:
                    break


                # Mid-turn auto-compaction: prevent context overflow during long turns
                usage_pct = estimator.count_messages(messages) / self._context_window if self._context_window > 0 else 0.0
                if usage_pct > 0.70:
                    compacted, report = compact_messages(
                        messages, session_id=session_id, model_name=self._model_name,
                    )
                    if report.stage != "none":
                        messages = list(compacted)
                        self._emit(events, turn_id, "mid_turn_compaction", {
                            "step": step, "stage": report.stage,
                            "usage_pct": round(usage_pct, 3),
                            "tokens_before": report.tokens_before,
                            "tokens_after": report.tokens_after,
                        })

                marker = f"{len(tool_calls_log)}:{len(tool_results_log)}:{final_answer[:60]}"
                if marker == last_progress_marker:
                    no_progress_count += 1
                else:
                    no_progress_count = 0
                    last_progress_marker = marker
                if no_progress_count >= 4:
                    stop_reason = "no_progress"
                    output_type = "partial"
                    break

            tool_result_objs = [ToolResult(**item) for item in tool_results_log]
            if not final_answer:
                final_answer = self._fallback_final_answer(tool_result_objs, stop_reason)
            if output_type == "answer" and stop_reason in {"timeout", "approval_required", "max_steps", "no_progress"}:
                output_type = "partial"
            # Propagate skill partial output_type to overall result
            if output_type in {"answer", "tool_result"} and skill_results_log:
                for sr in skill_results_log:
                    if isinstance(sr, dict) and sr.get("output_type") == "partial":
                        output_type = "partial"
                        break

            summary = self.summary_composer.compose(
                final_answer=final_answer,
                tool_results=tool_result_objs,
                stop_reason=stop_reason,
                output_type=output_type,
                context_reuse=context_reuse_detected,
                available_skills=available_skills,
                loaded_skills=loaded_skills,
                skill_loads_count=len(loaded_skills),
                skills_used=skills_used,
                skill_calls_count=len(skill_results_log),
                skill_results=skill_results_log,
                previous_summaries=self.store.load_summaries(session_id, limit=5),
            )
            self.store.save_summary(session_id, turn_id, summary)
            _UNCLEAN_STOP_REASONS = {"max_steps", "timeout", "no_progress", "consecutive_failures",
                                     "retry_with_tool_instruction", "provider_network_error", "length"}
            if final_answer and stop_reason not in _UNCLEAN_STOP_REASONS:
                self.store.save_final_answer(session_id, turn_id, final_answer)
            elif final_answer:
                # Unclean stop: save_final_answer is skipped, so persist
                # the assistant message manually for cross-turn continuity.
                self.store.append_message(session_id, turn_id, "assistant", final_answer)

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

            # s16: Fire lifecycle hooks — turn_end / session_end
            if self.event_bus is not None:
                from ..core.hooks.schema import HookStage
                self.event_bus.fire_audit(HookStage.TURN_END, {
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "status": status,
                    "stop_reason": stop_reason,
                })
                self.event_bus.fire_audit(HookStage.SESSION_END, {
                    "session_id": session_id,
                    "turn_id": turn_id,
                })
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
                previous_summaries=self.store.load_summaries(session_id, limit=5),
            )
            self.store.save_summary(session_id, turn_id, summary)
            self.store.save_final_answer(session_id, turn_id, final_answer)

            # s16: Fire lifecycle hooks on failure too
            if self.event_bus is not None:
                from ..core.hooks.schema import HookStage
                self.event_bus.fire_audit(HookStage.TURN_END, {
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "status": "failed",
                    "stop_reason": stop_reason,
                })
                self.event_bus.fire_audit(HookStage.SESSION_END, {
                    "session_id": session_id,
                    "turn_id": turn_id,
                })

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
    ) -> AgentRunResult:
        summary = self.summary_composer.compose(
            final_answer=final_answer,
            tool_results=[],
            stop_reason=stop_reason,
            output_type=output_type,
            available_skills=available_skills,
            loaded_skills=loaded_skills,
            skill_loads_count=len(loaded_skills),
            previous_summaries=self.store.load_summaries(session_id, limit=5),
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

    def _persist_tool_message(
        self, session_id: str, turn_id: str, call_id: str,
        tool_name: str, content: str,
    ) -> None:
        """Persist a tool result as a message so it appears in cross-turn history."""
        self.store.append_message(
            session_id, turn_id, "tool", content,
            tool_call_id=call_id,
            metadata={"tool_name": tool_name},
        )

    def _persist_stream_turn_result(
        self, session_id: str, turn_id: str,
        final_answer: str, stop_reason: str,
    ) -> None:
        """Save assistant message and summary at the end of a streaming turn."""
        if final_answer.strip():
            self.store.save_final_answer(session_id, turn_id, final_answer)
        summary = self.summary_composer.compose(
            final_answer=final_answer,
            tool_results=[],
            stop_reason=stop_reason,
            previous_summaries=self.store.load_summaries(session_id, limit=5),
        )
        self.store.save_summary(session_id, turn_id, summary)

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

    # Minimum Jaccard similarity (0.0-1.0) to consider two texts related
    _CONTEXT_REUSE_SIMILARITY_THRESHOLD: float = 0.15

    @staticmethod
    def _jaccard_similarity(text_a: str, text_b: str) -> float:
        """Jaccard similarity on word sets (3+ char words, case-insensitive)."""
        def _words(s: str) -> set[str]:
            return {w for w in str(s or "").lower().split() if len(w) >= 3}
        wa = _words(text_a)
        wb = _words(text_b)
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / len(wa | wb)

    def _detect_context_reuse_signals(self, text: str, session_id: str) -> dict[str, Any] | None:
        """Detect prior context that may be relevant; LLM decides whether to use it.

        Uses explicit keyword markers as fast path, then falls back to Jaccard
        word-overlap similarity against recent observations for implicit reuse.
        """
        lowered = str(text or "").lower()
        markers = (
            "刚才", "that file", "previous result", "刚才那个文件", "刚才的结果",
            "based on the previous", "刚才查到", "official source", "official docs",
            "previous research", "based on the previous research",
        )
        if any(marker in lowered for marker in markers):
            signals: dict[str, Any] = {}
            skill_obs = self.context_store.retrieve_skill_observation(session_id)
            if skill_obs is not None:
                signals["skill_observation"] = skill_obs.to_dict()
            research_obs = self.context_store.retrieve_research_observation(session_id)
            if research_obs is not None:
                signals["research_observation"] = research_obs.to_dict()
            return signals if signals else None

        # Semantic fallback: Jaccard word overlap with recent observations
        recent = self.context_store.retrieve_recent_context(session_id, limit=6)
        signals: dict[str, Any] = {}
        for obs_dict in recent.get("skill_observations", []):
            obs_text = f"{obs_dict.get('skill_name', '')} {obs_dict.get('summary', '')}"
            if self._jaccard_similarity(text, obs_text) >= self._CONTEXT_REUSE_SIMILARITY_THRESHOLD:
                signals["skill_observation"] = obs_dict
                break
        for obs_dict in recent.get("research_observations", []):
            obs_text = f"{obs_dict.get('query', '')} {obs_dict.get('answer_summary', '')}"
            if self._jaccard_similarity(text, obs_text) >= self._CONTEXT_REUSE_SIMILARITY_THRESHOLD:
                signals["research_observation"] = obs_dict
                break
        return signals if signals else None

    def run_turn_stream(self, chat_input: ChatInput) -> Iterator[ModelChunk]:
        """Streaming variant of run_turn — yields ModelChunk events as the LLM responds.

        Multi-turn: after tool execution, tool results are fed back to the LLM so it
        can produce a final answer informed by actual observations.
        """
        started = time.perf_counter()
        session = self.store.create_or_resume_session(chat_input)
        session_id = str(session["session_id"])
        turn = self.store.create_turn(session_id, status="running", metadata={"project_id": chat_input.project_id})
        turn_id = turn.turn_id

        self.store.append_message(session_id, turn_id, "user", chat_input.text, metadata={"kind": "user_input"})
        yield ModelChunk(kind="event", text_delta="", tool_name="turn_started",
                         tool_arguments_delta=chat_input.text)

        from ..core.debug_log import debug_log as _dbg2, is_debug_enabled as _dbg_on2
        _dbg2_on = _dbg_on2()
        if _dbg2_on:
            _dbg2("loop", "post-event: starting sensitive check + tool specs + build_messages")

        if self._is_sensitive_request(chat_input.text):
            yield ModelChunk(kind="text_delta", text_delta="I can't print .env files or API keys because they may contain secrets.")
            yield ModelChunk(kind="done", finish_reason="safety_refusal")
            return

        if _dbg2_on:
            _t1 = time.perf_counter()
        tool_specs = self.tool_registry.list_tool_specs()
        if _dbg2_on:
            _dbg2("loop", f"list_tool_specs done in {time.perf_counter()-_t1:.1f}s, {len(tool_specs)} tools")

        if _dbg2_on:
            _t2 = time.perf_counter()
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
        if _dbg2_on:
            _dbg2("loop", f"build_messages done in {time.perf_counter()-_t2:.1f}s, {len(messages)} messages")

        # Emit context window usage so the TUI can track context budget
        stream_estimator = TokenEstimator(self._model_name)
        stream_context_used = stream_estimator.count_messages(messages)
        stream_usage_pct = stream_context_used / self._context_window if self._context_window > 0 else 0.0
        self._event_sink.emit(AgentEvent.new(
            turn_id=turn_id, event_type="context_window_usage",
            payload={
                "used_tokens": stream_context_used,
                "context_window": self._context_window,
                "usage_pct": round(stream_usage_pct, 3),
                "message_count": len(messages),
            }))

        if _dbg2_on:
            _dbg2("loop", "entering step loop")

        try:
            stream_failures = FailureTracker(max_repeat=3)
            stream_no_progress = 0
            stream_last_tool_count = 0
            stream_last_tool_names: frozenset[str] = frozenset()
            stream_retry_with_length_count = 0
            stream_retry_tool_intent_count = 0
            stream_retry_reasoning_only_count = 0
            stream_retry_empty_response_count = 0
            stream_any_tool_called = False
            stream_seen_calls: dict[str, list[tuple[frozenset[tuple[str, Any]], dict[str, Any]]]] = {}
            stream_loaded_skills: list[str] = []
            stream_tool_call_counts_total: dict[str, int] = {}
            stream_last_good_content: str = ""
            stream_synthesis_steps = 0  # successful tool-calling steps since last nudge
            stream_total_tool_calls = 0  # total successful tool calls across all steps
            for step in range(1, self.max_steps + 1):
                if (time.perf_counter() - started) > self.timeout_s:
                    yield ModelChunk(kind="done", finish_reason="timeout")
                    return

                # Inject completed background task results before each streaming LLM call
                if self.tool_registry is not None:
                    notifs = self.tool_registry.bg_task_manager.drain_notifications()
                    if notifs:
                        notif_lines = "\n".join(
                            f"[bg:{n['task_id']}] {n['status']}: "
                            f"{n.get('result') or n.get('error') or ''}"
                            for n in notifs
                        )
                        messages.append({
                            "role": "user",
                            "content": f"<background-results>\n{notif_lines}\n</background-results>",
                        })
                        yield ModelChunk(kind="progress_delta", text="bg_notifications_injected")

                    # Inject completed subagent results
                    subagent_notifs = self.tool_registry.subagent_pool.drain_notifications()
                    if subagent_notifs:
                        notif_lines = "\n".join(
                            f"[{n['agent_id']}] ({n['agent_type']}) {n['status']}: "
                            f"{n.get('result') or n.get('error') or ''}"
                            for n in subagent_notifs
                        )
                        messages.append({
                            "role": "user",
                            "content": f"<subagent-results>\n{notif_lines}\n</subagent-results>",
                        })
                        yield ModelChunk(kind="progress_delta", text="subagent_notifications_injected")

                from ..core.debug_log import debug_log as _dbg_log, is_debug_enabled as _dbg_on
                _dbg = _dbg_on()
                _t0 = time.perf_counter()
                if _dbg:
                    _dbg_log("loop", f"step {step}: LLM call starting, {len(messages)} messages")
                yield ModelChunk(kind="progress_delta", progress_delta="__phase_thinking__")
                stream = self.model_client.complete_stream(messages, tools=tool_specs)
                if _dbg:
                    _dbg_log("loop", f"step {step}: LLM stream obtained in {time.perf_counter()-_t0:.1f}s")
                tool_calls_buffer: list[ToolCall] = []
                step_chunks: list[ModelChunk] = []  # Buffer entire LLM response
                step_finish_reason = "stop"

                for chunk in stream:
                    if chunk.kind == "tool_call_delta":
                        args = self._parse_tool_args(chunk.tool_arguments_delta)
                        tool_calls_buffer.append(ToolCall.new(
                            id=chunk.tool_call_id or None,
                            name=chunk.tool_name,
                            arguments=args,
                        ))
                        step_chunks.append(chunk)
                    elif chunk.kind == "done":
                        step_finish_reason = chunk.finish_reason  # captured for length detection
                    elif chunk.kind in ("text_delta", "reasoning_delta"):
                        step_chunks.append(chunk)

                if _dbg:
                    _dbg_log("loop", f"step {step}: LLM stream done in {time.perf_counter()-_t0:.1f}s, {len(step_chunks)} chunks, {len(tool_calls_buffer)} tool_calls, finish={step_finish_reason}")

                # — Classify: text + tool calls → progress; text only → answer —
                if not tool_calls_buffer:
                    # Check for tool intent before treating as final answer.
                    # Only on the first step — once tools have been called, the model is
                    # processing results, not describing intent. Phrases like "让我查看结果"
                    # are legitimate follow-up, not tool-intent statements.
                    collected_text = "".join(
                        c.text_delta or c.reasoning_delta or ""
                        for c in step_chunks
                        if c.kind in ("text_delta", "reasoning_delta")
                    )
                    if (collected_text.strip()
                            and not stream_any_tool_called
                            and RuntimeModelClient._looks_like_tool_intent_text(collected_text)):
                        # Try to salvage tool calls from text
                        salvaged = RuntimeModelClient._parse_tool_plan_from_content(
                            collected_text, safe_to_canonical={},
                        )
                        if salvaged.tool_calls:
                            for tc in salvaged.tool_calls:
                                yield ModelChunk(
                                    kind="tool_call_delta",
                                    tool_call_id=tc.id,
                                    tool_name=tc.name,
                                    tool_arguments_delta=json.dumps(tc.arguments, ensure_ascii=False),
                                )
                                tool_calls_buffer.append(tc)
                            # Fall through to tool execution below
                        else:
                            stream_retry_tool_intent_count += 1
                            if stream_retry_tool_intent_count >= 2:
                                yield ModelChunk(kind="done", finish_reason="retry_with_tool_instruction")
                                return
                            messages.append({
                                "role": "user",
                                "content": (
                                    "Your last response described what you intend to do "
                                    "but did NOT actually call any tool. You MUST call the "
                                    "appropriate tool function directly — do NOT just say "
                                    "what you will do. Use the tool now."
                                ),
                            })
                            continue

                if not tool_calls_buffer:
                    # Handle length (truncated) — compact and retry once
                    if step_finish_reason == "length" and stream_retry_with_length_count < 1:
                        stream_retry_with_length_count += 1
                        compacted, _ = compact_messages(
                            messages, session_id=session_id, model_name=self._model_name,
                        )
                        messages = list(compacted)
                        continue
                    # Final answer — no tool calls in this step
                    stream_final_parts: list[str] = []
                    for c in step_chunks:
                        if c.kind == "text_delta":
                            text = c.text_delta or ""
                            if text.strip():
                                stream_final_parts.append(text)
                                yield ModelChunk(kind="text_delta", text_delta=text)
                        elif c.kind == "reasoning_delta":
                            text = c.reasoning_delta or ""
                            if text.strip():
                                yield ModelChunk(kind="reasoning_delta", reasoning_delta=text)
                    stream_final_answer = "".join(stream_final_parts).strip()
                    if stream_final_answer:
                        self._persist_stream_turn_result(session_id, turn_id, stream_final_answer, "completed")
                        yield ModelChunk(kind="done", finish_reason="stop")
                        return

                    # Model produced reasoning but no text answer — retry once.
                    # Reasoning models (DeepSeek, o1, etc.) can exhaust their reasoning
                    # budget without outputting a single visible token. Claude Code
                    # handles this by blocking think/tool_choice in the retry; for
                    # providers without that API, we inject a strong textual nudge.
                    has_reasoning = any(
                        c.kind == "reasoning_delta" and (c.reasoning_delta or "").strip()
                        for c in step_chunks
                    )
                    if has_reasoning and stream_retry_reasoning_only_count < 1:
                        stream_retry_reasoning_only_count += 1
                        messages.append({
                            "role": "user",
                            "content": (
                                "Your last response was ALL reasoning — the user "
                                "cannot see it. You MUST write a direct answer in "
                                "the main text output. "
                                "Do NOT put your answer in reasoning blocks. "
                                "Do NOT think — just output the final answer. "
                                "Start your response with the answer immediately."
                            ),
                        })
                        continue

                    # Empty response after tool results — model produced zero
                    # tokens. DeepSeek sometimes returns an empty stream when
                    # it sees a rejection or large results. Retry once with a
                    # guidance prompt that asks it to synthesize.
                    if stream_any_tool_called and stream_retry_empty_response_count < 1:
                        stream_retry_empty_response_count += 1
                        messages.append({
                            "role": "user",
                            "content": (
                                "Your last response was empty — you must answer. "
                                "Review the tool results above and write a summary "
                                "of what you found. Start writing NOW."
                            ),
                        })
                        continue

                    yield ModelChunk(kind="done", finish_reason="stop")
                    return

                # Has tool calls — text and reasoning from this step are progress
                for c in step_chunks:
                    if c.kind == "text_delta":
                        text = c.text_delta or ""
                        if text.strip():
                            yield ModelChunk(kind="progress_delta", progress_delta=text)
                    elif c.kind == "reasoning_delta":
                        text = c.reasoning_delta or ""
                        if text.strip():
                            yield ModelChunk(kind="progress_delta", progress_delta=text)
                    elif c.kind == "tool_call_delta":
                        yield c  # forward tool calls as-is

                # Handle length (truncated) on steps with tool calls too
                if step_finish_reason == "length" and stream_retry_with_length_count < 1:
                    stream_retry_with_length_count += 1
                    compacted, _ = compact_messages(
                        messages, session_id=session_id, model_name=self._model_name,
                    )
                    messages = list(compacted)
                    continue

                any_ok = False
                stream_tool_names_this_step: set[str] = set()
                stream_tool_call_counts: dict[str, int] = {}
                processed_call_ids: list[str] = []  # track which calls were executed
                for call in tool_calls_buffer:
                    stream_tool_names_this_step.add(call.name)
                    stream_tool_call_counts[call.name] = stream_tool_call_counts.get(call.name, 0) + 1

                    # Reject tools that have failed or been called too many times
                    reject, reject_reason, reject_kind = stream_failures.should_reject_tool(call.name)
                    if reject:
                        if reject_kind == "repeat":
                            # Cross-step repeat: model already saw a rejection
                            # for this tool in a previous step but called it again.
                            if stream_failures.is_repeat_hard_stop(call.name):
                                yield ModelChunk(kind="done", finish_reason="consecutive_rejections")
                                return
                            # First repeat rejection in this batch — inject nudge
                            # and BREAK the tool loop so remaining calls from the
                            # same batch (planned before seeing this rejection) are
                            # discarded. The model gets a fresh chance next step.
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"<rejected>You have called `{call.name}` "
                                    f"too many times. Do NOT call it again. "
                                    "Synthesize your final answer NOW from the "
                                    "results you already have. Write the answer "
                                    "directly — no more tool calls.</rejected>"
                                ),
                            })
                            yield ModelChunk(kind="text_delta",
                                             text_delta=f"\n[Tool `{call.name}`: rejected: {reject_reason}]")
                            break  # stop processing remaining calls; go to next step
                        # Failure kind — tool has failed too many times
                        messages.append({
                            "role": "user",
                            "content": f"Tool `{call.name}` rejected: {reject_reason}",
                        })
                        yield ModelChunk(kind="text_delta",
                                         text_delta=f"\n[Tool `{call.name}`: rejected: {reject_reason}]")
                        continue

                    # — Dedup: skill.load — prevent re-loading the same skill in one turn
                    if call.name == "skill.load":
                        skill_name = str(call.arguments.get("name") or "").strip()
                        if skill_name and skill_name in stream_loaded_skills:
                            dedup_content = (
                                f"Skill `{skill_name}` is already loaded in this turn. "
                                f"Use the instructions from the earlier skill.load result above. "
                                f"Do NOT load it again — proceed with answering the user."
                            )
                            messages.append({
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": dedup_content,
                            })
                            self._persist_tool_message(session_id, turn_id, call.id, call.name, dedup_content)
                            yield ModelChunk(kind="text_delta",
                                             text_delta=f"\n[skill.load `{skill_name}`: already loaded, skipped]")
                            any_ok = True
                            stream_any_tool_called = True
                            stream_failures.record_success(call.name)
                            continue

                    # — Dedup: general tool calls — same args = same result
                    reused_result = self._find_seen_result(stream_seen_calls, call)
                    if reused_result is not None:
                        dedup_text = json.dumps(reused_result.get('content', ''), ensure_ascii=False)[:50000]
                        processed_call_ids.append(call.id)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": dedup_text,
                        })
                        self._persist_tool_message(session_id, turn_id, call.id, call.name, dedup_text)
                        yield ModelChunk(kind="text_delta",
                                         text_delta=f"\n[Tool `{call.name}`: deduplicated]")
                        # Count dedup as progress — we have a valid cached result
                        if reused_result.get("ok"):
                            any_ok = True
                            stream_any_tool_called = True
                        stream_failures.record_success(call.name)
                        continue

                    canonical_key = (call.name, self._tool_args_frozen(call))

                    if call.name == "skill.run":
                        skill_name = str(call.arguments.get("name") or call.arguments.get("skill_name") or "").strip()
                        skill_result = self.skill_executor.run(
                            SkillCall.new(name=skill_name, arguments=call.arguments, source="model"),
                            turn_context,
                        )
                        obs_text = skill_result.final_answer
                        # Track skill.run success/failure
                        skill_ok = skill_result.output_type != "error"
                        if skill_ok:
                            any_ok = True
                            stream_any_tool_called = True
                            stream_seen_calls.setdefault(call.name, []).append(
                                (canonical_key[1], {"content": obs_text, "ok": True})
                            )
                        yield ModelChunk(kind="text_delta", text_delta=obs_text)
                        processed_call_ids.append(call.id)
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": obs_text})
                        self._persist_tool_message(session_id, turn_id, call.id, call.name, obs_text)
                    else:
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
                        obs_text = self._format_content_for_observation(result.content)
                        # Yield tool result for display
                        yield ModelChunk(kind="text_delta",
                                         text_delta=f"\n[Tool `{result.name}`: {obs_text[:16000]}]")
                        # Emit file_change chunk if this tool modified a file
                        if result.metadata.get("auto_diff"):
                            fd = result.metadata["auto_diff"]
                            yield ModelChunk(
                                kind="file_change",
                                file_change={
                                    "path": fd["path"],
                                    "diff_text": fd["diff_text"],
                                    "added": fd["added"],
                                    "removed": fd["removed"],
                                    "status": fd["status"],
                                },
                            )
                        # Track failures and successes
                        if result.ok:
                            stream_failures.record_success(result.name)
                            any_ok = True
                            stream_any_tool_called = True
                            if call.name == "command_runner.run":
                                stream_last_good_content = obs_text
                            if call.name == "skill.load":
                                sk_name = str(result.metadata.get("skill_name") or call.arguments.get("name") or "").strip()
                                if sk_name and sk_name not in stream_loaded_skills:
                                    stream_loaded_skills.append(sk_name)
                            stream_seen_calls.setdefault(call.name, []).append(
                                (canonical_key[1], result.to_dict())
                            )
                        else:
                            classification = self.error_classifier.classify(result)
                            stream_failures.record_failure(
                                tool_name=result.name,
                                error_category=classification.category,
                                error_message=str(result.error or "")[:200],
                                step=step,
                            )
                            should_stop, stop_msg = stream_failures.should_stop()
                            if should_stop:
                                yield ModelChunk(kind="text_delta",
                                                 text_delta=f"\n{stop_msg}")
                                yield ModelChunk(kind="done", finish_reason="consecutive_failures")
                                return
                        # Feed observation back so the LLM can respond
                        if call.name == "skill.load" and result.ok:
                            skill_body = obs_text
                            # Aligned with Claude Code: skill body goes directly into the
                            # tool result so the model can act on it. The model called
                            # skill.load — it gets the instructions as the response.
                            skill_tool_msg = (
                                f"<skill-context name=\"{sk_name}\">\n"
                                f"{skill_body}\n"
                                "</skill-context>\n\n"
                                f"These are the complete instructions for the `{sk_name}` skill. "
                                "Call the tools described above NOW to complete the user's task. "
                                "Do NOT describe what you plan to do — use the tool functions directly."
                            )
                            processed_call_ids.append(call.id)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": skill_tool_msg,
                            })
                            self._persist_tool_message(session_id, turn_id, call.id, call.name, skill_tool_msg)
                        else:
                            truncated = obs_text[:24000]
                            processed_call_ids.append(call.id)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": truncated,
                            })
                            self._persist_tool_message(session_id, turn_id, call.id, result.name, truncated)

                # Build assistant message with ONLY the tool calls that were
                # actually processed (break on repeat rejection skips the rest).
                assistant_text = "".join(
                    c.text_delta or c.reasoning_delta or ""
                    for c in step_chunks
                    if c.kind in ("text_delta", "reasoning_delta")
                ).strip() or None
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": assistant_text}
                processed_ids_set = set(processed_call_ids)
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls_buffer
                    if tc.id in processed_ids_set
                ]
                messages.append(assistant_msg)

                # Mid-turn auto-compaction: prevent context overflow during long turns
                stream_estimator = TokenEstimator(self._model_name)
                stream_usage_pct = stream_estimator.count_messages(messages) / self._context_window if self._context_window > 0 else 0.0
                if stream_usage_pct > 0.70:
                    compacted, report = compact_messages(
                        messages, session_id=session_id, model_name=self._model_name,
                    )
                    if report.stage != "none":
                        messages = list(compacted)

                # ── Progressive synthesis guidance ──────────────────────────
                # Aligned with Claude Code "Stop hook" and Codex "needs_follow_up":
                # after the model has successfully gathered information, nudge it
                # to synthesize a final answer. Without this, reasoning models
                # (DeepSeek) keep calling tools indefinitely — each observation
                # triggers another tool idea, never converging on an answer.
                current_tool_names = frozenset(stream_tool_names_this_step)
                tool_set_repeat = (
                    current_tool_names
                    and current_tool_names == stream_last_tool_names
                    and stream_any_tool_called
                )

                if not any_ok:
                    stream_no_progress += 1
                    stream_synthesis_steps = 0
                    if stream_no_progress >= 3:
                        if stream_last_good_content:
                            yield ModelChunk(kind="text_delta",
                                             text_delta=f"\n{stream_last_good_content}")
                            self._persist_stream_turn_result(session_id, turn_id, stream_last_good_content, "no_progress")
                        yield ModelChunk(kind="done", finish_reason="stop")
                        return
                else:
                    stream_no_progress = 0
                    stream_synthesis_steps += 1
                    stream_total_tool_calls += len([1 for _ in stream_tool_names_this_step])

                # Synthesis nudge: after enough successful tool calls (2+ steps OR
                # 3+ total calls), tell the model to stop gathering and write the
                # answer. Claude Code does this via Stop hooks; Codex uses
                # needs_follow_up signals. A single step with 4 tool calls is just
                # as information-gathering as 2 steps with 2 calls each.
                if stream_any_tool_called and (
                    stream_synthesis_steps >= 2 or stream_total_tool_calls >= 3
                ):
                    messages.append({
                        "role": "user",
                        "content": (
                            "You have collected enough information. "
                            "STOP calling tools. "
                            "Synthesize your final answer NOW from the results above. "
                            "Write the answer directly — do NOT use reasoning blocks, "
                            "do NOT call more tools."
                        ),
                    })
                    stream_synthesis_steps = 0
                    stream_total_tool_calls = 0

                # Tool-set repeat detection: model is re-calling the exact same
                # set of tools as the previous step — stuck in a pattern.
                if tool_set_repeat:
                    messages.append({
                        "role": "user",
                        "content": (
                            "You just called the same tools as the previous step. "
                            "Do NOT repeat the same tool calls. "
                            "Write your final answer NOW based on the results "
                            "you already have."
                        ),
                    })

                stream_last_tool_names = current_tool_names

                # Per-tool-type loop detection: track total calls & hard-stop if looping
                for tool_name, count in stream_tool_call_counts.items():
                    stream_tool_call_counts_total[tool_name] = (
                        stream_tool_call_counts_total.get(tool_name, 0) + count
                    )
                worst_tool = max(stream_tool_call_counts_total.items(), key=lambda kv: kv[1], default=(None, 0))
                if worst_tool[1] >= 4 and stream_any_tool_called:
                    if stream_last_good_content:
                        yield ModelChunk(kind="text_delta",
                                         text_delta=f"\n{stream_last_good_content}")
                        self._persist_stream_turn_result(session_id, turn_id, stream_last_good_content, "no_progress")
                    yield ModelChunk(kind="done", finish_reason="stop")
                    return

            # Max steps exhausted — signal end
            self._persist_stream_turn_result(session_id, turn_id, stream_last_good_content or "", "max_steps")
            yield ModelChunk(kind="done", finish_reason="max_steps")

        except Exception as exc:
            yield ModelChunk(kind="text_delta", text_delta=self._friendly_error_message(exc))
            yield ModelChunk(kind="done", finish_reason=self._map_provider_error_stop_reason(exc))

    @staticmethod
    def _parse_tool_args(raw_args: str) -> dict[str, Any]:
        """Parse a JSON arguments string into a dict, falling back to empty dict."""
        if not raw_args or not raw_args.strip():
            return {}
        try:
            parsed = json.loads(raw_args)
            if isinstance(parsed, dict):
                return parsed
            return {}
        except (json.JSONDecodeError, TypeError):
            return {}

    _MAX_OBSERVATION_LEN = 50000

    @staticmethod
    def _format_content_for_observation(content: Any) -> str:
        """Format tool result content for LLM observation, handling dicts/lists."""
        if isinstance(content, dict):
            tree_text = content.get("tree")
            if tree_text:
                return str(tree_text)
            return json.dumps(content, ensure_ascii=False)
        if isinstance(content, list):
            return json.dumps(content, ensure_ascii=False)
        if isinstance(content, str):
            return content
        return str(content or "")

    @classmethod
    def _observation_text(cls, result: ToolResult) -> str:
        """Return clean tool output — no status headers, no diagnoses.

        Aligned with reference agents (Claude Code, Codex, Hermes, OpenClaw):
        feed the raw tool output to the LLM and let it decide what to do next.
        """
        content = result.content
        limit = cls._MAX_OBSERVATION_LEN

        if isinstance(content, dict):
            # Command output (stdout/stderr/exit_code) — show only what matters.
            # Claude Code style: exit code + stdout + stderr. No verbose JSON
            # metadata (command, cwd, duration_ms) that the model already knows
            # and would only repeat verbatim in its answer.
            if any(k in content for k in ("stdout", "stderr", "exit_code")):
                parts = []
                ec = content.get("exit_code")
                if ec is not None:
                    parts.append(f"exit_code={ec}")
                out = content.get("stdout")
                if out:
                    parts.append(str(out)[:limit])
                err = content.get("stderr")
                if err:
                    parts.append(str(err)[:limit])
                if not out and not err:
                    parts.append("(empty output)")
                return "\n".join(parts) if parts else "(empty)"
            # Tree result — just the tree text
            tree = content.get("tree")
            if tree:
                return str(tree)[:limit]
            # Other dict — JSON
            return json.dumps(content, ensure_ascii=False)[:limit]

        if isinstance(content, list):
            return json.dumps(content, ensure_ascii=False)[:limit]

        if isinstance(content, str):
            return content[:limit]

        raw = str(content or "")
        return raw[:limit] if raw else "(empty)"

    @staticmethod
    def _is_sensitive_request(text: str) -> bool:
        lowered = str(text or "").lower()
        markers = (
            ".env",
            "api key",
            "api token", "access token", "bearer token", "auth token",
            "password",
            "id_rsa",
            "client secret", "api secret", "secret key",
            "jarvis_llm_api_key",
        )
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
        return f"Model call failed: {type(exc).__name__} — {exc}"
