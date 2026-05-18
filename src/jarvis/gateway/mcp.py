from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from time import perf_counter
from typing import Any
from uuid import uuid4

from .audit import GatewayAuditStore
from .channel_directory import ChannelDirectory
from .hooks import run_gateway_hooks
from .permissions import can_call_tool, filter_tools_for_profile, is_mutating_tool
from .schema import GatewayAuditRecord, McpCapability
from ..core.policy import get_approval_store
from ..store.memory_store import MemoryStore
from ..store.redaction import redact_for_persistence
from ..store import ThreadStore

SUPPORTED_MCP_PROTOCOL_VERSIONS = ["2025-06-18"]


def make_jsonrpc_result(request_id: str | int | None, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": redact_for_persistence(result)}


def make_jsonrpc_error(
    request_id: str | int | None,
    code: int,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {"code": int(code), "message": str(message)}
    if data is not None:
        payload["data"] = redact_for_persistence(data)
    return {"jsonrpc": "2.0", "id": request_id, "error": payload}


def validate_jsonrpc_request(payload: Any) -> tuple[bool, str | None]:
    if not isinstance(payload, dict):
        return False, "Request must be object"
    if payload.get("jsonrpc") != "2.0":
        return False, "jsonrpc must be '2.0'"
    if "method" not in payload:
        return False, "method is required"
    if not isinstance(payload.get("method"), str):
        return False, "method must be string"
    if "params" in payload and payload.get("params") is not None and not isinstance(payload.get("params"), dict):
        return False, "params must be object"
    return True, None


def _user_hash(user_id: str | None) -> str | None:
    if not user_id:
        return None
    return sha256(user_id.encode("utf-8")).hexdigest()[:16]


class MCPGatewayService:
    def __init__(
        self,
        *,
        channel_directory: ChannelDirectory,
        audit_store: GatewayAuditStore,
        thread_store: ThreadStore,
        memory_store: MemoryStore,
        benchmark_loader,
        agent_runner,
        coding_runner,
    ) -> None:
        self.channel_directory = channel_directory
        self.audit_store = audit_store
        self.thread_store = thread_store
        self.memory_store = memory_store
        self.benchmark_loader = benchmark_loader
        self.agent_runner = agent_runner
        self.coding_runner = coding_runner

    def capabilities(self) -> dict[str, Any]:
        return {
            "mcp_endpoint": "/api/mcp",
            "compatibility_level": "mcp_compatible_foundation",
            "canonical_wire_format": "jsonrpc_2_0",
            "supported_methods": [
                "initialize",
                "tools/list",
                "tools/call",
                "resources/list",
                "resources/read",
                "prompts/list",
                "prompts/get",
            ],
            "convenience_endpoints": [
                "/api/mcp/capabilities",
                "/api/mcp/run",
            ],
            "note": "/api/mcp/capabilities and /api/mcp/run are convenience endpoints, not canonical MCP wire format.",
        }

    def process_http(self, payload: Any, *, channel: str = "mock_mcp", user_id: str | None = None) -> tuple[int, Any]:
        if isinstance(payload, list):
            if not payload:
                return 400, make_jsonrpc_error(None, -32600, "Invalid Request", {"reason": "empty_batch"})
            responses: list[dict[str, Any]] = []
            for item in payload:
                status, response = self._process_one(item, channel=channel, user_id=user_id)
                if response is not None:
                    responses.append(response)
                if status >= 500:
                    return status, responses
            if not responses:
                return 204, None
            return 200, responses
        return self._process_one(payload, channel=channel, user_id=user_id)

    def _process_one(self, payload: Any, *, channel: str, user_id: str | None) -> tuple[int, dict[str, Any] | None]:
        if not isinstance(payload, dict):
            return 400, make_jsonrpc_error(None, -32600, "Invalid Request", {"reason": "request_object_required"})
        request_id = payload.get("id")
        ok, err = validate_jsonrpc_request(payload)
        if not ok:
            return 400, make_jsonrpc_error(request_id, -32600, "Invalid Request", {"reason": err})
        method = str(payload.get("method"))
        params = payload.get("params") or {}
        if request_id is None:
            # notification
            self._dispatch(method, params, channel=channel, user_id=user_id, request_id=None, notification=True)
            return 204, None
        try:
            result = self._dispatch(method, params, channel=channel, user_id=user_id, request_id=request_id, notification=False)
            return 200, make_jsonrpc_result(request_id, result)
        except ValueError as exc:
            message = str(exc)
            if message.startswith("METHOD_NOT_FOUND:"):
                return 404, make_jsonrpc_error(request_id, -32601, "Method not found", {"method": method})
            if message.startswith("INVALID_PARAMS:"):
                return 400, make_jsonrpc_error(request_id, -32602, "Invalid params", {"reason": message.split(":", 1)[1].strip()})
            if message.startswith("UNSUPPORTED_PROTOCOL:"):
                return 400, make_jsonrpc_error(request_id, -32602, "Invalid params", {"reason": message.split(":", 1)[1].strip()})
            return 500, make_jsonrpc_error(request_id, -32603, "Internal error", {"reason": message[:200]})
        except Exception:
            return 500, make_jsonrpc_error(request_id, -32603, "Internal error")

    def _dispatch(
        self,
        method: str,
        params: dict[str, Any],
        *,
        channel: str,
        user_id: str | None,
        request_id: str | int | None,
        notification: bool,
    ) -> dict[str, Any]:
        hook = run_gateway_hooks(method=method, params=params)
        if not hook.allowed:
            raise ValueError(f"INVALID_PARAMS:{hook.reason or 'blocked_by_hook'}")
        channel_spec = self.channel_directory.get_channel(channel)
        if channel_spec is None:
            raise ValueError("INVALID_PARAMS:unknown_channel")
        if not channel_spec.enabled:
            raise ValueError("INVALID_PARAMS:channel_disabled")
        profile = channel_spec.permissions_profile
        start = perf_counter()
        approvals: list[str] = []
        tool_names: list[str] = []
        resource_uris: list[str] = []
        prompt_names: list[str] = []
        status = "success"
        out: dict[str, Any] | str = {}
        error_code: int | None = None
        error_message: str | None = None
        try:
            if method == "initialize":
                protocol_version = str(params.get("protocolVersion") or "").strip()
                if not protocol_version:
                    raise ValueError("INVALID_PARAMS:protocolVersion is required")
                if protocol_version not in SUPPORTED_MCP_PROTOCOL_VERSIONS:
                    raise ValueError(f"UNSUPPORTED_PROTOCOL:{protocol_version}")
                out = {
                    "protocolVersion": protocol_version,
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                    "serverInfo": {"name": "jarvis", "version": "0.20.0"},
                }
            elif method == "tools/list":
                tools = [asdict(cap) for cap in self._tool_capabilities()]
                tools = filter_tools_for_profile(tools, profile)
                out = {"tools": tools}
            elif method == "tools/call":
                name = str(params.get("name") or "").strip()
                if not name:
                    raise ValueError("INVALID_PARAMS:name is required")
                if not can_call_tool(profile, name):
                    raise ValueError("INVALID_PARAMS:tool_not_allowed_for_channel")
                arguments = params.get("arguments")
                if arguments is not None and not isinstance(arguments, dict):
                    raise ValueError("INVALID_PARAMS:arguments must be object")
                arguments = arguments or {}
                tool_names.append(name)
                out = self._call_tool(name=name, arguments=arguments, channel=channel, profile=profile, approvals=approvals)
                status = "approval_required" if bool((out.get("structuredContent") or {}).get("status") == "approval_required") else "success"
            elif method == "resources/list":
                out = {"resources": self._resource_catalog()}
            elif method == "resources/read":
                uri = str(params.get("uri") or "").strip()
                if not uri:
                    raise ValueError("INVALID_PARAMS:uri is required")
                resource_uris.append(uri)
                out = {"contents": [self._read_resource(uri)]}
            elif method == "prompts/list":
                out = {"prompts": self._prompt_catalog()}
            elif method == "prompts/get":
                name = str(params.get("name") or "").strip()
                if not name:
                    raise ValueError("INVALID_PARAMS:name is required")
                prompt_names.append(name)
                args = params.get("arguments") or {}
                if not isinstance(args, dict):
                    raise ValueError("INVALID_PARAMS:arguments must be object")
                out = self._get_prompt(name=name, arguments=args)
            else:
                raise ValueError(f"METHOD_NOT_FOUND:{method}")
            return out
        except Exception as exc:
            status = "error"
            message = str(exc)
            if "METHOD_NOT_FOUND" in message:
                error_code = -32601
            elif "INVALID_PARAMS" in message or "UNSUPPORTED_PROTOCOL" in message:
                error_code = -32602
            else:
                error_code = -32603
            error_message = message[:220]
            raise
        finally:
            duration_ms = int((perf_counter() - start) * 1000)
            if not notification:
                self.audit_store.append(
                    GatewayAuditRecord(
                        audit_id=f"audit_{uuid4().hex[:12]}",
                        request_id=str(request_id),
                        channel=channel,
                        method=method,
                        user_id_hash=_user_hash(user_id),
                        client_name=str((params.get("clientInfo") or {}).get("name") or "") or None,
                        permissions_profile=profile,
                        redacted_input={"method": method, "params": redact_for_persistence(params)},
                        redacted_output=redact_for_persistence(out),
                        status=status,
                        approval_ids=approvals,
                        tool_names=tool_names,
                        resource_uris=resource_uris,
                        prompt_names=prompt_names,
                        error_code=error_code,
                        error_message=error_message,
                        duration_ms=duration_ms,
                    )
                )

    def _tool_capabilities(self) -> list[McpCapability]:
        return [
            McpCapability(
                name="agent.run",
                description="Run one Jarvis turn through AgentLoop.run_turn.",
                mutating=False,
                requires_approval=False,
                input_schema={
                    "type": "object",
                    "properties": {
                        "input": {"type": "string"},
                        "thread_id": {"type": "string"},
                    },
                    "required": ["input"],
                },
            ),
            McpCapability(
                name="coding.review",
                description="Review code without modifying files.",
                mutating=False,
                requires_approval=False,
                input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            ),
            McpCapability(
                name="coding.test",
                description="Run tests through Jarvis permissioned tool execution.",
                mutating=False,
                requires_approval=False,
                input_schema={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
            ),
            McpCapability(
                name="coding.fix",
                description="Create a patch plan and diff preview. Applying patches requires approval.",
                mutating=True,
                requires_approval=True,
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "issue": {"type": "string"}, "apply": {"type": "boolean"}},
                    "required": ["path"],
                },
            ),
        ]

    def _call_tool(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        channel: str,
        profile: str,
        approvals: list[str],
    ) -> dict[str, Any]:
        if name == "agent.run":
            text = str(arguments.get("input") or "").strip()
            if not text:
                raise ValueError("INVALID_PARAMS:input is required")
            thread_id = str(arguments.get("thread_id") or f"mcp_session_{uuid4().hex[:8]}")
            result = self.agent_runner(text=text, thread_id=thread_id)
            return {
                "content": [{"type": "text", "text": "Jarvis completed the requested turn."}],
                "isError": False,
                "structuredContent": {"agent_result": redact_for_persistence(result)},
            }
        if name in {"coding.review", "coding.test", "coding.fix"}:
            target = str(arguments.get("path") or arguments.get("command") or arguments.get("issue") or "").strip()
            if not target:
                raise ValueError("INVALID_PARAMS:path/command/issue is required")
            action = name.split(".", 1)[1]
            apply_changes = bool(arguments.get("apply", False))
            if name == "coding.fix" and profile == "strict" and apply_changes:
                req = get_approval_store().create_request(
                    tool_name="coding.fix",
                    arguments_preview={"path": target, "apply": True, "channel": channel},
                    risk_level="high",
                    reason="Mutating patch apply via MCP requires explicit approval.",
                    session_id=f"mcp_{channel}",
                )
                approvals.append(req.approval_id)
                return {
                    "content": [{"type": "text", "text": "Approval required before patch apply."}],
                    "isError": False,
                    "structuredContent": {
                        "status": "approval_required",
                        "approval_id": req.approval_id,
                        "action_summary": "Apply coding.fix patch",
                        "risk_level": "high",
                        "requested_tool": "coding.fix",
                        "channel": channel,
                    },
                }
            coding = self.coding_runner(action=action, target=target, apply=apply_changes)
            status = str((coding.get("result") or {}).get("stop_reason") or "")
            structured = {"coding_result": redact_for_persistence(coding)}
            if status == "approval_required":
                structured["status"] = "approval_required"
            return {
                "content": [{"type": "text", "text": f"coding.{action} finished with status {status or 'completed'}."}],
                "isError": False,
                "structuredContent": structured,
            }
        raise ValueError("METHOD_NOT_FOUND:tools/call")

    def _resource_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "uri": "jarvis://threads",
                "name": "Jarvis Threads",
                "description": "List persisted Jarvis threads.",
                "mimeType": "application/json",
            },
            {
                "uri": "jarvis://benchmarks/latest",
                "name": "Latest Benchmark Report",
                "description": "Latest redacted Jarvis benchmark report.",
                "mimeType": "application/json",
            },
            {
                "uri": "jarvis://memory/project/default",
                "name": "Project Memory",
                "description": "Redacted project memory.",
                "mimeType": "application/json",
            },
        ]

    def _read_resource(self, uri: str) -> dict[str, Any]:
        if uri == "jarvis://threads":
            data = [row.to_dict() for row in self.thread_store.list_threads(limit=50)]
            return {"uri": uri, "mimeType": "application/json", "text": json.dumps(redact_for_persistence(data), ensure_ascii=False)}
        if uri.startswith("jarvis://threads/"):
            thread_id = uri.replace("jarvis://threads/", "", 1).strip()
            if not thread_id:
                raise ValueError("INVALID_PARAMS:thread_id missing")
            data = {
                "thread": self.thread_store.get_thread(thread_id).to_dict() if self.thread_store.get_thread(thread_id) else None,
                "turns": [row.to_dict() for row in self.thread_store.get_recent_turns(thread_id, limit=20)],
                "background_only": True,
            }
            return {"uri": uri, "mimeType": "application/json", "text": json.dumps(redact_for_persistence(data), ensure_ascii=False)}
        if uri == "jarvis://benchmarks/latest":
            data = redact_for_persistence(self.benchmark_loader() or {})
            return {"uri": uri, "mimeType": "application/json", "text": json.dumps(data, ensure_ascii=False)}
        if uri.startswith("jarvis://memory/project/"):
            project_id = uri.replace("jarvis://memory/project/", "", 1).strip() or "default"
            data = {"project_id": project_id, "memory": self.memory_store.get_project_memory(project_id), "background_only": True}
            return {"uri": uri, "mimeType": "application/json", "text": json.dumps(redact_for_persistence(data), ensure_ascii=False)}
        raise ValueError("INVALID_PARAMS:unknown_resource_uri")

    def _prompt_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "jarvis.coding.review",
                "description": "Prompt template for reviewing code safely.",
                "arguments": [{"name": "path", "description": "File or directory to review.", "required": True}],
            },
            {
                "name": "jarvis.coding.fix",
                "description": "Prompt template for proposing a safe patch plan.",
                "arguments": [
                    {"name": "path", "description": "File or directory to fix.", "required": True},
                    {"name": "issue", "description": "Optional issue summary.", "required": False},
                ],
            },
            {
                "name": "jarvis.coding.test",
                "description": "Prompt template for running scoped tests safely.",
                "arguments": [{"name": "command", "description": "Scoped test command.", "required": True}],
            },
            {
                "name": "jarvis.web_research.verify_bug",
                "description": "Prompt template for web research bug verification.",
                "arguments": [{"name": "query", "description": "Bug query.", "required": True}],
            },
            {
                "name": "jarvis.memory.summarize_thread",
                "description": "Prompt template for summarizing a thread from historical memory.",
                "arguments": [{"name": "thread_id", "description": "Thread id.", "required": True}],
            },
        ]

    def _get_prompt(self, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        templates = {row["name"]: row for row in self._prompt_catalog()}
        if name not in templates:
            raise ValueError("INVALID_PARAMS:unknown_prompt")
        if name == "jarvis.coding.review":
            path = str(arguments.get("path") or "").strip()
            if not path:
                raise ValueError("INVALID_PARAMS:path is required")
            text = f"Review {path}. Do not modify files. Return issues, risks, and suggested patch plan only."
        elif name == "jarvis.coding.fix":
            path = str(arguments.get("path") or "").strip()
            if not path:
                raise ValueError("INVALID_PARAMS:path is required")
            issue = str(arguments.get("issue") or "").strip()
            text = f"Propose a safe patch plan for {path}." + (f" Issue: {issue}." if issue else "")
        elif name == "jarvis.coding.test":
            command = str(arguments.get("command") or "").strip()
            if not command:
                raise ValueError("INVALID_PARAMS:command is required")
            text = f"Run scoped tests with command: {command}. Respect approval and policy boundaries."
        elif name == "jarvis.web_research.verify_bug":
            query = str(arguments.get("query") or "").strip()
            if not query:
                raise ValueError("INVALID_PARAMS:query is required")
            text = f"Use web research evidence to verify bug claim: {query}."
        else:
            thread_id = str(arguments.get("thread_id") or "").strip()
            if not thread_id:
                raise ValueError("INVALID_PARAMS:thread_id is required")
            text = f"Summarize historical thread {thread_id}. Treat persisted memory as background only."
        return {
            "description": templates[name]["description"],
            "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
        }

