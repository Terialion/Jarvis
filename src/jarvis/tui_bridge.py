"""TUI Bridge — JSON-line protocol server for the Ink TUI.

Runs as a child process spawned by the Node/Ink TUI. Communicates via
newline-delimited JSON over stdin/stdout:

    stdin  ← TUI requests  (input, cancel, ask_user_response)
    stdout → TUI events    (init, chunk, done, ask_user)

Usage: python -m jarvis tui_bridge
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

from jarvis.agent.loop import AgentLoop
from jarvis.agent.types import ChatInput, ModelChunk


def _send_event(event: dict) -> None:
    """Write a JSON event line to stdout for the TUI to consume."""
    data = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def _read_request() -> dict | None:
    """Read a JSON request line from stdin. Blocks until a line arrives."""
    line = sys.stdin.buffer.readline().decode("utf-8", errors="replace")
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _get_git_branch(cwd: str) -> str:
    """Detect current git branch."""
    try:
        head_path = Path(cwd) / ".git" / "HEAD"
        if head_path.exists():
            ref = head_path.read_text().strip()
            if ref.startswith("ref: refs/heads/"):
                return ref[len("ref: refs/heads/"):]
    except Exception:
        pass
    return ""


def run_bridge() -> int:
    """Main entry point for the TUI bridge process."""
    cwd = str(Path.cwd())

    # Send init event so TUI knows we're ready
    _send_event({
        "type": "init",
        "model": "deepseek-v4-pro",
        "project_root": cwd,
        "git_branch": _get_git_branch(cwd),
        "permission_mode": "default",
    })

    # Create agent loop (shared across turns)
    try:
        loop = AgentLoop(
            project_root=cwd,
            permission_mode="workspace_write",
            auto_approve=True,
            max_steps=20,
            timeout_s=90,
        )
    except Exception as exc:
        _send_event({
            "type": "chunk",
            "data": {"kind": "text_delta", "text_delta": f"AgentLoop init failed: {exc}"},
        })
        _send_event({"type": "done", "finish_reason": "error"})
        traceback.print_exc(file=sys.stderr)
        return 1

    while True:
        req = _read_request()
        if req is None:
            break  # stdin closed → exit

        req_type = req.get("type", "")

        if req_type == "input":
            _handle_input(loop, req["text"], cwd)

        elif req_type == "cancel":
            pass

        elif req_type == "ask_user_response":
            pass

        elif req_type == "exit":
            break

    return 0


def _handle_input(loop: AgentLoop, text: str, cwd: str) -> None:
    """Run one agent turn and stream chunks to the TUI."""
    chat_input = ChatInput(
        text=text,
        cwd=cwd,
        session_id=None,
        metadata={"source": "jarvis.tui", "mode": "tui_ink"},
    )

    try:
        for chunk in loop.run_turn_stream(chat_input):
            _emit_chunk(chunk)
    except Exception as exc:
        _send_event({
            "type": "chunk",
            "data": {
                "kind": "text_delta",
                "text_delta": f"\n[Agent error: {exc}]",
            },
        })
        _send_event({
            "type": "done",
            "finish_reason": "error",
        })
        traceback.print_exc(file=sys.stderr)


def _get_attr(chunk: Any, name: str) -> str:
    """Get an attribute or dict value from a chunk, returning '' if missing."""
    if hasattr(chunk, name):
        return getattr(chunk, name) or ""
    if hasattr(chunk, "get"):
        return chunk.get(name, "")  # type: ignore[union-attr]
    return ""


def _emit_chunk(chunk: Any) -> None:
    """Convert an AgentLoop chunk to a TUI event and send it."""
    kind = _get_attr(chunk, "kind")

    data: dict = {"kind": kind}

    if kind == "text_delta":
        data["text_delta"] = _get_attr(chunk, "text_delta")

    elif kind == "reasoning_delta":
        data["reasoning_delta"] = _get_attr(chunk, "reasoning_delta")

    elif kind == "progress_delta":
        data["progress_delta"] = _get_attr(chunk, "progress_delta")

    elif kind == "tool_call_delta":
        data["tool_call_id"] = _get_attr(chunk, "tool_call_id")
        data["tool_name"] = _get_attr(chunk, "tool_name")
        data["tool_arguments_delta"] = _get_attr(chunk, "tool_arguments_delta")

    elif kind == "done":
        reason = _get_attr(chunk, "finish_reason")
        _send_event({"type": "done", "finish_reason": reason or "stop"})
        return

    _send_event({"type": "chunk", "data": data})


if __name__ == "__main__":
    sys.exit(run_bridge())
