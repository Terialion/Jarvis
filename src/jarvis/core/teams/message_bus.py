"""JSONL inbox per teammate — append-only writes, drain-on-read."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

VALID_MSG_TYPES = frozenset({
    "message", "broadcast", "shutdown_request",
    "shutdown_response", "plan_approval_response",
})


class MessageBus:
    """File-based message bus where each teammate has a JSONL inbox.

    Messages are appended to the recipient's inbox file. Reading drains
    (empties) the file so each message is consumed exactly once.
    """

    def __init__(self, inbox_dir: Path) -> None:
        self.dir = Path(inbox_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def send(
        self,
        sender: str,
        to: str,
        content: str,
        msg_type: str = "message",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if msg_type not in VALID_MSG_TYPES:
            return {"ok": False, "error": f"invalid msg_type: {msg_type}"}

        msg: dict[str, Any] = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time(),
        }
        if extra:
            msg.update(extra)

        path = self.dir / f"{to}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

        return {"ok": True, "to": to, "msg_type": msg_type}

    def read_inbox(self, name: str) -> list[dict[str, Any]]:
        """Read and drain (empty) all messages for *name*."""
        path = self.dir / f"{name}.jsonl"
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return []
        msgs: list[dict[str, Any]] = []
        for line in text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msgs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        # Drain — truncate the file
        path.write_text("", encoding="utf-8")
        return msgs

    def broadcast(
        self,
        sender: str,
        content: str,
        teammates: list[str],
    ) -> dict[str, Any]:
        """Send *content* to all teammates except *sender*."""
        sent: list[str] = []
        for name in teammates:
            if name != sender:
                self.send(sender, name, content, msg_type="broadcast")
                sent.append(name)
        return {"ok": True, "sent_to": sent}
