"""Model adapters for AgentLoop."""

from __future__ import annotations

import json
from json import JSONDecoder
from typing import Any, Iterator, Protocol

from ..core.llm.config import load_llm_config
from ..core.llm.runtime_provider import LLMProviderConfig, OpenAICompatibleProvider, build_runtime_llm_provider
from .types import ModelChunk, ModelResponse, ToolCall, ToolSpec

class ModelClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        stream: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ModelResponse: ...

    def complete_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[ModelChunk]: ...

    def backend_info(self) -> dict[str, str]: ...


class FakeModelClient:
    """Offline deterministic model for tests.

    All intelligence lives in the real LLM.  This class exists solely so
    tests can pre-program responses via ``scripted``.  When no scripted
    responses remain it returns a polite "no LLM configured" message —
    it does **not** attempt to simulate an LLM with keyword matching.
    """

    def __init__(self, scripted: list[ModelResponse] | None = None) -> None:
        self.scripted = list(scripted or [])

    def backend_info(self) -> dict[str, str]:
        return {
            "model_backend": "fake",
            "model_provider": "fake",
            "model_name": "fake-agent-v0",
            "api_key_source": "none",
        }

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

        original_text = self._latest_user_text(messages)
        has_chinese = any("一" <= ch <= "鿿" for ch in original_text)

        no_llm_msg = (
            "没有配置LLM提供商。请设置 JARVIS_LLM_API_KEY 环境变量，或运行 jarvis config 进行配置。"
            if has_chinese
            else "No LLM provider configured. Set the JARVIS_LLM_API_KEY environment variable or run `jarvis config`."
        )
        return ModelResponse(
            assistant_text=no_llm_msg,
            final_answer=no_llm_msg,
            finish_reason="stop",
        )

    def complete_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[ModelChunk]:
        """Simulate streaming by breaking the complete response into chunks."""
        response = self.complete(messages, tools=tools, metadata=metadata)
        if response.reasoning_summary:
            yield ModelChunk(kind="reasoning_delta", reasoning_delta=response.reasoning_summary)
        for call in response.tool_calls:
            yield ModelChunk(
                kind="tool_call_delta",
                tool_call_id=call.id,
                tool_name=call.name,
                tool_arguments_delta=json.dumps(call.arguments, ensure_ascii=False),
            )
        text = response.final_answer or response.assistant_text
        if text:
            words = text.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i : i + 3])
                if i > 0:
                    chunk = " " + chunk
                yield ModelChunk(kind="text_delta", text_delta=chunk)
        yield ModelChunk(kind="done", finish_reason=response.finish_reason or "stop")

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
        self.supports_native_tool_calling = self.config.supports_native_tool_calling

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
            msg = "No LLM provider configured. Set the JARVIS_LLM_API_KEY environment variable or run `jarvis config`."
            return ModelResponse(assistant_text=msg, final_answer=msg, finish_reason="stop")

        if isinstance(self.provider, OpenAICompatibleProvider):
            safe_tools, safe_to_canonical = self._build_openai_tool_schema(tools or [])
            prepared = self._prepare_messages(messages)
            if tools and not self.supports_native_tool_calling:
                prepared = self._inject_tool_descriptions(prepared, tools)
            prepared = self._normalize_messages(prepared)
            data = self.provider.chat_completion(
                messages=prepared,
                tools=safe_tools,
                system=None,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            return self._parse_chat_completion_response(data, safe_to_canonical=safe_to_canonical)

        # Fallback for provider implementations that only support plain completion.
        prompt = self._build_prompt(messages, tools or [])
        content_text, debug = self.provider.raw_completion(prompt=prompt, system=None)
        finish_reason = "stop"
        if isinstance(content_text, dict) and "error" in content_text:
            finish_reason = "provider_error"
            content_text = str(content_text.get("error") or "")

        if content_text.strip():
            if RuntimeModelClient._looks_like_tool_intent_text(content_text):
                # Try to salvage tool calls from natural-language text before retrying
                salvaged = RuntimeModelClient._parse_tool_plan_from_content(content_text, safe_to_canonical={})
                if salvaged.tool_calls:
                    return salvaged
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

    def complete_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[ModelChunk]:
        """Stream model response via SSE, yielding ModelChunk events."""
        _ = metadata
        if self.provider is None:
            msg = "No LLM provider configured. Set the JARVIS_LLM_API_KEY environment variable or run `jarvis config`."
            yield ModelChunk(kind="text_delta", text_delta=msg)
            yield ModelChunk(kind="done", finish_reason="stop")
            return

        if isinstance(self.provider, OpenAICompatibleProvider):
            safe_tools, safe_to_canonical = self._build_openai_tool_schema(tools or [])
            prepared = self._prepare_messages(messages)
            if tools and not self.supports_native_tool_calling:
                prepared = self._inject_tool_descriptions(prepared, tools)
            prepared = self._normalize_messages(prepared)
            chunks = self.provider.chat_completion_stream(
                messages=prepared,
                tools=safe_tools,
                system=None,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
            # Accumulators for streaming deltas
            acc_text: list[str] = []
            acc_reasoning: list[str] = []
            tool_acc: dict[int, dict[str, Any]] = {}  # index -> {id, name, arguments}
            finish_reason = "stop"
            acc_usage: dict | None = None
            for chunk in chunks:
                # Capture usage from trailing chunks (some providers send usage
                # in a final chunk without choices)
                raw_usage = chunk.get("usage")
                if isinstance(raw_usage, dict):
                    acc_usage = dict(raw_usage)
                choices = list(chunk.get("choices") or [])
                if not choices:
                    continue
                delta = dict(choices[0].get("delta") or {})
                chunk_finish = str(choices[0].get("finish_reason") or "")
                if chunk_finish:
                    finish_reason = chunk_finish

                # Text delta
                content = str(delta.get("content") or "")
                if content:
                    acc_text.append(content)
                    # For non-native tool calling, defer text until post-processing
                    # so we can filter JSON/XML artifacts first.
                    if self.supports_native_tool_calling or not tools:
                        yield ModelChunk(kind="text_delta", text_delta=content)

                # Reasoning delta
                reasoning = str(delta.get("reasoning_content") or "")
                if reasoning:
                    acc_reasoning.append(reasoning)
                    if self.supports_native_tool_calling or not tools:
                        yield ModelChunk(kind="reasoning_delta", reasoning_delta=reasoning)

                # Tool call deltas
                tc_deltas = list(delta.get("tool_calls") or [])
                for tc in tc_deltas:
                    idx = int(tc.get("index", 0))
                    if idx not in tool_acc:
                        tool_acc[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc.get("id"):
                        tool_acc[idx]["id"] = str(tc["id"])
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        tool_acc[idx]["name"] = str(fn["name"])
                    if fn.get("arguments"):
                        tool_acc[idx]["arguments"] += str(fn["arguments"])

            # Post-processing: salvage tool calls from non-native providers
            # that output tool_plan_json or <tool_call> XML in text content.
            if tools and not self.supports_native_tool_calling and not tool_acc:
                # Search content text first, then reasoning text (some models
                # output tool_plan_json inside thinking/reasoning blocks).
                for source in (acc_text, acc_reasoning):
                    joined = "".join(source)
                    # Try JSON tool_plan_json format
                    salvaged = self._parse_tool_plan_from_content(
                        joined, safe_to_canonical=safe_to_canonical
                    )
                    if salvaged.tool_calls:
                        for i, call in enumerate(salvaged.tool_calls):
                            tool_acc[len(tool_acc) + i] = {
                                "id": call.id or f"call_salvaged_{i}",
                                "name": call.name,
                                "arguments": json.dumps(call.arguments, ensure_ascii=False),
                            }
                        # Clear the tool-plan JSON from the source we found it in
                        self._filter_artifacts_from_acc(source)
                        break

                    # Try XML <tool_call> format
                    xml_calls = self._parse_xml_tool_calls(joined, safe_to_canonical)
                    if xml_calls:
                        for i, call in enumerate(xml_calls):
                            tool_acc[len(tool_acc) + i] = {
                                "id": call.id or f"call_xml_{i}",
                                "name": call.name,
                                "arguments": json.dumps(call.arguments, ensure_ascii=False),
                            }
                        self._filter_artifacts_from_acc(source)
                        break

            # Yield filtered text for non-native providers that had text suppressed.
            if tools and not self.supports_native_tool_calling:
                remaining = "".join(acc_text).strip()
                if remaining:
                    yield ModelChunk(kind="text_delta", text_delta=remaining)

                # Yield cleaned reasoning (deferred during streaming to avoid
                # leaking raw tool_plan_json fragments to the TUI).
                RuntimeModelClient._filter_artifacts_from_acc(acc_reasoning)
                reasoning_remaining = "".join(acc_reasoning).strip()
                if reasoning_remaining:
                    yield ModelChunk(kind="reasoning_delta", reasoning_delta=reasoning_remaining)

            # Emit accumulated tool calls as individual deltas
            for idx in sorted(tool_acc.keys()):
                entry = tool_acc[idx]
                canonical_name = safe_to_canonical.get(entry["name"], entry["name"])
                yield ModelChunk(
                    kind="tool_call_delta",
                    tool_call_id=entry["id"],
                    tool_name=canonical_name,
                    tool_arguments_delta=entry["arguments"],
                )
            yield ModelChunk(kind="done", finish_reason=finish_reason, usage=acc_usage)
            return

        # Fallback: non-streaming provider — call complete() and emit as chunks
        response = self.complete(messages, tools=tools)
        if response.reasoning_summary:
            yield ModelChunk(kind="reasoning_delta", reasoning_delta=response.reasoning_summary)
        for call in response.tool_calls:
            yield ModelChunk(
                kind="tool_call_delta",
                tool_call_id=call.id,
                tool_name=call.name,
                tool_arguments_delta=json.dumps(call.arguments, ensure_ascii=False),
            )
        text = response.final_answer or response.assistant_text
        if text:
            yield ModelChunk(kind="text_delta", text_delta=text)
        yield ModelChunk(kind="done", finish_reason=response.finish_reason or "stop")

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
            tool_call_id = str(item.get("id") or "") or None
            out.append(ToolCall.new(id=tool_call_id, name=canonical_name, arguments=args))
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
            # English tool-intent phrases — specific action intent, not common tech terms
            "tool_call",
            "tool plan",
            "tool_plan",
            "run command",
            "list directory",
            "read file",
            # Chinese tool-intent phrases — specific action patterns
            "让我尝试用", "让我试试", "让我来调用", "让我来执行", "让我来运行",
            "让我抓取", "让我读取", "让我搜索", "让我检查", "让我查看",
            "让我看一看", "让我看一下",
            "调用工具", "尝试用工具",
            "写入工具返回",
            "重试一次",
            "再试一下",
        )
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _parse_first_json_object(text: str) -> dict[str, Any] | None:
        decoder = JSONDecoder()
        idx = 0
        text = text.lstrip("​")
        while idx < len(text):
            if text[idx] in ("{", "["):
                try:
                    obj, _ = decoder.raw_decode(text, idx)
                    if isinstance(obj, dict):
                        return obj
                    idx = 0
                except json.JSONDecodeError:
                    pass
            idx += 1
        return None

    @staticmethod
    def _strip_fence(text: str) -> str:
        t = text.strip()
        if t.startswith("```"):
            t = t[3:]
        if t.endswith("```"):
            t = t[:-3]
        return t.strip()

    @staticmethod
    def _parse_xml_tool_calls(
        text: str, safe_to_canonical: dict[str, str]
    ) -> list[ToolCall]:
        """Parse ``<tool_call><function=NAME><parameter=KEY>VALUE</parameter></function></tool_call>`` XML."""
        import re

        out: list[ToolCall] = []
        # Match each tool_call block
        for m in re.finditer(
            r"<tool_call>\s*<function=([^>]+)>(.*?)</function>\s*</tool_call>",
            text,
            re.DOTALL,
        ):
            func_name = m.group(1).strip()
            body = m.group(2)
            args: dict[str, Any] = {}
            for pm in re.finditer(
                r"<parameter=([^>]+)>\s*(.*?)\s*</parameter>", body, re.DOTALL
            ):
                key = pm.group(1).strip()
                val = pm.group(2).strip()
                # Try parse as JSON, fallback to string
                try:
                    args[key] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    args[key] = val
            if func_name:
                canonical = safe_to_canonical.get(func_name, func_name)
                out.append(ToolCall.new(name=canonical, arguments=args))
        return out

    @staticmethod
    def _filter_artifacts_from_acc(acc_text: list[str]) -> None:
        """Remove tool_plan_json JSON blocks and <tool_call> XML from accumulated text.

        Joins all fragments, cleans with brace-counting (handles arbitrary
        nesting), then replaces acc_text with the cleaned text.
        """
        import re

        joined = "".join(acc_text)

        # Brace-counting: find {"tool_plan_json":{...}} with arbitrary nesting
        needle = '"tool_plan_json"'
        while True:
            idx = joined.find(needle)
            if idx == -1:
                break
            brace_start = -1
            for i in range(idx, -1, -1):
                if joined[i] == "{":
                    brace_start = i
                    break
            if brace_start == -1:
                break
            depth = 0
            pos = brace_start
            while pos < len(joined):
                if joined[pos] == "{":
                    depth += 1
                elif joined[pos] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                pos += 1
            joined = joined[:brace_start] + joined[pos + 1:]

        # Remove ```json ... ``` code fences
        joined = re.sub(r"```json\s*[\s\S]*?```", "", joined, flags=re.DOTALL)

        # Remove <tool_call> XML
        joined = re.sub(
            r"<tool_call>\s*<function=[^>]+>.*?</function>\s*</tool_call>",
            "",
            joined,
            flags=re.DOTALL,
        )

        acc_text.clear()
        if joined.strip():
            acc_text.append(joined)

    def _prepare_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [_redact_sensitive_message(m) for m in messages]

    def _normalize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply model-specific message normalization before sending to provider."""
        from .message_normalizer import normalize_messages

        return normalize_messages(
            messages,
            provider=self.config.provider or "",
            model=self.config.model or "",
        )

    def _build_prompt(self, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> str:
        from .prompt_builder import PromptBuilder
        from .types import TurnContext

        pb = PromptBuilder()
        ctx = TurnContext(
            user_input="",
            cwd=".",
            model_provider=self.config.provider,
            model_name=self.config.model,
        )
        built = pb.build_messages(ctx)
        return "\n".join(
            str(m.get("content") or "") for m in built if isinstance(m, dict) and m.get("content")
        )

    def _build_openai_tool_schema(self, tools: list[ToolSpec]) -> tuple[list[dict[str, Any]], dict[str, str]]:
        safe_schema: list[dict[str, Any]] = []
        safe_to_canonical: dict[str, str] = {}
        for tool in tools:
            safe_name = tool.name.replace(".", "_").replace("-", "_")
            safe_to_canonical[safe_name] = tool.name
            safe_schema.append(
                {
                    "type": "function",
                    "function": {
                        "name": safe_name,
                        "description": tool.description,
                        "parameters": {
                            "type": "object",
                            "properties": tool.input_schema.get("properties", {}),
                            "required": tool.input_schema.get("required", []),
                        },
                    },
                }
            )
        return safe_schema, safe_to_canonical

    @staticmethod
    def _inject_tool_descriptions(
        messages: list[dict[str, Any]], tools: list[ToolSpec]
    ) -> list[dict[str, Any]]:
        """Inject tool schemas as text in the system prompt for models without native tool calling."""
        tool_entries: list[str] = []
        for tool in tools:
            safe_name = tool.name.replace(".", "_").replace("-", "_")
            params = tool.input_schema.get("properties", {})
            required = tool.input_schema.get("required", [])
            entry = f"- {safe_name}: {tool.description}"
            if params:
                param_desc = ", ".join(
                    f"{k}: {v.get('description', v.get('type', 'string'))}"
                    for k, v in sorted(params.items())
                )
                entry += f"\n  Parameters: {param_desc}"
            if required:
                entry += f"\n  Required: {', '.join(required)}"
            tool_entries.append(entry)

        tool_text = (
            "\n## Available tools\n"
            "You have the following tools available. To use a tool, output JSON in this format:\n"
            "```json\n"
            '{"tool_plan_json": {"thought": "<reasoning>", "tool_calls": ['
            '{"tool_name": "<name>", "arguments": {<args>}}]}}\n'
            "```\n\n"
            + "\n".join(tool_entries)
        )

        out: list[dict[str, Any]] = []
        injected = False
        for m in messages:
            if m.get("role") == "system" and not injected:
                content = str(m.get("content") or "")
                out.append({**m, "content": content + tool_text})
                injected = True
            else:
                out.append(m)
        if not injected:
            out.insert(0, {"role": "system", "content": tool_text})
        return out

    def _parse_chat_completion_response(
        self, data: dict[str, Any], *, safe_to_canonical: dict[str, str]
    ) -> ModelResponse:
        choices = list(data.get("choices") or [])
        if not choices:
            return ModelResponse(final_answer="", assistant_text="", finish_reason="empty")

        choice = choices[0]
        message = dict(choice.get("message") or {})
        content_text = str(message.get("content") or "")
        reasoning_text = str(message.get("reasoning_content") or "")
        raw_finish = str(choice.get("finish_reason") or "")
        finish_reason = raw_finish if raw_finish in ("stop", "length", "tool_calls") else "stop"

        tool_calls = self._parse_native_tool_calls(
            message.get("tool_calls"), safe_to_canonical=safe_to_canonical
        )
        if tool_calls:
            return ModelResponse(
                reasoning_summary=content_text,
                tool_calls=tool_calls,
                finish_reason="tool_calls",
                raw=data,
            )

        # Some models put tool_plan_json in reasoning_content; check both.
        for source_text in (content_text, reasoning_text):
            if not source_text or not source_text.strip():
                continue
            if self._looks_like_tool_intent_text(source_text) or "tool_plan_json" in source_text:
                salvaged = self._parse_tool_plan_from_content(source_text, safe_to_canonical=safe_to_canonical)
                if salvaged.tool_calls:
                    return salvaged
            if source_text is content_text and self._looks_like_tool_intent_text(source_text):
                return ModelResponse(
                    assistant_text="",
                    final_answer="",
                    finish_reason="retry_with_tool_instruction",
                    raw={"retry_reason": "natural_language_tool_intent"},
                )

        if content_text.strip():
            return ModelResponse(
                assistant_text=content_text,
                final_answer=content_text,
                finish_reason=finish_reason,
                raw=data,
            )

        return self._parse_tool_plan_from_content(content_text, safe_to_canonical=safe_to_canonical)


def _redact_sensitive_message(message: dict[str, Any]) -> dict[str, Any]:
    from .types import redact_secret_text

    role = str(message.get("role") or "")
    content = str(message.get("content") or "")
    if role in ("user", "system"):
        content = redact_secret_text(content)
    return {**message, "role": role, "content": content}
