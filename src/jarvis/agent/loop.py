"""Chat-first AgentLoop implementation."""

from __future__ import annotations

import time
from typing import Any

from ..core.react_readiness.replay_store import ReplayStore
from .context import ContextBuilder, ContextCompactorAdapter
from .events import EVENT_TYPES, InMemoryEventSink, ReplayEventSink
from .model import ModelClient, RuntimeModelClient
from .retry import ErrorClassifier, ReplanPolicy, RetryPolicy
from .store import ThreadStore
from .summary import ResponseComposer
from .tools import ToolCallExecutor, ToolRegistryAdapter
from .types import AgentEvent, AgentOutputType, AgentRunResult, ChatInput, ToolCall, ToolResult


class AgentLoop:
    def __init__(
        self,
        *,
        project_root: str = ".",
        store: ThreadStore | None = None,
        context_builder: ContextBuilder | None = None,
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
        self.context_builder = context_builder or ContextBuilder(
            thread_store=self.store,
            compactor=ContextCompactorAdapter(max_tokens=12000),
        )
        self.model_client = model_client or RuntimeModelClient()
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
        # Deduplication: canonical tool_name -> list of (args_frozen, tool_result)
        _seen_calls: dict[str, list[tuple[frozenset, dict[str, Any]]]] = {}

        self.store.append_message(session_id, turn_id, "user", chat_input.text, metadata={"kind": "user_input"})
        self._emit(events, turn_id, "turn_started", {"session_id": session_id, "text": chat_input.text})

        if self._is_sensitive_request(chat_input.text):
            output_type = "refusal"
            stop_reason = "safety_refusal"
            final_answer = "不能直接打印 .env 或 API key，因为其中可能包含敏感凭据。"
            summary = self.summary_composer.compose(
                final_answer=final_answer,
                tool_results=[],
                stop_reason=stop_reason,
                output_type=output_type,
            )
            machine = summary.get("machine") if isinstance(summary, dict) else None
            if isinstance(machine, dict):
                risks = list(machine.get("risks") or [])
                for risk in ("sensitive_env_requested", "secret_requested"):
                    if risk not in risks:
                        risks.append(risk)
                machine["risks"] = risks
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
                tool_calls=tool_calls_log,
                tool_results=tool_results_log,
                status="completed",
                output_type=output_type,
            )

        clarification = self._build_clarification_if_needed(chat_input.text)
        if clarification is not None:
            output_type = "clarification"
            stop_reason = "needs_user_clarification"
            clarification_payload = clarification
            final_answer = str(clarification.get("question") or "").strip()
            summary = self.summary_composer.compose(
                final_answer=final_answer,
                tool_results=[],
                stop_reason=stop_reason,
                output_type=output_type,
                clarification=clarification_payload,
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
                tool_calls=tool_calls_log,
                tool_results=tool_results_log,
                status="completed",
                output_type=output_type,
            )

        tool_specs = self.tool_registry.list_tool_specs()
        messages = self.context_builder.build_messages(
            session_id=session_id,
            chat_input=chat_input,
            tool_specs=tool_specs,
        )

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

                if self._is_sensitive_request(chat_input.text):
                    output_type = "refusal"
                    if model_resp.tool_calls:
                        model_resp.tool_calls = []
                    if not model_resp.final_answer:
                        refusal = "不能直接打印 .env 或 API key，因为其中可能包含敏感凭据。"
                        model_resp.assistant_text = refusal
                        model_resp.final_answer = refusal
                        model_resp.finish_reason = "safety_refusal"

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
                    if output_type != "refusal":
                        output_type = "tool_result" if len(tool_calls_log) > 0 else "answer"
                    stop_reason = "completed"
                    self._emit(events, turn_id, "final_answer_created", {"step": step})
                    break

                if not model_resp.tool_calls and not final_answer:
                    stop_reason = model_resp.finish_reason or "no_progress"
                    break

                for call in model_resp.tool_calls:
                    call = self._normalize_tool_call(chat_input.text, call)
                    canonical_key = (call.name, self._tool_args_frozen(call))
                    is_deduped = False
                    # Check if we've already successfully executed this exact tool+args
                    if call.name in _seen_calls:
                        for args_frozen, prev_result_dict in _seen_calls[call.name]:
                            if args_frozen == canonical_key[1]:
                                # Same tool + same args — reuse previous result
                                is_deduped = True
                                self._emit(events, turn_id, "tool_call_deduped", {
                                    "step": step, "tool_name": call.name,
                                    "args": dict(canonical_key[1]),
                                    "reused_result": prev_result_dict,
                                })
                                tool_calls_log.append(call.to_dict())
                                self.store.append_tool_call(session_id, turn_id, call.to_dict())
                                # Re-inject previous observation so model sees it
                                prev_obs = self._observation_text(ToolResult(**prev_result_dict))
                                messages.append({"role": "tool", "content": prev_obs})
                                tool_results_log.append(prev_result_dict)
                                self.store.append_tool_result(session_id, turn_id, prev_result_dict)
                                self._emit(events, turn_id, "observation_reused", {"step": step, "tool_name": call.name})
                                break
                    if is_deduped:
                        continue
                    tool_calls_log.append(call.to_dict())
                    self.store.append_tool_call(session_id, turn_id, call.to_dict())
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
                    tool_results_log.append(result.to_dict())
                    self.store.append_tool_result(session_id, turn_id, result.to_dict())
                    self._emit(events, turn_id, "tool_call_completed", {"step": step, "tool_result": result.to_dict()})

                    if result.error and "approval_required" in str(result.error):
                        stop_reason = "approval_required"
                        output_type = "partial"
                        self._emit(events, turn_id, "approval_required", {"step": step, "tool_name": result.name, "error": result.error})
                        break

                    if result.ok:
                        # Record for deduplication
                        _seen_calls.setdefault(call.name, []).append((canonical_key[1], result.to_dict()))
                        # Inject summarization hint for query tools
                        if call.name in ("repo_reader.read_file", "repo_reader.search_files", "directory_list", "list_directory"):
                            messages.append({
                                "role": "system",
                                "content": (
                                    "Based on the above observation, generate a concise final answer now. "
                                    "Do not call the same tool again unless the user explicitly asks for more content."
                                ),
                            })
                        obs = self._observation_text(result)
                        messages.append({"role": "tool", "content": obs})
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
                        tool_results_log.append(retry_result.to_dict())
                        self.store.append_tool_result(session_id, turn_id, retry_result.to_dict())
                        self._emit(events, turn_id, "tool_call_completed", {"step": step, "tool_result": retry_result.to_dict()})
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
            )
            if self._is_sensitive_request(chat_input.text):
                machine = summary.get("machine") if isinstance(summary, dict) else None
                if isinstance(machine, dict):
                    risks = list(machine.get("risks") or [])
                    if "sensitive_env_requested" not in risks:
                        risks.append("sensitive_env_requested")
                    machine["risks"] = risks
                    machine["output_type"] = "refusal"

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

            return AgentRunResult(
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
            )
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
            )

    def _emit(self, collector: list[dict[str, Any]], turn_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if event_type not in EVENT_TYPES:
            payload = dict(payload)
            payload["unknown_event_type"] = event_type
            event_type = "turn_failed"
        event = AgentEvent.new(turn_id=turn_id, event_type=event_type, payload=payload)
        self._event_sink.emit(event)
        collector.append(event.to_dict())

    @staticmethod
    def _observation_text(result: ToolResult) -> str:
        return f"Tool `{result.name}` returned ok={result.ok}. content={result.content}"

    @staticmethod
    def _request_requires_tool(text: str) -> bool:
        lowered = str(text or "").lower()
        markers = (
            "读取",
            "readme",
            "read file",
            "列一下当前目录",
            "current directory",
            "run pytest",
            "运行 pytest",
            "modify file",
            "修改文件",
            "run command",
        )
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _is_sensitive_request(text: str) -> bool:
        lowered = str(text or "").lower()
        markers = (
            ".env",
            "api key",
            "token",
            "password",
            "id_rsa",
            "secret",
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
        """Return a hashable representation of tool call arguments for deduplication."""
        return frozenset((str(k), str(v)) for k, v in sorted((call.arguments or {}).items()))

    @staticmethod
    def _fallback_final_answer(tool_results: list[ToolResult], stop_reason: str) -> str:
        if not tool_results:
            return ""
        last = tool_results[-1]
        if last.ok:
            return f"已完成工具执行：{last.name}。模型未返回完整总结，已记录结果。"
        return f"工具执行未完成（{last.name}）：{last.error or 'unknown error'}。stop_reason={stop_reason}。"

    @staticmethod
    def _build_clarification_if_needed(text: str) -> dict[str, Any] | None:
        raw = str(text or "").strip()
        lowered = raw.lower()
        normalized = raw.replace("。", "").replace("？", "").replace("?", "").strip()
        if normalized in {"帮我弄一下", "处理一下", "修一下", "优化它", "这个有问题", "处理这个"}:
            return {"missing_fields": ["target"], "question": "你希望我处理哪个文件、命令或问题？"}
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
        if "403" in lowered or "forbidden" in lowered:
            return "provider_http_error"
        if "404" in lowered or "not found" in lowered:
            return "provider_http_error"
        if "provider unavailable" in lowered or "service unavailable" in lowered:
            return "provider_unavailable"
        return "model_call_failed"

    @staticmethod
    def _friendly_error_message(exc: Exception) -> str:
        stop_reason = AgentLoop._map_provider_error_stop_reason(exc)
        if stop_reason == "provider_network_error":
            return "真实 LLM 调用失败，网络连接被系统拒绝。可以运行 python scripts/check_llm_api.py 检查 API、代理或防火墙配置。"
        if stop_reason == "provider_auth_error":
            return "LLM API 认证失败（401/Unauthorized）。请检查 API key 是否正确，或是否已过期。"
        if stop_reason == "provider_http_error":
            return "LLM provider 返回了错误响应（403/404）。请检查 base_url 配置是否正确。"
        if stop_reason == "provider_unavailable":
            return "当前 LLM provider 不可用，请检查 .env 配置或稍后重试。"
        return f"模型调用失败：{type(exc).__name__}"
