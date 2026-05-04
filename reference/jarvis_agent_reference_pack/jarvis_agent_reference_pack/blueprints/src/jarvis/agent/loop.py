"""Chat-first AgentLoop for Jarvis.

This is the missing centerline: user input -> model -> tool calls -> tool results ->
model continuation -> final answer -> summary/history/events.
"""

from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from .context import ContextBuilder, JsonlThreadStore
from .events import EventSink, InMemoryEventSink
from .model import ModelClient
from .summary import SummaryComposer
from .tools import ToolExecutor
from .types import AgentEvent, AgentRunResult, ChatInput, ChatMessage, ToolResult, TurnStatus


class AgentLoop:
    def __init__(
        self,
        *,
        model_client: ModelClient,
        tool_executor: ToolExecutor,
        context_builder: ContextBuilder,
        thread_store: JsonlThreadStore,
        summary_composer: SummaryComposer | None = None,
        event_sink: EventSink | None = None,
        max_model_steps: int = 8,
        max_tool_calls: int = 16,
    ) -> None:
        self.model_client = model_client
        self.tool_executor = tool_executor
        self.context_builder = context_builder
        self.thread_store = thread_store
        self.summary_composer = summary_composer or SummaryComposer()
        self.event_sink = event_sink or InMemoryEventSink()
        self.max_model_steps = max_model_steps
        self.max_tool_calls = max_tool_calls

    def run_turn(self, chat_input: ChatInput) -> AgentRunResult:
        thread_id = self.thread_store.resolve_thread_id(chat_input)
        turn_id = f"turn_{uuid4().hex[:12]}"
        tool_results: list[ToolResult] = []
        messages = self.context_builder.build_messages(
            thread_id=thread_id,
            chat_input=chat_input,
            tools=self.tool_executor.registry.list_specs(),
        )
        self._emit(turn_id, "turn.started", {"thread_id": thread_id, "text": chat_input.text})

        final_answer = ""
        stop_reason = "max_steps"
        tool_call_count = 0

        try:
            for step in range(self.max_model_steps):
                self._emit(turn_id, "model.started", {"step": step})
                response = self.model_client.complete(messages, self.tool_executor.registry.list_specs())
                self._emit(turn_id, "model.completed", {"step": step, "stop_reason": response.stop_reason})

                if response.content:
                    messages.append(ChatMessage(role="assistant", content=response.content))
                    final_answer = response.content

                if not response.tool_calls:
                    stop_reason = response.stop_reason or "stop"
                    break

                for call in response.tool_calls:
                    if tool_call_count >= self.max_tool_calls:
                        stop_reason = "max_tool_calls"
                        break
                    tool_call_count += 1
                    self._emit(turn_id, "tool.started", {"call": asdict(call)})
                    result = self.tool_executor.execute(call)
                    tool_results.append(result)
                    self._emit(
                        turn_id,
                        "tool.completed" if result.ok else "tool.failed",
                        {"result": asdict(result)},
                    )
                    messages.append(ChatMessage(
                        role="tool",
                        name=result.name,
                        tool_call_id=result.call_id,
                        content=result.content if result.ok else f"ERROR[{result.error_type}]: {result.error}",
                    ))
                else:
                    continue
                break

            user_msg = ChatMessage(role="user", content=chat_input.text)
            self.thread_store.append(thread_id, user_msg)
            if final_answer:
                self.thread_store.append(thread_id, ChatMessage(role="assistant", content=final_answer))
            for result in tool_results:
                self.thread_store.append(thread_id, ChatMessage(
                    role="tool",
                    name=result.name,
                    tool_call_id=result.call_id,
                    content=result.content if result.ok else f"ERROR[{result.error_type}]: {result.error}",
                ))

            summary = self.summary_composer.compose(
                answer=final_answer,
                tool_results=tool_results,
                stop_reason=stop_reason,
            )
            status = TurnStatus.COMPLETED if final_answer else TurnStatus.FAILED
            self._emit(turn_id, "turn.completed", {"status": status.value, "stop_reason": stop_reason})
            return AgentRunResult(
                thread_id=thread_id,
                turn_id=turn_id,
                status=status,
                answer=final_answer,
                messages=messages,
                tool_results=tool_results,
                summary=summary,
                stop_reason=stop_reason,
            )
        except Exception as exc:
            self._emit(turn_id, "turn.failed", {"error": str(exc), "error_type": type(exc).__name__})
            return AgentRunResult(
                thread_id=thread_id,
                turn_id=turn_id,
                status=TurnStatus.FAILED,
                answer="",
                messages=messages,
                tool_results=tool_results,
                summary={"risks": [{"error": str(exc), "error_type": type(exc).__name__}]},
                stop_reason="error",
            )

    def _emit(self, turn_id: str, event_type: str, payload: dict) -> None:
        self.event_sink.emit(AgentEvent(type=event_type, turn_id=turn_id, payload=payload))
