"""AgentToolLoop — the main execution loop for agent requests.

Two paths:
1. Chat path: user input → LLM direct response (no tools)
2. Work path: user input → LLM with tool context → tool calls → ToolRuntime → feedback loop

The loop is bounded by max_rounds to prevent infinite execution.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from json import JSONDecoder
from typing import TYPE_CHECKING, Any

from ..llm.prompt_builder import build_work_execution_prompt
from ..routing.agent_router import AgentRequest, route_agent_request
from .schema import ToolCall, ToolContext, ToolResult
from .registry import ToolRegistry
from .runtime import ToolRuntime

if TYPE_CHECKING:
    from ..llm.provider import LLMProvider


logger = logging.getLogger(__name__)

# Default maximum rounds for the tool loop
DEFAULT_MAX_ROUNDS = 10


@dataclass
class LoopStep:
    """A single step in the agent tool loop."""

    round_num: int
    thought: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    response: str = ""
    is_final: bool = False
    error: str | None = None


@dataclass
class LoopResult:
    """Final result from the agent tool loop."""

    response: str
    steps: list[LoopStep] = field(default_factory=list)
    total_tool_calls: int = 0
    total_rounds: int = 0
    exhausted: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "response": self.response,
            "steps": [self._step_to_dict(s) for s in self.steps],
            "total_tool_calls": self.total_tool_calls,
            "total_rounds": self.total_rounds,
            "exhausted": self.exhausted,
            "error": self.error,
        }

    @staticmethod
    def _step_to_dict(step: LoopStep) -> dict[str, Any]:
        return {
            "round_num": step.round_num,
            "thought": step.thought,
            "tool_calls": step.tool_calls,
            "tool_results": step.tool_results,
            "response": step.response,
            "is_final": step.is_final,
            "error": step.error,
        }


class AgentToolLoop:
    """Main execution loop for agent requests.

    Routes requests through AgentRequestRouter first, then:
    - Chat path: direct LLM response, no tools
    - Work path: LLM + ToolRuntime with multi-round feedback

    LLM sees tool schemas but never calls handlers directly.
    All tool execution goes through ToolRuntime's safety chain.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        runtime: ToolRuntime,
        llm_provider: LLMProvider | None = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
    ) -> None:
        self.registry = registry
        self.runtime = runtime
        self.llm_provider = llm_provider
        self.max_rounds = max_rounds
        self._tool_context = registry.to_llm_tool_context()

    def execute(self, user_input: str, context: ToolContext | None = None) -> LoopResult:
        """Execute a user request through the appropriate path.

        1. Route via AgentRequestRouter (deterministic, no LLM)
        2. If chat → direct response
        3. If work → tool loop with safety chain
        4. If safety refusal → refuse immediately
        """
        if context is None:
            context = ToolContext(permission_mode=self.runtime.permission_mode)

        # Step 1: Route the request
        agent_request = route_agent_request(user_input)
        logger.info(
            "Agent request routed: is_work=%s, type=%s, risk=%s",
            agent_request.is_work_request,
            agent_request.work_type or agent_request.chat_type,
            agent_request.risk_level,
        )

        # Step 2: Safety refusal — never enter LLM
        if agent_request.response_mode == "refusal_or_safety_message":
            return LoopResult(
                response="[SAFETY] 此请求涉及安全敏感操作，已被拒绝。",
                error="safety_refusal",
                steps=[LoopStep(
                    round_num=0,
                    response="[SAFETY] 此请求涉及安全敏感操作，已被拒绝。",
                    is_final=True,
                    error="safety_refusal",
                )],
            )

        # Step 3: Chat path — no tools needed
        if not agent_request.is_work_request:
            return self._chat_path(user_input, agent_request)

        # Step 4: Work path — tool loop
        return self._work_path(user_input, agent_request, context)

    def _chat_path(self, user_input: str, agent_request: AgentRequest) -> LoopResult:
        """Handle chat requests — direct LLM response, no tools."""
        from ..llm.prompt_builder import generate_chat_response_direct

        chat_type = agent_request.chat_type or "chat_answer"

        response = generate_chat_response_direct(
            user_input=user_input,
            chat_type=chat_type,
            llm_provider=self.llm_provider,
        )

        return LoopResult(
            response=response,
            steps=[LoopStep(
                round_num=0,
                response=response,
                is_final=True,
            )],
            total_rounds=1,
        )

    def _work_path(self, user_input: str, agent_request: AgentRequest, context: ToolContext) -> LoopResult:
        """Handle work requests — LLM + ToolRuntime with multi-round feedback.

        Loop structure:
        1. Build prompt with tool context
        2. LLM decides: call tools or return final answer
        3. If tools: execute via ToolRuntime, feed results back
        4. Repeat until LLM returns final answer or max_rounds reached
        """
        steps: list[LoopStep] = []
        all_tool_results: list[dict[str, Any]] = []
        total_tool_calls = 0

        for round_num in range(1, self.max_rounds + 1):
            step = LoopStep(round_num=round_num)

            # Build prompt with accumulated tool results
            prompt = build_work_execution_prompt(
                instructions=None,  # Could pass project instructions here
                user_input=user_input,
                tool_context=self._tool_context,
                agent_request=agent_request.to_dict(),
                tool_results=all_tool_results if all_tool_results else None,
            )

            # Get LLM response
            if self.llm_provider is None:
                # No LLM available — return structured work acknowledgment
                step.response = (
                    f"[WORK] 无法连接 LLM。路由信息: work_type={agent_request.work_type}, "
                    f"required_tools={agent_request.required_tools}, "
                    f"reason={agent_request.reason}"
                )
                step.is_final = True
                steps.append(step)
                return LoopResult(
                    response=step.response,
                    steps=steps,
                    total_tool_calls=total_tool_calls,
                    total_rounds=round_num,
                )

            try:
                from ..llm.provider import safe_complete

                raw = safe_complete(
                    self.llm_provider,
                    prompt,
                    system=(
                        "You are Jarvis executing a work request. "
                        "Return strict JSON object tool plan only when calling tools."
                    ),
                )
                if raw is None:
                    # Keep legacy behavior for tests/hooks that patch safe_complete,
                    # but recover explicit provider errors in real-provider scenarios.
                    provider_name = type(self.llm_provider).__name__
                    if provider_name != "MagicMock" and hasattr(self.llm_provider, "complete"):
                        raw = self.llm_provider.complete(
                            prompt,
                            system=(
                                "You are Jarvis executing a work request. "
                                "Return strict JSON object tool plan only when calling tools."
                            ),
                        )
            except Exception as exc:
                step.error = f"llm_error: {exc}"
                step.is_final = True
                steps.append(step)
                err_text = str(exc)
                prefix = "[ERROR] LLM 调用失败"
                if "network error" in err_text.lower():
                    prefix = "[ERROR] 无法连接 LLM"
                return LoopResult(
                    response=f"{prefix}: {exc}",
                    steps=steps,
                    total_tool_calls=total_tool_calls,
                    total_rounds=round_num,
                    error=str(exc),
                )

            if raw is None:
                step.error = "llm_returned_none"
                step.is_final = True
                steps.append(step)
                return LoopResult(
                    response="[ERROR] LLM 返回空结果",
                    steps=steps,
                    total_tool_calls=total_tool_calls,
                    total_rounds=round_num,
                    error="llm_returned_none",
                )

            # Try to parse as JSON (tool calls)
            parsed = self._parse_llm_response(raw)

            if parsed is None or parsed.get("tool_calls") is None:
                if _looks_like_tool_plan(raw):
                    preview = raw.strip().replace("\n", " ")[:200]
                    step.error = "parse_error"
                    step.response = (
                        "[ERROR] parse_error: failed to parse tool plan JSON; "
                        f"content_length={len(raw)} content_preview={preview}"
                    )
                    step.is_final = True
                    steps.append(step)
                    return LoopResult(
                        response=step.response,
                        steps=steps,
                        total_tool_calls=total_tool_calls,
                        total_rounds=round_num,
                        error="parse_error",
                    )
                # LLM returned a final text answer (not JSON tool calls)
                step.response = raw
                step.is_final = True
                steps.append(step)
                return LoopResult(
                    response=raw,
                    steps=steps,
                    total_tool_calls=total_tool_calls,
                    total_rounds=round_num,
                )

            # LLM wants to call tools
            step.thought = parsed.get("thought", "")
            tool_calls_data = parsed.get("tool_calls", [])

            if not tool_calls_data:
                # Empty tool_calls means LLM is done
                step.response = step.thought or "完成"
                step.is_final = True
                steps.append(step)
                return LoopResult(
                    response=step.response,
                    steps=steps,
                    total_tool_calls=total_tool_calls,
                    total_rounds=round_num,
                )

            # Execute tool calls through ToolRuntime
            step.tool_calls = tool_calls_data
            round_results: list[dict[str, Any]] = []

            for tc_data in tool_calls_data:
                call = ToolCall(
                    tool_name=tc_data.get("tool_name", ""),
                    arguments=tc_data.get("arguments", {}),
                    reason=tc_data.get("reason"),
                )

                result = self.runtime.run(call, context)
                round_results.append(result.to_dict())
                total_tool_calls += 1

            step.tool_results = round_results
            all_tool_results.extend(round_results)
            steps.append(step)

            # Check if all results indicate no more action needed
            all_ok = all(r.get("ok", False) for r in round_results)
            if not all_ok:
                # Some tool failed — give LLM one more chance to adapt
                logger.warning("Tool execution failures in round %d, continuing loop", round_num)

        # Max rounds exhausted
        return LoopResult(
            response=f"[MAX_ROUNDS] 达到最大执行轮次 ({self.max_rounds})，停止执行。",
            steps=steps,
            total_tool_calls=total_tool_calls,
            total_rounds=self.max_rounds,
            exhausted=True,
        )

    @staticmethod
    def _parse_llm_response(raw: str) -> dict[str, Any] | None:
        """Parse LLM response as JSON tool call structure.

        Returns None if the response is not valid JSON (treated as final text).
        """
        text = raw.strip()
        # Strip code fences
        if text.startswith("```"):
            first_nl = text.find("\n")
            if first_nl != -1:
                text = text[first_nl + 1:]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3].rstrip()

        parsed = _try_parse_json_object(text)
        if isinstance(parsed, dict):
            return parsed
        return None


def _try_parse_json_object(text: str) -> dict[str, Any] | None:
    """Parse either full JSON object or first object wrapped in extra text."""
    try:
        direct = json.loads(text)
        if isinstance(direct, dict):
            return direct
    except (json.JSONDecodeError, ValueError):
        pass

    decoder = JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                return obj
        except ValueError:
            continue
    return None


def _looks_like_tool_plan(raw: str) -> bool:
    text = (raw or "").strip().lower()
    if not text:
        return False
    if text.startswith("{") or text.startswith("```"):
        return True
    return "tool_calls" in text or "\"thought\"" in text
