"""MCP client for connecting Jarvis to external MCP servers.

Supports stdio transport for launching and communicating with MCP server processes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .transport.stdio import StdioTransport


@dataclass
class MCPServerConnection:
    name: str
    transport: StdioTransport
    server_info: dict[str, Any] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)


class MCPClient:
    """Connect to external MCP servers and bridge their tools/resources/prompts.

    Usage::

        client = MCPClient()
        client.connect_stdio("my_server", ["python", "-m", "my_mcp_server"])
        tools = client.list_tools("my_server")
        result = client.call_tool("my_server", "some_tool", {"arg": "val"})
        client.disconnect("my_server")
    """

    def __init__(self) -> None:
        self._connections: dict[str, MCPServerConnection] = {}

    # ── connection management ──────────────────────────────────────────

    def connect_stdio(self, name: str, command: list[str]) -> dict[str, Any]:
        """Launch an MCP server via subprocess and perform initialize handshake."""
        if name in self._connections:
            raise ValueError(f"MCP server '{name}' is already connected.")

        transport = StdioTransport(command)
        transport.start()

        try:
            result = transport.send_request("initialize", {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "clientInfo": {"name": "jarvis", "version": "0.21.0"},
            })
        except Exception:
            transport.stop()
            raise

        server_info = result.get("serverInfo", {})
        conn = MCPServerConnection(name=name, transport=transport, server_info=server_info)

        # Discover tools
        try:
            tools_resp = transport.send_request("tools/list", {})
            conn.tools = tools_resp.get("tools", [])
        except Exception:
            conn.tools = []

        # Discover resources
        try:
            resources_resp = transport.send_request("resources/list", {})
            conn.resources = resources_resp.get("resources", [])
        except Exception:
            conn.resources = []

        # Discover prompts
        try:
            prompts_resp = transport.send_request("prompts/list", {})
            conn.prompts = prompts_resp.get("prompts", [])
        except Exception:
            conn.prompts = []

        # Send initialized notification
        transport.send_notification("notifications/initialized", {})

        self._connections[name] = conn
        return {
            "name": name,
            "server_info": server_info,
            "tool_count": len(conn.tools),
            "resource_count": len(conn.resources),
            "prompt_count": len(conn.prompts),
        }

    def disconnect(self, name: str) -> bool:
        """Disconnect and shut down an MCP server. Returns True if it was connected."""
        conn = self._connections.pop(name, None)
        if conn is None:
            return False
        conn.transport.stop()
        return True

    @property
    def server_names(self) -> list[str]:
        return sorted(self._connections.keys())

    # ── tool operations ────────────────────────────────────────────────

    def list_tools(self, name: str) -> list[dict[str, Any]]:
        conn = self._connections.get(name)
        if conn is None:
            raise ValueError(f"MCP server '{name}' not connected.")
        return list(conn.tools)

    def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        conn = self._connections.get(server_name)
        if conn is None:
            raise ValueError(f"MCP server '{server_name}' not connected.")
        return conn.transport.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        })

    def all_tools(self) -> list[dict[str, Any]]:
        """Return all tools from all connected servers, annotated with server name."""
        result: list[dict[str, Any]] = []
        for name, conn in self._connections.items():
            for tool in conn.tools:
                annotated = dict(tool)
                annotated["_mcp_server"] = name
                result.append(annotated)
        return result

    # ── resource operations ────────────────────────────────────────────

    def list_resources(self, name: str) -> list[dict[str, Any]]:
        conn = self._connections.get(name)
        if conn is None:
            raise ValueError(f"MCP server '{name}' not connected.")
        return list(conn.resources)

    def read_resource(self, server_name: str, uri: str) -> dict[str, Any]:
        conn = self._connections.get(server_name)
        if conn is None:
            raise ValueError(f"MCP server '{server_name}' not connected.")
        return conn.transport.send_request("resources/read", {"uri": uri})

    # ── prompt operations ──────────────────────────────────────────────

    def list_prompts(self, name: str) -> list[dict[str, Any]]:
        conn = self._connections.get(name)
        if conn is None:
            raise ValueError(f"MCP server '{name}' not connected.")
        return list(conn.prompts)

    def get_prompt(self, server_name: str, prompt_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        conn = self._connections.get(server_name)
        if conn is None:
            raise ValueError(f"MCP server '{server_name}' not connected.")
        return conn.transport.send_request("prompts/get", {
            "name": prompt_name,
            "arguments": arguments or {},
        })

    # ── lifecycle ──────────────────────────────────────────────────────

    def shutdown_all(self) -> None:
        for name in list(self._connections):
            self.disconnect(name)
