# Hermes 关键参考代码摘录

### ContextEngine 压缩接口

Source: `hermes-agent/hermes-agent-main/agent/context_engine.py` lines 1-120

```
0001: """Abstract base class for pluggable context engines.
0002: 
0003: A context engine controls how conversation context is managed when
0004: approaching the model's token limit. The built-in ContextCompressor
0005: is the default implementation. Third-party engines (e.g. LCM) can
0006: replace it via the plugin system or by being placed in the
0007: ``plugins/context_engine/<name>/`` directory.
0008: 
0009: Selection is config-driven: ``context.engine`` in config.yaml.
0010: Default is ``"compressor"`` (the built-in). Only one engine is active.
0011: 
0012: The engine is responsible for:
0013:   - Deciding when compaction should fire
0014:   - Performing compaction (summarization, DAG construction, etc.)
0015:   - Optionally exposing tools the agent can call (e.g. lcm_grep)
0016:   - Tracking token usage from API responses
0017: 
0018: Lifecycle:
0019:   1. Engine is instantiated and registered (plugin register() or default)
0020:   2. on_session_start() called when a conversation begins
0021:   3. update_from_response() called after each API response with usage data
0022:   4. should_compress() checked after each turn
0023:   5. compress() called when should_compress() returns True
0024:   6. on_session_end() called at real session boundaries (CLI exit, /reset,
0025:      gateway session expiry) — NOT per-turn
0026: """
0027: 
0028: from abc import ABC, abstractmethod
0029: from typing import Any, Dict, List
0030: 
0031: 
0032: class ContextEngine(ABC):
0033:     """Base class all context engines must implement."""
0034: 
0035:     # -- Identity ----------------------------------------------------------
0036: 
0037:     @property
0038:     @abstractmethod
0039:     def name(self) -> str:
0040:         """Short identifier (e.g. 'compressor', 'lcm')."""
0041: 
0042:     # -- Token state (read by run_agent.py for display/logging) ------------
0043:     #
0044:     # Engines MUST maintain these. run_agent.py reads them directly.
0045: 
0046:     last_prompt_tokens: int = 0
0047:     last_completion_tokens: int = 0
0048:     last_total_tokens: int = 0
0049:     threshold_tokens: int = 0
0050:     context_length: int = 0
0051:     compression_count: int = 0
0052: 
0053:     # -- Compaction parameters (read by run_agent.py for preflight) --------
0054:     #
0055:     # These control the preflight compression check.  Subclasses may
0056:     # override via __init__ or property; defaults are sensible for most
0057:     # engines.
0058: 
0059:     threshold_percent: float = 0.75
0060:     protect_first_n: int = 3
0061:     protect_last_n: int = 6
0062: 
0063:     # -- Core interface ----------------------------------------------------
0064: 
0065:     @abstractmethod
0066:     def update_from_response(self, usage: Dict[str, Any]) -> None:
0067:         """Update tracked token usage from an API response.
0068: 
0069:         Called after every LLM call with the usage dict from the response.
0070:         """
0071: 
0072:     @abstractmethod
0073:     def should_compress(self, prompt_tokens: int = None) -> bool:
0074:         """Return True if compaction should fire this turn."""
0075: 
0076:     @abstractmethod
0077:     def compress(
0078:         self,
0079:         messages: List[Dict[str, Any]],
0080:         current_tokens: int = None,
0081:         focus_topic: str = None,
0082:     ) -> List[Dict[str, Any]]:
0083:         """Compact the message list and return the new message list.
0084: 
0085:         This is the main entry point. The engine receives the full message
0086:         list and returns a (possibly shorter) list that fits within the
0087:         context budget. The implementation is free to summarize, build a
0088:         DAG, or do anything else — as long as the returned list is a valid
0089:         OpenAI-format message sequence.
0090: 
0091:         Args:
0092:             focus_topic: Optional topic string from manual ``/compress <focus>``.
0093:                 Engines that support guided compression should prioritise
0094:                 preserving information related to this topic.  Engines that
0095:                 don't support it may simply ignore this argument.
0096:         """
0097: 
0098:     # -- Optional: pre-flight check ----------------------------------------
0099: 
0100:     def should_compress_preflight(self, messages: List[Dict[str, Any]]) -> bool:
0101:         """Quick rough check before the API call (no real token count yet).
0102: 
0103:         Default returns False (skip pre-flight). Override if your engine
0104:         can do a cheap estimate.
0105:         """
0106:         return False
0107: 
0108:     # -- Optional: manual /compress preflight ------------------------------
0109: 
0110:     def has_content_to_compress(self, messages: List[Dict[str, Any]]) -> bool:
0111:         """Quick check: is there anything in ``messages`` that can be compacted?
0112: 
0113:         Used by the gateway ``/compress`` command as a preflight guard —
0114:         returning False lets the gateway report "nothing to compress yet"
0115:         without making an LLM call.
0116: 
0117:         Default returns True (always attempt).  Engines with a cheap way
0118:         to introspect their own head/tail boundaries should override this
0119:         to return False when the transcript is still entirely protected.
0120:         """
```
### ContextCompressor 设计目标与摘要提示

Source: `hermes-agent/hermes-agent-main/agent/context_compressor.py` lines 1-90

```
0001: """Automatic context window compression for long conversations.
0002: 
0003: Self-contained class with its own OpenAI client for summarization.
0004: Uses auxiliary model (cheap/fast) to summarize middle turns while
0005: protecting head and tail context.
0006: 
0007: Improvements over v2:
0008:   - Structured summary template with Resolved/Pending question tracking
0009:   - Summarizer preamble: "Do not respond to any questions" (from OpenCode)
0010:   - Handoff framing: "different assistant" (from Codex) to create separation
0011:   - "Remaining Work" replaces "Next Steps" to avoid reading as active instructions
0012:   - Clear separator when summary merges into tail message
0013:   - Iterative summary updates (preserves info across multiple compactions)
0014:   - Token-budget tail protection instead of fixed message count
0015:   - Tool output pruning before LLM summarization (cheap pre-pass)
0016:   - Scaled summary budget (proportional to compressed content)
0017:   - Richer tool call/result detail in summarizer input
0018: """
0019: 
0020: import hashlib
0021: import json
0022: import logging
0023: import re
0024: import time
0025: from typing import Any, Dict, List, Optional
0026: 
0027: from agent.auxiliary_client import call_llm
0028: from agent.context_engine import ContextEngine
0029: from agent.model_metadata import (
0030:     MINIMUM_CONTEXT_LENGTH,
0031:     get_model_context_length,
0032:     estimate_messages_tokens_rough,
0033: )
0034: from agent.redact import redact_sensitive_text
0035: 
0036: logger = logging.getLogger(__name__)
0037: 
0038: SUMMARY_PREFIX = (
0039:     "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted "
0040:     "into the summary below. This is a handoff from a previous context "
0041:     "window — treat it as background reference, NOT as active instructions. "
0042:     "Do NOT answer questions or fulfill requests mentioned in this summary; "
0043:     "they were already addressed. "
0044:     "Your current task is identified in the '## Active Task' section of the "
0045:     "summary — resume exactly from there. "
0046:     "Respond ONLY to the latest user message "
0047:     "that appears AFTER this summary. The current session state (files, "
0048:     "config, etc.) may reflect work described here — avoid repeating it:"
0049: )
0050: LEGACY_SUMMARY_PREFIX = "[CONTEXT SUMMARY]:"
0051: 
0052: # Minimum tokens for the summary output
0053: _MIN_SUMMARY_TOKENS = 2000
0054: # Proportion of compressed content to allocate for summary
0055: _SUMMARY_RATIO = 0.20
0056: # Absolute ceiling for summary tokens (even on very large context windows)
0057: _SUMMARY_TOKENS_CEILING = 12_000
0058: 
0059: # Placeholder used when pruning old tool results
0060: _PRUNED_TOOL_PLACEHOLDER = "[Old tool output cleared to save context space]"
0061: 
0062: # Chars per token rough estimate
0063: _CHARS_PER_TOKEN = 4
0064: # Flat token cost per attached image part.  Real cost varies by provider and
0065: # dimensions (Anthropic ≈ width×height/750, GPT-4o up to ~1700 for
0066: # high-detail 2048×2048, Gemini 258/tile), but 1600 is a realistic ceiling
0067: # that keeps compression budgeting honest for multi-image conversations.
0068: # Matches Claude Code's IMAGE_TOKEN_ESTIMATE constant.
0069: _IMAGE_TOKEN_ESTIMATE = 1600
0070: # Same figure expressed in the char-budget currency the rest of the
0071: # compressor speaks in.  Used when accumulating message "content length"
0072: # for tail-cut decisions.
0073: _IMAGE_CHAR_EQUIVALENT = _IMAGE_TOKEN_ESTIMATE * _CHARS_PER_TOKEN
0074: _SUMMARY_FAILURE_COOLDOWN_SECONDS = 600
0075: 
0076: 
0077: def _content_length_for_budget(raw_content: Any) -> int:
0078:     """Return the effective char-length of a message's content for token budgeting.
0079: 
0080:     Plain strings: ``len(content)``. Multimodal lists: sum of text-part
0081:     ``len(text)`` plus a flat ``_IMAGE_CHAR_EQUIVALENT`` per image part
0082:     (``image_url`` / ``input_image`` / Anthropic-style ``image``). This
0083:     keeps the compressor from treating a turn with 5 attached images as
0084:     near-zero tokens just because the text part is empty.
0085:     """
0086:     if isinstance(raw_content, str):
0087:         return len(raw_content)
0088:     if not isinstance(raw_content, list):
0089:         return len(str(raw_content or ""))
0090: 
```
### ErrorClassifier 恢复动作语义

Source: `hermes-agent/hermes-agent-main/agent/error_classifier.py` lines 1-95

```
0001: """API error classification for smart failover and recovery.
0002: 
0003: Provides a structured taxonomy of API errors and a priority-ordered
0004: classification pipeline that determines the correct recovery action
0005: (retry, rotate credential, fallback to another provider, compress
0006: context, or abort).
0007: 
0008: Replaces scattered inline string-matching with a centralized classifier
0009: that the main retry loop in run_agent.py consults for every API failure.
0010: """
0011: 
0012: from __future__ import annotations
0013: 
0014: import enum
0015: import logging
0016: from dataclasses import dataclass, field
0017: from typing import Any, Dict, Optional
0018: 
0019: logger = logging.getLogger(__name__)
0020: 
0021: 
0022: # ── Error taxonomy ──────────────────────────────────────────────────────
0023: 
0024: class FailoverReason(enum.Enum):
0025:     """Why an API call failed — determines recovery strategy."""
0026: 
0027:     # Authentication / authorization
0028:     auth = "auth"                        # Transient auth (401/403) — refresh/rotate
0029:     auth_permanent = "auth_permanent"    # Auth failed after refresh — abort
0030: 
0031:     # Billing / quota
0032:     billing = "billing"                  # 402 or confirmed credit exhaustion — rotate immediately
0033:     rate_limit = "rate_limit"            # 429 or quota-based throttling — backoff then rotate
0034: 
0035:     # Server-side
0036:     overloaded = "overloaded"            # 503/529 — provider overloaded, backoff
0037:     server_error = "server_error"        # 500/502 — internal server error, retry
0038: 
0039:     # Transport
0040:     timeout = "timeout"                  # Connection/read timeout — rebuild client + retry
0041: 
0042:     # Context / payload
0043:     context_overflow = "context_overflow"  # Context too large — compress, not failover
0044:     payload_too_large = "payload_too_large"  # 413 — compress payload
0045:     image_too_large = "image_too_large"   # Native image part exceeds provider's per-image limit — shrink and retry
0046: 
0047:     # Model
0048:     model_not_found = "model_not_found"  # 404 or invalid model — fallback to different model
0049:     provider_policy_blocked = "provider_policy_blocked"  # Aggregator (e.g. OpenRouter) blocked the only endpoint due to account data/privacy policy
0050: 
0051:     # Request format
0052:     format_error = "format_error"        # 400 bad request — abort or strip + retry
0053: 
0054:     # Provider-specific
0055:     thinking_signature = "thinking_signature"  # Anthropic thinking block sig invalid
0056:     long_context_tier = "long_context_tier"    # Anthropic "extra usage" tier gate
0057:     oauth_long_context_beta_forbidden = "oauth_long_context_beta_forbidden"  # Anthropic OAuth subscription rejects 1M context beta — disable beta and retry
0058: 
0059:     # Catch-all
0060:     unknown = "unknown"                  # Unclassifiable — retry with backoff
0061: 
0062: 
0063: # ── Classification result ───────────────────────────────────────────────
0064: 
0065: @dataclass
0066: class ClassifiedError:
0067:     """Structured classification of an API error with recovery hints."""
0068: 
0069:     reason: FailoverReason
0070:     status_code: Optional[int] = None
0071:     provider: Optional[str] = None
0072:     model: Optional[str] = None
0073:     message: str = ""
0074:     error_context: Dict[str, Any] = field(default_factory=dict)
0075: 
0076:     # Recovery action hints — the retry loop checks these instead of
0077:     # re-classifying the error itself.
0078:     retryable: bool = True
0079:     should_compress: bool = False
0080:     should_rotate_credential: bool = False
0081:     should_fallback: bool = False
0082: 
0083:     @property
0084:     def is_auth(self) -> bool:
0085:         return self.reason in (FailoverReason.auth, FailoverReason.auth_permanent)
0086: 
0087: 
0088: 
0089: # ── Provider-specific patterns ──────────────────────────────────────────
0090: 
0091: # Patterns that indicate billing exhaustion (not transient rate limit)
0092: _BILLING_PATTERNS = [
0093:     "insufficient credits",
0094:     "insufficient_quota",
0095:     "insufficient balance",
```
### 文本 fallback tool_call 约束

Source: `hermes-agent/hermes-agent-main/agent/copilot_acp_client.py` lines 120-165

```
0120:         "You are being used as the active ACP agent backend for Hermes.",
0121:         "Use ACP capabilities to complete tasks.",
0122:         "IMPORTANT: If you take an action with a tool, you MUST output tool calls using <tool_call>{...}</tool_call> blocks with JSON exactly in OpenAI function-call shape.",
0123:         "If no tool is needed, answer normally.",
0124:     ]
0125:     if model:
0126:         sections.append(f"Hermes requested model hint: {model}")
0127: 
0128:     if isinstance(tools, list) and tools:
0129:         tool_specs: list[dict[str, Any]] = []
0130:         for t in tools:
0131:             if not isinstance(t, dict):
0132:                 continue
0133:             fn = t.get("function") or {}
0134:             if not isinstance(fn, dict):
0135:                 continue
0136:             name = fn.get("name")
0137:             if not isinstance(name, str) or not name.strip():
0138:                 continue
0139:             tool_specs.append(
0140:                 {
0141:                     "name": name.strip(),
0142:                     "description": fn.get("description", ""),
0143:                     "parameters": fn.get("parameters", {}),
0144:                 }
0145:             )
0146:         if tool_specs:
0147:             sections.append(
0148:                 "Available tools (OpenAI function schema). "
0149:                 "When using a tool, emit ONLY <tool_call>{...}</tool_call> with one JSON object "
0150:                 "containing id/type/function{name,arguments}. arguments must be a JSON string.\n"
0151:                 + json.dumps(tool_specs, ensure_ascii=False)
0152:             )
0153: 
0154:     if tool_choice is not None:
0155:         sections.append(f"Tool choice hint: {json.dumps(tool_choice, ensure_ascii=False)}")
0156: 
0157:     transcript: list[str] = []
0158:     for message in messages:
0159:         if not isinstance(message, dict):
0160:             continue
0161:         role = str(message.get("role") or "unknown").strip().lower()
0162:         if role == "tool":
0163:             role = "tool"
0164:         elif role not in {"system", "user", "assistant"}:
0165:             role = "context"
```
### 从文本抽取 tool_call

Source: `hermes-agent/hermes-agent-main/agent/copilot_acp_client.py` lines 212-270

```
0212: def _extract_tool_calls_from_text(text: str) -> tuple[list[SimpleNamespace], str]:
0213:     if not isinstance(text, str) or not text.strip():
0214:         return [], ""
0215: 
0216:     extracted: list[SimpleNamespace] = []
0217:     consumed_spans: list[tuple[int, int]] = []
0218: 
0219:     def _try_add_tool_call(raw_json: str) -> None:
0220:         try:
0221:             obj = json.loads(raw_json)
0222:         except Exception:
0223:             return
0224:         if not isinstance(obj, dict):
0225:             return
0226:         fn = obj.get("function")
0227:         if not isinstance(fn, dict):
0228:             return
0229:         fn_name = fn.get("name")
0230:         if not isinstance(fn_name, str) or not fn_name.strip():
0231:             return
0232:         fn_args = fn.get("arguments", "{}")
0233:         if not isinstance(fn_args, str):
0234:             fn_args = json.dumps(fn_args, ensure_ascii=False)
0235:         call_id = obj.get("id")
0236:         if not isinstance(call_id, str) or not call_id.strip():
0237:             call_id = f"acp_call_{len(extracted)+1}"
0238: 
0239:         extracted.append(
0240:             SimpleNamespace(
0241:                 id=call_id,
0242:                 call_id=call_id,
0243:                 response_item_id=None,
0244:                 type="function",
0245:                 function=SimpleNamespace(name=fn_name.strip(), arguments=fn_args),
0246:             )
0247:         )
0248: 
0249:     for m in _TOOL_CALL_BLOCK_RE.finditer(text):
0250:         raw = m.group(1)
0251:         _try_add_tool_call(raw)
0252:         consumed_spans.append((m.start(), m.end()))
0253: 
0254:     # Only try bare-JSON fallback when no XML blocks were found.
0255:     if not extracted:
0256:         for m in _TOOL_CALL_JSON_RE.finditer(text):
0257:             raw = m.group(0)
0258:             _try_add_tool_call(raw)
0259:             consumed_spans.append((m.start(), m.end()))
0260: 
0261:     if not consumed_spans:
0262:         return extracted, text.strip()
0263: 
0264:     consumed_spans.sort()
0265:     merged: list[tuple[int, int]] = []
0266:     for start, end in consumed_spans:
0267:         if not merged or start > merged[-1][1]:
0268:             merged.append((start, end))
0269:         else:
0270:             merged[-1] = (merged[-1][0], max(merged[-1][1], end))
```
### ToolCallStart/Progress 事件构造

Source: `hermes-agent/hermes-agent-main/acp_adapter/tools.py` lines 270-360

```
0270:     tool_call_id: str,
0271:     tool_name: str,
0272:     arguments: Dict[str, Any],
0273: ) -> ToolCallStart:
0274:     """Create a ToolCallStart event for the given hermes tool invocation."""
0275:     kind = get_tool_kind(tool_name)
0276:     title = build_tool_title(tool_name, arguments)
0277:     locations = extract_locations(arguments)
0278: 
0279:     if tool_name == "patch":
0280:         mode = arguments.get("mode", "replace")
0281:         if mode == "replace":
0282:             path = arguments.get("path", "")
0283:             old = arguments.get("old_string", "")
0284:             new = arguments.get("new_string", "")
0285:             content = [acp.tool_diff_content(path=path, new_text=new, old_text=old)]
0286:         else:
0287:             patch_text = arguments.get("patch", "")
0288:             content = _build_patch_mode_content(patch_text)
0289:         return acp.start_tool_call(
0290:             tool_call_id, title, kind=kind, content=content, locations=locations,
0291:             raw_input=arguments,
0292:         )
0293: 
0294:     if tool_name == "write_file":
0295:         path = arguments.get("path", "")
0296:         file_content = arguments.get("content", "")
0297:         content = [acp.tool_diff_content(path=path, new_text=file_content)]
0298:         return acp.start_tool_call(
0299:             tool_call_id, title, kind=kind, content=content, locations=locations,
0300:             raw_input=arguments,
0301:         )
0302: 
0303:     if tool_name == "terminal":
0304:         command = arguments.get("command", "")
0305:         content = [acp.tool_content(acp.text_block(f"$ {command}"))]
0306:         return acp.start_tool_call(
0307:             tool_call_id, title, kind=kind, content=content, locations=locations,
0308:             raw_input=arguments,
0309:         )
0310: 
0311:     if tool_name == "read_file":
0312:         path = arguments.get("path", "")
0313:         content = [acp.tool_content(acp.text_block(f"Reading {path}"))]
0314:         return acp.start_tool_call(
0315:             tool_call_id, title, kind=kind, content=content, locations=locations,
0316:             raw_input=arguments,
0317:         )
0318: 
0319:     if tool_name == "search_files":
0320:         pattern = arguments.get("pattern", "")
0321:         target = arguments.get("target", "content")
0322:         content = [acp.tool_content(acp.text_block(f"Searching for '{pattern}' ({target})"))]
0323:         return acp.start_tool_call(
0324:             tool_call_id, title, kind=kind, content=content, locations=locations,
0325:             raw_input=arguments,
0326:         )
0327: 
0328:     # Generic fallback
0329:     import json
0330:     try:
0331:         args_text = json.dumps(arguments, indent=2, default=str)
0332:     except (TypeError, ValueError):
0333:         args_text = str(arguments)
0334:     content = [acp.tool_content(acp.text_block(args_text))]
0335:     return acp.start_tool_call(
0336:         tool_call_id, title, kind=kind, content=content, locations=locations,
0337:         raw_input=arguments,
0338:     )
0339: 
0340: 
0341: def build_tool_complete(
0342:     tool_call_id: str,
0343:     tool_name: str,
0344:     result: Optional[str] = None,
0345:     function_args: Optional[Dict[str, Any]] = None,
0346:     snapshot: Any = None,
0347: ) -> ToolCallProgress:
0348:     """Create a ToolCallUpdate (progress) event for a completed tool call."""
0349:     kind = get_tool_kind(tool_name)
0350:     content = _build_tool_complete_content(
0351:         tool_name,
0352:         result,
0353:         function_args=function_args,
0354:         snapshot=snapshot,
0355:     )
0356:     return acp.update_tool_call(
0357:         tool_call_id,
0358:         kind=kind,
0359:         status="completed",
0360:         content=content,
```
