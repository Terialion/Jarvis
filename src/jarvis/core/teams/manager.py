"""Teammate manager — spawn named agents with file-based communication."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .message_bus import MessageBus


class TeammateManager:
    """Persistent named agent teammates stored in ``.jarvis/team/``.

    Each teammate runs as a daemon thread with its own agent loop.
    The team config is persisted as ``config.json``, and message inboxes
    are managed by the :class:`MessageBus`.
    """

    def __init__(
        self,
        team_dir: Path,
        bus: MessageBus,
        tool_registry: Any = None,
        model_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.dir = Path(team_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.bus = bus
        self.tool_registry = tool_registry
        self.model_client_factory = model_client_factory
        self.config = self._load_config()
        self.threads: dict[str, threading.Thread] = {}

    # ── config persistence ──────────────────────────────────────────

    def _config_path(self) -> Path:
        return self.dir / "config.json"

    def _load_config(self) -> dict[str, Any]:
        path = self._config_path()
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"team_name": "default", "members": []}

    def _save_config(self) -> None:
        self._config_path().write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _find_member(self, name: str) -> dict[str, Any] | None:
        for m in self.config.get("members", []):
            if m["name"] == name:
                return m
        return None

    def _set_status(self, name: str, status: str) -> None:
        member = self._find_member(name)
        if member:
            member["status"] = status
            self._save_config()

    # ── public API ──────────────────────────────────────────────────

    def spawn(
        self, name: str, role: str, prompt: str, autonomous: bool = False,
    ) -> dict[str, Any]:
        """Start a new teammate (or restart an existing one).

        If *autonomous* is True, uses the WORK/IDLE two-phase loop with
        auto-claiming from the persistent task board.
        """
        member = self._find_member(name)
        if member:
            member["role"] = role
            member["status"] = "working"
        else:
            member = {"name": name, "role": role, "status": "working"}
            self.config.setdefault("members", []).append(member)
        self._save_config()

        target = self._autonomous_loop if autonomous else self._teammate_loop
        thread = threading.Thread(
            target=target,
            args=(name, role, prompt),
            daemon=True,
        )
        thread.start()
        self.threads[name] = thread
        return {"ok": True, "name": name, "role": role, "status": "working"}

    def list_all(self) -> list[dict[str, Any]]:
        return list(self.config.get("members", []))

    def member_names(self) -> list[str]:
        return [m["name"] for m in self.config.get("members", [])]

    def shutdown_all(self) -> None:
        for name in list(self.threads):
            self.bus.send(
                "lead",
                name,
                "Shutting down team.",
                msg_type="shutdown_request",
            )
            self._set_status(name, "shutdown")

    # ── teammate loop ───────────────────────────────────────────────

    def _teammate_loop(self, name: str, role: str, prompt: str) -> None:
        """Core agent loop for a single teammate."""
        if self.model_client_factory is None:
            self._set_status(name, "idle")
            return

        try:
            model_client = self.model_client_factory()
        except Exception:
            self._set_status(name, "idle")
            return

        sys_text = (
            f"You are '{name}', role: {role}, working in team "
            f"'{self.config.get('team_name', 'default')}'. "
            "You have access to bash, read_file, write_file, "
            "send_message, and read_inbox tools. "
            "Read your inbox at the start of each step."
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": prompt},
        ]
        tools = self._teammate_tools()

        for _ in range(50):
            inbox = self.bus.read_inbox(name)
            for msg in inbox:
                if msg.get("type") == "shutdown_request":
                    self._set_status(name, "shutdown")
                    return
                messages.append({
                    "role": "user",
                    "content": f"<team-inbox>{json.dumps(msg, ensure_ascii=False)}</team-inbox>",
                })

            try:
                response = model_client.complete(messages, tools=tools)
            except Exception:
                break

            if response.finish_reason != "tool_use" or not response.tool_calls:
                break

            results: list[dict[str, Any]] = []
            for tc in response.tool_calls:
                output = self._exec(name, tc.name, tc.arguments)
                results.append({
                    "tool_use_id": tc.id,
                    "type": "tool_result",
                    "content": output,
                })
            messages.append({"role": "user", "content": json.dumps(results, ensure_ascii=False)})

        self._set_status(name, "idle")

    def _exec(self, sender: str, tool_name: str, args: dict[str, Any]) -> str:
        """Execute a teammate tool call."""
        if tool_name == "send_message":
            to = str(args.get("to") or "")
            content = str(args.get("content") or "")
            result = self.bus.send(sender, to, content)
            return json.dumps(result, ensure_ascii=False)

        if tool_name == "read_inbox":
            msgs = self.bus.read_inbox(sender)
            return json.dumps(msgs, ensure_ascii=False)

        if tool_name == "bash":
            import subprocess
            command = str(args.get("command") or "")
            if not command:
                return "Error: command required"
            try:
                proc = subprocess.run(
                    command, shell=True, capture_output=True, text=True,
                    timeout=60, cwd=str(Path.cwd()),
                )
                return proc.stdout or proc.stderr or "(no output)"
            except Exception as e:
                return f"Error: {e}"

        if tool_name == "read_file":
            from pathlib import Path as _Path
            file_path = str(args.get("path") or "")
            try:
                return _Path(file_path).read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return f"Error: {e}"

        if tool_name == "write_file":
            from pathlib import Path as _Path
            file_path = str(args.get("path") or "")
            content = str(args.get("content") or "")
            try:
                _Path(file_path).write_text(content, encoding="utf-8")
                return f"Wrote {file_path}"
            except Exception as e:
                return f"Error: {e}"

        return f"Unknown teammate tool: {tool_name}"

    def _autonomous_loop(self, name: str, role: str, prompt: str) -> None:
        """WORK/IDLE two-phase loop with auto-claiming from the task board."""
        from .autonomous import (
            IDLE_TIMEOUT,
            POLL_INTERVAL,
            claim_task,
            make_identity_block,
            scan_unclaimed_tasks,
        )
        from pathlib import Path as _Path

        tasks_dir = _Path(self.dir).parent / "tasks"

        if self.model_client_factory is None:
            self._set_status(name, "idle")
            return

        try:
            model_client = self.model_client_factory()
        except Exception:
            self._set_status(name, "idle")
            return

        team_name = self.config.get("team_name", "default")
        sys_text = (
            f"You are '{name}', role: {role}, team: {team_name}. "
            "Use the idle tool when you have no more work. "
            "You will automatically claim new tasks from the board."
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": sys_text},
            {"role": "user", "content": prompt},
        ]
        tools = self._teammate_tools() + [
            {
                "name": "idle",
                "description": "Signal that you have no more work to do.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "claim_task",
                "description": "Claim a task by its ID.",
                "input_schema": {
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                    "required": ["task_id"],
                },
            },
        ]

        while True:
            # ── WORK PHASE ──
            for _ in range(50):
                inbox = self.bus.read_inbox(name)
                for msg in inbox:
                    if msg.get("type") == "shutdown_request":
                        self._set_status(name, "shutdown")
                        return
                    messages.append({
                        "role": "user",
                        "content": f"<team-inbox>{json.dumps(msg, ensure_ascii=False)}</team-inbox>",
                    })

                try:
                    response = model_client.complete(messages, tools=tools)
                except Exception:
                    self._set_status(name, "idle")
                    return

                if response.finish_reason != "tool_use" or not response.tool_calls:
                    break

                idle_requested = False
                results: list[dict[str, Any]] = []
                for tc in response.tool_calls:
                    if tc.name == "idle":
                        idle_requested = True
                        results.append({
                            "tool_use_id": tc.id,
                            "type": "tool_result",
                            "content": "Entering idle phase.",
                        })
                    elif tc.name == "claim_task":
                        task_id = str(tc.arguments.get("task_id") or "")
                        output = claim_task(tasks_dir, task_id, name)
                        results.append({
                            "tool_use_id": tc.id,
                            "type": "tool_result",
                            "content": json.dumps(output, ensure_ascii=False),
                        })
                    else:
                        output = self._exec(name, tc.name, tc.arguments)
                        results.append({
                            "tool_use_id": tc.id,
                            "type": "tool_result",
                            "content": output,
                        })
                messages.append({"role": "user", "content": json.dumps(results, ensure_ascii=False)})
                if idle_requested:
                    break

            # ── IDLE PHASE ──
            self._set_status(name, "idle")
            resume = False
            polls = max(1, IDLE_TIMEOUT // max(POLL_INTERVAL, 1))
            for _ in range(polls):
                time.sleep(POLL_INTERVAL)
                inbox = self.bus.read_inbox(name)
                if inbox:
                    for msg in inbox:
                        if msg.get("type") == "shutdown_request":
                            self._set_status(name, "shutdown")
                            return
                        messages.append({
                            "role": "user",
                            "content": f"<team-inbox>{json.dumps(msg, ensure_ascii=False)}</team-inbox>",
                        })
                    resume = True
                    break

                unclaimed = scan_unclaimed_tasks(tasks_dir)
                if unclaimed:
                    task = unclaimed[0]
                    result = claim_task(tasks_dir, task["id"], name)
                    if not result.get("ok"):
                        continue
                    if len(messages) <= 3:
                        messages.insert(0, make_identity_block(name, role, team_name))
                    messages.append({
                        "role": "user",
                        "content": f"<auto-claimed>Task #{task['id']}: {task.get('subject', '')}</auto-claimed>",
                    })
                    resume = True
                    break

            if not resume:
                self._set_status(name, "shutdown")
                return
            self._set_status(name, "working")

    def _teammate_tools(self) -> list[dict[str, Any]]:
        """Restricted tool set available to teammates."""
        return [
            {
                "name": "bash",
                "description": "Run a shell command.",
                "input_schema": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
            {
                "name": "read_file",
                "description": "Read a file from the filesystem.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write content to a file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "send_message",
                "description": "Send a message to another teammate by name.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["to", "content"],
                },
            },
            {
                "name": "read_inbox",
                "description": "Read and drain your own inbox.",
                "input_schema": {"type": "object", "properties": {}},
            },
        ]
