"""JSON-RPC over stdio transport for MCP client connections."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


class StdioTransport:
    """Launch an MCP server process and communicate via JSON-RPC over stdin/stdout.

    Usage::

        transport = StdioTransport(["python", "-m", "my_mcp_server"])
        transport.start()
        result = transport.send_request("tools/list", {})
        transport.stop()
    """

    def __init__(self, command: list[str], *, idle_timeout: int = 60) -> None:
        self._command = list(command)
        self._idle_timeout = idle_timeout
        self._process: subprocess.Popen | None = None
        self._request_id = 0

    def start(self) -> None:
        if self._process is not None:
            return
        self._process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )

    def stop(self) -> None:
        proc = self._process
        if proc is None:
            return
        self._process = None
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.stdout.close()
        except Exception:
            pass
        try:
            proc.stderr.close()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)

    def send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request and return the result dict."""
        proc = self._process
        if proc is None:
            raise RuntimeError("Transport not started")
        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("Transport pipes not available")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }
        raw = json.dumps(request, ensure_ascii=False)
        try:
            proc.stdin.write(raw + "\n")
            proc.stdin.flush()
        except BrokenPipeError:
            raise RuntimeError(f"MCP server process exited unexpectedly. stderr: {self._read_stderr()}")

        try:
            line = proc.stdout.readline()
        except Exception:
            raise RuntimeError(f"Failed to read from MCP server. stderr: {self._read_stderr()}")

        if not line:
            raise RuntimeError(f"MCP server closed stdout. stderr: {self._read_stderr()}")

        try:
            response = json.loads(line.strip())
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid JSON response from MCP server: {line[:200]}")

        if "error" in response:
            err = response["error"]
            raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message', 'unknown')}")
        return response.get("result", {})

    def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        proc = self._process
        if proc is None or proc.stdin is None:
            return
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        try:
            proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            proc.stdin.flush()
        except BrokenPipeError:
            pass

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _read_stderr(self) -> str:
        proc = self._process
        if proc is None:
            return ""
        try:
            if proc.stderr is not None and proc.stderr.seekable():
                pos = proc.stderr.tell()
                text = proc.stderr.read()
                proc.stderr.seek(pos)
            else:
                text = ""
        except Exception:
            text = ""
        return (text or "")[:500]
