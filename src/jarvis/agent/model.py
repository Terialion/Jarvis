"""Model adapters for AgentLoop."""

from __future__ import annotations

import json
from json import JSONDecoder
from typing import Any, Protocol

from ..core.llm.config import load_llm_config
from ..core.llm.runtime_provider import LLMProviderConfig, OpenAICompatibleProvider, build_runtime_llm_provider
from .types import ModelResponse, ToolCall, ToolSpec

_CHAT_COMPLETIONS_SYSTEM_PROMPT = (
    "You are Jarvis AgentLoop operating in workspace tool mode.\n"
    "When the user asks to list directories, read files, run tests, run commands, or edit files, "
    "you MUST call tools instead of answering from assumption.\n"
    "Only produce final answer after tool observations confirm results.\n"
    "Do not output tool_plan JSON.\n"
    "Use provided function tools only. Never invent tool names.\n"
    "Never claim a command/file read/edit happened unless tool results show it.\n"
    "For secrets (.env, API keys, tokens), refuse and do not expose sensitive values."
)


class ModelClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        stream: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ModelResponse: ...


class FakeModelClient:
    """Offline deterministic model for tests and benchmark v0.1."""

    def __init__(self, scripted: list[ModelResponse] | None = None) -> None:
        self.scripted = list(scripted or [])

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        stream: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ModelResponse:
        _ = tools, stream, metadata
        if self.scripted:
            return self.scripted.pop(0)

        text = self._latest_user_text(messages).lower()
        has_observation = any(str(row.get("role")) == "tool" for row in messages)
        if has_observation:
            if "delete entire project" in text or "删除整个项目目录" in text:
                answer = "不能执行该删除请求。这是危险操作，需要安全审批并限定范围。"
                return ModelResponse(assistant_text=answer, final_answer=answer, finish_reason="stop")
            answer = "Done. I inspected the observation and completed the requested step."
            return ModelResponse(assistant_text=answer, final_answer=answer, finish_reason="stop")

        if any(k in text for k in ("list current directory", "列一下当前目录", "当前目录", "directory")):
            return ModelResponse(
                reasoning_summary="Need directory listing first.",
                tool_calls=[
                    ToolCall.new(
                        name="repo_reader.search_files",
                        arguments={"repo_path": ".", "pattern": "README", "max_results": 20},
                    )
                ],
                finish_reason="tool_calls",
            )
        if any(k in text for k in ("readme", "读取", "read file", "summarize", "mocked pages")):
            return ModelResponse(
                reasoning_summary="Need read file content.",
                tool_calls=[ToolCall.new(name="repo_reader.read_file", arguments={"path": "README.md"})],
                finish_reason="tool_calls",
            )
        if any(k in text for k in ("run pytest", "运行 pytest", "run tests", "fix bug", "scoped tests")):
            return ModelResponse(
                reasoning_summary="Need scoped tests.",
                tool_calls=[ToolCall.new(name="test_runner.run_test", arguments={"command": "python -m pytest -q"})],
                finish_reason="tool_calls",
            )
        if any(k in text for k in ("run command", "inspect files", "shell", "stderr")):
            return ModelResponse(
                reasoning_summary="Need a shell command for inspection.",
                tool_calls=[
                    ToolCall.new(
                        name="command_runner.run",
                        arguments={"command": "python -V", "cwd": ".", "timeout_s": 20},
                    )
                ],
                finish_reason="tool_calls",
            )
        if any(k in text for k in ("删除整个项目目录", "delete entire project")):
            return ModelResponse(
                reasoning_summary="Need safe non-destructive check first.",
                tool_calls=[
                    ToolCall.new(
                        name="repo_reader.search_files",
                        arguments={"repo_path": ".", "pattern": "README", "max_results": 5},
                    )
                ],
                finish_reason="tool_calls",
            )
        answer = "I can help with analysis, planning, and tool-assisted execution when needed."
        return ModelResponse(assistant_text=answer, final_answer=answer, finish_reason="stop")

    @staticmethod
    def _latest_user_text(messages: list[dict[str, Any]]) -> str:
        for row in reversed(messages):
            if str(row.get("role")) == "user":
                return str(row.get("content") or "")
        return ""


class RuntimeModelClient:
    """Runtime provider adapter preserving current provider behavior."""

    def __init__(self, provider: Any | None = None) -> None:
        self.config = load_llm_config()
        provider_cfg = LLMProviderConfig.from_llm_config(self.config)
        self.provider = provider if provider is not None else build_runtime_llm_provider(provider_cfg)

    def backend_info(self) -> dict[str, str]:
        if self.provider is None:
            return {
                "model_backend": "fake",
                "model_provider": "fake",
                "model_name": "fake-agent-v0",
                "api_key_source": "missing",
            }
        return {
            "model_backend": "real",
            "model_provider": self.config.provider or "unknown",
            "model_name": self.config.model or "unknown",
            "api_key_source": self.config.api_key_source or "missing",
        }

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        stream: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ModelResponse:
        _ = stream, metadata
        if self.provider is None:
            return FakeModelClient().complete(messages, tools=tools, stream=stream, metadata=metadata)

        if isinstance(self.provider, OpenAICompatibleProvider):
            safe_tools, safe_to_canonical = self._build_openai_tool_schema(tools or [])
            data = self.provider.chat_completion(
                messages=self._prepare_messages(messages),
                tools=safe_tools,
                system=_CHAT_COMPLETIONS_SYSTEM_PROMPT,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            return self._parse_chat_completion_response(data, safe_to_canonical=safe_to_canonical)

        # Fallback for provider implementations that only support plain completion.
        prompt = self._build_prompt(messages, tools or [])
        raw = self.provider.complete(prompt, system=_CHAT_COMPLETIONS_SYSTEM_PROMPT)
        return self._parse_response_text(raw)

    @staticmethod
    def _prepare_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prepared: list[dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role") or "")
            content = msg.get("content")
            if role not in {"system", "user", "assistant", "tool"}:
                continue
            if role == "tool":
                # OpenAI tool role expects tool_call_id; we keep observation as assistant text instead.
                prepared.append({"role": "assistant", "content": f"Observation: {content}"})
                continue
            prepared.append({"role": role, "content": str(content or "")})
        return prepared

    @staticmethod
    def _build_openai_tool_schema(
        tools: list[ToolSpec],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        safe_to_canonical: dict[str, str] = {}
        schema: list[dict[str, Any]] = []
        for spec in tools:
            canonical = str(spec.name or "").strip()
            if not canonical:
                continue
            safe_name = canonical.replace(".", "_")
            safe_to_canonical[safe_name] = canonical
            parameters = spec.input_schema if isinstance(spec.input_schema, dict) else {}
            if not parameters:
                parameters = {"type": "object", "properties": {}, "required": []}
            if str(parameters.get("type") or "") != "object":
                parameters = {"type": "object", "properties": {}, "required": []}
            if "properties" not in parameters or not isinstance(parameters.get("properties"), dict):
                parameters["properties"] = {}
            if "required" not in parameters or not isinstance(parameters.get("required"), list):
                parameters["required"] = []
            schema.append(
                {
                    "type": "function",
                    "function": {
                        "name": safe_name,
                        "description": str(spec.description or canonical),
                        "parameters": parameters,
                    },
                }
            )
        return schema, safe_to_canonical

    @staticmethod
    def _parse_chat_completion_response(
        data: dict[str, Any],
        *,
        safe_to_canonical: dict[str, str],
    ) -> ModelResponse:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return ModelResponse(final_answer="", assistant_text="", finish_reason="empty", raw={"debug": {"choices": 0}})

        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        finish_reason = str(first.get("finish_reason") or "stop")
        content_text = str(message.get("content") or "")
        tool_calls = message.get("tool_calls")
        debug = {
            "response_json_keys": sorted(list(data.keys())),
            "choices_count": len(choices),
            "choice0_keys": sorted(list(first.keys())) if isinstance(first, dict) else [],
            "message_keys": sorted(list(message.keys())),
            "content_length": len(content_text),
            "content_preview": content_text[:200],
            "finish_reason": finish_reason,
            "tool_calls_present": isinstance(tool_calls, list) and len(tool_calls) > 0,
            "tool_calls_count": len(tool_calls) if isinstance(tool_calls, list) else 0,
        }

        parsed_calls = RuntimeModelClient._parse_native_tool_calls(tool_calls, safe_to_canonical)
        if parsed_calls:
            return ModelResponse(
                reasoning_summary="Tool call planned by model.",
                tool_calls=parsed_calls,
                finish_reason="tool_calls",
                raw={"debug": debug},
            )

        parsed_from_content = RuntimeModelClient._parse_tool_plan_from_content(content_text, safe_to_canonical=safe_to_canonical)
        if parsed_from_content.tool_calls:
            parsed_from_content.raw = {"debug": debug}
            return parsed_from_content

        if content_text.strip():
            if RuntimeModelClient._looks_like_tool_intent_text(content_text):
                return ModelResponse(
                    assistant_text="",
                    final_answer="",
                    finish_reason="retry_with_tool_instruction",
                    raw={"debug": debug, "retry_reason": "natural_language_tool_intent"},
                )
            return ModelResponse(
                assistant_text=content_text,
                final_answer=content_text,
                finish_reason=finish_reason or "stop",
                raw={"debug": debug},
            )
        return ModelResponse(assistant_text="", final_answer="", finish_reason=finish_reason or "empty", raw={"debug": debug})

    @staticmethod
    def _parse_native_tool_calls(tool_calls: Any, safe_to_canonical: dict[str, str]) -> list[ToolCall]:
        out: list[ToolCall] = []
        if not isinstance(tool_calls, list):
            return out
        for item in tool_calls:
            if not isinstance(item, dict):
                continue
            fn = item.get("function") if isinstance(item.get("function"), dict) else {}
            name = str(fn.get("name") or "").strip()
            if not name:
                continue
            canonical_name = safe_to_canonical.get(name, name)
            raw_args = fn.get("arguments")
            args: dict[str, Any] = {}
            if isinstance(raw_args, dict):
                args = raw_args
            elif isinstance(raw_args, str):
                try:
                    parsed = json.loads(raw_args)
                    if isinstance(parsed, dict):
                        args = parsed
                except json.JSONDecodeError:
                    args = {}
            out.append(ToolCall.new(name=canonical_name, arguments=args))
        return out

    @staticmethod
    def _parse_tool_plan_from_content(content_text: str, *, safe_to_canonical: dict[str, str]) -> ModelResponse:
        text = str(content_text or "").strip()
        if not text:
            return ModelResponse(final_answer="", assistant_text="", finish_reason="empty")
        parsed = RuntimeModelClient._parse_first_json_object(RuntimeModelClient._strip_fence(text))
        if not isinstance(parsed, dict):
            return ModelResponse(assistant_text=text, final_answer=text, finish_reason="stop")

        payload = parsed
        if isinstance(payload.get("tool_plan_json"), dict):
            payload = payload["tool_plan_json"]

        tool_calls: list[ToolCall] = []
        for item in list(payload.get("tool_calls") or []):
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool_name") or item.get("name") or "").strip()
            if not tool_name:
                continue
            canonical_name = safe_to_canonical.get(tool_name, tool_name.replace(".", "."))
            args = item.get("arguments")
            if not isinstance(args, dict):
                args = {}
            tool_calls.append(ToolCall.new(name=canonical_name, arguments=args))
        if tool_calls:
            return ModelResponse(
                reasoning_summary=str(payload.get("thought") or ""),
                tool_calls=tool_calls,
                finish_reason="tool_calls",
                raw=parsed,
            )

        answer = str(
            payload.get("final_answer_text")
            or payload.get("final_answer")
            or payload.get("answer")
            or ""
        ).strip()
        if answer:
            return ModelResponse(assistant_text=answer, final_answer=answer, finish_reason="stop", raw=parsed)
        return ModelResponse(assistant_text=text, final_answer=text, finish_reason="stop", raw=parsed)

    @staticmethod
    def _looks_like_tool_intent_text(text: str) -> bool:
        lowered = str(text or "").lower()
        markers = (
            "tool_call",
            "tool plan",
            "tool_plan",
            "run command",
            "list directory",
            "read file",
            "调用工具",
            "调用 command",
            "需要运行",
            "需要读取",
        )
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _build_prompt(messages: list[dict[str, Any]], tools: list[ToolSpec]) -> str:
        prompt_obj = {
            "messages": messages,
            "tools": [tool.to_dict() for tool in tools],
            "output_contract": {
                "single_json_object_only": True,
                "tool_calls_schema": [{"tool_name": "string", "arguments": {}}],
                "final_answer_text": "string",
            },
        }
        return json.dumps(prompt_obj, ensure_ascii=False)

    @staticmethod
    def _parse_response_text(raw: str) -> ModelResponse:
        text = str(raw or "").strip()
        if not text:
            return ModelResponse(final_answer="", assistant_text="", finish_reason="empty")
        return RuntimeModelClient._parse_tool_plan_from_content(text, safe_to_canonical={})

    @staticmethod
    def _strip_fence(text: str) -> str:
        cleaned = text
        if cleaned.startswith("```"):
            first_nl = cleaned.find("\n")
            if first_nl != -1:
                cleaned = cleaned[first_nl + 1 :]
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3].rstrip()
        return cleaned

    @staticmethod
    def _parse_first_json_object(text: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        decoder = JSONDecoder()
        for idx, char in enumerate(text):
            if char != "{":
                continue
            try:
                obj, _end = decoder.raw_decode(text[idx:])
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
        return None

